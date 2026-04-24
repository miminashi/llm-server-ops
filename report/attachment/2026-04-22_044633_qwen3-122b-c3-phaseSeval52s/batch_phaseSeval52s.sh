#!/usr/bin/env bash
# batch_phaseSeval52s.sh - Phase S-eval-51session 3 条件バッチ (ub=1584/1586/1664 × ctx=32768)
# Phase S-eval / cross / 3s / 4s / 5s / 6s / 7s / 8s / 9s / 10s / 11s / 12s / 13s / 14s / 15s / 16s / 17s / 18s / 19s / 20s / 21s / 22s / 23s / 24s / 25s / 26s / 27s / 28s / 29s / 30s / 31s / 32s / 33s / 34s / 35s / 36s / 37s / 38s / 39s / 40s / 41s / 42s / 43s / 44s / 45s / 46s / 47s / 48s / 49s / 50s / 51s と同条件を第 52 session として再実施し、session 間の mean 変動を定量化
# 各 ub で warmup 2 run + 1k eval 5 run を実施
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

CTX=32768
UBS=(1584 1586 1664)

echo "[batchSeval52s] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"

for UB in "${UBS[@]}"; do
  echo "[batchSeval52s] ================================"
  echo "[batchSeval52s] cond: ctx=$CTX ub=$UB at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchSeval52s] ================================"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
    bash start_phaseSeval52s.sh > "start_stdout_Seval52s_ctx${CTX}_ub${UB}.log" 2>&1 &
  START_PID=$!

  healthy=0
  for i in $(seq 1 80); do
    if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
      echo "[batchSeval52s] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchSeval52s] ERROR: health never OK for ctx=$CTX ub=$UB" >&2
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
    echo "[batchSeval52s] ERROR: PID not found for ctx=$CTX ub=$UB" >&2
    exit 2
  fi
  echo "[batchSeval52s] PID=$PID"

  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/llama-server_phaseSeval52s_fa1_ctx${CTX}_b${UB}_ub${UB}.log" \
    > "startup_logs/fa1_ctx${CTX}_b${UB}_ub${UB}.log"
  echo "[batchSeval52s] startup log saved ($(wc -l < startup_logs/fa1_ctx${CTX}_b${UB}_ub${UB}.log) lines)"

  PID="$PID" TAG_PREFIX="Seval52s_fa1_ctx${CTX}_ub${UB}" WARMUP_RUNS=2 EVAL_RUNS=5 \
    bash run_all.sh > "run_Seval52s_ctx${CTX}_ub${UB}.log" 2>&1
  echo "[batchSeval52s] measure done ($(tail -1 run_Seval52s_ctx${CTX}_ub${UB}.log))"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchSeval52s] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
