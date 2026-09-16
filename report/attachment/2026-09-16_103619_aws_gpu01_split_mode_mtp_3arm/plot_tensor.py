#!/usr/bin/env python3
"""Isolate the two changes made to the tensor arm: the AllReduce backend and MTP.

The 2026-09-14 tensor baseline ran on the default NCCL AllReduce; the MTP-on tensor
arm had to use GGML_CUDA_ALLREDUCE=none to get past the start-up hang.  Comparing
those two directly confounds "MTP" with "no CUDA-side AllReduce", so this figure adds
the missing cell -- tensor / MTP off / none -- and shows the three series side by side.
"""
import argparse, json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

INK, MUTED, GRID, SURF = "#1a1a1a", "#5a5a5a", "#d8d8d4", "#fcfcfb"
SER = [  # key, colour, marker, linestyle
    ("nccl_off",  "#d62728", "s", (0, (6, 3))),
    ("none_off",  "#8c6d31", "^", (0, (2, 2))),
    ("none_on",   "#1f77b4", "o", "-"),
]
LAB_JA = {"nccl_off": "NCCL・MTP 無効（既定・2026-09-14）",
          "none_off": "none・MTP 無効（回避策のコスト測定）",
          "none_on":  "none・MTP 有効（本計測）"}
LAB_EN = {"nccl_off": "NCCL, MTP off (default, 2026-09-14)",
          "none_off": "none, MTP off (cost of the workaround)",
          "none_on":  "none, MTP on (this run)"}


def lad(d):
    return json.load(open(os.path.join(d, "results-tensor.json")))


def pp0(d):
    return json.load(open(os.path.join(d, "results-tensor-pp0.json")))


def main():
    ap = argparse.ArgumentParser()
    for k in ("nccl-off", "none-off", "none-on"):
        ap.add_argument("--" + k, required=True)
    ap.add_argument("--lang", default="ja", choices=["ja", "en"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ja = a.lang == "ja"
    L = LAB_JA if ja else LAB_EN
    plt.rcParams["font.family"] = ["Noto Sans CJK JP"] if ja else ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    dirs = {"nccl_off": a.nccl_off, "none_off": a.none_off, "none_on": a.none_on}
    rows = {k: lad(v) for k, v in dirs.items()}
    p0 = {k: pp0(v) for k, v in dirs.items()}

    x = list(range(len(rows["none_on"])))
    xlab = [f"{r['effective_depth']:,}" for r in rows["none_on"]]

    fig, axes = plt.subplots(1, 3, figsize=(16.5, 5.4), facecolor=SURF)
    for ax in axes:
        ax.set_facecolor(SURF)
        ax.grid(True, color=GRID, lw=0.8, zorder=0)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(GRID)
        ax.tick_params(colors=MUTED, labelsize=9.5)

    # (1) decode
    ax = axes[0]
    for k, c, mk, ls in SER:
        y = [r["predicted_per_second"] for r in rows[k]]
        ax.plot(x, y, color=c, lw=2.0, ls=ls, marker=mk, ms=6.5,
                markeredgecolor=SURF, markeredgewidth=1.3, zorder=3, label=L[k])
        ax.annotate(f"{y[-1]:.1f}", (x[-1], y[-1]), textcoords="offset points",
                    xytext=(7, 0), color=c, fontsize=9.5, fontweight="bold", va="center")
    ax.set_xticks(x); ax.set_xticklabels(xlab, rotation=20)
    ax.set_title("① decode (t/s)" if ja else "(1) decode (t/s)", loc="left",
                 color=INK, fontsize=12.5, fontweight="bold", pad=9)
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=8.6, frameon=False, labelcolor=MUTED, loc="lower left")

    # (2) incremental prefill
    ax = axes[1]
    for k, c, mk, ls in SER:
        y = [r["prompt_per_second"] for r in rows[k]][1:]
        ax.plot(x[:len(y)], y, color=c, lw=2.0, ls=ls, marker=mk, ms=6.5,
                markeredgecolor=SURF, markeredgewidth=1.3, zorder=3, label=L[k])
        ax.annotate(f"{y[-1]:.0f}", (x[len(y) - 1], y[-1]), textcoords="offset points",
                    xytext=(7, 0), color=c, fontsize=9.5, fontweight="bold", va="center")
    ax.set_xticks(x[:len(xlab) - 1]); ax.set_xticklabels(xlab[1:], rotation=20)
    ax.set_title("② prefill (増分, t/s)" if ja else "(2) prefill (incremental, t/s)",
                 loc="left", color=INK, fontsize=12.5, fontweight="bold", pad=9)
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=8.6, frameon=False, labelcolor=MUTED, loc="upper right")

    # (3) depth-0 prefill
    ax = axes[2]
    sizes = [k for k in p0["none_on"] if k.startswith("pp")]
    w = 0.78 / len(SER)
    for i, (k, c, mk, ls) in enumerate(SER):
        y = [p0[k][s]["prompt_per_second"] for s in sizes]
        pos = [j - 0.39 + w * (i + 0.5) for j in range(len(sizes))]
        ax.bar(pos, y, width=w * 0.86, color=c, zorder=3, label=L[k])
        for px, v in zip(pos, y):
            ax.annotate(f"{v:.0f}", (px, v), textcoords="offset points", xytext=(0, 3),
                        ha="center", color=MUTED, fontsize=8.4)
    ax.set_xticks(range(len(sizes))); ax.set_xticklabels(sizes)
    lo, hi = ax.get_ylim(); ax.set_ylim(lo, hi * 1.22)
    ax.set_title("③ depth-0 prefill (新規プロンプト, t/s)" if ja else
                 "(3) depth-0 prefill (fresh prompt, t/s)",
                 loc="left", color=INK, fontsize=12.5, fontweight="bold", pad=9)
    ax.legend(fontsize=8.6, frameon=False, labelcolor=MUTED, loc="upper left")

    for ax in axes[:2]:
        ax.set_xlabel("実効深さ (tok)" if ja else "effective depth (tok)", color=MUTED, fontsize=10)
        ax.set_ylabel("t/s", color=MUTED, fontsize=10)

    sup = ("aws-gpu01 — Tesla P100 ×7 / Qwen3.8-27B UD-Q4_K_XL / ctx=131,072 / --split-mode tensor\n"
           "回避策 (GGML_CUDA_ALLREDUCE=none) と MTP の効果を分離する 3 系列"
           if ja else
           "aws-gpu01 - Tesla P100 x7 / Qwen3.8-27B UD-Q4_K_XL / ctx=131,072 / --split-mode tensor\n"
           "separating the workaround (GGML_CUDA_ALLREDUCE=none) from MTP")
    fig.suptitle(sup, x=0.005, ha="left", color=INK, fontsize=11.5)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(a.out, dpi=130, facecolor=SURF)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
