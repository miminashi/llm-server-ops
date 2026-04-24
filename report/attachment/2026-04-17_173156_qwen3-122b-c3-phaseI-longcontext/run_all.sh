#!/usr/bin/env bash
# Phase I 計測の一括実行
# 事前: llama-server が t120h-p100 で C-D3 構成で起動済み
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PID="${PID:?PID env required}"
echo "[run_all] PID=${PID}"
MASTER_LOG="${SCRIPT_DIR}/run_all.log"
echo "[run_all] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')" | tee "$MASTER_LOG"

run() {
  local tag="$1"
  local spec="$2"
  local runs="$3"
  echo "[run_all] ==== $tag (runs=$runs) ====" | tee -a "$MASTER_LOG"
  RUNS="$runs" bash measure_phaseI.sh "$PID" "$tag" "$spec" 2>&1 | tee -a "$MASTER_LOG"
  echo "[run_all] ---- $tag done ----" | tee -a "$MASTER_LOG"
}

# 1. セッション基準点（Phase H 同等 prompt）
run I_warmup  "Write a short haiku about autumn." 3

# 2-6. 5 サイズ（1k, 8k は 3 runs、長コンテキストは短縮）
run I_1k   "@${SCRIPT_DIR}/prompts/prompt_1k.txt"   3
run I_8k   "@${SCRIPT_DIR}/prompts/prompt_8k.txt"   3
run I_32k  "@${SCRIPT_DIR}/prompts/prompt_32k.txt"  2
run I_64k  "@${SCRIPT_DIR}/prompts/prompt_64k.txt"  1
run I_120k "@${SCRIPT_DIR}/prompts/prompt_120k.txt" 1

# 7. セッション終点（drift 検出）
run I_post "Write a short haiku about autumn." 1

echo "[run_all] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')" | tee -a "$MASTER_LOG"
