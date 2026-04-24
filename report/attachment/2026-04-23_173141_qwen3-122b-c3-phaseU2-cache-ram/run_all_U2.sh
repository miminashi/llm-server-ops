#!/usr/bin/env bash
# run_all_U2.sh - Phase U-2 regression eval (既存 measure_phaseT5.sh 流用)
# warmup (短 prompt marker 付き) + 1k (prompt_1k.txt marker 付き) = cache miss 強制
# Phase T-5a-ts2 baseline と比較可能な形式で結果を保存する。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PID="${PID:?PID env required}"
TAG_PREFIX="${TAG_PREFIX:?TAG_PREFIX env required}"
WARMUP_RUNS="${WARMUP_RUNS:-2}"
EVAL_RUNS="${EVAL_RUNS:-5}"
COOLDOWN="${COOLDOWN:-60}"
HOST="${HOST:-t120h-p100}"

# 既存 measure_phaseT5.sh へのパス (marker 付き cache-miss 保証)
T5A_DIR="/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-23_093629_qwen3-122b-c3-phaseT5a-ts2"
MEASURE="${T5A_DIR}/measure_phaseT5.sh"
PROMPT_1K="${T5A_DIR}/prompts/prompt_1k.txt"

MASTER_LOG="${SCRIPT_DIR}/run_all_U2_${TAG_PREFIX}.log"
echo "[run_all_U2] PID=${PID} TAG_PREFIX=${TAG_PREFIX} WARMUP_RUNS=${WARMUP_RUNS} EVAL_RUNS=${EVAL_RUNS}" | tee "$MASTER_LOG"
echo "[run_all_U2] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')" | tee -a "$MASTER_LOG"

export HOST COOLDOWN

run_measure() {
  local tag="$1"
  local spec="$2"
  local runs="$3"
  echo "[run_all_U2] ==== $tag (runs=$runs) ====" | tee -a "$MASTER_LOG"
  RUNS="$runs" bash "$MEASURE" "$PID" "$tag" "$spec" 2>&1 | tee -a "$MASTER_LOG"
  echo "[run_all_U2] ---- $tag done ----" | tee -a "$MASTER_LOG"
}

run_measure "${TAG_PREFIX}_warmup" "Write a short haiku about autumn." "$WARMUP_RUNS"
run_measure "${TAG_PREFIX}_1k" "@${PROMPT_1K}" "$EVAL_RUNS"

echo "[run_all_U2] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')" | tee -a "$MASTER_LOG"
