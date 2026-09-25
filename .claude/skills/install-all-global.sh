#!/usr/bin/env bash
set -euo pipefail

# 全スキルをグローバル Claude Code プラグインとして一括インストールする
#
# Usage:
#   install-all-global.sh              # インストール（冪等。再実行で最新のスキルに更新）
#   install-all-global.sh --uninstall  # アンインストール
#   install-all-global.sh -h|--help    # ヘルプ
#
# 仕組み:
#   ローカルマーケットプレース llm-server-ops-local をステージングディレクトリに生成し、
#   `claude plugin` CLI で正規に登録・インストールする。プラグイン llm-server-ops に
#   gpu-server / llama-server / discord-notify の 3 スキルを兄弟として収めるので、
#   スクリプト内の `$SKILL_DIR/../gpu-server/scripts` 等の相対参照はそのまま解決する。
#   他プロジェクトからは `llm-server-ops:gpu-server` のような名前空間付きで見える。
#
#   旧版（2026-09-26 まで）は claude-plugins-official のプラグインに偽装して登録しており、
#   「not found in marketplace」で読み込まれていなかった。その残骸はインストール時に掃除する。

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_CONFIG_DIR="${HOME}/.config/gpu-server"
ENV_CONFIG_FILE="${ENV_CONFIG_DIR}/.env"

PLUGIN_NAME="llm-server-ops"
PLUGIN_VERSION="1.0.0"
MARKETPLACE="llm-server-ops-local"
PLUGIN_KEY="${PLUGIN_NAME}@${MARKETPLACE}"
SKILLS=(gpu-server llama-server discord-notify)

CLAUDE_DIR="${HOME}/.claude"
SETTINGS_JSON="${CLAUDE_DIR}/settings.json"
INSTALLED_PLUGINS_JSON="${CLAUDE_DIR}/plugins/installed_plugins.json"
STAGING_DIR="${HOME}/.local/share/claude-marketplaces/${PLUGIN_NAME}"
PLUGIN_SRC="${STAGING_DIR}/plugins/${PLUGIN_NAME}"

# 旧版の偽装登録
LEGACY_MARKETPLACE="claude-plugins-official"
LEGACY_PLUGINS=(gpu-server llama-server)

# permissions.allow に登録するスクリプト（<skill>/scripts/<file>）
PERM_SCRIPTS=(
  gpu-server/lock.sh
  gpu-server/unlock.sh
  gpu-server/lock-status.sh
  gpu-server/power.sh
  gpu-server/power-ctl.sh
  gpu-server/setup-llama-cpp.sh
  gpu-server/setup-remote-browser.sh
  gpu-server/transfer-file.sh
  llama-server/start.sh
  llama-server/stop.sh
  llama-server/wait-ready.sh
  llama-server/ttyd-gpu.sh
  llama-server/ttyd-up.sh
  llama-server/monitor-download.sh
  llama-server/llama-up.sh
  llama-server/llama-down.sh
)

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

gpu-server / llama-server / discord-notify スキルを、グローバル Claude Code プラグイン
${PLUGIN_KEY} として一括インストールします。再実行すると最新のスキルで入れ直します。

Options:
  --uninstall    プラグインをアンインストール
  -h, --help     このヘルプを表示

インストール後のスキル名（他プロジェクトから見える名前）:
  ${PLUGIN_NAME}:gpu-server     排他制御（ロック）、リモートブラウザ、電源制御、セットアップ
  ${PLUGIN_NAME}:llama-server   LLM推論サーバの起動・管理、llama.cppのビルド
  ${PLUGIN_NAME}:discord-notify Discord 通知
EOF
}

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "=> $*"; }

check_deps() {
  command -v jq >/dev/null 2>&1 || die "jq が必要です: sudo apt install jq"
  command -v claude >/dev/null 2>&1 || die "claude CLI が PATH にありません"
  [[ -d "${CLAUDE_DIR}" ]] || die "${CLAUDE_DIR} が見つかりません。Claude Code がインストールされていますか？"
  local s
  for s in "${SKILLS[@]}"; do
    [[ -f "${SCRIPT_DIR}/${s}/SKILL.md" ]] || die "ソース SKILL.md が見つかりません: ${SCRIPT_DIR}/${s}/SKILL.md"
  done
}

# JSON ファイルをアトミックに更新する
# Usage: json_update <file> <jq_expression> [jq_args...]
json_update() {
  local file="$1"; shift
  local expr="$1"; shift
  local tmp="${file}.tmp.$$"
  jq "$@" "$expr" "$file" > "$tmp"
  mv "$tmp" "$file"
}

