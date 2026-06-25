#!/usr/bin/env bash
# mi25 4枚復旧後の電源サイクル/再起動 安定性テスト
#  cycles 1..COLD = コールド電源サイクル (soft -> 電力ドレイン -> on)
#  cycles COLD+1..COLD+WARM = ウォーム再起動 (ssh sudo reboot)
# 各ブートで: 認識枚数(Instinct MI25)、4ルートポートの Width/Speed/PresDet、
#           4ルートポートの AER (cor/fatal/nonfatal TOTAL)、生存GUID、
#           dmesg の dropout/reset/hang signature を記録。
# 4枚未満を検知したら即停止(遠隔では戻せないため)。
# 各 SSH 復帰後に gpu-server ロックを取り直す(/tmp はリブートで消えるため)。
set -u
cd /home/ubuntu/projects/llm-server-ops || exit 1

BMC=".claude/skills/gpu-server/scripts/bmc-power.sh"
LOCK=".claude/skills/gpu-server/scripts/lock.sh"
UNLOCK=".claude/skills/gpu-server/scripts/unlock.sh"
SHOT=".claude/skills/gpu-server/scripts/bmc-screenshot.sh"

COLD="${COLD:-5}"
WARM="${WARM:-2}"
SID="${SID:-$(hostname)-mi25stab}"
OUTDIR="${OUTDIR:-/tmp/claude-1000/-home-ubuntu-projects-llm-server-ops/7516709a-391e-4335-8cb2-0de4a4dc2491/scratchpad}"
LOG="$OUTDIR/cycle_trend.log"
: > "$LOG"

log() { echo "$@" | tee -a "$LOG"; }

wait_off() {
  local i
  for i in $(seq 1 48); do
    $BMC mi25 status 2>/dev/null | grep -q "Power: off" && return 0
    sleep 5
  done
  return 1
}

wait_ssh() {
  local i
  for i in $(seq 1 40); do
    ssh -o ConnectTimeout=5 -o BatchMode=yes mi25 "uptime" >/dev/null 2>&1 && return 0
    sleep 10
  done
  return 1
}

relock() {
  $UNLOCK mi25 "$SID" >/dev/null 2>&1 || true
  $LOCK mi25 "$SID"   >>"$LOG" 2>&1 || true
}

# 戻り値: 標準出力に "COUNT=<n>" を含む。呼び出し側で枚数を抽出。
cap() {
  ssh -o ConnectTimeout=8 -o BatchMode=yes mi25 'bash -s' <<'REMOTE'
    cnt=$(lspci 2>/dev/null | grep -c "Instinct MI25")
    echo "COUNT=$cnt"
    echo "UPTIME=$(uptime | sed 's/^ *//')"
    for rp in 00:02.0 00:03.0 80:02.0 80:03.0; do
      out=$(sudo -n lspci -vvs "$rp" 2>/dev/null)
      if [ -z "$out" ]; then echo "PORT $rp = ROOTPORT_ABSENT"; continue; fi
      lnk=$(echo "$out" | grep "LnkSta:" | head -1 | sed 's/^[[:space:]]*//')
      w=$(echo "$lnk"  | grep -oE "Width x[0-9]+")
      sp=$(echo "$lnk" | grep -oE "Speed [0-9.]+GT/s")
      pd=$(echo "$out" | grep "SltSta:" | head -1 | grep -oE "PresDet[+-]")
      cor=$(cat "/sys/bus/pci/devices/0000:$rp/aer_dev_correctable" 2>/dev/null | grep -E "^TOTAL_ERR_COR" | awk '{print $2}')
      fat=$(cat "/sys/bus/pci/devices/0000:$rp/aer_dev_fatal" 2>/dev/null | grep -E "^TOTAL_ERR_FATAL" | awk '{print $2}')
      nft=$(cat "/sys/bus/pci/devices/0000:$rp/aer_dev_nonfatal" 2>/dev/null | grep -E "^TOTAL_ERR_NONFATAL" | awk '{print $2}')
      echo "PORT $rp = ${w:-Width-?} ${sp:-Speed-?} ${pd:-PresDet?} AER(cor=${cor:-?} fatal=${fat:-?} nonfatal=${nft:-?})"
    done
    guids=$(rocm-smi --showid 2>/dev/null | grep -oE "GUID:[[:space:]]*[0-9]+" | grep -oE "[0-9]+" | tr '\n' ' ')
    echo "GUIDS_ALIVE= $guids"
    sig=$(sudo -n dmesg 2>/dev/null | grep -iE "amdgpu|pcieport|aer" | grep -iE "fail|reset|hang|timeout|Width x0|Width x8|link down|PresDet" | tail -8)
    if [ -n "$sig" ]; then echo "DMESG_SIG:"; echo "$sig"; else echo "DMESG_SIG: none"; fi
REMOTE
}

