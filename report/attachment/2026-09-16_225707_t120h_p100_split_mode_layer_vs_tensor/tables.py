#!/usr/bin/env python3
"""llama-split-bench の run ディレクトリから、レポート用の表を生成する。"""
import json, sys, os, statistics

d = sys.argv[1]
modes = sys.argv[2].split(',') if len(sys.argv) > 2 else ['layer', 'tensor', 'layer2']

def load(p):
    with open(p) as f:
        return json.load(f)

info = load(os.path.join(d, 'run-info.json'))
print("## run-info")
for k in ('tag', 'started', 'ctx', 'stages', 'n_predict', 'machine', 'bin', 'bin_version',
          'bin_sha256', 'cache_k', 'cache_v', 'launch_prefix', 'tensor_split'):
    if k in info:
        print(f"- {k}: {info[k]}")
print("- modes:", json.dumps(info.get('modes'), ensure_ascii=False))

res = {}
for m in modes:
    p = os.path.join(d, f'results-{m}.json')
    if os.path.exists(p):
        res[m] = load(p)

print("\n## decode (t/s)")
print("| 実効深さ (tok) | " + " | ".join(modes) + " |")
print("|---:|" + "---:|" * len(modes))
rows = res[modes[0]]['stages'] if 'stages' in res[modes[0]] else res[modes[0]]
for i in range(len(rows)):
    depth = rows[i]['effective_depth']
    cells = []
    for m in modes:
        r = res[m]['stages'] if 'stages' in res[m] else res[m]
        cells.append(f"{r[i]['predicted_per_second']:.2f}")
    print(f"| {depth:,} | " + " | ".join(cells) + " |")
# 維持率
cells = []
for m in modes:
    r = res[m]['stages'] if 'stages' in res[m] else res[m]
    cells.append(f"{100*r[-1]['predicted_per_second']/r[0]['predicted_per_second']:.1f}%")
print("| **初段比の維持率** | " + " | ".join(cells) + " |")

print("\n## prefill 増分 (t/s)")
print("| 実効深さ (tok) | " + " | ".join(modes) + " |")
print("|---:|" + "---:|" * len(modes))
for i in range(len(rows)):
    depth = rows[i]['effective_depth']
    cells = []
    for m in modes:
        r = res[m]['stages'] if 'stages' in res[m] else res[m]
        cells.append(f"{r[i]['prompt_per_second']:.1f}")
    print(f"| {depth:,} | " + " | ".join(cells) + " |")

print("\n## depth-0 prefill (t/s)")
pp = {}
for m in modes:
    p = os.path.join(d, f'results-{m}-pp0.json')
    if os.path.exists(p):
        pp[m] = load(p)
if pp:
    first = pp[modes[0]]
    items = first['sizes'] if isinstance(first, dict) and 'sizes' in first else first
    print("| サイズ | " + " | ".join(modes) + " |")
    print("|---|" + "---:|" * len(modes))
    for i in range(len(items)):
        label = items[i].get('size') or items[i].get('pp') or items[i].get('n')
        cells = []
        for m in modes:
            o = pp[m]['sizes'] if isinstance(pp[m], dict) and 'sizes' in pp[m] else pp[m]
            cells.append(f"{o[i]['prefill_per_second' if 'prefill_per_second' in o[i] else 'prompt_per_second']:.1f}")
        print(f"| pp{label} | " + " | ".join(cells) + " |")

rp = os.path.join(d, 'results-real.json')
if os.path.exists(rp):
    print("\n## 実プロンプト補正")
    print(json.dumps(load(rp), ensure_ascii=False, indent=1)[:1500])
