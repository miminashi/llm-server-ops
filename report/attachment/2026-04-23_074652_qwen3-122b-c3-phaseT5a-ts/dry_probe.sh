#!/usr/bin/env bash
# dry_probe.sh - Phase T-5a-ts: -ts × OT の OOM 境界探索
# 5 件: D1 (B18 default), D2 (B18 ts_equal), D3 (B18 ts_skew), D4 (B16 ts1), D5 (B16 ts2)
# 各 起動→/health 待ち or OOM→nvidia-smi 取得→stop。eval 計測なし。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

# OT regex 定義
OT_B18='blk\.([0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'   # CPU 18層: 0-3, 20-24, 31-39
OT_B16='blk\.([2-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'   # CPU 16層: 2-3, 20-24, 31-39 (layer 0,1 を GPU 戻し)

# CONDITIONS: "LABEL#OT_TAG#OT_REGEX#TS"
PROBES=(
  "D1#B18#${OT_B18}#"                  # default = TS 未指定
  "D2#B18#${OT_B18}#15,11,10,13"       # default 等価明示 (実測 used 比 control)
  "D3#B18#${OT_B18}#13,11,12,13"       # CUDA0 -2GB
  "D4#B16#${OT_B16}#13,11,12,13"       # B16 第一候補
  "D5#B16#${OT_B16}#11,12,13,13"       # B16 第二候補 (CUDA0 更削減)
)

mkdir -p dry_logs

echo "[dry_probe] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"

declare -A RESULT
for P in "${PROBES[@]}"; do
  IFS='#' read -r LABEL OT_TAG OT_REGEX TS <<< "$P"
  echo ""
  echo "[dry_probe] ================================"
  echo "[dry_probe] ${LABEL}: OT_TAG=${OT_TAG} TS=${TS:-(default)} at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[dry_probe] ================================"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  STDOUT_LOG="dry_logs/${LABEL}_stdout.log"
  TS_TAG="${TS:+_ts$(echo "$TS" | tr , -)}"
  REMOTE_LOG_NAME="llama-server_phaseT5_${OT_TAG}_t40_smlayer_kq8_0_vq8_0_fa1_ctx32768_b256_ub256${TS_TAG}.log"

  set +e
  TS="$TS" OT_TAG="$OT_TAG" OT_REGEX="$OT_REGEX" \
    FLASH_ATTN=1 CTX_SIZE=32768 BATCH_SIZE=256 UB_SIZE=256 \
    CACHE_TYPE_K=q8_0 CACHE_TYPE_V=q8_0 SPLIT_MODE=layer THREADS=40 \
    bash start_phaseT5.sh > "$STDOUT_LOG" 2>&1
  RC=$?
  set -e

  echo "[dry_probe] start_phaseT5 rc=${RC}"
  case $RC in
    0) RESULT[$LABEL]="OK" ;;
    2) RESULT[$LABEL]="OOM" ;;
    3) RESULT[$LABEL]="REJECT" ;;
    *) RESULT[$LABEL]="OTHER(rc=${RC})" ;;
  esac

  # nvidia-smi 取得 (OK 時のみ)
  if [ "$RC" -eq 0 ]; then
    ssh -o ConnectTimeout=10 "$HOST" "nvidia-smi --query-gpu=index,memory.total,memory.used,memory.free --format=csv" \
      > "dry_logs/${LABEL}_nvidia_smi.csv" 2>&1 || true
    # remote log 取得 (compute_buf, sched_reserve, model size 等)
    ssh -o ConnectTimeout=10 "$HOST" "cat /tmp/${REMOTE_LOG_NAME}" \
      > "dry_logs/${LABEL}_server.log" 2>&1 || true
  else
    # OOM 時は server.log のみ取得 (失敗原因)
    ssh -o ConnectTimeout=10 "$HOST" "cat /tmp/${REMOTE_LOG_NAME} 2>/dev/null || true" \
      > "dry_logs/${LABEL}_server.log" 2>&1 || true
  fi

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo ""
echo "[dry_probe] ============== SUMMARY =============="
for P in "${PROBES[@]}"; do
  IFS='#' read -r LABEL OT_TAG OT_REGEX TS <<< "$P"
  echo "  ${LABEL}: OT=${OT_TAG} TS=${TS:-default} → ${RESULT[$LABEL]}"
done
echo "[dry_probe] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
