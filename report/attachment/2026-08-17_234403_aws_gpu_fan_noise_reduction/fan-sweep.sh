#!/usr/bin/env bash
# duty スイープ実験（Full mode に切替 → 指定 zone の duty を段階的に変えて RPM/温度を記録）
#   使い方: fan-sweep.sh <server> <zone:0|1> <hold_sec> <duty...>
#   例:     fan-sweep.sh aws-gpu02 0 45 0x30 0x28 0x20 0x18 0x10
#
# 安全: CPU>=75C / GPU>=75C を検知したら即 Optimal(0x02) に戻して exit 9。
#       中断(INT/TERM)・エラー時も trap で Optimal に戻す。
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SERVER="${1:?}"; ZONE="${2:?}"; HOLD="${3:-45}"; shift 3
DUTIES=("$@")

set -a; . "${GPU_SERVER_ENV:-$HOME/.config/gpu-server/.env}"; set +a
PREFIX="BMC_$(echo "$SERVER" | tr '[:lower:]-' '[:upper:]_')"
eval "HOST=\${${PREFIX}_HOST}; USER_=\${${PREFIX}_USER}; PASS=\${${PREFIX}_PASS}"
IPMI=(ipmitool -I lanplus -H "$HOST" -U "$USER_" -P "$PASS")

restore() {
    echo ">>> Optimal(0x02) に復帰させます" >&2
    "${IPMI[@]}" raw 0x30 0x45 0x01 0x02 >/dev/null 2>&1 && echo ">>> 復帰完了" >&2
}
trap 'restore; exit 130' INT TERM

CSV="$HERE/sweep_${SERVER}_zone${ZONE}.csv"
"$HERE/fan-sample.sh" "$SERVER" --header | sed 's/^/set_duty,/' > "$CSV"

sample() { echo "$1,$("$HERE/fan-sample.sh" "$SERVER")" | tee -a "$CSV"; }

echo "=== $SERVER zone$ZONE sweep: ${DUTIES[*]} (hold ${HOLD}s) ==="
echo "--- 現状(Optimal) ---"; sample "before"

# Full mode へ切替 → 間を置かず初期 duty を書く（全開時間を最小化）
"${IPMI[@]}" raw 0x30 0x45 0x01 0x01 >/dev/null
"${IPMI[@]}" raw 0x30 0x70 0x66 0x01 "0x0$ZONE" "${DUTIES[0]}" >/dev/null
echo "--- Full mode + zone$ZONE=${DUTIES[0]} 設定直後 ---"; sample "full_${DUTIES[0]}"

for d in "${DUTIES[@]}"; do
    "${IPMI[@]}" raw 0x30 0x70 0x66 0x01 "0x0$ZONE" "$d" >/dev/null
    sleep "$HOLD"
    line=$(sample "$d")
    cpu1=$(echo "$line" | cut -d, -f14); cpu2=$(echo "$line" | cut -d, -f15)
    gmax=$(echo "$line" | cut -d, -f19)
    for t in "$cpu1" "$cpu2" "$gmax"; do
        if [[ -n "$t" ]] && (( ${t%.*} >= 75 )); then
            echo "!!! 温度アボート (${t}C) !!!" >&2; restore; exit 9
        fi
    done
done

echo "=== sweep 完了。CSV: $CSV ==="
echo "（fan mode は Full のまま。必要なら restore を呼ぶこと）"
