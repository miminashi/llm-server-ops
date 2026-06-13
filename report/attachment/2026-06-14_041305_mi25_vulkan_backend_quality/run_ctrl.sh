#!/bin/bash
# Vulkan自己対照: Vulkanで基準logits生成 → Vulkanで同一テキストのKLD計算。
# 同一構成なので Same-top≈100% / Mean KLD≈0 になるはず(メトリクス健全性と決定性の確認)。
set -uo pipefail
MODEL=/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.6-35B-A3B-GGUF/snapshots/a483e9e6cbd595906af30beda3187c2663a1118c/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf
BENCH=/home/llm/bench-quality
DATA=/home/llm/llama.cpp/wikitext-2-raw/wiki.test.raw
BIN=/home/llm/llama.cpp/build-vulkan/bin/llama-perplexity
CH="${1:-30}"
KLD="$BENCH/ppl/vulkan-en-ctrl.kld"
unset GGML_VK_VISIBLE_DEVICES
common=(-m "$MODEL" -f "$DATA" --flash-attn 1 --cache-type-k q8_0 --cache-type-v q8_0 -ngl 99 --chunks "$CH")

echo "=== vulkan base (control) chunks=$CH ==="
"$BIN" "${common[@]}" --kl-divergence-base "$KLD" > "$BENCH/ppl/vulkan-en-ctrlbase.log" 2>&1
echo "base EXIT=$?"
echo "=== vulkan-vs-vulkan KLD chunks=$CH ==="
"$BIN" "${common[@]}" --kl-divergence --kl-divergence-base "$KLD" > "$BENCH/ppl/vulkan-en-ctrlkld.log" 2>&1
echo "kld EXIT=$?"
grep -aiE "Mean PPL|Cor\(|Mean KLD|Maximum KLD|Median|Same top" "$BENCH/ppl/vulkan-en-ctrlkld.log" | tr -cd '[:print:]\n'
rm -f "$KLD"   # 大きいので対照用基準は計測後に削除
