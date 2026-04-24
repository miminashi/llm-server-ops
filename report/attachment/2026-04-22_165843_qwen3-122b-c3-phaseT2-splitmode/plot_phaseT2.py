#!/usr/bin/env python3
"""plot_phaseT2.py - Phase T-2 の eval_tps bar chart を生成"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SCRIPT_DIR = Path(__file__).resolve().parent

PEAK_PHASE_D = 15.03
PEAK_PHASE_S = 15.39
PEAK_PHASE_T1_Q8 = 15.016


def load_stats():
    # 各 (kv, split_mode) eval_tps eval phase の mean を取得
    out = {}
    with (SCRIPT_DIR / "phaseT2_stats.csv").open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["metric"] == "eval_tps" and row["phase"] == "eval" and row["n"]:
                out[(row["kv"], row["split_mode"])] = {
                    "mean": float(row["mean"]),
                    "stdev": float(row["stdev"]),
                }
    return out


def main():
    data = load_stats()

    kvs = ["f16", "q8_0"]
    sms = ["layer", "row"]
    x = list(range(len(kvs)))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5.5))

    layer_means = [data[(kv, "layer")]["mean"] for kv in kvs]
    layer_stdevs = [data[(kv, "layer")]["stdev"] for kv in kvs]
    row_means = [data[(kv, "row")]["mean"] for kv in kvs]
    row_stdevs = [data[(kv, "row")]["stdev"] for kv in kvs]

    b1 = ax.bar([i - width / 2 for i in x], layer_means, width, yerr=layer_stdevs,
                label="split-mode=layer", color="#4C72B0", capsize=4)
    b2 = ax.bar([i + width / 2 for i in x], row_means, width, yerr=row_stdevs,
                label="split-mode=row", color="#DD8452", capsize=4)

    # 値ラベル
    for bars, means in ((b1, layer_means), (b2, row_means)):
        for bar, m in zip(bars, means):
            ax.text(bar.get_x() + bar.get_width() / 2, m + 0.15, f"{m:.3f}",
                    ha="center", va="bottom", fontsize=9)

    # 基準線
    ax.axhline(PEAK_PHASE_S, color="#C44E52", linestyle="--", linewidth=1, alpha=0.8,
               label=f"Phase S peak {PEAK_PHASE_S}")
    ax.axhline(PEAK_PHASE_D, color="#8172B3", linestyle="--", linewidth=1, alpha=0.8,
               label=f"Phase D peak {PEAK_PHASE_D}")
    ax.axhline(PEAK_PHASE_T1_Q8, color="#55A868", linestyle=":", linewidth=1, alpha=0.9,
               label=f"Phase T-1 q8_0 {PEAK_PHASE_T1_Q8}")

    ax.set_xticks(x)
    ax.set_xticklabels([f"KV={kv}" for kv in kvs])
    ax.set_ylabel("eval_tps (t/s, 5-run mean ± stdev)")
    ax.set_title("Phase T-2: split-mode row vs layer (qwen3-122b, ub=1586, ctx=32k)")
    ax.set_ylim(0, max(layer_means + row_means) + 2)
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    fig.tight_layout()

    out = SCRIPT_DIR / "phaseT2_eval_tps.png"
    fig.savefig(out, dpi=120)
    print(f"[plot] wrote {out}")


if __name__ == "__main__":
    main()
