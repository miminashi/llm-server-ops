#!/usr/bin/env bash
# aws-gpu01/02 のファン・温度・duty を CSV 1 行で出力する（WS から lanplus 経由・読み取りのみ）
#   使い方: fan-sample.sh <server> [--header]
set -uo pipefail

SERVER="${1:?usage: fan-sample.sh <aws-gpu01|aws-gpu02> [--header]}"
MODE_ARG="${2:-}"

if [[ "$MODE_ARG" == "--header" ]]; then
    echo "ts,mode,duty0,duty1,fan1,fan2,fan3,fan4,fan5,fan6,fan7,fan8,cpu1,cpu2,system,periph,gpu_max,pch"
    exit 0
fi

set -a; . "${GPU_SERVER_ENV:-$HOME/.config/gpu-server/.env}"; set +a
PREFIX="BMC_$(echo "$SERVER" | tr '[:lower:]-' '[:upper:]_')"
eval "HOST=\${${PREFIX}_HOST}; USER_=\${${PREFIX}_USER}; PASS=\${${PREFIX}_PASS}"
IPMI=(ipmitool -I lanplus -H "$HOST" -U "$USER_" -P "$PASS")

SDR=$("${IPMI[@]}" sdr 2>/dev/null)
MODE=$("${IPMI[@]}" raw 0x30 0x45 0x00 2>/dev/null | tr -d ' \r\n')
D0=$("${IPMI[@]}" raw 0x30 0x70 0x66 0x00 0x00 2>/dev/null | tr -d ' \r\n')
D1=$("${IPMI[@]}" raw 0x30 0x70 0x66 0x00 0x01 2>/dev/null | tr -d ' \r\n')

val() {  # センサ名 → 数値（No Reading や na は空欄）
    echo "$SDR" | awk -F'|' -v n="$1" '
        { gsub(/^[ \t]+|[ \t]+$/, "", $1) }
        $1 == n { gsub(/[^0-9.]/, "", $2); print $2; exit }'
}
gpu_max() {
    echo "$SDR" | awk -F'|' '
        $1 ~ /GPU[0-9]+ Temp/ { gsub(/[^0-9.]/, "", $2); if ($2+0 > m) m = $2+0 }
        END { if (m > 0) print m }'
}

printf '%s,%s,%s,%s' "$(date +%Y-%m-%dT%H:%M:%S)" "$MODE" "$D0" "$D1"
for f in FAN1 FAN2 FAN3 FAN4 FAN5 FAN6 FAN7 FAN8; do printf ',%s' "$(val $f)"; done
printf ',%s,%s,%s,%s,%s,%s\n' \
    "$(val 'CPU1 Temp')" "$(val 'CPU2 Temp')" "$(val 'System Temp')" \
    "$(val 'Peripheral Temp')" "$(gpu_max)" "$(val 'PCH Temp')"
