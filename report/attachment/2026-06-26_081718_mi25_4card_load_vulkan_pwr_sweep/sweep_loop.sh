#!/bin/bash
# mi25 4枚 Vulkan 負荷 — 電力スイープ 190→140W 5W刻み 11点
# usage: nohup bash sweep_loop.sh > nohup.out 2>&1 &
set -u
SCR=/tmp/claude-1000/-home-ubuntu-projects-llm-server-ops/443a4e1e-b515-4c40-9d86-8fa004fbbe82/scratchpad
PROJ=/home/ubuntu/projects/llm-server-ops
LOG="$SCR/sweep_master.log"

# 既存ロックの有無を表示するだけ (取得は既に外部で実施済を前提とする)
( cd "$PROJ" && .claude/skills/gpu-server/scripts/lock-status.sh mi25 ) | tee -a "$LOG"

echo "[$(date -Iseconds)] ===== SWEEP START =====" | tee -a "$LOG"

for W in 190 185 180 175 170 165 160 155 150 145 140; do
  echo "[$(date -Iseconds)] === POWER POINT ${W}W START ===" | tee -a "$LOG"
  bash "$SCR/sweep_one_point.sh" "$W" 2>&1 | tee -a "$LOG"
  RC=${PIPESTATUS[0]}
  echo "[$(date -Iseconds)] === POWER POINT ${W}W END rc=$RC ===" | tee -a "$LOG"
  if [ "$RC" -ne 0 ]; then
    echo "[$(date -Iseconds)] !!! sweep_one_point ${W}W rc=$RC → スイープ中断 !!!" | tee -a "$LOG"
    break
  fi
done

echo "[$(date -Iseconds)] ===== CLEANUP: stop llama-server, restore power_cap=160W =====" | tee -a "$LOG"
ssh -o ConnectTimeout=10 mi25 'pkill -f bin/llama-server || true' 2>&1 | tee -a "$LOG"
ssh -o ConnectTimeout=10 mi25 'bash -s' < "$SCR/set_power_cap.sh" 160 2>&1 | tee -a "$LOG"

echo "[$(date -Iseconds)] ===== SWEEP DONE =====" | tee -a "$LOG"
