# 起動試験 plan: Qwen3.5-122B-A10B × 128k default 構成の検証 + レポート

> **この plan は同ファイルに既存の「メタ plan: tmux 上の worker claude へ作業委譲」とは別タスク**。現タスクは先に承認された起動スクリプト更新 (start.sh / wait-ready.sh / SKILL.md) の実機起動試験と、試験結果 + 修正内容のレポート化。

## Context

先のターンで `.claude/skills/llama-server/scripts/start.sh` と `wait-ready.sh`、`SKILL.md` を Phase U-6 確定構成 (ctx=128k / B14b OT / ts=11,12,13,14 / -b 2048 -ub 512 / threads 40 / numactl node1) に更新した。ユーザーからは「起動試験をおこなってください。起動試験の結果と、起動スクリプトの修正内容をレポートにまとめてください」との依頼。

**事前発覚した修正前ブロッカー (実行前に要修正)**:
現在 start.sh 内の NGL_OPTS は以下になっている:
```
-ot 'blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU'
```
この値は既存パイプライン `ssh "$SERVER" "cd ... && nohup bash -c '$LAUNCH_CMD' > ..."` を通過する際、外側 shell の **nested single-quote stripping** で単一引用符が消費された後、**内側 bash -c パーサがパターン中の `(`, `)`, `|` をメタキャラとして解釈** してしまい syntax error で llama-server を起動できない。従来の単純 `-ot 'ffn_.*_exps.weight=CPU'` は `.` と `*` しかメタが無く偶然動いていた。

**調査結果 (Explore エージェント経由、llama.cpp ソース根拠)**:
- `-ot` は複数回指定可能で OR 合成される (`llama_model_loader::create_tensor()` が `std::regex_search()` で順照合)
- 単一 `-ot` 値内は `parse_tensor_buffer_overrides()` が **カンマ `,` で分割**
- よってパーレン・パイプを使わないカンマ区切り列挙パターンで等価表現が可能

## 修正方針 (Step 1 で start.sh に追加実施)

`blk.N.ffn_.*_exps.weight=CPU` を 14 層ぶんカンマで連結した単一 `-ot` 値に置換する。`\` escape は bash unquoted で食われるため不要 (削除しても std::regex では `.` = 任意 1 文字だが、対象テンソル名は他に該当なしで誤マッチしない)。

修正後 NGL_OPTS (Qwen3.5-122B-A10B 分岐):
```bash
OT_CPU_LAYERS="2 3 20 21 22 23 31 32 33 34 35 36 37 38"
OT_PATTERNS=""
for L in $OT_CPU_LAYERS; do
  [ -n "$OT_PATTERNS" ] && OT_PATTERNS+=","
  OT_PATTERNS+="blk.$L.ffn_.*_exps.weight=CPU"
done
NGL_OPTS="-ngl 999 --split-mode layer -ot '$OT_PATTERNS'"
```

bash unquoted 通過後: `blk.2.ffn_.*_exps.weight=CPU,blk.3.ffn_.*_exps.weight=CPU,…,blk.38.ffn_.*_exps.weight=CPU` (14 パターン)。llama.cpp が `,` で split、各々 `std::regex_search` で評価。layer 24, 39 は含まれずそのまま GPU に残る。

### Step 1 の事前検証 (修正後 / 実機起動前)
1. `bash -n start.sh`
2. bash の dry-run で NGL_OPTS 展開結果を echo — `-ot 'blk.2.ffn_.*_exps.weight=CPU,blk.3.ffn_.*_exps.weight=CPU,...'` (長い 1 トークン) が出ることを確認
3. 旧パターンがメタ解釈されることも対比で確認 (syntax error 再現): `bash -c 'echo blk\.([2-3])\.ffn_.*_exps\.weight=CPU'` → "syntax error near unexpected token '('"
4. 修正後パターンが single token で通ることを確認: `bash -c "echo blk.2.ffn_.*_exps.weight=CPU,blk.3.ffn_.*_exps.weight=CPU"` → 正常 echo

## 起動試験手順

### Step 2: 環境準備 (read-only 事前確認)
- `.claude/skills/gpu-server/scripts/lock-status.sh t120h-p100` でロック空きを確認
- `ssh t120h-p100 "ps aux | grep llama-server | grep -v grep"` で既存プロセス無しを確認
- `ssh t120h-p100 "df -h ~/llama.cpp ~ ~/.cache/huggingface 2>/dev/null"` でディスク空きを確認
- `ssh t120h-p100 "nvidia-smi --query-gpu=index,memory.free --format=csv,noheader"` で全 GPU に 15+ GB 空きを確認

### Step 3: ロック取得
```
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
```
失敗時は理由を報告し abort。

### Step 4: 起動 (本試験)
```bash
.claude/skills/llama-server/scripts/ttyd-gpu.sh t120h-p100
.claude/skills/llama-server/scripts/start.sh t120h-p100 \
  "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit
