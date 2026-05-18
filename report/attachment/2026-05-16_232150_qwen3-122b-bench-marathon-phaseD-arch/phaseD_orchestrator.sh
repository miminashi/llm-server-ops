#!/usr/bin/env bash
# Phase D orchestrator: Architecture
#   O1: B12 (OT 12 層に縮小、B14 から layer 20, 38 を GPU に戻す)
#   O2: B16 (OT 16 層、B14 から layer 24, 39 を CPU に戻す)
#   G1: -sm tensor + cache-type k/v f16 (KV 量子化禁止、ctx=128k のまま試行)
#   W1: --swa-full (Qwen3.5 の full_attention_interval=4 を活用)
set -uo pipefail

WORK=$(cat /tmp/bench_marathon_workdir)
PROJ=/home/ubuntu/projects/llm-server-ops
PROMPT_DIR=$PROJ/report/attachment/2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default/prompts
MEASURE=$PROJ/report/attachment/2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default/measure_phaseU6.sh
CSV="$WORK/results.csv"
START_SH=$PROJ/.claude/skills/llama-server/scripts/start.sh
LLAMA_UP=$PROJ/.claude/skills/llama-server/scripts/llama-up.sh

log() { echo "[$(TZ=Asia/Tokyo date +%H:%M:%S)] [phaseD] $*"; }

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

# Helper: replace OT layer list and/or SERVER_OPTS
# args: id, server_opts, ot_layer_list (空文字なら B14b 既定), measure_32k(yes/no)
run_arch_trial() {
  local id="$1"
  local server_opts="$2"
  local ot_layers="$3"
  local measure_32k="$4"
  log "=== $id ==="
  python3 - <<PY
p = "$START_SH"
s = open(p).read()
# Replace SERVER_OPTS
old_so = 'SERVER_OPTS="--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14"'
new_so = 'SERVER_OPTS="$server_opts"'
assert old_so in s, "SERVER_OPTS line not found"
s = s.replace(old_so, new_so)
# Replace OT layer list if non-empty
ot_layers_str = "$ot_layers"
if ot_layers_str:
    old_ot = "for L in 2 3 20 21 22 23 31 32 33 34 35 36 37 38; do"
    new_ot = f"for L in {ot_layers_str}; do"
    assert old_ot in s, "OT loop not found"
    s = s.replace(old_ot, new_ot)
open(p,"w").write(s)
PY
  git -C "$PROJ" diff "$START_SH" | head -15
  server_up "$id" || { log "$id server_up failed"; git -C "$PROJ" checkout -- "$START_SH"; return 1; }
  if curl -sf -m 5 http://10.1.4.14:8000/health >/dev/null 2>&1; then
    measure_cell "$id" 1k "$id" 512
    [ "$measure_32k" = "yes" ] && measure_cell "$id" 32k "$id" 512
    server_down "$id"
  fi
  git -C "$PROJ" checkout -- "$START_SH"
  sleep 30
}

# ===========================================================================
# O1: B12 (OT 12 層、B14b から layer 20, 38 を GPU に戻す)
# CPU offload = {2,3,21,22,23,31,32,33,34,35,36,37}
# ===========================================================================
run_arch_trial O1_B12 \
  "--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14" \
  "2 3 21 22 23 31 32 33 34 35 36 37" \
  yes

# ===========================================================================
# O2: B16 (OT 16 層、B14b に layer 24, 39 を追加)
# CPU offload = {2,3,20,21,22,23,24,31,32,33,34,35,36,37,38,39}
# ===========================================================================
run_arch_trial O2_B16 \
  "--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14" \
  "2 3 20 21 22 23 24 31 32 33 34 35 36 37 38 39" \
  no

# ===========================================================================
# G1: -sm tensor + KV f16
# 注意: split-mode tensor は KV 量子化と非互換のため f16 にする
# また OT パターンも有効なまま（B14b）
# CTX フォールバック: 128k で起動失敗時は llama-up.sh の fit-ctx で 98304/65536 に下げて再試行
# ===========================================================================
log "=== G1: -sm tensor + KV f16 (CTX フォールバック付き) ==="
python3 - <<PY
p = "$START_SH"
s = open(p).read()
# SERVER_OPTS replacement: split-mode tensor
old_so = 'SERVER_OPTS="--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14"'
new_so = 'SERVER_OPTS="--flash-attn 1 --poll 0 -b 2048 -ub 512"'
assert old_so in s
s = s.replace(old_so, new_so)
# Replace --split-mode layer with --split-mode tensor (in NGL_OPTS)
s = s.replace("--split-mode layer", "--split-mode tensor")
# Replace KV q8_0 with f16
s = s.replace("--cache-type-k q8_0 --cache-type-v q8_0", "--cache-type-k f16 --cache-type-v f16")
open(p,"w").write(s)
PY
git -C "$PROJ" diff "$START_SH" | head -25
# 128k で起動を試みる
server_up G1_sm_tensor || {
  log "G1 ctx=128k 失敗、ctx=96k に下げて再試行..."
  bash "$LLAMA_UP" t120h-p100 "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit 98304 >/tmp/up_G1_ctx96k.log 2>&1 || true
  sleep 60
  wait_ready || log "G1 ctx=96k も失敗 → スキップ"
}
if curl -sf -m 5 http://10.1.4.14:8000/health >/dev/null 2>&1; then
  measure_cell G1_sm_tensor 1k G1 512
  server_down G1_sm_tensor
fi
git -C "$PROJ" checkout -- "$START_SH"
sleep 30

# ===========================================================================
# W1: --swa-full (Qwen3.5 の full_attention_interval=4 を活用)
# ===========================================================================
run_arch_trial W1_swa_full \
  "--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14 --swa-full" \
  "" \
  no

log "=== Phase D done ==="
git -C "$PROJ" status --short | tee -a "$WORK/git_status_phaseD.log"
wc -l "$CSV"
