#!/usr/bin/env python3
"""Phase Sb-fa0 (拡張版) 分析スクリプト.

入力:  startup_logs/fa0_ctx<C>_ub<U>.log (12 条件)
出力:
  - summary_Sbfa0.tsv            : 12 行 × [ctx, ub, cuda0_MiB, cuda1_MiB, cuda2_MiB, cuda3_MiB, host_MiB, nodes, splits_pp, splits_tg]
  - Sbfa0_pivot.csv              : ctx × ub の CUDA0 MiB ピボット (4x3)
  - Sbfa0_slopes.csv             : 各 ctx の Δ(1584→1585), Δ(1585→1586), step 位置
  - Sbfa0_verdict.txt            : Phase Sbctx 互換の拡張 verdict
  - Sbfa0_candidate_K_verdict.txt: 候補 K (FA workspace cross 項) の support/partial/reject 3 値判定 + fa=1 対比表

候補 K 支持条件 (3 つ、fa=1 前 Phase との対比):
  1. slope 縮小:     全 ctx × 両 Δ で ≤ SLOPE_MAX_K (0.05 MiB/ub)
  2. ctx 非依存化:   全 8 値 (4 ctx × 2 Δ) の max/min ≤ SLOPE_RATIO_K (2.0)
  3. δ 項消失:       ctx=32k で |Δ(1585→1586)| ≤ DELTA_32K_UB1586_MAX (0.05 MiB)

3/3 → support、1-2/3 → partial_support、0/3 → reject
"""

from __future__ import annotations

import csv
import glob
import re
import sys
from pathlib import Path

CTXS = [16384, 32768, 65536, 131072]
UBS = [1584, 1585, 1586]

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = SCRIPT_DIR / "startup_logs"

# 候補 K 判定基準
SLOPE_MAX_K = 0.05          # 全 ctx × 両 Δ で slope ≤ 0.05 MiB/ub (fa=1 ctx=16k レベル)
SLOPE_RATIO_K = 2.0         # max/min slope ≤ 2.0 (ctx 非依存)
DELTA_32K_UB1586_MAX = 0.05 # ctx=32k で |Δ(1585→1586)| ≤ 0.05 (δ 消失)

