#!/bin/bash
# Discord通知スクリプト
# 汎用的な通知をDiscordへ投稿（レポートURL付きも可）

set -e

# 設定
WEBHOOK_URL="https://discord.com/api/webhooks/1479088254216044737/UwpL1bhi1MvBHMNfdo7eR5cuoaHAjUTkutAgNYmyumcPvAK7c3TrSpUHdecqrP0H9uAw"
BASE_URL="http://10.1.6.1:5032/llm-server-ops"
PROJECT_ROOT="/home/ubuntu/projects/llm-server-ops"

# 引数チェック
if [ $# -lt 1 ]; then
    echo "Usage: $0 <summary> [report_path]"
    echo ""
    echo "Arguments:"
    echo "  summary      メッセージ（必須）"
    echo "  report_path  レポートファイルのパス（任意）"
    echo ""
    echo "Examples:"
    echo "  $0 'テスト通知'"
    echo "  $0 'P100で50回テスト、成功率92%' 'report/2026-01-02_test.md'"
    exit 1
fi

SUMMARY="$1"
REPORT_PATH="${2:-}"

# メッセージを構築
if [ -n "$REPORT_PATH" ]; then
    # パスを正規化（絶対パス→相対パスに変換）
    if [[ "$REPORT_PATH" == "$PROJECT_ROOT/"* ]]; then
        RELATIVE_PATH="${REPORT_PATH#$PROJECT_ROOT/}"
    else
        RELATIVE_PATH="$REPORT_PATH"
    fi

    # URLを生成
    REPORT_URL="${BASE_URL}/${RELATIVE_PATH}"

    MESSAGE="**レポート作成**
${SUMMARY}

URL: ${REPORT_URL}"
else
    MESSAGE="${SUMMARY}"
fi

# JSON payloadを作成（jqがない環境でも動くよう手動でエスケープ）
# 改行を\nに、"を\"にエスケープ
ESCAPED_MESSAGE=$(echo "$MESSAGE" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g' | sed ':a;N;$!ba;s/\n/\\n/g')
PAYLOAD="{\"content\": \"${ESCAPED_MESSAGE}\"}"

# Discord webhookに送信
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    "$WEBHOOK_URL")

if [ "$RESPONSE" = "204" ] || [ "$RESPONSE" = "200" ]; then
    echo "Discord通知を送信しました"
    echo "  メッセージ: $SUMMARY"
    if [ -n "$REPORT_PATH" ]; then
        echo "  URL: $REPORT_URL"
    fi
else
    echo "Error: Discord通知の送信に失敗しました (HTTP $RESPONSE)"
    exit 1
fi
