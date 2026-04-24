#!/usr/bin/env bash
# measure_phaseU6.sh - Phase U-6: 1 セル分 warmup + eval 計測
# usage:
#   CELL=<cell_id> PID=<pid> OUTDIR=<path> PROMPT_TAG=<1k|32k|96k> PROMPT_FILE=<path> \
#     COND_ID=<B14b|B18|B20> UB=<256|512|1024> \
#     WARMUP_RUNS=<N> EVAL_RUNS=<N> EVAL_MAX_TOKENS=<N> COOLDOWN=<N> \
#     CSV=<path> \
#     bash measure_phaseU6.sh
set -euo pipefail

CELL="${CELL:?CELL required (e.g. B14b_ub512_1k)}"
PID="${PID:?PID required}"
OUTDIR="${OUTDIR:?OUTDIR required}"
PROMPT_TAG="${PROMPT_TAG:?PROMPT_TAG required (1k|32k|96k)}"
PROMPT_FILE="${PROMPT_FILE:?PROMPT_FILE required}"
COND_ID="${COND_ID:?COND_ID required}"
UB="${UB:?UB required}"
WARMUP_RUNS="${WARMUP_RUNS:-2}"
EVAL_RUNS="${EVAL_RUNS:-5}"
EVAL_MAX_TOKENS="${EVAL_MAX_TOKENS:-512}"
COOLDOWN="${COOLDOWN:-15}"
CSV="${CSV:?CSV required}"

HOST="${HOST:-t120h-p100}"
URL="${URL:-http://10.1.4.14:8000}"
CURL_MAX_TIME="${CURL_MAX_TIME:-3600}"

mkdir -p "$OUTDIR"
PROMPT="$(cat "$PROMPT_FILE")"

log() { echo "[$(TZ=Asia/Tokyo date +%H:%M:%S)] [measure] $*" | tee -a "${OUTDIR}/timeline.log"; }

build_payload() {
  local run_marker="$1"
  local tmp
  tmp=$(mktemp)
  printf '[Request ID %s] ' "$run_marker" > "$tmp"
  printf '%s' "$PROMPT" >> "$tmp"
  jq -n \
    --arg model "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" \
    --rawfile content "$tmp" \
    --argjson max_tokens "$EVAL_MAX_TOKENS" \
    '{model: $model, messages: [{role: "user", content: $content}], max_tokens: $max_tokens, stream: false, temperature: 0.6, top_p: 0.95}'
  rm -f "$tmp"
}

run_one() {
  local role="$1"  # warmup | eval
  local idx="$2"
  local run_id="${role}${idx}"
  local run_marker="${CELL}_${run_id}_$(date +%s%N)"
  local out="${OUTDIR}/${run_id}.json"

  log "${CELL} ${run_id}: start (prompt_tag=${PROMPT_TAG} prompt_bytes=$(printf '%s' "$PROMPT" | wc -c))"

  # GPU 空き VRAM モニタ (開始 + 5s 間隔で 3 点取得)
  ssh -o ConnectTimeout=5 -o BatchMode=yes "$HOST" \
    "nvidia-smi --query-gpu=index,memory.free --format=csv,noheader,nounits" \
    > "${OUTDIR}/${run_id}_gpu_pre.csv" 2>&1 || true

  local t_start=$(date +%s)
  build_payload "$run_marker" | curl -sS -X POST "${URL}/v1/chat/completions" \
    --max-time "$CURL_MAX_TIME" \
    -H 'Content-Type: application/json' \
    --data-binary @- > "$out" || {
    log "${CELL} ${run_id}: curl FAILED"
    echo '{"error":"curl_failed"}' > "$out"
  }
  local t_end=$(date +%s)
  local wallclock=$((t_end - t_start))

  ssh -o ConnectTimeout=5 -o BatchMode=yes "$HOST" \
    "nvidia-smi --query-gpu=index,memory.free --format=csv,noheader,nounits" \
    > "${OUTDIR}/${run_id}_gpu_post.csv" 2>&1 || true

  local eval_tps prompt_tps prompt_n predicted_n prompt_ms predicted_ms err
  eval_tps=$(jq -r '.timings.predicted_per_second // ""' "$out" 2>/dev/null)
  prompt_tps=$(jq -r '.timings.prompt_per_second // ""' "$out" 2>/dev/null)
  prompt_n=$(jq -r '.timings.prompt_n // ""' "$out" 2>/dev/null)
  predicted_n=$(jq -r '.timings.predicted_n // ""' "$out" 2>/dev/null)
  prompt_ms=$(jq -r '.timings.prompt_ms // ""' "$out" 2>/dev/null)
  predicted_ms=$(jq -r '.timings.predicted_ms // ""' "$out" 2>/dev/null)
  err=$(jq -r '.error // ""' "$out" 2>/dev/null)

  # min GPU free (pre/post から min)
  local min_gpu_free
  min_gpu_free=$(awk -F, '{gsub(/[^0-9]/,"",$2); if($2!="") print $2}' \
    "${OUTDIR}/${run_id}_gpu_pre.csv" "${OUTDIR}/${run_id}_gpu_post.csv" 2>/dev/null \
    | sort -n | head -1)
  [ -z "$min_gpu_free" ] && min_gpu_free=""

  log "${CELL} ${run_id}: eval=${eval_tps} prompt=${prompt_tps} prompt_n=${prompt_n} pred_n=${predicted_n} wall=${wallclock}s min_gpu=${min_gpu_free}"

  # CSV 行
  printf "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n" \
    "$CELL" "$COND_ID" "$UB" "$PROMPT_TAG" "$role" "$idx" \
    "${eval_tps}" "${prompt_tps}" "${prompt_n}" "${predicted_n}" \
    "${prompt_ms}" "${predicted_ms}" "${wallclock}" "${min_gpu_free}" "${err}" \
    >> "$CSV"
}

log "==== measure_phaseU6 cell=${CELL} ===="
log "/health wait"
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  if curl -sf "${URL}/health" > /dev/null 2>&1; then
    log "/health OK"
    break
  fi
  sleep 5
done

# warmup
for i in $(seq 1 "$WARMUP_RUNS"); do
  [ "$i" -gt 1 ] && sleep "$COOLDOWN"
  run_one warmup "$i"
done

# eval
for i in $(seq 1 "$EVAL_RUNS"); do
  sleep "$COOLDOWN"
  run_one eval "$i"
done

log "==== measure_phaseU6 cell=${CELL} end ===="
