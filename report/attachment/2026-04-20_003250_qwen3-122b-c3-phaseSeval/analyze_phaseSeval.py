#!/usr/bin/env python3
"""analyze_phaseSeval.py — Phase S-eval 集計スクリプト
3 条件 (ub=1584/1586/1664) × 5 run の eval_tps / prompt_tps / prompt_n / predicted_n を集計し、
過去 1-run 参照値との再現性判定（confirmed/partial/reject）を行う。
"""
from __future__ import annotations

import json
import math
import os
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
os.chdir(SCRIPT_DIR)

# 過去 1-run 参照値（未検証事項にある数値）
REF = {
    1584: 15.293,  # Phase Sbfine2
    1586: 15.466,  # Phase Sbfine3
    1664: 15.451,  # Phase Sbfine
}

UBS = [1584, 1586, 1664]
CTX = 32768
EVAL_RUNS = 5
WARMUP_RUNS = 2

# 判定しきい値
TH_CONFIRMED = 0.05
TH_PARTIAL = 0.10


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


def collect_ub(ub: int) -> dict:
    prefix = f"Seval_fa1_ctx{CTX}_ub{ub}"
    warmup_dir = SCRIPT_DIR / f"out_{prefix}_warmup"
    eval_dir = SCRIPT_DIR / f"out_{prefix}_1k"

    warmup_runs = []
    for r in range(1, WARMUP_RUNS + 1):
        d = load_run(warmup_dir, r)
        if d:
            warmup_runs.append(d)

    eval_runs = []
    for r in range(1, EVAL_RUNS + 1):
        d = load_run(eval_dir, r)
        if d:
            eval_runs.append(d)

    return {"warmup": warmup_runs, "eval": eval_runs}


def stats(values):
    vs = [v for v in values if isinstance(v, (int, float))]
    if not vs:
        return None
    mean = statistics.mean(vs)
    stdev = statistics.pstdev(vs) if len(vs) < 2 else statistics.stdev(vs)
    return {
        "n": len(vs),
        "mean": mean,
        "stdev": stdev,
        "min": min(vs),
        "max": max(vs),
        "median": statistics.median(vs),
    }


def verdict_for(ref: float, s: dict | None) -> str:
    if s is None or s["n"] == 0:
        return "no_data"
    d = abs(s["mean"] - ref)
    if d <= TH_CONFIRMED:
        return "confirmed"
    if d <= TH_PARTIAL:
        return "partial"
    return "reject"


