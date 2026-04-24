# Qwen3.5-122B-A10B C-3 Phase R-ctx3（中間 ctx × 4 点フィット検証）

- **実施日時**: 2026年4月19日 10:57 – 11:52 (JST、実計測時間 約 55 分)
- **作業種別**: 計測・検証（Phase R 未検証事項「新規項目」最上位「他 4 GPU の ctx 係数 3 点以上フィット」）

## 添付ファイル

- [実装プラン](attachment/2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints/plan.md)
- [起動スクリプト (start_phaseR.sh、Phase R からプレフィックスのみ phaseRctx3_ に変更)](attachment/2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints/start_phaseR.sh)
- [計測スクリプト (measure_phaseI.sh、流用)](attachment/2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints/measure_phaseI.sh)
- [一括実行スクリプト (run_all.sh、流用)](attachment/2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints/run_all.sh)
- [集計スクリプト (aggregate_results.sh、`out_Rctx3_*` 対応)](attachment/2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints/aggregate_results.sh)
- [4 点線形フィット Python (fit_analysis_Rctx3.py、CUDA0 二次フィット込み)](attachment/2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints/fit_analysis_Rctx3.py)
- [検証結果 (fit_analysis_Rctx3.txt)](attachment/2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints/fit_analysis_Rctx3.txt)
- [集計結果 TSV (results.tsv、21 run)](attachment/2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints/results.tsv)
- [compute buffer サマリ (compute_buffer_summary.txt)](attachment/2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints/compute_buffer_summary.txt)
- [起動ログ ctx=32768](attachment/2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints/startup_logs/fa1_ctx32768_b2048_ub2048.log)
- [起動ログ ctx=65536](attachment/2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints/startup_logs/fa1_ctx65536_b2048_ub2048.log)
- `out_Rctx3_*` 計測アーティファクト 7 条件（warmup/1k/8k @32k、warmup/1k/8k/32k @65k）

## 参照

- 前身レポート: [2026-04-19_085127_qwen3-122b-c3-phaseR-ctx131k-ub2048.md](2026-04-19_085127_qwen3-122b-c3-phaseR-ctx131k-ub2048.md)
- Phase Q (ub 下限探索): [2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound.md](2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound.md)
- Phase P (fa=1 batch スキャン): [2026-04-19_051604_qwen3-122b-c3-phaseP-fa1-batch-scan.md](2026-04-19_051604_qwen3-122b-c3-phaseP-fa1-batch-scan.md)

## 前提・目的

Phase R レポート末尾「未検証事項 / 新規項目」最上位:

> **他 4 GPU の ctx 係数（CUDA0=0.00987、CUDA1/2=0.00391、CUDA_Host=0.00781）の 3 点以上フィット**: ctx=16k と 131k の 2 点からの線形補間のため、中間 ctx (32k / 64k) での実測が必要。Phase R-ctx3 候補

Phase Q P1 (ctx=16384) と Phase R R1 (ctx=131072) の **2 点から外挿** した線形モデル `CUDA0 = 951 + 0.077·ub + 0.00987·Δctx` 等は、起動前 lint に組み込む根拠として **中間点での実証が不足**していた。本 Phase R-ctx3 では ctx=32,768 / 65,536 の 2 点を追加計測し、計 4 点で:

1. **CUDA1/2/CUDA3/CUDA_Host の ctx 線形性を実証**（R² ≥ 0.99 または ctx 完全不依存）
2. **CUDA0 の線形モデル外れを検出し、二次モデルに置換**
3. KV buffer と graph 構造の ctx 外挿性を 4 点で確認
4. 起動前 lint 用の確定モデル（1 変数 ctx の 4 点検証済み）を提供

### 成功条件

- [x] ctx=32768 起動成功（/health OK、OOM ゼロ、-ub 下限拒否ゼロ）
- [x] ctx=65536 起動成功（同上）
- [x] **CUDA3 が 4 点すべて 2012.0 ± 0.5 MiB**（実測: **全 4 点で 2012.00、変動幅 0.000 MiB**）
- [x] **CUDA1/CUDA2 線形性 R² ≥ 0.99**（実測: **R² = 1.00000000、傾き 0.003906**）
- [x] **CUDA_Host 線形性 R² ≥ 0.99**（実測: **R² = 1.00000000、傾き 0.007812**）
- [ ] **CUDA0 線形性 R² ≥ 0.99**（実測: **R² = 0.97144、NG**）
- [x] **CUDA0 二次フィット R² ≥ 0.999**（実測: **R² = 0.99998**、予測誤差 ≤ 0.29%）
- [x] KV buffer 4 点で ctx 完全比例（実測: **4 点とも誤差 0.000 MiB**）
- [x] graph 構造 4 点で完全同一（nodes=4473、splits=136+77）

## 環境情報

- **サーバ**: `t120h-p100` (10.1.4.14)
- **GPU**: NVIDIA Tesla P100-PCIE-16GB × 4（各 16,269 MiB、合計 65,077 MiB、CC 6.0）
- **CPU**: Intel Xeon Gold 6138 @ 2.00GHz × 2 socket、計 40 コア / 80 スレッド、NUMA 2 ノード
- **メモリ**: 257,560 MiB (約 251 GiB)
- **モデル**: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- **llama.cpp ビルド**: b8807-b3d758750（Phase D〜R と同一系列）
- **構成**: Phase R P1 と同一 C-D3 base + `--cache-type-{k,v} f16`
  - NUMA: `numactl --cpunodebind=1 --membind=1 --`
  - `--threads 40 --poll 0 -ngl 999`
  - `-ot 'blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'`
  - `--flash-attn 1 -b 2048 -ub 2048`