log "##### mi25 4-card power-cycle / reboot stability test #####"
log "cold=$COLD warm=$WARM  start=$(date '+%F %T')"
log "slot map (4-card recovery): 29525=SLOT2(00:02)  33301=SLOT4(00:03)  54068=SLOT8(80:02)  8820=SLOT6(80:03)"
log "baseline expected: COUNT=4, all ports Width x16 Speed 8GT/s PresDet+ AER cor/fatal/nonfatal=0, GUIDs 29525 33301 54068 8820"
log ""

TOTAL=$((COLD + WARM))
ABORT=0
for n in $(seq 1 "$TOTAL"); do
  if [ "$n" -le "$COLD" ]; then KIND="COLD-CYCLE"; else KIND="WARM-REBOOT"; fi
  log "===================== CYCLE $n / $TOTAL  [$KIND] ====================="

  if [ "$KIND" = "COLD-CYCLE" ]; then
    log "[$(date '+%F %T')] soft shutdown"
    $BMC mi25 soft >>"$LOG" 2>&1 || true
    if wait_off; then
      log "[$(date '+%F %T')] power OFF confirmed"
    else
      log "[$(date '+%F %T')] soft no response -> hard OFF"
      $BMC mi25 off >>"$LOG" 2>&1 || true
      sleep 10
    fi
    log "[$(date '+%F %T')] 30s power drain"
    sleep 30
    log "[$(date '+%F %T')] power ON"
    $BMC mi25 on >>"$LOG" 2>&1 || true
  else
    log "[$(date '+%F %T')] warm reboot via ssh sudo reboot"
    ssh -o ConnectTimeout=8 -o BatchMode=yes mi25 "sudo -n reboot" >/dev/null 2>&1 || true
    sleep 30
  fi

  if wait_ssh; then
    sleep 8
    log "[$(date '+%F %T')] SSH back -- re-acquire lock & capture:"
    relock
    OUT="$(cap)"
    echo "$OUT" | tee -a "$LOG"
    CNT=$(echo "$OUT" | grep -oE "^COUNT=[0-9]+" | grep -oE "[0-9]+")
    if [ -z "$CNT" ] || [ "$CNT" -lt 4 ]; then
      log ""
      log "!!!!! ALERT: GPU count = ${CNT:-?} (<4) at cycle $n -- card dropout detected. STOP. !!!!!"
      ABORT=1
      break
    fi
    log "[OK] cycle $n: 4 cards present"
  else
    log "[$(date '+%F %T')] !!! SSH did NOT recover at cycle $n (possible hang/boot failure)"
    log "[$(date '+%F %T')] capturing BMC KVM screenshot before any reset"
    $SHOT mi25 "$OUTDIR/hang_cycle${n}.png" >>"$LOG" 2>&1 || true
    ABORT=2
    break
  fi
  log ""
done

if [ "$ABORT" -eq 0 ]; then
  log "##### ALL $TOTAL CYCLES PASSED (4 cards every time) -- done $(date '+%F %T') #####"
elif [ "$ABORT" -eq 1 ]; then
  log "##### ABORTED: card dropout -- physical reseat required -- $(date '+%F %T') #####"
else
  log "##### ABORTED: SSH/boot failure -- KVM screenshot saved -- $(date '+%F %T') #####"
fi
exit "$ABORT"
