#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
NOTIFY_SCRIPT="$(cd "$SKILL_DIR/../discord-notify/scripts" && pwd)/notify.sh"

usage() {
  cat <<'EOF'
Usage: wait-ready.sh <server> <hf-model> [ctx-size|fit] [fit-ctx]

start.sh をバックグラウンドで実行した後、ヘルスチェックとDiscord通知を行う。

Arguments:
  server     GPUサーバ名 (mi25, t120h-p100, t120h-m10)
  hf-model   HuggingFaceモデル (例: unsloth/gpt-oss-20b-GGUF:Q8_0)
  ctx-size   コンテキストサイズ or "fit" (省略時: 65536)
  fit-ctx    fitモード時のctx-size (省略時: 8192、"fit"指定時のみ有効)

Examples:
  wait-ready.sh t120h-p100 "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M" 131072
  wait-ready.sh t120h-p100 "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit 16384
EOF
  exit 1
}

if [ $# -lt 2 ]; then
  usage
fi

SERVER="$1"
HF_MODEL="$2"
CTX_SIZE_ARG="${3:-65536}"
FIT_CTX="${4:-8192}"

# fitモード判定
if [ "$CTX_SIZE_ARG" = "fit" ]; then
  CTX_SIZE_DISPLAY="fit (MoE CPUオフロード, ctx-size: $FIT_CTX)"
else
  CTX_SIZE_DISPLAY="$CTX_SIZE_ARG"
fi

# モデル別サンプリングパラメータ
case "$HF_MODEL" in
  *Qwen3.5*)
    SAMPLING_OPTS="--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0"
    ;;
  *)
    SAMPLING_OPTS="--temp 1.0 --top-p 1.0 --top-k 0"
    ;;
esac

# --- IPアドレス解決 ---
IP=$(ssh -G "$SERVER" | grep '^hostname ' | awk '{print $2}')
HEALTH_URL="http://${IP}:8000/health"

echo "==> ヘルスチェック中... ($HEALTH_URL)"
# fitモードまたは大コンテキスト（>65536）時はリトライ上限を引き上げ（300秒）
if [ "$CTX_SIZE_ARG" = "fit" ] || { [ "$CTX_SIZE_ARG" != "fit" ] && [ "$CTX_SIZE_ARG" -gt 65536 ] 2>/dev/null; }; then
  MAX_RETRIES=60
else
  MAX_RETRIES=30
fi
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
- ctx-size: ${CTX_SIZE_DISPLAY}
- サンプリング: ${SAMPLING_OPTS}
- エンドポイント: http://${IP}:8000/v1
- GPU監視: http://${IP}:7681
- サーバログ: http://${IP}:7682"
      ("$NOTIFY_SCRIPT" "$NOTIFY_MSG" || echo "WARNING: Discord通知の送信に失敗しました" >&2) || true
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
