#!/bin/bash
# monitor-download.sh - llama.cppモデルダウンロードの進捗を監視
#
# Usage: monitor-download.sh <server> <hf-model>
# Example: monitor-download.sh t120h-p100 "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M"

set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 <server> <hf-model>" >&2
  echo "Example: $0 t120h-p100 \"unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M\"" >&2
  exit 1
fi

SERVER="$1"
HF_MODEL="$2"

# HFモデル名からglobフィルタ用のパターンを生成
# "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M" → "unsloth_Qwen3.5-35B-A3B-GGUF"
FILTER_PATTERN=""
if [ -n "$HF_MODEL" ]; then
  # org/repo:quant → org_repo (colonより前を取り、/を_に変換)
  FILTER_PATTERN=$(echo "$HF_MODEL" | cut -d: -f1 | tr '/' '_')
fi

CACHE_DIR="/home/llm/.cache/llama.cpp"

# サーバ側でループ実行（SSH接続1本）
ssh "$SERVER" bash -s -- "$CACHE_DIR" "$FILTER_PATTERN" <<'REMOTE_SCRIPT'
CACHE_DIR="$1"
FILTER_PATTERN="$2"
PREV=0
PREV_FILE=""

while true; do
  # ダウンロード中ファイルを検索
  TARGET=""
  if [ -n "$FILTER_PATTERN" ]; then
    # HFモデル名でフィルタしてdownloadInProgressを探す
    TARGET=$(ls "$CACHE_DIR"/${FILTER_PATTERN}*.downloadInProgress 2>/dev/null | head -1)
    # なければ完成ファイルを探す
    if [ -z "$TARGET" ]; then
      TARGET=$(ls "$CACHE_DIR"/${FILTER_PATTERN}*.gguf 2>/dev/null | grep -v downloadInProgress | head -1)
    fi
  fi

  # フィルタで見つからなければ全downloadInProgressから探す
  if [ -z "$TARGET" ]; then
    TARGET=$(ls "$CACHE_DIR"/*.downloadInProgress 2>/dev/null | head -1)
  fi

  if [ -z "$TARGET" ]; then
    printf "\r%s Waiting for download to start...    " "$(date +%H:%M:%S)"
    PREV=0
    PREV_FILE=""
    sleep 1
    continue
  fi

  # ファイルが変わったらPREVをリセット
  if [ "$TARGET" != "$PREV_FILE" ]; then
    PREV=0
    PREV_FILE="$TARGET"
  fi

  BYTES=$(stat -c %s "$TARGET" 2>/dev/null || echo "")
  if [ -z "$BYTES" ]; then
    printf "\r%s Waiting for download to start...    " "$(date +%H:%M:%S)"
    PREV=0
    sleep 1
    continue
  fi

  FNAME=$(basename "$TARGET")
  MB=$(awk "BEGIN { printf \"%.2f\", $BYTES / 1048576 }")

  if [ "$PREV" -gt 0 ]; then
    DIFF=$((BYTES - PREV))
    MBPS=$(awk "BEGIN { printf \"%.2f\", $DIFF * 8 / 1048576 }")
    printf "\r%s  %s MB  %s Mbps  %s    " "$(date +%H:%M:%S)" "$MB" "$MBPS" "$FNAME"
  else
    printf "\r%s  %s MB  %s    " "$(date +%H:%M:%S)" "$MB" "$FNAME"
  fi

  # ダウンロード完了検出（.downloadInProgressが消えた）
  if [[ ! "$TARGET" == *.downloadInProgress ]]; then
    echo ""
    echo "Download complete: $FNAME ($MB MB)"
    exit 0
  fi

  PREV=$BYTES
  sleep 1
done
REMOTE_SCRIPT
