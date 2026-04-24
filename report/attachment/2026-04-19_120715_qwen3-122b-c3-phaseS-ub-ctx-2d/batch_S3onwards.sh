#!/usr/bin/env bash
# Phase S S3-S8 バッチ計測 (S1/S2 済のため)
# 改善: ssh -f の stdout が tail pipe に残って親 wait がハングする問題を回避するため、
#       start_phaseS.sh の stdout を file に redirect し、パイプを使わない
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

CONDS=(
  "32768 4096"
  "32768 8192"
  "65536 512"
  "65536 1024"
  "65536 4096"
  "65536 8192"
)

echo "[batch2] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"

for cond in "${CONDS[@]}"; do
  read -r CTX UB <<< "$cond"
  echo "[batch2] ================================"
  echo "[batch2] cond: ctx=$CTX ub=$UB at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batch2] ================================"

  # stop any previous server
  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  # start (stdout to file, 非パイプ化)
  FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
    bash start_phaseS.sh > "start_stdout_ctx${CTX}_ub${UB}.log" 2>&1 &
  START_PID=$!

  # wait for health (curl with -m 5 timeout)
  healthy=0
  for i in $(seq 1 80); do
    if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
      echo "[batch2] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batch2] ERROR: health never OK for ctx=$CTX ub=$UB" >&2
    kill -9 "$START_PID" 2>/dev/null || true
    exit 3
  fi

  # ensure start_phaseS.sh has exited (wait with timeout via kill-0 polling)
  for i in 1 2 3 4 5 6; do
    if ! kill -0 "$START_PID" 2>/dev/null; then break; fi
    sleep 2
  done
  # force-kill if still running (doesn't affect llama-server since it was detached)
  kill "$START_PID" 2>/dev/null || true
  wait "$START_PID" 2>/dev/null || true

  # get PID (short connect timeout to avoid hangs)
  PID=$(ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "ps -eo pid,comm | awk '\$2==\"llama-server\"{print \$1;exit}'" | tr -d '[:space:]')
  if [ -z "$PID" ]; then
    echo "[batch2] ERROR: PID not found for ctx=$CTX ub=$UB" >&2
    exit 2
  fi
  echo "[batch2] PID=$PID"

  # save startup log
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/llama-server_phaseS_fa1_ctx${CTX}_b${UB}_ub${UB}.log" \
    > "startup_logs/fa1_ctx${CTX}_b${UB}_ub${UB}.log"
  echo "[batch2] startup log saved ($(wc -l < startup_logs/fa1_ctx${CTX}_b${UB}_ub${UB}.log) lines)"

  # measure
  PID="$PID" TAG_PREFIX="S_f16_fa1_ctx${CTX}_b${UB}_ub${UB}" SIZES="warmup 1k" \
    GATE_SIZES="1k" GATE_MIB=1500 bash run_all.sh > "run_S_ctx${CTX}_ub${UB}.log" 2>&1
  echo "[batch2] measure done ($(tail -1 run_S_ctx${CTX}_ub${UB}.log))"

  # stop
  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batch2] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
