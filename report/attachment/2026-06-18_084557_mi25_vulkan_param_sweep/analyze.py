#!/usr/bin/env python3
"""mi25+Vulkan パラメータ探索ベンチ 集計・統計・作図.
CSV 列: CELL,COND_ID,UB,PROMPT_TAG,role,idx,eval_tps,prompt_tps,prompt_n,
         predicted_n,prompt_ms,predicted_ms,wallclock,max_gpu_used,err
role=eval の行のみ集計。COND_ID 単位で mean/std/CV、baseline(B0) との Welch t 検定。
"""
import csv, glob, math, sys, os
from collections import defaultdict

RESULTS_DIR = sys.argv[1] if len(sys.argv) > 1 else "/tmp/mi25vk_bench/results"
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "/tmp/mi25vk_bench/out"
BASELINE = sys.argv[3] if len(sys.argv) > 3 else "B0_baseline_32k"
os.makedirs(OUT_DIR, exist_ok=True)

def fnum(x):
    try: return float(x)
    except: return None

# rows[cell] = list of dict
rows = []
for f in sorted(glob.glob(os.path.join(RESULTS_DIR, "*.csv"))):
    with open(f) as fh:
        for r in csv.reader(fh):
            if len(r) < 15: continue
            if r[0] == "CELL": continue
            rows.append(dict(cell=r[0], cond=r[1], ub=r[2], tag=r[3], role=r[4],
                             idx=r[5], eval_tps=fnum(r[6]), prompt_tps=fnum(r[7]),
                             prompt_n=fnum(r[8]), pred_n=fnum(r[9]),
                             wall=fnum(r[12]), vram=fnum(r[13]), err=r[14]))

def stats(vals):
    vals = [v for v in vals if v is not None]
    n = len(vals)
    if n == 0: return (0, None, None, None)
    m = sum(vals)/n
    if n > 1:
        var = sum((v-m)**2 for v in vals)/(n-1)
        sd = math.sqrt(var)
    else:
        sd = 0.0
    cv = (sd/m*100) if m else None
    return (n, m, sd, cv)

def welch_t(a, b):
    a = [v for v in a if v is not None]; b = [v for v in b if v is not None]
    if len(a) < 2 or len(b) < 2: return (None, None)
    na, nb = len(a), len(b)
    ma, mb = sum(a)/na, sum(b)/nb
    va = sum((v-ma)**2 for v in a)/(na-1)
    vb = sum((v-mb)**2 for v in b)/(nb-1)
    se = math.sqrt(va/na + vb/nb)
    if se == 0: return (None, None)
    t = (mb-ma)/se
    df = (va/na+vb/nb)**2 / ((va/na)**2/(na-1)+(vb/nb)**2/(nb-1))
    # 両側 p 値 (Welch-Satterthwaite df) を Student-t CDF で近似
    p = 2*(1-_t_cdf(abs(t), df))
    return (t, p)

def _t_cdf(t, df):
    # incomplete beta による t 分布 CDF
    x = df/(df+t*t)
    ib = _betainc(df/2, 0.5, x)
    return 1 - 0.5*ib

def _betainc(a, b, x):
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    lbeta = math.lgamma(a)+math.lgamma(b)-math.lgamma(a+b)
    front = math.exp(math.log(x)*a + math.log(1-x)*b - lbeta)/a
    f, c, d = 1.0, 1.0, 0.0
    for i in range(0, 200):
        m = i//2
        if i == 0: num = 1.0
        elif i % 2 == 0: num = (m*(b-m)*x)/((a+2*m-1)*(a+2*m))
        else: num = -((a+m)*(a+b+m)*x)/((a+2*m)*(a+2*m+1))
        d = 1.0+num*d
        if abs(d) < 1e-30: d = 1e-30
        d = 1.0/d
        c = 1.0+num/c
        if abs(c) < 1e-30: c = 1e-30
        f *= d*c
        if abs(1.0-d*c) < 1e-8: break
    return front*(f-1.0)

# COND 単位集計 (eval rows)
conds = defaultdict(lambda: defaultdict(list))  # cond -> metric -> vals
order = []
for r in rows:
    c = r["cond"]
    # eval_tps は eval run (prompt cache 命中・32k 深コンテキスト) から
    if r["role"] == "eval":
        if c not in order: order.append(c)
        conds[c]["eval"].append(r["eval_tps"])
        conds[c]["vram"].append(r["vram"])
    # prompt_tps は warmup1 (サーバ再起動直後=コールド・キャッシュ空) のみ採用
    if r["role"] == "warmup" and r["idx"] == "1":
        conds[c]["prompt"].append(r["prompt_tps"])

base_eval = conds.get(BASELINE, {}).get("eval", [])
base_prompt = conds.get(BASELINE, {}).get("prompt", [])

print(f"{'COND':<26}{'N':>3} {'eval mean±sd':>16} {'CV%':>6} {'Δ%':>7} {'t':>6} {'p':>7} {'prompt':>9} {'VRAM':>7}")
print("-"*100)
summary = []
for c in order:
    n, m, sd, cv = stats(conds[c]["eval"])
    _, pm, _, _ = stats(conds[c]["prompt"])
    _, vm, _, _ = stats(conds[c]["vram"])
    if base_eval and m and c != BASELINE:
        _, bm, _, _ = stats(base_eval)
        delta = (m-bm)/bm*100 if bm else None
        t, p = welch_t(base_eval, conds[c]["eval"])
    else:
        delta, t, p = (0.0 if c == BASELINE else None), None, None
    summary.append(dict(cond=c, n=n, eval=m, sd=sd, cv=cv, delta=delta, t=t, p=p, prompt=pm, vram=vm))
    ds = f"{delta:+.2f}" if delta is not None else "  -"
    ts = f"{t:.2f}" if t is not None else "  -"
    ps = f"{p:.4f}" if p is not None else "  -"
    print(f"{c:<26}{n:>3} {m:>10.2f}±{sd:<4.2f} {cv:>6.1f} {ds:>7} {ts:>6} {ps:>7} {pm:>9.1f} {vm or 0:>6.0f}M")

# 作図
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    s2 = [x for x in summary if x["eval"]]
    labels = [x["cond"] for x in s2]
    evals = [x["eval"] for x in s2]
    sds = [x["sd"] or 0 for x in s2]
    fig, ax = plt.subplots(figsize=(max(8, len(labels)*0.7), 5))
    colors = ["#888" if c == BASELINE else ("#2a8" if (x["delta"] or 0) > 0 else "#c55")
              for c, x in zip(labels, s2)]
    ax.bar(range(len(labels)), evals, yerr=sds, capsize=4, color=colors)
    if base_eval:
        _, bm, _, _ = stats(base_eval)
        ax.axhline(bm, color="#444", ls="--", lw=1, label=f"baseline {bm:.2f} t/s")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("eval throughput (tok/s)")
    ax.set_title("mi25+Vulkan eval t/s by condition (mean±sd, N runs)")
    ax.legend()
    fig.tight_layout()
    p1 = os.path.join(OUT_DIR, "eval_by_condition.png")
    fig.savefig(p1, dpi=120)
    print(f"\nsaved: {p1}")
except Exception as e:
    print(f"plot skipped: {e}")
