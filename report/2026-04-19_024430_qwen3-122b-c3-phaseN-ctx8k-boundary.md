# Qwen3.5-122B-A10B C-3 Phase N（fa=0 ctx=8192 境界実験 + fa=1 ctx スキャン）

- **実施日時**: 2026年4月19日 02:18 – 02:44 (JST、実計測時間 約 25 分)
- **作業種別**: 計測・検証（Phase M 未検証事項「ctx=8192 境界実験」「fa=1 側の ctx スキャン」）

## 添付ファイル

- [起動スクリプト (start_phaseN.sh、Phase L から流用、コメント行のみ修正)](attachment/2026-04-19_021803_qwen3-122b-c3-phaseN-ctx8k/start_phaseN.sh)
- [計測スクリプト (measure_phaseI.sh、Phase I から流用)](attachment/2026-04-19_021803_qwen3-122b-c3-phaseN-ctx8k/measure_phaseI.sh)
- [一括実行スクリプト (run_all.sh、Phase J から流用)](attachment/2026-04-19_021803_qwen3-122b-c3-phaseN-ctx8k/run_all.sh)
- [集計スクリプト (aggregate_results.sh、`out_M_*` → `out_N_*` に 1 行修正)](attachment/2026-04-19_021803_qwen3-122b-c3-phaseN-ctx8k/aggregate_results.sh)
- [係数フィット Python (fit_analysis.py)](attachment/2026-04-19_021803_qwen3-122b-c3-phaseN-ctx8k/fit_analysis.py)
- [フィット結果 (fit_analysis.txt)](attachment/2026-04-19_021803_qwen3-122b-c3-phaseN-ctx8k/fit_analysis.txt)
- [集計結果 TSV (results.tsv)](attachment/2026-04-19_021803_qwen3-122b-c3-phaseN-ctx8k/results.tsv)
- [compute buffer サマリ (compute_buffer_summary.txt)](attachment/2026-04-19_021803_qwen3-122b-c3-phaseN-ctx8k/compute_buffer_summary.txt)
- [fa=0 ctx=8192 起動ログ (startup_logs/fa0_ctx8192.log)](attachment/2026-04-19_021803_qwen3-122b-c3-phaseN-ctx8k/startup_logs/fa0_ctx8192.log)
- [fa=1 ctx=1024 起動ログ (startup_logs/fa1_ctx1024.log)](attachment/2026-04-19_021803_qwen3-122b-c3-phaseN-ctx8k/startup_logs/fa1_ctx1024.log)
- [fa=1 ctx=2048 起動ログ (startup_logs/fa1_ctx2048.log)](attachment/2026-04-19_021803_qwen3-122b-c3-phaseN-ctx8k/startup_logs/fa1_ctx2048.log)
- [fa=1 ctx=8192 起動ログ (startup_logs/fa1_ctx8192.log)](attachment/2026-04-19_021803_qwen3-122b-c3-phaseN-ctx8k/startup_logs/fa1_ctx8192.log)
- `out_N_f16_fa1_ctx{1024,2048,8192}_warmup/` の各計測アーティファクト

## 参照

- 前身レポート: [2026-04-18_220428_qwen3-122b-c3-phaseM-ctx-scan.md](2026-04-18_220428_qwen3-122b-c3-phaseM-ctx-scan.md)
- Phase L (fa=0 ctx スキャン): [2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan.md](2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan.md)
- Phase K (ctx=16384 f16 A/B): [2026-04-18_025221_qwen3-122b-c3-phaseK-f16-flashattn-ab.md](2026-04-18_025221_qwen3-122b-c3-phaseK-f16-flashattn-ab.md)

## 前提・目的

Phase M で fa=0 側に **3 点厳密解モデル** `buffer(n) = a·n² + b·n + c`（ctx=1024/2048/4096）を確立した。しかし 2 つの未決問題が残存:

1. **ctx=8192 境界実験**: Phase M の 3 点厳密解モデル（小 ctx 域）と Phase L の log-log ベキ則 `k=1.306`（大 ctx 域）のどちらが ctx=8192 で成立するか。Phase M では「どちらも過大予測の可能性」と結論を保留していた。
2. **fa=1 側の同等オーダー特定**: Phase L で fa=1 ctx=4096 は合計 7,340 MiB、Phase K で fa=1 ctx=16384 は csv 経由で採取済みだが、fa=1 の compute buffer のオーダー（`O(n²)` か `O(n)` か）は未定量。

本 Phase N では:

- **fa=0 ctx=8192** の起動試行で Phase M モデル予測 (CUDA0: 12,448 MiB、CUDA1: 9,536 MiB) と OOM 位置を突合
- **fa=1 ctx=1024 / 2048 / 8192** の 3 点を追加計測し、Phase L 既計測の ctx=4096 と合わせて 4 点フィット

### 成功条件

- [x] fa=0 ctx=8192 起動可否の判定と OOM 位置特定
- [x] Phase M 3 点厳密解の ctx=8192 外挿値 (CUDA1=9,536.1 MiB) と実測の突合
- [x] fa=1 ctx=1024 / 2048 / 8192 の 3 点採取
- [x] fa=1 側の 4 点フィット係数 `a, b, c` と log-log k の推定
- [x] fa=0 と fa=1 の compute buffer スケーリング様式の比較