def main() -> int:
    data = {ub: collect_ub(ub) for ub in UBS}

    # run 別 raw TSV
    summary_path = SCRIPT_DIR / "summary_phaseSeval.tsv"
    with summary_path.open("w") as f:
        f.write("ub\tphase\trun\teval_tps\tprompt_tps\tprompt_n\tpredicted_n\n")
        for ub in UBS:
            for phase in ("warmup", "eval"):
                for idx, d in enumerate(data[ub][phase], start=1):
                    f.write(
                        f"{ub}\t{phase}\t{idx}\t"
                        f"{d.get('eval_tps')}\t{d.get('prompt_tps')}\t"
                        f"{d.get('prompt_n')}\t{d.get('predicted_n')}\n"
                    )
    print(f"[analyze] wrote {summary_path}")

    # 統計 CSV
    stats_path = SCRIPT_DIR / "phaseSeval_stats.csv"
    with stats_path.open("w") as f:
        f.write("ub,phase,n,mean_eval_tps,stdev,min,max,median,ref_1run,delta_mean_ref,verdict\n")
        for ub in UBS:
            for phase in ("warmup", "eval"):
                vals = [d.get("eval_tps") for d in data[ub][phase]]
                s = stats(vals)
                if phase == "eval":
                    ref = REF[ub]
                    v = verdict_for(ref, s)
                    if s is None:
                        f.write(f"{ub},{phase},0,,,,,,{ref},,no_data\n")
                    else:
                        f.write(
                            f"{ub},{phase},{s['n']},{s['mean']:.4f},{s['stdev']:.4f},"
                            f"{s['min']:.4f},{s['max']:.4f},{s['median']:.4f},"
                            f"{ref},{s['mean']-ref:+.4f},{v}\n"
                        )
                else:
                    if s is None:
                        f.write(f"{ub},{phase},0,,,,,,,,\n")
                    else:
                        f.write(
                            f"{ub},{phase},{s['n']},{s['mean']:.4f},{s['stdev']:.4f},"
                            f"{s['min']:.4f},{s['max']:.4f},{s['median']:.4f},,,\n"
                        )
    print(f"[analyze] wrote {stats_path}")

    # verdict
    verdict_path = SCRIPT_DIR / "phaseSeval_verdict.txt"
    with verdict_path.open("w") as f:
        f.write("# Phase S-eval 再現性検証 verdict\n")
        f.write(f"ctx={CTX}, fa=1, f16/f16 KV, OT_REGEX=MoE only, threads=40, poll=0, numactl node1\n")
        f.write(f"warmup_runs={WARMUP_RUNS}, eval_runs={EVAL_RUNS}\n")
        f.write(f"thresholds: confirmed <= {TH_CONFIRMED} t/s, partial <= {TH_PARTIAL} t/s\n\n")
        f.write("ub    | ref (1-run) | mean   | stdev  | min    | max    | median | Δmean  | verdict\n")
        f.write("------|-------------|--------|--------|--------|--------|--------|--------|----------\n")
        overall = []
        for ub in UBS:
            vals = [d.get("eval_tps") for d in data[ub]["eval"]]
            s = stats(vals)
            ref = REF[ub]
            v = verdict_for(ref, s)
            overall.append(v)
            if s is None:
                f.write(f"{ub}  | {ref:11.3f} | {'NA':>6} | {'NA':>6} | {'NA':>6} | {'NA':>6} | {'NA':>6} | {'NA':>6} | no_data\n")
            else:
                f.write(
                    f"{ub}  | {ref:11.3f} | {s['mean']:6.3f} | {s['stdev']:6.3f} | "
                    f"{s['min']:6.3f} | {s['max']:6.3f} | {s['median']:6.3f} | "
                    f"{s['mean']-ref:+6.3f} | {v}\n"
                )
        f.write(f"\noverall: {overall}\n")
        # Run 1 外れ値判定（eval フェーズのみ対象、平均 ± 2σ 外）
        f.write("\n## Run 1 外れ値チェック（eval フェーズ、平均 ± 2σ）\n")
        for ub in UBS:
            vals = [d.get("eval_tps") for d in data[ub]["eval"]]
            if not vals or None in vals or len(vals) < 2:
                f.write(f"ub={ub}: 不十分なデータ\n")
                continue
            m = statistics.mean(vals)
            sd = statistics.stdev(vals)
            r1 = vals[0]
            flag = abs(r1 - m) > 2 * sd
            f.write(
                f"ub={ub}: run1={r1:.3f}, mean={m:.3f}, stdev={sd:.3f}, "
                f"|run1-mean|={abs(r1 - m):.3f}, 2σ={2*sd:.3f} "
                f"→ {'OUTLIER' if flag else 'in_range'}\n"
            )

        # ub=1586 vs ub=1584 の有意差（単純 Welch 近似、t_obs 算出）
        f.write("\n## ub=1586 vs ub=1584 有意差（Welch t 近似）\n")

        def welch(a: list[float], b: list[float]) -> dict | None:
            aa = [v for v in a if isinstance(v, (int, float))]
            bb = [v for v in b if isinstance(v, (int, float))]
            if len(aa) < 2 or len(bb) < 2:
                return None
            ma, mb = statistics.mean(aa), statistics.mean(bb)
            va, vb = statistics.variance(aa), statistics.variance(bb)
            se = math.sqrt(va / len(aa) + vb / len(bb))
            if se == 0:
                return {"t": float("inf"), "diff": ma - mb, "se": 0.0}
            t = (ma - mb) / se
            return {"t": t, "diff": ma - mb, "se": se}

        a = [d.get("eval_tps") for d in data[1586]["eval"]]
        b = [d.get("eval_tps") for d in data[1584]["eval"]]
        w = welch(a, b)
        if w is None:
            f.write("データ不足\n")
        else:
            sig = "significant" if abs(w["t"]) > 2.0 else "not_significant"
            f.write(
                f"ub=1586 - ub=1584: diff={w['diff']:+.3f}, SE={w['se']:.3f}, "
                f"t={w['t']:+.2f} → {sig} (|t|>2.0)\n"
            )

        a = [d.get("eval_tps") for d in data[1664]["eval"]]
        b = [d.get("eval_tps") for d in data[1584]["eval"]]
        w = welch(a, b)
        if w is not None:
            sig = "significant" if abs(w["t"]) > 2.0 else "not_significant"
            f.write(
                f"ub=1664 - ub=1584: diff={w['diff']:+.3f}, SE={w['se']:.3f}, "
                f"t={w['t']:+.2f} → {sig} (|t|>2.0)\n"
            )

        a = [d.get("eval_tps") for d in data[1586]["eval"]]
        b = [d.get("eval_tps") for d in data[1664]["eval"]]
        w = welch(a, b)
        if w is not None:
            sig = "significant" if abs(w["t"]) > 2.0 else "not_significant"
            f.write(
                f"ub=1586 - ub=1664: diff={w['diff']:+.3f}, SE={w['se']:.3f}, "
                f"t={w['t']:+.2f} → {sig} (|t|>2.0)\n"
            )

    print(f"[analyze] wrote {verdict_path}")
    # 画面サマリ
    with verdict_path.open() as f:
        print(f.read())


if __name__ == "__main__":
    sys.exit(main() or 0)
