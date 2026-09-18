#!/bin/bash
# tensor 分割の起動プローブ。$1 = 試行回数, $2 = GGML_CUDA_ALLREDUCE の値 (空なら既定)
M=/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.6-35B-A3B-GGUF/snapshots/a483e9e6cbd595906af30beda3187c2663a1118c/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf
N=${1:-3}; AR=${2:-}
PREFIX=""; [ -n "$AR" ] && PREFIX="env GGML_CUDA_ALLREDUCE=$AR"
OK=0
for i in $(seq 1 $N); do
  pkill -x llama-server 2>/dev/null; sleep 3
  LOG=/tmp/probe-try$i.log
  setsid nohup $PREFIX ~/llama.cpp/build/bin/llama-server -m "$M" --host 127.0.0.1 --port 18099 \
    --device CUDA0,CUDA1,CUDA2,CUDA3 --split-mode tensor -ngl all -fa on -c 8192 \
    --parallel 1 -t 16 --jinja --cache-type-k q8_0 --cache-type-v q8_0 > $LOG 2>&1 < /dev/null &
  R=""
  for s in $(seq 1 36); do
    R=$(curl -s -m 2 http://127.0.0.1:18099/health 2>/dev/null)
    case "$R" in *'"status":"ok"'*) break;; esac
    sleep 5
  done
  case "$R" in
    *'"status":"ok"'*) echo "try$i: OK (${s}x5s)"; OK=$((OK+1));;
    *) echo "try$i: HANG/FAIL last=$R"
       nvidia-smi --query-gpu=index,utilization.gpu,utilization.memory --format=csv,noheader | paste -sd'|'
       tail -3 $LOG;;
  esac
  pkill -x llama-server 2>/dev/null; sleep 5
  if ! ~/llama.cpp/build/bin/llama-server --list-devices 2>&1 | grep -q CUDA0; then
    echo "try$i: CUDA BROKEN after kill"; break
  fi
done
echo "RESULT: $OK/$N ok (AR=${AR:-default})"
