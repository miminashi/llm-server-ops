#!/usr/bin/env bash
# measure_phaseU2_prefix.sh - Phase U-2: shared prefix pattern (system fixed + variable user suffix)
# usage:
#   measure_phaseU2_prefix.sh <pid> <tag> <system_prompt_file> <suffix_tsv>
#     system_prompt_file: 固定 system prompt のファイル (~500 tok 想定)
#     suffix_tsv: header "suffix_id\tcontent"、各行が 1 pattern (~50-100 tok 想定)
#
# messages = [{role: system, content: <system>}, {role: user, content: <suffix>}]
# の 2 メッセージ構造で POST。system 部分が共有 prefix として cache hit するはず。
#
set -euo pipefail

PID="${1:?pid required}"
TAG="${2:?tag required}"
SYS_FILE="${3:?system prompt file required}"
SUF_TSV="${4:?suffix tsv required}"

HOST="${HOST:-t120h-p100}"
URL="${URL:-http://10.1.4.14:8000}"
OUTDIR="./out_${TAG}"
COOLDOWN="${COOLDOWN:-10}"
EVAL_MAX_TOKENS="${EVAL_MAX_TOKENS:-256}"
CURL_MAX_TIME="${CURL_MAX_TIME:-1800}"

[ -f "$SYS_FILE" ] || { echo "ERROR: sys file not found: $SYS_FILE" >&2; exit 1; }
[ -f "$SUF_TSV" ]  || { echo "ERROR: suffix tsv not found: $SUF_TSV" >&2; exit 1; }

mkdir -p "$OUTDIR"

log() { echo "[$(TZ=Asia/Tokyo date +%H:%M:%S)] $*" | tee -a "${OUTDIR}/timeline.log"; }

snap_slots() {
  local phase="$1"
  curl -sS "${URL}/slots" > "${OUTDIR}/slots_${phase}.json" 2>&1 || echo '{}' > "${OUTDIR}/slots_${phase}.json"
}

build_payload() {
  local suffix_content="$1"
  local sys_tmp user_tmp
  sys_tmp=$(mktemp)
  user_tmp=$(mktemp)
  cat "$SYS_FILE" > "$sys_tmp"
  printf '%s' "$suffix_content" > "$user_tmp"
  jq -n \
    --arg model "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" \
    --rawfile sys "$sys_tmp" \
    --rawfile usr "$user_tmp" \
    --argjson max_tokens "$EVAL_MAX_TOKENS" \
    '{model: $model, messages: [{role: "system", content: $sys}, {role: "user", content: $usr}], max_tokens: $max_tokens, stream: false, temperature: 0.6, top_p: 0.95}'
  rm -f "$sys_tmp" "$user_tmp"
}

run_one() {
  local idx="$1"
  local suffix_id="$2"
  local suffix_content="$3"

  snap_slots "pre_${suffix_id}"

  local t0 t1
  t0=$(date +%s.%N)
  build_payload "$suffix_content" | curl -sS -X POST "${URL}/v1/chat/completions" \
    --max-time "$CURL_MAX_TIME" \
    -H 'Content-Type: application/json' \
    --data-binary @- > "${OUTDIR}/run_prefix_${suffix_id}.json" || {
    log "Run ${suffix_id}: curl FAILED"
    echo '{}' > "${OUTDIR}/run_prefix_${suffix_id}.json"
  }
  t1=$(date +%s.%N)
  local wall_ms
  wall_ms=$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.1f", (b-a)*1000}')

  local prompt_ms predicted_ms eval_tps prompt_n predicted_n cache_n
  prompt_ms=$(jq -r '.timings.prompt_ms // "n/a"' "${OUTDIR}/run_prefix_${suffix_id}.json")
  predicted_ms=$(jq -r '.timings.predicted_ms // "n/a"' "${OUTDIR}/run_prefix_${suffix_id}.json")
  eval_tps=$(jq -r '.timings.predicted_per_second // "n/a"' "${OUTDIR}/run_prefix_${suffix_id}.json")
  prompt_n=$(jq -r '.timings.prompt_n // "n/a"' "${OUTDIR}/run_prefix_${suffix_id}.json")
  predicted_n=$(jq -r '.timings.predicted_n // "n/a"' "${OUTDIR}/run_prefix_${suffix_id}.json")
  cache_n=$(jq -r '.timings.cache_n // "n/a"' "${OUTDIR}/run_prefix_${suffix_id}.json")

  snap_slots "post_${suffix_id}"

  log "Prefix ${idx} (${suffix_id}): prompt_n=${prompt_n} cache_n=${cache_n} prompt_ms=${prompt_ms} eval_tps=${eval_tps} wall_ms=${wall_ms}"

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$idx" "$suffix_id" "$prompt_n" "$cache_n" "$prompt_ms" "$predicted_ms" "$eval_tps" "$wall_ms" \
    >> "${OUTDIR}/prefix_summary.tsv"
}

log "==== measure_phaseU2_prefix start tag=${TAG} pid=${PID} ===="
printf 'idx\tsuffix_id\tprompt_n\tcache_n\tprompt_ms\tpredicted_ms\teval_tps\twall_ms\n' > "${OUTDIR}/prefix_summary.tsv"

ssh "$HOST" "free -w" > "${OUTDIR}/free_pre.txt" 2>&1 || true

# Skip header line of suffix tsv
idx=0
while IFS=$'\t' read -r suffix_id content; do
  [ "$suffix_id" = "suffix_id" ] && continue
  idx=$((idx + 1))
  if [ "$idx" -gt 1 ]; then
    log "cooldown ${COOLDOWN}s before suffix ${idx}"
    sleep "$COOLDOWN"
  fi
  run_one "$idx" "$suffix_id" "$content"
done < "$SUF_TSV"

ssh "$HOST" "free -w" > "${OUTDIR}/free_post.txt" 2>&1 || true

log "==== summary ===="
cat "${OUTDIR}/prefix_summary.tsv" | tee -a "${OUTDIR}/timeline.log"
log "==== measure_phaseU2_prefix end tag=${TAG} ===="
