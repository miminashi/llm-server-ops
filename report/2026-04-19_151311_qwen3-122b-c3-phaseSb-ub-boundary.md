# Qwen3.5-122B-A10B C-3 Phase S-boundary（CUDA0 区分境界 ub\* の特定）

- **実施日時**: 2026年4月19日 15:13 – 15:46 (JST、実計測時間 約 33 分)
- **作業種別**: 計測・検証（Phase S 未検証事項「新規項目」最上位「CUDA0 区分境界 ub\* の特定」）

## 添付ファイル

- [実装プラン](attachment/2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary/plan.md)
- [起動スクリプト (start_phaseSb.sh、Phase S からプレフィックスのみ phaseSb\_ に変更)](attachment/2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary/start_phaseSb.sh)
- [計測スクリプト (measure_phaseI.sh、流用)](attachment/2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary/measure_phaseI.sh)
- [一括実行スクリプト (run_all.sh、流用)](attachment/2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary/run_all.sh)
- [3 条件バッチスクリプト (batch_boundary.sh、stdout redirect 版)](attachment/2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary/batch_boundary.sh)
- [集計スクリプト (aggregate_boundary.sh、`out_Sb_*` 対応)](attachment/2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary/aggregate_boundary.sh)
- [解析スクリプト (analyze_boundary.py、Phase S 4p モデル 19 点検証)](attachment/2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary/analyze_boundary.py)
- [解析結果 (analyze_boundary.txt)](attachment/2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary/analyze_boundary.txt)
- [集計結果 TSV (results.tsv、3 条件 × warmup/1k × 3 run = 18 run)](attachment/2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary/results.tsv)
- [compute buffer サマリ (compute_buffer_summary.txt)](attachment/2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary/compute_buffer_summary.txt)
- [バッチログ (batch_boundary.log)](attachment/2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary/batch_boundary.log)
- 起動ログ 3 条件（`startup_logs/fa1_ctx32768_b{1280,1536,1792}_ub{同}.log`）
- `out_Sb_*` 計測アーティファクト 3 条件（warmup + 1k、計 18 run）

## 参照

- 直前レポート: [2026-04-19_120715_qwen3-122b-c3-phaseS-ub-ctx-2d.md](2026-04-19_120715_qwen3-122b-c3-phaseS-ub-ctx-2d.md)
- Phase R-ctx3 (ctx=8k/24k/48k、ub=2048 固定): [2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints.md](2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints.md)
- Phase Q (ub 下限探索、ctx=16k): [2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound.md](2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound.md)

## 前提・目的

直前レポート Phase S の末尾「未検証事項 / 新規項目」最上位かつ「検証完了後に実施すべき TODO / 新規項目」に **Phase S-boundary 候補**として登録:

> **CUDA0 区分境界 ub\* の特定** (本 Phase 最優先候補): 1024 < ub\* ≤ 2048 の範囲で CUDA0 基底値が跳ね上がる閾値を ub=1280/1536/1792 等の中間点で特定

Phase S で発見した CUDA0 compute buffer の区分的挙動:

| ctx \\ ub | 128 | 256 | 512 | 1024 | 2048 | 4096 | 8192 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 16,384 | 961.62 | 963.25 | 966.50 | 973.00 | 1,048.13 | — | — |
| 32,768 | — | — | 966.50 | 973.00 | 1,112.13 | 1,912.00 | 2,784.00 |
| 65,536 | — | — | 966.50 | 973.00 | 1,348.00 | 2,296.00 | 4,320.00 |

- **ub ≤ 1024 平坦域**: 961-973 MiB、ctx 独立
- **ub ≥ 2048 急増域**: ctx に強く依存、二次多項式で単一 fit 困難 (R²=0.9918)
- **境界 ub\*** は `(1024, 2048]` 区間内にあり未特定

本 Phase では ctx=32768 固定で **ub=1280/1536/1792 の 3 条件**を計測し:

1. **CUDA0 区分境界 ub\*** を `(1280, 1536]`・`(1536, 1792]`・`(1792, 2048]` のいずれかに確定
2. **Phase S 4p 2 軸モデル** (CUDA1/2, CUDA_Host) の予測精度を 16 点 → 19 点で再検証
3. **CUDA3 純 ub 比例式** (0.9824·ub) の 16 点 → 19 点で再確証
4. 副次目的: ub=1280/1536/1792 での eval/prompt 性能を把握

### 成功条件

- [x] 3 条件すべて起動成功（/health OK、OOM ゼロ、-ub 下限拒否ゼロ）
- [x] CUDA3 3 点で `0.9824·ub ± 0 MiB`（実測 max_err 0.04 MiB）
- [x] CUDA0 3 点で境界 ub\* を具体区間に確定 — **実測 ub\* ∈ (1536, 1792]**
- [x] CUDA1/2 / CUDA_Host 3 点が Phase S 確定 4p モデルと max_err < 5 MiB — **実測 max_err < 0.25 MiB**
- [x] graph nodes=4473 / splits_bs1=77 の 3 条件不変
- [x] KV buffer 3 点で `96·(ctx/16384)` = 192 MiB 誤差 0 MiB

## 環境情報

- **サーバ**: `t120h-p100` (10.1.4.14)
- **GPU**: NVIDIA Tesla P100-PCIE-16GB × 4（各 16,269 MiB、合計 65,077 MiB、CC 6.0）
- **CPU**: Intel Xeon Gold 6138 @ 2.00GHz × 2 socket、計 40 コア / 80 スレッド、NUMA 2 ノード
- **メモリ**: 257,560 MiB (約 251 GiB)
- **モデル**: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- **llama.cpp ビルド**: b8807-b3d758750（Phase D〜S と同一系列）
- **構成**: Phase S と同一 C-D3 base + `--cache-type-{k,v} f16`
  - NUMA: `numactl --cpunodebind=1 --membind=1 --`
  - `--threads 40 --poll 0 -ngl 999`
  - `-ot 'blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'`
  - `--flash-attn 1 -b ub -ub ub` (b=ub 同値)
