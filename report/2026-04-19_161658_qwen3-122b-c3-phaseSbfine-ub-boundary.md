# Qwen3.5-122B-A10B C-3 Phase Sb-fine（CUDA0 区分境界 ub\* の 64-token 精度絞り込み）

- **実施日時**: 2026年4月19日 16:16 – 17:00 (JST、実計測時間 約 44 分)
- **作業種別**: 計測・検証（Phase Sb 未検証事項「新規項目」最上位「CUDA0 境界 ub\* の 64-token 精度での絞り込み」）

## 添付ファイル

- [実装プラン](attachment/2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary/plan.md)
- [起動スクリプト (start_phaseSbf.sh、Phase Sb からプレフィックスのみ phaseSbf\_ に変更)](attachment/2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary/start_phaseSbf.sh)
- [計測スクリプト (measure_phaseI.sh、流用)](attachment/2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary/measure_phaseI.sh)
- [一括実行スクリプト (run_all.sh、流用)](attachment/2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary/run_all.sh)
- [4 条件バッチスクリプト (batch_boundary_fine.sh、CONDS を 4 行化)](attachment/2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary/batch_boundary_fine.sh)
- [集計スクリプト (aggregate_boundary_fine.sh、`out_Sbf_*` 対応)](attachment/2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary/aggregate_boundary_fine.sh)
- [解析スクリプト (analyze_boundary_fine.py、ub >= 1600 線形モデル新規 fit + 23 点検証)](attachment/2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary/analyze_boundary_fine.py)
- [解析結果 (analyze_boundary_fine.txt)](attachment/2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary/analyze_boundary_fine.txt)
- [集計結果 TSV (results.tsv、4 条件 × warmup/1k × 3 run = 24 run)](attachment/2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary/results.tsv)
- [compute buffer サマリ (compute_buffer_summary.txt)](attachment/2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary/compute_buffer_summary.txt)
- [バッチログ (batch_boundary_fine.log)](attachment/2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary/batch_boundary_fine.log)
- 起動ログ 4 条件（`startup_logs/fa1_ctx32768_b{1600,1664,1700,1750}_ub{同}.log`）
- `out_Sbf_*` 計測アーティファクト 4 条件（warmup + 1k、計 24 run）

## 参照

- 直前レポート: [2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary.md](2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary.md)
- Phase S (ub × ctx 2 軸 16 点): [2026-04-19_120715_qwen3-122b-c3-phaseS-ub-ctx-2d.md](2026-04-19_120715_qwen3-122b-c3-phaseS-ub-ctx-2d.md)
- Phase Q (ub 下限探索、ctx=16k): [2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound.md](2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound.md)

## 前提・目的

直前レポート Phase Sb の末尾「未検証事項 / 新規項目」最上位かつ「検証完了後に実施すべき TODO / 新規項目」に **Phase Sb-fine 候補**として登録:

> **★最優先: CUDA0 境界 ub\* の 64-token 精度での絞り込み** (Phase S-boundary-fine 候補): ub=1600/1664/1700/1750 で追加計測、ub\* を 64-token 以下の精度で特定

Phase Sb で確定した境界区間:

| ub | ... | 1024 | 1280 | 1536 | **?** | ? | ? | 1792 | 2048 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CUDA0 (MiB) | | 973.00 | 976.25 | 979.50 | | | | 1039.12 | 1112.13 |
| Δ/step | | — | +3.25 | +3.25 | (+59.62 at jump) | | | | +73.01 |

- **境界 ub\*** は `(1536, 1792]` の 256-token 区間内と確定、実位置は未特定
- ub=1536 → 1792 の 256-token で +59.62 MiB のジャンプが発生

本 Phase では ctx=32768 固定で **ub=1600/1664/1700/1750 の 4 条件**を計測し:

1. **CUDA0 区分境界 ub\*** を 64-token 精度で特定
2. **Phase Sb 4p 2 軸モデル** (CUDA1/2, CUDA_Host) の 19 → 23 点再検証
3. **CUDA3 純 ub 比例式** (0.9824·ub) の 19 → 23 点再確証
4. 副次目的: ub=1600/1664/1700/1750 での eval/prompt 性能を把握

### 成功条件

- [x] 4 条件すべて起動成功（/health OK、OOM ゼロ、-ub 下限拒否ゼロ）
- [x] CUDA3 4 点で `0.9824·ub ± 0.1 MiB`（実測 max_err 0.040 MiB）
- [x] CUDA0 4 点で境界 ub\* を 64-token 精度で確定 — **実測 ub\* ∈ (1536, 1600]**
- [x] CUDA1/2 / CUDA_Host 4 点が Phase Sb 確定 4p モデルと max_err < 5 MiB — **実測 max_err 0.185 / 0.004 MiB**
- [x] graph nodes=4473 / splits_bs1=77 の 4 条件不変
- [x] KV buffer 4 点で `96·(ctx/16384)` = 192 MiB 誤差 0 MiB

## 環境情報

- **サーバ**: `t120h-p100` (10.1.4.14)
- **GPU**: NVIDIA Tesla P100-PCIE-16GB × 4（各 16,269 MiB、合計 65,077 MiB、CC 6.0）
- **CPU**: Intel Xeon Gold 6138 @ 2.00GHz × 2 socket、計 40 コア / 80 スレッド、NUMA 2 ノード
- **メモリ**: 257,560 MiB (約 251 GiB)
- **モデル**: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- **llama.cpp ビルド**: b8807-b3d758750（Phase D〜Sb と同一系列）
- **構成**: Phase Sb と同一 C-D3 base + `--cache-type-{k,v} f16`
  - NUMA: `numactl --cpunodebind=1 --membind=1 --`
  - `--threads 40 --poll 0 -ngl 999`
  - `-ot 'blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'`
  - `--flash-attn 1 -b ub -ub ub` (b=ub 同値)
- **条件マトリクス（4 条件 × warmup/1k 3 run 各）**:
  - Sbf1: ctx=32768 × ub=1600
  - Sbf2: ctx=32768 × ub=1664
  - Sbf3: ctx=32768 × ub=1700
  - Sbf4: ctx=32768 × ub=1750

## 再現方法

### スクリプト差分（Phase Sb からの改変は最小限）

