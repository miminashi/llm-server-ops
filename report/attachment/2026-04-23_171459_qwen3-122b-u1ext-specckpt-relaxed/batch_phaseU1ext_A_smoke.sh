#!/usr/bin/env bash
# batch_phaseU1ext_A_smoke.sh - Phase U-1-ext Config A dry probe
# B14b_ts_alt + ctx=16384 + --cache-ram 256 が OOM なしで run 2 以降走るか確認
# 1 prompt (prompt_1k) × 2 mode (OFF/ON) × warmup 2 + eval 2 = 8 run
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p startup_logs

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

KV="q8_0"
SM="layer"
CTX=16384
UB=256
THR=40
OT_TAG="B14bC16k"
OT_REGEX='blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU'
TS="11,12,13,14"

# Config A 共通: --cache-ram 256 (OFF/ON 両方に適用し公平比較)
# ON 時のみさらに spec ckpt フラグを追加
COMMON_ARGS="${COMMON_ARGS:---cache-ram 256}"
SPEC_ON_ARGS="${SPEC_ON_ARGS:---spec-type ngram-mod --ctx-checkpoints 4 --spec-ngram-size-n 24 --draft-min 48 --draft-max 64}"

CONDITIONS=(
  "OFF_prompt1k_smoke#OFF#prompt_1k.txt"
  "ON_prompt1k_smoke#ON#prompt_1k.txt"
)

echo "[U1ext-A-smoke] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
echo "[U1ext-A-smoke] COMMON_ARGS=${COMMON_ARGS}"
echo "[U1ext-A-smoke] SPEC_ON_ARGS=${SPEC_ON_ARGS}"

for COND in "${CONDITIONS[@]}"; do
  IFS='#' read -r LABEL MODE PROMPT_BN <<< "$COND"
  PROMPT_FILE="${SCRIPT_DIR}/prompts/${PROMPT_BN}"

  if [ "$MODE" = "ON" ]; then
    EXTRA_ARGS="$COMMON_ARGS $SPEC_ON_ARGS"
    EXTRA_TAG="specON"
  else
    EXTRA_ARGS="$COMMON_ARGS"
    EXTRA_TAG="specOFF"
  fi

  TAG_COND="U1ext_${OT_TAG}_${LABEL}_t${THR}_kv${KV}_sm${SM}_ctx${CTX}_ub${UB}"

  echo "[U1ext-A-smoke] ================================"
  echo "[U1ext-A-smoke] label=${LABEL} mode=${MODE} at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[U1ext-A-smoke] EXTRA_ARGS=${EXTRA_ARGS}"
  echo "[U1ext-A-smoke] ================================"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  TS="$TS" OT_TAG="$OT_TAG" OT_REGEX="$OT_REGEX" \
    FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
    CACHE_TYPE_K="$KV" CACHE_TYPE_V="$KV" SPLIT_MODE="$SM" THREADS="$THR" \
    EXTRA_ARGS="$EXTRA_ARGS" EXTRA_TAG="$EXTRA_TAG" \
    bash start_phaseU1ext.sh > "start_stdout_${TAG_COND}.log" 2>&1 &
  START_PID=$!

  healthy=0
  for i in $(seq 1 60); do
    if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
      echo "[U1ext-A-smoke] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    if ! kill -0 "$START_PID" 2>/dev/null; then break; fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[U1ext-A-smoke] ERROR: health never OK for label=${LABEL}" >&2
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
    echo "[U1ext-A-smoke] ERROR: PID not found for label=${LABEL}" >&2
    continue
  fi
  echo "[U1ext-A-smoke] PID=$PID"

  TS_TAG="_ts$(echo "$TS" | tr , -)"
  REMOTE_LOG_NAME="llama-server_phaseU1ext_${OT_TAG}_t${THR}_sm${SM}_k${KV}_v${KV}_fa1_ctx${CTX}_b${UB}_ub${UB}${TS_TAG}_${EXTRA_TAG}.log"

  # startup 初期ログを取得（eval 前）
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/${REMOTE_LOG_NAME}" \
    > "startup_logs/${TAG_COND}_preeval.log"
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "nvidia-smi --query-gpu=index,memory.total,memory.used,memory.free --format=csv" \
    > "startup_logs/${TAG_COND}_nvidia_smi.csv" 2>&1 || true

  PID="$PID" TAG_PREFIX="${TAG_COND}" PROMPT_FILE="$PROMPT_FILE" \
    WARMUP_RUNS=2 EVAL_RUNS=2 \
    bash run_all_phaseU1ext.sh > "run_${TAG_COND}.log" 2>&1 || {
      echo "[U1ext-A-smoke] run_all FAILED for ${LABEL}, continuing" >&2
  }
  echo "[U1ext-A-smoke] measure done"

  # eval 後のサーバログを fetch（spec stats が書かれる可能性）
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/${REMOTE_LOG_NAME}" \
    > "startup_logs/${TAG_COND}.log" 2>&1 || true

  # /slots / /metrics を叩いて spec stats 取得
  curl -sS -m 10 "http://10.1.4.14:8000/slots" > "startup_logs/${TAG_COND}_slots.json" 2>&1 || true
  curl -sS -m 10 "http://10.1.4.14:8000/metrics" > "startup_logs/${TAG_COND}_metrics.txt" 2>&1 || true

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[U1ext-A-smoke] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
