#!/bin/bash
# mi25 per-card PCIe + AER サンプラ（4ルートポート / 10秒毎）。
# 原 ROCm 版負荷検証(report/2026-06-25_094641) で追加された per-card サンプラ相当。
# 4 ルートポート(00:02.0/00:03.0/80:02.0/80:03.0)について
#  LnkSta Width / Speed / PresDet / AER cor/fatal/nonfatal TOTAL を 10s 毎に採取。
#
# Usage: telemetry_pcie.sh <scratch_dir> <server>

set -u
SCRATCH="$1"
SERVER="${2:-mi25}"

PCIE_LOG="$SCRATCH/telemetry_pcie.log"
PIDFILE="$SCRATCH/telemetry_pcie.pid"

(
  while true; do
    EPOCH=$(date +%s)
    OUT=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "$SERVER" 'bash -s' <<'REMOTE' 2>&1
for rp in 00:02.0 00:03.0 80:02.0 80:03.0; do
  out=$(sudo -n lspci -vvs "$rp" 2>/dev/null)
  if [ -z "$out" ]; then echo "PORT=$rp STATE=ROOTPORT_ABSENT"; continue; fi
  w=$(echo "$out" | grep "LnkSta:" | head -1 | grep -oE "Width x[0-9]+" | tr -d ' ')
  sp=$(echo "$out" | grep "LnkSta:" | head -1 | grep -oE "Speed [0-9.]+GT/s" | tr -d ' ')
  pd=$(echo "$out" | grep "SltSta:" | head -1 | grep -oE "PresDet[+-]")
  cor=$(cat "/sys/bus/pci/devices/0000:$rp/aer_dev_correctable" 2>/dev/null | grep -E "^TOTAL_ERR_COR" | awk '{print $2}')
  fat=$(cat "/sys/bus/pci/devices/0000:$rp/aer_dev_fatal" 2>/dev/null | grep -E "^TOTAL_ERR_FATAL" | awk '{print $2}')
  nft=$(cat "/sys/bus/pci/devices/0000:$rp/aer_dev_nonfatal" 2>/dev/null | grep -E "^TOTAL_ERR_NONFATAL" | awk '{print $2}')
  echo "PORT=$rp W=${w:-?} SP=${sp:-?} PD=${pd:-?} COR=${cor:-?} FAT=${fat:-?} NFT=${nft:-?}"
done
gpu_count=$(lspci 2>/dev/null | grep -c "Instinct MI25")
echo "GPU_COUNT=$gpu_count"
REMOTE
    )
    RC=$?
    {
      echo "===== epoch=$EPOCH ssh_rc=$RC ====="
      echo "$OUT"
    } >> "$PCIE_LOG"
    sleep 10
  done
) &
echo "$!" > "$PIDFILE"
echo "telemetry_pcie started. pid: $(cat "$PIDFILE")"
echo "log: $PCIE_LOG"
