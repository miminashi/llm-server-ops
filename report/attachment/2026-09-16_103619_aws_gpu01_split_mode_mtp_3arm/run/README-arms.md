# この run ディレクトリの腕の対応

| ディレクトリ | 腕 | split | AllReduce | MTP | 用途 |
|---|---|---|---|---|---|
| `run/` (tag `gpu01-7way-mtp2`) | layer / tensor / layer2 | それぞれ | **none** | **有効** | 本計測（3 腕） |
| `run/real-layer/`, `run/real-layer2/` | layer / layer2 | layer | none | 有効 | 腕別の実プロンプト補正（本計測後に個別取得） |
| `run/results-real.json` | tensor | tensor | none | 有効 | `REAL_MODE=auto` がツール内で取得した分 |
| `run-tensor-none-nomtp/` (tag `gpu01-7way-tensor-none-nomtp`) | tensor | tensor | **none** | **無効** | 回避策単独のコストを測る切り分け腕 |
| `nccl-retry/` (tag `gpu01-7way-tensor-nccl-nomtp`) | tensor | tensor | **NCCL(既定)** | 無効 | NCCL 経路の再測定を 10 回試み、**全て起動ハングで失敗**。`retry.log` と `server-try{1..10}.log` が証跡 |

MTP 無効側の比較対象（`gpu01-7way-1`、NCCL 既定）は
`report/attachment/2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor/run/` にある。
