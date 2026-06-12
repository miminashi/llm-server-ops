# llama-server スキル: ttyd 起動の信頼性向上

## Context（なぜこの変更をするか）

t120h-p100 で llama-server は稼働していたのに、ttyd（7681 GPU 監視 / 7682 ログ閲覧）が両方とも起動していない障害が発生した。調査の結果、これは単発のミスではなくスキルの構造的欠陥に起因することが判明した:

1. **ttyd 起動ロジックが 3 箇所に重複・不整合** — `start.sh:323,330,333,334`（7681/7682 両方）と `ttyd-gpu.sh:31,32`（7681 のみ）。TERM ラップの有無や kill 対象パターンが揃っていない。
2. **「llama-server は稼働中だが ttyd だけ落ちている」状態を立て直す経路が無い** — 複数の経路がこの状態を生み・放置しうる:
   - `llama-up.sh:77-81` は `/health` 200 で冪等 early-exit (`exit 0`) し start.sh を呼ばない → ttyd 起動に到達しない。
   - `start.sh:146-152` は既存 llama-server 検出で `exit 1` → ttyd 起動行（330/334）に到達しない。
   - `stop.sh:65,100` / `llama-down.sh` は `pkill -f 'ttyd --port 768'` で ttyd を殺すが、何らかの理由で llama-server だけ残ると「本体稼働・ttyd 全滅」になる。
   - **注**: 今回の障害（観測 ps は start.sh:327 のパターンそのものなのに 7681/7682 とも完全消失）は上記いずれの経路でも起こりうる。証拠から単一の主因は特定できないが、本変更は **どの経路で入っても ttyd を担保する**ことで全ケースを一括解消する。
3. **検証ステップが無い** — `wait-ready.sh:87-94` は Discord 通知に 7681/7682 URL を載せるが LISTEN 確認はせず、ttyd が落ちていても気付けない（silent fail）。
4. **nvtop の TERM バグ** — `ttyd --port 7681 nvtop` を直起動すると子に TERM が渡らず `Error opening terminal: unknown.` で即終了し、ttyd は LISTEN するが画面は死ぬ。`bash -c 'TERM=xterm-256color exec nvtop'` で正常動作することを実機で確認済み。

**目標**: ttyd 起動を単一の冪等スクリプトに集約し、Claude がどの経路で起動しても ttyd が自動的に担保され、落ちていれば必ず表面化する状態にする。「Claude が ttyd 起動を忘れる」余地そのものを無くす。

**確定した方針（ユーザ承認済み）**:
- 単一冪等スクリプト `ttyd-up.sh` に集約する。
- LISTEN 検証失敗は **警告のみ（exit 0 継続）**。落ちたポートは通知に「(未起動)」と明記して silent fail を防ぐ。

---

## 変更内容

### 1. 新規 `scripts/ttyd-up.sh <server>`（集約スクリプト・単一の真実源）

責務: 7681（GPU 監視）と 7682（ログ閲覧）の ttyd を冪等に kill→再起動し、両ポートの LISTEN を検証して報告する。

