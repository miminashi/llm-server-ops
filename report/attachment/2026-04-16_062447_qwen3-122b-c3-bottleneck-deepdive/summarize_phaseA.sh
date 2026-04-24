#!/usr/bin/env bash
# Phase A 集計スクリプト
# 使い方: bash summarize_phaseA.sh [PREFIX]
set -euo pipefail

PREFIX="${1:-phaseA}"
ATTACH="$(cd "$(dirname "$0")" && pwd)"
cd "$ATTACH"

TL="${PREFIX}_timeline.log"

parse_timeline_window() {
  local RUN="$1"
  local LINE
  LINE=$(grep "^run=$RUN eval_start=" "$TL" 2>/dev/null || true)
  if [[ -z "$LINE" ]]; then
    echo ""
    return
  fi
  local START END
  START=$(echo "$LINE" | sed -n 's/.*eval_start=\([^ ]*\).*/\1/p')
  END=$(echo "$LINE" | sed -n 's/.*eval_end=\([^ ]*\).*/\1/p')
  # 時刻文字列 (2026-04-16T05:48:41.123456789) から HH:MM:SS を抽出
  local SH EH
  SH=$(echo "$START" | sed -n 's/.*T\([0-9:]*\).*/\1/p')
  EH=$(echo "$END"   | sed -n 's/.*T\([0-9:]*\).*/\1/p')
  echo "$SH $EH"
}

# ---- summary_gpu.tsv ----
# dmon を eval 窓で frame 平均
{
  echo -e "run\tgpu\tsm_avg\tsm_p95\tmem_avg\tpwr_avg\trxpci_avg\ttxpci_avg\tfb_avg\tsamples"
  for RUN in 0 1 2 3; do
    F="${PREFIX}_dmon_run${RUN}.log"
    [[ -f "$F" ]] || continue
    if [[ "$RUN" == "0" ]]; then
      WINDOW=""
    else
      WINDOW=$(parse_timeline_window "$RUN")
    fi
    awk -v run="$RUN" -v win="$WINDOW" '
      BEGIN { split(win, w, " "); sh=w[1]; eh=w[2] }
      /^#/ { next }
      NF < 10 { next }
      {
        # cols: date(1) time(2) gpu(3) pwr(4) gtemp(5) mtemp(6) sm(7) mem(8) enc(9) dec(10) jpg(11) ofa(12) mclk(13) pclk(14) pviol(15) tviol(16) fb(17) bar1(18) ccpm(19) sbecc(20) dbecc(21) pci(22) rxpci(23) txpci(24)
        d=$1; t=$2; g=$3; pwr=$4; sm=$7; mem=$8; rx=$23; tx=$24; fb=$17
        if (sh != "" && (t < sh || t > eh)) next
        key=run"\t"g
        n[key]++
        sm_s[key]+=sm; mem_s[key]+=mem; pwr_s[key]+=pwr; rx_s[key]+=rx; tx_s[key]+=tx; fb_s[key]+=fb
        sm_arr[key"\t"n[key]]=sm
      }
      END {
        for (k in n) {
          c=n[k]
          # p95 = ceil(0.95*c) のインデックス (ソート後)
          delete sorted
          for (i=1;i<=c;i++) sorted[i]=sm_arr[k"\t"i]
          # simple sort
          for (i=1;i<=c;i++) for (j=i+1;j<=c;j++) if (sorted[i]>sorted[j]) { tmp=sorted[i]; sorted[i]=sorted[j]; sorted[j]=tmp }
          p95_idx=int(c*0.95); if (p95_idx<1) p95_idx=1
          printf "%s\t%.2f\t%.2f\t%.2f\t%.2f\t%.2f\t%.2f\t%.2f\t%d\n", k, sm_s[k]/c, sorted[p95_idx], mem_s[k]/c, pwr_s[k]/c, rx_s[k]/c, tx_s[k]/c, fb_s[k]/c, c
        }
      }
    ' "$F" | sort -k1,1n -k2,2n
  done
} > summary_gpu.tsv