# permissions.allow から文字列 $1 を含む項目を除去する
remove_perms_containing() {
  [[ -f "${SETTINGS_JSON}" ]] || return 0
  json_update "${SETTINGS_JSON}" \
    'if .permissions.allow then .permissions.allow |= map(select(contains($s) | not)) else . end' \
    --arg s "$1"
}

# インストール済みなら installPath を出力する（未インストールなら空）
installed_path() {
  claude plugin list --json 2>/dev/null \
    | jq -r --arg id "${PLUGIN_KEY}" '.[] | select(.id == $id) | .installPath' 2>/dev/null || true
}

# プロジェクトの .env から ~/.config/gpu-server/.env へ秘密情報をマージ
sync_env() {
  # プロジェクトルートを算出（.claude/skills/ の2階層上）
  local project_root
  project_root="$(cd "${SCRIPT_DIR}/../.." && pwd)"
  local project_env="${project_root}/.env"

  if [[ ! -f "$project_env" ]]; then
    if [[ ! -f "$ENV_CONFIG_FILE" ]]; then
      echo "WARNING: .env が見つかりません（${project_env} も ${ENV_CONFIG_FILE} もなし）" >&2
      echo "         HF_TOKEN が必要な場合は手動で ${ENV_CONFIG_FILE} を作成してください" >&2
    fi
    return 0
  fi

  mkdir -p "$ENV_CONFIG_DIR"

  if [[ ! -f "$ENV_CONFIG_FILE" ]]; then
    info ".env をコピー: ${project_env} -> ${ENV_CONFIG_FILE}"
    cp "$project_env" "$ENV_CONFIG_FILE"
    chmod 600 "$ENV_CONFIG_FILE"
    return 0
  fi

  # 既存の設定ファイルに不足しているキーを追記
  local added=0
  while IFS='=' read -r key _; do
    # コメント行・空行をスキップ
    [[ -z "$key" || "$key" == \#* ]] && continue
    if ! grep -q "^${key}=" "$ENV_CONFIG_FILE" 2>/dev/null; then
      local line
      line=$(grep "^${key}=" "$project_env")
      echo "$line" >> "$ENV_CONFIG_FILE"
      info "  ${key} を ${ENV_CONFIG_FILE} に追記"
      added=1
    fi
  done < "$project_env"

  if [[ $added -eq 0 ]]; then
    info ".env は最新です（${ENV_CONFIG_FILE}）"
  fi
}

# 旧版が claude-plugins-official に偽装して書き込んだ登録を消す（冪等）
cleanup_legacy() {
  local p key
  for p in "${LEGACY_PLUGINS[@]}"; do
    key="${p}@${LEGACY_MARKETPLACE}"
    local base="${CLAUDE_DIR}/plugins/cache/${LEGACY_MARKETPLACE}/${p}"
    if [[ -d "$base" ]]; then
      info "旧登録のファイルを削除: ${base}"
      rm -rf "$base"
    fi
    if [[ -f "${INSTALLED_PLUGINS_JSON}" ]] && jq -e --arg k "$key" '.plugins | has($k)' "${INSTALLED_PLUGINS_JSON}" >/dev/null; then
      info "installed_plugins.json から旧登録を削除: ${key}"
      json_update "${INSTALLED_PLUGINS_JSON}" 'del(.plugins[$k])' --arg k "$key"
    fi
    if [[ -f "${SETTINGS_JSON}" ]] && jq -e --arg k "$key" '(.enabledPlugins // {}) | has($k)' "${SETTINGS_JSON}" >/dev/null; then
      info "settings.json の enabledPlugins から旧登録を削除: ${key}"
      json_update "${SETTINGS_JSON}" 'del(.enabledPlugins[$k])' --arg k "$key"
    fi
    remove_perms_containing "${base}/"
  done
}

# プラグインとマーケットプレースを CLI から外す（未登録なら何もしない）
unregister() {
  local old_path
  old_path="$(installed_path)"
  if [[ -n "$old_path" ]]; then
    info "既存のプラグインをアンインストール: ${PLUGIN_KEY}"
    claude plugin uninstall "${PLUGIN_KEY}" >/dev/null
    remove_perms_containing "${old_path}/"
  fi
  if claude plugin marketplace list 2>/dev/null | grep -q "${MARKETPLACE}"; then
    info "マーケットプレースを登録解除: ${MARKETPLACE}"
    claude plugin marketplace remove "${MARKETPLACE}" >/dev/null
  fi
}

# ステージングディレクトリにマーケットプレースを生成する
build_staging() {
  info "マーケットプレースを生成: ${STAGING_DIR}"
  rm -rf "${STAGING_DIR}"
  mkdir -p "${STAGING_DIR}/.claude-plugin" "${PLUGIN_SRC}/.claude-plugin" "${PLUGIN_SRC}/skills"

  cat > "${STAGING_DIR}/.claude-plugin/marketplace.json" <<EOF
{
  "name": "${MARKETPLACE}",
  "owner": { "name": "llm-server-ops" },
  "plugins": [
    {
      "name": "${PLUGIN_NAME}",
      "source": "./plugins/${PLUGIN_NAME}",
      "description": "GPUサーバの管理（ロック・電源・リモートブラウザ）と llama-server の起動・管理、Discord 通知"
    }
  ]
}
EOF
  cat > "${PLUGIN_SRC}/.claude-plugin/plugin.json" <<EOF
{
  "name": "${PLUGIN_NAME}",
  "description": "GPUサーバ（mi25、t120h-p100、t120h-m10、aws-gpu01、aws-gpu02、aws-v100）の管理と llama-server の起動・管理、Discord 通知",
  "version": "${PLUGIN_VERSION}"
}
EOF

  local s
  for s in "${SKILLS[@]}"; do
    cp -r "${SCRIPT_DIR}/${s}" "${PLUGIN_SRC}/skills/${s}"
    # venv は作成時の絶対パスに縛られ、コピーしても動かない（gpu-server の BMC 用 .venv は
    # 必要ならインストール先で setup-bmc-venv.sh を実行して作り直す）
    find "${PLUGIN_SRC}/skills/${s}" \( -name .venv -o -name __pycache__ \) -type d -prune -exec rm -rf {} +
    chmod +x "${PLUGIN_SRC}/skills/${s}/scripts/"*.sh 2>/dev/null || true
  done
}

# インストール先の *.md にある相対パス参照を絶対パスへ変換する
rewrite_docs() {
  local root="$1"
  info "スキル文書のパスを変換: .claude/skills/ -> ${root}/skills/"
  find "${root}/skills" -name '*.md' -print0 | xargs -0 sed -i \
    -e "s#\.claude/skills/\(gpu-server\|llama-server\|discord-notify\)/#${root}/skills/\1/#g" \
    -e 's#^\*\*すべてのスクリプトはプロジェクトルートからの相対パス.*$#**スクリプトは以下に記載の絶対パスで実行してください（グローバルプラグイン '"${PLUGIN_KEY}"' としてインストール済み）。**#'
}

add_perms() {
  local root="$1"
  info "settings.json に permissions を登録"
  [[ -f "${SETTINGS_JSON}" ]] || echo '{}' > "${SETTINGS_JSON}"
  local perms_json item
  perms_json="$(for item in "${PERM_SCRIPTS[@]}"; do
    printf 'Bash(%s/skills/%s/scripts/%s:*)\n' "${root}" "${item%%/*}" "${item#*/}"
  done | jq -R . | jq -s .)"
  json_update "${SETTINGS_JSON}" \
    '.permissions.allow = (((.permissions.allow // []) + $new) | unique)' \
    --argjson new "${perms_json}"
}

# --- インストール ---

do_install() {
  check_deps

  echo "========================================="
  echo " グローバルプラグインのインストール"
  echo "========================================="
  echo ""

  info ".env の同期"
  sync_env

  cleanup_legacy
  unregister
  build_staging

  info "マーケットプレースを登録: ${STAGING_DIR}"
  claude plugin marketplace add "${STAGING_DIR}"
  info "プラグインをインストール: ${PLUGIN_KEY}"
  claude plugin install "${PLUGIN_KEY}"

  local root
  root="$(installed_path)"
  [[ -n "$root" && -d "$root/skills" ]] || die "インストール先が取得できません（claude plugin list --json を確認してください）"

  rewrite_docs "$root"
  add_perms "$root"

  echo ""
  echo "=== インストール完了 ==="
  echo "  プラグイン:     ${PLUGIN_KEY}"
  echo "  インストール先: ${root}"
  echo ""
  echo "Claude Code を再起動してください（/exit して再度起動）。"
}

# --- アンインストール ---

do_uninstall() {
  command -v jq >/dev/null 2>&1 || die "jq が必要です: sudo apt install jq"
  command -v claude >/dev/null 2>&1 || die "claude CLI が PATH にありません"

  unregister
  if [[ -d "${STAGING_DIR}" ]]; then
    info "マーケットプレースのディレクトリを削除: ${STAGING_DIR}"
    rm -rf "${STAGING_DIR}"
  fi
  remove_perms_containing "${STAGING_DIR}/"
  cleanup_legacy

  echo ""
  echo "=== アンインストール完了 ==="
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
