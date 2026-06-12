# llama-server スキル ttyd 起動の信頼性向上

- **実施日時**: 2026年6月10日 21:39 (JST)

## 添付ファイル

- [実装プラン](attachment/2026-06-10_213920_ttyd_startup_reliability/plan.md)

## 前提・目的

- **背景**: opencode プロジェクトの Claude が t120h-p100 で llama-server を起動した際、ttyd（7681 GPU監視 / 7682 ログ閲覧）が両方とも起動していない障害が発生した。調査の結果、これは単発のミスではなく、llama-server スキルの ttyd 起動まわりの構造的欠陥に起因することが判明した。
- **目的**: ttyd 起動を単一の冪等スクリプトに集約し、Claude がどの経路で起動しても ttyd が自動的に担保され、落ちていれば必ず表面化する状態にする。「Claude が ttyd 起動を忘れる／silent fail する」余地そのものを無くす。
- **前提条件**: 変更対象はローカルのスキルスクリプト群（GPU サーバには触れない）。実機検証はユーザの GPU サーバ他タスクと競合するため、本レポート時点では未実施（依頼後に実施予定）。

## 環境情報

- 対象サーバ（運用先）: t120h-p100 (10.1.4.14) / mi25 (10.1.4.13) / t120h-m10
- 変更対象: `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/` 配下のスクリプトと SKILL.md、および `.claude/settings.local.json`
- ブランチ: master

## 問題分析（根本原因）

調査で判明した 4 つの構造的欠陥:

1. **ttyd 起動ロジックが 3 箇所に重複・不整合** — `start.sh`（7681/7682 両方）と `ttyd-gpu.sh`（7681 のみ）。TERM ラップの有無・kill 対象パターンが揃っていない。
2. **「llama-server は稼働中だが ttyd だけ落ちている」状態を立て直す経路が無い**:
   - `llama-up.sh` は `/health` 200 で冪等 early-exit (`exit 0`) し start.sh を呼ばない → ttyd 起動に到達しない。
   - `start.sh` は既存 llama-server 検出で `exit 1` → ttyd 起動行に到達しない。
   - `stop.sh` / `llama-down.sh` は ttyd を `pkill` するが、何らかの理由で llama-server だけ残ると「本体稼働・ttyd 全滅」になる。
   - 今回の障害は上記いずれの経路でも起こりうる。証拠から単一主因は特定できないが、本変更は**どの経路で入っても ttyd を担保する**ことで全ケースを一括解消する。
3. **検証ステップが無い** — `wait-ready.sh` は Discord 通知に 7681/7682 URL を載せるが LISTEN 確認はせず、ttyd が落ちていても気付けない（silent fail）。
4. **nvtop の TERM バグ** — `ttyd --port 7681 nvtop` を直起動すると子に TERM が渡らず、nvtop(ncurses) が `Error opening terminal: unknown.` で即終了し、ttyd は LISTEN するが画面は死ぬ。`bash -c 'TERM=xterm-256color exec nvtop'` で正常動作することを実機で確認済み。

## 実施した変更

| # | ファイル | 変更内容 |
|---|---------|---------|
| 1 | `scripts/ttyd-up.sh`（新規） | 7681/7682 を冪等に kill→ログ touch→TERM ラップ再起動→LISTEN 検証する集約スクリプト。検証失敗でも自前 WARNING を出して **常に exit 0**（ttyd は監視用途で本体推論に無関係なため起動全体は止めない）。 |
| 2 | `scripts/start.sh` | インライン ttyd/nvtop 起動ブロック（旧 323–334行）を削除し、llama-server 起動直後に `ttyd-up.sh` 呼び出し 1 行へ集約。 |
| 3 | `scripts/ttyd-gpu.sh` | 後方互換のため残しつつ、本体を `exec ttyd-up.sh` の薄いラッパー化（SERVER バリデーション + SCRIPT_DIR 解決を追加）。 |
| 4 | `scripts/llama-up.sh` | health-200 の冪等 early-exit 経路でも `exit 0` の前に `ttyd-up.sh` を呼び、既起動時の ttyd を担保（本障害の本丸修正）。 |
| 5 | `scripts/wait-ready.sh` | Discord 通知前に 7681/7682 の LISTEN を `ss` で確認し、落ちているポートには本文で「(未起動)」を付記（silent fail の防止。再起動はしない）。 |
| 6 | `scripts/install-global.sh` / `.claude/settings.local.json` | `ttyd-up.sh` を PERM_SCRIPTS と allow に追加。 |
| 7 | `SKILL.md` | 手動 3 ステップ記述を `ttyd-up.sh` 統一の 2 ステップへ更新。start.sh / llama-up.sh / wait-ready.sh の動作説明に ttyd 担保・LISTEN 検証を反映。`ttyd-up.sh の動作`セクションを新設。 |

### 設計レビューで解消した論点

- **死にコードの矛盾**: 「ttyd-up.sh は失敗しても exit 0」と llama-up.sh 側の `|| echo WARNING` は両立しない（exit 0 なら分岐が発火しない）。warn 表示を ttyd-up.sh 側に一元化し、呼び出し側の `||` を排した。
- **投機実装の排除**: 消費側のない `TTYD_xxx=ok` 機械可読 stdout 契約は設けない。
- **7682 のログファイル依存の穴**: `ttyd-up.sh` で `touch /tmp/llama-server.log` してから 7682 を起動し、llama-server 未起動でも画面が死なないよう堅牢化。
- **mi25 の TERM ラップ**: `watch -n 1 rocm-smi` も terminfo を使うため、nvtop と統一して `bash -c 'TERM=xterm-256color exec ...'` でラップ。

全スクリプトは `bash -n` で構文チェック済み、`settings.local.json` は JSON 妥当性を確認済み。

