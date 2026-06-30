#!/bin/bash
# 8820 (menu 1, Bus 0x87) を 7200s (120分) standard + extended 連続実行。
# wall-time で SIGINT 送出して終了サマリを得る。
set -u
SCR="$1"
LOG="$SCR/mt_8820_long.log"
echo "=== LONG START $(date -Iseconds) menu=1 max=7200s ===" > "$LOG"
ssh -o ConnectTimeout=10 -o ServerAliveInterval=30 mi25 \
  "cd ~/memtest_vulkan && VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.x86_64.json \
   timeout --signal=INT --kill-after=15 7200 ./memtest_vulkan 1 2>&1" \
  >> "$LOG" 2>&1
RC=$?
ssh -o ConnectTimeout=10 mi25 'pkill -INT memtest_vulkan 2>/dev/null; sleep 1; pkill -9 memtest_vulkan 2>/dev/null; true'
echo "=== LONG END $(date -Iseconds) rc=$RC ===" >> "$LOG"
echo "LONG_DONE"
