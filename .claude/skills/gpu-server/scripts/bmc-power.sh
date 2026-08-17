#!/usr/bin/env bash
# GPUサーバの電源制御（IPMI / ipmitool lanplus 経由）
#
# Supermicro 機（mi25 = X10DRG-Q など）は Redfish が DCMS ライセンス未活性で
# 使えないため、OS 非依存の out-of-band 電源制御には IPMI を用いる。
# HPE iLO5 機（t120h-p100 など）は Redfish が使えるので従来通り power.sh を使うこと。
#
# 使い方:
#   .claude/skills/gpu-server/scripts/bmc-power.sh <server> <action> [args...]
#
# アクション:
#   status        電源状態を確認（System Power: on/off）
#   reset         即時ハードリセット（暖機なし。OS ハングからの復旧本命）
#   cycle [wait]  電源OFF → wait秒待機 → ON（コールドブート。既定 wait=15）
#   on            電源ON
#   off           ハード電源OFF（即時）
#   soft          ACPI ソフトシャットダウン（OS にシャットダウン要求）
#
# 認証情報:
#   ~/.config/gpu-server/.env の BMC_<SERVER>_HOST/USER/PASS から解決する。
#   未設定の場合は終了コード 10 で bmc-setup.sh の使用を案内する。
#   （環境変数 GPU_SERVER_ENV で .env のパスを上書き可能）
#
# 終了コード:
#   0 正常 / 1 その他エラー / 2 引数エラー / 3 IPMI接続失敗 / 10 認証情報未設定
#   20 = ファン爆音サーバに対する電源操作を拒否（下記「爆音ガード」参照）
#
# 爆音ガード:
#   FAN_LOUD_SERVERS に列挙したサーバは、起動時にファンが爆音になるため
#   ユーザの明確な指示なしに電源を操作してはならない。該当サーバに対する
#   on/off/soft/reset/cycle は ALLOW_FAN_NOISE=1 が無い限り exit 20 で拒否する。
#   status は読み取りのみなので常に許可。
#
# 起動時のファン抑制 (boot-quiet の自動併走):
#   FAN_LOUD_SERVERS に対して on/reset/cycle を実行するとき、boot-quiet.sh を
#   バックグラウンドで自動起動して POST 中の回転数を抑える。POST 中の BMC は
#   ファン制御を手放さず duty を 100% に書き戻すため完全には抑えられないが、
#   平均回転数は下がる (2026-08-17 実測: 中央値 5,386 → 3,700rpm)。
#   NO_BOOT_QUIET=1 で無効化。duty/秒数は BOOT_QUIET_DUTY / BOOT_QUIET_SECS で変更可。
#
# 例:
#   .claude/skills/gpu-server/scripts/bmc-power.sh mi25 status
#   .claude/skills/gpu-server/scripts/bmc-power.sh mi25 reset
#   .claude/skills/gpu-server/scripts/bmc-power.sh mi25 cycle 20
#   ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 on

set -euo pipefail

ENV_FILE="${GPU_SERVER_ENV:-${XDG_CONFIG_HOME:-$HOME/.config}/gpu-server/.env}"

# 起動時にファンが爆音になるサーバ（ユーザの明示指示なしに電源操作しない）
FAN_LOUD_SERVERS="aws-gpu01 aws-gpu02"

SERVER="${1:-}"
ACTION="${2:-}"

if [[ -z "$SERVER" || -z "$ACTION" ]]; then
    echo "使い方: $0 <server> <action> [args...]"
    echo "アクション: status, reset, cycle [wait], on, off, soft"
    exit 2
fi

# 爆音サーバへの電源操作を ALLOW_FAN_NOISE=1 が無い限り拒否する。
# off/soft も対象にするのは、一度落とすと復帰に必ず爆音を伴う電源投入が要るため。
guard_fan_noise() {
    local server="$1" action="$2"
    echo "$FAN_LOUD_SERVERS" | grep -qw "$server" || return 0
    case "$action" in
        on|off|soft|reset|cycle) ;;
        *) return 0 ;;
    esac
    [[ "${ALLOW_FAN_NOISE:-}" == "1" ]] && return 0
    echo "エラー: ${server} への電源操作 '${action}' を拒否しました。" >&2
    echo "" >&2
    echo "${server} は起動時にファンが爆音になるため、ユーザの明確な指示なしに" >&2
    echo "リブート・電源投入・電源断を行わない運用になっています。" >&2
    echo "" >&2
    echo "ユーザの指示を得た上で意図的に実行する場合のみ、以下のように明示してください:" >&2
    echo "  ALLOW_FAN_NOISE=1 $0 ${server} ${action}" >&2
    exit 20
}

guard_fan_noise "$SERVER" "$ACTION"

