#!/usr/bin/env bash
# Phase Sb-fa0-offload バッチ: OT_REGEX 拡張による fa=0 × ctx≥32k 実現
#   Stage 1: ctx=32k × ub=1584 で OT 案 X1 → X4 の escalation（最初に起動成立した案を採用）
#   Stage 2: 確定 OT × ctx=32k × ub ∈ {1584, 1585, 1586}  [★最優先, δ 項 fa 依存性]
#   Stage 3: 確定 OT × ctx ∈ {65536, 131072} × ub ∈ {1584, 1585, 1586}  [副次, 残時間依存]
#   Stage 4: 確定 OT × ctx=16k × ub ∈ {1584, 1585, 1586}  [比較, slope 影響確認]
# 失敗条件の OOM alloc size は batch_Sbfa0offload_oom.tsv に記録（派生 slope 用）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p startup_logs

HOST="${HOST:-t120h-p100}"
HEALTH_URL="${HEALTH_URL:-http://10.1.4.14:8000/health}"
SKILL_STOP="/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh"

# OT 案 escalation ladder（既存 MoE オフロードと OR 結合、カンマ区切り）
MOE_OT='blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'
declare -A OT_REGEX_MAP
OT_REGEX_MAP[X1]="${MOE_OT},blk\\.(2[0-3])\\.attn_.*\\.weight=CPU"
OT_REGEX_MAP[X2]="${MOE_OT},blk\\.(1[6-9]|2[0-3])\\.attn_.*\\.weight=CPU"
OT_REGEX_MAP[X3]="${MOE_OT},blk\\.(1[2-9]|2[0-3])\\.attn_.*\\.weight=CPU"
OT_REGEX_MAP[X4]="${MOE_OT},blk\\.([0-9]|[1-4][0-9])\\.attn_.*\\.weight=CPU"
OT_ORDER=(X1 X2 X3 X4)

START_EPOCH=$(date +%s)
TIMEBOX_SEC=2400   # 40 分
timebox_remaining() {
  echo $(( START_EPOCH + TIMEBOX_SEC - $(date +%s) ))
}

health_iter_for() {
  case "$1" in
    16384)  echo 60 ;;
    32768)  echo 75 ;;
    65536)  echo 90 ;;
    131072) echo 120 ;;
    *)      echo 60 ;;
  esac
}

FAIL_LOG="batch_Sbfa0offload_failures.tsv"
OOM_LOG="batch_Sbfa0offload_oom.tsv"
: > "$FAIL_LOG"
: > "$OOM_LOG"
printf "tag\tctx\tub\tot_tag\tdevice\talloc_MiB\n" > "$OOM_LOG"

extract_oom() {
  # $1: startup log path, $2: tag, $3: ctx, $4: ub, $5: ot_tag
  local lp="$1" tag="$2" ctx="$3" ub="$4" otag="$5"
  if [ -f "$lp" ]; then
    grep -E 'allocating [0-9.]+ MiB on device [0-9]' "$lp" 2>/dev/null | \
      while IFS= read -r line; do
        # 例: "ggml_cuda_host_malloc: ... allocating 6744.41 MiB on device 1: cudaMalloc failed"
        local mib dev
        mib=$(echo "$line" | grep -oE 'allocating [0-9.]+ MiB' | grep -oE '[0-9.]+')
        dev=$(echo "$line" | grep -oE 'on device [0-9]' | grep -oE '[0-9]$')
        printf "%s\t%s\t%s\t%s\t%s\t%s\n" "$tag" "$ctx" "$ub" "$otag" "$dev" "$mib" >> "$OOM_LOG"
      done
  fi
}

