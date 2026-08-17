#!/usr/bin/env bash
# wikitext-2 (test) に対する perplexity を RPC 分散構成で計測する。
#
# 使い方:
#   run_ppl.sh baseline    ~/models/DeepSeek-V4-Flash-0731-GGUF/UD-Q4_K_XL/DeepSeek-V4-Flash-0731-UD-Q4_K_XL-00001-of-00005.gguf
#   run_ppl.sh abliterated ~/models/Huihui-DeepSeek-V4-Flash-0731-abliterated-GGUF/DeepSeek-V4-Flash-Q4_K-0731.gguf
#
# llama-server とは VRAM を共有できないので、実行前に llama-server を停止しておくこと
# (rpc-server は動かしたままでよい)。
# リモート側は setsid nohup でデタッチ起動する。末尾に `disown` を付けてはいけない
# (非対話 bash では SSH チャネルが開いたままハングする)。

set -euo pipefail

LABEL="${1:?usage: run_ppl.sh <label> <remote-model-path>}"
MODEL="${2:?usage: run_ppl.sh <label> <remote-model-path>}"
SERVER="${SERVER:-aws-gpu01}"
RPC="${RPC:-192.168.100.2:50052}"
CHUNKS="${CHUNKS:-40}"
CTX="${CTX:-512}"
REMOTE_LOG="/tmp/ppl-${LABEL}.log"

echo "[run_ppl] label=$LABEL chunks=$CHUNKS ctx=$CTX"
echo "[run_ppl] model=$MODEL"

# パターンを [b]in/... と書くのは、ssh 越しに起動される bash 自身のコマンドラインに
# パターン文字列が含まれてしまい pgrep が自己マッチするのを避けるため。
if ssh -n "$SERVER" "pgrep -f '[b]in/llama-server' > /dev/null"; then
  echo "[run_ppl] ERROR: llama-server が稼働中。先に停止すること" >&2
  exit 1
fi

# $MODEL をクォートで囲まないのは、先頭の ~ をリモート側で展開させるため
# (パスに空白は含まれない前提)
ssh -n "$SERVER" "cd ~/llama.cpp && setsid nohup ./build/bin/llama-perplexity \
  -m $MODEL \
  --rpc $RPC \
  -ngl 999 -c $CTX --chunks $CHUNKS -fa 1 \
  -f ~/data/wikitext-2-raw/wiki.test.raw \
  > $REMOTE_LOG 2>&1 < /dev/null &"

echo "[run_ppl] started. remote log: $SERVER:$REMOTE_LOG"
