#!/usr/bin/env bash
# aws-gpu01 (メイン) + aws-gpu02 (RPC ワーカー) で llama-server を起動する。
#
# 使い方:
#   launch_server.sh baseline    [ctx]
#   launch_server.sh abliterated [ctx]
#
# 前回セッション (report/2026-08-16_175749_deepseek_v4_rpc_dual_gpu_server.md) と
# 完全に同一のパラメータを使う。ctx は既定 131072、OOM 時のみ引数で下げる。
#
# 注意:
#   * 末尾に `disown` を付けてはいけない (非対話 bash で SSH チャネルがハングする)
#   * 起動完了の検出は "listening on" のみ。
#     "W common_fit_params: ... abort" は正常時にも出る警告なので失敗と誤判定しないこと

set -euo pipefail

LABEL="${1:?usage: launch_server.sh <baseline|abliterated> [ctx]}"
CTX="${2:-131072}"
SERVER="${SERVER:-aws-gpu01}"
RPC="${RPC:-192.168.100.2:50052}"

case "$LABEL" in
  baseline)
    MODEL='~/models/DeepSeek-V4-Flash-0731-GGUF/UD-Q4_K_XL/DeepSeek-V4-Flash-0731-UD-Q4_K_XL-00001-of-00005.gguf'
    ALIAS='DeepSeek-V4-Flash-0731-UD-Q4_K_XL'
    ;;
  abliterated)
    MODEL='~/models/Huihui-DeepSeek-V4-Flash-0731-abliterated-GGUF/DeepSeek-V4-Flash-Q4_K-0731.gguf'
    ALIAS='DeepSeek-V4-Flash-0731-abliterated-Q4_K'
    ;;
  *)
    echo "unknown label: $LABEL" >&2; exit 2 ;;
esac

LOG="/tmp/llama-server-${LABEL}-ctx${CTX}.log"

# [b]in/... 表記は pgrep の自己マッチ (ssh 越しの bash 自身がヒットする) 回避のため
if ssh -n "$SERVER" "pgrep -f '[b]in/llama-server' > /dev/null"; then
  echo "[launch] ERROR: llama-server がすでに稼働中。二重起動は VRAM を食い合うので中止" >&2
  exit 1
fi

echo "[launch] label=$LABEL ctx=$CTX log=$SERVER:$LOG"

ssh -n "$SERVER" "cd ~/llama.cpp && setsid nohup ./build/bin/llama-server \
  --model $MODEL \
  --alias $ALIAS \
  --rpc $RPC \
  --n-gpu-layers 999 --ctx-size $CTX \
  --flash-attn 1 --poll 0 -b 2048 -ub 512 \
  --jinja --temp 1.0 --top-p 1.0 --min-p 0.01 \
  --host 0.0.0.0 --port 8000 \
  > $LOG 2>&1 < /dev/null &"

echo "[launch] started. 完了検出:"
echo "  ssh $SERVER \"grep -E 'listening on|error|out of memory|terminate' $LOG\""