run_condition() {
  # $1: ctx, $2: ub, $3: ot_tag, $4: ot_regex
  local ctx="$1" ub="$2" otag="$3" ot_regex="$4"
  local tag="${otag}_ctx${ctx}_ub${ub}"
  local max_iter
  max_iter=$(health_iter_for "$ctx")

  echo "[batchSbfa0offload] -- run: ctx=${ctx} ub=${ub} OT_TAG=${otag} max_iter=${max_iter} at $(TZ=Asia/Tokyo date +'%H:%M:%S')"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5

  FLASH_ATTN=0 CTX_SIZE="$ctx" BATCH_SIZE="$ub" UB_SIZE="$ub" \
    MAX_ITER="$max_iter" OT_TAG="$otag" OT_REGEX="$ot_regex" \
    bash start_phaseSbfa0offload.sh > "start_stdout_${tag}.log" 2>&1 &
  local start_pid=$!

  local healthy=0
  for i in $(seq 1 "$max_iter"); do
    if curl -sf -m 5 "$HEALTH_URL" > /dev/null 2>&1; then
      echo "[batchSbfa0offload] /health OK after ${i}*5s (${tag})"
      healthy=1
      break
    fi
    # start 側で OOM/ub-reject 検出時は早期終了している。kill -0 でプロセス生死判定
    if ! kill -0 "$start_pid" 2>/dev/null; then
      wait "$start_pid" 2>/dev/null || true
      break
    fi
    sleep 5
  done

  for i in 1 2 3 4 5 6; do
    if ! kill -0 "$start_pid" 2>/dev/null; then break; fi
    sleep 2
  done
  kill "$start_pid" 2>/dev/null || true
  wait "$start_pid" 2>/dev/null || true

  local remote_log="/tmp/llama-server_phaseSbfa0offload_${otag}_fa0_ctx${ctx}_b${ub}_ub${ub}.log"
  local local_log="startup_logs/fa0offload_${tag}.log"
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" "cat ${remote_log}" > "$local_log" 2>/dev/null || true

  if [ "$healthy" -ne 1 ]; then
    echo "[batchSbfa0offload] FAIL: ${tag} not healthy" >&2
    printf "%s\tfail_timeout_or_oom\n" "$tag" >> "$FAIL_LOG"
    extract_oom "$local_log" "$tag" "$ctx" "$ub" "$otag"
    bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
    sleep 5
    return 1
  fi

  if ! grep -q "CUDA0 compute buffer size" "$local_log" 2>/dev/null; then
    echo "[batchSbfa0offload] WARN: sched_reserve missing for ${tag}" >&2
    printf "%s\tsched_reserve_missing\n" "$tag" >> "$FAIL_LOG"
    bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
    sleep 5
    return 1
  fi

  local cb
  cb=$(grep 'CUDA0 compute buffer size' "$local_log" | head -1)
  echo "[batchSbfa0offload] OK (${tag}): ${cb}"

  bash "$SKILL_STOP" "$HOST" > /dev/null 2>&1 || true
  sleep 5
  return 0
}

echo "[batchSbfa0offload] start at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S'), TIMEBOX=${TIMEBOX_SEC}s"

# ----- Stage 1: pilot escalation (ctx=32k × ub=1584) -----
echo "[batchSbfa0offload] === Stage 1: pilot escalation ==="
FINAL_OT_TAG=""
FINAL_OT_REGEX=""
for otag in "${OT_ORDER[@]}"; do
  echo "[batchSbfa0offload] [escalation] trying OT_TAG=${otag}"
  if run_condition 32768 1584 "$otag" "${OT_REGEX_MAP[$otag]}"; then
    FINAL_OT_TAG="$otag"
    FINAL_OT_REGEX="${OT_REGEX_MAP[$otag]}"
    echo "[batchSbfa0offload] [escalation] ${otag} SUCCESS, adopting as FINAL_OT_TAG"
    break
  fi
  echo "[batchSbfa0offload] [escalation] ${otag} FAILED, escalating"
done

if [ -z "$FINAL_OT_TAG" ]; then
  echo "[batchSbfa0offload] Stage 1: all OT escalation failed for ctx=32k. Fallback to ctx=16k × X4 for baseline." >&2
  FINAL_OT_TAG="X4"
  FINAL_OT_REGEX="${OT_REGEX_MAP[X4]}"
  STAGE2_CTX=16384
else
  STAGE2_CTX=32768
fi

echo "[batchSbfa0offload] FINAL_OT_TAG=${FINAL_OT_TAG} STAGE2_CTX=${STAGE2_CTX} (remaining: $(timebox_remaining)s)"

