#!/usr/bin/env bash
# start_phaseT5.sh - Phase T-5: OT pattern 層範囲スイープ用 llama-server 起動
# T-3 (start_phaseT3.sh) ベース。OT_REGEX を環境変数化 (CPU offload 層数 32/36/40)、
# THREADS={32,40}、SPLIT_MODE=layer / KV=q8_0 固定。
set -euo pipefail

HOST="${HOST:-t120h-p100}"
HEALTH_URL="${HEALTH_URL:-http://10.1.4.14:8000/health}"
FLASH_ATTN="${FLASH_ATTN:-1}"
CTX_SIZE="${CTX_SIZE:-32768}"
BATCH_SIZE="${BATCH_SIZE:-1586}"
UB_SIZE="${UB_SIZE:-${BATCH_SIZE}}"
CACHE_TYPE_K="${CACHE_TYPE_K:-q8_0}"
CACHE_TYPE_V="${CACHE_TYPE_V:-q8_0}"
SPLIT_MODE="${SPLIT_MODE:-layer}"
THREADS="${THREADS:-40}"
OT_TAG="${OT_TAG:-A36}"

MODEL_PATH="/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf"

OT_REGEX="${OT_REGEX:?OT_REGEX env required (e.g. blk\.([0-9]|...)\.ffn_.*_exps\.weight=CPU)}"

PREFIX="numactl --cpunodebind=1 --membind=1 --"
POLL="0"

REMOTE_LOG="/tmp/llama-server_phaseT5_${OT_TAG}_t${THREADS}_sm${SPLIT_MODE}_k${CACHE_TYPE_K}_v${CACHE_TYPE_V}_fa${FLASH_ATTN}_ctx${CTX_SIZE}_b${BATCH_SIZE}_ub${UB_SIZE}.log"

LAUNCH_CMD="${PREFIX} ./build/bin/llama-server \
  -m '${MODEL_PATH}' --jinja \
  -ngl 999 -ot '${OT_REGEX}' \
  --split-mode ${SPLIT_MODE} \
  --flash-attn ${FLASH_ATTN} --poll ${POLL} -b ${BATCH_SIZE} -ub ${UB_SIZE} \
  --n-predict 32768 --threads ${THREADS} \
  --ctx-size ${CTX_SIZE} --parallel 1 \
  --cache-type-k ${CACHE_TYPE_K} --cache-type-v ${CACHE_TYPE_V} \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 \
  --port 8000 --host 0.0.0.0 \
  --alias 'unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M'"

echo "[start_phaseT5] OT_TAG=${OT_TAG} OT_REGEX=${OT_REGEX}"
echo "[start_phaseT5] THREADS=${THREADS} SPLIT_MODE=${SPLIT_MODE} CACHE_TYPE_K=${CACHE_TYPE_K} CACHE_TYPE_V=${CACHE_TYPE_V} FLASH_ATTN=${FLASH_ATTN} CTX_SIZE=${CTX_SIZE} -b ${BATCH_SIZE} -ub ${UB_SIZE}"
echo "[start_phaseT5] remote log: ${REMOTE_LOG}"

ssh -f "$HOST" "cd ~/llama.cpp && nohup bash -c \"${LAUNCH_CMD}\" > ${REMOTE_LOG} 2>&1 < /dev/null &"

echo "[start_phaseT5] waiting for /health (max 300s) or OOM/ub-reject/threads abort..."
for i in $(seq 1 60); do
  if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    echo "[start_phaseT5] /health OK after ${i}*5s"
    sleep 3
    PID=$(ssh "$HOST" "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
    echo "[start_phaseT5] PID=${PID}"
    echo "$PID"
    exit 0
  fi
  if ssh "$HOST" "grep -qE 'cudaMalloc failed: out of memory|failed to allocate CUDA[0-9] buffer|graph_reserve: failed to allocate|llama_kv_cache.*failed|n_ctx.*too large|failed to allocate KV' ${REMOTE_LOG} 2>/dev/null"; then
    echo "[start_phaseT5] OOM pattern detected in ${REMOTE_LOG}, abort" >&2
    ssh "$HOST" "tail -20 ${REMOTE_LOG}" >&2 || true
    exit 2
  fi
  if ssh "$HOST" "grep -qE 'ubatch.*must be|n_ubatch.*must|invalid.*ubatch|llama_init.*failed|unsupported KV|unknown cache-type|split.?mode.*not supported|invalid.*threads|threads.*must' ${REMOTE_LOG} 2>/dev/null"; then
    echo "[start_phaseT5] param rejection detected in ${REMOTE_LOG}, abort" >&2
    ssh "$HOST" "tail -30 ${REMOTE_LOG}" >&2 || true
    exit 3
  fi
  sleep 5
done
echo "[start_phaseT5] FAILED to become healthy in 300s" >&2
ssh "$HOST" "tail -20 ${REMOTE_LOG}" >&2 || true
exit 1
