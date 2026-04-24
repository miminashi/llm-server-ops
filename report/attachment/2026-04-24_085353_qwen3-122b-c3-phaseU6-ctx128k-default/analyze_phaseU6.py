#!/usr/bin/env python3
"""Phase U-6 analysis: aggregate phaseU6_results.csv into pivots + baseline comparison."""
import csv
import os
import statistics as st
import sys

BASELINE = 18.664  # B14b_ts_alt @ ctx=32k, historic baseline

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "phaseU6_results.csv")
OUT_PIVOT = os.path.join(BASE_DIR, "phaseU6_pivot.md")
OUT_STATS = os.path.join(BASE_DIR, "phaseU6_stats.csv")


def to_float(x):
    try:
        return float(x)
    except (ValueError, TypeError):
        return None


def load_rows():
    rows = []
    with open(CSV_PATH) as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)
    return rows


def compute_stats(rows):
    """cell/ub/prompt_tag/role でグループ化、eval_tps, prompt_tps を集計"""
    groups = {}
    for r in rows:
        key = (r["cond"], r["ub"], r["prompt_tag"], r["role"])
        groups.setdefault(key, []).append(r)

    out = []
    for (cond, ub, prompt_tag, role), grp in sorted(groups.items()):
        if role not in ("eval", "warmup"):
            continue
        eval_tps = [to_float(g["eval_tps"]) for g in grp]
        eval_tps = [x for x in eval_tps if x is not None]
        prompt_tps = [to_float(g["prompt_tps"]) for g in grp]
        prompt_tps = [x for x in prompt_tps if x is not None]
        prompt_ms = [to_float(g["prompt_ms"]) for g in grp]
        prompt_ms = [x for x in prompt_ms if x is not None]
        min_gpu = [to_float(g["min_gpu_free_MiB"]) for g in grp]
        min_gpu = [x for x in min_gpu if x is not None]

        rec = {
            "cond": cond, "ub": ub, "prompt_tag": prompt_tag, "role": role,
            "n": len(grp),
            "eval_median": st.median(eval_tps) if eval_tps else None,
            "eval_stdev": st.stdev(eval_tps) if len(eval_tps) >= 2 else None,
            "eval_min": min(eval_tps) if eval_tps else None,
            "eval_max": max(eval_tps) if eval_tps else None,
            "prompt_tps_median": st.median(prompt_tps) if prompt_tps else None,
            "prompt_ms_median": st.median(prompt_ms) if prompt_ms else None,
            "min_gpu_free_MiB": min(min_gpu) if min_gpu else None,
        }
        if rec["eval_median"] is not None:
            rec["baseline_ratio"] = rec["eval_median"] / BASELINE
        else:
            rec["baseline_ratio"] = None
        out.append(rec)
    return out


def fmt(x, digits=3):
    if x is None:
        return "-"
    if isinstance(x, float):
        return f"{x:.{digits}f}"
    return str(x)


def write_stats_csv(stats):
    with open(OUT_STATS, "w") as f:
        w = csv.writer(f)
        w.writerow(["cond", "ub", "prompt_tag", "role", "n",
                    "eval_median", "eval_stdev", "eval_min", "eval_max",
                    "prompt_tps_median", "prompt_ms_median",
                    "min_gpu_free_MiB", "baseline_ratio"])
        for s in stats:
            w.writerow([s["cond"], s["ub"], s["prompt_tag"], s["role"], s["n"],
                        fmt(s["eval_median"]), fmt(s["eval_stdev"], 4),
                        fmt(s["eval_min"]), fmt(s["eval_max"]),
                        fmt(s["prompt_tps_median"], 2),
                        fmt(s["prompt_ms_median"], 0),
                        fmt(s["min_gpu_free_MiB"], 0),
                        fmt(s["baseline_ratio"], 4)])


