#!/bin/bash
# c48c4 = SLOT8 (BDF 84:00.0 = GPU[2]) を含む 4 枚同時可視化 + Vulkan + Qwen3-8B Q6_K で
# llama-server を起動するスタンドアロン起動コマンド。
# Fable レビュー D-2 の決定実験: c48c4 個体の SLOT8 位置での fault 抑制 (SA 0/221) が
# 4 枚同時 multi-GPU 負荷でも維持されるかを検証 (4 枚 64GB 常用復帰の前提条件)。
# 元 run-a48e4-slot6.sh の派生 (GGML_VK_VISIBLE_DEVICES を 3→"0,1,2,3" に変更、n-gpu-layers/split-mode は既存踏襲)。
# start.sh の detect_radv_vk_indices() は現在も 4 枚を掴む挙動だが、env と split-mode の一貫性のため
# 本ラッパで start.sh を経由せず ssh で直接 mi25 上に nohup llama-server を投入する。

set -euo pipefail
SERVER=mi25

# 4 枚同時可視化 (0=c3164, 1=448c4, 2=c48c4, 3=a48e4)
# multi-GPU 経路と c48c4 個体を同時に負荷させ、fault 発生率を計測する
GGML_VK_IDX="0,1,2,3"

# モデル指定 (Qwen3-8B Q6_K、D-1 と同一で比較可能性を担保)
HF_REPO="unsloth/Qwen3-8B-GGUF"
HF_QUANT="Q6_K"
ALIAS="${HF_REPO}:${HF_QUANT}"

# ctx-size は 131072 を default (D-1 と同一)。cache q8_0 で 4 枚に十分収まる想定
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
  echo "ERROR: モデルが見つかりません ${HF_REPO}:${HF_QUANT}" >&2
  exit 1
fi
echo "MODEL_PATH=$MODEL_PATH"
echo "CTX_SIZE=$CTX_SIZE"
echo "GGML_VK_VISIBLE_DEVICES=$GGML_VK_IDX (4 枚同時、c48c4=idx2 を含む)"

# llama-server 起動コマンド (start.sh の mi25+vulkan 経路を複製、4 枚 split-mode layer)
LAUNCH_CMD="GGML_VK_VISIBLE_DEVICES=$GGML_VK_IDX ./build-vulkan/bin/llama-server \
  -m '$MODEL_PATH' \
  --jinja --n-gpu-layers 99 --split-mode layer \
  --flash-attn 1 --poll 0 -b 2048 -ub 2048 --n-predict 32768 --threads -1 \
  --ctx-size $CTX_SIZE --parallel 1 --cache-type-k q8_0 --cache-type-v q8_0 \
  --defrag-thold 0.1 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 --presence-penalty 1.0 --dry-multiplier 0 \
  --port 8000 --host 0.0.0.0 \
  --alias '$ALIAS'"

echo "==> llama-server 起動 (c48c4 SLOT8 4-card Vulkan ctx=$CTX_SIZE)"
ssh -f "$SERVER" "cd ~/llama.cpp && nohup bash -c \"$LAUNCH_CMD\" > /tmp/llama-server.log 2>&1 < /dev/null &" </dev/null >/dev/null 2>&1

# /health 確認待機 (最大 300s、4 枚 init が単独より遅い可能性あり)
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
