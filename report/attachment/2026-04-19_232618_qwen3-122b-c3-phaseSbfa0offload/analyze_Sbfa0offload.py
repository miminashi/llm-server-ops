#!/usr/bin/env python3
"""Phase Sb-fa0-offload 分析スクリプト.

入力:
  - startup_logs/fa0offload_<TAG>_ctx<C>_ub<U>.log
  - batch_Sbfa0offload_oom.tsv (OOM alloc size 派生データ)
  - summary_state.txt (FINAL_OT_TAG 等)

出力:
  - summary_Sbfa0offload.tsv
  - Sbfa0offload_pivot_<TAG>.csv
  - Sbfa0offload_slopes.csv
  - Sbfa0offload_verdict.txt (Sbfa0 互換)
  - Sbfa0offload_candidate_L_verdict.txt (候補 L: FA tile 量子化副作用判定)
  - Sbfa0offload_oom_slopes.csv (OOM 派生 slope)

候補 L 判定ルール:
  - δ_fa1(ctx=32k, ub=1586) = +0.24 MiB（ハードコード、Phase Sb-fa0 で既知）
  - δ_fa0(ctx=32k) = Δ(1585→1586) − Δ(1584→1585)
  - cond_L_1: |δ_fa0| ≤ DELTA_ABS_SMALL（0.10 MiB）→ δ 項は fa=1 固有
  - cond_L_2: |δ_fa0 − 0.24| ≤ DELTA_DIFF_TIGHT（0.05 MiB）→ δ は fa 共通
  - cond_L_3: slope_fa0(ctx=32k) / slope_fa0(ctx=16k) 比を記録（副次）
"""

from __future__ import annotations

import csv
import glob
import re
import sys
from collections import defaultdict
from pathlib import Path

CTXS = [16384, 32768, 65536, 131072]
UBS = [1584, 1585, 1586]

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = SCRIPT_DIR / "startup_logs"

DELTA_ABS_SMALL = 0.10
DELTA_DIFF_TIGHT = 0.05
DELTA_FA1_CTX32K = 0.24  # Phase Sb-ctx-boundary 実測 (fa=1)

# fa=1 (Phase Sbctx) 実測 slope（対比用、Sb-fa0 と同値）
FA1_DELTAS: dict[int, dict[str, float | None]] = {
    16384:  {"d_pre": 0.01,  "d_step": 0.01},
    32768:  {"d_pre": None,  "d_step": 0.24},
    65536:  {"d_pre": 0.40,  "d_step": 0.40},
    131072: {"d_pre": 0.65,  "d_step": 0.65},
}

# Phase Sb-fa0 実測値（現 OT = MoE のみ、fa=0 × ctx=16k）— Stage 4 の baseline 比較用
FA0_PREV_DELTAS_CTX16K = {"d_pre": 2.12, "d_step": 2.12}


def parse_log(path: Path) -> dict[str, float | int | str | None]:
    m = re.match(r"fa0offload_(?P<tag>\w+)_ctx(?P<ctx>\d+)_ub(?P<ub>\d+)\.log$", path.name)
    if not m:
        return {}
    ot_tag = m.group("tag")
    ctx = int(m.group("ctx"))
    ub = int(m.group("ub"))
    out: dict[str, float | int | str | None] = {
        "ot_tag": ot_tag,
        "ctx": ctx,
        "ub": ub,
    }
    try:
        text = path.read_text()
    except Exception:
        return out

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


def load_state() -> dict[str, str]:
    state: dict[str, str] = {}
    sf = SCRIPT_DIR / "summary_state.txt"
    if sf.exists():
        for line in sf.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                state[k.strip()] = v.strip()
    return state


def analyze_oom() -> list[dict]:
    oom_rows: list[dict] = []
    of = SCRIPT_DIR / "batch_Sbfa0offload_oom.tsv"
    if not of.exists():
        return oom_rows
    with open(of) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            try:
                oom_rows.append({
                    "tag": row.get("tag", ""),
                    "ctx": int(row.get("ctx", 0) or 0),
                    "ub": int(row.get("ub", 0) or 0),
                    "ot_tag": row.get("ot_tag", ""),
                    "device": int(row.get("device", 0) or 0),
                    "alloc_MiB": float(row.get("alloc_MiB", 0) or 0),
                })
            except (ValueError, TypeError):
                continue
    return oom_rows