# fa=1 (Phase Sbctx) 実測 slope (対比表用、ハードコード)
#   Sbctx_slopes.csv より: delta_1584_1585 / delta_1585_1586
#   ctx=32768 は fa=1 Sbf3 既存値 (Δ(1585→1586)=+0.24, Δ(1584→1585) 不明 → NA)
FA1_DELTAS: dict[int, dict[str, float | None]] = {
    16384:  {"d_pre": 0.01,  "d_step": 0.01},
    32768:  {"d_pre": None,  "d_step": 0.24},  # Sbf3 既存、ub=1584 未測定
    65536:  {"d_pre": 0.40,  "d_step": 0.40},
    131072: {"d_pre": 0.65,  "d_step": 0.65},
}


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
    logs = sorted(glob.glob(str(LOG_DIR / "fa0_ctx*_ub*.log")))
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
    with open(SCRIPT_DIR / "summary_Sbfa0.tsv", "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(cols)
        for r in sorted(rows, key=lambda x: (x["ctx"], x["ub"])):
            w.writerow([r.get(c) for c in cols])

    # Pivot: ctx × ub の CUDA0 MiB
    pivot: dict[int, dict[int, float | None]] = {c: {u: None for u in UBS} for c in CTXS}
    for r in rows:
        if r["ctx"] in pivot and r["ub"] in pivot[r["ctx"]]:
            pivot[r["ctx"]][r["ub"]] = r["cuda0_MiB"]

    with open(SCRIPT_DIR / "Sbfa0_pivot.csv", "w", newline="") as f:
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

    with open(SCRIPT_DIR / "Sbfa0_slopes.csv", "w", newline="") as f:
        if slopes:
            w = csv.DictWriter(f, fieldnames=list(slopes[0].keys()))
            w.writeheader()
            for row in slopes:
                w.writerow(row)

    nodes_vals = {r["nodes"] for r in rows if r["nodes"] is not None}
    splits_vals = {(r["splits_pp"], r["splits_tg"]) for r in rows if r["splits_pp"] is not None}
    n_ok_ctx = len(slopes)

    # Sbfa0_verdict.txt (Sbctx 互換の拡張 verdict)
    # candidate_J を再評価する意義は薄いが、参考値として出力
    PRE_MAX = 0.05
    STEP_MIN = 0.15
    RATIO_MIN = 5.0
    all_pre_ok = all(abs(s["delta_1584_1585"]) <= PRE_MAX for s in slopes)
    all_step_ok = all(s["delta_1585_1586"] >= STEP_MIN for s in slopes)
    all_ratio_ok = all(s["ratio_step_over_pre"] >= RATIO_MIN for s in slopes)
    all_peak_1586 = all(s["peak_ub"] == 1586 for s in slopes)
    verdict_J = all_pre_ok and all_step_ok and all_ratio_ok and all_peak_1586 and n_ok_ctx == 4

    with open(SCRIPT_DIR / "Sbfa0_verdict.txt", "w") as f:
        f.write("# Phase Sb-fa0 判定結果 (Sbctx 互換形式)\n\n")
        f.write(f"candidate_J_support_reeval_fa0: {verdict_J}\n")
        f.write(f"n_valid_ctx: {n_ok_ctx}/4\n")
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
        f.write("\n## slopes per ctx (fa=0)\n")
        for s in slopes:
            f.write(
                f"  ctx={s['ctx']:>6}: Δ(1584→1585)={s['delta_1584_1585']:+.4f} MiB, "
                f"Δ(1585→1586)={s['delta_1585_1586']:+.4f} MiB, "
                f"ratio={s['ratio_step_over_pre']:.2f}, peak_ub={s['peak_ub']}\n"
            )

    # Sbfa0_candidate_K_verdict.txt (候補 K 3 条件判定)
    all_slopes_list: list[float] = []
    for s in slopes:
        all_slopes_list.append(abs(s["delta_1584_1585"]))
        all_slopes_list.append(abs(s["delta_1585_1586"]))

    cond1_slope_max_ok = all(v <= SLOPE_MAX_K for v in all_slopes_list) if all_slopes_list else False

    if all_slopes_list:
        mx = max(all_slopes_list)
        mn = min(all_slopes_list)
        # min が 0 に近い場合は max が充分小さければ ratio 問題にしない
        if mn < 1e-4:
            cond2_ctx_indep_ok = mx <= SLOPE_MAX_K  # 全値が絶対値で小さいなら OK
        else:
            cond2_ctx_indep_ok = (mx / mn) <= SLOPE_RATIO_K
    else:
        cond2_ctx_indep_ok = False

    s32k = next((s for s in slopes if s["ctx"] == 32768), None)
    if s32k is not None:
        cond3_delta_32k_ok = abs(s32k["delta_1585_1586"]) <= DELTA_32K_UB1586_MAX
    else:
        cond3_delta_32k_ok = False

    conds_passed = int(cond1_slope_max_ok) + int(cond2_ctx_indep_ok) + int(cond3_delta_32k_ok)
    if conds_passed == 3:
        status = "support"
    elif conds_passed >= 1:
        status = "partial_support"
    else:
        status = "reject"

    with open(SCRIPT_DIR / "Sbfa0_candidate_K_verdict.txt", "w") as f:
        f.write("# Phase Sb-fa0 候補 K (FA/attention workspace の ub×ctx cross 項) 判定結果\n\n")
        f.write(f"candidate_K_status: {status}\n")
        f.write(f"conds_passed: {conds_passed}/3\n")
        f.write(f"cond1_all_slope_within_{SLOPE_MAX_K}_MiB: {cond1_slope_max_ok}\n")
        f.write(f"cond2_slope_ctx_independent_ratio_under_{SLOPE_RATIO_K}: {cond2_ctx_indep_ok}\n")
        f.write(f"cond3_delta_ctx32k_ub1586_within_{DELTA_32K_UB1586_MAX}_MiB: {cond3_delta_32k_ok}\n")
        f.write(f"n_valid_ctx: {n_ok_ctx}/4\n")

        f.write("\n## fa=1 (Phase Sbctx) vs fa=0 (本 Phase) slope 対比\n")
        f.write(
            f"{'ctx':>8}  "
            f"{'fa1_d_pre':>11}  {'fa1_d_step':>11}  "
            f"{'fa0_d_pre':>11}  {'fa0_d_step':>11}  "
            f"{'ratio_pre':>11}  {'ratio_step':>11}\n"
        )
        fa0_by_ctx = {s["ctx"]: s for s in slopes}
        for c in CTXS:
            fa1 = FA1_DELTAS.get(c, {})
            fa0 = fa0_by_ctx.get(c)
            fa1_pre = fa1.get("d_pre")
            fa1_step = fa1.get("d_step")
            fa0_pre = fa0["delta_1584_1585"] if fa0 else None
            fa0_step = fa0["delta_1585_1586"] if fa0 else None

            def fmt(v: float | None) -> str:
                return f"{v:+.4f}" if v is not None else "   NA   "

            def ratio(a: float | None, b: float | None) -> str:
                if a is None or b is None or abs(b) < 1e-6:
                    return "   NA   "
                return f"{a / b:+.2f}"

            f.write(
                f"{c:>8}  "
                f"{fmt(fa1_pre):>11}  {fmt(fa1_step):>11}  "
                f"{fmt(fa0_pre):>11}  {fmt(fa0_step):>11}  "
                f"{ratio(fa1_pre, fa0_pre):>11}  {ratio(fa1_step, fa0_step):>11}\n"
            )

        f.write("\n## 解釈ガイド\n")
        f.write("- cond1 (slope 縮小): fa=1 で ctx=65k→0.40, ctx=131k→0.65 MiB/ub の大きな slope が全 ctx で 0.05 未満に縮小していれば FA workspace が主因\n")
        f.write("- cond2 (ctx 非依存化): fa=0 で slope が ctx に依存しなくなれば cross 項は FA 起源\n")
        f.write("- cond3 (δ 消失): fa=0 で ctx=32k の +0.24 MiB step が消えれば FA による量子化 step\n")
        f.write("- support (3/3): 候補 K 成立 → 次 Phase で FA kernel / workspace の詳細 dump\n")
        f.write("- partial_support (1-2/3): FA 部分寄与 → I-c (build_graph 離散) との複合モデル要\n")
        f.write("- reject (0/3): FA 無関係 → 新候補 L/M の設計要 (例: KV cache 参照 workspace、SSM 以外の層)\n")

    print(f"Analysis complete. candidate_K_status={status} ({conds_passed}/3)")
    print(f"See: {SCRIPT_DIR / 'Sbfa0_candidate_K_verdict.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
