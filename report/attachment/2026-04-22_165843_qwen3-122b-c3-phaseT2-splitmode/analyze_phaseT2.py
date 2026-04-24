#!/usr/bin/env python3
"""analyze_phaseT2.py - Phase T-2: split-mode row vs layer 比較集計

split-mode {layer, row} × KV {f16, q8_0} × ub=1586 の 4 条件から
eval_tps / prompt_tps の mean/stdev/min/max を抽出し、
pivot 比較表 (行 = KV 型, 列 = split-mode × {eval, prompt}) を CSV + Markdown で出力する。
Phase D (15.03 t/s) / Phase S (15.39 t/s) / Phase T-1 q8_0 (15.016 t/s) 超え判定も付記。
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

KV_TYPES = ["f16", "q8_0"]
SPLIT_MODES = ["layer", "row"]
UB = 1586
CTX = 32768
WARMUP_RUNS = 2
EVAL_RUNS = 5

PEAK_PHASE_D = 15.03
PEAK_PHASE_S = 15.39
PEAK_PHASE_T1_Q8 = 15.016  # Phase T-1 最良 (q8_0 ub=1586, split=layer)
PEAK_PHASE_T1_F16 = 14.425  # Phase T-1 f16 ub=1586 (split=layer)


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


def collect(kv: str, sm: str, ub: int) -> dict:
    tag_cond = f"kv{kv}_sm{sm}_ctx{CTX}_ub{ub}"
    warmup_dir = SCRIPT_DIR / f"out_T2_{tag_cond}_warmup"
    eval_dir = SCRIPT_DIR / f"out_T2_{tag_cond}_1k"

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
    return f"below_T1 ({mean_eval:.3f} ≤ {PEAK_PHASE_T1_Q8})"


def main() -> int:
    data: dict = {}
    for kv in KV_TYPES:
        data[kv] = {}
        for sm in SPLIT_MODES:
            data[kv][sm] = collect(kv, sm, UB)

    # raw TSV
    summary_path = SCRIPT_DIR / "summary_phaseT2.tsv"
    with summary_path.open("w") as f:
        f.write("kv\tsplit_mode\tub\tphase\trun\teval_tps\tprompt_tps\tprompt_n\tpredicted_n\n")
        for kv in KV_TYPES:
            for sm in SPLIT_MODES:
                for phase in ("warmup", "eval"):
                    for idx, d in enumerate(data[kv][sm][phase], start=1):
                        f.write(
                            f"{kv}\t{sm}\t{UB}\t{phase}\t{idx}\t"
                            f"{d.get('eval_tps')}\t{d.get('prompt_tps')}\t"
                            f"{d.get('prompt_n')}\t{d.get('predicted_n')}\n"
                        )
    print(f"[analyze] wrote {summary_path}")

    # 統計 CSV
    stats_path = SCRIPT_DIR / "phaseT2_stats.csv"
    with stats_path.open("w") as f:
        f.write(
            "kv,split_mode,ub,metric,phase,n,mean,stdev,min,max,median,"
            "surpass_phase_d,surpass_phase_s,surpass_phase_t1_q8\n"
        )
        for kv in KV_TYPES:
            for sm in SPLIT_MODES:
                for metric in ("eval_tps", "prompt_tps"):
                    for phase in ("warmup", "eval"):
                        vals = [d.get(metric) for d in data[kv][sm][phase]]
                        s = stats(vals)
                        if s is None:
                            f.write(f"{kv},{sm},{UB},{metric},{phase},0,,,,,,,,\n")
                            continue
                        is_eval_m = (metric == "eval_tps" and phase == "eval")
                        sd = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_D) else "no"
                        ss = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_S) else "no"
                        st1 = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T1_Q8) else "no"
                        f.write(
                            f"{kv},{sm},{UB},{metric},{phase},{s['n']},{s['mean']:.4f},{s['stdev']:.4f},"
                            f"{s['min']:.4f},{s['max']:.4f},{s['median']:.4f},{sd},{ss},{st1}\n"
                        )
    print(f"[analyze] wrote {stats_path}")

    # pivot Markdown
    pivot_path = SCRIPT_DIR / "phaseT2_pivot.md"
    with pivot_path.open("w") as f:
        f.write("# Phase T-2: split-mode row vs layer pivot 比較表\n\n")
        f.write(f"- ctx={CTX}, ub={UB}, fa=1, threads=40, numactl node1, OT=MoE only, poll=0\n")
        f.write(f"- warmup {WARMUP_RUNS} run + eval {EVAL_RUNS} run\n")
        f.write(
            f"- ベースライン: Phase D {PEAK_PHASE_D} t/s / Phase S {PEAK_PHASE_S} t/s / "
            f"Phase T-1 q8_0 {PEAK_PHASE_T1_Q8} t/s / Phase T-1 f16 {PEAK_PHASE_T1_F16} t/s\n\n"
        )

        # eval_tps pivot
        f.write("## eval_tps (mean±stdev, t/s) — eval フェーズ 5 run\n\n")
        f.write("| KV 型 | split=layer | split=row | row/layer 比 | best split | best mean | 判定 |\n")
        f.write("|-------|-------------|-----------|--------------|------------|-----------|------|\n")
        best_overall = None
        for kv in KV_TYPES:
            cells = []
            means = {}
            for sm in SPLIT_MODES:
                vals = [d.get("eval_tps") for d in data[kv][sm]["eval"]]
                s = stats(vals)
                cells.append(fmt_cell(s))
                if s is not None:
                    means[sm] = s["mean"]
            ratio = "NA"
            if "layer" in means and "row" in means and means["layer"] > 0:
                ratio = f"{means['row'] / means['layer']:.4f}"
            if means:
                best_sm = max(means, key=means.get)
                best_mean = means[best_sm]
                v = verdict(best_mean)
                if best_overall is None or best_mean > best_overall[2]:
                    best_overall = (kv, best_sm, best_mean)
            else:
                best_sm, best_mean, v = "NA", None, "no_data"
            bm_s = f"{best_mean:.3f}" if best_mean is not None else "NA"
            f.write(f"| {kv} | {cells[0]} | {cells[1]} | {ratio} | {best_sm} | {bm_s} | {v} |\n")
        f.write("\n")

        # prompt_tps pivot
        f.write("## prompt_tps (mean±stdev, t/s) — eval フェーズ 5 run\n\n")
        f.write("| KV 型 | split=layer | split=row | row/layer 比 | best split | best mean |\n")
        f.write("|-------|-------------|-----------|--------------|------------|-----------|\n")
        for kv in KV_TYPES:
            cells = []
            means = {}
            for sm in SPLIT_MODES:
                vals = [d.get("prompt_tps") for d in data[kv][sm]["eval"]]
                s = stats(vals)
                cells.append(fmt_cell(s))
                if s is not None:
                    means[sm] = s["mean"]
            ratio = "NA"
            if "layer" in means and "row" in means and means["layer"] > 0:
                ratio = f"{means['row'] / means['layer']:.4f}"
            if means:
                best_sm = max(means, key=means.get)
                best_mean = means[best_sm]
                bm_s = f"{best_mean:.3f}"
            else:
                best_sm, bm_s = "NA", "NA"
            f.write(f"| {kv} | {cells[0]} | {cells[1]} | {ratio} | {best_sm} | {bm_s} |\n")
        f.write("\n")

        # 結果サマリ
        f.write("## 結果サマリ\n\n")
        if best_overall:
            kv, sm, m = best_overall
            f.write(f"- **最良 eval 構成**: KV={kv}, split-mode={sm}, eval_mean={m:.3f} t/s\n")
            f.write(f"- **Phase D (15.03) 超え**: {'YES' if m > PEAK_PHASE_D else 'NO'}\n")
            f.write(f"- **Phase S (15.39) 超え**: {'YES' if m > PEAK_PHASE_S else 'NO'}\n")
            f.write(f"- **Phase T-1 q8_0 (15.016) 超え**: {'YES' if m > PEAK_PHASE_T1_Q8 else 'NO'}\n")
        else:
            f.write("- データ不足\n")
        f.write("\n")

        # q8_0 vs f16 独立再現性 (split=layer 条件で)
        f.write("## q8_0 vs f16 独立再現性 (Phase T-1 副次発見 +4.1% の再現可否)\n\n")
        vals_f16_layer = [d.get("eval_tps") for d in data.get("f16", {}).get("layer", {}).get("eval", [])]
        vals_q8_layer = [d.get("eval_tps") for d in data.get("q8_0", {}).get("layer", {}).get("eval", [])]
        s_f16_l = stats(vals_f16_layer)
        s_q8_l = stats(vals_q8_layer)
        if s_f16_l and s_q8_l:
            diff_pct = (s_q8_l["mean"] - s_f16_l["mean"]) / s_f16_l["mean"] * 100
            f.write(f"- 本 Phase split=layer: f16 eval_mean = {s_f16_l['mean']:.3f} t/s (Phase T-1: {PEAK_PHASE_T1_F16})\n")
            f.write(f"- 本 Phase split=layer: q8_0 eval_mean = {s_q8_l['mean']:.3f} t/s (Phase T-1: {PEAK_PHASE_T1_Q8})\n")
            f.write(f"- q8_0 - f16 (split=layer) = {s_q8_l['mean']-s_f16_l['mean']:+.3f} t/s ({diff_pct:+.2f}%)\n")
            f.write(f"- Phase T-1 副次発見 +4.1% との一致: {'YES' if 2.0 <= diff_pct <= 6.0 else 'NO'} (差分 {diff_pct:+.2f}%)\n")
        else:
            f.write("- layer split データ不足\n")
        f.write("\n")

        # split-mode 効果
        f.write("## split-mode row 効果 (CUDA3 compute buffer 偏在解消狙い)\n\n")
        for kv in KV_TYPES:
            vals_l = [d.get("eval_tps") for d in data.get(kv, {}).get("layer", {}).get("eval", [])]
            vals_r = [d.get("eval_tps") for d in data.get(kv, {}).get("row", {}).get("eval", [])]
            s_l = stats(vals_l)
            s_r = stats(vals_r)
            if s_l and s_r:
                delta_pct = (s_r["mean"] - s_l["mean"]) / s_l["mean"] * 100
                marker = "改善" if delta_pct >= 3 else ("劣化" if delta_pct <= -3 else "中立")
                f.write(f"- KV={kv}: row - layer = {s_r['mean']-s_l['mean']:+.3f} t/s ({delta_pct:+.2f}%) → **{marker}**\n")
            else:
                f.write(f"- KV={kv}: データ不足 (layer={'有' if s_l else '無'}, row={'有' if s_r else '無'})\n")

    print(f"[analyze] wrote {pivot_path}")
    with pivot_path.open() as f:
        print(f.read())
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
