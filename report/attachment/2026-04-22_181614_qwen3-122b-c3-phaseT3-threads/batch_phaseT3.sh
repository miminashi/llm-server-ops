#!/usr/bin/env bash
# batch_phaseT3.sh - Phase T-3 threads 中間値スイープ
# THREADS {40, 36, 32, 28, 24} × KV=q8_0 × split=layer × ub=1586 = 5 条件
# 各条件 warmup 2 run + 1k eval 5 run
# 実行順: 40 (baseline) 先行で session drift 監視
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
# THREADS 降順: baseline 40 を先頭で session drift 監視
THREADS_LIST=(40 36 32 28 24)

echo "[batchT3] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"

for THR in "${THREADS_LIST[@]}"; do
  TAG_COND="t${THR}_kv${KV}_sm${SM}_ctx${CTX}_ub${UB}"
  echo "[batchT3] ================================"
  echo "[batchT3] cond: threads=${THR} split=${SM} kv=${KV} ctx=$CTX ub=$UB at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchT3] ================================"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
    CACHE_TYPE_K="$KV" CACHE_TYPE_V="$KV" SPLIT_MODE="$SM" THREADS="$THR" \
    bash start_phaseT3.sh > "start_stdout_T3_${TAG_COND}.log" 2>&1 &
  START_PID=$!

  healthy=0
  for i in $(seq 1 80); do
    if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
      echo "[batchT3] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    if ! kill -0 "$START_PID" 2>/dev/null; then
      echo "[batchT3] start_phaseT3.sh exited early for threads=$THR" >&2
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchT3] ERROR: health never OK for threads=$THR (start_stdout に OOM/reject の可能性)" >&2
    tail -60 "start_stdout_T3_${TAG_COND}.log" >&2 || true
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
    echo "[batchT3] ERROR: PID not found for threads=$THR" >&2
    continue
  fi
  echo "[batchT3] PID=$PID"

  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/llama-server_phaseT3_t${THR}_sm${SM}_k${KV}_v${KV}_fa1_ctx${CTX}_b${UB}_ub${UB}.log" \
    > "startup_logs/T3_${TAG_COND}.log"
  echo "[batchT3] startup log saved ($(wc -l < startup_logs/T3_${TAG_COND}.log) lines)"

  PID="$PID" TAG_PREFIX="T3_${TAG_COND}" WARMUP_RUNS=2 EVAL_RUNS=5 \
    bash run_all.sh > "run_T3_${TAG_COND}.log" 2>&1
  echo "[batchT3] measure done ($(tail -1 run_T3_${TAG_COND}.log))"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchT3] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
