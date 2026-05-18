#!/usr/bin/env bash
# Phase C orchestrator: Parameter sweep (ub/b/threads) on BL baseline
# Reduced version: 7 trials total
#   U1: ub=256, 384, 768 (512=BL は Phase A の値を流用)
#   B1: b=1024, 4096    (2048=BL 同上)
#   T1: threads=32, 44   (40=BL 同上)
# 各試行は 1k のみ計測（warmup 2 + eval 5, max_tokens=1024）
# Best 1-2 候補のみ 32k 追加計測
set -uo pipefail

WORK=$(cat /tmp/bench_marathon_workdir)
PROJ=/home/ubuntu/projects/llm-server-ops
PROMPT_DIR=$PROJ/report/attachment/2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default/prompts
MEASURE=$PROJ/report/attachment/2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default/measure_phaseU6.sh
CSV="$WORK/results.csv"
START_SH=$PROJ/.claude/skills/llama-server/scripts/start.sh
LLAMA_UP=$PROJ/.claude/skills/llama-server/scripts/llama-up.sh

log() { echo "[$(TZ=Asia/Tokyo date +%H:%M:%S)] [phaseC] $*"; }

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

# Apply edit: replace SERVER_OPTS / THREADS_OPT in start.sh
patch_start_sh() {
  local new_server_opts="$1"
  local new_threads_opt="${2:-}"
  python3 - <<PY
p = "$START_SH"
s = open(p).read()
old = 'SERVER_OPTS="--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14"\n  ENV_PREFIX="numactl --cpunodebind=1 --membind=1"\n  THREADS_OPT="--threads 40"'
threads = "$new_threads_opt"
if threads == "":
    threads = "--threads 40"
new = f'SERVER_OPTS="$new_server_opts"\n  ENV_PREFIX="numactl --cpunodebind=1 --membind=1"\n  THREADS_OPT="{threads}"'
assert old in s, "SERVER_OPTS+THREADS_OPT block not found"
open(p,"w").write(s.replace(old, new))
PY
}

run_trial_1k() {
  local id="$1"
  local server_opts="$2"
  local threads_opt="${3:-}"
  local cond_id="$4"
  local ub_log="$5"
  log "=== $id: SERVER_OPTS=$server_opts THREADS_OPT=${threads_opt:-default} ==="
  patch_start_sh "$server_opts" "$threads_opt"
  git -C "$PROJ" diff "$START_SH" | head -5
  server_up "$id" || { log "$id server_up failed"; git -C "$PROJ" checkout -- "$START_SH"; return 1; }
  if curl -sf -m 5 http://10.1.4.14:8000/health >/dev/null 2>&1; then
    measure_cell "$id" 1k "$cond_id" "$ub_log"
    server_down "$id"
  fi
  git -C "$PROJ" checkout -- "$START_SH"
  sleep 30
}

# ===========================================================================
# U1: ub sweep (1k のみ)
# ===========================================================================
run_trial_1k U1_ub256 \
  "--flash-attn 1 --poll 0 -b 2048 -ub 256 --tensor-split 11,12,13,14" \
  "" U1 256
run_trial_1k U1_ub384 \
  "--flash-attn 1 --poll 0 -b 2048 -ub 384 --tensor-split 11,12,13,14" \
  "" U1 384
run_trial_1k U1_ub768 \
  "--flash-attn 1 --poll 0 -b 2048 -ub 768 --tensor-split 11,12,13,14" \
  "" U1 768

# ===========================================================================
# B1: b sweep (ub=512 固定, 1k のみ)
# ===========================================================================
run_trial_1k B1_b1024 \
  "--flash-attn 1 --poll 0 -b 1024 -ub 512 --tensor-split 11,12,13,14" \
  "" B1 512
run_trial_1k B1_b4096 \
  "--flash-attn 1 --poll 0 -b 4096 -ub 512 --tensor-split 11,12,13,14" \
  "" B1 512

# ===========================================================================
# T1: threads sweep (1k のみ)
# ===========================================================================
run_trial_1k T1_th32 \
  "--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14" \
  "--threads 32" T1 512
run_trial_1k T1_th44 \
  "--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14" \
  "--threads 44" T1 512

log "=== Phase C done ==="
git -C "$PROJ" status --short | tee -a "$WORK/git_status_phaseC.log"
wc -l "$CSV"
