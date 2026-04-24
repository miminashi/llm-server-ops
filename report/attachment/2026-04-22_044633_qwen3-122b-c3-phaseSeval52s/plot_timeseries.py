#!/usr/bin/env python3
"""plot_timeseries.py - Phase S-eval 52 session + Sbfine 3 reference points の時系列プロット

直接比較可能な実験 (ctx=32768 × fa=1 × OT=MoE-only × ub∈{1584,1586,1664} × prompt_1k × P100 t120h-p100) の
eval_tps 時系列を 1 枚の PNG にまとめる。

- Sbfine/Sbfine2/Sbfine3 (3-run mean) を x=0 に参照点として各 ub でプロット（星型 marker）
- S1..S52 (5-run mean) を x=1..52 に折れ線 + 丸 marker でプロット
- 崩壊閾値 eval_mean=15.0 を水平線で表示
- S1..S52 に対する線形回帰直線（trend line）を各 ub ごとに dashed で重ねる
"""
from __future__ import annotations

import csv
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SCRIPT_DIR = Path(__file__).resolve().parent
ATTACH = SCRIPT_DIR.parent
OUT_PNG = SCRIPT_DIR / "timeseries_eval_tps.png"

UBS = [1584, 1586, 1664]
COLORS = {1584: "#1f77b4", 1586: "#2ca02c", 1664: "#d62728"}

# Sbfine 系 3 レポート (3-run、各 ub 1 点のみ)
SBFINE_TSV = {
    1584: (
        ATTACH / "2026-04-19_172104_qwen3-122b-c3-phaseSbfine2-ub16tok" / "results.tsv",
        "Sbf2_f16_fa1_ctx32768_b1584_ub1584_1k",
    ),
    1586: (
        ATTACH / "2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok" / "results.tsv",
        "Sbf3_f16_fa1_ctx32768_b1586_ub1586_1k",
    ),
    1664: (
        ATTACH / "2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary" / "results.tsv",
        "Sbf_f16_fa1_ctx32768_b1664_ub1664_1k",
    ),
}