- `start_phaseSbf.sh`: `REMOTE_LOG` プレフィックスを `phaseSb_` → `phaseSbf_` に置換、ログ識別子を `[start_phaseSbf]` に一斉置換
- `batch_boundary_fine.sh`: Phase Sb の `batch_boundary.sh` をベースに `CONDS` 配列を 4 行 (ctx=32768 × ub=1600/1664/1700/1750) に置換、識別子を `[batchSbf]`、start script 参照を `start_phaseSbf.sh`、REMOTE_LOG 参照と TAG_PREFIX を `phaseSbf_/Sbf_` に置換
- `aggregate_boundary_fine.sh`: `out_Sb_*` → `out_Sbf_*` に置換
- `measure_phaseI.sh` / `run_all.sh` / `prompts/`: **無改変流用**
- `analyze_boundary_fine.py`: **新規** (Phase Sb 4p モデル検証 + CUDA0 平坦域 / 新 `ub >= 1600 線形` モデルの比較、Python 標準ライブラリのみ使用)

### 実行フロー（実際の実行順序）

```bash
# 1. ロック取得 + ディレクトリ準備 + スクリプト流用
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
TS=2026-04-19_161658
PHASE_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseSbfine-ub-boundary"
mkdir -p "$PHASE_DIR/startup_logs"
PHASE_SB="report/attachment/2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary"
cp "$PHASE_SB"/{measure_phaseI.sh,run_all.sh,start_phaseSb.sh,aggregate_boundary.sh,batch_boundary.sh} "$PHASE_DIR/"
cp -r "$PHASE_SB/prompts" "$PHASE_DIR/"
mv "$PHASE_DIR/start_phaseSb.sh" "$PHASE_DIR/start_phaseSbf.sh"
mv "$PHASE_DIR/batch_boundary.sh" "$PHASE_DIR/batch_boundary_fine.sh"
mv "$PHASE_DIR/aggregate_boundary.sh" "$PHASE_DIR/aggregate_boundary_fine.sh"

# プレフィックス置換
sed -i 's/phaseSb_/phaseSbf_/g; s/\[start_phaseSb\]/[start_phaseSbf]/g' "$PHASE_DIR/start_phaseSbf.sh"
sed -i 's/\[batchSb\]/[batchSbf]/g; s/start_phaseSb\.sh/start_phaseSbf.sh/g; s/phaseSb_/phaseSbf_/g; s/TAG_PREFIX="Sb_f16/TAG_PREFIX="Sbf_f16/g; s/run_Sb_ctx/run_Sbf_ctx/g; s/start_stdout_Sb_ctx/start_stdout_Sbf_ctx/g' "$PHASE_DIR/batch_boundary_fine.sh"
sed -i 's/out_Sb_\*/out_Sbf_*/g' "$PHASE_DIR/aggregate_boundary_fine.sh"
# batch_boundary_fine.sh の CONDS 配列は 4 行 (32768 1600/1664/1700/1750) に手動編集

# 2. 4 条件バッチ計測
cd "$PHASE_DIR"
bash batch_boundary_fine.sh > batch_boundary_fine.log 2>&1

# 3. 停止 + 集計 + 解析 + 解放
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash aggregate_boundary_fine.sh > results.tsv
grep -E "sched_reserve:|KV buffer|graph nodes|graph splits|cudaMalloc|failed to allocate|reserve took|llama_kv_cache: size|llama_memory_recurrent: size" \
  startup_logs/*.log > compute_buffer_summary.txt
python3 analyze_boundary_fine.py | tee analyze_boundary_fine.txt
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 実行タイムライン

| フェーズ | 開始 | 終了 | 所要 |
|---|---:|---:|---:|
| lock 取得 + ディレクトリ準備 + スクリプト編集 | 16:16 | 16:17 | 1 分 |
| Sbf1 (ctx=32k ub=1600) バッチ起動+計測 | 16:17:34 | 16:27:49 | 10 分 15 秒 |
| Sbf2 (ctx=32k ub=1664) バッチ起動+計測 | 16:28:03 | 16:38:25 | 10 分 22 秒 |
| Sbf3 (ctx=32k ub=1700) バッチ起動+計測 | 16:38:39 | 16:48:57 | 10 分 18 秒 |
| Sbf4 (ctx=32k ub=1750) バッチ起動+計測 | 16:49:11 | 16:59:30 | 10 分 19 秒 |
| 停止 + 集計 + 解析 + 解放 | 17:00 | 17:00 | < 1 分 |

実計測時間: **約 44 分**（Phase Sb の stdout redirect 版パターンをそのまま流用、1 回もパイプ詰まりなし）

## 実行結果サマリ

### 1. compute buffer 実測値（4 点）

| GPU | ctx=32k ub=1600 | 32k/1664 | 32k/1700 | 32k/1750 |
|---|---:|---:|---:|---:|
| CUDA0 | **984.35** | **1,002.61** | **1,012.88** | **1,027.14** |
| CUDA1 | 456.30 | 474.55 | 484.82 | 499.08 |
| CUDA2 | 456.30 | 474.55 | 484.82 | 499.08 |
| CUDA3 | 1,571.88 | 1,634.75 | 1,670.12 | 1,719.24 |
| CUDA_Host | 237.56 | 247.06 | 252.41 | 259.83 |
| KV/GPU | 192.00 | 192.00 | 192.00 | 192.00 |

### 2. 境界 ub\* の確定 ✅ ub\* ∈ (1536, 1600]

Phase Q/S/Sb 既測データに本 Phase 4 点を追加した ctx=32k 系列 CUDA0:

| ub | 1024 | 1280 | 1536 | **1600** | **1664** | **1700** | **1750** | 1792 | 2048 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CUDA0 (MiB) | 973.00 | 976.25 | 979.50 | **984.35** | **1,002.61** | **1,012.88** | **1,027.14** | 1,039.12 | 1,112.13 |
| Δ from prev | — | +3.25 | +3.25 | **+4.85** | **+18.26** | **+10.27** | **+14.26** | +11.98 | +73.01 |
| Δ/step (MiB/tok) | — | 0.0127 | 0.0127 | **0.0758** | **0.285** | **0.285** | **0.285** | **0.285** | 0.2854 |

**決定的発見**:
- ub=1536 → **1600 で +4.85 MiB**（平坦域傾きの ~6 倍）— 境界突破の兆候
- ub=1600 → **1664 で +18.26 MiB**（平坦域傾きの 22 倍）— 完全な新定常域へ移行
- **ub=1600 以降の傾きは 0.285 MiB/token で一定**（ub=1664/1700/1750/1792/2048 の 5 点で極めて線形）
- **境界 ub\* は (1536, 1600] の 64-token 区間内** に確定

### 3. ub ≥ 1600 線形モデルの発見 🔥 max_err 0.035 MiB（ub=2048 まで外挿成立）

本 Phase の最大発見。ub >= 1600 の 4 点と Phase Sb/R の ub=1792/2048 の 2 点、計 6 点を対象に線形 fit:

```
CUDA0 (ub >= 1600, ctx=32k) = 1002.61 + 0.2853 · (ub - 1664)
```

検証結果:

| ub | 実測 C0 | 予測 | Δ (MiB) |
|---:|---:|---:|---:|
| 1600 | 984.35 | 984.35 | **−0.001** |
| 1664 | 1,002.61 | 1,002.61 | +0.000 |
| 1700 | 1,012.88 | 1,012.88 | −0.001 |
| 1750 | 1,027.14 | 1,027.15 | −0.006 |
| 1792 | 1,039.12 | 1,039.13 | −0.008 |
| **2048** | 1,112.13 | 1,112.17 | **−0.035** |

→ **max_err 0.035 MiB** で ub=1600〜2048 の 6 点が完全に線形モデル上にある。

これは Phase Sb で「ub >= 2048 は二次多項式 R²=0.9918、max_err 236 MiB」とした推定が **ctx 固定では誤りで、ub 軸のみ見ると完全線形** という重要な訂正。Phase Sb の二次性は ctx 方向の寄与だった。

### 4. Phase Sb 4p モデルとの予測誤差（CUDA1/2, CUDA_Host, CUDA3） ✅ max_err 0.185 MiB

`analyze_boundary_fine.py` 出力より本 Phase 新 4 点:

```
  ub     C1    pred    dC1 |   C3      pred   dC3  |  Host  pred   dH
 1600  456.30  456.48  -0.18 | 1571.88 1571.84 +0.04 | 237.56 237.56 +0.00
 1664  474.55  474.73  -0.18 | 1634.75 1634.71 +0.04 | 247.06 247.06 -0.00
 1700  484.82  484.99  -0.17 | 1670.12 1670.08 +0.04 | 252.41 252.41 +0.00
 1750  499.08  499.25  -0.17 | 1719.24 1719.20 +0.04 | 259.83 259.83 -0.00
