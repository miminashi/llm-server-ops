#!/usr/bin/env bash
set -euo pipefail

# llama-server スキルをグローバル Claude Code プラグインとしてインストールする
#
# Usage:
#   install-global.sh              # インストール（冪等）
#   install-global.sh --uninstall  # アンインストール
#   install-global.sh -h|--help    # ヘルプ

PLUGIN_NAME="llama-server"
PLUGIN_VERSION="1.0.0"
MARKETPLACE="claude-plugins-official"
PLUGIN_KEY="${PLUGIN_NAME}@${MARKETPLACE}"

CLAUDE_DIR="${HOME}/.claude"
INSTALL_BASE="${CLAUDE_DIR}/plugins/cache/${MARKETPLACE}/${PLUGIN_NAME}/${PLUGIN_VERSION}"
SKILL_DIR="${INSTALL_BASE}/skills/${PLUGIN_NAME}"
SCRIPTS_PATH="${SKILL_DIR}/scripts"
INSTALLED_PLUGINS_JSON="${CLAUDE_DIR}/plugins/installed_plugins.json"
SETTINGS_JSON="${CLAUDE_DIR}/settings.json"

# ソースディレクトリ: スクリプト自身の場所から算出
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# discord-notify はllama-serverの兄弟スキル
DISCORD_NOTIFY_SOURCE="$(cd "${SOURCE_DIR}/../discord-notify" && pwd)"

# パーミッション追加対象スクリプト
PERM_SCRIPTS=(
  start.sh
  stop.sh
  wait-ready.sh
  ttyd-gpu.sh
  monitor-download.sh
)

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

llama-server スキルをグローバル Claude Code プラグインとしてインストールします。

Options:
  --uninstall    プラグインをアンインストール
  -h, --help     このヘルプを表示
EOF
}

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "=> $*"; }

check_deps() {
  command -v jq >/dev/null 2>&1 || die "jq が必要です: sudo apt install jq"
  [[ -d "${CLAUDE_DIR}" ]] || die "${CLAUDE_DIR} が見つかりません。Claude Code がインストールされていますか？"
  [[ -f "${SOURCE_DIR}/SKILL.md" ]] || die "ソース SKILL.md が見つかりません: ${SOURCE_DIR}/SKILL.md"
}

# JSON ファイルをアトミックに更新する
json_update() {
  local file="$1"; shift
  local expr="$1"; shift
  local tmp="${file}.tmp.$$"
  jq "$@" "$expr" "$file" > "$tmp"
  mv "$tmp" "$file"
}

# --- インストール ---