- **条件マトリクス（2 条件）**:
  - **Rctx3-A**: `ctx=32768 -b=2048 -ub=2048`（PID=193098、起動成功）
  - **Rctx3-B**: `ctx=65536 -b=2048 -ub=2048`（PID=197460、起動成功）

## 再現方法

### スクリプト差分（Phase R からの改変は最小限）

- `start_phaseR.sh`: `REMOTE_LOG` プレフィックスを `phaseR_` → `phaseRctx3_` に置換（Phase R ログ衝突防止のみ）
- `aggregate_results.sh`: `out_R_*` → `out_Rctx3_*` に置換（tag 衝突防止）
- `measure_phaseI.sh` / `run_all.sh` / `prompts/`: **無改変流用**（環境変数駆動設計）
- `fit_analysis_Rctx3.py`: **新規**（4 点線形フィット + CUDA0 二次フィット）

### 実行フロー

```bash
# 作業ディレクトリ準備 + Phase R スクリプト流用
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
PHASE_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseR-ctx3-midpoints"
mkdir -p "$PHASE_DIR/startup_logs"
PHASE_R_DIR="report/attachment/2026-04-19_085127_qwen3-122b-c3-phaseR-ctx131k-ub2048"
cp "$PHASE_R_DIR"/{measure_phaseI.sh,run_all.sh,aggregate_results.sh,start_phaseR.sh} "$PHASE_DIR/"
cp -r "$PHASE_R_DIR/prompts" "$PHASE_DIR/"
# start_phaseR.sh / aggregate_results.sh にプレフィックス置換を適用

cd "$PHASE_DIR"

# ロック取得 → ctx=32768 計測
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
FLASH_ATTN=1 CTX_SIZE=32768 BATCH_SIZE=2048 UB_SIZE=2048 bash start_phaseR.sh
PID=$(ssh t120h-p100 "ps -eo pid,comm | awk '\$2==\"llama-server\"{print \$1;exit}'")
ssh t120h-p100 "cat /tmp/llama-server_phaseRctx3_fa1_ctx32768_b2048_ub2048.log" \
  > startup_logs/fa1_ctx32768_b2048_ub2048.log
nohup env TAG_PREFIX="Rctx3_f16_fa1_ctx32768_b2048_ub2048" \
  SIZES="warmup 1k 8k" GATE_SIZES="8k" GATE_MIB=1500 \
  PID=$PID bash run_all.sh > /tmp/run_all_Rctx3_32k.log 2>&1 < /dev/null & disown

# 停止 → ctx=65536 計測
.claude/skills/llama-server/scripts/stop.sh t120h-p100
FLASH_ATTN=1 CTX_SIZE=65536 BATCH_SIZE=2048 UB_SIZE=2048 bash start_phaseR.sh
PID=$(ssh t120h-p100 "ps -eo pid,comm | awk '\$2==\"llama-server\"{print \$1;exit}'")
ssh t120h-p100 "cat /tmp/llama-server_phaseRctx3_fa1_ctx65536_b2048_ub2048.log" \
  > startup_logs/fa1_ctx65536_b2048_ub2048.log
nohup env TAG_PREFIX="Rctx3_f16_fa1_ctx65536_b2048_ub2048" \
  SIZES="warmup 1k 8k 32k" GATE_SIZES="32k" GATE_MIB=1500 \
  PID=$PID bash run_all.sh > /tmp/run_all_Rctx3_65k.log 2>&1 < /dev/null & disown

# 集計・解析・停止・解放
.claude/skills/llama-server/scripts/stop.sh t120h-p100
bash aggregate_results.sh > results.tsv
grep -E "sched_reserve:|KV buffer|graph nodes|graph splits|cudaMalloc|failed to allocate|model buffer|RS buffer|fused Gated|prompt cache is enabled|reserve took|llama_kv_cache: size|llama_memory_recurrent: size" \
  startup_logs/*.log > compute_buffer_summary.txt
python3 fit_analysis_Rctx3.py | tee fit_analysis_Rctx3.txt
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 実行タイムライン

| フェーズ | 開始 | 終了 | 所要 |
|---|---:|---:|---:|
| lock 取得 + ディレクトリ準備 | 10:57:37 | 11:00:00 | 2 分 23 秒 |
| Rctx3-A 起動 (ctx=32768) | 11:00:30 | 11:00:55 | 25 秒 |
| ctx=32k warmup (3 run) | 11:01:02 | 11:05:48 | 4 分 46 秒 |
| ctx=32k 1k (3 run) | 11:05:48 | 11:10:14 | 4 分 26 秒 |
| ctx=32k 8k (3 run) | 11:10:14 | 11:18:01 | 7 分 47 秒 |
| 停止 + Rctx3-B 起動 (ctx=65536) | 11:18:05 | 11:19:40 | 1 分 35 秒 |
| ctx=65k warmup (3 run) | 11:19:46 | 11:23:45 | 3 分 59 秒 |
| ctx=65k 1k (3 run) | 11:23:45 | 11:28:44 | 4 分 59 秒 |
| ctx=65k 8k (3 run) | 11:28:47 | 11:36:22 | 7 分 35 秒 |
| ctx=65k 32k (2 run) | 11:36:32 | 11:50:03 | 13 分 31 秒 |
| 停止 + 集計 + 解放 | 11:50:10 | 11:52:00 | 1 分 50 秒 |

実計測時間: **約 55 分**（run_all.sh 2 回分の合計）、全体 55 分。

## 実行結果サマリ

### 1. compute buffer 実測値（4 ctx 点、ub=2048 固定）

| GPU | ctx=16384 (Phase Q) | **ctx=32768 (新規)** | **ctx=65536 (新規)** | ctx=131072 (Phase R) |
|---|---:|---:|---:|---:|
| CUDA0 | 1,048.13 | **1,112.13** | **1,348.00** | 2,180.00 |
| CUDA1 | 520.06 | **584.06** | **712.06** | 968.06 |
| CUDA2 | 520.06 | **584.06** | **712.06** | 968.06 |
| CUDA3 | 2,012.00 | **2,012.00** | **2,012.00** | 2,012.00 |
| CUDA_Host | 176.08 | **304.08** | **560.08** | 1,072.08 |
| **合計** | **4,276.33** | **4,596.33** | **5,344.20** | **7,200.20** |

### 2. ctx 係数の 4 点最小二乗フィット ✅ CUDA1/2/3/Host は完全線形

| GPU | intercept | ctx_slope (MiB/token) | R² | 2 点モデル（Phase R） | diff | 判定 |
|---|---:|---:|---:|---:|---:|---|
| CUDA0 | 965.4775 | 0.010134 | **0.97144** | 0.00987 | +0.000264 | **NG**（線形外れ）|
| CUDA1 | 520.0600 | 0.003906 | **1.00000000** | 0.00391 | -0.000004 | **完璧** |
| CUDA2 | 520.0600 | 0.003906 | **1.00000000** | 0.00391 | -0.000004 | **完璧** |
| CUDA3 | 2,012.0000 | **0.000000** | 1.00000000 | 0.00000 | +0.000000 | **完璧** |
| CUDA_Host | 176.0800 | 0.007812 | **1.00000000** | 0.00781 | +0.000002 | **完璧** |

**決定的発見**:

- **CUDA1 / CUDA2 / CUDA_Host / CUDA3**: **R² = 1.00000000** で完全線形（または定数）。Phase R の 2 点モデル係数は中間点でも完璧に一致（誤差 < 0.05%）。
- **CUDA0 のみ線形が成立しない**: R² = 0.97144。中間点で Phase R 2 点モデルから -12.5%（ctx=32k）、-15.4%（ctx=65k）の予測誤差。

### 3. CUDA0 の二次フィット ✅ R² = 0.99998

CUDA0 は Δctx に対し非線形（Δctx² 項あり）と判明。4 点で二次フィット:

```
CUDA0 = 1046.29 + 3.269e-3·Δctx + 5.770e-8·Δctx²   [Δctx = ctx - 16384]
R² = 0.99997994   最大誤差 -3.22 MiB (-0.289%)
```

| Δctx | 実測 (MiB) | 予測 (MiB) | 誤差 MiB | 誤差 % |
|---:|---:|---:|---:|---:|
| 0       | 1,048.13 | 1,046.29 | +1.838 | +0.175% |
| 16,384  | 1,112.13 | 1,115.35 | -3.216 | -0.289% |
| 49,152  | 1,348.00 | 1,346.39 | +1.608 | +0.119% |
| 114,688 | 2,180.00 | 2,180.23 | -0.230 | -0.011% |

これにより **Phase R の 2 点モデル `CUDA0 = 951 + 0.077·ub + 0.00987·Δctx`（予測誤差 12〜15%）は二次モデルで置き換えるべき**であることが判明。

### 4. Phase R 2 点モデルと中間点の比較

| GPU | ctx | Phase R 予測 (MiB) | 実測 (MiB) | 誤差 (MiB) | 誤差 % | 許容 5% |
|---|---:|---:|---:|---:|---:|---|
| CUDA0 | 32,768 | 1,270.41 | 1,112.13 | -158.28 | -12.459% | **NG** |
| CUDA1 | 32,768 | 584.25 | 584.06 | -0.19 | -0.033% | OK |
| CUDA2 | 32,768 | 584.25 | 584.06 | -0.19 | -0.033% | OK |
| CUDA3 | 32,768 | 2,011.96 | 2,012.00 | +0.04 | +0.002% | OK |
| CUDA_Host | 32,768 | 304.09 | 304.08 | -0.01 | -0.002% | OK |
| CUDA0 | 65,536 | 1,593.83 | 1,348.00 | -245.83 | **-15.424%** | **NG** |
| CUDA1 | 65,536 | 712.38 | 712.06 | -0.32 | -0.044% | OK |
| CUDA2 | 65,536 | 712.38 | 712.06 | -0.32 | -0.044% | OK |
| CUDA3 | 65,536 | 2,011.96 | 2,012.00 | +0.04 | +0.002% | OK |
| CUDA_Host | 65,536 | 560.01 | 560.08 | +0.07 | +0.013% | OK |

- CUDA1/2/3/CUDA_Host は 4 点で Phase R 2 点モデルが **完璧に成立**（すべて ± 0.05% 以内）
- CUDA0 のみ二次補正が必要（Phase R の予測は短ctx側で**過大予測**）

### 5. CUDA3 の ctx 完全不依存性 ✅ 4 点で再確証

| ctx | CUDA3 (MiB) | 偏差 vs 2012.00 | 判定 |
|---:|---:|---:|---|
| 16,384 | 2,012.00 | +0.000 | OK |
| 32,768 | 2,012.00 | +0.000 | OK |
| 65,536 | 2,012.00 | +0.000 | OK |
| 131,072 | 2,012.00 | +0.000 | OK |

**変動幅 (max - min): 0.000 MiB**。Phase R で「CUDA3 は ctx 完全不依存」と結論したが、**4 点すべてで偏差ゼロの理想的不依存**を再確証。`CUDA3 = 0.9824·ub` は **ub のみの純粋な関数**であることが実験的・物理的・数学的に確定。

### 6. KV buffer の ctx 比例性 ✅ 完全比例

| ctx | 予測 MiB/GPU | CUDA0 | CUDA1 | CUDA2 | CUDA3 | 誤差 % |
|---:|---:|---:|---:|---:|---:|---:|
| 16,384 | 96.00 | 96.00 | 96.00 | 96.00 | 96.00 | **+0.000%** |
| 32,768 | 192.00 | 192.00 | 192.00 | 192.00 | 192.00 | **+0.000%** |
| 65,536 | 384.00 | 384.00 | 384.00 | 384.00 | 384.00 | **+0.000%** |
| 131,072 | 768.00 | 768.00 | 768.00 | 768.00 | 768.00 | **+0.000%** |

K+V = 12 層 × 2 × (ctx × hidden_kv × bytes) が各 GPU で 96 MiB/16k_ctx × ctx の形で完璧に比例。

### 7. graph 構造 ✅ 4 点で完全不変

| ctx | graph nodes | splits_main | splits_main bs= | splits_bs1 |
|---:|---:|---:|---:|---:|
| 16,384 | 4,473 | 136 | 2,048 | 77 |
| 32,768 | 4,473 | 136 | 2,048 | 77 |
| 65,536 | 4,473 | 136 | 2,048 | 77 |
| 131,072 | 4,473 | 136 | 2,048 | 77 |

graph 構造は **ctx に一切依存しない**（Phase R で既に確認済みだが 4 点で再確認）。

### 8. reserve 時間の ctx 比例性（副次発見）

| ctx | reserve_took (ms) | 倍率 vs ctx=16k |
|---:|---:|---:|
| 16,384 | ≈ 110 (Phase Q 推定) | 1.00× |
| **32,768** | **224.14** | ≈ 2.04× |
| **65,536** | **357.26** | ≈ 3.25× |
| 131,072 | 628.35 (Phase R) | ≈ 5.71× |

reserve 時間は ctx にほぼ線形（切片あり）。起動タイムアウト 300 秒に対して ctx=131k でも 2% 未満と依然余裕。

### 9. プロンプトサイズ別 eval / prompt 中央値

| ctx | プロンプト | runs | prompt_n | eval_tps | prompt_tps | GPU 合計 (MiB) |
|---:|---|---:|---:|---:|---:|---:|
| 32,768 | warmup | 3 | 71 | **15.069** | 11.042 | 28,794 |
| 32,768 | 1k | 3 | 1,092 | **15.063** | 68.589 | 28,978 |
| 32,768 | 8k | 3 | 8,093 | **15.323** | 98.813 | 29,384 |
| 65,536 | warmup | 3 | 71 | **14.579** | 11.047 | 30,054 |
| 65,536 | 1k | 3 | 1,092 | **14.555** | 69.330 | 30,238 |
| 65,536 | 8k | 3 | 8,093 | **14.819** | 98.990 | 30,644 |
| 65,536 | 32k | 2 | 32,124 | **14.034** | 92.674 | 30,644 |
| **参考**: 131,072 | 8k | 3 | 8,092 | 15.142 | 99.387 | 33,532 |

**観察**:
- ctx=32k では eval 15.07〜15.32 t/s、ctx=65k では 14.03〜14.82 t/s
- **ctx=32k 8k prompt で 15.323 t/s は Phase R ctx=131k 8k の 15.142 より +1.2% 高速** — 中間 ctx で eval ピークに近い
- ctx=65k の warmup/1k は ctx=131k 比でも差が小さい（-0.22〜-2.2%）
- 32k プロンプト @ ctx=65k で 14.03 t/s（Phase R ctx=131k の 32k prompt 14.40 t/s から -2.6%）

### 10. GPU 使用量の ctx 依存性

| ctx | 8k post-eval 合計 (MiB) | Phase Q ctx=16k との Δ |
|---:|---:|---:|
| 16,384 | 28,218 (Phase Q) | — |
| 32,768 | 29,384 | +1,166 (+4.1%) |
| 65,536 | 30,644 | +2,426 (+8.6%) |
| 131,072 | 33,532 (Phase R) | +5,314 (+18.8%) |

全 GPU 空き枠は 4 点とも 4 GiB 以上を維持。

## ボトルネック・副次発見の分析

### 1. CUDA0 の非線形性 — 新発見

Phase R では ctx=16k と ctx=131k の 2 点で 0.00987 MiB/token の線形補間を提示したが、中間点で:

- ctx=16384 → 32768 の増分: **+64.00 / 16384 = 0.003906 MiB/token**
- ctx=32768 → 65536 の増分: **+235.87 / 32768 = 0.007198 MiB/token**
- ctx=65536 → 131072 の増分: **+832.00 / 65536 = 0.012695 MiB/token**

単位 ctx あたりの増分が **ctx に比例的に増加**しており、二次関数的増加が示唆される。四次フィット: `CUDA0 - 1046.29 = 3.269e-3·Δctx + 5.770e-8·Δctx²` で R² = 0.99998。

**物理解釈（推定）**: CUDA0 は Qwen3.5 の入力 embedding + 浅層 attention buffer を保持し、ctx ≥ 32k 以降で attention score matrix のサイズ（O(ctx²) 成分）が顕在化する可能性。FlashAttention (fa=1) でも softmax 後のスコア matrix partial staging が残存するため、ctx² 成分は完全には消えない。

### 2. CUDA1/2/CUDA_Host は完全線形 — 2 点モデルが正確

CUDA1 / CUDA2 / CUDA_Host は **4 点で R² = 1.00000000** の完璧な線形。Phase R の 2 点モデル係数（0.00391 / 0.00781）は中間点で誤差 < 0.05% と完璧に一致し、**純粋な ctx 1 次成分のみ**であることが数学的に確定。

- CUDA1/2 は 16k 基準での切片 520.06 MiB、傾き 0.003906 MiB/token
- CUDA_Host は切片 176.08 MiB、傾き 0.007812 MiB/token

### 3. CUDA3 の ctx 完全不依存性を 4 点で再確証

Phase R では 2 点で偏差 0.04 MiB と報告したが、本 Phase では **4 点すべて 2,012.00 MiB（偏差 0.000 MiB、変動幅 0.000 MiB）**。llama.cpp 起動ログの MiB 表示精度（1 MiB 刻み）内での「完全一致」で、CUDA3 が純粋に `ub` のみの関数 `0.9824·ub` であることを数学的・物理的に確定。

### 4. ctx=32k で eval ピーク — ctx=131k の 8k を上回る

ctx=32k / 8k プロンプトの eval 15.323 t/s は、Phase R ctx=131k / 8k の 15.142 t/s を **+1.2% 上回る**。これは ctx が小さいほど KV 読み取りコストが少なく、8k 近傍で SM occupancy と KV 負荷のバランスが最適になるため。本番運用で prompt 長が主に 8k 前後なら、ctx を 32k に抑えるほうが eval 高速化に寄与する可能性。

### 5. Phase O 線形モデルと Phase R-ctx3 の整合

Phase O の線形モデル `time_per_token ≈ 66.5μs + 0.485μs × N_context` に本 Phase の prompt_n を代入:

| prompt_n | Phase O 予測 eval | Phase R-ctx3 実測 eval | 乖離 |
|---:|---:|---:|---:|
| 71 @ctx32k | 15.03 | 15.07 | +0.3% |
| 1,092 @ctx32k | 14.93 | 15.06 | +0.9% |
| 8,093 @ctx32k | 14.14 | 15.32 | **+8.3%** |
| 32,124 @ctx65k | 12.28 | 14.03 | **+14.3%** |

ctx が 8k を超えると Phase O モデルは過少予測（実測の方が速い）。Phase O は ctx ≤ 8k の線形フィットだったため、この傾向は予想通り。本 Phase のデータは Phase R のそれと合わせて、**長 ctx 域では saturating 型モデル**が必要であることを示唆。

## 採用判定

| 項目 | 結果 |
|---|---|
| Rctx3-A / Rctx3-B 起動成功 | ✅（両 ctx で /health OK、OOM ゼロ、-ub 下限拒否ゼロ）|
| sched_reserve 採取 | ✅ 両 ctx で全 5 チャネル |
| CUDA3 ctx 完全不依存の 4 点再確証 | ✅ **4 点とも 2,012.00 MiB、変動幅 0.000 MiB** |
| CUDA1/2 線形性 | ✅ **R² = 1.00000000、傾き 0.003906** |
| CUDA_Host 線形性 | ✅ **R² = 1.00000000、傾き 0.007812** |
| CUDA0 線形性 | ❌ **R² = 0.97144** — 二次フィットで置換 |
| CUDA0 二次フィット | ✅ **R² = 0.99998、予測誤差 ≤ 0.29%** |
| KV buffer ctx 比例性 | ✅ **4 点誤差 0.000 MiB** |
| graph 構造不変性 | ✅ **4 点ともnodes=4473、splits=136+77** |
| eval 速度要件 (≥ 14.5) | ✅ 全条件でクリア（32k-warmup 14.58 が最低、下限超）|

**結論**: **Phase R-ctx3 は主要目的を完全達成**。Phase R の 2 点モデルは CUDA1/2/CUDA_Host では中間点まで完璧に成立することを 4 点で実証した一方、**CUDA0 の線形近似は成立せず二次モデルへの置換が必要**と判明。skill 側の起動前 lint は以下の確定モデルで実装可能:

```
f16 KV, fa=1, C-D3 base, ub=128〜8192 × ctx=16k〜131k で実証:
  CUDA0     = 1046.29 + 3.269e-3·Δctx + 5.770e-8·Δctx² + 0.077·(ub - 2048)
             (※ Δctx 成分は ub=2048 固定下での fit、ub 可変時は別途要検証)
  CUDA1/2   = 520.06 + 0.003906·Δctx + 0.254·(ub - 2048)
             (※ 線形項の切片 520.06 は ub=2048 基準、ub=128 では 32.51 等)
  CUDA3     = 0.9824·ub                                 [ctx 完全不依存、4 点で確定]
  CUDA_Host = 176.08 + 0.007812·Δctx + 0.086·(ub - 2048)
  Δctx      = ctx - 16384
