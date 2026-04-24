#!/usr/bin/env bash
# run_all_phaseU1.sh - 1 server × 1 prompt を warmup + eval 実行
# 環境変数:
#   PID           (必須) llama-server PID
#   TAG_PREFIX    (必須) 例 "U1_B14b_specOFF_prompt1k"
#   PROMPT_FILE   (必須) /tmp/phaseU1/prompts/xxx.txt
#   WARMUP_RUNS   (省略時 2)
#   EVAL_RUNS     (省略時 5)
#   COOLDOWN      (省略時 60)
#   HOST          (省略時 t120h-p100)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PID="${PID:?PID env required}"
TAG_PREFIX="${TAG_PREFIX:?TAG_PREFIX env required}"
PROMPT_FILE="${PROMPT_FILE:?PROMPT_FILE env required}"
WARMUP_RUNS="${WARMUP_RUNS:-2}"
EVAL_RUNS="${EVAL_RUNS:-5}"
COOLDOWN="${COOLDOWN:-60}"
HOST="${HOST:-t120h-p100}"

if [ ! -f "$PROMPT_FILE" ]; then
  echo "[run_all_phaseU1] ERROR: prompt file not found: $PROMPT_FILE" >&2
  exit 1
fi

MASTER_LOG="${SCRIPT_DIR}/run_all_${TAG_PREFIX}.log"
echo "[run_all_phaseU1] PID=${PID} TAG_PREFIX=${TAG_PREFIX} PROMPT_FILE=${PROMPT_FILE}" | tee "$MASTER_LOG"
echo "[run_all_phaseU1] WARMUP=${WARMUP_RUNS} EVAL=${EVAL_RUNS}" | tee -a "$MASTER_LOG"
echo "[run_all_phaseU1] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')" | tee -a "$MASTER_LOG"

export HOST COOLDOWN

run_measure() {
  local tag="$1"
  local spec="$2"
  local runs="$3"
  echo "[run_all_phaseU1] ==== $tag (runs=$runs) ====" | tee -a "$MASTER_LOG"
  RUNS="$runs" bash measure_phaseT5.sh "$PID" "$tag" "$spec" 2>&1 | tee -a "$MASTER_LOG"
  echo "[run_all_phaseU1] ---- $tag done ----" | tee -a "$MASTER_LOG"
}

run_measure "${TAG_PREFIX}_warmup" "Write a short haiku about autumn." "$WARMUP_RUNS"
run_measure "${TAG_PREFIX}_eval"   "@${PROMPT_FILE}" "$EVAL_RUNS"

echo "[run_all_phaseU1] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')" | tee -a "$MASTER_LOG"