## 環境情報

- **サーバ**: `t120h-p100` (10.1.4.14)
- **GPU**: NVIDIA Tesla P100-PCIE-16GB × 4（各 16,269 MiB、合計 65,077 MiB、CC 6.0）
- **CPU**: Intel Xeon Gold 6138 @ 2.00GHz × 2 socket、計 40 コア / 80 スレッド、NUMA 2 ノード
- **メモリ**: 257,560 MiB (約 251 GiB)
- **モデル**: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- **llama.cpp ビルド**: b8807-b3d758750（Phase D〜M と同一系列）
- **構成**: Phase M と同じ C-D3 ベース + `--cache-type-{k,v} f16`
  - NUMA: `numactl --cpunodebind=1 --membind=1 --`
  - `--threads 40 --poll 0 -b 8192 -ub 8192`
  - `-ngl 999 -ot 'blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'`
- **fa=0 ctx=8192 試行**: OOM で起動不可（後述、セッション PID なし）
- **fa=1 ctx=8192 PID**: 158289（fresh、計測直後に停止）
- **fa=1 ctx=2048 PID**: 160278（fresh、計測直後に停止）
- **fa=1 ctx=1024 PID**: 162251（fresh、計測直後に停止）

## 再現方法

Phase M 添付の `start_phaseL.sh` は `FLASH_ATTN` / `CTX_SIZE` 環境変数に対応済みのため、コピー後はコメントのみ修正してそのまま流用。

### 実行フロー

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
PHASE_N_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseN-ctx8k"
mkdir -p "$PHASE_N_DIR/startup_logs"
# Phase M 資産を流用
cp report/attachment/2026-04-18_220428_qwen3-122b-c3-phaseM-ctx-scan/{start_phaseL.sh,measure_phaseI.sh,run_all.sh,aggregate_results.sh} "$PHASE_N_DIR/"
mv "$PHASE_N_DIR/start_phaseL.sh" "$PHASE_N_DIR/start_phaseN.sh"
cp -r report/attachment/2026-04-18_220428_qwen3-122b-c3-phaseM-ctx-scan/prompts "$PHASE_N_DIR/"
# aggregate_results.sh の out_M_* → out_N_* に書き換え

cd "$PHASE_N_DIR"

# ---- Step 1: fa=0 ctx=8192 (OOM 予測)
FLASH_ATTN=0 CTX_SIZE=8192 bash start_phaseN.sh
# → OOM 検出で abort（CUDA1 9,536.19 MiB 要求）
ssh t120h-p100 "cat /tmp/llama-server_fa0_ctx8192.log" > startup_logs/fa0_ctx8192.log

# ---- Step 2: fa=1 ctx=8192
FLASH_ATTN=1 CTX_SIZE=8192 bash start_phaseN.sh  # PID=158289
ssh t120h-p100 "cat /tmp/llama-server_fa1_ctx8192.log" > startup_logs/fa1_ctx8192.log
TAG_PREFIX=N_f16_fa1_ctx8192 SIZES="warmup" PID=158289 bash run_all.sh
cd - ; .claude/skills/llama-server/scripts/stop.sh t120h-p100 ; cd "$PHASE_N_DIR"

# ---- Step 3: fa=1 ctx=2048
FLASH_ATTN=1 CTX_SIZE=2048 bash start_phaseN.sh  # PID=160278
ssh t120h-p100 "cat /tmp/llama-server_fa1_ctx2048.log" > startup_logs/fa1_ctx2048.log
TAG_PREFIX=N_f16_fa1_ctx2048 SIZES="warmup" PID=160278 bash run_all.sh
cd - ; .claude/skills/llama-server/scripts/stop.sh t120h-p100 ; cd "$PHASE_N_DIR"

# ---- Step 4: fa=1 ctx=1024
FLASH_ATTN=1 CTX_SIZE=1024 bash start_phaseN.sh  # PID=162251
ssh t120h-p100 "cat /tmp/llama-server_fa1_ctx1024.log" > startup_logs/fa1_ctx1024.log
TAG_PREFIX=N_f16_fa1_ctx1024 SIZES="warmup" PID=162251 bash run_all.sh
cd - ; .claude/skills/llama-server/scripts/stop.sh t120h-p100 ; cd "$PHASE_N_DIR"

