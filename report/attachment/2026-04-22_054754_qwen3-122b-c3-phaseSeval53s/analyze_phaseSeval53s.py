#!/usr/bin/env python3
"""analyze_phaseSeval53s.py - Phase S-eval-53session 集計スクリプト

52 session (phaseSeval + phaseSevalcross + phaseSeval3s ... phaseSeval51s + 本 Phase phaseSeval53s) を合算し、
ub 別 n=52 の session 間 σ, 52-session verdict, ピーク順序安定性、pooled 260-run 統計、
ub=1584/1586/1664 崩壊頻度 (Wilson 95% CI)、ub 別時系列パターン分析、
mode 分類比較を出力する。
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
    ("S5_phaseSeval5s",
     SCRIPT_DIR.parent / "2026-04-20_041308_qwen3-122b-c3-phaseSeval5s" / "summary_phaseSeval5s.tsv"),
    ("S6_phaseSeval6s",
     SCRIPT_DIR.parent / "2026-04-20_050710_qwen3-122b-c3-phaseSeval6s" / "summary_phaseSeval6s.tsv"),
    ("S7_phaseSeval7s",
     SCRIPT_DIR.parent / "2026-04-20_061007_qwen3-122b-c3-phaseSeval7s" / "summary_phaseSeval7s.tsv"),
    ("S8_phaseSeval8s",
     SCRIPT_DIR.parent / "2026-04-20_075044_qwen3-122b-c3-phaseSeval8s" / "summary_phaseSeval8s.tsv"),
    ("S9_phaseSeval9s",
     SCRIPT_DIR.parent / "2026-04-20_080258_qwen3-122b-c3-phaseSeval9s" / "summary_phaseSeval9s.tsv"),
    ("S10_phaseSeval10s",
     SCRIPT_DIR.parent / "2026-04-20_085556_qwen3-122b-c3-phaseSeval10s" / "summary_phaseSeval10s.tsv"),
    ("S11_phaseSeval11s",
     SCRIPT_DIR.parent / "2026-04-20_094934_qwen3-122b-c3-phaseSeval11s" / "summary_phaseSeval11s.tsv"),
    ("S12_phaseSeval12s",
     SCRIPT_DIR.parent / "2026-04-20_104503_qwen3-122b-c3-phaseSeval12s" / "summary_phaseSeval12s.tsv"),
    ("S13_phaseSeval13s",
     SCRIPT_DIR.parent / "2026-04-20_113929_qwen3-122b-c3-phaseSeval13s" / "summary_phaseSeval13s.tsv"),
    ("S14_phaseSeval14s",
     SCRIPT_DIR.parent / "2026-04-20_123152_qwen3-122b-c3-phaseSeval14s" / "summary_phaseSeval14s.tsv"),
    ("S15_phaseSeval15s",
     SCRIPT_DIR.parent / "2026-04-20_132400_qwen3-122b-c3-phaseSeval15s" / "summary_phaseSeval15s.tsv"),
    ("S16_phaseSeval16s",
     SCRIPT_DIR.parent / "2026-04-20_142019_qwen3-122b-c3-phaseSeval16s" / "summary_phaseSeval16s.tsv"),
    ("S17_phaseSeval17s",
     SCRIPT_DIR.parent / "2026-04-20_151741_qwen3-122b-c3-phaseSeval17s" / "summary_phaseSeval17s.tsv"),
    ("S18_phaseSeval18s",
     SCRIPT_DIR.parent / "2026-04-20_161642_qwen3-122b-c3-phaseSeval18s" / "summary_phaseSeval18s.tsv"),
    ("S19_phaseSeval19s",
     SCRIPT_DIR.parent / "2026-04-20_212313_qwen3-122b-c3-phaseSeval19s" / "summary_phaseSeval19s.tsv"),
    ("S20_phaseSeval20s",
     SCRIPT_DIR.parent / "2026-04-20_222307_qwen3-122b-c3-phaseSeval20s" / "summary_phaseSeval20s.tsv"),
    ("S21_phaseSeval21s",
     SCRIPT_DIR.parent / "2026-04-20_232604_qwen3-122b-c3-phaseSeval21s" / "summary_phaseSeval21s.tsv"),
    ("S22_phaseSeval22s",
     SCRIPT_DIR.parent / "2026-04-21_002703_qwen3-122b-c3-phaseSeval22s" / "summary_phaseSeval22s.tsv"),
    ("S23_phaseSeval23s",
     SCRIPT_DIR.parent / "2026-04-21_012929_qwen3-122b-c3-phaseSeval23s" / "summary_phaseSeval23s.tsv"),
    ("S24_phaseSeval24s",
     SCRIPT_DIR.parent / "2026-04-21_023213_qwen3-122b-c3-phaseSeval24s" / "summary_phaseSeval24s.tsv"),
    ("S25_phaseSeval25s",
     SCRIPT_DIR.parent / "2026-04-21_032417_qwen3-122b-c3-phaseSeval25s" / "summary_phaseSeval25s.tsv"),
    ("S26_phaseSeval26s",
     SCRIPT_DIR.parent / "2026-04-21_041752_qwen3-122b-c3-phaseSeval26s" / "summary_phaseSeval26s.tsv"),
    ("S27_phaseSeval27s",
     SCRIPT_DIR.parent / "2026-04-21_051039_qwen3-122b-c3-phaseSeval27s" / "summary_phaseSeval27s.tsv"),
    ("S28_phaseSeval28s",
     SCRIPT_DIR.parent / "2026-04-21_060329_qwen3-122b-c3-phaseSeval28s" / "summary_phaseSeval28s.tsv"),
    ("S29_phaseSeval29s",
     SCRIPT_DIR.parent / "2026-04-21_065614_qwen3-122b-c3-phaseSeval29s" / "summary_phaseSeval29s.tsv"),
    ("S30_phaseSeval30s",
     SCRIPT_DIR.parent / "2026-04-21_074512_qwen3-122b-c3-phaseSeval30s" / "summary_phaseSeval30s.tsv"),
    ("S31_phaseSeval31s",
     SCRIPT_DIR.parent / "2026-04-21_083727_qwen3-122b-c3-phaseSeval31s" / "summary_phaseSeval31s.tsv"),
    ("S32_phaseSeval32s",
     SCRIPT_DIR.parent / "2026-04-21_093107_qwen3-122b-c3-phaseSeval32s" / "summary_phaseSeval32s.tsv"),
    ("S33_phaseSeval33s",
     SCRIPT_DIR.parent / "2026-04-21_102734_qwen3-122b-c3-phaseSeval33s" / "summary_phaseSeval33s.tsv"),
    ("S34_phaseSeval34s",
     SCRIPT_DIR.parent / "2026-04-21_112228_qwen3-122b-c3-phaseSeval34s" / "summary_phaseSeval34s.tsv"),
    ("S35_phaseSeval35s",
     SCRIPT_DIR.parent / "2026-04-21_121546_qwen3-122b-c3-phaseSeval35s" / "summary_phaseSeval35s.tsv"),
    ("S36_phaseSeval36s",
     SCRIPT_DIR.parent / "2026-04-21_130908_qwen3-122b-c3-phaseSeval36s" / "summary_phaseSeval36s.tsv"),
    ("S37_phaseSeval37s",
     SCRIPT_DIR.parent / "2026-04-21_140342_qwen3-122b-c3-phaseSeval37s" / "summary_phaseSeval37s.tsv"),
    ("S38_phaseSeval38s",
     SCRIPT_DIR.parent / "2026-04-21_145730_qwen3-122b-c3-phaseSeval38s" / "summary_phaseSeval38s.tsv"),
    ("S39_phaseSeval39s",
     SCRIPT_DIR.parent / "2026-04-21_155525_qwen3-122b-c3-phaseSeval39s" / "summary_phaseSeval39s.tsv"),
    ("S40_phaseSeval40s",
     SCRIPT_DIR.parent / "2026-04-21_164936_qwen3-122b-c3-phaseSeval40s" / "summary_phaseSeval40s.tsv"),
    ("S41_phaseSeval41s",
     SCRIPT_DIR.parent / "2026-04-21_174520_qwen3-122b-c3-phaseSeval41s" / "summary_phaseSeval41s.tsv"),
    ("S42_phaseSeval42s",
     SCRIPT_DIR.parent / "2026-04-21_184122_qwen3-122b-c3-phaseSeval42s" / "summary_phaseSeval42s.tsv"),
    ("S43_phaseSeval43s",
     SCRIPT_DIR.parent / "2026-04-21_194635_qwen3-122b-c3-phaseSeval43s" / "summary_phaseSeval43s.tsv"),
    ("S44_phaseSeval44s",
     SCRIPT_DIR.parent / "2026-04-21_214018_qwen3-122b-c3-phaseSeval44s" / "summary_phaseSeval44s.tsv"),
    ("S45_phaseSeval45s",
     SCRIPT_DIR.parent / "2026-04-21_224532_qwen3-122b-c3-phaseSeval45s" / "summary_phaseSeval45s.tsv"),
    ("S46_phaseSeval46s",
     SCRIPT_DIR.parent / "2026-04-21_234926_qwen3-122b-c3-phaseSeval46s" / "summary_phaseSeval46s.tsv"),
    ("S47_phaseSeval47s",
     SCRIPT_DIR.parent / "2026-04-22_005619_qwen3-122b-c3-phaseSeval47s" / "summary_phaseSeval47s.tsv"),
    ("S48_phaseSeval48s",
     SCRIPT_DIR.parent / "2026-04-22_010836_qwen3-122b-c3-phaseSeval48s" / "summary_phaseSeval48s.tsv"),
    ("S49_phaseSeval49s",
     SCRIPT_DIR.parent / "2026-04-22_020513_qwen3-122b-c3-phaseSeval49s" / "summary_phaseSeval49s.tsv"),
    ("S50_phaseSeval50s",
     SCRIPT_DIR.parent / "2026-04-22_025948_qwen3-122b-c3-phaseSeval50s" / "summary_phaseSeval50s.tsv"),
    ("S51_phaseSeval51s",
     SCRIPT_DIR.parent / "2026-04-22_035441_qwen3-122b-c3-phaseSeval51s" / "summary_phaseSeval51s.tsv"),
    ("S52_phaseSeval52s",
     SCRIPT_DIR.parent / "2026-04-22_044633_qwen3-122b-c3-phaseSeval52s" / "summary_phaseSeval52s.tsv"),
]
CUR_SESSION_LABEL = "S53_phaseSeval53s"

MODE_GROUPS = {
    "mode_A_S1_S3": ["S1_phaseSeval", "S2_phaseSevalcross", "S3_phaseSeval3s"],
    "mode_B_S4_S5": ["S4_phaseSeval4s", "S5_phaseSeval5s"],
    "mode_C_S6": ["S6_phaseSeval6s"],
    "mode_D_S8": ["S8_phaseSeval8s"],
    "prev_S9": ["S9_phaseSeval9s"],
    "prev_S10": ["S10_phaseSeval10s"],
    "prev_S11": ["S11_phaseSeval11s"],
    "prev_S12": ["S12_phaseSeval12s"],
    "prev_S13": ["S13_phaseSeval13s"],
    "prev_S14": ["S14_phaseSeval14s"],
    "prev_S15": ["S15_phaseSeval15s"],
    "prev_S16": ["S16_phaseSeval16s"],
    "prev_S17": ["S17_phaseSeval17s"],
    "prev_S18": ["S18_phaseSeval18s"],
    "prev_S19": ["S19_phaseSeval19s"],
    "prev_S20": ["S20_phaseSeval20s"],
    "prev_S21": ["S21_phaseSeval21s"],
    "prev_S22": ["S22_phaseSeval22s"],
    "prev_S23": ["S23_phaseSeval23s"],
    "prev_S24": ["S24_phaseSeval24s"],
    "prev_S25": ["S25_phaseSeval25s"],
    "prev_S26": ["S26_phaseSeval26s"],
    "prev_S27": ["S27_phaseSeval27s"],
    "prev_S28": ["S28_phaseSeval28s"],
    "prev_S29": ["S29_phaseSeval29s"],
    "prev_S30": ["S30_phaseSeval30s"],
    "prev_S31": ["S31_phaseSeval31s"],
    "prev_S32": ["S32_phaseSeval32s"],
    "prev_S33": ["S33_phaseSeval33s"],
    "prev_S34": ["S34_phaseSeval34s"],
    "prev_S35": ["S35_phaseSeval35s"],
    "prev_S36": ["S36_phaseSeval36s"],
    "prev_S37": ["S37_phaseSeval37s"],
    "prev_S38": ["S38_phaseSeval38s"],
    "prev_S39": ["S39_phaseSeval39s"],
    "prev_S40": ["S40_phaseSeval40s"],
    "prev_S41": ["S41_phaseSeval41s"],
    "prev_S42": ["S42_phaseSeval42s"],
    "prev_S43": ["S43_phaseSeval43s"],
    "prev_S44": ["S44_phaseSeval44s"],
    "prev_S45": ["S45_phaseSeval45s"],
    "prev_S46": ["S46_phaseSeval46s"],
    "prev_S47": ["S47_phaseSeval47s"],
    "prev_S48": ["S48_phaseSeval48s"],
    "prev_S49": ["S49_phaseSeval49s"],
    "prev_S50": ["S50_phaseSeval50s"],
    "prev_S51": ["S51_phaseSeval51s"],
    "prev_S52": ["S52_phaseSeval52s"],
    "cur_S53": ["S53_phaseSeval53s"],
}

TH_CONFIRMED = 0.05
TH_PARTIAL = 0.10

TH_SESSION_INDEP = 0.02
TH_SESSION_PARTIAL = 0.10

# 崩壊判定しきい値（前 Phase 踏襲）
TH_COLLAPSE = 15.0

TAG_PREFIX = "Seval53s_fa1_ctx"


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


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return 0.0, 0.0, 0.0
    p_hat = k / n
    denom = 1 + z * z / n
    center = (p_hat + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n)) / denom
    return p_hat, max(0.0, center - margin), min(1.0, center + margin)


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
    summary_path = SCRIPT_DIR / "summary_phaseSeval53s.tsv"
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
    stats_path = SCRIPT_DIR / "phaseSeval53s_stats.csv"
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
    verdict_path = SCRIPT_DIR / "phaseSeval53s_verdict.txt"
    with verdict_path.open("w") as f:
        f.write("# Phase S-eval-53session verdict\n")
        f.write(f"ctx={CTX}, fa=1, f16/f16 KV, OT_REGEX=MoE only, threads=40, poll=0, numactl node1\n")
        f.write(f"warmup_runs={WARMUP_RUNS}, eval_runs={EVAL_RUNS}\n")
        f.write(f"sessions: {session_labels}\n")
        f.write(
            f"thresholds: 1-run [confirmed <= {TH_CONFIRMED}, partial <= {TH_PARTIAL}], "
            f"session range [independent <= {TH_SESSION_INDEP}, partial <= {TH_SESSION_PARTIAL}]\n"
        )
        f.write(f"崩壊判定: eval_mean < {TH_COLLAPSE} t/s\n\n")

        # 1. 本 Phase (S51) 5-run 統計
        f.write("## 1. 本 Phase (S52) 5-run 統計（eval フェーズ）\n")
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

        # 2. 52 session mean 時系列
        f.write("\n## 2. 52 session mean 時系列 (eval 5-run mean, t/s)\n")
        f.write("ub    | " + " | ".join(f"{lbl[:9]:9s}" for lbl in session_labels) + " | range | mean_all | σ_session\n")
        f.write("------|" + "-|".join(["-" * 11 for _ in session_labels]) + "-|-------|---------|----------\n")
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
                for m in means_per_session:
                    if math.isnan(m):
                        cells.append("   NA    ")
                    else:
                        cells.append(f"{m:9.3f}")
                f.write(
                    f"{ub}  | " + " | ".join(cells) + f" | "
                    f"{rng:5.3f} | {mm:7.3f} | {sig:8.3f}  [{vr}]\n"
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

        # 5. Welch t (prior 50-session pool vs cur S51)
        f.write("\n## 5. Prior 52-session pool (S1..S52) vs 本 Phase (S53) Welch t\n")
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

        # 6. pooled 260-run
        f.write("\n## 6. Pooled 260-run (S1..S52) 統計\n")
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

        # 9. 52-session verdict summary
        f.write("\n## 9. 52-session verdict summary (range ベース)\n")
        for ub in UBS:
            if ub in range_verdicts:
                finite_m = [m for m in session_means[ub] if not math.isnan(m)]
                rng = max(finite_m) - min(finite_m)
                f.write(f"ub={ub}: range_Δ={rng:.3f} t/s → {range_verdicts[ub]}\n")

        # 10. 崩壊頻度カウント (ub=1584, ub=1586, ub=1664 すべて + Wilson 95% CI)
        f.write(f"\n## 10. 崩壊頻度カウント（eval_mean < {TH_COLLAPSE} t/s）\n")
        for ub in UBS:
            means = session_means.get(ub, [])
            collapse_sessions = []
            f.write(f"\n### ub={ub}\n")
            for label, mean_v in zip(session_labels, means):
                if not math.isnan(mean_v):
                    tag = "COLLAPSE" if mean_v < TH_COLLAPSE else "normal"
                    f.write(f"  {label}: mean={mean_v:.3f} → {tag}\n")
                    if mean_v < TH_COLLAPSE:
                        collapse_sessions.append(label)
            n_total = sum(1 for m in means if not math.isnan(m))
            k = len(collapse_sessions)
            p_hat, ci_lo, ci_hi = wilson_ci(k, n_total)
            f.write(f"  → 崩壊 session: {k} / {n_total} = {p_hat*100:.1f}% "
                    f"(Wilson 95% CI: [{ci_lo*100:.1f}%, {ci_hi*100:.1f}%])\n")
            f.write(f"  崩壊 session ラベル: {collapse_sessions}\n")

        # 11. ub=1664 時系列パターン分析
        f.write("\n## 11. ub=1664 時系列パターン分析 (52 session)\n")
        ub1664_means = session_means.get(1664, [])
        finite_pairs = [(label, m) for label, m in zip(session_labels, ub1664_means) if not math.isnan(m)]
        if len(finite_pairs) >= 5:
            for label, m in finite_pairs:
                f.write(f"  {label}: {m:.3f}\n")
            diffs = [finite_pairs[i+1][1] - finite_pairs[i][1] for i in range(len(finite_pairs) - 1)]
            f.write(f"  Δ_pattern: " + " | ".join(f"{d:+.3f}" for d in diffs) + "\n")
            sign_changes = sum(1 for i in range(len(diffs) - 1)
                              if (diffs[i] > 0) != (diffs[i+1] > 0))
            f.write(f"  符号変化数: {sign_changes} / {len(diffs)-1}\n")
            ups = sum(1 for d in diffs if d > 0)
            downs = sum(1 for d in diffs if d < 0)
            f.write(f"  上昇 step: {ups}, 下降 step: {downs}\n")
            alternating = all((diffs[i] > 0) != (diffs[i+1] > 0) for i in range(len(diffs) - 1))
            f.write(f"  完全交互（bimodal/periodic 候補）: {'YES' if alternating else 'NO'}\n")
            monotonic_inc = all(d > 0 for d in diffs)
            monotonic_dec = all(d < 0 for d in diffs)
            f.write(f"  単調増加: {'YES' if monotonic_inc else 'NO'} / 単調減少: {'YES' if monotonic_dec else 'NO'}\n")

        # 11b. ub=1586 時系列パターン分析
        f.write("\n## 11b. ub=1586 時系列パターン分析 (52 session)\n")
        ub1586_means = session_means.get(1586, [])
        finite_pairs = [(label, m) for label, m in zip(session_labels, ub1586_means) if not math.isnan(m)]
        if len(finite_pairs) >= 5:
            for label, m in finite_pairs:
                f.write(f"  {label}: {m:.3f}\n")
            diffs = [finite_pairs[i+1][1] - finite_pairs[i][1] for i in range(len(finite_pairs) - 1)]
            f.write(f"  Δ_pattern: " + " | ".join(f"{d:+.3f}" for d in diffs) + "\n")
            sign_changes = sum(1 for i in range(len(diffs) - 1)
                              if (diffs[i] > 0) != (diffs[i+1] > 0))
            f.write(f"  符号変化数: {sign_changes} / {len(diffs)-1}\n")

        # 11c. ub=1584 時系列パターン分析
        f.write("\n## 11c. ub=1584 時系列パターン分析 (52 session)\n")
        ub1584_means = session_means.get(1584, [])
        finite_pairs = [(label, m) for label, m in zip(session_labels, ub1584_means) if not math.isnan(m)]
        if len(finite_pairs) >= 5:
            for label, m in finite_pairs:
                f.write(f"  {label}: {m:.3f}\n")
            diffs = [finite_pairs[i+1][1] - finite_pairs[i][1] for i in range(len(finite_pairs) - 1)]
            f.write(f"  Δ_pattern: " + " | ".join(f"{d:+.3f}" for d in diffs) + "\n")

        # 12. ピーク順序 52-session 集計
        f.write("\n## 12. ピーク 1 位 ub の出現頻度 (52 session)\n")
        peak_count: dict[int, int] = {ub: 0 for ub in UBS}
        peak_order_counts: dict[tuple, int] = {}
        for label in session_labels:
            means_this = {}
            for ub in UBS:
                s = stats(session_data[label].get(ub, []))
                if s is not None:
                    means_this[ub] = s["mean"]
            if len(means_this) == 3:
                order = peak_order(means_this)
                peak_count[order[0]] += 1
                ot = tuple(order)
                peak_order_counts[ot] = peak_order_counts.get(ot, 0) + 1
        for ub in UBS:
            f.write(f"  ub={ub}: 1位回数 {peak_count[ub]} / {len(session_labels)}\n")
        f.write("\n  ピーク順序パターン集計:\n")
        for order_tup, count in sorted(peak_order_counts.items(), key=lambda x: -x[1]):
            f.write(f"    {order_tup}: {count} / {len(session_labels)}\n")

        # 13. モード分類 (S1-S3 A / S4-S5 B / S6 C / S8 D / S9 / S10 / S11 / S12 / S13) 比較
        f.write("\n## 13. モード分類 (S1-S3 A / S4-S5 B / S6 C / S8 D / S9 / S10 / S11 / S12 / S13) の eval_mean 比較\n")
        f.write("ub    | modeA_mean | modeB_mean | modeC_mean | modeD_mean | S9_mean | S10_mean | S11_mean | S12_mean | closer_to | dA     | dB     | dC     | dD     | dS9    | dS10   | dS11\n")
        f.write("------|------------|------------|------------|------------|---------|----------|----------|----------|-----------|--------|--------|--------|--------|--------|--------|--------\n")
        for ub in UBS:
            mode_A = []
            mode_B = []
            mode_C = []
            mode_D = []
            prev_S9_list = []
            prev_S10_list = []
            prev_S11_list = []
            for lbl in MODE_GROUPS["mode_A_S1_S3"]:
                mode_A.extend(session_data.get(lbl, {}).get(ub, []))
            for lbl in MODE_GROUPS["mode_B_S4_S5"]:
                mode_B.extend(session_data.get(lbl, {}).get(ub, []))
            for lbl in MODE_GROUPS["mode_C_S6"]:
                mode_C.extend(session_data.get(lbl, {}).get(ub, []))
            for lbl in MODE_GROUPS["mode_D_S8"]:
                mode_D.extend(session_data.get(lbl, {}).get(ub, []))
            for lbl in MODE_GROUPS["prev_S9"]:
                prev_S9_list.extend(session_data.get(lbl, {}).get(ub, []))
            for lbl in MODE_GROUPS["prev_S10"]:
                prev_S10_list.extend(session_data.get(lbl, {}).get(ub, []))
            for lbl in MODE_GROUPS["prev_S11"]:
                prev_S11_list.extend(session_data.get(lbl, {}).get(ub, []))
            sa = stats(mode_A)
            sb = stats(mode_B)
            sc = stats(mode_C)
            sd = stats(mode_D)
            s9 = stats(prev_S9_list)
            s10 = stats(prev_S10_list)
            s11 = stats(prev_S11_list)
            s12 = stats(cur_eval[ub])
            if sa is None or sb is None or sc is None or sd is None or s9 is None or s10 is None or s11 is None or s12 is None:
                f.write(f"{ub}  | insufficient data\n")
                continue
            dA = s12["mean"] - sa["mean"]
            dB = s12["mean"] - sb["mean"]
            dC = s12["mean"] - sc["mean"]
            dD = s12["mean"] - sd["mean"]
            dS9 = s12["mean"] - s9["mean"]
            dS10 = s12["mean"] - s10["mean"]
            dS11 = s12["mean"] - s11["mean"]
            d_abs = {"mode_A": abs(dA), "mode_B": abs(dB), "mode_C": abs(dC), "mode_D": abs(dD), "S9": abs(dS9), "S10": abs(dS10), "S11": abs(dS11)}
            closer = min(d_abs, key=d_abs.get)
            f.write(f"{ub}  | {sa['mean']:10.3f} | {sb['mean']:10.3f} | {sc['mean']:10.3f} | {sd['mean']:10.3f} | {s9['mean']:7.3f} | {s10['mean']:8.3f} | {s11['mean']:8.3f} | {s12['mean']:8.3f} | "
                    f"{closer:9s} | {dA:+.3f} | {dB:+.3f} | {dC:+.3f} | {dD:+.3f} | {dS9:+.3f} | {dS10:+.3f} | {dS11:+.3f}\n")

        # 14. warmup1 ub=1584 absolute 値のモード判定
        f.write("\n## 14. warmup1 ub=1584 absolute 帯のモード判定（S40）\n")
        w1_1584 = None
        eval_1584 = stats(cur_eval[1584])
        warmup_runs = cur_data[1584]["warmup"]
        if warmup_runs:
            w1_1584 = warmup_runs[0].get("eval_tps")
        if w1_1584 is not None and eval_1584 is not None:
            delta = w1_1584 - eval_1584["mean"]
            f.write(f"  warmup1 ub=1584 absolute = {w1_1584:.3f}\n")
            f.write(f"  eval mean ub=1584 = {eval_1584['mean']:.3f}\n")
            f.write(f"  Δ(warmup1 - eval_mean) = {delta:+.3f}\n")
            # モード帯判定（S7 で発見された第 4 帯 15.418 も考慮）
            if 14.78 <= w1_1584 <= 15.37:
                band = "mode_B_band (S4-S5: 14.78-15.37)"
            elif 15.51 <= w1_1584 <= 15.78:
                band = "mode_A_band (S1-S3: 15.51-15.78)"
            elif 15.38 <= w1_1584 <= 15.46:
                band = "S7_band (15.418 ± 0.04)"
            else:
                band = f"out_of_prior_bands ({w1_1584:.3f})"
            f.write(f"  判定: {band}\n")
            # Δ 帯判定 (A +0.30〜0.31 / B +0.15〜0.16 / C +0.017 / S7_A +0.296)
            if abs(delta - 0.017) < 0.05:
                dband = f"mode_C_delta (S6: +0.017, Δ={delta:+.3f})"
            elif 0.12 <= delta <= 0.20:
                dband = "mode_B_delta (S4-S5: +0.15〜+0.16)"
            elif 0.27 <= delta <= 0.35:
                dband = "mode_A_delta (S1-S3 / S7: +0.296〜+0.31)"
            else:
                dband = f"out_of_prior_delta_bands ({delta:+.3f})"
            f.write(f"  Δ 判定: {dband}\n")
        else:
            f.write("  warmup1 データ不足\n")

        # 15. prompt_tps 要約
        f.write("\n## 15. prompt_tps (本 Phase eval フェーズ、参考)\n")
        f.write("ub    | mean   | stdev  | min    | max\n")
        f.write("------|--------|--------|--------|--------\n")
        for ub in UBS:
            vals = [d.get("prompt_tps") for d in cur_data[ub]["eval"]]
            s = stats(vals)
            if s is None:
                f.write(f"{ub}  | no_data\n")
                continue
            f.write(f"{ub}  | {s['mean']:6.3f} | {s['stdev']:6.3f} | {s['min']:6.3f} | {s['max']:6.3f}\n")

    print(f"[analyze] wrote {verdict_path}")
    with verdict_path.open() as f:
        print(f.read())
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
