#!/usr/bin/env bash
# GPUサーバ電源制御の抽象化ディスパッチャ
#
# サーバ種別（HPE iLO5/Redfish か Supermicro/IPMI か）を吸収し、統一インタフェース
# <status|on|off> を提供する。llama-up.sh / llama-down.sh はこのスクリプトだけを呼ぶ。
# 低レベルの個別操作が必要なときは power.sh（Redfish）/ bmc-power.sh（IPMI）を直接使う。
#
# 使い方:
#   .claude/skills/gpu-server/scripts/power-ctl.sh <server> <status|on|off>
#
# アクション（正規化済みセマンティクス）:
#   status  電源状態を確認。標準出力に必ず "On" / "Off" / "Unknown" の1語だけを返す
#           （下位スクリプトの人間向け生出力は stderr に流す）。
#   on      電源ON。
#   off     グレースフルシャットダウン（OSに正常終了を要求）。
#             - HPE       : power.sh off      （Redfish GracefulShutdown）
#             - Supermicro: bmc-power.sh soft （ACPI ソフトシャットダウン）
#           ※ Supermicro の bmc-power.sh off はハード即時電源断（FS破損リスク）なので使わない。
#
# サーバ種別の真実源はこのファイルの server_type() の case。サーバ追加時はここを更新する。
#
# 終了コード: 下位スクリプトの終了コードをそのまま伝播する。
#   10 = 認証情報未設定 / 3 = IPMI接続失敗(Supermicro) / 1 = その他エラー / 2 = 引数エラー

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

SERVER="${1:-}"
ACTION="${2:-}"

if [[ -z "$SERVER" || -z "$ACTION" ]]; then
    echo "使い方: $0 <server> <status|on|off>" >&2
    exit 2
fi

# サーバ種別: hpe (iLO5/Redfish → power.sh) / supermicro (IPMI → bmc-power.sh)
server_type() {
    case "$1" in
        t120h-p100)  echo "hpe" ;;
        mi25)        echo "supermicro" ;;
        # t120h-m10 の BMC 方式は未確認。判明するまで既定の hpe(Redfish/power.sh)に倒す。
        # power.sh は認証情報未設定なら exit 10 で setup を案内するため、誤判定でも安全側。
        t120h-m10)   echo "hpe" ;;
        *)           echo "hpe" ;;
    esac
}

# 下位 status の生出力を受け取り、stdout に "On"/"Off"/"Unknown" の1語だけを返す。
# 注意: 呼び出しは必ずトップレベル（local を使わない）。local だと下位スクリプトの
# 終了コードが local の成功で握りつぶされ、set -e による伝播が効かなくなる。
normalize_status() {
    local raw="$1"
    echo "$raw" >&2
    # pipefail 下では grep のマッチ0件(exit 1)でパイプ全体が非ゼロになるため、
    # || true は必ずパイプライン全体の末尾(tail の後)に置く。
    local state
    state="$(printf '%s\n' "$raw" | grep -oiE 'on|off' | tail -n1 || true)"
    case "$state" in
        [Oo][Nn])      echo "On" ;;
        [Oo][Ff][Ff])  echo "Off" ;;
        *)             echo "Unknown" ;;
    esac
}

TYPE="$(server_type "$SERVER")"

case "$TYPE" in
    hpe)
        case "$ACTION" in
            status)
                # OUT 取得はトップレベル代入。下位が exit≠0 なら set -e で停止し伝播する。
                OUT="$("$SCRIPT_DIR/power.sh" "$SERVER" status)"
                normalize_status "$OUT"
                ;;
            on)   "$SCRIPT_DIR/power.sh" "$SERVER" on ;;
            off)  "$SCRIPT_DIR/power.sh" "$SERVER" off ;;
            *)    echo "エラー: 不明なアクション '$ACTION'（status|on|off）" >&2; exit 2 ;;
        esac
        ;;
    supermicro)
        case "$ACTION" in
            status)
                OUT="$("$SCRIPT_DIR/bmc-power.sh" "$SERVER" status)"
                normalize_status "$OUT"
                ;;
            on)   "$SCRIPT_DIR/bmc-power.sh" "$SERVER" on ;;
            off)  "$SCRIPT_DIR/bmc-power.sh" "$SERVER" soft ;;  # グレースフル相当へマップ
            *)    echo "エラー: 不明なアクション '$ACTION'（status|on|off）" >&2; exit 2 ;;
        esac
        ;;
esac
