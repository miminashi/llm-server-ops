#!/usr/bin/env python3
"""plot_phaseT5a-ts.py - Phase T-5a-ts: tensor-split (-ts) で B16 化試行 グラフ生成

3 枚の PNG を出力:
  1. ts_axis.png:           x=label (実行順), y=eval_tps (raw + corrected)、ts/OT 比較
  2. b18_vs_b16.png:        OT (B18 vs B16) × ts (default/equal/skew/alt) 配置で eval を比較
  3. drift_3pt.png:         3 点 bracket (起点/中央/終点) drift と線形/2 次 fit
"""
from __future__ import annotations

import csv
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
PEAK_PHASE_T5A_UB_CORR = 18.209
PEAK_PHASE_T5A_THR_BEST = 17.988

RUN_ORDER = [
    ("B18_default_a",   "B18", "default",     "drift start"),
    ("B18_ts_equal",    "B18", "13,11,12,13", "ts control"),
    ("B18_ts_skew",     "B18", "11,12,13,13", "ts skew"),
    ("B16_ts_skew",     "B16", "11,12,13,13", "B16 本命"),
    ("B16_ts_alt",      "B16", "10,12,13,14", "B16 alt"),
    ("B18_default_mid", "B18", "default",     "linearity"),
    ("B18_default_z",   "B18", "default",     "drift end"),
]


def load_stats():
    out = {}
    with (SCRIPT_DIR / "phaseT5a-ts_stats.csv").open() as f:
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


def hybrid_drift_corrector(data):
    """3 点 bracket から線形/2 次 hybrid 補正器を構築。
    return: (corrector(idx) -> additive correction, info dict)"""
    pts = []
    for lbl in ("B18_default_a", "B18_default_mid", "B18_default_z"):
        e = data.get(lbl, {}).get("eval_tps")
        if e:
            pts.append((e["run_index"], e["mean"]))
    pts.sort(key=lambda p: p[0])
    if len(pts) < 2:
        return (lambda idx: 0.0), {"recommendation": "insufficient", "n_points": len(pts)}
    a_idx, a_y = pts[0]
    z_idx, z_y = pts[-1]
    per_run = (z_y - a_y) / (z_idx - a_idx) if z_idx != a_idx else 0.0
    info = {"linear_per_run": per_run, "a_idx": a_idx, "a_y": a_y, "n_points": len(pts)}
    if len(pts) == 3:
        m_idx, m_y = pts[1]
        pred_m = a_y + per_run * (m_idx - a_idx)
        residual = m_y - pred_m
        ys_pred_lin = [a_y + per_run * (idx - a_idx) for idx, _ in pts]
        ys = [y for _, y in pts]
        ss_res = sum((y - p) ** 2 for y, p in zip(ys, ys_pred_lin))
        ss_tot = sum((y - sum(ys) / 3) ** 2 for y in ys)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 1.0
        info.update({"residual": residual, "r2": r2})
        try:
            coeff = np.polyfit([p[0] for p in pts], [p[1] for p in pts], 2)
            qa, qb, qc = float(coeff[0]), float(coeff[1]), float(coeff[2])
            info.update({"qa": qa, "qb": qb, "qc": qc})
            use_quad = r2 < 0.95
            info["recommendation"] = "quadratic" if use_quad else "linear"
            if use_quad:
                baseline_val = qa * a_idx ** 2 + qb * a_idx + qc
                def _corr(idx):
                    return baseline_val - (qa * idx ** 2 + qb * idx + qc)
                return _corr, info
        except Exception:
            info["recommendation"] = "linear"
    else:
        info["recommendation"] = "linear"
    def _corr(idx):
        return -per_run * (idx - a_idx)
    return _corr, info


