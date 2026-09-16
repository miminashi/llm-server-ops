#!/usr/bin/env bash
# Re-measure the tensor arm on the DEFAULT NCCL AllReduce at ctx=131072.
# The start hangs probabilistically, so retry the launch until one gets past
# warm-up, then drive the same three measure_*.py steps run-bench.sh uses.
set -u
HERE=$HOME/llama-split-bench
TAG=gpu01-7way-tensor-nccl-nomtp
D="$HERE/runs/$TAG"
SRC="$HERE/runs/gpu01-7way-1/argv-tensor.txt"   # 2026-09-14 argv: NCCL default, SPEC_ARGS=""
PORT=18081
TRIES=${1:-8}
WAIT=${2:-100}
mkdir -p "$D"
cp "$SRC" "$D/argv-tensor.txt"
mapfile -t ARGS < "$D/argv-tensor.txt"

idle() {
  # 1) no llama-server left, 2) no compute apps and no busy GPU,
  # 3) CUDA actually initialises again -- killing a spin-kernel process leaves the
  #    driver in a state where ggml_cuda_init fails with "unknown error" for a while,
  #    and the next launch then dies on "invalid device: CUDA0".
  for i in $(seq 1 90); do
    pgrep -x llama-server >/dev/null && { sleep 2; continue; }
    busy=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | awk '$1>5{c++} END{print c+0}')
    procs=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | wc -l)
    if [ "$busy" = "0" ] && [ "$procs" = "0" ]; then
      n=$("$HOME/llama.cpp/build/bin/llama-server" --list-devices 2>/dev/null | grep -c "^  CUDA[0-9]")
      [ "$n" = "7" ] && return 0
    fi
    sleep 2
  done
  echo "idle(): GPUs never came back clean"
  return 1
}

ok=0
for t in $(seq 1 "$TRIES"); do
  idle || { echo "NCCL-GIVEUP: CUDA never recovered"; exit 1; }
  setsid nohup "${ARGS[@]}" > "$D/server-try$t.log" 2>&1 < /dev/null &
  SRV=$!
  for i in $(seq 1 $((WAIT / 5))); do
    if curl -s -m 2 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"status":"ok"'; then ok=1; break; fi
    kill -0 "$SRV" 2>/dev/null || break
    sleep 5
  done
  if [ "$ok" = 1 ]; then
    echo "NCCL-START ok on try $t  $(date +%H:%M:%S)"
    cp "$D/server-try$t.log" "$D/server-tensor.log"
    break
  fi
  echo "NCCL-HANG try $t  $(date +%H:%M:%S)  gpu=[$(nvidia-smi --query-gpu=utilization.gpu,utilization.memory --format=csv,noheader | tr '\n' ' ')]"
  pkill -x llama-server 2>/dev/null; sleep 3
  pgrep -x llama-server >/dev/null && { sleep 8; pkill -9 -x llama-server; }
done
[ "$ok" = 1 ] || { echo "NCCL-GIVEUP after $TRIES tries"; exit 1; }

nvidia-smi --query-gpu=index,memory.used --format=csv,noheader | tr '\n' ' '; echo
STOP="$D/sampler-tensor.stop"; rm -f "$STOP"
( while [ ! -f "$STOP" ]; do
    echo "$(date +%H:%M:%S) $(nvidia-smi --query-gpu=index,temperature.gpu,temperature.memory,power.draw,utilization.gpu --format=csv,noheader,nounits 2>/dev/null | tr '\n' '|')"
    sleep 2
  done > "$D/sampler-tensor.log" 2>&1 ) &
SAMPLER=$!

U="http://127.0.0.1:$PORT"
python3 "$HERE/measure_ladder.py" --tag tensor --stages 0,16000,32000,64000,128000 \
  --n-predict 1000 --url "$U" --out "$D" --guard-devices 0,1,2,3,4,5,6 \
  --ratio-init 4.3 --server-pid "$SRV"
python3 "$HERE/measure_pp0.py" --tag tensor --sizes 512,2048,8192 --url "$U" \
  --out "$D/results-tensor-pp0.json" --chars-per-token 4.3
python3 "$HERE/measure_real.py" --url "$U" --out "$D/results-real.json"

touch "$STOP"; wait $SAMPLER 2>/dev/null; kill -9 $SAMPLER 2>/dev/null
pkill -x llama-server 2>/dev/null; sleep 3
pgrep -x llama-server >/dev/null && { sleep 10; pkill -9 -x llama-server; }
echo "NCCL-DONE $(date +%H:%M:%S)"
