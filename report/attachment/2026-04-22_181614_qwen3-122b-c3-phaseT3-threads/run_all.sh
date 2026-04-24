#!/usr/bin/env bash
# run_all.sh (Phase S-eval) — warmup N + 1k M 連続実行
# 環境変数:
#   PID           (必須)
#   TAG_PREFIX    (必須) 例 "Seval_fa1_ctx32768_ub1586"
#   WARMUP_RUNS   (省略時 2) 「warmup」として記録する早期 run 数
#   EVAL_RUNS     (省略時 5) 「1k」として記録する計測 run 数
#   COOLDOWN      (省略時 60) run 間のクールダウン秒
#   HOST          (省略時 t120h-p100)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PID="${PID:?PID env required}"
TAG_PREFIX="${TAG_PREFIX:?TAG_PREFIX env required}"
WARMUP_RUNS="${WARMUP_RUNS:-2}"
EVAL_RUNS="${EVAL_RUNS:-5}"
COOLDOWN="${COOLDOWN:-60}"
HOST="${HOST:-t120h-p100}"

MASTER_LOG="${SCRIPT_DIR}/run_all_${TAG_PREFIX}.log"
echo "[run_all] PID=${PID} TAG_PREFIX=${TAG_PREFIX} WARMUP_RUNS=${WARMUP_RUNS} EVAL_RUNS=${EVAL_RUNS}" | tee "$MASTER_LOG"
echo "[run_all] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')" | tee -a "$MASTER_LOG"

export HOST COOLDOWN

run_measure() {
  local tag="$1"
  local spec="$2"
  local runs="$3"
  echo "[run_all] ==== $tag (runs=$runs) ====" | tee -a "$MASTER_LOG"
  RUNS="$runs" bash measure_phaseT3.sh "$PID" "$tag" "$spec" 2>&1 | tee -a "$MASTER_LOG"
  echo "[run_all] ---- $tag done ----" | tee -a "$MASTER_LOG"
}

# warmup（短 prompt）
run_measure "${TAG_PREFIX}_warmup" "Write a short haiku about autumn." "$WARMUP_RUNS"

# 1k 評価
run_measure "${TAG_PREFIX}_1k" "@${SCRIPT_DIR}/prompts/prompt_1k.txt" "$EVAL_RUNS"

echo "[run_all] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')" | tee -a "$MASTER_LOG"
