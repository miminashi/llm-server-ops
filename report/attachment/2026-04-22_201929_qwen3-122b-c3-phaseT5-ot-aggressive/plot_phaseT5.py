#!/usr/bin/env python3
"""plot_phaseT5.py - Phase T-5 OT 層削減 (B32a/B30/B28/B28c/B32z) のグラフ生成"""
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
PEAK_PHASE_T3_BEST = 14.860
PEAK_PHASE_T4_BEST = 15.494

# trend 折れ線の x 軸: CPU 層数 {32, 30, 28} (threads=40 のみ)
# drift 両端 (B32a / B32z) は別点で可視化
TREND_LABELS = ["B32a", "B30", "B28"]
TREND_CPU = {"B32a": 32, "B30": 30, "B28": 28}


def load_stats():
    # label -> (metric -> {mean, stdev, threads, cpu_layers})
    out = {}
    with (SCRIPT_DIR / "phaseT5_stats.csv").open() as f:
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
                "threads": int(row["threads"]),
                "cpu_layers": int(row["cpu_layers"]),
            }
    return out


def plot_trend(data, ax, metric: str, title: str, ylabel: str):
    """CPU 層数 (x) vs metric (y) の折れ線 + B32z drift 終点、B28c 不一致 control"""
    # trend 折れ線 (threads=40)
    xs = [TREND_CPU[lbl] for lbl in TREND_LABELS]
    means, stdevs = [], []
    for lbl in TREND_LABELS:
        v = data.get(lbl, {}).get(metric)
        if v:
            means.append(v["mean"])
            stdevs.append(v["stdev"])
        else:
            means.append(np.nan)
            stdevs.append(0)
    ax.errorbar(xs, means, yerr=stdevs, fmt="o-", color="#C44E52", lw=2, markersize=10,
                capsize=4, label="threads=40 (trend)")
    for x, lbl, m in zip(xs, TREND_LABELS, means):
        if not np.isnan(m):
            ax.annotate(f"{lbl}\n{m:.3f}", (x, m),
                        textcoords="offset points", xytext=(8, -4),
                        fontsize=9)

    # B32z drift end (CPU layers=32)
    b32z = data.get("B32z", {}).get(metric)
    if b32z:
        ax.errorbar([32], [b32z["mean"]], yerr=[b32z["stdev"]], fmt="D",
                    color="#808080", markersize=12, capsize=4,
                    label=f"B32z (drift end) {b32z['mean']:.3f}")

    # B28c threads=32 control (CPU layers=28)
    b28c = data.get("B28c", {}).get(metric)
    if b28c:
        ax.errorbar([28], [b28c["mean"]], yerr=[b28c["stdev"]], fmt="^",
                    color="#4C72B0", markersize=12, capsize=4,
                    label=f"B28c (t32) {b28c['mean']:.3f}")

    # 過去 Phase 基準線 (eval_tps のみ)
    if metric == "eval_tps":
        for y, lbl, color in [
            (PEAK_PHASE_T4_BEST, f"Phase T-4 best ({PEAK_PHASE_T4_BEST})", "#8B0000"),
            (PEAK_PHASE_S, f"Phase S peak ({PEAK_PHASE_S})", "#DD8452"),
            (PEAK_PHASE_D, f"Phase D peak ({PEAK_PHASE_D})", "#8172B2"),
        ]:
            ax.axhline(y=y, color=color, ls="--", alpha=0.6, lw=1)
            ax.annotate(lbl, (28, y), textcoords="offset points",
                        xytext=(-5, 5), fontsize=8, color=color,
                        ha="left", va="bottom")

    ax.set_xlabel("CPU offload layer count")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_xticks([28, 30, 32])
    ax.grid(True, alpha=0.3)
    ax.invert_xaxis()   # fewer CPU layers (right) = more GPU layers = higher perf
    ax.legend(loc="best", fontsize=8)


def plot_drift(data, ax, metric: str, title: str, ylabel: str):
    """B32a と B32z を時系列順 (実行順) で表示して drift を可視化"""
    labels = ["B32a\n(start)", "B30", "B28", "B28c (t32)", "B32z\n(end)"]
    order = ["B32a", "B30", "B28", "B28c", "B32z"]
    means = []
    stdevs = []
    colors = []
    for lbl in order:
        v = data.get(lbl, {}).get(metric)
        if v:
            means.append(v["mean"])
            stdevs.append(v["stdev"])
            if lbl.startswith("B32"):
                colors.append("#4C72B0")
            elif lbl == "B28c":
                colors.append("#55A868")
            else:
                colors.append("#C44E52")
        else:
            means.append(np.nan)
            stdevs.append(0)
            colors.append("#999999")
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
        ax.axhline(y=PEAK_PHASE_T4_BEST, color="#8B0000", ls="--", alpha=0.6,
                   label=f"T-4 best ({PEAK_PHASE_T4_BEST})")
        ax.axhline(y=PEAK_PHASE_S, color="#DD8452", ls="--", alpha=0.5,
                   label=f"Phase S ({PEAK_PHASE_S})")
        ax.legend(loc="lower right", fontsize=8)


def main():
    data = load_stats()
    print(f"[plot] loaded: {list(data.keys())}")

    # 1. eval/prompt trend 図
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Phase T-5: OT layer reduction (B28 VRAM boundary) — qwen3-122b q8_0 layer ub=1586 ctx=32k",
                 fontsize=12)
    plot_trend(data, ax1, "eval_tps",
               "eval_tps vs CPU layer count (threads=40)",
               "eval_tps (t/s, 5-run mean ± stdev)")
    plot_trend(data, ax2, "prompt_tps",
               "prompt_tps vs CPU layer count (threads=40)",
               "prompt_tps (t/s)")
    fig.tight_layout()
    out1 = SCRIPT_DIR / "phaseT5_eval_tps.png"
    fig.savefig(out1, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out1}")
    plt.close(fig)

    # 2. session drift 棒グラフ (実行順)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Phase T-5: execution order (session drift visualization)",
                 fontsize=12)
    plot_drift(data, ax1, "eval_tps",
               "eval_tps by run order",
               "eval_tps (t/s)")
    plot_drift(data, ax2, "prompt_tps",
               "prompt_tps by run order",
               "prompt_tps (t/s)")
    fig.tight_layout()
    out2 = SCRIPT_DIR / "phaseT5_drift.png"
    fig.savefig(out2, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out2}")
    plt.close(fig)


if __name__ == "__main__":
    main()
