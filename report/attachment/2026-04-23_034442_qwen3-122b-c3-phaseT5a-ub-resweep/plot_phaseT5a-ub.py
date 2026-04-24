#!/usr/bin/env python3
"""plot_phaseT5a-ub.py - Phase T-5a-ub: B18 × ctx=32k × ub 再スイープ グラフ生成

3 枚の PNG を出力:
  1. phaseT5aub_ub_trend.png: ub (log scale) vs eval_mean + prompt_mean dual y-axis line
  2. phaseT5aub_pareto.png:   x=prompt_mean, y=eval_mean scatter (ub ラベル付き)
  3. phaseT5aub_drift.png:    run_index=1..6 vs eval_mean、起点・終点強調
"""
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
PEAK_PHASE_T5E_BEST = 16.380
PEAK_PHASE_T5F_BEST = 16.455
PEAK_PHASE_T5A_BEST = 18.006  # T-5a B18_run1 (直前歴代最高)

# run_index 順 (batch で実行する順)
RUN_ORDER = [
    ("B18_ub512a", 512, "drift start"),
    ("B18_ub768",  768, ""),
    ("B18_ub384",  384, ""),
    ("B18_ub256",  256, ""),
    ("B18_ub128",  128, ""),
    ("B18_ub512z", 512, "drift end"),
]


def load_stats():
    out = {}
    with (SCRIPT_DIR / "phaseT5a-ub_stats.csv").open() as f:
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
                "run_index": int(row["run_index"]),
            }
    return out


def plot_ub_trend(data):
    """ub (log) vs eval_mean + prompt_mean dual-axis line (ub ユニーク値のみ、ub=512 は drift 起点採用)"""
    # ub ユニーク化: ub=512 は起点 (B28_32k_ub512a) のみ使用
    ub_data = {}  # ub -> (eval_mean, eval_stdev, prompt_mean, prompt_stdev)
    for lbl, ub, _ in RUN_ORDER:
        if lbl == "B18_ub512z":
            continue  # 終点は drift 用、trend からは除外
        e = data.get(lbl, {}).get("eval_tps")
        p = data.get(lbl, {}).get("prompt_tps")
        if e and p:
            ub_data[ub] = (e["mean"], e["stdev"], p["mean"], p["stdev"])
    ubs = sorted(ub_data.keys())
    e_means = [ub_data[u][0] for u in ubs]
    e_stds = [ub_data[u][1] for u in ubs]
    p_means = [ub_data[u][2] for u in ubs]
    p_stds = [ub_data[u][3] for u in ubs]

    fig, ax1 = plt.subplots(figsize=(11, 6))
    ax1.set_xscale("log", base=2)
    ax1.errorbar(ubs, e_means, yerr=e_stds, fmt="o-", color="#C44E52",
                 markersize=9, lw=2.2, capsize=4, label="eval_tps")
    ax1.set_xlabel("ub (-b = -ub, log2 scale)")
    ax1.set_ylabel("eval_tps (t/s)", color="#C44E52")
    ax1.tick_params(axis="y", labelcolor="#C44E52")
    ax1.set_xticks(ubs)
    ax1.set_xticklabels([str(u) for u in ubs])
    for u, m in zip(ubs, e_means):
        ax1.annotate(f"{m:.3f}", (u, m), textcoords="offset points",
                     xytext=(6, 8), fontsize=8, color="#C44E52")
    ax1.axhline(y=PEAK_PHASE_T5A_BEST, color="#006400", ls="--", alpha=0.9, lw=2.0,
                label=f"T-5a B18 baseline ({PEAK_PHASE_T5A_BEST})")
    ax1.axhline(y=PEAK_PHASE_T5F_BEST, color="#8B0000", ls="--", alpha=0.7,
                label=f"T-5f ({PEAK_PHASE_T5F_BEST})")
    ax1.axhline(y=PEAK_PHASE_T5E_BEST, color="#A52A2A", ls="--", alpha=0.55,
                label=f"T-5e ({PEAK_PHASE_T5E_BEST})")
    ax1.axhline(y=PEAK_PHASE_T5_BEST, color="#DD8452", ls="--", alpha=0.5,
                label=f"T-5 ({PEAK_PHASE_T5_BEST})")
    ax1.axhline(y=PEAK_PHASE_D, color="#4C72B0", ls="--", alpha=0.4,
                label=f"D ({PEAK_PHASE_D})")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="lower left", fontsize=8)

    ax2 = ax1.twinx()
    ax2.errorbar(ubs, p_means, yerr=p_stds, fmt="s--", color="#4C72B0",
                 markersize=7, lw=1.5, capsize=4, label="prompt_tps", alpha=0.85)
    ax2.set_ylabel("prompt_tps (t/s)", color="#4C72B0")
    ax2.tick_params(axis="y", labelcolor="#4C72B0")
    for u, m in zip(ubs, p_means):
        ax2.annotate(f"{m:.1f}", (u, m), textcoords="offset points",
                     xytext=(6, -14), fontsize=7, color="#4C72B0")
    ax2.legend(loc="lower right", fontsize=8)

    fig.suptitle("Phase T-5a-ub: B18 × ctx=32k × ub trend (eval + prompt dual-axis)",
                 fontsize=12)
    fig.tight_layout()
    out = SCRIPT_DIR / "phaseT5aub_ub_trend.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out}")
    plt.close(fig)


