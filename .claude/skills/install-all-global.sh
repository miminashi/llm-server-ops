#!/usr/bin/env bash
set -euo pipefail

# 全スキルをグローバル Claude Code プラグインとして一括インストールする
#
# Usage:
#   install-all-global.sh              # インストール（冪等）
#   install-all-global.sh --uninstall  # アンインストール
#   install-all-global.sh -h|--help    # ヘルプ
#
# インストール対象:
#   - gpu-server  (排他制御、リモートブラウザ、電源制御、セットアップ)
#   - llama-server (LLM推論サーバの起動・管理)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_CONFIG_DIR="${HOME}/.config/gpu-server"
ENV_CONFIG_FILE="${ENV_CONFIG_DIR}/.env"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

gpu-server / llama-server スキルをグローバル Claude Code プラグインとして
一括インストールします。

Options:
  --uninstall    全プラグインをアンインストール
  -h, --help     このヘルプを表示

インストール対象:
  gpu-server     排他制御（ロック）、リモートブラウザ、電源制御、セットアップ
  llama-server   LLM推論サーバの起動・管理、llama.cppのビルド
EOF
}

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "=> $*"; }

check_deps() {
  command -v jq >/dev/null 2>&1 || die "jq が必要です: sudo apt install jq"
  [[ -d "${HOME}/.claude" ]] || die "${HOME}/.claude が見つかりません。Claude Code がインストールされていますか？"
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

# --- インストール ---

do_install() {
  check_deps

  echo "========================================="
  echo " グローバルプラグイン一括インストール"
  echo "========================================="
  echo ""

  # .env をマージ
  info ".env の同期"
  sync_env
  echo ""

  # gpu-server
  echo "--- gpu-server ---"
  "${SCRIPT_DIR}/gpu-server/scripts/install-global.sh"
  echo ""

  # llama-server
  echo "--- llama-server ---"
  "${SCRIPT_DIR}/llama-server/scripts/install-global.sh"
  echo ""

  echo "========================================="
  echo " 全プラグインのインストールが完了しました"
  echo "========================================="
  echo ""
  echo "Claude Code を再起動してください（/exit して再度起動）。"
}

# --- アンインストール ---

do_uninstall() {
  echo "========================================="
  echo " グローバルプラグイン一括アンインストール"
  echo "========================================="
  echo ""

  echo "--- gpu-server ---"
  "${SCRIPT_DIR}/gpu-server/scripts/install-global.sh" --uninstall
  echo ""

  echo "--- llama-server ---"
  "${SCRIPT_DIR}/llama-server/scripts/install-global.sh" --uninstall
  echo ""

  echo "========================================="
  echo " 全プラグインのアンインストールが完了しました"
  echo "========================================="
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
