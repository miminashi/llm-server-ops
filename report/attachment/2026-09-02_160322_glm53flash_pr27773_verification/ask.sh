#!/usr/bin/env bash
# GPU サーバ上で実行する。WS から curl を長時間張ると切断されるため
# (2026-08-29 レポートの副次発見)、リクエストはサーバ側で setsid nohup して
# 結果をファイルに落とし、それをポーリングする方式にする。
#
# usage: ask.sh <payload.json> <out.json>
set -u
PAYLOAD="$1"; OUT="$2"
rm -f "$OUT" "$OUT.done"
setsid nohup bash -c "curl -sS -m 7200 -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' --data-binary @'$PAYLOAD' -o '$OUT' ; echo \$? > '$OUT.done'" \
  > /dev/null 2>&1 < /dev/null &
echo "started: $PAYLOAD -> $OUT"
