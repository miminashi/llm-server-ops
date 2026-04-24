#!/usr/bin/env python3
"""plot_phaseT5a-thr.py - Phase T-5a-thr: B18 × ub=256 × threads 再スイープ グラフ生成

3 枚の PNG を出力:
  1. threads_eval.png:       x=threads linear, y=eval_tps (raw + corrected 2 系列 + 局所多項式)
  2. t3_vs_t5a_dip.png:      T-3 (CPU 36 層) と T-5a-thr (CPU 14 層) の threads sweep 重畳
  3. phaseT5athr_drift.png:  run_index 順の eval、drift 起点・中央・終点ハイライト
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
PEAK_PHASE_T5A_BEST = 18.006
PEAK_PHASE_T5A_UB_BEST = 18.103  # 実測
PEAK_PHASE_T5A_UB_CORR = 18.209  # 補正後 (参考)

# run_index 順 (batch 実行順)
RUN_ORDER = [
    ("thr40a",    40, "drift start"),
    ("thr14",     14, ""),
    ("thr20",     20, ""),
    ("thr28",     28, ""),
    ("thr32",     32, ""),
    ("thr36",     36, ""),
    ("thr38",     38, ""),
    ("thr40_mid", 40, "linearity"),
    ("thr40z",    40, "drift end"),
]

# T-3 (OT=A36, CPU 36 層) の threads sweep 実測値 (参考レポート attachment/phaseT3_pivot.md より)
T3_DATA = {
    24: 14.024,
    28: 14.453,
    32: 14.860,
    36: 14.551,   # dip
    40: 14.781,
}


def load_stats():
    out = {}
    with (SCRIPT_DIR / "phaseT5a-thr_stats.csv").open() as f:
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
                "run_index": int(row["run_index"]),
            }
    return out


def compute_drift_corrected(data):
    """run_index 順で thr40a を起点、thr40z を終点として線形補正。
    return: list of (run_index, threads, label, raw_mean, raw_std, corrected_mean)"""
    rows = []
    for lbl, thr, role in RUN_ORDER:
        e = data.get(lbl, {}).get("eval_tps")
        if not e:
            continue
        rows.append((e["run_index"], thr, lbl, e["mean"], e["stdev"], role))
    rows.sort(key=lambda x: x[0])

    a = next((r for r in rows if r[2] == "thr40a"), None)
    z = next((r for r in rows if r[2] == "thr40z"), None)
    if a is None or z is None:
        return [(idx, thr, lbl, m, s, m, role) for idx, thr, lbl, m, s, role in rows]

    run_count = max(idx for _, _, _, _, _, idx in [(r[0], r[1], r[2], r[3], r[4], r[0]) for r in rows])
    per_run_drift = (z[3] - a[3]) / (run_count - 1) if run_count > 1 else 0.0
    corrected = []
    for idx, thr, lbl, m, s, role in rows:
        corr = m - per_run_drift * (idx - 1)
        corrected.append((idx, thr, lbl, m, s, corr, role))
    return corrected


def plot_threads_eval(data):
    """x=threads linear, y=eval_tps 2 系列 (raw + corrected)。thr40 は 3 点 (a/mid/z) の平均を使用。"""
    corr_rows = compute_drift_corrected(data)

    # threads 毎に集約 (thr40 は a/mid/z の 3 点があるため平均)
    thr_raw = {}
    thr_corr = {}
    thr_err = {}
    for idx, thr, lbl, raw, std, corr, role in corr_rows:
        thr_raw.setdefault(thr, []).append(raw)
        thr_corr.setdefault(thr, []).append(corr)
        thr_err.setdefault(thr, []).append(std)

    threads_sorted = sorted(thr_raw.keys())
    raw_mean = [np.mean(thr_raw[t]) for t in threads_sorted]
    raw_std = [np.mean(thr_err[t]) for t in threads_sorted]
    corr_mean = [np.mean(thr_corr[t]) for t in threads_sorted]

    fig, ax = plt.subplots(figsize=(11, 6.5))
    ax.errorbar(threads_sorted, raw_mean, yerr=raw_std, fmt="o--", color="#C44E52",
                markersize=9, lw=1.4, capsize=4, alpha=0.75, label="raw eval_tps (mean)")
    ax.errorbar(threads_sorted, corr_mean, yerr=raw_std, fmt="s-", color="#006400",
                markersize=10, lw=2.2, capsize=4, label="drift-corrected eval_tps")

    # 局所多項式 (deg=3) を corrected に重ねる (点数が 5 以上の時のみ)
    if len(threads_sorted) >= 5:
        xs = np.array(threads_sorted)
        ys = np.array(corr_mean)
        poly = np.poly1d(np.polyfit(xs, ys, min(3, len(xs) - 1)))
        xfit = np.linspace(xs.min(), xs.max(), 80)
        ax.plot(xfit, poly(xfit), ":", color="#1F77B4", alpha=0.6, lw=1.4,
                label=f"poly deg={min(3, len(xs) - 1)} (corrected)")

    # アノテーション (corrected)
    for t, m in zip(threads_sorted, corr_mean):
        ax.annotate(f"{m:.3f}", (t, m), textcoords="offset points",
                    xytext=(6, 10), fontsize=8, color="#006400")

    # CPU 層数ライン (dip 仮説の検証点)
    ax.axvline(x=14, color="#FFA500", ls=":", alpha=0.55, lw=1.5,
               label="CPU 14 層 (dip 仮説点)")

    # 歴代ピークライン
    ax.axhline(y=PEAK_PHASE_T5A_UB_BEST, color="#006400", ls="--", alpha=0.9, lw=2.0,
               label=f"T-5a-ub 実測 ({PEAK_PHASE_T5A_UB_BEST})")
    ax.axhline(y=PEAK_PHASE_T5A_UB_CORR, color="#006400", ls=":", alpha=0.6, lw=1.4,
               label=f"T-5a-ub 補正後 ({PEAK_PHASE_T5A_UB_CORR})")
    ax.axhline(y=PEAK_PHASE_T5A_BEST, color="#8B0000", ls="--", alpha=0.6,
               label=f"T-5a ({PEAK_PHASE_T5A_BEST})")
    ax.axhline(y=PEAK_PHASE_T5F_BEST, color="#DD8452", ls="--", alpha=0.45,
               label=f"T-5f ({PEAK_PHASE_T5F_BEST})")
    ax.axhline(y=PEAK_PHASE_D, color="#4C72B0", ls="--", alpha=0.35,
               label=f"D ({PEAK_PHASE_D})")

    ax.set_xlabel("threads (numactl node1 束縛、物理20+HT20)")
    ax.set_ylabel("eval_tps (t/s)")
    ax.set_title("Phase T-5a-thr: B18 × ub=256 × threads (raw + drift-corrected)")
    ax.set_xticks(threads_sorted)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right", fontsize=8, ncol=2)

    # node1 境界 (物理 20) を強調
    ax.axvspan(20, 40, alpha=0.06, color="#888888")
    ax.text(30, ax.get_ylim()[0] + 0.05, "HT 領域 (physical > 20)",
            fontsize=8, alpha=0.6, ha="center")

    fig.tight_layout()
    out = SCRIPT_DIR / "threads_eval.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out}")
    plt.close(fig)


def plot_t3_vs_t5a_dip(data):
    """T-3 (CPU 36 層) と T-5a-thr (CPU 14 層) の threads sweep を overlay。
    CPU 層数と threads の dip 仮説を可視化する。"""
    # T-5a-thr eval_mean (drift 補正後)
    corr_rows = compute_drift_corrected(data)
    thr_corr = {}
    for idx, thr, lbl, raw, std, corr, role in corr_rows:
        thr_corr.setdefault(thr, []).append(corr)
    t5a_threads = sorted(thr_corr.keys())
    t5a_corr = [np.mean(thr_corr[t]) for t in t5a_threads]

    # 正規化: 各 Phase の baseline (threads=40) で割る
    t3_threads = sorted(T3_DATA.keys())
    t3_eval = [T3_DATA[t] for t in t3_threads]
    t3_ref = T3_DATA[40]
    t3_rel = [(v - t3_ref) / t3_ref * 100 for v in t3_eval]

    t5a_ref_idx = next((i for i, t in enumerate(t5a_threads) if t == 40), None)
    if t5a_ref_idx is None:
        t5a_rel = [0.0 for _ in t5a_corr]  # fallback
    else:
        t5a_ref = t5a_corr[t5a_ref_idx]
        t5a_rel = [(v - t5a_ref) / t5a_ref * 100 for v in t5a_corr]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # 左: 絶対値
    ax1.plot(t3_threads, t3_eval, "o-", color="#C44E52", markersize=9, lw=2.0,
             label="T-3 (OT=A36, CPU 36 層, ub=1586)")
    ax1.plot(t5a_threads, t5a_corr, "s-", color="#006400", markersize=10, lw=2.2,
             label="T-5a-thr (OT=B18, CPU 14 層, ub=256)")
    ax1.axvline(x=36, color="#C44E52", ls=":", alpha=0.6, lw=1.2, label="T-3 CPU 層数 (36)")
    ax1.axvline(x=14, color="#006400", ls=":", alpha=0.6, lw=1.2, label="T-5a-thr CPU 層数 (14)")
    ax1.set_xlabel("threads")
    ax1.set_ylabel("eval_tps (t/s)")
    ax1.set_title("絶対値 (スケール差大)")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="lower right", fontsize=8)

    # 右: 正規化 (threads=40 基準)
    ax2.plot(t3_threads, t3_rel, "o-", color="#C44E52", markersize=9, lw=2.0,
             label="T-3 (CPU 36 層)")
    ax2.plot(t5a_threads, t5a_rel, "s-", color="#006400", markersize=10, lw=2.2,
             label="T-5a-thr (CPU 14 層)")
    ax2.axvline(x=36, color="#C44E52", ls=":", alpha=0.6, lw=1.2)
    ax2.axvline(x=14, color="#006400", ls=":", alpha=0.6, lw=1.2)
    ax2.axhline(y=0, color="black", ls="-", alpha=0.3, lw=0.8)
    ax2.set_xlabel("threads")
    ax2.set_ylabel("threads=40 比 (%)")
    ax2.set_title("正規化 (threads=40 基準、dip 仮説検証)")
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc="lower right", fontsize=8)

    # アノテーション (dip 指摘)
    for t, r in zip(t3_threads, t3_rel):
        ax2.annotate(f"{r:+.2f}%", (t, r), textcoords="offset points",
                     xytext=(6, 8 if r > -0.5 else -14), fontsize=7, color="#C44E52")
    for t, r in zip(t5a_threads, t5a_rel):
        ax2.annotate(f"{r:+.2f}%", (t, r), textcoords="offset points",
                     xytext=(6, 8 if r > -0.5 else -14), fontsize=7, color="#006400")

    fig.suptitle("T-3 vs T-5a-thr: CPU 層数 ≒ threads での dip 仮説",
                 fontsize=13)
    fig.tight_layout()
    out = SCRIPT_DIR / "t3_vs_t5a_dip.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out}")
    plt.close(fig)


def plot_drift(data):
    """run_index=1..9 vs eval_mean (line with drift 起点・終点・中央 annotation)"""
    xs, ys, es, lbls = [], [], [], []
    for lbl, thr, role in RUN_ORDER:
        e = data.get(lbl, {}).get("eval_tps")
        if e:
            xs.append(e["run_index"])
            ys.append(e["mean"])
            es.append(e["stdev"])
            lbls.append((lbl, thr, role))

    fig, ax = plt.subplots(figsize=(12, 6.5))
    ax.errorbar(xs, ys, yerr=es, fmt="o-", color="#C44E52",
                markersize=9, lw=1.8, capsize=4, label="eval_tps")
    for x, y, (lbl, thr, role) in zip(xs, ys, lbls):
        suffix = f"\n({role})" if role else ""
        ax.annotate(f"thr={thr}\n{y:.3f}{suffix}", (x, y), textcoords="offset points",
                    xytext=(0, 14), fontsize=8, ha="center")

    # drift 起点・中央・終点をハイライト
    if len(xs) >= 1:
        ax.scatter([xs[0]], [ys[0]], s=260, facecolors="none", edgecolors="#4C72B0",
                   linewidths=2.2, zorder=5, label="drift start (thr40a)")
    # 中央 (thr40_mid)
    mid_idx_pos = next((i for i, (l, _, _) in enumerate(lbls) if l == "thr40_mid"), None)
    if mid_idx_pos is not None:
        ax.scatter([xs[mid_idx_pos]], [ys[mid_idx_pos]], s=260, facecolors="none",
                   edgecolors="#FFA500", linewidths=2.2, zorder=5, label="linearity check (thr40_mid)")
    if len(xs) >= 2:
        ax.scatter([xs[-1]], [ys[-1]], s=260, facecolors="none", edgecolors="#55A868",
                   linewidths=2.2, zorder=5, label="drift end (thr40z)")
        # drift 補正後トレンド
        per_run = (ys[-1] - ys[0]) / (xs[-1] - xs[0]) if xs[-1] != xs[0] else 0.0
        corr = [y - per_run * (x - xs[0]) for x, y in zip(xs, ys)]
        ax.plot(xs, corr, ":", color="#006400", lw=1.8, alpha=0.75,
                label=f"drift-corrected (per_run={per_run:+.4f})")

    ax.axhline(y=PEAK_PHASE_T5A_UB_BEST, color="#006400", ls="--", alpha=0.9, lw=2.0,
               label=f"T-5a-ub baseline ({PEAK_PHASE_T5A_UB_BEST})")
    ax.axhline(y=PEAK_PHASE_T5A_BEST, color="#8B0000", ls="--", alpha=0.55,
               label=f"T-5a ({PEAK_PHASE_T5A_BEST})")
    ax.set_xlabel("run_index (batch 実行順)")
    ax.set_ylabel("eval_tps (t/s)")
    ax.set_title("Phase T-5a-thr: session drift bracket + 線形性検証 (run_index 順)")
    ax.set_xticks(xs)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower left", fontsize=8)

    fig.tight_layout()
    out = SCRIPT_DIR / "phaseT5athr_drift.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out}")
    plt.close(fig)


def main():
    data = load_stats()
    print(f"[plot] loaded: {sorted(data.keys())}")
    plot_threads_eval(data)
    plot_t3_vs_t5a_dip(data)
    plot_drift(data)


if __name__ == "__main__":
    main()
