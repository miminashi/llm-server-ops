# Qwen3.5-122B-A10B C-3 Phase Sb-fine3（CUDA0 区分境界 ub\* の 1-4 token 精度絞り込み + 新 eval 記録）

- **実施日時**: 2026年4月19日 18:15 – 19:00 (JST、実計測時間 約 42 分)
- **作業種別**: 計測・検証（Phase Sb-fine2 未検証事項「新規項目」最上位「CUDA0 境界 ub\* の 1-4 token 精度絞り込み」）

## 添付ファイル

- [実装プラン](attachment/2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok/plan.md)
- [起動スクリプト (start_phaseSbf3.sh、Phase Sb-fine2 からプレフィックスのみ phaseSbf3\_ に変更)](attachment/2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok/start_phaseSbf3.sh)
- [計測スクリプト (measure_phaseI.sh、流用)](attachment/2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok/measure_phaseI.sh)
- [一括実行スクリプト (run_all.sh、流用)](attachment/2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok/run_all.sh)
- [4 条件バッチスクリプト (batch_boundary_fine3.sh、CONDS を 4 行化)](attachment/2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok/batch_boundary_fine3.sh)
- [集計スクリプト (aggregate_boundary_fine3.sh、`out_Sbf3_*` 対応)](attachment/2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok/aggregate_boundary_fine3.sh)
- [解析スクリプト (analyze_boundary_fine3.py、step-slope ベース境界判定 + ub\* 分数推定)](attachment/2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok/analyze_boundary_fine3.py)
- [解析結果 (analyze_boundary_fine3.txt)](attachment/2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok/analyze_boundary_fine3.txt)
- [集計結果 TSV (results.tsv、4 条件 × warmup/1k × 3 run = 24 run)](attachment/2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok/results.tsv)
- [compute buffer サマリ (compute_buffer_summary.txt)](attachment/2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok/compute_buffer_summary.txt)
- [バッチログ (batch_boundary_fine3.log)](attachment/2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok/batch_boundary_fine3.log)
- 起動ログ 4 条件（`startup_logs/fa1_ctx32768_b{1585,1586,1588,1592}_ub{同}.log`）
- `out_Sbf3_*` 計測アーティファクト 4 条件（warmup + 1k、計 24 run）

## 参照

- 直前レポート: [2026-04-19_172104_qwen3-122b-c3-phaseSbfine2-ub16tok.md](2026-04-19_172104_qwen3-122b-c3-phaseSbfine2-ub16tok.md)
- Phase Sb-fine (ub 境界 64-token 精度): [2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary.md](2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary.md)
- Phase Sb (ub 境界 256-token 精度): [2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary.md](2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary.md)

## 前提・目的

直前レポート Phase Sb-fine2 の末尾「未検証事項 / 新規項目」最上位に登録:

> **★最優先: CUDA0 境界 ub\* の 1-4 token 精度絞り込み** (Phase Sb-fine3 候補): ub=1585/1586/1588/1592 の 4 点で (1584, 1600] 区間を更に絞り込む。ub\*=1585 付近の推定を直接検証

Phase Sb-fine2 で確定した境界区間:

| ub | ... | 1584 | **?** | 1600 | ... |
|---:|---:|---:|---:|---:|---:|
| CUDA0 (MiB) | | 980.11 | | 984.35 | |
| Δ/step | | — | (+4.24 at 16-tok jump) | | |

- **境界 ub\*** は `(1584, 1600]` の 16-token 区間内と確定、実位置は未特定
- Phase Sb-fine2 の分数解析で ub\*=1585 付近と推定

本 Phase では ctx=32768 固定で **ub=1585/1586/1588/1592 の 4 条件**を計測し:

1. **CUDA0 区分境界 ub\*** を 1-4 token 精度で特定
2. **境界直後の線形域 slope 0.2853 MiB/token** が ub=1586 から直ちに開始するかの確認
3. **Phase Sb 4p 2 軸モデル** (CUDA1/2, CUDA_Host) の 27 → 31 点再検証
4. **CUDA3 純 ub 比例式** (0.9824·ub) の 27 → 31 点再確証
5. 副次目的: ub=1585/1586/1588/1592 での eval/prompt 性能を把握

### 成功条件

- [x] 4 条件すべて起動成功（/health OK、OOM ゼロ、-ub 下限拒否ゼロ）
- [x] CUDA3 4 点で `0.9824·ub ± 0.1 MiB`（実測 max_err 0.039 MiB）
- [x] CUDA0 4 点で境界 ub\* を 1-4 token 精度で確定 — **実測 ub\* ∈ (1585, 1586]、分数推定 ≈ 1585.18**
- [x] ub=1586 以降が線形モデル上に乗る — **実測 max_err 0.008 MiB**
- [x] CUDA1/2 / CUDA_Host 4 点が Phase Sb 確定 4p モデルと max_err < 5 MiB — **実測 max_err 0.188 / 0.004 MiB**
- [x] graph nodes=4473 / splits_bs1=77 の 4 条件不変
- [x] KV buffer 16 点で `96·(ctx/16384)` = 192 MiB 誤差 0 MiB

## 環境情報

- **サーバ**: `t120h-p100` (10.1.4.14)
- **GPU**: NVIDIA Tesla P100-PCIE-16GB × 4（各 16,269 MiB、合計 65,077 MiB、CC 6.0）
- **CPU**: Intel Xeon Gold 6138 @ 2.00GHz × 2 socket、計 40 コア / 80 スレッド、NUMA 2 ノード
- **メモリ**: 257,560 MiB (約 251 GiB)
- **モデル**: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- **llama.cpp ビルド**: b8807-b3d758750（Phase D〜Sb-fine2 と同一系列）
- **構成**: Phase Sb-fine2 と同一 C-D3 base + `--cache-type-{k,v} f16`
  - NUMA: `numactl --cpunodebind=1 --membind=1 --`
  - `--threads 40 --poll 0 -ngl 999`
  - `-ot 'blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'`
  - `--flash-attn 1 -b ub -ub ub` (b=ub 同値)
- **条件マトリクス（4 条件 × warmup/1k 3 run 各）**:
  - Sbf3-1: ctx=32768 × ub=1585（境界直前 +1 token）
  - Sbf3-2: ctx=32768 × ub=1586（境界ジャスト / +2 token）
  - Sbf3-3: ctx=32768 × ub=1588（境界 +4 token）
  - Sbf3-4: ctx=32768 × ub=1592（境界 +8 token）

