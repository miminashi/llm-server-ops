#!/usr/bin/env bash
# batch_phaseU6.sh - Phase U-6 (縮小版): 構成 × ub × prompt ループ
# 1 セル = 1 起動 (構成+ub) で複数 prompt を回す (prompt ごとに warmup/eval 数を個別設定)
#
# CELL フォーマット:
#   cell_id#COND_ID#OT_REGEX_VAR#UB#PROMPT_TAGS#MAX_TOKENS_LIST#WARMUPS_LIST#EVALS_LIST
#   ↑ PROMPT_TAGS, MAX_TOKENS_LIST, WARMUPS_LIST, EVALS_LIST は comma 区切り (同数の要素)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p startup_logs

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

KV="q8_0"
SM="layer"
THR=40
FA=1
CTX=131072
BATCH=2048
TS="11,12,13,14"

COOLDOWN="${COOLDOWN:-15}"

CSV="${SCRIPT_DIR}/phaseU6_results.csv"

OT_B14b='blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU'
OT_B18='blk\.([0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
OT_B20='blk\.([0-3]|19|2[0-4]|3[0-9])\.ffn_.*_exps\.weight=CPU'

# 縮小版行列:
# - B14b_ub256: 1k(w2+e5), 32k(w1+e2)    ← 96k は PP rate 43 t/s で budget 外
# - B14b_ub512: 1k(w2+e5), 32k(w1+e2), 96k(w1+e1)  ← 本命
# - B14b_ub1024: 1k(w2+e5), 32k(w1+e2), 96k(w1+e1)
# - B18_ub512: 1k(w2+e5)   ← B14b_ub512 の直接比較点
CELLS=(
  "B14b_ub256#B14b#OT_B14b#256#1k,32k#1024,512#2,1#5,2"
  "B14b_ub512#B14b#OT_B14b#512#1k,32k,96k#1024,512,256#2,1,1#5,2,1"
  "B14b_ub1024#B14b#OT_B14b#1024#1k,32k,96k#1024,512,256#2,1,1#5,2,1"
  "B18_ub512#B18#OT_B18#512#1k#1024#2#5"
)

SKIP_CELLS="${SKIP_CELLS:-}"

if [ ! -f "$CSV" ]; then
  echo "cell,cond,ub,prompt_tag,role,run_idx,eval_tps,prompt_tps,prompt_n,predicted_n,prompt_ms,predicted_ms,wallclock_sec,min_gpu_free_MiB,error" > "$CSV"
fi

START_EPOCH=$(date +%s)
echo "[U6] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
echo "[U6] total cells: ${#CELLS[@]}"

