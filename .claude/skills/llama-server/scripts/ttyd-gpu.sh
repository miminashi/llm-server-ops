#!/bin/bash
set -euo pipefail

# GPU監視用ttydを起動するスクリプト（後方互換のための薄いラッパー）
#
# ttyd 起動ロジックは ttyd-up.sh に集約済み。本スクリプトは互換のために残し、
# ttyd-up.sh へ委譲する。GPU監視 (7681) に加えログ閲覧 (7682) も起動される。

if [ $# -lt 1 ]; then
  echo "Usage: ttyd-gpu.sh <server>" >&2
  echo "  server: mi25, t120h-p100, t120h-m10" >&2
  exit 1
fi

SERVER="$1"

# --- サーバ名バリデーション ---
case "$SERVER" in
  mi25|t120h-p100|t120h-m10) ;;
  *)
    echo "ERROR: 不明なサーバ: $SERVER" >&2
    exit 1
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

exec "$SCRIPT_DIR/ttyd-up.sh" "$SERVER"
