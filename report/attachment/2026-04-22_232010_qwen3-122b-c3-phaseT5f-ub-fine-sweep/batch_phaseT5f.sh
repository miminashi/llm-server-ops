#!/usr/bin/env bash
# batch_phaseT5f.sh - Phase T-5f: B28 × ctx=32k × ub 微細スイープ + drift bracket
# 9 条件 × (warmup 2 + 1k eval 5) = 63 measurement
#   1. B28_32k_ub512a (ub=512, drift 起点、T-5e 最良 16.380 の再現)
#   2. B28_32k_ub1586 (ub=1586, T-5/T-5e drift 補正基準)
#   3. B28_32k_ub1024 (ub=1024, Pareto 中間点)
#   4. B28_32k_ub768  (ub=768, Pareto knee 候補)
#   5. B28_32k_ub384  (ub=384, ub<512 trend 確認)
#   6. B28_32k_ub256  (ub=256, 新記録候補)
#   7. B28_32k_ub128  (ub=128, trend 延長)
#   8. B28_32k_ub64   (ub=64, 動作下限)
#   9. B28_32k_ub512z (ub=512, drift 終点)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p startup_logs

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

# 固定パラメータ (T-5e 最良継承: OT=B28, ctx=32k, KV=q8_0, SM=layer, threads=40, fa=1)
OT_TAG="B28"
OT_REGEX='blk\.([0-9]|1[0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
KV="q8_0"
SM="layer"
THR=40

# 条件定義: "LABEL#CTX#UB"
# LABEL で out_ ディレクトリを分離 (同一 ub でも drift 起点・終点を区別)
# 順序: drift 起点 → 高 ub → 低 ub → drift 終点 (線形 drift 仮定を強化する monotonic schedule)
CONDITIONS=(
  'B28_32k_ub512a#32768#512'
  'B28_32k_ub1586#32768#1586'
  'B28_32k_ub1024#32768#1024'
  'B28_32k_ub768#32768#768'
  'B28_32k_ub384#32768#384'
  'B28_32k_ub256#32768#256'
  'B28_32k_ub128#32768#128'
  'B28_32k_ub64#32768#64'
  'B28_32k_ub512z#32768#512'
)

# OOM/rejection 時 skip したい条件 (envvar SKIP_LABELS で指定、カンマ区切り)
SKIP_LABELS="${SKIP_LABELS:-}"

echo "[batchT5f] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
echo "[batchT5f] total conditions: ${#CONDITIONS[@]} (skip: ${SKIP_LABELS:-none})"

for COND in "${CONDITIONS[@]}"; do
  IFS='#' read -r LABEL CTX UB <<< "$COND"

  if [[ ",${SKIP_LABELS}," == *",${LABEL},"* ]]; then
    echo "[batchT5f] SKIP label=${LABEL} (per SKIP_LABELS)"
    continue
  fi

  TAG_COND="${LABEL}_t${THR}_kv${KV}_sm${SM}_ctx${CTX}_ub${UB}"
  echo "[batchT5f] ================================"
  echo "[batchT5f] cond: label=${LABEL} ctx=${CTX} ub=${UB} at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchT5f] ================================"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
    CACHE_TYPE_K="$KV" CACHE_TYPE_V="$KV" SPLIT_MODE="$SM" THREADS="$THR" \
    OT_TAG="$OT_TAG" OT_REGEX="$OT_REGEX" \
    bash start_phaseT5.sh > "start_stdout_T5f_${TAG_COND}.log" 2>&1 &
  START_PID=$!

  # ctx=32k は初期化 ~30s 程度。余裕を見て 60 × 5s = 300s 猶予
  healthy=0
  for i in $(seq 1 60); do
    if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
      echo "[batchT5f] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    if ! kill -0 "$START_PID" 2>/dev/null; then
      echo "[batchT5f] start_phaseT5.sh exited early for label=${LABEL}" >&2
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchT5f] ERROR: health never OK for label=${LABEL}" >&2
    tail -80 "start_stdout_T5f_${TAG_COND}.log" >&2 || true
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
    echo "[batchT5f] ERROR: PID not found for label=${LABEL}" >&2
    continue
  fi
  echo "[batchT5f] PID=$PID"

  # start_phaseT5.sh が書くリモートログ名を SCP で吸い上げ
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/llama-server_phaseT5_${OT_TAG}_t${THR}_sm${SM}_k${KV}_v${KV}_fa1_ctx${CTX}_b${UB}_ub${UB}.log" \
    > "startup_logs/T5f_${TAG_COND}.log"
  echo "[batchT5f] startup log saved ($(wc -l < startup_logs/T5f_${TAG_COND}.log) lines)"

  PID="$PID" TAG_PREFIX="T5f_${TAG_COND}" WARMUP_RUNS=2 EVAL_RUNS=5 \
    bash run_all.sh > "run_T5f_${TAG_COND}.log" 2>&1
  echo "[batchT5f] measure done ($(tail -1 run_T5f_${TAG_COND}.log))"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchT5f] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