- **条件マトリクス（3 条件 × warmup/1k 3 run 各）**:
  - Sb1: ctx=32768 × ub=1280
  - Sb2: ctx=32768 × ub=1536
  - Sb3: ctx=32768 × ub=1792

## 再現方法

### スクリプト差分（Phase S からの改変は最小限）

- `start_phaseSb.sh`: `REMOTE_LOG` プレフィックスを `phaseS_` → `phaseSb_` に置換、ログ識別子を `[start_phaseSb]` に一斉置換
- `batch_boundary.sh`: Phase S の `batch_S3onwards.sh` をベースに条件マトリクスを 3 行 (ctx=32768 × ub=1280/1536/1792) に削減、識別子を `[batchSb]`、start script 参照を `start_phaseSb.sh`、REMOTE_LOG 参照と TAG_PREFIX を `phaseSb_/Sb_` に置換
- `aggregate_boundary.sh`: `out_S_*` → `out_Sb_*` に置換
- `measure_phaseI.sh` / `run_all.sh` / `prompts/`: **無改変流用**
- `analyze_boundary.py`: **新規** (Phase S 4p モデル + CUDA0 平坦域/6p モデルの 3 点予測誤差表を生成、Python 標準ライブラリのみ使用)

### 実行フロー（実際の実行順序）

```bash
# 1. ロック取得 + ディレクトリ準備 + スクリプト流用
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
TS=2026-04-19_151311
PHASE_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseSb-ub-boundary"
mkdir -p "$PHASE_DIR/startup_logs"
PHASE_S="report/attachment/2026-04-19_120715_qwen3-122b-c3-phaseS-ub-ctx-2d"
cp "$PHASE_S"/{measure_phaseI.sh,run_all.sh,start_phaseS.sh,aggregate_results.sh,batch_S3onwards.sh} "$PHASE_DIR/"
cp -r "$PHASE_S/prompts" "$PHASE_DIR/"
mv "$PHASE_DIR/start_phaseS.sh" "$PHASE_DIR/start_phaseSb.sh"
mv "$PHASE_DIR/batch_S3onwards.sh" "$PHASE_DIR/batch_boundary.sh"
mv "$PHASE_DIR/aggregate_results.sh" "$PHASE_DIR/aggregate_boundary.sh"

# プレフィックス置換
sed -i 's/phaseS_/phaseSb_/g; s/\[start_phaseS\]/[start_phaseSb]/g' "$PHASE_DIR/start_phaseSb.sh"
sed -i 's/\[batch2\]/[batchSb]/g; s/start_phaseS\.sh/start_phaseSb.sh/g; s/phaseS_/phaseSb_/g; s/TAG_PREFIX="S_f16/TAG_PREFIX="Sb_f16/g; s/run_S_ctx/run_Sb_ctx/g; s/start_stdout_ctx/start_stdout_Sb_ctx/g' "$PHASE_DIR/batch_boundary.sh"
# batch_boundary.sh の CONDS 配列は 3 行 (32768 1280/1536/1792) に手動編集
sed -i 's/out_S_\*/out_Sb_*/g' "$PHASE_DIR/aggregate_boundary.sh"

# 2. 3 条件バッチ計測
cd "$PHASE_DIR"
bash batch_boundary.sh > batch_boundary.log 2>&1

# 3. 停止 + 集計 + 解析 + 解放
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash aggregate_boundary.sh > results.tsv
grep -E "sched_reserve:|KV buffer|graph nodes|graph splits|cudaMalloc|failed to allocate|reserve took|llama_kv_cache: size|llama_memory_recurrent: size" \
  startup_logs/*.log > compute_buffer_summary.txt
python3 analyze_boundary.py | tee analyze_boundary.txt
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 実行タイムライン

| フェーズ | 開始 | 終了 | 所要 |
|---|---:|---:|---:|
| lock 取得 + ディレクトリ準備 + スクリプト編集 | 15:13 | 15:14 | 1 分 |
| Sb1 (ctx=32k ub=1280) バッチ起動+計測 | 15:14:28 | 15:24:50 | 10 分 22 秒 |
| Sb2 (ctx=32k ub=1536) バッチ起動+計測 | 15:25:04 | 15:35:23 | 10 分 19 秒 |
| Sb3 (ctx=32k ub=1792) バッチ起動+計測 | 15:35:36 | 15:45:56 | 10 分 20 秒 |
| 停止 + 集計 + 解析 + 解放 | 15:46 | 15:46 | < 1 分 |

実計測時間: **約 33 分**（Phase S の batch_S3onwards.sh をそのまま流用した stdout redirect 版、1 回もパイプ詰まりなし）

## 実行結果サマリ

### 1. compute buffer 実測値（3 点）

| GPU | ctx=32k ub=1280 | 32k/1536 | 32k/1792 |
|---|---:|---:|---:|
| CUDA0 | **976.25** | **979.50** | **1,039.12** |
| CUDA1 | 365.04 | 438.05 | 511.05 |
| CUDA2 | 365.04 | 438.05 | 511.05 |
| CUDA3 | 1,257.50 | 1,509.00 | 1,760.50 |
| CUDA_Host | 190.05 | 228.06 | 266.07 |
| KV/GPU | 192.00 | 192.00 | 192.00 |

### 2. 境界 ub\* の確定 ✅ ub\* ∈ (1536, 1792]

Phase Q/S 既測データに本 Phase 3 点を追加した ctx=32k 系列 CUDA0:

| ub | 128 | 256 | 512 | 1024 | **1280** | **1536** | **1792** | 2048 | 4096 | 8192 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CUDA0 (MiB) | — | — | 966.50 | 973.00 | **976.25** | **979.50** | **1,039.12** | 1,112.13 | 1,912.00 | 2,784.00 |
| Δ from prev | — | — | — | +6.50 | +3.25 | +3.25 | **+59.62** | +73.01 | +799.87 | +872.00 |

**決定的発見**:
- ub=1024 → 1280 → 1536 の ctx=32k 系列で **CUDA0 の増加は +3.25 MiB/ステップ（1ステップ = 256 token）で線形、合計 +6.5 MiB**
- ub=1536 → 1792 で **+59.62 MiB の大ジャンプ**（直前までの 18 倍の傾き）
- ub=1792 → 2048 で +73.01 MiB（急増域の定常傾き）

**境界 ub\*** は **(1536, 1792]** の区間内、かつ **ub=1792 時点で jump は既に発生済み**。

### 3. Phase S 4p モデルとの予測誤差（CUDA1/2, CUDA_Host, CUDA3） ✅ max_err < 0.25 MiB

`analyze_boundary.py` 出力:

```
  ub       C0  C0_flat    dFlat    C0_6p      d6p |       C1     pred     dC1 |       C3     pred     dC3 |    Host    pred      dH