骨子:
- shebang + `set -euo pipefail`、`SCRIPT_DIR` 解決は既存スクリプトと同形。
- 引数チェック + SERVER バリデーション（既存 `case "$SERVER" in mi25|t120h-p100|t120h-m10)` を流用）。
- `GPU_CMD` をサーバ別に決定: mi25 → `watch -n 1 rocm-smi`、それ以外 → `nvtop`。
- 既存 ttyd 停止: `pkill -f 'ttyd --port 7681'` / `pkill -f 'ttyd --port 7682'` をポート完全一致で個別発行（stop.sh の `768` ワイルドカードは将来 768x 追加時の巻き込みを避けるため使わない）。`pkill nvtop` も併用（start.sh:333 踏襲）。`set -e` 下で落ちないよう末尾 `|| true`。
- ポート解放待ち（`ss -tln | grep ':7681'` が消えるまで最大数秒）で再起動 race を回避。
- **ログファイル担保**: 7682 起動前に `ssh "$SERVER" "touch /tmp/llama-server.log"`。llama-server 未起動でログが無い場合に `tail -f` が即終了して 7682 画面が死ぬのを防ぐ（単体 / ttyd-gpu.sh ラッパー経由の堅牢性確保）。
- 再起動（**fd リダイレクトは start.sh:330 パターンを踏襲**、ローカル側にも `</dev/null >/dev/null 2>&1`）:
  - 7681: `ssh -f "$SERVER" "nohup ttyd --port 7681 bash -c 'TERM=xterm-256color exec $GPU_CMD' > /dev/null 2>&1 < /dev/null &" </dev/null >/dev/null 2>&1`
    - **注意**: `exec $GPU_CMD` はクオートしない（`watch -n 1 rocm-smi` の引数分割を意図的に使う。`exec "$GPU_CMD"` は単一コマンド名扱いで失敗）。
  - 7682: `ssh -f "$SERVER" "nohup ttyd --port 7682 --writable bash -c 'tail -f /tmp/llama-server.log' > /dev/null 2>&1 < /dev/null &" </dev/null >/dev/null 2>&1`
- LISTEN 検証: 短いリトライ（最大 ~10 秒）で `ssh "$SERVER" "ss -tln | grep -q ':7681 '"` と `:7682`（私が実機で動作確認済みの `ss -tln | grep ':768x'` パターン）。
- 結果出力 + 終了コード: 両 OK → `0` と成功メッセージ。片方/両方 NG → **ttyd-up.sh 自身が `WARNING: ttyd <port> が LISTEN しません` を stderr に出し、それでも exit 0**（ユーザ承認の「warn のみ・起動継続」を ttyd-up.sh のレベルで完結させる）。`TTYD_xxx=ok` のような機械可読 stdout は消費側が無いため設けない（投機実装の排除）。
- `chmod +x`。

### 2. `scripts/start.sh`

行 323–334 のインライン ttyd 起動・nvtop kill ブロックを削除し、llama-server 起動（327行）直後に `"$SCRIPT_DIR/ttyd-up.sh" "$SERVER"` の 1 行へ置換。末尾の案内 echo（337–339）は維持。`SCRIPT_DIR` は定義済み（4行）。

### 3. `scripts/llama-up.sh`（主因の本丸修正）

health-200 early-exit ブロック（77–81行）の `exit 0` の前に `"$SCRIPT_DIR/ttyd-up.sh" "$SERVER"` の 1 行を挿入。これで既起動の冪等スキップ時も ttyd を担保する。**`|| echo WARNING` は付けない** — ttyd-up.sh は §1 の通り失敗時も exit 0 で自前の WARNING を stderr に出すため、`||` 分岐は死にコードになる。warn 表示は ttyd-up.sh 側に一元化する。

### 4. `scripts/ttyd-gpu.sh`（後方互換・薄いラッパー化）

SERVER バリデーション後、本体を `exec "$SCRIPT_DIR/ttyd-up.sh" "$SERVER"` に差し替え。7682 も追加で立つ（従来は 7681 のみ）が、§1 のログ touch 対応により llama-server 未起動でも 7682 画面が死なないため、追加的・非破壊。`SCRIPT_DIR` 解決を追加（現状未定義のため）。SKILL.md / settings.local.json / install-global.sh から参照される公開 IF なので削除はしない。

### 5. `scripts/wait-ready.sh`（通知の正直化）

Discord 通知の URL 行（93–94）の手前で 7681/7682 の LISTEN を `ss` で問い合わせ、落ちているポートには本文で「(未起動)」を付記。**ここでは ttyd 再起動はしない**（wait-ready の責務は本体 health 確認。start.sh 経由なら ttyd は既に立っているはず＝二重起動回避）。通知送信自体は止めない。

**カバー範囲の注意**: この「(未起動)」明記は wait-ready.sh を通る **fresh start 経路でのみ**発火する。`llama-up.sh` の冪等スキップ経路（health 200）は wait-ready.sh を呼ばず exit 0 するため、そちらは §3 の「`exit 0` 前に ttyd-up.sh を呼び、失敗時 stderr に WARNING」で担保する（二重の安全網であり、wait-ready の通知が全経路をカバーするわけではない）。

