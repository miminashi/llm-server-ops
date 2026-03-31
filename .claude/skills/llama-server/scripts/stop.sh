#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
NOTIFY_SCRIPT="$(cd "$SKILL_DIR/../discord-notify/scripts" && pwd)/notify.sh"

usage() {
  cat <<'EOF'
Usage: stop.sh <server>

Arguments:
  server     GPUサーバ名 (mi25, t120h-p100, t120h-m10)

Examples:
  stop.sh t120h-p100
  stop.sh mi25
EOF
  exit 1
}

if [ $# -lt 1 ]; then
  usage
fi

SERVER="$1"

# --- サーバ名バリデーション ---
case "$SERVER" in
  mi25|t120h-p100|t120h-m10) ;;
  *)
    echo "ERROR: 不明なサーバ: $SERVER" >&2
    echo "有効なサーバ: mi25, t120h-p100, t120h-m10" >&2
    exit 1
    ;;
esac

# --- llama-server プロセス検索 ---
echo "==> $SERVER の llama-server プロセスを確認中..."
PIDS=$(ssh "$SERVER" "pgrep -f './build/bin/llama-server'" 2>/dev/null || true)

if [ -z "$PIDS" ]; then
  echo "llama-server は $SERVER で起動していません。"
  exit 0
fi

# 起動中のモデル情報を取得（通知用）
MODEL_INFO=$(ssh "$SERVER" "ps -p $(echo $PIDS | tr ' ' ',') -o args= 2>/dev/null | head -1" || true)
ALIAS=$(echo "$MODEL_INFO" | grep -oP '(?<=--alias )\S+' || echo "unknown")

# --- 停止 ---
echo "==> llama-server を停止中... (PID: $PIDS)"
for PID in $PIDS; do
  ssh "$SERVER" "kill $PID" 2>/dev/null || true
done

# 停止確認（最大10秒待機）
for i in $(seq 1 10); do
  REMAINING=$(ssh "$SERVER" "pgrep -f './build/bin/llama-server'" 2>/dev/null || true)
  if [ -z "$REMAINING" ]; then
    echo "llama-server を停止しました。"

    # --- ttyd 停止 ---
    echo "==> ttyd を停止中..."
    ssh "$SERVER" "pkill -f 'ttyd --port 768' 2>/dev/null || true"

    # Discord通知（失敗しても主機能のexit codeに影響させない）
    if [ -x "$NOTIFY_SCRIPT" ]; then
      NOTIFY_MSG="llama-server 停止
- サーバ: ${SERVER}
- モデル: ${ALIAS}"
      ("$NOTIFY_SCRIPT" "$NOTIFY_MSG" || echo "WARNING: Discord通知の送信に失敗しました" >&2) || true
    fi

    exit 0
  fi
  sleep 1
done

# SIGTERM で停止できなかった場合、SIGKILL にエスカレーション
echo "WARNING: SIGTERM での停止がタイムアウトしました。SIGKILL で強制終了します..." >&2
REMAINING=$(ssh "$SERVER" "pgrep -f './build/bin/llama-server'" 2>/dev/null || true)
if [ -n "$REMAINING" ]; then
  for PID in $REMAINING; do
    ssh "$SERVER" "kill -9 $PID" 2>/dev/null || true
  done
  sleep 2
  STILL_RUNNING=$(ssh "$SERVER" "pgrep -f './build/bin/llama-server'" 2>/dev/null || true)
  if [ -n "$STILL_RUNNING" ]; then
    echo "ERROR: SIGKILL でも llama-server を停止できませんでした。" >&2
    echo "手動で確認してください: ssh $SERVER 'ps aux | grep llama-server'" >&2
    exit 1
  fi
fi

echo "llama-server を強制終了しました。"

# --- ttyd 停止 ---
echo "==> ttyd を停止中..."
ssh "$SERVER" "pkill -f 'ttyd --port 768' 2>/dev/null || true"

# Discord通知（失敗しても主機能のexit codeに影響させない）
if [ -x "$NOTIFY_SCRIPT" ]; then
  NOTIFY_MSG="llama-server 強制停止 (SIGKILL)
- サーバ: ${SERVER}
- モデル: ${ALIAS}"
  ("$NOTIFY_SCRIPT" "$NOTIFY_MSG" || echo "WARNING: Discord通知の送信に失敗しました" >&2) || true
fi

exit 0