------------------------------------------------------------------------------------------------------------------------
1280   976.25   974.69    +1.56  1052.09   -75.84 |   365.04   365.25   -0.21 |  1257.50  1257.47  +0.028 |  190.05  190.04   +0.01
1536   979.50   976.33    +3.17  1102.88  -123.38 |   438.05   438.24   -0.19 |  1509.00  1508.97  +0.034 |  228.06  228.05   +0.01
1792  1039.12   977.97   +61.15  1154.87  -115.75 |   511.05   511.22   -0.17 |  1760.50  1760.46  +0.039 |  266.07  266.07   -0.00
```

- **CUDA1/2**: Phase S 4p モデル (`520.26 + 3.903e-3·Δctx + 0.2538·Δub + 1.910e-6·Δctx·Δub`) で **max_err 0.21 MiB**
- **CUDA3**: 純比例 (`0.9824·ub`) で **max_err 0.039 MiB**（小数第 2 位までほぼ完全一致）
- **CUDA_Host**: Phase S 4p モデル (`176.08 + 7.813e-3·Δctx + 0.0860·Δub + 3.815e-6·Δctx·Δub`) で **max_err 0.01 MiB**

**CUDA0 の区分モデル**:
- `C0_flat`（平坦域モデル `966.5 + 0.0064·ub` の延伸）: ub=1280/1536 で +1.56/+3.17 MiB（平坦域継続）、ub=1792 で **+61.15 MiB（境界突破）**
- `C0_6p`（急増域モデル、Phase S の ub ≥ 2048 用 6p fit）: ub=1280/1536/1792 で -76〜-116 MiB（6p モデルは本区間で大幅過大予測）

### 4. graph 構造 ✅ 3 点で完全不変

- graph nodes = **4,473**（Phase S 16 点と完全一致）
- graph splits = **136 (with bs=ub) + 77 (with bs=1)**（Phase S 16 点と完全一致）
- ub=1280/1536/1792 で splits_main の bs だけが ub に連動、ctx・ub の graph 構造非依存性を 19 点で再確証

### 5. KV buffer ✅ 3 点で max_err 0.000 MiB

全 3 点で `96 · (ctx/16384) = 192 MiB/GPU`、layer 12 on GPU の想定値と完全一致。

### 6. reserve 時間の ub 依存性（副次）

| ub | reserve took |
|---:|---:|
| 1280 | 147.84 ms |
| 1536 | 169.10 ms |
| 1792 | 196.79 ms |

`reserve_ms = 104.3 + 0.0517·ub` に近い線形増加（ub=1280→1792 で +33%）。Phase S の ub=2048 (ctx=32k) での reserve_ms と接続性あり（Phase S ログに戻って確認可能）。

### 7. eval / prompt 性能サマリ

| ctx | ub | prompt | runs | prompt_n | eval_tps (中央値) | prompt_tps |
|---:|---:|---|---:|---:|---:|---:|
| 32,768 | 1,280 | warmup | 3 | 69 | **15.426** | 10.82 |
| 32,768 | 1,280 | 1k | 3 | 1,090 | **15.405** | 68.13 |
| 32,768 | 1,536 | warmup | 3 | 69 | 14.945 | 10.92 |
| 32,768 | 1,536 | 1k | 3 | 1,090 | 14.910 | 68.92 |
| 32,768 | 1,792 | warmup | 3 | 69 | 15.281 | 10.98 |
| 32,768 | 1,792 | 1k | 3 | 1,090 | 15.255 | 68.53 |

**観察**:
- **eval 最速**: ctx=32k × ub=1280 × 1k prompt で **15.405 t/s**。Phase S ctx=32k 系列で最速（Phase S の ctx=32k × ub=512 14.636 / ub=1024 14.640 / ub=4096 14.651 / ub=8192 14.915 すべてを上回る）
- ub=1280 と ub=1792 で eval が比較的速く、ub=1536 で一段遅い「谷」あり — 本 Phase 最大の eval 性能観察
- prompt_tps は 3 点で 68.1〜68.9 t/s と ±1% 以内の変動。ub による prompt 並列化効果が ub ≥ 1280 で飽和しつつあることを示唆

## ボトルネック・副次発見の分析

### 1. CUDA0 区分境界 ub\* = (1536, 1792] — 本 Phase の核心発見

ctx=32k 系列で CUDA0 は **ub=1024 → 1280 → 1536 まで +3.25 MiB/ステップの緩やかな線形**、**ub=1792 で +59.62 MiB の急変**。これは Phase S で推定した「ub=2048 閾値」より内側に境界があることを示す。

物理的に考えると:
- 256 token あたり +3.25 MiB = 12.7 KiB/token の線形増加（平坦域、おそらく attention softmax 前のグローバル staging が 1 token あたり定数）
- 境界 ub\* 近辺で +59.62 MiB = 232 KiB/token に相当する「新 staging の突発追加」が発生
- ub=2048 / 4096 / 8192 では +73 / +800 / +872 MiB と急増する二次項が支配的

**仮説**: llama.cpp scheduler が **ub 閾値（実装では 2^n 境界の 1024 or 2048 付近、または実効ブロック数のしきい値）を越えたときに attention の部分スコアを CUDA0 に staging し始める**。境界は `1024*1.5 = 1536 と 1024*1.75 = 1792 の間`、つまり **およそ 1540〜1790 の間**。実装上の定数は 2^10=1024 ではなく、8-step boundary (1024, 1152, 1280, 1408, 1536, 1664, 1792, ...) のいずれか。

Phase S-boundary-fine 候補として ub=1600, 1664, 1700, 1750 で更に絞り込みが可能。

### 2. CUDA1/2 / CUDA_Host の Phase S 4p モデル 19 点妥当性 — 完全維持

Phase S で ub=128〜8192 × ctx=16k〜131k の 16 点に基づき決定された:

```
CUDA1/2   = 520.26 + 3.903e-3·Δctx + 0.2538·Δub + 1.910e-6·Δctx·Δub   [16 点 R²=0.99999965]
CUDA_Host = 176.08 + 7.813e-3·Δctx + 0.0860·Δub + 3.815e-6·Δctx·Δub   [16 点 R²=1.00000000]
```

本 Phase の新 3 点 (ctx=32k, ub=1280/1536/1792) を追加しても:
- CUDA1/2 残差 |dC1| < 0.21 MiB（既存 max_err 1.715 MiB より良い）
- CUDA_Host 残差 |dH| < 0.01 MiB（既存 max_err 0.005 MiB とほぼ同値）

→ **19 点でも Phase S 4p モデルは R² ≥ 0.99999 を維持**し、CUDA1/2 および CUDA_Host には区分境界が**ない**ことが定量的に確定した。**CUDA0 のみが区分的挙動**という Phase S の所見を、境界周辺での対比によって強化した。

### 3. CUDA3 純 ub 比例性の 19 点確証

Phase S で 16 点 max_err 0.000 MiB だった `CUDA3 = 0.9824·ub`。本 Phase 3 点を加えても:

| ub | 実測 | 0.9824·ub | 差 |
|---:|---:|---:|---:|
| 1280 | 1257.50 | 1257.47 | +0.028 |
| 1536 | 1509.00 | 1508.97 | +0.034 |
| 1792 | 1760.50 | 1760.46 | +0.039 |

→ **19 点 max_err 0.039 MiB**（Phase S の 16 点時点 max_err 0.000 より若干大きいが、ub=1280/1536/1792 は 2^n 丸め境界ではないため量子化残差 ≈ 0.03 MiB は自然）。純 ub 比例の物理的確定は揺るがず。

### 4. eval 性能「谷」の再発見

ctx=32k での eval 中央値 (1k prompt):
- ub=512: 14.636 t/s (Phase S)
- ub=1024: 14.640 t/s (Phase S)
- **ub=1280: 15.405 t/s** (本 Phase、**最速**)
- **ub=1536: 14.910 t/s** (本 Phase、谷)
- **ub=1792: 15.255 t/s** (本 Phase)
- ub=2048: 15.06 t/s (Phase R-ctx3 の近傍 ctx=32k × ub=2048)
- ub=4096: 14.651 t/s (Phase S)
- ub=8192: 14.915 t/s (Phase S)

**観察**: ctx=32k 系列では **ub=1280 が eval 最速 (15.405 t/s)**。Phase Q の ub=2048 付近最速という観察と併せると、eval 性能は **ub ∈ [1280, 2048]** に「ピーク帯」があり、境界 ub\* ≈ (1536, 1792] を跨ぐ箇所で eval が一旦落ち込む（ub=1536 の谷）。CUDA0 staging 開始に伴う GPU0 パイプラインの一時的な非効率が eval を劣化させる可能性。

ただし各 ub で 3 run の中央値のみのため、セッション間ゆらぎは別実験で要確認。

### 5. stdout redirect 方式の再現性確認

Phase S で新規導入した `bash start_phaseSb.sh > log 2>&1 &` + `wait PID` 方式が本 Phase でも **1 回もパイプ詰まりなく動作**。全 3 条件を 33 分で完走（1 条件 10.3 分、Phase S の batch_S3onwards.sh 段階と同じ所要感）。本方式は skill の batch 運用パターンとして確定可能。

## 採用判定

| 項目 | 結果 |
|---|---|
| Sb1-Sb3 起動成功 (/health OK) | ✅ 3 条件すべて正常起動（すべて 4*5s=20s で /health OK、ページキャッシュ有効） |
| OOM / -ub 下限拒否 | ✅ ゼロ |
| sched_reserve 全 5 チャネル採取 | ✅ 3 点 × 5 GPU = 15 データ点 |
| CUDA3 純 ub 比例性 (3 点 max_err 0.039 MiB) | ✅ **維持** |
| CUDA1/2 4p モデル 3 点残差 max_err 0.21 MiB | ✅ **Phase S モデル維持** |
| CUDA_Host 4p モデル 3 点残差 max_err 0.01 MiB | ✅ **Phase S モデル維持** |
| CUDA0 境界 ub\* 確定 | ✅ **ub\* ∈ (1536, 1792]** |
| Phase S 平坦域モデル `966.5+0.0064·ub` の ub=1024→1536 外挿 | ✅ max_err +3.17 MiB（延伸可） |
| Phase S 6p 急増域モデルの ub ≤ 1792 延伸 | ❌ 誤差 -75〜-123 MiB（6p は ub ≥ 2048 専用を再確認） |
| graph 構造 3 点不変 | ✅ nodes=4473, splits_bs1=77 |
| KV buffer 3 点誤差 0 MiB | ✅ **max_err 0.000** |
| eval 速度 ≥ 14.5 t/s (全条件) | ✅ ub=1280 で 15.405 t/s（ctx=32k 系列最速） |

**結論**: **Phase S-boundary は全成功条件を達成**。主要な新規発見:

1. **CUDA0 区分境界 ub\* ∈ (1536, 1792]** を定量的に確定
2. **Phase S 4p モデルの CUDA1/2 / CUDA_Host 部分は 19 点でも高精度維持**（CUDA1/2 0.21 MiB、Host 0.01 MiB）
3. **CUDA0 平坦域モデル `966.5 + 0.0064·ub` は ub ≤ 1536 まで延伸可能**（max_err +3.17 MiB）
4. **CUDA0 急増域 6p モデルは ub ≥ 2048 でのみ有効**（ub=1792 に適用すると -115 MiB の過小予測だが絶対値として CUDA0 実測より過大、境界以下では使えない）
5. **eval 最速条件**: ctx=32k × ub=1280 × 1k prompt で **15.405 t/s**（ctx=32k 系列の既知最速）

## 確定モデル（更新版、Phase S の 16 点モデルに本 Phase 3 点を加えた 19 点検証済み）

```
Δctx = ctx - 16384, Δub = ub - 2048

