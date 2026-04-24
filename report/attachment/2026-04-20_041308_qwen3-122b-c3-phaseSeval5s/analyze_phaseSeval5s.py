#!/usr/bin/env python3
"""analyze_phaseSeval5s.py - Phase S-eval-5session 集計スクリプト

5 session (phaseSeval + phaseSevalcross + phaseSeval3s + phaseSeval4s + 本 Phase phaseSeval5s) を合算し、
ub 別 n=5 の session 間 σ, 5-session verdict, ピーク順序安定性、pooled 25-run 統計、
ub=1584 崩壊頻度、ub=1664 時系列パターン分析を出力する。
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

REF_1RUN = {
    1584: 15.293,  # Phase Sbfine2
    1586: 15.466,  # Phase Sbfine3
    1664: 15.451,  # Phase Sbfine
}

UBS = [1584, 1586, 1664]
CTX = 32768
EVAL_RUNS = 5
WARMUP_RUNS = 2

PRIOR_TSVS = [
    ("S1_phaseSeval",
     SCRIPT_DIR.parent / "2026-04-20_003250_qwen3-122b-c3-phaseSeval" / "summary_phaseSeval.tsv"),
    ("S2_phaseSevalcross",
     SCRIPT_DIR.parent / "2026-04-20_013006_qwen3-122b-c3-phaseSevalcross" / "summary_phaseSevalcross.tsv"),
    ("S3_phaseSeval3s",
     SCRIPT_DIR.parent / "2026-04-20_022922_qwen3-122b-c3-phaseSeval3s" / "summary_phaseSeval3s.tsv"),
    ("S4_phaseSeval4s",
     SCRIPT_DIR.parent / "2026-04-20_032317_qwen3-122b-c3-phaseSeval4s" / "summary_phaseSeval4s.tsv"),
]
CUR_SESSION_LABEL = "S5_phaseSeval5s"

TH_CONFIRMED = 0.05
TH_PARTIAL = 0.10

TH_SESSION_INDEP = 0.02
TH_SESSION_PARTIAL = 0.10

# ub=1584 崩壊判定しきい値（前 Phase で「崩壊 session」を eval_mean < 15.0 と暫定定義）
TH_UB1584_COLLAPSE = 15.0

TAG_PREFIX = "Seval5s_fa1_ctx"


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
    result: dict[int, list[float]] = {ub: [] for ub in UBS}
    if not path.exists():
        print(f"WARN: prior TSV not found: {path}", file=sys.stderr)
        return result
    with path.open() as f:
        header = f.readline().strip().split("\t")
        idx_ub = header.index("ub")
        idx_phase = header.index("phase")
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


def verdict_range(range_v: float) -> str:
    if range_v <= TH_SESSION_INDEP:
        return "fully_independent"
    if range_v <= TH_SESSION_PARTIAL:
        return "partial_drift"
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
    cur_data = {ub: collect_ub(ub) for ub in UBS}
    session_data: dict[str, dict[int, list[float]]] = {}
    for label, tsv in PRIOR_TSVS:
        session_data[label] = load_prior_tsv(tsv)
    cur_eval: dict[int, list[float]] = {}
    for ub in UBS:
        cur_eval[ub] = [d.get("eval_tps") for d in cur_data[ub]["eval"]]
    session_data[CUR_SESSION_LABEL] = cur_eval
    session_labels = [label for label, _ in PRIOR_TSVS] + [CUR_SESSION_LABEL]

    # run 別 raw TSV
    summary_path = SCRIPT_DIR / "summary_phaseSeval5s.tsv"
    with summary_path.open("w") as f:
        f.write("ub\tphase\trun\teval_tps\tprompt_tps\tprompt_n\tpredicted_n\n")
        for ub in UBS:
            for phase in ("warmup", "eval"):
                for idx, d in enumerate(cur_data[ub][phase], start=1):
                    f.write(
                        f"{ub}\t{phase}\t{idx}\t"
                        f"{d.get('eval_tps')}\t{d.get('prompt_tps')}\t"
                        f"{d.get('prompt_n')}\t{d.get('predicted_n')}\n"
                    )
    print(f"[analyze] wrote {summary_path}")

    # 統計 CSV
    stats_path = SCRIPT_DIR / "phaseSeval5s_stats.csv"
    with stats_path.open("w") as f:
        f.write(
            "ub,phase,n,mean_eval_tps,stdev,min,max,median,"
            "ref_1run,delta_1run,verdict_1run\n"
        )
        for ub in UBS:
            for phase in ("warmup", "eval"):
                vals = [d.get("eval_tps") for d in cur_data[ub][phase]]
                s = stats(vals)
                if phase == "eval":
                    ref = REF_1RUN[ub]
                    v1 = verdict_1run(ref, s)
                    if s is None:
                        f.write(f"{ub},{phase},0,,,,,,{ref},,no_data\n")
                    else:
                        f.write(
                            f"{ub},{phase},{s['n']},{s['mean']:.4f},{s['stdev']:.4f},"
                            f"{s['min']:.4f},{s['max']:.4f},{s['median']:.4f},"
                            f"{ref},{s['mean']-ref:+.4f},{v1}\n"
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
    verdict_path = SCRIPT_DIR / "phaseSeval5s_verdict.txt"
    with verdict_path.open("w") as f:
        f.write("# Phase S-eval-5session verdict\n")
        f.write(f"ctx={CTX}, fa=1, f16/f16 KV, OT_REGEX=MoE only, threads=40, poll=0, numactl node1\n")
        f.write(f"warmup_runs={WARMUP_RUNS}, eval_runs={EVAL_RUNS}\n")
        f.write(f"sessions: {session_labels}\n")
        f.write(
            f"thresholds: 1-run [confirmed <= {TH_CONFIRMED}, partial <= {TH_PARTIAL}], "
            f"session range [independent <= {TH_SESSION_INDEP}, partial <= {TH_SESSION_PARTIAL}]\n"
        )
        f.write(f"ub=1584 崩壊判定: eval_mean < {TH_UB1584_COLLAPSE} t/s\n\n")

        # 1. 本 Phase 5-run 統計
        f.write("## 1. 本 Phase (S5) 5-run 統計（eval フェーズ）\n")
        f.write("ub    | mean   | stdev  | min    | max    | median\n")
        f.write("------|--------|--------|--------|--------|--------\n")
        cur_means: dict[int, float] = {}
        for ub in UBS:
            s = stats(cur_eval[ub])
            if s is None:
                f.write(f"{ub}  | no_data\n")
                continue
            cur_means[ub] = s["mean"]
            f.write(
                f"{ub}  | {s['mean']:6.3f} | {s['stdev']:6.3f} | "
                f"{s['min']:6.3f} | {s['max']:6.3f} | {s['median']:6.3f}\n"
            )

        # 2. 5 session mean 時系列
        f.write("\n## 2. 5 session mean 時系列 (eval 5-run mean, t/s)\n")
        f.write("ub    | S1_Seval | S2_Sevalcross | S3_Seval3s | S4_Seval4s | S5_Seval5s | range | mean_of_5 | σ_session\n")
        f.write("------|----------|---------------|------------|------------|------------|-------|-----------|----------\n")
        session_means: dict[int, list[float]] = {}
        range_verdicts: dict[int, str] = {}
        for ub in UBS:
            means_per_session = []
            for label in session_labels:
                vs = session_data[label].get(ub, [])
                s = stats(vs)
                if s is not None:
                    means_per_session.append(s["mean"])
                else:
                    means_per_session.append(float("nan"))
            session_means[ub] = means_per_session
            finite = [m for m in means_per_session if not math.isnan(m)]
            if len(finite) >= 2:
                rng = max(finite) - min(finite)
                mm = statistics.mean(finite)
                sig = statistics.pstdev(finite) if len(finite) < 2 else statistics.stdev(finite)
                vr = verdict_range(rng)
                range_verdicts[ub] = vr
                cells = []
                widths = [8, 13, 10, 10, 10]
                for i in range(5):
                    if i < len(means_per_session) and not math.isnan(means_per_session[i]):
                        cells.append(f"{means_per_session[i]:{widths[i]}.3f}")
                    else:
                        cells.append("NA".center(widths[i]))
                f.write(
                    f"{ub}  | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} | {cells[4]} | "
                    f"{rng:5.3f} | {mm:9.3f} | {sig:8.3f}  [{vr}]\n"
                )
            else:
                f.write(f"{ub}  | insufficient session data\n")

        # 3. 1-run ref との再現性（本 Phase）
        f.write("\n## 3. 過去 1-run 参照値との再現性（本 Phase, 再確認）\n")
        f.write("ub    | ref_1run | cur_mean | Δ_1run   | verdict_1run\n")
        f.write("------|----------|----------|----------|-------------\n")
        for ub in UBS:
            s = stats(cur_eval[ub])
            ref = REF_1RUN[ub]
            v = verdict_1run(ref, s)
            if s is None:
                f.write(f"{ub}  | {ref:8.3f} | NA       | NA       | no_data\n")
            else:
                f.write(
                    f"{ub}  | {ref:8.3f} | {s['mean']:8.3f} | "
                    f"{s['mean']-ref:+8.3f} | {v}\n"
                )

        # 4. ピーク ub 順序 (全 session)
        f.write("\n## 4. ピーク ub 順序の session 間安定性\n")
        for idx, label in enumerate(session_labels):
            means_this = {}
            for ub in UBS:
                s = stats(session_data[label].get(ub, []))
                if s is not None:
                    means_this[ub] = s["mean"]
            if len(means_this) == 3:
                order = peak_order(means_this)
                f.write(f"{label} peak order: {order} (means: " +
                        ", ".join(f"ub{u}={means_this[u]:.3f}" for u in order) + ")\n")
            else:
                f.write(f"{label}: data insufficient\n")

        # 5. Welch t (prior 4-session pool vs cur S5)
        f.write("\n## 5. Prior 4-session pool (S1+S2+S3+S4) vs 本 Phase (S5) Welch t\n")
        f.write("ub    | n_prior | mean_prior | n_cur | mean_cur | diff    | SE      | t_welch | sig\n")
        f.write("------|---------|------------|-------|----------|---------|---------|---------|-----\n")
        for ub in UBS:
            prior_pool = []
            for label, _ in PRIOR_TSVS:
                prior_pool.extend(session_data[label].get(ub, []))
            cur = cur_eval[ub]
            w = welch(cur, prior_pool)
            ps = stats(prior_pool)
            cs = stats(cur)
            if w is None or ps is None or cs is None:
                f.write(f"{ub}  | insufficient data\n")
                continue
            sig = "significant" if abs(w["t"]) > 2.0 else "not_sig"
            f.write(
                f"{ub}  | {ps['n']:7d} | {ps['mean']:10.3f} | {cs['n']:5d} | "
                f"{cs['mean']:8.3f} | {w['diff']:+7.3f} | {w['se']:7.3f} | "
                f"{w['t']:+7.2f} | {sig}\n"
            )

        # 6. pooled 25-run
        f.write("\n## 6. Pooled 25-run (S1+S2+S3+S4+S5) 統計\n")
        f.write("ub    | pool_n | mean   | stdev  | min    | max    | median | σ_pool/σ_run_avg\n")
        f.write("------|--------|--------|--------|--------|--------|--------|------------------\n")
        for ub in UBS:
            pool = []
            run_sigmas = []
            for label in session_labels:
                vs = session_data[label].get(ub, [])
                pool.extend(vs)
                s_inner = stats(vs)
                if s_inner is not None and s_inner["n"] >= 2:
                    run_sigmas.append(s_inner["stdev"])
            s = stats(pool)
            if s is None:
                f.write(f"{ub}  | no_data\n")
                continue
            sigma_run_avg = statistics.mean(run_sigmas) if run_sigmas else float("nan")
            ratio = s["stdev"] / sigma_run_avg if sigma_run_avg and sigma_run_avg > 0 else float("nan")
            f.write(
                f"{ub}  | {s['n']:6d} | {s['mean']:6.3f} | {s['stdev']:6.3f} | "
                f"{s['min']:6.3f} | {s['max']:6.3f} | {s['median']:6.3f} | "
                f"{ratio:17.1f}x\n"
            )

        # 7. Run 1 外れ値
        f.write("\n## 7. Run 1 外れ値チェック（本 Phase eval、平均 ± 2σ）\n")
        for ub in UBS:
            vals = cur_eval[ub]
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

        # 8. ub 間有意差（本 Phase 単独）
        f.write("\n## 8. ub 間有意差（本 Phase 5-run プール、Welch t 近似）\n")
        pairs = [(1586, 1584), (1664, 1584), (1586, 1664)]
        for x, y in pairs:
            w = welch(cur_eval[x], cur_eval[y])
            if w is None:
                f.write(f"ub={x} - ub={y}: データ不足\n")
                continue
            sig = "significant" if abs(w["t"]) > 2.0 else "not_sig"
            f.write(
                f"ub={x} - ub={y}: diff={w['diff']:+.3f}, SE={w['se']:.3f}, "
                f"t={w['t']:+.2f} → {sig}\n"
            )

        # 9. 5-session verdict summary
        f.write("\n## 9. 5-session verdict summary (range ベース)\n")
        for ub in UBS:
            if ub in range_verdicts:
                rng = max(m for m in session_means[ub] if not math.isnan(m)) - min(
                    m for m in session_means[ub] if not math.isnan(m)
                )
                f.write(f"ub={ub}: range_Δ={rng:.3f} t/s → {range_verdicts[ub]}\n")

        # 10. ub=1584 崩壊頻度カウント (本 Phase 新規)
        f.write(f"\n## 10. ub=1584 崩壊頻度カウント（eval_mean < {TH_UB1584_COLLAPSE} t/s）\n")
        ub1584_means = session_means.get(1584, [])
        collapse_sessions = []
        for label, mean_v in zip(session_labels, ub1584_means):
            if not math.isnan(mean_v):
                tag = "COLLAPSE" if mean_v < TH_UB1584_COLLAPSE else "normal"
                f.write(f"  {label}: mean={mean_v:.3f} → {tag}\n")
                if mean_v < TH_UB1584_COLLAPSE:
                    collapse_sessions.append(label)
        n_total = sum(1 for m in ub1584_means if not math.isnan(m))
        f.write(f"  → 崩壊 session: {len(collapse_sessions)} / {n_total} = "
                f"{len(collapse_sessions)/n_total*100:.0f}% ({collapse_sessions})\n")

        # 11. ub=1664 時系列パターン分析 (本 Phase 新規)
        f.write("\n## 11. ub=1664 時系列パターン分析 (5 session)\n")
        ub1664_means = session_means.get(1664, [])
        finite_pairs = [(label, m) for label, m in zip(session_labels, ub1664_means) if not math.isnan(m)]
        if len(finite_pairs) >= 5:
            for label, m in finite_pairs:
                f.write(f"  {label}: {m:.3f}\n")
            # 隣接差分（Δ）
            diffs = [finite_pairs[i+1][1] - finite_pairs[i][1] for i in range(len(finite_pairs) - 1)]
            f.write(f"  Δ_pattern: " + " | ".join(f"{d:+.3f}" for d in diffs) + "\n")
            # 符号変化数（zero crossings）
            sign_changes = sum(1 for i in range(len(diffs) - 1)
                              if (diffs[i] > 0) != (diffs[i+1] > 0))
            f.write(f"  符号変化数: {sign_changes} / {len(diffs)-1}\n")
            # 上昇 vs 下降
            ups = sum(1 for d in diffs if d > 0)
            downs = sum(1 for d in diffs if d < 0)
            f.write(f"  上昇 step: {ups}, 下降 step: {downs}\n")
            # bimodal 判定（Δ 符号が交互）
            alternating = all((diffs[i] > 0) != (diffs[i+1] > 0) for i in range(len(diffs) - 1))
            f.write(f"  完全交互（bimodal/periodic 候補）: {'YES' if alternating else 'NO'}\n")
            # 単調性
            monotonic_inc = all(d > 0 for d in diffs)
            monotonic_dec = all(d < 0 for d in diffs)
            f.write(f"  単調増加: {'YES' if monotonic_inc else 'NO'} / 単調減少: {'YES' if monotonic_dec else 'NO'}\n")

        # 12. ピーク順序 5-session 集計
        f.write("\n## 12. ピーク 1 位 ub の出現頻度 (5 session)\n")
        peak_count: dict[int, int] = {ub: 0 for ub in UBS}
        for label in session_labels:
            means_this = {}
            for ub in UBS:
                s = stats(session_data[label].get(ub, []))
                if s is not None:
                    means_this[ub] = s["mean"]
            if len(means_this) == 3:
                order = peak_order(means_this)
                peak_count[order[0]] += 1
        for ub in UBS:
            f.write(f"  ub={ub}: 1位回数 {peak_count[ub]} / {len(session_labels)}\n")

    print(f"[analyze] wrote {verdict_path}")
    with verdict_path.open() as f:
        print(f.read())
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