# 爆音サーバの電源投入時に boot-quiet.sh を併走させ、POST 中の回転数を抑える。
# 電源が入る直前に呼ぶこと（boot-quiet は BMC に Full + 低 duty を投げ続ける）。
start_boot_quiet() {
    local server="$1" script log pidfile
    echo "$FAN_LOUD_SERVERS" | grep -qw "$server" || return 0
    [[ "${NO_BOOT_QUIET:-}" == "1" ]] && return 0
    script="$(dirname "$0")/boot-quiet.sh"
    if [[ ! -x "$script" ]]; then
        echo "警告: ${script} が見つからないので起動時のファン抑制をスキップします" >&2
        return 0
    fi
    # 二重起動の判定は boot-quiet.sh が書く pidfile で行う（pgrep -f のパターン照合は
    # 呼び出し元のコマンドラインに誤マッチしうるため使わない）
    pidfile="/tmp/boot-quiet-${server}.pid"
    if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile" 2>/dev/null)" 2>/dev/null; then
        echo "${server}: boot-quiet は既に稼働中なので新たに起動しません (pid $(cat "$pidfile"))"
        return 0
    fi
    log="/tmp/boot-quiet-${server}.log"
    BOOT_QUIET_WRITE_INTERVAL="${BOOT_QUIET_WRITE_INTERVAL:-0.5}" \
    BOOT_QUIET_SAMPLE_EVERY="${BOOT_QUIET_SAMPLE_EVERY:-20}" \
        setsid nohup "$script" "$server" "${BOOT_QUIET_DUTY:-0x10}" "${BOOT_QUIET_SECS:-420}" \
        > "$log" 2>&1 < /dev/null &
    echo "${server}: 起動中のファン抑制 (boot-quiet) を開始しました → ${log}"
    sleep 1  # 電源が入る前に最初の duty 投入を済ませる
}

# サーバ名 → env変数名（ハイフン→アンダースコア、大文字化）
VAR_PREFIX="BMC_$(echo "$SERVER" | tr '[:lower:]-' '[:upper:]_')"

# .env から BMC 認証情報を読み込み
load_credentials() {
    if [[ ! -f "$ENV_FILE" ]]; then
        return 1
    fi
    BMC_HOST=$(grep "^${VAR_PREFIX}_HOST=" "$ENV_FILE" | cut -d= -f2- || true)
    BMC_USER=$(grep "^${VAR_PREFIX}_USER=" "$ENV_FILE" | cut -d= -f2- || true)
    BMC_PASS=$(grep "^${VAR_PREFIX}_PASS=" "$ENV_FILE" | cut -d= -f2- || true)
    [[ -n "$BMC_HOST" && -n "$BMC_USER" && -n "$BMC_PASS" ]]
}

BMC_HOST="" BMC_USER="" BMC_PASS=""
if ! load_credentials; then
    echo "エラー: ${SERVER} の BMC 認証情報が設定されていません。" >&2
    echo "" >&2
    echo "bmc-setup.sh で登録してください:" >&2
    echo "  $(dirname "$0")/bmc-setup.sh ${SERVER} <bmc_ip> <bmc_user> <bmc_pass>" >&2
    exit 10
fi

# ipmitool 共通オプション（lanplus）
IPMI=(ipmitool -I lanplus -H "$BMC_HOST" -U "$BMC_USER" -P "$BMC_PASS")

# 接続失敗（exit 3）と通常エラーを区別するヘルパ
run_ipmi() {
    local out rc
    out=$("${IPMI[@]}" "$@" 2>&1) || rc=$?
    rc=${rc:-0}
    if [[ $rc -ne 0 ]]; then
        echo "$out" >&2
        # 認証・到達性エラーは接続失敗として扱う
        if echo "$out" | grep -qiE 'unable to establish|connection timed out|no route|authentication|password|rakp'; then
            exit 3
        fi
        exit 1
    fi
    echo "$out"
}

case "$ACTION" in
    status)
        OUT=$(run_ipmi chassis status)
        POWER=$(echo "$OUT" | sed -n 's/^System Power[[:space:]]*:[[:space:]]*\(.*\)$/\1/p' | tr -d '\r')
        echo "${SERVER}: System Power: ${POWER:-unknown}"
        ;;
    on)
        start_boot_quiet "$SERVER"
        run_ipmi chassis power on >/dev/null
        echo "${SERVER}: 電源ON を要求しました"
        ;;
    off)
        run_ipmi chassis power off >/dev/null
        echo "${SERVER}: ハード電源OFF を要求しました"
        ;;
    soft)
        run_ipmi chassis power soft >/dev/null
        echo "${SERVER}: ACPI ソフトシャットダウンを要求しました"
        ;;
    reset)
        start_boot_quiet "$SERVER"
        run_ipmi chassis power reset >/dev/null
        echo "${SERVER}: ハードリセットを要求しました"
        ;;
    cycle)
        WAIT_SECS="${3:-15}"
        echo "${SERVER}: 電源OFF..."
        run_ipmi chassis power off >/dev/null
        echo "${SERVER}: ${WAIT_SECS}秒待機..."
        sleep "$WAIT_SECS"
        start_boot_quiet "$SERVER"
        echo "${SERVER}: 電源ON..."
        run_ipmi chassis power on >/dev/null
        echo "${SERVER}: 電源サイクル完了"
        ;;
    *)
        echo "エラー: 不明なアクション '$ACTION'" >&2
        echo "アクション: status, reset, cycle [wait], on, off, soft" >&2
        exit 2
        ;;
esac
