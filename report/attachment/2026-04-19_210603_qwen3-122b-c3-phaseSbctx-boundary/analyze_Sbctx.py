#!/usr/bin/env python3
"""Phase Sb-ctx-boundary 分析スクリプト.

入力:  startup_logs/fa1_ctx<C>_ub<U>.log (9 条件)
出力:
  - summary_Sbctx.tsv   : 9 行 × [ctx, ub, cuda0_MiB, cuda1_MiB, cuda2_MiB, cuda3_MiB, host_MiB, nodes, splits_pp, splits_tg]
  - Sbctx_pivot.csv     : ctx × ub の CUDA0 MiB ピボット (3x3)
  - Sbctx_slopes.csv    : 各 ctx の Δ(1584→1585), Δ(1585→1586), step 位置
  - Sbctx_verdict.txt   : 候補 J (ctx 非依存性) の支持/棄却判定

判定基準 (決定論的、1 run のため統計検定不可):
  - 全 3 ctx で |Δ(1584→1585)| ≤ 0.05 MiB  (平坦域)
  - 全 3 ctx で Δ(1585→1586) ≥ 0.15 MiB   (step)
  - 全 3 ctx で Δ(1585→1586) / max(|Δ(1584→1585)|, 1e-6) ≥ 5
  - 全 3 ctx で peak_ub (argmax Δ) = 1586
"""

from __future__ import annotations

import csv
import glob
import os
import re
import sys
from pathlib import Path

CTXS = [16384, 65536, 131072]
UBS = [1584, 1585, 1586]

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = SCRIPT_DIR / "startup_logs"

# 判定基準
PRE_MAX = 0.05
STEP_MIN = 0.15
RATIO_MIN = 5.0


def parse_log(path: Path) -> dict[str, float | int | None]:
    """sched_reserve ブロックから主要値を抽出."""
    m = re.match(r"fa\d+_ctx(\d+)_ub(\d+)\.log$", path.name)
    if not m:
        return {}
    ctx, ub = int(m.group(1)), int(m.group(2))
    out: dict[str, float | int | None] = {"ctx": ctx, "ub": ub}
    text = path.read_text()

    patterns = {
        "cuda0_MiB": r"CUDA0 compute buffer size\s*=\s*([\d.]+)\s*MiB",
        "cuda1_MiB": r"CUDA1 compute buffer size\s*=\s*([\d.]+)\s*MiB",
        "cuda2_MiB": r"CUDA2 compute buffer size\s*=\s*([\d.]+)\s*MiB",
        "cuda3_MiB": r"CUDA3 compute buffer size\s*=\s*([\d.]+)\s*MiB",
        "host_MiB": r"CUDA_Host\s+compute buffer size\s*=\s*([\d.]+)\s*MiB",
    }
    for key, pat in patterns.items():
        mm = re.search(pat, text)
        out[key] = float(mm.group(1)) if mm else None

    mm = re.search(r"graph nodes\s*=\s*(\d+)", text)
    out["nodes"] = int(mm.group(1)) if mm else None

    mm = re.search(r"graph splits\s*=\s*(\d+)\s*\(with bs=\d+\)\s*,\s*(\d+)\s*\(with bs=1\)", text)
    if mm:
        out["splits_pp"] = int(mm.group(1))
        out["splits_tg"] = int(mm.group(2))
    else:
        out["splits_pp"] = None
        out["splits_tg"] = None
    return out


