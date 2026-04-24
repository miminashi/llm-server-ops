# Phase M: ctx=1024 / 2048 での fa=0 compute buffer 実測

## Context

Phase L（`report/2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan.md`）の未検証事項「新規項目」筆頭、かつ「検証完了後に実施すべき TODO（新規項目）」で **Phase M 候補** として明記された最優先項目。

**問題**: Phase L 実測で f16 KV + flash-attn=0 の compute buffer が O(n^1.3) の混合オーダーであることが判明（Phase K 仮説 O(n²) の部分訂正）。しかし 2 点（ctx=16384 で CUDA0=18,176 MiB、ctx=4096 で CUDA0=2,888 MiB）では、以下の分離ができない:

- `buffer(n) = a·n² + b·n + c` の各係数（attention score の n² 成分 / 中間活性の n 成分 / embed/output の定数成分）

**解決**: ctx=2048, 1024 を追加し計 4 点で最小二乗フィット → 係数分離。

**副次目的**: Phase L 副次所見「ctx-size は eval 速度にほぼ影響しない」を極小 ctx 側（16k/4k/2k/1k）でも検証。

## 実施内容

### 1. 準備（既存資産流用 + 1 行修正）

- Phase L 資産ディレクトリ `report/attachment/2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan/` から以下をコピー:
  - `start_phaseL.sh`（**そのまま流用、CTX_SIZE 環境変数化済み**）
  - `measure_phaseI.sh`（そのまま流用）
  - `run_all.sh`（そのまま流用）
  - `prompts/`（そのままコピー）
  - `aggregate_results.sh` → **`out_L_*` を `out_M_*` に変更（10 行目 1 箇所）**
- 新規作成: `startup_logs/` サブディレクトリ

### 2. 計測順序（OOM リスクの低い側から昇順）

| Step | CTX_SIZE | FLASH_ATTN | 計測 | 備考 |
|:--|--:|--:|--|--|
| 1 | 1024 | 0 | warmup × 3 runs | 1k プロンプト (1,079 tok) は ctx 超過で不可、warmup のみ |
| 2 | 2048 | 0 | warmup + 1k × 3 runs | Phase L 同条件 |

各ステップで以下を採取:
- 起動ログ `startup_logs/fa0_ctx${CTX_SIZE}.log`（`sched_reserve: CUDA* compute buffer size` 行 5 本、`graph nodes` / `graph splits`）
- `out_M_f16_fa0_ctx${CTX_SIZE}_*/` に `eval_run*.json` + `gpu_post_run*.csv`

### 3. 集計 + 回帰フィット

- `bash aggregate_results.sh > results.tsv`
- `grep "compute buffer size" startup_logs/fa0_ctx*.log > compute_buffer_summary.txt`
- **回帰分析**（レポート本文内で手計算または小スクリプト）:
  - **主結果**: `log(buffer) = k·log(n) + c` の 1 次フィット、3 点 (ctx=1024/2048/4096) で GPU 別に実施（CUDA0 / CUDA1 / CUDA2 / CUDA3 / CUDA_Host）
  - **参考値**: CUDA0 のみ 4 点 (+ ctx=16384 の 18,176 MiB) を加えた k を併記
  - **モデル分離**: `buffer(n) = a·n² + b·n + c` の 3 点厳密解（3 変数 3 式）

### 4. 事前予測表（レポートに明示）

| ctx | Phase K 予測 (O(n²)) | Phase L 外挿 (O(n^1.3)) | Phase M 実測 |
|---:|---:|---:|---:|
| 16384 | 18,176 (採取値、基準) | 18,176 | 既測 (CUDA0 のみ) |
| 4096 | 1,136 (Phase K 予測) | 2,888 (Phase L 実測) | 既測 |
| 2048 | 284 | ~1,165 | **Phase M** |
| 1024 | 71 | ~473 | **Phase M** |

外挿計算: `2888 / (4096/n)^1.306`

### 5. 起動コマンド

