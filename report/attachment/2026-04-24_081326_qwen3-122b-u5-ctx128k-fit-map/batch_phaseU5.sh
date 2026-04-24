#!/usr/bin/env bash
# batch_phaseU5.sh - Phase U-5 dry-probe 21 条件ループ
# 1 条件 = stop → start → (wait /health or OOM) → probe (nvidia-smi + warm /completions) → stop
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p startup_logs

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

KV="q8_0"
SM="layer"
UB=256
THR=40
FA=1

CSV="${SCRIPT_DIR}/phaseU5_results.csv"

# OT regex 定義
OT_B14b='blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU'
OT_B16='blk\.([2-3]|2[0-4]|3[0-8])\.ffn_.*_exps\.weight=CPU'
OT_B18='blk\.([0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
OT_B20='blk\.([0-3]|19|2[0-4]|3[0-9])\.ffn_.*_exps\.weight=CPU'
OT_B24='blk\.([0-4]|1[6-9]|2[0-4]|3[0-9])\.ffn_.*_exps\.weight=CPU'

# CONDITIONS フォーマット: cond_id#OT_TAG#CPU_LAYERS#CTX#TS_VALUE#OT_REGEX_NAME
# TS_VALUE が "default" なら --tensor-split を省略
CONDITIONS=(
  "T1-01#B14b#14#32768#11,12,13,14#OT_B14b"
  "T1-02#B14b#14#65536#11,12,13,14#OT_B14b"
  "T1-03#B14b#14#98304#11,12,13,14#OT_B14b"
  "T1-04#B14b#14#131072#11,12,13,14#OT_B14b"
  "T1-05#B16#16#65536#11,12,13,14#OT_B16"
  "T1-06#B16#16#98304#11,12,13,14#OT_B16"
  "T1-07#B16#16#131072#11,12,13,14#OT_B16"
  "T1-08#B18#18#32768#11,14,14,11#OT_B18"
  "T1-09#B18#18#65536#11,12,13,14#OT_B18"
  "T1-10#B18#18#98304#11,12,13,14#OT_B18"
  "T1-11#B18#18#131072#11,12,13,14#OT_B18"
  "T1-12#B20#20#65536#11,12,13,14#OT_B20"
  "T1-13#B20#20#98304#11,12,13,14#OT_B20"
  "T1-14#B20#20#131072#11,12,13,14#OT_B20"
  "T1-15#B24#24#98304#11,12,13,14#OT_B24"
  "T1-16#B24#24#131072#11,12,13,14#OT_B24"
  "T1-17#B14b#14#131072#11,14,14,11#OT_B14b"
  "T1-18#B18#18#131072#11,14,14,11#OT_B18"
  "T1-19#B20#20#131072#11,14,14,11#OT_B20"
  "T1-20#B14b#14#131072#default#OT_B14b"
  "T1-21#B18#18#131072#12,14,14,10#OT_B18"
)

SKIP_IDS="${SKIP_IDS:-}"

# CSV ヘッダ (新規 or append)
if [ ! -f "$CSV" ]; then
  echo "condition_id,OT_name,CPU_layers,ctx,ts,fit,startup_sec,GPU0_free_static_MiB,GPU1_free_static_MiB,GPU2_free_static_MiB,GPU3_free_static_MiB,min_GPU_free_static_MiB,GPU0_free_after_probe_MiB,GPU1_free_after_probe_MiB,GPU2_free_after_probe_MiB,GPU3_free_after_probe_MiB,min_GPU_free_after_probe_MiB,error_class,error_msg" > "$CSV"
fi

echo "[U5] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
echo "[U5] total conditions: ${#CONDITIONS[@]}"