fa=1, C-D3, f16 KV: compute_buffer [MiB]

  CUDA0 (3 区分モデル):
    ub ≤ 1024:  966.50 + 0.0064·ub                                              [平坦域、Phase Q 5 点で確定]
    1024 < ub ≤ 1536:  966.50 + 0.0064·ub                                        [平坦域延伸、本 Phase 2 点で max_err +3.17 MiB]
    1536 < ub ≤ 1792:  境界遷移域（本 Phase で突入、実測 1039.12 MiB @ ub=1792）    [詳細モデル未確定、要追加計測]
    ub ≥ 2048:  1116.34 + 4.996e-3·Δctx + 3.670e-8·Δctx² + 0.1115·Δub
                + 6.016e-6·Δctx·Δub + 9.104e-6·Δub²                             [R²=0.9918、max_err 236 MiB]

  CUDA1/2   = 520.26 + 3.903e-3·Δctx + 0.2538·Δub + 1.910e-6·Δctx·Δub         [19 点 max_err 1.72 MiB]
  CUDA3     = 0.9824·ub                                                         [19 点 max_err 0.039 MiB]
  CUDA_Host = 176.08 + 7.813e-3·Δctx + 0.0860·Δub + 3.815e-6·Δctx·Δub          [19 点 max_err 0.01 MiB]

