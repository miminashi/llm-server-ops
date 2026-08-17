#!/usr/bin/env bash
# 温度連動ファン制御デーモン (smc-fanctl) を aws-gpu01 / aws-gpu02 に導入する。
#
# 使い方:
#   .claude/skills/gpu-server/scripts/install-fan-control.sh <server> [--uninstall]
#   .claude/skills/gpu-server/scripts/install-fan-control.sh all
#
# 何をするか:
#   1. ipmitool を導入（in-band /dev/ipmi0 経由で BMC を叩くため）
#   2. /opt/smc-fanctl/smc-fanctl.py を配置
#   3. /etc/systemd/system/smc-fanctl.service を配置して enable + start
#
# --uninstall はサービスを停止し（停止時に fan mode が Optimal に戻る）ファイルを削除する。
#
# 注: リモート側で sudo を使う（対象機は NOPASSWD 設定済み）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$(cd "${SCRIPT_DIR}/../fan-control" && pwd)"
SUPPORTED="aws-gpu01 aws-gpu02"

SERVER="${1:-}"
MODE="${2:-install}"

if [[ -z "$SERVER" ]]; then
    echo "使い方: $0 <aws-gpu01|aws-gpu02|all> [--uninstall]" >&2
    exit 2
fi
[[ "$MODE" == "--uninstall" ]] && MODE=uninstall

info() { echo "=> $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

install_one() {
    local s="$1"
    info "[$s] ipmitool を確認"
    if ! ssh "$s" "command -v ipmitool >/dev/null"; then
        info "[$s] ipmitool を導入します"
        ssh "$s" "sudo apt-get install -y ipmitool" >/dev/null || die "[$s] ipmitool の導入に失敗"
    fi
    ssh "$s" "test -c /dev/ipmi0" || die "[$s] /dev/ipmi0 がありません（ipmi_si 未ロード？）"

    info "[$s] smc-fanctl.py を /opt/smc-fanctl/ に配置"
    scp -q "${SRC_DIR}/smc-fanctl.py" "$s:/tmp/smc-fanctl.py"
    ssh "$s" "sudo install -d -m 755 /opt/smc-fanctl && \
              sudo install -m 755 /tmp/smc-fanctl.py /opt/smc-fanctl/smc-fanctl.py && \
              rm -f /tmp/smc-fanctl.py"

    info "[$s] systemd unit を配置して有効化"
    scp -q "${SRC_DIR}/smc-fanctl.service" "$s:/tmp/smc-fanctl.service"
    ssh "$s" "sudo install -m 644 /tmp/smc-fanctl.service /etc/systemd/system/smc-fanctl.service && \
              rm -f /tmp/smc-fanctl.service && \
              sudo systemctl daemon-reload && \
              sudo systemctl enable smc-fanctl.service && \
              sudo systemctl restart smc-fanctl.service"

    sleep 12
    info "[$s] 状態:"
    ssh "$s" "systemctl is-active smc-fanctl.service; \
              sudo journalctl -u smc-fanctl.service -n 5 --no-pager | cat; \
              printf 'fan mode: '; sudo ipmitool -I open raw 0x30 0x45 0x00; \
              printf 'duty z0-z3:'; for z in 0 1 2 3; do printf ' %s' \"\$(sudo ipmitool -I open raw 0x30 0x70 0x66 0x00 0x0\$z)\"; done; echo; \
              sudo ipmitool -I open sdr type fan | head -8"
}

uninstall_one() {
    local s="$1"
    info "[$s] サービスを停止（停止時に fan mode は Optimal に戻る）"
    ssh "$s" "sudo systemctl disable --now smc-fanctl.service || true; \
              sudo rm -f /etc/systemd/system/smc-fanctl.service; \
              sudo rm -rf /opt/smc-fanctl; \
              sudo systemctl daemon-reload; \
              printf 'fan mode: '; sudo ipmitool -I open raw 0x30 0x45 0x00"
}

targets=()
if [[ "$SERVER" == "all" ]]; then
    read -ra targets <<< "$SUPPORTED"
else
    echo "$SUPPORTED" | grep -qw "$SERVER" || die "未対応のサーバ: $SERVER（対象: $SUPPORTED）"
    targets=("$SERVER")
fi

for t in "${targets[@]}"; do
    if [[ "$MODE" == "uninstall" ]]; then uninstall_one "$t"; else install_one "$t"; fi
done

echo
echo "=== 完了 ==="
