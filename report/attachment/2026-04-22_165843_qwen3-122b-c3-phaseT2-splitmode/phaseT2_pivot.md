# Phase T-2: split-mode row vs layer pivot 比較表

- ctx=32768, ub=1586, fa=1, threads=40, numactl node1, OT=MoE only, poll=0
- warmup 2 run + eval 5 run
- ベースライン: Phase D 15.03 t/s / Phase S 15.39 t/s / Phase T-1 q8_0 15.016 t/s / Phase T-1 f16 14.425 t/s

## eval_tps (mean±stdev, t/s) — eval フェーズ 5 run

| KV 型 | split=layer | split=row | row/layer 比 | best split | best mean | 判定 |
|-------|-------------|-----------|--------------|------------|-----------|------|
| f16 | 14.181±0.004 | 12.052±0.009 | 0.8498 | layer | 14.181 | below_T1 (14.181 ≤ 15.016) |
| q8_0 | 14.672±0.003 | 11.457±0.008 | 0.7809 | layer | 14.672 | below_T1 (14.672 ≤ 15.016) |

## prompt_tps (mean±stdev, t/s) — eval フェーズ 5 run

| KV 型 | split=layer | split=row | row/layer 比 | best split | best mean |
|-------|-------------|-----------|--------------|------------|-----------|
| f16 | 68.277±0.131 | 64.125±0.027 | 0.9392 | layer | 68.277 |
| q8_0 | 68.627±0.274 | 64.180±0.059 | 0.9352 | layer | 68.627 |

## 結果サマリ

- **最良 eval 構成**: KV=q8_0, split-mode=layer, eval_mean=14.672 t/s
- **Phase D (15.03) 超え**: NO
- **Phase S (15.39) 超え**: NO
- **Phase T-1 q8_0 (15.016) 超え**: NO

## q8_0 vs f16 独立再現性 (Phase T-1 副次発見 +4.1% の再現可否)

- 本 Phase split=layer: f16 eval_mean = 14.181 t/s (Phase T-1: 14.425)
- 本 Phase split=layer: q8_0 eval_mean = 14.672 t/s (Phase T-1: 15.016)
- q8_0 - f16 (split=layer) = +0.491 t/s (+3.46%)
- Phase T-1 副次発見 +4.1% との一致: YES (差分 +3.46%)

## split-mode row 効果 (CUDA3 compute buffer 偏在解消狙い)

- KV=f16: row - layer = -2.129 t/s (-15.02%) → **劣化**
- KV=q8_0: row - layer = -3.215 t/s (-21.91%) → **劣化**