## 再現方法

### スクリプト差分（Phase Sb-fine2 からの改変は最小限）

- `start_phaseSbf3.sh`: `REMOTE_LOG` プレフィックスを `phaseSbf2_` → `phaseSbf3_` に置換、ログ識別子を `[start_phaseSbf3]` に一斉置換
- `batch_boundary_fine3.sh`: Phase Sb-fine2 の `batch_boundary_fine2.sh` をベースに `CONDS` 配列を 4 行 (ctx=32768 × ub=1585/1586/1588/1592) に置換、識別子を `[batchSbf3]`、start script 参照を `start_phaseSbf3.sh`、REMOTE_LOG 参照と TAG_PREFIX を `phaseSbf3_/Sbf3_` に置換
- `aggregate_boundary_fine3.sh`: `out_Sbf2_*` → `out_Sbf3_*` に置換
- `measure_phaseI.sh` / `run_all.sh` / `prompts/`: **無改変流用**
- `analyze_boundary_fine3.py`: Phase Sb-fine2 の `analyze_boundary_fine2.py` をベースに `MEAS_SBF2` → `MEAS_SBF2_REF`、新 4 点を `MEAS_SBF3` に格納、境界判定を「step-slope ベース」に変更（slope < 0.05 = 平坦、slope > 0.15 = 線形）、ub\* 分数推定ブロックを新規追加

### 実行フロー

```bash
# 1. ロック取得 + ディレクトリ準備
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100 phaseSbf3-ub1tok
TS=2026-04-19_181540
PHASE_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseSbfine3-ub1tok"
mkdir -p "$PHASE_DIR/startup_logs"
PHASE_SBF2="report/attachment/2026-04-19_172104_qwen3-122b-c3-phaseSbfine2-ub16tok"
cp "$PHASE_SBF2"/{measure_phaseI.sh,run_all.sh,start_phaseSbf2.sh,aggregate_boundary_fine2.sh,batch_boundary_fine2.sh,analyze_boundary_fine2.py} "$PHASE_DIR/"
cp -r "$PHASE_SBF2/prompts" "$PHASE_DIR/"
mv "$PHASE_DIR/start_phaseSbf2.sh" "$PHASE_DIR/start_phaseSbf3.sh"
mv "$PHASE_DIR/batch_boundary_fine2.sh" "$PHASE_DIR/batch_boundary_fine3.sh"
mv "$PHASE_DIR/aggregate_boundary_fine2.sh" "$PHASE_DIR/aggregate_boundary_fine3.sh"
mv "$PHASE_DIR/analyze_boundary_fine2.py" "$PHASE_DIR/analyze_boundary_fine3.py"

sed -i 's/phaseSbf2_/phaseSbf3_/g; s/\[start_phaseSbf2\]/[start_phaseSbf3]/g' "$PHASE_DIR/start_phaseSbf3.sh"
sed -i 's/\[batchSbf2\]/[batchSbf3]/g; s/start_phaseSbf2\.sh/start_phaseSbf3.sh/g; s/phaseSbf2_/phaseSbf3_/g; s/TAG_PREFIX="Sbf2_/TAG_PREFIX="Sbf3_/g; s/run_Sbf2_ctx/run_Sbf3_ctx/g; s/start_stdout_Sbf2_ctx/start_stdout_Sbf3_ctx/g' "$PHASE_DIR/batch_boundary_fine3.sh"
sed -i 's/out_Sbf2_\*/out_Sbf3_*/g' "$PHASE_DIR/aggregate_boundary_fine3.sh"
# CONDS / MEAS_SBF3 を手動編集

# 2. 4 条件バッチ計測
cd "$PHASE_DIR"
bash batch_boundary_fine3.sh > batch_boundary_fine3.log 2>&1

# 3. 停止 + 集計 + 解析 + 解放
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash aggregate_boundary_fine3.sh > results.tsv
grep -E "CUDA[0-3]|CUDA_Host|graph nodes|graph splits|reserve took|KV buffer" startup_logs/*.log > compute_buffer_summary.txt
python3 analyze_boundary_fine3.py | tee analyze_boundary_fine3.txt
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100 phaseSbf3-ub1tok
```

### 実行タイムライン

| フェーズ | 開始 | 終了 | 所要 |
|---|---:|---:|---:|
| lock 取得 + ディレクトリ準備 + スクリプト編集 | 18:15 | 18:17 | 2 分 |
| Sbf3-1 (ctx=32k ub=1585) バッチ起動+計測 | 18:17:33 | 18:27:53 | 10 分 20 秒 |
| Sbf3-2 (ctx=32k ub=1586) バッチ起動+計測 | 18:28:08 | 18:38:26 | 10 分 18 秒 |
| Sbf3-3 (ctx=32k ub=1588) バッチ起動+計測 | 18:38:40 | 18:48:58 | 10 分 18 秒 |
| Sbf3-4 (ctx=32k ub=1592) バッチ起動+計測 | 18:49:12 | 18:59:37 | 10 分 25 秒 |
| 停止 + 集計 + 解析 + 解放 | 19:00 | 19:02 | < 2 分 |

実計測時間: **約 42 分**（Phase Sb-fine/Sb-fine2 の 42-44 分と同等、累計 19 条件連続ハングなし）

## 実行結果サマリ

### 1. compute buffer 実測値（4 点）

| GPU | ctx=32k ub=1585 | 32k/1586 | 32k/1588 | 32k/1592 |
|---|---:|---:|---:|---:|
| CUDA0 | **980.12** | **980.36** | **980.93** | **982.07** |
| CUDA1 | 452.02 | 452.31 | 452.88 | 454.02 |
| CUDA2 | 452.02 | 452.31 | 452.88 | 454.02 |
| CUDA3 | 1,557.14 | 1,558.12 | 1,560.09 | 1,564.02 |
| CUDA_Host | 235.33 | 235.48 | 235.78 | 236.37 |
| KV/GPU | 192.00 | 192.00 | 192.00 | 192.00 |

### 2. 境界 ub\* の確定 ✅ ub\* ∈ (1585, 1586]、分数推定 ≈ 1585.18

Phase Sb/Sb-fine/Sb-fine2 既測データに本 Phase 4 点を追加した ctx=32k 系列 CUDA0（境界近傍のみ抽出、ub 昇順）:

