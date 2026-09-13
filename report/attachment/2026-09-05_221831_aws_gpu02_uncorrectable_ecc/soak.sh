#!/usr/bin/env bash
# 軽量ソーク監視: SEL 件数と SSH 到達性のみ（負荷中でも詰まらないように in-band SDR は使わない）
cd /home/ubuntu/projects/llm-server-ops
set -a; . ~/.config/gpu-server/.env; set +a
H=$BMC_AWS_GPU02_HOST; U=$BMC_AWS_GPU02_USER; P=$BMC_AWS_GPU02_PASS
LOG="$1"; N="${2:-480}"
[ -f "$LOG" ] || echo "time,sel_entries,sel_mem_uce,ssh,uptime_s,load1" > "$LOG"
for i in $(seq 1 "$N"); do
    SEL=$(timeout 25 ipmitool -I lanplus -H "$H" -U "$U" -P "$P" sel info 2>/dev/null | awk -F': *' '/^Entries/{print $2}')
    UCE=$(timeout 40 ipmitool -I lanplus -H "$H" -U "$U" -P "$P" sel elist 2>/dev/null | grep -ci "Uncorrectable ECC")
    R=$(timeout 20 ssh -o ConnectTimeout=6 -o BatchMode=yes -n aws-gpu02 "awk '{print \$1}' /proc/uptime; awk '{print \$1}' /proc/loadavg" 2>/dev/null | tr '\n' ',')
    [ -n "$R" ] && SSHOK=up || { SSHOK=down; R=","; }
    echo "$(date '+%F %T'),${SEL:-?},${UCE:-?},$SSHOK,$R" >> "$LOG"
    sleep 45
done
