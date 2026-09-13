#!/usr/bin/env bash
# GPU サーバ上で実行する。ask.sh で投入 → .done を待つ → check.py で判定する。
# usage: measure.sh <payload.json> <out.json> <timeout_sec> [code...]
set -u
P="$1"; OUT="$2"; TMO="$3"; shift 3
bash /tmp/ask.sh "$P" "$OUT" >/dev/null
i=0
while [ ! -f "$OUT.done" ]; do
  i=$((i+5)); [ "$i" -ge "$TMO" ] && { echo "TIMEOUT after ${TMO}s"; exit 1; }
  sleep 5
done
echo "curl_exit=$(cat "$OUT.done")"
python3 /tmp/check.py "$OUT" "$@"
