#!/usr/bin/env bash
# start_phaseC.sh - C-3 構成を異なる NUMA 設定で起動
# usage: start_phaseC.sh <variant>
#   variant: C1 (numactl -N1 -m1) | C2 (numactl --interleave=all) | C3 (--numa distribute)

set -euo pipefail

VARIANT="${1:?variant required: C1|C2|C3|C2isolate}"
HOST="${HOST:-t120h-p100}"
HEALTH_URL="${HEALTH_URL:-http://10.1.4.14:8000/health}"

MODEL_PATH="/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf"

# C-3 の -ot 正規表現: blk.0..13, blk.20..24, blk.31..47 を CPU へ
OT_REGEX='blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'

case "$VARIANT" in
  C1)
    PREFIX="numactl --cpunodebind=1 --membind=1 --"
    EXTRA_ARGS=""
    ;;
  C2)
    PREFIX="numactl --interleave=all --"
    EXTRA_ARGS=""
    ;;
  C2isolate)
    PREFIX="numactl --interleave=0,1 --cpunodebind=0,1 --"
    EXTRA_ARGS=""
    ;;
  C3)
    PREFIX=""
    EXTRA_ARGS="--numa distribute"
    ;;
  C3iso)
    PREFIX=""
    EXTRA_ARGS="--numa isolate"
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
  --n-predict 32768 --threads -1 \
  --ctx-size 131072 --parallel 1 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --defrag-thold 0.1 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 \
  ${EXTRA_ARGS} \
  --port 8000 --host 0.0.0.0 \
  --alias 'unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M'"

echo "[start_phaseC] variant=${VARIANT}"
echo "[start_phaseC] launch cmd:"
echo "$LAUNCH_CMD"

# nohup で起動
ssh -f "$HOST" "cd ~/llama.cpp && nohup bash -c \"${LAUNCH_CMD}\" > /tmp/llama-server.log 2>&1 < /dev/null &"

echo "[start_phaseC] waiting for /health..."
for i in $(seq 1 60); do
  if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    echo "[start_phaseC] /health OK after ${i}*5s"
    sleep 5
    PID=$(ssh "$HOST" "pgrep -f 'llama-server.*--alias' | head -1")
    echo "[start_phaseC] PID=${PID}"
    echo "$PID"
    exit 0
  fi
  sleep 5
done
echo "[start_phaseC] FAILED to become healthy in 300s" >&2
exit 1
