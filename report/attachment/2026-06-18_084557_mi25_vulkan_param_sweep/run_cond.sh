#!/usr/bin/env bash
# run_cond.sh - 1条件: サーバ再起動(custom env+override flags) → measure.sh で計測
# 必須 env:
#   COND_ID CELL TAG MAXTOK WARM EVALN DEVS CSV
# 任意 env:
#   ENV_EXTRA   (例 "GGML_VK_FORCE_MMVQ=1")  サーバ起動時の追加環境変数
#   OVERRIDE    (例 "-ub 4096" / "-sm row")  canonical cmdline 末尾に追記する上書きフラグ
#   CANON_FILE  (default /tmp/mi25vk_bench/canonical_cmd.txt) canonical llama-server cmdline
#   COOLDOWN    (default 15)
set -uo pipefail
BENCH=/tmp/mi25vk_bench
COND_ID="${COND_ID:?}"; CELL="${CELL:?}"; TAG="${TAG:?}"
MAXTOK="${MAXTOK:?}"; WARM="${WARM:?}"; EVALN="${EVALN:?}"; DEVS="${DEVS:?}"; CSV="${CSV:?}"
ENV_EXTRA="${ENV_EXTRA:-}"; OVERRIDE="${OVERRIDE:-}"
CANON_FILE="${CANON_FILE:-$BENCH/canonical_cmd.txt}"
COOLDOWN="${COOLDOWN:-15}"
HOST=mi25; URL=http://10.1.4.13:8000

ts() { TZ=Asia/Tokyo date +%H:%M:%S; }
say() { echo "[$(ts)] [orch] $*"; }

CANON="$(cat "$CANON_FILE")"

say "COND=$COND_ID  ENV_EXTRA='$ENV_EXTRA'  OVERRIDE='$OVERRIDE'  DEVS=$DEVS"

# 1) 既存サーバ停止
ssh "$HOST" "pkill -f build-vulkan/bin/llama-server 2>/dev/null; sleep 3; pkill -9 -f build-vulkan/bin/llama-server 2>/dev/null; true" >/dev/null 2>&1
sleep 2

# 2) 起動 (canonical に DEVS と override を反映)
LAUNCH="cd ~/llama.cpp && ${ENV_EXTRA:+$ENV_EXTRA }GGML_VK_VISIBLE_DEVICES=$DEVS $CANON $OVERRIDE"
say "launch: $LAUNCH"
ssh -f "$HOST" "$LAUNCH > /tmp/llama-server.log 2>&1 < /dev/null &" </dev/null >/dev/null 2>&1

# 3) health 待ち (モデルロード ~60s, 最大 ~180s)
ok=0
for i in $(seq 1 36); do
  if curl -sf "$URL/health" >/dev/null 2>&1; then ok=1; break; fi
  sleep 5
done
if [ "$ok" != 1 ]; then
  say "HEALTH FAILED for $COND_ID -- dumping log tail"
  ssh "$HOST" "tail -25 /tmp/llama-server.log"
  echo "$CELL,$COND_ID,NA,$TAG,eval,0,,,,,,,,,health_failed" >> "$CSV"
  exit 2
fi
say "health OK"

# 4) 計測
OUTDIR="$BENCH/results/raw_${CELL}"
CELL="$CELL" OUTDIR="$OUTDIR" PROMPT_TAG="$TAG" PROMPT_FILE="$BENCH/prompts/prompt_${TAG}.txt" \
  COND_ID="$COND_ID" UB="${OVERRIDE:-base}" WARMUP_RUNS="$WARM" EVAL_RUNS="$EVALN" \
  EVAL_MAX_TOKENS="$MAXTOK" COOLDOWN="$COOLDOWN" CSV="$CSV" \
  HOST="$HOST" URL="$URL" bash "$BENCH/measure.sh"
say "COND=$COND_ID done"
