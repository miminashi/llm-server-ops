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
#   setup      iLO5認証情報を設定（認証テスト後に永続化）
#
# 例:
#   .claude/skills/gpu-server/scripts/power.sh t120h-p100 status
#   .claude/skills/gpu-server/scripts/power.sh t120h-p100 on
#   .claude/skills/gpu-server/scripts/power.sh t120h-p100 off
#   .claude/skills/gpu-server/scripts/power.sh t120h-p100 setup <ilo_host> <ilo_user> <ilo_pass>

set -euo pipefail

ENV_FILE="${GPU_SERVER_ENV:-${XDG_CONFIG_HOME:-$HOME/.config}/gpu-server/.env}"

SERVER="${1:-}"
ACTION="${2:-}"

if [[ -z "$SERVER" || -z "$ACTION" ]]; then
    echo "使い方: $0 <server> <action>"
    echo "アクション: status, on, off, force-off, setup"
    exit 1
fi

# サーバ名をenv変数名に変換（ハイフン→アンダースコア、大文字化）
VAR_PREFIX="ILO_$(echo "$SERVER" | tr '[:lower:]-' '[:upper:]_')"

CURL_BASE=(--insecure --silent --max-time 30)

# iLO5への認証テスト（セッション作成を試行）
# 成功時: トークンとセッションURIを出力して終了コード0
# 失敗時: エラーメッセージを出力して終了コード1
test_ilo_auth() {
    local host="$1" user="$2" pass="$3"
    local redfish_base="https://${host}/redfish/v1"

    local response
    response=$(curl "${CURL_BASE[@]}" -w "\n%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "{\"UserName\": \"${user}\", \"Password\": \"${pass}\"}" \
        "${redfish_base}/SessionService/Sessions/" 2>/dev/null) || {
        echo "エラー: iLO (${host}) に接続できません" >&2
        return 1
    }

    local http_code body
    http_code=$(echo "$response" | tail -1)
    body=$(echo "$response" | sed '$d')

    if [[ ! "$http_code" =~ ^2 ]]; then
        echo "エラー: iLO認証失敗 HTTP $http_code" >&2
        echo "$body" | jq -r '.error.message // .' 2>/dev/null >&2 || echo "$body" >&2
        return 1
    fi

    # トークン取得
    local token
    token=$(echo "$body" | jq -r '.Oem.Hpe.Token // empty')
    if [[ -z "$token" ]]; then
        token=$(curl "${CURL_BASE[@]}" -D - -o /dev/null \
            -X POST \
            -H "Content-Type: application/json" \
            -d "{\"UserName\": \"${user}\", \"Password\": \"${pass}\"}" \
            "${redfish_base}/SessionService/Sessions/" 2>/dev/null \
            | grep -i "X-Auth-Token" | tr -d '\r' | awk '{print $2}')
    fi
    local session_uri
    session_uri=$(echo "$body" | jq -r '.["@odata.id"] // empty')

    echo "${token}|${session_uri}"
    return 0
}

# 認証情報を.envファイルに保存
save_credentials() {
    local host="$1" user="$2" pass="$3"

    mkdir -p "$(dirname "$ENV_FILE")"

    # ファイルが無ければ作成
    if [[ ! -f "$ENV_FILE" ]]; then
        touch "$ENV_FILE"
        chmod 600 "$ENV_FILE"
    fi

    # 既存エントリを削除して追記
    local tmp="${ENV_FILE}.tmp.$$"
    grep -v "^${VAR_PREFIX}_" "$ENV_FILE" > "$tmp" 2>/dev/null || true
    {
        echo "${VAR_PREFIX}_HOST=${host}"
        echo "${VAR_PREFIX}_USER=${user}"
        echo "${VAR_PREFIX}_PASS=${pass}"
    } >> "$tmp"
    mv "$tmp" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
}

# --- setup アクション ---
if [[ "$ACTION" == "setup" ]]; then
    ILO_HOST="${3:-}"
    ILO_USER="${4:-}"
    ILO_PASS="${5:-}"

    if [[ -z "$ILO_HOST" || -z "$ILO_USER" || -z "$ILO_PASS" ]]; then
        echo "使い方: $0 $SERVER setup <ilo_host> <ilo_user> <ilo_pass>"
        echo ""
        echo "Claude Code から実行する場合は、AskUserQuestion で以下を問い合わせてください:"
        echo "  1. iLOのIPアドレスまたはホスト名"
        echo "  2. iLOのユーザ名"
        echo "  3. iLOのパスワード"
        exit 2
    fi

    echo "==> iLO5 認証テスト中... (${ILO_HOST})"
    AUTH_RESULT=$(test_ilo_auth "$ILO_HOST" "$ILO_USER" "$ILO_PASS") || exit 1

    # 認証成功 — セッションをクリーンアップ
    TOKEN="${AUTH_RESULT%%|*}"
    SESSION_URI="${AUTH_RESULT##*|}"
    if [[ -n "$SESSION_URI" && -n "$TOKEN" ]]; then
        curl "${CURL_BASE[@]}" -X DELETE -H "X-Auth-Token: ${TOKEN}" \
            "https://${ILO_HOST}${SESSION_URI}" >/dev/null 2>&1 || true
    fi

    echo "    認証成功"
    echo "==> 認証情報を保存中... (${ENV_FILE})"
    save_credentials "$ILO_HOST" "$ILO_USER" "$ILO_PASS"
    echo "    保存完了: ${VAR_PREFIX}_HOST/USER/PASS"
    exit 0
fi

# --- 通常アクション (status, on, off, force-off) ---

# .envから認証情報を読み込み
load_credentials() {
    if [[ ! -f "$ENV_FILE" ]]; then
        return 1
    fi
    ILO_HOST=$(grep "^${VAR_PREFIX}_HOST=" "$ENV_FILE" | cut -d= -f2- || true)
    ILO_USER=$(grep "^${VAR_PREFIX}_USER=" "$ENV_FILE" | cut -d= -f2- || true)
    ILO_PASS=$(grep "^${VAR_PREFIX}_PASS=" "$ENV_FILE" | cut -d= -f2- || true)
    [[ -n "$ILO_HOST" && -n "$ILO_USER" && -n "$ILO_PASS" ]]
}

ILO_HOST="" ILO_USER="" ILO_PASS=""
if ! load_credentials; then
    echo "エラー: ${SERVER} の iLO5 認証情報が設定されていません。"
    echo ""
    echo "AskUserQuestion で以下の情報を問い合わせて、setup コマンドで設定してください:"
    echo "  1. iLOのIPアドレスまたはホスト名"
    echo "  2. iLOのユーザ名"
    echo "  3. iLOのパスワード"
    echo ""
    echo "設定コマンド:"
    echo "  $0 $SERVER setup <ilo_host> <ilo_user> <ilo_pass>"
    exit 10
fi

REDFISH_BASE="https://${ILO_HOST}/redfish/v1"

# セッション作成
AUTH_RESULT=$(test_ilo_auth "$ILO_HOST" "$ILO_USER" "$ILO_PASS") || exit 1
AUTH_TOKEN="${AUTH_RESULT%%|*}"
SESSION_URI="${AUTH_RESULT##*|}"

CURL_AUTH=("${CURL_BASE[@]}" -H "X-Auth-Token: ${AUTH_TOKEN}")

# セッション削除用のクリーンアップ
cleanup() {
    if [[ -n "${SESSION_URI:-}" && -n "${AUTH_TOKEN:-}" ]]; then
        curl "${CURL_BASE[@]}" -X DELETE -H "X-Auth-Token: ${AUTH_TOKEN}" \
            "https://${ILO_HOST}${SESSION_URI}" >/dev/null 2>&1 || true
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
        echo "アクション: status, on, off, force-off, setup"
        exit 1
        ;;
esac
