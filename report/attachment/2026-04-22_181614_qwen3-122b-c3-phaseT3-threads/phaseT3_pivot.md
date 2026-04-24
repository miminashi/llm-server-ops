# Phase T-3: threads 中間値スイープ pivot 比較表

- KV=q8_0, split-mode=layer, ctx=32768, ub=1586, fa=1, numactl node1, OT=MoE only, poll=0
- warmup 2 run + eval 5 run
- ベースライン: Phase D 15.03 / Phase S 15.39 / Phase T-1 q8_0 15.016 / Phase T-2 最良 14.672 (t/s)

## eval_tps (mean±stdev, t/s) — eval フェーズ 5 run

| threads | eval mean±stdev | eval min | eval max | vs threads=40 | 判定 |
|---------|-----------------|----------|----------|---------------|------|
| 24 | 14.024±0.017 | 14.005 | 14.048 | -5.12% | below_T2 (14.024 ≤ 14.672) |
| 28 | 14.453±0.006 | 14.444 | 14.461 | -2.22% | below_T2 (14.453 ≤ 14.672) |
| 32 | 14.860±0.002 | 14.857 | 14.863 | +0.53% | surpass_T2 (14.860 > 14.672) |
| 36 | 14.551±0.003 | 14.548 | 14.555 | -1.55% | below_T2 (14.551 ≤ 14.672) |
| 40 | 14.781±0.002 | 14.778 | 14.783 | +0.00% | surpass_T2 (14.781 > 14.672) |

## prompt_tps (mean±stdev, t/s) — eval フェーズ 5 run

| threads | prompt mean±stdev | vs threads=40 |
|---------|-------------------|---------------|
| 24 | 68.361±0.066 | +0.17% |
| 28 | 68.734±0.122 | +0.72% |
| 32 | 68.836±0.119 | +0.87% |
| 36 | 68.155±0.101 | -0.13% |
| 40 | 68.246±0.030 | +0.00% |

## 結果サマリ

- **最良 eval 構成**: threads=32, eval_mean=14.860 t/s
- **Phase D (15.03) 超え**: NO
- **Phase S (15.39) 超え**: NO
- **Phase T-1 q8_0 (15.016) 超え**: NO
- **Phase T-2 最良 (14.672) 超え**: YES

## threads スイープ効果 (baseline threads=40 比、±1% 閾値)

- threads=24: -0.756 t/s (-5.12%) → **劣化**
- threads=28: -0.328 t/s (-2.22%) → **劣化**
- threads=32: +0.079 t/s (+0.53%) → **中立**
- threads=36: -0.230 t/s (-1.55%) → **劣化**
- threads=40: baseline (14.781 t/s)
