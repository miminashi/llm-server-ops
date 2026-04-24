#!/usr/bin/env bash
# batch_phaseT1.sh - Phase T-1 KV cache 量子化スイープ
# KV 型 (f16/q8_0/q4_0/q4_1) × ub (1586/1664) = 8 条件
# 各 ub で warmup 2 run + 1k eval 5 run
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p startup_logs

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

CTX=32768
KV_TYPES=(f16 q8_0 q4_0 q4_1)
UBS=(1586 1664)

echo "[batchT1] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"

for KV in "${KV_TYPES[@]}"; do
  for UB in "${UBS[@]}"; do
    TAG_COND="kv${KV}_ctx${CTX}_ub${UB}"
    echo "[batchT1] ================================"
    echo "[batchT1] cond: kv=$KV ctx=$CTX ub=$UB at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
    echo "[batchT1] ================================"

    bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
    sleep 5

    FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
      CACHE_TYPE_K="$KV" CACHE_TYPE_V="$KV" \
      bash start_phaseT1.sh > "start_stdout_T1_${TAG_COND}.log" 2>&1 &
    START_PID=$!

    healthy=0
    for i in $(seq 1 80); do
      if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
        echo "[batchT1] /health OK after ${i}*5s"
        healthy=1
        break
      fi
      if ! kill -0 "$START_PID" 2>/dev/null; then
        echo "[batchT1] start_phaseT1.sh exited early for kv=$KV ub=$UB" >&2
        break
      fi
      sleep 5
    done

    if [ "$healthy" -ne 1 ]; then
      echo "[batchT1] ERROR: health never OK for kv=$KV ub=$UB (start_stdout に OOM/reject の可能性)" >&2
      tail -40 "start_stdout_T1_${TAG_COND}.log" >&2 || true
      kill -9 "$START_PID" 2>/dev/null || true
      # Fail-soft: 失敗した条件はスキップして次へ
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
      echo "[batchT1] ERROR: PID not found for kv=$KV ub=$UB" >&2
      continue
    fi
    echo "[batchT1] PID=$PID"

    ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
      "cat /tmp/llama-server_phaseT1_k${KV}_v${KV}_fa1_ctx${CTX}_b${UB}_ub${UB}.log" \
      > "startup_logs/T1_${TAG_COND}.log"
    echo "[batchT1] startup log saved ($(wc -l < startup_logs/T1_${TAG_COND}.log) lines)"

    PID="$PID" TAG_PREFIX="T1_${TAG_COND}" WARMUP_RUNS=2 EVAL_RUNS=5 \
      bash run_all.sh > "run_T1_${TAG_COND}.log" 2>&1
    echo "[batchT1] measure done ($(tail -1 run_T1_${TAG_COND}.log))"

    bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
    sleep 5
  done
done

echo "[batchT1] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