# ----- Stage 2: main scan (determined OT × STAGE2_CTX × ub ∈ {1585, 1586}) -----
# ub=1584 は Stage 1 で既取得（成功時）
echo "[batchSbfa0offload] === Stage 2: main scan (ctx=${STAGE2_CTX}) ==="
STAGE2_OK=0
STAGE2_TOTAL=1  # Stage 1 で 1584 を既カウント済み
if [ "$STAGE2_CTX" -eq 32768 ]; then
  STAGE2_OK=1  # Stage 1 で ub=1584 成功
fi

for ub in 1585 1586; do
  STAGE2_TOTAL=$((STAGE2_TOTAL+1))
  if run_condition "$STAGE2_CTX" "$ub" "$FINAL_OT_TAG" "$FINAL_OT_REGEX"; then
    STAGE2_OK=$((STAGE2_OK+1))
  fi
done
echo "[batchSbfa0offload] Stage 2 done: ${STAGE2_OK}/${STAGE2_TOTAL} conditions OK (remaining: $(timebox_remaining)s)"

# ----- Stage 3: extended scan (ctx=65k/131k) -----
if [ "$STAGE2_CTX" -eq 32768 ] && [ "$(timebox_remaining)" -gt 900 ]; then
  echo "[batchSbfa0offload] === Stage 3: extended (ctx=65k, 131k) ==="
  for ctx in 65536 131072; do
    for ub in 1584 1585 1586; do
      if [ "$(timebox_remaining)" -lt 300 ]; then
        echo "[batchSbfa0offload] Stage 3: insufficient time (remaining $(timebox_remaining)s), skip ctx=${ctx} ub=${ub}" >&2
        printf "%s_ctx%d_ub%d\ttimebox_skip\n" "$FINAL_OT_TAG" "$ctx" "$ub" >> "$FAIL_LOG"
        continue
      fi
      run_condition "$ctx" "$ub" "$FINAL_OT_TAG" "$FINAL_OT_REGEX" || true
    done
  done
  echo "[batchSbfa0offload] Stage 3 done (remaining: $(timebox_remaining)s)"
else
  echo "[batchSbfa0offload] Stage 3 skipped (STAGE2_CTX=${STAGE2_CTX} or timebox <900s)"
fi

# ----- Stage 4: baseline comparison (ctx=16k × determined OT) -----
if [ "$(timebox_remaining)" -gt 200 ]; then
  echo "[batchSbfa0offload] === Stage 4: baseline comparison (ctx=16k × ${FINAL_OT_TAG}) ==="
  # Stage 2 で既 ctx=16k を走査した場合は Stage 4 省略
  if [ "$STAGE2_CTX" -eq 16384 ]; then
    echo "[batchSbfa0offload] Stage 4: already covered by Stage 2 (STAGE2_CTX=16384), skip"
  else
    for ub in 1584 1585 1586; do
      if [ "$(timebox_remaining)" -lt 100 ]; then
        echo "[batchSbfa0offload] Stage 4: timebox <100s, skip ub=${ub}" >&2
        printf "%s_ctx16384_ub%d\ttimebox_skip\n" "$FINAL_OT_TAG" "$ub" >> "$FAIL_LOG"
        continue
      fi
      run_condition 16384 "$ub" "$FINAL_OT_TAG" "$FINAL_OT_REGEX" || true
    done
  fi
else
  echo "[batchSbfa0offload] Stage 4 skipped (timebox <200s)"
fi

echo "[batchSbfa0offload] end at $(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S')"
if [ -s "$FAIL_LOG" ]; then
  echo "[batchSbfa0offload] failures recorded in $FAIL_LOG:"
  cat "$FAIL_LOG"
else
  echo "[batchSbfa0offload] all attempted conditions succeeded"
fi
if [ -s "$OOM_LOG" ] && [ "$(wc -l < "$OOM_LOG")" -gt 1 ]; then
  echo "[batchSbfa0offload] OOM alloc size records:"
  cat "$OOM_LOG"
fi

# Stage 確定サマリ
cat > summary_state.txt <<EOF
FINAL_OT_TAG=${FINAL_OT_TAG}
FINAL_OT_REGEX=${FINAL_OT_REGEX}
STAGE2_CTX=${STAGE2_CTX}
STAGE2_OK=${STAGE2_OK}
STAGE2_TOTAL=${STAGE2_TOTAL}
START_EPOCH=${START_EPOCH}
END_EPOCH=$(date +%s)
EOF
echo "[batchSbfa0offload] wrote summary_state.txt"