# ---- summary_cpu.tsv (system-wide top から us/sy/id/wa 抽出) ----
{
  echo -e "run\tus_avg\tsy_avg\tid_avg\twa_avg\tpid_cpu_avg\tpid_cpu_p95\tsamples"
  for RUN in 0 1 2 3; do
    TS_F="${PREFIX}_top_system_run${RUN}.log"
    PP_F="${PREFIX}_top_pid_run${RUN}.log"
    [[ -f "$TS_F" ]] || continue
    if [[ "$RUN" == "0" ]]; then WINDOW=""; else WINDOW=$(parse_timeline_window "$RUN"); fi

    # system us/sy/id/wa を集計
    sys_line=$(awk -v win="$WINDOW" '
      BEGIN { split(win, w, " "); sh=w[1]; eh=w[2] }
      /^top -/ {
        # top - 05:48:41 up ...
        t=$3
        if (sh!="" && (t<sh || t>eh)) { in_w=0 } else { in_w=1 }
        next
      }
      /^%Cpu/ {
        if (sh=="" || in_w) {
          # %Cpu(s):  91.1 us,  0.1 sy,  0.0 ni,  8.8 id,  0.0 wa
          for (i=1;i<=NF;i++) {
            if ($i=="us,") us += $(i-1)
            else if ($i=="sy,") sy += $(i-1)
            else if ($i=="id,") id += $(i-1)
            else if ($i=="wa,") wa += $(i-1)
          }
          n++
        }
      }
      END {
        if (n>0) printf "%.2f\t%.2f\t%.2f\t%.2f\t%d\n", us/n, sy/n, id/n, wa/n, n
      }
    ' "$TS_F")

    # pid %CPU を集計
    pid_line=$(awk -v win="$WINDOW" '
      BEGIN { split(win, w, " "); sh=w[1]; eh=w[2] }
      /^top -/ { t=$3; if (sh!="" && (t<sh || t>eh)) { in_w=0 } else { in_w=1 }; next }
      /^[[:space:]]*[0-9]+[[:space:]]+/ {
        if (sh=="" || in_w) {
          cpu=$9+0
          vals[++c]=cpu
          s+=cpu
        }
      }
      END {
        if (c>0) {
          # sort for p95
          for (i=1;i<=c;i++) for (j=i+1;j<=c;j++) if (vals[i]>vals[j]) { tmp=vals[i]; vals[i]=vals[j]; vals[j]=tmp }
          p95=int(c*0.95); if (p95<1) p95=1
          printf "%.1f\t%.1f\n", s/c, vals[p95]
        } else {
          printf "0.0\t0.0\n"
        }
      }
    ' "$PP_F")

    if [[ -z "$sys_line" ]]; then continue; fi
    us=$(echo "$sys_line" | cut -f1)
    sy=$(echo "$sys_line" | cut -f2)
    id=$(echo "$sys_line" | cut -f3)
    wa=$(echo "$sys_line" | cut -f4)
    ns=$(echo "$sys_line" | cut -f5)
    pid_avg=$(echo "$pid_line" | cut -f1)
    pid_p95=$(echo "$pid_line" | cut -f2)
    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$RUN" "$us" "$sy" "$id" "$wa" "$pid_avg" "$pid_p95" "$ns"
  done
} > summary_cpu.tsv

# ---- summary_perf.tsv (perf stat の末尾の集計から抽出) ----
{
  echo -e "run\tcycles\tinstructions\tipc\tcache_misses\tcache_refs\tcache_miss_rate\tLLC_loads\tLLC_load_misses\tLLC_miss_rate\tnode_loads\tnode_load_misses\tnode_miss_rate\tdTLB_miss_rate"
  for RUN in 0 1 2 3; do
    F="${PREFIX}_perfstat_run${RUN}.log"
    [[ -f "$F" ]] || continue
    awk -v run="$RUN" '
      function num(s) { gsub(/,/,"",s); return s+0 }
      /[0-9]+[[:space:]]+cycles/ { cy=num($1) }
      /[0-9]+[[:space:]]+instructions/ { ins=num($1) }
      /[0-9]+[[:space:]]+cache-misses/ { cm=num($1) }
      /[0-9]+[[:space:]]+cache-references/ { cr=num($1) }
      /[0-9]+[[:space:]]+LLC-loads/ { ll=num($1) }
      /[0-9]+[[:space:]]+LLC-load-misses/ { llm=num($1) }
      /[0-9]+[[:space:]]+node-loads/ { nl=num($1) }
      /[0-9]+[[:space:]]+node-load-misses/ { nlm=num($1) }
      /[0-9]+[[:space:]]+dTLB-loads/ { dl=num($1) }
      /[0-9]+[[:space:]]+dTLB-load-misses/ { dlm=num($1) }
      END {
        ipc = (cy>0) ? ins/cy : 0
        cmr = (cr>0) ? cm/cr : 0
        lmr = (ll>0) ? llm/ll : 0
        nmr = (nl>0) ? nlm/nl : 0
        dmr = (dl>0) ? dlm/dl : 0
        printf "%s\t%d\t%d\t%.3f\t%d\t%d\t%.4f\t%d\t%d\t%.4f\t%d\t%d\t%.4f\t%.4f\n", run, cy, ins, ipc, cm, cr, cmr, ll, llm, lmr, nl, nlm, nmr, dmr
      }
    ' "$F"
  done
} > summary_perf.tsv

# ---- summary_threads.tsv (/proc/$PID/status の Threads) ----
{
  echo -e "run\tthreads_min\tthreads_max\tvoluntary_ctxt_delta\tnonvoluntary_ctxt_delta"
  for RUN in 0 1 2 3; do
    F="${PREFIX}_status_run${RUN}.log"
    [[ -f "$F" ]] || continue
    awk -v run="$RUN" '
      /^Threads:/ { th[++nth]=$2 }
      /^voluntary_ctxt_switches:/ { vc[++nvc]=$2 }
      /^nonvoluntary_ctxt_switches:/ { nc[++nnc]=$2 }
      END {
        if (nth==0) { exit }
        tmin=th[1]; tmax=th[1]
        for (i=1;i<=nth;i++) { if (th[i]<tmin) tmin=th[i]; if (th[i]>tmax) tmax=th[i] }
        vd = (nvc>=2) ? vc[nvc]-vc[1] : 0
        nd = (nnc>=2) ? nc[nnc]-nc[1] : 0
        printf "%s\t%d\t%d\t%d\t%d\n", run, tmin, tmax, vd, nd
      }
    ' "$F"
  done
} > summary_threads.tsv

# ---- summary_numa.tsv (numastat の Total ノード別 + /proc/vmstat delta) ----
{
  echo -e "run\tN0_total_MB\tN1_total_MB\tnuma_hit_delta\tnuma_miss_delta\tnuma_foreign_delta\tnuma_local_delta\tnuma_other_delta\tmiss_ratio_pct\tother_ratio_pct"
  for RUN in 0 1 2 3; do
    NS_POST="${PREFIX}_numastat_post_run${RUN}.log"
    VP="${PREFIX}_vmstat_pre_run${RUN}.log"
    VO="${PREFIX}_vmstat_post_run${RUN}.log"
    [[ -f "$NS_POST" && -f "$VP" && -f "$VO" ]] || continue
    # numastat -p 出力末尾の Total 行 "Total  N0_MB  N1_MB  Total_MB"
    NU=$(awk '/^Total/ { n0=$2; n1=$3; printf "%s\t%s\n", n0, n1; exit }' "$NS_POST")
    [[ -z "$NU" ]] && NU="0\t0"
    # vmstat NUMA カウンタ
    HIT_PRE=$(awk '$1=="numa_hit"{print $2}'     "$VP"); HIT_POST=$(awk '$1=="numa_hit"{print $2}'     "$VO")
    MIS_PRE=$(awk '$1=="numa_miss"{print $2}'    "$VP"); MIS_POST=$(awk '$1=="numa_miss"{print $2}'    "$VO")
    FOR_PRE=$(awk '$1=="numa_foreign"{print $2}' "$VP"); FOR_POST=$(awk '$1=="numa_foreign"{print $2}' "$VO")
    LOC_PRE=$(awk '$1=="numa_local"{print $2}'   "$VP"); LOC_POST=$(awk '$1=="numa_local"{print $2}'   "$VO")
    OTH_PRE=$(awk '$1=="numa_other"{print $2}'   "$VP"); OTH_POST=$(awk '$1=="numa_other"{print $2}'   "$VO")
    HD=$((HIT_POST - HIT_PRE)); MD=$((MIS_POST - MIS_PRE)); FD=$((FOR_POST - FOR_PRE))
    LD=$((LOC_POST - LOC_PRE)); OD=$((OTH_POST - OTH_PRE))
    # ratio
    MISR=$(awk -v m="$MD" -v h="$HD" 'BEGIN{if(h>0) printf "%.3f", m/h*100; else print "0.000"}')
    OTHR=$(awk -v o="$OD" -v h="$HD" 'BEGIN{if(h>0) printf "%.3f", o/h*100; else print "0.000"}')
    printf "%s\t%s\t%d\t%d\t%d\t%d\t%d\t%s\t%s\n" "$RUN" "$NU" "$HD" "$MD" "$FD" "$LD" "$OD" "$MISR" "$OTHR"
  done
} > summary_numa.tsv

# ---- summary_percore.tsv (mpstat から per-CPU %usr 平均 NUMA0/NUMA1 集計) ----
{
  echo -e "run\tn0_usr_avg\tn1_usr_avg\tn0_cores_used\tn1_cores_used"
  for RUN in 0 1 2 3; do
    F="${PREFIX}_mpstat_run${RUN}.log"
    [[ -f "$F" ]] || continue
    awk -v run="$RUN" '
      # mpstat 24h 出力: "HH:MM:SS CPU %usr %nice %sys ..."
      # フィールド: $1=time $2=cpu $3=%usr $4=%nice $5=%sys ...
      # CPU が数値 (0-79) の行を対象 ("all" は除外)
      $2 ~ /^[0-9]+$/ {
        cpu=$2+0; usr=$3+0
        # NUMA node 判定 (t120h-p100: N0={0-19,40-59}, N1={20-39,60-79})
        if ((cpu>=0 && cpu<=19) || (cpu>=40 && cpu<=59)) { n="0" } else { n="1" }
        if (n=="0") { n0_s+=usr; n0_c++; if (usr>5) n0_used[cpu]=1 }
        else        { n1_s+=usr; n1_c++; if (usr>5) n1_used[cpu]=1 }
      }
      END {
        n0u = (n0_c>0) ? n0_s/n0_c : 0
        n1u = (n1_c>0) ? n1_s/n1_c : 0
        n0used=0; for (k in n0_used) n0used++
        n1used=0; for (k in n1_used) n1used++
        printf "%s\t%.2f\t%.2f\t%d\t%d\n", run, n0u, n1u, n0used, n1used
      }
    ' "$F"
  done
} > summary_percore.tsv

# ---- eval t/s 集計 (eval_run{1,2,3}.json から timings.predicted_per_second) ----
{
  echo -e "run\teval_tps\tprompt_tps\teval_ms\tn_tokens"
  for RUN in 1 2 3; do
    F="${PREFIX}_eval_run${RUN}.json"
    [[ -f "$F" ]] || continue
    python3 - "$F" "$RUN" <<'PY' 2>/dev/null || true
import json,sys
p=sys.argv[1]; r=sys.argv[2]
try:
    d=json.load(open(p))
    t=d.get("timings",{})
    print(f"{r}\t{t.get('predicted_per_second',0):.2f}\t{t.get('prompt_per_second',0):.2f}\t{t.get('predicted_ms',0):.1f}\t{t.get('predicted_n',0)}")
except Exception as e:
    print(f"{r}\tERR\tERR\tERR\tERR")
PY
  done
} > summary_eval.tsv

echo "=== summary_gpu.tsv ==="
cat summary_gpu.tsv
echo ""
echo "=== summary_cpu.tsv ==="
cat summary_cpu.tsv
echo ""
echo "=== summary_perf.tsv ==="
cat summary_perf.tsv
echo ""
echo "=== summary_threads.tsv ==="
cat summary_threads.tsv
echo ""
echo "=== summary_numa.tsv ==="
cat summary_numa.tsv
echo ""
echo "=== summary_percore.tsv ==="
cat summary_percore.tsv
echo ""
echo "=== summary_eval.tsv ==="
cat summary_eval.tsv
