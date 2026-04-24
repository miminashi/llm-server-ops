#!/usr/bin/env bash
# dry_probe_T5ats2.sh (v2) - Phase T-5a-ts2: B14 × -ts OOM 境界探索 (OT-b/OT-c 中心)
#
# 背景: attempt1 で OT-a (CPU から layer 2,3 除外) は CUDA0 に layer 2,3 expert が載り
#       ts=11,12,14,13 (22%) / 11,11,15,13 (22%) で 16,418 MiB OOM、10,12,15,13 (20%) は
#       model は fit するが flash-attention compute で CUDA0 OOM。
#       → OT を変更し layer 24, 39 を GPU 戻し (CUDA0 据え置き、CUDA2/3 に負荷集中) 方向へ。
#
# 6 件: D1-D4 = OT-b (layer 24,39 GPU)、D5-D6 = OT-c (layer 23,24 GPU)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

# OT-b: CPU = 2,3, 20-23, 31-38 (14 層、layer 24, 39 を GPU 戻し)
OT_B14_b='blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU'
# OT-c: CPU = 2,3, 20-22, 31-39 (14 層、layer 23, 24 を GPU 戻し)
OT_B14_c='blk\.([2-3]|2[0-2]|3[1-9])\.ffn_.*_exps\.weight=CPU'

# PROBES: "LABEL#OT_TAG#OT_REGEX#TS"
PROBES=(
  "D1#B14b#${OT_B14_b}#11,12,13,14"   # OT-b B16 最小差分 (CUDA3 +1)
  "D2#B14b#${OT_B14_b}#11,12,14,13"   # OT-b CUDA2 寄せ
  "D3#B14b#${OT_B14_b}#10,12,14,14"   # OT-b CUDA0 保険
  "D4#B14b#${OT_B14_b}#11,11,14,14"   # OT-b CUDA1 軽減
  "D5#B14c#${OT_B14_c}#11,12,13,14"   # OT-c (layer 23,24 GPU 戻し)
  "D6#B14c#${OT_B14_c}#11,12,14,13"   # OT-c CUDA2 寄せ
)

mkdir -p dry_logs

echo "[dry_probe_T5ats2 v2] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"

declare -A RESULT
for P in "${PROBES[@]}"; do
  IFS='#' read -r LABEL OT_TAG OT_REGEX TS <<< "$P"
  echo ""
  echo "[dry_probe v2] ================================"
  echo "[dry_probe v2] ${LABEL}: OT_TAG=${OT_TAG} TS=${TS:-(default)} at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[dry_probe v2] ================================"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  STDOUT_LOG="dry_logs/${LABEL}_stdout.log"
  TS_TAG="${TS:+_ts$(echo "$TS" | tr , -)}"
  REMOTE_LOG_NAME="llama-server_phaseT5_${OT_TAG}_t40_smlayer_kq8_0_vq8_0_fa1_ctx32768_b256_ub256${TS_TAG}.log"

  set +e
  timeout 240 env TS="$TS" OT_TAG="$OT_TAG" OT_REGEX="$OT_REGEX" \
    FLASH_ATTN=1 CTX_SIZE=32768 BATCH_SIZE=256 UB_SIZE=256 \
    CACHE_TYPE_K=q8_0 CACHE_TYPE_V=q8_0 SPLIT_MODE=layer THREADS=40 \
    bash start_phaseT5.sh > "$STDOUT_LOG" 2>&1
  RC=$?
  set -e

  echo "[dry_probe v2] start_phaseT5 rc=${RC}"
  case $RC in
    0) RESULT[$LABEL]="OK" ;;
    2) RESULT[$LABEL]="OOM(start)" ;;
    3) RESULT[$LABEL]="REJECT" ;;
    124) RESULT[$LABEL]="TIMEOUT" ;;  # timeout(1) exit
    *) RESULT[$LABEL]="OTHER(rc=${RC})" ;;
  esac

  # 常に remote log 取得 (OOM 原因解析用)
  ssh -o ConnectTimeout=10 "$HOST" "cat /tmp/${REMOTE_LOG_NAME} 2>/dev/null || true" \
    > "dry_logs/${LABEL}_server.log" 2>&1 || true

  # warmup 後 OOM の二次チェック (start_phaseT5 が healthy で抜けた場合でも warmup 中に崩れる可能性)
  if [ "$RC" -eq 0 ]; then
    sleep 3
    if grep -qE 'CUDA error: out of memory|cudaMalloc failed: out of memory' "dry_logs/${LABEL}_server.log" 2>/dev/null; then
      RESULT[$LABEL]="OOM(warmup)"
      echo "[dry_probe v2] ${LABEL}: post-start warmup OOM detected in server log"
    else
      ssh -o ConnectTimeout=10 "$HOST" "nvidia-smi --query-gpu=index,memory.total,memory.used,memory.free --format=csv" \
        > "dry_logs/${LABEL}_nvidia_smi.csv" 2>&1 || true
    fi
  fi

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo ""
echo "[dry_probe v2] ============== SUMMARY =============="
for P in "${PROBES[@]}"; do
  IFS='#' read -r LABEL OT_TAG OT_REGEX TS <<< "$P"
  echo "  ${LABEL}: OT=${OT_TAG} TS=${TS:-default} → ${RESULT[$LABEL]}"
done
echo "[dry_probe v2] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
