#!/usr/bin/env bash
# Phase B 失敗時のロールバック: numactl 無しで元の C-3 を再起動
set -euo pipefail
HOST="t120h-p100"

MODEL_PATH="/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf"

LAUNCH_CMD="./build/bin/llama-server \
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

# 既存停止
.claude/skills/llama-server/scripts/stop.sh "$HOST" || true

# 起動
ssh -f "$HOST" "cd ~/llama.cpp && nohup bash -c \"$LAUNCH_CMD\" > /tmp/llama-server.log 2>&1 < /dev/null &"

# ヘルスチェック (120 秒以内)
for i in $(seq 1 24); do
  if curl -sf http://10.1.4.14:8000/health > /dev/null; then
    echo "rollback OK after ${i}x5s"
    exit 0
  fi
  sleep 5
done
echo "rollback FAILED /health timeout"
exit 1
