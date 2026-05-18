#!/usr/bin/env bash
# Phase A orchestrator: BL (32k/96k continuation) + F1/N1/M1/K1
# Called after BL 1k already finished externally.
set -uo pipefail

WORK=$(cat /tmp/bench_marathon_workdir)
PROJ=/home/ubuntu/projects/llm-server-ops
PROMPT_DIR=$PROJ/report/attachment/2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default/prompts
MEASURE=$PROJ/report/attachment/2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default/measure_phaseU6.sh
CSV="$WORK/results.csv"
START_SH=$PROJ/.claude/skills/llama-server/scripts/start.sh
LLAMA_UP=$PROJ/.claude/skills/llama-server/scripts/llama-up.sh
LLAMA_DOWN=$PROJ/.claude/skills/llama-server/scripts/llama-down.sh

log() { echo "[$(TZ=Asia/Tokyo date +%H:%M:%S)] [phaseA] $*"; }
ts() { TZ=Asia/Tokyo date +%H:%M:%S; }

wait_ready() {
  local n=0
  while [ $n -lt 120 ]; do
    if curl -sf -m 5 http://10.1.4.14:8000/health >/dev/null 2>&1; then
      log "  /health OK after ${n}x5s"
      return 0
    fi
    sleep 5
    n=$((n+1))
  done
  log "  /health TIMEOUT"
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
  ssh t120h-p100 "cp /tmp/llama-server.log /tmp/llama-server-${label}.log 2>/dev/null || true" || true
  scp -q t120h-p100:/tmp/llama-server-${label}.log "$WORK/llama-server_${label}.log" 2>/dev/null || true
  # llama-down.sh will release the lock; we need to keep the lock through the run.
  # Use ssh kill instead to keep lock.
  ssh t120h-p100 "pkill -f 'build/bin/llama-server' || true" 2>&1 | tee -a "$WORK/down_${label}.log" || true
  local n=0
  while [ $n -lt 30 ]; do
    if ! ssh t120h-p100 "pgrep -f 'build/bin/llama-server' >/dev/null 2>&1"; then
      log "  llama-server stopped after ${n}x2s"
      return 0
    fi
    sleep 2
    n=$((n+1))
  done
  log "  llama-server kill TIMEOUT - escalating"
  ssh t120h-p100 "pkill -9 -f 'build/bin/llama-server' || true"
  sleep 5
}

measure_cell() {
  local label="$1"  # e.g. BL, F1, N1, M1, K1
  local tag="$2"    # 1k, 32k, 96k
  local cond="$3"
  local ub="$4"
  case $tag in
    1k)  W=2; E=5; MT=1024 ;;
    32k) W=1; E=5; MT=512  ;;
    96k) W=1; E=5; MT=256  ;;
    *)   W=1; E=5; MT=512  ;;
  esac
  local cell="${label}_${tag}"
  local outdir="$WORK/out_${label}_${tag}"
  local pid
  pid=$(ssh t120h-p100 "pgrep -f 'build/bin/llama-server' | head -1")
  if [ -z "$pid" ]; then
    log "  $cell: no PID, skip"
    return 1
  fi
  log "$cell start (warmup=$W eval=$E max_tokens=$MT)"
  CELL=$cell COND_ID=$cond UB=$ub \
    PROMPT_TAG=$tag PROMPT_FILE=$PROMPT_DIR/prompt_${tag}.txt \
    OUTDIR=$outdir \
    WARMUP_RUNS=$W EVAL_RUNS=$E EVAL_MAX_TOKENS=$MT COOLDOWN=15 \
    PID=$pid CSV=$CSV \
    bash "$MEASURE" >>"$WORK/measure.log" 2>&1
  log "$cell end"
}

# ============================================================
# Step 1: BL 32k + 96k (BL 1k was done externally)
# ============================================================
log "=== BL 32k/96k (existing server) ==="
measure_cell BL 32k BL 512
measure_cell BL 96k BL 512
server_down BL
sleep 30

# ============================================================
# Step 2: F1  -fa auto
# ============================================================
log "=== F1: --flash-attn 1 -> auto ==="
cp "$START_SH" "$WORK/start.sh.bak"
sed -i 's|--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14|--flash-attn auto --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14|' "$START_SH"
git -C "$PROJ" diff "$START_SH" | head -20
server_up F1 || { log "F1 server_up failed"; git -C "$PROJ" checkout -- "$START_SH"; }
if curl -sf -m 5 http://10.1.4.14:8000/health >/dev/null 2>&1; then
  measure_cell F1 1k F1 512
  measure_cell F1 32k F1 512
  server_down F1
