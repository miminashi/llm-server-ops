#!/usr/bin/env bash
# usage: real-arm.sh <tag> <arm>
# Re-launches the exact server argv recorded for <arm> and runs measure_real.py
# into runs/<tag>/real-<arm>/ so it never clobbers the run's own results-real.json
# (measure_real.py writes real-response-*.txt next to --out).
set -u
TAG="$1"; ARM="$2"
HERE=$HOME/llama-split-bench
D="$HERE/runs/$TAG"
OUT="$D/real-$ARM"
mkdir -p "$OUT"

pkill -x llama-server 2>/dev/null
for i in $(seq 1 60); do
  busy=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits | awk '$1>5{c++} END{print c+0}')
  procs=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader | wc -l)
  [ "$busy" = "0" ] && [ "$procs" = "0" ] && break
  sleep 2
done

mapfile -t ARGS < "$D/argv-$ARM.txt"
PORT=$(awk '/^--port$/{getline; print}' "$D/argv-$ARM.txt")
: "${PORT:=18081}"
printf '%s\n' "${ARGS[@]}" > "$OUT/argv-used.txt"

setsid nohup "${ARGS[@]}" > "$OUT/server.log" 2>&1 < /dev/null &
SRV=$!
ok=0
for i in $(seq 1 120); do
  if curl -s -m 2 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"status":"ok"'; then ok=1; break; fi
  kill -0 "$SRV" 2>/dev/null || { echo "REAL-ABORT $ARM: server exited"; tail -5 "$OUT/server.log"; exit 1; }
  sleep 5
done
[ "$ok" = 1 ] || { echo "REAL-ABORT $ARM: not ready"; tail -5 "$OUT/server.log"; pkill -x llama-server; exit 1; }
echo "REAL-READY $ARM port=$PORT $(date +%H:%M:%S)"
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader | tr '\n' ' '; echo

python3 "$HERE/measure_real.py" --url "http://127.0.0.1:$PORT" --out "$OUT/results-real-$ARM.json"
rc=$?
pkill -x llama-server 2>/dev/null
sleep 3
pgrep -x llama-server >/dev/null && { sleep 10; pkill -9 -x llama-server; }
echo "REAL-DONE $ARM rc=$rc $(date +%H:%M:%S)"
