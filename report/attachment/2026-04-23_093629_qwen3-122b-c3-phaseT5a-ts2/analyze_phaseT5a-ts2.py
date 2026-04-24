#!/usr/bin/env python3
"""analyze_phaseT5a-ts2.py - Phase T-5a-ts2: B14 × tensor-split で 19+ 突破試行

5 条件の eval_tps / prompt_tps の mean/stdev/min/max を抽出し、
- 条件別実行順 1D 表 (drift 補正前・補正後)
- session drift bracket (B18_default_a 起点 / 終点、2 点 linear)
- B14 fit 達成と eval 影響評価
- B16_ts_skew の cross-session 再現性 (T-5a-ts 18.417 との一致)
- T-5a-ub baseline (18.103) との独立再現性
- 歴代 Phase 全比較
を CSV / Markdown で出力する。

attachments/tag_cond 命名は T5ats2_* (batch_T5ats2.sh と整合)
TS 値は batch_T5ats2.sh の env var override で決まるため、本スクリプトも同じ env を尊重。
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# TS 値は batch スクリプトと同じ env var で override 可能
TS_B14_PRIMARY = os.environ.get("TS_B14_PRIMARY", "11,12,13,14")
TS_B14_ALT = os.environ.get("TS_B14_ALT", "11,12,13,14")
TS_B16_SKEW = os.environ.get("TS_B16_SKEW", "11,12,13,13")

# CONDITIONS: (LABEL, OT_TAG, CPU_LAYERS, TS_STR, run_index, NOTE)
# PRIMARY: OT-c (remove layer 23,24 from CPU) = VRAM 最バランス
# ALT:     OT-b (remove layer 24,39 from CPU) = CUDA3 tight だが OT 比較
CONDITIONS = [
    ("B18_default_a",     "B18",  18, "",              1, "drift 起点・T-5a-ub 18.103 / T-5a-ts 17.964 cross-session 再現 (4 回目)"),
    ("B14c_ts_primary",   "B14c", 14, TS_B14_PRIMARY,  2, "B14 本命 (OT-c: layer 23,24 GPU、dry D5 VRAM 最バランス)"),
    ("B14b_ts_alt",       "B14b", 14, TS_B14_ALT,      3, "B14 alt (OT-b: layer 24,39 GPU、同 ts で OT 比較)"),
    ("B16_ts_skew",       "B16",  16, TS_B16_SKEW,     4, "T-5a-ts peak 18.417 cross-session 再現 (ベンチマーク)"),
    ("B18_default_z",     "B18",  18, "",              5, "drift 終点 (2-pt linear bracket)"),
]

KV = "q8_0"
SM = "layer"
CTX = 32768
UB = 256
THR = 40
WARMUP_RUNS = 2
EVAL_RUNS = 5

PEAK_PHASE_D = 15.030
PEAK_PHASE_S = 15.390
PEAK_PHASE_T1_Q8 = 15.016
PEAK_PHASE_T2_BEST = 14.672
PEAK_PHASE_T3_BEST = 14.860
PEAK_PHASE_T4_BEST = 15.494
PEAK_PHASE_T5_BEST = 16.024
PEAK_PHASE_T5E_BEST = 16.380
PEAK_PHASE_T5F_BEST = 16.455
PEAK_PHASE_T5A_BEST = 18.006
PEAK_PHASE_T5A_UB_BEST = 18.103   # T-5a-ub B18_ub256 (実測)
PEAK_PHASE_T5A_UB_CORR = 18.209   # 補正後 (参考)
PEAK_PHASE_T5A_THR_BEST = 17.988  # T-5a-thr thr40a (実測)
PEAK_PHASE_T5A_TS_BEST = 18.417   # T-5a-ts B16_ts_skew (実測、直前歴代 #1)
PEAK_PHASE_T5A_TS_B16_ALT = 18.332  # T-5a-ts B16_ts_alt
PEAK_PHASE_T5A_TS_B18_TS_EQUAL = 18.120  # T-5a-ts B18_ts_equal


def ts_tag(ts: str) -> str:
    return ("_ts" + ts.replace(",", "-")) if ts else ""


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


def collect(label: str, ts: str) -> dict:
    tag_cond = f"{label}_t{THR}_kv{KV}_sm{SM}_ctx{CTX}_ub{UB}{ts_tag(ts)}"
    warmup_dir = SCRIPT_DIR / f"out_T5ats2_{tag_cond}_warmup"
    eval_dir = SCRIPT_DIR / f"out_T5ats2_{tag_cond}_1k"
    warmup, ev = [], []
    for r in range(1, WARMUP_RUNS + 1):
        d = load_run(warmup_dir, r)
        if d:
            warmup.append(d)
    for r in range(1, EVAL_RUNS + 1):
        d = load_run(eval_dir, r)
        if d:
            ev.append(d)
    return {"warmup": warmup, "eval": ev, "tag_cond": tag_cond}


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
    if mean_eval > 19.0:
        return f"**🎯 BREAK 19+ (歴代最高 + 1 t/s 突破)** ({mean_eval:.3f} > 19.0)"
    if mean_eval > PEAK_PHASE_T5A_TS_BEST + 0.10:
        return f"**SURPASS_T5a-ts +0.10 (新記録確実)** ({mean_eval:.3f} > {PEAK_PHASE_T5A_TS_BEST + 0.10:.3f})"
    if mean_eval > PEAK_PHASE_T5A_TS_BEST:
        return f"**SURPASS_T5a-ts (新記録)** ({mean_eval:.3f} > {PEAK_PHASE_T5A_TS_BEST})"
    if mean_eval > PEAK_PHASE_T5A_UB_BEST:
        return f"surpass_T5a-ub ({mean_eval:.3f} > {PEAK_PHASE_T5A_UB_BEST})"
    if mean_eval > PEAK_PHASE_T5A_BEST:
        return f"surpass_T5a ({mean_eval:.3f} > {PEAK_PHASE_T5A_BEST})"
    if mean_eval > PEAK_PHASE_T5F_BEST:
        return f"surpass_T5f ({mean_eval:.3f} > {PEAK_PHASE_T5F_BEST})"
    if mean_eval > PEAK_PHASE_D:
        return f"surpass_D ({mean_eval:.3f} > {PEAK_PHASE_D})"
    return f"below_D ({mean_eval:.3f} ≤ {PEAK_PHASE_D})"


def linear_quad_drift(bracket_points):
    """3 点 bracket [(idx, mean), ...] から線形 fit + 2 次 fit を計算し hybrid 採用判定。

    return: dict(linear_per_run, linear_predicted_mid, linear_residual,
                 quad_a, quad_b, quad_c, linear_r2, recommendation,
                 corrector(idx) -> correction)
    線形 R² < 0.95 のとき 2 次回帰を採用 (hybrid)。
    """
    pts = sorted(bracket_points, key=lambda p: p[0])
    if len(pts) < 2:
        return {"recommendation": "insufficient", "corrector": lambda idx: 0.0}
    # 線形 fit (起点・終点のみ): per_run = (z - a) / (idx_z - idx_a)
    a_idx, a_y = pts[0]
    z_idx, z_y = pts[-1]
    per_run = (z_y - a_y) / (z_idx - a_idx) if z_idx != a_idx else 0.0
    out = {
        "linear_per_run": per_run,
        "linear_a_idx": a_idx,
        "linear_a_y": a_y,
        "n_points": len(pts),
    }
    if len(pts) == 3:
        m_idx, m_y = pts[1]
        pred_m = a_y + per_run * (m_idx - a_idx)
        residual = m_y - pred_m
        out.update({
            "linear_predicted_mid": pred_m,
            "linear_residual": residual,
            "linear_residual_ok": abs(residual) < 0.05,
        })
        # 線形 R² (3 点に対して)
        ys_pred_lin = [a_y + per_run * (idx - a_idx) for idx, _ in pts]
        ys = [y for _, y in pts]
        ss_res = sum((y - p) ** 2 for y, p in zip(ys, ys_pred_lin))
        ss_tot = sum((y - sum(ys) / 3) ** 2 for y in ys)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 1.0
        out["linear_r2"] = r2
        # 2 次 fit (3 点なら必ず通る、つまり R²=1.0、純粋に hybrid モデル)
        # y = a*idx^2 + b*idx + c
        import numpy as np
        try:
            coeff = np.polyfit([p[0] for p in pts], [p[1] for p in pts], 2)
            out["quad_a"], out["quad_b"], out["quad_c"] = float(coeff[0]), float(coeff[1]), float(coeff[2])
        except Exception:
            out["quad_a"] = out["quad_b"] = out["quad_c"] = None

        # 採用判定: R² >= 0.95 なら線形、< 0.95 なら 2 次採用
        use_quad = r2 < 0.95 and out.get("quad_a") is not None
        out["recommendation"] = "quadratic" if use_quad else "linear"
        if use_quad:
            qa, qb, qc = out["quad_a"], out["quad_b"], out["quad_c"]
            # baseline = 起点 (a_idx) のときの値、補正は (predicted_baseline - predicted_idx)
            baseline_val = qa * a_idx ** 2 + qb * a_idx + qc
            def _corr(idx):
                return baseline_val - (qa * idx ** 2 + qb * idx + qc)
            out["corrector"] = _corr
        else:
            def _corr(idx):
                return -per_run * (idx - a_idx)
            out["corrector"] = _corr
    else:
        out["recommendation"] = "linear"
        def _corr(idx):
            return -per_run * (idx - a_idx)
        out["corrector"] = _corr
    return out


def main() -> int:
    data: dict = {}
    for label, ot, cpu, ts, idx, note in CONDITIONS:
        data[label] = collect(label, ts)

    # raw TSV
    summary_path = SCRIPT_DIR / "summary_phaseT5a-ts2.tsv"
    with summary_path.open("w") as f:
        f.write(
            "label\tot_tag\tcpu_layers\tts\tthreads\tkv\tsplit_mode\tctx\tub\trun_index\tphase\trun\t"
            "eval_tps\tprompt_tps\tprompt_n\tpredicted_n\n"
        )
        for label, ot, cpu, ts, idx, note in CONDITIONS:
            for phase in ("warmup", "eval"):
                for k, d in enumerate(data[label][phase], start=1):
                    f.write(
                        f"{label}\t{ot}\t{cpu}\t{ts}\t{THR}\t{KV}\t{SM}\t{CTX}\t{UB}\t{idx}\t{phase}\t{k}\t"
                        f"{d.get('eval_tps')}\t{d.get('prompt_tps')}\t"
                        f"{d.get('prompt_n')}\t{d.get('predicted_n')}\n"
                    )
    print(f"[analyze] wrote {summary_path}")

    # 統計 CSV
    stats_path = SCRIPT_DIR / "phaseT5a-ts2_stats.csv"
    with stats_path.open("w") as f:
        f.write(
            "label,ot_tag,cpu_layers,ts,threads,kv,split_mode,ctx,ub,run_index,metric,phase,"
            "n,mean,stdev,min,max,median,"
            "surpass_phase_d,surpass_phase_s,surpass_phase_t4,surpass_phase_t5,surpass_phase_t5e,"
            "surpass_phase_t5f,surpass_phase_t5a,surpass_phase_t5a_ub,surpass_19plus\n"
        )
        for label, ot, cpu, ts, idx, note in CONDITIONS:
            for metric in ("eval_tps", "prompt_tps"):
                for phase in ("warmup", "eval"):
                    vals = [d.get(metric) for d in data[label][phase]]
                    s = stats(vals)
                    if s is None:
                        f.write(
                            f"{label},{ot},{cpu},{ts},{THR},{KV},{SM},{CTX},{UB},{idx},"
                            f"{metric},{phase},0,,,,,,,,,,,,,,\n"
                        )
                        continue
                    is_eval_m = (metric == "eval_tps" and phase == "eval")
                    flags = []
                    for ref in (PEAK_PHASE_D, PEAK_PHASE_S, PEAK_PHASE_T4_BEST,
                                PEAK_PHASE_T5_BEST, PEAK_PHASE_T5E_BEST,
                                PEAK_PHASE_T5F_BEST, PEAK_PHASE_T5A_BEST,
                                PEAK_PHASE_T5A_UB_BEST, 19.0):
                        flags.append("yes" if (is_eval_m and s["mean"] > ref) else "no")
                    f.write(
                        f"{label},{ot},{cpu},\"{ts}\",{THR},{KV},{SM},{CTX},{UB},{idx},"
                        f"{metric},{phase},{s['n']},{s['mean']:.4f},{s['stdev']:.4f},"
                        f"{s['min']:.4f},{s['max']:.4f},{s['median']:.4f},"
                        + ",".join(flags) + "\n"
                    )
    print(f"[analyze] wrote {stats_path}")

    # Pivot Markdown
    pivot_path = SCRIPT_DIR / "phaseT5a-ts2_pivot.md"
    with pivot_path.open("w") as f:
        f.write("# Phase T-5a-ts2: B14 × tensor-split で 19+ 突破試行 pivot\n\n")
        f.write(f"- ctx=32k, ub={UB}, KV={KV}, split-mode={SM}, threads={THR}, fa=1, numactl node1, poll=0\n")
        f.write(f"- warmup {WARMUP_RUNS} run + eval {EVAL_RUNS} run\n")
        f.write(
            f"- ベースライン: D {PEAK_PHASE_D} / S {PEAK_PHASE_S} / "
            f"T-5 {PEAK_PHASE_T5_BEST} / T-5f {PEAK_PHASE_T5F_BEST} / "
            f"T-5a {PEAK_PHASE_T5A_BEST} / T-5a-ub {PEAK_PHASE_T5A_UB_BEST} / "
            f"T-5a-thr {PEAK_PHASE_T5A_THR_BEST} / "
            f"**T-5a-ts {PEAK_PHASE_T5A_TS_BEST}** (直前歴代 #1、B16×`-ts 11,12,13,13`) (t/s)\n\n"
        )

        # 条件別実行順
        f.write("## eval/prompt 条件別 (実行順, mean±stdev, t/s)\n\n")
        f.write("| # | label | OT | CPU | TS | 役割 | eval_mean±stdev | prompt_mean±stdev | 判定 |\n")
        f.write("|---|-------|----|-----|-----|------|-----------------|-------------------|------|\n")
        eval_map = {}
        prompt_map = {}
        best_overall = None
        for label, ot, cpu, ts, idx, note in CONDITIONS:
            vs_e = [d.get("eval_tps") for d in data[label]["eval"]]
            vs_p = [d.get("prompt_tps") for d in data[label]["eval"]]
            se, sp = stats(vs_e), stats(vs_p)
            eval_map[label] = se
            prompt_map[label] = sp
            verd = verdict(se["mean"] if se else None)
            ts_show = ts if ts else "(default)"
            f.write(f"| {idx} | {label} | {ot} | {cpu} | `{ts_show}` | {note} | {fmt_cell(se)} | {fmt_cell(sp)} | {verd} |\n")
            if se is not None and (best_overall is None or se["mean"] > best_overall[2]):
                best_overall = (label, ot, se["mean"])
        f.write("\n")

        # drift bracket (2 点 linear)
        f.write("## Session drift bracket (B18_default_a 起点 / 終点、2-pt linear)\n\n")
        s_a = eval_map.get("B18_default_a")
        s_z = eval_map.get("B18_default_z")
        bracket_pts = []
        if s_a:
            bracket_pts.append((1, s_a["mean"]))
        if s_z:
            bracket_pts.append((5, s_z["mean"]))  # run_index 5 = 終点

        drift_info = linear_quad_drift(bracket_pts)
        ref_a = s_a  # alias for downstream sections
        if s_a and s_z:
            delta = s_z["mean"] - s_a["mean"]
            dpct = delta / s_a["mean"] * 100
            f.write("| label | 役割 | run_index | eval_mean | 起点比 |\n")
            f.write("|-------|------|-----------|-----------|--------|\n")
            f.write(f"| B18_default_a | drift 起点 | 1 | {s_a['mean']:.3f} | -- |\n")
            f.write(f"| B18_default_z | drift 終点 | 5 | {s_z['mean']:.3f} | {delta:+.3f} t/s ({dpct:+.2f}%) |\n\n")
            adelta = abs(delta)
            if adelta < 0.20:
                judge = "**drift 健全** (< 0.20 t/s、本 Phase 目標)"
            elif adelta < 0.40:
                judge = "**drift 許容** (0.20-0.40 t/s、目標ギリギリ)"
            elif adelta < 0.60:
                judge = "**drift 要注意** (0.40-0.60 t/s)"
            else:
                judge = "**drift 大** (≥ 0.60 t/s、T-5a-ts 0.818 と同等)"
            f.write(f"### drift 判定: {judge} (|差| = {adelta:.3f} t/s, per_run = {drift_info['linear_per_run']:+.4f})\n\n")

            # cross-session 再現性 (T-5a-ts B18_default_a = 17.964, T-5a-ub = 18.103)
            f.write(f"### B18 default の cross-session 再現性\n\n")
            f.write("| label | eval_mean | T-5a-ts B18_default_a (17.964) 差 | T-5a-ub baseline (18.103) 差 | 判定 |\n")
            f.write("|-------|-----------|-----------------------------------|------------------------------|------|\n")
            for lbl, sm_ in (("B18_default_a", s_a), ("B18_default_z", s_z)):
                dd_ts = sm_["mean"] - 17.964
                dd_ub = sm_["mean"] - PEAK_PHASE_T5A_UB_BEST
                judg = "再現 (±0.5 内)" if abs(dd_ub) <= 0.5 else ("**逸脱**" if abs(dd_ub) > 1.0 else "やや逸脱")
                f.write(f"| {lbl} | {sm_['mean']:.3f} | {dd_ts:+.3f} | {dd_ub:+.3f} | {judg} |\n")
            f.write("\n")

            # drift 補正適用 (2-pt linear 採用)
            corrector = drift_info["corrector"]
            f.write(
                f"### drift 補正 (linear 2-pt, "
                f"per_run={drift_info.get('linear_per_run', 0):+.4f} t/s/run)\n\n"
            )
            f.write("| # | label | OT | TS | 実測 eval_mean | 補正後 eval_mean | 補正後 - T-5a-ts (18.417) | 補正後 - 19.0 |\n")
            f.write("|---|-------|----|-----|----------------|------------------|---------------------------|----------------|\n")
            corrected_map = {}
            for label, ot, cpu, ts, idx, note in CONDITIONS:
                s = eval_map.get(label)
                if s is None:
                    f.write(f"| {idx} | {label} | {ot} | `{ts or '(default)'}` | no_data | -- | -- | -- |\n")
                    continue
                corr_val = s["mean"] + corrector(idx)
                corrected_map[label] = corr_val
                d_t5ats = corr_val - PEAK_PHASE_T5A_TS_BEST
                d_19 = corr_val - 19.0
                star = ""
                if d_t5ats > 0.10:
                    star = " **★ 新記録**"
                elif d_t5ats > 0:
                    star = " (やや上回る)"
                if d_19 > 0:
                    star = " **🎯 19+ 突破**"
                f.write(
                    f"| {idx} | {label} | {ot} | `{ts or '(default)'}` | {s['mean']:.3f} | **{corr_val:.3f}**{star} | {d_t5ats:+.3f} | {d_19:+.3f} |\n"
                )
            f.write("\n")

            if corrected_map:
                best_corr = max(corrected_map.items(), key=lambda kv: kv[1])
                f.write(
                    f"**補正後最良**: {best_corr[0]} (corrected = {best_corr[1]:.3f} t/s, "
                    f"T-5a-ts 比 {best_corr[1] - PEAK_PHASE_T5A_TS_BEST:+.3f} t/s, "
                    f"19.0 比 {best_corr[1] - 19.0:+.3f} t/s)\n\n"
                )
        else:
            f.write("(drift bracket データ不足、補正スキップ)\n\n")

        # B14 fit 評価 (本 Phase の主目的)
        f.write("## B14 fit 達成と eval 影響評価 (本 Phase 主目的)\n\n")
        f.write("| label | OT | TS | eval_mean | T-5a-ts (18.417) 差 | B18_default_a 比 | B14 評価 |\n")
        f.write("|-------|----|-----|-----------|----------------------|------------------|----------|\n")
        for lbl in ("B14c_ts_primary", "B14b_ts_alt"):
            s = eval_map.get(lbl)
            ts_val = next((c[3] for c in CONDITIONS if c[0] == lbl), "")
            if not s:
                f.write(f"| {lbl} | `{ts_val}` | no_data (OOM 等) | -- | -- | **B14 fit 失敗** |\n")
                continue
            d_t5ats = s["mean"] - PEAK_PHASE_T5A_TS_BEST
            d_a = (s["mean"] - ref_a["mean"]) if ref_a else None
            if s["mean"] > 19.0:
                judg = "**🎯 B14 fit + 19+ 突破**"
            elif d_t5ats > 0.10:
                judg = "**B14 fit + 新記録 (有意)**"
            elif d_t5ats > 0:
                judg = "B14 fit + 微改善 (再現性要)"
            elif d_t5ats > -0.30:
                judg = "B14 fit、eval 同等 (改善なし)"
            else:
                judg = "**B14 fit、eval 大幅悪化**"
            d_a_s = f"{d_a:+.3f}" if d_a is not None else "--"
            ot_tag = next((c[1] for c in CONDITIONS if c[0] == lbl), "")
            f.write(f"| {lbl} | {ot_tag} | `{ts_val}` | {s['mean']:.3f} | {d_t5ats:+.3f} | {d_a_s} | {judg} |\n")
        f.write("\n")

        # B16_ts_skew cross-session 再現性 (T-5a-ts peak ベンチマーク)
        f.write("## B16_ts_skew cross-session 再現性 (T-5a-ts 18.417 peak との一致)\n\n")
        s_b16 = eval_map.get("B16_ts_skew")
        if s_b16:
            dd = s_b16["mean"] - PEAK_PHASE_T5A_TS_BEST
            if abs(dd) <= 0.10:
                jr = "**再現良好** (±0.10 内、T-5a-ts peak と一致)"
            elif abs(dd) <= 0.30:
                jr = "再現 (±0.30 内)"
            elif abs(dd) <= 0.50:
                jr = "やや逸脱 (0.30-0.50 差)"
            else:
                jr = "**大幅逸脱 (測定系異常疑い)**"
            f.write(f"| label | TS | eval_mean | T-5a-ts (18.417) 差 | 判定 |\n")
            f.write(f"|-------|-----|-----------|----------------------|------|\n")
            f.write(f"| B16_ts_skew | `{TS_B16_SKEW}` | {s_b16['mean']:.3f} | {dd:+.3f} | {jr} |\n\n")
        else:
            f.write("(B16_ts_skew データなし、cross-session 再現性評価スキップ)\n\n")

        # 結果サマリ
        f.write("## 結果サマリ\n\n")
        if best_overall:
            lbl_b, ot_b, m_b = best_overall
            f.write(f"- **最良 eval 構成 (実測)**: label={lbl_b} (OT={ot_b}, ub={UB}, ctx=32k, threads={THR}), eval_mean={m_b:.3f} t/s\n")
            f.write(f"- **🎯 19+ 突破**: {'**YES**' if m_b > 19.0 else 'NO'}\n")
            f.write(f"- **Phase T-5a-ts ({PEAK_PHASE_T5A_TS_BEST}) 超え**: {'**YES (歴代新記録)**' if m_b > PEAK_PHASE_T5A_TS_BEST else 'NO'}\n")
            f.write(f"- **Phase T-5a-ub ({PEAK_PHASE_T5A_UB_BEST}) 超え**: {'YES' if m_b > PEAK_PHASE_T5A_UB_BEST else 'NO'}\n")
            f.write(f"- **Phase T-5a ({PEAK_PHASE_T5A_BEST}) 超え**: {'YES' if m_b > PEAK_PHASE_T5A_BEST else 'NO'}\n")
            f.write(f"- **Phase D ({PEAK_PHASE_D}) 超え**: {'YES' if m_b > PEAK_PHASE_D else 'NO'}\n")
            f.write(f"- B18_default_a (T-5a-ts cross-session 再現): {ref_a['mean']:.3f} t/s\n" if ref_a else "")
        else:
            f.write("- データ不足\n")
        f.write("\n")

        # 全 Phase 比較
        f.write("## 全 Phase 比較\n\n")
        f.write("| Phase | 条件 (要点) | eval mean (t/s) | T-5a-ts2 最良との差 |\n")
        f.write("|-------|-------------|-----------------|----------------------|")
        f.write("\n")
        ref_rows = [
            ("D", "threads=40, ub=1586, ctx=32k, OT=A36", PEAK_PHASE_D),
            ("S", "ctx=65k, ub=512, threads=40, A36", PEAK_PHASE_S),
            ("T-5 best", "B28 × ub=1586", PEAK_PHASE_T5_BEST),
            ("T-5e best", "B28 × ctx=32k × ub=512", PEAK_PHASE_T5E_BEST),
            ("T-5f best", "B28 × ub=512 微細", PEAK_PHASE_T5F_BEST),
            ("T-5a best", "B18 × ub=512 × thr=40", PEAK_PHASE_T5A_BEST),
            ("T-5a-ub best", "B18 × ub=256 × thr=40", PEAK_PHASE_T5A_UB_BEST),
            ("T-5a-thr", "B18 × ub=256 × thr=40 (再測定)", PEAK_PHASE_T5A_THR_BEST),
            ("**T-5a-ts best**", "**B16 × `-ts 11,12,13,13` (直前歴代 #1)**", PEAK_PHASE_T5A_TS_BEST),
        ]
        m_b = best_overall[2] if best_overall else None
        for phase_lbl, cond, val in ref_rows:
            if m_b:
                d = (m_b - val) / val * 100
                f.write(f"| {phase_lbl} | {cond} | {val:.3f} | {d:+.2f}% |\n")
            else:
                f.write(f"| {phase_lbl} | {cond} | {val:.3f} | NA |\n")
        for label, ot, cpu, ts, idx, note in CONDITIONS:
            s = eval_map.get(label)
            if s is None:
                continue
            marker = " (**本 Phase 最良**)" if best_overall and best_overall[0] == label else ""
            if m_b:
                d_pct = (s["mean"] - m_b) / m_b * 100
                ts_show = f", TS=`{ts}`" if ts else ""
                f.write(
                    f"| **T-5a-ts2** | {label} (OT={ot}{ts_show}, {note}){marker} | "
                    f"{s['mean']:.3f} | {d_pct:+.2f}% |\n"
                )
        f.write("\n")

    print(f"[analyze] wrote {pivot_path}")
    with pivot_path.open() as f:
        print(f.read())
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
