#!/usr/bin/env bash
# BMC（IPMI）認証情報の登録
#
# ipmitool で疎通テスト後、~/.config/gpu-server/.env に
# BMC_<SERVER>_HOST/USER/PASS として保存する（chmod 600）。
#
# 使い方:
#   .claude/skills/gpu-server/scripts/bmc-setup.sh <server> [bmc_ip] [bmc_user] [bmc_pass]
#
#   bmc_ip を省略するとサーバ別の既定 BMC IP を使用する。
#
# 例:
#   .claude/skills/gpu-server/scripts/bmc-setup.sh mi25 10.1.4.7 claude Claude123
#   .claude/skills/gpu-server/scripts/bmc-setup.sh mi25            # 既定IP + 対話入力は不可（引数必須）

set -euo pipefail

ENV_FILE="${GPU_SERVER_ENV:-${XDG_CONFIG_HOME:-$HOME/.config}/gpu-server/.env}"

SERVER="${1:-}"
if [[ -z "$SERVER" ]]; then
    echo "使い方: $0 <server> [bmc_ip] [bmc_user] [bmc_pass]"
    exit 2
fi

# サーバ別の既定 BMC IP（bmc_ip 省略時に使用）
default_bmc_ip() {
    case "$1" in
        mi25)        echo "10.1.4.7" ;;
        t120h-p100)  echo "10.1.4.8" ;;
        *)           echo "" ;;
    esac
}

BMC_HOST="${2:-$(default_bmc_ip "$SERVER")}"
BMC_USER="${3:-}"
BMC_PASS="${4:-}"

if [[ -z "$BMC_HOST" || -z "$BMC_USER" || -z "$BMC_PASS" ]]; then
    echo "使い方: $0 $SERVER <bmc_ip> <bmc_user> <bmc_pass>" >&2
    if [[ -n "$BMC_HOST" ]]; then
        echo "  （${SERVER} の既定 BMC IP は ${BMC_HOST}）" >&2
    fi
    echo "" >&2
    echo "Claude Code から実行する場合は AskUserQuestion で以下を問い合わせてください:" >&2
    echo "  1. BMC の IP アドレス" >&2
    echo "  2. BMC のユーザ名" >&2
    echo "  3. BMC のパスワード" >&2
    exit 2
fi

VAR_PREFIX="BMC_$(echo "$SERVER" | tr '[:lower:]-' '[:upper:]_')"

echo "==> IPMI 疎通テスト中... (${BMC_HOST})"
if ! ipmitool -I lanplus -H "$BMC_HOST" -U "$BMC_USER" -P "$BMC_PASS" mc info >/tmp/bmc_setup_mcinfo.$$ 2>&1; then
    echo "エラー: IPMI 疎通/認証に失敗しました" >&2
    cat /tmp/bmc_setup_mcinfo.$$ >&2
    rm -f /tmp/bmc_setup_mcinfo.$$
    exit 1
fi
PRODUCT=$(sed -n 's/^Product Name[[:space:]]*:[[:space:]]*\(.*\)$/\1/p' /tmp/bmc_setup_mcinfo.$$ | tr -d '\r')
FWREV=$(sed -n 's/^Firmware Revision[[:space:]]*:[[:space:]]*\(.*\)$/\1/p' /tmp/bmc_setup_mcinfo.$$ | tr -d '\r')
rm -f /tmp/bmc_setup_mcinfo.$$
echo "    疎通成功 (Product: ${PRODUCT:-?}, FW: ${FWREV:-?})"

echo "==> 認証情報を保存中... (${ENV_FILE})"
mkdir -p "$(dirname "$ENV_FILE")"
if [[ ! -f "$ENV_FILE" ]]; then
    touch "$ENV_FILE"
    chmod 600 "$ENV_FILE"
fi
tmp="${ENV_FILE}.tmp.$$"
grep -v "^${VAR_PREFIX}_" "$ENV_FILE" > "$tmp" 2>/dev/null || true
{
    echo "${VAR_PREFIX}_HOST=${BMC_HOST}"
    echo "${VAR_PREFIX}_USER=${BMC_USER}"
    echo "${VAR_PREFIX}_PASS=${BMC_PASS}"
} >> "$tmp"
mv "$tmp" "$ENV_FILE"
chmod 600 "$ENV_FILE"
echo "    保存完了: ${VAR_PREFIX}_HOST/USER/PASS"