def main() -> int:
    logs = sorted(glob.glob(str(LOG_DIR / "fa0offload_*.log")))
    rows = [parse_log(Path(p)) for p in logs]
    rows = [r for r in rows if r and r.get("cuda0_MiB") is not None]

    state = load_state()
    final_ot = state.get("FINAL_OT_TAG", "unknown")
    stage2_ctx = int(state.get("STAGE2_CTX", "32768") or "32768")

    # --- summary TSV ---
    cols = [
        "ot_tag", "ctx", "ub",
        "cuda0_MiB", "cuda1_MiB", "cuda2_MiB", "cuda3_MiB", "host_MiB",
        "nodes", "splits_pp", "splits_tg",
    ]
    with open(SCRIPT_DIR / "summary_Sbfa0offload.tsv", "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(cols)
        for r in sorted(rows, key=lambda x: (str(x.get("ot_tag", "")), x.get("ctx", 0), x.get("ub", 0))):
            w.writerow([r.get(c) for c in cols])

    # --- Pivot per OT_TAG ---
    by_tag: dict[str, dict[int, dict[int, float | None]]] = defaultdict(
        lambda: {c: {u: None for u in UBS} for c in CTXS}
    )
    for r in rows:
        tag = str(r.get("ot_tag", ""))
        c, u = r["ctx"], r["ub"]
        if c in by_tag[tag] and u in by_tag[tag][c]:
            by_tag[tag][c][u] = r["cuda0_MiB"]

    for tag, pivot in by_tag.items():
        with open(SCRIPT_DIR / f"Sbfa0offload_pivot_{tag}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ctx", *[f"ub={u}" for u in UBS]])
            for c in CTXS:
                w.writerow([c, *[pivot[c][u] for u in UBS]])

    # --- Slopes per (OT_TAG, ctx) ---
    slopes: list[dict] = []
    for tag, pivot in by_tag.items():
        for c in CTXS:
            v84, v85, v86 = pivot[c][1584], pivot[c][1585], pivot[c][1586]
            if None in (v84, v85, v86):
                continue
            d_pre = v85 - v84
            d_step = v86 - v85
            delta_of_delta = d_step - d_pre
            ratio = d_step / max(abs(d_pre), 1e-6)
            peak_ub = 1586 if d_step > d_pre else (1585 if d_pre > 0 else 1584)
            slopes.append({
                "ot_tag": tag,
                "ctx": c,
                "cuda0_ub1584": v84,
                "cuda0_ub1585": v85,
                "cuda0_ub1586": v86,
                "delta_1584_1585": round(d_pre, 4),
                "delta_1585_1586": round(d_step, 4),
                "delta_of_delta": round(delta_of_delta, 4),
                "ratio_step_over_pre": round(ratio, 2),
                "peak_ub": peak_ub,
            })

    if slopes:
        with open(SCRIPT_DIR / "Sbfa0offload_slopes.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(slopes[0].keys()))
            w.writeheader()
            for row in slopes:
                w.writerow(row)

    # --- Sbfa0offload_verdict.txt (Sbfa0 互換) ---
    with open(SCRIPT_DIR / "Sbfa0offload_verdict.txt", "w") as f:
        f.write("# Phase Sb-fa0-offload 判定結果 (Sbfa0 互換形式)\n\n")
        f.write(f"FINAL_OT_TAG: {final_ot}\n")
        f.write(f"STAGE2_CTX: {stage2_ctx}\n")
        f.write(f"n_valid_conditions: {len(rows)}\n")
        f.write(f"n_slope_rows: {len(slopes)}\n")
        f.write("\n## CUDA0 compute buffer MiB (pivot per OT_TAG)\n")
        for tag, pivot in by_tag.items():
            f.write(f"\n### OT_TAG={tag}\n")
            f.write(f"{'ctx':>10}" + "".join(f"{'ub=' + str(u):>14}" for u in UBS) + "\n")
            for c in CTXS:
                row = f"{c:>10}"
                for u in UBS:
                    v = pivot[c][u]
                    row += f"{v:>14.4f}" if v is not None else f"{'NA':>14}"
                f.write(row + "\n")

        f.write("\n## slopes per (OT_TAG, ctx) (fa=0-offload)\n")
        for s in slopes:
            f.write(
                f"  OT={s['ot_tag']:>4} ctx={s['ctx']:>6}: "
                f"Δ(1584→1585)={s['delta_1584_1585']:+.4f}, "
                f"Δ(1585→1586)={s['delta_1585_1586']:+.4f}, "
                f"δ_of_δ={s['delta_of_delta']:+.4f}, "
                f"peak_ub={s['peak_ub']}\n"
            )

    # --- Candidate L verdict ---
    # stage2_ctx で measure できた slope を基に δ_fa0 を算出
    s_stage2 = next(
        (s for s in slopes if s["ot_tag"] == final_ot and s["ctx"] == stage2_ctx),
        None,
    )

    cond1 = cond2 = cond3_recorded = False
    delta_fa0 = None
    ratio_stage2_over_16k = None

    if s_stage2 is not None:
        delta_fa0 = s_stage2["delta_of_delta"]
        cond1 = abs(delta_fa0) <= DELTA_ABS_SMALL
        cond2 = abs(delta_fa0 - DELTA_FA1_CTX32K) <= DELTA_DIFF_TIGHT
        # cond3: slope (Δ(1585→1586)) が ctx=16k の同 OT_TAG と比較で変化するか
        s_16k = next(
            (s for s in slopes if s["ot_tag"] == final_ot and s["ctx"] == 16384),
            None,
        )
        if s_16k is not None and abs(s_16k["delta_1585_1586"]) > 1e-4:
            ratio_stage2_over_16k = s_stage2["delta_1585_1586"] / s_16k["delta_1585_1586"]
            cond3_recorded = True

    # 判定ロジック:
    # - cond1 True & cond2 False → candidate_L support (δ fa 固有)
    # - cond1 False & cond2 True → candidate_L reject (δ fa 共通)
    # - それ以外 → partial / not_conclusive
    if s_stage2 is None:
        status = "not_conclusive"
    elif cond1 and not cond2:
        status = "support"
    elif cond2 and not cond1:
        status = "reject"
    elif cond1 and cond2:
        status = "ambiguous_both_cond_true"
    else:
        status = "partial_neither_cond_met"

    with open(SCRIPT_DIR / "Sbfa0offload_candidate_L_verdict.txt", "w") as f:
        f.write("# Phase Sb-fa0-offload 候補 L (FA tile 量子化副作用) 判定結果\n\n")
        f.write(f"candidate_L_status: {status}\n")
        f.write(f"FINAL_OT_TAG: {final_ot}\n")
        f.write(f"STAGE2_CTX: {stage2_ctx}\n")
        f.write(f"delta_fa1_reference_ctx32k_ub1586: +{DELTA_FA1_CTX32K:.4f} MiB\n")
        f.write(f"delta_fa0_measured_ctx{stage2_ctx}: "
                f"{delta_fa0:+.4f} MiB\n" if delta_fa0 is not None else "delta_fa0_measured: NA\n")
        f.write(f"cond_L_1 |delta_fa0| <= {DELTA_ABS_SMALL}: {cond1}\n")
        f.write(f"cond_L_2 |delta_fa0 - 0.24| <= {DELTA_DIFF_TIGHT}: {cond2}\n")
        if cond3_recorded:
            f.write(f"cond_L_3 slope_fa0(stage2)/slope_fa0(16k) ratio: {ratio_stage2_over_16k:.3f}\n")
        else:
            f.write("cond_L_3 slope ratio: NA (ctx=16k missing)\n")

        f.write("\n## fa=1 (Sbctx) vs fa=0 (Sbfa0 既存) vs fa=0-offload (本 Phase) slope 対比\n")
        f.write(
            f"{'ctx':>8}  {'OT':>4}  "
            f"{'fa1_d_pre':>11}  {'fa1_d_step':>11}  "
            f"{'fa0_d_pre':>11}  {'fa0_d_step':>11}  "
            f"{'delta_of_delta':>16}\n"
        )
        for s in slopes:
            c = s["ctx"]
            fa1 = FA1_DELTAS.get(c, {})
            fa1_pre = fa1.get("d_pre")
            fa1_step = fa1.get("d_step")

            def fmt(v: float | None) -> str:
                return f"{v:+.4f}" if v is not None else "   NA   "

            f.write(
                f"{c:>8}  {s['ot_tag']:>4}  "
                f"{fmt(fa1_pre):>11}  {fmt(fa1_step):>11}  "
                f"{fmt(s['delta_1584_1585']):>11}  {fmt(s['delta_1585_1586']):>11}  "
                f"{s['delta_of_delta']:>+16.4f}\n"
            )

        f.write("\n## Phase Sb-fa0 既存値 (現 OT = MoE のみ, fa=0 × ctx=16k) との baseline 比較\n")
        f.write(f"  Sb-fa0 original: delta_1584_1585=+2.1200, delta_1585_1586=+2.1200 (ctx=16k)\n")
        s_16k = next((s for s in slopes if s["ot_tag"] == final_ot and s["ctx"] == 16384), None)
        if s_16k is not None:
            d_pre_diff = s_16k["delta_1584_1585"] - 2.12
            d_step_diff = s_16k["delta_1585_1586"] - 2.12
            f.write(
                f"  Sb-fa0-offload (OT={final_ot}): "
                f"delta_1584_1585={s_16k['delta_1584_1585']:+.4f} "
                f"(Δ vs Sbfa0={d_pre_diff:+.4f}), "
                f"delta_1585_1586={s_16k['delta_1585_1586']:+.4f} "
                f"(Δ vs Sbfa0={d_step_diff:+.4f})\n"
            )
            if abs(d_pre_diff) > 0.1 or abs(d_step_diff) > 0.1:
                f.write("  -> OT 拡張が slope に 0.1 MiB/ub 以上の影響: 補正必要\n")
            else:
                f.write("  -> OT 拡張は slope 影響小 (<0.1 MiB/ub)\n")
        else:
            f.write("  Sb-fa0-offload ctx=16k: NA (Stage 4 未実施 or 失敗)\n")

        f.write("\n## 解釈ガイド\n")
        f.write("- support (cond1 True & cond2 False): δ 項は fa=1 固有 = FA tile 量子化副作用。次 Phase は tensor-dump で確定\n")
        f.write("- reject (cond1 False & cond2 True): δ 項は fa 共通 = FA 無関係。新候補 M の設計要 (例: KV-cache 参照 pattern)\n")
        f.write("- ambiguous: cond 両立 (数値精度不足、ctx 選択ミス等)\n")
        f.write("- partial: cond いずれも不成立 (δ_fa0 が 0 でも 0.24 でもない中間値) → FA 以外の混合要因\n")
        f.write("- not_conclusive: Stage 2 の stage2_ctx で slope を取れず (fa=0 全 OT 案 OOM)\n")

    # --- OOM slopes extraction ---
    oom_rows = analyze_oom()
    if oom_rows:
        # per (ctx, device) の ub 系列を作り、ub 差分 slope を算出
        by_cd: dict[tuple[int, int, str], dict[int, float]] = defaultdict(dict)
        for r in oom_rows:
            by_cd[(r["ctx"], r["device"], r["ot_tag"])][r["ub"]] = r["alloc_MiB"]
        oom_slope_rows = []
        for (c, d, ot), ub_map in sorted(by_cd.items()):
            if len(ub_map) >= 2:
                ubs_sorted = sorted(ub_map.keys())
                for i in range(len(ubs_sorted) - 1):
                    u1, u2 = ubs_sorted[i], ubs_sorted[i + 1]
                    slope = (ub_map[u2] - ub_map[u1]) / max(u2 - u1, 1)
                    oom_slope_rows.append({
                        "ctx": c, "device": d, "ot_tag": ot,
                        "ub_from": u1, "ub_to": u2,
                        "alloc_from": ub_map[u1], "alloc_to": ub_map[u2],
                        "slope_MiB_per_ub": round(slope, 4),
                    })
            # 単一 ub でも alloc size 単体として記録
            for u, v in ub_map.items():
                oom_slope_rows.append({
                    "ctx": c, "device": d, "ot_tag": ot,
                    "ub_from": u, "ub_to": u,
                    "alloc_from": v, "alloc_to": v,
                    "slope_MiB_per_ub": None,
                })
        if oom_slope_rows:
            with open(SCRIPT_DIR / "Sbfa0offload_oom_slopes.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(oom_slope_rows[0].keys()))
                w.writeheader()
                for r in oom_slope_rows:
                    w.writerow(r)

    print(f"Analysis complete. candidate_L_status={status}, FINAL_OT_TAG={final_ot}")
    print(f"See: {SCRIPT_DIR / 'Sbfa0offload_candidate_L_verdict.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
