#!/usr/bin/env bash
# drive.sh - 条件リストを順次実行 (各条件で run_cond.sh)。health 失敗時も次へ継続。
# usage: CSV=<path> DEVS=0,1,2 WARM=2 EVALN=5 MAXTOK=256 LIST=<file> bash drive.sh
set -uo pipefail
BENCH=/tmp/mi25vk_bench
CSV="${CSV:?}"; DEVS="${DEVS:?}"; LIST="${LIST:?}"
WARM="${WARM:-2}"; EVALN="${EVALN:-5}"; MAXTOK="${MAXTOK:-256}"
ts() { TZ=Asia/Tokyo date +%H:%M:%S; }

# CSV ヘッダ (無ければ)
[ -s "$CSV" ] || echo "CELL,COND_ID,UB,PROMPT_TAG,role,idx,eval_tps,prompt_tps,prompt_n,predicted_n,prompt_ms,predicted_ms,wallclock,max_gpu_used,err" > "$CSV"

# FD 3 から読む (run_cond/ssh が stdin=FD0 を消費してもループが壊れないように)
while IFS='|' read -r -u 3 COND ENVX OVR TAG; do
  [ -z "${COND// }" ] && continue
  case "$COND" in \#*) continue;; esac
  COND="${COND// }"; TAG="${TAG// }"
  echo "[$(ts)] ===== DRIVE $COND (tag=$TAG) ====="
  COND_ID="$COND" CELL="${COND}_${TAG}" TAG="$TAG" MAXTOK="$MAXTOK" \
    WARM="$WARM" EVALN="$EVALN" DEVS="$DEVS" CSV="$CSV" \
    ENV_EXTRA="$ENVX" OVERRIDE="$OVR" \
    bash "$BENCH/run_cond.sh" </dev/null || echo "[$(ts)] $COND returned non-zero (continue)"
done 3< "$LIST"
echo "[$(ts)] ===== DRIVE LIST COMPLETE ====="
