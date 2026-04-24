# Phase I: Qwen3.5-122B C-D3 長コンテキストでの eval/prompt 速度計測

## Context（なぜこの項目を選んだか）

直近の Phase H（`report/2026-04-17_082738_qwen3-122b-c3-phaseH-idle-poll.md`）で C-D3 `--poll 0` が採用構成として確定。しかし **Phase D〜H の計測はすべて 18 トークン固定プロンプト**で、`ctx_size=131072` で起動しているモデルの長コンテキスト性能プロファイルが完全に欠落している。

Phase H 未検証事項のうち、以下 3 つを本 Phase I で同時に解消する:

1. **大コンテキストでの eval 速度（16k / 32k / 64k / 128k）** — 実運用では長プロンプトが主。ここが未知のままでは Qwen3.5-122B-A10B の採用可否を判断できない。
2. **CUDA1 の 2 GiB セーフティマージン** — プロンプト処理中の KV cache ピーク使用量が未計測。長コンテキストは OOM リスクの最大源。
3. **flash-attn 1 の有効性** — 長コンテキストでこそ flash-attn の恩恵が大きい。現行 `--flash-attn 1` 固定が妥当かの一次確認になる（off との比較は本 Phase では実施せず、TODO 化のみ）。

優先度判定:
- vs `--poll 1 / 10 / 100`: Phase H の延長で、かつ Phase H で `--poll 0` 劣化なしが確定しているため実用上の緊急度は低い
- vs C-4 実験（CPU 層削減）: GPU メモリ余剰の活用で速度向上の可能性は高いが、前提として**現行構成の運用プロファイル確定**が先。長コンテキストで OOM が出るようなら C-4 の層配置も大きく変わる
- vs perf stat / 他モデル: 診断用途で実利益は間接的

→ **長コンテキスト計測が最優先**。

## 方針

- **構成変更なし**: `.claude/skills/llama-server/scripts/start.sh` は一切変更せず、現行 C-D3 `--flash-attn 1 --poll 0 -b 8192 -ub 8192 --ctx-size 131072` で計測
- **5 サイズ**で計測: 1k / 8k / 32k / 64k / 120k トークン（近似） × 3 run
- **プロンプトはファイル化**して `measure_phaseH.sh` の EVAL_PROMPT 固定値をファイル読み込みに変更
- **トークン数検証**は llama-server の `/tokenize` API（llama.cpp ネイティブ）で事前確認、応答の `.timings.prompt_n` で事後確認
- **KV cache の GPU メモリピーク**を nvidia-smi `dmon` + pre/post スナップで捕捉
- 1 サイクル後に llama-server を停止 → 次サイクルでは fresh restart は行わず、**同一プロセス内で 5 サイズを連続実行**（セッション間ゆらぎを混入させない）

## 実行フロー

