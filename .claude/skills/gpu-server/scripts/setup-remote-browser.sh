#!/bin/bash
#
# setup-remote-browser.sh - GPUサーバにリモートブラウザ(chrome-novnc-cdp)をセットアップ
#
# Usage: ./setup-remote-browser.sh <server>
#   server: mi25, t120h-p100, t120h-m10
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_URL="https://github.com/miminashi/chrome-novnc-cdp.git"

usage() {
    echo "Usage: $0 <server>"
    echo "  server: mi25, t120h-p100, t120h-m10"
    exit 1
}

if [ $# -ne 1 ]; then
    usage
fi

SERVER="$1"

# サーバ確認
case "$SERVER" in
    mi25|t120h-p100|t120h-m10)
        ;;
    *)
        echo "Error: Unknown server '$SERVER'"
        usage
        ;;
esac

echo "=== $SERVER に chrome-novnc-cdp をセットアップ ==="

# 1. Docker確認
echo ""
echo "--- Step 1: Docker 確認 ---"
HAS_DOCKER=$(ssh "$SERVER" "which docker 2>/dev/null || echo 'not_found'")

if [ "$HAS_DOCKER" = "not_found" ]; then
    echo "WARNING: docker が見つかりません"
    echo ""
    echo "Docker のインストールが必要です。"
    echo "以下のコマンドでインストールしてください:"
    echo ""
    echo "  # Dockerインストール"
    echo "  curl -fsSL https://get.docker.com | sudo sh"
    echo "  sudo usermod -aG docker \$USER"
    echo "  # ログアウト＆再ログイン後に使用可能"
    echo ""
    exit 1
else
    echo "docker: $HAS_DOCKER"
fi

# Docker動作確認
echo "Docker動作確認..."
DOCKER_OK=$(ssh "$SERVER" "docker ps >/dev/null 2>&1 && echo 'ok' || echo 'error'")
if [ "$DOCKER_OK" != "ok" ]; then
    echo "WARNING: docker ps が失敗しました"
    echo "以下を確認してください:"
    echo "  - Docker サービスが起動しているか: sudo systemctl start docker"
    echo "  - ユーザーが docker グループに属しているか: sudo usermod -aG docker \$USER"
    exit 1
fi
echo "Docker動作OK"

# 2. chrome-novnc-cdpディレクトリの確認
echo ""
echo "--- Step 2: chrome-novnc-cdp ディレクトリ確認 ---"
HAS_REPO=$(ssh "$SERVER" "test -d ~/chrome-novnc-cdp && echo 'yes' || echo 'no'")

if [ "$HAS_REPO" = "no" ]; then
    echo "chrome-novnc-cdp が存在しません。クローンします..."
    ssh "$SERVER" "git clone $REPO_URL ~/chrome-novnc-cdp"
    echo "クローン完了"
    NEED_PULL=0
else
    echo "chrome-novnc-cdp は既に存在します"

    # 最新版かチェック
    echo "最新版をチェック..."
    ssh "$SERVER" "cd ~/chrome-novnc-cdp && git fetch origin"
    LOCAL=$(ssh "$SERVER" "cd ~/chrome-novnc-cdp && git rev-parse HEAD")
    REMOTE=$(ssh "$SERVER" "cd ~/chrome-novnc-cdp && git rev-parse origin/main 2>/dev/null || git rev-parse origin/master")

    if [ "$LOCAL" != "$REMOTE" ]; then
        echo "更新があります (local: ${LOCAL:0:8}, remote: ${REMOTE:0:8})"
        NEED_PULL=1
    else
        echo "最新版です"
        NEED_PULL=0
    fi
fi

# 3. 更新がある場合はpull
if [ "$NEED_PULL" = "1" ]; then
    echo ""
    echo "--- Step 3: 更新を適用 ---"
    echo "git pull を実行しますか? (y/N)"
    read -r REPLY
    if [ "$REPLY" = "y" ] || [ "$REPLY" = "Y" ]; then
        ssh "$SERVER" "cd ~/chrome-novnc-cdp && git pull"
        echo "更新完了"

        # Dockerイメージの再ビルドが必要
        echo ""
        echo "Dockerイメージを再ビルドしますか? (y/N)"
        read -r REPLY2
        if [ "$REPLY2" = "y" ] || [ "$REPLY2" = "Y" ]; then
            echo "Dockerイメージをビルドします..."
            ssh "$SERVER" "cd ~/chrome-novnc-cdp && docker compose build"
            echo "ビルド完了"
        fi
    fi
fi

# 4. Dockerイメージの確認
echo ""
echo "--- Step 4: Dockerイメージ確認 ---"
HAS_IMAGE=$(ssh "$SERVER" "docker images | grep -q 'chrome-novnc-cdp' && echo 'yes' || echo 'no'")

if [ "$HAS_IMAGE" = "no" ]; then
    echo "Dockerイメージがありません。ビルドします..."
    ssh "$SERVER" "cd ~/chrome-novnc-cdp && docker compose build"
    echo "ビルド完了"
else
    echo "Dockerイメージは存在します"
fi

# 5. コンテナ状態の確認
echo ""
echo "--- Step 5: コンテナ状態確認 ---"
CONTAINER_STATUS=$(ssh "$SERVER" "docker ps --filter 'name=chrome-novnc' --format '{{.Status}}' 2>/dev/null || echo 'not_running'")

if [ -z "$CONTAINER_STATUS" ] || [ "$CONTAINER_STATUS" = "not_running" ]; then
    echo "コンテナは起動していません"
    echo ""
    echo "コンテナを起動しますか? (y/N)"
    read -r REPLY
    if [ "$REPLY" = "y" ] || [ "$REPLY" = "Y" ]; then
        echo "コンテナを起動します..."
        ssh "$SERVER" "cd ~/chrome-novnc-cdp && docker compose up -d"
        echo "起動完了"
        echo "30秒待機中（ブラウザ初期化）..."
        sleep 30
    fi
else
    echo "コンテナ状態: $CONTAINER_STATUS"
fi

# 6. 接続確認
echo ""
echo "--- Step 6: 接続確認 ---"

# IPアドレス取得
IP=$(ssh -G "$SERVER" | grep "^hostname " | awk '{print $2}')

echo "CDP URL: http://$IP:9222"
echo "ブラウザ再起動API: http://$IP:9221"

# CDPヘルスチェック
CDP_OK=$(curl -s --max-time 5 "http://$IP:9222/json/version" >/dev/null 2>&1 && echo 'ok' || echo 'error')
if [ "$CDP_OK" = "ok" ]; then
    echo "CDP接続: OK"
else
    echo "CDP接続: 確認できませんでした（コンテナ未起動の可能性）"
fi

echo ""
echo "=== セットアップ完了 ==="
echo ""
echo "使い方:"
echo "  # コンテナ起動"
echo "  ssh $SERVER 'cd ~/chrome-novnc-cdp && docker compose up -d'"
echo ""
echo "  # コンテナ停止"
echo "  ssh $SERVER 'cd ~/chrome-novnc-cdp && docker compose down'"
echo ""
echo "  # ブラウザ再起動"
echo "  ssh $SERVER 'cd ~/chrome-novnc-cdp && docker compose restart chrome-novnc'"
