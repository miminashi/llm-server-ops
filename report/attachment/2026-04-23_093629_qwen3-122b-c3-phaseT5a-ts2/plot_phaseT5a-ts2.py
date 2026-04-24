#!/usr/bin/env python3
"""plot_phaseT5a-ts2.py - Phase T-5a-ts2: B14 × tensor-split で 19+ 突破試行 グラフ生成

3 枚の PNG を出力:
  1. b14_eval.png:    x=label (実行順), y=eval_tps (raw + linear corrected)、T-5a-ts peak 比較
  2. b14_vs_b16.png:  OT (B18/B16/B14) × eval の散布図、CPU 層削減感度可視化
  3. drift_2pt.png:   2 点 bracket (起点/終点) drift と線形 fit
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent

PEAK_PHASE_D = 15.030
PEAK_PHASE_T5_BEST = 16.024
PEAK_PHASE_T5F_BEST = 16.455
PEAK_PHASE_T5A_BEST = 18.006
PEAK_PHASE_T5A_UB_BEST = 18.103
PEAK_PHASE_T5A_THR_BEST = 17.988
PEAK_PHASE_T5A_TS_BEST = 18.417  # 直前歴代 #1

TS_B14_PRIMARY = os.environ.get("TS_B14_PRIMARY", "11,12,13,14")
TS_B14_ALT = os.environ.get("TS_B14_ALT", "11,12,13,14")
TS_B16_SKEW = os.environ.get("TS_B16_SKEW", "11,12,13,13")

RUN_ORDER = [
    ("B18_default_a",    "B18",  "default",       "drift start"),
    ("B14c_ts_primary",  "B14c", TS_B14_PRIMARY,  "B14 本命 (OT-c)"),
    ("B14b_ts_alt",      "B14b", TS_B14_ALT,      "B14 alt (OT-b)"),
    ("B16_ts_skew",      "B16",  TS_B16_SKEW,     "T-5a-ts peak 再現"),
    ("B18_default_z",    "B18",  "default",       "drift end"),
]


def load_stats():
    out = {}
    with (SCRIPT_DIR / "phaseT5a-ts2_stats.csv").open() as f:
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
                "ts": row["ts"],
                "ot_tag": row["ot_tag"],
                "cpu_layers": int(row["cpu_layers"]),
                "run_index": int(row["run_index"]),
            }
    return out


def linear_2pt_corrector(data):
    """2 点 bracket (起点 + 終点) から線形補正器を構築。"""
    pts = []
    for lbl in ("B18_default_a", "B18_default_z"):
        e = data.get(lbl, {}).get("eval_tps")
        if e:
            pts.append((e["run_index"], e["mean"]))
    pts.sort(key=lambda p: p[0])
    if len(pts) < 2:
        return (lambda idx: 0.0), {"recommendation": "insufficient", "n_points": len(pts)}
    a_idx, a_y = pts[0]
    z_idx, z_y = pts[-1]
    per_run = (z_y - a_y) / (z_idx - a_idx) if z_idx != a_idx else 0.0
    info = {
        "linear_per_run": per_run,
        "a_idx": a_idx,
        "a_y": a_y,
        "z_idx": z_idx,
        "z_y": z_y,
        "delta": z_y - a_y,
        "n_points": len(pts),
        "recommendation": "linear",
    }
    def _corr(idx):
        return -per_run * (idx - a_idx)
    return _corr, info


def plot_b14_eval(data):
    """label 実行順 × eval_tps の bar (raw + corrected)。T-5a-ts peak 水準線で比較。"""
    corrector, info = linear_2pt_corrector(data)
    rows = []
    for lbl, ot, ts, role in RUN_ORDER:
        e = data.get(lbl, {}).get("eval_tps")
        if not e:
            continue
        idx = e["run_index"]
        corr = e["mean"] + corrector(idx)
        rows.append((idx, lbl, ot, ts, e["mean"], e["stdev"], corr, role))
    rows.sort(key=lambda r: r[0])

    labels = [f"{r[1]}\n({r[2]} ts={r[3]})" for r in rows]
    raws = [r[4] for r in rows]
    errs = [r[5] for r in rows]
    corrs = [r[6] for r in rows]
    xs = np.arange(len(rows))

    fig, ax = plt.subplots(figsize=(12, 7))
    width = 0.38
    ax.bar(xs - width/2, raws, width, yerr=errs, color="#C44E52", alpha=0.75,
           capsize=4, label="raw eval_tps")
    ax.bar(xs + width/2, corrs, width, color="#006400", alpha=0.85,
           label=f"linear-corrected (per_run={info.get('linear_per_run', 0):+.4f})")

    for x, raw, corr in zip(xs, raws, corrs):
        ax.annotate(f"{raw:.3f}", (x - width/2, raw), textcoords="offset points",
                    xytext=(0, 4), fontsize=7, ha="center", color="#8B0000")
        ax.annotate(f"{corr:.3f}", (x + width/2, corr), textcoords="offset points",
                    xytext=(0, 4), fontsize=7, ha="center", color="#003300")

    ax.axhline(y=PEAK_PHASE_T5A_TS_BEST, color="#006400", ls="--", alpha=0.9, lw=1.8,
               label=f"T-5a-ts peak ({PEAK_PHASE_T5A_TS_BEST}, 直前歴代 #1)")
    ax.axhline(y=19.0, color="#FFA500", ls="-.", alpha=0.7, lw=1.8, label="19.0 t/s 目標")
    ax.axhline(y=PEAK_PHASE_T5A_UB_BEST, color="#1F77B4", ls=":", alpha=0.6,
               label=f"T-5a-ub ({PEAK_PHASE_T5A_UB_BEST})")
    ax.axhline(y=PEAK_PHASE_T5A_BEST, color="#8B0000", ls="--", alpha=0.4,
               label=f"T-5a ({PEAK_PHASE_T5A_BEST})")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=8)
    ax.set_ylabel("eval_tps (t/s)")
    ax.set_title("Phase T-5a-ts2: B14 × tensor-split eval (raw + drift linear 補正)")
    ax.grid(True, alpha=0.3, axis="y")
    ax.legend(loc="lower left", fontsize=8)

    y_min = min(min(raws), min(corrs)) - 0.3
    y_max = max(max(raws), max(corrs), 19.2) + 0.2
    ax.set_ylim(max(15.0, y_min), y_max)

    fig.tight_layout()
    out = SCRIPT_DIR / "b14_eval.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out}")
    plt.close(fig)


def plot_b14_vs_b16(data):
    """CPU 層 (B14/B16/B18) × eval の散布図、OT 削減感度可視化。"""
    fig, ax = plt.subplots(figsize=(11, 6.5))
    color_map = {"B18": "#4C72B0", "B16": "#8B4513", "B14": "#C44E52"}

    cpu_to_x = {18: 0, 16: 1, 14: 2}
    cpu_labels = {18: "B18 (CPU 18 層)", 16: "B16 (CPU 16 層)", 14: "B14 (CPU 14 層)"}
    plotted_legend = set()
    # OT を B14 は B14c/B14b 両方扱う — color も区別
    color_map2 = {"B18": "#4C72B0", "B16": "#8B4513", "B14c": "#C44E52", "B14b": "#FFA500"}
    for lbl, ot, ts, role in RUN_ORDER:
        e = data.get(lbl, {}).get("eval_tps")
        if not e:
            continue
        x = cpu_to_x.get(e["cpu_layers"], -1)
        if x < 0:
            continue
        # 同じ OT で複数 label がある場合は微小オフセット
        xo = 0
        if lbl == "B18_default_a":
            xo = -0.10
        elif lbl == "B18_default_z":
            xo = 0.10
        elif lbl == "B14c_ts_primary":
            xo = -0.10
        elif lbl == "B14b_ts_alt":
            xo = 0.10
        show_label = f"{ot}" if ot not in plotted_legend else None
        plotted_legend.add(ot)
        ax.errorbar([x + xo], [e["mean"]], yerr=[e["stdev"]],
                    fmt="o", color=color_map2.get(ot, color_map.get(ot, "#888")),
                    markersize=14, capsize=4,
                    markeredgecolor="black", markeredgewidth=0.5,
                    label=show_label)
        ax.annotate(f"{lbl}\nts={ts}\n{e['mean']:.3f}", (x + xo, e["mean"]),
                    textcoords="offset points", xytext=(12, 2), fontsize=7,
                    va="center")

    # T-5a-ts peak と target line
    ax.axhline(y=PEAK_PHASE_T5A_TS_BEST, color="#006400", ls="--", alpha=0.9, lw=1.8,
               label=f"T-5a-ts peak ({PEAK_PHASE_T5A_TS_BEST})")
    ax.axhline(y=19.0, color="#FFA500", ls="-.", alpha=0.7, lw=1.8, label="19.0 目標")
    ax.axhline(y=PEAK_PHASE_T5A_UB_BEST, color="#1F77B4", ls=":", alpha=0.5,
               label=f"T-5a-ub ({PEAK_PHASE_T5A_UB_BEST})")

    ax.set_xticks(list(cpu_to_x.values()))
    ax.set_xticklabels([cpu_labels[k] for k in cpu_to_x.keys()], fontsize=10)
    ax.set_ylabel("eval_tps (t/s)")
    ax.set_title("Phase T-5a-ts2: CPU 層削減 (B18 → B16 → B14) × `-ts` の eval 感度")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right", fontsize=8)

    fig.tight_layout()
    out = SCRIPT_DIR / "b14_vs_b16.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out}")
    plt.close(fig)


def plot_drift_2pt(data):
    """run_index 順 eval、2 点 bracket (起点/終点) + 線形 fit"""
    xs, ys, es, lbls = [], [], [], []
    for lbl, ot, ts, role in RUN_ORDER:
        e = data.get(lbl, {}).get("eval_tps")
        if e:
            xs.append(e["run_index"])
            ys.append(e["mean"])
            es.append(e["stdev"])
            lbls.append((lbl, ot, ts, role))

    fig, ax = plt.subplots(figsize=(11, 6.5))
    ax.errorbar(xs, ys, yerr=es, fmt="o-", color="#C44E52", markersize=10, lw=1.8,
                capsize=4, label="eval_tps")
    for x, y, (lbl, ot, ts, role) in zip(xs, ys, lbls):
        ax.annotate(f"{ot}\n{y:.3f}", (x, y), textcoords="offset points",
                    xytext=(0, 14), fontsize=8, ha="center")

    bracket = []
    for lbl in ("B18_default_a", "B18_default_z"):
        e = data.get(lbl, {}).get("eval_tps")
        if e:
            bracket.append((e["run_index"], e["mean"]))
    bracket.sort(key=lambda p: p[0])

    if len(bracket) == 2:
        bx = [b[0] for b in bracket]
        by = [b[1] for b in bracket]
        ax.scatter([bx[0]], [by[0]], s=300, facecolors="none", edgecolors="#4C72B0",
                   linewidths=2.5, zorder=5, label="bracket start (B18_default_a)")
        ax.scatter([bx[-1]], [by[-1]], s=300, facecolors="none", edgecolors="#55A868",
                   linewidths=2.5, zorder=5, label="bracket end (B18_default_z)")
        per_run = (by[-1] - by[0]) / (bx[-1] - bx[0]) if bx[-1] != bx[0] else 0.0
        x_fit = np.linspace(min(xs), max(xs), 60)
        y_lin = [by[0] + per_run * (x - bx[0]) for x in x_fit]
        ax.plot(x_fit, y_lin, "--", color="#1F77B4", lw=1.8, alpha=0.8,
                label=f"linear fit (per_run={per_run:+.4f}, Δ={by[-1]-by[0]:+.3f})")

    ax.axhline(y=PEAK_PHASE_T5A_TS_BEST, color="#006400", ls="--", alpha=0.9, lw=1.8,
               label=f"T-5a-ts peak ({PEAK_PHASE_T5A_TS_BEST})")
    ax.axhline(y=PEAK_PHASE_T5A_UB_BEST, color="#1F77B4", ls=":", alpha=0.6,
               label=f"T-5a-ub ({PEAK_PHASE_T5A_UB_BEST})")
    ax.axhline(y=19.0, color="#FFA500", ls="-.", alpha=0.7, lw=1.6, label="19.0 t/s 目標")
    ax.set_xlabel("run_index (batch 実行順)")
    ax.set_ylabel("eval_tps (t/s)")
    ax.set_title("Phase T-5a-ts2: 2 点 bracket drift (linear fit)")
    ax.set_xticks(xs)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower left", fontsize=8)

    fig.tight_layout()
    out = SCRIPT_DIR / "drift_2pt.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out}")
    plt.close(fig)


def main():
    data = load_stats()
    print(f"[plot] loaded: {sorted(data.keys())}")
    plot_b14_eval(data)
    plot_b14_vs_b16(data)
    plot_drift_2pt(data)


if __name__ == "__main__":
    main()
