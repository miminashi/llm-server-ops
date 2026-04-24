#!/usr/bin/env bash
# start_phaseSbctx.sh - Phase Sb-ctx-boundary: 候補 J (9 層 SSM × VMM 非同期累積) の ctx 非依存性検証
# Phase Sbf3 からの変更点:
#   - REMOTE_LOG プレフィックス phaseSbf3_ → phaseSbctx_
#   - health 待機の最大反復を ctx=131k 対応で MAX_ITER (default 120=600s) に拡張（環境変数上書き可）
set -euo pipefail

HOST="${HOST:-t120h-p100}"
HEALTH_URL="${HEALTH_URL:-http://10.1.4.14:8000/health}"
FLASH_ATTN="${FLASH_ATTN:-1}"
CTX_SIZE="${CTX_SIZE:-4096}"
BATCH_SIZE="${BATCH_SIZE:-8192}"
UB_SIZE="${UB_SIZE:-${BATCH_SIZE}}"
MAX_ITER="${MAX_ITER:-120}"  # 120 * 5s = 600s (ctx=131k 対応)

MODEL_PATH="/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf"

OT_REGEX='blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'

PREFIX="numactl --cpunodebind=1 --membind=1 --"
THREADS="40"
POLL="0"

REMOTE_LOG="/tmp/llama-server_phaseSbctx_fa${FLASH_ATTN}_ctx${CTX_SIZE}_b${BATCH_SIZE}_ub${UB_SIZE}.log"

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

echo "[start_phaseSbctx] FLASH_ATTN=${FLASH_ATTN} CTX_SIZE=${CTX_SIZE} -b ${BATCH_SIZE} -ub ${UB_SIZE} MAX_ITER=${MAX_ITER} (C-D3 base, poll=0, f16 KV)"
echo "[start_phaseSbctx] remote log: ${REMOTE_LOG}"

ssh -f "$HOST" "cd ~/llama.cpp && nohup bash -c \"${LAUNCH_CMD}\" > ${REMOTE_LOG} 2>&1 < /dev/null &"

echo "[start_phaseSbctx] waiting for /health (max ${MAX_ITER}*5s) or OOM/ub-reject abort..."
for i in $(seq 1 ${MAX_ITER}); do
  if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    echo "[start_phaseSbctx] /health OK after ${i}*5s"
    sleep 3
    PID=$(ssh "$HOST" "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
    echo "[start_phaseSbctx] PID=${PID}"
    echo "$PID"
    exit 0
  fi
  # OOM 早期判定
  if ssh "$HOST" "grep -qE 'cudaMalloc failed: out of memory|failed to allocate CUDA[0-9] buffer|graph_reserve: failed to allocate|llama_kv_cache.*failed|n_ctx.*too large|failed to allocate KV' ${REMOTE_LOG} 2>/dev/null"; then
    echo "[start_phaseSbctx] OOM pattern detected in ${REMOTE_LOG}, abort" >&2
    ssh "$HOST" "tail -20 ${REMOTE_LOG}" >&2 || true
    exit 2
  fi
  # -ub 下限拒否検出
  if ssh "$HOST" "grep -qE 'ubatch.*must be|n_ubatch.*must|invalid.*ubatch|llama_init.*failed' ${REMOTE_LOG} 2>/dev/null"; then
    echo "[start_phaseSbctx] -ub lower-bound rejection detected in ${REMOTE_LOG}, abort" >&2
    ssh "$HOST" "tail -30 ${REMOTE_LOG}" >&2 || true
    exit 3
  fi
  sleep 5
done
echo "[start_phaseSbctx] FAILED to become healthy in $((MAX_ITER*5))s" >&2
ssh "$HOST" "tail -20 ${REMOTE_LOG}" >&2 || true
exit 1