def plot_pareto(data):
    """prompt_mean vs eval_mean scatter (ub ラベル)"""
    xs, ys, ubs, lbls = [], [], [], []
    for lbl, ub, _ in RUN_ORDER:
        if lbl == "B18_ub512z":
            continue
        e = data.get(lbl, {}).get("eval_tps")
        p = data.get(lbl, {}).get("prompt_tps")
        if e and p:
            xs.append(p["mean"])
            ys.append(e["mean"])
            ubs.append(ub)
            lbls.append(lbl)

    fig, ax = plt.subplots(figsize=(10, 7))
    sc = ax.scatter(xs, ys, c=np.log2(ubs), cmap="viridis", s=130, alpha=0.85,
                    edgecolor="black", linewidth=1)
    for x, y, u in zip(xs, ys, ubs):
        ax.annotate(f"ub={u}", (x, y), textcoords="offset points",
                    xytext=(8, 6), fontsize=9)

    # Pareto frontier (上方凸包 = eval 高 ∧ prompt 高)
    pts = sorted(zip(xs, ys, ubs))
    pareto = []
    max_y = -1
    for x, y, u in sorted(zip(xs, ys, ubs), key=lambda t: -t[0]):  # prompt 降順
        if y > max_y:
            pareto.append((x, y, u))
            max_y = y
    if len(pareto) >= 2:
        px, py, _ = zip(*sorted(pareto))
        ax.plot(px, py, "r--", alpha=0.4, lw=1.5, label="Pareto frontier")

    ax.axhline(y=PEAK_PHASE_T5A_BEST, color="#006400", ls=":", alpha=0.85, lw=2.0,
               label=f"T-5a B18 baseline ({PEAK_PHASE_T5A_BEST})")
    ax.axhline(y=PEAK_PHASE_T5F_BEST, color="#8B0000", ls=":", alpha=0.6,
               label=f"T-5f ({PEAK_PHASE_T5F_BEST})")
    ax.axhline(y=PEAK_PHASE_T5_BEST, color="#DD8452", ls=":", alpha=0.5,
               label=f"T-5 ({PEAK_PHASE_T5_BEST})")
    ax.set_xlabel("prompt_tps (t/s)")
    ax.set_ylabel("eval_tps (t/s)")
    ax.set_title("Phase T-5a-ub: B18 × eval / prompt Pareto (color = log2(ub))")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    plt.colorbar(sc, ax=ax, label="log2(ub)")

    fig.tight_layout()
    out = SCRIPT_DIR / "phaseT5aub_pareto.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out}")
    plt.close(fig)


def plot_drift(data):
    """run_index=1..9 vs eval_mean (line with drift 起点・終点 annotation)"""
    xs, ys, es, lbls = [], [], [], []
    for lbl, ub, role in RUN_ORDER:
        e = data.get(lbl, {}).get("eval_tps")
        if e:
            xs.append(e["run_index"])
            ys.append(e["mean"])
            es.append(e["stdev"])
            lbls.append((lbl, ub, role))

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.errorbar(xs, ys, yerr=es, fmt="o-", color="#C44E52",
                markersize=9, lw=1.8, capsize=4, label="eval_tps")
    for x, y, (lbl, ub, role) in zip(xs, ys, lbls):
        suffix = f"\n({role})" if role else ""
        ax.annotate(f"ub={ub}\n{y:.3f}{suffix}", (x, y), textcoords="offset points",
                    xytext=(0, 12), fontsize=8, ha="center")

    # drift 起点・終点をハイライト
    if len(xs) >= 1:
        ax.scatter([xs[0]], [ys[0]], s=260, facecolors="none", edgecolors="#4C72B0",
                   linewidths=2.2, zorder=5, label="drift start (ub=512a)")
    if len(xs) >= 2:
        ax.scatter([xs[-1]], [ys[-1]], s=260, facecolors="none", edgecolors="#55A868",
                   linewidths=2.2, zorder=5, label="drift end (ub=512z)")
        # drift 補正後トレンド
        per_run = (ys[-1] - ys[0]) / (xs[-1] - xs[0]) if xs[-1] != xs[0] else 0.0
        corr = [y - per_run * (x - xs[0]) for x, y in zip(xs, ys)]
        ax.plot(xs, corr, "g:.", lw=1.5, alpha=0.75,
                label=f"drift-corrected (per_run={per_run:+.4f})")

    ax.axhline(y=PEAK_PHASE_T5A_BEST, color="#006400", ls="--", alpha=0.9, lw=2.0,
               label=f"T-5a B18 baseline ({PEAK_PHASE_T5A_BEST})")
    ax.axhline(y=PEAK_PHASE_T5F_BEST, color="#8B0000", ls="--", alpha=0.6,
               label=f"T-5f ({PEAK_PHASE_T5F_BEST})")
    ax.axhline(y=PEAK_PHASE_T5_BEST, color="#DD8452", ls="--", alpha=0.5,
               label=f"T-5 ({PEAK_PHASE_T5_BEST})")
    ax.set_xlabel("run_index (batch 実行順)")
    ax.set_ylabel("eval_tps (t/s)")
    ax.set_title("Phase T-5a-ub: B18 session drift bracket (run_index 順)")
    ax.set_xticks(xs)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower left", fontsize=8)

    fig.tight_layout()
    out = SCRIPT_DIR / "phaseT5aub_drift.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out}")
    plt.close(fig)


def main():
    data = load_stats()
    print(f"[plot] loaded: {sorted(data.keys())}")
    plot_ub_trend(data)
    plot_pareto(data)
    plot_drift(data)


if __name__ == "__main__":
    main()
