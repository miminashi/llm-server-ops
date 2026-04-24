#!/usr/bin/env bash
# batch_U4.sh - Phase U-4 旧 unsloth vs 新 fused 比較バッチ
# モード: BATCH_MODE = "ab" (標準; unsloth→fused を 1 周; デフォルト) or "abab" (2 周)
# 各 model × 3 prompt で warmup 2 + eval 5 (合計 7 run / prompt)
set -euo pipefail

HOST="${HOST:-t120h-p100}"
URL="${URL:-http://10.1.4.14:8000}"
BATCH_MODE="${BATCH_MODE:-ab}"
PROMPTS_DIR="${PROMPTS_DIR:?PROMPTS_DIR required (path with prompt_1k.txt etc.)}"
UNSLOTH_PATH="${UNSLOTH_PATH:-/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf}"
FUSED_PATH="${FUSED_PATH:?FUSED_PATH required (remote path of fused Q4_K_M)}"
UNSLOTH_ALIAS="${UNSLOTH_ALIAS:-unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M}"
FUSED_ALIAS="${FUSED_ALIAS:-local/Qwen3.5-122B-A10B-fused:Q4_K_M}"

WARMUP_RUNS="${WARMUP_RUNS:-2}"
EVAL_RUNS="${EVAL_RUNS:-5}"
COOLDOWN="${COOLDOWN:-60}"

export HOST URL

PROMPTS=("1k:prompt_1k.txt" "code:prompt_code.txt" "repetitive:prompt_repetitive.txt")

stop_server() {
  echo "[batch_U4] stopping llama-server on $HOST"
  ssh "$HOST" "pkill -SIGTERM -f 'llama-server -m' || true; sleep 3; pkill -SIGKILL -f 'llama-server -m' || true; sleep 2" || true
  for i in 1 2 3 4 5; do
    if ! curl -sf "${URL}/health" > /dev/null 2>&1; then
      echo "[batch_U4] server stopped"
      return 0
    fi
    sleep 3
  done
  echo "[batch_U4] WARN server still responding to /health"
}

start_server() {
  local path="$1" alias="$2" tag_suffix="$3"
  echo "[batch_U4] starting llama-server with MODEL=$path ALIAS=$alias"
  MODEL_PATH="$path" MODEL_ALIAS="$alias" TAG_SUFFIX="$tag_suffix" bash "$(dirname "$0")/start_phaseU4.sh"
  echo "[batch_U4] start returned, server should be healthy"
}

measure_one() {
  local model="$1" alias="$2" prompt_key="$3" prompt_file="$4" round="$5"
  local pid
  pid=$(ssh "$HOST" "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
  echo "[batch_U4] measure model=${model} prompt=${prompt_key} round=${round} pid=${pid}"
  # warmup
  local warmup_tag="U4_${model}_${prompt_key}_r${round}_warmup"
  MODEL_ALIAS="$alias" RUNS="$WARMUP_RUNS" COOLDOWN="$COOLDOWN" \
    bash "$(dirname "$0")/measure_phaseU4.sh" "$pid" "$warmup_tag" "@${PROMPTS_DIR}/${prompt_file}"
  # eval
  local eval_tag="U4_${model}_${prompt_key}_r${round}"
  MODEL_ALIAS="$alias" RUNS="$EVAL_RUNS" COOLDOWN="$COOLDOWN" \
    bash "$(dirname "$0")/measure_phaseU4.sh" "$pid" "$eval_tag" "@${PROMPTS_DIR}/${prompt_file}"
}

run_round() {
  local round="$1"
  echo "[batch_U4] === Round ${round} ==="

  # unsloth
  start_server "$UNSLOTH_PATH" "$UNSLOTH_ALIAS" "_unsloth_r${round}"
  for p in "${PROMPTS[@]}"; do
    IFS=: read -r key file <<< "$p"
    measure_one unsloth "$UNSLOTH_ALIAS" "$key" "$file" "$round"
  done
  stop_server

  # fused
  start_server "$FUSED_PATH" "$FUSED_ALIAS" "_fused_r${round}"
  for p in "${PROMPTS[@]}"; do
    IFS=: read -r key file <<< "$p"
    measure_one fused "$FUSED_ALIAS" "$key" "$file" "$round"
  done
  stop_server
}

case "$BATCH_MODE" in
  ab)   run_round 1 ;;
  abab) run_round 1; run_round 2 ;;
  *) echo "Unknown BATCH_MODE: $BATCH_MODE" >&2; exit 1 ;;
esac

echo "[batch_U4] all rounds done"