.claude/skills/llama-server/scripts/wait-ready.sh t120h-p100 \
  "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit
```
(fit-ctx 省略時、qwen3_122b プロファイル判定で 131072 が自動採用される — 修正済み script の核心検証点)

起動時の非同期観測: `ssh t120h-p100 "tail -f /tmp/llama-server.log"` を別途バックグラウンド fetch。

### Step 5: 起動ログ検証 (成功条件)

llama-server プロセス引数の実機確認:
```
ssh t120h-p100 "ps -o cmd= -p \$(pgrep -f './build/bin/llama-server')"
```
期待される含有文字列:
- `numactl --cpunodebind=1 --membind=1` (親プロセス)
- `--flash-attn 1`
- `--poll 0`
- `-b 2048`
- `-ub 512`
- `--tensor-split 11,12,13,14`
- `--threads 40`
- `-ot blk.2.ffn_.*_exps.weight=CPU,blk.3.ffn_...` (14 個カンマ連結)
- `--ctx-size 131072`
- `--cache-type-k q8_0 --cache-type-v q8_0`
- `--split-mode layer`
- `--parallel 1`

llama-server ログ内確認 (`/tmp/llama-server.log`):
- `load_tensors: offloaded 48/48 layers to GPU` — 全層 -ngl 999 認識
- `tensor blk.2.ffn_*_exps.weight buffer type overridden to CPU` 系メッセージが 14 層ぶん × 3 (gate/up/down) 出ている
- `n_ctx = 131072`
- `flash_attn = 1`
- `HTTP server is listening, hostname: 0.0.0.0, port: 8000`

### Step 6: /health + /v1/models 検証
```
curl -s http://10.1.4.14:8000/health     # → {"status":"ok"}
curl -s http://10.1.4.14:8000/v1/models  # モデル ID 確認
```

### Step 7: VRAM 計測 (Phase U-5 T1-04 との一致確認)
```
ssh t120h-p100 "nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv"
```
期待値 (Phase U-5 T1-04、ctx=131072, B14b, ts=11,12,13,14):
- GPU0: free ≈ 960 MiB
- GPU1: free ≈ 1682 MiB
- GPU2: free ≈ 4238 MiB
- GPU3: free ≈ 956 MiB

### Step 8: Smoke test
短めの prompt で /v1/chat/completions 非 stream 1 回と stream 1 回:
```bash
curl -s http://10.1.4.14:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M",
    "messages": [{"role":"user","content":"1+1は?"}],
    "max_tokens": 64
  }' | jq
