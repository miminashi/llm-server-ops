#!/usr/bin/env bash
# batch_phaseT5.sh - Phase T-5 OT aggressive reduction (B28 VRAM 限界探索)
# 5 条件 × (warmup 2 run + 1k eval 5 run) = 35 measurement
#   1. B32-t40 (drift 起点、T-4 B32-t40=15.494 再現)
#   2. B30-t40 (中間点、B32→B28 monotonic 検証)
#   3. B28-t40 (本命、VRAM 限界、新記録狙い)
#   4. B28-t32 (層=28 ≠ threads=32 不一致 control)
#   5. B32-t40 (drift 終点)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p startup_logs

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

CTX=32768
UB=1586
KV="q8_0"
SM="layer"

# 条件定義 (順序固定): "LABEL#OT_TAG#THREADS#OT_REGEX"
# 区切り文字 # を使用 (OT_REGEX 内の | との衝突回避)
# LABEL は session drift 分離のため、同一 OT_TAG でも run ID 別名にする
CONDITIONS=(
  'B32a#B32#40#blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-3])\.ffn_.*_exps\.weight=CPU'
  'B30#B30#40#blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-1])\.ffn_.*_exps\.weight=CPU'
  'B28#B28#40#blk\.([0-9]|1[0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
  'B28c#B28#32#blk\.([0-9]|1[0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
  'B32z#B32#40#blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-3])\.ffn_.*_exps\.weight=CPU'
)

echo "[batchT5] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
echo "[batchT5] total conditions: ${#CONDITIONS[@]}"

for COND in "${CONDITIONS[@]}"; do
  IFS='#' read -r LABEL OT_TAG THR OT_REGEX <<< "$COND"
  TAG_COND="${LABEL}_t${THR}_kv${KV}_sm${SM}_ctx${CTX}_ub${UB}"
  echo "[batchT5] ================================"
  echo "[batchT5] cond: label=${LABEL} ot=${OT_TAG} threads=${THR} at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchT5]   regex=${OT_REGEX}"
  echo "[batchT5] ================================"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
    CACHE_TYPE_K="$KV" CACHE_TYPE_V="$KV" SPLIT_MODE="$SM" THREADS="$THR" \
    OT_TAG="$OT_TAG" OT_REGEX="$OT_REGEX" \
    bash start_phaseT5.sh > "start_stdout_T5_${TAG_COND}.log" 2>&1 &
  START_PID=$!

  healthy=0
  for i in $(seq 1 80); do
    if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
      echo "[batchT5] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    if ! kill -0 "$START_PID" 2>/dev/null; then
      echo "[batchT5] start_phaseT5.sh exited early for label=${LABEL} threads=${THR}" >&2
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchT5] ERROR: health never OK for label=${LABEL} threads=${THR} (start_stdout に OOM/reject の可能性)" >&2
    tail -60 "start_stdout_T5_${TAG_COND}.log" >&2 || true
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
    echo "[batchT5] ERROR: PID not found for label=${LABEL} threads=${THR}" >&2
    continue
  fi
  echo "[batchT5] PID=$PID"

  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/llama-server_phaseT5_${OT_TAG}_t${THR}_sm${SM}_k${KV}_v${KV}_fa1_ctx${CTX}_b${UB}_ub${UB}.log" \
    > "startup_logs/T5_${TAG_COND}.log"
  echo "[batchT5] startup log saved ($(wc -l < startup_logs/T5_${TAG_COND}.log) lines)"

  PID="$PID" TAG_PREFIX="T5_${TAG_COND}" WARMUP_RUNS=2 EVAL_RUNS=5 \
    bash run_all.sh > "run_T5_${TAG_COND}.log" 2>&1
  echo "[batchT5] measure done ($(tail -1 run_T5_${TAG_COND}.log))"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchT5] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