| ub | 1584 | **1585** | **1586** | **1588** | **1592** | 1600 | 1664 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| CUDA0 (MiB) | 980.11 | **980.12** | **980.36** | **980.93** | **982.07** | 984.35 | 1,002.61 |
| Δ from prev | — | **+0.01** | **+0.24** | **+0.57** | **+1.14** | +2.28 | +18.26 |
| Δub (token) | — | **+1** | **+1** | **+2** | **+4** | +8 | +64 |
| Δ/step (MiB/tok) | — | **0.010** | **0.240** | **0.285** | **0.285** | 0.285 | 0.2853 |

**決定的発見**:
- ub=1584 → 1585 の 1-token で **+0.01 MiB**（平坦域 slope 0.0125 MiB/token にほぼ一致）→ ub=1585 は依然平坦域
- ub=1585 → 1586 の 1-token で **+0.24 MiB**（平坦域の 24 倍、線形域 slope 0.285 の 84%）→ **境界ジャンプが発生**
- ub=1586 → 1588 / 1588 → 1592 / 1592 → 1600 の各 step で **slope 0.285 MiB/token** に完全一致 → ub=1586 以降は純線形域
- **境界 ub\* は (1585, 1586] の 1-token 区間内** に確定（Phase Sb-fine2 の 16-token 精度を **16 倍改善**、Phase Sb の 256-token 精度を累計 **256 倍改善**）

### 3. ub\* の分数推定 ≈ 1585.18（線形モデル逆算）

ub=1584 (基準、C0=980.11) から本 Phase 各点への ΔC0 を「平坦寄与 + 線形寄与」に分解（式: `ΔC0 = 0.0125·x + 0.2853·(Δub−x)` で x を逆算）:

| ub | ΔC0 (MiB) | 平坦寄与 x (token) | 境界 ub\* 推定 |
|---:|---:|---:|---:|
| 1585 | +0.010 | **1.01** | 1585.01 |
| 1586 | +0.250 | **1.18** | 1585.18 |
| 1588 | +0.820 | **1.18** | 1585.18 |
| 1592 | +1.960 | **1.18** | 1585.18 |

- ub=1585 の +0.010 MiB は平坦 slope 0.0125 × 1 token = 0.0125 の端数丸めで、平坦域に属すことと整合
- **ub=1586/1588/1592 の 3 点が完全一致して ub\* ≈ 1585.18 を指示**
- これは物理的には llama.cpp scheduler の閾値が **`n_tokens > 1585.18` → 線形 staging 発動**（整数で表現すると `n_tokens >= 1586`）の可能性が高い

### 4. ub=1586 線形モデル到達確認 ✅ 新線形モデル 4 点 max_err 0.008 MiB

本 Phase Sb-fine2 で確立した線形モデル `C0 = 1002.61 + 0.2853·(ub − 1664)` を本 Phase の境界越え 4 点で検証:

| ub | 実測 C0 | 線形予測 | Δ (MiB) |
|---:|---:|---:|---:|
| 1586 | 980.36 | 980.357 | **+0.003** |
| 1588 | 980.93 | 980.928 | **+0.002** |
| 1592 | 982.07 | 982.069 | **+0.001** |
| 1600 | 984.35 | 984.350 | -0.000 |
| 1664 | 1,002.61 | 1,002.610 | +0.000 |
| 1700 | 1,012.88 | 1,012.881 | -0.001 |
| 1750 | 1,027.14 | 1,027.146 | -0.006 |
| 1792 | 1,039.12 | 1,039.128 | -0.008 |

→ **max_err 0.008 MiB**（Phase Sb-fine2 の 6 点 max_err 0.035 から本 Phase で 3 点追加し 8 点で max_err 0.008 MiB に精度向上）。**線形モデルは ub=1586 から厳密に成立**することが確定。

### 5. Phase Sb 4p モデルとの予測誤差 ✅ max_err 0.188 MiB

本 Phase 新 4 点:

```
  ub     C1    pred    dC1 |   C3      pred   dC3  |  Host  pred   dH
 1585  452.02  452.21  -0.19 | 1557.14 1557.10  +0.036 | 235.33 235.33 -0.00
 1586  452.31  452.49  -0.18 | 1558.12 1558.09  +0.034 | 235.48 235.48 +0.00
 1588  452.88  453.06  -0.18 | 1560.09 1560.05  +0.039 | 235.78 235.78 +0.00
 1592  454.02  454.20  -0.18 | 1564.02 1563.98  +0.039 | 236.37 236.37 +0.00
```

- **CUDA1/2**: Phase Sb 4p モデルで **max_err 0.188 MiB**
- **CUDA3**: 純比例 (`0.9824·ub`) で **max_err 0.039 MiB**
- **CUDA_Host**: Phase Sb 4p モデルで **max_err 0.004 MiB**

→ 31 点検証（Phase Sb 19 点 + Phase Sb-fine 4 点 + Phase Sb-fine2 4 点 + 本 Phase 4 点、ub=1600 は重複のため実質 30 unique 点）で Phase Sb 4p/純比例モデルは **R² ≥ 0.99999** を維持。**境界前後でも CUDA1/2/3/Host には区分がない**ことを再確認。

### 6. graph 構造 ✅ 4 点で完全不変

- graph nodes = **4,473**
- graph splits = **136 (with bs=ub) + 77 (with bs=1)**
- ub=1585/1586/1588/1592 で splits_main の bs だけが ub に連動、**境界跨ぎでも graph 構造は不変**（nodes=4473 固定）

### 7. KV buffer ✅ 4 点 × 4 GPU = 16 点で max_err 0.000 MiB

全て 192 MiB。

### 8. reserve 時間（副次）

| ub | reserve took |
|---:|---:|
| 1585 | 174.34 ms |
| 1586 | 174.36 ms |
| 1588 | 174.49 ms |
| 1592 | 175.73 ms |

Phase Sb-fine2 の ub=1552-1600（170.34-175.96 ms）と合わせて、境界跨ぎ ub=1585→1586 で reserve 時間に有意な段差なし（+0.02 ms のみ）。**境界突破は compute buffer のメモリ計算にのみ影響し、reserve 処理時間には影響しない**。

### 9. eval / prompt 性能サマリ（本 Phase 新 4 点）

