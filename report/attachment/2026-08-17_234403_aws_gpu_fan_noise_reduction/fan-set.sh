#!/usr/bin/env bash
# 全 zone(0-3) に同じ duty を設定する。mode 引数で fan mode も切替可。
#   使い方: fan-set.sh <server> duty <0xNN>     # 全 zone に duty 設定（mode は変更しない）
#           fan-set.sh <server> full <0xNN>     # Full mode に切替 → 即 全 zone に duty 設定
#           fan-set.sh <server> optimal         # Optimal(BMC 自動)へ復帰
#           fan-set.sh <server> show            # 現在の mode / duty / RPM
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SERVER="${1:?}"; OP="${2:?}"; ARG="${3:-}"

set -a; . "${GPU_SERVER_ENV:-$HOME/.config/gpu-server/.env}"; set +a
PREFIX="BMC_$(echo "$SERVER" | tr '[:lower:]-' '[:upper:]_')"
eval "HOST=\${${PREFIX}_HOST}; USER_=\${${PREFIX}_USER}; PASS=\${${PREFIX}_PASS}"
IPMI=(ipmitool -I lanplus -H "$HOST" -U "$USER_" -P "$PASS")

set_all() {
    "${IPMI[@]}" raw 0x30 0x70 0x66 0x01 0x00 "$1" >/dev/null
    "${IPMI[@]}" raw 0x30 0x70 0x66 0x01 0x01 "$1" >/dev/null
    "${IPMI[@]}" raw 0x30 0x70 0x66 0x01 0x02 "$1" >/dev/null
    "${IPMI[@]}" raw 0x30 0x70 0x66 0x01 0x03 "$1" >/dev/null
}

case "$OP" in
    duty) set_all "$ARG" ;;
    full) "${IPMI[@]}" raw 0x30 0x45 0x01 0x01 >/dev/null; set_all "$ARG" ;;
    optimal) "${IPMI[@]}" raw 0x30 0x45 0x01 0x02 >/dev/null ;;
    show) ;;
    *) echo "unknown op: $OP" >&2; exit 2 ;;
esac

sleep 2
"$HERE/fan-sample.sh" "$SERVER"
