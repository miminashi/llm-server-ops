#!/bin/bash
# usage: infer.sh <tag> <env...> -- <llama-server args...>
# 起動して推論を1発叩き、decode t/s と draft 統計を出す。必ず停止する。
TAG="$1"; shift
ENVS=()
while [ "$1" != "--" ]; do ENVS+=("$1"); shift; done
shift
LOG=/tmp/infer-$TAG.log
pkill -x llama-server 2>/dev/null
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
END=$((SECONDS+60)); OK=0
while [ $SECONDS -lt $END ]; do
  grep -q "listening on" "$LOG" 2>/dev/null && { OK=1; break; }
  sleep 2
done
if [ $OK = 0 ]; then echo "tag=$TAG START=HANG"; pkill -x llama-server; exit 0; fi
R=$(curl -s --max-time 300 http://127.0.0.1:18099/completion -H 'Content-Type: application/json' \
  -d '{"prompt":"Write a short technical explanation of how a GPU executes a matrix multiplication.","n_predict":300,"temperature":0.7,"cache_prompt":false}')
echo "tag=$TAG START=OK"
echo "$R" | python3 -c "import sys,json; d=json.load(sys.stdin); t=d.get('timings',{}); print('  decode=%.2f t/s prefill=%.2f t/s n_gen=%s draft_n=%s draft_acc=%s' % (t.get('predicted_per_second',0), t.get('prompt_per_second',0), t.get('predicted_n'), t.get('draft_n'), t.get('draft_n_accepted')))" 2>/dev/null || echo "  (parse failed) ${R:0:200}"
pkill -x llama-server 2>/dev/null