# S1..S51 summary TSV path (phase=eval のみ抽出) + S52 (本 Phase)
S_EVAL_DIRS = [
    ("S1", "2026-04-20_003250_qwen3-122b-c3-phaseSeval", "summary_phaseSeval.tsv"),
    ("S2", "2026-04-20_013006_qwen3-122b-c3-phaseSevalcross", "summary_phaseSevalcross.tsv"),
    ("S3", "2026-04-20_022922_qwen3-122b-c3-phaseSeval3s", "summary_phaseSeval3s.tsv"),
    ("S4", "2026-04-20_032317_qwen3-122b-c3-phaseSeval4s", "summary_phaseSeval4s.tsv"),
    ("S5", "2026-04-20_041308_qwen3-122b-c3-phaseSeval5s", "summary_phaseSeval5s.tsv"),
    ("S6", "2026-04-20_050710_qwen3-122b-c3-phaseSeval6s", "summary_phaseSeval6s.tsv"),
    ("S7", "2026-04-20_061007_qwen3-122b-c3-phaseSeval7s", "summary_phaseSeval7s.tsv"),
    ("S8", "2026-04-20_075044_qwen3-122b-c3-phaseSeval8s", "summary_phaseSeval8s.tsv"),
    ("S9", "2026-04-20_080258_qwen3-122b-c3-phaseSeval9s", "summary_phaseSeval9s.tsv"),
    ("S10", "2026-04-20_085556_qwen3-122b-c3-phaseSeval10s", "summary_phaseSeval10s.tsv"),
    ("S11", "2026-04-20_094934_qwen3-122b-c3-phaseSeval11s", "summary_phaseSeval11s.tsv"),
    ("S12", "2026-04-20_104503_qwen3-122b-c3-phaseSeval12s", "summary_phaseSeval12s.tsv"),
    ("S13", "2026-04-20_113929_qwen3-122b-c3-phaseSeval13s", "summary_phaseSeval13s.tsv"),
    ("S14", "2026-04-20_123152_qwen3-122b-c3-phaseSeval14s", "summary_phaseSeval14s.tsv"),
    ("S15", "2026-04-20_132400_qwen3-122b-c3-phaseSeval15s", "summary_phaseSeval15s.tsv"),
    ("S16", "2026-04-20_142019_qwen3-122b-c3-phaseSeval16s", "summary_phaseSeval16s.tsv"),
    ("S17", "2026-04-20_151741_qwen3-122b-c3-phaseSeval17s", "summary_phaseSeval17s.tsv"),
    ("S18", "2026-04-20_161642_qwen3-122b-c3-phaseSeval18s", "summary_phaseSeval18s.tsv"),
    ("S19", "2026-04-20_212313_qwen3-122b-c3-phaseSeval19s", "summary_phaseSeval19s.tsv"),
    ("S20", "2026-04-20_222307_qwen3-122b-c3-phaseSeval20s", "summary_phaseSeval20s.tsv"),
    ("S21", "2026-04-20_232604_qwen3-122b-c3-phaseSeval21s", "summary_phaseSeval21s.tsv"),
    ("S22", "2026-04-21_002703_qwen3-122b-c3-phaseSeval22s", "summary_phaseSeval22s.tsv"),
    ("S23", "2026-04-21_012929_qwen3-122b-c3-phaseSeval23s", "summary_phaseSeval23s.tsv"),
    ("S24", "2026-04-21_023213_qwen3-122b-c3-phaseSeval24s", "summary_phaseSeval24s.tsv"),
    ("S25", "2026-04-21_032417_qwen3-122b-c3-phaseSeval25s", "summary_phaseSeval25s.tsv"),
    ("S26", "2026-04-21_041752_qwen3-122b-c3-phaseSeval26s", "summary_phaseSeval26s.tsv"),
    ("S27", "2026-04-21_051039_qwen3-122b-c3-phaseSeval27s", "summary_phaseSeval27s.tsv"),
    ("S28", "2026-04-21_060329_qwen3-122b-c3-phaseSeval28s", "summary_phaseSeval28s.tsv"),
    ("S29", "2026-04-21_065614_qwen3-122b-c3-phaseSeval29s", "summary_phaseSeval29s.tsv"),
    ("S30", "2026-04-21_074512_qwen3-122b-c3-phaseSeval30s", "summary_phaseSeval30s.tsv"),
    ("S31", "2026-04-21_083727_qwen3-122b-c3-phaseSeval31s", "summary_phaseSeval31s.tsv"),
    ("S32", "2026-04-21_093107_qwen3-122b-c3-phaseSeval32s", "summary_phaseSeval32s.tsv"),
    ("S33", "2026-04-21_102734_qwen3-122b-c3-phaseSeval33s", "summary_phaseSeval33s.tsv"),
    ("S34", "2026-04-21_112228_qwen3-122b-c3-phaseSeval34s", "summary_phaseSeval34s.tsv"),
    ("S35", "2026-04-21_121546_qwen3-122b-c3-phaseSeval35s", "summary_phaseSeval35s.tsv"),
    ("S36", "2026-04-21_130908_qwen3-122b-c3-phaseSeval36s", "summary_phaseSeval36s.tsv"),
    ("S37", "2026-04-21_140342_qwen3-122b-c3-phaseSeval37s", "summary_phaseSeval37s.tsv"),
    ("S38", "2026-04-21_145730_qwen3-122b-c3-phaseSeval38s", "summary_phaseSeval38s.tsv"),
    ("S39", "2026-04-21_155525_qwen3-122b-c3-phaseSeval39s", "summary_phaseSeval39s.tsv"),
    ("S40", "2026-04-21_164936_qwen3-122b-c3-phaseSeval40s", "summary_phaseSeval40s.tsv"),
    ("S41", "2026-04-21_174520_qwen3-122b-c3-phaseSeval41s", "summary_phaseSeval41s.tsv"),
    ("S42", "2026-04-21_184122_qwen3-122b-c3-phaseSeval42s", "summary_phaseSeval42s.tsv"),
    ("S43", "2026-04-21_194635_qwen3-122b-c3-phaseSeval43s", "summary_phaseSeval43s.tsv"),
    ("S44", "2026-04-21_214018_qwen3-122b-c3-phaseSeval44s", "summary_phaseSeval44s.tsv"),
    ("S45", "2026-04-21_224532_qwen3-122b-c3-phaseSeval45s", "summary_phaseSeval45s.tsv"),
    ("S46", "2026-04-21_234926_qwen3-122b-c3-phaseSeval46s", "summary_phaseSeval46s.tsv"),
    ("S47", "2026-04-22_005619_qwen3-122b-c3-phaseSeval47s", "summary_phaseSeval47s.tsv"),
    ("S48", "2026-04-22_010836_qwen3-122b-c3-phaseSeval48s", "summary_phaseSeval48s.tsv"),
    ("S49", "2026-04-22_020513_qwen3-122b-c3-phaseSeval49s", "summary_phaseSeval49s.tsv"),
    ("S50", "2026-04-22_025948_qwen3-122b-c3-phaseSeval50s", "summary_phaseSeval50s.tsv"),
    ("S51", "2026-04-22_035441_qwen3-122b-c3-phaseSeval51s", "summary_phaseSeval51s.tsv"),
    ("S52", None, "summary_phaseSeval52s.tsv"),  # 本 Phase、SCRIPT_DIR/summary_phaseSeval52s.tsv
]


