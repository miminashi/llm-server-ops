#!/usr/bin/env python3
"""Emit the markdown result tables for the 3-arm MTP report from two run dirs."""
import argparse, json, os

MODES = ("layer", "tensor", "layer2")
LBL = {"layer": "layer 4枚", "tensor": "tensor 4枚", "layer2": "layer 2枚"}


def load(d, name):
    p = os.path.join(d, name)
    return json.load(open(p)) if os.path.exists(p) else None


def pct(new, old):
    return f"{(new / old - 1) * 100:+.0f}%" if old else "—"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--off", required=True)
    ap.add_argument("--on", required=True)
    ap.add_argument("--real-arm", default="tensor")
    a = ap.parse_args()

    off = {m: load(a.off, f"results-{m}.json") for m in MODES}
    on = {m: load(a.on, f"results-{m}.json") for m in MODES}
    off = {k: v for k, v in off.items() if v}
    on = {k: v for k, v in on.items() if v}
    off0 = {m: load(a.off, f"results-{m}-pp0.json") for m in off}
    on0 = {m: load(a.on, f"results-{m}-pp0.json") for m in on}

    # per-arm real
    real, factor = {}, {}
    for m in on:
        p = os.path.join(a.on, f"real-{m}", f"results-real-{m}.json")
        if not os.path.exists(p) and m == a.real_arm:
            p = os.path.join(a.on, "results-real.json")
        if os.path.exists(p):
            real[m] = json.load(open(p))
            rd = [e["decode_tok_s"] for e in real[m] if e.get("decode_tok_s")]
            factor[m] = sum(rd) / len(rd) / on[m][0]["predicted_per_second"]

    depths = [r["effective_depth"] for r in next(iter(on.values()))]
    arms = [m for m in MODES if m in on]

    print("### decode（合成テキスト実測、t/s）\n")
    hdr = "| 実効深さ (tok) | " + " | ".join(
        f"{LBL[m]} off | {LBL[m]} on | 伸び" for m in arms) + " |"
    print(hdr)
    print("|---:|" + "---:|---:|---:|" * len(arms))
    for i, d in enumerate(depths):
        cells = []
        for m in arms:
            o = off[m][i]["predicted_per_second"] if m in off else None
            n = on[m][i]["predicted_per_second"]
            cells += [f"{o:.2f}" if o else "—", f"**{n:.2f}**", pct(n, o) if o else "—"]
        print(f"| {d:,} | " + " | ".join(cells) + " |")
    cells = []
    for m in arms:
        o = off[m] if m in off else None
        cells += [f"{o[-1]['predicted_per_second']/o[0]['predicted_per_second']*100:.1f}%" if o else "—",
                  f"**{on[m][-1]['predicted_per_second']/on[m][0]['predicted_per_second']*100:.1f}%**", "—"]
    print("| **初段比の維持率** | " + " | ".join(cells) + " |")

    print("\n### 採択率（合成テキスト）\n")
    print("| 実効深さ (tok) | " + " | ".join(LBL[m] for m in arms) + " |")
    print("|---:|" + "---:|" * len(arms))
    for i, d in enumerate(depths):
        print(f"| {d:,} | " + " | ".join(
            f"{on[m][i]['draft_n_accepted']}/{on[m][i]['draft_n']} = {on[m][i]['draft_accept_rate']:.3f}"
            for m in arms) + " |")

    print("\n### 実プロンプト（腕別）\n")
    print("| 腕 | プロンプト | decode (t/s) | prefill (t/s) | draft_n | 採択 | 採択率 | tokens_per_cycle |")
    print("|---|---|---:|---:|---:|---:|---:|---:|")
    for m in arms:
        if m not in real:
            continue
        for e in real[m]:
            print(f"| {LBL[m]} | {e['prompt']} | {e['decode_tok_s']:.2f} | {e['prefill_tok_s']:.1f} | "
                  f"{e['draft_n']} | {e['accepted']} | **{e['accept_rate']:.3f}** | {e['tokens_per_cycle']} |")
        n = len(real[m])
        print(f"| {LBL[m]} | **平均** | **{sum(e['decode_tok_s'] for e in real[m])/n:.2f}** | "
              f"{sum(e['prefill_tok_s'] for e in real[m])/n:.1f} | — | — | "
              f"**{sum(e['accept_rate'] for e in real[m])/n:.3f}** | "
              f"{sum(e['tokens_per_cycle'] for e in real[m])/n:.3f} |")
    print("\n補正係数: " + " / ".join(f"{LBL[m]} = **{factor[m]:.3f}**" for m in factor))

    print("\n### decode（実運用補正後、t/s）\n")
    print("| 実効深さ (tok) | " + " | ".join(
        f"{LBL[m]} on 補正後 | 対 off" for m in arms if m in factor) + " |")
    print("|---:|" + "---:|---:|" * len([m for m in arms if m in factor]))
    for i, d in enumerate(depths):
        cells = []
        for m in arms:
            if m not in factor:
                continue
            v = on[m][i]["predicted_per_second"] * factor[m]
            o = off[m][i]["predicted_per_second"] if m in off else None
            cells += [f"**{v:.2f}**", pct(v, o) if o else "—"]
        print(f"| {d:,} | " + " | ".join(cells) + " |")

    print("\n### prefill（増分プロンプト評価、t/s。初段は仕様上除外）\n")
    print("| 実効深さ (tok) | " + " | ".join(f"{LBL[m]} off | {LBL[m]} on | 変化" for m in arms) + " |")
    print("|---:|" + "---:|---:|---:|" * len(arms))
    for i, d in enumerate(depths):
        if i == 0:
            continue
        cells = []
        for m in arms:
            o = off[m][i]["prompt_per_second"] if m in off else None
            n = on[m][i]["prompt_per_second"]
            cells += [f"{o:.1f}" if o else "—", f"**{n:.1f}**", pct(n, o) if o else "—"]
        print(f"| {d:,} | " + " | ".join(cells) + " |")

    print("\n### depth-0 prefill（新規プロンプト、t/s）\n")
    sizes = [k for k in next(iter(on0.values())) if k.startswith("pp")]
    print("| サイズ | " + " | ".join(f"{LBL[m]} off | {LBL[m]} on | 変化" for m in arms) + " |")
    print("|---|" + "---:|---:|---:|" * len(arms))
    for key in sizes:
        cells = []
        for m in arms:
            o = off0[m][key]["prompt_per_second"] if off0.get(m) else None
            n = on0[m][key]["prompt_per_second"]
            cells += [f"{o:.1f}" if o else "—", f"**{n:.1f}**", pct(n, o) if o else "—"]
        print(f"| {key} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
