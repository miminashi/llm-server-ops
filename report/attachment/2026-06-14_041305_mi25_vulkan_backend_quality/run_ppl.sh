#!/bin/bash
# 使い方: run_ppl.sh <backend: rocm|vulkan> <lang: en|ja> <mode: base|kld|ppl> <chunks> [extra args...]
set -uo pipefail
MODEL=/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.6-35B-A3B-GGUF/snapshots/a483e9e6cbd595906af30beda3187c2663a1118c/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf
BENCH=/home/llm/bench-quality
backend="$1"; lang="$2"; mode="$3"; chunks="$4"; shift 4 || true
extra=("$@")

if [ "$lang" = "en" ]; then DATA=/home/llm/llama.cpp/wikitext-2-raw/wiki.test.raw; else DATA="$BENCH/ppl/ja-wiki.raw"; fi
if [ "$backend" = "rocm" ]; then BIN=/home/llm/llama.cpp/build/bin/llama-perplexity; unset GGML_VK_VISIBLE_DEVICES; else BIN=/home/llm/llama.cpp/build-vulkan/bin/llama-perplexity; unset GGML_VK_VISIBLE_DEVICES; fi

KLD="$BENCH/ppl/rocm-${lang}.kld"
LOG="$BENCH/ppl/${backend}-${lang}-${mode}.log"

common=(-m "$MODEL" -f "$DATA" --flash-attn 1 --cache-type-k q8_0 --cache-type-v q8_0 -ngl 99 --chunks "$chunks")

case "$mode" in
  base) args=("${common[@]}" --kl-divergence-base "$KLD") ;;
  kld)  args=("${common[@]}" --kl-divergence --kl-divergence-base "$KLD") ;;
  ppl)  args=("${common[@]}") ;;
  *) echo "bad mode"; exit 2 ;;
esac

echo "=== $backend $lang $mode chunks=$chunks ==="
echo "BIN=$BIN"
"$BIN" "${args[@]}" "${extra[@]}" > "$LOG" 2>&1
rc=$?
echo "EXIT=$rc"
echo "--- buffer/device lines ---"
grep -aE "Found .* devices|model buffer size|failed to load|ggml_cuda_init|found .* ROCm" "$LOG" | tr -cd '[:print:]\n'
echo "--- result lines ---"
grep -aiE "Final estimate|perplexity:.*chunk|Mean PPL|Mean KLD|Maximum KLD|Same top|PPL\(|estimate:" "$LOG" | tr -cd '[:print:]\n' | tail -15
echo "--- kld file ---"
ls -la "$KLD" 2>/dev/null | tr -cd '[:print:]\n'
echo "LOGFILE=$LOG"
