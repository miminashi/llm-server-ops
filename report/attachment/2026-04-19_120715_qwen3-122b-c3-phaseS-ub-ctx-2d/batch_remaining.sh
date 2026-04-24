#!/usr/bin/env bash
# Phase S S2-S8 一括計測バッチ
# 前提: S1 (ctx=32768, ub=512) は既に計測済み、サーバは停止済みであること
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${HOST:-t120h-p100}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

CONDS=(
  "32768 1024"
  "32768 4096"
  "32768 8192"
  "65536 512"
  "65536 1024"
  "65536 4096"
  "65536 8192"
)

echo "[batch] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"

for cond in "${CONDS[@]}"; do
  read -r CTX UB <<< "$cond"
  echo "[batch] ========================================"
  echo "[batch] cond: ctx=$CTX ub=$UB at $(TZ=Asia/Tokyo date +'%H:%M:%S')"
  echo "[batch] ========================================"

  # prior server stop (念のため)
  bash "$SKILL_STOP" "$HOST" 2>&1 | tail -5 || true
  sleep 5

  # 起動
  FLASH_ATTN=1 CTX_SIZE="$CTX" BATCH_SIZE="$UB" UB_SIZE="$UB" bash start_phaseS.sh 2>&1 | tail -10
  PID=$(ssh "$HOST" "ps -eo pid,comm | awk '\$2==\"llama-server\"{print \$1;exit}'" | tr -d '[:space:]')
  if [ -z "$PID" ]; then
    echo "[batch] ERROR: PID not found for ctx=$CTX ub=$UB, aborting batch" >&2
    exit 2
  fi
  echo "[batch] PID=$PID"

  # 起動ログ保存
  ssh "$HOST" "cat /tmp/llama-server_phaseS_fa1_ctx${CTX}_b${UB}_ub${UB}.log" \
    > "startup_logs/fa1_ctx${CTX}_b${UB}_ub${UB}.log"

  # 計測
  PID="$PID" TAG_PREFIX="S_f16_fa1_ctx${CTX}_b${UB}_ub${UB}" SIZES="warmup 1k" \
    GATE_SIZES="1k" GATE_MIB=1500 bash run_all.sh 2>&1 | tail -15

  # 停止
  bash "$SKILL_STOP" "$HOST" 2>&1 | tail -5 || true
  sleep 5
done

echo "[batch] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
