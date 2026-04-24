# Phase T-5a-ts2: B14 × tensor-split で 19+ 突破試行 pivot

- ctx=32k, ub=256, KV=q8_0, split-mode=layer, threads=40, fa=1, numactl node1, poll=0
- warmup 2 run + eval 5 run
- ベースライン: D 15.03 / S 15.39 / T-5 16.024 / T-5f 16.455 / T-5a 18.006 / T-5a-ub 18.103 / T-5a-thr 17.988 / **T-5a-ts 18.417** (直前歴代 #1、B16×`-ts 11,12,13,13`) (t/s)

## eval/prompt 条件別 (実行順, mean±stdev, t/s)

| # | label | OT | CPU | TS | 役割 | eval_mean±stdev | prompt_mean±stdev | 判定 |
|---|-------|----|-----|-----|------|-----------------|-------------------|------|
| 1 | B18_default_a | B18 | 18 | `(default)` | drift 起点・T-5a-ub 18.103 / T-5a-ts 17.964 cross-session 再現 (4 回目) | 18.080±0.004 | 38.598±0.034 | surpass_T5a (18.080 > 18.006) |
| 2 | B14c_ts_primary | B14c | 14 | `11,12,13,14` | B14 本命 (OT-c: layer 23,24 GPU、dry D5 VRAM 最バランス) | 18.356±0.006 | 45.728±0.041 | surpass_T5a-ub (18.356 > 18.103) |
| 3 | B14b_ts_alt | B14b | 14 | `11,12,13,14` | B14 alt (OT-b: layer 24,39 GPU、同 ts で OT 比較) | 18.664±0.003 | 46.082±0.026 | **SURPASS_T5a-ts +0.10 (新記録確実)** (18.664 > 18.517) |
| 4 | B16_ts_skew | B16 | 16 | `11,12,13,13` | T-5a-ts peak 18.417 cross-session 再現 (ベンチマーク) | 18.496±0.001 | 43.057±0.024 | **SURPASS_T5a-ts (新記録)** (18.496 > 18.417) |
| 5 | B18_default_z | B18 | 18 | `(default)` | drift 終点 (2-pt linear bracket) | 18.201±0.006 | 38.615±0.020 | surpass_T5a-ub (18.201 > 18.103) |

## Session drift bracket (B18_default_a 起点 / 終点、2-pt linear)

| label | 役割 | run_index | eval_mean | 起点比 |
|-------|------|-----------|-----------|--------|
| B18_default_a | drift 起点 | 1 | 18.080 | -- |
| B18_default_z | drift 終点 | 5 | 18.201 | +0.121 t/s (+0.67%) |

### drift 判定: **drift 健全** (< 0.20 t/s、本 Phase 目標) (|差| = 0.121 t/s, per_run = +0.0302)

### B18 default の cross-session 再現性

| label | eval_mean | T-5a-ts B18_default_a (17.964) 差 | T-5a-ub baseline (18.103) 差 | 判定 |
|-------|-----------|-----------------------------------|------------------------------|------|
| B18_default_a | 18.080 | +0.116 | -0.023 | 再現 (±0.5 内) |
| B18_default_z | 18.201 | +0.237 | +0.098 | 再現 (±0.5 内) |

### drift 補正 (linear 2-pt, per_run=+0.0302 t/s/run)

| # | label | OT | TS | 実測 eval_mean | 補正後 eval_mean | 補正後 - T-5a-ts (18.417) | 補正後 - 19.0 |
|---|-------|----|-----|----------------|------------------|---------------------------|----------------|
| 1 | B18_default_a | B18 | `(default)` | 18.080 | **18.080** | -0.337 | -0.920 |
| 2 | B14c_ts_primary | B14c | `11,12,13,14` | 18.356 | **18.326** | -0.091 | -0.674 |
| 3 | B14b_ts_alt | B14b | `11,12,13,14` | 18.664 | **18.604** **★ 新記録** | +0.187 | -0.396 |
| 4 | B16_ts_skew | B16 | `11,12,13,13` | 18.496 | **18.405** | -0.012 | -0.595 |
| 5 | B18_default_z | B18 | `(default)` | 18.201 | **18.080** | -0.337 | -0.920 |

**補正後最良**: B14b_ts_alt (corrected = 18.604 t/s, T-5a-ts 比 +0.187 t/s, 19.0 比 -0.396 t/s)

## B14 fit 達成と eval 影響評価 (本 Phase 主目的)

| label | OT | TS | eval_mean | T-5a-ts (18.417) 差 | B18_default_a 比 | B14 評価 |
|-------|----|-----|-----------|----------------------|------------------|----------|
| B14c_ts_primary | B14c | `11,12,13,14` | 18.356 | -0.061 | +0.276 | B14 fit、eval 同等 (改善なし) |
| B14b_ts_alt | B14b | `11,12,13,14` | 18.664 | +0.247 | +0.584 | **B14 fit + 新記録 (有意)** |

## B16_ts_skew cross-session 再現性 (T-5a-ts 18.417 peak との一致)

| label | TS | eval_mean | T-5a-ts (18.417) 差 | 判定 |
|-------|-----|-----------|----------------------|------|
| B16_ts_skew | `11,12,13,13` | 18.496 | +0.079 | **再現良好** (±0.10 内、T-5a-ts peak と一致) |

## 結果サマリ

- **最良 eval 構成 (実測)**: label=B14b_ts_alt (OT=B14b, ub=256, ctx=32k, threads=40), eval_mean=18.664 t/s
- **🎯 19+ 突破**: NO
- **Phase T-5a-ts (18.417) 超え**: **YES (歴代新記録)**
- **Phase T-5a-ub (18.103) 超え**: YES
- **Phase T-5a (18.006) 超え**: YES
- **Phase D (15.03) 超え**: YES
- B18_default_a (T-5a-ts cross-session 再現): 18.080 t/s

## 全 Phase 比較

| Phase | 条件 (要点) | eval mean (t/s) | T-5a-ts2 最良との差 |
|-------|-------------|-----------------|----------------------|
| D | threads=40, ub=1586, ctx=32k, OT=A36 | 15.030 | +24.18% |
| S | ctx=65k, ub=512, threads=40, A36 | 15.390 | +21.27% |
| T-5 best | B28 × ub=1586 | 16.024 | +16.48% |
| T-5e best | B28 × ctx=32k × ub=512 | 16.380 | +13.94% |
| T-5f best | B28 × ub=512 微細 | 16.455 | +13.42% |
| T-5a best | B18 × ub=512 × thr=40 | 18.006 | +3.65% |
| T-5a-ub best | B18 × ub=256 × thr=40 | 18.103 | +3.10% |
| T-5a-thr | B18 × ub=256 × thr=40 (再測定) | 17.988 | +3.76% |
| **T-5a-ts best** | **B16 × `-ts 11,12,13,13` (直前歴代 #1)** | 18.417 | +1.34% |
| **T-5a-ts2** | B18_default_a (OT=B18, drift 起点・T-5a-ub 18.103 / T-5a-ts 17.964 cross-session 再現 (4 回目)) | 18.080 | -3.13% |
| **T-5a-ts2** | B14c_ts_primary (OT=B14c, TS=`11,12,13,14`, B14 本命 (OT-c: layer 23,24 GPU、dry D5 VRAM 最バランス)) | 18.356 | -1.65% |
| **T-5a-ts2** | B14b_ts_alt (OT=B14b, TS=`11,12,13,14`, B14 alt (OT-b: layer 24,39 GPU、同 ts で OT 比較)) (**本 Phase 最良**) | 18.664 | +0.00% |
| **T-5a-ts2** | B16_ts_skew (OT=B16, TS=`11,12,13,13`, T-5a-ts peak 18.417 cross-session 再現 (ベンチマーク)) | 18.496 | -0.90% |
| **T-5a-ts2** | B18_default_z (OT=B18, drift 終点 (2-pt linear bracket)) | 18.201 | -2.48% |