def main() -> int:
    logs = sorted(glob.glob(str(LOG_DIR / "fa1_ctx*_ub*.log")))
    rows = [parse_log(Path(p)) for p in logs]
    rows = [r for r in rows if r and r.get("cuda0_MiB") is not None]

    if not rows:
        print("ERROR: no valid startup logs", file=sys.stderr)
        return 1

    cols = [
        "ctx",
        "ub",
        "cuda0_MiB",
        "cuda1_MiB",
        "cuda2_MiB",
        "cuda3_MiB",
        "host_MiB",
        "nodes",
        "splits_pp",
        "splits_tg",
    ]
    with open(SCRIPT_DIR / "summary_Sbctx.tsv", "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(cols)
        for r in sorted(rows, key=lambda x: (x["ctx"], x["ub"])):
            w.writerow([r.get(c) for c in cols])

    # Pivot: ctx × ub の CUDA0 MiB
    pivot: dict[int, dict[int, float | None]] = {c: {u: None for u in UBS} for c in CTXS}
    for r in rows:
        if r["ctx"] in pivot and r["ub"] in pivot[r["ctx"]]:
            pivot[r["ctx"]][r["ub"]] = r["cuda0_MiB"]

    with open(SCRIPT_DIR / "Sbctx_pivot.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ctx", *[f"ub={u}" for u in UBS]])
        for c in CTXS:
            w.writerow([c, *[pivot[c][u] for u in UBS]])

    # Slopes per ctx
    slopes: list[dict[str, float | int]] = []
    for c in CTXS:
        v84, v85, v86 = pivot[c][1584], pivot[c][1585], pivot[c][1586]
        if None in (v84, v85, v86):
            continue
        d_pre = v85 - v84
        d_step = v86 - v85
        ratio = d_step / max(abs(d_pre), 1e-6)
        peak_ub = 1586 if d_step > d_pre else 1585
        slopes.append(
            {
                "ctx": c,
                "cuda0_ub1584": v84,
                "cuda0_ub1585": v85,
                "cuda0_ub1586": v86,
                "delta_1584_1585": round(d_pre, 4),
                "delta_1585_1586": round(d_step, 4),
                "ratio_step_over_pre": round(ratio, 2),
                "peak_ub": peak_ub,
            }
        )

    with open(SCRIPT_DIR / "Sbctx_slopes.csv", "w", newline="") as f:
        if slopes:
            w = csv.DictWriter(f, fieldnames=list(slopes[0].keys()))
            w.writeheader()
            for row in slopes:
                w.writerow(row)

    # Verdict
    all_pre_ok = all(abs(s["delta_1584_1585"]) <= PRE_MAX for s in slopes)
    all_step_ok = all(s["delta_1585_1586"] >= STEP_MIN for s in slopes)
    all_ratio_ok = all(s["ratio_step_over_pre"] >= RATIO_MIN for s in slopes)
    all_peak_1586 = all(s["peak_ub"] == 1586 for s in slopes)
    n_ok_ctx = len(slopes)

    nodes_vals = {r["nodes"] for r in rows if r["nodes"] is not None}
    splits_vals = {(r["splits_pp"], r["splits_tg"]) for r in rows if r["splits_pp"] is not None}

    verdict_support = all_pre_ok and all_step_ok and all_ratio_ok and all_peak_1586 and n_ok_ctx == 3

    with open(SCRIPT_DIR / "Sbctx_verdict.txt", "w") as f:
        f.write("# Phase Sb-ctx-boundary 判定結果\n\n")
        f.write(f"candidate_J_support: {verdict_support}\n")
        f.write(f"n_valid_ctx: {n_ok_ctx}/3\n")
        f.write(f"all_pre_delta_within_{PRE_MAX}: {all_pre_ok}\n")
        f.write(f"all_step_delta_above_{STEP_MIN}: {all_step_ok}\n")
        f.write(f"all_ratio_above_{RATIO_MIN}: {all_ratio_ok}\n")
        f.write(f"all_peak_ub_equal_1586: {all_peak_1586}\n")
        f.write(f"peak_ub_per_ctx: {dict((s['ctx'], s['peak_ub']) for s in slopes)}\n")
        f.write(f"unique_nodes_values: {sorted(nodes_vals)}\n")
        f.write(f"unique_splits_values: {sorted(splits_vals)}\n")
        f.write("\n## CUDA0 compute buffer MiB (pivot)\n")
        f.write(f"{'ctx':>10}" + "".join(f"{'ub=' + str(u):>14}" for u in UBS) + "\n")
        for c in CTXS:
            row = f"{c:>10}"
            for u in UBS:
                v = pivot[c][u]
                row += f"{v:>14.4f}" if v is not None else f"{'NA':>14}"
            f.write(row + "\n")
        f.write("\n## slopes per ctx\n")
        for s in slopes:
            f.write(
                f"  ctx={s['ctx']:>6}: Δ(1584→1585)={s['delta_1584_1585']:+.4f} MiB, "
                f"Δ(1585→1586)={s['delta_1585_1586']:+.4f} MiB, "
                f"ratio={s['ratio_step_over_pre']:.2f}, peak_ub={s['peak_ub']}\n"
            )

    print(f"Analysis complete. candidate_J_support={verdict_support}")
    print(f"See: {SCRIPT_DIR / 'Sbctx_verdict.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
