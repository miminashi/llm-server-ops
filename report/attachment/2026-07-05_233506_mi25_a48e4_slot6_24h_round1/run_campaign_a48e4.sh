#!/bin/bash
# mi25 a48e4 (SLOT6 = BDF 87:00.0) 単独 stand-alone 24h 負荷キャンペーン オーケストレータ。
# Fable レビュー D-1 決定実験: 健全カード×SLOT6 で fault が出るかを検証。
# run_campaign_c48c4.sh (SLOT8_24h_x2 R2) から派生 (Vulkan idx 2→3、SCRATCH と MAX/MIN/HANG_SAFETY を SA 相当に)。
# - a48e4 は 2026-06-30 の SLOT4↔SLOT6 swap で既に SLOT6 に装着済、物理作業ゼロ
# - MAX_TRIALS/MIN_TRIALS/HANG_SAFETY を SA (200/80/10) に揃える (SLOT8 R2 の 120/20/5 ではなく)
# - BACO 後 power cap 160W 強制再設定ブロックを restart_llama 後に維持 (SLOT8 R2 で導入したロジック)
#
# 試行ループを回し、ハング時は KVMスクショ→BMCリセット→復帰→ブート状態記録→ロック再取得
# →llama再起動→テレメトリ再起動 を自動化して継続する。
#
# Usage:
#   run_campaign_a48e4.sh
#   主要パラメータは環境変数で上書き可:
#   MAX_TRIALS(200) MIN_TRIALS(80) HANG_SAFETY(10) PHASE_CAP_SEC(86400=24h) TRIAL_SEC(720)
#   CTX_SIZE(131072 = run-a48e4-slot6.sh 経由でラッパに渡す)
#
# 終了コード: 0=正常完了 / 7=ハング安全境界に到達(ユーザ確認要) / 9=復旧失敗(要介入)

set -u
PROJ=/home/ubuntu/projects/llm-server-ops
SCRATCH=/home/ubuntu/projects/llm-server-ops/report/attachment/2026-07-05_233506_mi25_a48e4_slot6_24h_round1
SERVER=mi25
ENDPOINT=http://10.1.4.13:8000
MODEL="unsloth/Qwen3-8B-GGUF:Q6_K"
BACKEND="vulkan"
ROCM_DEVICE_IDX=3  # a48e4 = GPU[3] (BDF 87:00.0 = SLOT6、2026-06-30 SLOT4↔SLOT6 swap 後の配置維持)

MAX_TRIALS="${MAX_TRIALS:-200}"
MIN_TRIALS="${MIN_TRIALS:-80}"
HANG_SAFETY="${HANG_SAFETY:-10}"
PHASE_CAP_SEC="${PHASE_CAP_SEC:-86400}"
TRIAL_SEC="${TRIAL_SEC:-720}"
export CTX_SIZE="${CTX_SIZE:-131072}"

JSONL="$SCRATCH/trials_${BACKEND}.jsonl"
CAMPLOG="$SCRATCH/campaign_${BACKEND}.log"
BOOTLOG="$SCRATCH/boot_state.log"

log(){ echo "[$(date -Iseconds)] $*" | tee -a "$CAMPLOG"; }

boot_seq=0
record_boot_state(){ # $1=reset_type
  local rt="$1" epoch ts cnt
  epoch=$(date +%s); ts=$(date -Iseconds)
  cnt=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "$SERVER" \
    "rocm-smi --showmaxpower 2>/dev/null | grep -oE 'GPU\[[0-9]+\]' | sort -u | wc -l" 2>/dev/null)
  {
    echo "### BOOT boot_seq=$boot_seq reset_type=$rt epoch=$epoch ts=$ts backend=$BACKEND"
    echo "gpu_count=${cnt:-ERR}"
    echo "--- rocm-smi --showmaxpower (per-GPU power cap) ---"
    ssh -o ConnectTimeout=8 -o BatchMode=yes "$SERVER" "rocm-smi --showmaxpower 2>/dev/null" 2>&1
    echo "--- root fs ---"
    ssh -o ConnectTimeout=8 -o BatchMode=yes "$SERVER" "awk '\$2==\"/\"{print}' /proc/mounts" 2>&1
    echo "### END BOOT boot_seq=$boot_seq gpu_count=${cnt:-ERR}"
    echo
  } >> "$BOOTLOG"
  log "boot_seq=$boot_seq ($rt) gpu_count=${cnt:-ERR}"
}