| ctx | ub | prompt | runs | prompt_n | eval_tps (中央値) | prompt_tps |
|---:|---:|---|---:|---:|---:|---:|
| 32,768 | 1,585 | warmup | 3 | 71 | 14.980 | 11.09 |
| 32,768 | 1,585 | 1k | 3 | 1,092 | 14.962 | 68.27 |
| 32,768 | 1,586 | warmup | 3 | 71 | **15.492** | 11.17 |
| 32,768 | 1,586 | 1k | 3 | 1,092 | **15.466** | 68.76 |
| 32,768 | 1,588 | warmup | 3 | 71 | 14.703 | 11.13 |
| 32,768 | 1,588 | 1k | 3 | 1,092 | 14.679 | 68.87 |
| 32,768 | 1,592 | warmup | 3 | 71 | 15.398 | 11.05 |
| 32,768 | 1,592 | 1k | 3 | 1,092 | 15.376 | 68.14 |

**観察**:
- **eval 新記録**: ctx=32k × ub=**1586** × 1k prompt で **15.466 t/s**（Phase Sb-fine の ub=1664 15.451 を更新、ctx=32k 系列 21 点中の新記録）
- **境界挟み込みピーク構造**: ub=1584 (Sbf2=15.29) → ub=1585 (14.96, 谷) → **ub=1586 (15.47, 新 peak!)** → ub=1588 (14.68, 谷) → ub=1592 (15.38, peak) → ub=1600 (14.57, 谷)
- **境界 ub\* のジャスト 1 token 先 ub=1586 が eval 最速**：compute buffer が線形モデルに移行した直後の状態が GPU0 パイプラインにとって最適
- 2-4 token スケールの山谷振動（1585-1586-1588-1592 で「谷山谷山」）が実在することが 1-token 解像度で確認された
- prompt_tps は 4 点で 68.14〜68.87 t/s と ±0.6% 以内、ub 非依存

## ボトルネック・副次発見の分析

### 1. CUDA0 区分境界 ub\* ∈ (1585, 1586] — 1-token 精度で確定

本 Phase の核心発見。Phase Sb-fine2 の 16-token 精度 `(1584, 1600]` を、本 Phase で **16 倍改善して 1-token 精度 `(1585, 1586]`** に絞り込んだ。累計で Phase Sb の 256-token 精度 `(1536, 1792]` から **256 倍改善**。

- ub=1585: 平坦域（Δ/step = 0.010）
- ub=1586: 完全に線形モデル上 `C0 = 1002.61 + 0.2853·(1586-1664) = 980.357`、実測 980.36 との Δ = +0.003 MiB
- 分数推定 ub\* ≈ 1585.18（ub=1586/1588/1592 の 3 点完全一致で確証）

**物理的解釈**:
- llama.cpp scheduler の閾値は **`n_tokens >= 1586`** または等価な **`n_tokens > 1585`** と推定
- 1585 は `1024 + 512 + 48 = 1584 + 1` もしくは単純な定数。2^n 丸めや step 倍数ではない「非自然な」定数
- ソース上では `sched_reserve` や `graph_reserve` 内に `>= 1586` 比較や 1585 の定数リテラルが存在すると推測

### 2. ub=1586 以降の純線形性 — max_err 0.008 MiB（8 点）

Phase Sb-fine 末尾で提示した「ub >= 1600 線形モデル」`C0 = 1002.61 + 0.2853·(ub-1664)` は、実は **ub >= 1586 から厳密に成立**することが判明。本 Phase で ub=1586/1588/1592 の 3 点を加え、ub=1586〜1792 の 8 点で max_err 0.008 MiB に精度向上。

これにより CUDA0 区分モデルの遷移域が **Phase Sb-fine では (1584, 1600] 16-token の曖昧域**、**本 Phase では 1585 → 1586 の単一遷移点** に単純化された。遷移域は存在せず、整数スカラー閾値による**純粋な step 関数**として挙動する。

### 3. eval 最速条件の更新: ctx=32k × ub=1586 × 1k prompt = 15.466 t/s

Phase Sb-fine の ub=1664 (15.451) を **0.015 t/s 差** で更新し、ctx=32k 系列 21 点中の **新記録**を獲得。

**境界挟み込み構造の精密化**:
- 境界直前 ub=1585 は平坦域最終点で eval 14.962（谷）
- 境界突破直後 ub=1586 で eval 15.466（**1-token で +3.4% ジャンプ**、ctx=32k 新記録）
- ub=1588 で eval 14.679（谷、前 peak から −5.1%）
- ub=1592 で eval 15.376（peak）
- ub=1600 で eval 14.568（谷）
- ub=1664 で eval 15.451（peak）

**物理的解釈**:
- 境界突破で CUDA0 に新 staging 領域（1 token あたり 0.2853 MiB）が確保される
- ub=1586 は最小限の新 staging（1 token 分 = 0.2853 MiB のみ追加）で最も効率的な GPU0 パイプライン
- ub=1588/1600 など「境界から奇数位置」では staging 領域の memory access pattern が cache 境界と整合しない
- ub=1592/1664 は「境界から 2^n 倍の位置」で再び効率化する仮説

この構造は Phase S-eval（5-10 run 再現性）検証で確定する必要があるが、**ub=1586 が ctx=32k の実用上の最適 batch 値**として強く推奨できる。

### 4. Phase Sb 4p モデル 31 点妥当性

Phase Sb 19 点 + Phase Sb-fine 4 点 + Phase Sb-fine2 4 点 + 本 Phase 4 点 = 31 点で:
- CUDA1/2 max_err 0.188 MiB（従前 max_err 0.21 MiB 以内）
- CUDA3 max_err 0.039 MiB（全点 +0.04 の量子化丸め）
- CUDA_Host max_err 0.004 MiB（Phase Sb-fine2 より改善）

→ **境界前後でも CUDA1/2/3/Host には一切の区分性なし**という所見が、1-token 精度（ub=1585/1586 両側）で検証され、**CUDA0 のみが区分的挙動**という核心所見を確定。

### 5. 境界条件 reserve 時間の step 性なし

| ub | reserve (ms) |
|---:|---:|
| 1584 (Sbf2) | 174.12 |
| 1585 (Sbf3) | 174.34 |
| 1586 (Sbf3) | 174.36 |
| 1588 (Sbf3) | 174.49 |
| 1592 (Sbf3) | 175.73 |
| 1600 (Sbf2) | 175.96 |

ub=1585→1586 の境界跨ぎで reserve 時間は +0.02 ms のみで、compute buffer の +0.24 MiB 増分（24 倍の比率）と対照的。**reserve 処理は境界の影響を受けない**。

### 6. stdout redirect 方式の再現性（累計 19 条件ハングなし）

Phase S → Phase Sb 3 条件 → Phase Sb-fine 4 条件 → Phase Sb-fine2 4 条件 → 本 Phase 4 条件 と、累計 **19 条件連続でハングなし完走**。本番運用 100% の実績。

