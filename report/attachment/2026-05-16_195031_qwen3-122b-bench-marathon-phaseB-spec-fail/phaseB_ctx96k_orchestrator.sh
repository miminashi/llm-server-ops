#!/usr/bin/env bash
# Phase B' orchestrator: Speculative decoding @ ctx=96k (98304)
# Phase B (ctx=128k) で spec checkpoint (~149 MiB / ckpt) が VRAM 不足で OOM したため、
# ctx を 96k に下げて再試行 (プランの ctx フォールバック規則)
set -uo pipefail

WORK=$(cat /tmp/bench_marathon_workdir)
PROJ=/home/ubuntu/projects/llm-server-ops
PROMPT_DIR=$PROJ/report/attachment/2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default/prompts
MEASURE=$PROJ/report/attachment/2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default/measure_phaseU6.sh
CSV="$WORK/results.csv"
START_SH=$PROJ/.claude/skills/llama-server/scripts/start.sh
LLAMA_UP=$PROJ/.claude/skills/llama-server/scripts/llama-up.sh

# ctx=96k で起動 (llama-up.sh の第 4 引数として渡す)
FIT_CTX_OVERRIDE=98304

log() { echo "[$(TZ=Asia/Tokyo date +%H:%M:%S)] [phaseB96k] $*"; }

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
  log "Starting llama-server for $label (ctx=$FIT_CTX_OVERRIDE)..."
  bash "$LLAMA_UP" t120h-p100 "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit $FIT_CTX_OVERRIDE >/tmp/up_${label}.log 2>&1 || true
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

run_spec_trial() {
  local id="$1"; shift
  local spec_args="$*"
  log "=== $id @ ctx96k: $spec_args ==="
  cp "$START_SH" "$WORK/start.sh.bak_${id}_ctx96k"
  python3 - <<PY
p = "$START_SH"
s = open(p).read()
old = 'SERVER_OPTS="--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14"'
new = 'SERVER_OPTS="--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14 $spec_args"'
assert old in s, "SERVER_OPTS line not found in start.sh"
open(p,"w").write(s.replace(old, new))
PY
  git -C "$PROJ" diff "$START_SH" | head -5
  local label="${id}_ctx96k"
  server_up "$label" || { log "$label server_up failed"; git -C "$PROJ" checkout -- "$START_SH"; return 1; }
  if curl -sf -m 5 http://10.1.4.14:8000/health >/dev/null 2>&1; then
    measure_cell "$label" 1k "$id" 512
    measure_cell "$label" 32k "$id" 512
    server_down "$label"
  fi
  git -C "$PROJ" checkout -- "$START_SH"
  sleep 30
}

# Phase B' trials @ ctx=96k
run_spec_trial S1 "--spec-type ngram-simple"
run_spec_trial S2 "--spec-type ngram-mod"
run_spec_trial S3 "--spec-type ngram-cache"
run_spec_trial S4 "--spec-type ngram-map-k"
run_spec_trial S5 "--spec-type ngram-map-k4v"
run_spec_trial S6 "--spec-type ngram-mod,ngram-cache"

log "=== Phase B' done ==="
git -C "$PROJ" status --short | tee -a "$WORK/git_status_phaseB96k.log"
wc -l "$CSV"
