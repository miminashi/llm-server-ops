#!/usr/bin/env bash
# batch_phaseT4.sh - Phase T-4 OT pattern 層範囲スイープ
# 3 OT条件 × THREADS {32, 40} = 6 条件
#   A36 (baseline, T-3 と同 OT、36 層 CPU、blk 14-19 GPU、44-47 CPU)
#   B32 (44-47 GPU 戻し、32 層 CPU)  ← VRAM リスクあり
#   C40 (14-17 CPU 追加、40 層 CPU、GPU 残: 18-19 + 25-30)
# 各条件 warmup 2 run + 1k eval 5 run
# 実行順: A36-t40 (T-3 baseline 14.781 直接再現で session drift 監視) → A36-t32 →
#         C40-t40 → C40-t32 (低リスク 2 cond) → B32-t40 → B32-t32 (高リスク 2 cond 最後)
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

# 条件定義 (順序固定): "OT_TAG|THREADS|OT_REGEX"
# OT_REGEX は単一引用符内なので bash 展開を回避
CONDITIONS=(
  'A36|40|blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'
  'A36|32|blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'
  'C40|40|blk\.([0-9]|1[0-7]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'
  'C40|32|blk\.([0-9]|1[0-9]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'
  'B32|40|blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-3])\.ffn_.*_exps\.weight=CPU'
  'B32|32|blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-3])\.ffn_.*_exps\.weight=CPU'
)

echo "[batchT4] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
echo "[batchT4] total conditions: ${#CONDITIONS[@]}"

for COND in "${CONDITIONS[@]}"; do
  IFS='|' read -r OT_TAG THR OT_REGEX <<< "$COND"
  TAG_COND="${OT_TAG}_t${THR}_kv${KV}_sm${SM}_ctx${CTX}_ub${UB}"
  echo "[batchT4] ================================"
  echo "[batchT4] cond: ot=${OT_TAG} threads=${THR} (regex=${OT_REGEX}) at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchT4] ================================"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
    CACHE_TYPE_K="$KV" CACHE_TYPE_V="$KV" SPLIT_MODE="$SM" THREADS="$THR" \
    OT_TAG="$OT_TAG" OT_REGEX="$OT_REGEX" \
    bash start_phaseT4.sh > "start_stdout_T4_${TAG_COND}.log" 2>&1 &
  START_PID=$!

  healthy=0
  for i in $(seq 1 80); do
    if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
      echo "[batchT4] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    if ! kill -0 "$START_PID" 2>/dev/null; then
      echo "[batchT4] start_phaseT4.sh exited early for ot=${OT_TAG} threads=${THR}" >&2
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchT4] ERROR: health never OK for ot=${OT_TAG} threads=${THR} (start_stdout に OOM/reject の可能性)" >&2
    tail -60 "start_stdout_T4_${TAG_COND}.log" >&2 || true
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
    echo "[batchT4] ERROR: PID not found for ot=${OT_TAG} threads=${THR}" >&2
    continue
  fi
  echo "[batchT4] PID=$PID"

  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/llama-server_phaseT4_${OT_TAG}_t${THR}_sm${SM}_k${KV}_v${KV}_fa1_ctx${CTX}_b${UB}_ub${UB}.log" \
    > "startup_logs/T4_${TAG_COND}.log"
  echo "[batchT4] startup log saved ($(wc -l < startup_logs/T4_${TAG_COND}.log) lines)"

  PID="$PID" TAG_PREFIX="T4_${TAG_COND}" WARMUP_RUNS=2 EVAL_RUNS=5 \
    bash run_all.sh > "run_T4_${TAG_COND}.log" 2>&1
  echo "[batchT4] measure done ($(tail -1 run_T4_${TAG_COND}.log))"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchT4] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