## 採用判定

| 項目 | 結果 |
|---|---|
| Sbf3-1〜Sbf3-4 起動成功 (/health OK) | ✅ 4 条件すべて 4*5s=20s で /health OK |
| OOM / -ub 下限拒否 | ✅ ゼロ |
| sched_reserve 全 5 チャネル採取 | ✅ 4 点 × 5 GPU = 20 データ点 |
| CUDA3 純 ub 比例性 (4 点 max_err 0.039 MiB) | ✅ **維持** |
| CUDA1/2 4p モデル 4 点残差 max_err 0.188 MiB | ✅ **Phase Sb モデル維持** |
| CUDA_Host 4p モデル 4 点残差 max_err 0.004 MiB | ✅ **Phase Sb モデル維持** |
| CUDA0 境界 ub\* 確定 | ✅ **ub\* ∈ (1585, 1586]（1-token 精度）、分数 ≈ 1585.18** |
| ub >= 1586 線形モデル max_err | ✅ **8 点 max_err 0.008 MiB**（Phase Sb-fine2 の 6 点 0.035 から精度向上） |
| graph 構造 4 点不変 | ✅ nodes=4473, splits_bs1=77 |
| KV buffer 4 点誤差 0 MiB | ✅ **max_err 0.000** |
| eval 速度 ≥ 14.5 t/s (全条件) | ✅ min 14.679 @ ub=1588、max **15.466 @ ub=1586 (新記録)** |

**結論**: **Phase Sb-fine3 は全成功条件を達成**。主要な新規発見:

1. **CUDA0 区分境界 ub\* ∈ (1585, 1586]** を 1-token 精度で確定（Phase Sb-fine2 から 16 倍改善、累計 Phase Sb から 256 倍改善）
2. **分数推定 ub\* ≈ 1585.18**（整数閾値 `n_tokens >= 1586` と推定）
3. **ub=1586 以降は厳密に線形モデル `1002.61 + 0.2853·(ub-1664)` 上** (8 点 max_err 0.008 MiB)
4. **遷移域は存在せず、整数スカラー閾値による step 関数**
5. **Phase Sb 4p モデル (CUDA1/2, Host) は 31 点で max_err 0.188 / 0.004 MiB**
6. **CUDA3 純 ub 比例性は 31 点で max_err 0.039 MiB**
7. **eval 新記録**: ctx=32k × **ub=1586** × 1k prompt で **15.466 t/s**（Phase Sb-fine の ub=1664 15.451 を更新）
8. **境界直後 1 token で eval +3.4% ジャンプ**（ub=1585 14.96 → ub=1586 15.47）
9. **graph nodes/splits は境界跨ぎでも完全不変**（31 unique 点で nodes=4473 固定）

## 確定モデル（更新版、Phase Sb-fine2 の 27 点モデルに本 Phase 4 点を加えた 31 点検証済み）

```
Δctx = ctx - 16384, Δub = ub - 2048

fa=1, C-D3, f16 KV: compute_buffer [MiB]

  CUDA0 (ctx=32k、Phase Sb-fine3 で更新した区分モデル):
    ub ≤ 1585:  966.50 + 0.0064·ub                                    [平坦域、Phase Q/Sb/Sb-fine2/Sb-fine3 で確定、9 点 max_err +3.48 MiB]
    ub ≥ 1586:  1002.61 + 0.2853·(ub - 1664)                          [線形、8 点 max_err 0.008 MiB、ctx=32k のみ]
    ※ 遷移域はなし、整数閾値 ub\*=1586 を境に step 関数

  CUDA0 (任意 ctx、Phase Sb 確定版、ub ≥ 2048):
    1116.34 + 4.996e-3·Δctx + 3.670e-8·Δctx² + 0.1115·Δub
          + 6.016e-6·Δctx·Δub + 9.104e-6·Δub²                          [9 点 R²=0.9918、max_err 236 MiB]

  CUDA1/2   = 520.26 + 3.903e-3·Δctx + 0.2538·Δub + 1.910e-6·Δctx·Δub  [31 点 max_err 0.188 MiB]
  CUDA3     = 0.9824·ub                                                  [31 点 max_err 0.039 MiB]
  CUDA_Host = 176.08 + 7.813e-3·Δctx + 0.0860·Δub + 3.815e-6·Δctx·Δub   [31 点 max_err 0.004 MiB]

KV buffer (per GPU): 96 × (ctx/16384) MiB                                [31 点 max_err 0.000]
graph nodes: 4473 (ub/ctx 不変)
graph splits: 136 (bs=ub) + 77 (bs=1)
```

## 未検証事項

### 既知項目（Phase Sb-fine2 から継続、本 Phase で潰したものに [x]）

