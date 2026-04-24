#!/usr/bin/env bash
# batch_phaseSeval55s.sh - Phase S-eval-55session 3 条件バッチ (ub=1584/1586/1664 × ctx=32768)
# Phase S-eval / cross / 3s ... 53s と同条件を第 55 session として再実施し、session 間の mean 変動を定量化
# 各 ub で warmup 2 run + 1k eval 5 run を実施
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

CTX=32768
UBS=(1584 1586 1664)

echo "[batchSeval55s] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"

for UB in "${UBS[@]}"; do
  echo "[batchSeval55s] ================================"
  echo "[batchSeval55s] cond: ctx=$CTX ub=$UB at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchSeval55s] ================================"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
    bash start_phaseSeval55s.sh > "start_stdout_Seval55s_ctx${CTX}_ub${UB}.log" 2>&1 &
  START_PID=$!

  healthy=0
  for i in $(seq 1 80); do
    if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
      echo "[batchSeval55s] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchSeval55s] ERROR: health never OK for ctx=$CTX ub=$UB" >&2
    kill -9 "$START_PID" 2>/dev/null || true
    exit 3
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
    echo "[batchSeval55s] ERROR: PID not found for ctx=$CTX ub=$UB" >&2
    exit 2
  fi
  echo "[batchSeval55s] PID=$PID"

  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/llama-server_phaseSeval55s_fa1_ctx${CTX}_b${UB}_ub${UB}.log" \
    > "startup_logs/fa1_ctx${CTX}_b${UB}_ub${UB}.log"
  echo "[batchSeval55s] startup log saved ($(wc -l < startup_logs/fa1_ctx${CTX}_b${UB}_ub${UB}.log) lines)"

  PID="$PID" TAG_PREFIX="Seval55s_fa1_ctx${CTX}_ub${UB}" WARMUP_RUNS=2 EVAL_RUNS=5 \
    bash run_all.sh > "run_Seval55s_ctx${CTX}_ub${UB}.log" 2>&1
  echo "[batchSeval55s] measure done ($(tail -1 run_Seval55s_ctx${CTX}_ub${UB}.log))"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchSeval55s] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
