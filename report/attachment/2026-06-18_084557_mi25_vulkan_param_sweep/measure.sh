#!/usr/bin/env bash
# measure.sh - mi25+Vulkan 1条件分 warmup + eval 計測 (measure_phaseU6.sh 派生)
# 改変点: HOST=mi25, rocm-smi で VRAM 監視, MODEL を env 化, 不要な PID 必須を撤去
# usage:
#   CELL=<id> OUTDIR=<path> PROMPT_TAG=<1k|32k> PROMPT_FILE=<path> COND_ID=<id> UB=<n> \
#     WARMUP_RUNS=<N> EVAL_RUNS=<N> EVAL_MAX_TOKENS=<N> COOLDOWN=<N> CSV=<path> \
#     bash measure.sh
set -euo pipefail

CELL="${CELL:?CELL required}"
OUTDIR="${OUTDIR:?OUTDIR required}"
PROMPT_TAG="${PROMPT_TAG:?PROMPT_TAG required}"
PROMPT_FILE="${PROMPT_FILE:?PROMPT_FILE required}"
COND_ID="${COND_ID:?COND_ID required}"
UB="${UB:?UB required}"
WARMUP_RUNS="${WARMUP_RUNS:-2}"
EVAL_RUNS="${EVAL_RUNS:-5}"
EVAL_MAX_TOKENS="${EVAL_MAX_TOKENS:-512}"
COOLDOWN="${COOLDOWN:-15}"
CSV="${CSV:?CSV required}"

HOST="${HOST:-mi25}"
URL="${URL:-http://10.1.4.13:8000}"
MODEL="${MODEL:-unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL}"
CURL_MAX_TIME="${CURL_MAX_TIME:-1800}"

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
    --arg model "$MODEL" \
    --rawfile content "$tmp" \
    --argjson max_tokens "$EVAL_MAX_TOKENS" \
    '{model: $model, messages: [{role: "user", content: $content}], max_tokens: $max_tokens, stream: false, temperature: 0.6, top_p: 0.95}'
  rm -f "$tmp"
}

# rocm-smi で各GPUの Used(MiB) を取得して "idx:usedMiB" を1行ずつ出す
gpu_vram() {
  ssh -o ConnectTimeout=5 -o BatchMode=yes "$HOST" \
    "rocm-smi --showmeminfo vram --csv 2>/dev/null" \
    | awk -F, 'NR>1 && $1!="" {gsub(/card/,"",$1); used=$3/1048576; printf "%s:%.0f\n",$1,used}'
}

run_one() {
  local role="$1" idx="$2"
  local run_id="${role}${idx}"
  # 固定マーカー: プロンプト prefix を全 run で共通化し、llama-server の prompt cache を効かせる。
  # サーバ再起動直後の warmup1 はキャッシュ空=コールドで実 prompt_tps を測定、
  # 以降の run はキャッシュ命中で prompt 再処理を回避し 32k 深コンテキストの eval_tps を安価に取得。
  local run_marker="${CELL}_fixed"
  local out="${OUTDIR}/${run_id}.json"

  log "${CELL} ${run_id}: start (prompt_tag=${PROMPT_TAG})"
  gpu_vram > "${OUTDIR}/${run_id}_gpu_pre.txt" 2>&1 || true

  local t_start=$(date +%s)
  build_payload "$run_marker" | curl -sS -X POST "${URL}/v1/chat/completions" \
    --max-time "$CURL_MAX_TIME" -H 'Content-Type: application/json' \
    --data-binary @- > "$out" || { log "${CELL} ${run_id}: curl FAILED"; echo '{"error":"curl_failed"}' > "$out"; }
  local t_end=$(date +%s)
  local wallclock=$((t_end - t_start))

  gpu_vram > "${OUTDIR}/${run_id}_gpu_post.txt" 2>&1 || true

  local eval_tps prompt_tps prompt_n predicted_n prompt_ms predicted_ms err
  eval_tps=$(jq -r '.timings.predicted_per_second // ""' "$out" 2>/dev/null)
  prompt_tps=$(jq -r '.timings.prompt_per_second // ""' "$out" 2>/dev/null)
  prompt_n=$(jq -r '.timings.prompt_n // ""' "$out" 2>/dev/null)
  predicted_n=$(jq -r '.timings.predicted_n // ""' "$out" 2>/dev/null)
  prompt_ms=$(jq -r '.timings.prompt_ms // ""' "$out" 2>/dev/null)
  predicted_ms=$(jq -r '.timings.predicted_ms // ""' "$out" 2>/dev/null)
  err=$(jq -r '.error // ""' "$out" 2>/dev/null)

  # 最大 Used VRAM (全GPU・pre/post の最大)
  local max_gpu_used
  max_gpu_used=$(awk -F: '{print $2}' "${OUTDIR}/${run_id}_gpu_pre.txt" "${OUTDIR}/${run_id}_gpu_post.txt" 2>/dev/null \
    | sort -n | tail -1)
  [ -z "$max_gpu_used" ] && max_gpu_used=""

  log "${CELL} ${run_id}: eval=${eval_tps} prompt=${prompt_tps} prompt_n=${prompt_n} pred_n=${predicted_n} wall=${wallclock}s maxVRAM=${max_gpu_used}MiB"

  printf "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n" \
    "$CELL" "$COND_ID" "$UB" "$PROMPT_TAG" "$role" "$idx" \
    "${eval_tps}" "${prompt_tps}" "${prompt_n}" "${predicted_n}" \
    "${prompt_ms}" "${predicted_ms}" "${wallclock}" "${max_gpu_used}" "${err}" \
    >> "$CSV"
}

log "==== measure cell=${CELL} ===="
for i in $(seq 1 12); do
  curl -sf "${URL}/health" > /dev/null 2>&1 && { log "/health OK"; break; }
  sleep 5
done

for i in $(seq 1 "$WARMUP_RUNS"); do
  [ "$i" -gt 1 ] && sleep "$COOLDOWN"
  run_one warmup "$i"
done
for i in $(seq 1 "$EVAL_RUNS"); do
  sleep "$COOLDOWN"
  run_one eval "$i"
done
log "==== measure cell=${CELL} end ===="
