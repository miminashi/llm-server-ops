#!/usr/bin/env python3
"""MTP on/off comparison figure for llama-split-bench runs on aws-gpu01 (3-arm edition).

Reads two finished runs/<tag> directories (MTP off = the 2026-09-14 baseline run,
MTP on = this run) and renders a 2x2 comparison.

Difference from the first edition (plot_mtp.py, 2026-09-14):
  * the MTP-on run now has a tensor arm too (GGML_CUDA_ALLREDUCE=none works around
    the NCCL start-up hang), so all six series exist.
  * the real-operation correction factor is computed PER ARM instead of taking a
    single factor from the layer arm and applying it everywhere.  Each arm's real
    prompts live in <on>/results-real.json (the arm run-bench.sh picked) plus
    <on>/real-<arm>/results-real-<arm>.json for the arms measured afterwards.

Encoding (composite, so color never carries MTP state alone):
  color     = split configuration   (layer 7-way / tensor 7-way / layer 2-way)
  linestyle = MTP off (dashed) vs MTP on (solid)
"""
import argparse, json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MODES = ("layer", "tensor", "layer2")
COL = {"layer": "#1f77b4", "tensor": "#d62728", "layer2": "#9467bd"}
NAME_JA = {"layer": "layer 7枚", "tensor": "tensor 7枚", "layer2": "layer 2枚"}
NAME_EN = {"layer": "layer 7-way", "tensor": "tensor 7-way", "layer2": "layer 2-way"}
INK, MUTED, GRID = "#1a1a1a", "#5a5a5a", "#d8d8d4"
SURF = "#fcfcfb"


def load(d, mode):
    p = os.path.join(d, f"results-{mode}.json")
    return json.load(open(p)) if os.path.exists(p) else None


