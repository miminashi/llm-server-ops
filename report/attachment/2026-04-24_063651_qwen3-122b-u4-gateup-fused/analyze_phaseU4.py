#!/usr/bin/env python3
"""analyze_phaseU4.py - Phase U-4 旧 unsloth vs 新 fused の比較集計
入力: out_U4_{model}_{prompt}_r{round}[_warmup]/eval_run{1..N}.json
出力: u4_stats.csv, u4_pivot.md, prompt_tps_compare.png, eval_tps_compare.png
"""
import json
import glob
import os
import re
import csv
import statistics
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).parent
OUT_CSV = ROOT / 'u4_stats.csv'
OUT_PIVOT = ROOT / 'u4_pivot.md'
PLOT_PROMPT = ROOT / 'prompt_tps_compare.png'
PLOT_EVAL = ROOT / 'eval_tps_compare.png'

BASELINE_T5ATS2 = 18.664  # T-5a-ts2 B14b_ts_alt eval_tps baseline

rows = []
dir_re = re.compile(r'out_U4_(unsloth|fused)_(1k|code|repetitive)_r(\d+)(_warmup)?$')
for d in sorted(glob.glob(str(ROOT / 'out_U4_*'))):
    name = os.path.basename(d.rstrip('/'))
    m = dir_re.match(name)
    if not m:
        continue
    model, prompt, rnd, warmup = m.group(1), m.group(2), int(m.group(3)), bool(m.group(4))
    phase = 'warmup' if warmup else 'eval'
    for j in sorted(glob.glob(os.path.join(d, 'eval_run*.json'))):
        try:
            with open(j) as f:
                data = json.load(f)
        except Exception:
            continue
        t = data.get('timings', {})
        if not t:
            continue
        run = int(re.search(r'run(\d+)', os.path.basename(j)).group(1))
        rows.append({
            'model': model, 'prompt': prompt, 'round': rnd, 'phase': phase, 'run': run,
            'eval_tps': t.get('predicted_per_second'),
            'prompt_tps': t.get('prompt_per_second'),
            'prompt_ms': t.get('prompt_ms'),
            'prompt_n': t.get('prompt_n'),
            'predicted_n': t.get('predicted_n'),
            'cache_n': t.get('cache_n', 0),
        })

with open(OUT_CSV, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['model', 'prompt', 'round', 'phase', 'run', 'eval_tps', 'prompt_tps', 'prompt_ms', 'prompt_n', 'predicted_n', 'cache_n'])
    w.writeheader()
    w.writerows(rows)

from collections import defaultdict
grp = defaultdict(list)
for r in rows:
    grp[(r['model'], r['prompt'], r['phase'])].append(r)


def stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None, None, None
    med = statistics.median(vals)
    m = statistics.mean(vals)
    s = statistics.stdev(vals) if len(vals) > 1 else 0.0
    return med, m, s


PROMPTS = ['1k', 'code', 'repetitive']

with open(OUT_PIVOT, 'w') as f:
    f.write('# Phase U-4 比較集計\n\n')
    f.write(f'baseline (T-5a-ts2 B14b_ts_alt 1k eval): **{BASELINE_T5ATS2} t/s**\n\n')

    for (metric, label) in [('eval_tps', 'eval_tps (TG, tok/s)'),
                             ('prompt_tps', 'prompt_tps (PP, tok/s)')]:
        f.write(f'## {label} — eval phase のみ (5 run/prompt)\n\n')
        f.write('| prompt | unsloth median | fused median | Δ (tps) | Δ (%) | unsloth mean±σ | fused mean±σ |\n')
        f.write('|--------|---------------:|-------------:|--------:|------:|----------------|--------------|\n')
        for p in PROMPTS:
            u = [r[metric] for r in grp.get(('unsloth', p, 'eval'), [])]
            ff = [r[metric] for r in grp.get(('fused', p, 'eval'), [])]
            um, umean, us = stats(u)
            fm, fmean, fs = stats(ff)
            if um is None or fm is None:
                continue
            delta = fm - um
            pct = 100 * delta / um if um else 0
            f.write(f'| {p} | {um:.3f} | {fm:.3f} | {delta:+.3f} | {pct:+.2f}% | {umean:.3f}±{us:.3f} | {fmean:.3f}±{fs:.3f} |\n')
        f.write('\n')

# plots
for (metric, title, outpath, show_baseline) in [
    ('prompt_tps', 'Prompt TPS (PP) — unsloth vs fused (eval phase)', PLOT_PROMPT, False),
    ('eval_tps', 'Eval TPS (TG) — unsloth vs fused (eval phase)', PLOT_EVAL, True),
]:
    fig, ax = plt.subplots(figsize=(9, 5.5))
    x = np.arange(len(PROMPTS))
    w = 0.36
    u_meds = []
    f_meds = []
    u_errs = []
    f_errs = []
    for p in PROMPTS:
        um, _, us = stats([r[metric] for r in grp.get(('unsloth', p, 'eval'), [])])
        fm, _, fs = stats([r[metric] for r in grp.get(('fused', p, 'eval'), [])])
        u_meds.append(um or 0); f_meds.append(fm or 0)
        u_errs.append(us or 0); f_errs.append(fs or 0)

    ax.bar(x - w/2, u_meds, w, label='unsloth (separate gate/up, baseline)', color='#3A7CA5', yerr=u_errs, capsize=4)
    ax.bar(x + w/2, f_meds, w, label='fused (PR #19139 gate+up)', color='#D9704B', yerr=f_errs, capsize=4)
    for i, (u, fv) in enumerate(zip(u_meds, f_meds)):
        if u > 0:
            pct = 100 * (fv - u) / u
            color = '#8B0000' if pct < -1 else ('#006400' if pct > 1 else '#666')
            ax.annotate(f'{pct:+.1f}%', xy=(x[i] + w/2, fv), xytext=(0, 4),
                        textcoords='offset points', ha='center', fontsize=10, color=color, fontweight='bold')

    if show_baseline:
        ax.axhline(BASELINE_T5ATS2, color='#888', linestyle='--', linewidth=1, label=f'T-5a-ts2 baseline ({BASELINE_T5ATS2})')

    ax.set_xticks(x)
    ax.set_xticklabels([f'prompt_{p}' for p in PROMPTS])
    ax.set_ylabel('tokens/second')
    ax.set_title(title)
    ax.legend(loc='lower right')
    ax.grid(axis='y', alpha=0.3)
    fig.tight_layout()
    fig.savefig(outpath, dpi=120)
    plt.close(fig)

print(f'Rows: {len(rows)}')
print(f'CSV: {OUT_CSV}')
print(f'Pivot: {OUT_PIVOT}')
print(f'PNG: {PLOT_PROMPT}, {PLOT_EVAL}')
