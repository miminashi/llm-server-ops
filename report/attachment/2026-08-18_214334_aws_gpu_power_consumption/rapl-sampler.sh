#!/usr/bin/env bash
# リモート側で実行する RAPL サンプラー（ssh "sudo bash -s" に流し込んで使う）。
# 10 秒毎に epoch と package/dram の累積エネルギー [uJ] を CSV 1 行で吐く。
# 列: epoch,pkg0_uj,pkg1_uj,dram0_uj,dram1_uj
DURATION="${1:-1400}"
END=$(( $(date +%s) + DURATION ))
while [[ $(date +%s) -lt $END ]]; do
    E=$(cat /sys/class/powercap/intel-rapl:0/energy_uj \
             /sys/class/powercap/intel-rapl:1/energy_uj \
             /sys/class/powercap/intel-rapl:0:0/energy_uj \
             /sys/class/powercap/intel-rapl:1:0/energy_uj 2>/dev/null | tr '\n' ',')
    echo "$(date +%s),${E%,}"
    sleep 10
done