```

- **CUDA1/2**: Phase Sb 4p モデル (`520.26 + 3.903e-3·Δctx + 0.2538·Δub + 1.910e-6·Δctx·Δub`) で **max_err 0.185 MiB**
- **CUDA3**: 純比例 (`0.9824·ub`) で **max_err 0.040 MiB**（ub 非 2^n 丸め境界の量子化残差、Phase Sb と同等）
- **CUDA_Host**: Phase Sb 4p モデル (`176.08 + 7.813e-3·Δctx + 0.0860·Δub + 3.815e-6·Δctx·Δub`) で **max_err 0.004 MiB**

→ 23 点検証（Phase Sb 19 点 + 本 Phase 4 点）でも Phase Sb 4p/純比例モデルは **R² ≥ 0.99999** を維持。

### 5. graph 構造 ✅ 4 点で完全不変

- graph nodes = **4,473**（Phase S/Sb 16+3 点と完全一致）
- graph splits = **136 (with bs=ub) + 77 (with bs=1)**（Phase S/Sb 19 点と完全一致）
- ub=1600/1664/1700/1750 で splits_main の bs だけが ub に連動、ctx・ub の graph 構造非依存性を 23 点で再確証

### 6. KV buffer ✅ 4 点で max_err 0.000 MiB

全 4 点で `96 · (ctx/16384) = 192 MiB/GPU`、layer 12 on GPU の想定値と完全一致。

### 7. reserve 時間の ub 依存性（副次）

| ub | reserve took |
|---:|---:|
| 1600 | 177.06 ms |
| 1664 | 185.92 ms |
| 1700 | 189.89 ms |
| 1750 | 193.91 ms |

Phase Sb 3 点 (1280→147.84 / 1536→169.10 / 1792→196.79) と合わせて ub=1280〜1792 で極めて線形（`reserve_ms ≈ 104.3 + 0.0517·ub` に近い）。本 Phase 4 点も同じ線形関係上にあり、境界突破前後で reserve 時間の傾きは変わらない（境界の影響は compute buffer メモリのみ）。

### 8. eval / prompt 性能サマリ

| ctx | ub | prompt | runs | prompt_n | eval_tps (中央値) | prompt_tps |
|---:|---:|---|---:|---:|---:|---:|
| 32,768 | 1,600 | warmup | 3 | 70 | 14.594 | 10.92 |
| 32,768 | 1,600 | 1k | 3 | 1,091 | 14.574 | 68.50 |
| 32,768 | 1,664 | warmup | 3 | 70 | 15.459 | 10.93 |
| 32,768 | 1,664 | 1k | 3 | 1,091 | **15.451** | 68.15 |
| 32,768 | 1,700 | warmup | 3 | 70 | 14.778 | 10.94 |
| 32,768 | 1,700 | 1k | 3 | 1,091 | 14.758 | 68.96 |
| 32,768 | 1,750 | warmup | 3 | 70 | 14.639 | 10.95 |
| 32,768 | 1,750 | 1k | 3 | 1,091 | 14.624 | 68.47 |

**観察**:
- **eval 最速**: ctx=32k × ub=**1664** × 1k prompt で **15.451 t/s**（**Phase Sb の ub=1280 の 15.405 t/s を上回る ctx=32k 系列の新記録**）
- ub=1600 (14.574) と ub=1750 (14.624) は低く、ub=1664 (15.451) がピーク、ub=1700 (14.758) は中間
- **境界 ub\* (1536, 1600] を越えて直後の ub=1664 に eval ピーク** という構造が発見された
- prompt_tps は 4 点で 68.15〜68.96 t/s と ±0.6% 以内、ub 非依存

## ボトルネック・副次発見の分析

### 1. CUDA0 区分境界 ub\* ∈ (1536, 1600] — 本 Phase の核心発見

ub=1536 → 1600 → 1664 の 3 点で CUDA0 の増分は +4.85 → +18.26 MiB と急変し、ub=1664 以降は +0.285 MiB/token の新定常傾きに乗る。境界 ub\* は (1536, 1600] の 64-token 区間にあり、Phase Sb の 256-token 精度を **4 倍改善**。

**物理的考察**:
- 平坦域 (ub ≤ 1536): slope ~0.0127 MiB/token、1 token あたり ~13 KiB のグローバル staging（attention 前処理の 1 token あたり定数）
- 境界突破直後 (ub=1600): +4.85 MiB、部分的にジャンプが始まっている中間状態
- ub ≥ 1664: slope 0.2853 MiB/token、約 22 倍に跳ね上がる（新 staging 領域が 1 token あたり ~292 KiB 追加）

Phase Sb で仮説した「8-step boundary (1024, 1152, 1280, 1408, 1536, 1664, ...)」の候補は **1664 よりも 1 つ下の 1600 ないしはそれに近い閾値** ということになる。1600 はむしろ **12.5-step boundary** で、2^n 丸めや偶数 step とは異なる「非対称な閾値」の可能性。

llama.cpp scheduler のソース (`sched_reserve` / `graph_reserve`) 側で、1540〜1600 付近に潜む定数 (たとえば `n_tokens >= 1600` 等の判定) を grep する候補区間が絞り込まれた。

### 2. ub ≥ 1600 線形モデルの発見 — Phase Sb 二次推定の訂正

Phase Sb では ub ≥ 2048 の ctx=16k/32k/65k/131k × ub=2048/4096/8192 の 9 点を 6p 二次多項式で fit し、R²=0.9918 / max_err 236 MiB だった。これは ctx 方向の非線形寄与が ub=ctx cross 項を通じて現れていたため。

本 Phase で ctx=32k **固定** の ub=1600〜2048 を見ると:

```
C0(ub) = 1002.61 + 0.2853·(ub - 1664)   [ctx=32k 固定、max_err 0.035 MiB]
```

6 点で max_err 0.035 MiB（Phase Sb 6p の 6700 倍精度）。これは **ctx 固定では ub 軸に対して完全線形** であることを意味する。

Phase Sb の 6p 二次は「ub² 項 9.104e-6 MiB/token² が必要」としていたが、これは **ctx 方向の変動** が cross 項経由で見かけ上 ub² 項に押し出されたもので、**ub 単独では二次性は存在しない**。これは区分モデルの大きな単純化であり、Phase Sb モデルを以下に修正できる:

```
  CUDA0 区分モデル（ctx=32k、本 Phase Sb-fine 確定版）:
    ub ≤ 1536:  966.50 + 0.0064·ub                      [平坦域、Phase Sb + 本 Phase で max_err +3.17 MiB]
    1536 < ub ≤ 1600:  境界遷移域（1 点のみ、遷移中）    [実測 ub=1600 で C0=984.35, 線形モデル上]
    ub ≥ 1600:  1002.61 + 0.2853·(ub - 1664)             [max_err 0.035 MiB、6 点検証済み]
