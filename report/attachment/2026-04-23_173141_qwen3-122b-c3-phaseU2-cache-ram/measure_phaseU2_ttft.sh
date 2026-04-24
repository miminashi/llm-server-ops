#!/usr/bin/env bash
# measure_phaseU2_ttft.sh - Phase U-2: 同一 prompt 連投による cache hit TTFT 計測
# usage:
#   measure_phaseU2_ttft.sh <pid> <tag> <prompt_spec> [n_hits]
#     prompt_spec: "文字列" or "@path"
#     n_hits: Run 0 (miss) の後に連投する回数 (default 4)
#
# 既存 measure_phaseT5.sh との差分:
#   - [Request ID <marker>] prefix を付けない (cache hit を意図的に発生させる)
#   - 各 run 前後で /slots を snap して n_prompt_tokens_cache を記録
#   - response JSON から timings.cache_n を抽出 (PR #16391)
#   - STREAM_TTFT=1 で stream=true 版 (SSE 初 chunk 時刻) も取得可能
#
set -euo pipefail

PID="${1:?pid required}"
TAG="${2:?tag required}"
PROMPT_SPEC="${3:?prompt spec required (string or @path)}"
N_HITS="${4:-4}"

HOST="${HOST:-t120h-p100}"
URL="${URL:-http://10.1.4.14:8000}"
OUTDIR="./out_${TAG}"
COOLDOWN="${COOLDOWN:-10}"   # cache hit 目的で短め
EVAL_MAX_TOKENS="${EVAL_MAX_TOKENS:-256}"
CURL_MAX_TIME="${CURL_MAX_TIME:-1800}"
STREAM_TTFT="${STREAM_TTFT:-0}"   # 1 なら stream=true で実測 TTFT も取得

# プロンプト本文をロード (marker なし!)
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

snap_slots() {
  local phase="$1"
  curl -sS "${URL}/slots" > "${OUTDIR}/slots_${phase}.json" 2>&1 || echo '{}' > "${OUTDIR}/slots_${phase}.json"
}

build_payload_nomark() {
  # marker なしで payload 構築
  local stream="$1"
  local tmp
  tmp=$(mktemp)
  printf '%s' "$EVAL_PROMPT" > "$tmp"
  jq -n \
    --arg model "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" \
    --rawfile content "$tmp" \
    --argjson max_tokens "$EVAL_MAX_TOKENS" \
    --argjson stream "$stream" \
    '{model: $model, messages: [{role: "user", content: $content}], max_tokens: $max_tokens, stream: $stream, temperature: 0.6, top_p: 0.95}'
  rm -f "$tmp"
}

