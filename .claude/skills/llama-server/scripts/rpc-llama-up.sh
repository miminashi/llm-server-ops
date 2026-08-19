#!/usr/bin/env bash
#
# RPC 分散構成 (aws-gpu01 メイン + aws-gpu02 ワーカー) で llama-server を起動する。
#
# start.sh は RPC 未対応なので、RPC 構成ではこちらを使う。
# rpc-server (ggml-rpc-server) は事前に rpc-up.sh で起動しておくこと。
#
# 使い方:
#   rpc-llama-up.sh [model-path] [ctx-size]
#
#   model-path : メインホスト上のパス。省略時は下記のデフォルト構成のモデル。
#                ~ 展開されるようクォートせずに渡される。
#                分割 GGUF は第 1 shard を指定すれば残りは自動で読まれる。
#   ctx-size   : 省略時 131072
#
# 環境変数:
#   SERVER            メインホスト (既定 aws-gpu01)
#   RPC               ワーカーの host:port (既定 192.168.100.2:50052)
#   ALIAS             --alias に渡す名前 (既定はモデルファイルの basename から生成)
#   SAMPLING_OPTS     サンプリング指定 (既定は下記。空文字を渡せば llama.cpp 既定に戻る)
#   EXTRA_LLAMA_OPTS  追加フラグ (既定オプションの後ろに置かれるので上書きできる)
#   WAIT_SECS         起動完了を待つ秒数 (既定 2400。144 GiB 級は cold で 15 分超かかる)
#   NO_WAIT=1         起動だけして待たない
#
# デフォルト構成 (aws-gpu01 + aws-gpu02 の標準構成、2026-08-18 制定):
#   モデル       : Huihui-DeepSeek-V4-Flash-0731-abliterated (Q4_K, 153.3 GiB)
#   ctx          : 131072
#   サンプリング : unsloth 公式値 --temp 1.0 --top-p 1.0 --min-p 0.01
#   ctx=131072 で起動できることを 2026-08-16 に実測済み (最小空き 460 MiB)。
#   これより大きいモデルを同じ設定で載せる余地は無い。
#
# 実績パラメータ (2026-08-16 / 2026-08-17):
#   --flash-attn 1 --poll 0 -b 2048 -ub 512 --n-gpu-layers 999
#   13 GPU / 200 GiB、DeepSeek-V4-Flash 144〜153 GiB を ctx=131072 で起動

set -euo pipefail

# --- デフォルト構成 (aws-gpu01 + aws-gpu02) ---
DEFAULT_MODEL='~/models/Huihui-DeepSeek-V4-Flash-0731-abliterated-GGUF/DeepSeek-V4-Flash-Q4_K-0731.gguf'
DEFAULT_ALIAS='DeepSeek-V4-Flash-0731-abliterated-Q4_K'
# DeepSeek-V4-Flash は unsloth 公式値を使う (Qwen3.x 共通プロファイルは適用しない)
DEFAULT_SAMPLING='--temp 1.0 --top-p 1.0 --min-p 0.01'

MODEL="${1:-$DEFAULT_MODEL}"
CTX="${2:-131072}"
SERVER="${SERVER:-aws-gpu01}"
RPC="${RPC:-192.168.100.2:50052}"
WAIT_SECS="${WAIT_SECS:-2400}"
SAMPLING_OPTS="${SAMPLING_OPTS-$DEFAULT_SAMPLING}"

if [ -z "${ALIAS:-}" ]; then
  if [ "$MODEL" = "$DEFAULT_MODEL" ]; then
    ALIAS="$DEFAULT_ALIAS"
  else
    ALIAS="$(basename "$MODEL" .gguf)"
  fi
fi

# ttyd の 7682 (ログ閲覧) が tail する先と同じパスにする。
LOG="/tmp/llama-server.log"

