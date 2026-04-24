#!/usr/bin/env bash
# start_phaseU6.sh - Phase U-6: ctx=128k 本計測用 llama-server 起動
# U-5 start をベースに
#   - --jinja 付与 (chat completions 利用)
#   - --metrics 付与
#   - --n-predict 2048 (runtime max_tokens で制御、cap のみ)
#   - UB_SIZE を runtime 化 (env 経由で変更可、既に U-5 で対応済)
set -euo pipefail

HOST="${HOST:-t120h-p100}"
HEALTH_URL="${HEALTH_URL:-http://10.1.4.14:8000/health}"
FLASH_ATTN="${FLASH_ATTN:-1}"
CTX_SIZE="${CTX_SIZE:-131072}"
BATCH_SIZE="${BATCH_SIZE:-2048}"
UB_SIZE="${UB_SIZE:-512}"
CACHE_TYPE_K="${CACHE_TYPE_K:-q8_0}"
CACHE_TYPE_V="${CACHE_TYPE_V:-q8_0}"
SPLIT_MODE="${SPLIT_MODE:-layer}"
THREADS="${THREADS:-40}"
OT_TAG="${OT_TAG:-B14b}"
TS="${TS:-11,12,13,14}"
EXTRA_ARGS="${EXTRA_ARGS:-}"
EXTRA_TAG="${EXTRA_TAG:-}"

MODEL_PATH="/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf"

OT_REGEX="${OT_REGEX:?OT_REGEX env required}"

PREFIX="numactl --cpunodebind=1 --membind=1 --"
POLL="0"

TS_TAG="${TS:+_ts$(echo "$TS" | tr , -)}"
EXTRA_TAG_PART="${EXTRA_TAG:+_${EXTRA_TAG}}"
REMOTE_LOG="/tmp/llama-server_phaseU6_${OT_TAG}_t${THREADS}_sm${SPLIT_MODE}_k${CACHE_TYPE_K}_v${CACHE_TYPE_V}_fa${FLASH_ATTN}_ctx${CTX_SIZE}_b${BATCH_SIZE}_ub${UB_SIZE}${TS_TAG}${EXTRA_TAG_PART}.log"

LAUNCH_CMD="${PREFIX} ./build/bin/llama-server \
  -m '${MODEL_PATH}' \
  -ngl 999 -ot '${OT_REGEX}' ${TS:+--tensor-split ${TS}} \
  --split-mode ${SPLIT_MODE} \
  --flash-attn ${FLASH_ATTN} --poll ${POLL} -b ${BATCH_SIZE} -ub ${UB_SIZE} \
  --n-predict 2048 --threads ${THREADS} \
  --ctx-size ${CTX_SIZE} --parallel 1 \
  --cache-type-k ${CACHE_TYPE_K} --cache-type-v ${CACHE_TYPE_V} \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 \
  --jinja --metrics \
  --port 8000 --host 0.0.0.0 \
  --alias 'unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M' \
  ${EXTRA_ARGS}"

echo "[start_phaseU6] OT_TAG=${OT_TAG} OT_REGEX=${OT_REGEX} TS=${TS:-(default)} EXTRA_TAG=${EXTRA_TAG}"
echo "[start_phaseU6] EXTRA_ARGS=${EXTRA_ARGS:-(none)}"
echo "[start_phaseU6] THREADS=${THREADS} CACHE_TYPE=${CACHE_TYPE_K} FA=${FLASH_ATTN} CTX=${CTX_SIZE} -b ${BATCH_SIZE} -ub ${UB_SIZE}"
echo "[start_phaseU6] remote log: ${REMOTE_LOG}"

ssh -f "$HOST" "cd ~/llama.cpp && nohup bash -c \"${LAUNCH_CMD}\" > ${REMOTE_LOG} 2>&1 < /dev/null &"

echo "[start_phaseU6] waiting for /health (max 300s) or OOM/param reject..."
START_EPOCH=$(date +%s)
for i in $(seq 1 60); do
  if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    ELAPSED=$(( $(date +%s) - START_EPOCH ))
    echo "[start_phaseU6] /health OK after ${i}*5s (elapsed=${ELAPSED}s)"
    sleep 3
    PID=$(ssh "$HOST" "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
    echo "[start_phaseU6] PID=${PID}"
    echo "STARTUP_SEC=${ELAPSED}"
    echo "REMOTE_LOG=${REMOTE_LOG}"
    exit 0
  fi
  if ssh "$HOST" "grep -qE 'cudaMalloc failed: out of memory|failed to allocate CUDA[0-9] buffer|graph_reserve: failed to allocate|llama_kv_cache.*failed|n_ctx.*too large|failed to allocate KV|CUDA error: out of memory|ggml_abort.*cuda' ${REMOTE_LOG} 2>/dev/null"; then
    echo "[start_phaseU6] OOM pattern detected, abort" >&2
    ssh "$HOST" "tail -30 ${REMOTE_LOG}" >&2 || true
    exit 2
  fi
  if ssh "$HOST" "grep -qE 'ubatch.*must be|n_ubatch.*must|invalid.*ubatch|llama_init.*failed|unsupported KV|unknown cache-type|split.?mode.*not supported|invalid.*threads|threads.*must|tensor.split.*invalid|invalid.*tensor.split|error: invalid argument|unknown argument' ${REMOTE_LOG} 2>/dev/null"; then
    echo "[start_phaseU6] param rejection detected, abort" >&2
    ssh "$HOST" "tail -40 ${REMOTE_LOG}" >&2 || true
    exit 3
  fi
  sleep 5
done
echo "[start_phaseU6] FAILED to become healthy in 300s (TIMEOUT)" >&2
ssh "$HOST" "tail -30 ${REMOTE_LOG}" >&2 || true
exit 1
