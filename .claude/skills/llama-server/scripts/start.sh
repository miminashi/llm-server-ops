#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

usage() {
  cat <<'EOF'
Usage: start.sh <server> <hf-model> [ctx-size]

Arguments:
  server     GPUサーバ名 (mi25, t120h-p100, t120h-m10)
  hf-model   HuggingFaceモデル (例: unsloth/gpt-oss-20b-GGUF:Q8_0)
  ctx-size   コンテキストサイズ (省略時: 65536)

Examples:
  start.sh t120h-p100 "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M" 131072
  start.sh mi25 "unsloth/gpt-oss-20b-GGUF:Q8_0"
EOF
  exit 1
}

# --- 引数チェック ---
if [ $# -lt 1 ]; then
  usage
fi

SERVER="$1"
HF_MODEL="${2:-}"
CTX_SIZE="${3:-65536}"

if [ -z "$HF_MODEL" ]; then
  echo "ERROR: モデルが指定されていません。" >&2
  echo "Claude側で AskUserQuestion を使ってモデルを選択してください。" >&2
  exit 1
fi

# --- サーバ名バリデーション ---
case "$SERVER" in
  mi25|t120h-p100|t120h-m10) ;;
  *)
    echo "ERROR: 不明なサーバ: $SERVER" >&2
    echo "有効なサーバ: mi25, t120h-p100, t120h-m10" >&2
    exit 1
    ;;
esac

# --- 既存プロセス確認 ---
echo "==> $SERVER の既存 llama-server プロセスを確認中..."
EXISTING=$(ssh "$SERVER" "ps aux | grep '[l]lama-server'" || true)
if [ -n "$EXISTING" ]; then
  echo "WARNING: $SERVER で llama-server が既に起動中です:" >&2
  echo "$EXISTING" >&2
  echo "" >&2
  echo "既存プロセスを終了してから再実行してください。" >&2
  exit 1
fi

# --- ビルドスクリプト転送・実行 ---
BUILD_SCRIPT="$SKILL_DIR/server-scripts/update_and_build-${SERVER}.sh"
if [ ! -f "$BUILD_SCRIPT" ]; then
  echo "ERROR: ビルドスクリプトが見つかりません: $BUILD_SCRIPT" >&2
  exit 1
fi

echo "==> ビルドスクリプトを $SERVER に転送中..."
scp -q "$BUILD_SCRIPT" "${SERVER}:~/llama.cpp/update_and_build.sh"
ssh "$SERVER" "chmod +x ~/llama.cpp/update_and_build.sh"

echo "==> llama.cpp を更新・ビルド中..."
ssh "$SERVER" "cd ~/llama.cpp && ./update_and_build.sh"

# --- サーバ別パラメータ設定 ---
SERVER_OPTS=""
ENV_PREFIX=""

case "$SERVER" in
  mi25)
    SERVER_OPTS="-b 4096 -ub 4096"
    ;;
  t120h-p100)
    SERVER_OPTS="--flash-attn 1 --poll 0 -b 8192 -ub 8192"
    ;;
  t120h-m10)
    ENV_PREFIX="CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14"
    SERVER_OPTS="-b 4096 -ub 4096"
    ;;
esac

# --- サンプリングパラメータ（デフォルト） ---
SAMPLING_OPTS="--temp 1.0 --top-p 1.0 --top-k 0"

# --- チャットテンプレートオプション ---
CHAT_TEMPLATE_OPTS="--jinja"

# --- エイリアス ---
ALIAS="$HF_MODEL"

# --- モデルパス解決 ---
# HF_MODEL形式: "org/repo:quantization" (例: "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M")
# huggingface-cliキャッシュからローカルパスを探し、なければ-hfでダウンロード
HF_REPO="${HF_MODEL%%:*}"    # org/repo部分
HF_QUANT="${HF_MODEL##*:}"   # quantization部分

echo "==> $SERVER でモデルのローカルキャッシュを確認中..."
# huggingface-cliのキャッシュからGGUFファイルを検索
MODEL_PATH=$(ssh "$SERVER" "find ~/.cache/huggingface/hub/models--${HF_REPO//\//--}/ -name '*${HF_QUANT}*.gguf' -not -name '*.incomplete' 2>/dev/null | head -1" || true)

if [ -n "$MODEL_PATH" ]; then
  echo "    ローカルキャッシュを使用: $MODEL_PATH"
  MODEL_OPT="-m '$MODEL_PATH'"
else
  echo "    ローカルキャッシュなし、-hf でダウンロードします"
  MODEL_OPT="-hf '$HF_MODEL'"
fi

# --- llama-server 起動 ---
echo "==> llama-server を $SERVER で起動中..."
echo "    モデル: $HF_MODEL"
echo "    ctx-size: $CTX_SIZE"

LAUNCH_CMD="${ENV_PREFIX:+$ENV_PREFIX }./build/bin/llama-server \
  $MODEL_OPT \
  $CHAT_TEMPLATE_OPTS --n-gpu-layers 99 --split-mode layer \
  $SERVER_OPTS --n-predict 32768 --threads -1 \
  --ctx-size $CTX_SIZE --cache-type-k q8_0 --cache-type-v q8_0 \
  --defrag-thold 0.1 $SAMPLING_OPTS \
  --port 8000 --host 0.0.0.0 \
  --alias '$ALIAS'"

# llama-serverをサーバ側でバックグラウンド起動し、ttydでログ閲覧UIを提供
ssh "$SERVER" "ps aux | grep '[t]tyd --port 7682' | awk '{print \$2}' | xargs -r kill 2>/dev/null || true"

# llama-serverをバックグラウンド起動（ssh -fでSSHを即座に返す）
ssh -f "$SERVER" "cd ~/llama.cpp && nohup bash -c '$LAUNCH_CMD' > /tmp/llama-server.log 2>&1 < /dev/null &"

# ttydでログ閲覧用UIを起動
ssh -f "$SERVER" "nohup ttyd --port 7682 --writable bash -c 'tail -f /tmp/llama-server.log' > /dev/null 2>&1 < /dev/null &"

echo "==> llama-server をバックグラウンドで起動しました"
echo "    ログ: ssh $SERVER 'tail -f /tmp/llama-server.log'"
echo "    ブラウザ: http://$SERVER:7682"
