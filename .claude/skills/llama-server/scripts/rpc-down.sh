#!/bin/bash
set -euo pipefail

# llama.cpp RPC ワーカー (ggml-rpc-server) を停止する。
# 停止すると、そのワーカーの GPU を使っているメインホストの llama-server も
# 推論を継続できなくなるので、先に llama-server を止めること。

usage() {
  cat <<'EOF'
Usage: rpc-down.sh [server]

Arguments:
  server     GPUサーバ名 (省略時: aws-gpu02)

Examples:
  rpc-down.sh
  rpc-down.sh aws-gpu02
EOF
  exit 1
}

case "${1:-}" in
  -h|--help) usage ;;
esac

SERVER="${1:-aws-gpu02}"

case "$SERVER" in
  mi25|t120h-p100|t120h-m10|aws-gpu01|aws-gpu02) ;;
  *)
    echo "ERROR: 不明なサーバ: $SERVER" >&2
    echo "有効なサーバ: mi25, t120h-p100, t120h-m10, aws-gpu01, aws-gpu02" >&2
    exit 1
    ;;
esac

PGREP_PAT='bin/(ggml-)?rpc-server'

echo "==> $SERVER の RPC サーバプロセスを確認中..."
PIDS=$(ssh -n "$SERVER" "pgrep -f '$PGREP_PAT'" 2>/dev/null || true)

if [ -z "$PIDS" ]; then
  echo "RPC サーバは $SERVER で起動していません。"
  exit 0
fi

echo "==> RPC サーバを停止中... (PID: $(echo "$PIDS" | tr '\n' ' '))"
for PID in $PIDS; do
  ssh -n "$SERVER" "kill $PID" 2>/dev/null || true
done

# 停止確認（最大10秒待機）
for _ in $(seq 1 10); do
  REMAINING=$(ssh -n "$SERVER" "pgrep -f '$PGREP_PAT'" 2>/dev/null || true)
  if [ -z "$REMAINING" ]; then
    echo "RPC サーバを停止しました。"
    exit 0
  fi
  sleep 1
done

echo "WARNING: SIGTERM での停止がタイムアウトしました。SIGKILL で強制終了します..." >&2
REMAINING=$(ssh -n "$SERVER" "pgrep -f '$PGREP_PAT'" 2>/dev/null || true)
for PID in $REMAINING; do
  ssh -n "$SERVER" "kill -9 $PID" 2>/dev/null || true
done
sleep 2

STILL_RUNNING=$(ssh -n "$SERVER" "pgrep -f '$PGREP_PAT'" 2>/dev/null || true)
if [ -n "$STILL_RUNNING" ]; then
  echo "ERROR: SIGKILL でも RPC サーバを停止できませんでした。" >&2
  echo "手動で確認してください: ssh $SERVER 'ps aux | grep rpc-server'" >&2
  exit 1
fi

echo "RPC サーバを強制終了しました。"
exit 0
