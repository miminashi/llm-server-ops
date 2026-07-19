#!/bin/bash
# a48e4 単独可視化 + Vulkan + Qwen3-8B Q6_K で llama-server を起動するスタンドアロン起動コマンド。
# Fable レビュー D-1 の決定実験: 健全カード×SLOT6 で fault が出るかを検証 (SLOT6 環境起因 vs c48c4 個体起因)。
# 元 run-c48c4-slot8.sh の派生 (Vulkan idx を 2→3 に変更)。
# start.sh の detect_radv_vk_indices() が GGML_VK_VISIBLE_DEVICES を 4枚に上書きしてしまうため、
# このスクリプトは start.sh を経由せず ssh で直接 mi25 上に nohup llama-server を投入する。

set -euo pipefail
SERVER=mi25

# a48e4 = SLOT6 (BDF 87:00.0) = GPU[3] = Vulkan idx 3 のみ可視化 (multi-GPU 経路を排除)
GGML_VK_IDX="3"

# モデル指定 (Qwen3-8B Q6_K)
HF_REPO="unsloth/Qwen3-8B-GGUF"
HF_QUANT="Q6_K"
ALIAS="${HF_REPO}:${HF_QUANT}"

# Step 4 で限界探索した値を env で渡す。default は 131072 (要 smoke test 検証)。
CTX_SIZE="${CTX_SIZE:-131072}"

# 既存 llama-server プロセス確認 (重複起動回避)
EXISTING=$(ssh "$SERVER" "pgrep -a -f 'bin/llama-server'" || true)
if [ -n "$EXISTING" ]; then
  echo "WARNING: llama-server が既に起動中:" >&2
  echo "$EXISTING" >&2
  exit 1
fi

# Vulkan ビルド存在確認
ssh "$SERVER" "test -x ~/llama.cpp/build-vulkan/bin/llama-server" || {
  echo "ERROR: build-vulkan/bin/llama-server が存在しません" >&2
  exit 1
}

# モデルパス解決: ~/models/ (wget DL 先) を最優先、なければ HF cache を fallback
MODEL_PATH=$(ssh "$SERVER" "find ~/models/ -name '*${HF_QUANT}*.gguf' -not -name '*.incomplete' 2>/dev/null | sort | head -1" || true)
if [ -z "$MODEL_PATH" ]; then
  MODEL_PATH=$(ssh "$SERVER" "find ~/.cache/huggingface/hub/models--${HF_REPO//\//--}/ -name '*${HF_QUANT}*.gguf' -not -name '*.incomplete' 2>/dev/null | sort | head -1" || true)
fi
if [ -z "$MODEL_PATH" ]; then
  echo "ERROR: モデルが見つかりません ${HF_REPO}:${HF_QUANT}。先に Step 3 でダウンロードしてください" >&2
  exit 1
fi
echo "MODEL_PATH=$MODEL_PATH"
echo "CTX_SIZE=$CTX_SIZE"

# llama-server 起動コマンド (start.sh の mi25+vulkan 経路を複製)
# - --flash-attn 1 --poll 0 -b 2048 -ub 2048 (mi25 gfx900 最適)
# - --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 --presence-penalty 1.0 --dry-multiplier 0 (Qwen3 系)
# - --n-gpu-layers 99 --split-mode layer (単独でも一応指定)
# - --cache-type-k q8_0 --cache-type-v q8_0 (VRAM 節約 + FA q8_0 安定)
LAUNCH_CMD="GGML_VK_VISIBLE_DEVICES=$GGML_VK_IDX ./build-vulkan/bin/llama-server \
  -m '$MODEL_PATH' \
  --jinja --n-gpu-layers 99 --split-mode layer \
  --flash-attn 1 --poll 0 -b 2048 -ub 2048 --n-predict 32768 --threads -1 \
  --ctx-size $CTX_SIZE --parallel 1 --cache-type-k q8_0 --cache-type-v q8_0 \
  --defrag-thold 0.1 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 --presence-penalty 1.0 --dry-multiplier 0 \
  --port 8000 --host 0.0.0.0 \
  --alias '$ALIAS'"

echo "==> llama-server 起動 (a48e4 SLOT6 stand-alone Vulkan ctx=$CTX_SIZE)"
ssh -f "$SERVER" "cd ~/llama.cpp && nohup bash -c \"$LAUNCH_CMD\" > /tmp/llama-server.log 2>&1 < /dev/null &" </dev/null >/dev/null 2>&1

# /health 確認待機 (最大 300s)
echo "==> /health 確認待機 (最大 300s)"
for i in $(seq 1 60); do
  if curl -sf -m 5 http://10.1.4.13:8000/health >/dev/null 2>&1; then
    echo "    /health OK (elapsed $((i*5))s)"
    exit 0
  fi
  sleep 5
done

echo "ERROR: /health に応答せず 300s 経過" >&2
exit 1
