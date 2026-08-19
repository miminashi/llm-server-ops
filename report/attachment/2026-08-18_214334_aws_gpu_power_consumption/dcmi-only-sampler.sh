#!/usr/bin/env bash
# BMC (IPMI DCMI) だけでシャーシ電力を採る観測者効果フリーのサンプラー。
# ssh を張らないので測定対象 OS の CPU を起こさない。
# 使い方: dcmi-only-sampler.sh <server> <out_csv> [interval] [duration]
set -u
SERVER="$1"; OUT="$2"; INTERVAL="${3:-10}"; DURATION="${4:-600}"
ENV_FILE="${GPU_SERVER_ENV:-$HOME/.config/gpu-server/.env}"
VAR_PREFIX="BMC_$(echo "$SERVER" | tr '[:lower:]-' '[:upper:]_')"
H=$(grep "^${VAR_PREFIX}_HOST=" "$ENV_FILE" | cut -d= -f2-)
U=$(grep "^${VAR_PREFIX}_USER=" "$ENV_FILE" | cut -d= -f2-)
P=$(grep "^${VAR_PREFIX}_PASS=" "$ENV_FILE" | cut -d= -f2-)
echo "$$" > "${OUT}.pid"
echo "epoch,iso_ts,server,chassis_w" > "$OUT"
END=$(( $(date +%s) + DURATION ))
while [[ $(date +%s) -lt $END ]]; do
    E=$(date +%s)
    W=$(timeout 25 ipmitool -I lanplus -H "$H" -U "$U" -P "$P" dcmi power reading 2>/dev/null \
        | sed -n 's/^[[:space:]]*Instantaneous power reading:[[:space:]]*\([0-9]*\).*/\1/p')
    echo "${E},$(TZ=Asia/Tokyo date -d "@$E" +%H:%M:%S),${SERVER},${W}" >> "$OUT"
    S=$(( INTERVAL - ($(date +%s) - E) )); [[ $S -gt 0 ]] && sleep "$S"
done
rm -f "${OUT}.pid"