```bash
# 1. ロック取得
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 2. llama-server 起動（現行設定のまま）
.claude/skills/llama-server/scripts/stop.sh t120h-p100
.claude/skills/llama-server/scripts/start.sh t120h-p100 "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M"
PID=$(ssh t120h-p100 "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")

# 3. warm-up: 18 トークン eval 3 本（Phase H と同じ）で warm 状態を作る
bash measure_phaseI.sh $PID warmup "Write a short haiku about autumn."

# 4. 5 サイズを順に計測
bash measure_phaseI.sh $PID I_1k   prompts/prompt_1k.txt
bash measure_phaseI.sh $PID I_8k   prompts/prompt_8k.txt
bash measure_phaseI.sh $PID I_32k  prompts/prompt_32k.txt
bash measure_phaseI.sh $PID I_64k  prompts/prompt_64k.txt
bash measure_phaseI.sh $PID I_120k prompts/prompt_120k.txt

# 5. 停止・ロック解放
.claude/skills/llama-server/scripts/stop.sh t120h-p100
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 変更・作成ファイル

- **新規**: `report/attachment/2026-04-17_<ts>_qwen3-122b-c3-phaseI-longcontext/measure_phaseI.sh`
  - `measure_phaseH.sh` をコピーし、第3引数でプロンプトを「文字列」または「ファイルパス」指定できるよう拡張
  - `-@` プレフィックス規約: `@path/to/file.txt` の場合はファイル読み込み
  - JSON escape を `jq -Rs .` で安全に処理
- **新規**: `report/attachment/2026-04-17_<ts>_qwen3-122b-c3-phaseI-longcontext/prompts/prompt_{1k,8k,32k,64k,120k}.txt`
  - 英文 Lorem Ipsum 系の長文（Project Gutenberg パブリックドメイン or プログラム的生成）
  - 各サイズはサーバの `/tokenize` で実測して ±5% 以内に調整
  - 最後に「Summarize the above in 3 bullet points.」を付けて eval タスクを定義
- **新規**: `report/attachment/2026-04-17_<ts>_qwen3-122b-c3-phaseI-longcontext/plan.md`（本ファイルのコピー）
- **新規**: `report/2026-04-17_<ts>_qwen3-122b-c3-phaseI-longcontext.md`
- **既存をそのまま利用**: `.claude/skills/llama-server/scripts/start.sh`（未変更）、`.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`、`.claude/skills/llama-server/scripts/stop.sh`

## 計測項目

| 項目 | 取得方法 |
|------|---------|
| prompt_per_second / prompt_n | `.timings` in eval_run*.json |
| predicted_per_second / predicted_n | 同上 |
| GPU メモリ使用量（pre/post + 計測中） | `nvidia-smi --query-gpu=memory.used --format=csv`、`nvidia-smi dmon -s m` |
| CUDA1 の空き（2 GiB マージン検証） | nvidia-smi index=1 の free |
| NUMA ページ分布 | `numastat -p $PID` pre/post |
| エラー（OOM, timeout） | llama-server 側の `stderr` journal、curl HTTP code |

## 成功条件 / 判定基準

- **全 5 サイズで OOM なし完走** → flash-attn 1 + KV cache = 2 GiB マージン妥当性
- **prompt_per_second**: 1k で ~32 t/s、8k で X t/s、32k 以上で Y t/s の実測値を表として記録（期待値は仮説に留め、棄却判定は行わない）
- **predicted_per_second**: 長コンテキストで −20% 以上の低下があれば「実用上の新制約」として記録
- **セッション間ゆらぎとの区別**: 先頭 warm-up 18 トークン計測値を Phase H の H1_t0 (14.66) 帯と比較し、今回セッションの基準点を確定

## 未検証事項セクション（レポート必須）

前身 Phase H のリストを引き継ぎ、本 Phase で解消した項目（大コンテキスト計測、CUDA1 マージン）は削除、残項目と本 Phase で新たに発見した項目を追加する（指示どおり「未検証事項」と「検証完了後に実施すべき TODO」の 2 セクション）。

## 検証方法（エンドツーエンド）

1. **トークン数正確性**: 各サイズで eval_run*.json の `.timings.prompt_n` が期待値 ±5% 以内
2. **結果の再現性**: 各サイズ 3 run の range が中央値の 1% 以内（Phase H と同水準）
3. **GPU 正常性**: `nvidia-smi` で ECC エラー 0、温度 80℃ 未満
4. **ロック**: 開始時 `lock.sh` で取得できること、終了時 `unlock.sh` が成功すること
5. **レポート**: `REPORT.md` のフォーマットに従い、未検証事項 + TODO セクションを含む

## リスクと対応

| リスク | 対応 |
|------|------|
| 120k プロンプトで OOM | CUDA1 の 14,173→16,271 MiB 使用で強制 OOM の可能性。発生時は 120k を抜いて 100k に下げて記録、未検証 TODO 化 |
| prompt 処理に 10 分超 | 120k の prompt_per_second が 10 t/s を切ると 3 run で 60 分超。COOLDOWN を 30s に短縮、dmon_secs を延長で対応 |
| 同時ユーザ利用 | GPU サーバは `lock.sh` で排他化済み |
| セッション内の経時劣化 | 最後に warm-up と同じ 18 トークン計測を 1 本追加し、セッション開始時との差を記録 |

## 参考コマンド（llama-server `/tokenize`）

```bash
curl -sS -X POST http://10.1.4.14:8000/tokenize \
  -H 'Content-Type: application/json' \
  -d "$(jq -n --arg c "$(cat prompts/prompt_32k.txt)" '{content: $c}')" \
  | jq '.tokens | length'
```

## 工数見積

- プロンプトファイル生成 + トークン数調整: 20 分
- warm-up + 5 サイズ × 3 run × 60s cooldown + dmon 20s: 約 60〜90 分（120k の prompt 処理に依存）
- 集計・レポート作成: 40 分
- **合計見積: 2〜3 時間**
