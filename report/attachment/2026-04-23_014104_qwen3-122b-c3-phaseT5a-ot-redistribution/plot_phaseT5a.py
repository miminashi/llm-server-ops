#!/usr/bin/env python3
"""plot_phaseT5a.py - Phase T-5a: OT 再配分 + drift bracket グラフ生成

3 枚の PNG を出力:
  1. phaseT5a_cpu_trend.png: CPU 層数 (x=B-number) vs eval + prompt dual y-axis
  2. phaseT5a_pareto.png:    x=prompt_mean, y=eval_mean scatter (OT ラベル付き)
  3. phaseT5a_drift.png:     run_index=1..7 vs eval_mean、起点・終点強調
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

# run_index 順 (batch で実行する順)
RUN_ORDER = [
    ("B28_run1", "B28", 28, "drift start"),
    ("B24_run1", "B24", 24, ""),
    ("B20_run1", "B20", 20, ""),
    ("B18_run1", "B18", 18, "OOM boundary"),
    ("B20_run2", "B20", 20, ""),
    ("B24_run2", "B24", 24, ""),
    ("B28_run2", "B28", 28, "drift end"),
]


def load_stats():
    out = {}
    with (SCRIPT_DIR / "phaseT5a_stats.csv").open() as f:
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
                "ot_tag": row["ot_tag"],
                "cpu_layers": int(row["cpu_layers"]),
            }
    return out


def plot_cpu_trend(data):
    """CPU 層数 (x=B-number) vs eval_mean + prompt_mean dual-axis (OT 別、run#1/run#2 平均)"""
    # OT タグ別に集約して run#1/run#2 平均
    ot_data = {}  # cpu_layers -> (ot_tag, eval_mean_avg, eval_std_max, prompt_mean_avg, prompt_std_max, n_run)
    groups = {}  # cpu_layers -> [(label, e, p), ...]
    for lbl, ot, cpu_l, _ in RUN_ORDER:
        e = data.get(lbl, {}).get("eval_tps")
        p = data.get(lbl, {}).get("prompt_tps")
        if e and p:
            groups.setdefault(cpu_l, []).append((lbl, ot, e, p))
    for cpu_l, rows in groups.items():
        e_means = [r[2]["mean"] for r in rows]
        e_stds = [r[2]["stdev"] for r in rows]
        p_means = [r[3]["mean"] for r in rows]
        p_stds = [r[3]["stdev"] for r in rows]
        ot = rows[0][1]
        ot_data[cpu_l] = (
            ot,
            np.mean(e_means), max(e_stds) if e_stds else 0,
            np.mean(p_means), max(p_stds) if p_stds else 0,
            len(rows),
        )

    cpu_ls = sorted(ot_data.keys())  # 昇順 (B18→B28)
    ots = [ot_data[c][0] for c in cpu_ls]
    e_means = [ot_data[c][1] for c in cpu_ls]
    e_stds = [ot_data[c][2] for c in cpu_ls]
    p_means = [ot_data[c][3] for c in cpu_ls]
    p_stds = [ot_data[c][4] for c in cpu_ls]
    n_runs = [ot_data[c][5] for c in cpu_ls]

    fig, ax1 = plt.subplots(figsize=(11, 6))
    ax1.errorbar(cpu_ls, e_means, yerr=e_stds, fmt="o-", color="#C44E52",
                 markersize=10, lw=2.3, capsize=5, label="eval_tps (avg)")
    ax1.set_xlabel("CPU offload layers (B-number)")
    ax1.set_ylabel("eval_tps (t/s)", color="#C44E52")
    ax1.tick_params(axis="y", labelcolor="#C44E52")
    ax1.set_xticks(cpu_ls)
    ax1.set_xticklabels([f"{ot_data[c][0]}\n({c} 層)" for c in cpu_ls])
    for c, m, n in zip(cpu_ls, e_means, n_runs):
        suffix = f" (n={n})" if n > 1 else ""
        ax1.annotate(f"{m:.3f}{suffix}", (c, m), textcoords="offset points",
                     xytext=(6, 10), fontsize=8, color="#C44E52")
    ax1.axhline(y=PEAK_PHASE_T5F_BEST, color="#8B0000", ls="--", alpha=0.75,
                label=f"T-5f ({PEAK_PHASE_T5F_BEST})")
    ax1.axhline(y=PEAK_PHASE_T5E_BEST, color="#8B4513", ls="--", alpha=0.6,
                label=f"T-5e ({PEAK_PHASE_T5E_BEST})")
    ax1.axhline(y=PEAK_PHASE_T5_BEST, color="#DD8452", ls="--", alpha=0.5,
                label=f"T-5 ({PEAK_PHASE_T5_BEST})")
    ax1.axhline(y=PEAK_PHASE_D, color="#4C72B0", ls="--", alpha=0.4,
                label=f"D ({PEAK_PHASE_D})")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="lower left", fontsize=8)

    ax2 = ax1.twinx()
    ax2.errorbar(cpu_ls, p_means, yerr=p_stds, fmt="s--", color="#4C72B0",
                 markersize=7, lw=1.5, capsize=4, label="prompt_tps (avg)", alpha=0.85)
    ax2.set_ylabel("prompt_tps (t/s)", color="#4C72B0")
    ax2.tick_params(axis="y", labelcolor="#4C72B0")
    for c, m in zip(cpu_ls, p_means):
        ax2.annotate(f"{m:.1f}", (c, m), textcoords="offset points",
                     xytext=(6, -14), fontsize=7, color="#4C72B0")
    ax2.legend(loc="lower right", fontsize=8)

    fig.suptitle("Phase T-5a: OT 再配分 (CPU 層数 vs eval + prompt)", fontsize=12)
    fig.tight_layout()
    out = SCRIPT_DIR / "phaseT5a_cpu_trend.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out}")
    plt.close(fig)


