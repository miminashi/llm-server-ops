#!/bin/bash
# 1 電力点ルーチン: 電力切替 → llama-server 起動 → run_campaign → 退避 → 停止
# usage: bash sweep_one_point.sh <watts>
set -u
WATTS=${1:?usage: $0 <watts>}
TAG="p${WATTS}W"
SCR=/tmp/claude-1000/-home-ubuntu-projects-llm-server-ops/b7cda347-5c3e-4616-a32b-d090008dc24b/scratchpad
PROJ=/home/ubuntu/projects/llm-server-ops
MODEL="unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL"

log(){ echo "[$(date -Iseconds)] [$TAG] $*"; }

# (a) llama-server 停止 (生きてれば)
log "step a: stop any running llama-server"
ssh -o ConnectTimeout=10 mi25 'pkill -f bin/llama-server || true; sleep 3'

# (b) 電力制限切替 + 反映確認
log "step b: set power cap to ${WATTS}W"
ssh -o ConnectTimeout=10 mi25 'bash -s' < "$SCR/set_power_cap.sh" "$WATTS"
ssh -o ConnectTimeout=10 mi25 'rocm-smi --showmaxpower' > "$SCR/maxpower_${TAG}.txt"

# (c) 期前 cursor 取得 (点別 journal 差分用)
log "step c: snapshot journal cursor"
ssh -o ConnectTimeout=10 mi25 "sudo journalctl --since=now --cursor-file=/tmp/jcur_${TAG} -n0 || true"
date -Iseconds > "$SCR/anchor_${TAG}.txt"

# (d) llama-server 起動 (Vulkan 4枚 auto 検出)
log "step d: bring up llama-server (Vulkan)"
( cd "$PROJ" && MI25_BACKEND=vulkan .claude/skills/llama-server/scripts/llama-up.sh mi25 "$MODEL" 131072 )
LL_RC=$?
if [ "$LL_RC" -ne 0 ]; then
  log "llama-up.sh failed rc=$LL_RC → abort point"
  exit 11
fi

# (e) per-card PCIe+AER サンプラ手動起動 (telemetry.sh は run_campaign が起動)
log "step e: start telemetry_pcie sampler"
bash "$SCR/telemetry_pcie.sh" "$SCR" mi25

# (f) run_campaign.sh vulkan 実行 (中で telemetry.sh が自動起動される)
log "step f: run_campaign vulkan MAX=4 MIN=4 CAP=3000 TRIAL=720"
MAX_TRIALS=4 MIN_TRIALS=4 PHASE_CAP_SEC=3000 TRIAL_SEC=720 \
  bash "$SCR/run_campaign.sh" vulkan
RC=$?
log "step f: run_campaign exited rc=$RC"

# (g) per-card PCIe サンプラ停止
log "step g: stop telemetry_pcie sampler"
if [ -f "$SCR/telemetry_pcie.pid" ]; then
  kill "$(cat "$SCR/telemetry_pcie.pid")" 2>/dev/null || true
  rm -f "$SCR/telemetry_pcie.pid"
fi
# 派生 ssh が孤立する可能性に備え念のためパターンキル
pkill -f 'telemetry_pcie.sh' 2>/dev/null || true

# (h) telemetry.sh が起動した子プロセスも停止
log "step h: stop run_campaign's telemetry children"
if [ -f "$SCR/telemetry.pids" ]; then
  xargs -r kill 2>/dev/null < "$SCR/telemetry.pids" || true
  rm -f "$SCR/telemetry.pids"
fi
pkill -f 'rocm-smi --showtemp' 2>/dev/null || true

# (i) 固定名出力を点別退避
log "step i: rename outputs with TAG=$TAG"
for f in trials_vulkan.jsonl campaign_vulkan.log telemetry_pcie.log telemetry_rocmsmi.log telemetry_gpucount.log kern_dmesg.log llama_server.log; do
  if [ -f "$SCR/$f" ]; then
    base="${f%.*}"; ext="${f##*.}"
    new="${base}_${TAG}.${ext}"
    mv "$SCR/$f" "$SCR/$new"
    echo "  $f -> $new"
  fi
done

# (j) llama-server.log のサーバ側 tail + 期間差分 journal を採取
log "step j: collect llama-server tail + journal diff"
ssh -o ConnectTimeout=10 mi25 "tail -300 /tmp/llama-server.log" > "$SCR/llama_server_${TAG}_tail.log" 2>&1 || true
ssh -o ConnectTimeout=10 mi25 "sudo journalctl --cursor-file=/tmp/jcur_${TAG} --no-pager 2>/dev/null" > "$SCR/journal_${TAG}.txt" 2>&1 || true

# (k) llama-server 停止 + post snapshot
log "step k: stop llama-server + post-rocm snapshot"
ssh -o ConnectTimeout=10 mi25 'pkill -f bin/llama-server || true'
ssh -o ConnectTimeout=10 mi25 'rocm-smi --showbus --showpower --showtemp --showmeminfo vram' > "$SCR/rocm_${TAG}_post.txt" 2>&1 || true

log "step l: returning rc=$RC"
exit $RC