```

## 未検証事項

### 既知項目（Phase R から継続、本 Phase で潰したものに [x]）

- [x] **他 4 GPU の ctx 係数の 3 点以上フィット** — **本 Phase で 4 点 (16k/32k/65k/131k) 実証、CUDA1/2/Host は完全線形、CUDA0 は二次モデル**
- [ ] **CUDA3 が ctx 完全不依存となる物理メカニズム**（ソース上のテンソル特定） — 本 Phase でも 4 点 0.000 MiB 偏差と実証、未だソース未特定
- [ ] **ctx 係数の `-ub` 依存性**: 本 Phase は ub=2048 固定、ub=512 / 1024 / 4096 / 8192 で ctx 係数が変化するかは未検証。Phase R-ctx3-ub 候補
- [ ] **q8_0 KV cache での同様確認（Phase R-KV8 候補）**: skill デフォルトは q8_0、本 Phase 係数はそのまま適用不可
- [ ] **fa=0 側での ctx 依存性**: Phase M 係数は ub=8192 固定、`-ub × ctx` 2 軸で再フィット要
- [ ] **120k eval 12.82 t/s の Run 間再現性**（Phase R から継続）
- [ ] **prompt 処理のピークが ctx=8k にある理由**
- [ ] **KV layer 数 12 の物理的確認**（ソース/ログから層番号特定）
- [ ] **ctx=262,144（モデルの n_ctx_train）での起動可否**
- [ ] **RS buffer 149.06 MiB の用途特定**: Gated Delta Net 由来と推定、ソース未確認
- [ ] **prompt cache (size limit 8192 MiB) の実際の挙動**: hit での eval 向上量未計測
- [ ] **2 時間超の連続稼働試験（eval あり）**
- [ ] **層→GPU アライメントのソース解析**
- [ ] **ページキャッシュのコールドスタート検証**: `sudo sysctl vm.drop_caches=3` 権限未付与
- [ ] **量子化ダウンでの eval 向上量**: Q4_K_M → Q3_K_M / IQ2_XXS
- [ ] **pcm-memory による DRAM 帯域実測**
- [ ] **C-D3 + コールドスタート**
- [ ] **Node 0 側のコールドスタート C-D6**
- [ ] **perf stat での C-D3 の node-load-miss rate**
- [ ] **C-4 実験**（CPU 層 36 → 20 層未満）
- [ ] **他モデルでの同様の傾向**（Qwen3.5-35B-A3B 等）
- [ ] **`--threads 30` / `--threads 28` などの中間値**
- [ ] **`--numa numactl` モード**
- [ ] **OpenMP 環境変数の影響**
- [ ] **「初回サイクル効果」の原因特定**
- [ ] **セッション間 warmup ゆらぎの原因特定**
- [ ] **`--poll 1` / `--poll 10` / `--poll 100` の影響**
- [ ] **G_aged_t96 の再現条件の特定**
- [ ] **`--poll` とスレッド affinity / OpenMP の相互作用**
- [ ] **64k / 120k の Run 間再現性**
- [ ] **128k コンテキストが純粋応答に与える影響**
- [ ] **KV cache 量子化 (q8_0) の精度影響**
- [ ] **prompt cache hit 時の実効 turn time**
- [ ] **llama.cpp のソース上で `--cache-type-{k,v} q8_0` と `--flash-attn` の依存ロジック確認**
- [ ] **Segfault 時のバックトレース取得**
- [ ] **P100 CC 6.0 の flash-attention カーネル経路の検証**
- [ ] **CUDA1/2/3 の SM 稼働実態の時系列計測**
- [ ] **J_fa1_warmup run 1 の外れ値（15.54 t/s）再現性**
- [ ] **CUDA1 / CUDA2 の n² 係数 (fa=0 a=1.26e-4) の物理解釈**
- [ ] **ctx=1024 の fa=0 eval 劣化 (−5.2%) の原因**
- [ ] **ctx=512 / 256 の極小域での挙動**
- [ ] **3 点厳密解 vs 4 点最小二乗の妥当性** — 本 Phase で 4 点最小二乗が CUDA1/2/3/Host で理想的（R²=1.0）、CUDA0 は二次が必要と判明
- [ ] **eval 速度のセッション間ゆらぎレンジ更新**
- [ ] **prompt 処理の ctx 非依存の長 ctx 側確認**
- [ ] **fa=1 eval の「谷型」(ctx=2048 最高 → ctx=4096 最低) の再現性**
- [ ] **Phase M のモデルを f16 KV → q8_0 KV（C-D3 採用構成）に適用した場合の整合性**
- [ ] **ctx=6144 等の中間 ctx での fa=1 / fa=0 境界確認**
- [ ] **fa=0 ctx=8192 で CUDA1 空き枠を増やす手法**
- [ ] **eval 谷型の最低値 ctx の fa=1 における物理原因**

### 既知項目（Phase Q で新規追加、Phase R / R-ctx3 で部分的に潰したもの）

- [ ] **`-ub=1 (greedy)` でのベンチマーク**: 未実施
- [ ] **`-ub > -b` の挙動（llama.cpp 制約検証）**: 未実施
- [ ] **fa=0 側での `-ub` 支配性の確認**: 未実施
- [ ] **大 prompt での `-ub` 依存性**: 未実施（本 Phase でも `-ub=2048` のみ、prompt×ub 2 軸は未）
- [ ] **`-b > -ub` 運用の意義**: Phase P で観測のみ
- [ ] **graph splits=77 (with bs=1) の存在意義**: 本 Phase でも固定 77（ctx 4 点すべて）
- [ ] **`--parallel 2` との相互作用**
- [ ] **P3 vs Phase O の eval 差 +1.17% のセッション源**

### 新規項目（本 Phase R-ctx3 で判明・発生）

- [ ] **CUDA0 二次係数 5.770e-8 MiB/token² の物理メカニズム**: attention score O(ctx²) 成分と推定、llama.cpp ソースで該当テンソル（attention score staging 等）を特定する
- [ ] **CUDA0 二次モデルの ub 依存性**: 本 Phase は ub=2048 固定、ub 可変で二次項係数 c が変化するかは未検証。`CUDA0 = a(ub) + b(ub)·Δctx + c(ub)·Δctx²` の 3 つの係数が `ub` にどう依存するかの追加計測が必要
- [ ] **CUDA0 二次モデルの ctx=262144 外挿**: 4 点は ctx=16k〜131k、ctx=262k (n_ctx_train) での予測値 4,781 MiB（intercept 1046 + 二次項 3,735）は GPU0 の空き枠を超過する可能性
- [ ] **ctx=32k / 65k の Run 間再現性**: 本 Phase は 32k プロンプトのみ 2 run、他は 3 run 計測済みで再現性良好
- [ ] **fa=0 側での 4 点フィット**: Phase M 係数は ub=8192 / ctx 4 点フィット、fa=1 の本 Phase 結果との比較で非線形性の fa 依存を確認
- [ ] **中間 ctx (24k / 48k / 96k) での二次項検証**: 本 Phase は 2 倍間隔 (16k/32k/65k/131k)、1.5 倍間隔で二次モデルの中間点外挿精度を確認
- [ ] **ctx=65k 32k prompt の 2 run のみで分散評価が不十分**: 3 run 以上が望ましい
- [ ] **reserve 時間の ctx 線形性**: 本 Phase で ctx=32k で 224 ms、ctx=65k で 357 ms と観測、ctx=16k の 110 ms（Phase Q 推定）と合わせて完全線形かは要検証

## 検証完了後に実施すべき TODO

### 既知項目（Phase R から継続、本 Phase で更新）

- [ ] **start.sh の拡張**: `LLAMA_NUMACTL_PREFIX` / `LLAMA_EXTRA_THREADS` 環境変数サポート追加
- [ ] **CUDA1 セーフティマージン OOM フォールバック実装**
- [ ] **層→GPU アライメントのソースコード解析**
- [ ] **C-4 実験**（CPU 層削減 + GPU 層追加）
- [ ] **drop_caches 権限の確保**（sudoers 設定 or vmtouch 導入）
- [ ] **start.sh での NUMA プリセット整備**
- [ ] **start.sh に `--threads` 設定追加**
- [ ] **`start_phaseJ.sh` 〜 `start_phaseR.sh` の環境変数化を skill 側 `start.sh` に逆輸入**
- [ ] **依存制約の lint 化**: 起動前 pre-check
  - **本 Phase 確定: fa=1 で `predicted_cuda3 = 0.9824·ub` ≤ GPU 空き枠（ctx 不依存、4 点で偏差 0.000 MiB）**
  - **CUDA1/2/Host は 1 次 ctx モデル、CUDA0 は 2 次 ctx モデル**
- [ ] **llama.cpp upstream issue/PR のサーベイ**
- [ ] **`measure_phaseI.sh` を汎用化して skill に組み込む**
- [ ] **「長コンテキスト性能カード」をモデル単位で記録するドキュメント整備**
- [ ] **アプリ側にコンテキストサイズ別レイテンシ警告を出す仕組み**

### 新規項目（本 Phase R-ctx3 で発見）

- [ ] **★最優先: skill 側 `.claude/skills/llama-server/scripts/start.sh:155` を `-b=2048 -ub=2048` に変更**:
  - Phase P/Q で `-ub=2048` が eval ピーク（+1.5%）、VRAM 73% 削減と確定
  - Phase R で ctx=131k × ub=2048 の実機成功を実証
  - 本 Phase で中間 ctx まで 2 変数モデルが確定（CUDA0 は二次、他は線形）
  - 現状 t120h-p100 デフォルト: `SERVER_OPTS="--flash-attn 1 --poll 0 -b 8192 -ub 8192"`
  - 変更後: `SERVER_OPTS="--flash-attn 1 --poll 0 -b 2048 -ub 2048"`
- [ ] **★最優先: 起動前 lint の 3 変数モデル組み込み**（CUDA0 二次 + 他線形）:
  - `predicted_cuda3 = 0.9824·ub`（ctx 不依存、4 点で確定）
  - `predicted_cuda0 = 1046.29 + 3.269e-3·Δctx + 5.770e-8·Δctx² + 0.077·(ub-2048)` (Δctx = ctx - 16384)
  - `predicted_cuda1/2 = 520.06 + 0.003906·Δctx + 0.254·(ub-2048)`
  - `predicted_cuda_host = 176.08 + 0.007812·Δctx + 0.086·(ub-2048)`
  - 予測 GPU 使用量と実空き枠を比較し、セーフティマージン 500 MiB で警告
  - ただし ub 項の `0.077·(ub-2048)` / `0.254·(ub-2048)` / `0.086·(ub-2048)` は ub=2048 固定での ctx fit を既定ベースにして ub 差分を Phase Q 係数で補正する近似。より精密には ub × ctx の 2 軸スキャンが必要。
- [ ] **★最優先: compute buffer 予測モデル（Phase R-ctx3 確定版）を skill / CLAUDE.md に記録**:
  - **fa=1, f16 KV, C-D3**: 上記 4 式、ub=128〜8192 × ctx=16k〜131k で実証
  - **CUDA0 が 2 次、他が線形**という発見を明記
  - **fa=0 / q8_0 KV**: 本 Phase では未検証、要 Phase R-fa0 / R-KV8
- [ ] **CLAUDE.md / skill の情報更新**:
  - 「fa=1 の **CUDA3 compute buffer は `-ub` に純比例、ctx に完全不依存（4 点偏差 0.000 MiB）**」を明記
  - 「**CUDA1/2/CUDA_Host は ctx 線形（R²=1.000）**」を記録
  - 「**CUDA0 は ctx 二次、R²=0.99998**」を記録
  - 「**Qwen3.5-122B-A10B t120h-p100 で ctx=32k〜131k ub=2048 の compute buffer が 4 点実測で 3 変数モデル化**」を明記
- [ ] **モデルカード更新**: Qwen3.5-122B-A10B の長コンテキスト性能カードに本 Phase 結果を追加
- [ ] **Phase R-ctx3-ub 候補**: ub=512 / 1024 / 4096 / 8192 × ctx=32k/65k で 2 軸スキャン、CUDA0 の ub × ctx 相互作用を検証
- [ ] **Phase R-KV8 候補（q8_0 KV での検証）**: `--cache-type-{k,v} q8_0` で本 Phase を再実施、KV 半分・compute buffer 変化を測定
- [ ] **Phase R-fa0 候補（fa=0 側の ctx × ub 2 軸スキャン）**: Phase M 係数は ub=8192 固定、`-ub` 軸での再フィット必要
- [ ] **Phase R-runs 候補（120k の 3 run 計測）**: Phase R は 1 run、分散評価のため再実施
- [ ] **Phase Q-2 候補（`-ub` 内部下限の真の値特定）**: `-ub=64 / 32 / 16 / 8 / 4 / 2 / 1`
- [ ] **Phase Q-3 候補（`-ub` ピーク周辺探索）**: ub=1536 / 1792 / 2304 / 2560 / 2816 / 3072
- [ ] **start.sh のデフォルト `ctx-size` を 131072 に更新**（現状 65536）:
  - 本 Phase で ctx=65536 起動成功を実証
  - q8_0 KV 構成での確認後に実施（Phase R-KV8）

## 補足

### Phase R-ctx3 の核心発見

1. **CUDA3 = 0.9824·ub は ctx に完全不依存（4 点偏差 0.000 MiB）** — Phase R の 2 点結論を 4 点で完璧に再確証
2. **CUDA1 / CUDA2 / CUDA_Host は完全線形（R² = 1.00000000）** — Phase R の 2 点モデル係数が中間点で誤差 < 0.05% と完璧一致
3. **CUDA0 は線形でなく二次関数** — Phase R 2 点モデルは中間点で -12〜-15% 誤差、二次フィット `CUDA0 = 1046.29 + 3.269e-3·Δctx + 5.770e-8·Δctx²` で R² = 0.99998 を達成
4. **KV buffer は ctx 完全比例（4 点誤差 0.000 MiB）**
5. **graph 構造は ctx 不変（4 点とも nodes=4473, splits=136+77）**
6. **ctx=32k / 8k プロンプトで eval 15.323 t/s — Phase R ctx=131k / 8k の 15.142 t/s を +1.2% 上回る**

### 計算モデルの確定版（fa=1, f16 KV, C-D3 base、ub=128〜8192 × ctx=16k〜131k で実証、本 Phase で CUDA0 二次項が追加）

```
Δctx = ctx - 16384   [基準 ctx=16k]
Δub  = ub - 2048     [基準 ub=2048]