### 6. `scripts/install-global.sh` + `.claude/settings.local.json`（許可整合）

- `install-global.sh` の `PERM_SCRIPTS` 配列（30行〜、現在 ttyd-gpu.sh が 34行）に `ttyd-up.sh` を追加。
- `settings.local.json` の allow（33行 ttyd-gpu.sh の隣）に `Bash(.claude/skills/llama-server/scripts/ttyd-up.sh:*)` を追加。

### 7. `SKILL.md`（ドキュメント更新）

- 手動 3 ステップ記述（188–217行付近: ttyd-gpu.sh → start.sh → wait-ready.sh）を `ttyd-up.sh` 統一形へ更新。start.sh が内部で ttyd-up.sh を呼ぶようになったため独立 ttyd-gpu.sh ステップを削除し、「監視 UI だけ立て直したい場合は `ttyd-up.sh`」と注記。
- `start.sh の動作`（219–225）: 「7681/7682 両方を ttyd-up.sh 経由で起動・LISTEN 検証」を反映。
- `llama-up.sh の動作`（158–163）: 「既起動（health 200）の冪等スキップ時も ttyd を担保」を追記。
- `wait-ready.sh の動作`（229–232）: 「通知前に ttyd LISTEN を確認し、落ちているポートは (未起動) と明記」を追記。

**推奨実装順序**: 1（新規）→ 2,4（start/ttyd-gpu を寄せる）→ 3（主因修正）→ 5（通知）→ 6（許可整合）→ 7（ドキュメント）。

---

## 検証手順（実機 t120h-p100）

実プロセスを起動するため read-only ではない。**現在 GPU サーバは他タスクが実行中のため、検証はユーザから明示的に依頼があるまで実行しない**（実装＝ローカルのスクリプト編集は GPU サーバに触れないため先行して可）。依頼後に以下を実施:

1. 既存 ttyd を止めて初期状態に: `ssh t120h-p100 "pkill -f 'ttyd --port 7681'; pkill -f 'ttyd --port 7682'; pkill nvtop; true"` → `ssh t120h-p100 "ss -tln | grep -E ':768[12] '"` で空を確認。
2. 単体起動: `.claude/skills/llama-server/scripts/ttyd-up.sh t120h-p100` → 標準出力に両ポート OK。
3. LISTEN 確認: `ssh t120h-p100 "ss -tlnp | grep -E ':768[12] '"` で 7681/7682 とも ttyd が LISTEN。
4. **TERM バグ回帰チェック**: `ssh t120h-p100 "pgrep -a nvtop"` で nvtop が即終了せず生存。ブラウザ `http://<ip>:7681` で nvtop 画面が描画され `Error opening terminal: unknown.` が出ないこと（IP は `ssh -G t120h-p100 | grep '^hostname '`）。
5. ログ閲覧: ブラウザ `http://<ip>:7682` で `tail -f` の出力が流れること。
6. 冪等性: `ttyd-up.sh t120h-p100` を再実行 → 二重 LISTEN にならず PID が更新されること。
7. **主因シナリオ**: llama-server 起動済みにし、ttyd だけ手動で殺す（手順1）→ `llama-up.sh t120h-p100 ...` を再実行 → health 200 の冪等スキップ経路でも 7681/7682 が立ち直ることを `ss` で確認。
8. **通知の正直性**: ttyd を片方だけ殺した状態で `wait-ready.sh` 実行 → Discord 通知の該当 URL に「(未起動)」が付くこと。
9. （可能なら）mi25 TERM ラップ確認: `ttyd-up.sh mi25` → `http://<mi25-ip>:7681` で `watch -n 1 rocm-smi` が描画され即終了しないこと。

---

## レポート

CLAUDE.md / REPORT.md の規約により、本変更は対になるレポート（[REPORT.md](../../projects/llm-server-ops/REPORT.md) フォーマット）を作成する。
