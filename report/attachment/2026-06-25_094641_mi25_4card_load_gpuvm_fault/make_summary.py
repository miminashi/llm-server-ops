#!/usr/bin/env python3
"""mi25 4枚復旧の安定性再検証 核心サマリ図。
(a) 電源サイクル7回の PCIeリンク幅ヒートマップ(全x16)
(b) 負荷テスト構成別の「フォルトまでの稼働秒」(8820を含む全構成で node-5 フォルト)
(c) 成功ターン(全run)のスループット箱ひげ
図中ラベルは日本語フォント不在のため英語で統一する。"""
import json, re, sys, statistics
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

D = sys.argv[1] if len(sys.argv) > 1 else "."

# ---- (a) 電源サイクル ----
PORTS = ["00:02.0","00:03.0","80:02.0","80:03.0"]
cyc_widths={}; cyc_kind={}; cyc_pass=[]; cur=None
with open(f"{D}/cycle_trend.log") as f:
    for line in f:
        m=re.search(r"CYCLE (\d+) / \d+\s+\[(COLD-CYCLE|WARM-REBOOT)\]",line)
        if m: cur=int(m.group(1)); cyc_kind[cur]=m.group(2); cyc_widths[cur]={}
        m=re.match(r"PORT (\S+) = Width x(\d+)",line)
        if m and cur is not None: cyc_widths[cur][m.group(1)]=int(m.group(2))
        m=re.search(r"\[OK\] cycle (\d+): 4 cards present",line)
        if m: cyc_pass.append(int(m.group(1)))
cycles=sorted(cyc_widths)
mat=np.array([[cyc_widths[c].get(p,0) for p in PORTS] for c in cycles])
n_cold=sum(1 for v in cyc_kind.values() if v=="COLD-CYCLE")
n_warm=sum(1 for v in cyc_kind.values() if v=="WARM-REBOOT")

# ---- (b) 負荷テスト構成別 time-to-fault (実測値) ----
# LOAD_RESULTS は run毎: (label, seconds_until_fault, faulted(bool), note)
LOAD_RESULTS = json.load(open(f"{D}/load_results.json"))

# ---- (c) スループット(クリア試行: 3card incl8820 の2完走 + excl8820) ----
def turns_of(path):
    ev=[]; pp=[]
    try:
        for l in open(path):
            r=json.loads(l)
            if r.get("event")=="turn":
                if r.get("eval_tps"): ev.append(r["eval_tps"])
                if r.get("pp_tps"): pp.append(r["pp_tps"])
    except FileNotFoundError: pass
    return ev,pp
ev_all=[]; pp_all=[]
for p in ["trials_hip_3card_incl8820.jsonl","trials_hip_excl8820.jsonl","trials_hip_run1.jsonl"]:
    e,p2=turns_of(f"{D}/{p}"); ev_all+=e; pp_all+=p2

# ================= 図 =================
plt.rcParams["font.family"]="DejaVu Sans"
fig=plt.figure(figsize=(15.5,4.9))
gs=fig.add_gridspec(1,3,width_ratios=[1.0,1.3,0.8])

# (a)
ax=fig.add_subplot(gs[0,0])
ax.imshow(mat,cmap="RdYlGn",vmin=0,vmax=16,aspect="auto")
ax.set_xticks(range(4)); ax.set_xticklabels(["SLOT2\n00:02","SLOT4\n00:03","SLOT8\n80:02","SLOT6\n80:03"],fontsize=8)
ax.set_yticks(range(len(cycles))); ax.set_yticklabels([f"cyc{c}{'C' if cyc_kind[c]=='COLD-CYCLE' else 'W'}" for c in cycles],fontsize=8)
for i in range(len(cycles)):
    for j in range(4): ax.text(j,i,f"x{mat[i,j]}",ha="center",va="center",fontsize=8,fontweight="bold")
ax.set_title(f"(a) Power-cycle: PCIe link width\n{n_cold} cold + {n_warm} warm = {len(cyc_pass)}/{len(cycles)} PASS (4 cards, x16, AER0)",fontsize=9.5)

# (b)
ax=fig.add_subplot(gs[0,1])
labels=[r["label"] for r in LOAD_RESULTS]
secs=[r["seconds"] for r in LOAD_RESULTS]
cols=["#d9534f" if r["faulted"] else "#5cb85c" for r in LOAD_RESULTS]
y=range(len(labels))
ax.barh(list(y),secs,color=cols,alpha=0.75)
for i,r in enumerate(LOAD_RESULTS):
    txt=("FAULT @%ds\n(GPU %s)"%(r["seconds"],r["note"])) if r["faulted"] else ("CLEAN %ds\n(%s)"%(r["seconds"],r["note"]))
    ax.text(r["seconds"]+40,i,txt,va="center",fontsize=8,fontweight="bold")
ax.set_yticks(list(y)); ax.set_yticklabels(labels,fontsize=8.5)
ax.invert_yaxis()
ax.set_xlabel("sustained inference load until GPUVM page fault (s)",fontsize=9)
ax.set_xlim(0,max(secs)*1.45)
ax.set_title("(b) Load stability by GPU config\nevery config WITH card 8820 (SLOT6) faults on node-5; excluding 8820 is clean",fontsize=9.5)
ax.grid(axis="x",alpha=0.3)

# (c)
ax=fig.add_subplot(gs[0,2])
if ev_all and pp_all:
    bp=ax.boxplot([ev_all,pp_all],labels=[f"eval\nmed {statistics.median(ev_all):.1f}",
                                          f"prompt\nmed {statistics.median(pp_all):.0f}"],
                  patch_artist=True,showmeans=True)
    for patch,c in zip(bp["boxes"],["#d9534f","#5cb85c"]): patch.set_facecolor(c); patch.set_alpha(0.6)
ax.set_ylabel("throughput (tok/s)",fontsize=9)
ax.set_title("(c) Throughput on successful turns (all runs)\n(healthy until the fault: not a perf issue)",fontsize=9.5)
ax.grid(axis="y",alpha=0.3)

fig.suptitle("mi25 4-card recovery re-validation: power-cycle 7/7 PASS, but inference load faults the SLOT6 GPU (8820)",
             fontsize=12.5,fontweight="bold")
fig.tight_layout(rect=[0,0,1,0.95])
fig.savefig(f"{D}/summary.png",dpi=120)
print("saved summary.png")
