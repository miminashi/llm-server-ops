#!/usr/bin/env python3
"""analyze_phaseT5f.py - Phase T-5f: B28 × ctx=32k × ub 微細スイープ + drift bracket 集計

9 条件の eval_tps / prompt_tps の mean/stdev/min/max を抽出し、
- ub 1D trend 表 (drift 補正前・補正後)
- session drift bracket (B28_32k_ub512a vs B28_32k_ub512z)
- eval/prompt Pareto 評価用表
- 歴代 Phase 比較
を CSV / Markdown で出力する。
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# CONDITIONS: (LABEL, CTX, UB, THREADS, run_index, NOTE)
# run_index は drift 補正に使用 (1..9)
CONDITIONS = [
    ("B28_32k_ub512a", 32768,  512, 40, 1, "drift 起点 (T-5e 最良 16.380 の再現狙い)"),
    ("B28_32k_ub1586", 32768, 1586, 40, 2, "T-5 drift 補正基準 (ub=1586 at 32k)"),
    ("B28_32k_ub1024", 32768, 1024, 40, 3, "Pareto 中間点"),
    ("B28_32k_ub768",  32768,  768, 40, 4, "Pareto knee 候補"),
    ("B28_32k_ub384",  32768,  384, 40, 5, "ub<512 trend 確認"),
    ("B28_32k_ub256",  32768,  256, 40, 6, "新記録候補"),
    ("B28_32k_ub128",  32768,  128, 40, 7, "trend 延長"),
    ("B28_32k_ub64",   32768,   64, 40, 8, "動作下限"),
    ("B28_32k_ub512z", 32768,  512, 40, 9, "drift 終点"),
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
PEAK_PHASE_T5_BEST = 16.024
PEAK_PHASE_T5E_BEST = 16.380  # T-5e B28_32k_ub512 (直前歴代最高)


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
    warmup_dir = SCRIPT_DIR / f"out_T5f_{tag_cond}_warmup"
    eval_dir = SCRIPT_DIR / f"out_T5f_{tag_cond}_1k"
    warmup, ev = [], []
    for r in range(1, WARMUP_RUNS + 1):
        d = load_run(warmup_dir, r)
        if d:
            warmup.append(d)
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
    if mean_eval > PEAK_PHASE_T5E_BEST:
        return f"**SURPASS_T5e** ({mean_eval:.3f} > {PEAK_PHASE_T5E_BEST})"
    if mean_eval > PEAK_PHASE_T5_BEST:
        return f"surpass_T5 ({mean_eval:.3f} > {PEAK_PHASE_T5_BEST})"
    if mean_eval > PEAK_PHASE_T4_BEST:
        return f"surpass_T4 ({mean_eval:.3f} > {PEAK_PHASE_T4_BEST})"
    if mean_eval > PEAK_PHASE_S:
        return f"surpass_S ({mean_eval:.3f} > {PEAK_PHASE_S})"
    if mean_eval > PEAK_PHASE_D:
        return f"surpass_D ({mean_eval:.3f} > {PEAK_PHASE_D})"
    return f"below_D ({mean_eval:.3f} ≤ {PEAK_PHASE_D})"


def main() -> int:
    data: dict = {}
    for label, ctx, ub, thr, idx, note in CONDITIONS:
        data[label] = collect(label, ctx, ub, thr)

    # raw TSV
    summary_path = SCRIPT_DIR / "summary_phaseT5f.tsv"
    with summary_path.open("w") as f:
        f.write(
            "label\tot_tag\tcpu_layers\tthreads\tkv\tsplit_mode\tctx\tub\trun_index\tphase\trun\t"
            "eval_tps\tprompt_tps\tprompt_n\tpredicted_n\n"
        )
        for label, ctx, ub, thr, idx, note in CONDITIONS:
            for phase in ("warmup", "eval"):
                for k, d in enumerate(data[label][phase], start=1):
                    f.write(
                        f"{label}\t{OT_TAG}\t{CPU_LAYERS}\t{thr}\t{KV}\t{SM}\t{ctx}\t{ub}\t{idx}\t{phase}\t{k}\t"
                        f"{d.get('eval_tps')}\t{d.get('prompt_tps')}\t"
                        f"{d.get('prompt_n')}\t{d.get('predicted_n')}\n"
                    )
    print(f"[analyze] wrote {summary_path}")

    # 統計 CSV
    stats_path = SCRIPT_DIR / "phaseT5f_stats.csv"
    with stats_path.open("w") as f:
        f.write(
            "label,ot_tag,cpu_layers,threads,kv,split_mode,ctx,ub,run_index,metric,phase,n,mean,stdev,min,max,median,"
            "surpass_phase_d,surpass_phase_s,surpass_phase_t4,surpass_phase_t5,surpass_phase_t5e\n"
        )
        for label, ctx, ub, thr, idx, note in CONDITIONS:
            for metric in ("eval_tps", "prompt_tps"):
                for phase in ("warmup", "eval"):
                    vals = [d.get(metric) for d in data[label][phase]]
                    s = stats(vals)
                    if s is None:
                        f.write(
                            f"{label},{OT_TAG},{CPU_LAYERS},{thr},{KV},{SM},{ctx},{ub},{idx},"
                            f"{metric},{phase},0,,,,,,,,,,\n"
                        )
                        continue
                    is_eval_m = (metric == "eval_tps" and phase == "eval")
                    sd = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_D) else "no"
                    ss = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_S) else "no"
                    st4 = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T4_BEST) else "no"
                    st5 = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T5_BEST) else "no"
                    st5e = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T5E_BEST) else "no"
                    f.write(
                        f"{label},{OT_TAG},{CPU_LAYERS},{thr},{KV},{SM},{ctx},{ub},{idx},"
                        f"{metric},{phase},{s['n']},{s['mean']:.4f},{s['stdev']:.4f},"
                        f"{s['min']:.4f},{s['max']:.4f},{s['median']:.4f},"
                        f"{sd},{ss},{st4},{st5},{st5e}\n"
                    )
    print(f"[analyze] wrote {stats_path}")

    # Pivot Markdown
    pivot_path = SCRIPT_DIR / "phaseT5f_pivot.md"
    with pivot_path.open("w") as f:
        f.write("# Phase T-5f: B28 × ctx=32k × ub 微細スイープ + drift bracket pivot\n\n")
        f.write(f"- OT={OT_TAG} (CPU {CPU_LAYERS} 層), ctx=32k, KV={KV}, split-mode={SM}, threads=40, fa=1, numactl node1, poll=0\n")
        f.write(f"- warmup {WARMUP_RUNS} run + eval {EVAL_RUNS} run\n")
        f.write(
            f"- ベースライン: Phase D {PEAK_PHASE_D} / Phase S {PEAK_PHASE_S} / "
            f"T-4 {PEAK_PHASE_T4_BEST} / T-5 {PEAK_PHASE_T5_BEST} / **T-5e {PEAK_PHASE_T5E_BEST}** (t/s)\n\n"
        )

        # eval_tps 実行順
        f.write("## eval_tps 条件別 (実行順, mean±stdev, t/s)\n\n")
        f.write("| # | label | ub | 役割 | eval_mean±stdev | prompt_mean±stdev | 判定 |\n")
        f.write("|---|-------|----|------|----------------|-------------------|------|\n")
        eval_map = {}
        prompt_map = {}
        best_overall = None
        for label, ctx, ub, thr, idx, note in CONDITIONS:
            vs_e = [d.get("eval_tps") for d in data[label]["eval"]]
            vs_p = [d.get("prompt_tps") for d in data[label]["eval"]]
            se, sp = stats(vs_e), stats(vs_p)
            eval_map[label] = se
            prompt_map[label] = sp
            verd = verdict(se["mean"] if se else None)
            f.write(f"| {idx} | {label} | {ub} | {note} | {fmt_cell(se)} | {fmt_cell(sp)} | {verd} |\n")
            if se is not None and (best_overall is None or se["mean"] > best_overall[2]):
                best_overall = (label, ub, se["mean"])
        f.write("\n")

        # drift bracket
        f.write("## Session drift bracket (B28_32k_ub512a 起点 vs B28_32k_ub512z 終点)\n\n")
        s_a = eval_map.get("B28_32k_ub512a")
        s_z = eval_map.get("B28_32k_ub512z")
        if s_a and s_z:
            delta = s_z["mean"] - s_a["mean"]
            dpct = delta / s_a["mean"] * 100
            f.write("| label | 役割 | run_index | eval_mean | 起点比 |\n")
            f.write("|-------|------|-----------|-----------|--------|\n")
            f.write(f"| B28_32k_ub512a | drift 起点 | 1 | {s_a['mean']:.3f} | -- |\n")
            f.write(f"| B28_32k_ub512z | drift 終点 | 9 | {s_z['mean']:.3f} | {delta:+.3f} t/s ({dpct:+.2f}%) |\n\n")
            judge = "**drift 健全**" if abs(delta) < 0.3 else "**drift 大**"
            f.write(f"### drift 判定: {judge} (|差| {abs(delta):.3f} {'<' if abs(delta) < 0.3 else '≥'} 0.3 t/s 閾値)\n\n")

            # 線形 drift 補正 per_run = delta / (run_count - 1)
            run_count = max(idx for _, _, _, _, idx, _ in CONDITIONS)
            per_run_drift = delta / (run_count - 1)
            f.write(
                f"### drift 補正 (線形、per_run = (z - a) / ({run_count}-1) = {per_run_drift:+.4f} t/s/run)\n\n"
            )
            f.write("| # | label | ub | 実測 eval_mean | 補正後 eval_mean | 補正後 - T-5e best (16.380) |\n")
            f.write("|---|-------|----|----------------|------------------|-----------------------------|\n")
            corrected_map = {}
            for label, ctx, ub, thr, idx, note in CONDITIONS:
                s = eval_map.get(label)
                if s is None:
                    f.write(f"| {idx} | {label} | {ub} | no_data | -- | -- |\n")
                    continue
                corr = s["mean"] - per_run_drift * (idx - 1)
                corrected_map[label] = corr
                delta_t5e = corr - PEAK_PHASE_T5E_BEST
                star = " **★**" if delta_t5e > 0 else ""
                f.write(
                    f"| {idx} | {label} | {ub} | {s['mean']:.3f} | **{corr:.3f}**{star} | {delta_t5e:+.3f} |\n"
                )
            f.write("\n")

            # 補正後最良
            if corrected_map:
                best_corr = max(corrected_map.items(), key=lambda kv: kv[1])
                f.write(
                    f"**補正後最良**: {best_corr[0]} (corrected eval_mean = {best_corr[1]:.3f} t/s)\n\n"
                )
        else:
            f.write("(drift bracket データ不足、補正スキップ)\n\n")

        # ub trend (eval + prompt)
        f.write("## ub 1D trend (ub 降順ソート)\n\n")
        f.write("| ub | label | eval_mean | prompt_mean | eval_stdev | prompt_stdev |\n")
        f.write("|----|-------|-----------|-------------|------------|-------------|\n")
        ub_rows = []
        for label, ctx, ub, thr, idx, note in CONDITIONS:
            se = eval_map.get(label)
            sp = prompt_map.get(label)
            ub_rows.append((ub, label, se, sp))
        for ub, label, se, sp in sorted(ub_rows, key=lambda x: -x[0]):
            e_m = f"{se['mean']:.3f}" if se else "no_data"
            p_m = f"{sp['mean']:.3f}" if sp else "no_data"
            e_s = f"{se['stdev']:.3f}" if se else "--"
            p_s = f"{sp['stdev']:.3f}" if sp else "--"
            f.write(f"| {ub} | {label} | {e_m} | {p_m} | {e_s} | {p_s} |\n")
        f.write("\n")

        # Pareto (eval vs prompt)
        f.write("## eval/prompt Pareto (eval 降順)\n\n")
        f.write("| eval_rank | label | ub | eval_mean | prompt_mean |\n")
        f.write("|-----------|-------|----|-----------|-------------|\n")
        ranked = sorted(
            [(l, ub, eval_map[l], prompt_map[l]) for l, c, ub, t, i, n in CONDITIONS if eval_map.get(l)],
            key=lambda x: -x[2]["mean"],
        )
        for r, (l, ub, se, sp) in enumerate(ranked, start=1):
            p_m = f"{sp['mean']:.3f}" if sp else "--"
            f.write(f"| {r} | {l} | {ub} | {se['mean']:.3f} | {p_m} |\n")
        f.write("\n")

        # 結果サマリ
        f.write("## 結果サマリ\n\n")
        if best_overall:
            lbl_b, ub_b, m_b = best_overall
            f.write(f"- **最良 eval 構成 (実測)**: label={lbl_b} (ub={ub_b}, ctx=32k, OT=B28, threads=40), eval_mean={m_b:.3f} t/s\n")
            f.write(f"- **Phase T-5e ({PEAK_PHASE_T5E_BEST}) 超え**: {'**YES (新記録)**' if m_b > PEAK_PHASE_T5E_BEST else 'NO'}\n")
            f.write(f"- **Phase T-5 ({PEAK_PHASE_T5_BEST}) 超え**: {'YES' if m_b > PEAK_PHASE_T5_BEST else 'NO'}\n")
            f.write(f"- **Phase S ({PEAK_PHASE_S}) 超え**: {'YES' if m_b > PEAK_PHASE_S else 'NO'}\n")
            f.write(f"- **Phase D ({PEAK_PHASE_D}) 超え**: {'YES' if m_b > PEAK_PHASE_D else 'NO'}\n")
        else:
            f.write("- データ不足\n")
        f.write("\n")

        # 歴代 Phase 比較
        f.write("## Phase D / S / T-1..T-5 / T-5e / T-5f 全体比較\n\n")
        f.write("| Phase | 条件 (要点) | eval mean (t/s) | T-5f 最良との差 |\n")
        f.write("|-------|-------------|----------------|----------------|\n")
        ref_rows = [
            ("D", "threads=40, ub=1586, ctx=32k, OT=36 層", PEAK_PHASE_D),
            ("S", "ctx=65k, ub=512, threads=40, A36 (旧 #2)", PEAK_PHASE_S),
            ("T-1", "KV q8_0, ub=1586, threads=40", PEAK_PHASE_T1_Q8),
            ("T-2 best", "split=layer, q8_0, threads=40", PEAK_PHASE_T2_BEST),
            ("T-3 best", "threads=32, OT=A36", PEAK_PHASE_T3_BEST),
            ("T-4 best", "B32 × threads=40", PEAK_PHASE_T4_BEST),
            ("T-5 best", "B28 × threads=40, ctx=32k ub=1586", PEAK_PHASE_T5_BEST),
            ("T-5e best", "B28 × ctx=32k × ub=512 (直前歴代 #1)", PEAK_PHASE_T5E_BEST),
        ]
        m_b = best_overall[2] if best_overall else None
        for phase_lbl, cond, val in ref_rows:
            if m_b:
                d = (m_b - val) / val * 100
                f.write(f"| {phase_lbl} | {cond} | {val:.3f} | {d:+.2f}% |\n")
            else:
                f.write(f"| {phase_lbl} | {cond} | {val:.3f} | NA |\n")
        for label, ctx, ub, thr, idx, note in CONDITIONS:
            s = eval_map.get(label)
            if s is None:
                continue
            marker = " (**本 Phase 最良**)" if best_overall and best_overall[0] == label else ""
            if m_b:
                d_pct = (s["mean"] - m_b) / m_b * 100
                f.write(
                    f"| **T-5f** | {label} (ub={ub}, {note}){marker} | "
                    f"{s['mean']:.3f} | {d_pct:+.2f}% |\n"
                )
        f.write("\n")

    print(f"[analyze] wrote {pivot_path}")
    with pivot_path.open() as f:
        print(f.read())
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
