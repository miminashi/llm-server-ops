#!/usr/bin/env python3
"""analyze_phaseT5e.py - Phase T-5e: B28 × (ctx, ub) 適用 集計

5 条件 (B28_32k_1586a, B28_65k_ub512, B28_65k_ub1586, B28_32k_ub512, B28_32k_1586z) から
eval_tps / prompt_tps の mean/stdev/min/max を抽出し、(ctx, ub) 2x2 factorial 分析と
session drift (起点 vs 終点) を CSV / Markdown で出力する。
Phase D / S / T-1 / T-2 / T-3 / T-4 / T-5 超え判定を付記。
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# CONDITIONS: (LABEL, CTX, UB, THREADS, NOTE)
CONDITIONS = [
    ("B28_32k_1586a",  32768, 1586, 40, "drift 起点 (T-5 B28 = 16.024 再現)"),
    ("B28_65k_ub512",  65536,  512, 40, "★本命 (Phase S 条件適用)"),
    ("B28_65k_ub1586", 65536, 1586, 40, "ctx 単独効果分離"),
    ("B28_32k_ub512",  32768,  512, 40, "ub 単独効果分離"),
    ("B28_32k_1586z",  32768, 1586, 40, "drift 終点"),
]

OT_TAG = "B28"
CPU_LAYERS = 28
KV = "q8_0"
SM = "layer"
WARMUP_RUNS = 2
EVAL_RUNS = 5

PEAK_PHASE_D = 15.03
PEAK_PHASE_S = 15.39
PEAK_PHASE_T1_Q8 = 15.016
PEAK_PHASE_T2_BEST = 14.672
PEAK_PHASE_T3_BEST = 14.860
PEAK_PHASE_T4_BEST = 15.494
PEAK_PHASE_T5_BEST = 16.024    # T-5 B28 × t40 (直前歴代最高)


def load_run(outdir: Path, run: int) -> dict:
    p = outdir / f"eval_run{run}.json"
    if not p.exists():
        return {}
    try:
        with p.open() as f:
            data = json.load(f)
    except Exception as e:
        print(f"WARN: {p} parse error: {e}", file=sys.stderr)
        return {}
    t = data.get("timings", {})
    return {
        "eval_tps": t.get("predicted_per_second"),
        "prompt_tps": t.get("prompt_per_second"),
        "prompt_n": t.get("prompt_n"),
        "predicted_n": t.get("predicted_n"),
    }


def collect(label: str, ctx: int, ub: int, thr: int) -> dict:
    tag_cond = f"{label}_t{thr}_kv{KV}_sm{SM}_ctx{ctx}_ub{ub}"
    warmup_dir = SCRIPT_DIR / f"out_T5e_{tag_cond}_warmup"
    eval_dir = SCRIPT_DIR / f"out_T5e_{tag_cond}_1k"
    warmup = []
    for r in range(1, WARMUP_RUNS + 1):
        d = load_run(warmup_dir, r)
        if d:
            warmup.append(d)
    ev = []
    for r in range(1, EVAL_RUNS + 1):
        d = load_run(eval_dir, r)
        if d:
            ev.append(d)
    return {"warmup": warmup, "eval": ev}


def stats(values):
    vs = [v for v in values if isinstance(v, (int, float))]
    if not vs:
        return None
    return {
        "n": len(vs),
        "mean": statistics.mean(vs),
        "stdev": statistics.pstdev(vs) if len(vs) < 2 else statistics.stdev(vs),
        "min": min(vs),
        "max": max(vs),
        "median": statistics.median(vs),
    }


def fmt_cell(s):
    if s is None:
        return "no_data"
    return f"{s['mean']:.3f}±{s['stdev']:.3f}"


def verdict(mean_eval):
    if mean_eval is None:
        return "no_data"
    if mean_eval > PEAK_PHASE_T5_BEST:
        return f"**SURPASS_T5** ({mean_eval:.3f} > {PEAK_PHASE_T5_BEST})"
    if mean_eval > PEAK_PHASE_T4_BEST:
        return f"surpass_T4 ({mean_eval:.3f} > {PEAK_PHASE_T4_BEST})"
    if mean_eval > PEAK_PHASE_S:
        return f"surpass_S ({mean_eval:.3f} > {PEAK_PHASE_S})"
    if mean_eval > PEAK_PHASE_D:
        return f"surpass_D ({mean_eval:.3f} > {PEAK_PHASE_D})"
    if mean_eval > PEAK_PHASE_T1_Q8:
        return f"surpass_T1_q8 ({mean_eval:.3f} > {PEAK_PHASE_T1_Q8})"
    return f"below_T1_q8 ({mean_eval:.3f} ≤ {PEAK_PHASE_T1_Q8})"


def main() -> int:
    data: dict = {}
    for label, ctx, ub, thr, note in CONDITIONS:
        data[label] = collect(label, ctx, ub, thr)

    # raw TSV
    summary_path = SCRIPT_DIR / "summary_phaseT5e.tsv"
    with summary_path.open("w") as f:
        f.write(
            "label\tot_tag\tcpu_layers\tthreads\tkv\tsplit_mode\tctx\tub\tphase\trun\t"
            "eval_tps\tprompt_tps\tprompt_n\tpredicted_n\n"
        )
        for label, ctx, ub, thr, note in CONDITIONS:
            for phase in ("warmup", "eval"):
                for idx, d in enumerate(data[label][phase], start=1):
                    f.write(
                        f"{label}\t{OT_TAG}\t{CPU_LAYERS}\t{thr}\t{KV}\t{SM}\t{ctx}\t{ub}\t{phase}\t{idx}\t"
                        f"{d.get('eval_tps')}\t{d.get('prompt_tps')}\t"
                        f"{d.get('prompt_n')}\t{d.get('predicted_n')}\n"
                    )
    print(f"[analyze] wrote {summary_path}")

    # 統計 CSV
    stats_path = SCRIPT_DIR / "phaseT5e_stats.csv"
    with stats_path.open("w") as f:
        f.write(
            "label,ot_tag,cpu_layers,threads,kv,split_mode,ctx,ub,metric,phase,n,mean,stdev,min,max,median,"
            "surpass_phase_d,surpass_phase_s,surpass_phase_t1_q8,surpass_phase_t4,surpass_phase_t5\n"
        )
        for label, ctx, ub, thr, note in CONDITIONS:
            for metric in ("eval_tps", "prompt_tps"):
                for phase in ("warmup", "eval"):
                    vals = [d.get(metric) for d in data[label][phase]]
                    s = stats(vals)
                    if s is None:
                        f.write(
                            f"{label},{OT_TAG},{CPU_LAYERS},{thr},{KV},{SM},{ctx},{ub},"
                            f"{metric},{phase},0,,,,,,,,,,\n"
                        )
                        continue
                    is_eval_m = (metric == "eval_tps" and phase == "eval")
                    sd = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_D) else "no"
                    ss = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_S) else "no"
                    st1 = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T1_Q8) else "no"
                    st4 = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T4_BEST) else "no"
                    st5 = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T5_BEST) else "no"
                    f.write(
                        f"{label},{OT_TAG},{CPU_LAYERS},{thr},{KV},{SM},{ctx},{ub},"
                        f"{metric},{phase},{s['n']},{s['mean']:.4f},{s['stdev']:.4f},"
                        f"{s['min']:.4f},{s['max']:.4f},{s['median']:.4f},"
                        f"{sd},{ss},{st1},{st4},{st5}\n"
                    )
    print(f"[analyze] wrote {stats_path}")

    # pivot Markdown
    pivot_path = SCRIPT_DIR / "phaseT5e_pivot.md"
    with pivot_path.open("w") as f:
        f.write("# Phase T-5e: B28 × (ctx, ub) 適用 pivot 比較表\n\n")
        f.write(f"- OT={OT_TAG} (CPU {CPU_LAYERS} 層), KV={KV}, split-mode={SM}, threads=40, fa=1, numactl node1, poll=0\n")
        f.write(f"- warmup {WARMUP_RUNS} run + eval {EVAL_RUNS} run\n")
        f.write(
            f"- ベースライン: Phase D {PEAK_PHASE_D} / Phase S {PEAK_PHASE_S} / "
            f"Phase T-4 最良 {PEAK_PHASE_T4_BEST} / **Phase T-5 最良 {PEAK_PHASE_T5_BEST}** (t/s)\n\n"
        )

        # eval_tps 条件別 (実行順)
        f.write("## eval_tps 条件別 (mean±stdev, t/s) — eval フェーズ 5 run\n\n")
        f.write("| label | ctx | ub | 役割 | eval_mean±stdev | 判定 |\n")
        f.write("|-------|-----|----|------|----------------|------|\n")
        best_overall = None
        eval_map = {}
        for label, ctx, ub, thr, note in CONDITIONS:
            vals = [d.get("eval_tps") for d in data[label]["eval"]]
            s = stats(vals)
            eval_map[label] = s
            verd = verdict(s["mean"] if s else None)
            f.write(f"| {label} | {ctx} | {ub} | {note} | {fmt_cell(s)} | {verd} |\n")
            if s is not None:
                if best_overall is None or s["mean"] > best_overall[2]:
                    best_overall = (label, (ctx, ub), s["mean"])
        f.write("\n")

        # prompt_tps 条件別
        f.write("## prompt_tps 条件別 (mean±stdev, t/s)\n\n")
        f.write("| label | ctx | ub | prompt_mean±stdev |\n")
        f.write("|-------|-----|----|------------------|\n")
        for label, ctx, ub, thr, note in CONDITIONS:
            vals = [d.get("prompt_tps") for d in data[label]["eval"]]
            s = stats(vals)
            f.write(f"| {label} | {ctx} | {ub} | {fmt_cell(s)} |\n")
        f.write("\n")

        # 2x2 factorial 分析 (4 点: B28_a, B28_65k_ub1586, B28_32k_ub512, B28_65k_ub512)
        # B28_a = baseline (ctx=32k, ub=1586)
        # ctx 単独: B28_65k_ub1586 vs B28_a
        # ub 単独: B28_32k_ub512 vs B28_a
        # 本命: B28_65k_ub512 (ctx 増 & ub 減 両方)
        f.write("## 2x2 factorial 分析 (ctx × ub)\n\n")
        f.write("| | **ub=1586** | **ub=512** | Δub (固定 ctx) |\n")
        f.write("|---|-------------|------------|---------------|\n")
        b_a = eval_map.get("B28_32k_1586a")
        b_65_1586 = eval_map.get("B28_65k_ub1586")
        b_32_512 = eval_map.get("B28_32k_ub512")
        b_65_512 = eval_map.get("B28_65k_ub512")

        def cell(s):
            return f"{s['mean']:.3f}" if s else "no_data"

        def delta(a, b):
            if a is None or b is None:
                return "--"
            return f"{b['mean']-a['mean']:+.3f}"

        f.write(f"| **ctx=32k** | {cell(b_a)} (baseline) | {cell(b_32_512)} | {delta(b_a, b_32_512)} |\n")
        f.write(f"| **ctx=65k** | {cell(b_65_1586)} | {cell(b_65_512)} | {delta(b_65_1586, b_65_512)} |\n")
        f.write(f"| Δctx (固定 ub) | {delta(b_a, b_65_1586)} | {delta(b_32_512, b_65_512)} | -- |\n\n")

        # 相加 vs 相乗
        if b_a and b_65_1586 and b_32_512 and b_65_512:
            additive = (b_65_1586["mean"] - b_a["mean"]) + (b_32_512["mean"] - b_a["mean"])
            actual = b_65_512["mean"] - b_a["mean"]
            synergy = actual - additive
            f.write(f"- **ctx 単独効果** (ub=1586 固定): {b_65_1586['mean']-b_a['mean']:+.3f} t/s\n")
            f.write(f"- **ub 単独効果** (ctx=32k 固定): {b_32_512['mean']-b_a['mean']:+.3f} t/s\n")
            f.write(f"- **純加算予測**: B28_a + (ctx 単独) + (ub 単独) = {b_a['mean']:.3f} + {b_65_1586['mean']-b_a['mean']:+.3f} + {b_32_512['mean']-b_a['mean']:+.3f} = **{b_a['mean']+additive:.3f}** t/s\n")
            f.write(f"- **実測値 (本命)**: {b_65_512['mean']:.3f} t/s\n")
            f.write(f"- **相乗効果** (実測 − 純加算): **{synergy:+.3f}** t/s ")
            if synergy > 0.05:
                f.write(f"→ **相乗 (positive synergy)** ✓\n\n")
            elif synergy < -0.05:
                f.write(f"→ **反相乗 (negative synergy, ctx×ub の cross penalty)**\n\n")
            else:
                f.write(f"→ **純加算 (additive)**\n\n")

        # Session drift (B28_32k_1586a vs B28_32k_1586z)
        f.write("## Session drift 分析 (B28_32k_1586a 起点 vs B28_32k_1586z 終点)\n\n")
        s_start = eval_map.get("B28_32k_1586a")
        s_end = eval_map.get("B28_32k_1586z")
        f.write("| label | 役割 | eval_mean | 起点比 |\n")
        f.write("|-------|------|----------|--------|\n")
        if s_start:
            f.write(f"| B28_32k_1586a | drift 起点 | {s_start['mean']:.3f} | -- |\n")
        if s_end and s_start:
            delta_v = s_end["mean"] - s_start["mean"]
            dpct = delta_v / s_start["mean"] * 100
            f.write(f"| B28_32k_1586z | drift 終点 | {s_end['mean']:.3f} | {delta_v:+.3f} t/s ({dpct:+.2f}%) |\n\n")
            if abs(delta_v) < 0.2:
                drift_verdict = f"**drift 健全** (|差| {abs(delta_v):.3f} < 0.2 t/s、絶対値比較有効)"
            else:
                drift_verdict = f"**drift 大** (|差| {abs(delta_v):.3f} ≥ 0.2 t/s、絶対値比較は drift 補正要)"
            f.write(f"### drift 判定: {drift_verdict}\n\n")

        # T-5 再現性 (B28_32k_1586a vs T-5 B28 16.024)
        if s_start:
            repro_delta = s_start["mean"] - PEAK_PHASE_T5_BEST
            f.write(f"### T-5 B28 再現性 (session 間 drift):\n")
            f.write(f"- T-5 B28 (前回 session): {PEAK_PHASE_T5_BEST:.3f} t/s\n")
            f.write(f"- T-5e B28_32k_1586a (今回 session 起点): {s_start['mean']:.3f} t/s\n")
            f.write(f"- **session 間 drift: {repro_delta:+.3f} t/s ({repro_delta/PEAK_PHASE_T5_BEST*100:+.2f}%)**\n\n")

        # 結果サマリ
        f.write("## 結果サマリ\n\n")
        if best_overall:
            lbl_b, (ctx_b, ub_b), m_b = best_overall
            f.write(f"- **最良 eval 構成**: label={lbl_b} (ctx={ctx_b}, ub={ub_b}, OT=B28, threads=40), eval_mean={m_b:.3f} t/s\n")
            f.write(f"- **Phase T-5 ({PEAK_PHASE_T5_BEST}) 超え**: {'**YES (新記録)**' if m_b > PEAK_PHASE_T5_BEST else 'NO'}\n")
            f.write(f"- **Phase T-4 ({PEAK_PHASE_T4_BEST}) 超え**: {'YES' if m_b > PEAK_PHASE_T4_BEST else 'NO'}\n")
            f.write(f"- **Phase S ({PEAK_PHASE_S}) 超え**: {'YES' if m_b > PEAK_PHASE_S else 'NO'}\n")
            f.write(f"- **Phase D ({PEAK_PHASE_D}) 超え**: {'YES' if m_b > PEAK_PHASE_D else 'NO'}\n")
        else:
            f.write("- データ不足\n")
        f.write("\n")

        # 歴代全 Phase 比較
        f.write("## Phase D / S / T-1 / T-2 / T-3 / T-4 / T-5 / T-5e 全体比較\n\n")
        f.write("| Phase | 条件 (要点) | eval mean (t/s) | T-5e 最良との差 |\n")
        f.write("|-------|-------------|----------------|----------------|\n")
        ref_rows = [
            ("D", "threads=40, ub=1586, ctx=32k, OT=36 層", PEAK_PHASE_D),
            ("S", "ctx=65k, ub=512, threads=40, A36 (旧歴代 #2)", PEAK_PHASE_S),
            ("T-1", "KV q8_0, ub=1586, threads=40", PEAK_PHASE_T1_Q8),
            ("T-2 best", "split=layer, q8_0, threads=40", PEAK_PHASE_T2_BEST),
            ("T-3 best", "threads=32, OT=A36", PEAK_PHASE_T3_BEST),
            ("T-4 best", "B32 (CPU 32 層) × threads=40", PEAK_PHASE_T4_BEST),
            ("T-5 best", "B28 (CPU 28 層) × threads=40, ctx=32k ub=1586 (直前歴代 #1)", PEAK_PHASE_T5_BEST),
        ]
        m_b = best_overall[2] if best_overall else None
        for label, cond, val in ref_rows:
            if m_b:
                d = (m_b - val) / val * 100
                f.write(f"| {label} | {cond} | {val:.3f} | {d:+.2f}% |\n")
            else:
                f.write(f"| {label} | {cond} | {val:.3f} | NA |\n")
        for label, ctx, ub, thr, note in CONDITIONS:
            s = eval_map.get(label)
            if s is None:
                continue
            marker = " (**本 Phase 最良**)" if best_overall and best_overall[0] == label else ""
            if m_b:
                d_pct = (s["mean"] - m_b) / m_b * 100
                f.write(
                    f"| **T-5e** | {label} (ctx={ctx}, ub={ub}, {note}){marker} | "
                    f"{s['mean']:.3f} | {d_pct:+.2f}% |\n"
                )
        f.write("\n")

    print(f"[analyze] wrote {pivot_path}")
    with pivot_path.open() as f:
        print(f.read())
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
