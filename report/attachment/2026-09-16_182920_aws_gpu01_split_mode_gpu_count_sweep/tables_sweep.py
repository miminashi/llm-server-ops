#!/usr/bin/env python3
"""スイープ結果を Markdown 表にする。

  tables_sweep.py runs/gpu01-sweep-layer runs/gpu01-sweep-tensor
"""
import json, os, sys

def arms(prefix):
    return [(n, f"{prefix}{n}") for n in range(2, 7)] + [(7, prefix)]

def load(run_dir, prefix):
    out = {}
    for n, arm in arms(prefix):
        f = os.path.join(run_dir, f"results-{arm}.json")
        if not os.path.exists(f):
            continue
        lad = json.load(open(f))
        if isinstance(lad, dict) or not lad:
            continue
        rec = {"arm": arm, "ladder": lad, "pp0": None, "sampler": os.path.join(run_dir, f"sampler-{arm}.log")}
        p = os.path.join(run_dir, f"results-{arm}-pp0.json")
        if os.path.exists(p):
            rec["pp0"] = json.load(open(p))
        out[n] = rec
    return out

def sampler(path, ncards):
    keep = set(range(ncards)); u=[]; t=[]; p=[]
    if not os.path.exists(path):
        return None
    for ln in open(path):
        for card in ln.strip().split("|"):
            f=[c.strip() for c in card.split(",")]
            if len(f)<5 or not f[0].isdigit() or int(f[0]) not in keep: continue
            try: t.append(float(f[1])); p.append(float(f[3])); u.append(float(f[4]))
            except (ValueError, IndexError): pass
    if not u: return None
    return sum(u)/len(u), max(t), sum(t)/len(t), max(p), sum(p)/len(p)

def vram(rec, ncards):
    tot=0
    for ln in (rec["ladder"][0].get("gpu_before") or "").splitlines():
        f=[c.strip() for c in ln.split(",")]
        if len(f)<2 or not f[0].isdigit() or int(f[0])>=ncards: continue
        tot += float(f[1].split()[0])
    return tot or None

def table(data, key, label, depths):
    print(f"\n### {label}\n")
    print("| 実効深さ (tok) | " + " | ".join(f"{n} 枚" for n in sorted(data)) + " |")
    print("|---:|" + "---:|"*len(data))
    for i, d in enumerate(depths):
        row = []
        for n in sorted(data):
            lad = data[n]["ladder"]
            v = lad[i].get(key) if i < len(lad) else None
            row.append(f"{v:.2f}" if v is not None else "—")
        print(f"| {d:,} | " + " | ".join(row) + " |")

def main():
    ldir = sys.argv[1]
    tdir = sys.argv[2] if len(sys.argv) > 2 else ""
    for run_dir, prefix, name in ((ldir, "layer", "layer 分割"), (tdir, "tensor", "tensor 分割")):
        if not run_dir: continue
        data = load(run_dir, prefix)
        if not data:
            print(f"\n## {name}: 腕なし ({run_dir})"); continue
        depths = [r["effective_depth"] for r in data[min(data)]["ladder"]]
        print(f"\n## {name}  ({run_dir})")
        table(data, "predicted_per_second", "decode (t/s)", depths)
        table(data, "prompt_per_second", "増分 prefill (t/s)", depths)
        print("\n### depth-0 prefill (t/s)\n")
        print("| サイズ | " + " | ".join(f"{n} 枚" for n in sorted(data)) + " |")
        print("|---|" + "---:|"*len(data))
        for size in ("pp512", "pp2048", "pp8192"):
            row=[]
            for n in sorted(data):
                pp = data[n]["pp0"]
                v = pp.get(size, {}).get("prompt_per_second") if pp else None
                row.append(f"{v:.1f}" if v else "—")
            print(f"| {size} | " + " | ".join(row) + " |")
        print("\n### GPU 利用率・温度・電力・VRAM\n")
        print("| 枚数 | 利用率 平均 | 温度 最大/平均 | 電力 最大/平均 | VRAM 合計 | 1 枚あたり |")
        print("|---:|---:|---:|---:|---:|---:|")
        for n in sorted(data):
            s = sampler(data[n]["sampler"], n)
            v = vram(data[n], n)
            if s:
                print(f"| {n} | {s[0]:.1f}% | {s[1]:.0f}℃ / {s[2]:.1f}℃ | {s[3]:.0f} W / {s[4]:.0f} W | "
                      f"{v:,.0f} MiB | {v/n:,.0f} MiB |" if v else
                      f"| {n} | {s[0]:.1f}% | {s[1]:.0f}℃ / {s[2]:.1f}℃ | {s[3]:.0f} W / {s[4]:.0f} W | — | — |")
            else:
                print(f"| {n} | — | — | — | {v:,.0f} MiB | {v/n:,.0f} MiB |" if v else f"| {n} | — | — | — | — | — |")

main()
