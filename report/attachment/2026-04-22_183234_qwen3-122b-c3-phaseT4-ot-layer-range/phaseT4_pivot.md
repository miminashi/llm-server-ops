# Phase T-4: OT pattern 層範囲スイープ pivot 比較表

- KV=q8_0, split-mode=layer, ctx=32768, ub=1586, fa=1, numactl node1, poll=0
- warmup 2 run + eval 5 run
- OT 条件:
  - **B32** (32 層 CPU、GPU 残: 0-13, 20-24, 31-43 (GPU 残: 14-19 + 25-30 + 44-47))
  - **A36** (36 層 CPU、GPU 残: 0-13, 20-24, 31-47 (GPU 残: 14-19 + 25-30))
  - **C40** (40 層 CPU、GPU 残: 0-17, 20-24, 31-47 (GPU 残: 18-19 + 25-30) ※ threads=32 条件のみ 1[0-9] で 42 層 (0-24, 31-47、GPU 残: 25-30))
- ベースライン: Phase D 15.03 / Phase S 15.39 / Phase T-1 q8_0 15.016 / Phase T-2 最良 14.672 / Phase T-3 最良 14.86 / T-3 t40 baseline 14.781 (t/s)

## eval_tps OT × threads マトリクス (mean±stdev, t/s) — eval フェーズ 5 run

| OT (CPU 層数) | threads=32 | threads=40 | t32 vs t40 |
|---------------|-----------|-----------|-----------|
| **B32** (32) | 14.919±0.002 | 15.494±0.005 | -3.71% |
| **A36** (36) | 14.297±0.003 | 15.052±0.003 | -5.01% |
| **C40** (40) | 13.972±0.003 | 14.103±0.004 | -0.93% |

## prompt_tps OT × threads マトリクス (mean±stdev, t/s)

| OT (CPU 層数) | threads=32 | threads=40 | t32 vs t40 |
|---------------|-----------|-----------|-----------|
| **B32** (32) | 71.620±0.031 | 71.750±0.107 | -0.18% |
| **A36** (36) | 68.348±0.259 | 68.657±0.088 | -0.45% |
| **C40** (40) | 61.904±0.072 | 63.260±0.086 | -2.14% |

## T-3 仮説判定 (CPU offload 層数 = threads で drop ≥ 1%)

仮説: OT pattern でマッチする CPU offload 層数と threads 数が一致すると、OpenMP の expert 層分配が「丁度 1 thread/層」になり、MoE expert routing の非一様な activation が idle thread として直接露出して eval_tps が drop する。

**注記**: C40-t32 は batch script の修正漏れにより実効 42 層 CPU で実行された (1[0-9] 指定、本来は 1[0-7] で 40 層)。42 ≠ 32 のため仮説の「不一致側」としては依然有効。

| OT 条件 | match (層=threads) | other (層≠threads) | match-other | 判定 |
|---------|--------------------|--------------------|-----------|------|
| B32 (32 層) | t32: 14.919 | t40: 15.494 | -0.575 t/s | **SUPPORT** (-3.71%) |
| A36 (36 層) | -- | t32 / t40 control | -- | control (T-3 状態の再現) |
| C40 (40 層) | t40: 14.103 | t32: 13.972 | +0.131 t/s | NEUTRAL (+0.94%) |

### 総合判定: **PARTIAL SUPPORT** (片方のみで drop ≥ 1%)

## 結果サマリ

- **最良 eval 構成**: ot=B32 (CPU 32 層) × threads=40, eval_mean=15.494 t/s
- **Phase D (15.03) 超え**: YES
- **Phase S (15.39) 超え**: YES
- **Phase T-1 q8_0 (15.016) 超え**: YES
- **Phase T-3 最良 (14.860) 超え**: YES
- **Phase T-3 t40 baseline (14.781) 超え**: YES
- **Phase T-2 最良 (14.672) 超え**: YES

## Phase D / S / T-1 / T-2 / T-3 / T-4 全体比較

| Phase | 条件 (要点) | eval mean (t/s) | T-4 最良との差 |
|-------|-------------|----------------|---------------|
| D | threads=40, ub=1586, ctx=32k, OT=36 層 | 15.030 | +3.09% |
| S | ctx=65k, ub=512, threads=40 (歴代最高) | 15.390 | +0.68% |
| T-1 | KV q8_0, ub=1586, threads=40 | 15.016 | +3.18% |
| T-2 best | split=layer, q8_0, threads=40 | 14.672 | +5.60% |
| T-3 best | threads=32, OT=A36 (CPU 36 層) | 14.860 | +4.27% |
| T-3 t40 | threads=40, OT=A36 (baseline) | 14.781 | +4.82% |
| **T-4** | B32 (CPU 32 層) × threads=32 | 14.919 | -3.71% |
| **T-4** | B32 (CPU 32 層) × threads=40 (本 Phase 最良) | 15.494 | +0.00% |
| **T-4** | A36 (CPU 36 層) × threads=32 | 14.297 | -7.72% |
| **T-4** | A36 (CPU 36 層) × threads=40 | 15.052 | -2.85% |
| **T-4** | C40 (CPU 40 層) × threads=32 | 13.972 | -9.82% |
| **T-4** | C40 (CPU 40 層) × threads=40 | 14.103 | -8.97% |