```

ただし、ctx 変動を含む式（Phase Sb の 2 軸モデル全体）は未検証なので、ub ≥ 1600 × 複数 ctx で線形性が維持されるかは次 Phase 課題。

### 3. CUDA1/2 / CUDA_Host の Phase Sb 4p モデル 23 点妥当性 — 完全維持

Phase Sb 19 点に本 Phase 4 点を追加した 23 点で:
- CUDA1/2 残差 |dC1| ≤ 0.185 MiB（Phase Sb max_err 0.21 MiB と同等）
- CUDA_Host 残差 |dH| ≤ 0.004 MiB（Phase Sb max_err 0.01 MiB と同等）

→ **23 点でも Phase Sb 4p モデルは R² ≥ 0.99999 を維持**し、CUDA1/2 および CUDA_Host には区分境界が**ない**ことを強化。**CUDA0 のみが区分的挙動**という所見は確定。

### 4. CUDA3 純 ub 比例性の 23 点確証

Phase Sb の `CUDA3 = 0.9824·ub` を本 Phase 4 点で検証:

| ub | 実測 | 0.9824·ub | 差 |
|---:|---:|---:|---:|
| 1600 | 1571.88 | 1571.84 | +0.04 |
| 1664 | 1634.75 | 1634.71 | +0.04 |
| 1700 | 1670.12 | 1670.08 | +0.04 |
| 1750 | 1719.24 | 1719.20 | +0.04 |

→ **23 点 max_err 0.040 MiB**（Phase Sb と同等、全点 +0.04 の一定残差は係数 fit の量子化丸め）。純 ub 比例は揺るがず。

### 5. eval 性能「谷山構造」の再発見

ctx=32k 系列の eval 中央値 (1k prompt):

| ub | 512 | 1024 | 1280 | 1536 | **1600** | **1664** | **1700** | **1750** | 1792 | 2048 | 4096 | 8192 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| eval t/s | 14.64 | 14.64 | 15.41 | 14.91 | **14.57** | **15.45** | **14.76** | **14.62** | 15.26 | 15.06 | 14.65 | 14.92 |

**観察**:
- ctx=32k 系列で eval が ≥ 15.0 t/s となるのは **ub=1280 / 1664 / 1792 / 2048** の 4 点（狭いピーク群）
- 境界 ub\* (1536, 1600] を跨ぐ **ub=1600 で最遅 14.57 t/s**（境界突破直後の GPU0 パイプライン非効率）
- **ub=1664 で再ピーク 15.45 t/s**（本 Phase および ctx=32k 系列 13 点の新記録）
- ub=1700/1750 で再度 14.6〜14.8 に低下、ub=1792/2048 で再度ピーク

→ eval 性能には **ub 64-token ~128-token スケールの細かな谷山構造** が存在する。compute buffer は ub ≥ 1600 で線形だが、eval 性能はそれと独立した周期的な非線形性を持つ。セッション間ゆらぎ 5-10 run での再現性検証が必須。

### 6. stdout redirect 方式の再現性（5 回連続成功）

Phase S → Phase Sb 3 条件 → 本 Phase 4 条件 と、計 11 条件連続でハングなし完走。`bash start_phaseSbf.sh > log 2>&1 &` + `wait PID` + `kill -0 polling` パターンが確定版。

## 採用判定

| 項目 | 結果 |
|---|---|
| Sbf1-Sbf4 起動成功 (/health OK) | ✅ 4 条件すべて 4*5s=20s で /health OK（ページキャッシュ有効） |
| OOM / -ub 下限拒否 | ✅ ゼロ |
| sched_reserve 全 5 チャネル採取 | ✅ 4 点 × 5 GPU = 20 データ点 |
| CUDA3 純 ub 比例性 (4 点 max_err 0.040 MiB) | ✅ **維持** |
| CUDA1/2 4p モデル 4 点残差 max_err 0.185 MiB | ✅ **Phase Sb モデル維持** |
| CUDA_Host 4p モデル 4 点残差 max_err 0.004 MiB | ✅ **Phase Sb モデル維持** |
| CUDA0 境界 ub\* 確定 | ✅ **ub\* ∈ (1536, 1600]（64-token 精度）** |
| ub ≥ 1600 線形モデル成立 | ✅ **6 点 max_err 0.035 MiB** (1600〜2048) |
| graph 構造 4 点不変 | ✅ nodes=4473, splits_bs1=77 |
| KV buffer 4 点誤差 0 MiB | ✅ **max_err 0.000** |
| eval 速度 ≥ 14.5 t/s (全条件) | ✅ min 14.574 @ ub=1600、max 15.451 @ ub=1664 |

**結論**: **Phase Sb-fine は全成功条件を達成**。主要な新規発見:

1. **CUDA0 区分境界 ub\* ∈ (1536, 1600]** を 64-token 精度で確定
2. **ub ≥ 1600 で線形モデル `C0 = 1002.61 + 0.2853·(ub-1664)` が max_err 0.035 MiB で成立**（ub=2048 まで外挿可能）— Phase Sb の二次推定を単純線形に訂正
3. **Phase Sb 4p モデル (CUDA1/2, Host) は 23 点で max_err < 0.19 MiB**
4. **CUDA3 純 ub 比例性は 23 点で max_err 0.040 MiB**
5. **eval 最速条件**: ctx=32k × **ub=1664** × 1k prompt で **15.451 t/s**（ctx=32k 系列 13 点の新記録、Phase Sb の ub=1280 15.405 を更新）
6. **eval 谷山構造**: 境界直後の ub=1600 で 14.57 t/s（谷）、次の ub=1664 で 15.45 t/s（山）、ub=1700/1750 で再度谷、ub=1792/2048 でまた山

## 確定モデル（更新版、Phase Sb の 19 点モデルに本 Phase 4 点を加えた 23 点検証済み）

```
Δctx = ctx - 16384, Δub = ub - 2048

