#!/usr/bin/env bash
# batch_phaseT5e.sh - Phase T-5e: B28 × (ctx, ub) 適用
# 5 条件 × (warmup 2 + 1k eval 5) = 35 measurement
#   1. B28_32k_1586a: ctx=32k ub=1586 (T-5 B28 = 16.024 再現、drift 起点)
#   2. B28_65k_ub512: ctx=65k ub=512 (★本命: Phase S 条件適用)
#   3. B28_65k_ub1586: ctx=65k ub=1586 (ctx 単独効果分離)
#   4. B28_32k_ub512: ctx=32k ub=512 (ub 単独効果分離)
#   5. B28_32k_1586z: ctx=32k ub=1586 (drift 終点)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p startup_logs

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

# 固定パラメータ (T-5 最良継承: OT=B28, KV=q8_0, SM=layer, threads=40, fa=1)
OT_TAG="B28"
OT_REGEX='blk\.([0-9]|1[0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
KV="q8_0"
SM="layer"
THR=40

# 条件定義: "LABEL#CTX#UB"
# LABEL は drift 分離のため、同一 (ctx, ub) でも a/z を付けて別 out_ ディレクトリに
CONDITIONS=(
  'B28_32k_1586a#32768#1586'
  'B28_65k_ub512#65536#512'
  'B28_65k_ub1586#65536#1586'
  'B28_32k_ub512#32768#512'
  'B28_32k_1586z#32768#1586'
)

# OOM 時 skip したい条件 (envvar SKIP_LABELS で指定、カンマ区切り)
SKIP_LABELS="${SKIP_LABELS:-}"

echo "[batchT5e] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
echo "[batchT5e] total conditions: ${#CONDITIONS[@]} (skip: ${SKIP_LABELS:-none})"

for COND in "${CONDITIONS[@]}"; do
  IFS='#' read -r LABEL CTX UB <<< "$COND"

  if [[ ",${SKIP_LABELS}," == *",${LABEL},"* ]]; then
    echo "[batchT5e] SKIP label=${LABEL} (per SKIP_LABELS)"
    continue
  fi

  TAG_COND="${LABEL}_t${THR}_kv${KV}_sm${SM}_ctx${CTX}_ub${UB}"
  echo "[batchT5e] ================================"
  echo "[batchT5e] cond: label=${LABEL} ctx=${CTX} ub=${UB} at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchT5e] ================================"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
    CACHE_TYPE_K="$KV" CACHE_TYPE_V="$KV" SPLIT_MODE="$SM" THREADS="$THR" \
    OT_TAG="$OT_TAG" OT_REGEX="$OT_REGEX" \
    bash start_phaseT5.sh > "start_stdout_T5e_${TAG_COND}.log" 2>&1 &
  START_PID=$!

  # ctx=65k は KV 初期化 +10-20 秒かかるので 120 × 5s = 600s 猶予
  healthy=0
  for i in $(seq 1 120); do
    if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
      echo "[batchT5e] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    if ! kill -0 "$START_PID" 2>/dev/null; then
      echo "[batchT5e] start_phaseT5.sh exited early for label=${LABEL}" >&2
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchT5e] ERROR: health never OK for label=${LABEL} (start_stdout に OOM/reject の可能性)" >&2
    tail -80 "start_stdout_T5e_${TAG_COND}.log" >&2 || true
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
    echo "[batchT5e] ERROR: PID not found for label=${LABEL}" >&2
    continue
  fi
  echo "[batchT5e] PID=$PID"

  # start_phaseT5.sh が書くリモートログ名: /tmp/llama-server_phaseT5_${OT_TAG}_t${THREADS}_sm${SPLIT_MODE}_k${CACHE_TYPE_K}_v${CACHE_TYPE_V}_fa${FLASH_ATTN}_ctx${CTX_SIZE}_b${BATCH_SIZE}_ub${UB_SIZE}.log
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/llama-server_phaseT5_${OT_TAG}_t${THR}_sm${SM}_k${KV}_v${KV}_fa1_ctx${CTX}_b${UB}_ub${UB}.log" \
    > "startup_logs/T5e_${TAG_COND}.log"
  echo "[batchT5e] startup log saved ($(wc -l < startup_logs/T5e_${TAG_COND}.log) lines)"

  PID="$PID" TAG_PREFIX="T5e_${TAG_COND}" WARMUP_RUNS=2 EVAL_RUNS=5 \
    bash run_all.sh > "run_T5e_${TAG_COND}.log" 2>&1
  echo "[batchT5e] measure done ($(tail -1 run_T5e_${TAG_COND}.log))"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchT5e] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
