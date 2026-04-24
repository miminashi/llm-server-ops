#!/usr/bin/env bash
# Phase Sb-fa0 (拡張版) 12 条件バッチ計測
#   fa=0 × ctx ∈ {16384, 32768, 65536, 131072} × ub ∈ {1584, 1585, 1586}
#   f16 KV, numactl --cpunodebind=1 --membind=1, threads=40, poll=0 (Sbctx と fa 以外同一 baseline)
# startup_log の sched_reserve (compute buffer size) のみ取得、eval benchmark なし
# 目的: 候補 K (FA workspace の ub×ctx cross 項) 検証
# 失敗時は当該条件のみスキップして次へ（全体中断なし）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p startup_logs

HOST="${HOST:-t120h-p100}"
HEALTH_URL="${HEALTH_URL:-http://10.1.4.14:8000/health}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

# 順序: 小 ctx → 大 ctx (失敗時でも低 ctx データは確保できる設計)
CONDS=(
  "16384 1584"  "16384 1585"  "16384 1586"
  "32768 1584"  "32768 1585"  "32768 1586"
  "65536 1584"  "65536 1585"  "65536 1586"
  "131072 1584" "131072 1585" "131072 1586"
)

# ctx 依存タイムアウト (health 待機の最大反復数、1反復=5s)
health_iter_for() {
  case "$1" in
    16384)  echo 60 ;;   # 300s
    32768)  echo 75 ;;   # 375s
    65536)  echo 90 ;;   # 450s
    131072) echo 120 ;;  # 600s
    *)      echo 60 ;;
  esac
}

echo "[batchSbfa0] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
FAIL_LOG="batch_Sbfa0_failures.tsv"
: > "$FAIL_LOG"

for cond in "${CONDS[@]}"; do
  read -r CTX UB <<< "$cond"
  TAG="ctx${CTX}_ub${UB}"
  echo "[batchSbfa0] ================================"
  echo "[batchSbfa0] cond: $TAG at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batchSbfa0] ================================"

  # 1. 前セッション確実停止
  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  # 2. 起動（stdout を file に redirect、パイプハング回避）
  MAX_ITER=$(health_iter_for "$CTX")
  FLASH_ATTN=0 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" MAX_ITER="$MAX_ITER" \
    bash start_phaseSbfa0.sh > "start_stdout_Sbfa0_${TAG}.log" 2>&1 &
  START_PID=$!

  # 3. /health 待機
  healthy=0
  for i in $(seq 1 "$MAX_ITER"); do
    if curl -sf -m 5 "$HEALTH_URL" > /dev/null 2>&1; then
      echo "[batchSbfa0] /health OK after ${i}*5s"
      healthy=1
      break
    fi
    sleep 5
  done

  if [ "$healthy" -ne 1 ]; then
    echo "[batchSbfa0] ERROR: health never OK for $TAG" >&2
    printf "%s\ttimeout_%ds\n" "$TAG" "$((MAX_ITER*5))" >> "$FAIL_LOG"
    kill -9 "$START_PID" 2>/dev/null || true
    bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
    sleep 10
    continue
  fi

  # 4. start_phaseSbfa0.sh 終了待ち (最大 12s)
  for i in 1 2 3 4 5 6; do
    if ! kill -0 "$START_PID" 2>/dev/null; then break; fi
    sleep 2
  done
  kill "$START_PID" 2>/dev/null || true
  wait "$START_PID" 2>/dev/null || true

  # 5. startup log 取得
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
    "cat /tmp/llama-server_phaseSbfa0_fa0_ctx${CTX}_b${UB}_ub${UB}.log" \
    > "startup_logs/fa0_${TAG}.log" 2>/dev/null || true

  # 6. 健全性チェック
  if ! grep -q "CUDA0 compute buffer size" "startup_logs/fa0_${TAG}.log" 2>/dev/null; then
    echo "[batchSbfa0] WARN: sched_reserve missing for $TAG" >&2
    printf "%s\tsched_reserve_missing\n" "$TAG" >> "$FAIL_LOG"
  else
    cb_line=$(grep 'CUDA0 compute buffer size' "startup_logs/fa0_${TAG}.log" | head -1)
    echo "[batchSbfa0] startup log OK: ${cb_line}"
  fi

  # 7. 停止
  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
done

echo "[batchSbfa0] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
if [ -s "$FAIL_LOG" ]; then
  echo "[batchSbfa0] failures recorded in $FAIL_LOG:"
  cat "$FAIL_LOG"
else
  echo "[batchSbfa0] all 12 conditions succeeded"
fi
