#!/usr/bin/env python3
import csv, math, os, sys
import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
font_manager.fontManager.addfont("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf")
matplotlib.rcParams["font.family"] = "IPAGothic"
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt

CSV = "/tmp/mi25vk_bench/results/sweep.csv"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/mi25vk_bench/out"
os.makedirs(OUT, exist_ok=True)

def fnum(x):
    try: return float(x)
    except: return None

rows = []
with open(CSV) as fh:
    for r in csv.reader(fh):
        if len(r) < 15 or r[0] == "CELL": continue
        rows.append(r)

def evals(cond):
    return [fnum(r[6]) for r in rows if r[1] == cond and r[4] == "eval" and fnum(r[6])]

def mean_sd(v):
    v = [x for x in v if x is not None]
    m = sum(v)/len(v)
    sd = math.sqrt(sum((x-m)**2 for x in v)/(len(v)-1)) if len(v) > 1 else 0
    return m, sd

def _tcdf(t, df):
    x = df/(df+t*t)
    def betai(a, b, x):
        if x <= 0: return 0.0
        if x >= 1: return 1.0
        lb = math.lgamma(a)+math.lgamma(b)-math.lgamma(a+b)
        fr = math.exp(math.log(x)*a+math.log(1-x)*b-lb)/a
        f=c=1.0; d=0.0
        for i in range(200):
            mm=i//2
            if i==0: num=1.0
            elif i%2==0: num=(mm*(b-mm)*x)/((a+2*mm-1)*(a+2*mm))
            else: num=-((a+mm)*(a+b+mm)*x)/((a+2*mm)*(a+2*mm+1))
            d=1.0+num*d; d=1e-30 if abs(d)<1e-30 else d; d=1.0/d
            c=1.0+num/c; c=1e-30 if abs(c)<1e-30 else c
            f*=d*c
            if abs(1.0-d*c)<1e-8: break
        return fr*(f-1.0)
    return 1-0.5*betai(df/2,0.5,x)

def welch_p(a, b):
    a=[x for x in a if x]; b=[x for x in b if x]
    if len(a)<2 or len(b)<2: return 1.0
    na,nb=len(a),len(b); ma,mb=sum(a)/na,sum(b)/nb
    va=sum((x-ma)**2 for x in a)/(na-1); vb=sum((x-mb)**2 for x in b)/(nb-1)
    se=math.sqrt(va/na+vb/nb)
    if se==0: return 1.0
    t=(mb-ma)/se
    df=(va/na+vb/nb)**2/((va/na)**2/(na-1)+(vb/nb)**2/(nb-1))
    return 2*(1-_tcdf(abs(t),df))

# 32k 条件 (表示順)。1k と end は別扱い
order = [
    ("B0_baseline_32k", "baseline\n(auto, 32k)"),
    ("E1a_mmvq_force", "E1 MMVQ\nforce"),
    ("E1b_mmvq_disable", "E1 MMVQ\ndisable"),
    ("E5a_ub4096", "E5 ub4096"),
    ("E5b_ub1024", "E5 ub1024"),
    ("E5c_ub512", "E5 ub512"),
    ("E6_sm_row", "E6 split\nrow"),
    ("E7_xfer_queue", "E7 xfer\nqueue"),
    ("E8a_threads6", "E8 t=6"),
    ("E8b_threads24", "E8 t=24"),
    ("E9_maingpu1", "E9 mg=1"),
    ("E10_suballoc2g", "E10 sub\nalloc2G"),
    ("E11_no_hostvis_vidmem", "E11 no\nhostvis"),
    ("D2_no_intdot", "D2 no\nint-dot"),
    ("D3_no_fusion", "D3 no\nfusion"),
]
base = evals("B0_baseline_32k")
bstart, _ = mean_sd(base)
bend, _ = mean_sd(evals("B0_baseline_end"))
lo, hi = min(bstart, bend), max(bstart, bend)

labels, means, sds, colors = [], [], [], []
for cond, lab in order:
    v = evals(cond)
    if not v: continue
    m, sd = mean_sd(v)
    labels.append(lab); means.append(m); sds.append(sd)
    p = welch_p(base, v)
    if cond == "B0_baseline_32k":
        colors.append("#555")
    elif p >= 0.05:
        colors.append("#4a90d9")   # 有意差なし = 基準を改善せず
    elif m < bstart:
        colors.append("#d9534f")   # 有意に低い (既定最適化を無効化した診断=劣化)
    else:
        colors.append("#5cb85c")   # 有意に高い (該当なし)

fig, ax = plt.subplots(figsize=(13, 5.6))
x = range(len(labels))
ax.bar(x, means, yerr=sds, capsize=3, color=colors, zorder=3)
# drift 帯 (起点-終点 baseline)
ax.axhspan(lo, hi, color="#999", alpha=0.18, zorder=1,
           label=f"baseline drift帯 {lo:.2f}–{hi:.2f} t/s")
ax.axhline(bstart, color="#333", ls="--", lw=1, zorder=2)
for i, (m, sd) in enumerate(zip(means, sds)):
    d = (m - bstart)/bstart*100
    ax.text(i, m + sd + 0.12, f"{d:+.1f}%", ha="center", va="bottom", fontsize=7.5)
ax.set_ylim(0, max(means)+2.2)
ax.set_ylabel("eval throughput (tok/s)  ※32k深コンテキスト, N=5, mean±sd")
ax.set_title("MI25+Vulkan eval スループット: パラメータ/env-var 探索 (基準=auto構成, 全14条件 N=5)\n"
             "基準を有意に改善した条件はゼロ(正Δは全て p>0.05)。"
             "有意差は既定最適化の無効化による劣化のみ(赤=E11/D3, p<0.01)。drift -1.4%。")
ax.set_xticks(list(x)); ax.set_xticklabels(labels, fontsize=7.5)
ax.legend(loc="upper right", fontsize=8)
ax.grid(axis="y", alpha=0.25, zorder=0)
fig.tight_layout()
p = os.path.join(OUT, "eval_param_sweep.png")
fig.savefig(p, dpi=130)
print("saved", p, "baseline_start=%.2f end=%.2f"%(bstart,bend))
