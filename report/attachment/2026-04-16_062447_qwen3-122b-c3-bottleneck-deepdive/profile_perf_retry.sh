#!/usr/bin/env bash
# perf stat / perf record を paranoid=0 環境で再計測
# profile_phaseA.sh と同じ eval プロンプトを 3 run 投入しつつ perf を採取
set -euo pipefail

LLAMA_PID="${1:?usage: profile_perf_retry.sh <LLAMA_PID>}"
ATTACH="$(cd "$(dirname "$0")" && pwd)"
HOST="t120h-p100"
SSH_OPTS="-o ServerAliveInterval=10 -o ServerAliveCountMax=3"

API_URL="http://10.1.4.14:8000/v1/chat/completions"
PROMPT='Write a short haiku about autumn.'
REQ_JSON=$(cat <<EOF
{"model":"unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M","messages":[{"role":"user","content":"$PROMPT"}],"max_tokens":256,"temperature":0.6,"top_p":0.95,"top_k":20}
EOF
)

ts_now() { TZ=Asia/Tokyo date +%Y-%m-%dT%H:%M:%S.%N; }
TL="$ATTACH/phaseA_perf_timeline.log"
: > "$TL"

run_perf_window() {
  local RUN="$1" SEC="$2" DO_EVAL="$3"
  echo "=== perf Run $RUN (${SEC}s, eval=${DO_EVAL}) ==="

  ssh $SSH_OPTS "$HOST" "perf stat -a -e cycles,instructions,cache-misses,cache-references,LLC-loads,LLC-load-misses,node-loads,node-load-misses,dTLB-loads,dTLB-load-misses -- sleep $SEC" \
    > "$ATTACH/phaseA_perfstat_run${RUN}.log" 2>&1 &
  local PFPID=$!

  local PRPID=""
  if [[ "$RUN" == "3" ]]; then
    ssh $SSH_OPTS "$HOST" "perf record -g -F 99 -a -o /tmp/perf_phaseA_run3.data -- sleep $SEC" \
      > "$ATTACH/phaseA_perfrec_run${RUN}.log" 2>&1 &
    PRPID=$!
  fi

  sleep 3

  if [[ "$DO_EVAL" == "1" ]]; then
    local S E
    S=$(ts_now)
    curl -s "$API_URL" -H 'Content-Type: application/json' -d "$REQ_JSON" \
      > "$ATTACH/phaseA_eval_perf_run${RUN}.json" 2>&1
    E=$(ts_now)
    echo "run=$RUN eval_start=$S eval_end=$E" >> "$TL"
  else
    echo "run=$RUN (idle) $(ts_now)" >> "$TL"
  fi

  wait $PFPID 2>/dev/null || true
  if [[ -n "$PRPID" ]]; then wait "$PRPID" 2>/dev/null || true; fi
}

run_perf_window 0 20 0
for R in 1 2 3; do
  run_perf_window "$R" 40 1
  if [[ "$R" != "3" ]]; then
    echo "--- cooldown 45s ---"
    sleep 45
  fi
done

# perf.data → text report
ssh $SSH_OPTS "$HOST" "test -f /tmp/perf_phaseA_run3.data && cd /tmp && perf report -i perf_phaseA_run3.data --stdio --no-children 2>/dev/null | head -n 200" \
  > "$ATTACH/phaseA_perf_report_run3.txt" 2>&1 || true

echo "perf retry DONE"
