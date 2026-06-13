#!/usr/bin/env bash
# BMC KVM スクリーンショット用の Python venv を構築する
#
# bmc-kvm.py は Playwright + Chromium で BMC の HTML5 KVM ビューアを操作し、
# canvas をスクリーンショットする。本スクリプトは uv で venv を作り playwright を導入する。
# Chromium ブラウザ本体は ~/.cache/ms-playwright/ の共有キャッシュを使うため、
# 既にダウンロード済みなら再取得は走らない。
#
# 使い方:
#   .claude/skills/gpu-server/scripts/setup-bmc-venv.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"          # .../skills/gpu-server
VENV_DIR="${SKILL_DIR}/.venv"
PY="${VENV_DIR}/bin/python"

if ! command -v uv >/dev/null 2>&1; then
    echo "エラー: uv が見つかりません。https://docs.astral.sh/uv/ を参照してください。" >&2
    exit 1
fi

if [[ ! -x "$PY" ]]; then
    echo "==> venv を作成中... (${VENV_DIR})"
    uv venv "$VENV_DIR"
fi

echo "==> playwright を導入中..."
uv pip install --python "$PY" playwright pillow

echo "==> Chromium を確認中..."
# 共有キャッシュに無い場合のみダウンロードされる
"${VENV_DIR}/bin/playwright" install chromium

echo "==> 動作確認..."
"$PY" -c "import importlib.metadata as m; from PIL import Image; print('playwright', m.version('playwright'), '/ pillow OK')"
echo "完了: ${VENV_DIR}"
