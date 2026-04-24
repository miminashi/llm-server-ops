#!/usr/bin/env bash
# start_phaseU4.sh - Phase U-4 起動 (モデルパス/エイリアス可変)
# B14b_ts_alt 構成 (Phase T-5a-ts2 / U-2 と完全同一) でモデルのみ差し替え
set -euo pipefail

HOST="${HOST:-t120h-p100}"
HEALTH_URL="${HEALTH_URL:-http://10.1.4.14:8000/health}"
FLASH_ATTN="${FLASH_ATTN:-1}"
CTX_SIZE="${CTX_SIZE:-32768}"
BATCH_SIZE="${BATCH_SIZE:-256}"
UB_SIZE="${UB_SIZE:-${BATCH_SIZE}}"
CACHE_TYPE_K="${CACHE_TYPE_K:-q8_0}"
CACHE_TYPE_V="${CACHE_TYPE_V:-q8_0}"
SPLIT_MODE="${SPLIT_MODE:-layer}"
THREADS="${THREADS:-40}"
OT_TAG="${OT_TAG:-B14b}"
TS="${TS:-11,12,13,14}"
MODEL_PATH="${MODEL_PATH:?MODEL_PATH env required (full GGUF path on remote)}"
MODEL_ALIAS="${MODEL_ALIAS:?MODEL_ALIAS env required (e.g. unsloth/... or qwen3.5/fused:Q4_K_M)}"

OT_REGEX="${OT_REGEX:-blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU}"

PREFIX="numactl --cpunodebind=1 --membind=1 --"
POLL="0"

TS_TAG="${TS:+_ts$(echo "$TS" | tr , -)}"
TAG_SUFFIX="${TAG_SUFFIX:-}"
REMOTE_LOG="/tmp/llama-server_phaseU4_${OT_TAG}_t${THREADS}_sm${SPLIT_MODE}_k${CACHE_TYPE_K}_v${CACHE_TYPE_V}_fa${FLASH_ATTN}_ctx${CTX_SIZE}_b${BATCH_SIZE}_ub${UB_SIZE}${TS_TAG}${TAG_SUFFIX}.log"

LAUNCH_CMD="${PREFIX} ./build/bin/llama-server \
  -m '${MODEL_PATH}' --jinja \
  -ngl 999 -ot '${OT_REGEX}' ${TS:+--tensor-split ${TS}} \
  --split-mode ${SPLIT_MODE} \
  --flash-attn ${FLASH_ATTN} --poll ${POLL} -b ${BATCH_SIZE} -ub ${UB_SIZE} \
  --n-predict 32768 --threads ${THREADS} \
  --ctx-size ${CTX_SIZE} --parallel 1 \
  --cache-type-k ${CACHE_TYPE_K} --cache-type-v ${CACHE_TYPE_V} \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 \
  --port 8000 --host 0.0.0.0 \
  --alias '${MODEL_ALIAS}'"

echo "[start_phaseU4] MODEL_PATH=${MODEL_PATH}"
echo "[start_phaseU4] MODEL_ALIAS=${MODEL_ALIAS}"
echo "[start_phaseU4] OT_TAG=${OT_TAG} OT_REGEX=${OT_REGEX} TS=${TS:-(default)}"
echo "[start_phaseU4] THREADS=${THREADS} SPLIT_MODE=${SPLIT_MODE} K=${CACHE_TYPE_K} V=${CACHE_TYPE_V} FA=${FLASH_ATTN} CTX=${CTX_SIZE} b=${BATCH_SIZE} ub=${UB_SIZE}"
echo "[start_phaseU4] remote log: ${REMOTE_LOG}"

ssh -f "$HOST" "cd ~/llama.cpp && nohup bash -c \"${LAUNCH_CMD}\" > ${REMOTE_LOG} 2>&1 < /dev/null &"

echo "[start_phaseU4] waiting for /health (max 300s) or OOM/reject..."
for i in $(seq 1 60); do
  if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    echo "[start_phaseU4] /health OK after ${i}*5s"
    sleep 3
    PID=$(ssh "$HOST" "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
    echo "[start_phaseU4] PID=${PID}"
    echo "$PID"
    exit 0
  fi
  if ssh "$HOST" "grep -qE 'cudaMalloc failed|failed to allocate CUDA|graph_reserve: failed|failed to allocate KV|CUDA error: out of memory|ggml_abort.*cuda|unsupported .*arch|unknown tensor' ${REMOTE_LOG} 2>/dev/null"; then
    echo "[start_phaseU4] OOM/arch error detected" >&2
    ssh "$HOST" "tail -30 ${REMOTE_LOG}" >&2 || true
    exit 2
  fi
  if ssh "$HOST" "grep -qE 'llama_init.*failed|invalid.*ubatch|model not found|unable to load model' ${REMOTE_LOG} 2>/dev/null"; then
    echo "[start_phaseU4] model load error detected" >&2
    ssh "$HOST" "tail -30 ${REMOTE_LOG}" >&2 || true
    exit 3
  fi
  sleep 5
done
echo "[start_phaseU4] FAILED to become healthy in 300s" >&2
ssh "$HOST" "tail -30 ${REMOTE_LOG}" >&2 || true
exit 1
