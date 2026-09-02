#!/usr/bin/env bash
# run_cfg.sh で再起動し、起動できたら 11k needle を投げて pp を測る。
# usage: sweep_meas.sh <model.gguf> <ctx> <tag-prefix> <ub...>
set -u
M="$1"; CTX="$2"; PFX="$3"; shift 3
for UB in "$@"; do
  TAG="${PFX}_ub${UB}"
  OUT=$(/tmp/run_cfg.sh "$TAG" "$M" "$CTX" "$UB" 2>&1)
  echo "$OUT" | grep -E '^RESULT|failed to allocate|graph_reserve'
  if echo "$OUT" | grep -q "RESULT $TAG OK"; then
    /tmp/ask.sh /tmp/needle_11k.json "/tmp/r_${TAG}.json" > /dev/null
    for i in $(seq 1 120); do [ -f "/tmp/r_${TAG}.json.done" ] && break; sleep 10; done
    python3 /tmp/check.py "/tmp/r_${TAG}.json" 山茶花6104 木蓮3357 2>&1 | grep -E '山茶花|木蓮|^pp:|COLLAPSE'
  fi
done
echo SWEEP_DONE
