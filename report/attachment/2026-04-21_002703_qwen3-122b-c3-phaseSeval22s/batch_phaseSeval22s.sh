#!/usr/bin/env bash
# batch_phaseSeval22s.sh - Phase S-eval-22session 3 条件バッチ (ub=1584/1586/1664 × ctx=32768)
# Phase S-eval / cross / 3s / 4s / 5s / 6s / 7s / 8s / 9s / 10s / 11s / 12s / 13s / 14s / 15s / 16s / 17s / 18s / 19s / 20s / 21s と同条件を第 22 session として再実施し、session 間の mean 変動を定量化
# 各 ub で warmup 2 run + 1k eval 5 run を実施
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

CTX=32768
UBS=(1584 1586 1664)

echo "[batchSeval22s] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"

for UB in "${UBS[@]}"; do
  echo "[batchSeval22s] ================================"
  echo "[batchSeval22s] cond: ctx=$CTX ub=$UB at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchSeval22s] ================================"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
    bash start_phaseSeval22s.sh > "start_stdout_Seval22s_ctx${CTX}_ub${UB}.log" 2>&1 &
  START_PID=$!

  healthy=0
  for i in $(seq 1 80); do
    if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
      echo "[batchSeval22s] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchSeval22s] ERROR: health never OK for ctx=$CTX ub=$UB" >&2
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
    echo "[batchSeval22s] ERROR: PID not found for ctx=$CTX ub=$UB" >&2
    exit 2
  fi
  echo "[batchSeval22s] PID=$PID"

  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/llama-server_phaseSeval22s_fa1_ctx${CTX}_b${UB}_ub${UB}.log" \
    > "startup_logs/fa1_ctx${CTX}_b${UB}_ub${UB}.log"
  echo "[batchSeval22s] startup log saved ($(wc -l < startup_logs/fa1_ctx${CTX}_b${UB}_ub${UB}.log) lines)"

  PID="$PID" TAG_PREFIX="Seval22s_fa1_ctx${CTX}_ub${UB}" WARMUP_RUNS=2 EVAL_RUNS=5 \
    bash run_all.sh > "run_Seval22s_ctx${CTX}_ub${UB}.log" 2>&1
  echo "[batchSeval22s] measure done ($(tail -1 run_Seval22s_ctx${CTX}_ub${UB}.log))"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchSeval22s] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
