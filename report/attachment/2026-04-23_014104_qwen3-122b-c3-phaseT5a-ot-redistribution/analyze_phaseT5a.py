#!/usr/bin/env python3
"""analyze_phaseT5a.py - Phase T-5a: OT 再配分 (B28/B24/B20/B18) × ub=512 × drift bracket 集計

7 条件の eval_tps / prompt_tps の mean/stdev/min/max を抽出し、
- CPU 層数 (B-number) 1D trend 表 (drift 補正前・補正後)
- session drift bracket (B28_run1 vs B28_run2)
- OT 別 run_index ごとの再現性表 (B20_run1/B20_run2, B24_run1/B24_run2)
- 歴代 Phase 比較 (T-5f 16.455 を baseline)
を CSV / Markdown で出力する。
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# CONDITIONS: (LABEL, CTX, UB, OT_TAG, CPU_LAYERS, THREADS, run_index, NOTE)
# batch_phaseT5a.sh の実行順と一致させる
CONDITIONS = [
    ("B28_run1", 32768, 512, "B28", 28, 40, 1, "drift 起点 (T-5f 16.455 再現確認)"),
    ("B24_run1", 32768, 512, "B24", 24, 40, 2, "+4 層 GPU 戻し (layer 10-13)"),
    ("B20_run1", 32768, 512, "B20", 20, 40, 3, "+8 層 (layer 6-13、境界付近)"),
    ("B18_run1", 32768, 512, "B18", 18, 40, 4, "+10 層 (layer 4-13、OOM 境界テスト)"),
    ("B20_run2", 32768, 512, "B20", 20, 40, 5, "B20 再現性"),
    ("B24_run2", 32768, 512, "B24", 24, 40, 6, "B24 再現性"),
    ("B28_run2", 32768, 512, "B28", 28, 40, 7, "drift 終点"),
]

KV = "q8_0"
SM = "layer"
WARMUP_RUNS = 2
EVAL_RUNS = 5

# 歴代 Phase ベースライン
PEAK_PHASE_D = 15.03
PEAK_PHASE_S = 15.39
PEAK_PHASE_T1_Q8 = 15.016
PEAK_PHASE_T2_BEST = 14.672
PEAK_PHASE_T3_BEST = 14.860
PEAK_PHASE_T4_BEST = 15.494
PEAK_PHASE_T5_BEST = 16.024
PEAK_PHASE_T5E_BEST = 16.380
PEAK_PHASE_T5F_BEST = 16.455  # T-5f B28_32k_ub512a (直前歴代最高)


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


def collect(label: str, ot_tag: str, ctx: int, ub: int, thr: int) -> dict:
    # batch_phaseT5a.sh の TAG_COND 命名に合わせる
    tag_cond = f"{label}_{ot_tag}_t{thr}_kv{KV}_sm{SM}_ctx{ctx}_ub{ub}"
    warmup_dir = SCRIPT_DIR / f"out_T5a_{tag_cond}_warmup"
    eval_dir = SCRIPT_DIR / f"out_T5a_{tag_cond}_1k"
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
    if mean_eval > PEAK_PHASE_T5F_BEST:
        return f"**SURPASS_T5f** ({mean_eval:.3f} > {PEAK_PHASE_T5F_BEST})"
    if mean_eval > PEAK_PHASE_T5E_BEST:
        return f"surpass_T5e ({mean_eval:.3f} > {PEAK_PHASE_T5E_BEST})"
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
    for label, ctx, ub, ot, cpu_l, thr, idx, note in CONDITIONS:
        data[label] = collect(label, ot, ctx, ub, thr)

    # raw TSV
    summary_path = SCRIPT_DIR / "summary_phaseT5a.tsv"
    with summary_path.open("w") as f:
        f.write(
            "label\tot_tag\tcpu_layers\tthreads\tkv\tsplit_mode\tctx\tub\trun_index\tphase\trun\t"
            "eval_tps\tprompt_tps\tprompt_n\tpredicted_n\n"
        )
        for label, ctx, ub, ot, cpu_l, thr, idx, note in CONDITIONS:
            for phase in ("warmup", "eval"):
                for k, d in enumerate(data[label][phase], start=1):
                    f.write(
                        f"{label}\t{ot}\t{cpu_l}\t{thr}\t{KV}\t{SM}\t{ctx}\t{ub}\t{idx}\t{phase}\t{k}\t"
                        f"{d.get('eval_tps')}\t{d.get('prompt_tps')}\t"
                        f"{d.get('prompt_n')}\t{d.get('predicted_n')}\n"
                    )
    print(f"[analyze] wrote {summary_path}")

    # 統計 CSV
    stats_path = SCRIPT_DIR / "phaseT5a_stats.csv"
    with stats_path.open("w") as f:
        f.write(
            "label,ot_tag,cpu_layers,threads,kv,split_mode,ctx,ub,run_index,metric,phase,n,mean,stdev,min,max,median,"
            "surpass_phase_d,surpass_phase_s,surpass_phase_t4,surpass_phase_t5,surpass_phase_t5e,surpass_phase_t5f\n"
        )
        for label, ctx, ub, ot, cpu_l, thr, idx, note in CONDITIONS:
            for metric in ("eval_tps", "prompt_tps"):
                for phase in ("warmup", "eval"):
                    vals = [d.get(metric) for d in data[label][phase]]
                    s = stats(vals)
                    if s is None:
                        f.write(
                            f"{label},{ot},{cpu_l},{thr},{KV},{SM},{ctx},{ub},{idx},"
                            f"{metric},{phase},0,,,,,,,,,,,\n"
                        )
                        continue
                    is_eval_m = (metric == "eval_tps" and phase == "eval")
                    sd = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_D) else "no"
                    ss = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_S) else "no"
                    st4 = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T4_BEST) else "no"
                    st5 = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T5_BEST) else "no"
                    st5e = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T5E_BEST) else "no"
                    st5f = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T5F_BEST) else "no"
                    f.write(
                        f"{label},{ot},{cpu_l},{thr},{KV},{SM},{ctx},{ub},{idx},"
                        f"{metric},{phase},{s['n']},{s['mean']:.4f},{s['stdev']:.4f},"
                        f"{s['min']:.4f},{s['max']:.4f},{s['median']:.4f},"
                        f"{sd},{ss},{st4},{st5},{st5e},{st5f}\n"
                    )
    print(f"[analyze] wrote {stats_path}")

    # Pivot Markdown
    pivot_path = SCRIPT_DIR / "phaseT5a_pivot.md"
    with pivot_path.open("w") as f:
        f.write("# Phase T-5a: OT 再配分 (B28/B24/B20/B18) × ub=512 + drift bracket pivot\n\n")
        f.write(f"- ctx=32k, ub=512, KV={KV}, split-mode={SM}, threads=40, fa=1, numactl node1, poll=0\n")
        f.write(f"- warmup {WARMUP_RUNS} run + eval {EVAL_RUNS} run\n")
        f.write(
            f"- ベースライン: Phase D {PEAK_PHASE_D} / Phase S {PEAK_PHASE_S} / "
            f"T-4 {PEAK_PHASE_T4_BEST} / T-5 {PEAK_PHASE_T5_BEST} / "
            f"T-5e {PEAK_PHASE_T5E_BEST} / **T-5f {PEAK_PHASE_T5F_BEST}** (t/s)\n\n"
        )

        # eval_tps 実行順
        f.write("## eval_tps 条件別 (実行順, mean±stdev, t/s)\n\n")
        f.write("| # | label | OT | CPU 層 | 役割 | eval_mean±stdev | prompt_mean±stdev | 判定 |\n")
        f.write("|---|-------|----|-------|------|----------------|-------------------|------|\n")
        eval_map = {}
        prompt_map = {}
        best_overall = None
        for label, ctx, ub, ot, cpu_l, thr, idx, note in CONDITIONS:
            vs_e = [d.get("eval_tps") for d in data[label]["eval"]]
            vs_p = [d.get("prompt_tps") for d in data[label]["eval"]]
            se, sp = stats(vs_e), stats(vs_p)
            eval_map[label] = se
            prompt_map[label] = sp
            verd = verdict(se["mean"] if se else None)
            f.write(f"| {idx} | {label} | {ot} | {cpu_l} | {note} | {fmt_cell(se)} | {fmt_cell(sp)} | {verd} |\n")
            if se is not None and (best_overall is None or se["mean"] > best_overall[3]):
                best_overall = (label, ot, cpu_l, se["mean"])
        f.write("\n")

        # drift bracket (B28_run1 vs B28_run2)
        f.write("## Session drift bracket (B28_run1 起点 vs B28_run2 終点)\n\n")
        s_a = eval_map.get("B28_run1")
        s_z = eval_map.get("B28_run2")
        if s_a and s_z:
            delta = s_z["mean"] - s_a["mean"]
            dpct = delta / s_a["mean"] * 100
            f.write("| label | 役割 | run_index | eval_mean | 起点比 |\n")
            f.write("|-------|------|-----------|-----------|--------|\n")
            f.write(f"| B28_run1 | drift 起点 | 1 | {s_a['mean']:.3f} | -- |\n")
            f.write(f"| B28_run2 | drift 終点 | 7 | {s_z['mean']:.3f} | {delta:+.3f} t/s ({dpct:+.2f}%) |\n\n")
            judge = (
                "**drift 健全**" if abs(delta) < 0.15 else
                "**drift 要注意**" if abs(delta) < 0.3 else "**drift 大**"
            )
            f.write(f"### drift 判定: {judge} (|差| {abs(delta):.3f} vs 閾値 0.15/0.3 t/s)\n\n")

            # 線形 drift 補正 per_run = delta / (last_idx - first_idx)
            run_count = max(idx for _, _, _, _, _, _, idx, _ in CONDITIONS)
            per_run_drift = delta / (run_count - 1)
            f.write(
                f"### drift 補正 (線形、per_run = (end - start) / ({run_count}-1) = {per_run_drift:+.4f} t/s/run)\n\n"
            )
            f.write("| # | label | OT | CPU 層 | 実測 eval_mean | 補正後 eval_mean | 補正後 - T-5f best (16.455) |\n")
            f.write("|---|-------|----|-------|----------------|------------------|-----------------------------|\n")
            corrected_map = {}
            for label, ctx, ub, ot, cpu_l, thr, idx, note in CONDITIONS:
                s = eval_map.get(label)
                if s is None:
                    f.write(f"| {idx} | {label} | {ot} | {cpu_l} | no_data | -- | -- |\n")
                    continue
                corr = s["mean"] - per_run_drift * (idx - 1)
                corrected_map[label] = corr
                delta_t5f = corr - PEAK_PHASE_T5F_BEST
                star = " **★**" if delta_t5f > 0 else ""
                f.write(
                    f"| {idx} | {label} | {ot} | {cpu_l} | {s['mean']:.3f} | **{corr:.3f}**{star} | {delta_t5f:+.3f} |\n"
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

        # CPU 層数 1D trend (OT 単位で集約、同一 OT の 2 run 平均)
        f.write("## CPU 層数 1D trend (OT 別 mean, run#1/run#2 平均)\n\n")
        f.write("| CPU 層 | OT | eval_mean (avg) | prompt_mean (avg) | eval_stdev (max) | N run |\n")
        f.write("|--------|----|-----------------|-------------------|-------------------|-------|\n")
        ot_groups = {}  # ot_tag -> [(cpu_l, label, se, sp), ...]
        for label, ctx, ub, ot, cpu_l, thr, idx, note in CONDITIONS:
            se = eval_map.get(label)
            sp = prompt_map.get(label)
            ot_groups.setdefault((cpu_l, ot), []).append((label, se, sp))
        # cpu_l 降順 (B28→B18)
        for (cpu_l, ot), rows in sorted(ot_groups.items(), key=lambda x: -x[0][0]):
            e_means = [r[1]["mean"] for r in rows if r[1]]
            p_means = [r[2]["mean"] for r in rows if r[2]]
            e_stds = [r[1]["stdev"] for r in rows if r[1]]
            if e_means:
                em = statistics.mean(e_means)
                pm = statistics.mean(p_means) if p_means else 0
                es = max(e_stds) if e_stds else 0
                f.write(f"| {cpu_l} | {ot} | {em:.3f} | {pm:.3f} | {es:.3f} | {len(e_means)} |\n")
            else:
                f.write(f"| {cpu_l} | {ot} | no_data | -- | -- | 0 |\n")
        f.write("\n")

        # OT 別再現性 (run#1/run#2 比較)
        f.write("## OT 別再現性 (run#1 vs run#2)\n\n")
        f.write("| OT | run#1 label | run#1 eval | run#2 label | run#2 eval | 差 (run#2 - run#1) |\n")
        f.write("|----|-------------|-----------|-------------|-----------|---------------------|\n")
        pairs = [
            ("B28", "B28_run1", "B28_run2"),
            ("B24", "B24_run1", "B24_run2"),
            ("B20", "B20_run1", "B20_run2"),
            ("B18", "B18_run1", None),
        ]
        for ot, l1, l2 in pairs:
            s1 = eval_map.get(l1)
            s2 = eval_map.get(l2) if l2 else None
            m1 = f"{s1['mean']:.3f}" if s1 else "no_data"
            m2 = f"{s2['mean']:.3f}" if s2 else ("--" if l2 is None else "no_data")
            d = (
                f"{s2['mean'] - s1['mean']:+.3f}"
                if (s1 and s2) else "--"
            )
            f.write(f"| {ot} | {l1} | {m1} | {l2 or '(1 run のみ)'} | {m2} | {d} |\n")
        f.write("\n")

        # Pareto (eval vs prompt) — 全条件
        f.write("## eval/prompt Pareto (eval 降順)\n\n")
        f.write("| eval_rank | label | OT | CPU 層 | eval_mean | prompt_mean |\n")
        f.write("|-----------|-------|----|-------|-----------|-------------|\n")
        ranked = sorted(
            [(l, ot, cpu_l, eval_map[l], prompt_map[l])
             for l, c, ub, ot, cpu_l, t, i, n in CONDITIONS
             if eval_map.get(l)],
            key=lambda x: -x[3]["mean"],
        )
        for r, (l, ot, cpu_l, se, sp) in enumerate(ranked, start=1):
            p_m = f"{sp['mean']:.3f}" if sp else "--"
            f.write(f"| {r} | {l} | {ot} | {cpu_l} | {se['mean']:.3f} | {p_m} |\n")
        f.write("\n")

        # 結果サマリ
        f.write("## 結果サマリ\n\n")
        if best_overall:
            lbl_b, ot_b, cpu_b, m_b = best_overall
            f.write(f"- **最良 eval 構成 (実測)**: label={lbl_b} (OT={ot_b}, CPU {cpu_b} 層, ctx=32k, ub=512, threads=40), eval_mean={m_b:.3f} t/s\n")
            f.write(f"- **Phase T-5f ({PEAK_PHASE_T5F_BEST}) 超え**: {'**YES (歴代新記録)**' if m_b > PEAK_PHASE_T5F_BEST else 'NO'}\n")
            f.write(f"- **Phase T-5e ({PEAK_PHASE_T5E_BEST}) 超え**: {'YES' if m_b > PEAK_PHASE_T5E_BEST else 'NO'}\n")
            f.write(f"- **Phase T-5 ({PEAK_PHASE_T5_BEST}) 超え**: {'YES' if m_b > PEAK_PHASE_T5_BEST else 'NO'}\n")
            f.write(f"- **Phase D ({PEAK_PHASE_D}) 超え**: {'YES' if m_b > PEAK_PHASE_D else 'NO'} ({(m_b - PEAK_PHASE_D)/PEAK_PHASE_D*100:+.2f}%)\n")
        else:
            f.write("- データ不足\n")
        f.write("\n")

        # 歴代 Phase 比較
        f.write("## Phase D / S / T-1..T-5 / T-5e / T-5f / T-5a 全体比較\n\n")
        f.write("| Phase | 条件 (要点) | eval mean (t/s) | T-5a 最良との差 |\n")
        f.write("|-------|-------------|----------------|----------------|\n")
        ref_rows = [
            ("D", "threads=40, ub=1586, ctx=32k, OT=36 層", PEAK_PHASE_D),
            ("S", "ctx=65k, ub=512, threads=40, A36", PEAK_PHASE_S),
            ("T-1", "KV q8_0, ub=1586, threads=40", PEAK_PHASE_T1_Q8),
            ("T-2 best", "split=layer, q8_0, threads=40", PEAK_PHASE_T2_BEST),
            ("T-3 best", "threads=32, OT=A36", PEAK_PHASE_T3_BEST),
            ("T-4 best", "B32 × threads=40", PEAK_PHASE_T4_BEST),
            ("T-5 best", "B28 × threads=40, ctx=32k ub=1586", PEAK_PHASE_T5_BEST),
            ("T-5e best", "B28 × ctx=32k × ub=512", PEAK_PHASE_T5E_BEST),
            ("T-5f best", "B28 × ctx=32k × ub=512 (T-5e 更新)", PEAK_PHASE_T5F_BEST),
        ]
        m_b = best_overall[3] if best_overall else None
        for phase_lbl, cond, val in ref_rows:
            if m_b:
                d = (m_b - val) / val * 100
                f.write(f"| {phase_lbl} | {cond} | {val:.3f} | {d:+.2f}% |\n")
            else:
                f.write(f"| {phase_lbl} | {cond} | {val:.3f} | NA |\n")
        for label, ctx, ub, ot, cpu_l, thr, idx, note in CONDITIONS:
            s = eval_map.get(label)
            if s is None:
                continue
            marker = " (**本 Phase 最良**)" if best_overall and best_overall[0] == label else ""
            if m_b:
                d_pct = (s["mean"] - m_b) / m_b * 100
                f.write(
                    f"| **T-5a** | {label} (OT={ot}, CPU {cpu_l} 層, {note}){marker} | "
                    f"{s['mean']:.3f} | {d_pct:+.2f}% |\n"
                )
        f.write("\n")

    print(f"[analyze] wrote {pivot_path}")
    with pivot_path.open() as f:
        print(f.read())
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
