#!/bin/bash
# llama-server 起動統合スクリプト
#
# 電源確認 → 電源 ON + SSH 疎通待機 → ヘルスチェック（既起動なら冪等スキップ）
# → start.sh → wait-ready.sh を 1 コマンドで実行する薄いラッパー。
#
# 使い方:
#   llama-up.sh [server] [hf-model] [mode] [fit-ctx]
#
# 引数（すべて省略可）:
#   server    GPUサーバ名               (デフォルト: t120h-p100)
#   hf-model  HuggingFaceモデル          (デフォルト: unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M)
#   mode      ctx-size or "fit"          (デフォルト: fit)
#   fit-ctx   fit時のctx-size            (デフォルト: 空 → start.sh のプロファイル既定に委譲)
#
# 例:
#   .claude/skills/llama-server/scripts/llama-up.sh
#   .claude/skills/llama-server/scripts/llama-up.sh t120h-p100 "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M" 8192
#
# ロック取得は行わない（必要なら事前に gpu-server/scripts/lock.sh を実行）。
# 終了コード: 0=成功 / 1=エラー。
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
GPU_SCRIPTS_DIR="$(cd "$SKILL_DIR/../gpu-server/scripts" && pwd)"

SERVER="${1:-t120h-p100}"
HF_MODEL="${2:-unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M}"
MODE="${3:-fit}"
FIT_CTX="${4:-}"

# --- Step 1: 電源状態確認 ---
echo "==> [1/4] $SERVER の電源状態を確認中..."
POWER_OUT=$("$GPU_SCRIPTS_DIR/power.sh" "$SERVER" status)
echo "$POWER_OUT"
POWER_STATE=$(echo "$POWER_OUT" | grep -oE 'On|Off' | tail -1)
if [ -z "$POWER_STATE" ]; then
  echo "ERROR: 電源状態を判定できませんでした" >&2
  exit 1
fi

# --- Step 2: 電源OFFなら起動 + SSH疎通待機 ---
if [ "$POWER_STATE" = "Off" ]; then
  echo "==> [2/4] 電源を ON にします..."
  "$GPU_SCRIPTS_DIR/power.sh" "$SERVER" on

  echo "==> SSH 疎通を待機中（最大 5 分）..."
  SSH_READY=false
  for i in $(seq 1 60); do
    if ssh -o ConnectTimeout=5 -o BatchMode=yes "$SERVER" true 2>/dev/null; then
      echo "    [$i/60] SSH 接続成功"
      SSH_READY=true
      break
    fi
    echo "    [$i/60] 待機中..."
    sleep 5
  done
  if [ "$SSH_READY" != true ]; then
    echo "ERROR: SSH 疎通タイムアウト（5 分）。OS が起動していない可能性があります。" >&2
    exit 1
  fi
else
  echo "==> [2/4] 電源は既に ON です。スキップ。"
fi

# --- Step 3: ヘルスチェック（既起動判定） ---
echo "==> [3/4] llama-server の起動状態を確認中..."
IP=$(ssh -G "$SERVER" | grep '^hostname ' | awk '{print $2}')
if [ -z "$IP" ]; then
  echo "ERROR: $SERVER の IP を ssh -G で解決できませんでした" >&2
  exit 1
fi
if curl -sf -m 5 "http://${IP}:8000/health" >/dev/null 2>&1; then
  echo "    llama-server は既に起動しています (http://${IP}:8000/health → 200)"
  echo "==> 完了（冪等スキップ）"
  exit 0
fi
echo "    /health 応答なし。起動を開始します。"

# --- Step 4: start.sh + wait-ready.sh ---
echo "==> [4/4] llama-server を起動中..."
# FIT_CTX が空のときは quote なしで完全省略させる（start.sh / wait-ready.sh の既定値に委譲）
"$SCRIPT_DIR/start.sh" "$SERVER" "$HF_MODEL" "$MODE" $FIT_CTX
"$SCRIPT_DIR/wait-ready.sh" "$SERVER" "$HF_MODEL" "$MODE" $FIT_CTX
echo "==> 起動完了"
