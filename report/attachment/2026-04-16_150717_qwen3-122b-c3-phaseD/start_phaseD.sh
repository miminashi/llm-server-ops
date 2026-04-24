#!/usr/bin/env bash
# start_phaseD.sh - Phase D variants (C-D2 / C-D3 / C-D4)
# usage: start_phaseD.sh <variant>
#   D2: numactl --interleave=all -- + --numa distribute
#   D3: numactl --cpunodebind=1 --membind=1 -- + --threads 40
#   D4: numactl --interleave=all -- + --threads 80 (明示)

set -euo pipefail

VARIANT="${1:?variant required: D2|D3|D4|D5|D6}"
HOST="${HOST:-t120h-p100}"
HEALTH_URL="${HEALTH_URL:-http://10.1.4.14:8000/health}"

MODEL_PATH="/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf"

OT_REGEX='blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'

case "$VARIANT" in
  D2)
    PREFIX="numactl --interleave=all --"
    THREADS="-1"
    EXTRA_ARGS="--numa distribute"
    ;;
  D3)
    PREFIX="numactl --cpunodebind=1 --membind=1 --"
    THREADS="40"
    EXTRA_ARGS=""
    ;;
  D4)
    PREFIX="numactl --interleave=all --"
    THREADS="80"
    EXTRA_ARGS=""
    ;;
  D5)
    PREFIX="numactl --interleave=all --"
    THREADS="40"
    EXTRA_ARGS=""
    ;;
  D6)
    PREFIX="numactl --cpunodebind=0 --membind=0 --"
    THREADS="40"
    EXTRA_ARGS=""
    ;;
  *)
    echo "Unknown variant: $VARIANT" >&2
    exit 1
    ;;
esac

LAUNCH_CMD="${PREFIX} ./build/bin/llama-server \
  -m '${MODEL_PATH}' --jinja \
  -ngl 999 -ot '${OT_REGEX}' \
  --flash-attn 1 --poll 0 -b 8192 -ub 8192 \
  --n-predict 32768 --threads ${THREADS} \
  --ctx-size 131072 --parallel 1 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 \
  ${EXTRA_ARGS} \
  --port 8000 --host 0.0.0.0 \
  --alias 'unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M'"

echo "[start_phaseD] variant=${VARIANT}"
echo "[start_phaseD] launch cmd:"
echo "$LAUNCH_CMD"

ssh -f "$HOST" "cd ~/llama.cpp && nohup bash -c \"${LAUNCH_CMD}\" > /tmp/llama-server.log 2>&1 < /dev/null &"

echo "[start_phaseD] waiting for /health..."
for i in $(seq 1 60); do
  if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    echo "[start_phaseD] /health OK after ${i}*5s"
    sleep 5
    PID=$(ssh "$HOST" "pgrep -f 'llama-server.*--alias' | head -1")
    echo "[start_phaseD] PID=${PID}"
    echo "$PID"
    exit 0
  fi
  sleep 5
done
echo "[start_phaseD] FAILED to become healthy in 300s" >&2
exit 1