start_telemetry(){
  pkill -f "telemetry.sh $SCRATCH" 2>/dev/null
  pkill -f "telemetry_pcie.sh $SCRATCH" 2>/dev/null
  [ -f "$SCRATCH/telemetry.pids" ] && xargs -r kill 2>/dev/null < "$SCRATCH/telemetry.pids"
  [ -f "$SCRATCH/telemetry_pcie.pid" ] && xargs -r kill 2>/dev/null < "$SCRATCH/telemetry_pcie.pid"
  bash "$SCRATCH/telemetry.sh" "$SCRATCH" "$SERVER" >> "$CAMPLOG" 2>&1
  bash "$SCRATCH/telemetry_pcie.sh" "$SCRATCH" "$SERVER" >> "$CAMPLOG" 2>&1
}
stop_telemetry(){
  [ -f "$SCRATCH/telemetry.pids" ] && xargs -r kill 2>/dev/null < "$SCRATCH/telemetry.pids"
  [ -f "$SCRATCH/telemetry_pcie.pid" ] && xargs -r kill 2>/dev/null < "$SCRATCH/telemetry_pcie.pid"
  pkill -f "rocm-smi --showtemp" 2>/dev/null
  # H-1 是正 (Fable レビュー B-1): mi25 側の残存 ssh セッション (dmesg -w / tail -F) も明示停止。
  # SA/SLOT8 では正常終了時にこれらが停止されず、commit 済みログが試験終了後も書き換わった。
  ssh -o ConnectTimeout=5 -o BatchMode=yes "$SERVER" \
    "pkill -f 'dmesg -w' 2>/dev/null; pkill -f 'tail -F /tmp/llama-server.log' 2>/dev/null" 2>/dev/null || true
}

# H-1 是正: スクリプトが正常終了/異常終了/シグナル終了しても stop_telemetry を必ず呼ぶ
trap 'stop_telemetry' EXIT INT TERM

wait_ssh(){ # 最大 $1 秒
  local max="$1" i
  for ((i=0;i<max;i+=5)); do
    ssh -o ConnectTimeout=5 -o BatchMode=yes "$SERVER" true 2>/dev/null && return 0
    sleep 5
  done
  return 1
}

restart_llama(){
  log "llama 再起動 (a48e4 SLOT6 stand-alone Vulkan ctx=$CTX_SIZE)"
  # a48e4 単独可視化ラッパを呼ぶ (start.sh の detect_radv_vk_indices を回避)
  CTX_SIZE="$CTX_SIZE" bash "$SCRATCH/run-a48e4-slot6.sh" >> "$CAMPLOG" 2>&1
  local rc=$?
  # BACO 後の power cap 160W 強制再設定 (stand_alone_24h 副次発見: BACO で 220W に戻る)
  # ssh 経由 sudo は user 許可済 (本セッション特例)
  if [ "$rc" -eq 0 ]; then
    local pc
    pc=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "$SERVER" \
      "rocm-smi --showmaxpower 2>/dev/null | grep -E \"GPU\\[${ROCM_DEVICE_IDX}\\].*Power\" | grep -oE '[0-9]+\\.[0-9]+' | head -1" 2>/dev/null)
    if [ -n "$pc" ] && awk -v p="$pc" 'BEGIN{exit !(p>165)}'; then
      log "BACO power cap reset detected (GPU[$ROCM_DEVICE_IDX] cap=${pc}W) → 160W に再設定"
      ssh -o ConnectTimeout=8 "$SERVER" \
        "sudo rocm-smi --setpoweroverdrive 160 -d $ROCM_DEVICE_IDX" >> "$CAMPLOG" 2>&1
    fi
  fi
  return $rc
}

