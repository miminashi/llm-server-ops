#!/usr/bin/env python3
"""analyze_phaseU5.py - Phase U-5 結果 CSV から ts 別ヒートマップ + summary.md を生成"""
import csv
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

SCRIPT_DIR = Path(__file__).parent
CSV_PATH = SCRIPT_DIR / "phaseU5_results.csv"

OT_ORDER = ["B14b", "B16", "B18", "B20", "B24"]
CTX_ORDER = [32768, 65536, 98304, 131072]

def load():
    rows = []
    with CSV_PATH.open() as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows

def to_int(s, default=None):
    try:
        return int(s)
    except (ValueError, TypeError):
        return default

def heatmap_for_ts(rows, ts_value, outpath):
    matrix = np.full((len(OT_ORDER), len(CTX_ORDER)), np.nan)
    err_matrix = [["" for _ in CTX_ORDER] for _ in OT_ORDER]

    for r in rows:
        if r["ts"] != ts_value:
            continue
        ot = r["OT_name"]
        ctx = to_int(r["ctx"])
        if ot not in OT_ORDER or ctx not in CTX_ORDER:
            continue
        i = OT_ORDER.index(ot)
        j = CTX_ORDER.index(ctx)
        fit = r["fit"] == "1"
        if fit:
            min_after = to_int(r["min_GPU_free_after_probe_MiB"], default=-1)
            matrix[i, j] = min_after
        else:
            err_matrix[i][j] = r["error_class"]

    fig, ax = plt.subplots(figsize=(8, 5))
    cmap = plt.cm.YlGn.copy()
    cmap.set_bad(color="lightgray")
    masked = np.ma.masked_invalid(matrix)
    im = ax.imshow(masked, cmap=cmap, vmin=0, vmax=6000, aspect="auto")

    ax.set_xticks(range(len(CTX_ORDER)))
    ax.set_xticklabels([f"{c//1024}k" for c in CTX_ORDER])
    ax.set_yticks(range(len(OT_ORDER)))
    ax.set_yticklabels(OT_ORDER)
    ax.set_xlabel("ctx")
    ax.set_ylabel("OT tag")
    ax.set_title(f"Phase U-5 fit map: ts={ts_value}\n(cell value = min GPU free after probe [MiB])")

    for i in range(len(OT_ORDER)):
        for j in range(len(CTX_ORDER)):
            v = matrix[i, j]
            if not np.isnan(v):
                txt = f"{int(v)}"
                color = "black" if v > 2000 else "white"
            else:
                err = err_matrix[i][j]
                if err:
                    txt = err
                else:
                    txt = "—"
                color = "black"
            ax.text(j, i, txt, ha="center", va="center", color=color, fontsize=9)

    plt.colorbar(im, ax=ax, label="min GPU free MiB")
    plt.tight_layout()
    fig.savefig(outpath, dpi=120)
    plt.close(fig)
    print(f"[analyze] wrote {outpath}")

def summary_md(rows, outpath):
    lines = []
    lines.append("# Phase U-5 結果サマリ")
    lines.append("")
    lines.append(f"- 総条件数: {len(rows)}")
    fits = [r for r in rows if r["fit"] == "1"]
    lines.append(f"- fit 条件数: {len(fits)}")
    fits_128k = [r for r in fits if to_int(r["ctx"]) == 131072]
    fits_96k = [r for r in fits if to_int(r["ctx"]) == 98304]
    lines.append(f"- ctx=131072 fit: {len(fits_128k)}")
    lines.append(f"- ctx=98304 fit: {len(fits_96k)}")
    lines.append("")

    lines.append("## ctx=131072 fit 構成 (推奨度スコア順)")
    lines.append("")
    lines.append("score = (B14b なら +1000) + min_GPU_free_after_probe_MiB − (ts 非標準なら 100)")
    lines.append("")
    def score(r):
        s = to_int(r["min_GPU_free_after_probe_MiB"], default=0)
        if r["OT_name"] == "B14b":
            s += 1000
        if r["ts"] not in ("11-12-13-14", "default"):
            s -= 100
        return s

    fits_128k_sorted = sorted(fits_128k, key=score, reverse=True)
    if fits_128k_sorted:
        lines.append("| rank | cond_id | OT | CPU | ts | min_static (MiB) | min_after (MiB) | score |")
        lines.append("|------|---------|----|----|-----|-----------------|-----------------|-------|")
        for rk, r in enumerate(fits_128k_sorted, 1):
            lines.append(f"| {rk} | {r['condition_id']} | {r['OT_name']} | {r['CPU_layers']} | {r['ts']} | {r['min_GPU_free_static_MiB']} | {r['min_GPU_free_after_probe_MiB']} | {score(r)} |")
    else:
        lines.append("**ctx=131072 fit 構成なし**")
        lines.append("")
        lines.append("## ctx=98304 fit 構成 (fallback、推奨度スコア順)")
        lines.append("")
        fits_96k_sorted = sorted(fits_96k, key=score, reverse=True)
        if fits_96k_sorted:
            lines.append("| rank | cond_id | OT | CPU | ts | min_static (MiB) | min_after (MiB) | score |")
            lines.append("|------|---------|----|----|-----|-----------------|-----------------|-------|")
            for rk, r in enumerate(fits_96k_sorted, 1):
                lines.append(f"| {rk} | {r['condition_id']} | {r['OT_name']} | {r['CPU_layers']} | {r['ts']} | {r['min_GPU_free_static_MiB']} | {r['min_GPU_free_after_probe_MiB']} | {score(r)} |")
        else:
            lines.append("**ctx=98304 fit 構成も無し**")
    lines.append("")

    lines.append("## 全条件詳細")
    lines.append("")
    lines.append("| cond | OT | CPU | ctx | ts | fit | startup(s) | min_static | min_after | error |")
    lines.append("|------|----|----|-----|----|-----|-----------|-----------|-----------|-------|")
    for r in rows:
        lines.append(f"| {r['condition_id']} | {r['OT_name']} | {r['CPU_layers']} | {r['ctx']} | {r['ts']} | {r['fit']} | {r['startup_sec']} | {r['min_GPU_free_static_MiB']} | {r['min_GPU_free_after_probe_MiB']} | {r['error_class']} |")

    with open(outpath, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[analyze] wrote {outpath}")

def main():
    rows = load()
    ts_values = sorted({r["ts"] for r in rows})
    for ts in ts_values:
        out = SCRIPT_DIR / f"phaseU5_heatmap_ts{ts}.png"
        heatmap_for_ts(rows, ts, out)
    summary_md(rows, SCRIPT_DIR / "phaseU5_summary.md")

if __name__ == "__main__":
    main()