CELL_INDEX=0
for CELL_SPEC in "${CELLS[@]}"; do
  CELL_INDEX=$((CELL_INDEX + 1))
  IFS='#' read -r CELL_ID COND_ID OT_REGEX_VAR UB PROMPT_TAGS MAX_TOKENS_LIST WARMUPS_LIST EVALS_LIST <<< "$CELL_SPEC"

  if [[ ",${SKIP_CELLS}," == *",${CELL_ID},"* ]]; then
    echo "[U6] SKIP ${CELL_ID}"
    continue
  fi

  OT_REGEX="${!OT_REGEX_VAR}"

  TAG_CELL="U6_${CELL_ID}"

  echo ""
  echo "[U6] ==========================================="
  echo "[U6] (${CELL_INDEX}/${#CELLS[@]}) ${CELL_ID}: cond=${COND_ID} ub=${UB} prompts=${PROMPT_TAGS} warmups=${WARMUPS_LIST} evals=${EVALS_LIST}"
  ELAPSED_MIN=$(( ($(date +%s) - START_EPOCH) / 60 ))
  echo "[U6] at $(TZ=Asia/Tokyo date +'%H:%M:%S') (elapsed=${ELAPSED_MIN}m)"
  echo "[U6] ==========================================="

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  START_STDOUT="start_stdout_${TAG_CELL}.log"
  set +e
  TS="$TS" OT_TAG="$COND_ID" OT_REGEX="$OT_REGEX" \
    FLASH_ATTN="$FA" CTX_SIZE="$CTX" BATCH_SIZE="$BATCH" UB_SIZE="$UB" \
    CACHE_TYPE_K="$KV" CACHE_TYPE_V="$KV" SPLIT_MODE="$SM" THREADS="$THR" \
    EXTRA_TAG="" \
    bash start_phaseU6.sh > "$START_STDOUT" 2>&1
  START_RC=$?
  set -e

  STARTUP_SEC=$(grep -oE 'STARTUP_SEC=[0-9]+' "$START_STDOUT" | tail -1 | cut -d= -f2 || echo "")
  REMOTE_LOG_NAME=$(grep -oE 'REMOTE_LOG=[^ ]+' "$START_STDOUT" | tail -1 | cut -d= -f2 || echo "")

  if [ -n "$REMOTE_LOG_NAME" ]; then
    ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
      "cat ${REMOTE_LOG_NAME}" > "startup_logs/${TAG_CELL}_server.log" 2>&1 || true
  fi

  if [ $START_RC -ne 0 ]; then
    case $START_RC in
      1) EC="TIMEOUT" ;;
      2) EC="OOM_STARTUP" ;;
      3) EC="PARAM_REJECT" ;;
      *) EC="STARTUP_FAIL_${START_RC}" ;;
    esac
    echo "[U6] ${CELL_ID}: NOT-FIT (${EC}) - SKIP cell"
    printf "%s,%s,%s,%s,%s,%s,,,,,,,,%s\n" \
      "$CELL_ID" "$COND_ID" "$UB" "startup" "error" "0" "$EC" >> "$CSV"
    bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
    sleep 5
    continue
  fi

  PID=$(ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
  echo "[U6] ${CELL_ID}: PID=${PID} STARTUP_SEC=${STARTUP_SEC}"

  ssh -o ConnectTimeout=5 -o BatchMode=yes "$HOST" \
    "nvidia-smi --query-gpu=index,memory.free --format=csv,noheader,nounits" \
    > "startup_logs/${TAG_CELL}_gpu_start.csv" 2>&1 || true

  IFS=',' read -ra PROMPTS <<< "$PROMPT_TAGS"
  IFS=',' read -ra MAX_TOKS <<< "$MAX_TOKENS_LIST"
  IFS=',' read -ra WARMUPS <<< "$WARMUPS_LIST"
  IFS=',' read -ra EVALS <<< "$EVALS_LIST"

  SKIP_REST=0
  for idx in "${!PROMPTS[@]}"; do
    PROMPT_TAG="${PROMPTS[$idx]}"
    MAX_T="${MAX_TOKS[$idx]}"
    W="${WARMUPS[$idx]}"
    E="${EVALS[$idx]}"
    PROMPT_FILE="${SCRIPT_DIR}/prompts/prompt_${PROMPT_TAG}.txt"
    if [ ! -f "$PROMPT_FILE" ]; then
      echo "[U6] ${CELL_ID}: prompt file missing: $PROMPT_FILE" >&2
      continue
    fi

    SUB_CELL="${CELL_ID}_${PROMPT_TAG}"
    OUTDIR="${SCRIPT_DIR}/out_${SUB_CELL}"
    mkdir -p "$OUTDIR"

    if [ "$SKIP_REST" -eq 1 ]; then
      echo "[U6] ${CELL_ID}: skip ${PROMPT_TAG} (prior OOM)"
      printf "%s,%s,%s,%s,%s,%s,,,,,,,,%s\n" \
        "$SUB_CELL" "$COND_ID" "$UB" "$PROMPT_TAG" "skip" "0" "SKIPPED_AFTER_OOM" >> "$CSV"
      continue
    fi

    set +e
    CELL="$SUB_CELL" PID="$PID" OUTDIR="$OUTDIR" \
      PROMPT_TAG="$PROMPT_TAG" PROMPT_FILE="$PROMPT_FILE" \
      COND_ID="$COND_ID" UB="$UB" \
      WARMUP_RUNS="$W" EVAL_RUNS="$E" \
      EVAL_MAX_TOKENS="$MAX_T" COOLDOWN="$COOLDOWN" \
      CSV="$CSV" HOST="$HOST" \
      bash measure_phaseU6.sh 2>&1 | tee "${SCRIPT_DIR}/measure_${SUB_CELL}.log"
    M_RC=${PIPESTATUS[0]}
    set -e

    if [ -n "$REMOTE_LOG_NAME" ]; then
      if ssh -o ConnectTimeout=5 -o BatchMode=yes "$HOST" \
          "grep -qE 'cudaMalloc failed: out of memory|failed to allocate CUDA[0-9] buffer|graph_reserve: failed to allocate|CUDA error: out of memory|ggml_abort.*cuda' ${REMOTE_LOG_NAME} 2>/dev/null"; then
        echo "[U6] ${CELL_ID}: OOM during ${PROMPT_TAG} - skip remaining prompts in this cell"
        printf "%s,%s,%s,%s,%s,%s,,,,,,,,%s\n" \
          "$SUB_CELL" "$COND_ID" "$UB" "$PROMPT_TAG" "error" "0" "OOM_DURING_EVAL" >> "$CSV"
        SKIP_REST=1
      fi
    fi

    if [ $M_RC -ne 0 ]; then
      echo "[U6] ${CELL_ID}/${PROMPT_TAG}: measure returned ${M_RC}, continuing"
    fi
  done

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  ELAPSED_MIN=$(( ($(date +%s) - START_EPOCH) / 60 ))
  echo "[U6] ${CELL_ID} done (elapsed=${ELAPSED_MIN}m)"
done

echo ""
echo "[U6] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
echo "[U6] results: ${CSV}"
