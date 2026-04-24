#!/usr/bin/env bash
# C-3 eval ボトルネック プロファイル計測スクリプト
# 使い方: bash profile.sh <LLAMA_PID>
# 引数: llama-server の実 PID (wrapper bash ではなく)
set -euo pipefail

LLAMA_PID="${1:?usage: profile.sh <LLAMA_PID>}"
ATTACH="$(cd "$(dirname "$0")" && pwd)"
HOST="t120h-p100"

SSH_OPTS="-o ServerAliveInterval=10 -o ServerAliveCountMax=3"

API_URL="http://10.1.4.14:8000/v1/chat/completions"
PROMPT='Write a short haiku about autumn.'
REQ_JSON=$(cat <<EOF
{"model":"unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M","messages":[{"role":"user","content":"$PROMPT"}],"max_tokens":256,"temperature":0.6,"top_p":0.95,"top_k":20}
EOF
)

ts_now() { TZ=Asia/Tokyo date +%Y-%m-%dT%H:%M:%S.%N; }

# --- Run 0: idle 20 秒 (eval を打たない基準値) -----------------------------
echo "=== Run 0 (idle) ==="
{
  ssh $SSH_OPTS "$HOST" "nvidia-smi dmon -s pucvmet -d 1 -c 20 -o DT" \
    > "$ATTACH/dmon_run0.log" 2>&1 &
  DPID=$!
  ssh $SSH_OPTS "$HOST" "top -b -d 1 -n 20 -w 512" \
    > "$ATTACH/top_system_run0.log" 2>&1 &
  TSPID=$!
  ssh $SSH_OPTS "$HOST" "top -b -d 1 -n 20 -p $LLAMA_PID -w 512" \
    > "$ATTACH/top_pid_run0.log" 2>&1 &
  TPPID=$!
  wait $DPID $TSPID $TPPID
}
echo "run=0 (idle) done at $(ts_now)" >> "$ATTACH/timeline.log"

# --- Run 1-3: eval + dmon/top 40 秒窓 -------------------------------------
for RUN in 1 2 3; do
  echo "=== Run $RUN (eval) ==="
  # dmon/top を起動
  ssh $SSH_OPTS "$HOST" "nvidia-smi dmon -s pucvmet -d 1 -c 40 -o DT" \
    > "$ATTACH/dmon_run${RUN}.log" 2>&1 &
  DPID=$!
  ssh $SSH_OPTS "$HOST" "top -b -d 1 -n 40 -w 512" \
    > "$ATTACH/top_system_run${RUN}.log" 2>&1 &
  TSPID=$!
  ssh $SSH_OPTS "$HOST" "top -b -d 1 -n 40 -p $LLAMA_PID -w 512" \
    > "$ATTACH/top_pid_run${RUN}.log" 2>&1 &
  TPPID=$!

  # dmon ウォームアップ
  sleep 3

  # eval 実行
  EVAL_START=$(ts_now)
  curl -s "$API_URL" \
    -H 'Content-Type: application/json' \
    -d "$REQ_JSON" \
    > "$ATTACH/eval_run${RUN}.json" 2>&1
  EVAL_END=$(ts_now)

  # dmon/top の終了を待つ
  wait $DPID $TSPID $TPPID

  echo "run=$RUN eval_start=$EVAL_START eval_end=$EVAL_END" >> "$ATTACH/timeline.log"

  # Run 間インターバル (最後以外)
  if [[ "$RUN" != 3 ]]; then
    echo "--- cooldown 60s ---"
    sleep 60
  fi
done

echo "DONE. logs in $ATTACH"
