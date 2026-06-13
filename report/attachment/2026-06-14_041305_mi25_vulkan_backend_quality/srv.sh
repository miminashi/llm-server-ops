#!/bin/bash
# 使い方: srv.sh start <rocm|vulkan> | srv.sh stop | srv.sh health
# llama-server を perplexity と同一の実証済み invocation で起動(3 RADV/ROCm, q8_0/FA)。
set -uo pipefail
MODEL=/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.6-35B-A3B-GGUF/snapshots/a483e9e6cbd595906af30beda3187c2663a1118c/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf
BENCH=/home/llm/bench-quality
PORT=8000
PIDF="$BENCH/srv.pid"

cmd="${1:-}"
case "$cmd" in
  start)
    backend="${2:-rocm}"
    if [ "$backend" = "rocm" ]; then BIN=/home/llm/llama.cpp/build/bin/llama-server; else BIN=/home/llm/llama.cpp/build-vulkan/bin/llama-server; fi
    unset GGML_VK_VISIBLE_DEVICES
    # Qwen3.6推奨 + 決定論計測のためサンプリングはリクエスト側で上書きする。サーバ既定は最小限。
    nohup "$BIN" -m "$MODEL" --host 0.0.0.0 --port $PORT \
      --flash-attn 1 --cache-type-k q8_0 --cache-type-v q8_0 -ngl 99 \
      -c 16384 -b 2048 -ub 2048 --poll 0 \
      > "$BENCH/server-$backend.log" 2>&1 &
    echo $! > "$PIDF"
    echo "STARTED $backend pid=$(cat $PIDF)"
    ;;
  stop)
    if [ -f "$PIDF" ]; then kill "$(cat $PIDF)" 2>/dev/null; sleep 2; kill -9 "$(cat $PIDF)" 2>/dev/null; rm -f "$PIDF"; fi
    pkill -f "llama-server -m $MODEL" 2>/dev/null
    echo "STOPPED"
    ;;
  health)
    code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$PORT/health 2>/dev/null)
    echo "HEALTH=$code"
    ;;
  *) echo "usage: srv.sh start <rocm|vulkan> | stop | health"; exit 2 ;;
esac