def write_pivot_md(stats):
    lines = [
        f"# Phase U-6 Pivot Summary",
        f"Baseline: B14b_ts_alt @ ctx=32k = {BASELINE} t/s",
        "",
        "## eval (TG) by cond × ub × prompt_tag",
        "",
        "| cond | ub | prompt | n | eval_median | stdev | baseline_ratio | prompt_tps | prompt_ms | min_gpu_free |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in sorted([x for x in stats if x["role"] == "eval"],
                    key=lambda x: (x["cond"], int(x["ub"]) if x["ub"].isdigit() else 0,
                                   {"1k": 0, "32k": 1, "96k": 2}.get(x["prompt_tag"], 99))):
        lines.append("| {cond} | {ub} | {pt} | {n} | {em} | {sd} | {br} | {pt2} | {pm} | {mg} |".format(
            cond=s["cond"], ub=s["ub"], pt=s["prompt_tag"], n=s["n"],
            em=fmt(s["eval_median"]), sd=fmt(s["eval_stdev"], 4),
            br=fmt(s["baseline_ratio"], 3),
            pt2=fmt(s["prompt_tps_median"], 2),
            pm=fmt(s["prompt_ms_median"], 0),
            mg=fmt(s["min_gpu_free_MiB"], 0)))

    lines += [
        "",
        "## score (Phase U-6 default 決定用)",
        "",
        "score = 0.50 \\* R_eval + 0.25 \\* R_prompt_32k + 0.15 \\* R_headroom + 0.10 \\* R_stability",
        "",
    ]

    # Pareto / score 計算
    # R_eval は prompt=1k の eval_median を baseline で割る
    # R_prompt_32k は prompt=32k の prompt_tps_median を構成間で max=1
    # R_headroom は min_gpu_free / 2500 (cap 1.0)
    # R_stability は 1 - stdev/median (prompt=1k 時)
    eval_map = {(s["cond"], s["ub"]): s for s in stats if s["role"] == "eval" and s["prompt_tag"] == "1k"}
    prompt32_map = {(s["cond"], s["ub"]): s for s in stats if s["role"] == "eval" and s["prompt_tag"] == "32k"}
    max_prompt32 = max((s["prompt_tps_median"] or 0) for s in prompt32_map.values()) if prompt32_map else 1.0
    max_prompt32 = max_prompt32 if max_prompt32 > 0 else 1.0

    lines.append("| cond | ub | R_eval | R_p32k | R_head | R_stab | score |")
    lines.append("|---|---|---|---|---|---|---|")
    scores = []
    for key, s in eval_map.items():
        cond, ub = key
        p32 = prompt32_map.get(key)
        R_eval = (s["eval_median"] or 0) / BASELINE
        R_p32 = ((p32["prompt_tps_median"] or 0) / max_prompt32) if p32 else 0.0
        mg = s["min_gpu_free_MiB"] or 0
        R_head = min(mg / 2500.0, 1.0)
        if s["eval_median"] and s["eval_stdev"]:
            R_stab = 1.0 - s["eval_stdev"] / s["eval_median"]
        else:
            R_stab = 0.0
        score = 0.50 * R_eval + 0.25 * R_p32 + 0.15 * R_head + 0.10 * R_stab
        scores.append((score, cond, ub, R_eval, R_p32, R_head, R_stab))
        lines.append(f"| {cond} | {ub} | {R_eval:.3f} | {R_p32:.3f} | {R_head:.3f} | {R_stab:.3f} | {score:.3f} |")

    if scores:
        scores.sort(reverse=True)
        top = scores[0]
        lines.append("")
        lines.append(f"**推奨 default**: cond={top[1]} ub={top[2]} score={top[0]:.3f}")

    with open(OUT_PIVOT, "w") as f:
        f.write("\n".join(lines))


def main():
    if not os.path.exists(CSV_PATH):
        print(f"ERROR: {CSV_PATH} not found", file=sys.stderr)
        sys.exit(1)
    rows = load_rows()
    stats = compute_stats(rows)
    write_stats_csv(stats)
    write_pivot_md(stats)
    print(f"wrote: {OUT_STATS}")
    print(f"wrote: {OUT_PIVOT}")


if __name__ == "__main__":
    main()
