#!/usr/bin/env bash
# mi25 コールド電源サイクル×5 傾向観測
# 各ブートで 4ルートポート(00:02/00:03/80:02/80:03)のリンク幅・PresDet、
# dmidecode スロット状態、生存GUIDを記録する。
cd /home/ubuntu/projects/llm-server-ops || exit 1
BMC=".claude/skills/gpu-server/scripts/bmc-power.sh"
LOG=/tmp/mi25_cycle_trend.log
: > "$LOG"

log() { echo "$@" | tee -a "$LOG"; }

wait_off() {
  local i
  for i in $(seq 1 48); do
    if $BMC mi25 status 2>/dev/null | grep -q "Power: off"; then return 0; fi
    sleep 5
  done
  return 1
}

wait_ssh() {
  local i
  for i in $(seq 1 40); do
    if ssh -o ConnectTimeout=5 -o BatchMode=yes mi25 "uptime" >/dev/null 2>&1; then return 0; fi
    sleep 10
  done
  return 1
}

cap() {
  ssh -o ConnectTimeout=8 -o BatchMode=yes mi25 'bash -s' <<'REMOTE'
    vga=$(lspci 2>/dev/null | grep -c "VGA compatible controller.*\[AMD/ATI\]")
    echo "VGA_GPU_COUNT=$vga"
    for rp in 00:02.0 00:03.0 80:02.0 80:03.0; do
      out=$(sudo -n lspci -vvs "$rp" 2>/dev/null)
      if [ -z "$out" ]; then
        echo "PORT $rp = ROOTPORT_ABSENT"
        continue
      fi
      w=$(echo "$out" | grep -oE "LnkSta:.*" | grep -oE "Width x[0-9]+" | head -1)
      sp=$(echo "$out" | grep -oE "LnkSta: Speed [^,]+" | head -1 | sed 's/LnkSta: //')
      p=$(echo "$out" | grep -oE "PresDet[+-]" | head -1)
      echo "PORT $rp = ${w:-Width-?} ${sp:-Speed-?} ${p:-PresDet?}"
    done
    echo "SLOTS:"
    sudo -n dmidecode -t slot 2>/dev/null | grep -E "Designation: CPU[12] SLOT[2468] |Current Usage:" | grep -E "SLOT[2468] |Current Usage" | paste - - | sed 's/\t/  ->  /'
    guids=$(rocm-smi --showid 2>/dev/null | grep -oE "GUID:[[:space:]]*[0-9]+" | grep -oE "[0-9]+" | tr '\n' ' ')
    echo "GUIDS_ALIVE= $guids"
REMOTE
}

log "##### mi25 cold power-cycle trend (5 cycles) #####"
log "GUID map: 29525=SLOT2  33301=SLOT4  54068=SLOT6  8820=SLOT8"
log ""

for n in 1 2 3 4 5; do
  log "===================== CYCLE $n / 5 ====================="
  log "[$(date '+%F %T')] ソフトシャットダウン要求"
  $BMC mi25 soft >>"$LOG" 2>&1 || true
  if wait_off; then
    log "[$(date '+%F %T')] 電源OFF確認"
  else
    log "[$(date '+%F %T')] soft応答せず -> ハード電源OFF"
    $BMC mi25 off >>"$LOG" 2>&1 || true
    sleep 10
  fi
  log "[$(date '+%F %T')] 30秒 電力ドレイン待機"
  sleep 30
  log "[$(date '+%F %T')] 電源ON"
  $BMC mi25 on >>"$LOG" 2>&1 || true
  if wait_ssh; then
    sleep 8
    log "[$(date '+%F %T')] SSH復帰 -- トポロジ取得:"
    cap | tee -a "$LOG"
  else
    log "[$(date '+%F %T')] !!! SSH復帰せず(起動失敗の可能性) cycle $n"
  fi
  log ""
done

log "##### 完了 $(date '+%F %T') #####"
