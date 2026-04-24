#!/usr/bin/env bash
# measure_phaseE.sh - Phase E の軽量計測（dmon + curl eval + status + numastat snap）
# usage: measure_phaseE.sh <pid> <tag>

set -euo pipefail

PID="${1:?pid required}"
TAG="${2:?tag required}"
HOST="${HOST:-t120h-p100}"
URL="${URL:-http://10.1.4.14:8000}"
OUTDIR="./out_${TAG}"
COOLDOWN="${COOLDOWN:-60}"
DMON_SECS=20
EVAL_PROMPT='Write a short haiku about autumn.'
EVAL_MAX_TOKENS=256

mkdir -p "$OUTDIR"

log() { echo "[$(TZ=Asia/Tokyo date +%H:%M:%S)] $*" | tee -a "${OUTDIR}/timeline.log"; }

run_eval() {
  local run="$1"
  log "Run ${run}: dmon start (background, ${DMON_SECS}s)"
  ssh "$HOST" "nvidia-smi dmon -s pucvmet -c ${DMON_SECS}" > "${OUTDIR}/dmon_run${run}.log" 2>&1 &
  local dmon_pid=$!

  log "Run ${run}: eval request"
  curl -sS -X POST "${URL}/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d "$(cat <<EOF
{
  "model": "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M",
  "messages": [{"role": "user", "content": "${EVAL_PROMPT}"}],
  "max_tokens": ${EVAL_MAX_TOKENS},
  "stream": false,
  "temperature": 0.6,
  "top_p": 0.95
}
EOF
)" > "${OUTDIR}/eval_run${run}.json"

  log "Run ${run}: eval done, predicted_per_second=$(jq -r '.timings.predicted_per_second // "n/a"' "${OUTDIR}/eval_run${run}.json")"

  wait "$dmon_pid" || true

  if [ "$run" = "3" ]; then
    log "Run 3: status snapshot"
    ssh "$HOST" "cat /proc/${PID}/status | grep -E 'Threads|Cpus_allowed_list|voluntary_ctxt_switches|nonvoluntary_ctxt_switches'" \
      > "${OUTDIR}/status_run${run}.txt"
  fi
}

log "==== measure_phaseE start tag=${TAG} pid=${PID} ===="
log "wait /health"
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  if curl -sf "${URL}/health" > /dev/null 2>&1; then
    log "/health OK"
    break
  fi
  sleep 5
done

ssh "$HOST" "cat /proc/${PID}/cmdline | tr '\0' ' '; echo" > "${OUTDIR}/cmdline.txt" 2>&1 || true

log "numastat snapshot (pre-run)"
ssh "$HOST" "numastat -p ${PID}" > "${OUTDIR}/numastat_pre.txt" 2>&1 || true

for run in 1 2 3; do
  if [ "$run" -gt 1 ]; then
    log "cooldown ${COOLDOWN}s before run ${run}"
    sleep "$COOLDOWN"
  fi
  run_eval "$run"
done

log "numastat snapshot (post-run)"
ssh "$HOST" "numastat -p ${PID}" > "${OUTDIR}/numastat_post.txt" 2>&1 || true

log "==== summary (predicted_per_second / prompt_per_second) ===="
for run in 1 2 3; do
  eval_v=$(jq -r '.timings.predicted_per_second // "n/a"' "${OUTDIR}/eval_run${run}.json")
  prompt_v=$(jq -r '.timings.prompt_per_second // "n/a"' "${OUTDIR}/eval_run${run}.json")
  echo "run${run}: eval=${eval_v} prompt=${prompt_v}" | tee -a "${OUTDIR}/timeline.log"
done

log "==== measure_phaseE end tag=${TAG} ===="
