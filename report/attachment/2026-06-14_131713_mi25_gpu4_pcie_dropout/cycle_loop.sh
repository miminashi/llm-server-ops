#!/usr/bin/env bash
# mi25 コールド電源サイクルを N 回繰り返し、各ブートのトポロジを記録(修正版:
# リモート capture は mi25:~/mi25_cap.sh を呼ぶ。クォート問題を回避)。
set -uo pipefail

PROJ=/home/ubuntu/projects/llm-server-ops
BMC="$PROJ/.claude/skills/gpu-server/scripts/bmc-power.sh"
LOG=/tmp/mi25_cycle_results2.log
BMCLOG=/tmp/mi25_cycle_bmc2.log
N="${1:-10}"

echo "===== mi25 cold-cycle 傾向確認(修正版) 開始: $N 回 =====" | tee -a "$LOG"
date '+%F %T' | tee -a "$LOG"

for i in $(seq 1 "$N"); do
  echo "" | tee -a "$LOG"
  echo "----- cycle #$i / $N -----" | tee -a "$LOG"
  "$BMC" mi25 cycle 30 >>"$BMCLOG" 2>&1
  echo "[#$i] $(date '+%T') power cycle issued, waiting for boot..." | tee -a "$LOG"
  sleep 120
  up=""
  for t in $(seq 1 30); do
    if out=$(ssh -o ConnectTimeout=10 -o BatchMode=yes -o StrictHostKeyChecking=no mi25 'bash ~/mi25_cap.sh' 2>/dev/null); then
      if [ -n "$out" ]; then up="$out"; break; fi
    fi
    sleep 10
  done
  if [ -n "$up" ]; then
    echo "[#$i] $(date '+%T') $up" | tee -a "$LOG"
  else
    echo "[#$i] $(date '+%T') BOOT-TIMEOUT (SSH 復帰せず — 要確認)" | tee -a "$LOG"
  fi
done

echo "" | tee -a "$LOG"
echo "===== 完了 $(date '+%F %T') =====" | tee -a "$LOG"
