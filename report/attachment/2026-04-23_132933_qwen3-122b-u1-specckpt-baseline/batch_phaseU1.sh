#!/usr/bin/env bash
# batch_phaseU1.sh - Phase U-1: spec ckpt OFF/ON A/B on B14b_ts_alt
# 6 条件 (2 mode × 3 prompt) × (warmup 2 + eval 5)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p startup_logs

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

# B14b_ts_alt 固定 (Phase T-5a-ts2 現最良, 18.664 t/s)
KV="q8_0"
SM="layer"
CTX=32768
UB=256
THR=40
OT_TAG="B14b"
OT_REGEX='blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU'
TS="11,12,13,14"

# spec ckpt ON 時の追加フラグ (Step 3 dry probe で確定)
# llama.cpp PR #19493 + 関連 fix 後 master:
#   --spec-type ngram-mod        : ngram ベース draft 生成 (draft model 不要, default: none)
#   --ctx-checkpoints 4          : 保持する context checkpoint 数 (default 32, PR #15293)
#   --spec-ngram-size-n 24       : lookup n-gram 長 (default 12)
#   --draft-min 48               : draft token 最小値 (default 0)
#   --draft-max 64               : draft token 最大値 (default 16)
# 注: --spec-use-checkpoints は master HEAD では存在しない (PR #22114 refactor 後)
SPEC_ON_ARGS="${SPEC_ON_ARGS:---spec-type ngram-mod --ctx-checkpoints 4 --spec-ngram-size-n 24 --draft-min 48 --draft-max 64}"

# 条件定義: "LABEL#MODE#PROMPT_BASENAME"
# MODE は OFF / ON, prompt は prompts/ 配下 (.txt 付きで指定)
CONDITIONS=(
  "OFF_prompt1k#OFF#prompt_1k.txt"
  "ON_prompt1k#ON#prompt_1k.txt"
  "OFF_code#OFF#prompt_code.txt"
  "ON_code#ON#prompt_code.txt"
  "OFF_repetitive#OFF#prompt_repetitive.txt"
  "ON_repetitive#ON#prompt_repetitive.txt"
)

SKIP_LABELS="${SKIP_LABELS:-}"

echo "[batchU1] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
echo "[batchU1] total conditions: ${#CONDITIONS[@]} (skip: ${SKIP_LABELS:-none})"
echo "[batchU1] SPEC_ON_ARGS=${SPEC_ON_ARGS}"

for COND in "${CONDITIONS[@]}"; do
  IFS='#' read -r LABEL MODE PROMPT_BN <<< "$COND"
  PROMPT_FILE="${SCRIPT_DIR}/prompts/${PROMPT_BN}"

  if [[ ",${SKIP_LABELS}," == *",${LABEL},"* ]]; then
    echo "[batchU1] SKIP label=${LABEL}"
    continue
  fi

  if [ "$MODE" = "ON" ]; then
    EXTRA_ARGS="$SPEC_ON_ARGS"
    EXTRA_TAG="specON"
  else
    EXTRA_ARGS=""
    EXTRA_TAG="specOFF"
  fi

  TAG_COND="U1_${OT_TAG}_${LABEL}_t${THR}_kv${KV}_sm${SM}_ctx${CTX}_ub${UB}"

  echo "[batchU1] ================================"
  echo "[batchU1] cond: label=${LABEL} mode=${MODE} prompt=${PROMPT_BN} at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchU1] ================================"

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
      echo "[batchU1] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    if ! kill -0 "$START_PID" 2>/dev/null; then
      echo "[batchU1] start exited early for label=${LABEL}" >&2
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchU1] ERROR: health never OK for label=${LABEL}" >&2
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
    echo "[batchU1] ERROR: PID not found for label=${LABEL}" >&2
    continue
  fi
  echo "[batchU1] PID=$PID"

  TS_TAG="_ts$(echo "$TS" | tr , -)"
  REMOTE_LOG_NAME="llama-server_phaseU1_${OT_TAG}_t${THR}_sm${SM}_k${KV}_v${KV}_fa1_ctx${CTX}_b${UB}_ub${UB}${TS_TAG}_${EXTRA_TAG}.log"
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/${REMOTE_LOG_NAME}" \
    > "startup_logs/${TAG_COND}.log"
  echo "[batchU1] startup log saved ($(wc -l < startup_logs/${TAG_COND}.log) lines)"

  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "nvidia-smi --query-gpu=index,memory.total,memory.used,memory.free --format=csv" \
    > "startup_logs/${TAG_COND}_nvidia_smi.csv" 2>&1 || true

  PID="$PID" TAG_PREFIX="${TAG_COND}" PROMPT_FILE="$PROMPT_FILE" \
    WARMUP_RUNS=2 EVAL_RUNS=5 \
    bash run_all_phaseU1.sh > "run_${TAG_COND}.log" 2>&1
  echo "[batchU1] measure done ($(tail -1 run_${TAG_COND}.log))"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchU1] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
