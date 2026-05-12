# start.sh wrapper ハング修正 (ssh -f ローカル fd 継承)

## Context

前タスクのレポート [`report/2026-05-12_105909_llama_down_unlock_order_fix.md`](../../projects/llm-server-ops/report/2026-05-12_105909_llama_down_unlock_order_fix.md) の「引き続き残る制約」として明記された wrapper ハング問題を解消する。さらに先行する [`report/2026-05-12_051827_llama_up_down_scripts.md`](../../projects/llm-server-ops/report/2026-05-12_051827_llama_up_down_scripts.md) でも 3 サイクル全てで観測されており、回避策として `TaskStop` 強制終了を必要としていた。

### 問題

`.claude/skills/llama-server/scripts/start.sh` の 281, 284, 288 行で `ssh -f` を使ってリモートに `llama-server` / `ttyd` をバックグラウンド起動しているが、SSH クライアントプロセスが**呼び出し元の stdout/stderr fd を継承したまま背景化**する。`llama-up.sh | tee log.txt` のようにパイプライン経由で呼ばれると、`tee` が SSH クライアントの保持する fd 由来で EOF を受け取れず、永続ハングする。

リモート側は既に `< /dev/null > /tmp/llama-server.log 2>&1 < /dev/null &` でリダイレクト済みだが、これはリモートシェル内の fd 制御であり、**ローカル側 SSH クライアント自身の fd には作用しない**。

### 目的

- `tee` などパイプライン経由でも `llama-up.sh` がハングせず終了する
- 前タスクの「TaskStop で回避」という ad-hoc 対処を不要にする
- 既存の `ssh -f` の「リモートコマンド起動完了まで return しない」保証は維持する

## 修正対象ファイル

- `.claude/skills/llama-server/scripts/start.sh` (281, 284, 288 行)
- `.claude/skills/llama-server/SKILL.md` (既知制約セクションがあれば更新。現状なし→末尾の制約一覧に追記検討)
  - 確認: 現時点で `ssh -f` / `wrapper` / `tee` 関連の記述は SKILL.md に存在しない (grep 結果)。必要なら「動作」セクションに 1 行注記する程度に留める

## 修正内容

各 `ssh -f "$SERVER" "..."` の末尾に **`</dev/null >/dev/null 2>&1`** を付与。SSH クライアントプロセスの stdin/stdout/stderr を `/dev/null` に向けることで、親プロセス (tee) との fd 継承を遮断する。

### 修正 diff (概念)

```diff
-ssh -f "$SERVER" "cd ~/llama.cpp && nohup bash -c '$LAUNCH_CMD' > /tmp/llama-server.log 2>&1 < /dev/null &"
+ssh -f "$SERVER" "cd ~/llama.cpp && nohup bash -c '$LAUNCH_CMD' > /tmp/llama-server.log 2>&1 < /dev/null &" </dev/null >/dev/null 2>&1

-ssh -f "$SERVER" "nohup ttyd --port 7682 --writable bash -c 'tail -f /tmp/llama-server.log' > /dev/null 2>&1 < /dev/null &"
+ssh -f "$SERVER" "nohup ttyd --port 7682 --writable bash -c 'tail -f /tmp/llama-server.log' > /dev/null 2>&1 < /dev/null &" </dev/null >/dev/null 2>&1

-ssh -f "$SERVER" "nohup ttyd --port 7681 nvtop > /dev/null 2>&1 < /dev/null &"
+ssh -f "$SERVER" "nohup ttyd --port 7681 nvtop > /dev/null 2>&1 < /dev/null &" </dev/null >/dev/null 2>&1
```

### 副作用と緩和策

- **副作用**: SSH 接続失敗 (認証エラー、ホスト到達不能、リモートシェル構文エラー) の stderr が `/dev/null` に飲まれる
- **緩和**: 起動失敗は後段の `wait-ready.sh` の `/health` 5xx/タイムアウトで検出される。診断時はリモートの `/tmp/llama-server.log` を `ssh "$SERVER" "cat /tmp/llama-server.log"` で確認可能

### 適用範囲外

