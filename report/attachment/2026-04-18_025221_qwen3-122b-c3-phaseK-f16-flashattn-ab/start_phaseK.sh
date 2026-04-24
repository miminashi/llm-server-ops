#!/usr/bin/env bash
# start_phaseK.sh - Phase K flash-attn A/B 比較用 (f16 KV cache + ctx=16384 縮小版)
# Phase J から変更点:
#   --cache-type-k q8_0 → f16
#   --cache-type-v q8_0 → f16
#   --ctx-size 131072   → 16384
# FLASH_ATTN 環境変数で 0/1 切替（既定 1）

set -euo pipefail

HOST="${HOST:-t120h-p100}"
HEALTH_URL="${HEALTH_URL:-http://10.1.4.14:8000/health}"
FLASH_ATTN="${FLASH_ATTN:-1}"

MODEL_PATH="/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf"

OT_REGEX='blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'

PREFIX="numactl --cpunodebind=1 --membind=1 --"
THREADS="40"
POLL="0"

LAUNCH_CMD="${PREFIX} ./build/bin/llama-server \
  -m '${MODEL_PATH}' --jinja \
  -ngl 999 -ot '${OT_REGEX}' \
  --flash-attn ${FLASH_ATTN} --poll ${POLL} -b 8192 -ub 8192 \
  --n-predict 32768 --threads ${THREADS} \
  --ctx-size 16384 --parallel 1 \
  --cache-type-k f16 --cache-type-v f16 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 \
  --port 8000 --host 0.0.0.0 \
  --alias 'unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M'"

echo "[start_phaseK] FLASH_ATTN=${FLASH_ATTN} (C-D3 base, poll=0, ctx=16384, f16 KV)"
echo "[start_phaseK] launch cmd:"
echo "$LAUNCH_CMD"

ssh -f "$HOST" "cd ~/llama.cpp && nohup bash -c \"${LAUNCH_CMD}\" > /tmp/llama-server.log 2>&1 < /dev/null &"

echo "[start_phaseK] waiting for /health..."
for i in $(seq 1 60); do
  if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    echo "[start_phaseK] /health OK after ${i}*5s"
    sleep 5
    PID=$(ssh "$HOST" "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
    echo "[start_phaseK] PID=${PID}"
    echo "$PID"
    exit 0
  fi
  sleep 5
done
echo "[start_phaseK] FAILED to become healthy in 300s" >&2
exit 1
