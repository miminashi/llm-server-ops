#!/bin/bash
# usage: probe2.sh <tag> <timeout_sec> <env-assignments...> -- <extra llama-server args...>
TAG="$1"; shift
TMO="$1"; shift
ENVS=()
while [ "$1" != "--" ]; do ENVS+=("$1"); shift; done
shift
LOG=/tmp/probe-$TAG.log
pkill -x llama-server 2>/dev/null
# GPU が完全にアイドルに戻るまで待つ(前試行のスピンカーネル残留対策)
for i in $(seq 1 30); do
  busy=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits | awk '$1>5{c++} END{print c+0}')
  procs=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader | wc -l)
  [ "$busy" = "0" ] && [ "$procs" = "0" ] && break
  sleep 2
done
env "${ENVS[@]}" setsid nohup ~/llama.cpp/build/bin/llama-server \
  -m ~/models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf \
  --host 127.0.0.1 --port 18099 \
  -ngl all -fa on --parallel 1 -t 16 --jinja \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  "$@" > "$LOG" 2>&1 < /dev/null &
SRVPID=$!
END=$((SECONDS+TMO))
RESULT=TIMEOUT
while [ $SECONDS -lt $END ]; do
  if grep -q "listening on" "$LOG" 2>/dev/null; then RESULT=OK; break; fi
  if grep -qE "terminate called|out of memory|has no device code" "$LOG" 2>/dev/null; then RESULT=ERROR; break; fi
  if ! kill -0 $SRVPID 2>/dev/null; then RESULT=DIED; break; fi
  sleep 2
done
GPU=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits | tr '\n' ',')
echo "RESULT=$RESULT tag=$TAG elapsed=${SECONDS}s gpu=[$GPU] idlewait=$(($i*2))s"
pkill -x llama-server 2>/dev/null