## 実機検証結果（2026年6月13日 06:13 JST, t120h-p100）

電源 OFF だった t120h-p100 を iLO5 で起動・ロック取得し、下記「再現方法」の手順 1〜8 を実機で実施した（手順 9 の mi25 は今回対象外）。

### 検証中に発見・修正した重大バグ: `pkill -f` の自己マッチによるセッション自殺

`ttyd-up.sh` を初回実行したところ、最初の echo 直後に **ssh が exit 255 を返し `set -e` でスクリプト全体が中断、ttyd が一切起動しない**事象を観測した。原因は ttyd 停止処理:

```bash
ssh "$SERVER" "pkill -f 'ttyd --port 7681' ...; true"
```

`ssh host "cmd"` はリモートで `bash -c "cmd"` を実行するため、**このシェル自身のコマンドラインに文字列 `ttyd --port 7681` が含まれ**、`pkill -f` のパターンがリモートシェルにマッチして自殺させる。接続が切れて ssh が 255 を返し、`set -e` でスクリプトが止まる。実機で再現確認:

| パターン | 結果 |
|---------|------|
| `pkill -f 'ttyd --port 7681'`（現行） | EXIT=255（自殺） |
| `pkill -f '^ttyd --port 7681'`（アンカー） | EXIT=0 |

`^` で先頭アンカーすると、実 ttyd プロセス（cmdline が `ttyd --port 7681 ...` で始まる）にはマッチし、`bash -c ...` で始まるリモートシェルにはマッチしない。アンカー版が実 ttyd を確実に kill できることも実機で確認した（pid 3174 を起動→アンカー版 pkill→消滅）。**この自己マッチ修正なしには ttyd-up.sh は機能せず、デプロイ前に検証で捕捉できた。**

同じパターンが `stop.sh:65,100`（`pkill -f 'ttyd --port 768'`）にも存在し、同根のため両行を `^ttyd --port 768` にアンカー修正した（stop.sh は `set -euo pipefail` 下のため、自殺で ssh 255 → 異常終了し「停止」Discord 通知をスキップする潜在バグだった。ttyd 自体は kill されるが終了コードが汚れる）。

### 各手順の結果

| 手順 | 内容 | 結果 |
|------|------|------|
| 1 | 既存 ttyd 停止→初期状態 | 768x 空を確認 ✅ |
| 2–3 | `ttyd-up.sh` 単体起動→LISTEN | EXIT=0、7681/7682 とも ttyd が LISTEN ✅ |
| 4 | TERM バグ回帰チェック | pty 対比でラップなしは `Error opening terminal: unknown.` で即死、ラップありは生存(Error 0 行)。さらに **実 ttyd への WS 接続で nvtop(pid 3964) が spawn・生存**を end-to-end 確認 ✅ |
| 5 | 7682 ログ閲覧 | WS 接続で `tail -f`(pid 4079) が spawn・生存 ✅ |
| 6 | 冪等性 | 再実行で PID が更新（3611/3559→4449/4397）、各ポート LISTEN は 1 個ずつ（二重起動なし）✅ |
| 7 | **主因シナリオ** | スタブ `/health`(200) で「llama 稼働・ttyd 全滅」を作り `llama-up.sh` 実行 → 冪等スキップ経路から ttyd-up.sh が呼ばれ 7681/7682 復活 ✅ |
| 8 | 通知の正直性 | 7682 のみ kill し wait-ready.sh:86–98 と同一ロジック実行 → 7681 は接尾辞なし、7682 に「(未起動)」付与 ✅ |

検証後はスタブ `/health` を停止し、ttyd を正常な両起動状態へ復旧、ロックを解放した。手順 4 の TERM 検証には stdlib のみの最小 ttyd WebSocket クライアントを使用（接続して init を送ると ttyd がコマンドを spawn することを利用）。

## 再現方法（実機検証手順）

GPU サーバが空き次第、以下を実施する。

1. 既存 ttyd を止めて初期状態に:
   ```bash
   ssh t120h-p100 "pkill -f 'ttyd --port 7681'; pkill -f 'ttyd --port 7682'; pkill nvtop; true"
   ssh t120h-p100 "ss -tln | grep -E ':768[12] '"   # 空であること
   ```
2. 単体起動と LISTEN 確認:
   ```bash
   .claude/skills/llama-server/scripts/ttyd-up.sh t120h-p100
   ssh t120h-p100 "ss -tlnp | grep -E ':768[12] '"
   ```
3. **TERM バグ回帰チェック**: `ssh t120h-p100 "pgrep -a nvtop"` で nvtop が即終了せず生存。ブラウザ `http://10.1.4.14:7681` で nvtop が描画され `Error opening terminal: unknown.` が出ないこと。
4. ログ閲覧: ブラウザ `http://10.1.4.14:7682` で `tail -f` の出力が流れること。
5. 冪等性: `ttyd-up.sh t120h-p100` を再実行 → 二重 LISTEN にならず PID が更新されること。
6. **障害シナリオ**: llama-server 起動済みにし ttyd だけ手動で殺す → `llama-up.sh t120h-p100 ...` を再実行 → health 200 の冪等スキップ経路でも 7681/7682 が立ち直ることを `ss` で確認。
7. **通知の正直性**: ttyd を片方だけ殺した状態で `wait-ready.sh` を実行 → Discord 通知の該当 URL に「(未起動)」が付くこと。
8. （可能なら）mi25 TERM ラップ確認: `ttyd-up.sh mi25` → `http://10.1.4.13:7681` で `watch -n 1 rocm-smi` が描画され即終了しないこと。

## 関連

- 本障害の発端は、t120h-p100 で llama-server 稼働中に ttyd 7681/7682 が両方未起動だった事象（本セッションで調査・暫定復旧済み）。
