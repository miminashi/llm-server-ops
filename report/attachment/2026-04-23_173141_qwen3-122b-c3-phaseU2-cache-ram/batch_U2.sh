#!/usr/bin/env bash
# batch_U2.sh - Phase U-2: --cache-ram 6 条件 × (TTFT / prefix / eval regression)
#   CACHE_RAM_VALUES=(0 128 256 512 1024 2048)
#   固定構成: B14b_ts_alt (T-5a-ts2 歴代最良、eval 18.664 t/s)
#
# 各条件: stop → start(CACHE_RAM) → health wait → A) TTFT → B) prefix → C) eval 5-run → stop
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p startup_logs

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

# 固定 (B14b_ts_alt 継承)
KV="q8_0"
SM="layer"
CTX=32768
UB=256
THR=40
OT_TAG="B14b"
OT_REGEX='blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU'
TS="11,12,13,14"

# 条件軸: CACHE_RAM (MiB)
CACHE_RAM_VALUES=(${CACHE_RAM_VALUES:-0 128 256 512 1024 2048})

# regression eval の RUNS (既存 measure_phaseT5.sh 流用)
WARMUP_RUNS="${WARMUP_RUNS:-2}"
EVAL_RUNS="${EVAL_RUNS:-5}"

# TTFT 連投回数
N_HITS="${N_HITS:-4}"

# 最初の 1 条件のみ STREAM_TTFT=1 で実測 TTFT と prompt_ms 近似の乖離を検証
STREAM_TTFT_FIRST="${STREAM_TTFT_FIRST:-1}"

SKIP_CRAM="${SKIP_CRAM:-}"

echo "[batchU2] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
echo "[batchU2] CACHE_RAM_VALUES=${CACHE_RAM_VALUES[*]} (skip: ${SKIP_CRAM:-none})"
echo "[batchU2] fixed: OT=${OT_TAG} TS=${TS} ctx=${CTX} ub=${UB} kv=${KV} thr=${THR}"

cond_idx=0
for CACHE_RAM in "${CACHE_RAM_VALUES[@]}"; do
  cond_idx=$((cond_idx + 1))
  if [[ ",${SKIP_CRAM}," == *",${CACHE_RAM},"* ]]; then
    echo "[batchU2] SKIP CACHE_RAM=${CACHE_RAM} (per SKIP_CRAM)"
    continue
  fi

  TS_TAG="_ts$(echo "$TS" | tr , -)"
  CRAM_TAG="_cram${CACHE_RAM}"
  TAG_COND="${OT_TAG}_t${THR}_kv${KV}_sm${SM}_ctx${CTX}_ub${UB}${TS_TAG}${CRAM_TAG}"

  echo "[batchU2] ================================"
  echo "[batchU2] cond #${cond_idx}: CACHE_RAM=${CACHE_RAM} MiB at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchU2] ================================"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  TS="$TS" OT_TAG="$OT_TAG" OT_REGEX="$OT_REGEX" \
    FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
    CACHE_TYPE_K="$KV" CACHE_TYPE_V="$KV" SPLIT_MODE="$SM" THREADS="$THR" \
    CACHE_RAM="$CACHE_RAM" \
    bash start_phaseU2.sh > "start_stdout_U2_${TAG_COND}.log" 2>&1 &
  START_PID=$!

  healthy=0
  for i in $(seq 1 60); do
    if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
      echo "[batchU2] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    if ! kill -0 "$START_PID" 2>/dev/null; then
      echo "[batchU2] start_phaseU2.sh exited early for CACHE_RAM=${CACHE_RAM}" >&2
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchU2] ERROR: health never OK for CACHE_RAM=${CACHE_RAM}" >&2
    tail -80 "start_stdout_U2_${TAG_COND}.log" >&2 || true
    kill -9 "$START_PID" 2>/dev/null || true
    bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
    sleep 5
    continue
  fi

  for i in 1 2 3 4 5 6; do
    if ! kill -0 "$START_PID" 2>/dev/null; then break; fi
    sleep 2
  done
  kill "$START_PID" 2>/dev/null || true
  wait "$START_PID" 2>/dev/null || true

  PID=$(ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "ps -eo pid,comm | awk '\$2==\"llama-server\"{print \$1;exit}'" | tr -d '[:space:]')
  if [ -z "$PID" ]; then
    echo "[batchU2] ERROR: PID not found for CACHE_RAM=${CACHE_RAM}" >&2
    continue
  fi
  echo "[batchU2] PID=$PID"

  REMOTE_LOG_NAME="llama-server_phaseU2_${OT_TAG}_t${THR}_sm${SM}_k${KV}_v${KV}_fa1_ctx${CTX}_b${UB}_ub${UB}${TS_TAG}${CRAM_TAG}.log"
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/${REMOTE_LOG_NAME}" \
    > "startup_logs/U2_${TAG_COND}.log" 2>&1 || true
  echo "[batchU2] startup log saved ($(wc -l < startup_logs/U2_${TAG_COND}.log 2>/dev/null || echo 0) lines)"

  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "nvidia-smi --query-gpu=index,memory.total,memory.used,memory.free --format=csv" \
    > "startup_logs/U2_${TAG_COND}_nvidia_smi.csv" 2>&1 || true
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "free -w" > "startup_logs/U2_${TAG_COND}_free_pre.txt" 2>&1 || true

  # (A) TTFT miss→hit 連投
  STREAM_TTFT_THIS=0
  if [ "$cond_idx" -eq 1 ] && [ "$STREAM_TTFT_FIRST" -eq 1 ]; then
    STREAM_TTFT_THIS=1
  fi
  echo "[batchU2] (A) TTFT: STREAM_TTFT=${STREAM_TTFT_THIS} N_HITS=${N_HITS}"
  STREAM_TTFT=$STREAM_TTFT_THIS COOLDOWN=10 \
    bash measure_phaseU2_ttft.sh "$PID" "U2_${TAG_COND}_ttft" "@${SCRIPT_DIR}/prompts/system_fixed.txt" "$N_HITS" \
    > "measure_ttft_${TAG_COND}.log" 2>&1 || echo "[batchU2] ttft measure failed" >&2

  # (B) shared-prefix (5 suffix)
  echo "[batchU2] (B) Prefix pattern (5 suffixes)"
  COOLDOWN=10 \
    bash measure_phaseU2_prefix.sh "$PID" "U2_${TAG_COND}_prefix" \
      "${SCRIPT_DIR}/prompts/system_fixed.txt" "${SCRIPT_DIR}/prompts/user_suffixes.tsv" \
    > "measure_prefix_${TAG_COND}.log" 2>&1 || echo "[batchU2] prefix measure failed" >&2

  # (C) eval regression (既存 measure_phaseT5.sh; marker 付き、cache miss 強制)
  echo "[batchU2] (C) eval regression (warmup ${WARMUP_RUNS} + 1k ${EVAL_RUNS})"
  PID="$PID" TAG_PREFIX="U2_${TAG_COND}" WARMUP_RUNS="$WARMUP_RUNS" EVAL_RUNS="$EVAL_RUNS" \
    bash run_all_U2.sh > "run_U2_${TAG_COND}.log" 2>&1 || echo "[batchU2] run_all_U2 failed" >&2
  echo "[batchU2] measure done ($(tail -1 run_U2_${TAG_COND}.log 2>/dev/null))"

  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "free -w" > "startup_logs/U2_${TAG_COND}_free_post.txt" 2>&1 || true

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchU2] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