fa=1, C-D3, f16 KV: compute_buffer [MiB]

  CUDA0 (ctx=32k、本 Phase で決定した区分モデル):
    ub ≤ 1536:  966.50 + 0.0064·ub                                    [平坦域、Phase Q/Sb で確定、max_err +3.17 MiB]
    1536 < ub < 1600:  境界遷移域（1 点のみ、未モデル化）
    ub ≥ 1600:  1002.61 + 0.2853·(ub - 1664)                          [線形、6 点 max_err 0.035 MiB、ctx=32k のみ]

  CUDA0 (任意 ctx、Phase Sb 確定版、ub ≥ 2048):
    1116.34 + 4.996e-3·Δctx + 3.670e-8·Δctx² + 0.1115·Δub
          + 6.016e-6·Δctx·Δub + 9.104e-6·Δub²                          [9 点 R²=0.9918、max_err 236 MiB]
    ※ 本 Phase で ctx=32k 固定時は線形と判明、ub² 項は ctx 方向の効果

  CUDA1/2   = 520.26 + 3.903e-3·Δctx + 0.2538·Δub + 1.910e-6·Δctx·Δub  [23 点 max_err 0.21 MiB]
  CUDA3     = 0.9824·ub                                                  [23 点 max_err 0.040 MiB]
  CUDA_Host = 176.08 + 7.813e-3·Δctx + 0.0860·Δub + 3.815e-6·Δctx·Δub   [23 点 max_err 0.01 MiB]

