#!/usr/bin/env bash
# 1ブート分の GPU トポロジ要約を1行で出力(mi25 のホームに置いて再利用)
slots="00:02.0 00:03.0 80:02.0 80:03.0"
out=""
for rp in $slots; do
  if [ -n "$(lspci -s "$rp" 2>/dev/null)" ]; then
    w=$(sudo -n lspci -vvs "$rp" 2>/dev/null | grep -oP 'LnkSta:.*Width \Kx[0-9]+' | head -1)
    out="$out $rp=${w:-x?}"
  else
    out="$out $rp=MISSING"
  fi
done
guids=$(rocm-smi --showid 2>/dev/null | grep -oP 'GUID:\s*\K[0-9]+' | sort -n | tr '\n' ',')
ngpu=$(rocm-smi --showid 2>/dev/null | grep -c 'Device Name')
echo "uptime=$(uptime -s) ngpu=$ngpu guids=[$guids] slots:$out"
