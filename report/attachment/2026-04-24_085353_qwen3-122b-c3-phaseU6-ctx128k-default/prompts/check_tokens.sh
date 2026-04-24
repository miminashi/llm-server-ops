#!/usr/bin/env bash
# check_tokens.sh - llama-server /tokenize で各プロンプトのトークン数を確認
set -euo pipefail
URL="${URL:-http://10.1.4.14:8000}"
DIR="$(cd "$(dirname "$0")" && pwd)"
for f in "$DIR"/prompt_*.txt; do
  name=$(basename "$f" .txt)
  chars=$(wc -c < "$f")
  n_tok=$(jq -n --rawfile c "$f" '{content: $c}' \
    | curl -sS -X POST "${URL}/tokenize" \
        -H 'Content-Type: application/json' \
        --data-binary @- \
        | jq '.tokens | length')
  printf "%-18s chars=%-7s tokens=%s\n" "$name" "$chars" "$n_tok"
done
