#!/usr/bin/env python3
"""analyze_phaseT5a-thr.py - Phase T-5a-thr: B18 × ub=256 × threads 再スイープ + drift bracket

9 条件の eval_tps / prompt_tps の mean/stdev/min/max を抽出し、
- threads 1D trend 表 (drift 補正前・補正後)
- session drift bracket (thr40a vs thr40z)
- drift 線形性検証 (thr40_mid が thr40a↔thr40z 線形予測から ±0.05 内)
- T-5a-ub baseline (18.103) との独立再現性
- T-3 dip 仮説 (CPU 層数 ≒ threads で eval dip) の B=18 再現性
- 歴代 Phase 比較
を CSV / Markdown で出力する。
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# CONDITIONS: (LABEL, THREADS, run_index, NOTE)
CONDITIONS = [
    ("thr40a",    40, 1, "drift 起点 (T-5a-ub B18_ub256=18.103 cross-session 再現性)"),
    ("thr14",     14, 2, "CPU 層数一致点 (T-3 dip 仮説の B=18 検証)"),
    ("thr20",     20, 3, "node1 物理コアフル、HT 境界"),
    ("thr28",     28, 4, "中間帯 (node1 HT 8 コア使用)"),
    ("thr32",     32, 5, "T-3 で最良、B=18 で再評価"),
    ("thr36",     36, 6, "T-3 で dip、B=18 再測定"),
    ("thr38",     38, 7, "node1 上端-2"),
    ("thr40_mid", 40, 8, "drift 線形性検証 (中央)"),
    ("thr40z",    40, 9, "drift 終点"),
]

OT_TAG = "B18"
CPU_LAYERS = 14  # B=18 は CPU 14 層 (layer 0-3, 24, 31-39)
KV = "q8_0"
SM = "layer"
CTX = 32768
UB = 256
WARMUP_RUNS = 2
EVAL_RUNS = 5

PEAK_PHASE_D = 15.03
PEAK_PHASE_S = 15.39
PEAK_PHASE_T1_Q8 = 15.016
PEAK_PHASE_T2_BEST = 14.672
PEAK_PHASE_T3_BEST = 14.860
PEAK_PHASE_T4_BEST = 15.494
PEAK_PHASE_T5_BEST = 16.024
PEAK_PHASE_T5E_BEST = 16.380
PEAK_PHASE_T5F_BEST = 16.455
PEAK_PHASE_T5A_BEST = 18.006
PEAK_PHASE_T5A_UB_BEST = 18.103  # T-5a-ub B18_ub256 (直前歴代 #1、実測)
PEAK_PHASE_T5A_UB_CORR = 18.209  # T-5a-ub drift 補正後 (参考)


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
    warmup_dir = SCRIPT_DIR / f"out_T5athr_{tag_cond}_warmup"
    eval_dir = SCRIPT_DIR / f"out_T5athr_{tag_cond}_1k"
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
    if mean_eval > PEAK_PHASE_T5A_UB_BEST:
        return f"**SURPASS_T5a-ub (歴代新記録)** ({mean_eval:.3f} > {PEAK_PHASE_T5A_UB_BEST})"
    if mean_eval > PEAK_PHASE_T5A_BEST:
        return f"surpass_T5a ({mean_eval:.3f} > {PEAK_PHASE_T5A_BEST})"
    if mean_eval > PEAK_PHASE_T5F_BEST:
        return f"surpass_T5f ({mean_eval:.3f} > {PEAK_PHASE_T5F_BEST})"
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
    for label, thr, idx, note in CONDITIONS:
        data[label] = collect(label, thr)

    # raw TSV
    summary_path = SCRIPT_DIR / "summary_phaseT5a-thr.tsv"
    with summary_path.open("w") as f:
        f.write(
            "label\tot_tag\tcpu_layers\tthreads\tkv\tsplit_mode\tctx\tub\trun_index\tphase\trun\t"
            "eval_tps\tprompt_tps\tprompt_n\tpredicted_n\n"
        )
        for label, thr, idx, note in CONDITIONS:
            for phase in ("warmup", "eval"):
                for k, d in enumerate(data[label][phase], start=1):
                    f.write(
                        f"{label}\t{OT_TAG}\t{CPU_LAYERS}\t{thr}\t{KV}\t{SM}\t{CTX}\t{UB}\t{idx}\t{phase}\t{k}\t"
                        f"{d.get('eval_tps')}\t{d.get('prompt_tps')}\t"
                        f"{d.get('prompt_n')}\t{d.get('predicted_n')}\n"
                    )
    print(f"[analyze] wrote {summary_path}")

    # 統計 CSV
    stats_path = SCRIPT_DIR / "phaseT5a-thr_stats.csv"
    with stats_path.open("w") as f:
        f.write(
            "label,ot_tag,cpu_layers,threads,kv,split_mode,ctx,ub,run_index,metric,phase,n,mean,stdev,min,max,median,"
            "surpass_phase_d,surpass_phase_s,surpass_phase_t4,surpass_phase_t5,surpass_phase_t5e,"
            "surpass_phase_t5f,surpass_phase_t5a,surpass_phase_t5a_ub\n"
        )
        for label, thr, idx, note in CONDITIONS:
            for metric in ("eval_tps", "prompt_tps"):
                for phase in ("warmup", "eval"):
                    vals = [d.get(metric) for d in data[label][phase]]
                    s = stats(vals)
                    if s is None:
                        f.write(
                            f"{label},{OT_TAG},{CPU_LAYERS},{thr},{KV},{SM},{CTX},{UB},{idx},"
                            f"{metric},{phase},0,,,,,,,,,,,,,\n"
                        )
                        continue
                    is_eval_m = (metric == "eval_tps" and phase == "eval")
                    sd = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_D) else "no"
                    ss = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_S) else "no"
                    st4 = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T4_BEST) else "no"
                    st5 = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T5_BEST) else "no"
                    st5e = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T5E_BEST) else "no"
                    st5f = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T5F_BEST) else "no"
                    st5a = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T5A_BEST) else "no"
                    st5aub = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T5A_UB_BEST) else "no"
                    f.write(
                        f"{label},{OT_TAG},{CPU_LAYERS},{thr},{KV},{SM},{CTX},{UB},{idx},"
                        f"{metric},{phase},{s['n']},{s['mean']:.4f},{s['stdev']:.4f},"
                        f"{s['min']:.4f},{s['max']:.4f},{s['median']:.4f},"
                        f"{sd},{ss},{st4},{st5},{st5e},{st5f},{st5a},{st5aub}\n"
                    )
    print(f"[analyze] wrote {stats_path}")

    # Pivot Markdown
    pivot_path = SCRIPT_DIR / "phaseT5a-thr_pivot.md"
    with pivot_path.open("w") as f:
        f.write("# Phase T-5a-thr: B18 × ub=256 × threads 再スイープ + drift bracket pivot\n\n")
        f.write(f"- OT={OT_TAG} (CPU {CPU_LAYERS} 層), ctx=32k, KV={KV}, split-mode={SM}, ub={UB}, fa=1, numactl node1, poll=0\n")
        f.write(f"- warmup {WARMUP_RUNS} run + eval {EVAL_RUNS} run\n")
        f.write(
            f"- ベースライン: Phase D {PEAK_PHASE_D} / S {PEAK_PHASE_S} / "
            f"T-4 {PEAK_PHASE_T4_BEST} / T-5 {PEAK_PHASE_T5_BEST} / "
            f"T-5e {PEAK_PHASE_T5E_BEST} / T-5f {PEAK_PHASE_T5F_BEST} / "
            f"T-5a {PEAK_PHASE_T5A_BEST} / "
            f"**T-5a-ub {PEAK_PHASE_T5A_UB_BEST}** (実測、補正後 {PEAK_PHASE_T5A_UB_CORR}) (t/s, 直前歴代 #1)\n\n"
        )

        # eval_tps 実行順
        f.write("## eval_tps 条件別 (実行順, mean±stdev, t/s)\n\n")
        f.write("| # | label | threads | 役割 | eval_mean±stdev | prompt_mean±stdev | 判定 |\n")
        f.write("|---|-------|---------|------|-----------------|-------------------|------|\n")
        eval_map = {}
        prompt_map = {}
        best_overall = None
        for label, thr, idx, note in CONDITIONS:
            vs_e = [d.get("eval_tps") for d in data[label]["eval"]]
            vs_p = [d.get("prompt_tps") for d in data[label]["eval"]]
            se, sp = stats(vs_e), stats(vs_p)
            eval_map[label] = se
            prompt_map[label] = sp
            verd = verdict(se["mean"] if se else None)
            f.write(f"| {idx} | {label} | {thr} | {note} | {fmt_cell(se)} | {fmt_cell(sp)} | {verd} |\n")
            if se is not None and (best_overall is None or se["mean"] > best_overall[2]):
                best_overall = (label, thr, se["mean"])
        f.write("\n")

        # drift bracket
        f.write("## Session drift bracket (thr40a 起点 vs thr40z 終点)\n\n")
        s_a = eval_map.get("thr40a")
        s_z = eval_map.get("thr40z")
        s_mid = eval_map.get("thr40_mid")
        if s_a and s_z:
            delta = s_z["mean"] - s_a["mean"]
            dpct = delta / s_a["mean"] * 100
            run_count = max(idx for _, _, idx, _ in CONDITIONS)
            f.write("| label | 役割 | run_index | eval_mean | 起点比 |\n")
            f.write("|-------|------|-----------|-----------|--------|\n")
            f.write(f"| thr40a | drift 起点 | 1 | {s_a['mean']:.3f} | -- |\n")
            if s_mid:
                mid_idx = next(idx for lbl, _, idx, _ in CONDITIONS if lbl == "thr40_mid")
                mid_delta = s_mid["mean"] - s_a["mean"]
                f.write(f"| thr40_mid | 中央線形性 | {mid_idx} | {s_mid['mean']:.3f} | {mid_delta:+.3f} t/s |\n")
            f.write(f"| thr40z | drift 終点 | {run_count} | {s_z['mean']:.3f} | {delta:+.3f} t/s ({dpct:+.2f}%) |\n\n")
            adelta = abs(delta)
            if adelta < 0.15:
                judge = "**drift 健全** (< 0.15 t/s)"
            elif adelta < 0.30:
                judge = "**drift 要注意** (0.15-0.30 t/s)"
            else:
                judge = "**drift 大** (≥ 0.30 t/s)"
            f.write(f"### drift 判定: {judge} (|差| = {adelta:.3f} t/s)\n\n")

            # drift 線形性検証 (thr40_mid)
            if s_mid:
                mid_idx = next(idx for lbl, _, idx, _ in CONDITIONS if lbl == "thr40_mid")
                per_run_drift = delta / (run_count - 1)
                predicted_mid = s_a["mean"] + per_run_drift * (mid_idx - 1)
                residual = s_mid["mean"] - predicted_mid
                linearity_ok = abs(residual) < 0.05
                f.write("### drift 線形性検証 (thr40_mid)\n\n")
                f.write(f"- 線形予測: thr40_mid_pred = thr40a + per_run_drift × (mid_idx - 1) = {s_a['mean']:.3f} + {per_run_drift:+.4f} × {mid_idx - 1} = **{predicted_mid:.3f} t/s**\n")
                f.write(f"- 実測: thr40_mid = **{s_mid['mean']:.3f} t/s**\n")
                f.write(f"- 残差: {residual:+.3f} t/s\n")
                f.write(f"- 判定: **{'線形性 OK (|残差| < 0.05)' if linearity_ok else '**線形性疑義 (|残差| ≥ 0.05)** — 補正手法の見直しを検討'}**\n\n")

            # T-5a-ub baseline 比較 (cross-session 再現性)
            t5aub_delta_a = s_a["mean"] - PEAK_PHASE_T5A_UB_BEST
            t5aub_delta_z = s_z["mean"] - PEAK_PHASE_T5A_UB_BEST
            f.write(f"### T-5a-ub baseline (B18 ub=256 = {PEAK_PHASE_T5A_UB_BEST}) との cross-session 再現性\n\n")
            f.write("| label | eval_mean | T-5a-ub baseline 差 | 判定 |\n")
            f.write("|-------|-----------|---------------------|------|\n")
            for lbl, sm, dd in (("thr40a", s_a, t5aub_delta_a), ("thr40z", s_z, t5aub_delta_z)):
                judg = "再現 (±0.5 内)" if abs(dd) <= 0.5 else ("**逸脱**" if abs(dd) > 1.0 else "やや逸脱")
                f.write(f"| {lbl} | {sm['mean']:.3f} | {dd:+.3f} | {judg} |\n")
            f.write("\n")

            # 線形 drift 補正 per_run = delta / (run_count - 1)
            per_run_drift = delta / (run_count - 1)
            f.write(
                f"### drift 補正 (線形、per_run = (z - a) / ({run_count}-1) = {per_run_drift:+.4f} t/s/run)\n\n"
            )
            f.write("| # | label | threads | 実測 eval_mean | 補正後 eval_mean | 補正後 - T-5a-ub (18.103) | 補正後 - T-5a (18.006) |\n")
            f.write("|---|-------|---------|----------------|------------------|---------------------------|------------------------|\n")
            corrected_map = {}
            for label, thr, idx, note in CONDITIONS:
                s = eval_map.get(label)
                if s is None:
                    f.write(f"| {idx} | {label} | {thr} | no_data | -- | -- | -- |\n")
                    continue
                corr = s["mean"] - per_run_drift * (idx - 1)
                corrected_map[label] = corr
                delta_t5aub = corr - PEAK_PHASE_T5A_UB_BEST
                delta_t5a = corr - PEAK_PHASE_T5A_BEST
                star = " **★**" if delta_t5aub > 0 else ""
                f.write(
                    f"| {idx} | {label} | {thr} | {s['mean']:.3f} | **{corr:.3f}**{star} | {delta_t5aub:+.3f} | {delta_t5a:+.3f} |\n"
                )
            f.write("\n")

            # 補正後最良
            if corrected_map:
                best_corr = max(corrected_map.items(), key=lambda kv: kv[1])
                f.write(
                    f"**補正後最良**: {best_corr[0]} (corrected eval_mean = {best_corr[1]:.3f} t/s, "
                    f"T-5a-ub 比 {best_corr[1]-PEAK_PHASE_T5A_UB_BEST:+.3f} t/s)\n\n"
                )
        else:
            f.write("(drift bracket データ不足、補正スキップ)\n\n")

        # threads trend
        f.write("## threads 1D trend (threads 昇順)\n\n")
        f.write("| threads | label | eval_mean | prompt_mean | eval_stdev | prompt_stdev | 役割 |\n")
        f.write("|---------|-------|-----------|-------------|------------|--------------|------|\n")
        thr_rows = []
        for label, thr, idx, note in CONDITIONS:
            se = eval_map.get(label)
            sp = prompt_map.get(label)
            thr_rows.append((thr, label, se, sp, note))
        for thr, label, se, sp, note in sorted(thr_rows, key=lambda x: (x[0], x[1])):
            e_m = f"{se['mean']:.3f}" if se else "no_data"
            p_m = f"{sp['mean']:.3f}" if sp else "no_data"
            e_s = f"{se['stdev']:.3f}" if se else "--"
            p_s = f"{sp['stdev']:.3f}" if sp else "--"
            f.write(f"| {thr} | {label} | {e_m} | {p_m} | {e_s} | {p_s} | {note} |\n")
        f.write("\n")

        # T-3 dip 仮説検証 (CPU 層数 ≒ threads で eval dip)
        f.write("## T-3 dip 仮説の B=18 (CPU 14 層) 再現性\n\n")
        f.write("T-3 (OT=A36、CPU 36 層) では threads=36 で -2.08% dip が観測された。\n")
        f.write("本 Phase (B=18、CPU 14 層) では threads=14 で同様の dip が出るかを検証する。\n\n")
        f.write("| threads | label | eval_mean | threads=40 比 | dip 該当? |\n")
        f.write("|---------|-------|-----------|---------------|-----------|\n")
        ref = eval_map.get("thr40a")
        ref_mean = ref["mean"] if ref else None
        for label, thr, idx, note in sorted(CONDITIONS, key=lambda x: x[1]):
            s = eval_map.get(label)
            if not s:
                continue
            if ref_mean:
                rel = (s["mean"] - ref_mean) / ref_mean * 100
                dip_flag = "**YES (dip)**" if rel < -1.0 else ("やや低下" if rel < -0.3 else "同等+")
            else:
                rel = None
                dip_flag = "no_ref"
            rel_s = f"{rel:+.2f}%" if rel is not None else "--"
            f.write(f"| {thr} | {label} | {s['mean']:.3f} | {rel_s} | {dip_flag} |\n")
        f.write("\n")

        # 結果サマリ
        f.write("## 結果サマリ\n\n")
        if best_overall:
            lbl_b, thr_b, m_b = best_overall
            f.write(f"- **最良 eval 構成 (実測)**: label={lbl_b} (threads={thr_b}, ub={UB}, ctx=32k, OT=B18), eval_mean={m_b:.3f} t/s\n")
            f.write(f"- **Phase T-5a-ub ({PEAK_PHASE_T5A_UB_BEST}) 超え**: {'**YES (歴代新記録)**' if m_b > PEAK_PHASE_T5A_UB_BEST else 'NO'}\n")
            f.write(f"- **Phase T-5a ({PEAK_PHASE_T5A_BEST}) 超え**: {'YES' if m_b > PEAK_PHASE_T5A_BEST else 'NO'}\n")
            f.write(f"- **Phase T-5f ({PEAK_PHASE_T5F_BEST}) 超え**: {'YES' if m_b > PEAK_PHASE_T5F_BEST else 'NO'}\n")
            f.write(f"- **Phase T-5e ({PEAK_PHASE_T5E_BEST}) 超え**: {'YES' if m_b > PEAK_PHASE_T5E_BEST else 'NO'}\n")
            f.write(f"- **Phase T-5 ({PEAK_PHASE_T5_BEST}) 超え**: {'YES' if m_b > PEAK_PHASE_T5_BEST else 'NO'}\n")
            f.write(f"- **Phase S ({PEAK_PHASE_S}) 超え**: {'YES' if m_b > PEAK_PHASE_S else 'NO'}\n")
            f.write(f"- **Phase D ({PEAK_PHASE_D}) 超え**: {'YES' if m_b > PEAK_PHASE_D else 'NO'}\n")
        else:
            f.write("- データ不足\n")
        f.write("\n")

        # 歴代 Phase 比較
        f.write("## Phase D / S / T-1..T-5 / T-5e / T-5f / T-5a / T-5a-ub / T-5a-thr 全体比較\n\n")
        f.write("| Phase | 条件 (要点) | eval mean (t/s) | T-5a-thr 最良との差 |\n")
        f.write("|-------|-------------|-----------------|---------------------|")
        f.write("\n")
        ref_rows = [
            ("D", "threads=40, ub=1586, ctx=32k, OT=36 層", PEAK_PHASE_D),
            ("S", "ctx=65k, ub=512, threads=40, A36", PEAK_PHASE_S),
            ("T-1", "KV q8_0, ub=1586, threads=40", PEAK_PHASE_T1_Q8),
            ("T-2 best", "split=layer, q8_0, threads=40", PEAK_PHASE_T2_BEST),
            ("T-3 best", "threads=32, OT=A36", PEAK_PHASE_T3_BEST),
            ("T-4 best", "B32 × threads=40", PEAK_PHASE_T4_BEST),
            ("T-5 best", "B28 × threads=40, ub=1586", PEAK_PHASE_T5_BEST),
            ("T-5e best", "B28 × ctx=32k × ub=512", PEAK_PHASE_T5E_BEST),
            ("T-5f best", "B28 × ctx=32k × ub=512 (補正後)", PEAK_PHASE_T5F_BEST),
            ("T-5a best", "B18 × ctx=32k × ub=512 × threads=40", PEAK_PHASE_T5A_BEST),
            ("T-5a-ub best", "B18 × ctx=32k × ub=256 × threads=40 (実測、直前歴代 #1)", PEAK_PHASE_T5A_UB_BEST),
        ]
        m_b = best_overall[2] if best_overall else None
        for phase_lbl, cond, val in ref_rows:
            if m_b:
                d = (m_b - val) / val * 100
                f.write(f"| {phase_lbl} | {cond} | {val:.3f} | {d:+.2f}% |\n")
            else:
                f.write(f"| {phase_lbl} | {cond} | {val:.3f} | NA |\n")
        for label, thr, idx, note in CONDITIONS:
            s = eval_map.get(label)
            if s is None:
                continue
            marker = " (**本 Phase 最良**)" if best_overall and best_overall[0] == label else ""
            if m_b:
                d_pct = (s["mean"] - m_b) / m_b * 100
                f.write(
                    f"| **T-5a-thr** | {label} (threads={thr}, {note}){marker} | "
                    f"{s['mean']:.3f} | {d_pct:+.2f}% |\n"
                )
        f.write("\n")

    print(f"[analyze] wrote {pivot_path}")
    with pivot_path.open() as f:
        print(f.read())
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
