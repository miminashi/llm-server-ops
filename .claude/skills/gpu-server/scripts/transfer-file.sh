#!/bin/bash
#
# transfer-file.sh - GPUサーバ間でファイルを転送
#
# Usage: ./transfer-file.sh <src-server> <src-path> <dst-server> <dst-path>
#
# 転送元でPython HTTPサーバを起動し、転送先からcurlでダウンロード
#

set -e

usage() {
    echo "Usage: $0 <src-server> <src-path> <dst-server> <dst-path>"
    echo ""
    echo "Arguments:"
    echo "  src-server  転送元サーバ (mi25, t120h-p100, t120h-m10)"
    echo "  src-path    転送元ファイルパス（絶対パスまたは~からの相対パス）"
    echo "  dst-server  転送先サーバ (mi25, t120h-p100, t120h-m10)"
    echo "  dst-path    転送先ファイルパス（絶対パスまたは~からの相対パス）"
    echo ""
    echo "Example:"
    echo "  $0 t120h-p100 ~/models/model.gguf t120h-m10 ~/models/model.gguf"
    exit 1
}

if [ $# -ne 4 ]; then
    usage
fi

SRC_SERVER="$1"
SRC_PATH="$2"
DST_SERVER="$3"
DST_PATH="$4"

# サーバ確認
for server in "$SRC_SERVER" "$DST_SERVER"; do
    case "$server" in
        mi25|t120h-p100|t120h-m10)
            ;;
        *)
            echo "Error: Unknown server '$server'"
            usage
            ;;
    esac
done

if [ "$SRC_SERVER" = "$DST_SERVER" ]; then
    echo "Error: 転送元と転送先が同じサーバです"
    exit 1
fi

# 転送元サーバのIPアドレス取得
SRC_IP=$(ssh -G "$SRC_SERVER" | grep "^hostname " | awk '{print $2}')
echo "転送元: $SRC_SERVER ($SRC_IP)"
echo "転送先: $DST_SERVER"

# 転送元ファイルの確認
echo ""
echo "--- ファイル確認 ---"
FILE_INFO=$(ssh -n -T "$SRC_SERVER" "ls -lh $SRC_PATH 2>/dev/null" || echo "NOT_FOUND")
if [ "$FILE_INFO" = "NOT_FOUND" ]; then
    echo "Error: 転送元ファイルが見つかりません: $SRC_PATH"
    exit 1
fi
echo "転送元: $FILE_INFO"

# ファイルサイズ取得
FILE_SIZE=$(ssh -n -T "$SRC_SERVER" "stat -c%s $SRC_PATH")
FILE_SIZE_HUMAN=$(ssh -n -T "$SRC_SERVER" "ls -lh $SRC_PATH | awk '{print \$5}'")
FILENAME=$(basename "$SRC_PATH")
DIRNAME=$(ssh -n -T "$SRC_SERVER" "dirname $SRC_PATH")

echo "ファイル名: $FILENAME"
echo "サイズ: $FILE_SIZE_HUMAN ($FILE_SIZE bytes)"

# 使用するポート（8888-8899の空きポートを探す）
PORT=8888
while ssh -n -T "$SRC_SERVER" "ss -tlnp | grep -q :$PORT" 2>/dev/null; do
    PORT=$((PORT + 1))
    if [ $PORT -gt 8899 ]; then
        echo "Error: 利用可能なポートが見つかりません (8888-8899)"
        exit 1
    fi
done
echo "使用ポート: $PORT"

# 転送先ディレクトリの作成
DST_DIR=$(dirname "$DST_PATH")
echo ""
echo "--- 転送先準備 ---"
ssh -n -T "$DST_SERVER" "mkdir -p $DST_DIR"
echo "転送先ディレクトリ: $DST_DIR"

# 転送元でHTTPサーバを起動
echo ""
echo "--- HTTPサーバ起動 ---"

# リモートでHTTPサーバをバックグラウンド起動（setsidで新セッションとして起動）
ssh -n -T "$SRC_SERVER" "setsid python3 -m http.server $PORT --directory $DIRNAME > /tmp/http_server_$PORT.log 2>&1 < /dev/null &"

# サーバ起動を待機（最大10秒）
echo -n "起動待機中..."
for i in $(seq 1 10); do
    sleep 1
    if ssh -n -T "$SRC_SERVER" "ss -tlnp 2>/dev/null | grep -q ':$PORT '" 2>/dev/null; then
        echo " OK"
        break
    fi
    echo -n "."
    if [ $i -eq 10 ]; then
        echo " 失敗"
        echo "Error: HTTPサーバの起動に失敗しました"
        ssh -n -T "$SRC_SERVER" "cat /tmp/http_server_$PORT.log" 2>/dev/null || true
        exit 1
    fi
done

# HTTPサーバのPID確認（情報表示用）
HTTP_PID=$(ssh -n -T "$SRC_SERVER" "pgrep -f 'python3 -m http.server $PORT' | head -1" 2>/dev/null || echo "unknown")
echo "HTTPサーバ起動 (PID: $HTTP_PID, ポート: $PORT)"

# クリーンアップ関数
cleanup() {
    set +e  # エラーで終了しないように
    echo ""
    echo "--- クリーンアップ ---"
    # setsidで起動したプロセスを終了
    ssh -n -T -o BatchMode=yes "$SRC_SERVER" "pkill -f 'python3 -m http.server $PORT'" 2>/dev/null
    echo "HTTPサーバ停止"
}
trap cleanup EXIT

# 転送実行
echo ""
echo "--- 転送開始 ---"
DOWNLOAD_URL="http://$SRC_IP:$PORT/$FILENAME"
echo "URL: $DOWNLOAD_URL"

# プログレス表示付きでダウンロード
ssh -n -T "$DST_SERVER" "curl -# -o $DST_PATH '$DOWNLOAD_URL'"

# 転送確認
echo ""
echo "--- 転送確認 ---"
DST_FILE_INFO=$(ssh -n -T "$DST_SERVER" "ls -lh $DST_PATH 2>/dev/null" || echo "NOT_FOUND")
if [ "$DST_FILE_INFO" = "NOT_FOUND" ]; then
    echo "Error: 転送に失敗しました"
    exit 1
fi
echo "転送先: $DST_FILE_INFO"

# サイズ確認
DST_SIZE=$(ssh -n -T "$DST_SERVER" "stat -c%s $DST_PATH")
if [ "$FILE_SIZE" != "$DST_SIZE" ]; then
    echo "Warning: ファイルサイズが一致しません (src: $FILE_SIZE, dst: $DST_SIZE)"
    exit 1
fi

echo ""
echo "=== 転送完了 ==="
echo "  $SRC_SERVER:$SRC_PATH"
echo "  → $DST_SERVER:$DST_PATH"
echo "  サイズ: $FILE_SIZE_HUMAN"
