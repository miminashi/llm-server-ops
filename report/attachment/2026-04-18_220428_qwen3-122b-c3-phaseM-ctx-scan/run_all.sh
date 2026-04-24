#!/usr/bin/env bash
# Phase J 計測の一括実行 (flash-attn ON/OFF A/B)
# 事前: llama-server が t120h-p100 で FLASH_ATTN 指定済みで起動済み
#
# 環境変数:
#   PID         (必須) llama-server の PID
#   TAG_PREFIX  (必須) "J_fa1" or "J_fa0" 等
#   SIZES       (省略時: "warmup 1k 8k") 実行するサイズ空白区切り
#   GATE_SIZES  (省略時: "32k 64k 120k") run_gated で CUDA1 free チェックするサイズ
#   GATE_MIB    (省略時: 1500) CUDA1 free 閾値 MiB
#   HOST        (省略時: t120h-p100)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PID="${PID:?PID env required}"
TAG_PREFIX="${TAG_PREFIX:?TAG_PREFIX env required (e.g., J_fa1 or J_fa0)}"
SIZES="${SIZES:-warmup 1k 8k}"
GATE_SIZES="${GATE_SIZES:-32k 64k 120k}"
GATE_MIB="${GATE_MIB:-1500}"
HOST="${HOST:-t120h-p100}"

echo "[run_all] PID=${PID} TAG_PREFIX=${TAG_PREFIX} SIZES='${SIZES}' GATE_SIZES='${GATE_SIZES}' GATE_MIB=${GATE_MIB}"
MASTER_LOG="${SCRIPT_DIR}/run_all_${TAG_PREFIX}.log"
echo "[run_all] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')" | tee "$MASTER_LOG"

run() {
  local tag="$1"
  local spec="$2"
  local runs="$3"
  echo "[run_all] ==== $tag (runs=$runs) ====" | tee -a "$MASTER_LOG"
  RUNS="$runs" bash measure_phaseI.sh "$PID" "$tag" "$spec" 2>&1 | tee -a "$MASTER_LOG"
  echo "[run_all] ---- $tag done ----" | tee -a "$MASTER_LOG"
}

check_cuda1_free() {
  local threshold_mib="$1"
  local free
  free=$(ssh "$HOST" "nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits -i 1" \
    | tr -d '[:space:]')
  if [ "${free:-0}" -lt "$threshold_mib" ]; then
    echo "[gate] CUDA1 free=${free} MiB < ${threshold_mib}, SKIP" | tee -a "$MASTER_LOG"
    return 1
  fi
  echo "[gate] CUDA1 free=${free} MiB >= ${threshold_mib}, proceed" | tee -a "$MASTER_LOG"
  return 0
}

run_gated() {
  local tag="$1" spec="$2" runs="$3"
  if check_cuda1_free "$GATE_MIB"; then
    run "$tag" "$spec" "$runs"
  else
    echo "[run_all] SKIPPED $tag (memory gate)" | tee -a "$MASTER_LOG"
  fi
}

is_gated() {
  local size="$1"
  for gs in $GATE_SIZES; do
    if [ "$size" = "$gs" ]; then return 0; fi
  done
  return 1
}

spec_for_size() {
  local size="$1"
  case "$size" in
    warmup|post) echo 'Write a short haiku about autumn.' ;;
    *) echo "@${SCRIPT_DIR}/prompts/prompt_${size}.txt" ;;
  esac
}

runs_for_size() {
  local size="$1"
  case "$size" in
    warmup|post) echo 3 ;;
    1k|8k) echo 3 ;;
    32k) echo 2 ;;
    64k|120k) echo 1 ;;
    *) echo 1 ;;
  esac
}

for size in $SIZES; do
  tag="${TAG_PREFIX}_${size}"
  spec=$(spec_for_size "$size")
  runs=$(runs_for_size "$size")
  if is_gated "$size"; then
    run_gated "$tag" "$spec" "$runs"
  else
    run "$tag" "$spec" "$runs"
  fi
done

echo "[run_all] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')" | tee -a "$MASTER_LOG"
