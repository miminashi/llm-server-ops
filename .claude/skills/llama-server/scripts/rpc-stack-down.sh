#!/usr/bin/env bash
# aws-gpu01 + aws-gpu02 の RPC 分散構成（デフォルト構成）を停止する。
#
# 停止順序は llama-server → ggml-rpc-server。逆順にするとメインホストの推論が壊れる。
# 電源 OFF は既定で行わない（次回起動の POST でファンが爆音になるため、
# 電源を落とすかどうかはユーザの判断に委ねる）。
#
# 使い方:
#   rpc-stack-down.sh [--power-off]
#
# 環境変数:
#   MAIN / WORKER  メインホスト / RPC ワーカー（既定 aws-gpu01 / aws-gpu02）
#
# ロックは解放しない（取得していれば gpu-server/scripts/unlock.sh を別途実行）。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
GPU_SCRIPTS_DIR="$(cd "$SKILL_DIR/../gpu-server/scripts" && pwd)"

MAIN="${MAIN:-aws-gpu01}"
WORKER="${WORKER:-aws-gpu02}"
POWER_OFF=false
if [ "${1:-}" = "--power-off" ]; then
  POWER_OFF=true
fi

echo "==> [1/2] $MAIN の llama-server を停止中..."
if ! "$SCRIPT_DIR/stop.sh" "$MAIN"; then
  echo "WARNING: stop.sh が失敗しましたが、続行します" >&2
fi

echo "==> [2/2] $WORKER の RPC ワーカーを停止中..."
if ! "$SCRIPT_DIR/rpc-down.sh" "$WORKER"; then
  echo "WARNING: rpc-down.sh が失敗しましたが、続行します" >&2
fi

if [ "$POWER_OFF" = true ]; then
  echo "==> 電源を OFF にします（グレースフル）..."
  for S in "$MAIN" "$WORKER"; do
    if ! "$GPU_SCRIPTS_DIR/power-ctl.sh" "$S" off; then
      echo "WARNING: $S の電源 OFF に失敗しました（爆音ガードの場合は ALLOW_FAN_NOISE=1 が必要）" >&2
    fi
  done
fi

echo "==> 停止完了"
