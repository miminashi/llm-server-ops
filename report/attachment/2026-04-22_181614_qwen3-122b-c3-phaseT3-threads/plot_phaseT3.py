#!/usr/bin/env python3
"""plot_phaseT3.py - Phase T-3 threads スイープの eval_tps 折れ線 + prompt 軸を生成"""
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
PEAK_PHASE_T2_BEST = 14.672


def load_stats():
    # (threads, metric, phase=eval) -> {mean, stdev}
    out = {}
    with (SCRIPT_DIR / "phaseT3_stats.csv").open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["phase"] == "eval" and row["n"]:
                out[(int(row["threads"]), row["metric"])] = {
                    "mean": float(row["mean"]),
                    "stdev": float(row["stdev"]),
                }
    return out


def main():
    data = load_stats()

    threads_list = sorted({k[0] for k in data.keys()})
    eval_means = [data[(t, "eval_tps")]["mean"] for t in threads_list]
    eval_stdevs = [data[(t, "eval_tps")]["stdev"] for t in threads_list]
    prompt_means = [data[(t, "prompt_tps")]["mean"] for t in threads_list]
    prompt_stdevs = [data[(t, "prompt_tps")]["stdev"] for t in threads_list]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5.5))

    # eval_tps 折れ線
    ax1.errorbar(threads_list, eval_means, yerr=eval_stdevs, marker="o",
                 markersize=8, linewidth=2, color="#4C72B0", capsize=5,
                 label="eval_tps (q8_0, split=layer, ub=1586)")
    for t, m in zip(threads_list, eval_means):
        ax1.text(t, m + 0.05, f"{m:.3f}", ha="center", va="bottom", fontsize=9)

    ax1.axhline(PEAK_PHASE_S, color="#C44E52", linestyle="--", linewidth=1, alpha=0.8,
                label=f"Phase S peak {PEAK_PHASE_S}")
    ax1.axhline(PEAK_PHASE_D, color="#8172B3", linestyle="--", linewidth=1, alpha=0.8,
                label=f"Phase D peak {PEAK_PHASE_D}")
    ax1.axhline(PEAK_PHASE_T1_Q8, color="#55A868", linestyle=":", linewidth=1, alpha=0.9,
                label=f"Phase T-1 q8_0 {PEAK_PHASE_T1_Q8}")
    ax1.axhline(PEAK_PHASE_T2_BEST, color="#DD8452", linestyle=":", linewidth=1, alpha=0.9,
                label=f"Phase T-2 best {PEAK_PHASE_T2_BEST}")

    ax1.set_xlabel("threads")
    ax1.set_ylabel("eval_tps (t/s, 5-run mean ± stdev)")
    ax1.set_title("eval_tps vs threads")
    ax1.set_xticks(threads_list)
    lo = min(eval_means + [PEAK_PHASE_T2_BEST]) - 0.3
    hi = max(eval_means + [PEAK_PHASE_S]) + 0.3
    ax1.set_ylim(lo, hi)
    ax1.legend(loc="lower right", fontsize=8)
    ax1.grid(axis="y", linestyle=":", alpha=0.4)

    # prompt_tps 折れ線
    ax2.errorbar(threads_list, prompt_means, yerr=prompt_stdevs, marker="s",
                 markersize=8, linewidth=2, color="#55A868", capsize=5,
                 label="prompt_tps")
    for t, m in zip(threads_list, prompt_means):
        ax2.text(t, m + 0.1, f"{m:.2f}", ha="center", va="bottom", fontsize=9)

    ax2.set_xlabel("threads")
    ax2.set_ylabel("prompt_tps (t/s)")
    ax2.set_title("prompt_tps vs threads")
    ax2.set_xticks(threads_list)
    ax2.legend(loc="lower right", fontsize=9)
    ax2.grid(axis="y", linestyle=":", alpha=0.4)

    fig.suptitle("Phase T-3: threads sweep (qwen3-122b q8_0, split=layer, ub=1586, ctx=32k)",
                 fontsize=12)
    fig.tight_layout()

    out = SCRIPT_DIR / "phaseT3_eval_tps.png"
    fig.savefig(out, dpi=120)
    print(f"[plot] wrote {out}")


if __name__ == "__main__":
    main()
