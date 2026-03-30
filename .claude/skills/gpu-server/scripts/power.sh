#!/usr/bin/env bash
# GPUサーバの電源制御（iLO5 Redfish API経由）
#
# 使い方:
#   .claude/skills/gpu-server/scripts/power.sh <server> <action>
#
# アクション:
#   status     電源状態を確認
#   on         電源ON
#   off        グレースフルシャットダウン
#   force-off  強制電源OFF
#
# 例:
#   .claude/skills/gpu-server/scripts/power.sh t120h-p100 status
#   .claude/skills/gpu-server/scripts/power.sh t120h-p100 on
#   .claude/skills/gpu-server/scripts/power.sh t120h-p100 off

set -euo pipefail

ENV_FILE="${GPU_SERVER_ENV:-${XDG_CONFIG_HOME:-$HOME/.config}/gpu-server/.env}"

SERVER="${1:-}"
ACTION="${2:-}"

if [[ -z "$SERVER" || -z "$ACTION" ]]; then
    echo "使い方: $0 <server> <action>"
    echo "アクション: status, on, off, force-off"
    exit 1
fi

# .envから認証情報を読み込み
if [[ ! -f "$ENV_FILE" ]]; then
    echo "エラー: .env ファイルが見つかりません: $ENV_FILE"
    exit 1
fi

# サーバ名をenv変数名に変換（ハイフン→アンダースコア、大文字化）
VAR_PREFIX="ILO_$(echo "$SERVER" | tr '[:lower:]-' '[:upper:]_')"

ILO_HOST=$(grep "^${VAR_PREFIX}_HOST=" "$ENV_FILE" | cut -d= -f2-)
ILO_USER=$(grep "^${VAR_PREFIX}_USER=" "$ENV_FILE" | cut -d= -f2-)
ILO_PASS=$(grep "^${VAR_PREFIX}_PASS=" "$ENV_FILE" | cut -d= -f2-)

if [[ -z "$ILO_HOST" || -z "$ILO_USER" || -z "$ILO_PASS" ]]; then
    echo "エラー: ${VAR_PREFIX}_HOST/USER/PASS が .env に設定されていません"
    exit 1
fi

REDFISH_BASE="https://${ILO_HOST}/redfish/v1"
CURL_BASE=(--insecure --silent --max-time 30)

# セッション作成（iLO5はBasic Authではなくセッション認証が必要）
SESSION_RESPONSE=$(curl "${CURL_BASE[@]}" -w "\n%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d "{\"UserName\": \"${ILO_USER}\", \"Password\": \"${ILO_PASS}\"}" \
    "${REDFISH_BASE}/SessionService/Sessions/")
SESSION_HTTP=$(echo "$SESSION_RESPONSE" | tail -1)
SESSION_BODY=$(echo "$SESSION_RESPONSE" | sed '$d')

if [[ ! "$SESSION_HTTP" =~ ^2 ]]; then
    echo "エラー: iLOセッション作成失敗 HTTP $SESSION_HTTP"
    echo "$SESSION_BODY" | jq -r '.error.message // .' 2>/dev/null || echo "$SESSION_BODY"
    exit 1
fi

AUTH_TOKEN=$(echo "$SESSION_BODY" | jq -r '.Oem.Hpe.Token // empty')
if [[ -z "$AUTH_TOKEN" ]]; then
    # ヘッダから取得を試行
    AUTH_TOKEN=$(curl "${CURL_BASE[@]}" -D - -o /dev/null \
        -X POST \
        -H "Content-Type: application/json" \
        -d "{\"UserName\": \"${ILO_USER}\", \"Password\": \"${ILO_PASS}\"}" \
        "${REDFISH_BASE}/SessionService/Sessions/" 2>/dev/null \
        | grep -i "X-Auth-Token" | tr -d '\r' | awk '{print $2}')
fi
SESSION_URI=$(echo "$SESSION_BODY" | jq -r '.["@odata.id"] // empty')

CURL_AUTH=("${CURL_BASE[@]}" -H "X-Auth-Token: ${AUTH_TOKEN}")

# セッション削除用のクリーンアップ
cleanup() {
    if [[ -n "${SESSION_URI:-}" && -n "${AUTH_TOKEN:-}" ]]; then
        curl "${CURL_BASE[@]}" -X DELETE -H "X-Auth-Token: ${AUTH_TOKEN}" \
            "${REDFISH_BASE%/redfish/v1}${SESSION_URI}" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

case "$ACTION" in
    status)
        RESPONSE=$(curl "${CURL_AUTH[@]}" -w "\n%{http_code}" "${REDFISH_BASE}/Systems/1")
        HTTP_CODE=$(echo "$RESPONSE" | tail -1)
        BODY=$(echo "$RESPONSE" | sed '$d')

        if [[ "$HTTP_CODE" != "200" ]]; then
            echo "エラー: iLO API応答 HTTP $HTTP_CODE"
            echo "$BODY" | jq -r '.error.message // .' 2>/dev/null || echo "$BODY"
            exit 1
        fi

        POWER_STATE=$(echo "$BODY" | jq -r '.PowerState')
        echo "$SERVER: 電源状態 = $POWER_STATE"
        ;;

    on|off|force-off)
        case "$ACTION" in
            on)        RESET_TYPE="On" ;;
            off)       RESET_TYPE="GracefulShutdown" ;;
            force-off) RESET_TYPE="ForceOff" ;;
        esac

        RESPONSE=$(curl "${CURL_AUTH[@]}" -w "\n%{http_code}" \
            -X POST \
            -H "Content-Type: application/json" \
            -d "{\"ResetType\": \"${RESET_TYPE}\"}" \
            "${REDFISH_BASE}/Systems/1/Actions/ComputerSystem.Reset")
        HTTP_CODE=$(echo "$RESPONSE" | tail -1)
        BODY=$(echo "$RESPONSE" | sed '$d')

        if [[ "$HTTP_CODE" =~ ^2 ]]; then
            echo "$SERVER: ${ACTION} コマンドを送信しました (ResetType: ${RESET_TYPE})"
        else
            echo "エラー: iLO API応答 HTTP $HTTP_CODE"
            echo "$BODY" | jq -r '.error.message // .' 2>/dev/null || echo "$BODY"
            exit 1
        fi
        ;;

    *)
        echo "エラー: 不明なアクション '$ACTION'"
        echo "アクション: status, on, off, force-off"
        exit 1
        ;;
esac
