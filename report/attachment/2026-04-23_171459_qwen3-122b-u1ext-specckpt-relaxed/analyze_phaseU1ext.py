#!/usr/bin/env python3
"""analyze_phaseU1ext.py - Phase U-1-ext: spec ckpt OFF/ON 集計 + drift 補正

出力:
  - phaseU1ext_stats.csv / .tsv : 条件別 eval_mean, eval_std, prompt_mean,
                                    accept_rate, drift 補正後 eval, speedup
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EVAL_RUNS = 5

# B14b_ts_alt OFF (Phase T-5a-ts2 現最良) baseline
B14B_OFF_REF = 18.664

# Phase U-1 OFF baselines (前回 cross-session reference)
U1_OFF_REF = {
    "prompt_1k":         18.542,
    "prompt_code":       18.940,
    "prompt_repetitive": 18.726,
}

# Config A: B14bC16k
CONFIG_A_CONDS = [
    ("OFF_prompt1k",   "OFF", "prompt_1k"),
    ("ON_prompt1k",    "ON",  "prompt_1k"),
    ("OFF_code",       "OFF", "prompt_code"),
    ("ON_code",        "ON",  "prompt_code"),
    ("OFF_repetitive", "OFF", "prompt_repetitive"),
    ("ON_repetitive",  "ON",  "prompt_repetitive"),
]

# Config B: B18tsBal
CONFIG_B_CONDS = CONFIG_A_CONDS  # 同じ label 体系

CONFIGS = [
    ("B14bC16k",   "A", "Config A (B14b + ctx=16384 + --cache-ram 256)", CONFIG_A_CONDS),
    ("B18tsBal",   "B", "Config B (B18 + -ts 11,14,14,11)",              CONFIG_B_CONDS),
]

KV = "q8_0"
SM = "layer"
UB = 256
THR = 40


def tag(ot_tag: str, label: str, ctx: int) -> str:
    return f"U1ext_{ot_tag}_{label}_t{THR}_kv{KV}_sm{SM}_ctx{ctx}_ub{UB}"


def load_run(outdir: Path, run: int) -> dict:
    p = outdir / f"eval_run{run}.json"
    if not p.exists():
        return {}
    try:
        with p.open() as f:
            return json.load(f)
    except Exception as e:
        print(f"WARN: {p} parse error: {e}", file=sys.stderr)
        return {}


def summarize(outdir: Path) -> dict:
    evals, prompts, pred_ns = [], [], []
    draft_ns, draft_accs = [], []
    all_keys = set()
    for run in range(1, EVAL_RUNS + 1):
        data = load_run(outdir, run)
        if not data:
            continue
        t = data.get("timings", {}) or {}
        all_keys.update(t.keys())
        e = t.get("predicted_per_second")
        p = t.get("prompt_per_second")
        pn = t.get("predicted_n")
        if e is not None: evals.append(float(e))
        if p is not None: prompts.append(float(p))
        if pn is not None: pred_ns.append(int(pn))
        for k in ("draft_n", "n_draft", "draft_total"):
            if k in t:
                draft_ns.append(int(t[k]))
                break
        for k in ("draft_n_accepted", "draft_accepted_n", "n_draft_accepted", "draft_accept"):
            if k in t:
                draft_accs.append(int(t[k]))
                break

    def stats(xs):
        if not xs: return (None, None)
        if len(xs) == 1: return (xs[0], 0.0)
        return (statistics.mean(xs), statistics.stdev(xs))

    e_m, e_s = stats(evals)
    p_m, p_s = stats(prompts)
    accept = None
    if draft_ns and draft_accs and sum(draft_ns) > 0:
        accept = sum(draft_accs) / sum(draft_ns)
    return dict(
        n=len(evals),
        eval_mean=e_m, eval_std=e_s,
        prompt_mean=p_m, prompt_std=p_s,
        predicted_n_mean=(statistics.mean(pred_ns) if pred_ns else None),
        draft_n_total=sum(draft_ns) if draft_ns else None,
        draft_accepted_n_total=sum(draft_accs) if draft_accs else None,
        timings_accept_rate=accept,
        timings_keys=sorted(all_keys),
    )


def main() -> int:
    rows = []
    for ot_tag, conf_id, conf_desc, conds in CONFIGS:
        ctx = 16384 if conf_id == "A" else 32768
        for label, mode, prompt in conds:
            outdir = SCRIPT_DIR / f"out_{tag(ot_tag, label, ctx)}_eval"
            if not outdir.exists():
                continue
            s = summarize(outdir)
            row = dict(config=conf_id, ot_tag=ot_tag, label=label, mode=mode,
                       prompt=prompt, ctx=ctx)
            row.update(s)
            rows.append(row)

    # drift 補正: 各 config 内の同じ prompt での OFF eval_mean を baseline に ON を補正
    # 補正後 ON = ON_raw * (B14B_OFF_REF / OFF_raw)
    # これで B14b_ts_alt 18.664 基準と直接比較可能になる
    for conf_id in ("A", "B"):
        off_by_prompt = {}
        for r in rows:
            if r["config"] == conf_id and r["mode"] == "OFF" and r.get("eval_mean") is not None:
                off_by_prompt[r["prompt"]] = r["eval_mean"]
        for r in rows:
            if r["config"] != conf_id: continue
            off_base = off_by_prompt.get(r["prompt"])
            if off_base is None or r.get("eval_mean") is None:
                r["eval_drift_corrected"] = None
                r["speedup_in_config"] = None
                continue
            # config 内 OFF との比率 → speedup_in_config
            r["speedup_in_config"] = r["eval_mean"] / off_base
            # drift 補正は ON 行でのみ意味あり（OFF 自体 = baseline）
            if r["mode"] == "ON":
                r["eval_drift_corrected"] = r["eval_mean"] * (B14B_OFF_REF / off_base)
            else:
                r["eval_drift_corrected"] = r["eval_mean"] * (B14B_OFF_REF / off_base)

    # CSV/TSV 出力
    headers = ["config", "ot_tag", "ctx", "label", "mode", "prompt", "n",
               "eval_mean", "eval_std", "eval_drift_corrected",
               "prompt_mean", "prompt_std", "predicted_n_mean",
               "draft_n_total", "draft_accepted_n_total", "timings_accept_rate",
               "speedup_in_config"]
    csv = SCRIPT_DIR / "phaseU1ext_stats.csv"
    tsv = SCRIPT_DIR / "phaseU1ext_stats.tsv"
    with csv.open("w") as fc, tsv.open("w") as ft:
        fc.write(",".join(headers) + "\n")
        ft.write("\t".join(headers) + "\n")
        for r in rows:
            vals = []
            for h in headers:
                v = r.get(h)
                if v is None: vals.append("")
                elif isinstance(v, float):
                    if h in ("timings_accept_rate", "speedup_in_config"):
                        vals.append(f"{v:.4f}")
                    elif h in ("predicted_n_mean",):
                        vals.append(f"{v:.1f}")
                    else:
                        vals.append(f"{v:.3f}")
                else:
                    vals.append(str(v))
            fc.write(",".join(vals) + "\n")
            ft.write("\t".join(vals) + "\n")
    print(f"wrote {csv}")
    print(f"wrote {tsv}")

    # stdout に簡易表
    print()
    print(f"{'cfg':<3} {'label':<22} {'mode':<4} {'prompt':<18} {'n':>2} "
          f"{'eval':>7} {'±std':>6} {'drift':>7} {'x(inCfg)':>8}")
    for r in rows:
        em = r.get("eval_mean")
        es = r.get("eval_std")
        ed = r.get("eval_drift_corrected")
        sp = r.get("speedup_in_config")
        em_s = f"{em:.3f}" if em is not None else "-"
        es_s = f"{es:.3f}" if es is not None else "-"
        ed_s = f"{ed:.3f}" if ed is not None else "-"
        sp_s = f"{sp:.4f}" if sp is not None else "-"
        print(f"{r['config']:<3} {r['label']:<22} {r['mode']:<4} {r['prompt']:<18} "
              f"{r['n']:>2} {em_s:>7} {es_s:>6} {ed_s:>7} {sp_s:>8}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
