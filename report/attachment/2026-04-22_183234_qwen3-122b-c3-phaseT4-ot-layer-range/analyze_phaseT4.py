#!/usr/bin/env python3
"""analyze_phaseT4.py - Phase T-4: OT pattern 層範囲スイープ集計

3 OT条件 (A36, B32, C40) × THREADS {32, 40} = 6 条件から
eval_tps / prompt_tps の mean/stdev/min/max を抽出し、
OT × threads pivot 比較表を CSV + Markdown で出力する。
Phase D / S / T-1 q8_0 / T-2 / T-3 best 超え判定 + T-3 「層数=threads drop」仮説判定を付記。
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# (OT_TAG, THREADS) ペアリスト (実行順)
CONDITIONS = [
    ("A36", 40), ("A36", 32),
    ("C40", 40), ("C40", 32),
    ("B32", 40), ("B32", 32),
]
OT_TAGS = ["B32", "A36", "C40"]   # pivot 表示順 (CPU 層数昇順)
THREADS_LIST = [32, 40]
OT_LAYER_COUNT = {"A36": 36, "B32": 32, "C40": 40}
# C40 は threads=32 条件で batch script の修正漏れにより 42 層 CPU (1[0-9]) で実行された。
# 実効 CPU 層数は (OT, THREADS) ペア別に保持する。
OT_LAYER_EFFECTIVE = {
    ("A36", 40): 36, ("A36", 32): 36,
    ("B32", 40): 32, ("B32", 32): 32,
    ("C40", 40): 40,   # 正しい 40 層 (1[0-7])
    ("C40", 32): 42,   # batch 修正漏れで 42 層 (1[0-9])
}
OT_LAYER_RANGE = {
    "A36": "0-13, 20-24, 31-47 (GPU 残: 14-19 + 25-30)",
    "B32": "0-13, 20-24, 31-43 (GPU 残: 14-19 + 25-30 + 44-47)",
    "C40": "0-17, 20-24, 31-47 (GPU 残: 18-19 + 25-30) ※ threads=32 条件のみ 1[0-9] で 42 層 (0-24, 31-47、GPU 残: 25-30)",
}
KV = "q8_0"
SM = "layer"
UB = 1586
CTX = 32768
WARMUP_RUNS = 2
EVAL_RUNS = 5

PEAK_PHASE_D = 15.03
PEAK_PHASE_S = 15.39
PEAK_PHASE_T1_Q8 = 15.016
PEAK_PHASE_T2_BEST = 14.672
PEAK_PHASE_T3_BEST = 14.860     # T-3 最良 (threads=32, A36)
PEAK_PHASE_T3_T40 = 14.781      # T-3 baseline (threads=40, A36)


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


def collect(ot: str, thr: int) -> dict:
    tag_cond = f"{ot}_t{thr}_kv{KV}_sm{SM}_ctx{CTX}_ub{UB}"
    warmup_dir = SCRIPT_DIR / f"out_T4_{tag_cond}_warmup"
    eval_dir = SCRIPT_DIR / f"out_T4_{tag_cond}_1k"

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
    if mean_eval > PEAK_PHASE_T3_BEST:
        return f"surpass_T3_best ({mean_eval:.3f} > {PEAK_PHASE_T3_BEST})"
    if mean_eval > PEAK_PHASE_T2_BEST:
        return f"surpass_T2 ({mean_eval:.3f} > {PEAK_PHASE_T2_BEST})"
    return f"below_T2 ({mean_eval:.3f} ≤ {PEAK_PHASE_T2_BEST})"


def main() -> int:
    data: dict = {}
    for ot, thr in CONDITIONS:
        data[(ot, thr)] = collect(ot, thr)

    # raw TSV
    summary_path = SCRIPT_DIR / "summary_phaseT4.tsv"
    with summary_path.open("w") as f:
        f.write(
            "ot_tag\tcpu_layers\tthreads\tkv\tsplit_mode\tub\tphase\trun\t"
            "eval_tps\tprompt_tps\tprompt_n\tpredicted_n\n"
        )
        for ot, thr in CONDITIONS:
            for phase in ("warmup", "eval"):
                for idx, d in enumerate(data[(ot, thr)][phase], start=1):
                    f.write(
                        f"{ot}\t{OT_LAYER_EFFECTIVE[(ot,thr)]}\t{thr}\t{KV}\t{SM}\t{UB}\t{phase}\t{idx}\t"
                        f"{d.get('eval_tps')}\t{d.get('prompt_tps')}\t"
                        f"{d.get('prompt_n')}\t{d.get('predicted_n')}\n"
                    )
    print(f"[analyze] wrote {summary_path}")

    # 統計 CSV
    stats_path = SCRIPT_DIR / "phaseT4_stats.csv"
    with stats_path.open("w") as f:
        f.write(
            "ot_tag,cpu_layers,threads,kv,split_mode,ub,metric,phase,n,mean,stdev,min,max,median,"
            "surpass_phase_d,surpass_phase_s,surpass_phase_t1_q8,surpass_phase_t2,surpass_phase_t3_best\n"
        )
        for ot, thr in CONDITIONS:
            for metric in ("eval_tps", "prompt_tps"):
                for phase in ("warmup", "eval"):
                    vals = [d.get(metric) for d in data[(ot, thr)][phase]]
                    s = stats(vals)
                    if s is None:
                        f.write(
                            f"{ot},{OT_LAYER_EFFECTIVE[(ot,thr)]},{thr},{KV},{SM},{UB},"
                            f"{metric},{phase},0,,,,,,,,,,\n"
                        )
                        continue
                    is_eval_m = (metric == "eval_tps" and phase == "eval")
                    sd = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_D) else "no"
                    ss = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_S) else "no"
                    st1 = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T1_Q8) else "no"
                    st2 = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T2_BEST) else "no"
                    st3 = "yes" if (is_eval_m and s["mean"] > PEAK_PHASE_T3_BEST) else "no"
                    f.write(
                        f"{ot},{OT_LAYER_EFFECTIVE[(ot,thr)]},{thr},{KV},{SM},{UB},"
                        f"{metric},{phase},{s['n']},{s['mean']:.4f},{s['stdev']:.4f},"
                        f"{s['min']:.4f},{s['max']:.4f},{s['median']:.4f},"
                        f"{sd},{ss},{st1},{st2},{st3}\n"
                    )
    print(f"[analyze] wrote {stats_path}")

    # pivot Markdown
    pivot_path = SCRIPT_DIR / "phaseT4_pivot.md"
    with pivot_path.open("w") as f:
        f.write("# Phase T-4: OT pattern 層範囲スイープ pivot 比較表\n\n")
        f.write(f"- KV={KV}, split-mode={SM}, ctx={CTX}, ub={UB}, fa=1, numactl node1, poll=0\n")
        f.write(f"- warmup {WARMUP_RUNS} run + eval {EVAL_RUNS} run\n")
        f.write("- OT 条件:\n")
        for ot in OT_TAGS:
            f.write(f"  - **{ot}** ({OT_LAYER_COUNT[ot]} 層 CPU、GPU 残: {OT_LAYER_RANGE[ot]})\n")
        f.write(
            f"- ベースライン: Phase D {PEAK_PHASE_D} / Phase S {PEAK_PHASE_S} / "
            f"Phase T-1 q8_0 {PEAK_PHASE_T1_Q8} / Phase T-2 最良 {PEAK_PHASE_T2_BEST} / "
            f"Phase T-3 最良 {PEAK_PHASE_T3_BEST} / T-3 t40 baseline {PEAK_PHASE_T3_T40} (t/s)\n\n"
        )

        # eval_tps OT × threads マトリクス
        f.write("## eval_tps OT × threads マトリクス (mean±stdev, t/s) — eval フェーズ 5 run\n\n")
        f.write("| OT (CPU 層数) | threads=32 | threads=40 | t32 vs t40 |\n")
        f.write("|---------------|-----------|-----------|-----------|\n")
        best_overall = None
        for ot in OT_TAGS:
            row = f"| **{ot}** ({OT_LAYER_COUNT[ot]}) "
            cells = {}
            for thr in (32, 40):
                vals = [d.get("eval_tps") for d in data.get((ot, thr), {}).get("eval", [])]
                s = stats(vals)
                cells[thr] = s
                row += f"| {fmt_cell(s)} "
                if s is not None:
                    if best_overall is None or s["mean"] > best_overall[2]:
                        best_overall = (ot, thr, s["mean"])
            s32, s40 = cells[32], cells[40]
            if s32 is not None and s40 is not None and s40["mean"] > 0:
                delta = (s32["mean"] - s40["mean"]) / s40["mean"] * 100
                row += f"| {delta:+.2f}% |"
            else:
                row += "| NA |"
            f.write(row + "\n")
        f.write("\n")

        # prompt_tps OT × threads マトリクス
        f.write("## prompt_tps OT × threads マトリクス (mean±stdev, t/s)\n\n")
        f.write("| OT (CPU 層数) | threads=32 | threads=40 | t32 vs t40 |\n")
        f.write("|---------------|-----------|-----------|-----------|\n")
        for ot in OT_TAGS:
            row = f"| **{ot}** ({OT_LAYER_COUNT[ot]}) "
            cells = {}
            for thr in (32, 40):
                vals = [d.get("prompt_tps") for d in data.get((ot, thr), {}).get("eval", [])]
                s = stats(vals)
                cells[thr] = s
                row += f"| {fmt_cell(s)} "
            s32, s40 = cells[32], cells[40]
            if s32 is not None and s40 is not None and s40["mean"] > 0:
                delta = (s32["mean"] - s40["mean"]) / s40["mean"] * 100
                row += f"| {delta:+.2f}% |"
            else:
                row += "| NA |"
            f.write(row + "\n")
        f.write("\n")

        # 「層数 = threads で drop」仮説の判定
        f.write("## T-3 仮説判定 (CPU offload 層数 = threads で drop ≥ 1%)\n\n")
        f.write("仮説: OT pattern でマッチする CPU offload 層数と threads 数が一致すると、")
        f.write("OpenMP の expert 層分配が「丁度 1 thread/層」になり、MoE expert routing の非一様な activation が ")
        f.write("idle thread として直接露出して eval_tps が drop する。\n\n")
        f.write("**注記**: C40-t32 は batch script の修正漏れにより実効 42 層 CPU で実行された ")
        f.write("(1[0-9] 指定、本来は 1[0-7] で 40 層)。42 ≠ 32 のため仮説の「不一致側」としては依然有効。\n\n")
        f.write("| OT 条件 | match (層=threads) | other (層≠threads) | match-other | 判定 |\n")
        f.write("|---------|--------------------|--------------------|-----------|------|\n")
        support_count = 0
        inverse_count = 0
        eligible_count = 0
        for ot in OT_TAGS:
            layers = OT_LAYER_COUNT[ot]
            if layers == 32:
                match_thr, other_thr = 32, 40
            elif layers == 40:
                match_thr, other_thr = 40, 32
            else:
                # A36 (36 層、32/40 と非一致) は control
                f.write(f"| {ot} ({layers} 層) | -- | t32 / t40 control | -- | control (T-3 状態の再現) |\n")
                continue
            eligible_count += 1
            m = stats([d.get("eval_tps") for d in data.get((ot, match_thr), {}).get("eval", [])])
            o = stats([d.get("eval_tps") for d in data.get((ot, other_thr), {}).get("eval", [])])
            if m and o and o["mean"] > 0:
                delta = (m["mean"] - o["mean"]) / o["mean"] * 100
                if delta <= -1.0:
                    j = f"**SUPPORT** ({delta:+.2f}%)"
                    support_count += 1
                elif delta >= 1.0:
                    j = f"**INVERSE** ({delta:+.2f}%)"
                    inverse_count += 1
                else:
                    j = f"NEUTRAL ({delta:+.2f}%)"
                f.write(
                    f"| {ot} ({layers} 層) | t{match_thr}: {m['mean']:.3f} | "
                    f"t{other_thr}: {o['mean']:.3f} | {m['mean']-o['mean']:+.3f} t/s | {j} |\n"
                )
            else:
                f.write(f"| {ot} ({layers} 層) | data missing | data missing | -- | no_data |\n")
        f.write("\n")
        # 総合判定
        if eligible_count == 2:
            if support_count == 2:
                final = "**STRONG SUPPORT** (B32-t32 と C40-t40 両方で drop ≥ 1%)"
            elif support_count == 1:
                final = "**PARTIAL SUPPORT** (片方のみで drop ≥ 1%)"
            elif inverse_count >= 1:
                final = "**INVERSE** (層数=threads がむしろ最適、仮説と逆方向)"
            else:
                final = "**REJECT** (両方とも |drop| < 1%、T-3 の 36 drop は別要因)"
        else:
            final = "data 不足のため判定不能"
        f.write(f"### 総合判定: {final}\n\n")

        # 結果サマリ
        f.write("## 結果サマリ\n\n")
        if best_overall:
            ot_b, thr_b, m_b = best_overall
            f.write(f"- **最良 eval 構成**: ot={ot_b} (CPU {OT_LAYER_COUNT[ot_b]} 層) × threads={thr_b}, eval_mean={m_b:.3f} t/s\n")
            f.write(f"- **Phase D (15.03) 超え**: {'YES' if m_b > PEAK_PHASE_D else 'NO'}\n")
            f.write(f"- **Phase S (15.39) 超え**: {'YES' if m_b > PEAK_PHASE_S else 'NO'}\n")
            f.write(f"- **Phase T-1 q8_0 (15.016) 超え**: {'YES' if m_b > PEAK_PHASE_T1_Q8 else 'NO'}\n")
            f.write(f"- **Phase T-3 最良 (14.860) 超え**: {'YES' if m_b > PEAK_PHASE_T3_BEST else 'NO'}\n")
            f.write(f"- **Phase T-3 t40 baseline (14.781) 超え**: {'YES' if m_b > PEAK_PHASE_T3_T40 else 'NO'}\n")
            f.write(f"- **Phase T-2 最良 (14.672) 超え**: {'YES' if m_b > PEAK_PHASE_T2_BEST else 'NO'}\n")
        else:
            f.write("- データ不足\n")
        f.write("\n")

        # 歴代全 Phase 比較
        f.write("## Phase D / S / T-1 / T-2 / T-3 / T-4 全体比較\n\n")
        f.write("| Phase | 条件 (要点) | eval mean (t/s) | T-4 最良との差 |\n")
        f.write("|-------|-------------|----------------|---------------|\n")
        ref_rows = [
            ("D", "threads=40, ub=1586, ctx=32k, OT=36 層", PEAK_PHASE_D),
            ("S", "ctx=65k, ub=512, threads=40 (歴代最高)", PEAK_PHASE_S),
            ("T-1", "KV q8_0, ub=1586, threads=40", PEAK_PHASE_T1_Q8),
            ("T-2 best", "split=layer, q8_0, threads=40", PEAK_PHASE_T2_BEST),
            ("T-3 best", "threads=32, OT=A36 (CPU 36 層)", PEAK_PHASE_T3_BEST),
            ("T-3 t40", "threads=40, OT=A36 (baseline)", PEAK_PHASE_T3_T40),
        ]
        m_b = best_overall[2] if best_overall else None
        for label, cond, val in ref_rows:
            if m_b:
                d = (m_b - val) / val * 100
                f.write(f"| {label} | {cond} | {val:.3f} | {d:+.2f}% |\n")
            else:
                f.write(f"| {label} | {cond} | {val:.3f} | NA |\n")
        # T-4 全条件
        for ot in OT_TAGS:
            for thr in (32, 40):
                vals = [d.get("eval_tps") for d in data.get((ot, thr), {}).get("eval", [])]
                s = stats(vals)
                if s is None:
                    continue
                marker = " (本 Phase 最良)" if best_overall and (best_overall[0] == ot and best_overall[1] == thr) else ""
                if m_b:
                    d_pct = (s["mean"] - m_b) / m_b * 100 if m_b else 0
                    f.write(
                        f"| **T-4** | {ot} (CPU {OT_LAYER_COUNT[ot]} 層) × threads={thr}{marker} | "
                        f"{s['mean']:.3f} | {d_pct:+.2f}% |\n"
                    )
        f.write("\n")

    print(f"[analyze] wrote {pivot_path}")
    with pivot_path.open() as f:
        print(f.read())
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
