#!/usr/bin/env bash
# measure_phaseU4.sh - Phase U-4 計測 (MODEL_ALIAS 可変 + RUNS 可変)
# usage: measure_phaseU4.sh <pid> <tag> <prompt_spec>
set -euo pipefail

PID="${1:?pid required}"
TAG="${2:?tag required}"
PROMPT_SPEC="${3:?prompt spec required (string or @path)}"

HOST="${HOST:-t120h-p100}"
URL="${URL:-http://10.1.4.14:8000}"
MODEL_ALIAS="${MODEL_ALIAS:?MODEL_ALIAS env required}"
OUTDIR="./out_${TAG}"
COOLDOWN="${COOLDOWN:-60}"
DMON_SECS="${DMON_SECS:-30}"
EVAL_MAX_TOKENS="${EVAL_MAX_TOKENS:-256}"
CURL_MAX_TIME="${CURL_MAX_TIME:-7200}"
RUNS="${RUNS:-5}"

if [[ "$PROMPT_SPEC" == @* ]]; then
  PROMPT_FILE="${PROMPT_SPEC#@}"
  [ -f "$PROMPT_FILE" ] || { echo "ERROR: prompt file not found: $PROMPT_FILE" >&2; exit 1; }
  EVAL_PROMPT="$(cat "$PROMPT_FILE")"
else
  EVAL_PROMPT="$PROMPT_SPEC"
fi

mkdir -p "$OUTDIR"
log() { echo "[$(TZ=Asia/Tokyo date +%H:%M:%S)] $*" | tee -a "${OUTDIR}/timeline.log"; }

snap_extras() {
  local phase="$1"
  ssh "$HOST" "free -w" > "${OUTDIR}/free_${phase}.txt" 2>&1 || true
  ssh "$HOST" "numastat -m | head -30" > "${OUTDIR}/numastat_m_${phase}.txt" 2>&1 || true
  ssh "$HOST" "nvidia-smi --query-gpu=index,memory.used,memory.free,temperature.gpu,clocks.current.sm --format=csv" > "${OUTDIR}/gpu_${phase}.csv" 2>&1 || true
}

build_payload() {
  local run_marker="$1"
  local tmp
  tmp=$(mktemp)
  printf '[Request ID %s] ' "$run_marker" > "$tmp"
  printf '%s' "$EVAL_PROMPT" >> "$tmp"
  jq -n \
    --arg model "$MODEL_ALIAS" \
    --rawfile content "$tmp" \
    --argjson max_tokens "$EVAL_MAX_TOKENS" \
    '{model: $model, messages: [{role: "user", content: $content}], max_tokens: $max_tokens, stream: false, temperature: 0.6, top_p: 0.95}'
  rm -f "$tmp"
}

run_eval() {
  local run="$1"
  log "Run ${run}: dmon start (${DMON_SECS}s)"
  ssh "$HOST" "nvidia-smi dmon -s pucvmet -c ${DMON_SECS}" > "${OUTDIR}/dmon_run${run}.log" 2>&1 &
  local dmon_pid=$!

  local run_marker="${TAG}_r${run}_$(date +%s%N)"
  log "Run ${run}: eval (marker=${run_marker})"
  build_payload "$run_marker" | curl -sS -X POST "${URL}/v1/chat/completions" \
    --max-time "$CURL_MAX_TIME" \
    -H 'Content-Type: application/json' \
    --data-binary @- > "${OUTDIR}/eval_run${run}.json" || {
    log "Run ${run}: curl FAILED"
    echo '{}' > "${OUTDIR}/eval_run${run}.json"
  }

  local eval_v prompt_v prompt_n predicted_n prompt_ms
  eval_v=$(jq -r '.timings.predicted_per_second // "n/a"' "${OUTDIR}/eval_run${run}.json")
  prompt_v=$(jq -r '.timings.prompt_per_second // "n/a"' "${OUTDIR}/eval_run${run}.json")
  prompt_n=$(jq -r '.timings.prompt_n // "n/a"' "${OUTDIR}/eval_run${run}.json")
  predicted_n=$(jq -r '.timings.predicted_n // "n/a"' "${OUTDIR}/eval_run${run}.json")
  prompt_ms=$(jq -r '.timings.prompt_ms // "n/a"' "${OUTDIR}/eval_run${run}.json")
  log "Run ${run}: eval=${eval_v} prompt=${prompt_v} prompt_ms=${prompt_ms} prompt_n=${prompt_n} predicted_n=${predicted_n}"
  wait "$dmon_pid" || true
}

log "==== measure_phaseU4 start tag=${TAG} pid=${PID} alias=${MODEL_ALIAS} ===="
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  if curl -sf "${URL}/health" > /dev/null 2>&1; then log "/health OK"; break; fi
  sleep 5
done

ssh "$HOST" "cat /proc/${PID}/cmdline | tr '\0' ' '; echo" > "${OUTDIR}/cmdline.txt" 2>&1 || true
snap_extras pre
for run in $(seq 1 "$RUNS"); do
  [ "$run" -gt 1 ] && { log "cooldown ${COOLDOWN}s"; sleep "$COOLDOWN"; }
  run_eval "$run"
done
snap_extras post

log "==== summary (tag=${TAG}) ===="
for run in $(seq 1 "$RUNS"); do
  eval_v=$(jq -r '.timings.predicted_per_second // "n/a"' "${OUTDIR}/eval_run${run}.json")
  prompt_v=$(jq -r '.timings.prompt_per_second // "n/a"' "${OUTDIR}/eval_run${run}.json")
  prompt_n=$(jq -r '.timings.prompt_n // "n/a"' "${OUTDIR}/eval_run${run}.json")
  predicted_n=$(jq -r '.timings.predicted_n // "n/a"' "${OUTDIR}/eval_run${run}.json")
  prompt_ms=$(jq -r '.timings.prompt_ms // "n/a"' "${OUTDIR}/eval_run${run}.json")
  echo "run${run}: eval=${eval_v} prompt=${prompt_v} prompt_ms=${prompt_ms} prompt_n=${prompt_n} predicted_n=${predicted_n}" | tee -a "${OUTDIR}/timeline.log"
done
log "==== measure_phaseU4 end ===="
