#!/bin/bash
set -euo pipefail

# GPU監視用ttydをサーバ側でバックグラウンド起動するスクリプト

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

# サーバ別GPU監視コマンド
case "$SERVER" in
  mi25) GPU_CMD="watch -n 1 rocm-smi" ;;
  *)    GPU_CMD="nvtop" ;;
esac

# 既存プロセスを停止してからバックグラウンド起動
echo "==> ttyd GPU監視を $SERVER で起動中 (port 7681)..."
ssh "$SERVER" "ps aux | grep '[t]tyd --port 7681' | awk '{print \$2}' | xargs -r kill 2>/dev/null || true"
ssh -f "$SERVER" "nohup ttyd --port 7681 $GPU_CMD > /dev/null 2>&1 < /dev/null &"

echo "==> ttyd GPU監視をバックグラウンドで起動しました"
echo "    ブラウザ: http://$SERVER:7681"
