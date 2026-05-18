#!/usr/bin/env bash
# Phase B orchestrator: Speculative decoding (S1-S6 ngram-*, S7 draft-mtp skipped)
# MTP テンソル不在のため S7 はスキップ確定
# BL_A の決定は phaseA.log の集計後に判明するが、BL とそれほど変わらない可能性が高いので
# ここでは BL 構成 (start.sh のデフォルト) に対して --spec-type を追加する方針。
set -uo pipefail

WORK=$(cat /tmp/bench_marathon_workdir)
PROJ=/home/ubuntu/projects/llm-server-ops
PROMPT_DIR=$PROJ/report/attachment/2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default/prompts
MEASURE=$PROJ/report/attachment/2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default/measure_phaseU6.sh
CSV="$WORK/results.csv"
START_SH=$PROJ/.claude/skills/llama-server/scripts/start.sh
LLAMA_UP=$PROJ/.claude/skills/llama-server/scripts/llama-up.sh

log() { echo "[$(TZ=Asia/Tokyo date +%H:%M:%S)] [phaseB] $*"; }

wait_ready() {
  local n=0
  while [ $n -lt 120 ]; do
    if curl -sf -m 5 http://10.1.4.14:8000/health >/dev/null 2>&1; then
      return 0
    fi
    sleep 5
    n=$((n+1))
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
    if ! ssh t120h-p100 "pgrep -f 'build/bin/llama-server' >/dev/null 2>&1"; then
      return 0
    fi
    sleep 2
    n=$((n+1))
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

# spec_type pairs: (id, spec_args)
# Use bash array to avoid complex parsing
run_spec_trial() {
  local id="$1"; shift
  local spec_args="$*"
  log "=== $id: $spec_args ==="
  cp "$START_SH" "$WORK/start.sh.bak_$id"
  # Insert spec_args into SERVER_OPTS line (191)
  python3 - <<PY
p = "$START_SH"
s = open(p).read()
old = 'SERVER_OPTS="--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14"'
new = 'SERVER_OPTS="--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14 $spec_args"'
assert old in s, "SERVER_OPTS line not found in start.sh"
open(p,"w").write(s.replace(old, new))
PY
  git -C "$PROJ" diff "$START_SH" | head -5
  server_up "$id" || { log "$id server_up failed"; git -C "$PROJ" checkout -- "$START_SH"; return 1; }
  if curl -sf -m 5 http://10.1.4.14:8000/health >/dev/null 2>&1; then
    measure_cell "$id" 1k "$id" 512
    measure_cell "$id" 32k "$id" 512
    server_down "$id"
  fi
  git -C "$PROJ" checkout -- "$START_SH"
  sleep 30
}

# Phase B trials
run_spec_trial S1 "--spec-type ngram-simple"
run_spec_trial S2 "--spec-type ngram-mod"
run_spec_trial S3 "--spec-type ngram-cache"
run_spec_trial S4 "--spec-type ngram-map-k"
run_spec_trial S5 "--spec-type ngram-map-k4v"
run_spec_trial S6 "--spec-type ngram-mod,ngram-cache"
# S7 draft-mtp skipped (no MTP tensors in GGUF)

log "=== Phase B done ==="
git -C "$PROJ" status --short | tee -a "$WORK/git_status_phaseB.log"
wc -l "$CSV"
