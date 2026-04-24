# Phase R-ctx3: 他 GPU の ctx 係数 3〜4 点フィット

## Context

Phase R（2026-04-19 08:51）で以下が確定した:
- **CUDA3 = 0.9824·ub** は ctx に完全不依存（ctx=16k → 131k の 8 倍でも誤差 +0.04 MiB / +0.002%）
- 他 4 チャネル（CUDA0 / CUDA1 / CUDA2 / CUDA_Host）は **ctx 依存成分を持つ**ことが判明
- Phase Q は ctx=16k 固定だったため、ctx 係数と ub 係数を分離できていなかった

しかし現時点の ctx 係数は **ctx=16k と ctx=131k の 2 点から線形補間しただけ**。中間点での検証がなく、「2 変数線形モデル」として skill の起動前 lint に組み込む根拠が不足している。

Phase R レポート「未検証事項 / 新規項目」最上位:

> **他 4 GPU の ctx 係数（CUDA0=0.00987、CUDA1/2=0.00391、CUDA_Host=0.00781）の 3 点以上フィット**: ctx=16k と 131k の 2 点からの線形補間のため、中間 ctx (32k / 64k) での実測が必要。Phase R-ctx3 候補

本 Phase R-ctx3 でこれを潰し、検証完了後の「★最優先 TODO: 起動前 lint の 2 変数モデル組み込み」の根拠を提供する。

## 目的

- CUDA0 / CUDA1 / CUDA2 / CUDA_Host の ctx 係数の **線形性を 3〜4 点で実証**（R² ≥ 0.99）
- **CUDA3 = 0.9824·ub** が ctx=32k / 65k でも維持されることを再確認
- KV buffer の ctx 完全比例が 4 点で保持されることを確認
- 起動前 lint 用の 2 変数線形モデルを最終確定する

## 既存データ（再計測不要）

| ctx | 由来 | compute buffer 実測 |
|---:|---|---|
| 16,384 | Phase Q P1 | CUDA0=1,048.13 / 1=520.06 / 2=520.06 / 3=2,012.00 / Host=176.08 MiB |
| 131,072 | Phase R R1 | CUDA0=2,180.00 / 1=968.06 / 2=968.06 / 3=2,012.00 / Host=1,072.08 MiB |

## 新規計測点

| ctx | プロンプト | 所要（見込） |
|---:|---|---:|
| 32,768 | warmup / 1k / 8k | 約 17 分 |
| 65,536 | warmup / 1k / 8k / 32k | 約 30 分 |

合計 lock 占有時間: **約 60〜75 分**（起動 × 2、停止 × 2、lock/unlock 含む）。

eval は副次情報として採取（主目的は起動時 compute buffer の ctx 係数確定）。両 ctx で 32k プロンプト以上を流さないのは、ctx 係数評価には不要かつ時間削減のため。

## 構成

Phase R（P1）と**共通**:
- サーバ: `t120h-p100`
- モデル: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- llama.cpp: b8807-b3d758750（Phase Q/R と同一ビルド）
- NUMA: `numactl --cpunodebind=1 --membind=1 --`
- `--threads 40 --poll 0 -ngl 999`
- `-ot 'blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'`
- `--flash-attn 1 -b 2048 -ub 2048`
- `--cache-type-k f16 --cache-type-v f16`

Phase R-ctx3 で**可変**:
- `--ctx-size`: **32,768** および **65,536**

## 実装計画

### ステップ 1: 作業ディレクトリ準備

```bash
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
PHASE_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseR-ctx3-midpoints"
mkdir -p "$PHASE_DIR/startup_logs"

PHASE_R_DIR="report/attachment/2026-04-19_085127_qwen3-122b-c3-phaseR-ctx131k-ub2048"
cp "$PHASE_R_DIR"/{measure_phaseI.sh,run_all.sh,aggregate_results.sh,start_phaseR.sh} "$PHASE_DIR/"
cp -r "$PHASE_R_DIR/prompts" "$PHASE_DIR/"

# aggregate_results.sh: out_R_ → out_Rctx3_ へ 1 箇所置換（tag 衝突回避）
# start_phaseR.sh: REMOTE_LOG プレフィックスを phaseR_ → phaseRctx3_ に変更（ログ衝突回避のみ）
```

`start_phaseR.sh` / `measure_phaseI.sh` / `run_all.sh` は**環境変数駆動設計**（Phase R-R1 調査で確認済み）のため、ctx を環境変数で指定するのみで本体改変は不要。

### ステップ 2: ロック取得 + llama-server 起動（ctx=32768）

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
cd "$PHASE_DIR"

FLASH_ATTN=1 CTX_SIZE=32768 BATCH_SIZE=2048 UB_SIZE=2048 bash start_phaseR.sh
PID=$(ssh t120h-p100 "ps -eo pid,comm | awk '\$2==\"llama-server\"{print \$1;exit}'")
ssh t120h-p100 "cat /tmp/llama-server_phaseRctx3_fa1_ctx32768_b2048_ub2048.log" \
  > "startup_logs/fa1_ctx32768_b2048_ub2048.log"
```

### ステップ 3: ctx=32768 の warmup / 1k / 8k 計測

```bash
nohup env TAG_PREFIX="Rctx3_f16_fa1_ctx32768_b2048_ub2048" \
  SIZES="warmup 1k 8k" \
  GATE_SIZES="8k" GATE_MIB=1500 \
  PID=$PID bash run_all.sh > /tmp/run_all_Rctx3_32k.log 2>&1 < /dev/null & disown
# 完了待ち（約 17 分）
```

### ステップ 4: 停止 → ctx=65536 で同様に再計測

```bash
cd - && .claude/skills/llama-server/scripts/stop.sh t120h-p100 && cd "$PHASE_DIR"

