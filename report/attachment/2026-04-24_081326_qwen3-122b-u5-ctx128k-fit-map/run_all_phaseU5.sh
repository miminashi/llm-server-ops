#!/usr/bin/env bash
# run_all_phaseU5.sh - Phase U-5 ロック確認 → batch_phaseU5.sh 実行 → Discord 通知
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${HOST:-t120h-p100}"
LOCK_SESSION_EXPECTED="${LOCK_SESSION_EXPECTED:-phaseU5}"
NOTIFY="/home/ubuntu/projects/llm-server-ops/.claude/skills/discord-notify/scripts/notify.sh"

# --- ロック確認 (既に取得済みであることを期待) ---
LOCK_HOLDER=$(ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
  "readlink /tmp/gpu-server-locks/${HOST}.lock 2>/dev/null || echo NO_LOCK")
echo "[run_all_phaseU5] lock holder: ${LOCK_HOLDER}"
if [ "$LOCK_HOLDER" != "$LOCK_SESSION_EXPECTED" ]; then
  echo "[run_all_phaseU5] ERROR: lock not held by '${LOCK_SESSION_EXPECTED}' (got '${LOCK_HOLDER}')" >&2
  exit 1
fi

START_TIME=$(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')
echo "[run_all_phaseU5] start at ${START_TIME}"

bash "$NOTIFY" "[Phase U-5] sweep 開始 (Tier-1 21 条件、~2.5 時間予想)" > /dev/null 2>&1 || true

# --- batch 実行 ---
set +e
bash batch_phaseU5.sh 2>&1 | tee batch_stdout.log
BATCH_RC=${PIPESTATUS[0]}
set -e

END_TIME=$(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')
echo "[run_all_phaseU5] end at ${END_TIME} (rc=${BATCH_RC})"

# --- 完了通知 ---
if [ -f phaseU5_results.csv ]; then
  TOTAL=$(tail -n +2 phaseU5_results.csv | wc -l)
  FITS=$(tail -n +2 phaseU5_results.csv | awk -F, '$6==1' | wc -l)
  FITS_128K=$(tail -n +2 phaseU5_results.csv | awk -F, '$6==1 && $4==131072' | wc -l)
  SUMMARY="[Phase U-5] sweep 完了: total=${TOTAL}, fit=${FITS}, ctx=131072 fit=${FITS_128K} (rc=${BATCH_RC})"
else
  SUMMARY="[Phase U-5] sweep 完了 (CSV 無し、rc=${BATCH_RC})"
fi
bash "$NOTIFY" "$SUMMARY" > /dev/null 2>&1 || true
echo "[run_all_phaseU5] ${SUMMARY}"

exit $BATCH_RC