fi
git -C "$PROJ" checkout -- "$START_SH"
sleep 30

# ============================================================
# Step 3: N1  -ncmoe 14 (replaces OT pattern)
# ============================================================
log "=== N1: -ot ... -> -ncmoe 14 ==="
# Replace the multi-line OT block (lines 240-249) with simple -ncmoe 14
# Easiest: replace the entire "if qwen3_122b" OT logic with a simpler one for this trial only.
# We use a marker sed replacement on the OT_PATTERNS loop.
python3 - <<'PY'
import re, sys
p = "/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/start.sh"
s = open(p).read()
# Replace the entire if-else block of the fit-mode profile to use -ncmoe 14
old = '''if [ "$MODEL_PROFILE" = "qwen3_122b" ]; then
    # Phase U-6 確定 OT=B14b: CPU offload = layer {2,3,20-23,31-38}、他は GPU
    # llama.cpp の -ot はカンマ区切りで複数パターンを OR 合成できる (parse_tensor_buffer_overrides)。
    # 単一 regex の `(|)` は bash のメタキャラで outer ssh パイプラインを通らないため使えない。
    OT_PATTERNS=""
    for L in 2 3 20 21 22 23 31 32 33 34 35 36 37 38; do
      [ -n "$OT_PATTERNS" ] && OT_PATTERNS+=","
      OT_PATTERNS+="blk.$L.ffn_.*_exps.weight=CPU"
    done
    NGL_OPTS="-ngl 999 --split-mode layer -ot '$OT_PATTERNS'"
  else'''
new = '''if [ "$MODEL_PROFILE" = "qwen3_122b" ]; then
    # PHASE A N1 TRIAL: -ncmoe 14 (front-14 layers CPU offload, NOT same as B14b)
    NGL_OPTS="-ngl 999 --split-mode layer -ncmoe 14"
  else'''
assert old in s, "OT block not found"
open(p,"w").write(s.replace(old, new))
print("N1 patch applied")
PY
git -C "$PROJ" diff "$START_SH" | head -30
server_up N1 || { log "N1 server_up failed"; git -C "$PROJ" checkout -- "$START_SH"; }
if curl -sf -m 5 http://10.1.4.14:8000/health >/dev/null 2>&1; then
  measure_cell N1 1k N1 512
  measure_cell N1 32k N1 512
  server_down N1
fi
git -C "$PROJ" checkout -- "$START_SH"
sleep 30

# ============================================================
# Step 4: M1  --main-gpu 1
# ============================================================
log "=== M1: --main-gpu 1 ==="
sed -i 's|--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14|--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14 --main-gpu 1|' "$START_SH"
git -C "$PROJ" diff "$START_SH" | head -10
server_up M1 || { log "M1 server_up failed"; git -C "$PROJ" checkout -- "$START_SH"; }
if curl -sf -m 5 http://10.1.4.14:8000/health >/dev/null 2>&1; then
  measure_cell M1 1k M1 512
  measure_cell M1 32k M1 512
  server_down M1
fi
git -C "$PROJ" checkout -- "$START_SH"
sleep 30

# ============================================================
# Step 5: K1  KV q4_0
# ============================================================
log "=== K1: KV q8_0 -> q4_0 ==="
sed -i 's|--cache-type-k q8_0 --cache-type-v q8_0|--cache-type-k q4_0 --cache-type-v q4_0|' "$START_SH"
git -C "$PROJ" diff "$START_SH" | head -10
server_up K1 || { log "K1 server_up failed"; git -C "$PROJ" checkout -- "$START_SH"; }
if curl -sf -m 5 http://10.1.4.14:8000/health >/dev/null 2>&1; then
  measure_cell K1 1k K1 512
  measure_cell K1 32k K1 512
  server_down K1
fi
git -C "$PROJ" checkout -- "$START_SH"
sleep 10

# Final cleanup verification
log "=== Phase A done ==="
log "git status check:"
git -C "$PROJ" status --short | tee -a "$WORK/git_status_final.log"
log "results.csv summary:"
wc -l "$CSV"
