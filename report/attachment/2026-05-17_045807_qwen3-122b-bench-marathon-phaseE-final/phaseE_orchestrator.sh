#!/usr/bin/env bash
# Phase E orchestrator: BL_FINAL = BL + M1 (--main-gpu 1) + T1_th32 (--threads 32)
# 1k/32k/96k で 5 ラン (warmup 込み) を 1 セット計測
# 再現性確認のため、これを 2 セット (interval 30s) 実施
set -uo pipefail

WORK=$(cat /tmp/bench_marathon_workdir)
PROJ=/home/ubuntu/projects/llm-server-ops
PROMPT_DIR=$PROJ/report/attachment/2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default/prompts
MEASURE=$PROJ/report/attachment/2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default/measure_phaseU6.sh
CSV="$WORK/results.csv"
START_SH=$PROJ/.claude/skills/llama-server/scripts/start.sh
LLAMA_UP=$PROJ/.claude/skills/llama-server/scripts/llama-up.sh

log() { echo "[$(TZ=Asia/Tokyo date +%H:%M:%S)] [phaseE] $*"; }

wait_ready() {
  local n=0
  while [ $n -lt 120 ]; do
    if curl -sf -m 5 http://10.1.4.14:8000/health >/dev/null 2>&1; then return 0; fi
    sleep 5; n=$((n+1))
  done
  return 1
}

server_up() {
  local label="$1"
  log "Starting llama-server for $label..."
  bash "$LLAMA_UP" >/tmp/up_${label}.log 2>&1 || true
  wait_ready || return 1
  ssh t120h-p100 "cat /proc/\$(pgrep -f 'build/bin/llama-server' | head -1)/cmdline | tr '\0' ' '" > "$WORK/cmdline_${label}.txt"
  ssh t120h-p100 "nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv" > "$WORK/gpu_pre_${label}.csv"
}

server_down() {
  local label="$1"
  log "Stopping llama-server for $label..."
  ssh t120h-p100 "nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv" > "$WORK/gpu_post_${label}.csv" 2>&1 || true
  scp -q t120h-p100:/tmp/llama-server.log "$WORK/llama-server_${label}.log" 2>/dev/null || true
  ssh t120h-p100 "pkill -f 'build/bin/llama-server' || true" || true
  local n=0
  while [ $n -lt 30 ]; do
    if ! ssh t120h-p100 "pgrep -f 'build/bin/llama-server' >/dev/null 2>&1"; then return 0; fi
    sleep 2; n=$((n+1))
  done
  ssh t120h-p100 "pkill -9 -f 'build/bin/llama-server' || true"
  sleep 5
}

measure_cell() {
  local label="$1"; local tag="$2"; local cond="$3"; local ub="$4"
  case $tag in
    1k)  W=2; E=5; MT=1024 ;;
    32k) W=1; E=5; MT=512  ;;
    96k) W=1; E=5; MT=256  ;;
  esac
  local cell="${label}_${tag}"
  local outdir="$WORK/out_${label}_${tag}"
  local pid; pid=$(ssh t120h-p100 "pgrep -f 'build/bin/llama-server' | head -1")
  [ -z "$pid" ] && { log "  $cell: no PID, skip"; return 1; }
  log "$cell start (W=$W E=$E MT=$MT)"
  CELL=$cell COND_ID=$cond UB=$ub \
    PROMPT_TAG=$tag PROMPT_FILE=$PROMPT_DIR/prompt_${tag}.txt \
    OUTDIR=$outdir \
    WARMUP_RUNS=$W EVAL_RUNS=$E EVAL_MAX_TOKENS=$MT COOLDOWN=15 \
    PID=$pid CSV=$CSV \
    bash "$MEASURE" >>"$WORK/measure.log" 2>&1
  log "$cell end"
}

# ========================================================
# Patch start.sh: BL_FINAL = BL + --main-gpu 1 + --threads 32
# ========================================================
log "=== BL_FINAL: BL + --main-gpu 1 + --threads 32 ==="
python3 - <<PY
p = "$START_SH"
s = open(p).read()
old = 'SERVER_OPTS="--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14"\n  ENV_PREFIX="numactl --cpunodebind=1 --membind=1"\n  THREADS_OPT="--threads 40"'
new = 'SERVER_OPTS="--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14 --main-gpu 1"\n  ENV_PREFIX="numactl --cpunodebind=1 --membind=1"\n  THREADS_OPT="--threads 32"'
assert old in s
open(p,"w").write(s.replace(old, new))
PY
git -C "$PROJ" diff "$START_SH" | head -15

# ========================================================
# Set 1: 1k + 32k + 96k
# ========================================================
log "--- Set 1 ---"
server_up BL_FINAL_set1 || { log "BL_FINAL set1 failed"; git -C "$PROJ" checkout -- "$START_SH"; exit 1; }
if curl -sf -m 5 http://10.1.4.14:8000/health >/dev/null 2>&1; then
  measure_cell BL_FINAL_set1 1k  BL_FINAL 512
  measure_cell BL_FINAL_set1 32k BL_FINAL 512
  measure_cell BL_FINAL_set1 96k BL_FINAL 512
  server_down BL_FINAL_set1
fi
sleep 60

# ========================================================
# Set 2: 1k + 32k のみ (96k は時間予算考慮で省略、Set 1 で十分)
# ========================================================
log "--- Set 2 ---"
server_up BL_FINAL_set2 || { log "BL_FINAL set2 failed"; git -C "$PROJ" checkout -- "$START_SH"; exit 1; }
if curl -sf -m 5 http://10.1.4.14:8000/health >/dev/null 2>&1; then
  measure_cell BL_FINAL_set2 1k  BL_FINAL 512
  measure_cell BL_FINAL_set2 32k BL_FINAL 512
  server_down BL_FINAL_set2
fi

git -C "$PROJ" checkout -- "$START_SH"
log "=== Phase E done ==="
git -C "$PROJ" status --short | tee -a "$WORK/git_status_phaseE.log"
wc -l "$CSV"