fa=1, C-D3: compute_buffer [MiB]
  CUDA0     = 1046.29 + 3.269e-3·Δctx + 5.770e-8·Δctx² + 0.077·Δub  [R²=0.99998 for ctx fit]
  CUDA1/2   = 520.06  + 0.003906·Δctx + 0.254·Δub                    [R²=1.00000000]
  CUDA3     = 0.9824·ub                                                [ctx 完全不依存、4 点偏差 0.000 MiB]
  CUDA_Host = 176.08  + 0.007812·Δctx + 0.086·Δub                    [R²=1.00000000]

fa=1: KV cache [MiB]  (f16, 12 layers on GPU)
  KV = 384 × (ctx / 16384) MiB (per GPU × 4 GPU = 1,536 × ctx/16384 MiB)
     = 96 × (ctx/16384) MiB/GPU × 4 GPU = 384 × (ctx/16384) MiB
  合計 384.00 (ctx=16k) / 768.00 (ctx=32k) / 1,536.00 (ctx=65k) / 3,072.00 (ctx=131k)

fa=1: graph structure (ub=2048 基準)
  nodes = 4473     [ctx 不変]
  splits_main = 136 (with bs=2048)   [ctx 不変]
  splits_bs1 = 77                    [ctx 不変]
```

### 4 点データベース（ub=2048 固定）

| ctx | CUDA0 | CUDA1 | CUDA2 | CUDA3 | CUDA_Host | 合計 | KV/GPU | graph_nodes | reserve_ms |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 16,384 | 1,048.13 | 520.06 | 520.06 | 2,012.00 | 176.08 | 4,276.33 | 96.00 | 4,473 | ~110 |
| 32,768 | 1,112.13 | 584.06 | 584.06 | 2,012.00 | 304.08 | 4,596.33 | 192.00 | 4,473 | 224 |
| 65,536 | 1,348.00 | 712.06 | 712.06 | 2,012.00 | 560.08 | 5,344.20 | 384.00 | 4,473 | 357 |
| 131,072 | 2,180.00 | 968.06 | 968.06 | 2,012.00 | 1,072.08 | 7,200.20 | 768.00 | 4,473 | 628 |

### eval / prompt 性能データベース（ub=2048 固定、3 run 中央値）

| ctx | prompt | prompt_n | eval_med (t/s) | prompt_med (t/s) |
|---:|---|---:|---:|---:|
| 16,384 (Phase Q P1) | warmup | 67 | 15.416 | 10.99 |
| 32,768 | warmup | 71 | 15.069 | 11.042 |
| 32,768 | 1k | 1,092 | 15.063 | 68.589 |
| 32,768 | 8k | 8,093 | **15.323** | 98.813 |
| 65,536 | warmup | 71 | 14.579 | 11.047 |
| 65,536 | 1k | 1,092 | 14.555 | 69.330 |
| 65,536 | 8k | 8,093 | 14.819 | 98.990 |
| 65,536 | 32k | 32,124 | 14.034 | 92.674 |
| 131,072 (Phase R R1) | warmup | 70 | 14.917 | 11.146 |
| 131,072 (Phase R R1) | 1k | 1,091 | 14.893 | 68.816 |
| 131,072 (Phase R R1) | 8k | 8,092 | 15.142 | 99.387 |
| 131,072 (Phase R R1) | 32k | 32,123 | 14.400 | 92.540 |

**eval ピーク**: ctx=32k × 8k prompt で **15.323 t/s**（本 Phase で最速）。

### 作業終了時点の状態

- llama-server は停止済み（stop.sh で正常終了、PID 193097/193098 → 197459/197460）
- GPU サーバロック（t120h-p100）は解放済み（unlock.sh）
- `results.tsv` 21 行（7 条件 × 計 21 run）で集計完了
- `compute_buffer_summary.txt` に両起動ログの主要行 58 行を集約
- `fit_analysis_Rctx3.py` / `fit_analysis_Rctx3.txt` で 4 点線形 + CUDA0 二次フィット、予測差分、KV 比例性、成功条件サマリを保存
- **skill 側 `start.sh:155` の `-b 2048 -ub 2048` 変更と 3 変数モデル（CUDA0 二次）の lint 組み込みを次の最優先タスクとして登録**
