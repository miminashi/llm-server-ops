# Phase T-5: OT 層削減 (B28 VRAM 限界) pivot 比較表

- KV=q8_0, split-mode=layer, ctx=32768, ub=1586, fa=1, numactl node1, poll=0
- warmup 2 run + eval 5 run
- ベースライン: Phase D 15.03 / Phase S 15.39 / Phase T-1 q8_0 15.016 / Phase T-3 最良 14.86 / **Phase T-4 最良 15.494** (t/s)

## eval_tps 条件別 (mean±stdev, t/s) — eval フェーズ 5 run

| label | OT | CPU 層数 | threads | 役割 | eval_mean±stdev | 判定 |
|-------|----|---------|---------|------|----------------|------|
| B32a | B32 | 32 | 40 | drift 起点 | 15.357±0.001 | surpass_D (15.357 > 15.03) |
| B30 | B30 | 30 | 40 | 中間点 | 15.379±0.006 | surpass_D (15.379 > 15.03) |
| B28 | B28 | 28 | 40 | 本命 (VRAM 限界) | 16.024±0.003 | **SURPASS_T4** (16.024 > 15.494) |
| B28c | B28 | 28 | 32 | 層≠threads control | 15.318±0.004 | surpass_D (15.318 > 15.03) |
| B32z | B32 | 32 | 40 | drift 終点 | 15.354±0.004 | surpass_D (15.354 > 15.03) |

## prompt_tps 条件別 (mean±stdev, t/s)

| label | OT | CPU 層数 | threads | prompt_mean±stdev |
|-------|----|---------|---------|------------------|
| B32a | B32 | 32 | 40 | 71.608±0.134 |
| B30 | B30 | 30 | 40 | 74.132±0.092 |
| B28 | B28 | 28 | 40 | 76.490±0.064 |
| B28c | B28 | 28 | 32 | 77.060±0.115 |
| B32z | B32 | 32 | 40 | 72.084±0.039 |

## CPU 層数 monotonic trend (threads=40 のみ)

| CPU 層数 | label | eval_mean (t/s) | B32a 起点差 |
|----------|-------|----------------|-------------|
| 32 | B32a | 15.357 | +0.000 t/s |
| 30 | B30 | 15.379 | +0.022 t/s |
| 28 | B28 | 16.024 | +0.667 t/s |

### trend 判定: **STRONG monotonic** (B32a < B30 < B28, 差 +0.667 ≥ 0.1)

## Session drift 分析 (B32a 起点 vs B32z 終点)

| label | 役割 | eval_mean | 起点比 |
|-------|------|----------|--------|
| B32a | drift 起点 | 15.357 | -- |
| B32z | drift 終点 | 15.354 | -0.003 t/s (-0.02%) |

### drift 判定: **drift 健全** (|差| 0.003 < 0.2 t/s、絶対値比較有効)

## 層 ≠ threads 不一致 control (B28-t40 vs B28-t32)

| label | threads | 層==threads? | eval_mean |
|-------|---------|--------------|----------|
| B28 | 40 | no (28≠40) | 16.024 |
| B28c | 32 | no (28≠32) | 15.318 |

t32 vs t40 (at B28): -0.706 t/s (-4.41%) — 両方とも不一致条件、純粋 threads 効果のみ

## 結果サマリ

- **最良 eval 構成**: label=B28 (ot=B28, CPU 28 層 × threads=40), eval_mean=16.024 t/s
- **Phase T-4 (15.494) 超え**: **YES**
- **Phase S (15.39) 超え**: YES
- **Phase D (15.03) 超え**: YES
- **Phase T-1 q8_0 (15.016) 超え**: YES
- **Phase T-3 最良 (14.86) 超え**: YES

## Phase D / S / T-1 / T-2 / T-3 / T-4 / T-5 全体比較

| Phase | 条件 (要点) | eval mean (t/s) | T-5 最良との差 |
|-------|-------------|----------------|----------------|
| D | threads=40, ub=1586, ctx=32k, OT=36 層 | 15.030 | +6.62% |
| S | ctx=65k, ub=512, threads=40 (旧歴代最高) | 15.390 | +4.12% |
| T-1 | KV q8_0, ub=1586, threads=40 | 15.016 | +6.72% |
| T-2 best | split=layer, q8_0, threads=40 | 14.672 | +9.22% |
| T-3 best | threads=32, OT=A36 (CPU 36 層) | 14.860 | +7.84% |
| T-3 t40 | threads=40, OT=A36 (baseline) | 14.781 | +8.41% |
| T-4 best | B32 (CPU 32 層) × threads=40 (T-4 歴代最高) | 15.494 | +3.42% |
| **T-5** | B32a (B32, CPU 32 層 × threads=40, drift 起点) | 15.357 | -4.17% |
| **T-5** | B30 (B30, CPU 30 層 × threads=40, 中間点) | 15.379 | -4.03% |
| **T-5** | B28 (B28, CPU 28 層 × threads=40, 本命 (VRAM 限界)) (**本 Phase 最良**) | 16.024 | +0.00% |
| **T-5** | B28c (B28, CPU 28 層 × threads=32, 層≠threads control) | 15.318 | -4.41% |
| **T-5** | B32z (B32, CPU 32 層 × threads=40, drift 終点) | 15.354 | -4.18% |

