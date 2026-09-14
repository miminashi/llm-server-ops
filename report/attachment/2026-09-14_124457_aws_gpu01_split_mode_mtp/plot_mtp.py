#!/usr/bin/env python3
"""MTP on/off comparison figure for llama-split-bench runs on aws-gpu01.

Reads two finished runs/<tag> directories (MTP off = the 2026-09-14 baseline run,
MTP on = this run) and renders a 2x2 comparison.

Encoding (composite, so color never carries MTP state alone):
  color     = split configuration   (layer 7-way / tensor 7-way / layer 2-way)
  linestyle = MTP off (dashed) vs MTP on (solid)
Palette validated with the dataviz validator (light surface, all six checks PASS).
"""
import argparse, json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

COL = {"layer": "#1f77b4", "tensor": "#d62728", "layer2": "#9467bd"}
NAME_JA = {"layer": "layer 7枚", "tensor": "tensor 7枚", "layer2": "layer 2枚"}
NAME_EN = {"layer": "layer 7-way", "tensor": "tensor 7-way", "layer2": "layer 2-way"}
INK, MUTED, GRID = "#1a1a1a", "#5a5a5a", "#d8d8d4"
SURF = "#fcfcfb"


def load(d, mode):
    p = os.path.join(d, f"results-{mode}.json")
    return json.load(open(p)) if os.path.exists(p) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--off", required=True, help="runs/<tag> of the MTP-off run")
    ap.add_argument("--on", required=True, help="runs/<tag> of the MTP-on run")
    ap.add_argument("--lang", default="ja", choices=["ja", "en"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ja = a.lang == "ja"
    N = NAME_JA if ja else NAME_EN
    plt.rcParams["font.family"] = ["Noto Sans CJK JP"] if ja else ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    off = {m: load(a.off, m) for m in ("layer", "tensor", "layer2")}
    on = {m: load(a.on, m) for m in ("layer", "tensor", "layer2")}
    off = {k: v for k, v in off.items() if v}
    on = {k: v for k, v in on.items() if v}

    factor = None
    realp = os.path.join(a.on, "results-real.json")
    if os.path.exists(realp):
        rr = json.load(open(realp))
        rd = [e["decode_tok_s"] for e in rr if e.get("decode_tok_s")]
        base = (on.get("layer") or next(iter(on.values())))[0]["predicted_per_second"]
        if rd and base:
            factor = (sum(rd) / len(rd)) / base

    ref = on.get("layer") or next(iter(on.values()))
    x = list(range(len(ref)))
    xlab = [f"{r['effective_depth']:,}" for r in ref]

    fig, axes = plt.subplots(2, 2, figsize=(15.5, 10.2), facecolor=SURF)
    for ax in axes.ravel():
        ax.set_facecolor(SURF)
        ax.grid(True, color=GRID, lw=0.8, zorder=0)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(GRID)
        ax.tick_params(colors=MUTED, labelsize=9.5)
        ax.set_xticks(x)
        ax.set_xticklabels(xlab)

    def line(ax, rows, mode, key, mtp_on):
        y = [r[key] for r in rows]
        ax.plot(x[:len(y)], y, color=COL[mode], lw=2.0,
                ls="-" if mtp_on else (0, (6, 3)),
                marker="o" if mtp_on else "s", ms=6,
                markeredgecolor=SURF, markeredgewidth=1.4, zorder=3,
                label=f"{N[mode]} · MTP {'on' if mtp_on else 'off'}")
        ax.annotate(f"{y[-1]:.1f}", (x[len(y) - 1], y[-1]), textcoords="offset points",
                    xytext=(7, 0), color=COL[mode], fontsize=9.5,
                    fontweight="bold" if mtp_on else "normal", va="center")

    # (1) decode
    ax = axes[0][0]
    for m, rows in off.items():
        line(ax, rows, m, "predicted_per_second", False)
    for m, rows in on.items():
        line(ax, rows, m, "predicted_per_second", True)
    if factor:
        for m, rows in on.items():
            y = [r["predicted_per_second"] * factor for r in rows]
            ax.plot(x[:len(y)], y, color=COL[m], lw=1.3, ls=(0, (2, 2)), alpha=0.75, zorder=2,
                    label=f"{N[m]} · MTP on{'（実運用推定）' if ja else ' (real est.)'}")
            ax.annotate(f"{y[-1]:.1f}", (x[len(y) - 1], y[-1]), textcoords="offset points",
                        xytext=(7, 0), color=COL[m], fontsize=8.5, alpha=0.85, va="center")
    ax.set_title("① decode (平均生成速度) — MTP on/off" if ja else
                 "(1) decode (mean generation speed) - MTP on/off",
                 loc="left", color=INK, fontsize=12.5, fontweight="bold", pad=9)
    ax.set_ylabel("t/s", color=MUTED, fontsize=10)
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=8.2, frameon=False, labelcolor=MUTED, ncol=2, loc="lower left")

    # (2) MTP gain on decode
    ax = axes[0][1]
    modes = [m for m in on if m in off]
    variants = [("syn", 1.0), ("real", factor)] if factor else [("syn", 1.0)]
    nb = len(modes) * len(variants)
    w = 0.82 / max(1, nb)
    b = 0
    for m in modes:
        for kind, f in variants:
            g = [(on[m][k]["predicted_per_second"] * f / off[m][k]["predicted_per_second"] - 1) * 100
                 for k in range(min(len(on[m]), len(off[m])))]
            pos = [xx - 0.41 + w * (b + 0.5) for xx in x[:len(g)]]
            lab = N[m] + ("" if kind == "syn" else ("（実運用推定）" if ja else " (real est.)"))
            ax.bar(pos, g, width=w * 0.82, color=COL[m], zorder=3, label=lab,
                   alpha=1.0 if kind == "syn" else 0.42,
                   edgecolor=COL[m], linewidth=0 if kind == "syn" else 1.2)
            for px, gv in zip(pos, g):
                ax.annotate(f"{gv:+.0f}", (px, gv), textcoords="offset points", xytext=(0, 3),
                            ha="center", color=MUTED, fontsize=7.6)
            b += 1
    ax.axhline(0, color=MUTED, lw=1.0, zorder=2)
    ax.set_title(("② MTP による decode の伸び率 [%%]（濃 = 合成 / 淡 = 実運用補正 ×%.3f）" % (factor or 1)) if ja else
                 ("(2) decode gain from MTP [%%] (solid = synthetic, faded = real x%.3f)" % (factor or 1)),
                 loc="left", color=INK, fontsize=12.5, fontweight="bold", pad=9)
    ax.set_ylabel("%", color=MUTED, fontsize=10)
    ax.legend(fontsize=8.2, frameon=False, labelcolor=MUTED, ncol=2, loc="upper left")

    # (3) prefill
    ax = axes[1][0]
    for m, rows in off.items():
        line(ax, rows[1:], m, "prompt_per_second", False)
    for m, rows in on.items():
        line(ax, rows[1:], m, "prompt_per_second", True)
    ax.set_xticks(x[:len(ref) - 1])
    ax.set_xticklabels(xlab[1:])
    ax.set_title("③ prefill (増分プロンプト評価速度) — ラダー初段は仕様上除外" if ja else
                 "(3) prefill (incremental prompt eval) - first ladder stage excluded",
                 loc="left", color=INK, fontsize=12.5, fontweight="bold", pad=9)
    ax.set_ylabel("t/s", color=MUTED, fontsize=10)
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=9, frameon=False, labelcolor=MUTED, ncol=2, loc="lower left")

    # (4) acceptance
    ax = axes[1][1]
    for i, m in enumerate(on):
        r = [(row["draft_accept_rate"] or 0) * 100 for row in on[m]]
        pos = [xx - 0.4 + w * (i + 0.5) for xx in x[:len(r)]]
        ax.bar(pos, r, width=w * 0.86, color=COL[m], zorder=3, label=N[m])
        for px, rv in zip(pos, r):
            ax.annotate(f"{rv:.0f}%", (px, rv), textcoords="offset points", xytext=(0, 3),
                        ha="center", color=MUTED, fontsize=8.5)
    if os.path.exists(realp):
        rr = json.load(open(realp))
        vals = [p["accept_rate"] for p in rr if p.get("accept_rate")]
        if vals:
            mv = sum(vals) / len(vals) * 100
            ax.axhline(mv, color=INK, lw=1.6, ls=(0, (5, 3)), zorder=4)
            ax.text(0.5, mv + 1.5, ("実プロンプトでの平均採択率 %.0f%%" % mv) if ja
                    else ("real-prompt mean acceptance %.0f%%" % mv),
                    color=INK, fontsize=9.5, va="bottom", ha="center",
                    transform=ax.get_yaxis_transform(which="grid") if False else ax.transData)
    ax.set_ylim(0, 122)
    ax.set_title("④ MTP ドラフト採択率（合成テキスト）" if ja else
                 "(4) MTP draft acceptance rate (synthetic text)",
                 loc="left", color=INK, fontsize=12.5, fontweight="bold", pad=9)
    ax.set_ylabel("%", color=MUTED, fontsize=10)
    ax.legend(fontsize=9, frameon=False, labelcolor=MUTED, ncol=2, loc="upper left")

    for ax in axes.ravel():
        ax.set_xlabel("実効深さ (tok)" if ja else "effective depth (tok)", color=MUTED, fontsize=10)

    info = json.load(open(os.path.join(a.on, "run-info.json")))
    sup = (f"aws-gpu01 — Tesla P100-PCIE-16GB ×7 / Qwen3.8-27B UD-Q4_K_XL / KV q8_0 / -fa on / ctx={info['ctx']:,}"
           f"\nMTP off = {os.path.basename(a.off)} ／ MTP on = {os.path.basename(a.on)}"
           f"（--spec-type draft-mtp --spec-draft-n-max 2）。tensor 分割は MTP と併用すると初期化がハングするため MTP on の腕が無い")
    if not ja:
        sup = (f"aws-gpu01 - Tesla P100-PCIE-16GB x7 / Qwen3.8-27B UD-Q4_K_XL / KV q8_0 / -fa on / ctx={info['ctx']:,}"
               f"\nMTP off = {os.path.basename(a.off)} / MTP on = {os.path.basename(a.on)}"
               f" (--spec-type draft-mtp --spec-draft-n-max 2). tensor split hangs at init with MTP, so it has no MTP-on arm")
    fig.suptitle(sup, x=0.005, ha="left", color=INK, fontsize=11.5)
    fig.tight_layout(rect=(0, 0, 1, 0.935))
    fig.savefig(a.out, dpi=130, facecolor=SURF)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
