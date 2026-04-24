#!/usr/bin/env python3
"""analyze_phaseT3.py - Phase T-3: threads 中間値スイープ集計

THREADS {24, 28, 32, 36, 40} × KV=q8_0 × split=layer × ub=1586 の 5 条件から
eval_tps / prompt_tps の mean/stdev/min/max を抽出し、
pivot 比較表 (行 = threads) を CSV + Markdown で出力する。
Phase D (15.03) / Phase S (15.39) / Phase T-1 q8_0 (15.016) / Phase T-2 最良 (14.672) 超え判定を付記。
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

THREADS_LIST = [24, 28, 32, 36, 40]
KV = "q8_0"
SM = "layer"
UB = 1586
CTX = 32768
WARMUP_RUNS = 2
EVAL_RUNS = 5

PEAK_PHASE_D = 15.03
PEAK_PHASE_S = 15.39
PEAK_PHASE_T1_Q8 = 15.016  # Phase T-1 最良 (q8_0 ub=1586, split=layer, threads=40)
PEAK_PHASE_T2_BEST = 14.672  # Phase T-2 最良 (q8_0 ub=1586, split=layer, threads=40)


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


def collect(thr: int) -> dict:
    tag_cond = f"t{thr}_kv{KV}_sm{SM}_ctx{CTX}_ub{UB}"
    warmup_dir = SCRIPT_DIR / f"out_T3_{tag_cond}_warmup"
    eval_dir = SCRIPT_DIR / f"out_T3_{tag_cond}_1k"

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
    if mean_eval > PEAK_PHASE_S:
        return f"SURPASS_S ({mean_eval:.3f} > {PEAK_PHASE_S})"
    if mean_eval > PEAK_PHASE_D:
        return f"surpass_D ({mean_eval:.3f} > {PEAK_PHASE_D})"
    if mean_eval > PEAK_PHASE_T1_Q8:
        return f"surpass_T1_q8 ({mean_eval:.3f} > {PEAK_PHASE_T1_Q8})"
    if mean_eval > PEAK_PHASE_T2_BEST:
        return f"surpass_T2 ({mean_eval:.3f} > {PEAK_PHASE_T2_BEST})"
    return f"below_T2 ({mean_eval:.3f} ≤ {PEAK_PHASE_T2_BEST})"


def main() -> int:
    data: dict = {}
    for thr in THREADS_LIST:
        data[thr] = collect(thr)

    # raw TSV
    summary_path = SCRIPT_DIR / "summary_phaseT3.tsv"
    with summary_path.open("w") as f:
        f.write("threads\tkv\tsplit_mode\tub\tphase\trun\teval_tps\tprompt_tps\tprompt_n\tpredicted_n\n")
        for thr in THREADS_LIST:
            for phase in ("warmup", "eval"):
                for idx, d in enumerate(data[thr][phase], start=1):
                    f.write(
                        f"{thr}\t{KV}\t{SM}\t{UB}\t{phase}\t{idx}\t"
                        f"{d.get('eval_tps')}\t{d.get('prompt_tps')}\t"
                        f"{d.get('prompt_n')}\t{d.get('predicted_n')}\n"
                    )
    print(f"[analyze] wrote {summary_path}")

    # 統計 CSV
    stats_path = SCRIPT_DIR / "phaseT3_stats.csv"
    with stats_path.open("w") as f:
        f.write(
            "threads,kv,split_mode,ub,metric,phase,n,mean,stdev,min,max,median,"
            "surpass_phase_d,surpass_phase_s,surpass_phase_t1_q8,surpass_phase_t2\n"
        )
        for thr in THREADS_LIST:
            for metric in ("eval_tps", "prompt_tps"):
                for phase in ("warmup", "eval"):
                    vals = [d.get(metric) for d in data[thr][phase]]
                    s = stats(vals)
                    if s is None:
                        f.write(f"{thr},{KV},{SM},{UB},{metric},{phase},0,,,,,,,,,\n")
                        continue
                    is_eval_m = (metric == "eval_tps" and phase == "eval")
                    sd = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_D) else "no"
                    ss = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_S) else "no"
                    st1 = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T1_Q8) else "no"
                    st2 = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T2_BEST) else "no"
                    f.write(
                        f"{thr},{KV},{SM},{UB},{metric},{phase},{s['n']},{s['mean']:.4f},{s['stdev']:.4f},"
                        f"{s['min']:.4f},{s['max']:.4f},{s['median']:.4f},{sd},{ss},{st1},{st2}\n"
                    )
    print(f"[analyze] wrote {stats_path}")

    # pivot Markdown
    pivot_path = SCRIPT_DIR / "phaseT3_pivot.md"
    with pivot_path.open("w") as f:
        f.write("# Phase T-3: threads 中間値スイープ pivot 比較表\n\n")
        f.write(f"- KV={KV}, split-mode={SM}, ctx={CTX}, ub={UB}, fa=1, numactl node1, OT=MoE only, poll=0\n")
        f.write(f"- warmup {WARMUP_RUNS} run + eval {EVAL_RUNS} run\n")
        f.write(
            f"- ベースライン: Phase D {PEAK_PHASE_D} / Phase S {PEAK_PHASE_S} / "
            f"Phase T-1 q8_0 {PEAK_PHASE_T1_Q8} / Phase T-2 最良 {PEAK_PHASE_T2_BEST} (t/s)\n\n"
        )

        # eval_tps pivot (行=threads)
        f.write("## eval_tps (mean±stdev, t/s) — eval フェーズ 5 run\n\n")
        f.write("| threads | eval mean±stdev | eval min | eval max | vs threads=40 | 判定 |\n")
        f.write("|---------|-----------------|----------|----------|---------------|------|\n")
        # baseline threads=40 の eval mean
        vals_40 = [d.get("eval_tps") for d in data.get(40, {}).get("eval", [])]
        s_40 = stats(vals_40)
        best_overall = None
        for thr in THREADS_LIST:
            vals = [d.get("eval_tps") for d in data[thr]["eval"]]
            s = stats(vals)
            cell = fmt_cell(s)
            vs40 = "NA"
            if s is not None and s_40 is not None and s_40["mean"] > 0:
                delta_pct = (s["mean"] - s_40["mean"]) / s_40["mean"] * 100
                vs40 = f"{delta_pct:+.2f}%"
            if s is not None:
                v = verdict(s["mean"])
                if best_overall is None or s["mean"] > best_overall[1]:
                    best_overall = (thr, s["mean"])
                mn = f"{s['min']:.3f}"
                mx = f"{s['max']:.3f}"
            else:
                v = "no_data"
                mn = "NA"
                mx = "NA"
            f.write(f"| {thr} | {cell} | {mn} | {mx} | {vs40} | {v} |\n")
        f.write("\n")

        # prompt_tps pivot
        f.write("## prompt_tps (mean±stdev, t/s) — eval フェーズ 5 run\n\n")
        f.write("| threads | prompt mean±stdev | vs threads=40 |\n")
        f.write("|---------|-------------------|---------------|\n")
        vals_40_p = [d.get("prompt_tps") for d in data.get(40, {}).get("eval", [])]
        s_40_p = stats(vals_40_p)
        for thr in THREADS_LIST:
            vals = [d.get("prompt_tps") for d in data[thr]["eval"]]
            s = stats(vals)
            cell = fmt_cell(s)
            vs40 = "NA"
            if s is not None and s_40_p is not None and s_40_p["mean"] > 0:
                delta_pct = (s["mean"] - s_40_p["mean"]) / s_40_p["mean"] * 100
                vs40 = f"{delta_pct:+.2f}%"
            f.write(f"| {thr} | {cell} | {vs40} |\n")
        f.write("\n")

        # 結果サマリ
        f.write("## 結果サマリ\n\n")
        if best_overall:
            thr, m = best_overall
            f.write(f"- **最良 eval 構成**: threads={thr}, eval_mean={m:.3f} t/s\n")
            f.write(f"- **Phase D (15.03) 超え**: {'YES' if m > PEAK_PHASE_D else 'NO'}\n")
            f.write(f"- **Phase S (15.39) 超え**: {'YES' if m > PEAK_PHASE_S else 'NO'}\n")
            f.write(f"- **Phase T-1 q8_0 (15.016) 超え**: {'YES' if m > PEAK_PHASE_T1_Q8 else 'NO'}\n")
            f.write(f"- **Phase T-2 最良 (14.672) 超え**: {'YES' if m > PEAK_PHASE_T2_BEST else 'NO'}\n")
        else:
            f.write("- データ不足\n")
        f.write("\n")

        # threads 効果 (+1%/-1% 閾値)
        f.write("## threads スイープ効果 (baseline threads=40 比、±1% 閾値)\n\n")
        if s_40 is not None:
            for thr in THREADS_LIST:
                if thr == 40:
                    f.write(f"- threads={thr}: baseline ({s_40['mean']:.3f} t/s)\n")
                    continue
                vals = [d.get("eval_tps") for d in data[thr]["eval"]]
                s = stats(vals)
                if s:
                    delta_pct = (s["mean"] - s_40["mean"]) / s_40["mean"] * 100
                    marker = "改善" if delta_pct >= 1 else ("劣化" if delta_pct <= -1 else "中立")
                    f.write(f"- threads={thr}: {s['mean']-s_40['mean']:+.3f} t/s ({delta_pct:+.2f}%) → **{marker}**\n")
                else:
                    f.write(f"- threads={thr}: データ不足\n")
        else:
            f.write("- baseline (threads=40) データ不足\n")

    print(f"[analyze] wrote {pivot_path}")
    with pivot_path.open() as f:
        print(f.read())
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