def plot_pareto(data):
    """prompt_mean vs eval_mean scatter (OT ラベル、run#1/run#2 個別 plot)"""
    xs, ys, cpu_ls, lbls, ots = [], [], [], [], []
    for lbl, ot, cpu_l, _ in RUN_ORDER:
        e = data.get(lbl, {}).get("eval_tps")
        p = data.get(lbl, {}).get("prompt_tps")
        if e and p:
            xs.append(p["mean"])
            ys.append(e["mean"])
            cpu_ls.append(cpu_l)
            lbls.append(lbl)
            ots.append(ot)

    fig, ax = plt.subplots(figsize=(10, 7))
    sc = ax.scatter(xs, ys, c=cpu_ls, cmap="viridis_r", s=140, alpha=0.85,
                    edgecolor="black", linewidth=1)
    for x, y, lbl in zip(xs, ys, lbls):
        ax.annotate(lbl, (x, y), textcoords="offset points",
                    xytext=(8, 6), fontsize=8)

    # Pareto frontier (上方凸包)
    pareto = []
    max_y = -1
    for x, y, u in sorted(zip(xs, ys, cpu_ls), key=lambda t: -t[0]):  # prompt 降順
        if y > max_y:
            pareto.append((x, y, u))
            max_y = y
    if len(pareto) >= 2:
        px, py, _ = zip(*sorted(pareto))
        ax.plot(px, py, "r--", alpha=0.4, lw=1.5, label="Pareto frontier")

    ax.axhline(y=PEAK_PHASE_T5F_BEST, color="#8B0000", ls=":", alpha=0.7,
               label=f"T-5f ({PEAK_PHASE_T5F_BEST})")
    ax.axhline(y=PEAK_PHASE_T5E_BEST, color="#8B4513", ls=":", alpha=0.5,
               label=f"T-5e ({PEAK_PHASE_T5E_BEST})")
    ax.set_xlabel("prompt_tps (t/s)")
    ax.set_ylabel("eval_tps (t/s)")
    ax.set_title("Phase T-5a: eval / prompt Pareto (color = CPU layers)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    plt.colorbar(sc, ax=ax, label="CPU offload layers")

    fig.tight_layout()
    out = SCRIPT_DIR / "phaseT5a_pareto.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out}")
    plt.close(fig)


def plot_drift(data):
    """run_index=1..7 vs eval_mean (line with drift 起点・終点 annotation)"""
    xs, ys, es, lbls = [], [], [], []
    for lbl, ot, cpu_l, role in RUN_ORDER:
        e = data.get(lbl, {}).get("eval_tps")
        if e:
            xs.append(e["run_index"])
            ys.append(e["mean"])
            es.append(e["stdev"])
            lbls.append((lbl, ot, cpu_l, role))

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.errorbar(xs, ys, yerr=es, fmt="o-", color="#C44E52",
                markersize=9, lw=1.8, capsize=4, label="eval_tps")
    for x, y, (lbl, ot, cpu_l, role) in zip(xs, ys, lbls):
        suffix = f"\n({role})" if role else ""
        ax.annotate(f"{ot}\n{y:.3f}{suffix}", (x, y), textcoords="offset points",
                    xytext=(0, 12), fontsize=8, ha="center")

    # drift 起点・終点をハイライト (B28_run1 / B28_run2)
    b28_points = [(x, y) for x, y, l in zip(xs, ys, lbls) if l[1] == "B28"]
    if len(b28_points) >= 1:
        ax.scatter([b28_points[0][0]], [b28_points[0][1]], s=260, facecolors="none",
                   edgecolors="#4C72B0", linewidths=2.2, zorder=5, label="drift start (B28)")
    if len(b28_points) >= 2:
        ax.scatter([b28_points[-1][0]], [b28_points[-1][1]], s=260, facecolors="none",
                   edgecolors="#55A868", linewidths=2.2, zorder=5, label="drift end (B28)")
        # drift 補正後トレンド (B28 起点・終点から線形外挿)
        per_run = (b28_points[-1][1] - b28_points[0][1]) / (b28_points[-1][0] - b28_points[0][0])
        corr = [y - per_run * (x - b28_points[0][0]) for x, y in zip(xs, ys)]
        ax.plot(xs, corr, "g:.", lw=1.5, alpha=0.75,
                label=f"drift-corrected (per_run={per_run:+.4f})")

    ax.axhline(y=PEAK_PHASE_T5F_BEST, color="#8B0000", ls="--", alpha=0.75,
               label=f"T-5f ({PEAK_PHASE_T5F_BEST})")
    ax.axhline(y=PEAK_PHASE_T5E_BEST, color="#8B4513", ls="--", alpha=0.5,
               label=f"T-5e ({PEAK_PHASE_T5E_BEST})")
    ax.set_xlabel("run_index (batch 実行順)")
    ax.set_ylabel("eval_tps (t/s)")
    ax.set_title("Phase T-5a: session drift bracket (B28→B24→B20→B18→B20→B24→B28)")
    ax.set_xticks(xs)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower left", fontsize=8)

    fig.tight_layout()
    out = SCRIPT_DIR / "phaseT5a_drift.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out}")
    plt.close(fig)


def main():
    data = load_stats()
    print(f"[plot] loaded: {sorted(data.keys())}")
    plot_cpu_trend(data)
    plot_pareto(data)
    plot_drift(data)


if __name__ == "__main__":
    main()