def plot_ts_axis(data):
    """label (実行順) × eval_tps の bar/error。raw + drift 補正後を併記。"""
    corrector, info = hybrid_drift_corrector(data)
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

    fig, ax = plt.subplots(figsize=(13, 7))
    width = 0.38
    bars_raw = ax.bar(xs - width/2, raws, width, yerr=errs, color="#C44E52", alpha=0.75,
                      capsize=4, label="raw eval_tps")
    bars_corr = ax.bar(xs + width/2, corrs, width, color="#006400", alpha=0.85,
                       label=f"drift-corrected ({info.get('recommendation', 'n/a')})")

    for x, raw, corr in zip(xs, raws, corrs):
        ax.annotate(f"{raw:.3f}", (x - width/2, raw), textcoords="offset points",
                    xytext=(0, 4), fontsize=7, ha="center", color="#8B0000")
        ax.annotate(f"{corr:.3f}", (x + width/2, corr), textcoords="offset points",
                    xytext=(0, 4), fontsize=7, ha="center", color="#003300")

    ax.axhline(y=PEAK_PHASE_T5A_UB_BEST, color="#006400", ls="--", alpha=0.9, lw=1.8,
               label=f"T-5a-ub baseline ({PEAK_PHASE_T5A_UB_BEST})")
    ax.axhline(y=19.0, color="#FFA500", ls="-.", alpha=0.7, lw=1.8,
               label="19.0 t/s 目標")
    ax.axhline(y=PEAK_PHASE_T5A_BEST, color="#8B0000", ls="--", alpha=0.5,
               label=f"T-5a ({PEAK_PHASE_T5A_BEST})")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("eval_tps (t/s)")
    ax.set_title(f"Phase T-5a-ts: -ts × OT による eval (raw + drift {info.get('recommendation', 'n/a')} 補正)")
    ax.grid(True, alpha=0.3, axis="y")
    ax.legend(loc="lower left", fontsize=8)

    # y 軸 zoom (16-20 想定)
    y_min = min(min(raws), min(corrs)) - 0.3
    y_max = max(max(raws), max(corrs), 19.2) + 0.2
    ax.set_ylim(max(15.0, y_min), y_max)

    fig.tight_layout()
    out = SCRIPT_DIR / "ts_axis.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out}")
    plt.close(fig)


def plot_b18_vs_b16(data):
    """OT (B18 vs B16) × ts (4 種) の散布図。同一 ts での OT 効果分離を強調。"""
    fig, ax = plt.subplots(figsize=(11, 6.5))
    color_map = {"B18": "#4C72B0", "B16": "#C44E52"}

    # ts → x 座標 (label)
    ts_to_x = {
        "default":     0,
        "13,11,12,13": 1,
        "11,12,13,13": 2,
        "10,12,13,14": 3,
    }
    plotted = []
    for lbl, ot, ts, role in RUN_ORDER:
        e = data.get(lbl, {}).get("eval_tps")
        if not e:
            continue
        x = ts_to_x.get(ts, -1)
        if x < 0:
            continue
        # B18_default_a/mid/z は重なるため微小オフセット
        if lbl == "B18_default_a":
            xo = -0.08
        elif lbl == "B18_default_mid":
            xo = 0
        elif lbl == "B18_default_z":
            xo = 0.08
        else:
            xo = 0
        ax.errorbar([x + xo], [e["mean"]], yerr=[e["stdev"]],
                    fmt="o", color=color_map.get(ot, "#888"), markersize=12, capsize=4,
                    markeredgecolor="black", markeredgewidth=0.5,
                    label=f"{ot} {lbl}" if lbl not in [p[1] for p in plotted] else None)
        ax.annotate(f"{e['mean']:.3f}", (x + xo, e["mean"]), textcoords="offset points",
                    xytext=(8, 0), fontsize=8, va="center")
        plotted.append((ot, lbl))

    # 同 ts での B18 vs B16 を線で結ぶ
    for ts_str in ("11,12,13,13",):
        x = ts_to_x[ts_str]
        b18 = data.get("B18_ts_skew", {}).get("eval_tps")
        b16 = data.get("B16_ts_skew", {}).get("eval_tps")
        if b18 and b16:
            ax.plot([x, x], [b18["mean"], b16["mean"]], "k:", alpha=0.5, lw=1.5)
            mid = (b18["mean"] + b16["mean"]) / 2
            delta = b16["mean"] - b18["mean"]
            ax.annotate(f"Δ={delta:+.3f}\n(同 ts での OT 効果)",
                        (x - 0.15, mid), fontsize=8, color="#444",
                        ha="right", va="center")

    ax.set_xticks(list(ts_to_x.values()))
    ax.set_xticklabels([f"ts={k}" for k in ts_to_x.keys()], fontsize=9)
    ax.set_ylabel("eval_tps (t/s)")
    ax.set_title("Phase T-5a-ts: -ts × OT (B18 vs B16) eval 比較")
    ax.axhline(y=PEAK_PHASE_T5A_UB_BEST, color="#006400", ls="--", alpha=0.9, lw=1.8,
               label=f"T-5a-ub ({PEAK_PHASE_T5A_UB_BEST})")
    ax.axhline(y=19.0, color="#FFA500", ls="-.", alpha=0.7, lw=1.8, label="19.0 目標")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower left", fontsize=8, ncol=2)

    fig.tight_layout()
    out = SCRIPT_DIR / "b18_vs_b16.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out}")
    plt.close(fig)


