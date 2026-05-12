# llama-server 統合スクリプト (llama-up.sh / llama-down.sh) 追加

- **実施日時**: 2026年5月12日 05:18 JST

## 添付ファイル

- [実装プラン (実機検証フェーズ含む最終版)](attachment/2026-05-12_051827_llama_up_down_scripts/plan.md)
- [Cycle 1 V1 ログ (電源 OFF → ON 起動)](attachment/2026-05-12_051827_llama_up_down_scripts/verification/cycle1_v1_llama-up.log)
- [Cycle 1 V2 ログ (既起動冪等性)](attachment/2026-05-12_051827_llama_up_down_scripts/verification/cycle1_v2_llama-up-idempotent.log)
- [Cycle 1 V4 ログ (他者ロック / --force)](attachment/2026-05-12_051827_llama_up_down_scripts/verification/cycle1_v4_other-lock-then-force.log)
- [Cycle 2 V3 setup ログ (再起動)](attachment/2026-05-12_051827_llama_up_down_scripts/verification/cycle2_v3_setup_llama-up.log)
- [Cycle 2 V3 本体ログ (自分ロック停止)](attachment/2026-05-12_051827_llama_up_down_scripts/verification/cycle2_v3_own-lock-stop.log)
- [Cycle 3 V5 setup ログ (再起動)](attachment/2026-05-12_051827_llama_up_down_scripts/verification/cycle3_v5_setup_llama-up.log)
- [Cycle 3 V5 本体ログ (未ロック停止)](attachment/2026-05-12_051827_llama_up_down_scripts/verification/cycle3_v5_unlocked-stop.log)

## 前提・目的

- **背景**: opencode フォーク（別 Claude セッションで作業中）の README.md に「LLM サーバの起動」セクションを追加したところ、`power.sh status → power.sh on → ttyd-gpu.sh → start.sh → wait-ready.sh` の 5 ステップが冗長すぎる、という指摘を受けた。
- **目的**: 「電源 OFF 判断 → GPU サーバ起動 → llama-server 起動」を 1 コマンドで実行できる統合スクリプトを `llama-server` スキルに追加し、opencode 側 README から 1 行で呼び出せる状態にする。停止側も同様に統合する。
- **方針**: 既存スクリプト（`power.sh` / `start.sh` / `stop.sh` / `wait-ready.sh` / `lock.sh` / `unlock.sh` / `lock-status.sh`）の中身・引数仕様は **一切変更せず**、薄いラッパーに留める。

## 環境情報

- リポジトリ: `/home/ubuntu/projects/llm-server-ops` (master ブランチ)
- 対象スキル: `.claude/skills/llama-server/` および `.claude/skills/gpu-server/`
- 実行ホスト hostname: `aws-mmns-generic`（`-` を含むので session_id の hostname 抽出で要注意）

## 追加・変更ファイル

| ファイル | 種別 | 説明 |
|----------|------|------|
| `.claude/skills/llama-server/scripts/llama-up.sh` | 新規 (3343 B, 実行ビット付与) | 起動統合スクリプト |
| `.claude/skills/llama-server/scripts/llama-down.sh` | 新規 (3718 B, 実行ビット付与) | 停止統合スクリプト |
| `.claude/skills/llama-server/SKILL.md` | +43 行 | 「## 統合スクリプト（推奨）」セクションを追加（先頭推奨配置） |

既存スクリプトの差分は **空**（受け入れ基準 5 を満たす）。

## llama-up.sh 仕様

**引数**: `[server] [hf-model] [mode] [fit-ctx]`（全省略可）

**デフォルト**: `t120h-p100` / `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M` / `fit` / 空

**フロー**:

1. `power.sh <server> status` で電源状態を確認（`grep -oE 'On|Off' | tail -1` でパース）
2. `Off` の場合: `power.sh <server> on` → `ssh -o ConnectTimeout=5 -o BatchMode=yes <server> true` を 5 秒間隔 × 60 回（最大 5 分）でポーリング
3. `ssh -G <server> | grep '^hostname '` で IP 解決 → `curl -sf -m 5 http://<ip>:8000/health` で既起動チェック。200 応答なら冪等スキップで `exit 0`
4. `start.sh <server> <hf-model> <mode> [fit-ctx]` → `wait-ready.sh <server> <hf-model> <mode> [fit-ctx]`

`FIT_CTX` 空文字は quote なしで完全省略させ、`start.sh` / `wait-ready.sh` のプロファイル既定値（Qwen3.5-122B-A10B=131072、その他=8192）に委譲する。

## llama-down.sh 仕様

**引数**: `[server] [--force]`

**デフォルト**: `t120h-p100`

**フロー**:

1. `lock-status.sh <server>` の出力をパースしロック保持者を判定
   - `UNREACHABLE` → `exit 1`
   - `: available` → 警告のみで継続（`OWN_LOCK` 空）
   - `: LOCKED` → `Holder:` 行から session_id を抽出、hostname 部分が `$(hostname)` と一致するかで自分/他者判定
     - 自分保持 → `OWN_LOCK=<session_id>`
     - 他者保持 + `--force` なし → `exit 1`
     - 他者保持 + `--force` あり → 警告のみで継続（`OWN_LOCK` 空のまま）
