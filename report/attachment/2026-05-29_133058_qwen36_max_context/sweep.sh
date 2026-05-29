#!/bin/bash
# 起動のみ VRAM 天井スイープ (ub=512 固定)。各 ctx で起動を試み、loaded/VRAM を記録。
# 262144 までは YaRN なし、超える場合は factor=ctx/262144 で YaRN 適用。
set -uo pipefail
cd /home/ubuntu/projects/llm-server-ops
STOP=.claude/skills/llama-server/scripts/stop.sh
START=.claude/skills/llama-server/scripts/start.sh
MODEL="unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL"
OUT=/tmp/qwen36_ctx/sweep_results.csv
echo "ctx,factor,ub,loaded,vram_gb,gpu0_mib" > "$OUT"

# ctx:factor の組
PAIRS="393216:1.5 524288:2.0 786432:3.0 1048576:4.0"

for P in $PAIRS; do
  C="${P%%:*}"; F="${P##*:}"
  echo "===== ctx=$C factor=$F ub=512 ====="
  "$STOP" t120h-p100 >/dev/null 2>&1
  sleep 2
  export EXTRA_LLAMA_OPTS="-b 2048 -ub 512 --rope-scaling yarn --rope-scale $F --yarn-orig-ctx 262144"
  "$START" t120h-p100 "$MODEL" "$C" >/dev/null 2>&1
  LOADED="no";
  for i in $(seq 1 50); do
    if curl -sf -m 5 http://10.1.4.14:8000/health >/dev/null 2>&1; then LOADED="yes"; break; fi
    if ssh t120h-p100 "tail -3 /tmp/llama-server.log | grep -qiE 'out of memory|failed to allocate compute'"; then
      # OOM の可能性。さらに数秒待って health 出なければ確定
      sleep 4
      curl -sf -m 5 http://10.1.4.14:8000/health >/dev/null 2>&1 && { LOADED="yes"; break; }
      LOADED="OOM"; break
    fi
    sleep 3
  done
  if [ "$LOADED" = "yes" ]; then
    read VR G0 < <(ssh t120h-p100 "nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits | awk 'NR==1{g0=\$2} {s+=\$2} END {printf \"%.1f %d\", s/1024, g0}'")
    echo "$C,$F,512,yes,$VR,$G0" >> "$OUT"
    echo "  -> loaded, vram=${VR}GiB gpu0=${G0}MiB"
  else
    echo "$C,$F,512,$LOADED,," >> "$OUT"
    echo "  -> $LOADED"
    ssh t120h-p100 "grep -iE 'out of memory|n_ctx' /tmp/llama-server.log | tail -2"
  fi
done
echo "===== sweep done ====="
cat "$OUT"
