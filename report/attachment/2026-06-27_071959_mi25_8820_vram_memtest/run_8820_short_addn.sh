#!/bin/bash
# 8820 ショート standard test を 2 本追加実行 (各 6 分、計 12 分)。
# 既存 pass00/01_misrouted で 2 本確保済み、pass02_misrouted は不完全。
# 本スクリプトで pass03/pass04 を追加し、合計 short ×4 本相当を確保する。
set -u
SCR="$1"
echo "=== SHORT_ADDN START $(date -Iseconds) ===" > "$SCR/short_addn_runner.log"
bash "$SCR/run_memtest.sh" 1 360 "$SCR/mt_8820_pass03.log" >> "$SCR/short_addn_runner.log" 2>&1
bash "$SCR/run_memtest.sh" 1 360 "$SCR/mt_8820_pass04.log" >> "$SCR/short_addn_runner.log" 2>&1
echo "=== SHORT_ADDN END $(date -Iseconds) ===" >> "$SCR/short_addn_runner.log"