```
- HTTP 200
- choices[0].message.content が非空文字列 (期待: "2" を含む)
- usage.prompt_tokens / completion_tokens が妥当な値
- /tmp/llama-server.log に eval time を含む slot 完了行があること

Optional 第 2 弾 (長文脈の sanity): 2k token 程度の prompt で応答させ、完走することを確認 (+TTFT 目測)。OOM/hang の兆候あれば stop → 原因調査。

### Step 9: 停止・解放
```
.claude/skills/llama-server/scripts/stop.sh t120h-p100
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```
`ssh t120h-p100 "pgrep -a llama-server"` が空であること、ロックが解放されていることを確認。

### Step 10: 添付収集 (レポート前)
- `start.log` (start.sh の stdout をキャプチャ)
- `wait-ready.log` (wait-ready.sh の stdout をキャプチャ)
- `llama-server.log.head500.txt` (`/tmp/llama-server.log` の先頭 500 行)
- `process-cmd.txt` (起動直後の `ps -o cmd=` 出力)
- `nvidia-smi.txt` (起動後の VRAM snapshot)
- `smoke-test-nonstream.json`, `smoke-test-stream.txt` (2 ケース)
- `plan.md` (この plan ファイル)

### Step 11: レポート執筆 (REPORT.md 準拠)

ファイル名テンプレ: `report/YYYY-MM-DD_HHMMSS_qwen3-122b-startup-script-128k-default.md` (タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得)

章立て:
1. **タイトル + 実施日時** — タイトル 50 字以内「Qwen3.5-122B 128k 既定構成の起動スクリプト更新と実機起動試験」
2. **核心発見サマリ** — 1〜2 文 + 該当 PNG があれば先頭埋め込み (今回は起動試験主体で画像は任意。VRAM bar chart 等を attachment に付ける場合のみ埋め込む)
3. **添付ファイル** — `plan.md` を筆頭にリンク一式
4. **前提・目的** — start.sh の Phase U-6 profile 化、実機での正しさ検証、事前発見した quoting バグとその修正含む
5. **環境情報** — t120h-p100、P100×4、llama.cpp HEAD commit、モデル、OS、RAM
6. **再現方法** — start.sh → wait-ready.sh → smoke test の最小コマンド列
7. **起動スクリプトの修正内容** — start.sh / wait-ready.sh / SKILL.md の diff 要約 + quoting バグ修正の理由(現象・原因・fix)
8. **起動試験結果** — ps cmd 実測、llama-server ログ抜粋、VRAM 表、/health・/v1/models、smoke test 結果
9. **未検証事項**
10. **検証完了後に実施すべき TODO**
11. **参考レポート** — Phase U-5, U-6 へのリンク

## Critical Files

### 編集対象
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/start.sh` (NGL_OPTS の quoting バグ修正 — Qwen3.5-122B 分岐)
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/SKILL.md` (fitモード欄の OT パターン表記を新形式に合わせる; 旧表記 `blk\.([2-3]\|2[0-3]\|3[1-8])\...` → 新表記 `blk.N.ffn_.*_exps.weight=CPU × 14` or カンマ列挙説明)

### 編集済 (前ターンで更新済、起動試験対象、今回変更無し)
- `.../skills/llama-server/scripts/wait-ready.sh`

### 読み取り参照
- `/home/ubuntu/projects/llm-server-ops/REPORT.md` — レポート規約
- `/home/ubuntu/projects/llm-server-ops/CLAUDE.md` — プロジェクト制約
- `/home/ubuntu/projects/llm-server-ops/report/2026-04-24_081326_qwen3-122b-u5-ctx128k-fit-map.md` (VRAM 期待値ソース)
- `/home/ubuntu/projects/llm-server-ops/report/2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default.md` (default 選定根拠)

## 想定リスク

| リスク | 影響 | 対処 |
|---|---|---|
| GPU ロックが他セッションで取得中 | 試験着手不可 | 保留、lock-status で保持者確認してユーザーに報告 |
| quoting 修正後も llama-server 起動失敗 | 試験目的達成不可 | /tmp/llama-server.log 先頭 100 行を取得し root-cause、再修正 |
| 128k KV 初期化が wait-ready timeout (300s) 超過 | false negative | MAX_RETRIES を環境変数で延長 or 手動で /health poll |
| smoke test で無意味な出力 | 起動自体は OK だがモデル不具合の可能性 | HF キャッシュ再確認、別プロンプトで再試行 |
| 実測 VRAM が U-5 期待と大きく乖離 | GPU 層配置の再現性欠如 | start.sh の `-ot` 実展開を `ps cmd` で確認、原因分析 |

## 検証方法

End-to-end の試験そのものがこの plan の検証。追加の自動テストは無いが、以下を満たせば「成功」:
- start.sh 引数 `fit` のみで 131072 ctx + B14b profile が当たる
- llama-server が正常起動し /health が 200
- smoke test が妥当な応答を返す
- VRAM 分布が Phase U-5 の誤差内 (±200 MiB)
- stop.sh で全てクリーンアップされる

## 停止判定

本タスク (起動試験 + レポート) は「単発」のため、完了次第そのまま終了。残作業が無ければメタ plan の自動ループに復帰しない。

---

# メタ plan: tmux 上の worker claude へ作業委譲 (別タスク、参照用に保持)

## Context

ユーザーは従来「plan モードで投げる → 未検証事項と検証完了後 TODO が計画されているか確認 → 承認」のループを手動で繰り返していた。これを、**現在の tmux セッションに別ペインを開き、そこでもう 1 プロセス起動した worker claude** に委譲して自動化する。

worker には課題選定からレポート作成まで一任する。plan レビューは claude の標準挙動（`ExitPlanMode` 時に呼び出し元で plan 承認ダイアログが出る）をそのまま利用する。

**メインは、主要な課題がなくなるか、ユーザーから「停止してください」と言われるまで、サイクル（課題選定 → plan → レビュー → 実行 → レポート → レビュー）を繰り返し続ける**。

## 委譲する指示

worker に渡す指示は 1 文で済む（ユーザー指定の原文）:

> 最後のレポートの未検証事項から優先度が高いものを実施してください。レポートには直前のレポートと同様に「未検証事項」と「検証完了後に実施すべき TODO」のセクションをいれてください。

## チーム体制

| 役割 | 担当 |
|------|------|
| メイン（ペイン管理・plan レビュー・レポートレビュー） | 私（現セッション） |
| worker（課題選定 → 計画 → 実行 → レポート） | 同一 tmux セッションの別ペインで起動する `claude --enable-auto-mode` |

## ワークフロー

### ステップ 1: worker ペイン作成
```
WORKER_PANE=$(tmux split-window -h -d -P -F '#{pane_id}')
```
- `-h` 水平分割、`-d` detach、`-P -F '#{pane_id}'` でペイン ID を返す
- コマンド指定なしで開くことで、claude が終了してもペインは残る（シェルに戻る）
- `WORKER_PANE` はメイン側で保持し、以降の tmux 操作で `-t "$WORKER_PANE"` を使う

### ステップ 2: worker claude 起動
```
tmux send-keys -t "$WORKER_PANE" 'cd /home/ubuntu/projects/llm-server-ops' Enter
tmux send-keys -t "$WORKER_PANE" 'claude --enable-auto-mode' Enter
```
- 起動後、TUI 初期化を待ち、`tmux capture-pane -t "$WORKER_PANE" -p -S -100` で入力プロンプト `>` が出ていることを確認

### ステップ 3: worker を plan mode に遷移
```
tmux send-keys -t "$WORKER_PANE" S-Tab
```
- `capture-pane` で plan mode 表示が出ているか確認。auto edit モードから plan へ一回で入らなければ追加で `S-Tab` を送る

### ステップ 4: 指示送信
上記「委譲する指示」を 1 メッセージで送る。
```
tmux send-keys -t "$WORKER_PANE" '最後のレポートの未検証事項から優先度が高いものを実施してください。レポートには直前のレポートと同様に「未検証事項」と「検証完了後に実施すべき TODO」のセクションをいれてください。' Enter
```
- シングルクォート内で日本語・全角「」はそのまま渡せる

### ステップ 5: worker の plan 作成を待機 → ExitPlanMode 時に plan レビュー
- worker は最新レポートを自分で特定し、未検証事項の優先度を判断、plan モードで plan ファイルを書く
- 書き終えたら worker は `ExitPlanMode` を呼ぶ。これにより worker の TUI に **plan 承認ダイアログ**（通常の plan mode 承認 UI）が表示される
- メインは `capture-pane` で承認ダイアログの内容（plan 要約）を読み、以下をチェック:
  - 選定項目の妥当性（レポート内の優先度表記・Phase X 候補との整合）
  - 条件・成功条件・OOM 事前予測
  - GPU ロック取得/解放の計画
  - レポートに「未検証事項」と「検証完了後に実施すべき TODO」セクションを含む計画
  - REPORT.md 準拠（ファイル名、タイムスタンプ取得方法、添付ディレクトリ、相対パス）
- 問題なければ承認キー（通常は「Yes」選択 + Enter）を `send-keys` で送る。問題あれば拒否キー + 修正指示メッセージを送って worker に plan 修正させる

### ステップ 6: worker が実行 + レポート作成
- worker は自律的に Phase を実施、レポート `report/<TS>_<slug>.md` + 添付一式を作る
- メインは一定間隔（20〜60 秒）で `capture-pane` により進捗を観測。計測中は長時間沈黙するので過度にポーリングしない

### ステップ 7: メインのレポートレビュー
完了通知を capture-pane で確認したら、メインが `Read` で `report/<TS>_<slug>.md` を読み:
- 前身レポートの章立て踏襲
- 成功条件の達成（定量評価表）
- 実測 vs 予測の誤差
- 「未検証事項」「検証完了後に実施すべき TODO」セクション完備、次 Phase 候補の明示
- 添付ファイル網羅（`plan.md` 含む）
- REPORT.md 規約準拠

必要なら `tmux send-keys` で修正指示を送る。

### ステップ 8: 1 サイクルの終了時の状態確認
メインが以下を確認:
- `ssh <host> "pgrep -a llama-server"` が空
- GPU ロック解放済み（`.claude/skills/gpu-server/scripts/lock-status.sh` 等）
- レポート + 添付一式が揃っている

### ステップ 9: 次サイクルへの継続判定
以下のいずれかを満たせば **停止**、それ以外は次サイクルへ進む:

- ユーザーから「停止してください」等の明示的停止指示がある
- 最新レポート（いま worker が書いたもの）の「未検証事項」が空、かつ「検証完了後に実施すべき TODO」も空
- 主要な未検証事項がなくなり、残項目が実行コストに対して価値が低すぎる（メインが判断、判断根拠をユーザーに報告して確認を取る）

### ステップ 10: 次サイクルの開始（繰り返し）
継続する場合:
1. worker の claude を `/exit` で終了させてシェルに戻す（ペインは残る、コンテキスト膨張を防ぐ）
2. 同じペインで `claude --enable-auto-mode` を再起動（ステップ 2 相当）
3. `S-Tab` で plan mode へ遷移（ステップ 3 相当）
4. 同じ指示文を再度送信（ステップ 4 相当）。「最後のレポート」は worker が実行するたびに更新されているので、自然に次の未検証事項が対象となる
5. ステップ 5 以降をループ

メインはループ全体を管理し、ユーザーからの中断指示（`system-reminder` / ユーザー発話）を各ステップの境界で確認する。長時間の計測中でも `capture-pane` のポーリング間隔の中でユーザー入力を受け取れるよう、過度に長いブロッキング処理は避ける。

## Critical Files

### メインが読むもの
- `/home/ubuntu/projects/llm-server-ops/report/` 以下の最新レポート（plan レビュー時に worker が選んだ項目と照合するため）
- `/home/ubuntu/projects/llm-server-ops/REPORT.md` — レポート規約
- `/home/ubuntu/projects/llm-server-ops/CLAUDE.md` — プロジェクト制約
- worker が書いた plan ファイル（ExitPlanMode 時に capture-pane で要約は見えるが、必要なら該当ファイルを直接 Read）
- worker が書いたレポート `report/<TS>_<slug>.md`

### worker が作成
- plan ファイル（claude が自動割当、`/home/ubuntu/.claude/plans/plan-*.md`）
- `report/<TS>_<slug>.md`
- `report/attachment/<TS>_<slug>/` 以下に plan.md コピー、スクリプト、ログ、解析結果

## 検証方法

1. ステップ 2 後: `tmux capture-pane -t "$WORKER_PANE"` で claude のプロンプトが見える
2. ステップ 3 後: plan mode 表示が見える
3. ステップ 5 後: ExitPlanMode 承認ダイアログが capture-pane で確認できる、plan ファイルが `/home/ubuntu/.claude/plans/` に存在
4. ステップ 7: `report/<TS>_<slug>.md` 存在、添付一式揃う、規約準拠
5. ステップ 8: llama-server 停止、GPU ロック解放
6. ステップ 10 に進む場合: worker claude が再起動し、plan mode で新しい指示が受理されている
7. 停止時: 停止理由（ユーザー指示 / 未検証事項空 / 価値が低い）を明示してユーザーに報告

## 想定リスクと対処

- **S-Tab がモード切替として解釈されない**: `capture-pane` でモード表示を確認し、未遷移なら追加送信 or `BTab` を試す
- **plan ファイルのパス不明**: worker の plan mode 起動時に system-reminder で告知される。承認ダイアログ内にも記載されるので、必要ならそこから特定してメインが直接 Read
- **worker の実行が長時間沈黙（計測中の正常な沈黙）**: 過度にポーリングしない。20〜60 秒間隔で十分
- **OOM/ハング**: worker の plan に GPU ロック解放と stop.sh 呼び出しが計画されていることをステップ 5 で確認。計画になければ拒否して修正依頼
- **worker claude の異常終了**: ペイン自体はシェルに戻って残るので、同じペインで `claude --enable-auto-mode` を再起動して状況再説明（既存 plan ファイルを参照する形で継続可能）
