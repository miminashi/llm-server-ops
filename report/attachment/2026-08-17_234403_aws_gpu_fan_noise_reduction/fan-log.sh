#!/usr/bin/env bash
# fan-sample.sh を一定間隔で回して CSV に追記する
#   使い方: fan-log.sh <server> <out.csv> <interval_sec> <duration_sec>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SERVER="${1:?}"; OUT="${2:?}"; IVL="${3:-15}"; DUR="${4:-600}"

"$HERE/fan-sample.sh" "$SERVER" --header > "$OUT"
END=$((SECONDS + DUR))
while (( SECONDS < END )); do
    "$HERE/fan-sample.sh" "$SERVER" >> "$OUT"
    sleep "$IVL"
done
echo "done: $OUT ($(wc -l < "$OUT") lines)"