```bash
# ロック取得
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

# Phase M ディレクトリ作成
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
PHASE_M_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseM-ctx-scan"
mkdir -p "$PHASE_M_DIR/startup_logs"
# Phase L 資産をコピー、aggregate_results.sh の out_L_* → out_M_* を修正

# Step 1: ctx=1024
FLASH_ATTN=0 CTX_SIZE=1024 bash "$PHASE_M_DIR/start_phaseL.sh"
ssh t120h-p100 "cat /tmp/llama-server_fa0_ctx1024.log" > "$PHASE_M_DIR/startup_logs/fa0_ctx1024.log"
cd "$PHASE_M_DIR"
TAG_PREFIX=M_f16_fa0_ctx1024 SIZES="warmup" PID=<取得値> bash run_all.sh
cd -
.claude/skills/llama-server/scripts/stop.sh t120h-p100

# Step 2: ctx=2048
FLASH_ATTN=0 CTX_SIZE=2048 bash "$PHASE_M_DIR/start_phaseL.sh"
ssh t120h-p100 "cat /tmp/llama-server_fa0_ctx2048.log" > "$PHASE_M_DIR/startup_logs/fa0_ctx2048.log"
cd "$PHASE_M_DIR"
TAG_PREFIX=M_f16_fa0_ctx2048 SIZES="warmup 1k" PID=<取得値> bash run_all.sh
cd -
.claude/skills/llama-server/scripts/stop.sh t120h-p100

# 集計
cd "$PHASE_M_DIR" && bash aggregate_results.sh > results.tsv
grep -h "compute buffer size\|graph nodes\|graph splits" startup_logs/fa0_ctx*.log > compute_buffer_summary.txt

# ロック解放
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 6. レポート作成

- ファイル名: `report/${TS}_qwen3-122b-c3-phaseM-ctx-scan.md`
- 必須セクション（REPORT.md 準拠 + ユーザー要望）:
  - 添付ファイル（plan.md、startup_logs、results.tsv、compute_buffer_summary.txt）
  - 前提・目的（Phase L 未検証事項の引用）
  - 環境情報（Phase L と同一）
  - 計測手順
  - 実行結果サマリ（起動可否、compute buffer 4 点表、GPU 別回帰係数、eval 速度、prompt 速度）
  - ボトルネック分析（n²/n/定数の内訳、CUDA3 の ctx 不変の再確認）
  - 採用判定
  - **未検証事項**（Phase L から継続 + 新規）
  - **検証完了後に実施すべき TODO**（Phase L から継続 + 新規）
  - 補足

## Critical Files

### 既存ファイル（流用）

- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan/start_phaseL.sh` — CTX_SIZE 可変、OOM 早期判定付き
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan/run_all.sh`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan/measure_phaseI.sh`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan/aggregate_results.sh` — `out_L_*` を `out_M_*` に変更

### 参照レポート

- `/home/ubuntu/projects/llm-server-ops/report/2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan.md`（Phase L、直前のレポート）
- `/home/ubuntu/projects/llm-server-ops/report/2026-04-18_025221_qwen3-122b-c3-phaseK-f16-flashattn-ab.md`（Phase K、O(n²) 仮説提示元）

### 新規作成（Phase M ディレクトリ配下）

- `report/${TS}_qwen3-122b-c3-phaseM-ctx-scan.md`（本レポート）
- `report/attachment/${TS}_qwen3-122b-c3-phaseM-ctx-scan/plan.md`（本プランのコピー）
- `report/attachment/${TS}_qwen3-122b-c3-phaseM-ctx-scan/startup_logs/fa0_ctx{1024,2048}.log`
- `report/attachment/${TS}_qwen3-122b-c3-phaseM-ctx-scan/results.tsv`
- `report/attachment/${TS}_qwen3-122b-c3-phaseM-ctx-scan/compute_buffer_summary.txt`
- `report/attachment/${TS}_qwen3-122b-c3-phaseM-ctx-scan/out_M_f16_fa0_ctx{1024,2048}_*/`

## 検証（Verification）

1. **起動可否**: 両 ctx で `/health` が 120s 以内に 200 OK を返すこと（OOM で abort しないこと）
2. **compute buffer 採取**: 起動ログの `sched_reserve: CUDA{0,1,2,3,_Host} compute buffer size` 行が 5 本揃っていること
3. **eval 計測**: `eval_run{1,2,3}.json` がそれぞれ `timings.predicted_per_second` を含み、Run 間 range が Phase L 同等の ±0.1% に収まること
4. **集計**: `results.tsv` が `M_f16_fa0_ctx1024_warmup` × 3 + `M_f16_fa0_ctx2048_warmup` × 3 + `M_f16_fa0_ctx2048_1k` × 3 = 計 9 行になること
5. **回帰整合**: 3 点フィットの `k` が Phase L の 1.306 と同等の値（1.2〜1.5 の範囲）に収まること、または乖離する場合は定数成分 `c` が顕著に効いている証拠として解釈
6. **VRAM 整合**: `sched_reserve` の値と `gpu_post_run*.csv` の差分が Phase L 同様（fa=1 比較ではないので差分の直接確認は不可、代わりに各 ctx での GPU 使用量総和が compute buffer 総和 + model weight + KV cache のオーダーで辻褄が合うこと）

## スコープ外（Phase N 以降）

- ctx=512 / 256 の更に極小 ctx
- fa=1 側の同 ctx スキャン
- q8_0 KV × fa=0 × ctx=4k の組み合わせ
- llama.cpp ソースコードでの compute buffer 計算ロジック解析