FLASH_ATTN=1 CTX_SIZE=65536 BATCH_SIZE=2048 UB_SIZE=2048 bash start_phaseR.sh
PID=$(ssh t120h-p100 "ps -eo pid,comm | awk '\$2==\"llama-server\"{print \$1;exit}'")
ssh t120h-p100 "cat /tmp/llama-server_phaseRctx3_fa1_ctx65536_b2048_ub2048.log" \
  > "startup_logs/fa1_ctx65536_b2048_ub2048.log"

nohup env TAG_PREFIX="Rctx3_f16_fa1_ctx65536_b2048_ub2048" \
  SIZES="warmup 1k 8k 32k" \
  GATE_SIZES="32k" GATE_MIB=1500 \
  PID=$PID bash run_all.sh > /tmp/run_all_Rctx3_65k.log 2>&1 < /dev/null & disown
# 完了待ち（約 30 分）
```

### ステップ 5: 集計・分析・停止・lock 解放

```bash
cd - && .claude/skills/llama-server/scripts/stop.sh t120h-p100 && cd "$PHASE_DIR"

bash aggregate_results.sh > results.tsv

grep -E "sched_reserve:|KV buffer|graph nodes|graph splits|cudaMalloc|failed to allocate|model buffer|RS buffer|fused Gated|prompt cache is enabled|reserve took|llama_kv_cache: size|llama_memory_recurrent: size" \
  startup_logs/*.log > compute_buffer_summary.txt

# 新規 fit スクリプト（Phase Q P1 + Phase R R1 + 本 Phase の 32k/65k = 4 点で線形フィット）
python3 fit_analysis_Rctx3.py | tee fit_analysis_Rctx3.txt

cd - && .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### ステップ 6: `fit_analysis_Rctx3.py` の主要ロジック

Phase R の `fit_analysis_R.py` をベースに:

- 入力: 4 ctx 点（16384 / 32768 / 65536 / 131072）での CUDA0/1/2/3/Host MiB（16k は Phase Q P1 から、131k は Phase R R1 から、中間 2 点は本 Phase から）
- 出力:
  - 各 GPU の ctx 係数（傾き）と切片の最小二乗フィット
  - R²（決定係数）と最大誤差
  - **成功条件: CUDA0/1/2/Host で R² ≥ 0.99、CUDA3 は 4 点すべて 2,012.0 ± 0.5 MiB**
  - Phase R 2 点モデル（`CUDA0 = 951 + 0.077·ub + 0.00987·Δctx` など）と 4 点モデルの係数差分も出力

## 成果物

Phase ディレクトリ `report/attachment/${TS}_qwen3-122b-c3-phaseR-ctx3-midpoints/` に:

- `plan.md`（本プランのコピー）
- `start_phaseR.sh`（ログプレフィックスのみ変更）
- `measure_phaseI.sh` / `run_all.sh` / `aggregate_results.sh`（流用）
- `prompts/`（流用）
- `fit_analysis_Rctx3.py` / `fit_analysis_Rctx3.txt`（新規）
- `results.tsv`（新規、7 run 程度）
- `compute_buffer_summary.txt`（新規）
- `startup_logs/fa1_ctx32768_b2048_ub2048.log`
- `startup_logs/fa1_ctx65536_b2048_ub2048.log`
- `out_Rctx3_*` 計測アーティファクト

レポート本体: `report/${TS}_qwen3-122b-c3-phaseR-ctx3-midpoints.md`

レポートは [REPORT.md](../../projects/llm-server-ops/REPORT.md) に従い、末尾に **「未検証事項」** と **「検証完了後に実施すべき TODO」** セクションを含める（Phase R と同様の構造）。

## 重要な注意

- 本 Phase で**既存の skill ファイル（start.sh 等）は変更しない**。skill への `-ub=2048` / ctx=131072 デフォルト反映・2 変数 lint 組み込みは、本 Phase で 2 変数モデルが確定してから別タスクとして実施する（Phase R レポート「検証完了後に実施すべき TODO」の★最優先群）。
- llama-server の停止/ロック解放は、途中で失敗しても必ず実施する（冪等）。
- ctx=32768 は Phase I/J/M で試験済み、ctx=65536 も Phase I/L で 1k プロンプトは起動成功実績あり（-ub=8192 時）。今回は -ub=2048 のため VRAM 的にも余裕。

## 検証方法

1. **起動成功**: 両 ctx で /health OK、OOM / -ub 下限拒否ゼロ
2. **compute buffer 線形性**: `fit_analysis_Rctx3.py` が R² ≥ 0.99 を報告（CUDA0/1/2/Host）
3. **CUDA3 ctx 不依存**: 4 点すべて 2,012.0 ± 0.5 MiB
4. **KV buffer 比例性**: 各 ctx で `3,072 × (ctx / 131072)` MiB と一致（誤差 0.00 MiB）
5. **graph 構造不変**: nodes=4473、splits=136+77 が 4 点とも一致
6. **eval 速度**: warmup / 1k / 8k で Phase R R1 (ctx=131k) と同等かそれ以上（中間 ctx は長 ctx より速いはず）

## 参考: 重要ファイル

- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-19_085127_qwen3-122b-c3-phaseR-ctx131k-ub2048/start_phaseR.sh`（流用元）
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-19_085127_qwen3-122b-c3-phaseR-ctx131k-ub2048/fit_analysis_R.py`（fit_analysis_Rctx3.py のベース）
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh`
- `/home/ubuntu/projects/llm-server-ops/REPORT.md`（レポートフォーマット）
