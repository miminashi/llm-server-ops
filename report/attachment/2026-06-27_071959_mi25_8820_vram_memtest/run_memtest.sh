#!/bin/bash
# memtest_vulkan を 1 回実行（指定メニュー番号、wall-time 上限）。
# 標準 5 分テスト後 extended endless に入るため、wall-time 経過で SIGINT 送出。
#
# Usage: run_memtest.sh <menu_num> <max_seconds> <log_path>
# 例: run_memtest.sh 1 360 mt_8820_pass01.log
#
# 完了後 ssh 経由で memtest_vulkan プロセスを念のため kill する。
set -u
MENU="$1"
MAX="$2"
LOG="$3"

START=$(date -Iseconds)
echo "=== START $START menu=$MENU max=${MAX}s log=$LOG ===" > "$LOG"

# 第1引数でメニュー番号を渡すと非対話モード即時開始 (main.rs の args_os_iter 解析を確認)。
# timeout で SIGINT、その後 SIGKILL までさらに 10s 猶予。
ssh -o ConnectTimeout=10 mi25 "cd ~/memtest_vulkan && \
  VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.x86_64.json \
  timeout --signal=INT --kill-after=10 ${MAX} ./memtest_vulkan ${MENU} 2>&1" \
  >> "$LOG" 2>&1
RC=$?

# 念のため残存プロセス kill
ssh -o ConnectTimeout=10 mi25 'pkill -INT memtest_vulkan 2>/dev/null; sleep 1; pkill -9 memtest_vulkan 2>/dev/null; true'

END=$(date -Iseconds)
echo "=== END $END rc=$RC ===" >> "$LOG"
echo "run_memtest.sh: menu=$MENU rc=$RC log=$LOG"
exit 0
