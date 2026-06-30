#!/bin/bash
# mi25 テレメトリ収集（制御ホスト側で実行、全ログをローカルに保存）。
# - rocm-smi 10s毎（温度/電力/VRAM/クロック/利用率, GPU毎）
# - GPU枚数（unique GPU index）10s毎
# - dmesg 常時ストリーム（sudo dmesg -w）
# - llama-server ログ tail -F
# freeze 時は ssh がタイムアウトして gap が記録される。
#
# Usage: telemetry.sh <scratch_dir> <server>
# 停止: このスクリプトの PID を kill（子の ssh も pkill する）。

set -u
SCRATCH="$1"
SERVER="${2:-mi25}"

ROCM_LOG="$SCRATCH/telemetry_rocmsmi.log"
CNT_LOG="$SCRATCH/telemetry_gpucount.log"
DMESG_LOG="$SCRATCH/kern_dmesg.log"
LLAMA_LOG="$SCRATCH/llama_server.log"
PIDFILE="$SCRATCH/telemetry.pids"

: > "$PIDFILE"

# 長寿命ストリーム: dmesg
( ssh -o ConnectTimeout=5 -o ServerAliveInterval=10 "$SERVER" "sudo dmesg -w" ) >> "$DMESG_LOG" 2>&1 &
echo "$!" >> "$PIDFILE"

# 長寿命ストリーム: llama-server ログ
( ssh -o ConnectTimeout=5 -o ServerAliveInterval=10 "$SERVER" "tail -F /tmp/llama-server.log" ) >> "$LLAMA_LOG" 2>&1 &
echo "$!" >> "$PIDFILE"

# 10s毎サンプラ（rocm-smi + GPU枚数）
(
  while true; do
    EPOCH=$(date +%s)
    OUT=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "$SERVER" \
      "rocm-smi --showtemp --showpower --showuse --showmemuse --showclocks 2>/dev/null" 2>&1)
    RC=$?
    echo "===== epoch=$EPOCH rc=$RC =====" >> "$ROCM_LOG"
    echo "$OUT" >> "$ROCM_LOG"
    CNT=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "$SERVER" \
      "rocm-smi --showmaxpower 2>/dev/null | grep -oE 'GPU\[[0-9]+\]' | sort -u | wc -l" 2>/dev/null)
    echo "epoch=$EPOCH gpu_count=${CNT:-ERR} ssh_rc=$RC" >> "$CNT_LOG"
    sleep 10
  done
) &
echo "$!" >> "$PIDFILE"

echo "telemetry started. pids: $(tr '\n' ' ' < "$PIDFILE")"
echo "logs: $ROCM_LOG / $CNT_LOG / $DMESG_LOG / $LLAMA_LOG"