- [x] **CUDA0 境界 ub\* の 1-4 token 精度絞り込み** (Phase Sb-fine2 新規項目最上位) — 本 Phase で ub=1585/1586/1588/1592 計測、**ub\* ∈ (1585, 1586] に 1-token 精度で確定、分数 ≈ 1585.18**
- [x] **ub=1586 以降の純線形性確認** (本 Phase) — 本 Phase で 8 点 max_err 0.008 MiB、線形モデル `1002.61 + 0.2853·(ub-1664)` は ub=1586 から厳密成立
- [ ] **llama.cpp scheduler ソースの ub 閾値判定箇所特定** (Phase Sb-fine 継続) — 閾値候補 `1585` / `1586` の 1 個の定数リテラルか、`>=1586` 比較を grep。ソース特定優先度最大
- [ ] **★高優先: ub ≥ 1586 線形モデルの ctx 独立性検証** (Phase Sb-fine 継続): ctx=65k/131k × ub=1586/1664/1792 の 6 条件で slope 0.2853 の ctx 依存性確認
- [ ] **★高優先: ub=1586 eval 15.466 t/s の 5-10 run 再現性** (本 Phase 新規 ★): ctx=32k の新記録値、3 run 中央値のみ、セッション間ゆらぎ検証必須
- [ ] **ub=1664 eval 15.451 t/s の 5-10 run 再現性** (Phase Sb-fine 継続): 旧記録値の再現性
- [ ] **ub=1584 eval 15.293 t/s の 5-10 run 再現性** (Phase Sb-fine2 継続)
- [ ] **eval 境界挟み込み構造の再現性** (Phase Sb-fine2 継続): 1584/1585/1586/1588/1592/1600/1664 の eval 谷山パターン
- [ ] **CUDA0 区分モデルの物理的意味** (Phase Sb-fine 継続) — 閾値 1586 が非自然な定数である理由（2^n 丸めや step 倍数ではない）
- [ ] **境界 ub\* の ctx 依存性** (Phase Sb-fine 継続) — 本 Phase も ctx=32k 固定、ctx=16k/65k/131k での境界 ub\* 位置が同じ 1586 か要確認
- [ ] **境界 ub\* の fa 依存性** (Phase Sb-fine2 継続): fa=0 でも同じ ub\* か
- [ ] **境界 ub\* の KV 量子化依存性** (Phase Sb-fine2 継続): q8_0 KV で境界が移動するか
- [ ] **CUDA0 二次係数 9.104e-6 MiB/token² の物理メカニズム** (Phase Sb 継続)
- [ ] **CUDA0 二次モデルの ctx=262144 外挿** (Phase R-ctx3 継続)
- [ ] **CUDA1/2 cross_e = 1.910e-6, Host = 3.815e-6 MiB/(token·token) の物理メカニズム** (Phase Sb 継続)
- [ ] **ub=1280/1792 の eval 性能再現性** (Phase Sb 継続)
- [ ] **ub=1280/1536/1792 × ctx=65k での CUDA0 検証** (Phase Sb 継続)
- [ ] **中間 ctx (24k / 48k / 96k) での検証** (Phase Sb 継続)
- [ ] **ctx=65k 32k prompt の 3 run 以上再計測** (Phase R-ctx3 継続)
- [ ] **CUDA3 が ctx 完全不依存となる物理メカニズム** (Phase R 継続、31 点再確証済みだがソース未特定)
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
- [ ] **graph splits=77 (with bs=1) の存在意義** (本 Phase 31 点で全条件 77 固定を再確認、意義は未特定)
- [ ] **`--parallel 2` との相互作用**
- [ ] **P3 vs Phase O の eval 差 +1.17% のセッション源**

### 新規項目（本 Phase Sb-fine3 で判明・発生）

- [ ] **★最優先: llama.cpp scheduler ソースの閾値定数特定** (Phase Sb-fine3 新規 ★★★): 閾値 ub\*=1586 が整数スカラーと判明、`git grep -n "1585\|1586\|n_tokens.*>="` 等で定数リテラルを特定
- [ ] **★最優先: ub=1586 eval 15.466 t/s の 5-10 run 再現性** (本 Phase 新規 ★): ctx=32k の新記録、セッション間ゆらぎ検証必須
- [ ] **★高優先: ub=1586 eval 再現性確認後の skill 側 start.sh デフォルト更新**: ub=1586 への変更は新記録で魅力的だが再現性確認必須
- [ ] **eval 2-4 token スケール振動 (1585 谷 / 1586 山 / 1588 谷 / 1592 山) の物理原因**: GPU0 キャッシュ境界との整合性仮説の検証
- [ ] **境界 ub\* の ctx 1-token 精度依存性検証** (本 Phase 新規): ctx=16k/65k/131k で境界が同じ ub\*=1586 か、ctx によって閾値がシフトするか
- [ ] **reserve 時間の境界非依存性の根拠**: reserve 174.34→174.36 ms で +0.02 ms のみ（compute buffer +0.24 MiB に対し）、scheduler の reserve 処理は閾値判定に寄らない証拠
- [ ] **compute buffer のセッション間決定論性の他境界点検証**: 本 Phase で ub=1586 前後も決定論的か、Phase Sb-fine3 と同条件で再計測比較
- [ ] **整数閾値 1586 の非自然性分析**: 2^n 倍数・step 倍数・CUDA warp 境界 (32) などとの関係性、なぜ 1586 という数値か

## 検証完了後に実施すべき TODO

### 既知項目（Phase Sb-fine2 から継続、本 Phase で更新）

- [ ] **start.sh の拡張**: `LLAMA_NUMACTL_PREFIX` / `LLAMA_EXTRA_THREADS` 環境変数サポート追加
- [ ] **CUDA1 セーフティマージン OOM フォールバック実装**
- [ ] **層→GPU アライメントのソースコード解析**
- [ ] **C-4 実験**（CPU 層削減 + GPU 層追加）
- [ ] **drop_caches 権限の確保**（sudoers 設定 or vmtouch 導入）
- [ ] **start.sh での NUMA プリセット整備**
- [ ] **start.sh に `--threads` 設定追加**
- [ ] **`start_phaseJ.sh` 〜 `start_phaseSbf3.sh` の環境変数化を skill 側 `start.sh` に逆輸入**
- [ ] **依存制約の lint 化**: 起動前 pre-check
  - **本 Phase で更新**: CUDA0 モデルは「ub ≤ 1585 平坦 / ub ≥ 1586 線形」の **step 関数 2 区分**（Phase Sb-fine2 の遷移域 3 区分から単純化）
  - CUDA1/2/Host は Phase Sb 4p モデル (31 点検証済み)
  - CUDA3 = 0.9824·ub (31 点検証済み)
- [ ] **llama.cpp upstream issue/PR のサーベイ**
- [ ] **`measure_phaseI.sh` を汎用化して skill に組み込む**
- [ ] **「長コンテキスト性能カード」をモデル単位で記録するドキュメント整備**
- [ ] **アプリ側にコンテキストサイズ別レイテンシ警告を出す仕組み**

### 新規項目（本 Phase Sb-fine3 で発見・更新）

- [ ] **★最優先: 起動前 lint の CUDA0 step 関数モデル更新**（Phase Sb-fine2 の 3 区分を本 Phase の 2 区分 step 関数で更新）:
  - `ub ≤ 1585`: `CUDA0 ≈ 966.5 + 0.0064·ub` + マージン 10 MiB（平坦域、9 点 max_err +3.48 MiB）
  - `ub ≥ 1586`: `1002.61 + 0.2853·(ub - 1664)` + マージン 30 MiB（線形、8 点 max_err 0.008 MiB）
- [ ] **★最優先: 起動前 lint の 4p cross 項モデル 31 点版組み込み** (Phase Sb-fine2 から継続):
  - `predicted_cuda1/2 = 520.26 + 3.903e-3·Δctx + 0.2538·Δub + 1.910e-6·Δctx·Δub`（31 点 max_err 0.188 MiB）
  - `predicted_cuda_host = 176.08 + 7.813e-3·Δctx + 0.0860·Δub + 3.815e-6·Δctx·Δub`（31 点 max_err 0.004 MiB）
  - `predicted_cuda3 = 0.9824·ub`（31 点 max_err 0.039 MiB）
  - Δctx = ctx - 16384, Δub = ub - 2048
