#!/usr/bin/env bash
# batch_U1_retry_nockptcache.sh - Phase U-1: ctx-checkpoints 0 + cache-ram 0
# prompt cache (cache-ram) が Run 1 後に 153 MiB 追加 allocate → Run 2 で OOM (device 3)
# 対策: --cache-ram 0 で prompt cache 無効化
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

# cache-ram 0 で prompt cache 無効 + ctx-checkpoints 0 で ckpt 無効 + spec decoding (ngram-mod)
SPEC_ON_ARGS="${SPEC_ON_ARGS:---spec-type ngram-mod --ctx-checkpoints 0 --spec-ngram-size-n 24 --draft-min 48 --draft-max 64 --cache-ram 0}"

CONDITIONS=(
  "ON_prompt1k_nockptcache#ON#prompt_1k.txt"
  "ON_code_nockptcache#ON#prompt_code.txt"
  "ON_repetitive_nockptcache#ON#prompt_repetitive.txt"
)

SKIP_LABELS="${SKIP_LABELS:-}"

echo "[batchU1-nockptcache] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
echo "[batchU1-nockptcache] SPEC_ON_ARGS=${SPEC_ON_ARGS}"

for COND in "${CONDITIONS[@]}"; do
  IFS='#' read -r LABEL MODE PROMPT_BN <<< "$COND"
  PROMPT_FILE="${SCRIPT_DIR}/prompts/${PROMPT_BN}"

  if [[ ",${SKIP_LABELS}," == *",${LABEL},"* ]]; then
    echo "[batchU1-nockptcache] SKIP label=${LABEL}"
    continue
  fi

  EXTRA_ARGS="$SPEC_ON_ARGS"
  EXTRA_TAG="specNoCkptCache"
  TAG_COND="U1_${OT_TAG}_${LABEL}_t${THR}_kv${KV}_sm${SM}_ctx${CTX}_ub${UB}"

  echo "[batchU1-nockptcache] ================================"
  echo "[batchU1-nockptcache] cond: label=${LABEL} mode=${MODE} prompt=${PROMPT_BN} at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchU1-nockptcache] ================================"

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
      echo "[batchU1-nockptcache] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    if ! kill -0 "$START_PID" 2>/dev/null; then
      echo "[batchU1-nockptcache] start exited early for label=${LABEL}" >&2
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchU1-nockptcache] ERROR: health never OK for label=${LABEL}" >&2
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
    echo "[batchU1-nockptcache] ERROR: PID not found for label=${LABEL}" >&2
    continue
  fi
  echo "[batchU1-nockptcache] PID=$PID"

  TS_TAG="_ts$(echo "$TS" | tr , -)"
  REMOTE_LOG_NAME="llama-server_phaseU1_${OT_TAG}_t${THR}_sm${SM}_k${KV}_v${KV}_fa1_ctx${CTX}_b${UB}_ub${UB}${TS_TAG}_${EXTRA_TAG}.log"
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/${REMOTE_LOG_NAME}" \
    > "startup_logs/${TAG_COND}.log"
  echo "[batchU1-nockptcache] startup log saved ($(wc -l < startup_logs/${TAG_COND}.log) lines)"

  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "nvidia-smi --query-gpu=index,memory.total,memory.used,memory.free --format=csv" \
    > "startup_logs/${TAG_COND}_nvidia_smi.csv" 2>&1 || true

  PID="$PID" TAG_PREFIX="${TAG_COND}" PROMPT_FILE="$PROMPT_FILE" \
    WARMUP_RUNS=2 EVAL_RUNS=5 \
    bash run_all_phaseU1.sh > "run_${TAG_COND}.log" 2>&1
  echo "[batchU1-nockptcache] measure done ($(tail -1 run_${TAG_COND}.log))"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchU1-nockptcache] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
