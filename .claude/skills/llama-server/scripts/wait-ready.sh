#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
NOTIFY_SCRIPT="$(cd "$SKILL_DIR/../discord-notify/scripts" && pwd)/notify.sh"

usage() {
  cat <<'EOF'
Usage: wait-ready.sh <server> <hf-model> [ctx-size] [sampling-opts]

start.sh をバックグラウンドで実行した後、ヘルスチェックとDiscord通知を行う。

Arguments:
  server         GPUサーバ名 (mi25, t120h-p100, t120h-m10)
  hf-model       HuggingFaceモデル (例: unsloth/gpt-oss-20b-GGUF:Q8_0)
  ctx-size       コンテキストサイズ (省略時: 65536)
  sampling-opts  サンプリングオプション (省略時: --temp 1.0 --top-p 1.0 --top-k 0)

Examples:
  wait-ready.sh t120h-p100 "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M" 131072
EOF
  exit 1
}

if [ $# -lt 2 ]; then
  usage
fi

SERVER="$1"
HF_MODEL="$2"
CTX_SIZE="${3:-65536}"
SAMPLING_OPTS="${4:---temp 1.0 --top-p 1.0 --top-k 0}"

# --- IPアドレス解決 ---
IP=$(ssh -G "$SERVER" | grep '^hostname ' | awk '{print $2}')
HEALTH_URL="http://${IP}:8000/health"

echo "==> ヘルスチェック中... ($HEALTH_URL)"
MAX_RETRIES=30
RETRY_INTERVAL=5

for i in $(seq 1 $MAX_RETRIES); do
  STATUS=$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" 2>/dev/null || echo "000")
  if [ "$STATUS" = "200" ]; then
    echo "llama-server が正常に起動しました (attempt $i/$MAX_RETRIES)"
    echo ""
    echo "API endpoint: http://${IP}:8000/v1"

    # Discord通知
    if [ -x "$NOTIFY_SCRIPT" ]; then
      NOTIFY_MSG="llama-server 起動完了
- サーバ: ${SERVER}
- モデル: ${HF_MODEL}
- ctx-size: ${CTX_SIZE}
- サンプリング: ${SAMPLING_OPTS}
- エンドポイント: http://${IP}:8000/v1
- GPU監視: http://${IP}:7681
- サーバログ: http://${IP}:7682"
      "$NOTIFY_SCRIPT" "$NOTIFY_MSG" || echo "WARNING: Discord通知の送信に失敗しました" >&2
    fi

    exit 0
  fi
  if [ "$STATUS" = "503" ]; then
    echo "  [$i/$MAX_RETRIES] モデルロード中... (HTTP 503)"
  else
    echo "  [$i/$MAX_RETRIES] 待機中... (HTTP $STATUS)"
  fi
  sleep $RETRY_INTERVAL
done

echo "WARNING: ヘルスチェックがタイムアウトしました。" >&2
echo "ログを確認してください: ssh $SERVER 'tail -50 /tmp/llama-server.log'" >&2
exit 1