run_one() {
  local run="$1"  # 0 = miss baseline, 1..N_HITS = hit
  local kind
  if [ "$run" -eq 0 ]; then
    kind="miss"
  else
    kind="hit"
  fi

  snap_slots "pre_run${run}"

  local t0 t1
  t0=$(date +%s.%N)

  # stream=false 本計測 (timings 取得用)
  build_payload_nomark "false" | curl -sS -X POST "${URL}/v1/chat/completions" \
    --max-time "$CURL_MAX_TIME" \
    -H 'Content-Type: application/json' \
    --data-binary @- > "${OUTDIR}/run_ttft_${run}.json" || {
    log "Run ${run} (${kind}): curl FAILED"
    echo '{}' > "${OUTDIR}/run_ttft_${run}.json"
  }

  t1=$(date +%s.%N)
  local wall_ms
  wall_ms=$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.1f", (b-a)*1000}')

  local prompt_ms predicted_ms eval_tps prompt_n predicted_n cache_n
  prompt_ms=$(jq -r '.timings.prompt_ms // "n/a"' "${OUTDIR}/run_ttft_${run}.json")
  predicted_ms=$(jq -r '.timings.predicted_ms // "n/a"' "${OUTDIR}/run_ttft_${run}.json")
  eval_tps=$(jq -r '.timings.predicted_per_second // "n/a"' "${OUTDIR}/run_ttft_${run}.json")
  prompt_n=$(jq -r '.timings.prompt_n // "n/a"' "${OUTDIR}/run_ttft_${run}.json")
  predicted_n=$(jq -r '.timings.predicted_n // "n/a"' "${OUTDIR}/run_ttft_${run}.json")
  cache_n=$(jq -r '.timings.cache_n // "n/a"' "${OUTDIR}/run_ttft_${run}.json")

  snap_slots "post_run${run}"

  log "Run ${run} (${kind}): prompt_ms=${prompt_ms} predicted_ms=${predicted_ms} eval_tps=${eval_tps} prompt_n=${prompt_n} predicted_n=${predicted_n} cache_n=${cache_n} wall_ms=${wall_ms}"

  # TSV 1 行追記
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$run" "$kind" "$prompt_n" "$cache_n" "$prompt_ms" "$predicted_ms" "$eval_tps" "$predicted_n" "$wall_ms" \
    >> "${OUTDIR}/ttft_summary.tsv"

  # Optional: stream=true 実測 TTFT
  if [ "$STREAM_TTFT" -eq 1 ]; then
    local t_start t_ftok
    t_start=$(date +%s.%N)
    build_payload_nomark "true" | curl -sS -N --max-time "$CURL_MAX_TIME" \
      -H 'Content-Type: application/json' \
      --data-binary @- "${URL}/v1/chat/completions" 2>/dev/null | \
      awk -v tstart="$t_start" '/^data: /{ t=systime(); cmd="date +%s.%N"; cmd | getline now; close(cmd); printf "%s\n", now; exit }' \
      > "${OUTDIR}/stream_first_tok_${run}.txt" || true
    t_ftok=$(cat "${OUTDIR}/stream_first_tok_${run}.txt" 2>/dev/null || echo "")
    if [ -n "$t_ftok" ]; then
      local stream_ttft_ms
      stream_ttft_ms=$(awk -v a="$t_start" -v b="$t_ftok" 'BEGIN{printf "%.1f", (b-a)*1000}')
      log "Run ${run} (${kind}) STREAM: ttft_ms=${stream_ttft_ms}"
      printf '%s\t%s\t%s\n' "$run" "$kind" "$stream_ttft_ms" >> "${OUTDIR}/stream_ttft_summary.tsv"
    fi
  fi
}

log "==== measure_phaseU2_ttft start tag=${TAG} pid=${PID} n_hits=${N_HITS} ===="
printf 'run\tkind\tprompt_n\tcache_n\tprompt_ms\tpredicted_ms\teval_tps\tpredicted_n\twall_ms\n' > "${OUTDIR}/ttft_summary.tsv"
if [ "$STREAM_TTFT" -eq 1 ]; then
  printf 'run\tkind\tstream_ttft_ms\n' > "${OUTDIR}/stream_ttft_summary.tsv"
fi

# 事前環境記録
ssh "$HOST" "free -w" > "${OUTDIR}/free_pre.txt" 2>&1 || true
ssh "$HOST" "nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv" > "${OUTDIR}/gpu_pre.csv" 2>&1 || true
ssh "$HOST" "cat /proc/${PID}/cmdline | tr '\0' ' '; echo" > "${OUTDIR}/cmdline.txt" 2>&1 || true

# Run 0 (cache miss baseline)
run_one 0

# Run 1..N_HITS (cache hit expected)
for i in $(seq 1 "$N_HITS"); do
  log "cooldown ${COOLDOWN}s before hit run ${i}"
  sleep "$COOLDOWN"
  run_one "$i"
done

ssh "$HOST" "free -w" > "${OUTDIR}/free_post.txt" 2>&1 || true

log "==== summary (run / kind / prompt_n / cache_n / prompt_ms / eval_tps) ===="
cat "${OUTDIR}/ttft_summary.tsv" | tee -a "${OUTDIR}/timeline.log"
log "==== measure_phaseU2_ttft end tag=${TAG} ===="
