#!/usr/bin/env python3
"""analyze_phaseU1.py - Phase U-1: spec ckpt OFF/ON A/B の集計 + PNG 生成

出力:
  - phaseU1_stats.csv / phaseU1_stats.tsv
  - spec_onoff_eval.png
  - spec_onoff_speedup.png
  - spec_acceptance.png (acceptance rate が取れた場合)
  - phaseU1_history.png (歴代 Phase 比較)
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OT_TAG = "B14b"
KV = "q8_0"
SM = "layer"
CTX = 32768
UB = 256
THR = 40
WARMUP_RUNS = 2
EVAL_RUNS = 5

# 条件: (LABEL, MODE, PROMPT_BASE)
# B14b_ts_alt の tight VRAM では spec ckpt + cache-ram が共存できず、
# ctx-checkpoints を減らす / cache-ram 0 / draft-max 縮小 の段階的軽量化を試行した。
CONDITIONS = [
    ("OFF_prompt1k",          "OFF", "prompt_1k"),
    ("OFF_code",              "OFF", "prompt_code"),
    ("OFF_repetitive",        "OFF", "prompt_repetitive"),
    ("ON_prompt1k",           "ON",  "prompt_1k"),   # initial: ctx-ckpt=4, cache-ram on (OOM)
    ("ON_prompt1k_retry",     "ON",  "prompt_1k"),   # retry: ctx-ckpt=1, cpent=-1 (OOM)
    ("ON_prompt1k_nockpt",    "ON",  "prompt_1k"),   # ctx-ckpt=0, cache-ram on (Run 2 OOM)
    ("ON_prompt1k_nockptcache","ON", "prompt_1k"),   # ctx-ckpt=0, cache-ram 0 (warmup 1 OOM)
    ("ON_prompt1k_minimal",   "ON",  "prompt_1k"),   # minimal: draft-max default (16)
    ("ON_code",               "ON",  "prompt_code"),
    ("ON_code_retry",         "ON",  "prompt_code"),
    ("ON_code_nockpt",        "ON",  "prompt_code"),
    ("ON_code_nockptcache",   "ON",  "prompt_code"),
    ("ON_code_minimal",       "ON",  "prompt_code"),
    ("ON_repetitive",         "ON",  "prompt_repetitive"),
    ("ON_repetitive_retry",   "ON",  "prompt_repetitive"),
    ("ON_repetitive_nockpt",  "ON",  "prompt_repetitive"),
    ("ON_repetitive_nockptcache","ON","prompt_repetitive"),
    ("ON_repetitive_minimal", "ON",  "prompt_repetitive"),
]

# 各 prompt で優先的に採用する ON ラベル（minimal → nockptcache → nockpt → retry → 初回 の順に試行）
ON_PREFERRED_ORDER = {
    "prompt_1k":         ["ON_prompt1k_minimal", "ON_prompt1k_nockptcache", "ON_prompt1k_nockpt", "ON_prompt1k_retry", "ON_prompt1k"],
    "prompt_code":       ["ON_code_minimal", "ON_code_nockptcache", "ON_code_nockpt", "ON_code_retry", "ON_code"],
    "prompt_repetitive": ["ON_repetitive_minimal", "ON_repetitive_nockptcache", "ON_repetitive_nockpt", "ON_repetitive_retry", "ON_repetitive"],
}

# 歴代 Phase (T-5a-ts2 から継承)
HISTORY = [
    ("Phase D baseline",     15.030),
    ("Phase T-5 B28",        16.024),
    ("Phase T-5a B18 ub256", 18.103),
    ("Phase T-5a-ts B16",    18.417),
    ("Phase T-5a-ts2 B14b",  18.664),
]


def cond_tag(label: str) -> str:
    return f"U1_{OT_TAG}_{label}_t{THR}_kv{KV}_sm{SM}_ctx{CTX}_ub{UB}"


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
    evals, prompts, draft_ns, draft_accepted_ns, pred_ns = [], [], [], [], []
    all_timings = []
    for run in range(1, EVAL_RUNS + 1):
        data = load_run(outdir, run)
        if not data:
            continue
        t = data.get("timings", {}) or {}
        all_timings.append(t)
        e = t.get("predicted_per_second")
        p = t.get("prompt_per_second")
        pn = t.get("predicted_n")
        if e is not None: evals.append(float(e))
        if p is not None: prompts.append(float(p))
        if pn is not None: pred_ns.append(int(pn))
        # spec ckpt フィールド候補 (PR 後に名前変わる可能性あり: draft_n / n_draft / 等)
        for k in ("draft_n", "n_draft", "draft_total"):
            if k in t:
                draft_ns.append(int(t[k]))
                break
        for k in ("draft_accepted_n", "n_draft_accepted", "draft_accept"):
            if k in t:
                draft_accepted_ns.append(int(t[k]))
                break

    def stats(xs):
        if not xs: return (None, None)
        if len(xs) == 1: return (xs[0], 0.0)
        return (statistics.mean(xs), statistics.stdev(xs))

    eval_mean, eval_std = stats(evals)
    prompt_mean, prompt_std = stats(prompts)

    accept_rate = None
    if draft_ns and draft_accepted_ns and sum(draft_ns) > 0:
        accept_rate = sum(draft_accepted_ns) / sum(draft_ns)

    # timings の全 key を union 集約
    all_keys = set()
    for t in all_timings:
        all_keys.update(t.keys())

    return dict(
        n=len(evals),
        eval_mean=eval_mean, eval_std=eval_std,
        prompt_mean=prompt_mean, prompt_std=prompt_std,
        predicted_n_mean=(statistics.mean(pred_ns) if pred_ns else None),
        draft_n_total=sum(draft_ns) if draft_ns else None,
        draft_accepted_n_total=sum(draft_accepted_ns) if draft_accepted_ns else None,
        accept_rate=accept_rate,
        all_timings_keys=sorted(all_keys),
    )


def main() -> int:
    rows = []
    for label, mode, prompt_base in CONDITIONS:
        tag = cond_tag(label)
        outdir = SCRIPT_DIR / f"out_{tag}_eval"
        if not outdir.exists():
            print(f"WARN: outdir not found: {outdir}", file=sys.stderr)
            continue
        s = summarize(outdir)
        rows.append((label, mode, prompt_base, s))

    # CSV
    csv_path = SCRIPT_DIR / "phaseU1_stats.csv"
    tsv_path = SCRIPT_DIR / "phaseU1_stats.tsv"
    headers = ["label", "mode", "prompt", "n", "eval_mean", "eval_std",
               "prompt_mean", "prompt_std", "predicted_n_mean",
               "draft_n_total", "draft_accepted_n_total", "accept_rate",
               "timings_keys"]
    with csv_path.open("w") as f, tsv_path.open("w") as ftsv:
        f.write(",".join(headers) + "\n")
        ftsv.write("\t".join(headers) + "\n")
        for label, mode, prompt, s in rows:
            vals = [label, mode, prompt, str(s["n"]),
                    f"{s['eval_mean']:.3f}" if s["eval_mean"] is not None else "",
                    f"{s['eval_std']:.3f}" if s["eval_std"] is not None else "",
                    f"{s['prompt_mean']:.3f}" if s["prompt_mean"] is not None else "",
                    f"{s['prompt_std']:.3f}" if s["prompt_std"] is not None else "",
                    f"{s['predicted_n_mean']:.1f}" if s["predicted_n_mean"] is not None else "",
                    str(s["draft_n_total"]) if s["draft_n_total"] is not None else "",
                    str(s["draft_accepted_n_total"]) if s["draft_accepted_n_total"] is not None else "",
                    f"{s['accept_rate']:.4f}" if s["accept_rate"] is not None else "",
                    ";".join(s["all_timings_keys"])]
            f.write(",".join(vals) + "\n")
            ftsv.write("\t".join(vals) + "\n")
    print(f"wrote {csv_path}")
    print(f"wrote {tsv_path}")

    # プロット
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available, skip PNG", file=sys.stderr)
        return 0

    prompts = ["prompt_1k", "prompt_code", "prompt_repetitive"]
    off_evals = []
    on_evals = []
    off_prompts = []
    on_prompts = []
    speedups = []
    acc_rates = []
    for prompt in prompts:
        off = next((s for lbl, m, pr, s in rows if m == "OFF" and pr == prompt), None)
        # 優先順に走査し、最初に eval_mean が取れている条件を採用
        on = None
        for preferred in ON_PREFERRED_ORDER.get(prompt, []):
            candidate = next((s for lbl, m, pr, s in rows
                              if lbl == preferred and s["eval_mean"] is not None), None)
            if candidate is not None:
                on = candidate
                break
        off_eval = off["eval_mean"] if off else None
        on_eval = on["eval_mean"] if on else None
        off_evals.append(off_eval)
        on_evals.append(on_eval)
        off_prompts.append(off["prompt_mean"] if off else None)
        on_prompts.append(on["prompt_mean"] if on else None)
        speedups.append((on_eval / off_eval) if (off_eval and on_eval) else None)
        acc_rates.append(on["accept_rate"] if on else None)

    # 1) eval t/s bar
    fig, ax = plt.subplots(figsize=(9, 5))
    x = range(len(prompts))
    w = 0.35
    off_v = [v if v is not None else 0 for v in off_evals]
    on_v = [v if v is not None else 0 for v in on_evals]
    ax.bar([i - w/2 for i in x], off_v, w, label="OFF (no spec decoding)", color="#888")
    ax.bar([i + w/2 for i in x], on_v, w, label="ON (spec decoding)", color="#2a8")
    ax.axhline(18.664, color="red", linestyle="--", linewidth=1,
               label="T-5a-ts2 B14b 18.664 t/s")
    ax.set_xticks(list(x))
    ax.set_xticklabels(prompts)
    ax.set_ylabel("eval t/s (tokens/s)")
    ax.set_title("Phase U-1: spec ckpt OFF vs ON (B14b, 3 prompts)")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    for i, (o, n) in enumerate(zip(off_v, on_v)):
        if o: ax.text(i - w/2, o, f"{o:.2f}", ha="center", va="bottom", fontsize=9)
        if n: ax.text(i + w/2, n, f"{n:.2f}", ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    out = SCRIPT_DIR / "spec_onoff_eval.png"
    fig.savefig(out, dpi=120)
    print(f"wrote {out}")
    plt.close(fig)

    # 2) speedup
    fig, ax = plt.subplots(figsize=(9, 5))
    sp = [s if s is not None else 0 for s in speedups]
    colors = ["#2a8" if s and s >= 1 else "#d66" for s in speedups]
    ax.bar(list(x), sp, color=colors)
    ax.axhline(1.0, color="black", linewidth=1, linestyle="--")
    ax.set_xticks(list(x))
    ax.set_xticklabels(prompts)
    ax.set_ylabel("ON / OFF eval t/s ratio")
    ax.set_title("Phase U-1: spec ckpt speedup (ON / OFF)")
    ax.grid(axis="y", alpha=0.3)
    for i, s in enumerate(sp):
        if s: ax.text(i, s, f"{s:.3f}x", ha="center", va="bottom", fontsize=10)
    fig.tight_layout()
    out = SCRIPT_DIR / "spec_onoff_speedup.png"
    fig.savefig(out, dpi=120)
    print(f"wrote {out}")
    plt.close(fig)

    # 3) acceptance rate (取得できた場合のみ)
    if any(r is not None for r in acc_rates):
        fig, ax = plt.subplots(figsize=(9, 5))
        ar = [r if r is not None else 0 for r in acc_rates]
        ax.bar(list(x), ar, color="#48a")
        ax.set_xticks(list(x))
        ax.set_xticklabels(prompts)
        ax.set_ylabel("draft accept rate")
        ax.set_ylim(0, 1)
        ax.set_title("Phase U-1: spec ckpt draft acceptance rate")
        ax.grid(axis="y", alpha=0.3)
        for i, r in enumerate(ar):
            if r: ax.text(i, r, f"{r:.3f}", ha="center", va="bottom", fontsize=10)
        fig.tight_layout()
        out = SCRIPT_DIR / "spec_acceptance.png"
        fig.savefig(out, dpi=120)
        print(f"wrote {out}")
        plt.close(fig)

    # 4) 歴代比較 + U-1 best ON
    best_on = max((v for v in on_evals if v is not None), default=None)
    hist = list(HISTORY)
    if best_on is not None:
        hist.append(("Phase U-1 best (ON)", best_on))
    labels = [h[0] for h in hist]
    vals = [h[1] for h in hist]
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = ["#888"] * (len(hist) - 1) + ["#2a8"] if best_on is not None else ["#888"] * len(hist)
    ax.bar(range(len(hist)), vals, color=colors)
    ax.set_xticks(range(len(hist)))
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_ylabel("eval t/s (tokens/s)")
    ax.set_title("Historical eval t/s: Phase D baseline -> Phase U-1")
    ax.grid(axis="y", alpha=0.3)
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:.3f}", ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    out = SCRIPT_DIR / "phaseU1_history.png"
    fig.savefig(out, dpi=120)
    print(f"wrote {out}")
    plt.close(fig)

    return 0


if __name__ == "__main__":
    sys.exit(main())
