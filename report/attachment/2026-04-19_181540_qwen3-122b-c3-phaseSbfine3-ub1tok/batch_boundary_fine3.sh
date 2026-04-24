#!/usr/bin/env bash
# Phase Sb-fine3 4 条件バッチ計測 (ctx=32768 × ub=1585/1586/1588/1592)
# CUDA0 区分境界 ub* を 1-4 token 精度で絞り込む目的（ub* ∈ (1584, 1600] を (1584, 1585] or (1585, 1586] or ... に細分化）
# 改善: ssh -f の stdout が tail pipe に残って親 wait がハングする問題を回避するため、
#       start_phaseSbf3.sh の stdout を file に redirect し、パイプを使わない
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

CONDS=(
  "32768 1585"
  "32768 1586"
  "32768 1588"
  "32768 1592"
)

echo "[batchSbf3] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"

for cond in "${CONDS[@]}"; do
  read -r CTX UB <<< "$cond"
  echo "[batchSbf3] ================================"
  echo "[batchSbf3] cond: ctx=$CTX ub=$UB at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchSbf3] ================================"

  # stop any previous server
  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  # start (stdout to file, 非パイプ化)
  FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
    bash start_phaseSbf3.sh > "start_stdout_Sbf3_ctx${CTX}_ub${UB}.log" 2>&1 &
  START_PID=$!

  # wait for health (curl with -m 5 timeout)
  healthy=0
  for i in $(seq 1 80); do
    if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
      echo "[batchSbf3] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchSbf3] ERROR: health never OK for ctx=$CTX ub=$UB" >&2
    kill -9 "$START_PID" 2>/dev/null || true
    exit 3
  fi

  # ensure start_phaseSbf3.sh has exited (wait with timeout via kill-0 polling)
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
    echo "[batchSbf3] ERROR: PID not found for ctx=$CTX ub=$UB" >&2
    exit 2
  fi
  echo "[batchSbf3] PID=$PID"

  # save startup log
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/llama-server_phaseSbf3_fa1_ctx${CTX}_b${UB}_ub${UB}.log" \
    > "startup_logs/fa1_ctx${CTX}_b${UB}_ub${UB}.log"
  echo "[batchSbf3] startup log saved ($(wc -l < startup_logs/fa1_ctx${CTX}_b${UB}_ub${UB}.log) lines)"

  # measure
  PID="$PID" TAG_PREFIX="Sbf3_f16_fa1_ctx${CTX}_b${UB}_ub${UB}" SIZES="warmup 1k" \
    GATE_SIZES="1k" GATE_MIB=1500 bash run_all.sh > "run_Sbf3_ctx${CTX}_ub${UB}.log" 2>&1
  echo "[batchSbf3] measure done ($(tail -1 run_Sbf3_ctx${CTX}_ub${UB}.log))"

  # stop
  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchSbf3] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
