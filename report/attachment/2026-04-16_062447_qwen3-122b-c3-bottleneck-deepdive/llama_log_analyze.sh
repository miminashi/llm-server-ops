#!/usr/bin/env bash
# llama-server のテンソル配置ログを解析し、output / lm_head が載った GPU を特定
set -euo pipefail

ATTACH="$(cd "$(dirname "$0")" && pwd)"
HOST="t120h-p100"
OUT="$ATTACH/output_placement.txt"

{
  echo "=== llama-server log: output / lm_head / embedding の GPU 配置 ==="
  ssh "$HOST" "grep -E 'output|lm_head|token_embd|out_proj' /tmp/llama-server.log | head -n 200" 2>&1 || true
  echo ""
  echo "=== load_tensors 抜粋 ==="
  ssh "$HOST" "grep -E 'load_tensors|CUDA_Host|CUDA[0-3]' /tmp/llama-server.log | head -n 80" 2>&1 || true
  echo ""
  echo "=== buffer type summary (CUDA0/1/2/3 の載せられた層数カウント) ==="
  ssh "$HOST" "grep -oE 'CUDA[0-3]' /tmp/llama-server.log | sort | uniq -c" 2>&1 || true
} > "$OUT"

echo "written: $OUT"
wc -l "$OUT"