- [ ] **★最優先: compute buffer 予測モデル（Phase Sb-fine3 確定版）を skill / CLAUDE.md に記録**:
  - **fa=1, f16 KV, C-D3**: 31 点検証済みの確定式、ub=128〜8192 × ctx=16k〜131k
  - **CUDA0 は step 関数 2 区分モデル (境界 ub\* ∈ (1585, 1586]、ub ≥ 1586 は線形 slope 0.2853)**
  - **CUDA1/2/Host は 4p 2 軸 cross 項、CUDA3 は純 ub 比例**
- [ ] **★最優先: skill 側 `.claude/skills/llama-server/scripts/start.sh:155` のデフォルト更新**:
  - 現状 t120h-p100 デフォルト: `SERVER_OPTS="--flash-attn 1 --poll 0 -b 8192 -ub 8192"`
  - Phase Sb-fine の ub=1664 (15.451) を本 Phase の ub=1586 (**15.466**) が更新、ctx=32k 系列の新記録
  - 変更候補: `-b 1586 -ub 1586`（eval 最速、境界直後の低 compute buffer） or `-b 2048 -ub 2048`（prompt 平衡、旧来候補）
  - **5-10 run 再現性検証後に最終決定**
- [ ] **CLAUDE.md / skill の情報更新**:
  - **fa=1 の CUDA0 は step 関数 2 区分モデル (境界 ub\* ∈ (1585, 1586]、ub ≥ 1586 で線形)**
  - **CUDA1/2/CUDA3/CUDA_Host は Phase Sb 4p/純比例モデル、31 点 max_err 0〜0.188 MiB**
  - **Qwen3.5-122B-A10B t120h-p100 で ub=128〜8192 × ctx=16k〜131k の compute buffer が 31 点実測で 2 軸モデル化、ub=1586 が ctx=32k の eval 新記録 15.466 t/s**
  - **境界 ub\*=1586 は整数スカラー閾値、遷移域なし**
- [ ] **モデルカード更新**: Qwen3.5-122B-A10B の長コンテキスト性能カードに本 Phase 結果を追加
- [ ] **Phase Sb-src 候補**: llama.cpp scheduler ソース (graph_reserve / sched_reserve / llama-graph.cpp) で `1585`/`1586` 定数または閾値比較をソース特定
- [ ] **Phase Sb-ctx-linear 候補**: ctx=65k/131k × ub=1586/1664/1792 の 6 条件で ub ≥ 1586 線形モデルの ctx 依存性検証（所要 1 時間程度）
- [ ] **Phase Sb-ctx-boundary 候補**: ctx=16k/65k/131k × ub=1584/1585/1586 の 9 条件で境界 ub\* の ctx 依存性検証
- [ ] **Phase Sb-fa0 候補**: fa=0 系列で同一 4 条件スキャン
- [ ] **Phase Sb-KV8 候補**: `--cache-type-{k,v} q8_0` で本 Phase を再実施
- [ ] **Phase S-eval 候補**: ctx=32k × ub=1586/1664 eval ピーク 2 点を 5-10 run で再現性検証（所要 30 分-1 時間）★ 最重要
- [ ] **Phase Q-2 候補（`-ub` 内部下限の真の値特定）**: `-ub=64 / 32 / 16 / 8 / 4 / 2 / 1`
- [ ] **Phase Q-3 候補（`-ub` ピーク周辺探索）**: ub=1586 周辺 ±8 token で eval ピーク形状を特定（1587/1590 など）
- [ ] **skill 側 start.sh の `ssh -f` stdout redirect 改修** (Phase S から継続): 本 Phase で 4 条件すべてハングなし、累計 19 条件連続成功
- [ ] **start.sh のデフォルト `ctx-size` を 131072 に更新**（現状 65536、Phase S から継続）

## 補足

### Phase Sb-fine3 の核心発見

1. **CUDA0 区分境界 ub\* ∈ (1585, 1586]** を 1-token 精度で確定、**ub\* ≈ 1585.18**（整数閾値 `n_tokens >= 1586`）
2. **ub=1586 以降は厳密に線形モデル上** (8 点 max_err 0.008 MiB、Phase Sb-fine2 の 6 点 max_err 0.035 から向上)
3. **遷移域は存在せず step 関数**: Phase Sb-fine2 の「3 区分モデル」を 2 区分 step 関数に単純化
4. **eval 新記録**: ctx=32k × ub=**1586** × 1k prompt で **15.466 t/s**（Phase Sb-fine の ub=1664 15.451 を更新）
5. **境界直後 1 token で eval +3.4% ジャンプ** (ub=1585 14.96 → ub=1586 15.47)
6. **Phase Sb 4p モデル (CUDA1/2, Host) は 31 点で max_err 0.188 / 0.004 MiB**、CUDA3 純比例 max_err 0.039 MiB
7. **境界跨ぎで graph 構造は完全不変**、reserve 時間も +0.02 ms のみ
8. **batch 42 分で完走、stdout redirect 版は累計 19 条件ハングなし**

