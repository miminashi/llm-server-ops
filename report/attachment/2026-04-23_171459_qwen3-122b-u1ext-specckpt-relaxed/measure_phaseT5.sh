#!/usr/bin/env bash
# measure_phaseT5.sh - Phase T-5 計測（OT pattern 層範囲スイープ）
# usage:
#   measure_phaseT5.sh <pid> <tag> <prompt_spec>
#     prompt_spec:
#       "文字列" → そのままプロンプト
#       @path    → ファイル読み込み（@ プレフィックス）

set -euo pipefail

PID="${1:?pid required}"
TAG="${2:?tag required}"
PROMPT_SPEC="${3:?prompt spec required (string or @path)}"

HOST="${HOST:-t120h-p100}"
URL="${URL:-http://10.1.4.14:8000}"
OUTDIR="./out_${TAG}"
COOLDOWN="${COOLDOWN:-60}"
DMON_SECS="${DMON_SECS:-30}"
EVAL_MAX_TOKENS="${EVAL_MAX_TOKENS:-256}"
# 長コンテキストの prompt 処理 + eval の合計は最大 2 時間想定
CURL_MAX_TIME="${CURL_MAX_TIME:-7200}"
RUNS="${RUNS:-3}"

# プロンプト本文をロード
if [[ "$PROMPT_SPEC" == @* ]]; then
  PROMPT_FILE="${PROMPT_SPEC#@}"
  if [ ! -f "$PROMPT_FILE" ]; then
    echo "ERROR: prompt file not found: $PROMPT_FILE" >&2
    exit 1
  fi
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
  ssh "$HOST" "cat /proc/${PID}/sched | grep -E 'nr_migrations|nr_switches|nr_voluntary_switches|nr_involuntary_switches|se\\.exec_start' || true" > "${OUTDIR}/sched_${phase}.txt" 2>&1 || true
}

build_payload() {
  # 各 Run にユニーク prefix を付けて prompt cache hit を避ける
  # 大きい content は --arg ではなく --rawfile + tmpfile で渡す (ARG_MAX 対策)
  local run_marker="$1"
  local tmp
  tmp=$(mktemp)
  printf '[Request ID %s] ' "$run_marker" > "$tmp"
  printf '%s' "$EVAL_PROMPT" >> "$tmp"
  jq -n \
    --arg model "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" \
    --rawfile content "$tmp" \
    --argjson max_tokens "$EVAL_MAX_TOKENS" \
    '{model: $model, messages: [{role: "user", content: $content}], max_tokens: $max_tokens, stream: false, temperature: 0.6, top_p: 0.95}'
  rm -f "$tmp"
}

run_eval() {
  local run="$1"
  log "Run ${run}: dmon start (background, ${DMON_SECS}s)"
  ssh "$HOST" "nvidia-smi dmon -s pucvmet -c ${DMON_SECS}" > "${OUTDIR}/dmon_run${run}.log" 2>&1 &
  local dmon_pid=$!

  local run_marker="${TAG}_r${run}_$(date +%s%N)"
  log "Run ${run}: eval request (prompt bytes=$(printf '%s' "$EVAL_PROMPT" | wc -c), marker=${run_marker})"
  build_payload "$run_marker" | curl -sS -X POST "${URL}/v1/chat/completions" \
    --max-time "$CURL_MAX_TIME" \
    -H 'Content-Type: application/json' \
    --data-binary @- > "${OUTDIR}/eval_run${run}.json" || {
    log "Run ${run}: curl FAILED (timeout or error)"
    echo '{}' > "${OUTDIR}/eval_run${run}.json"
  }

  local eval_v prompt_v prompt_n predicted_n
  eval_v=$(jq -r '.timings.predicted_per_second // "n/a"' "${OUTDIR}/eval_run${run}.json")
  prompt_v=$(jq -r '.timings.prompt_per_second // "n/a"' "${OUTDIR}/eval_run${run}.json")
  prompt_n=$(jq -r '.timings.prompt_n // "n/a"' "${OUTDIR}/eval_run${run}.json")
  predicted_n=$(jq -r '.timings.predicted_n // "n/a"' "${OUTDIR}/eval_run${run}.json")
  log "Run ${run}: eval=${eval_v} prompt=${prompt_v} prompt_n=${prompt_n} predicted_n=${predicted_n}"
  timings_json=$(jq -c '.timings // {}' "${OUTDIR}/eval_run${run}.json")
  log "Run ${run}: timings=${timings_json}"

  wait "$dmon_pid" || true

  log "Run ${run}: status snapshot"
  ssh "$HOST" "cat /proc/${PID}/status | grep -E 'Threads|Cpus_allowed_list|voluntary_ctxt_switches|nonvoluntary_ctxt_switches'" \
    > "${OUTDIR}/status_run${run}.txt" 2>&1 || true
  ssh "$HOST" "nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv,noheader" \
    > "${OUTDIR}/gpu_post_run${run}.csv" 2>&1 || true
}

log "==== measure_phaseT5 start tag=${TAG} pid=${PID} ===="
log "wait /health"
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  if curl -sf "${URL}/health" > /dev/null 2>&1; then
    log "/health OK"
    break
  fi
  sleep 5
done

ssh "$HOST" "cat /proc/${PID}/cmdline | tr '\0' ' '; echo" > "${OUTDIR}/cmdline.txt" 2>&1 || true

log "numastat -p (pre)"
ssh "$HOST" "numastat -p ${PID}" > "${OUTDIR}/numastat_pre.txt" 2>&1 || true

log "snap_extras (pre)"
snap_extras pre

for run in $(seq 1 "$RUNS"); do
  if [ "$run" -gt 1 ]; then
    log "cooldown ${COOLDOWN}s before run ${run}"
    sleep "$COOLDOWN"
  fi
  run_eval "$run"
done

log "numastat -p (post)"
ssh "$HOST" "numastat -p ${PID}" > "${OUTDIR}/numastat_post.txt" 2>&1 || true

log "snap_extras (post)"
snap_extras post

log "==== summary (predicted_per_second / prompt_per_second / prompt_n / predicted_n) ===="
for run in $(seq 1 "$RUNS"); do
  eval_v=$(jq -r '.timings.predicted_per_second // "n/a"' "${OUTDIR}/eval_run${run}.json")
  prompt_v=$(jq -r '.timings.prompt_per_second // "n/a"' "${OUTDIR}/eval_run${run}.json")
  prompt_n=$(jq -r '.timings.prompt_n // "n/a"' "${OUTDIR}/eval_run${run}.json")
  predicted_n=$(jq -r '.timings.predicted_n // "n/a"' "${OUTDIR}/eval_run${run}.json")
  echo "run${run}: eval=${eval_v} prompt=${prompt_v} prompt_n=${prompt_n} predicted_n=${predicted_n}" | tee -a "${OUTDIR}/timeline.log"
done

log "==== measure_phaseT5 end tag=${TAG} ===="
