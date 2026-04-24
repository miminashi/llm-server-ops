#!/usr/bin/env bash
# batch_phaseT5a.sh - Phase T-5a: OT 再配分 (B28 → B24/B20/B18) + drift bracket
# 7 条件 × (warmup 2 + 1k eval 5) = 49 measurement (B18 OOM 時 42)
#   1. B28_run1 (drift 起点、T-5f 16.455 再現確認)
#   2. B24_run1 (+4 層 GPU 戻し)
#   3. B20_run1 (+8 層、境界付近)
#   4. B18_run1 (OOM 境界テスト、OOM なら SKIP_LABELS=B18_run1 で skip)
#   5. B20_run2 (B20 再現性)
#   6. B24_run2 (B24 再現性)
#   7. B28_run2 (drift 終点)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p startup_logs

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

# 固定パラメータ (T-5f 最良継承: ctx=32k, ub=512, KV=q8_0, SM=layer, threads=40, fa=1)
KV="q8_0"
SM="layer"
THR=40
UB=512
CTX=32768

# 条件定義: "LABEL#CTX#UB#OT_TAG#OT_REGEX"
# 順序: drift 起点 → 主候補降順 (層数減) → 再現 → drift 終点
CONDITIONS=(
  'B28_run1#32768#512#B28#blk\.([0-9]|1[0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
  'B24_run1#32768#512#B24#blk\.([0-9]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
  'B20_run1#32768#512#B20#blk\.([0-5]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
  'B18_run1#32768#512#B18#blk\.([0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
  'B20_run2#32768#512#B20#blk\.([0-5]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
  'B24_run2#32768#512#B24#blk\.([0-9]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
  'B28_run2#32768#512#B28#blk\.([0-9]|1[0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
)

# OOM/rejection 時 skip したい条件 (envvar SKIP_LABELS で指定、カンマ区切り)
SKIP_LABELS="${SKIP_LABELS:-}"

echo "[batchT5a] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
echo "[batchT5a] total conditions: ${#CONDITIONS[@]} (skip: ${SKIP_LABELS:-none})"

for COND in "${CONDITIONS[@]}"; do
  IFS='#' read -r LABEL C_CTX C_UB C_OT_TAG C_OT_REGEX <<< "$COND"

  if [[ ",${SKIP_LABELS}," == *",${LABEL},"* ]]; then
    echo "[batchT5a] SKIP label=${LABEL} (per SKIP_LABELS)"
    continue
  fi

  TAG_COND="${LABEL}_${C_OT_TAG}_t${THR}_kv${KV}_sm${SM}_ctx${C_CTX}_ub${C_UB}"
  echo "[batchT5a] ================================"
  echo "[batchT5a] cond: label=${LABEL} ot=${C_OT_TAG} ctx=${C_CTX} ub=${C_UB} at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchT5a] OT_REGEX=${C_OT_REGEX}"
  echo "[batchT5a] ================================"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  FLASH_ATTN=1 CTX_SIZE="$C_CTX" BATCH_SIZE="$C_UB" UB_SIZE="$C_UB" \
    CACHE_TYPE_K="$KV" CACHE_TYPE_V="$KV" SPLIT_MODE="$SM" THREADS="$THR" \
    OT_TAG="$C_OT_TAG" OT_REGEX="$C_OT_REGEX" \
    bash start_phaseT5.sh > "start_stdout_T5a_${TAG_COND}.log" 2>&1 &
  START_PID=$!

  # ctx=32k は初期化 ~30s 程度。余裕を見て 60 × 5s = 300s 猶予
  healthy=0
  for i in $(seq 1 60); do
    if curl -sf -m 5 http://10.1.4.14:8000/health > /dev/null 2>&1; then
      echo "[batchT5a] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    if ! kill -0 "$START_PID" 2>/dev/null; then
      echo "[batchT5a] start_phaseT5.sh exited early for label=${LABEL}" >&2
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchT5a] ERROR: health never OK for label=${LABEL}" >&2
    tail -80 "start_stdout_T5a_${TAG_COND}.log" >&2 || true
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
    echo "[batchT5a] ERROR: PID not found for label=${LABEL}" >&2
    continue
  fi
  echo "[batchT5a] PID=$PID"

  # start_phaseT5.sh が書くリモートログ名 (ただし OT_TAG を含めるため OT_TAG 変数に合わせて命名)
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/llama-server_phaseT5_${C_OT_TAG}_t${THR}_sm${SM}_k${KV}_v${KV}_fa1_ctx${C_CTX}_b${C_UB}_ub${C_UB}.log" \
    > "startup_logs/T5a_${TAG_COND}.log"
  echo "[batchT5a] startup log saved ($(wc -l < startup_logs/T5a_${TAG_COND}.log) lines)"

  PID="$PID" TAG_PREFIX="T5a_${TAG_COND}" WARMUP_RUNS=2 EVAL_RUNS=5 \
    bash run_all.sh > "run_T5a_${TAG_COND}.log" 2>&1
  echo "[batchT5a] measure done ($(tail -1 run_T5a_${TAG_COND}.log))"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchT5a] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