# NOTE: pgrep のパターンを [b]in/... と書くのは自己マッチ回避のため。
#       ssh 越しに起動される bash 自身のコマンドラインにパターン文字列が含まれるので、
#       素直に 'bin/llama-server' と書くと「常に稼働中」と誤判定する（2026-08-17 実測）。
if ssh -n "$SERVER" "pgrep -f '[b]in/llama-server' > /dev/null"; then
  echo "[rpc-llama-up] ERROR: $SERVER で llama-server がすでに稼働中。" >&2
  echo "               二重起動は同じ GPU 群で VRAM を食い合うので中止する。" >&2
  echo "               停止するなら: .claude/skills/llama-server/scripts/stop.sh $SERVER" >&2
  exit 1
fi

if ! ssh -n "$SERVER" "pgrep -f '[b]in/(ggml-)?rpc-server' > /dev/null" \
   && ! ssh -n aws-gpu02 "pgrep -f '[b]in/(ggml-)?rpc-server' > /dev/null"; then
  echo "[rpc-llama-up] WARNING: RPC ワーカーが見つからない。先に rpc-up.sh を実行すること" >&2
fi

echo "[rpc-llama-up] server=$SERVER rpc=$RPC ctx=$CTX"
echo "[rpc-llama-up] model=$MODEL"
echo "[rpc-llama-up] alias=$ALIAS log=$SERVER:$LOG"

# NOTE: $MODEL をクォートしないのは先頭の ~ をリモート側で展開させるため。
# NOTE: 末尾に `disown` を付けてはいけない。非対話 bash では起動用シェルが終了せず
#       SSH チャネルが開いたままになり、このスクリプトがハングする（実測）。
# NOTE: `disown` を外しても ssh が戻ってこないケースがある（2026-08-18 実測）。起動できたかは
#       後段の待機ループが判定するので、起動コマンド自体は timeout で打ち切る。
timeout 60 ssh -n "$SERVER" "cd ~/llama.cpp && setsid nohup ./build/bin/llama-server \
  --model $MODEL \
  --alias '$ALIAS' \
  --rpc $RPC \
  --n-gpu-layers 999 --ctx-size $CTX \
  --flash-attn 1 --poll 0 -b 2048 -ub 512 \
  --jinja $SAMPLING_OPTS ${EXTRA_LLAMA_OPTS:-} \
  --host 0.0.0.0 --port 8000 \
  > $LOG 2>&1 < /dev/null &" || true

if [ "${NO_WAIT:-0}" = "1" ]; then
  echo "[rpc-llama-up] started (NO_WAIT=1)。ログ: ssh $SERVER tail -f $LOG"
  exit 0
fi

echo "[rpc-llama-up] 起動完了を待機中 (最大 ${WAIT_SECS}s)..."

# 完了検出は 'listening on'（成功）と 'error|out of memory|terminate'（失敗）に限定する。
# 'abort' を含めてはいけない —
#   W common_fit_params: failed to fit params to free device memory: n_gpu_layers
#   already set by user to 999, abort
# は -ngl を明示した正常起動でも必ず出る警告で、失敗と誤判定すると
# 二重起動事故につながる（2026-08-16 実測）。
deadline=$((SECONDS + WAIT_SECS))
while [ $SECONDS -lt $deadline ]; do
  if ssh -n "$SERVER" "grep -q 'listening on' $LOG"; then
    echo "[rpc-llama-up] OK: listening on http://$(ssh -G "$SERVER" | awk '/^hostname /{print $2}'):8000"
    exit 0
  fi
  if ssh -n "$SERVER" "grep -qiE 'error|out of memory|terminate' $LOG"; then
    echo "[rpc-llama-up] FAILED:" >&2
    ssh -n "$SERVER" "grep -iE 'error|out of memory|terminate' $LOG | head -10" >&2
    exit 1
  fi
  sleep 20
done

echo "[rpc-llama-up] TIMEOUT: ${WAIT_SECS}s 以内に起動しなかった。ログを確認すること" >&2
exit 2
