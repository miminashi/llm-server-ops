#!/usr/bin/env python3
"""plot_phaseT5e.py - Phase T-5e: B28 × (ctx, ub) 適用のグラフ生成"""
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
PEAK_PHASE_T4_BEST = 15.494
PEAK_PHASE_T5_BEST = 16.024

# 2x2 factorial grid
# rows: ctx={32k, 65k}, cols: ub={512, 1586}
GRID_LABELS = {
    (32768, 1586): ["B28_32k_1586a", "B28_32k_1586z"],  # 同条件 2 回 (drift 起点・終点)
    (65536,  512): ["B28_65k_ub512"],
    (65536, 1586): ["B28_65k_ub1586"],
    (32768,  512): ["B28_32k_ub512"],
}


def load_stats():
    out = {}
    with (SCRIPT_DIR / "phaseT5e_stats.csv").open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["phase"] != "eval":
                continue
            if not row["n"] or int(row["n"]) == 0:
                continue
            lbl = row["label"]
            out.setdefault(lbl, {})[row["metric"]] = {
                "mean": float(row["mean"]),
                "stdev": float(row["stdev"]),
                "ctx": int(row["ctx"]),
                "ub": int(row["ub"]),
            }
    return out


def plot_bars(data, ax, metric: str, title: str, ylabel: str):
    """5 条件を実行順に棒グラフ表示"""
    order = ["B28_32k_1586a", "B28_65k_ub512", "B28_65k_ub1586", "B28_32k_ub512", "B28_32k_1586z"]
    labels = [
        "B28_32k_1586a\n(drift start)",
        "B28_65k_ub512\n(*target)",
        "B28_65k_ub1586\n(ctx only)",
        "B28_32k_ub512\n(ub only)",
        "B28_32k_1586z\n(drift end)",
    ]
    colors_map = {
        "B28_32k_1586a": "#4C72B0",
        "B28_65k_ub512": "#C44E52",
        "B28_65k_ub1586": "#55A868",
        "B28_32k_ub512": "#8172B2",
        "B28_32k_1586z": "#4C72B0",
    }
    means, stdevs, colors = [], [], []
    for lbl in order:
        v = data.get(lbl, {}).get(metric)
        if v:
            means.append(v["mean"])
            stdevs.append(v["stdev"])
        else:
            means.append(np.nan)
            stdevs.append(0)
        colors.append(colors_map.get(lbl, "#999999"))
    xs = np.arange(len(order))
    ax.bar(xs, means, yerr=stdevs, color=colors, capsize=4, alpha=0.85)
    for x, m, s in zip(xs, means, stdevs):
        if not np.isnan(m):
            ax.annotate(f"{m:.3f}", (x, m + s + 0.01),
                        ha="center", fontsize=9)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3, axis="y")
    if metric == "eval_tps":
        ax.axhline(y=PEAK_PHASE_T5_BEST, color="#8B0000", ls="--", alpha=0.7,
                   label=f"T-5 best ({PEAK_PHASE_T5_BEST})")
        ax.axhline(y=PEAK_PHASE_T4_BEST, color="#DD8452", ls="--", alpha=0.6,
                   label=f"T-4 best ({PEAK_PHASE_T4_BEST})")
        ax.axhline(y=PEAK_PHASE_S, color="#8172B2", ls="--", alpha=0.5,
                   label=f"Phase S ({PEAK_PHASE_S})")
        ax.axhline(y=PEAK_PHASE_D, color="#4C72B0", ls="--", alpha=0.4,
                   label=f"Phase D ({PEAK_PHASE_D})")
        ax.legend(loc="lower right", fontsize=8)


def plot_factorial(data, ax, metric: str, title: str, ylabel: str):
    """2x2 factorial interaction plot: ctx × ub"""
    ctxs = [32768, 65536]
    ubs = [512, 1586]
    # drift 起点 (1586a) を (32k, 1586) の代表とする
    repr_map = {
        (32768, 1586): "B28_32k_1586a",
        (32768,  512): "B28_32k_ub512",
        (65536, 1586): "B28_65k_ub1586",
        (65536,  512): "B28_65k_ub512",
    }
    for ub, color, marker in [(1586, "#4C72B0", "o"), (512, "#C44E52", "s")]:
        ys = []
        es = []
        for ctx in ctxs:
            lbl = repr_map.get((ctx, ub))
            v = data.get(lbl, {}).get(metric) if lbl else None
            if v:
                ys.append(v["mean"])
                es.append(v["stdev"])
            else:
                ys.append(np.nan)
                es.append(0)
        ax.errorbar(ctxs, ys, yerr=es, fmt=f"{marker}-", color=color, lw=2,
                    markersize=10, capsize=4, label=f"ub={ub}")
        for x, y in zip(ctxs, ys):
            if not np.isnan(y):
                ax.annotate(f"{y:.3f}", (x, y), textcoords="offset points",
                            xytext=(8, 5), fontsize=8, color=color)
    ax.set_xlabel("ctx")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_xticks(ctxs)
    ax.set_xticklabels([f"{c//1024}k" for c in ctxs])
    ax.grid(True, alpha=0.3)
    if metric == "eval_tps":
        ax.axhline(y=PEAK_PHASE_T5_BEST, color="#8B0000", ls="--", alpha=0.7,
                   label=f"T-5 best ({PEAK_PHASE_T5_BEST})")
    ax.legend(loc="best", fontsize=8)


def main():
    data = load_stats()
    print(f"[plot] loaded: {list(data.keys())}")

    # 1. 棒グラフ (5 条件実行順)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle("Phase T-5e: B28 × (ctx, ub) apply — qwen3-122b CPU 28 layers, threads=40, q8_0, split=layer",
                 fontsize=12)
    plot_bars(data, ax1, "eval_tps",
              "eval_tps (5-run mean ± stdev) — execution order",
              "eval_tps (t/s)")
    plot_bars(data, ax2, "prompt_tps",
              "prompt_tps (5-run mean ± stdev)",
              "prompt_tps (t/s)")
    fig.tight_layout()
    out1 = SCRIPT_DIR / "phaseT5e_eval_tps.png"
    fig.savefig(out1, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out1}")
    plt.close(fig)

    # 2. Factorial interaction plot (2x2)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Phase T-5e: 2x2 factorial (ctx × ub) interaction plot",
                 fontsize=12)
    plot_factorial(data, ax1, "eval_tps",
                   "eval_tps: ctx × ub interaction",
                   "eval_tps (t/s)")
    plot_factorial(data, ax2, "prompt_tps",
                   "prompt_tps: ctx × ub interaction",
                   "prompt_tps (t/s)")
    fig.tight_layout()
    out2 = SCRIPT_DIR / "phaseT5e_factorial.png"
    fig.savefig(out2, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out2}")
    plt.close(fig)


if __name__ == "__main__":
    main()