- `start.sh` 内の `ssh -f` を使わない通常 `ssh` 呼び出し (278 行 ttyd 既存プロセス kill、287 行 nvtop kill 等) は対象外
- `stop.sh` / `wait-ready.sh` / `llama-up.sh` / `llama-down.sh` / `gpu-server` 配下スクリプトは無変更
- アーキテクチャ変更 (`ssh -f` → `ssh -n + nohup &`) は採用しない (起動完了タイミング保証を失うリスク)

## 検証

### 静的検証

1. `bash -n .claude/skills/llama-server/scripts/start.sh` で構文チェック
2. `git diff --stat` で `start.sh` 1 ファイルのみ変更されていることを確認
3. `git diff .claude/skills/llama-server/scripts/start.sh` で意図通りの差分を目視確認

### 実機検証 (t120h-p100)

実機テストは `gpu-server` Skill を使ってロック管理する。

**前提取得フェーズ**:
1. `gpu-server` Skill 経由で `t120h-p100` ロック取得 (`lock.sh t120h-p100`)
2. 現状確認:
   - `power.sh t120h-p100 status` → On/Off 判定
   - 電源 On なら `curl -sf http://10.1.4.14:8000/health` で起動状況確認

**ベースライン状態調整**:
- 電源 On かつ llama-server 起動中の場合: 一旦 `llama-down.sh` で停止 (修正済み Step 順序の動作確認も兼ねる)
- 電源 Off または llama-server 未起動の場合: そのまま次へ

**ハング再現性テスト**:
- 修正版 `llama-up.sh` を `tee` 経由で **TaskCreate でバックグラウンド実行**:
  ```bash
  .claude/skills/llama-server/scripts/llama-up.sh 2>&1 | tee /tmp/wrapper_hang_test.log
  ```
- 期待挙動: `==> 起動完了` 出力後、即座に `tee` も EOF を受け取って終了 (タスクが `completed` 状態に遷移)
- 修正前との比較: 前タスクでは同条件で `tee` がハングし TaskStop を要した。今回は `TaskStop` 不要で自然終了することを確認する
- タイミング目安:
  - 既起動 (冪等スキップ) の場合: 数秒で完了
  - 電源 Off からの新規起動: ~15 分 (電源 ON + SSH 待機 + ビルド + モデルロード)
- `curl http://10.1.4.14:8000/health` で `{"status":"ok"}` を確認

**クリーンアップ**:
- `llama-down.sh` で停止 (自分ロック保持なので Step 3 unlock も自動実行される)
- ロック解放確認 (`gpu-server/scripts/lock-status.sh` 等で `available` 状態)

### 受け入れ基準

| # | 項目 | 基準 |
|---|------|------|
| 1 | 構文 | `bash -n` PASS |
| 2 | 変更範囲 | `start.sh` のみ変更 |
| 3 | tee 経由実行 | TaskStop 不要で自然終了 |
| 4 | 起動成功 | `/health` → 200 |
| 5 | 既存挙動 | `==> llama-server をバックグラウンドで起動しました` 等の echo は維持 |
| 6 | 停止 | `llama-down.sh` EC=0 |

## レポート作成

CLAUDE.md の規約に従い、レポートを作成する。

- **ファイル名**: `report/YYYY-MM-DD_HHMMSS_wrapper_hang_fix.md` (HHMMSS は `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得)
- **必須セクション**: 前提・目的 / 環境情報 / 修正内容 / 再現方法 / 実施結果 (静的検証・実機検証) / 残課題 / 参考リンク
- **添付**: プランファイル (`/home/ubuntu/.claude/plans/report-2026-05-12-105909-llama-down-unlo-bubbly-book.md` を `report/attachment/<basename>/plan.md` にコピー)、ハング再現テストログ
- **クロスリンク**: 前タスク 2 本 (`2026-05-12_051827_llama_up_down_scripts.md`, `2026-05-12_105909_llama_down_unlock_order_fix.md`) へのリンクを「参考」セクションに記載
- **タイトル**: 50 字以内、簡潔に (例: `start.sh wrapper ハング修正 (ssh -f fd リダイレクト)`)

## 注意事項

- GPU サーバ操作は `gpu-server` Skill 経由 (ロック管理必須、CLAUDE.md 規約)
- スクリプトはプロジェクトルートからの相対パス (`.claude/skills/...`) で実行 (CLAUDE.md 規約)
- 実機テスト中 `llama-up.sh` ハングを TaskStop で潰さないこと (ハング = 修正失敗の証拠なので観察優先)
