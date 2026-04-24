#!/usr/bin/env python3
"""analyze_phaseT1.py - Phase T-1: KV cache 量子化スイープ集計

KV 型 (f16/q8_0/q4_0/q4_1) × ub (1586/1664) の 8 条件から
eval_tps / prompt_tps の mean/std/min/max を抽出し、
pivot 比較表 (行 = KV 型, 列 = ub × {eval, prompt}) を CSV + Markdown で出力する。
Phase D (15.03 t/s) / Phase S (15.39 t/s) ピーク超え判定も付記。
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

KV_TYPES = ["f16", "q8_0", "q4_0", "q4_1"]
UBS = [1586, 1664]
CTX = 32768
WARMUP_RUNS = 2
EVAL_RUNS = 5

PEAK_PHASE_D = 15.03
PEAK_PHASE_S = 15.39


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


def collect(kv: str, ub: int) -> dict:
    tag_cond = f"kv{kv}_ctx{CTX}_ub{ub}"
    warmup_dir = SCRIPT_DIR / f"out_T1_{tag_cond}_warmup"
    eval_dir = SCRIPT_DIR / f"out_T1_{tag_cond}_1k"

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


def verdict(mean_eval: float | None) -> str:
    if mean_eval is None:
        return "no_data"
    if mean_eval > PEAK_PHASE_S:
        return f"SURPASS_S ({mean_eval:.3f} > {PEAK_PHASE_S})"
    if mean_eval > PEAK_PHASE_D:
        return f"surpass_D ({mean_eval:.3f} > {PEAK_PHASE_D})"
    return f"below_D ({mean_eval:.3f} ≤ {PEAK_PHASE_D})"


def main() -> int:
    # データ収集
    data: dict[str, dict[int, dict]] = {}
    for kv in KV_TYPES:
        data[kv] = {}
        for ub in UBS:
            data[kv][ub] = collect(kv, ub)

    # raw TSV
    summary_path = SCRIPT_DIR / "summary_phaseT1.tsv"
    with summary_path.open("w") as f:
        f.write("kv\tub\tphase\trun\teval_tps\tprompt_tps\tprompt_n\tpredicted_n\n")
        for kv in KV_TYPES:
            for ub in UBS:
                for phase in ("warmup", "eval"):
                    for idx, d in enumerate(data[kv][ub][phase], start=1):
                        f.write(
                            f"{kv}\t{ub}\t{phase}\t{idx}\t"
                            f"{d.get('eval_tps')}\t{d.get('prompt_tps')}\t"
                            f"{d.get('prompt_n')}\t{d.get('predicted_n')}\n"
                        )
    print(f"[analyze] wrote {summary_path}")

    # 統計 CSV
    stats_path = SCRIPT_DIR / "phaseT1_stats.csv"
    with stats_path.open("w") as f:
        f.write(
            "kv,ub,metric,phase,n,mean,stdev,min,max,median,"
            "surpass_phase_d,surpass_phase_s\n"
        )
        for kv in KV_TYPES:
            for ub in UBS:
                for metric in ("eval_tps", "prompt_tps"):
                    for phase in ("warmup", "eval"):
                        vals = [d.get(metric) for d in data[kv][ub][phase]]
                        s = stats(vals)
                        if s is None:
                            f.write(f"{kv},{ub},{metric},{phase},0,,,,,,,\n")
                            continue
                        sd = "yes" if (metric == "eval_tps" and phase == "eval" and s["mean"] > PEAK_PHASE_D) else "no"
                        ss = "yes" if (metric == "eval_tps" and phase == "eval" and s["mean"] > PEAK_PHASE_S) else "no"
                        f.write(
                            f"{kv},{ub},{metric},{phase},{s['n']},{s['mean']:.4f},{s['stdev']:.4f},"
                            f"{s['min']:.4f},{s['max']:.4f},{s['median']:.4f},{sd},{ss}\n"
                        )
    print(f"[analyze] wrote {stats_path}")

    # pivot Markdown
    pivot_path = SCRIPT_DIR / "phaseT1_pivot.md"
    with pivot_path.open("w") as f:
        f.write("# Phase T-1: KV cache 量子化スイープ pivot 比較表\n\n")
        f.write(f"- ctx={CTX}, fa=1, threads=40, numactl node1, OT=MoE only, poll=0\n")
        f.write(f"- warmup {WARMUP_RUNS} run + eval {EVAL_RUNS} run\n")
        f.write(f"- ベースライン: Phase D 15.03 t/s / Phase S 15.39 t/s\n\n")

        # eval_tps pivot
        f.write("## eval_tps (mean±stdev, t/s) — eval フェーズ 5 run\n\n")
        f.write("| KV 型 | ub=1586 | ub=1664 | best ub | best mean | 判定 |\n")
        f.write("|-------|---------|---------|---------|-----------|------|\n")
        best_overall = None
        for kv in KV_TYPES:
            cells = []
            means = {}
            for ub in UBS:
                vals = [d.get("eval_tps") for d in data[kv][ub]["eval"]]
                s = stats(vals)
                cells.append(fmt_cell(s))
                if s is not None:
                    means[ub] = s["mean"]
            if means:
                best_ub = max(means, key=means.get)
                best_mean = means[best_ub]
                v = verdict(best_mean)
                if best_overall is None or best_mean > best_overall[2]:
                    best_overall = (kv, best_ub, best_mean)
            else:
                best_ub, best_mean, v = "NA", None, "no_data"
            bm_s = f"{best_mean:.3f}" if best_mean is not None else "NA"
            f.write(f"| {kv} | {cells[0]} | {cells[1]} | {best_ub} | {bm_s} | {v} |\n")
        f.write("\n")

        # prompt_tps pivot
        f.write("## prompt_tps (mean±stdev, t/s) — eval フェーズ 5 run\n\n")
        f.write("| KV 型 | ub=1586 | ub=1664 | best ub | best mean |\n")
        f.write("|-------|---------|---------|---------|-----------|\n")
        for kv in KV_TYPES:
            cells = []
            means = {}
            for ub in UBS:
                vals = [d.get("prompt_tps") for d in data[kv][ub]["eval"]]
                s = stats(vals)
                cells.append(fmt_cell(s))
                if s is not None:
                    means[ub] = s["mean"]
            if means:
                best_ub = max(means, key=means.get)
                best_mean = means[best_ub]
                bm_s = f"{best_mean:.3f}"
            else:
                best_ub, bm_s = "NA", "NA"
            f.write(f"| {kv} | {cells[0]} | {cells[1]} | {best_ub} | {bm_s} |\n")
        f.write("\n")

        # 結果サマリ
        f.write("## 結果サマリ\n\n")
        if best_overall:
            kv, ub, m = best_overall
            f.write(f"- **最良 eval 構成**: KV={kv}, ub={ub}, eval_mean={m:.3f} t/s\n")
            f.write(f"- **Phase D (15.03) 超え**: {'YES' if m > PEAK_PHASE_D else 'NO'}\n")
            f.write(f"- **Phase S (15.39) 超え**: {'YES' if m > PEAK_PHASE_S else 'NO'}\n")
        else:
            f.write("- データ不足\n")
        f.write("\n")

        # f16 baseline 再現性チェック
        f.write("## f16 baseline 再現性チェック\n\n")
        vals_f16_1586 = [d.get("eval_tps") for d in data.get("f16", {}).get(1586, {}).get("eval", [])]
        s_f16_1586 = stats(vals_f16_1586)
        if s_f16_1586:
            ref = 15.173  # S54 f16 ub=1586 eval_mean
            delta_pct = abs(s_f16_1586["mean"] - ref) / ref * 100
            within = "within ±5%" if delta_pct <= 5 else "OUTSIDE ±5%"
            f.write(f"- S54 参照 f16 ub=1586 eval_mean = {ref:.3f} t/s\n")
            f.write(f"- 本 Phase f16 ub=1586 eval_mean = {s_f16_1586['mean']:.3f} t/s\n")
            f.write(f"- Δ = {s_f16_1586['mean']-ref:+.3f} t/s ({delta_pct:.1f}%) → {within}\n")
        else:
            f.write("- f16 ub=1586 データ不足\n")

    print(f"[analyze] wrote {pivot_path}")
    with pivot_path.open() as f:
        print(f.read())
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