2. `stop.sh <server>`（失敗時も警告のみで継続）
3. `power.sh <server> off`（失敗時も警告のみで継続）
4. `OWN_LOCK` が非空の場合のみ `unlock.sh <server> "$OWN_LOCK"`

### hostname 抽出ロジック

`hostname` は `aws-mmns-generic` のように `-` を含むため `${HOLDER%%-*}` だと先頭の `aws` だけになる。`lock.sh` の自動生成 session_id 形式 `<hostname>-<pid>-<timestamp>` の **末尾 2 セグメントが固定** であることを利用し、`%-*` を 2 段適用して hostname 部分のみ残す:

```bash
STRIPPED="${HOLDER%-*}"          # 末尾の -timestamp を除去
HOLDER_HOST="${STRIPPED%-*}"     # 末尾の -pid を除去 → hostname 部分
```

実機検証結果:

| 入力 session_id | 抽出された hostname |
|-----------------|---------------------|
| `aws-mmns-generic-12345-20260512_120000` | `aws-mmns-generic` |
| `simple-99-19700101_000000` | `simple` |
| `a-b-c-d-1-2` | `a-b-c-d` |

## 再現方法（実装手順）

```bash
# 1. llama-up.sh / llama-down.sh を作成（実装は .claude/skills/llama-server/scripts/ 配下）
chmod +x .claude/skills/llama-server/scripts/llama-up.sh
chmod +x .claude/skills/llama-server/scripts/llama-down.sh

# 2. SKILL.md に「## 統合スクリプト（推奨）」セクションを「## start.sh + ttyd-gpu.sh + wait-ready.sh の使い方」の直前に挿入

# 3. 構文チェック
bash -n .claude/skills/llama-server/scripts/llama-up.sh
bash -n .claude/skills/llama-server/scripts/llama-down.sh

# 4. 既存スクリプト未変更の確認
git diff --stat \
  .claude/skills/llama-server/scripts/{start,stop,wait-ready}.sh \
  .claude/skills/gpu-server/scripts/{power,lock,unlock,lock-status}.sh
# → 空であること
```

## 実施結果

### 静的検証

- `bash -n` 構文チェック: **PASS**（両スクリプト）
- 実行ビット: 0755（両スクリプト）
- 既存スクリプト diff: **空**（受け入れ基準 5 達成）
- SKILL.md diff: +43 行 0 削除（既存内容は無変更）
- hostname 抽出ロジック実機検証: PASS（`-` を含むケースで `aws-mmns-generic` を正しく抽出）

### 動作検証（実機実施）

**検証日時**: 2026 年 5 月 12 日 08:21 〜 09:17 JST（約 56 分）

