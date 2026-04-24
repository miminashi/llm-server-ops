#!/usr/bin/env bash
# batch_phaseT5a-ts.sh - Phase T-5a-ts: tensor-split で B16 化試行 + B18 ts 効果切り分け
# 7 label × (warmup 2 + 1k eval 5) = 49 measurement
#   1. B18_default_a   (B18, ts 未指定, drift 起点・T-5a-ub 18.103 cross-session 再現)
#   2. B18_ts_equal    (B18, ts=15,11,10,13, default 等価明示・-ts 副作用 control)
#   3. B18_ts_skew     (B18, ts=13,11,12,13, CUDA0 -2GB・-ts 純効果)
#   4. B16_ts_skew     (B16, ts=<dry probe 通過の最良>, 本命・新記録第一候補)
#   5. B16_ts_alt      (B16, ts=<dry probe 通過の次善>, B16 内 ts 感度・再現性)
#   6. B18_default_mid (B18, ts 未指定, drift 線形性中央点)
#   7. B18_default_z   (B18, ts 未指定, drift 終点)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p startup_logs

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

# 固定パラメータ (T-5a-ub 最良継承: ub=256, ctx=32k, KV=q8_0, SM=layer, threads=40)
KV="q8_0"
SM="layer"
CTX=32768
UB=256
THR=40

OT_B18='blk\.([0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
OT_B16='blk\.([2-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'

# dry probe 結果 (2026-04-23_074832 batch) で確定:
#   D1 B18 default → OK (CUDA0=15339)
#   D2 B18 ts=15,11,10,13 → OOM (CUDA0 への配分比 30.6% で default 越え)
#   D3 B18 ts=13,11,12,13 → OK, CUDA0=15339 (default と完全一致 → control に最適)
#   D4 B16 ts=13,11,12,13 → OOM
#   D5 B16 ts=11,12,13,13 → OK, CUDA0=15107, CUDA1=14235 (B16 fit 達成)
#   D6 B18 ts=12,12,12,13 → OK, CUDA0=13841 (-1498 MiB から default)
TS_B18_EQUAL="${TS_B18_EQUAL:-13,11,12,13}"   # D3, default と CUDA0 完全一致
TS_B18_SKEW="${TS_B18_SKEW:-11,12,13,13}"     # D5 と同 ts、B18 → B16 直接比較用
TS_B16_PRIMARY="${TS_B16_PRIMARY:-11,12,13,13}"  # D5 で B16 fit 確認済み
TS_B16_ALT="${TS_B16_ALT:-10,12,13,14}"          # B16 内 ts 感度評価 (CUDA0 更削減 + CUDA3 増)

# 条件定義: "LABEL#OT_TAG#OT_REGEX#TS"
CONDITIONS=(
  "B18_default_a#B18#${OT_B18}#"
  "B18_ts_equal#B18#${OT_B18}#${TS_B18_EQUAL}"
  "B18_ts_skew#B18#${OT_B18}#${TS_B18_SKEW}"
  "B16_ts_skew#B16#${OT_B16}#${TS_B16_PRIMARY}"
  "B16_ts_alt#B16#${OT_B16}#${TS_B16_ALT}"
  "B18_default_mid#B18#${OT_B18}#"
  "B18_default_z#B18#${OT_B18}#"
)

# OOM/skip 用 envvar
SKIP_LABELS="${SKIP_LABELS:-}"

echo "[batchT5ats] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
echo "[batchT5ats] total conditions: ${#CONDITIONS[@]} (skip: ${SKIP_LABELS:-none})"
echo "[batchT5ats] TS_B16_PRIMARY=${TS_B16_PRIMARY} TS_B16_ALT=${TS_B16_ALT}"

for COND in "${CONDITIONS[@]}"; do
  IFS='#' read -r LABEL OT_TAG OT_REGEX TS <<< "$COND"

  if [[ ",${SKIP_LABELS}," == *",${LABEL},"* ]]; then
    echo "[batchT5ats] SKIP label=${LABEL} (per SKIP_LABELS)"
    continue
  fi

  TS_TAG="${TS:+_ts$(echo "$TS" | tr , -)}"
  TAG_COND="${LABEL}_t${THR}_kv${KV}_sm${SM}_ctx${CTX}_ub${UB}${TS_TAG}"

  echo "[batchT5ats] ================================"
  echo "[batchT5ats] cond: label=${LABEL} OT=${OT_TAG} TS=${TS:-(default)} at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchT5ats] ================================"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  TS="$TS" OT_TAG="$OT_TAG" OT_REGEX="$OT_REGEX" \
    FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
    CACHE_TYPE_K="$KV" CACHE_TYPE_V="$KV" SPLIT_MODE="$SM" THREADS="$THR" \
    bash start_phaseT5.sh > "start_stdout_T5ats_${TAG_COND}.log" 2>&1 &
  START_PID=$!

  healthy=0
  for i in $(seq 1 60); do
    if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
      echo "[batchT5ats] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    if ! kill -0 "$START_PID" 2>/dev/null; then
      echo "[batchT5ats] start_phaseT5.sh exited early for label=${LABEL}" >&2
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchT5ats] ERROR: health never OK for label=${LABEL}" >&2
    tail -80 "start_stdout_T5ats_${TAG_COND}.log" >&2 || true
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
    echo "[batchT5ats] ERROR: PID not found for label=${LABEL}" >&2
    continue
  fi
  echo "[batchT5ats] PID=$PID"

  REMOTE_LOG_NAME="llama-server_phaseT5_${OT_TAG}_t${THR}_sm${SM}_k${KV}_v${KV}_fa1_ctx${CTX}_b${UB}_ub${UB}${TS_TAG}.log"
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/${REMOTE_LOG_NAME}" \
    > "startup_logs/T5ats_${TAG_COND}.log"
  echo "[batchT5ats] startup log saved ($(wc -l < startup_logs/T5ats_${TAG_COND}.log) lines)"

  PID="$PID" TAG_PREFIX="T5ats_${TAG_COND}" WARMUP_RUNS=2 EVAL_RUNS=5 \
    bash run_all.sh > "run_T5ats_${TAG_COND}.log" 2>&1
  echo "[batchT5ats] measure done ($(tail -1 run_T5ats_${TAG_COND}.log))"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchT5ats] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
