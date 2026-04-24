#!/usr/bin/env bash
# run_all_phaseU6.sh - Phase U-6 ロック確認 → batch_phaseU6.sh 実行 → Discord 通知
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${HOST:-t120h-p100}"
LOCK_SESSION_EXPECTED="${LOCK_SESSION_EXPECTED:-phaseU6}"
NOTIFY="/home/ubuntu/projects/llm-server-ops/.claude/skills/discord-notify/scripts/notify.sh"

# --- ロック確認 ---
LOCK_HOLDER=$(ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
  "readlink /tmp/gpu-server-locks/${HOST}.lock 2>/dev/null || echo NO_LOCK")
echo "[run_all_phaseU6] lock holder: ${LOCK_HOLDER}"
if [ "$LOCK_HOLDER" != "$LOCK_SESSION_EXPECTED" ]; then
  echo "[run_all_phaseU6] ERROR: lock not held by '${LOCK_SESSION_EXPECTED}' (got '${LOCK_HOLDER}')" >&2
  exit 1
fi

START_TIME=$(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')
echo "[run_all_phaseU6] start at ${START_TIME}"

bash "$NOTIFY" "[Phase U-6] ctx=128k default bench 開始 (15 セル × 7 run = 105 run、~2.5h 予想)" > /dev/null 2>&1 || true

set +e
bash batch_phaseU6.sh 2>&1 | tee batch_stdout.log
BATCH_RC=${PIPESTATUS[0]}
set -e

END_TIME=$(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')
echo "[run_all_phaseU6] end at ${END_TIME} (rc=${BATCH_RC})"

if [ -f phaseU6_results.csv ]; then
  EVAL_ROWS=$(awk -F, '$5=="eval"' phaseU6_results.csv | wc -l)
  ERR_ROWS=$(awk -F, '$5=="error" || $5=="skip"' phaseU6_results.csv | wc -l)
  SUMMARY="[Phase U-6] bench 完了: eval_rows=${EVAL_ROWS}, err/skip=${ERR_ROWS} (rc=${BATCH_RC})"
else
  SUMMARY="[Phase U-6] bench 完了 (CSV 無し、rc=${BATCH_RC})"
fi
bash "$NOTIFY" "$SUMMARY" > /dev/null 2>&1 || true
echo "[run_all_phaseU6] ${SUMMARY}"

exit $BATCH_RC