def plot_drift_3pt(data):
    """run_index 順 eval、起点/中央/終点ハイライト + 線形 fit + 2 次 fit"""
    xs, ys, es, lbls = [], [], [], []
    for lbl, ot, ts, role in RUN_ORDER:
        e = data.get(lbl, {}).get("eval_tps")
        if e:
            xs.append(e["run_index"])
            ys.append(e["mean"])
            es.append(e["stdev"])
            lbls.append((lbl, ot, ts, role))

    fig, ax = plt.subplots(figsize=(12, 6.5))
    ax.errorbar(xs, ys, yerr=es, fmt="o-", color="#C44E52", markersize=9, lw=1.8,
                capsize=4, label="eval_tps")
    for x, y, (lbl, ot, ts, role) in zip(xs, ys, lbls):
        ax.annotate(f"{ot}\n{y:.3f}", (x, y), textcoords="offset points",
                    xytext=(0, 14), fontsize=8, ha="center")

    # bracket points
    bracket = []
    for lbl in ("B18_default_a", "B18_default_mid", "B18_default_z"):
        e = data.get(lbl, {}).get("eval_tps")
        if e:
            bracket.append((e["run_index"], e["mean"]))
    bracket.sort(key=lambda p: p[0])

    if len(bracket) >= 2:
        bx = [b[0] for b in bracket]
        by = [b[1] for b in bracket]
        # 起点・終点
        ax.scatter([bx[0]], [by[0]], s=300, facecolors="none", edgecolors="#4C72B0",
                   linewidths=2.5, zorder=5, label="bracket start (B18_default_a)")
        ax.scatter([bx[-1]], [by[-1]], s=300, facecolors="none", edgecolors="#55A868",
                   linewidths=2.5, zorder=5, label="bracket end (B18_default_z)")
        if len(bracket) >= 3:
            ax.scatter([bx[1]], [by[1]], s=300, facecolors="none", edgecolors="#FFA500",
                       linewidths=2.5, zorder=5, label="bracket mid (B18_default_mid)")
        # 線形 fit
        per_run = (by[-1] - by[0]) / (bx[-1] - bx[0]) if bx[-1] != bx[0] else 0.0
        x_fit = np.linspace(min(xs), max(xs), 60)
        y_lin = [by[0] + per_run * (x - bx[0]) for x in x_fit]
        ax.plot(x_fit, y_lin, "--", color="#1F77B4", lw=1.6, alpha=0.7,
                label=f"linear fit (per_run={per_run:+.4f})")
        # 2 次 fit
        if len(bracket) >= 3:
            try:
                coeff = np.polyfit(bx, by, 2)
                y_quad = np.polyval(coeff, x_fit)
                ax.plot(x_fit, y_quad, "-.", color="#9467BD", lw=1.6, alpha=0.7,
                        label=f"quadratic fit (a={coeff[0]:+.5f})")
            except Exception:
                pass

    ax.axhline(y=PEAK_PHASE_T5A_UB_BEST, color="#006400", ls="--", alpha=0.9, lw=1.8,
               label=f"T-5a-ub ({PEAK_PHASE_T5A_UB_BEST})")
    ax.axhline(y=PEAK_PHASE_T5A_THR_BEST, color="#888", ls=":", alpha=0.6,
               label=f"T-5a-thr thr40a ({PEAK_PHASE_T5A_THR_BEST})")
    ax.axhline(y=19.0, color="#FFA500", ls="-.", alpha=0.7, lw=1.6, label="19.0 t/s 目標")
    ax.set_xlabel("run_index (batch 実行順)")
    ax.set_ylabel("eval_tps (t/s)")
    ax.set_title("Phase T-5a-ts: 3 点 bracket drift 線形/2 次 fit")
    ax.set_xticks(xs)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower left", fontsize=8, ncol=2)

    fig.tight_layout()
    out = SCRIPT_DIR / "drift_3pt.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"[plot] wrote {out}")
    plt.close(fig)


def main():
    data = load_stats()
    print(f"[plot] loaded: {sorted(data.keys())}")
    plot_ts_axis(data)
    plot_b18_vs_b16(data)
    plot_drift_3pt(data)


if __name__ == "__main__":
    main()
