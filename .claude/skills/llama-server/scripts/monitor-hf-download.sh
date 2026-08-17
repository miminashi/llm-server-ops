#!/usr/bin/env bash
#
# hf CLI (`hf download --local-dir ...`) の進捗を監視する。
#
# 既存の monitor-download.sh は llama.cpp の `-hf` 方式
# (/home/llm/.cache/llama.cpp/*.downloadInProgress) 専用で、
# aws-gpu01/02 のように `hf download --local-dir ~/models/...` を使う場合は動かない
# (ユーザが llm ではなく ubuntu、キャッシュ場所も別)。こちらはそのための版。
#
# 使い方:
#   monitor-hf-download.sh <server> <local-dir> [expected-bytes]
#
# 例:
#   .claude/skills/llama-server/scripts/monitor-hf-download.sh aws-gpu01 \
#     '~/models/Huihui-DeepSeek-V4-Flash-0731-abliterated-GGUF' 164633502592
#
# expected-bytes は HF API から取れる:
#   curl -s https://huggingface.co/api/models/<repo>/tree/main | \
#     python3 -c 'import json,sys; [print(f["size"], f["path"]) for f in json.load(sys.stdin)]'
#
# ロック不要（読み取り専用の監視）。

set -euo pipefail

SERVER="${1:?usage: monitor-hf-download.sh <server> <local-dir> [expected-bytes]}"
DIR="${2:?usage: monitor-hf-download.sh <server> <local-dir> [expected-bytes]}"
EXPECTED="${3:-0}"
INTERVAL="${INTERVAL:-30}"

prev=0
prev_t=0

while true; do
  # du -sb は .incomplete も含めた実バイト数。ディレクトリが無い間は 0 扱い。
  cur=$(ssh -n "$SERVER" "du -sb $DIR 2>/dev/null | cut -f1" || echo 0)
  cur=${cur:-0}
  now=$(date +%s)

  line="$(date '+%H:%M:%S') $(numfmt --to=iec "$cur")"

  if [ "$EXPECTED" -gt 0 ]; then
    pct=$((cur * 100 / EXPECTED))
    line="$line / $(numfmt --to=iec "$EXPECTED") (${pct}%)"
  fi

  if [ "$prev_t" -gt 0 ] && [ "$cur" -gt "$prev" ]; then
    rate=$(( (cur - prev) / (now - prev_t) ))
    line="$line  $(numfmt --to=iec "$rate")/s"
    if [ "$EXPECTED" -gt 0 ] && [ "$rate" -gt 0 ]; then
      eta=$(( (EXPECTED - cur) / rate ))
      line="$line  ETA $((eta / 60))m$((eta % 60))s"
    fi
  fi

  echo "$line"

  # hf のプロセスが消えたら終了。[h]f 表記は pgrep の自己マッチ回避のため
  # (ssh 越しの bash 自身のコマンドラインにパターンが含まれてしまう)。
  if ! ssh -n "$SERVER" "pgrep -f '[h]f download' > /dev/null"; then
    echo "$(date '+%H:%M:%S') hf download プロセスが終了しました"
    if [ "$EXPECTED" -gt 0 ]; then
      if [ "$cur" -ge "$EXPECTED" ]; then
        echo "==> サイズ一致を確認 (期待値以上)"
      else
        echo "==> WARNING: 期待サイズに達していません。ログを確認してください" >&2
      fi
    fi
    exit 0
  fi

  prev=$cur
  prev_t=$now
  sleep "$INTERVAL"
done