**検証環境**:
- 対象サーバ: `t120h-p100` (10.1.4.14, NVIDIA P100 ×4, 64 GB VRAM)
- 検証モデル: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M` モード `fit` (128k ctx, B14b OT, Phase U-6 プロファイル)
- 実行ホスト: `aws-mmns-generic`
- 初期状態: 電源 OFF, ロックなし
- llama.cpp バージョン: `1ec7ba0c1` (Cycle 1 で fast-forward update→フルビルド、Cycle 2/3 は差分なし)

#### 検証結果サマリ

| ケース | 検証内容 | 結果 | 所要時間 | 備考 |
|--------|---------|------|----------|------|
| V1 | 電源 OFF → ON 起動 | **PASS** | 約 17 分 | power on→SSH 接続 100 秒→ビルド (キャッシュなしフルビルド)→モデルロード→wait-ready 35/60 (175 秒) |
| V2 | 既起動時冪等性 | **PASS** | 5 秒 | `/health` 200 検出で `start.sh` 未呼出、即 `exit 0` |
| V4 part1 | 他者ロックで中断 | **PASS** | < 5 秒 | `exit 1`、ロック残存、サーバ稼働継続を確認 |
| V4 part2 | `--force` で強制停止 | **PASS** | 39 秒 | 警告のみ続行、stop+off 完了、ロック残存（他者ロックは touchしない） |
| V3 | 自分ロック停止 | **PASS with caveat** | 37 秒 | 「自分のロック」検出 / stop / power off は成功。**最後の `unlock.sh` で SSH 接続失敗** (`llama-down.sh EC=3`) |
| V5 | 未ロック停止 | **PASS** | 36 秒 | 「ロックなしで停止します」警告で継続、stop+off+解放スキップ、`EC=0` |

#### 重要な観測

**1. V3 で発覚した設計上の問題（要改修）**:
`llama-down.sh` のフロー Step 3 (`power.sh off`) → Step 4 (`unlock.sh`) の順序では、power off コマンド送信直後に OS がシャットダウン進行中になるため、Step 4 の `unlock.sh` の SSH 接続が失敗する。

```
==> [3/4] t120h-p100 の電源を OFF にします...
t120h-p100: off コマンドを送信しました (ResetType: GracefulShutdown)
==> [4/4] ロックを解放します...
Error: SSH connection to t120h-p100 failed
llama-down.sh EC=3
```

機能的には「自分のロック検出 → stop → off コマンド送信」までは正しく動作するが、ロックが GPU サーバ上の filesystem に残ってしまう。実用上は GPU サーバの `/tmp` が tmpfs であれば次回起動時にロックがクリアされる（実機 t120h-p100 で V5 setup 時に確認: `available` 状態）が、ロック設計の本来の意図とは異なる。

**推奨改修**: `llama-down.sh` のフロー順序を「stop → unlock → off」または「stop → off コマンド送信と unlock の並行実行」に変更する。`unlock.sh` を `power.sh off` の **前** に移動すれば、SSH 接続が生きている間に確実に解放できる。

**2. wrapper の tee close 待ちハング**:
`llama-up.sh` 本体は `==> 起動完了` で正常終了するが、`ssh -f` で起動した `ttyd` (port 7681/7682) のファイルディスクリプタを SSH クライアントが継承しているため、呼び出し側の `tee` が EOF を受け取れずハングする現象を 3 サイクル全てで観測。これは `llama-server` スキル既存の `start.sh` の `ssh -f` 起動パターンに由来し、本タスクの範疇外。回避には `ssh -f` 起動を `ssh -n` + `nohup ... &` に置き換えるか、`ssh ... </dev/null` + `&` の組み合わせを試す必要がある。

`llama-up.sh` を直接実行する場合（バックグラウンドラップなし）には影響しない可能性が高い。

**3. 既起動冪等スキップの効果**:
V2 の所要時間 5 秒は、ビルド・モデルロードを完全にスキップした結果。同一サーバを再起動せずに重複起動を防ぐ用途で有効。

**4. hostname 抽出ロジックの実機確認**:
Cycle 2 V3 で取得した session_id `aws-mmns-generic-2685601-20260512_085946` から、`%-*` 2 段適用で `aws-mmns-generic` を正しく抽出し、`$(hostname)` と一致判定して「自分のロック」フローに入ることを確認 (`自分のロック (holder=aws-mmns-generic-2685601-20260512_085946) → 停止後に解放します`)。

#### 検証フローの実行記録

3 サイクル構成で実施:

- **Cycle 1** (08:21 〜 08:42, 約 20 分): V1 (OFF→ON 起動) → V2 (冪等性) → V4 (他者ロック / --force)
- **Cycle 2** (08:59 〜 09:00, 約 1 分※ setup 別途約 14 分): 強制 unlock 前処理 → 自分ロック取得 → V3 (自分ロック停止)
- **Cycle 3** (09:16 〜 09:17, 約 1 分※ setup 別途約 14 分): V5 (未ロック停止)

各サイクル詳細ログは「## 添付ファイル」セクションのリンクを参照。

## 既知の制約

- **電源 ON 後の OS 起動失敗**: SSH 疎通待ち 5 分でタイムアウト → `exit 1`。BMC レベル ON / OS hang 状態をユーザに通知する設計。
- **`/health` が 200 だが API 異常**: 設計上「200 のみ既起動」とみなし `start.sh` をスキップ。500/503 の場合は通常フロー継続するが、`start.sh` の既存プロセスチェック（同名プロセス検出で `exit 1`）で停止する。
- **`stop.sh` 失敗時の挙動**: 警告のみで `power.sh off` へ続行（ユーザ確認済み・推奨案）。電源 OFF すれば結果的にプロセスも止まる。
- **`power.sh off` 後の `unlock.sh` 失敗（実機検証で確認）**: 現状のフロー順序では Step 4 (`unlock.sh`) が Step 3 (`power.sh off`) の後にあるため、自分ロック保持時に SSH 接続が切れて `EC=3` で終了する。GPU サーバの `/tmp` が tmpfs なら次回起動時にロックが消えるため実害は小さいが、設計改修（unlock を power off の前に移動）が推奨される。
- **ヘルスチェックと他者 start のレース**: ロックの責任範囲のため考慮外。
- **`ssh -f` 起動の wrapper ハング**: `llama-up.sh` を `tee` などパイプライン経由で呼ぶと、`ttyd` プロセスの fd 継承により呼び出し側がハングする。直接実行（パイプなし）では影響しない見込み。`llama-server` スキル既存の `start.sh` 起因。

## 今後の改修推奨

1. **`llama-down.sh` の Step 順序変更（優先）**: `unlock.sh` を `power.sh off` の前に移動。修正案:
   ```
   Step 1: lock 検証
   Step 2: stop.sh
   Step 3: unlock.sh (自分保持時のみ)   ← 移動
   Step 4: power.sh off
   ```
   または並行実行: power off コマンド送信と unlock を並行 (`&` で背景化)。

2. **`start.sh` の `ssh -f` を `ssh -n + nohup &` 化**: パイプライン下で呼ばれた際の fd 継承ハングを回避。本タスク範囲外、別途検討。

## 参考

- opencode フォーク側 Claude セッションからの引き継ぎ依頼（README.md 「LLM サーバの起動」セクション短縮目的）
- プラン: [attachment/2026-05-12_051827_llama_up_down_scripts/plan.md](attachment/2026-05-12_051827_llama_up_down_scripts/plan.md)