do_install() {
  check_deps

  info "ファイルをコピー: ${SOURCE_DIR} -> ${SKILL_DIR}"
  rm -rf "${INSTALL_BASE}"
  mkdir -p "${SKILL_DIR}"
  cp -r "${SOURCE_DIR}/." "${SKILL_DIR}/"
  chmod +x "${SCRIPTS_PATH}"/*.sh

  # discord-notify を兄弟スキルとしてコピー（stop.sh, wait-ready.sh が参照）
  local discord_dest="${INSTALL_BASE}/skills/discord-notify"
  if [[ -d "${DISCORD_NOTIFY_SOURCE}" ]]; then
    info "discord-notify をコピー: ${DISCORD_NOTIFY_SOURCE} -> ${discord_dest}"
    mkdir -p "${discord_dest}"
    cp -r "${DISCORD_NOTIFY_SOURCE}/." "${discord_dest}/"
    chmod +x "${discord_dest}/scripts/"*.sh 2>/dev/null || true
  else
    echo "WARNING: discord-notify が見つかりません: ${DISCORD_NOTIFY_SOURCE}" >&2
  fi

  info "plugin.json を作成"
  mkdir -p "${INSTALL_BASE}/.claude-plugin"
  cat > "${INSTALL_BASE}/.claude-plugin/plugin.json" <<EOF
{
  "name": "${PLUGIN_NAME}",
  "description": "llama-serverの起動・管理、llama.cppのビルド。モデル選択、起動コマンド、サーバ別最適化パラメータ。",
  "version": "${PLUGIN_VERSION}"
}
EOF

  info "SKILL.md のパスを変換"
  local relative_path=".claude/skills/llama-server/scripts/"
  if [[ -f "${SKILL_DIR}/SKILL.md" ]]; then
    sed -i "s|${relative_path}|${SCRIPTS_PATH}/|g" "${SKILL_DIR}/SKILL.md"
    # gpu-server スキルへの相対参照も更新
    local gpu_relative=".claude/skills/gpu-server/scripts/"
    # gpu-server がグローバルインストール済みならそのパスを使用
    local gpu_global_scripts="${CLAUDE_DIR}/plugins/cache/${MARKETPLACE}/gpu-server/1.0.0/skills/gpu-server/scripts"
    if [[ -d "${gpu_global_scripts}" ]]; then
      sed -i "s|${gpu_relative}|${gpu_global_scripts}/|g" "${SKILL_DIR}/SKILL.md"
    fi
    # 「プロジェクトルートから実行」注意書きを更新
    sed -i \
      -e 's|すべてのスクリプトはプロジェクトルートからの相対パス.*で実行してください。|スクリプトは絶対パスで実行してください（グローバルプラグインとしてインストール済み）。|' \
      -e '/フルパス.*承認ダイアログが毎回表示されます。/d' \
      "${SKILL_DIR}/SKILL.md"
  fi

  info "installed_plugins.json を更新"
  if [[ ! -f "${INSTALLED_PLUGINS_JSON}" ]] || [[ ! -s "${INSTALLED_PLUGINS_JSON}" ]]; then
    mkdir -p "$(dirname "${INSTALLED_PLUGINS_JSON}")"
    echo '{"version": 2, "plugins": {}}' > "${INSTALLED_PLUGINS_JSON}"
  fi
  local timestamp
  timestamp="$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")"
  json_update "${INSTALLED_PLUGINS_JSON}" \
    '.plugins[$key] = [{"scope":"user","installPath":$path,"version":$ver,"installedAt":$ts,"lastUpdated":$ts,"isLocal":true}]' \
    --arg key "${PLUGIN_KEY}" \
    --arg path "${INSTALL_BASE}" \
    --arg ver "${PLUGIN_VERSION}" \
    --arg ts "${timestamp}"

  info "settings.json を更新（enabledPlugins + permissions）"
  if [[ ! -f "${SETTINGS_JSON}" ]]; then
    echo '{}' > "${SETTINGS_JSON}"
  fi

  # enabledPlugins に追加
  json_update "${SETTINGS_JSON}" \
    '.enabledPlugins[$key] = true' \
    --arg key "${PLUGIN_KEY}"

  # パーミッションを追加（重複排除）
  local perms_json="["
  local first=true
  for script in "${PERM_SCRIPTS[@]}"; do
    ${first} || perms_json+=","
    first=false
    perms_json+="\"Bash(${SCRIPTS_PATH}/${script}:*)\""
  done
  perms_json+="]"

  json_update "${SETTINGS_JSON}" \
    '.permissions.allow = ((.permissions.allow // []) + ($new | map(select(. as $p | ($existing | index($p)) == null)))) | .permissions.allow |= unique' \
    --argjson new "${perms_json}" \
    --argjson existing "$(jq '.permissions.allow // []' "${SETTINGS_JSON}")"

  echo ""
  echo "=== インストール完了 ==="
  echo "  プラグイン: ${PLUGIN_KEY}"
  echo "  バージョン: ${PLUGIN_VERSION}"
  echo "  インストール先: ${INSTALL_BASE}"
  echo ""
  echo "Claude Code を再起動してください（/exit して再度起動）。"
}

# --- アンインストール ---

do_uninstall() {
  info "インストールディレクトリを削除: ${INSTALL_BASE}"
  rm -rf "${INSTALL_BASE}"
  rmdir "${CLAUDE_DIR}/plugins/cache/${MARKETPLACE}/${PLUGIN_NAME}" 2>/dev/null || true

  if [[ -f "${INSTALLED_PLUGINS_JSON}" ]]; then
    info "installed_plugins.json からエントリを削除"
    json_update "${INSTALLED_PLUGINS_JSON}" \
      'del(.plugins[$key])' \
      --arg key "${PLUGIN_KEY}"
  fi

  if [[ -f "${SETTINGS_JSON}" ]]; then
    info "settings.json から enabledPlugins を削除"
    json_update "${SETTINGS_JSON}" \
      'del(.enabledPlugins[$key])' \
      --arg key "${PLUGIN_KEY}"

    info "settings.json からパーミッションを削除"
    json_update "${SETTINGS_JSON}" \
      '.permissions.allow |= map(select(contains($path) | not))' \
      --arg path "${SCRIPTS_PATH}/"
  fi

  echo ""
  echo "=== アンインストール完了 ==="
  echo "  プラグイン: ${PLUGIN_KEY}"
  echo ""
  echo "Claude Code を再起動してください。"
}

# --- メイン ---

case "${1:-}" in
  --uninstall)
    do_uninstall
    ;;
  -h|--help)
    usage
    ;;
  "")
    do_install
    ;;
  *)
    die "不明なオプション: $1（--help を参照）"
    ;;
esac
