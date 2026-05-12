#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SKILL_DIR")")")"

# .envからHF_TOKENを読み込み（プロジェクトルート → ~/.config/gpu-server/.env の順）
ENV_FILE=""
if [ -f "$PROJECT_ROOT/.env" ]; then
  ENV_FILE="$PROJECT_ROOT/.env"
elif [ -f "${LLM_SERVER_ENV:-${HOME}/.config/gpu-server/.env}" ]; then
  ENV_FILE="${LLM_SERVER_ENV:-${HOME}/.config/gpu-server/.env}"
fi
if [ -n "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

# HF_TOKENが未設定の場合、対話的にセットアップ
if [ -z "${HF_TOKEN:-}" ]; then
  if [ -t 0 ]; then
    echo "==> HF_TOKEN が設定されていません。HuggingFace トークンを入力してください。"
    echo "    トークンは https://huggingface.co/settings/tokens で取得できます。"
    while true; do
      read -rp "HF_TOKEN: " HF_TOKEN_INPUT
      # CR・前後空白を除去（ペースト時の不可視文字対策）
      HF_TOKEN_INPUT="${HF_TOKEN_INPUT%$'\r'}"
      HF_TOKEN_INPUT="${HF_TOKEN_INPUT#"${HF_TOKEN_INPUT%%[![:space:]]*}"}"
      HF_TOKEN_INPUT="${HF_TOKEN_INPUT%"${HF_TOKEN_INPUT##*[![:space:]]}"}"
      if [ -z "$HF_TOKEN_INPUT" ]; then
        echo "    スキップします（認証なしでダウンロードを試みます）"
        break
      fi
      # トークンの有効性を検証
      RESPONSE=$(curl -sS -w '\n%{http_code}' \
        -H "Authorization: Bearer $HF_TOKEN_INPUT" \
        https://huggingface.co/api/whoami-v2)
      HTTP_CODE=$(echo "$RESPONSE" | tail -1)
      if [ "$HTTP_CODE" = "200" ]; then
        echo "    トークンは有効です。保存します..."
        HF_TOKEN="$HF_TOKEN_INPUT"
        # 永続化先を決定
        SAVE_TARGET=""
        if [ -n "$ENV_FILE" ]; then
          SAVE_TARGET="$ENV_FILE"
        elif [ -f "$PROJECT_ROOT/.env" ]; then
          SAVE_TARGET="$PROJECT_ROOT/.env"
        else
          SAVE_TARGET="${HOME}/.config/gpu-server/.env"
          mkdir -p "${HOME}/.config/gpu-server"
        fi
        echo "HF_TOKEN=$HF_TOKEN" >> "$SAVE_TARGET"
        chmod 600 "$SAVE_TARGET"
        echo "    保存完了: $SAVE_TARGET"
        break
      else
        BODY=$(echo "$RESPONSE" | sed '$d')
        echo "    トークンが無効です（HTTP $HTTP_CODE: $BODY）。再入力してください（空入力でスキップ）。"
      fi
    done
  else
    echo "WARNING: HF_TOKEN が未設定です。認証が必要なモデルのダウンロードは失敗する可能性があります。" >&2
  fi
fi

usage() {
  cat <<'EOF'
Usage: start.sh <server> <hf-model> [ctx-size|fit] [fit-ctx]

Arguments:
  server     GPUサーバ名 (mi25, t120h-p100, t120h-m10)
  hf-model   HuggingFaceモデル (例: unsloth/gpt-oss-20b-GGUF:Q8_0)
  ctx-size   コンテキストサイズ or "fit" (省略時: 65536)
  fit-ctx    fitモード時のctx-size ("fit"指定時のみ有効)
             - Qwen3.5-122B-A10B: 省略時 131072 (Phase U-6 確定 128k default)
             - その他 MoE       : 省略時 8192

Examples:
  start.sh t120h-p100 "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M" 131072
  start.sh mi25 "unsloth/gpt-oss-20b-GGUF:Q8_0"
  start.sh t120h-p100 "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit         # 128k default
  start.sh t120h-p100 "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit 32768   # 短 ctx 指定
EOF
  exit 1
}

# --- 引数チェック ---
if [ $# -lt 1 ]; then
  usage
fi

SERVER="$1"
HF_MODEL="${2:-}"
CTX_SIZE_ARG="${3:-65536}"
FIT_CTX_ARG="${4:-}"

# fitモード判定
if [ "$CTX_SIZE_ARG" = "fit" ]; then
  FIT_MODE=true
  CTX_SIZE="fit"
else
  FIT_MODE=false
  CTX_SIZE="$CTX_SIZE_ARG"
fi

if [ -z "$HF_MODEL" ]; then
  echo "ERROR: モデルが指定されていません。" >&2
  echo "Claude側で AskUserQuestion を使ってモデルを選択してください。" >&2
  exit 1
fi

# --- モデルプロファイル判定 ---
# Phase U-6 (2026-04-24) で確定した Qwen3.5-122B-A10B 向け ctx=128k 専用 default 構成を
# モデル名で自動適用する。他モデルは従来挙動。
MODEL_PROFILE="generic"
case "$HF_MODEL" in
  *Qwen3.5-122B-A10B*)
    MODEL_PROFILE="qwen3_122b"
    ;;
esac

# fit 時の ctx-size default はプロファイル依存 (qwen3_122b: 131072、その他: 8192)
if [ -z "$FIT_CTX_ARG" ]; then
  if [ "$MODEL_PROFILE" = "qwen3_122b" ]; then
    FIT_CTX=131072
  else
    FIT_CTX=8192
  fi
else
  FIT_CTX="$FIT_CTX_ARG"
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
EXISTING=$(ssh "$SERVER" "pgrep -a -f './build/bin/llama-server'" || true)
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
THREADS_OPT="--threads -1"

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

# --- モデルプロファイル上書き (サーバ別 default を上書き) ---
# Phase U-6 (2026-04-24) 確定構成: Qwen3.5-122B-A10B × t120h-p100 × ctx=128k
# -b 2048 / -ub 512 / tensor-split 11,12,13,14 / threads 40 / numactl node1
if [ "$MODEL_PROFILE" = "qwen3_122b" ] && [ "$SERVER" = "t120h-p100" ]; then
  SERVER_OPTS="--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14"
  ENV_PREFIX="numactl --cpunodebind=1 --membind=1"
  THREADS_OPT="--threads 40"
fi

# --- モデル別サンプリングパラメータ ---
case "$HF_MODEL" in
  *Qwen3.5*)
    SAMPLING_OPTS="--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0"
    ;;
  *)
    SAMPLING_OPTS="--temp 1.0 --top-p 1.0 --top-k 0"
    ;;
esac

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
MODEL_PATH=$(ssh "$SERVER" "find ~/.cache/huggingface/hub/models--${HF_REPO//\//--}/ -name '*${HF_QUANT}*.gguf' -not -name '*.incomplete' 2>/dev/null | sort | head -1" || true)

if [ -n "$MODEL_PATH" ]; then
  echo "    ローカルキャッシュを使用: $MODEL_PATH"
else
  echo "    ローカルキャッシュなし、huggingface-cli でダウンロードします"
  HF_TOKEN_OPT="${HF_TOKEN:+--token $HF_TOKEN}"
  ssh "$SERVER" "/home/llm/.local/bin/hf download '$HF_REPO' --include '*${HF_QUANT}*.gguf' $HF_TOKEN_OPT"
  # ダウンロード後にキャッシュからパスを再取得
  MODEL_PATH=$(ssh "$SERVER" "find ~/.cache/huggingface/hub/models--${HF_REPO//\//--}/ -name '*${HF_QUANT}*.gguf' -not -name '*.incomplete' 2>/dev/null | sort | head -1")
  if [ -z "$MODEL_PATH" ]; then
    echo "ERROR: ダウンロード後もGGUFファイルが見つかりません" >&2
    exit 1
  fi
  echo "    ダウンロード完了: $MODEL_PATH"
fi
MODEL_OPT="-m '$MODEL_PATH'"

# --- fitモード分岐 ---
if [ "$FIT_MODE" = true ]; then
  if [ "$MODEL_PROFILE" = "qwen3_122b" ]; then
    # Phase U-6 確定 OT=B14b: CPU offload = layer {2,3,20-23,31-38}、他は GPU
    # llama.cpp の -ot はカンマ区切りで複数パターンを OR 合成できる (parse_tensor_buffer_overrides)。
    # 単一 regex の `(|)` は bash のメタキャラで outer ssh パイプラインを通らないため使えない。
    OT_PATTERNS=""
    for L in 2 3 20 21 22 23 31 32 33 34 35 36 37 38; do
      [ -n "$OT_PATTERNS" ] && OT_PATTERNS+=","
      OT_PATTERNS+="blk.$L.ffn_.*_exps.weight=CPU"
    done
    NGL_OPTS="-ngl 999 --split-mode layer -ot '$OT_PATTERNS'"
  else
    NGL_OPTS="-ngl 999 -ot 'ffn_.*_exps.weight=CPU'"
  fi
  CTX_OPTS="--ctx-size $FIT_CTX"
else
  NGL_OPTS="--n-gpu-layers 99 --split-mode layer"
  CTX_OPTS="--ctx-size $CTX_SIZE"
fi

# --- llama-server 起動 ---
echo "==> llama-server を $SERVER で起動中..."
echo "    モデル: $HF_MODEL"
if [ "$FIT_MODE" = true ]; then
  echo "    モード: fit (MoE CPUオフロード, ctx-size: $FIT_CTX)"
else
  echo "    ctx-size: $CTX_SIZE"
fi

LAUNCH_CMD="${ENV_PREFIX:+$ENV_PREFIX }./build/bin/llama-server \
  $MODEL_OPT \
  $CHAT_TEMPLATE_OPTS $NGL_OPTS \
  $SERVER_OPTS --n-predict 32768 $THREADS_OPT \
  $CTX_OPTS --parallel 1 --cache-type-k q8_0 --cache-type-v q8_0 \
  --defrag-thold 0.1 $SAMPLING_OPTS \
  --port 8000 --host 0.0.0.0 \
  --alias '$ALIAS'"

# llama-serverをサーバ側でバックグラウンド起動し、ttydでログ閲覧UIを提供
ssh "$SERVER" "ps aux | grep '[t]tyd --port 7682' | awk '{print \$2}' | xargs -r kill 2>/dev/null || true"

# llama-serverをバックグラウンド起動（ssh -fでSSHを即座に返す）
# ローカル側 fd を /dev/null に向け、tee 等のパイプライン下でハングしないようにする
ssh -f "$SERVER" "cd ~/llama.cpp && nohup bash -c '$LAUNCH_CMD' > /tmp/llama-server.log 2>&1 < /dev/null &" </dev/null >/dev/null 2>&1

# ttydでログ閲覧用UIを起動
ssh -f "$SERVER" "nohup ttyd --port 7682 --writable bash -c 'tail -f /tmp/llama-server.log' > /dev/null 2>&1 < /dev/null &" </dev/null >/dev/null 2>&1

# 既存nvtopプロセスを停止してttydでnvtop監視UIを起動
ssh "$SERVER" "pkill nvtop 2>/dev/null || true"
ssh -f "$SERVER" "nohup ttyd --port 7681 nvtop > /dev/null 2>&1 < /dev/null &" </dev/null >/dev/null 2>&1

echo "==> llama-server をバックグラウンドで起動しました"
echo "    ログ: ssh $SERVER 'tail -f /tmp/llama-server.log'"
echo "    ブラウザ: http://$SERVER:7682"
echo "    GPU監視: http://$SERVER:7681"
