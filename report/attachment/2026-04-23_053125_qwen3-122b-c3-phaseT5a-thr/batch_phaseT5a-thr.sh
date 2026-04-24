#!/usr/bin/env bash
# batch_phaseT5a-thr.sh - Phase T-5a-thr: B18 × ub=256 × threads 再スイープ + drift bracket
# 9 label × (warmup 2 + 1k eval 5) = 63 measurement
#   1. thr40a     (threads=40, drift 起点、T-5a-ub B18_ub256=18.103 の cross-session 再現性検証)
#   2. thr14      (threads=14, CPU 層数一致点、T-3 dip 仮説の B=18 再現性検証)
#   3. thr20      (threads=20, node1 物理コアフル、HT 境界)
#   4. thr28      (threads=28, 中間帯)
#   5. thr32      (threads=32, T-3 で最良だった点、B=18 で再評価)
#   6. thr36      (threads=36, T-3 で dip が出た点の B=18 再測定)
#   7. thr38      (threads=38, node1 最上端に 2 コア余裕あり)
#   8. thr40_mid  (threads=40, 中央に挟み drift 線形性初検証)
#   9. thr40z     (threads=40, drift 終点)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p startup_logs

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

# 固定パラメータ (T-5a-ub 最良継承: OT=B18, ctx=32k, KV=q8_0, SM=layer, ub=256, fa=1)
OT_TAG="B18"
OT_REGEX='blk\.([0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
KV="q8_0"
SM="layer"
CTX=32768
UB=256

# 条件定義: "LABEL#THREADS"
# 順序: drift 起点 (thr40a) → 両端含む sweep → 中央 drift 線形性 (thr40_mid) → drift 終点 (thr40z)
CONDITIONS=(
  'thr40a#40'
  'thr14#14'
  'thr20#20'
  'thr28#28'
  'thr32#32'
  'thr36#36'
  'thr38#38'
  'thr40_mid#40'
  'thr40z#40'
)

# OOM/rejection 時 skip したい条件 (envvar SKIP_LABELS で指定、カンマ区切り)
SKIP_LABELS="${SKIP_LABELS:-}"

echo "[batchT5athr] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
echo "[batchT5athr] total conditions: ${#CONDITIONS[@]} (skip: ${SKIP_LABELS:-none})"

for COND in "${CONDITIONS[@]}"; do
  IFS='#' read -r LABEL THR <<< "$COND"

  if [[ ",${SKIP_LABELS}," == *",${LABEL},"* ]]; then
    echo "[batchT5athr] SKIP label=${LABEL} (per SKIP_LABELS)"
    continue
  fi

  TAG_COND="${LABEL}_t${THR}_kv${KV}_sm${SM}_ctx${CTX}_ub${UB}"
  echo "[batchT5athr] ================================"
  echo "[batchT5athr] cond: label=${LABEL} threads=${THR} at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchT5athr] ================================"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
    CACHE_TYPE_K="$KV" CACHE_TYPE_V="$KV" SPLIT_MODE="$SM" THREADS="$THR" \
    OT_TAG="$OT_TAG" OT_REGEX="$OT_REGEX" \
    bash start_phaseT5.sh > "start_stdout_T5athr_${TAG_COND}.log" 2>&1 &
  START_PID=$!

  # ctx=32k は初期化 ~30s 程度。余裕を見て 60 × 5s = 300s 猶予
  healthy=0
  for i in $(seq 1 60); do
    if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
      echo "[batchT5athr] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    if ! kill -0 "$START_PID" 2>/dev/null; then
      echo "[batchT5athr] start_phaseT5.sh exited early for label=${LABEL}" >&2
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchT5athr] ERROR: health never OK for label=${LABEL}" >&2
    tail -80 "start_stdout_T5athr_${TAG_COND}.log" >&2 || true
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
    echo "[batchT5athr] ERROR: PID not found for label=${LABEL}" >&2
    continue
  fi
  echo "[batchT5athr] PID=$PID"

  # start_phaseT5.sh が書くリモートログ名を SCP で吸い上げ
  # remote log 名は THREADS を含む (thr40a/thr40_mid/thr40z は同じ remote log だが起動毎に上書き)
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/llama-server_phaseT5_${OT_TAG}_t${THR}_sm${SM}_k${KV}_v${KV}_fa1_ctx${CTX}_b${UB}_ub${UB}.log" \
    > "startup_logs/T5athr_${TAG_COND}.log"
  echo "[batchT5athr] startup log saved ($(wc -l < startup_logs/T5athr_${TAG_COND}.log) lines)"

  PID="$PID" TAG_PREFIX="T5athr_${TAG_COND}" WARMUP_RUNS=2 EVAL_RUNS=5 \
    bash run_all.sh > "run_T5athr_${TAG_COND}.log" 2>&1
  echo "[batchT5athr] measure done ($(tail -1 run_T5athr_${TAG_COND}.log))"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchT5athr] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