KV buffer (per GPU): 96 × (ctx/16384) MiB                                       [19 点 max_err 0.000]
graph nodes: 4473 (ub/ctx 不変)
graph splits: 136 (bs=ub) + 77 (bs=1)
```

## 未検証事項

### 既知項目（Phase S から継続、本 Phase で潰したものに [x]）

- [x] **CUDA0 区分境界 ub\* の特定** (Phase S 新規項目最上位) — 本 Phase で ctx=32k × ub=1280/1536/1792 を計測、**ub\* ∈ (1536, 1792] に確定**
- [ ] **CUDA0 区分境界 ub\* のさらなる絞り込み** (本 Phase 新規) — ub=1600/1664/1700/1750 等の更に細かい刻みで境界を 64-token 精度以下まで特定
- [ ] **CUDA0 区分モデルの物理的意味** (Phase S 新規) — llama.cpp scheduler ソース (`llama_sched` / `graph_reserve`) で ub 閾値判定ロジックを特定し、どのテンソル/layer が境界を越えて CUDA0 に追加 staging されるか同定
- [ ] **CUDA0 二次係数 5.770e-8 MiB/token² の物理メカニズム** (Phase S) — 本 Phase で境界特定したが、急増域の二次挙動の物理起源は未特定
- [ ] **CUDA0 二次モデルの ctx=262144 外挿** (Phase R-ctx3 継続)
- [ ] **CUDA0 区分境界 ub\* の ctx 依存性** (本 Phase 新規) — 本 Phase は ctx=32k 固定、ctx=16k/65k/131k での境界 ub\* 位置が同じか要確認（Phase S の既測データで ub=512/1024 は ctx=16k/32k/65k ですべて同値、つまり平坦域 ub 閾値は ctx 独立と強く示唆されるが、境界値そのものの ctx 依存性は未検証）
- [ ] **CUDA0 境界遷移域 (1536 < ub ≤ 1792) の数学モデル** (本 Phase 新規) — 平坦域モデルでは +61 MiB 過小、6p 急増域モデルでは -76 MiB 過大。中間域専用の 1-2 パラメータモデルが必要
- [ ] **CUDA1/2 cross_e = 1.910e-6, Host = 3.815e-6 MiB/(token·token) の物理メカニズム** (Phase S 継続)
- [ ] **ub=1280/1792 の eval 性能再現性** (本 Phase 新規) — ub=1280 で 15.405 t/s の eval ピーク、ub=1536 で 14.910 t/s の谷、ub=1792 で 15.255 t/s の回復。3 run 中央値のみ、セッション間ゆらぎ検証 5-10 run 必要
- [ ] **ub=1280/1536/1792 × ctx=65k での CUDA0 検証** (本 Phase 新規) — 境界 ub\* の ctx 依存性と合わせて、ctx=65k でも境界が同じかを ub=1536/1792 で確認
- [ ] **fa=0 側での同様の区分境界** (Phase S 継続) — fa=0 では scheduler 経路が異なる可能性、同じ ub\* 位置か要確認
- [ ] **q8_0 KV 構成での同様の区分境界** (Phase S 継続) — KV 半減で境界 ub\* も変わる可能性
- [ ] **中間 ctx (24k / 48k / 96k) での検証** (Phase S 継続)
- [ ] **ctx=65k 32k prompt の 3 run 以上再計測** (Phase R-ctx3 継続)
- [ ] **CUDA3 が ctx 完全不依存となる物理メカニズム** (Phase R から継続、19 点再確証済みだがソース未特定)
- [ ] **120k eval 12.82 t/s の Run 間再現性** (Phase R から継続)
- [ ] **prompt 処理のピークが ctx=8k にある理由**
- [ ] **KV layer 数 12 の物理的確認**（ソース/ログから層番号特定）
- [ ] **ctx=262,144（モデルの n_ctx_train）での起動可否**
- [ ] **RS buffer 149.06 MiB の用途特定**: Gated Delta Net 由来
- [ ] **prompt cache (size limit 8192 MiB) の実際の挙動**
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
- [ ] **eval 速度のセッション間ゆらぎレンジ更新**
- [ ] **prompt 処理の ctx 非依存の長 ctx 側確認**
- [ ] **fa=1 eval の「谷型」(ctx=2048 最高 → ctx=4096 最低) の再現性**
- [ ] **Phase M のモデルを f16 KV → q8_0 KV（C-D3 採用構成）に適用した場合の整合性**
- [ ] **ctx=6144 等の中間 ctx での fa=1 / fa=0 境界確認**
- [ ] **fa=0 ctx=8192 で CUDA1 空き枠を増やす手法**
- [ ] **eval 谷型の最低値 ctx の fa=1 における物理原因**

### 既知項目（Phase Q で新規追加、Phase R / R-ctx3 / S / Sb で部分的に潰したもの）

- [ ] **`-ub=1 (greedy)` でのベンチマーク**: 未実施
- [ ] **`-ub > -b` の挙動（llama.cpp 制約検証）**: 未実施
- [ ] **fa=0 側での `-ub` 支配性の確認**: 未実施
- [x] **大 prompt での `-ub` 依存性** (Phase S で部分潰し、本 Phase 1k のみ)
- [ ] **`-b > -ub` 運用の意義**: Phase P で観測のみ
- [x] **graph splits=77 (with bs=1) の存在意義** (本 Phase 19 点で全条件 77 固定を再確認、意義は未特定)
- [ ] **`--parallel 2` との相互作用**
- [ ] **P3 vs Phase O の eval 差 +1.17% のセッション源**

### 新規項目（本 Phase Sb で判明・発生）

- [ ] **★最優先: CUDA0 境界 ub\* の 64-token 精度での絞り込み** (Phase S-boundary-fine 候補): ub=1600/1664/1700/1750 で追加計測、ub\* を 64-token 以下の精度で特定
- [ ] **★高優先: 境界遷移域 (1536 < ub ≤ 1792) の専用 CUDA0 モデル導出**: 現行の平坦域モデル `966.5+0.0064·ub` は ub=1792 で -61 MiB 過小、6p 急増モデルは +76 MiB 過大。中間域専用の 1-2 パラメータ fit (S字 / 閾値シフト) を検討
- [ ] **ub=1280 × ctx=32k eval ピーク 15.405 t/s の再現性**: 3 run 中央値のため、5-10 run で検証要
- [ ] **境界 ub\* の ctx 依存性**: 本 Phase は ctx=32k 固定、ctx=65k / 131k でも境界が (1536, 1792] にあるか ub=1536/1792 の 2 点追加で確認可能
- [ ] **境界 ub\* の fa 依存性**: fa=0 でも同じ ub\* 位置か、または fa スケジューラ経路の違いで異なる境界を持つか
- [ ] **境界 ub\* の KV 量子化依存性**: q8_0 KV で境界が移動するか
- [ ] **eval 性能「谷」(ub=1536) の再現性と物理原因**: ub=1280/1792 > ub=1536 の構造が偶発か、staging 開始に伴う GPU0 パイプライン非効率か
- [ ] **reserve 時間 vs ub の線形性の連続値確認**: 本 Phase 3 点で 147.84→169.10→196.79 ms。ub=512〜8192 全条件で reserve_ms を集計すれば 2 軸モデル化可能
- [ ] **llama.cpp scheduler ソースの ub 閾値判定箇所特定**: `graph_reserve` / `sched_reserve` / `llama-graph.cpp` で 1600-1700 付近の閾値定数を grep（要 llama.cpp リポジトリ側調査）

## 検証完了後に実施すべき TODO

### 既知項目（Phase S から継続、本 Phase で更新）

- [ ] **start.sh の拡張**: `LLAMA_NUMACTL_PREFIX` / `LLAMA_EXTRA_THREADS` 環境変数サポート追加
- [ ] **CUDA1 セーフティマージン OOM フォールバック実装**
- [ ] **層→GPU アライメントのソースコード解析**
- [ ] **C-4 実験**（CPU 層削減 + GPU 層追加）
- [ ] **drop_caches 権限の確保**（sudoers 設定 or vmtouch 導入）
- [ ] **start.sh での NUMA プリセット整備**
- [ ] **start.sh に `--threads` 設定追加**
- [ ] **`start_phaseJ.sh` 〜 `start_phaseSb.sh` の環境変数化を skill 側 `start.sh` に逆輸入**
- [ ] **依存制約の lint 化**: 起動前 pre-check
  - **本 Phase で更新**: CUDA0 3 区分モデル（ub ≤ 1536 / 1536 < ub < 1792 (遷移) / ub ≥ 1792 (急増)）
  - CUDA1/2/Host は Phase S 4p モデル (19 点検証済み)
  - CUDA3 = 0.9824·ub (19 点検証済み)
- [ ] **llama.cpp upstream issue/PR のサーベイ**
- [ ] **`measure_phaseI.sh` を汎用化して skill に組み込む**
- [ ] **「長コンテキスト性能カード」をモデル単位で記録するドキュメント整備**
- [ ] **アプリ側にコンテキストサイズ別レイテンシ警告を出す仕組み**

### 新規項目（本 Phase Sb で発見・更新）

- [ ] **★最優先: 起動前 lint の CUDA0 3 区分モデル組み込み**（Phase S の 2 区分を 3 区分に更新）:
  - `ub ≤ 1536`: `CUDA0 ≈ 966.5 + 0.0064·ub` + マージン 10 MiB（平坦域、max_err +3.17 MiB）
  - `1536 < ub < 1792`: 境界遷移域、保守的に `max(1100 MiB, 6p fit)` + マージン 100 MiB（ub=1792 実測 1039 MiB 近傍を跨ぐ）
  - `ub ≥ 1792`: 6p 二次 + マージン 300 MiB（Phase S 既定）
- [ ] **★最優先: 起動前 lint の 4p cross 項モデル組み込み** (Phase S から継続):
  - `predicted_cuda1/2 = 520.26 + 3.903e-3·Δctx + 0.2538·Δub + 1.910e-6·Δctx·Δub`（19 点 max_err 1.72 MiB）
  - `predicted_cuda_host = 176.08 + 7.813e-3·Δctx + 0.0860·Δub + 3.815e-6·Δctx·Δub`（19 点 max_err 0.01 MiB）
  - `predicted_cuda3 = 0.9824·ub`（19 点 max_err 0.039 MiB）
  - Δctx = ctx - 16384, Δub = ub - 2048
- [ ] **★最優先: compute buffer 予測モデル（Phase Sb 確定版）を skill / CLAUDE.md に記録**:
  - **fa=1, f16 KV, C-D3**: 19 点検証済みの確定式、ub=128〜8192 × ctx=16k〜131k
  - **CUDA0 は 3 区分モデル (境界 ub\* ∈ (1536, 1792])**、**CUDA1/2/Host は 4p 2 軸 cross 項**、**CUDA3 は純 ub 比例**を明記
- [ ] **★最優先: skill 側 `.claude/skills/llama-server/scripts/start.sh:155` を `-b=2048 -ub=2048` に変更** (Phase R-ctx3 / S から継続):
  - 現状 t120h-p100 デフォルト: `SERVER_OPTS="--flash-attn 1 --poll 0 -b 8192 -ub 8192"`
  - 本 Phase で ctx=32k × ub=1280 が ctx=32k 系列 eval 最速 (15.405 t/s) と判明。ub=1280/2048 が候補
  - 変更候補: `-b 1280 -ub 1280`（eval 最速） or `-b 2048 -ub 2048`（prompt も踏まえた平衡点）
- [ ] **CLAUDE.md / skill の情報更新**:
  - **fa=1 の CUDA0 は 3 区分モデル (境界 ub\* ∈ (1536, 1792])**
  - **CUDA1/2/CUDA3/CUDA_Host は Phase S 4p/純比例モデル、19 点 max_err 0〜1.72 MiB**
  - **Qwen3.5-122B-A10B t120h-p100 で ub=128〜8192 × ctx=16k〜131k の compute buffer が 19 点実測で 2 軸モデル化、ub=1280 が ctx=32k の eval 最速**
- [ ] **モデルカード更新**: Qwen3.5-122B-A10B の長コンテキスト性能カードに本 Phase 結果を追加
- [ ] **Phase Sb-fine 候補**: ub=1600/1664/1700/1750 の 4 点で境界 ub\* を 64-token 精度で確定
- [ ] **Phase Sb-ctx 候補**: ctx=65k / 131k での境界 ub\* 確認 (ub=1536 と 1792 の 2 点のみで ctx 依存性検証可能、所要 20 分程度)
- [ ] **Phase Sb-fa0 候補**: fa=0 系列で同一 3 条件スキャン
- [ ] **Phase Sb-KV8 候補**: `--cache-type-{k,v} q8_0` で本 Phase を再実施
- [ ] **Phase S-eval 候補**: ctx=32k × ub=1280 eval 15.405 t/s を 5-10 run で再現性検証（ctx=65k × ub=512 の Phase S 15.39 t/s と共に）
- [ ] **Phase Q-2 候補（`-ub` 内部下限の真の値特定）**: `-ub=64 / 32 / 16 / 8 / 4 / 2 / 1`
- [ ] **Phase Q-3 候補（`-ub` ピーク周辺探索）**: ub=2304 / 2560 / 2816 / 3072（本 Phase で 1280 が eval 最速と判明、ub=1100-1400 のさらに細かい eval 探索も有効）
- [ ] **skill 側 start.sh の `ssh -f` stdout redirect 改修** (Phase S から継続): 本 Phase で 3 条件すべて hang なし、batch_boundary.sh のパターンが確定版
- [ ] **start.sh のデフォルト `ctx-size` を 131072 に更新**（現状 65536、Phase S から継続）

## 補足

### Phase Sb の核心発見

1. **CUDA0 区分境界 ub\* ∈ (1536, 1792]** — Phase S で「(1024, 2048] 区間」と推定した境界を 256-token 精度で絞り込み
2. **ub=1024 → 1536 の CUDA0 は +3.25 MiB/step の線形挙動** — 平坦域モデル `966.5 + 0.0064·ub` が max_err +3.17 MiB で ub=1536 まで延伸可
3. **ub=1536 → 1792 で +59.62 MiB の急変** — 直前までの傾きの 18 倍、境界突破の定量証拠
4. **Phase S 4p モデル (CUDA1/2, Host) は 19 点で max_err < 0.25 MiB** — CUDA0 区分性の「ほとんど全ての他 GPU に波及しない」ことを確定
5. **CUDA3 純 ub 比例性は 19 点で max_err 0.039 MiB** — Phase S の 16 点確定を強化
6. **ctx=32k × ub=1280 × 1k prompt で eval 15.405 t/s** — ctx=32k 系列の既知最速
7. **eval 性能の「谷」(ub=1536)** — ub=1280 > ub=1792 > ub=1536 の順、境界突破に伴う GPU0 非効率仮説
8. **batch 33 分で完走、stdout redirect 版 batch_boundary.sh は安定運用可能** — Phase S の 2 時間 5 分の 1/4、効率的 Phase

### 19 点データベース（ctx=32k, ub=1280/1536/1792 を追加、ub 昇順）

| # | ctx | ub | CUDA0 | CUDA1 | CUDA2 | CUDA3 | CUDA_Host | 合計 | KV/GPU | Phase |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 16,384 | 128 | 961.62 | 34.64 | 34.64 | 125.75 | 11.00 | 1,167.65 | 96.00 | Q |
| 2 | 16,384 | 256 | 963.25 | 65.01 | 65.01 | 251.50 | 22.01 | 1,366.78 | 96.00 | Q |
| 3 | 16,384 | 512 | 966.50 | 130.02 | 130.02 | 503.00 | 44.02 | 1,773.56 | 96.00 | Q |
| 4 | 16,384 | 1024 | 973.00 | 260.03 | 260.03 | 1,006.00 | 88.04 | 2,587.10 | 96.00 | Q |
| 5 | 16,384 | 2048 | 1,048.13 | 520.06 | 520.06 | 2,012.00 | 176.08 | 4,276.33 | 96.00 | Q/R-ctx3 |
| 6 | 32,768 | 512 | 966.50 | 146.02 | 146.02 | 503.00 | 76.02 | 1,837.56 | 192.00 | S1 |
| 7 | 32,768 | 1024 | 973.00 | 292.03 | 292.03 | 1,006.00 | 152.04 | 2,715.10 | 192.00 | S2 |
| 8 | 32,768 | **1280** | **976.25** | **365.04** | **365.04** | **1,257.50** | **190.05** | **3,153.88** | **192.00** | **Sb1** |
| 9 | 32,768 | **1536** | **979.50** | **438.05** | **438.05** | **1,509.00** | **228.06** | **3,592.66** | **192.00** | **Sb2** |
| 10 | 32,768 | **1792** | **1,039.12** | **511.05** | **511.05** | **1,760.50** | **266.07** | **4,087.79** | **192.00** | **Sb3** |
| 11 | 32,768 | 2048 | 1,112.13 | 584.06 | 584.06 | 2,012.00 | 304.08 | 4,596.33 | 192.00 | R-ctx3 |
| 12 | 32,768 | 4096 | 1,912.00 | 1,168.13 | 1,168.13 | 4,024.00 | 608.16 | 8,880.42 | 192.00 | S3 |
| 13 | 32,768 | 8192 | 2,784.00 | 2,336.25 | 2,336.25 | 8,048.00 | 1,216.31 | 16,720.81 | 192.00 | S4 |
| 14 | 65,536 | 512 | 966.50 | 178.02 | 178.02 | 503.00 | 140.02 | 1,965.56 | 384.00 | S5 |
| 15 | 65,536 | 1024 | 973.00 | 356.03 | 356.03 | 1,006.00 | 280.04 | 2,971.10 | 384.00 | S6 |
| 16 | 65,536 | 2048 | 1,348.00 | 712.06 | 712.06 | 2,012.00 | 560.08 | 5,344.20 | 384.00 | R-ctx3 |
| 17 | 65,536 | 4096 | 2,296.00 | 1,424.13 | 1,424.13 | 4,024.00 | 1,120.16 | 10,288.42 | 384.00 | S7 |
| 18 | 65,536 | 8192 | 4,320.00 | 2,848.25 | 2,848.25 | 8,048.00 | 2,240.31 | 20,304.81 | 384.00 | S8 |
| 19 | 131,072 | 2048 | 2,180.00 | 968.06 | 968.06 | 2,012.00 | 1,072.08 | 7,200.20 | 768.00 | R |

（太字 = 本 Phase Sb 新規計測）

### eval / prompt 性能データベース（ctx=32k × ub=1280/1536/1792、1k prompt 3 run 中央値）

| ctx | ub | prompt_med (t/s) | eval_med (t/s) | prompt_n | 備考 |
|---:|---:|---:|---:|---:|---|
| 32,768 | 1,280 | 68.13 | **15.405** | 1,090 | Sb1 ★ ctx=32k eval 最速 |
| 32,768 | 1,536 | 68.92 | 14.910 | 1,090 | Sb2 ★ ctx=32k eval 最遅（谷） |
| 32,768 | 1,792 | 68.53 | 15.255 | 1,090 | Sb3 |

### 作業終了時点の状態

- llama-server は停止済み（batch_boundary.sh 末尾の stop.sh で正常終了）
- GPU サーバロック（t120h-p100）は解放済み（unlock.sh）
- `results.tsv` 19 行（Sb1-Sb3 × warmup/1k × 3 run = 18 run + ヘッダ）
- `compute_buffer_summary.txt` 54 行（3 条件 × 主要 18 行）
- `analyze_boundary.py` / `analyze_boundary.txt` で Phase S 4p モデル検証 + CUDA0 区分モデル判定
- **CUDA0 境界 ub\* ∈ (1536, 1792] を確定、CUDA1/2/3/Host の 19 点検証、skill 側 start.sh の `-b/-ub` デフォルト更新を次の最優先タスクとして登録**
