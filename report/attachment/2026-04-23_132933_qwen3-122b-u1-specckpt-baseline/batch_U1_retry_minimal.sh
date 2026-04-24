#!/usr/bin/env bash
# batch_U1_retry_minimal.sh - draft-max default (16) で spec decoding の最小動作確認
# 1 条件のみ: ON_prompt1k_minimal
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p startup_logs

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

KV="q8_0"
SM="layer"
CTX=32768
UB=256
THR=40
OT_TAG="B14b"
OT_REGEX='blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU'
TS="11,12,13,14"

# 最小構成: draft-max default (16), ctx-checkpoints 0, cache-ram 0
SPEC_ON_ARGS="${SPEC_ON_ARGS:---spec-type ngram-mod --ctx-checkpoints 0 --spec-ngram-size-n 24 --cache-ram 0}"

CONDITIONS=(
  "ON_prompt1k_minimal#ON#prompt_1k.txt"
  "ON_code_minimal#ON#prompt_code.txt"
  "ON_repetitive_minimal#ON#prompt_repetitive.txt"
)

SKIP_LABELS="${SKIP_LABELS:-}"

echo "[batchU1-minimal] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
echo "[batchU1-minimal] SPEC_ON_ARGS=${SPEC_ON_ARGS}"

for COND in "${CONDITIONS[@]}"; do
  IFS='#' read -r LABEL MODE PROMPT_BN <<< "$COND"
  PROMPT_FILE="${SCRIPT_DIR}/prompts/${PROMPT_BN}"

  if [[ ",${SKIP_LABELS}," == *",${LABEL},"* ]]; then
    echo "[batchU1-minimal] SKIP label=${LABEL}"
    continue
  fi

  EXTRA_ARGS="$SPEC_ON_ARGS"
  EXTRA_TAG="specMinimal"
  TAG_COND="U1_${OT_TAG}_${LABEL}_t${THR}_kv${KV}_sm${SM}_ctx${CTX}_ub${UB}"

  echo "[batchU1-minimal] ================================"
  echo "[batchU1-minimal] cond: label=${LABEL} mode=${MODE} at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchU1-minimal] ================================"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  TS="$TS" OT_TAG="$OT_TAG" OT_REGEX="$OT_REGEX" \
    FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
    CACHE_TYPE_K="$KV" CACHE_TYPE_V="$KV" SPLIT_MODE="$SM" THREADS="$THR" \
    EXTRA_ARGS="$EXTRA_ARGS" EXTRA_TAG="$EXTRA_TAG" \
    bash start_phaseU1.sh > "start_stdout_${TAG_COND}.log" 2>&1 &
  START_PID=$!

  healthy=0
  for i in $(seq 1 60); do
    if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
      echo "[batchU1-minimal] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    if ! kill -0 "$START_PID" 2>/dev/null; then break; fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchU1-minimal] ERROR: health never OK for label=${LABEL}" >&2
    tail -120 "start_stdout_${TAG_COND}.log" >&2 || true
    kill -9 "$START_PID" 2>/dev/null || true
    bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
    sleep 5
    continue
  fi

  for i in 1 2 3 4 5 6; do
    if ! kill -0 "$START_PID" 2>/dev/null; then break; fi
    sleep 2
  done
  kill "$START_PID" 2>/dev/null || true
  wait "$START_PID" 2>/dev/null || true

  PID=$(ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "ps -eo pid,comm | awk '\$2==\"llama-server\"{print \$1;exit}'" | tr -d '[:space:]')
  if [ -z "$PID" ]; then
    echo "[batchU1-minimal] ERROR: PID not found for label=${LABEL}" >&2
    continue
  fi
  echo "[batchU1-minimal] PID=$PID"

  TS_TAG="_ts$(echo "$TS" | tr , -)"
  REMOTE_LOG_NAME="llama-server_phaseU1_${OT_TAG}_t${THR}_sm${SM}_k${KV}_v${KV}_fa1_ctx${CTX}_b${UB}_ub${UB}${TS_TAG}_${EXTRA_TAG}.log"
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/${REMOTE_LOG_NAME}" \
    > "startup_logs/${TAG_COND}.log"
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "nvidia-smi --query-gpu=index,memory.total,memory.used,memory.free --format=csv" \
    > "startup_logs/${TAG_COND}_nvidia_smi.csv" 2>&1 || true

  PID="$PID" TAG_PREFIX="${TAG_COND}" PROMPT_FILE="$PROMPT_FILE" \
    WARMUP_RUNS=2 EVAL_RUNS=5 \
    bash run_all_phaseU1.sh > "run_${TAG_COND}.log" 2>&1
  echo "[batchU1-minimal] measure done ($(tail -1 run_${TAG_COND}.log))"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchU1-minimal] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
