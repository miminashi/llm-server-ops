#!/bin/bash
# 健全 3 枚 (29525=SLOT2/Bus04 menu4, 33301=SLOT4/Bus07 menu3, 54068=SLOT8/Bus84 menu2)
# を順次 standard 5-minute test。各 360s で SIGINT (Standard 完走 + extended ~30s)。
set -u
SCR="$1"
echo "=== HEALTHY3 START $(date -Iseconds) ===" > "$SCR/healthy3_runner.log"
bash "$SCR/run_memtest.sh" 4 360 "$SCR/mt_29525_SLOT2_pass01.log" >> "$SCR/healthy3_runner.log" 2>&1
bash "$SCR/run_memtest.sh" 3 360 "$SCR/mt_33301_SLOT4_pass01.log" >> "$SCR/healthy3_runner.log" 2>&1
bash "$SCR/run_memtest.sh" 2 360 "$SCR/mt_54068_SLOT8_pass01.log" >> "$SCR/healthy3_runner.log" 2>&1
echo "=== HEALTHY3 END $(date -Iseconds) ===" >> "$SCR/healthy3_runner.log"
