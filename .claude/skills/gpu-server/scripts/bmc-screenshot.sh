#!/usr/bin/env bash
# BMC KVM スクリーンショット取得（サーバ名指定の薄いラッパ）
#
# ~/.config/gpu-server/.env の BMC_<SERVER>_HOST/USER/PASS を解決して
# bmc-kvm.py screenshot を呼ぶ。OS がハング/クラッシュして SSH が効かない時でも
# BMC 経由で画面（POST/パニック/BIOS）を画像化できる。
#
# 使い方:
#   .claude/skills/gpu-server/scripts/bmc-screenshot.sh <server> <output.png> [--timeout SEC]
#
# 例:
#   .claude/skills/gpu-server/scripts/bmc-screenshot.sh mi25 /tmp/mi25.png

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PY="${SKILL_DIR}/.venv/bin/python"
KVM_PY="${SCRIPT_DIR}/bmc-kvm.py"
ENV_FILE="${GPU_SERVER_ENV:-${XDG_CONFIG_HOME:-$HOME/.config}/gpu-server/.env}"

SERVER="${1:-}"
OUTPUT="${2:-}"
shift 2 2>/dev/null || true

if [[ -z "$SERVER" || -z "$OUTPUT" ]]; then
    echo "使い方: $0 <server> <output.png> [--timeout SEC]" >&2
    exit 2
fi

if [[ ! -x "$VENV_PY" ]]; then
    echo "エラー: venv が未構築です。先に setup-bmc-venv.sh を実行してください。" >&2
    echo "  ${SCRIPT_DIR}/setup-bmc-venv.sh" >&2
    exit 3
fi

VAR_PREFIX="BMC_$(echo "$SERVER" | tr '[:lower:]-' '[:upper:]_')"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "エラー: ${SERVER} の BMC 認証情報が未設定です。bmc-setup.sh で登録してください。" >&2
    exit 10
fi
BMC_HOST=$(grep "^${VAR_PREFIX}_HOST=" "$ENV_FILE" | cut -d= -f2- || true)
BMC_USER=$(grep "^${VAR_PREFIX}_USER=" "$ENV_FILE" | cut -d= -f2- || true)
BMC_PASS=$(grep "^${VAR_PREFIX}_PASS=" "$ENV_FILE" | cut -d= -f2- || true)
if [[ -z "$BMC_HOST" || -z "$BMC_USER" || -z "$BMC_PASS" ]]; then
    echo "エラー: ${SERVER} の BMC 認証情報が未設定です。bmc-setup.sh で登録してください。" >&2
    exit 10
fi

exec "$VENV_PY" "$KVM_PY" \
    --bmc-ip "$BMC_HOST" --bmc-user "$BMC_USER" --bmc-pass "$BMC_PASS" \
    "$@" \
    screenshot "$OUTPUT"