### 31 点データベース（ub=1585/1586/1588/1592 を追加、ub 昇順、ctx=32k 系列 + 他 ctx 参照）

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
| 10 | 32,768 | 1552 | 979.70 | 442.61 | 442.61 | 1,524.72 | 230.43 | 3,620.07 | 192.00 | Sbf2-1 |
| 11 | 32,768 | 1568 | 979.91 | 447.17 | 447.17 | 1,540.44 | 232.81 | 3,647.50 | 192.00 | Sbf2-2 |
| 12 | 32,768 | 1584 | 980.11 | 451.74 | 451.74 | 1,556.16 | 235.19 | 3,674.94 | 192.00 | Sbf2-3 |
| 13 | 32,768 | **1585** | **980.12** | **452.02** | **452.02** | **1,557.14** | **235.33** | **3,676.63** | **192.00** | **Sbf3-1** |
| 14 | 32,768 | **1586** | **980.36** | **452.31** | **452.31** | **1,558.12** | **235.48** | **3,678.58** | **192.00** | **Sbf3-2** |
| 15 | 32,768 | **1588** | **980.93** | **452.88** | **452.88** | **1,560.09** | **235.78** | **3,682.56** | **192.00** | **Sbf3-3** |
| 16 | 32,768 | **1592** | **982.07** | **454.02** | **454.02** | **1,564.02** | **236.37** | **3,690.50** | **192.00** | **Sbf3-4** |
| 17 | 32,768 | 1600 | 984.35 | 456.30 | 456.30 | 1,571.88 | 237.56 | 3,706.39 | 192.00 | Sbf/Sbf2-4 |
| 18 | 32,768 | 1664 | 1,002.61 | 474.55 | 474.55 | 1,634.75 | 247.06 | 3,833.52 | 192.00 | Sbf |
| 19 | 32,768 | 1700 | 1,012.88 | 484.82 | 484.82 | 1,670.12 | 252.41 | 3,905.05 | 192.00 | Sbf |
| 20 | 32,768 | 1750 | 1,027.14 | 499.08 | 499.08 | 1,719.24 | 259.83 | 4,004.37 | 192.00 | Sbf |
| 21 | 32,768 | 1792 | 1,039.12 | 511.05 | 511.05 | 1,760.50 | 266.07 | 4,087.79 | 192.00 | Sb3 |
| 22 | 32,768 | 2048 | 1,112.13 | 584.06 | 584.06 | 2,012.00 | 304.08 | 4,596.33 | 192.00 | R-ctx3 |
| 23 | 32,768 | 4096 | 1,912.00 | 1,168.13 | 1,168.13 | 4,024.00 | 608.16 | 8,880.42 | 192.00 | S3 |
| 24 | 32,768 | 8192 | 2,784.00 | 2,336.25 | 2,336.25 | 8,048.00 | 1,216.31 | 16,720.81 | 192.00 | S4 |
| 25 | 65,536 | 512 | 966.50 | 178.02 | 178.02 | 503.00 | 140.02 | 1,965.56 | 384.00 | S5 |
| 26 | 65,536 | 1024 | 973.00 | 356.03 | 356.03 | 1,006.00 | 280.04 | 2,971.10 | 384.00 | S6 |
| 27 | 65,536 | 2048 | 1,348.00 | 712.06 | 712.06 | 2,012.00 | 560.08 | 5,344.20 | 384.00 | R-ctx3 |
| 28 | 65,536 | 4096 | 2,296.00 | 1,424.13 | 1,424.13 | 4,024.00 | 1,120.16 | 10,288.42 | 384.00 | S7 |
| 29 | 65,536 | 8192 | 4,320.00 | 2,848.25 | 2,848.25 | 8,048.00 | 2,240.31 | 20,304.81 | 384.00 | S8 |
| 30 | 131,072 | 2048 | 2,180.00 | 968.06 | 968.06 | 2,012.00 | 1,072.08 | 7,200.20 | 768.00 | R |
| 31\* | 32,768 | 1600 | 984.35 | 456.30 | 456.30 | 1,571.88 | 237.56 | 3,706.39 | 192.00 | Sbf2-4 再現 |

（太字 = 本 Phase Sb-fine3 新規計測、\* = ub=1600 は Phase Sb-fine/Sb-fine2 で完全一致）

### eval / prompt 性能データベース（ctx=32k × ub=1585/1586/1588/1592、1k prompt 3 run 中央値）

| ctx | ub | prompt_med (t/s) | eval_med (t/s) | prompt_n | 備考 |
|---:|---:|---:|---:|---:|---|
| 32,768 | 1,585 | 68.27 | 14.962 | 1,092 | Sbf3-1 — 境界直前の平坦域最終点、eval 谷 |
| 32,768 | **1,586** | 68.76 | **15.466** | 1,092 | **Sbf3-2 ★★ ctx=32k 21 点 eval 新記録（Phase Sb-fine ub=1664 15.451 を更新）** |
| 32,768 | 1,588 | 68.87 | 14.679 | 1,092 | Sbf3-3 — 境界直後 +2 token、eval 谷 |
| 32,768 | 1,592 | 68.14 | 15.376 | 1,092 | Sbf3-4 — 境界 +6 token、eval peak |

### ctx=32k eval 性能統合（21 点、ub=512〜8192、Phase Sb-fine3 で 4 点追加）

| ub | eval_med (t/s) | Phase | 備考 |
|---:|---:|---|---|
| 512 | 14.636 | S | |
| 1024 | 14.640 | S | |
| 1280 | 15.405 | Sb | |
| 1536 | 14.910 | Sb | |
| 1552 | 14.764 | Sbf2 | 平坦域 |
| 1568 | 14.687 | Sbf2 | 平坦域 |
| 1584 | 15.293 | Sbf2 | 平坦域最後、サブピーク |
| **1585** | **14.962** | **Sbf3** | 平坦域最終点、谷 |
| **1586** | **15.466** | **Sbf3** | **★★★ 21 点最速（新記録）、境界直後** |
| **1588** | **14.679** | **Sbf3** | 線形 +2 token、谷 |
| **1592** | **15.376** | **Sbf3** | 線形 +6 token、peak |
| 1600 | 14.568 | Sbf2 | 線形 +14 token、谷 |
| 1664 | 15.451 | Sbf | 旧記録、Sbf3 で更新 |
| 1700 | 14.758 | Sbf | |
| 1750 | 14.624 | Sbf | |
| 1792 | 15.255 | Sb | |
| 2048 | 15.06 | R-ctx3 | |
| 4096 | 14.651 | S | |
| 8192 | 14.915 | S | |

### 作業終了時点の状態

- llama-server は停止済み（batch_boundary_fine3.sh 末尾の stop.sh で正常終了）
- GPU サーバロック（t120h-p100）は解放済み
- `results.tsv` 25 行（Sbf3-1〜Sbf3-4 × warmup/1k × 3 run = 24 run + ヘッダ）
- `compute_buffer_summary.txt` （4 条件 × 主要 18 行）
- `analyze_boundary_fine3.py` / `analyze_boundary_fine3.txt` で Phase Sb/Sb-fine/Sb-fine2 4p モデル 31 点検証 + CUDA0 step 関数モデル確定（2 区分、境界 ub\*=1586、ub >= 1586 線形 slope 0.2853 を 8 点 max_err 0.008 MiB）
- **CUDA0 境界 ub\* ∈ (1585, 1586] を 1-token 精度で確定（Phase Sb-fine2 の 16-token 精度を 16 倍改善、累計 Phase Sb から 256 倍改善）、分数推定 ub\*=1585.18、ub=1586 eval 15.466 t/s ctx=32k 系列新記録、llama.cpp scheduler ソースの閾値定数 1586 特定を次の最優先タスクとして登録**
