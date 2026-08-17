#!/usr/bin/env bash
# 起動（POST）中のファン爆音を抑える／記録する。
#
# aws-gpu01 / aws-gpu02 は電源投入から OS 起動までの間、BMC が全ファンを 100%
# (約 11900rpm) で回すため爆音になる。BMC は POST 中も IPMI を受け付けるので、
# 電源 ON 直後から外部（このワークステーション）から
#   fan mode = Full + 低 duty
# を投げ続けることで、この区間の回転を抑えられる。
#
# 使い方:
#   boot-quiet.sh <server> [duty_hex] [duration_sec]   # 抑制しながら RPM を記録
#   boot-quiet.sh <server> --observe [duration_sec]    # 何もせず RPM だけ記録（比較用）
#
# 例（電源投入と同時に別端末で走らせる、あるいはバックグラウンドで起動してから reset）:
#   boot-quiet.sh aws-gpu02 0x10 420 &
#   ALLOW_FAN_NOISE=1 bmc-power.sh aws-gpu02 reset
#
# サーバ側の smc-fanctl.service が上がると以降はそちらが duty を管理するので、
# このスクリプトはデーモンの稼働を検知したら自動終了する。
set -uo pipefail

ENV_FILE="${GPU_SERVER_ENV:-${XDG_CONFIG_HOME:-$HOME/.config}/gpu-server/.env}"
SERVER="${1:-}"
if [[ -z "$SERVER" ]]; then
    echo "使い方: $0 <server> [duty_hex|--observe] [duration_sec]" >&2
    exit 2
fi

MODE=suppress
DUTY=0x10
DURATION=420
case "${2:-}" in
    --observe) MODE=observe; DURATION="${3:-$DURATION}" ;;
    "") ;;
    *) DUTY="$2"; DURATION="${3:-$DURATION}" ;;
esac

# shellcheck source=/dev/null
set -a; . "$ENV_FILE"; set +a
PREFIX="BMC_$(echo "$SERVER" | tr '[:lower:]-' '[:upper:]_')"
eval "HOST=\${${PREFIX}_HOST:-}; USER_=\${${PREFIX}_USER:-}; PASS=\${${PREFIX}_PASS:-}"
if [[ -z "$HOST" || -z "$USER_" || -z "$PASS" ]]; then
    echo "エラー: ${SERVER} の BMC 認証情報が未設定です（bmc-setup.sh を実行）" >&2
    exit 10
fi
IPMI=(ipmitool -I lanplus -H "$HOST" -U "$USER_" -P "$PASS")

# POST 中は BMC が duty を 100% に書き戻してくるので、書き込みは高頻度で行い、
# 計測（SDR 読み）は数回に 1 回に間引く。
WRITE_INTERVAL="${BOOT_QUIET_WRITE_INTERVAL:-0.5}"
SAMPLE_EVERY="${BOOT_QUIET_SAMPLE_EVERY:-6}"
MODE_CHECK_EVERY="${BOOT_QUIET_MODE_CHECK_EVERY:-20}"  # fan mode の確認間隔（周回数）

CSV="${BOOT_QUIET_CSV:-/tmp/boot-quiet-${SERVER}.csv}"
echo "elapsed_s,mode,duty0,fan1,fan2,fan3,fan4,fan5,fan6,fan7,fan8,cpu1,gpu_max,power" > "$CSV"

# 二重起動の検出用 pidfile（bmc-power.sh がこれを見て併走の有無を判断する）。
# pgrep -f でのパターン照合は呼び出し元のコマンドラインに誤マッチしうるため使わない。
PIDFILE="${BOOT_QUIET_PIDFILE:-/tmp/boot-quiet-${SERVER}.pid}"
echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT

echo "=== boot-quiet: ${SERVER} (${MODE}, duty=${DUTY}, ${DURATION}s) → ${CSV} ==="

START=$SECONDS
daemon_up=0
iter=0
while (( SECONDS - START < DURATION )); do
    ELAPSED=$((SECONDS - START))
    iter=$((iter + 1))

    if [[ "$MODE" == "suppress" ]]; then
        # fan mode は「Full でなければ設定する」に留める。毎周期 Full を書き直すと
        # そのたびに BMC が全 zone を 100% にリセットするため（2026-08-17 実測）、
        # 稼働中の機体や smc-fanctl と擾乱し合ってかえって回転が上がる。
        if (( iter % MODE_CHECK_EVERY == 1 )); then
            CUR_MODE=$("${IPMI[@]}" raw 0x30 0x45 0x00 2>/dev/null | tr -d ' \r\n')
            if [[ "$CUR_MODE" != "01" ]]; then
                "${IPMI[@]}" raw 0x30 0x45 0x01 0x01 >/dev/null 2>&1
            fi
        fi
        # duty は毎周期投げ直す（POST 中は BMC が 100% に書き戻してくる）。
        # エラーは無視（BMC が応答しない瞬間がある）
        for z in 0x00 0x01 0x02 0x03; do
            "${IPMI[@]}" raw 0x30 0x70 0x66 0x01 "$z" "$DUTY" >/dev/null 2>&1
        done
        # 計測しない周回はここで次へ（書き込み頻度を優先する）
        if (( iter % SAMPLE_EVERY != 0 )); then
            sleep "$WRITE_INTERVAL"
            continue
        fi
    fi

    SDR=$("${IPMI[@]}" sdr 2>/dev/null)
    D0=$("${IPMI[@]}" raw 0x30 0x70 0x66 0x00 0x00 2>/dev/null | tr -d ' \r\n')
    M=$("${IPMI[@]}" raw 0x30 0x45 0x00 2>/dev/null | tr -d ' \r\n')
    PWR=$("${IPMI[@]}" chassis status 2>/dev/null | sed -n 's/^System Power[[:space:]]*:[[:space:]]*//p' | tr -d '\r')

    val() { echo "$SDR" | awk -F'|' -v n="$1" '{gsub(/^[ \t]+|[ \t]+$/,"",$1)} $1==n {gsub(/[^0-9.]/,"",$2); print $2; exit}'; }
    gmax() { echo "$SDR" | awk -F'|' '$1 ~ /GPU[0-9]+ Temp/ {gsub(/[^0-9.]/,"",$2); if ($2+0>m) m=$2+0} END {if (m>0) print m}'; }

    LINE="$ELAPSED,$M,$D0"
    for f in FAN1 FAN2 FAN3 FAN4 FAN5 FAN6 FAN7 FAN8; do LINE+=",$(val $f)"; done
    LINE+=",$(val 'CPU1 Temp'),$(gmax),${PWR:-?}"
    echo "$LINE" | tee -a "$CSV"

    # サーバ側デーモンが上がったら以降は任せる
    if (( ELAPSED > 60 )) && ssh -o ConnectTimeout=3 -o BatchMode=yes "$SERVER" \
            "systemctl is-active --quiet smc-fanctl.service" 2>/dev/null; then
        daemon_up=1
        echo ">>> smc-fanctl.service が稼働開始（elapsed ${ELAPSED}s）。制御を引き渡して終了します"
        break
    fi
    sleep "$WRITE_INTERVAL"
done

if [[ "$MODE" == "suppress" && $daemon_up -eq 0 ]]; then
    echo ">>> 注意: デーモンの起動を検知できませんでした。fan mode は Full のままです。" >&2
    echo ">>>       サーバ側デーモンが無い場合は Optimal に戻してください:" >&2
    echo ">>>       ipmitool -I lanplus -H $HOST -U $USER_ -P *** raw 0x30 0x45 0x01 0x02" >&2
fi
echo "=== 記録: $CSV ==="