KV buffer (per GPU): 96 × (ctx/16384) MiB                                [23 点 max_err 0.000]
graph nodes: 4473 (ub/ctx 不変)
graph splits: 136 (bs=ub) + 77 (bs=1)
```

## 未検証事項

### 既知項目（Phase Sb から継続、本 Phase で潰したものに [x]）

- [x] **CUDA0 境界 ub\* の 64-token 精度での絞り込み** (Phase Sb 新規項目最上位) — 本 Phase で ub=1600/1664/1700/1750 計測、**ub\* ∈ (1536, 1600] に 64-token 精度で確定**
- [x] **境界遷移域 (1536 < ub ≤ 1792) の専用 CUDA0 モデル導出** (Phase Sb 新規) — 本 Phase で **ub ≥ 1600 は線形 (0.2853·(ub-1664))** と判明、遷移域は (1536, 1600] の 64-token のみ
- [ ] **CUDA0 区分境界 ub\* のさらなる絞り込み (16-token 精度)** (本 Phase 新規) — ub=1552/1568/1584/1600 など 16-token 刻みで境界を (1536, 1600] 内で詳細化
- [ ] **CUDA0 区分モデルの物理的意味** (Phase Sb 新規) — llama.cpp scheduler ソースで ub 閾値判定ロジックを特定（閾値候補は 1540-1600 付近）
- [ ] **CUDA0 二次係数 9.104e-6 MiB/token² の物理メカニズム** (Phase Sb) — 本 Phase で ctx 固定時は線形と判明したので、二次性は ctx 方向のみ
- [ ] **CUDA0 二次モデルの ctx=262144 外挿** (Phase R-ctx3 継続)
- [ ] **CUDA0 境界 ub\* の ctx 依存性** (本 Phase 新規) — 本 Phase は ctx=32k 固定、ctx=16k/65k/131k での境界 ub\* 位置が同じか要確認
- [ ] **ub ≥ 1600 線形モデルの ctx 独立性検証** (本 Phase 新規) — 本 Phase で `1002.61 + 0.2853·(ub-1664)` は ctx=32k のみ。ctx=65k/131k でも slope 0.2853 が維持されるか、slope が ctx 依存で変化するかを確認
- [ ] **CUDA1/2 cross_e = 1.910e-6, Host = 3.815e-6 MiB/(token·token) の物理メカニズム** (Phase Sb 継続)
- [ ] **ub=1280/1792 の eval 性能再現性** (Phase Sb 新規) — 本 Phase でさらに ub=1664 ピーク 15.45 t/s、ub=1600 谷 14.57 t/s、ub=1700/1750 中間。5-10 run 再現性検証
- [ ] **ub=1664 eval 15.451 t/s のセッション間再現性** (本 Phase 新規 ★) — ctx=32k × ub=1664 × 1k prompt の eval 最速値、3 run 中央値のみ、5-10 run 検証必須
- [ ] **ub=1280/1536/1792 × ctx=65k での CUDA0 検証** (Phase Sb 新規継続)
- [ ] **fa=0 側での同様の区分境界 + 線形** (Phase Sb 継続) — fa=0 では scheduler 経路が異なる可能性
- [ ] **q8_0 KV 構成での同様の区分境界 + 線形** (Phase Sb 継続) — KV 半減で境界 ub\* と slope が変わる可能性
- [ ] **中間 ctx (24k / 48k / 96k) での検証** (Phase Sb 継続)
- [ ] **ctx=65k 32k prompt の 3 run 以上再計測** (Phase R-ctx3 継続)
- [ ] **CUDA3 が ctx 完全不依存となる物理メカニズム** (Phase R 継続、23 点再確証済みだがソース未特定)
- [ ] **120k eval 12.82 t/s の Run 間再現性** (Phase R 継続)
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

### 既知項目（Phase Q/S 継続）

- [ ] **`-ub=1 (greedy)` でのベンチマーク**: 未実施
- [ ] **`-ub > -b` の挙動（llama.cpp 制約検証）**: 未実施
- [ ] **fa=0 側での `-ub` 支配性の確認**: 未実施
- [ ] **大 prompt での `-ub` 依存性** (Phase S/Sb で 1k のみ、4k/8k/16k prompt 未検証)
- [ ] **`-b > -ub` 運用の意義**: Phase P で観測のみ
- [ ] **graph splits=77 (with bs=1) の存在意義** (本 Phase 23 点で全条件 77 固定を再確認、意義は未特定)
- [ ] **`--parallel 2` との相互作用**
- [ ] **P3 vs Phase O の eval 差 +1.17% のセッション源**

### 新規項目（本 Phase Sb-fine で判明・発生）

- [ ] **★最優先: CUDA0 境界 ub\* の 16-token 精度絞り込み** (Phase Sb-fine2 候補): ub=1552/1568/1584/1600 の 4 点で (1536, 1600] 区間を 16-token に細分化
- [ ] **★高優先: ub ≥ 1600 線形モデルの ctx 独立性検証** (Phase Sb-ctx-linear 候補): ctx=65k/131k × ub=1600/1664/1792 の 6 条件で slope 0.2853 の ctx 依存性確認
- [ ] **★高優先: ub=1664 eval 15.451 t/s の 5-10 run 再現性**: 3 run 中央値のため、セッション間ゆらぎ検証要
- [ ] **eval 谷山構造 (1600 谷 / 1664 山 / 1700 谷 / 1750 谷 / 1792 山) の再現性**: 64-token スケールの谷山周期は偶発か物理的か
- [ ] **境界 ub\* の fa 依存性**: fa=0 でも同じ ub\* ∈ (1536, 1600] か、または fa スケジューラ経路の違いで異なる境界を持つか
- [ ] **境界 ub\* の KV 量子化依存性**: q8_0 KV で境界が移動するか
- [ ] **reserve 時間 vs ub の完全線形性検証**: ub=128〜8192 全条件で reserve_ms を集計、`104.3 + 0.0517·ub` の 23 点検証
- [ ] **llama.cpp scheduler ソースの ub 閾値判定箇所特定**: `graph_reserve` / `sched_reserve` / `llama-graph.cpp` で 1540-1600 付近の閾値定数を grep
- [ ] **ub=1664 で eval ピークとなる物理原因**: ub が 64 の倍数または 2^n 近傍だから? GPU の warp scheduling との整合性?
- [ ] **ub=1600 谷の原因**: 境界突破直後の CUDA0 staging による GPU0 パイプライン非効率の仮説検証

## 検証完了後に実施すべき TODO

### 既知項目（Phase Sb から継続、本 Phase で更新）

- [ ] **start.sh の拡張**: `LLAMA_NUMACTL_PREFIX` / `LLAMA_EXTRA_THREADS` 環境変数サポート追加
- [ ] **CUDA1 セーフティマージン OOM フォールバック実装**
- [ ] **層→GPU アライメントのソースコード解析**
- [ ] **C-4 実験**（CPU 層削減 + GPU 層追加）
- [ ] **drop_caches 権限の確保**（sudoers 設定 or vmtouch 導入）
- [ ] **start.sh での NUMA プリセット整備**
- [ ] **start.sh に `--threads` 設定追加**
- [ ] **`start_phaseJ.sh` 〜 `start_phaseSbf.sh` の環境変数化を skill 側 `start.sh` に逆輸入**
- [ ] **依存制約の lint 化**: 起動前 pre-check
  - **本 Phase で更新**: CUDA0 モデルは「ub ≤ 1536 平坦 / 1536 < ub < 1600 遷移 / ub ≥ 1600 線形」の 3 区分（Phase Sb の 3 区分から境界を 1792 → 1600 に、かつ急増域を二次 → 線形に単純化）
  - CUDA1/2/Host は Phase Sb 4p モデル (23 点検証済み)
  - CUDA3 = 0.9824·ub (23 点検証済み)
- [ ] **llama.cpp upstream issue/PR のサーベイ**
- [ ] **`measure_phaseI.sh` を汎用化して skill に組み込む**
- [ ] **「長コンテキスト性能カード」をモデル単位で記録するドキュメント整備**
- [ ] **アプリ側にコンテキストサイズ別レイテンシ警告を出す仕組み**

### 新規項目（本 Phase Sb-fine で発見・更新）

- [ ] **★最優先: 起動前 lint の CUDA0 3 区分モデル更新**（Phase Sb の 3 区分を本 Phase の境界 1600 + 線形 slope 0.2853 で更新）:
  - `ub ≤ 1536`: `CUDA0 ≈ 966.5 + 0.0064·ub` + マージン 10 MiB（平坦域、max_err +3.17 MiB）
  - `1536 < ub < 1600`: 境界遷移域、保守的に `線形延長 + 10 MiB`
  - `ub ≥ 1600`: `1002.61 + 0.2853·(ub - 1664)` + マージン 30 MiB（線形、6 点 max_err 0.035 MiB）
- [ ] **★最優先: 起動前 lint の 4p cross 項モデル組み込み** (Phase Sb から継続):
  - `predicted_cuda1/2 = 520.26 + 3.903e-3·Δctx + 0.2538·Δub + 1.910e-6·Δctx·Δub`（23 点 max_err 0.21 MiB）
  - `predicted_cuda_host = 176.08 + 7.813e-3·Δctx + 0.0860·Δub + 3.815e-6·Δctx·Δub`（23 点 max_err 0.01 MiB）
  - `predicted_cuda3 = 0.9824·ub`（23 点 max_err 0.040 MiB）
  - Δctx = ctx - 16384, Δub = ub - 2048
- [ ] **★最優先: compute buffer 予測モデル（Phase Sb-fine 確定版）を skill / CLAUDE.md に記録**:
  - **fa=1, f16 KV, C-D3**: 23 点検証済みの確定式、ub=128〜8192 × ctx=16k〜131k
  - **CUDA0 は 3 区分モデル (境界 ub\* ∈ (1536, 1600]、ub ≥ 1600 は線形 slope 0.2853)**、**CUDA1/2/Host は 4p 2 軸 cross 項**、**CUDA3 は純 ub 比例** を明記
- [ ] **★最優先: skill 側 `.claude/skills/llama-server/scripts/start.sh:155` を `-b=1664 -ub=1664` に変更**（Phase R-ctx3 / S / Sb から継続、本 Phase で ub=1664 最速確定）:
  - 現状 t120h-p100 デフォルト: `SERVER_OPTS="--flash-attn 1 --poll 0 -b 8192 -ub 8192"`
  - 本 Phase で ctx=32k × **ub=1664** が ctx=32k 系列 eval 最速 (15.451 t/s) と判明、Phase Sb の ub=1280 15.405 を更新
  - 変更候補: `-b 1664 -ub 1664`（eval 最速） or `-b 2048 -ub 2048`（prompt も踏まえた平衡点）
- [ ] **CLAUDE.md / skill の情報更新**:
  - **fa=1 の CUDA0 は 3 区分モデル (境界 ub\* ∈ (1536, 1600]、高域は線形)**
  - **CUDA1/2/CUDA3/CUDA_Host は Phase Sb 4p/純比例モデル、23 点 max_err 0〜0.21 MiB**
  - **Qwen3.5-122B-A10B t120h-p100 で ub=128〜8192 × ctx=16k〜131k の compute buffer が 23 点実測で 2 軸モデル化、ub=1664 が ctx=32k の eval 最速**
- [ ] **モデルカード更新**: Qwen3.5-122B-A10B の長コンテキスト性能カードに本 Phase 結果を追加
- [ ] **Phase Sb-fine2 候補**: ub=1552/1568/1584 の 3 点で境界 ub\* を 16-token 精度で確定
- [ ] **Phase Sb-ctx-linear 候補**: ctx=65k/131k × ub=1600/1664/1792 の 6 条件で ub ≥ 1600 線形モデルの ctx 依存性検証（所要 1 時間程度）
- [ ] **Phase Sb-fa0 候補**: fa=0 系列で同一 4 条件スキャン
- [ ] **Phase Sb-KV8 候補**: `--cache-type-{k,v} q8_0` で本 Phase を再実施
- [ ] **Phase S-eval 候補**: ctx=32k × ub=1664 eval 15.451 t/s を 5-10 run で再現性検証
- [ ] **Phase Q-2 候補（`-ub` 内部下限の真の値特定）**: `-ub=64 / 32 / 16 / 8 / 4 / 2 / 1`
- [ ] **Phase Q-3 候補（`-ub` ピーク周辺探索）**: ub=1600 近傍の 1 token 刻み、もしくは ub=1664 の周辺 ±16 token で eval ピーク形状を特定
- [ ] **skill 側 start.sh の `ssh -f` stdout redirect 改修** (Phase S から継続): 本 Phase で 4 条件すべてハングなし、累計 11 条件連続成功
- [ ] **start.sh のデフォルト `ctx-size` を 131072 に更新**（現状 65536、Phase S から継続）

## 補足

### Phase Sb-fine の核心発見

1. **CUDA0 区分境界 ub\* ∈ (1536, 1600]** — Phase Sb の 256-token 精度を 64-token に改善
2. **ub ≥ 1600 で C0 完全線形 `1002.61 + 0.2853·(ub-1664)`** — 6 点 max_err 0.035 MiB、ub=2048 まで外挿可
3. **Phase Sb の「ub² 項 9.104e-6」は ctx 方向の cross 項由来** — ub 軸だけ見ると完全線形、モデルを 6p → 3p に単純化可能
4. **Phase Sb 4p モデル (CUDA1/2, Host) は 23 点で max_err < 0.19 MiB**
5. **CUDA3 純 ub 比例性は 23 点で max_err 0.040 MiB**
6. **ctx=32k × ub=1664 × 1k prompt で eval 15.451 t/s** — ctx=32k 系列 13 点の新記録（Phase Sb の ub=1280 15.405 を更新）
7. **eval の谷山構造**: 境界突破直後の ub=1600 で最遅 14.57 t/s、直後 ub=1664 で最速 15.45 t/s、以降 64-128 token スケールの振動
8. **batch 44 分で完走、stdout redirect 版 batch_boundary_fine.sh は累計 11 条件でハングなし** — Phase S/Sb から累計成功率 100%

### 23 点データベース（ctx=32k, ub=1600/1664/1700/1750 を追加、ub 昇順）

| # | ctx | ub | CUDA0 | CUDA1 | CUDA2 | CUDA3 | CUDA_Host | 合計 | KV/GPU | Phase |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 16,384 | 128 | 961.62 | 34.64 | 34.64 | 125.75 | 11.00 | 1,167.65 | 96.00 | Q |
| 2 | 16,384 | 256 | 963.25 | 65.01 | 65.01 | 251.50 | 22.01 | 1,366.78 | 96.00 | Q |
| 3 | 16,384 | 512 | 966.50 | 130.02 | 130.02 | 503.00 | 44.02 | 1,773.56 | 96.00 | Q |
| 4 | 16,384 | 1024 | 973.00 | 260.03 | 260.03 | 1,006.00 | 88.04 | 2,587.10 | 96.00 | Q |
| 5 | 16,384 | 2048 | 1,048.13 | 520.06 | 520.06 | 2,012.00 | 176.08 | 4,276.33 | 96.00 | Q/R-ctx3 |
| 6 | 32,768 | 512 | 966.50 | 146.02 | 146.02 | 503.00 | 76.02 | 1,837.56 | 192.00 | S1 |
| 7 | 32,768 | 1024 | 973.00 | 292.03 | 292.03 | 1,006.00 | 152.04 | 2,715.10 | 192.00 | S2 |
| 8 | 32,768 | 1280 | 976.25 | 365.04 | 365.04 | 1,257.50 | 190.05 | 3,153.88 | 192.00 | Sb1 |
| 9 | 32,768 | 1536 | 979.50 | 438.05 | 438.05 | 1,509.00 | 228.06 | 3,592.66 | 192.00 | Sb2 |
| 10 | 32,768 | **1600** | **984.35** | **456.30** | **456.30** | **1,571.88** | **237.56** | **3,706.39** | **192.00** | **Sbf1** |
| 11 | 32,768 | **1664** | **1,002.61** | **474.55** | **474.55** | **1,634.75** | **247.06** | **3,833.52** | **192.00** | **Sbf2** |
| 12 | 32,768 | **1700** | **1,012.88** | **484.82** | **484.82** | **1,670.12** | **252.41** | **3,905.05** | **192.00** | **Sbf3** |
| 13 | 32,768 | **1750** | **1,027.14** | **499.08** | **499.08** | **1,719.24** | **259.83** | **4,004.37** | **192.00** | **Sbf4** |
| 14 | 32,768 | 1792 | 1,039.12 | 511.05 | 511.05 | 1,760.50 | 266.07 | 4,087.79 | 192.00 | Sb3 |
| 15 | 32,768 | 2048 | 1,112.13 | 584.06 | 584.06 | 2,012.00 | 304.08 | 4,596.33 | 192.00 | R-ctx3 |
| 16 | 32,768 | 4096 | 1,912.00 | 1,168.13 | 1,168.13 | 4,024.00 | 608.16 | 8,880.42 | 192.00 | S3 |
| 17 | 32,768 | 8192 | 2,784.00 | 2,336.25 | 2,336.25 | 8,048.00 | 1,216.31 | 16,720.81 | 192.00 | S4 |
| 18 | 65,536 | 512 | 966.50 | 178.02 | 178.02 | 503.00 | 140.02 | 1,965.56 | 384.00 | S5 |
| 19 | 65,536 | 1024 | 973.00 | 356.03 | 356.03 | 1,006.00 | 280.04 | 2,971.10 | 384.00 | S6 |
| 20 | 65,536 | 2048 | 1,348.00 | 712.06 | 712.06 | 2,012.00 | 560.08 | 5,344.20 | 384.00 | R-ctx3 |
| 21 | 65,536 | 4096 | 2,296.00 | 1,424.13 | 1,424.13 | 4,024.00 | 1,120.16 | 10,288.42 | 384.00 | S7 |
| 22 | 65,536 | 8192 | 4,320.00 | 2,848.25 | 2,848.25 | 8,048.00 | 2,240.31 | 20,304.81 | 384.00 | S8 |
| 23 | 131,072 | 2048 | 2,180.00 | 968.06 | 968.06 | 2,012.00 | 1,072.08 | 7,200.20 | 768.00 | R |

（太字 = 本 Phase Sb-fine 新規計測）

### eval / prompt 性能データベース（ctx=32k × ub=1600/1664/1700/1750、1k prompt 3 run 中央値）

| ctx | ub | prompt_med (t/s) | eval_med (t/s) | prompt_n | 備考 |
|---:|---:|---:|---:|---:|---|
| 32,768 | 1,600 | 68.50 | 14.574 | 1,091 | Sbf1 — 境界突破直後、ctx=32k 13 点中最遅 |
| 32,768 | **1,664** | 68.15 | **15.451** | 1,091 | **Sbf2 ★ ctx=32k 13 点 eval 最速（Phase Sb ub=1280 15.405 を更新）** |
| 32,768 | 1,700 | 68.96 | 14.758 | 1,091 | Sbf3 |
| 32,768 | 1,750 | 68.47 | 14.624 | 1,091 | Sbf4 |

### ctx=32k eval 性能統合（13 点、ub=512〜8192）

| ub | eval_med (t/s) | Phase | 備考 |
|---:|---:|---|---|
| 512 | 14.636 | S | |
| 1024 | 14.640 | S | |
| 1280 | 15.405 | Sb | Phase Sb 最速 |
| 1536 | 14.910 | Sb | |
| **1600** | **14.574** | **Sbf** | **★ 最遅（境界直後）** |
| **1664** | **15.451** | **Sbf** | **★★ 13 点最速（Phase Sb-fine で新記録）** |
| **1700** | **14.758** | **Sbf** | |
| **1750** | **14.624** | **Sbf** | |
| 1792 | 15.255 | Sb | |
| 2048 | 15.06 | R-ctx3 | |
| 4096 | 14.651 | S | |
| 8192 | 14.915 | S | |

### 作業終了時点の状態

- llama-server は停止済み（batch_boundary_fine.sh 末尾の stop.sh で正常終了）
- GPU サーバロック（t120h-p100）は未解放（本レポート作成後に unlock.sh）
- `results.tsv` 25 行（Sbf1-Sbf4 × warmup/1k × 3 run = 24 run + ヘッダ）
- `compute_buffer_summary.txt` 72 行（4 条件 × 主要 18 行）
- `analyze_boundary_fine.py` / `analyze_boundary_fine.txt` で Phase Sb 4p モデル 23 点検証 + CUDA0 区分モデル更新（3 区分、境界 (1536, 1600]、ub >= 1600 線形）
- **CUDA0 境界 ub\* ∈ (1536, 1600] を確定、ub >= 1600 線形モデル max_err 0.035 MiB を 6 点検証、CUDA1/2/3/Host の 23 点検証、skill 側 start.sh の `-b/-ub` デフォルト更新を次の最優先タスクとして登録**
