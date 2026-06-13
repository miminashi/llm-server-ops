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
# 例:
#   .claude/skills/gpu-server/scripts/bmc-power.sh mi25 status
#   .claude/skills/gpu-server/scripts/bmc-power.sh mi25 reset
#   .claude/skills/gpu-server/scripts/bmc-power.sh mi25 cycle 20

set -euo pipefail

ENV_FILE="${GPU_SERVER_ENV:-${XDG_CONFIG_HOME:-$HOME/.config}/gpu-server/.env}"

SERVER="${1:-}"
ACTION="${2:-}"

if [[ -z "$SERVER" || -z "$ACTION" ]]; then
    echo "使い方: $0 <server> <action> [args...]"
    echo "アクション: status, reset, cycle [wait], on, off, soft"
    exit 2
fi

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
        run_ipmi chassis power reset >/dev/null
        echo "${SERVER}: ハードリセットを要求しました"
        ;;
    cycle)
        WAIT_SECS="${3:-15}"
        echo "${SERVER}: 電源OFF..."
        run_ipmi chassis power off >/dev/null
        echo "${SERVER}: ${WAIT_SECS}秒待機..."
        sleep "$WAIT_SECS"
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