def real_path(on_dir, mode, primary_arm):
    """Where this arm's real-prompt records live."""
    sub = os.path.join(on_dir, f"real-{mode}", f"results-real-{mode}.json")
    if os.path.exists(sub):
        return sub
    main = os.path.join(on_dir, "results-real.json")
    if mode == primary_arm and os.path.exists(main):
        return main
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--off", required=True, help="runs/<tag> of the MTP-off run")
    ap.add_argument("--on", required=True, help="runs/<tag> of the MTP-on run")
    ap.add_argument("--real-arm", default="tensor",
                    help="arm that run-bench.sh measured into results-real.json")
    ap.add_argument("--lang", default="ja", choices=["ja", "en"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ja = a.lang == "ja"
    N = NAME_JA if ja else NAME_EN
    plt.rcParams["font.family"] = ["Noto Sans CJK JP"] if ja else ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    off = {m: v for m in MODES if (v := load(a.off, m))}
    on = {m: v for m in MODES if (v := load(a.on, m))}

    # per-arm real-operation correction factor + real acceptance rate
    factor, real_acc = {}, {}
    for m in on:
        p = real_path(a.on, m, a.real_arm)
        if not p:
            continue
        rr = json.load(open(p))
        rd = [e["decode_tok_s"] for e in rr if e.get("decode_tok_s")]
        ac = [e["accept_rate"] for e in rr if e.get("accept_rate")]
        base = on[m][0]["predicted_per_second"]
        if rd and base:
            factor[m] = (sum(rd) / len(rd)) / base
        if ac:
            real_acc[m] = sum(ac) / len(ac)

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
    for m, rows in on.items():
        if m not in factor:
            continue
        y = [r["predicted_per_second"] * factor[m] for r in rows]
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
    nb = sum(1 + (1 if m in factor else 0) for m in modes)
    w = 0.82 / max(1, nb)
    b = 0
    for m in modes:
        variants = [("syn", 1.0)] + ([("real", factor[m])] if m in factor else [])
        for kind, f in variants:
            g = [(on[m][k]["predicted_per_second"] * f / off[m][k]["predicted_per_second"] - 1) * 100
                 for k in range(min(len(on[m]), len(off[m])))]
            pos = [xx - 0.41 + w * (b + 0.5) for xx in x[:len(g)]]
            lab = N[m] + ("" if kind == "syn" else
                          (("（実運用 ×%.3f）" % f) if ja else (" (real x%.3f)" % f)))
            ax.bar(pos, g, width=w * 0.82, color=COL[m], zorder=3, label=lab,
                   alpha=1.0 if kind == "syn" else 0.42,
                   edgecolor=COL[m], linewidth=0 if kind == "syn" else 1.2)
            for px, gv in zip(pos, g):
                ax.annotate(f"{gv:+.0f}", (px, gv), textcoords="offset points", xytext=(0, 3),
                            ha="center", color=MUTED, fontsize=7.0)
            b += 1
    ax.axhline(0, color=MUTED, lw=1.0, zorder=2)
    ax.set_title("② MTP による decode の伸び率 [%]（淡 = 腕別の実運用補正）" if ja else
                 "(2) decode gain from MTP [%] (faded = per-arm real)",
                 loc="left", color=INK, fontsize=12.5, fontweight="bold", pad=9)
    ax.set_ylabel("%", color=MUTED, fontsize=10)
    lo, hi = ax.get_ylim()
    ax.set_ylim(lo, hi + (hi - lo) * 0.30)
    ax.legend(fontsize=7.6, frameon=False, labelcolor=MUTED, ncol=3, loc="upper left")

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
    wa = 0.82 / max(1, len(on))
    for i, m in enumerate(on):
        r = [(row["draft_accept_rate"] or 0) * 100 for row in on[m]]
        pos = [xx - 0.41 + wa * (i + 0.5) for xx in x[:len(r)]]
        ax.bar(pos, r, width=wa * 0.86, color=COL[m], zorder=3, label=N[m])
        for px, rv in zip(pos, r):
            ax.annotate(f"{rv:.0f}%", (px, rv), textcoords="offset points", xytext=(0, 3),
                        ha="center", color=MUTED, fontsize=8.0)
    for j, (m, av) in enumerate(sorted(real_acc.items(), key=lambda kv: kv[1])):
        mv = av * 100
        ax.axhline(mv, color=COL[m], lw=1.6, ls=(0, (5, 3)), zorder=4)
        ax.text(-0.46 + j * 1.45, mv + 1.4,
                (("%s 実プロンプト %.0f%%" % (N[m], mv)) if ja
                 else ("%s real %.0f%%" % (N[m], mv))),
                color=COL[m], fontsize=8.8, va="bottom", ha="left", zorder=6,
                bbox=dict(boxstyle="round,pad=0.18", fc=SURF, ec="none", alpha=0.92))
    ax.set_ylim(0, 125)
    ax.set_title("④ MTP ドラフト採択率（棒 = 合成 / 破線 = 実プロンプト）" if ja else
                 "(4) MTP draft acceptance (bars = synthetic, dashed = real)",
                 loc="left", color=INK, fontsize=12.5, fontweight="bold", pad=9)
    ax.set_ylabel("%", color=MUTED, fontsize=10)
    ax.legend(fontsize=8.6, frameon=False, labelcolor=MUTED, ncol=3, loc="upper left")

    for ax in axes.ravel():
        ax.set_xlabel("実効深さ (tok)" if ja else "effective depth (tok)", color=MUTED, fontsize=10)

    info = json.load(open(os.path.join(a.on, "run-info.json")))
    if ja:
        sup = (f"aws-gpu01 — Tesla P100-PCIE-16GB ×7 / Qwen3.8-27B UD-Q4_K_XL / KV q8_0 / -fa on / ctx={info['ctx']:,}"
               f"\nMTP off = {os.path.basename(a.off)} ／ MTP on = {os.path.basename(a.on)}"
               f"（--spec-type draft-mtp --spec-draft-n-max 2）。"
               f"tensor 腕は GGML_CUDA_ALLREDUCE=none で起動時ハングを回避して取得")
    else:
        sup = (f"aws-gpu01 - Tesla P100-PCIE-16GB x7 / Qwen3.8-27B UD-Q4_K_XL / KV q8_0 / -fa on / ctx={info['ctx']:,}"
               f"\nMTP off = {os.path.basename(a.off)} / MTP on = {os.path.basename(a.on)}"
               f" (--spec-type draft-mtp --spec-draft-n-max 2). "
               f"the tensor arm uses GGML_CUDA_ALLREDUCE=none to avoid the start-up hang")
    fig.suptitle(sup, x=0.005, ha="left", color=INK, fontsize=11.5)
    fig.tight_layout(rect=(0, 0, 1, 0.935))
    fig.savefig(a.out, dpi=130, facecolor=SURF)
    print("wrote", a.out, "factors:", {k: round(v, 3) for k, v in factor.items()})


if __name__ == "__main__":
    main()
