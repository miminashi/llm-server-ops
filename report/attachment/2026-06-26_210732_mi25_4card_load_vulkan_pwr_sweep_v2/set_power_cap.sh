#!/bin/bash
# mi25 4枚 GPU の power1_cap を <watts> [W] に揃える。hwmon パスは再起動で変わるので動的解決。
# usage: ssh mi25 'bash -s' < set_power_cap.sh <watts>
set -euo pipefail
W=${1:?usage: $0 <watts>}
UW=$((W * 1000000))
for c in 1 2 3 4; do
  H=$(ls -d /sys/class/drm/card$c/device/hwmon/hwmon* 2>/dev/null | head -1)
  [ -z "$H" ] && { echo "ERR: no hwmon for card$c" >&2; exit 1; }
  echo "$UW" | sudo tee "$H/power1_cap" > /dev/null
  CUR=$(cat "$H/power1_cap")
  echo "card$c $H/power1_cap = ${CUR} (=$((CUR/1000000))W)"
done
