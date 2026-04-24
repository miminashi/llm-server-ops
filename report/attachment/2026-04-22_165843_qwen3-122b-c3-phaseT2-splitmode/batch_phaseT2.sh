#!/usr/bin/env bash
# batch_phaseT2.sh - Phase T-2 split-mode row vs layer 比較
# split-mode {layer, row} × KV {f16, q8_0} × ub {1586} = 4 条件
# 各条件 warmup 2 run + 1k eval 5 run
# 実行順: row 先行で OT/split-mode 非対応を早期検知 (fail-soft)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p startup_logs

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

CTX=32768
UB=1586
# (split_mode:kv) ペアを 4 条件列挙。row を先にして早期失敗検知を優先
CONDITIONS=(
  "row:f16"
  "row:q8_0"
  "layer:f16"
  "layer:q8_0"
)

echo "[batchT2] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"

for COND in "${CONDITIONS[@]}"; do
  SM="${COND%%:*}"
  KV="${COND##*:}"
  TAG_COND="kv${KV}_sm${SM}_ctx${CTX}_ub${UB}"
  echo "[batchT2] ================================"
  echo "[batchT2] cond: split=${SM} kv=${KV} ctx=$CTX ub=$UB at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchT2] ================================"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
    CACHE_TYPE_K="$KV" CACHE_TYPE_V="$KV" SPLIT_MODE="$SM" \
    bash start_phaseT2.sh > "start_stdout_T2_${TAG_COND}.log" 2>&1 &
  START_PID=$!

  healthy=0
  for i in $(seq 1 80); do
    if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
      echo "[batchT2] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    if ! kill -0 "$START_PID" 2>/dev/null; then
      echo "[batchT2] start_phaseT2.sh exited early for split=$SM kv=$KV" >&2
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchT2] ERROR: health never OK for split=$SM kv=$KV (start_stdout に OOM/reject/split-mode 非対応の可能性)" >&2
    tail -60 "start_stdout_T2_${TAG_COND}.log" >&2 || true
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
    echo "[batchT2] ERROR: PID not found for split=$SM kv=$KV" >&2
    continue
  fi
  echo "[batchT2] PID=$PID"

  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/llama-server_phaseT2_sm${SM}_k${KV}_v${KV}_fa1_ctx${CTX}_b${UB}_ub${UB}.log" \
    > "startup_logs/T2_${TAG_COND}.log"
  echo "[batchT2] startup log saved ($(wc -l < startup_logs/T2_${TAG_COND}.log) lines)"

  PID="$PID" TAG_PREFIX="T2_${TAG_COND}" WARMUP_RUNS=2 EVAL_RUNS=5 \
    bash run_all.sh > "run_T2_${TAG_COND}.log" 2>&1
  echo "[batchT2] measure done ($(tail -1 run_T2_${TAG_COND}.log))"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchT2] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
