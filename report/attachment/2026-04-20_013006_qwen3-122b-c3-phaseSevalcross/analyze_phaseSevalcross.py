#!/usr/bin/env python3
"""analyze_phaseSevalcross.py — Phase S-eval-cross-session 集計スクリプト
3 条件 (ub=1584/1586/1664) × 5 run を別セッションで再計測し、前 Phase S-eval 結果との
session 間 mean 差・Welch t を算出。session verdict（independent/partial_drift/session_dominated）と
ピーク ub 順序のセッション間安定性を出力する。
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

# 過去 1-run 参照値
REF_1RUN = {
    1584: 15.293,  # Phase Sbfine2
    1586: 15.466,  # Phase Sbfine3
    1664: 15.451,  # Phase Sbfine
}

UBS = [1584, 1586, 1664]
CTX = 32768
EVAL_RUNS = 5
WARMUP_RUNS = 2

# 前 Phase TSV
PRIOR_TSV = SCRIPT_DIR.parent / "2026-04-20_003250_qwen3-122b-c3-phaseSeval" / "summary_phaseSeval.tsv"

# 1-run 判定しきい値
TH_CONFIRMED = 0.05
TH_PARTIAL = 0.10

# Session 間判定しきい値
TH_SESSION_INDEP = 0.02
TH_SESSION_PARTIAL = 0.10

# 本 Phase の TAG_PREFIX
TAG_PREFIX = "Sevalcross_fa1_ctx"


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
    prefix = f"{TAG_PREFIX}{CTX}_ub{ub}"
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


def load_prior_tsv(path: Path) -> dict[int, list[float]]:
    """前 Phase TSV から ub 別 eval 5-run を取得"""
    result: dict[int, list[float]] = {ub: [] for ub in UBS}
    if not path.exists():
        print(f"WARN: prior TSV not found: {path}", file=sys.stderr)
        return result
    with path.open() as f:
        header = f.readline().strip().split("\t")
        idx_ub = header.index("ub")
        idx_phase = header.index("phase")
        idx_run = header.index("run")
        idx_eval = header.index("eval_tps")
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < len(header):
                continue
            ub = int(parts[idx_ub])
            phase = parts[idx_phase]
            if phase != "eval":
                continue
            try:
                v = float(parts[idx_eval])
            except ValueError:
                continue
            if ub in result:
                result[ub].append(v)
    return result


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


def verdict_1run(ref: float, s: dict | None) -> str:
    if s is None or s["n"] == 0:
        return "no_data"
    d = abs(s["mean"] - ref)
    if d <= TH_CONFIRMED:
        return "confirmed"
    if d <= TH_PARTIAL:
        return "partial"
    return "reject"


def verdict_session(delta: float) -> str:
    a = abs(delta)
    if a <= TH_SESSION_INDEP:
        return "session_independent"
    if a <= TH_SESSION_PARTIAL:
        return "partial_session_drift"
    return "session_dominated"


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


def peak_order(means: dict[int, float]) -> list[int]:
    return sorted(means.keys(), key=lambda k: -means[k])


def main() -> int:
    data = {ub: collect_ub(ub) for ub in UBS}
    prior = load_prior_tsv(PRIOR_TSV)

    # run 別 raw TSV
    summary_path = SCRIPT_DIR / "summary_phaseSevalcross.tsv"
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

    # 統計 CSV（1-run ref との比較を含む）
    stats_path = SCRIPT_DIR / "phaseSevalcross_stats.csv"
    with stats_path.open("w") as f:
        f.write(
            "ub,phase,n,mean_eval_tps,stdev,min,max,median,"
            "ref_1run,delta_1run,verdict_1run,prior_mean,delta_session,verdict_session\n"
        )
        for ub in UBS:
            for phase in ("warmup", "eval"):
                vals = [d.get("eval_tps") for d in data[ub][phase]]
                s = stats(vals)
                if phase == "eval":
                    ref = REF_1RUN[ub]
                    v1 = verdict_1run(ref, s)
                    prior_stats = stats(prior.get(ub, []))
                    prior_mean = prior_stats["mean"] if prior_stats else float("nan")
                    if s is None:
                        f.write(
                            f"{ub},{phase},0,,,,,,{ref},,no_data,{prior_mean:.4f},,no_data\n"
                        )
                    else:
                        d_sess = s["mean"] - prior_mean
                        vs = verdict_session(d_sess)
                        f.write(
                            f"{ub},{phase},{s['n']},{s['mean']:.4f},{s['stdev']:.4f},"
                            f"{s['min']:.4f},{s['max']:.4f},{s['median']:.4f},"
                            f"{ref},{s['mean']-ref:+.4f},{v1},"
                            f"{prior_mean:.4f},{d_sess:+.4f},{vs}\n"
                        )
                else:
                    if s is None:
                        f.write(f"{ub},{phase},0,,,,,,,,,,,\n")
                    else:
                        f.write(
                            f"{ub},{phase},{s['n']},{s['mean']:.4f},{s['stdev']:.4f},"
                            f"{s['min']:.4f},{s['max']:.4f},{s['median']:.4f},,,,,,\n"
                        )
    print(f"[analyze] wrote {stats_path}")

    # verdict (main)
    verdict_path = SCRIPT_DIR / "phaseSevalcross_verdict.txt"
    with verdict_path.open("w") as f:
        f.write("# Phase S-eval-cross-session verdict\n")
        f.write(f"ctx={CTX}, fa=1, f16/f16 KV, OT_REGEX=MoE only, threads=40, poll=0, numactl node1\n")
        f.write(f"warmup_runs={WARMUP_RUNS}, eval_runs={EVAL_RUNS}\n")
        f.write(f"prior_tsv={PRIOR_TSV}\n")
        f.write(
            f"thresholds: 1-run [confirmed <= {TH_CONFIRMED}, partial <= {TH_PARTIAL}], "
            f"session [independent <= {TH_SESSION_INDEP}, partial <= {TH_SESSION_PARTIAL}]\n\n"
        )

        # 1. 本 Phase 5-run 統計
        f.write("## 1. 本 Phase 5-run 統計（eval フェーズ）\n")
        f.write("ub    | mean   | stdev  | min    | max    | median\n")
        f.write("------|--------|--------|--------|--------|--------\n")
        cur_means: dict[int, float] = {}
        for ub in UBS:
            vals = [d.get("eval_tps") for d in data[ub]["eval"]]
            s = stats(vals)
            if s is None:
                f.write(f"{ub}  | no_data\n")
                continue
            cur_means[ub] = s["mean"]
            f.write(
                f"{ub}  | {s['mean']:6.3f} | {s['stdev']:6.3f} | "
                f"{s['min']:6.3f} | {s['max']:6.3f} | {s['median']:6.3f}\n"
            )

        # 2. 前 Phase との session 間 mean 差
        f.write("\n## 2. 前 Phase S-eval との session 間 mean 差\n")
        f.write("ub    | prior   | cur     | Δsession | SE      | t_welch | sig     | verdict\n")
        f.write("------|---------|---------|----------|---------|---------|---------|-------------------\n")
        session_verdicts = []
        for ub in UBS:
            a = [d.get("eval_tps") for d in data[ub]["eval"]]
            b = prior.get(ub, [])
            w = welch(a, b)
            prior_s = stats(b)
            cur_s = stats(a)
            if w is None or prior_s is None or cur_s is None:
                f.write(f"{ub}  | insufficient data\n")
                continue
            vs = verdict_session(w["diff"])
            session_verdicts.append(vs)
            sig = "significant" if abs(w["t"]) > 2.0 else "not_sig"
            f.write(
                f"{ub}  | {prior_s['mean']:7.3f} | {cur_s['mean']:7.3f} | "
                f"{w['diff']:+8.3f} | {w['se']:7.3f} | {w['t']:+7.2f} | "
                f"{sig:7s} | {vs}\n"
            )
        f.write(f"\nsession_verdicts: {session_verdicts}\n")

        # 3. 1-run ref との再現性（参考、前 Phase と同じ判定を再実施）
        f.write("\n## 3. 過去 1-run 参照値との再現性（再確認）\n")
        f.write("ub    | ref_1run | cur_mean | Δ_1run   | verdict_1run\n")
        f.write("------|----------|----------|----------|-------------\n")
        for ub in UBS:
            vals = [d.get("eval_tps") for d in data[ub]["eval"]]
            s = stats(vals)
            ref = REF_1RUN[ub]
            v = verdict_1run(ref, s)
            if s is None:
                f.write(f"{ub}  | {ref:8.3f} | NA       | NA       | no_data\n")
            else:
                f.write(
                    f"{ub}  | {ref:8.3f} | {s['mean']:8.3f} | "
                    f"{s['mean']-ref:+8.3f} | {v}\n"
                )

        # 4. ピーク ub 順序のセッション間安定性
        f.write("\n## 4. ピーク ub 順序のセッション間安定性\n")
        prior_means: dict[int, float] = {}
        for ub in UBS:
            s = stats(prior.get(ub, []))
            if s:
                prior_means[ub] = s["mean"]
        if len(prior_means) == 3 and len(cur_means) == 3:
            prior_order = peak_order(prior_means)
            cur_order = peak_order(cur_means)
            same = prior_order == cur_order
            f.write(f"前 Phase peak order: {prior_order}\n")
            f.write(f"本 Phase peak order: {cur_order}\n")
            f.write(f"同一順序: {same}\n")
        else:
            f.write("データ不足（prior or cur mean 取得失敗）\n")

        # 5. Run 1 外れ値（eval フェーズ）
        f.write("\n## 5. Run 1 外れ値チェック（eval フェーズ、平均 ± 2σ）\n")
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
                f"|run1-mean|={abs(r1-m):.3f}, 2σ={2*sd:.3f} "
                f"→ {'OUTLIER' if flag else 'in_range'}\n"
            )

        # 6. ub 間有意差（本 Phase 単独、Welch）
        f.write("\n## 6. ub 間有意差（本 Phase 5-run プール、Welch t 近似）\n")
        pairs = [(1586, 1584), (1664, 1584), (1586, 1664)]
        for x, y in pairs:
            a = [d.get("eval_tps") for d in data[x]["eval"]]
            b = [d.get("eval_tps") for d in data[y]["eval"]]
            w = welch(a, b)
            if w is None:
                f.write(f"ub={x} - ub={y}: データ不足\n")
                continue
            sig = "significant" if abs(w["t"]) > 2.0 else "not_sig"
            f.write(
                f"ub={x} - ub={y}: diff={w['diff']:+.3f}, SE={w['se']:.3f}, "
                f"t={w['t']:+.2f} → {sig}\n"
            )

        # 7. pooled (prior + cur) σ / grand mean（真の性能推定）
        f.write("\n## 7. Pooled 10-run 統計（prior + cur、真の性能推定）\n")
        f.write("ub    | pool_n | mean   | stdev  | min    | max    | median\n")
        f.write("------|--------|--------|--------|--------|--------|--------\n")
        for ub in UBS:
            pooled = [d.get("eval_tps") for d in data[ub]["eval"]] + prior.get(ub, [])
            s = stats(pooled)
            if s is None:
                f.write(f"{ub}  | no_data\n")
                continue
            f.write(
                f"{ub}  | {s['n']:6d} | {s['mean']:6.3f} | {s['stdev']:6.3f} | "
                f"{s['min']:6.3f} | {s['max']:6.3f} | {s['median']:6.3f}\n"
            )

    print(f"[analyze] wrote {verdict_path}")
    with verdict_path.open() as f:
        print(f.read())
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
