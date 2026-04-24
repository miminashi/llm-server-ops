#!/usr/bin/env bash
# Phase B: numactl --cpunodebind=1 --membind=1 で C-3 を再起動
# モデルメモリが既に Node 1 側に偏在しているため、Node 1 固定で inter-socket 転送を排除する
set -euo pipefail
HOST="t120h-p100"

MODEL_PATH="/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf"

LAUNCH_CMD="numactl --cpunodebind=1 --membind=1 -- ./build/bin/llama-server \
  -m '$MODEL_PATH' --jinja \
  -ngl 999 -ot 'blk\\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\\.ffn_.*_exps\\.weight=CPU' \
  --flash-attn 1 --poll 0 -b 8192 -ub 8192 \
  --n-predict 32768 --threads -1 \
  --ctx-size 131072 --parallel 1 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --defrag-thold 0.1 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 \
  --port 8000 --host 0.0.0.0 \
  --alias 'unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M'"

.claude/skills/llama-server/scripts/stop.sh "$HOST" || true

ssh -f "$HOST" "cd ~/llama.cpp && nohup bash -c \"$LAUNCH_CMD\" > /tmp/llama-server.log 2>&1 < /dev/null &"

for i in $(seq 1 24); do
  if curl -sf http://10.1.4.14:8000/health > /dev/null; then
    echo "start_phaseB OK after ${i}x5s"
    exit 0
  fi
  sleep 5
done
echo "start_phaseB FAILED /health timeout"
exit 1