def mean_from_sbfine(tsv_path: Path, tag: str) -> float | None:
    if not tsv_path.exists():
        return None
    vs: list[float] = []
    with tsv_path.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if row.get("tag") == tag:
                try:
                    vs.append(float(row["eval_tps"]))
                except (KeyError, ValueError):
                    pass
    return statistics.mean(vs) if vs else None


def mean_from_seval(tsv_path: Path, ub: int) -> float | None:
    if not tsv_path.exists():
        return None
    vs: list[float] = []
    with tsv_path.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            try:
                row_ub = int(row["ub"])
                row_phase = row.get("phase", "")
                if row_ub == ub and row_phase == "eval":
                    vs.append(float(row["eval_tps"]))
            except (KeyError, ValueError):
                pass
    return statistics.mean(vs) if vs else None


def linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(xs, ys))
    den = sum((xi - mean_x) ** 2 for xi in xs)
    if den == 0:
        return None
    slope = num / den
    intercept = mean_y - slope * mean_x
    return slope, intercept


def main() -> int:
    labels: list[str] = ["Sbfine"]
    means: dict[int, list[float | None]] = {ub: [] for ub in UBS}

    # S0 = Sbfine 3-run mean（各 ub で該当レポートから）
    for ub in UBS:
        tsv_path, tag = SBFINE_TSV[ub]
        m = mean_from_sbfine(tsv_path, tag)
        means[ub].append(m)

    # S1..S52
    for label, dirname, tsv_name in S_EVAL_DIRS:
        labels.append(label)
        if dirname is None:
            tsv_path = SCRIPT_DIR / tsv_name
        else:
            tsv_path = ATTACH / dirname / tsv_name
        for ub in UBS:
            m = mean_from_seval(tsv_path, ub)
            means[ub].append(m)

    x = list(range(len(labels)))

    fig, ax = plt.subplots(figsize=(16, 7))
    for ub in UBS:
        ys = means[ub]
        # S1..S52 (x=1..51) は folded line
        xs_line = [xi for xi, y in zip(x[1:], ys[1:]) if y is not None]
        ys_line = [y for y in ys[1:] if y is not None]
        ax.plot(
            xs_line, ys_line,
            marker="o", markersize=5,
            color=COLORS[ub], linewidth=1.5,
            label=f"ub={ub} (S-eval 5-run mean)",
        )
        # 回帰直線 (S1..S52 only、Sbfine ref は除外)
        fit = linear_fit([float(xi) for xi in xs_line], ys_line)
        if fit is not None:
            slope, intercept = fit
            xs_fit = [xs_line[0], xs_line[-1]]
            ys_fit = [slope * xi + intercept for xi in xs_fit]
            ax.plot(
                xs_fit, ys_fit,
                linestyle="--", linewidth=1.2,
                color=COLORS[ub], alpha=0.55,
                label=f"ub={ub} trend (slope={slope:+.4f} t/s per session)",
            )
        # S0 (Sbfine) は ★ marker
        if ys[0] is not None:
            ax.plot(
                [x[0]], [ys[0]],
                marker="*", markersize=16,
                color=COLORS[ub], linestyle="",
                markeredgecolor="black", markeredgewidth=0.8,
                label=f"ub={ub} (Sbfine 3-run ref)",
            )

    # 崩壊閾値
    ax.axhline(15.0, color="gray", linestyle="--", linewidth=0.8, alpha=0.7)
    ax.text(len(labels) - 1, 15.005, "COLLAPSE threshold (eval_mean < 15.0)",
            fontsize=8, color="gray", ha="right", va="bottom")

    # ub=1664 band 境界 (>15.20 上帯 / 14.80-15.20 中帯 / <14.80 下帯)
    ax.axhline(15.20, color="#d62728", linestyle=":", linewidth=0.6, alpha=0.4)
    ax.axhline(14.80, color="#d62728", linestyle=":", linewidth=0.6, alpha=0.4)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=60, ha="right", fontsize=8)
    ax.set_xlabel("session")
    ax.set_ylabel("eval_tps (tokens/sec)")
    ax.set_title(
        "Phase S-eval 52-session + Sbfine 3-run ref (P100 t120h-p100, ctx=32768, fa=1, OT=MoE-only, prompt_1k)"
    )
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower left", fontsize=7, ncol=3)

    plt.tight_layout()
    plt.savefig(OUT_PNG, dpi=130)
    print(f"[plot] wrote {OUT_PNG}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main() or 0)
