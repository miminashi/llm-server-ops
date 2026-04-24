#!/usr/bin/env python3
"""plot_phaseT4.py - Phase T-4 OT pattern × threads スイープのグラフ生成"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent

PEAK_PHASE_D = 15.03
PEAK_PHASE_S = 15.39
PEAK_PHASE_T1_Q8 = 15.016
PEAK_PHASE_T2_BEST = 14.672
PEAK_PHASE_T3_BEST = 14.860
PEAK_PHASE_T3_T40 = 14.781

OT_TAGS = ["B32", "A36", "C40"]
OT_LAYER_COUNT = {"A36": 36, "B32": 32, "C40": 40}


def load_stats():
    # (ot_tag, threads, metric) -> {mean, stdev}
    out = {}
    with (SCRIPT_DIR / "phaseT4_stats.csv").open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["phase"] == "eval" and row["n"] and int(row["n"]) > 0:
                out[(row["ot_tag"], int(row["threads"]), row["metric"])] = {
                    "mean": float(row["mean"]),
                    "stdev": float(row["stdev"]),
                }
    return out


def plot_lines(data, ax, metric: str, title: str, ylabel: str):
    """OT (CPU 層数) を x 軸、threads={32,40} を 2 本の折れ線で重ね描き"""
    xs = [OT_LAYER_COUNT[ot] for ot in OT_TAGS]
    for thr, color, marker in [(32, "#4C72B0", "o"), (40, "#C44E52", "s")]:
        means = []
        stdevs = []
        for ot in OT_TAGS:
            v = data.get((ot, thr, metric))
            if v:
                means.append(v["mean"])
                stdevs.append(v["stdev"])
            else:
                means.append(None)
                stdevs.append(0)
        # None を除外して描画 (no_data 対応)
        valid = [(x, m, s) for x, m, s in zip(xs, means, stdevs) if m is not None]
        if not valid:
            continue
        vx, vm, vs = zip(*valid)
        ax.errorbar(vx, vm, yerr=vs, marker=marker, markersize=9, linewidth=2,
                    color=color, capsize=5, label=f"threads={thr}")
        for x, m in zip(vx, vm):
            ax.text(x, m + 0.05, f"{m:.3f}", ha="center", va="bottom", fontsize=8.5)

    if metric == "eval_tps":
        ax.axhline(PEAK_PHASE_S, color="#C44E52", linestyle="--", linewidth=1, alpha=0.7,
                   label=f"Phase S {PEAK_PHASE_S}")
        ax.axhline(PEAK_PHASE_D, color="#8172B3", linestyle="--", linewidth=1, alpha=0.7,
                   label=f"Phase D {PEAK_PHASE_D}")
        ax.axhline(PEAK_PHASE_T1_Q8, color="#55A868", linestyle=":", linewidth=1, alpha=0.8,
                   label=f"Phase T-1 q8_0 {PEAK_PHASE_T1_Q8}")
        ax.axhline(PEAK_PHASE_T3_BEST, color="#DD8452", linestyle="-.", linewidth=1.2, alpha=0.85,
                   label=f"Phase T-3 best {PEAK_PHASE_T3_BEST}")
        ax.axhline(PEAK_PHASE_T2_BEST, color="#937860", linestyle=":", linewidth=1, alpha=0.6,
                   label=f"Phase T-2 best {PEAK_PHASE_T2_BEST}")

    ax.set_xlabel("CPU offload layer count (OT pattern)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{c}\n({ot})" for c, ot in zip(xs, OT_TAGS)])
    ax.legend(loc="best", fontsize=7.5)
    ax.grid(axis="y", linestyle=":", alpha=0.4)


def plot_heatmap(data, ax):
    """OT × threads heatmap (eval_tps)"""
    matrix = np.full((len(OT_TAGS), 2), np.nan)
    for i, ot in enumerate(OT_TAGS):
        for j, thr in enumerate([32, 40]):
            v = data.get((ot, thr, "eval_tps"))
            if v:
                matrix[i, j] = v["mean"]
    im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn", vmin=14.0, vmax=15.5)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["threads=32", "threads=40"])
    ax.set_yticks(range(len(OT_TAGS)))
    ax.set_yticklabels([f"{ot} ({OT_LAYER_COUNT[ot]} layers)" for ot in OT_TAGS])
    for i in range(len(OT_TAGS)):
        for j in range(2):
            v = matrix[i, j]
            txt = f"{v:.3f}" if not np.isnan(v) else "no_data"
            color = "white" if (not np.isnan(v) and v < 14.4) else "black"
            ax.text(j, i, txt, ha="center", va="center", fontsize=10, color=color)
    ax.set_title("eval_tps heatmap (OT × threads)")
    plt.colorbar(im, ax=ax, label="eval_tps (t/s)")


def main():
    data = load_stats()

    # Figure 1: 折れ線 2 パネル (eval / prompt)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))
    plot_lines(data, ax1, "eval_tps",
               "eval_tps vs CPU layer count",
               "eval_tps (t/s, 5-run mean ± stdev)")
    plot_lines(data, ax2, "prompt_tps",
               "prompt_tps vs CPU layer count",
               "prompt_tps (t/s)")
    fig.suptitle(
        "Phase T-4: OT pattern × threads sweep (qwen3-122b q8_0 layer ub=1586 ctx=32k)",
        fontsize=12,
    )
    fig.tight_layout()
    out = SCRIPT_DIR / "phaseT4_eval_tps.png"
    fig.savefig(out, dpi=120)
    print(f"[plot] wrote {out}")

    # Figure 2: heatmap
    fig2, ax = plt.subplots(1, 1, figsize=(7, 4))
    plot_heatmap(data, ax)
    fig2.tight_layout()
    out2 = SCRIPT_DIR / "phaseT4_heatmap.png"
    fig2.savefig(out2, dpi=120)
    print(f"[plot] wrote {out2}")


if __name__ == "__main__":
    main()