COND_INDEX=0
for COND in "${CONDITIONS[@]}"; do
  COND_INDEX=$((COND_INDEX + 1))
  IFS='#' read -r COND_ID OT_TAG CPU_LAYERS CTX TS_VAL OT_REGEX_VAR <<< "$COND"

  if [[ ",${SKIP_IDS}," == *",${COND_ID},"* ]]; then
    echo "[U5] SKIP ${COND_ID}"
    continue
  fi

  OT_REGEX="${!OT_REGEX_VAR}"

  if [ "$TS_VAL" = "default" ]; then
    TS_ARG=""
    TS_LABEL="default"
  else
    TS_ARG="$TS_VAL"
    TS_LABEL="$TS_VAL"
  fi

  TS_TAG=$(echo "$TS_LABEL" | tr , -)
  TAG_COND="U5_${COND_ID}_${OT_TAG}_ctx${CTX}_ts${TS_TAG}"

  echo ""
  echo "[U5] ==========================================="
  echo "[U5] (${COND_INDEX}/${#CONDITIONS[@]}) ${COND_ID}: OT=${OT_TAG} CPU=${CPU_LAYERS} ctx=${CTX} ts=${TS_LABEL}"
  echo "[U5] at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[U5] ==========================================="

  # 既存 llama-server を停止
  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  # 起動 (OOM 時も batch を止めないため set -e の影響を避ける)
  START_STDOUT="start_stdout_${TAG_COND}.log"
  set +e
  TS="$TS_ARG" OT_TAG="$OT_TAG" OT_REGEX="$OT_REGEX" \
    FLASH_ATTN="$FA" CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" \
    CACHE_TYPE_K="$KV" CACHE_TYPE_V="$KV" SPLIT_MODE="$SM" THREADS="$THR" \
    EXTRA_ARGS="" EXTRA_TAG="" \
    bash start_phaseU5.sh > "$START_STDOUT" 2>&1
  START_RC=$?
  set -e

  # remote log のファイル名 (start_phaseU5.sh と合わせる)
  TS_FILE_TAG="${TS_ARG:+_ts$(echo "$TS_ARG" | tr , -)}"
  REMOTE_LOG_NAME="llama-server_phaseU5_${OT_TAG}_t${THR}_sm${SM}_k${KV}_v${KV}_fa${FA}_ctx${CTX}_b${UB}_ub${UB}${TS_FILE_TAG}.log"

  # startup log 取得 (fit/unfit 問わず)
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/${REMOTE_LOG_NAME}" > "startup_logs/${TAG_COND}_server.log" 2>&1 || true

  STARTUP_SEC=$(grep -oE 'STARTUP_SEC=[0-9]+' "$START_STDOUT" | tail -1 | cut -d= -f2 || echo "")
  if [ -z "$STARTUP_SEC" ]; then STARTUP_SEC="-1"; fi

  ERROR_CLASS=""
  ERROR_MSG=""
  FIT=0
  STATIC_FREE=",,,"
  AFTER_FREE=",,,"

  if [ $START_RC -ne 0 ]; then
    case $START_RC in
      1) ERROR_CLASS="TIMEOUT"; ERROR_MSG="health not OK in 300s" ;;
      2) ERROR_CLASS="OOM_STARTUP"; ERROR_MSG="OOM regex hit during startup" ;;
      3) ERROR_CLASS="PARAM_REJECT"; ERROR_MSG="llama.cpp rejected params" ;;
      *) ERROR_CLASS="STARTUP_FAIL_${START_RC}"; ERROR_MSG="start_phaseU5.sh exit ${START_RC}" ;;
    esac
    echo "[U5] ${COND_ID}: NOT-FIT (${ERROR_CLASS})"
  else
    # 正常起動 → probe
    PROBE_OUT="probe_stdout_${TAG_COND}.log"
    TAG_COND="$TAG_COND" SAVE_DIR="${SCRIPT_DIR}/startup_logs" HOST="$HOST" \
      bash probe_vram.sh > "$PROBE_OUT" 2>&1 || true

    STATIC_FREE=$(grep -oE 'STATIC_FREE="[^"]*"' "$PROBE_OUT" | tail -1 | sed 's/STATIC_FREE="//; s/"$//')
    AFTER_FREE=$(grep -oE 'AFTER_FREE="[^"]*"' "$PROBE_OUT" | tail -1 | sed 's/AFTER_FREE="//; s/"$//')
    PROBE_STATUS=$(grep -oE 'PROBE_STATUS=[A-Z_]+' "$PROBE_OUT" | tail -1 | cut -d= -f2)

    if [ -z "$STATIC_FREE" ]; then STATIC_FREE=",,,"; fi
    if [ -z "$AFTER_FREE" ]; then AFTER_FREE=",,,"; fi

    if [ "$PROBE_STATUS" = "OK" ]; then
      ERROR_CLASS="OK"
      FIT=1
      echo "[U5] ${COND_ID}: FIT (static=${STATIC_FREE} after=${AFTER_FREE})"
    else
      ERROR_CLASS="$PROBE_STATUS"
      ERROR_MSG="probe status ${PROBE_STATUS}"
      echo "[U5] ${COND_ID}: NOT-FIT (${ERROR_CLASS})"
    fi
  fi

  # 4 GPU 分に分解 (足りない列は空文字)
  GS0=$(echo "$STATIC_FREE" | cut -d, -f1); GS1=$(echo "$STATIC_FREE" | cut -d, -f2)
  GS2=$(echo "$STATIC_FREE" | cut -d, -f3); GS3=$(echo "$STATIC_FREE" | cut -d, -f4)
  GA0=$(echo "$AFTER_FREE" | cut -d, -f1); GA1=$(echo "$AFTER_FREE" | cut -d, -f2)
  GA2=$(echo "$AFTER_FREE" | cut -d, -f3); GA3=$(echo "$AFTER_FREE" | cut -d, -f4)

  # min free 計算
  compute_min() {
    echo "$1" | awk -F, 'BEGIN{m=999999} {for(i=1;i<=NF;i++){ if($i!="" && $i+0<m) m=$i+0}} END{if(m==999999) print ""; else print m}'
  }
  MIN_STATIC=$(compute_min "$STATIC_FREE")
  MIN_AFTER=$(compute_min "$AFTER_FREE")

  ERROR_MSG_CSV=$(echo "$ERROR_MSG" | tr ',' ';')
  printf "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n" \
    "$COND_ID" "$OT_TAG" "$CPU_LAYERS" "$CTX" "$TS_LABEL" "$FIT" "$STARTUP_SEC" \
    "$GS0" "$GS1" "$GS2" "$GS3" "$MIN_STATIC" \
    "$GA0" "$GA1" "$GA2" "$GA3" "$MIN_AFTER" \
    "$ERROR_CLASS" "$ERROR_MSG_CSV" >> "$CSV"

  # 次条件に備えて停止
  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo ""
echo "[U5] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
echo "[U5] results: ${CSV}"
