#!/bin/bash
set -euo pipefail

# llama.cpp RPC ワーカー (ggml-rpc-server) を GPU サーバ上で起動する。
#
# メインホスト側の llama-server に `--rpc <ip>:<port>` を渡すと、このワーカーが
# 公開する GPU が 1 プロセスから使えるようになる (複数台の VRAM を合算できる)。
#
# セキュリティ: llama.cpp 公式が「RPC サーバは認証が無く安全でない。オープンな
# ネットワークで動かすな」と明記している。そのため既定のバインド先は
# 100GbE 直結セグメント (192.168.100.0/24) のアドレスに限定してあり、
# 0.0.0.0 にはしない。

usage() {
  cat <<'EOF'
Usage: rpc-up.sh [server] [bind-ip] [port]

Arguments:
  server     GPUサーバ名 (省略時: aws-gpu02)
  bind-ip    バインドするIPアドレス (省略時: サーバ既定の 100GbE 側アドレス)
  port       ポート番号 (省略時: 50052)

Environment:
  RPC_DEVICES   公開する GPU を絞る場合に指定 (例: CUDA0,CUDA1)。
                省略時はサーバ上の全 GPU を公開する。
  GGML_RPC_DEBUG=1  ワーカー側のデバッグログを有効化する。
  RPC_CACHE=1   ローカルファイルキャッシュ (-c) を有効化する。ワーカー側
                ~/.cache/llama.cpp/rpc/ に転送済みテンソルを保存し、同じモデルの
                再ロードを速くする。ディスクを食う (aws-gpu02 は空き約 140GB)。

Examples:
  rpc-up.sh                              # aws-gpu02 の全 GPU を 192.168.100.2:50052 で公開
  rpc-up.sh aws-gpu02 192.168.100.2 50052
  RPC_DEVICES=CUDA0,CUDA1 rpc-up.sh      # 2 枚だけ公開
  RPC_CACHE=1 rpc-up.sh                  # 再ロードを速くする (未検証)
EOF
  exit 1
}

case "${1:-}" in
  -h|--help) usage ;;
esac

SERVER="${1:-aws-gpu02}"
BIND_IP="${2:-}"
PORT="${3:-50052}"

# --- サーバ名バリデーション & 既定バインドアドレス ---
case "$SERVER" in
  aws-gpu01) DEFAULT_BIND_IP="192.168.100.1" ;;
  aws-gpu02) DEFAULT_BIND_IP="192.168.100.2" ;;
  mi25|t120h-p100|t120h-m10)
    echo "ERROR: $SERVER には 100GbE 直結セグメントが無いため既定バインド先を持ちません。" >&2
    echo "       bind-ip を明示指定してください。" >&2
    exit 1
    ;;
  *)
    echo "ERROR: 不明なサーバ: $SERVER" >&2
    echo "有効なサーバ: mi25, t120h-p100, t120h-m10, aws-gpu01, aws-gpu02" >&2
    exit 1
    ;;
esac

BIND_IP="${BIND_IP:-$DEFAULT_BIND_IP}"

if [ "$BIND_IP" = "0.0.0.0" ]; then
  echo "ERROR: RPC サーバは認証を持たないため 0.0.0.0 へのバインドは許可しません。" >&2
  echo "       100GbE 直結セグメントのアドレス (192.168.100.x) を指定してください。" >&2
  exit 1
fi

echo "==> $SERVER の既存 ggml-rpc-server を確認中..."
EXISTING=$(ssh -n "$SERVER" "pgrep -f 'bin/(ggml-)?rpc-server'" 2>/dev/null || true)
if [ -n "$EXISTING" ]; then
  echo "WARNING: $SERVER で既に RPC サーバが起動しています (PID: $(echo "$EXISTING" | tr '\n' ' '))。" >&2
  echo "         人間や他のエージェントが使用中の可能性があります。停止する場合は rpc-down.sh $SERVER を実行してください。" >&2
  exit 1
fi

# --- バイナリ名の解決 (新: ggml-rpc-server / 旧: rpc-server) ---
BIN=$(ssh -n "$SERVER" "cd ~/llama.cpp && { [ -x build/bin/ggml-rpc-server ] && echo build/bin/ggml-rpc-server; } || { [ -x build/bin/rpc-server ] && echo build/bin/rpc-server; }" 2>/dev/null || true)
if [ -z "$BIN" ]; then
  echo "ERROR: $SERVER に RPC サーバのバイナリがありません。" >&2
  echo "       -DGGML_RPC=ON を含むビルドが必要です:" >&2
  echo "       scp .claude/skills/llama-server/server-scripts/update_and_build-$SERVER.sh $SERVER:~/llama.cpp/update_and_build.sh" >&2
  echo "       ssh $SERVER 'cd ~/llama.cpp && ./update_and_build.sh --no-pull --force'" >&2
  exit 1
fi

DEVICE_OPT=""
if [ -n "${RPC_DEVICES:-}" ]; then
  DEVICE_OPT="--device $RPC_DEVICES"
fi

DEBUG_ENV=""
if [ "${GGML_RPC_DEBUG:-}" = "1" ]; then
  DEBUG_ENV="GGML_RPC_DEBUG=1 "
fi

# ローカルファイルキャッシュ (-c/--cache)。ワーカー側 ~/.cache/llama.cpp/rpc/ に
# 転送済みテンソルを保存し、次回ロード時の RPC 転送を省く。
# 大きなモデルの再ロードが速くなる代わりにワーカーのディスクを食う
# (aws-gpu02 の空きは約 140GB = 1 モデル分しか入らない)。既定は無効。
CACHE_OPT=""
if [ "${RPC_CACHE:-}" = "1" ]; then
  CACHE_OPT="-c"
  echo "==> ローカルファイルキャッシュを有効化します (RPC_CACHE=1)"
fi

echo "==> $SERVER で $BIN を起動中... ($BIND_IP:$PORT)"
# NOTE: 末尾に `disown` を付けてはいけない。非対話 bash では起動用シェルが終了せず
#       SSH チャネルが開いたままになり、このスクリプトがハングする（実測）。
ssh -n "$SERVER" "cd ~/llama.cpp && setsid nohup env ${DEBUG_ENV}./$BIN -H $BIND_IP -p $PORT $DEVICE_OPT $CACHE_OPT > /tmp/rpc-server.log 2>&1 < /dev/null &" || true

# --- LISTEN 検証 (最大 30 秒) ---
for _ in $(seq 1 30); do
  if ssh -n "$SERVER" "ss -ltn | grep -q ':$PORT '" 2>/dev/null; then
    echo "==> LISTEN を確認しました: $BIND_IP:$PORT"
    echo
    echo "--- 公開デバイス ---"
    ssh -n "$SERVER" "sed -n '/^Devices:/,\$p' /tmp/rpc-server.log" 2>/dev/null || true
    echo
    echo "メインホスト側では --rpc $BIND_IP:$PORT を指定してください。"
    echo "ログ: ssh $SERVER 'tail -f /tmp/rpc-server.log'"
    exit 0
  fi
  sleep 1
done

echo "ERROR: $BIND_IP:$PORT が LISTEN しませんでした。" >&2
ssh -n "$SERVER" "tail -30 /tmp/rpc-server.log" >&2 2>/dev/null || true
exit 1