recover_from_hang(){ # $1=hang index。成功:0 / 失敗:9
  local hn="$1"
  # 1) KVMスクショ（リセット前に必ず）
  log "ハング#$hn: KVMスクショ取得（リセット前）"
  ( cd "$PROJ" && .claude/skills/gpu-server/scripts/bmc-screenshot.sh "$SERVER" "$SCRATCH/hang_${BACKEND}_${hn}.png" ) >> "$CAMPLOG" 2>&1
  # 2) warm reset
  log "ハング#$hn: BMC warm reset"
  ( cd "$PROJ" && .claude/skills/gpu-server/scripts/bmc-power.sh "$SERVER" reset ) >> "$CAMPLOG" 2>&1
  if ! wait_ssh 300; then
    log "warm reset 後 SSH 復帰せず → cold cycle へエスカレーション"
    ( cd "$PROJ" && .claude/skills/gpu-server/scripts/bmc-power.sh "$SERVER" cycle 20 ) >> "$CAMPLOG" 2>&1
    if ! wait_ssh 300; then
      log "cold cycle 後も SSH 復帰せず → 復旧失敗(要介入)"
      return 9
    fi
    boot_seq=$((boot_seq+1)); record_boot_state "cold-cycle"
  else
    boot_seq=$((boot_seq+1)); record_boot_state "warm-reset"
  fi
  # 3) 前ブートのカーネルトレース採取（永続journal）
  ssh -o ConnectTimeout=8 "$SERVER" "sudo journalctl -b -1 -k --no-pager 2>/dev/null | tail -200" \
    > "$SCRATCH/prevboot_${BACKEND}_${hn}.log" 2>&1
  ssh -o ConnectTimeout=8 "$SERVER" "sudo journalctl -b -1 --no-pager 2>/dev/null | grep -iE 'amdgpu|gpu reset|ring|pcie|aer|soft lockup|nmi|panic|call trace' | tail -100" \
    >> "$SCRATCH/prevboot_${BACKEND}_${hn}.log" 2>&1
  # 4) ロック再取得（reboot で tmpfs lock は消えるが冪等に）
  ( cd "$PROJ" && .claude/skills/gpu-server/scripts/unlock.sh "$SERVER"; .claude/skills/gpu-server/scripts/lock.sh "$SERVER" "a48e4-slot6-24h-r1-2026-07-05_233506" ) >> "$CAMPLOG" 2>&1
  # 5) llama 再起動
  restart_llama
  # 6) /health 確認
  for i in $(seq 1 60); do
    curl -sf -m 5 "$ENDPOINT/health" >/dev/null 2>&1 && break
    sleep 5
  done
  # 7) テレメトリ再起動
  start_telemetry
  return 0
}

log "===== キャンペーン開始 backend=$BACKEND model=$MODEL ctx=$CTX_SIZE MAX=$MAX_TRIALS MIN=$MIN_TRIALS HANG_SAFETY=$HANG_SAFETY CAP=${PHASE_CAP_SEC}s TRIAL=${TRIAL_SEC}s ====="
# 初回ブート状態（このフェーズの起点）を記録 + テレメトリ起動
record_boot_state "phase-start-${BACKEND}-a48e4-slot6"
start_telemetry
# 初回 llama-server 起動（電力スイープ版は sweep_one_point.sh が担っていた役割）
log "初回 llama-server 起動"
restart_llama
# /health 確認 (起動完了待機 最大 300s)
log "/health 確認待機 (最大 300s)"
for i in $(seq 1 60); do
  if curl -sf -m 5 "$ENDPOINT/health" >/dev/null 2>&1; then
    log "    /health OK (elapsed $((i*5))s)"
    break
  fi
  sleep 5
done
if ! curl -sf -m 5 "$ENDPOINT/health" >/dev/null 2>&1; then
  log "ERROR: 初回 llama-server 起動失敗 (/health に応答せず) → キャンペーン中断"
  exit 9
fi
phase_start=$(date +%s)
hang_count=0
net_outages=0
trial=0

