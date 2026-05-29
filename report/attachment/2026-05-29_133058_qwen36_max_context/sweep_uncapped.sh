#!/bin/bash
# キャップ解除(--override-kv)版 VRAM スイープ。真の高 ctx での VRAM とスロット n_ctx を記録。
set -uo pipefail
cd /home/ubuntu/projects/llm-server-ops
STOP=.claude/skills/llama-server/scripts/stop.sh
START=.claude/skills/llama-server/scripts/start.sh
MODEL="unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL"
UB="${1:-2048}"
OUT=/tmp/qwen36_ctx/sweep_uncapped_ub${UB}.csv
echo "ctx,factor,ub,slot_nctx,loaded,vram_gb,gpu0_mib" > "$OUT"

# 262144 まで factor=1(yarnなし)、超過分は factor=ctx/262144。override-kv で cap を 2,097,152 に引上げ。
PAIRS="262144:1.0 393216:1.5 524288:2.0 786432:3.0 1048576:4.0"
OVK="--override-kv qwen35moe.context_length=int:2097152"

for P in $PAIRS; do
  C="${P%%:*}"; F="${P##*:}"
  echo "===== ctx=$C factor=$F ub=$UB ====="
  "$STOP" t120h-p100 >/dev/null 2>&1
  sleep 2
  if [ "$F" = "1.0" ]; then
    export EXTRA_LLAMA_OPTS="-b 2048 -ub $UB $OVK"
  else
    export EXTRA_LLAMA_OPTS="-b 2048 -ub $UB $OVK --rope-scaling yarn --rope-scale $F --yarn-orig-ctx 262144"
  fi
  "$START" t120h-p100 "$MODEL" "$C" >/dev/null 2>&1
  LOADED="no"
  for i in $(seq 1 60); do
    curl -sf -m 5 http://10.1.4.14:8000/health >/dev/null 2>&1 && { LOADED="yes"; break; }
    if ssh t120h-p100 "tail -3 /tmp/llama-server.log | grep -qiE 'out of memory|failed to allocate compute'"; then
      sleep 4; curl -sf -m 5 http://10.1.4.14:8000/health >/dev/null 2>&1 && { LOADED="yes"; break; }
      LOADED="OOM"; break
    fi
    sleep 3
  done
  SLOT=$(ssh t120h-p100 "grep -oE 'new slot, n_ctx = [0-9]+' /tmp/llama-server.log | tail -1 | grep -oE '[0-9]+'")
  if [ "$LOADED" = "yes" ]; then
    read VR G0 < <(ssh t120h-p100 "nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits | awk 'NR==1{g0=\$2} {s+=\$2} END {printf \"%.1f %d\", s/1024, g0}'")
    echo "$C,$F,$UB,${SLOT:-?},yes,$VR,$G0" >> "$OUT"
    echo "  -> loaded slot_nctx=${SLOT} vram=${VR}GiB gpu0=${G0}MiB"
  else
    echo "$C,$F,$UB,${SLOT:-?},$LOADED,," >> "$OUT"
    echo "  -> $LOADED (slot=${SLOT})"
  fi
done
echo "===== uncapped sweep (ub=$UB) done ====="
cat "$OUT"
