# mi25 c48c4 SLOT8 移動 + Vulkan 8h 負荷 — 集計表

## 全期間サマリ
| 項目 | 値 |
|---|---|
| キャンペーン期間 [h] | 8.05 |
| 完了 trial 数 (trial_done) | 37 |
| HANG_CONFIRMED (jsonl) | 0 |
| dmesg GPU reset (新規 baseline+2296行以降) | 0 |
| 統合 fault 件数 | 0 |
| stall 件数 | 0 |
| ネットワーク障害 件数 | 0 |
| turn 総数 | 255 |
| eval_tps mean | 24.23 |
| eval_tps p50 | 23.90 |
| pp_tps mean | 255.42 |
| 本試験 fault 率 | 0/37 = 0.00% |
| 過去 4 枚運用 fault 率 | 3/88 = 3.41% |
| 過去 stand_alone_24h SLOT6 fault 率 | 2/147 = 1.36% |
| Fisher (本 vs 4 枚運用、H1: 本 < 4 枚) | p = 0.3454 |
| Fisher (本 vs stand_alone_24h、H1: 本 < SA) | p = 0.6374 |

## dmesg amdgpu フォルト集計
- baseline 行数: 2296
- kern_dmesg.log 全行数: 2301
- 新規 fault 関連検出件数: 0
- シグネチャ別: {}
- BDF 別: {}

## PCIe AER (キャンペーン中)
- samples: 5634, non-x16 entries: 0
- AER COR max: 0, FATAL max: 0, NFATAL max: 0
- GPU_COUNT min: 4

## GPU[2] (c48c4) テレメトリ
- rocm-smi samples: 5170
- power [W]: mean 71.8, p95 160.0, max 168.0
- Tj junction max: 95.0 °C

## 1h バケット推移
| hour | trials | faults | eval p50 [t/s] | GPU[2] power p95 [W] |
|---:|---:|---:|---:|---:|
| 0 | 4 | 0 | 24.60 | 163.0 |
| 1 | 5 | 0 | 23.50 | 162.0 |
| 2 | 4 | 0 | 24.40 | 162.2 |
| 3 | 5 | 0 | 24.25 | 163.0 |
| 4 | 4 | 0 | 24.40 | 162.0 |
| 5 | 5 | 0 | 23.70 | 162.0 |
| 6 | 5 | 0 | 23.70 | 161.0 |
| 7 | 4 | 0 | 24.25 | 162.0 |
| 8 | 1 | 0 | 22.65 | 116.4 |