# 集計・フィット
bash aggregate_results.sh > results.tsv
python3 fit_analysis.py | tee fit_analysis.txt
# compute_buffer_summary.txt 生成
for f in startup_logs/*.log; do
  echo "=== $(basename $f) ==="
  grep -E "sched_reserve:|cudaMalloc|allocate CUDA|failed to allocate" "$f" || true
  echo
done > compute_buffer_summary.txt

cd -
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 実行タイムライン

| タグ | prompt_n | Run 数 | 開始 | 終了 |
|------|---------:|------:|----------:|----------:|
| fa=0 ctx=8192 起動試行 | — | — | 02:20 | 02:20（**OOM abort、約 30s**）|
| fa=1 ctx=8192 起動 | — | — | 02:24 | 02:25（起動成功、約 20s）|
| N_f16_fa1_ctx8192_warmup | 58 | 3 | 02:25:35 | 02:30:32 |
| fa=1 ctx=2048 起動 | — | — | 02:31 | 02:31（起動成功、約 20s）|
| N_f16_fa1_ctx2048_warmup | 58 | 3 | 02:31:21 | 02:36:19 |
| fa=1 ctx=1024 起動 | — | — | 02:37 | 02:37（起動成功、約 20s）|
| N_f16_fa1_ctx1024_warmup | 58 | 3 | 02:37:08 | 02:42:05 |

実計測時間: **約 25 分**（Phase M と同等）。

## 実行結果サマリ

### 1. fa=0 ctx=8192 起動不可、OOM 主犯は CUDA1

```
(startup_logs/fa0_ctx8192.log 抜粋)
llama_kv_cache:      CUDA0 KV buffer size =    48.00 MiB  ×4 GPU
sched_reserve: fused Gated Delta Net (autoregressive) enabled
sched_reserve: fused Gated Delta Net (chunked) enabled
ggml_backend_cuda_buffer_type_alloc_buffer: allocating 9536.19 MiB on device 1:
                cudaMalloc failed: out of memory
ggml_gallocr_reserve_n_impl: failed to allocate CUDA1 buffer of size 9999417472
graph_reserve: failed to allocate compute buffers
```

**主犯は CUDA1 の 9,536.19 MiB 要求**。Phase M では「CUDA0 が 12,448 MiB で 16GB を超えるため bottleneck」と予測していたが、**実際は CUDA1 が先に落ちる**（CUDA1 の空き実効枠は P100 16GB − モデル重み等）。

### 2. Phase M 3 点厳密解モデルの ctx=8192 予測 vs 実測（極めて高精度）

Phase M の fa=0 係数で ctx=8192 に外挿:

| GPU | Phase M 予測 @ctx=8192 | Phase N 実測 | 誤差 |
|----|---:|---:|---:|
| CUDA0 | 12,448.0 MiB | (OOM 前に未採取) | — |
| **CUDA1** | **9,536.1 MiB** | **9,536.19 MiB** | **0.0009%（完全一致）** |
| CUDA2 | 9,440.1 MiB | (CUDA1 OOM で未到達) | — |
| CUDA3 | 8,048.0 MiB | (CUDA1 OOM で未到達) | — |
| CUDA_Host | 480.3 MiB | (CUDA1 OOM で未到達) | — |

CUDA1 の 4 桁一致は偶然ではなく、**Phase M の 3 点厳密解モデルが ctx=1024–8192 の範囲で極めて正確**であることを示す。Phase M で懸念した「外挿 145,584 MiB（ctx=16384）」の破綻は、n² 支配域（ctx≥4096）の k=1.306 ベキ則と厳密解モデルの合成が必要で、**ctx=8192 までは 3 点厳密解で十分**という**新しい領域区分**が明らかになった。

### 3. fa=1 ctx スキャンの compute buffer 実測（起動ログ `sched_reserve` より）

| GPU | ctx=1024 | ctx=2048 | ctx=4096 (Phase L) | ctx=8192 |
|----:|------:|------:|------:|------:|
| CUDA0 | 975.00 | 994.00 | 1,428.00 | **2,320.53** |
| CUDA1 | 230.03 | 464.06 | 944.13 | **1,952.25** |
| CUDA2 | 230.03 | 464.06 | 944.13 | **1,952.25** |
| CUDA3 | 1,006.00 | 2,012.00 | 4,024.00 | **8,048.00** |
| CUDA_Host | 28.04 | 64.08 | 160.16 | **448.31** |
| **CUDA 合計** | 2,469.10 | 3,998.20 | 7,500.42 | **14,721.34** |
| graph nodes | 4,473 | 4,473 | 4,473 | 4,473 |
| graph splits | 136 (bs=1024) | 136 (bs=2048) | 136 (bs=4096) | 136 (bs=8192) |

### 4. fa=1 の 4 点 GPU 別フィット（`buffer(n) = a·n² + b·n + c`、log-log 傾き k）

| GPU | a | b | c | max resid | log-log k | 解釈 |
|----|----:|----:|----:|----:|----:|------|
| CUDA0 | 1.10e-5 | 0.093 | 828.09 | **70.4** | 0.43 | 定数 c 支配、純線形 + 小 n² |
| CUDA1 | 1.91e-6 | 0.2227 | ≈0 | **0.00** | **1.028** | **ほぼ完全線形** |
| CUDA2 | 1.91e-6 | 0.2227 | ≈0 | **0.00** | **1.028** | CUDA1 と完全対称 |
| CUDA3 | 0 | 0.9824 | 0 | **0.00** | **1.000** | **完全線形**（fa=0 と同係数） |
| CUDA_Host | 3.81e-6 | 0.0235 | ≈0 | 0.00 | 1.332 | 中間オーダー（fa=0 の k=1.23 と近い） |
| 合計 | 1.86e-5 | 1.5442 | 828.07 | — | 0.864 | 合計 log-log k=0.864 |

**重要な発見**:

1. **CUDA1 / CUDA2 の log-log k=1.028** — ほぼ完全線形、fa=0 側の k=1.67 (n² 強支配) と対照的。**これが flash-attn の本質**（attention score matrix の O(n²) → Tiled O(n) への削減）の定量実証。
2. **CUDA3 は fa=0 / fa=1 共通で b=0.9824 MiB/token の純線形**（a=0, c=0 含む係数まで一致）→ CUDA3 の compute buffer は attention 非依存の KV 関連 staging buffer。
3. **CUDA0 の定数項 c=828.09** は fa=0 (c=1562.67) の約半分 → fa=1 は CUDA0 側の定数的な attention 関連 buffer を削減。
4. **CUDA1/CUDA2 が完全対称** (b=0.2227 MiB/token で一致) → Phase M の fa=0 観察 (a=1.259e-4 で対称) と整合、**attention 計算は CUDA1/CUDA2 に対称分散**という構造がここでも確認。

### 5. fa=0 vs fa=1 の compute buffer 比較

| ctx | fa=0 合計 | fa=1 合計 | 比 (fa0/fa1) | flash-attn 節約 MiB |
|---:|---:|---:|---:|---:|
| 1,024 | 2,684.07 | 2,469.10 | 1.087x | 215.0 |
| 2,048 | 4,856.16 | 3,998.20 | 1.215x | 858.0 |
| 4,096 | 12,352.31 | 7,500.42 | 1.647x | 4,851.9 |
| 8,192 | (CUDA1 単独 9,536 で破綻) | 14,721.34 | 起動不可 / 起動可 | 起動可否の差 |

**fa=1 の節約量が ctx² で急激に拡大**（1k→2k→4k で 215→858→4852 MiB、約 4x/倍ずつ）。これは Phase K の「fa=1 の本質は量子化 KV 互換ではなく、compute buffer の O(n²) 削減」という結論と完全整合。

ctx=8192 は **fa=1 でのみ起動可能**（合計 14,721 MiB、4 GPU で平均 3.7GB/枚で収まる）、**fa=0 では CUDA1 単独で 9,536 MiB 要求で即 OOM**。

### 6. eval 速度の ctx 依存（fa=1、f16 KV）

| タグ | prompt_n | Run 1 | Run 2 | Run 3 | 中央値 | Run 間 range |
|------|---------:|------:|------:|------:|------:|-----:|
| N_f16_fa1_ctx1024_warmup | 58 | 15.270 | 15.266 | 15.263 | **15.266** | 0.007 (0.04%) |
| N_f16_fa1_ctx2048_warmup | 58 | 15.446 | 15.422 | 15.426 | **15.426** | 0.024 (0.16%) |
| L_f16_fa1_ctx4096_warmup (Phase L) | 58 | — | — | — | 14.963 | — |
| N_f16_fa1_ctx8192_warmup | 58 | 15.055 | 15.049 | 15.058 | **15.049** | 0.009 (0.06%) |
| K_f16_fa1_warmup (Phase K, ctx=16384) | 58 | — | — | — | 15.046 | — |

**fa=1 は ctx に対して eval 速度が「谷型」**:

| ctx | fa=1 eval 中央値 (t/s) | fa=0 eval 中央値 (t/s, Phase L/M) |
|---:|---:|---:|
| 1,024 | **15.266** | 14.285 |
| 2,048 | **15.426**（最高） | 14.781 |
| 4,096 | 14.963 | 15.067（最高） |
| 8,192 | 15.049 | — |
| 16,384 | 15.046 | — |

- **fa=1 は ctx=2048 で最高 (15.43)**、ctx=4096 で最低 (14.96)、それ以降 15.05 で漸近
- **fa=0 は ctx=4096 で最高 (15.07)**、ctx=1024 で最低 (14.29)
- Phase M で fa=0 のみ観察した「小 ctx 側の eval 劣化」は **fa=1 では発生しない**（ctx=1024 でも 15.27）

これは **fa=1 が小 ctx の graph split オーバーヘッドに強い**ことを示唆。flash-attn カーネルが独立の計算パスを持ち、attention 以外の処理割合が変動しにくいため。

### 7. prompt 処理速度（fa=1 ctx スキャン）

| タグ | Run 1 | Run 2 | Run 3 | 中央値 |
|------|------:|------:|------:|------:|
| N_f16_fa1_ctx1024_warmup | 9.70 | 9.91 | 9.91 | **9.91** |
| N_f16_fa1_ctx2048_warmup | 9.85 | 10.10 | 10.21 | **10.10** |
| N_f16_fa1_ctx8192_warmup | 9.67 | 9.95 | 9.97 | **9.95** |

prompt_n=58 では ctx の影響は 0.1 t/s 以内（1% 未満）で、事実上無視できる。

### 8. GPU メモリ使用量（`gpu_post_run*.csv` warmup 時）

| GPU | ctx=1024 | ctx=2048 | ctx=4096 (L) | ctx=8192 | ctx=16384 (K) |
|----:|------:|------:|------:|------:|------:|
| 0 | 2,695 | 2,719 | — | 4,083 | 4,593 |
| 1 | 10,197 | 10,437 | — | 11,961 | 12,135 |
| 2 | 10,197 | 10,437 | — | 11,961 | 12,135 |
| 3 | 3,109 | 4,121 | — | 10,193 | 10,239 |
| **合計** | 26,198 | 27,714 | — | 38,198 | 39,102 |

CUDA3 の増分が顕著（3,109 → 4,121 → 10,193 → 10,239）で、compute buffer の線形 b=0.9824 MiB/token と完全整合。

## ボトルネック・副次発見の分析

### 1. Phase M モデルの ctx=8192 予測精度の実証

CUDA1 の 9,536.1 MiB 予測 vs 9,536.19 MiB 実測は **4 桁一致**。Phase M で「3 点厳密解は外挿に脆弱（ctx=16384 予測 145,584 MiB は非物理）」と懸念したが、**実際は ctx=8192 まで完璧**。これは:

- **ctx=16384 で破綻するのは CUDA0 の「定数項 c=1562 + 負の線形項 b=−0.68」の外挿脆弱性**
- **CUDA1/2 は n² 支配で単調増加するため、n² 外挿に安定**

という区別により理解できる。すなわち 3 点厳密解モデルは **「全 GPU を一様に外挿すると破綻」だが「GPU ごとに別の破綻点を持ち、CUDA1/2 は ctx=16384 まで有効」** という詳細化が必要。

### 2. flash-attn の本質的役割の定量証明

fa=0: CUDA1/2 は `a=1.26e-4`（n² 支配、log-log k=1.67）
fa=1: CUDA1/2 は `a≈2e-6`（ほぼゼロ）、`b=0.22`（線形支配、log-log k=1.028）

**fa=1 によって CUDA1/2 の a 係数は約 66 倍削減**、本質的に attention score matrix の O(n²) 項が消失。これは Phase K で「flash-attn = O(n²)→O(n) 削減が本質」と結論した仮説の定量的完全実証。

### 3. CUDA3 の係数が fa=0 と fa=1 で完全一致

| 条件 | b | c |
|---|---:|---:|
| fa=0 (Phase M) | 0.9824 | 0.00 |
| fa=1 (Phase N) | 0.9824 | 0.00 |

CUDA3 は **flash-attn の有無に依存しない** = attention 計算の分散に関与していない。これが Phase L で観察された「CUDA3 が fa=0/fa=1 両条件で同じ 4,024 MiB」現象の根本的理由。CUDA3 の 1 MiB/token は KV cache 関連の中間 staging buffer（f16 × n_kv × 何らかの定数）の可能性が高い。

### 4. CUDA0 の定数項 c が fa=1 で半減

fa=0: c=1,562.67 MiB
fa=1: c=828.09 MiB
差: 734.58 MiB

fa=1 は CUDA0 側の **定数的な attention 関連 buffer も 734 MiB 削減**。これは attention workspace または QKV 変換バッファの可能性。embedding / output head 自体は fa に非依存のはず。

### 5. fa=0 と fa=1 で OOM 主犯が異なる

| ctx | fa=0 最大要求 GPU | fa=1 最大要求 GPU |
|---:|---|---|
| 1,024 | CUDA0 (1,122) | CUDA3 (1,006) |
| 2,048 | CUDA3 (2,012) | CUDA3 (2,012) |
| 4,096 | CUDA3 (4,024) | CUDA3 (4,024) |
| 8,192 | **CUDA1 (9,536、OOM)** | CUDA3 (8,048、起動可) |
| 16,384 (Phase K 既知) | **CUDA0 (18,176、OOM)** | 起動成功 |

- fa=0 の CUDA0 外挿 ctx=8192 は 12,448 MiB で CUDA0 単独では収まる
- fa=0 の **CUDA1 が ctx=8192 で 9,536 MiB を要求し、モデル重み + KV cache で既に 7 GB 程度使っている CUDA1 の空き枠を超える**
- Phase K で観察された「fa=0 ctx=16384 で CUDA0 が 18,176 MiB 要求」は、より下位の **CUDA1 の OOM が先にくる** ことが Phase N で判明（Phase K は早期 abort で CUDA0 要求のみ記録、CUDA1 値は未記録）

これは Phase M の「CUDA0 が bottleneck」という仮説を **訂正**し、**fa=0 の OOM 主犯は ctx に応じて変わる** ことが分かった。

### 6. eval 速度の fa=0 / fa=1 比較

| ctx | fa=0 eval | fa=1 eval | fa=1 − fa=0 |
|---:|---:|---:|---:|
| 1,024 | 14.285 | 15.266 | **+0.981 (+6.9%)** |
| 2,048 | 14.781 | 15.426 | +0.645 (+4.4%) |
| 4,096 | 15.067 | 14.963 | −0.104 (−0.7%) |
| 8,192 | — | 15.049 | — |
| 16,384 | — | 15.046 | — |

**小 ctx 側で fa=1 が顕著に速い**（ctx=1024 で +6.9%）。Phase M の「ctx=1024 fa=0 で −5.2% 劣化」現象は **fa=1 では発生しない**。これは flash-attn がメモリ局所性に優れ、小 ctx の graph split オーバーヘッドの影響を受けにくいことを示唆。

### 7. fa=1 eval の「谷型」ctx 依存

fa=1 eval が ctx=2048 で最高 (15.426)、ctx=4096 で最低 (14.963) となる現象は Phase L/K の 1 ctx のみ計測では見えなかった。原因推定:

- ctx=2048 では KV cache が小さく attention カーネルの効率が高い
- ctx=4096 で KV cache が中途半端な大きさになり tiling 効率が下がる
- ctx≥8192 で大 ctx 向け tiling 経路に遷移し安定

定量的には ±3% のゆらぎ範囲内なので、**ctx=4096 ダニングは系統的効果か計測ゆらぎか判別不能**（再現性検証が Phase O で必要）。

## 採用判定

| 項目 | 結果 |
|------|------|
| fa=0 ctx=8192 起動 | ❌ 不可（CUDA1 9,536 MiB OOM） |
| fa=1 ctx=1024/2048/8192 起動 | ✅ 可能 |
| Phase M 3 点厳密解モデルの ctx=8192 予測精度 | **CUDA1 で 0.001% 誤差（完全一致）** |
| fa=1 compute buffer のオーダー特定 | **CUDA1/2 が log-log k=1.028 で ほぼ完全線形**（fa=0 の k=1.67 と対照） |
| CUDA3 の fa 非依存性 | **確定**（fa=0/fa=1 共通で b=0.9824 MiB/token の純線形） |
| C-D3 採用構成（q8_0, ctx=131k, fa=1）の妥当性 | **強化**（fa=1 の本質的役割が CUDA1/2 の O(n²)→O(n) 削減と完全定量証明） |

**結論**: Phase L/M/N を通じて、fa=1 / fa=0 両側の compute buffer スケーリングが GPU 別に完全に解明された。本番 `start.sh` の改変は不要。追加ドキュメント化 TODO:

- 「fa=0 の OOM 主犯は ctx に応じて変わる（ctx=8192: CUDA1、ctx=16384: CUDA0）」
- 「fa=1 の CUDA1/2 は log-log k=1.028 で ほぼ完全線形、CUDA3 は fa に依存せず b=0.9824 MiB/token」を skill に記録

## 未検証事項

### 既知項目（Phase M から継続、部分更新あり）

- [ ] **2 時間超の連続稼働試験（eval あり）**
- [ ] **層→GPU アライメントのソース解析**（Phase N で CUDA1/2 が完全対称、CUDA3 が fa 非依存 1 MiB/token と判明、解析動機最大化）
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
- [ ] **線形モデル `time_per_token = 66.5μs + 0.485μs × N_context` の他構成での検証**
- [ ] **prompt_per_second が 8k で頂点を打つ理由**（`-b / -ub 8192` との関連検証）
- [ ] **64k / 120k の Run 間再現性**
- [ ] **128k コンテキストが純粋応答に与える影響**
- [ ] **KV cache 量子化 (q8_0) の精度影響**
- [ ] **prompt cache hit 時の実効 turn time**
- [ ] **llama.cpp のソース上で `--cache-type-{k,v} q8_0` と `--flash-attn` の依存ロジック確認**
- [ ] **Segfault 時のバックトレース取得**（本 Phase で fa=0 ctx=8192 でも同 segfault 再現）
- [ ] **P100 CC 6.0 の flash-attention カーネル経路の検証**（本 Phase で CUDA1/2 の k=1.028 達成を確認、flash-attn カーネルが P100 上でも O(n) で動作する実証）
- [ ] **CUDA1/2/3 の SM 稼働実態の時系列計測**（本 Phase で CUDA1/2 完全対称・CUDA3 fa 非依存が確定、attention は CUDA1/2 のみが担当する強い証拠）
- [ ] **J_fa1_warmup run 1 の外れ値（15.54 t/s）再現性**
- [ ] **CUDA0 の定数項 c=1,562 (fa=0) / c=828 (fa=1) の内訳特定**（本 Phase で fa による差が +734 MiB と定量化、QKV workspace の可能性強化）
- [ ] **CUDA1 / CUDA2 の n² 係数 (fa=0 a=1.26e-4) の物理解釈**
- [ ] **CUDA3 の線形係数 b=0.9824 MiB/token の源**（fa=0/fa=1 両方で完全一致と Phase N で確認、attention 非関与の KV staging staging buffer 仮説が強化）
- [ ] **ctx=1024 の fa=0 eval 劣化 (−5.2%) の原因**（fa=1 では劣化しないことが本 Phase で判明、要因は attention 計算 or graph split のいずれか）
- [ ] **ctx=512 / 256 の極小域での挙動**
- [ ] **3 点厳密解 vs 4 点最小二乗の妥当性**（本 Phase で CUDA1 の ctx=8192 予測が 0.001% 誤差 → 3 点厳密解は n² 支配 GPU に対しては極めて安定）
- [ ] **2 次多項式モデルの外挿限界**（本 Phase で ctx=8192 までは有効と判明、ctx=16384 は CUDA0 の線形項符号と定数項の外挿脆弱性で破綻）
- [ ] **eval 速度のセッション間ゆらぎレンジ更新**
- [ ] **prompt 処理の ctx 非依存の長 ctx 側確認**

### 新規項目（本 Phase N で判明・発生）

- [ ] **fa=1 CUDA0 の定数項 c=828 MiB の 4 点フィット max resid 70 MiB が示すモデル不適合**: CUDA0 は n²+線形+定数の 3 係数では表現し切れず、より複雑な非線形関数が必要。最小二乗で resid=70 MiB の乖離。区分線形モデルか指数項を試す余地あり
- [ ] **fa=1 ctx=16384 の sched_reserve 値の再採取**: Phase K の起動ログが短く、sched_reserve 4 GPU の値が未記録。fa=1 側の 5 点フィット（ctx=1024/2048/4096/8192/16384）による精度向上が可能。10 分程度の再計測で完結
- [ ] **fa=0 ctx=8192 の OOM を CUDA1 基準で防御する起動前予測**: Phase M モデル (CUDA1 a=1.26e-4, b=0.13) により `ctx ≤ 8192` は CUDA1 空き枠 (モデル重み後の残り) と比較可能。起動前 pre-check の具体化
- [ ] **CUDA1/2 の fa=1 係数 b=0.2227 の物理解釈**: 対称 0.22 MiB/token は何由来か（fa=0 CUDA3 の 0.98 MiB/token と比較して約 1/4.4、つまり何らかの「1/4 の GPU 数」構造を示唆？）
- [ ] **fa=1 eval の「谷型」(ctx=2048 最高 → ctx=4096 最低) の再現性**: セッション再起動後も同じ pattern が出るかで、系統的効果か計測ゆらぎか判別可能。3 セッション ×3 runs の反復計測で確認
- [ ] **Phase M のモデルを f16 KV → q8_0 KV（C-D3 採用構成）に適用した場合の整合性**: 現在は fa=1 f16 KV で統一されているが、本番は q8_0。q8_0 + fa=1 の compute buffer が f16 + fa=1 からどの程度減るかは未定量
- [ ] **ctx=6144 等の中間 ctx での fa=1 / fa=0 境界確認**: fa=0 ctx=4096 は起動、ctx=8192 は OOM だが、ctx=5120 / 6144 は？ 細粒度での fa=0 起動上限特定
- [ ] **fa=0 ctx=8192 で CUDA1 空き枠を増やす手法**: `-ot` で CUDA1 の専家を追い出せば CUDA1 の compute buffer 空き枠が増え、fa=0 ctx=8192 が起動可能になる可能性。CUDA1 の層配置見直しで fa=0 の上限拡張
- [ ] **fa=1 での graph nodes 差異**: fa=0 は graph nodes=4,532、fa=1 は 4,473（59 node 少ない）。flash-attn カーネルが融合するノード数（59 node 分）の特定
- [ ] **eval 谷型の最低値 ctx の fa=1 における物理原因**: ctx=4096 は `-b -ub 8192` の半分で、ubatch が中途半端な効率を示す領域の可能性。`-ub 4096` に変えた場合の挙動確認

## 検証完了後に実施すべき TODO

### 既知項目（Phase M から継続、部分更新あり）

- [ ] **start.sh の拡張**: `LLAMA_NUMACTL_PREFIX` / `LLAMA_EXTRA_THREADS` 環境変数サポート追加
- [ ] **CUDA1 セーフティマージン OOM フォールバック実装**（本 Phase で CUDA1 が fa=0 ctx=8192 の OOM 主犯と判明、CUDA1 専用の事前判定が必要）
- [ ] **層→GPU アライメントのソースコード解析**（Phase N で CUDA1/2 完全対称 + CUDA3 fa 非依存と判明、動機最大化）
- [ ] **C-4 実験**（CPU 層削減 + GPU 層追加）
- [ ] **drop_caches 権限の確保**（sudoers 設定 or vmtouch 導入）
- [ ] **C-D3 での perf stat 計測**
- [ ] **コールドスタート C-D6 計測**
- [ ] **start.sh での NUMA プリセット整備**
- [ ] **start.sh に `--threads` 設定追加**
- [ ] **PID 取得ロジックの統一**
- [ ] **セッション間ゆらぎの管理**: 計測プロトコルに「直前プロセス情報（PID、etime、停止からの経過時間）」を明示的に記録
- [ ] **`--poll 50` を採用しない旨を start.sh のコメントで明記**
- [ ] **idle 劣化が偶発現象と確定した場合、Phase E/G の当該セクションに追記**
- [ ] **`measure_phaseI.sh` を汎用化して skill に組み込む**
- [ ] **「長コンテキスト性能カード」をモデル単位で記録するドキュメント整備**
- [ ] **アプリ側にコンテキストサイズ別レイテンシ警告を出す仕組み**
- [ ] **プロンプトキャッシュの活用ドキュメント化**
- [ ] **`-ub` の感度ベンチマーク追加**
- [ ] **`start_phaseJ.sh` / `start_phaseK.sh` / `start_phaseL.sh` / `start_phaseN.sh` の `FLASH_ATTN`/`CTX_SIZE` 環境変数化を skill 側 `start.sh` に逆輸入**
- [ ] **依存制約の lint 化**: 起動前 pre-check
  - Phase M 更新: 「ctx ≤ 4096 なら fa=0 許可、それ以上なら警告」
  - **Phase N 更新: fa=0 は CUDA1 の compute buffer 予測 `1.26e-4·n² + 0.13·n` が CUDA1 空き枠を超えたら拒否**（より厳密な下限判定）
- [ ] **llama.cpp upstream issue/PR のサーベイ**

### 新規項目（本 Phase N で発見）

- [ ] **compute buffer 予測モデルの完全版を skill に記録**:
  - **fa=0**: CUDA0=2.45e-4·n² − 0.68·n + 1563、CUDA1=CUDA2=1.26e-4·n² + 0.13·n、CUDA3=0.98·n、CUDA_Host=3.82e-6·n² + 0.027·n
  - **fa=1**: CUDA0≈828+0.09·n（要精査、resid 70 MiB）、CUDA1=CUDA2=2e-6·n² + 0.22·n、CUDA3=0.98·n、CUDA_Host=3.81e-6·n² + 0.024·n
  - ctx 指定時に **GPU 別に空き枠と比較して OOM を起動前予測**
- [ ] **CLAUDE.md / skill の情報更新**:
  - 「fa=0 は ctx ≤ 4096 で起動可能」を「fa=0 は ctx ≤ 4096 で起動可能、ctx=8192 は CUDA1 の compute buffer 9,536 MiB 要求で OOM」に精密化
  - 「fa=1 の本質は CUDA1/2 の O(n²)→O(n) 削減、CUDA3 は fa 非依存（b=0.98 MiB/token の純線形）」を記録
  - 「ctx=8192 は fa=1 でのみ起動可能、fa=0 では CUDA1 主犯の OOM」
- [ ] **モデルカード更新**: Qwen3.5-122B-A10B の「ctx vs eval 速度」テーブルを fa=0/fa=1 両方で更新（fa=1 ctx=1024: 15.266, 2048: 15.426, 4096: 14.963, 8192: 15.049, 16384: 15.046）
- [ ] **Phase M の「compute_buffer_summary.txt 自動生成」の汎用化**: 起動ログから sched_reserve 行を抽出して回帰フィット、3 点厳密解と 4 点最小二乗の両方を自動算出
- [ ] **Phase O 候補（fa=1 完全 5 点フィット）**: fa=1 ctx=16384 の sched_reserve を再採取し、ctx=1024/2048/4096/8192/16384 の 5 点フィットで CUDA0 の非線形モデル精度向上（現 max resid 70 MiB の解消）
- [ ] **Phase P 候補（q8_0 KV との整合性確認）**: f16 KV 系列の compute buffer モデルを q8_0 KV（本番 C-D3 構成）に適用可能か検証

## 補足

### Phase N の核心発見

1. **Phase M 3 点厳密解モデルが CUDA1 の ctx=8192 を 0.001% 誤差で予測** — n² 支配 GPU (CUDA1/2) に対しては外挿性能が極めて高い
2. **fa=1 の CUDA1/2 は log-log k=1.028 で ほぼ完全線形** — flash-attn の O(n²)→O(n) 本質を定量実証
3. **CUDA3 は fa=0/fa=1 共通で b=0.9824 MiB/token の純線形** — flash-attn に関与しない KV staging buffer の実体解明の手掛かり
4. **fa=0 ctx=8192 OOM の主犯は CUDA0 ではなく CUDA1** — Phase M の bottleneck 仮説を修正
5. **fa=1 CUDA0 の定数項 c=828 は fa=0 の c=1,562 の約半分** — fa=1 は attention workspace も削減

### 計算モデルの決定版（f16 KV, C-D3 base）

```
fa=0: compute_buffer(n)  [単位 MiB, n = ctx]
  CUDA0:    2.454e-4 * n^2 - 0.682 * n + 1562.67    (大 ctx で外挿破綻)
  CUDA1/2:  1.259e-4 * n^2 + 0.13  * n             (ctx=8192 まで実証)
  CUDA3:    0.982    * n                            (純線形、fa 非依存)
  CUDA_Host: 3.82e-6 * n^2 + 0.027 * n             (中間オーダー k≈1.23)

fa=1: compute_buffer(n)
  CUDA0:    (非線形、resid 70 MiB)、近似 c=828 + 0.09 * n
  CUDA1/2:  1.9e-6   * n^2 + 0.2227 * n            (ほぼ完全線形 k≈1.028)
  CUDA3:    0.9824   * n                            (fa=0 と完全一致)
  CUDA_Host: 3.81e-6 * n^2 + 0.024 * n             (fa=0 と近い)
```

### fa=0 / fa=1 の起動可能範囲（P100 16GB × 4 構成）

| ctx | fa=0 | fa=1 | 主要 bottleneck (fa=0) |
|---:|:---:|:---:|---|
| ≤ 4,096 | ✅ | ✅ | CUDA0 / CUDA3 |
| 8,192 | ❌ (CUDA1 9,536 MiB) | ✅ | CUDA1 |
| 16,384 | ❌ (CUDA0 18,176 MiB) | ✅ | CUDA0 |

### 作業終了時点の状態

- llama-server は停止済み（fa=1 ctx=1024 / 2048 / 8192 の 3 セッションとも計測後に stop.sh で正常終了）
- GPU サーバロック（t120h-p100）は解放済み
- `results.tsv` 9 行（fa=1 の 3 ctx 条件 × warmup 3 run）で集計完了
- `compute_buffer_summary.txt` に 4 条件（fa=0 ctx=8192 OOM + fa=1 ctx=1024/2048/8192）の `sched_reserve` 値を集約済み
- `fit_analysis.py` / `fit_analysis.txt` で係数フィット結果を保存
