#!/usr/bin/env bash
# start_phaseE.sh - Phase E variants (SMT / taskset / --numa isolate 検証)
# usage: start_phaseE.sh <variant>
#   E1: numactl -N1 -m1 + --threads 40          （C-D3 追試）
#   E2: numactl -N1 -m1 + --threads 20          （物理コアのみ、SMT なし）
#   E3: numactl -N1 -m1 + --threads 60          （中間値、SMT 部分使用）
#   E4: numactl -N1 -m1 + --threads 40 + taskset 20-39,60-79 で完全ピニング
#   E5: numactl -N1 -m1 + --threads 40 + --numa isolate

set -euo pipefail

VARIANT="${1:?variant required: E1|E2|E3|E4|E5}"
HOST="${HOST:-t120h-p100}"
HEALTH_URL="${HEALTH_URL:-http://10.1.4.14:8000/health}"

MODEL_PATH="/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf"

OT_REGEX='blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'

PREFIX=""
THREADS=""
EXTRA_ARGS=""
case "$VARIANT" in
  E1)
    PREFIX="numactl --cpunodebind=1 --membind=1 --"
    THREADS="40"
    ;;
  E2)
    PREFIX="numactl --cpunodebind=1 --membind=1 --"
    THREADS="20"
    ;;
  E3)
    PREFIX="numactl --cpunodebind=1 --membind=1 --"
    THREADS="60"
    ;;
  E4)
    # taskset -c で CPU リストを完全指定、numactl -m1 でメモリのみ拘束
    PREFIX="taskset -c 20-39,60-79 numactl --membind=1 --"
    THREADS="40"
    ;;
  E5)
    PREFIX="numactl --cpunodebind=1 --membind=1 --"
    THREADS="40"
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
  --n-predict 32768 --threads ${THREADS} \
  --ctx-size 131072 --parallel 1 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 \
  ${EXTRA_ARGS} \
  --port 8000 --host 0.0.0.0 \
  --alias 'unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M'"

echo "[start_phaseE] variant=${VARIANT}"
echo "[start_phaseE] launch cmd:"
echo "$LAUNCH_CMD"

ssh -f "$HOST" "cd ~/llama.cpp && nohup bash -c \"${LAUNCH_CMD}\" > /tmp/llama-server.log 2>&1 < /dev/null &"

echo "[start_phaseE] waiting for /health..."
for i in $(seq 1 60); do
  if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    echo "[start_phaseE] /health OK after ${i}*5s"
    sleep 5
    PID=$(ssh "$HOST" "pgrep -f 'build/bin/llama-server' | head -1")
    echo "[start_phaseE] PID=${PID}"
    echo "$PID"
    exit 0
  fi
  sleep 5
done
echo "[start_phaseE] FAILED to become healthy in 300s" >&2
exit 1