while :; do
  elapsed=$(( $(date +%s) - phase_start ))
  if [ "$trial" -ge "$MIN_TRIALS" ]; then
    if [ "$trial" -ge "$MAX_TRIALS" ]; then log "MAX_TRIALS 到達で終了"; break; fi
    if [ "$elapsed" -ge "$PHASE_CAP_SEC" ]; then log "PHASE_CAP 到達で終了 (${elapsed}s)"; break; fi
  fi
  trial=$((trial+1))
  # 各 trial 開始前に /health で llama-server 生死を確認
  # ・llama-server が落ちると load_driver は status=OK で server_error_transient を返し続け、
  #   rc=0 として無限ループ的に MAX_TRIALS を消費してしまう。
  # ・/health 不通なら restart_llama → 復旧不可なら HANG_CONFIRMED 扱いで recover_from_hang。
  if ! curl -sf -m 5 "$ENDPOINT/health" >/dev/null 2>&1; then
    log "trial $trial 前 /health 不通 → llama-server 再起動を試みる"
    restart_llama
    for i in $(seq 1 60); do
      curl -sf -m 5 "$ENDPOINT/health" >/dev/null 2>&1 && break
      sleep 5
    done
    if ! curl -sf -m 5 "$ENDPOINT/health" >/dev/null 2>&1; then
      log "ERROR: 再起動後も /health 不通 → HANG_CONFIRMED 扱いで recover_from_hang 起動"
      hang_count=$((hang_count+1))
      if ! recover_from_hang "$hang_count"; then
        log "復旧失敗 → キャンペーン中断(rc=9)"; exit 9
      fi
      if [ "$hang_count" -ge "$HANG_SAFETY" ]; then
        log "ハング安全境界($HANG_SAFETY)到達 → 一旦停止しユーザ確認(rc=7)"; exit 7
      fi
    fi
  fi
  log "--- trial $trial 開始 (elapsed=${elapsed}s hangs=$hang_count) ---"
  python3 "$SCRATCH/load_driver.py" --endpoint "$ENDPOINT" --model "$MODEL" --server "$SERVER" \
    --backend "$BACKEND" --trial-seconds "$TRIAL_SEC" --trial-no "$trial" \
    --jsonl "$JSONL" --hang-json "$SCRATCH/hang_info_${BACKEND}_${trial}.json" >> "$CAMPLOG" 2>&1
  rc=$?
  if [ "$rc" -eq 42 ]; then
    hang_count=$((hang_count+1))
    log "*** HANG 検出 trial=$trial (hang_count=$hang_count) ***"
    if ! recover_from_hang "$hang_count"; then
      log "復旧失敗 → キャンペーン中断(rc=9)"; exit 9
    fi
    if [ "$hang_count" -ge "$HANG_SAFETY" ]; then
      log "ハング安全境界($HANG_SAFETY)到達 → 一旦停止しユーザ確認(rc=7)"; exit 7
    fi
  elif [ "$rc" -eq 43 ]; then
    # ネットワーク障害（ホストは生存）→ リセット不要。回復を待って継続。
    net_outages=$((net_outages+1))
    log "### ネットワーク障害検出 trial=$trial (net_outages=$net_outages)。リセットせず回復待機 ###"
    recovered=0
    for i in $(seq 1 180); do  # 最大 30 分（10s間隔）
      if curl -sf -m 5 "$ENDPOINT/health" >/dev/null 2>&1 \
         && ssh -o ConnectTimeout=5 -o BatchMode=yes "$SERVER" true 2>/dev/null; then
        recovered=1; break
      fi
      sleep 10
    done
    if [ "$recovered" -eq 1 ]; then
      log "ネットワーク回復確認。テレメトリ再起動し継続（trialカウンタは継続、ハング扱いしない）"
      start_telemetry
    else
      log "30分待っても回復せず → キャンペーン中断(rc=8, ネットワーク要確認)"; exit 8
    fi
  elif [ "$rc" -ne 0 ]; then
    log "load_driver 異常終了 rc=$rc（ハング以外）。/health 確認して継続"
    curl -sf -m 5 "$ENDPOINT/health" >/dev/null 2>&1 || { log "health不通 → 30s待機"; sleep 30; }
  fi
done

log "===== キャンペーン完了 backend=$BACKEND trials=$trial hangs=$hang_count ====="
exit 0
