#!/usr/bin/env bash
# C-3 eval ボトルネック Phase A 深掘り計測スクリプト
# 使い方: bash profile_phaseA.sh <LLAMA_PID> [PREFIX]
#   PREFIX はログファイル名のプレフィックス (省略時 "phaseA")
# 既存 profile.sh の枠組みを踏襲し、perf / numastat / mpstat / pidstat /
# /proc snapshot を追加並列採取する。eval 3 回の中央値を採る。
set -euo pipefail

LLAMA_PID="${1:?usage: profile_phaseA.sh <LLAMA_PID> [PREFIX]}"
PREFIX="${2:-phaseA}"
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

# 事前 snapshot: /tmp/llama-server.log の先頭 (tensor 配置ログ) を保全
ssh $SSH_OPTS "$HOST" "head -n 400 /tmp/llama-server.log" \
  > "$ATTACH/llama_server_log_snapshot.txt" 2>&1 || true

# 共通並列観測本体 (Run N = 観測秒 SEC と eval 実行有無 DO_EVAL)
run_window() {
  local RUN="$1"
  local SEC="$2"
  local DO_EVAL="$3"

  echo "=== Run $RUN (${SEC}s, eval=${DO_EVAL}) ==="

  # dmon
  ssh $SSH_OPTS "$HOST" "nvidia-smi dmon -s pucvmet -d 1 -c $SEC -o DT" \
    > "$ATTACH/${PREFIX}_dmon_run${RUN}.log" 2>&1 &
  local DPID=$!
  # top (system)
  ssh $SSH_OPTS "$HOST" "top -b -d 1 -n $SEC -w 512" \
    > "$ATTACH/${PREFIX}_top_system_run${RUN}.log" 2>&1 &
  local TSPID=$!
  # top (pid)
  ssh $SSH_OPTS "$HOST" "top -b -d 1 -n $SEC -p $LLAMA_PID -w 512" \
    > "$ATTACH/${PREFIX}_top_pid_run${RUN}.log" 2>&1 &
  local TPPID=$!
  # mpstat (per-CPU)
  ssh $SSH_OPTS "$HOST" "mpstat -P ALL 1 $SEC" \
    > "$ATTACH/${PREFIX}_mpstat_run${RUN}.log" 2>&1 &
  local MPPID=$!
  # pidstat (per-thread)
  ssh $SSH_OPTS "$HOST" "pidstat -t -p $LLAMA_PID 1 $SEC" \
    > "$ATTACH/${PREFIX}_pidstat_run${RUN}.log" 2>&1 &
  local PSPID=$!
  # perf stat (system-wide)
  # メモリ系 (mem-loads/mem-stores) は一部環境で未対応なため除外し、
  # cycles, instructions, cache-misses, cache-references, LLC-loads,
  # LLC-load-misses, node-loads, node-load-misses, dTLB-loads, dTLB-load-misses を採取。
  ssh $SSH_OPTS "$HOST" "perf stat -a -e cycles,instructions,cache-misses,cache-references,LLC-loads,LLC-load-misses,node-loads,node-load-misses,dTLB-loads,dTLB-load-misses -- sleep $SEC" \
    > "$ATTACH/${PREFIX}_perfstat_run${RUN}.log" 2>&1 &
  local PFPID=$!
  # perf record (Run 3 のみ: eval 窓中の call-graph サンプリング)
  local PRPID=""
  if [[ "$RUN" == "3" ]]; then
    ssh $SSH_OPTS "$HOST" "perf record -g -F 99 -a -o /tmp/perf_${PREFIX}_run3.data -- sleep $SEC" \
      > "$ATTACH/${PREFIX}_perfrec_run${RUN}.log" 2>&1 &
    PRPID=$!
  fi

  # eval 前 snapshot: numastat / vmstat
  ssh $SSH_OPTS "$HOST" "numastat -p $LLAMA_PID" \
    > "$ATTACH/${PREFIX}_numastat_pre_run${RUN}.log" 2>&1 || true
  ssh $SSH_OPTS "$HOST" "cat /proc/vmstat" \
    > "$ATTACH/${PREFIX}_vmstat_pre_run${RUN}.log" 2>&1 || true

  # /proc/$PID/status を 3 秒毎 (概ね 14 点までサンプル) バックグラウンド採取
  (
    for i in $(seq 1 $((SEC / 3 + 1))); do
      echo "--- sample $i $(ts_now) ---"
      ssh $SSH_OPTS "$HOST" "cat /proc/$LLAMA_PID/status" 2>&1 || true
      sleep 3
    done
  ) > "$ATTACH/${PREFIX}_status_run${RUN}.log" 2>&1 &
  local STPID=$!

  # ウォームアップ (dmon/top 開始から 3 秒)
  sleep 3

  if [[ "$DO_EVAL" == "1" ]]; then
    # numa_maps スナップショット (eval 中の 1 ポイント)
    ssh $SSH_OPTS "$HOST" "cat /proc/$LLAMA_PID/numa_maps" \
      > "$ATTACH/${PREFIX}_numa_maps_run${RUN}.txt" 2>&1 || true

    local EVAL_START
    EVAL_START=$(ts_now)
    curl -s "$API_URL" \
      -H 'Content-Type: application/json' \
      -d "$REQ_JSON" \
      > "$ATTACH/${PREFIX}_eval_run${RUN}.json" 2>&1
    local EVAL_END
    EVAL_END=$(ts_now)
    echo "run=$RUN eval_start=$EVAL_START eval_end=$EVAL_END" >> "$ATTACH/${PREFIX}_timeline.log"
  else
    echo "run=$RUN (idle, no eval) $(ts_now)" >> "$ATTACH/${PREFIX}_timeline.log"
  fi

  # 観測プロセスの完了待ち
  wait $DPID $TSPID $TPPID $MPPID $PSPID $PFPID $STPID 2>/dev/null || true
  if [[ -n "$PRPID" ]]; then
    wait "$PRPID" 2>/dev/null || true
  fi

  # eval 後 snapshot
  ssh $SSH_OPTS "$HOST" "numastat -p $LLAMA_PID" \
    > "$ATTACH/${PREFIX}_numastat_post_run${RUN}.log" 2>&1 || true
  ssh $SSH_OPTS "$HOST" "cat /proc/vmstat" \
    > "$ATTACH/${PREFIX}_vmstat_post_run${RUN}.log" 2>&1 || true
  ssh $SSH_OPTS "$HOST" "cat /proc/$LLAMA_PID/sched" \
    > "$ATTACH/${PREFIX}_sched_run${RUN}.log" 2>&1 || true
}

# --- Run 0: idle 20s (eval なし) ---
run_window 0 20 0

# --- Run 1-3: eval 40s 窓 ---
for RUN in 1 2 3; do
  run_window "$RUN" 40 1
  if [[ "$RUN" != "3" ]]; then
    echo "--- cooldown 60s ---"
    sleep 60
  fi
done

# Run 3 の perf.data を手元にコピー + report 生成
ssh $SSH_OPTS "$HOST" "test -f /tmp/perf_${PREFIX}_run3.data && \
  cd /tmp && perf report -i perf_${PREFIX}_run3.data --stdio --no-children 2>/dev/null | head -n 200" \
  > "$ATTACH/${PREFIX}_perf_report_run3.txt" 2>&1 || true

echo "DONE. logs in $ATTACH"
