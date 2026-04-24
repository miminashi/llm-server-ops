#!/usr/bin/env python3
"""analyze_phaseT5.py - Phase T-5: OT 層削減 (B28 VRAM 限界) 集計

5 条件 (B32a, B30, B28-t40, B28-t32, B32z) から eval_tps / prompt_tps の
mean/stdev/min/max を抽出し、CPU 層数昇順 pivot + session drift 分析 (B32a vs B32z) を
CSV / Markdown で出力する。
Phase D / S / T-1 / T-2 / T-3 / **T-4** 超え判定を付記。
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# CONDITIONS は "LABEL" を key とする (B32 は B32a / B32z の 2 つに分離)
# LABEL, OT_TAG, THREADS, CPU_LAYERS, NOTE
CONDITIONS = [
    ("B32a", "B32", 40, 32, "drift 起点"),
    ("B30",  "B30", 40, 30, "中間点"),
    ("B28",  "B28", 40, 28, "本命 (VRAM 限界)"),
    ("B28c", "B28", 32, 28, "層≠threads control"),
    ("B32z", "B32", 40, 32, "drift 終点"),
]

KV = "q8_0"
SM = "layer"
UB = 1586
CTX = 32768
WARMUP_RUNS = 2
EVAL_RUNS = 5

PEAK_PHASE_D = 15.03
PEAK_PHASE_S = 15.39
PEAK_PHASE_T1_Q8 = 15.016
PEAK_PHASE_T2_BEST = 14.672
PEAK_PHASE_T3_BEST = 14.860
PEAK_PHASE_T3_T40 = 14.781
PEAK_PHASE_T4_BEST = 15.494     # T-4 B32 × t40 (歴代最高)


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


def collect(label: str, thr: int) -> dict:
    tag_cond = f"{label}_t{thr}_kv{KV}_sm{SM}_ctx{CTX}_ub{UB}"
    warmup_dir = SCRIPT_DIR / f"out_T5_{tag_cond}_warmup"
    eval_dir = SCRIPT_DIR / f"out_T5_{tag_cond}_1k"
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
    if mean_eval > PEAK_PHASE_T4_BEST:
        return f"**SURPASS_T4** ({mean_eval:.3f} > {PEAK_PHASE_T4_BEST})"
    if mean_eval > PEAK_PHASE_S:
        return f"surpass_S ({mean_eval:.3f} > {PEAK_PHASE_S})"
    if mean_eval > PEAK_PHASE_D:
        return f"surpass_D ({mean_eval:.3f} > {PEAK_PHASE_D})"
    if mean_eval > PEAK_PHASE_T1_Q8:
        return f"surpass_T1_q8 ({mean_eval:.3f} > {PEAK_PHASE_T1_Q8})"
    if mean_eval > PEAK_PHASE_T3_BEST:
        return f"surpass_T3_best ({mean_eval:.3f} > {PEAK_PHASE_T3_BEST})"
    return f"below_T3 ({mean_eval:.3f} ≤ {PEAK_PHASE_T3_BEST})"


def main() -> int:
    data: dict = {}
    for label, ot, thr, layers, note in CONDITIONS:
        data[label] = collect(label, thr)

    # raw TSV
    summary_path = SCRIPT_DIR / "summary_phaseT5.tsv"
    with summary_path.open("w") as f:
        f.write(
            "label\tot_tag\tcpu_layers\tthreads\tkv\tsplit_mode\tub\tphase\trun\t"
            "eval_tps\tprompt_tps\tprompt_n\tpredicted_n\n"
        )
        for label, ot, thr, layers, note in CONDITIONS:
            for phase in ("warmup", "eval"):
                for idx, d in enumerate(data[label][phase], start=1):
                    f.write(
                        f"{label}\t{ot}\t{layers}\t{thr}\t{KV}\t{SM}\t{UB}\t{phase}\t{idx}\t"
                        f"{d.get('eval_tps')}\t{d.get('prompt_tps')}\t"
                        f"{d.get('prompt_n')}\t{d.get('predicted_n')}\n"
                    )
    print(f"[analyze] wrote {summary_path}")

    # 統計 CSV
    stats_path = SCRIPT_DIR / "phaseT5_stats.csv"
    with stats_path.open("w") as f:
        f.write(
            "label,ot_tag,cpu_layers,threads,kv,split_mode,ub,metric,phase,n,mean,stdev,min,max,median,"
            "surpass_phase_d,surpass_phase_s,surpass_phase_t1_q8,surpass_phase_t3_best,surpass_phase_t4\n"
        )
        for label, ot, thr, layers, note in CONDITIONS:
            for metric in ("eval_tps", "prompt_tps"):
                for phase in ("warmup", "eval"):
                    vals = [d.get(metric) for d in data[label][phase]]
                    s = stats(vals)
                    if s is None:
                        f.write(
                            f"{label},{ot},{layers},{thr},{KV},{SM},{UB},"
                            f"{metric},{phase},0,,,,,,,,,,\n"
                        )
                        continue
                    is_eval_m = (metric == "eval_tps" and phase == "eval")
                    sd = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_D) else "no"
                    ss = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_S) else "no"
                    st1 = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T1_Q8) else "no"
                    st3 = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T3_BEST) else "no"
                    st4 = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T4_BEST) else "no"
                    f.write(
                        f"{label},{ot},{layers},{thr},{KV},{SM},{UB},"
                        f"{metric},{phase},{s['n']},{s['mean']:.4f},{s['stdev']:.4f},"
                        f"{s['min']:.4f},{s['max']:.4f},{s['median']:.4f},"
                        f"{sd},{ss},{st1},{st3},{st4}\n"
                    )
    print(f"[analyze] wrote {stats_path}")

    # pivot Markdown
    pivot_path = SCRIPT_DIR / "phaseT5_pivot.md"
    with pivot_path.open("w") as f:
        f.write("# Phase T-5: OT 層削減 (B28 VRAM 限界) pivot 比較表\n\n")
        f.write(f"- KV={KV}, split-mode={SM}, ctx={CTX}, ub={UB}, fa=1, numactl node1, poll=0\n")
        f.write(f"- warmup {WARMUP_RUNS} run + eval {EVAL_RUNS} run\n")
        f.write(
            f"- ベースライン: Phase D {PEAK_PHASE_D} / Phase S {PEAK_PHASE_S} / "
            f"Phase T-1 q8_0 {PEAK_PHASE_T1_Q8} / Phase T-3 最良 {PEAK_PHASE_T3_BEST} / "
            f"**Phase T-4 最良 {PEAK_PHASE_T4_BEST}** (t/s)\n\n"
        )

        # eval_tps CPU 層数 x threads 順
        f.write("## eval_tps 条件別 (mean±stdev, t/s) — eval フェーズ 5 run\n\n")
        f.write("| label | OT | CPU 層数 | threads | 役割 | eval_mean±stdev | 判定 |\n")
        f.write("|-------|----|---------|---------|------|----------------|------|\n")
        best_overall = None
        eval_map = {}
        for label, ot, thr, layers, note in CONDITIONS:
            vals = [d.get("eval_tps") for d in data[label]["eval"]]
            s = stats(vals)
            eval_map[label] = s
            verd = verdict(s["mean"] if s else None)
            f.write(
                f"| {label} | {ot} | {layers} | {thr} | {note} | {fmt_cell(s)} | {verd} |\n"
            )
            if s is not None:
                if best_overall is None or s["mean"] > best_overall[2]:
                    best_overall = (label, (ot, thr, layers), s["mean"])
        f.write("\n")

        # prompt_tps 条件別
        f.write("## prompt_tps 条件別 (mean±stdev, t/s)\n\n")
        f.write("| label | OT | CPU 層数 | threads | prompt_mean±stdev |\n")
        f.write("|-------|----|---------|---------|------------------|\n")
        for label, ot, thr, layers, note in CONDITIONS:
            vals = [d.get("prompt_tps") for d in data[label]["eval"]]
            s = stats(vals)
            f.write(f"| {label} | {ot} | {layers} | {thr} | {fmt_cell(s)} |\n")
        f.write("\n")

        # CPU 層数 monotonic trend (threads=40 のみ)
        f.write("## CPU 層数 monotonic trend (threads=40 のみ)\n\n")
        f.write("| CPU 層数 | label | eval_mean (t/s) | B32a 起点差 |\n")
        f.write("|----------|-------|----------------|-------------|\n")
        trend_labels = ["B32a", "B30", "B28"]
        baseline = eval_map.get("B32a")
        for lbl in trend_labels:
            s = eval_map.get(lbl)
            layer_count = {"B32a": 32, "B30": 30, "B28": 28}[lbl]
            if s is None or baseline is None:
                f.write(f"| {layer_count} | {lbl} | no_data | -- |\n")
            else:
                delta = s["mean"] - baseline["mean"]
                f.write(f"| {layer_count} | {lbl} | {s['mean']:.3f} | {delta:+.3f} t/s |\n")
        f.write("\n")

        # trend 判定
        s32a = eval_map.get("B32a")
        s30 = eval_map.get("B30")
        s28 = eval_map.get("B28")
        trend_verdict = ""
        if s32a and s30 and s28:
            if s28["mean"] > s30["mean"] > s32a["mean"] and (s28["mean"] - s32a["mean"]) >= 0.1:
                trend_verdict = f"**STRONG monotonic** (B32a < B30 < B28, 差 {s28['mean']-s32a['mean']:+.3f} ≥ 0.1)"
            elif s28["mean"] > s32a["mean"] and (s28["mean"] - s32a["mean"]) >= 0.1:
                trend_verdict = f"**SUPPORT** (B28 > B32a、中間非単調の可能性、差 {s28['mean']-s32a['mean']:+.3f})"
            elif abs(s28["mean"] - s32a["mean"]) < 0.05:
                trend_verdict = f"**NEUTRAL/plateau** (B28 ≈ B32a、差 {s28['mean']-s32a['mean']:+.3f} < 0.05)"
            elif s28["mean"] < s32a["mean"]:
                trend_verdict = f"**REVERSE** (B28 < B32a、GPU saturate 仮説支持、差 {s28['mean']-s32a['mean']:+.3f})"
            else:
                trend_verdict = f"小差別 (差 {s28['mean']-s32a['mean']:+.3f})"
        f.write(f"### trend 判定: {trend_verdict}\n\n")

        # session drift 分析 (B32a vs B32z)
        f.write("## Session drift 分析 (B32a 起点 vs B32z 終点)\n\n")
        s_start = eval_map.get("B32a")
        s_end = eval_map.get("B32z")
        f.write("| label | 役割 | eval_mean | 起点比 |\n")
        f.write("|-------|------|----------|--------|\n")
        if s_start:
            f.write(f"| B32a | drift 起点 | {s_start['mean']:.3f} | -- |\n")
        if s_end and s_start:
            delta = s_end["mean"] - s_start["mean"]
            dpct = delta / s_start["mean"] * 100
            f.write(f"| B32z | drift 終点 | {s_end['mean']:.3f} | {delta:+.3f} t/s ({dpct:+.2f}%) |\n")
            f.write("\n")
            if abs(delta) < 0.2:
                drift_verdict = f"**drift 健全** (|差| {abs(delta):.3f} < 0.2 t/s、絶対値比較有効)"
            else:
                drift_verdict = f"**drift 大** (|差| {abs(delta):.3f} ≥ 0.2 t/s、絶対値比較は drift 補正要)"
            f.write(f"### drift 判定: {drift_verdict}\n\n")
        else:
            f.write("\n(B32z data 不足で判定不能)\n\n")

        # 層≠threads control (B28-t32)
        f.write("## 層 ≠ threads 不一致 control (B28-t40 vs B28-t32)\n\n")
        s_b28_40 = eval_map.get("B28")
        s_b28_32 = eval_map.get("B28c")
        f.write("| label | threads | 層==threads? | eval_mean |\n")
        f.write("|-------|---------|--------------|----------|\n")
        if s_b28_40:
            f.write(f"| B28 | 40 | no (28≠40) | {s_b28_40['mean']:.3f} |\n")
        if s_b28_32:
            f.write(f"| B28c | 32 | no (28≠32) | {s_b28_32['mean']:.3f} |\n")
        if s_b28_40 and s_b28_32:
            delta = s_b28_32["mean"] - s_b28_40["mean"]
            dpct = delta / s_b28_40["mean"] * 100
            f.write(f"\nt32 vs t40 (at B28): {delta:+.3f} t/s ({dpct:+.2f}%) — 両方とも不一致条件、純粋 threads 効果のみ\n\n")

        # 結果サマリ
        f.write("## 結果サマリ\n\n")
        if best_overall:
            lbl_b, (ot_b, thr_b, layers_b), m_b = best_overall
            f.write(f"- **最良 eval 構成**: label={lbl_b} (ot={ot_b}, CPU {layers_b} 層 × threads={thr_b}), eval_mean={m_b:.3f} t/s\n")
            f.write(f"- **Phase T-4 ({PEAK_PHASE_T4_BEST}) 超え**: {'**YES**' if m_b > PEAK_PHASE_T4_BEST else 'NO'}\n")
            f.write(f"- **Phase S ({PEAK_PHASE_S}) 超え**: {'YES' if m_b > PEAK_PHASE_S else 'NO'}\n")
            f.write(f"- **Phase D ({PEAK_PHASE_D}) 超え**: {'YES' if m_b > PEAK_PHASE_D else 'NO'}\n")
            f.write(f"- **Phase T-1 q8_0 ({PEAK_PHASE_T1_Q8}) 超え**: {'YES' if m_b > PEAK_PHASE_T1_Q8 else 'NO'}\n")
            f.write(f"- **Phase T-3 最良 ({PEAK_PHASE_T3_BEST}) 超え**: {'YES' if m_b > PEAK_PHASE_T3_BEST else 'NO'}\n")
        else:
            f.write("- データ不足\n")
        f.write("\n")

        # 歴代全 Phase 比較
        f.write("## Phase D / S / T-1 / T-2 / T-3 / T-4 / T-5 全体比較\n\n")
        f.write("| Phase | 条件 (要点) | eval mean (t/s) | T-5 最良との差 |\n")
        f.write("|-------|-------------|----------------|----------------|\n")
        ref_rows = [
            ("D", "threads=40, ub=1586, ctx=32k, OT=36 層", PEAK_PHASE_D),
            ("S", "ctx=65k, ub=512, threads=40 (旧歴代最高)", PEAK_PHASE_S),
            ("T-1", "KV q8_0, ub=1586, threads=40", PEAK_PHASE_T1_Q8),
            ("T-2 best", "split=layer, q8_0, threads=40", PEAK_PHASE_T2_BEST),
            ("T-3 best", "threads=32, OT=A36 (CPU 36 層)", PEAK_PHASE_T3_BEST),
            ("T-3 t40", "threads=40, OT=A36 (baseline)", PEAK_PHASE_T3_T40),
            ("T-4 best", "B32 (CPU 32 層) × threads=40 (T-4 歴代最高)", PEAK_PHASE_T4_BEST),
        ]
        m_b = best_overall[2] if best_overall else None
        for label, cond, val in ref_rows:
            if m_b:
                d = (m_b - val) / val * 100
                f.write(f"| {label} | {cond} | {val:.3f} | {d:+.2f}% |\n")
            else:
                f.write(f"| {label} | {cond} | {val:.3f} | NA |\n")
        # T-5 全条件
        for label, ot, thr, layers, note in CONDITIONS:
            s = eval_map.get(label)
            if s is None:
                continue
            marker = " (**本 Phase 最良**)" if best_overall and best_overall[0] == label else ""
            if m_b:
                d_pct = (s["mean"] - m_b) / m_b * 100
                f.write(
                    f"| **T-5** | {label} ({ot}, CPU {layers} 層 × threads={thr}, {note}){marker} | "
                    f"{s['mean']:.3f} | {d_pct:+.2f}% |\n"
                )
        f.write("\n")

    print(f"[analyze] wrote {pivot_path}")
    with pivot_path.open() as f:
        print(f.read())
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
