#!/usr/bin/env bash
# start_phaseSeval19s.sh - Phase S-eval-19session: 第 19 セッションとして同条件再計測
# Phase S-eval-18session start と同じ起動形式。REMOTE_LOG prefix のみ phaseSeval19s に変更。
# FLASH_ATTN=1 固定想定、CTX_SIZE=32768 想定（呼び出し側で指定）。
set -euo pipefail

HOST="${HOST:-t120h-p100}"
HEALTH_URL="${HEALTH_URL:-http://10.1.4.14:8000/health}"
FLASH_ATTN="${FLASH_ATTN:-1}"
CTX_SIZE="${CTX_SIZE:-32768}"
BATCH_SIZE="${BATCH_SIZE:-1586}"
UB_SIZE="${UB_SIZE:-${BATCH_SIZE}}"

MODEL_PATH="/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf"

OT_REGEX='blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'

PREFIX="numactl --cpunodebind=1 --membind=1 --"
THREADS="40"
POLL="0"

REMOTE_LOG="/tmp/llama-server_phaseSeval19s_fa${FLASH_ATTN}_ctx${CTX_SIZE}_b${BATCH_SIZE}_ub${UB_SIZE}.log"

LAUNCH_CMD="${PREFIX} ./build/bin/llama-server \
  -m '${MODEL_PATH}' --jinja \
  -ngl 999 -ot '${OT_REGEX}' \
  --flash-attn ${FLASH_ATTN} --poll ${POLL} -b ${BATCH_SIZE} -ub ${UB_SIZE} \
  --n-predict 32768 --threads ${THREADS} \
  --ctx-size ${CTX_SIZE} --parallel 1 \
  --cache-type-k f16 --cache-type-v f16 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 \
  --port 8000 --host 0.0.0.0 \
  --alias 'unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M'"

echo "[start_phaseSeval19s] FLASH_ATTN=${FLASH_ATTN} CTX_SIZE=${CTX_SIZE} -b ${BATCH_SIZE} -ub ${UB_SIZE}"
echo "[start_phaseSeval19s] remote log: ${REMOTE_LOG}"

ssh -f "$HOST" "cd ~/llama.cpp && nohup bash -c \"${LAUNCH_CMD}\" > ${REMOTE_LOG} 2>&1 < /dev/null &"

echo "[start_phaseSeval19s] waiting for /health (max 300s) or OOM/ub-reject abort..."
for i in $(seq 1 60); do
  if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    echo "[start_phaseSeval19s] /health OK after ${i}*5s"
    sleep 3
    PID=$(ssh "$HOST" "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
    echo "[start_phaseSeval19s] PID=${PID}"
    echo "$PID"
    exit 0
  fi
  if ssh "$HOST" "grep -qE 'cudaMalloc failed: out of memory|failed to allocate CUDA[0-9] buffer|graph_reserve: failed to allocate|llama_kv_cache.*failed|n_ctx.*too large|failed to allocate KV' ${REMOTE_LOG} 2>/dev/null"; then
    echo "[start_phaseSeval19s] OOM pattern detected in ${REMOTE_LOG}, abort" >&2
    ssh "$HOST" "tail -20 ${REMOTE_LOG}" >&2 || true
    exit 2
  fi
  if ssh "$HOST" "grep -qE 'ubatch.*must be|n_ubatch.*must|invalid.*ubatch|llama_init.*failed' ${REMOTE_LOG} 2>/dev/null"; then
    echo "[start_phaseSeval19s] -ub lower-bound rejection detected in ${REMOTE_LOG}, abort" >&2
    ssh "$HOST" "tail -30 ${REMOTE_LOG}" >&2 || true
    exit 3
  fi
  sleep 5
done
echo "[start_phaseSeval19s] FAILED to become healthy in 300s" >&2
ssh "$HOST" "tail -20 ${REMOTE_LOG}" >&2 || true
exit 1
