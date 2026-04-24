#!/usr/bin/env bash
# batch_T5ats2.sh - Phase T-5a-ts2: B14 × ts で 19+ 突破試行 + 2-pt drift bracket
# 5 label × (warmup 2 + 1k eval 5) = 35 measurement
#   1. B18_default_a   (B18, ts 未指定, drift 起点・T-5a-ts 17.964 cross-session 再現)
#   2. B14_ts_primary  (B14, dry で確定した最良 ts、本命)
#   3. B14_ts_alt      (B14, dry で確定した次点 ts、感度評価)
#   4. B16_ts_skew     (B16, ts=11,12,13,13, T-5a-ts peak 18.417 cross-session 再現)
#   5. B18_default_z   (B18, ts 未指定, drift 終点)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p startup_logs

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

# 固定パラメータ (T-5a-ts 最良継承)
KV="q8_0"
SM="layer"
CTX=32768
UB=256
THR=40

OT_B18='blk\.([0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'            # 18 層 (0-3, 20-24, 31-39)
OT_B16='blk\.([2-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'            # 16 層 (2-3, 20-24, 31-39)
OT_B14_b='blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU'          # 14 層 (2-3, 20-23, 31-38: layer 24,39 GPU)
OT_B14_c='blk\.([2-3]|2[0-2]|3[1-9])\.ffn_.*_exps\.weight=CPU'          # 14 層 (2-3, 20-22, 31-39: layer 23,24 GPU)

# ts 設定: dry probe v2 結果で確定 (D5 = OT-c balanced, D1 = OT-b tight CUDA3)
# env var で override 可能
TS_B14_PRIMARY="${TS_B14_PRIMARY:-11,12,13,14}"   # PRIMARY: OT-c + D5 VRAM balance 最良
TS_B14_ALT="${TS_B14_ALT:-11,12,13,14}"           # ALT: OT-b 同 ts で OT 比較
TS_B16_SKEW="${TS_B16_SKEW:-11,12,13,13}"         # T-5a-ts D5 固定

# 条件定義: "LABEL#OT_TAG#OT_REGEX#TS"
CONDITIONS=(
  "B18_default_a#B18#${OT_B18}#"
  "B14c_ts_primary#B14c#${OT_B14_c}#${TS_B14_PRIMARY}"
  "B14b_ts_alt#B14b#${OT_B14_b}#${TS_B14_ALT}"
  "B16_ts_skew#B16#${OT_B16}#${TS_B16_SKEW}"
  "B18_default_z#B18#${OT_B18}#"
)

SKIP_LABELS="${SKIP_LABELS:-}"

echo "[batchT5ats2] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
echo "[batchT5ats2] total conditions: ${#CONDITIONS[@]} (skip: ${SKIP_LABELS:-none})"
echo "[batchT5ats2] TS_B14_PRIMARY=${TS_B14_PRIMARY} TS_B14_ALT=${TS_B14_ALT} TS_B16_SKEW=${TS_B16_SKEW}"

for COND in "${CONDITIONS[@]}"; do
  IFS='#' read -r LABEL OT_TAG OT_REGEX TS <<< "$COND"

  if [[ ",${SKIP_LABELS}," == *",${LABEL},"* ]]; then
    echo "[batchT5ats2] SKIP label=${LABEL} (per SKIP_LABELS)"
    continue
  fi

  TS_TAG="${TS:+_ts$(echo "$TS" | tr , -)}"
  TAG_COND="${LABEL}_t${THR}_kv${KV}_sm${SM}_ctx${CTX}_ub${UB}${TS_TAG}"

  echo "[batchT5ats2] ================================"
  echo "[batchT5ats2] cond: label=${LABEL} OT=${OT_TAG} TS=${TS:-(default)} at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchT5ats2] ================================"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  TS="$TS" OT_TAG="$OT_TAG" OT_REGEX="$OT_REGEX" \
    FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
    CACHE_TYPE_K="$KV" CACHE_TYPE_V="$KV" SPLIT_MODE="$SM" THREADS="$THR" \
    bash start_phaseT5.sh > "start_stdout_T5ats2_${TAG_COND}.log" 2>&1 &
  START_PID=$!

  healthy=0
  for i in $(seq 1 60); do
    if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
      echo "[batchT5ats2] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    if ! kill -0 "$START_PID" 2>/dev/null; then
      echo "[batchT5ats2] start_phaseT5.sh exited early for label=${LABEL}" >&2
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchT5ats2] ERROR: health never OK for label=${LABEL}" >&2
    tail -80 "start_stdout_T5ats2_${TAG_COND}.log" >&2 || true
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
    echo "[batchT5ats2] ERROR: PID not found for label=${LABEL}" >&2
    continue
  fi
  echo "[batchT5ats2] PID=$PID"

  REMOTE_LOG_NAME="llama-server_phaseT5_${OT_TAG}_t${THR}_sm${SM}_k${KV}_v${KV}_fa1_ctx${CTX}_b${UB}_ub${UB}${TS_TAG}.log"
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/${REMOTE_LOG_NAME}" \
    > "startup_logs/T5ats2_${TAG_COND}.log"
  echo "[batchT5ats2] startup log saved ($(wc -l < startup_logs/T5ats2_${TAG_COND}.log) lines)"

  # nvidia-smi 取得 (fit 実測値記録)
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "nvidia-smi --query-gpu=index,memory.total,memory.used,memory.free --format=csv" \
    > "startup_logs/T5ats2_${TAG_COND}_nvidia_smi.csv" 2>&1 || true

  PID="$PID" TAG_PREFIX="T5ats2_${TAG_COND}" WARMUP_RUNS=2 EVAL_RUNS=5 \
    bash run_all.sh > "run_T5ats2_${TAG_COND}.log" 2>&1
  echo "[batchT5ats2] measure done ($(tail -1 run_T5ats2_${TAG_COND}.log))"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchT5ats2] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
