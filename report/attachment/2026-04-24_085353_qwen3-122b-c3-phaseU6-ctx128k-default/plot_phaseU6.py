#!/usr/bin/env python3
"""Phase U-6 plots:
  PNG1: eval_tps × ub × 構成 (prompt=1k)
  PNG2: prompt_tps × prompt_len × 構成 (ub=512)
  PNG3: eval_tps × prompt_tag × 構成 (ub=512, eval drop by long ctx)
"""
import csv
import os
import statistics as st

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASELINE = 18.664
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "phaseU6_results.csv")


def to_float(x):
    try:
        return float(x)
    except (ValueError, TypeError):
        return None


def load_eval_rows():
    rows = []
    with open(CSV_PATH) as f:
        r = csv.DictReader(f)
        for row in r:
            if row["role"] != "eval":
                continue
            rows.append(row)
    return rows


def median_by(rows, key_fn, val_key):
    buckets = {}
    for r in rows:
        k = key_fn(r)
        v = to_float(r[val_key])
        if v is None:
            continue
        buckets.setdefault(k, []).append(v)
    return {k: st.median(v) for k, v in buckets.items()}


def plot_eval_vs_ub_by_cond(rows):
    """PNG1: eval_tps × ub × cond (prompt=1k)"""
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    conds = sorted(set(r["cond"] for r in rows))
    colors = {"B14b": "tab:red", "B18": "tab:orange", "B20": "tab:blue"}
    for cond in conds:
        sub = [r for r in rows if r["cond"] == cond and r["prompt_tag"] == "1k"]
        if not sub:
            continue
        med = median_by(sub, lambda r: int(r["ub"]), "eval_tps")
        xs = sorted(med.keys())
        ys = [med[x] for x in xs]
        ax.plot(xs, ys, marker="o", label=f"{cond}", color=colors.get(cond, "gray"))
    ax.axhline(BASELINE, color="k", linestyle="--", linewidth=1, alpha=0.6,
               label=f"baseline B14b_ts_alt@32k ({BASELINE:.3f} t/s)")
    ax.set_xlabel("ubatch size")
    ax.set_ylabel("eval_tps (TG) [t/s]  prompt_1k")
    ax.set_xscale("log", base=2)
    ax.set_xticks([256, 512, 1024])
    ax.set_xticklabels(["256", "512", "1024"])
    ax.set_title("Phase U-6: eval_tps × ub × cond (ctx=131072, prompt=1k)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    out = os.path.join(BASE_DIR, "phaseU6_eval_vs_ub.png")
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"wrote: {out}")


def plot_prompt_tps_vs_promptlen(rows):
    """PNG2: prompt_tps × prompt_len × cond (ub=512)"""
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    conds = sorted(set(r["cond"] for r in rows))
    colors = {"B14b": "tab:red", "B18": "tab:orange", "B20": "tab:blue"}
    PROMPT_N = {"1k": 1000, "32k": 32000, "96k": 96000}
    for cond in conds:
        sub = [r for r in rows if r["cond"] == cond and r["ub"] == "512"]
        if not sub:
            continue
        med = median_by(sub, lambda r: PROMPT_N.get(r["prompt_tag"], 0), "prompt_tps")
        xs = sorted(med.keys())
        ys = [med[x] for x in xs]
        ax.plot(xs, ys, marker="s", label=f"{cond}", color=colors.get(cond, "gray"))
    ax.set_xlabel("prompt length [tokens]")
    ax.set_ylabel("prompt_tps (PP) [t/s]")
    ax.set_xscale("log")
    ax.set_title("Phase U-6: prompt_tps × prompt_len × cond (ctx=131072, ub=512)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    out = os.path.join(BASE_DIR, "phaseU6_prompt_vs_len.png")
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"wrote: {out}")


def plot_eval_drop_by_ctx(rows):
    """PNG3: eval_tps × prompt_tag × cond (ub=512)"""
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    conds = sorted(set(r["cond"] for r in rows))
    colors = {"B14b": "tab:red", "B18": "tab:orange", "B20": "tab:blue"}
    PROMPT_N = {"1k": 1, "32k": 32, "96k": 96}
    for cond in conds:
        sub = [r for r in rows if r["cond"] == cond and r["ub"] == "512"]
        if not sub:
            continue
        med = median_by(sub, lambda r: PROMPT_N.get(r["prompt_tag"], 0), "eval_tps")
        xs = sorted(med.keys())
        ys = [med[x] for x in xs]
        xlabels = [f"{x}k" for x in xs]
        ax.plot(xs, ys, marker="^", label=f"{cond}", color=colors.get(cond, "gray"))
    ax.axhline(BASELINE, color="k", linestyle="--", linewidth=1, alpha=0.6,
               label=f"baseline ({BASELINE:.3f} t/s)")
    ax.set_xlabel("prompt length [k tokens]")
    ax.set_ylabel("eval_tps (TG) [t/s]")
    ax.set_title("Phase U-6: eval_tps × prompt_len × cond (ctx=131072, ub=512)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    out = os.path.join(BASE_DIR, "phaseU6_eval_vs_promptlen.png")
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"wrote: {out}")


def main():
    rows = load_eval_rows()
    if not rows:
        print("no eval rows in CSV")
        return
    plot_eval_vs_ub_by_cond(rows)
    plot_prompt_tps_vs_promptlen(rows)
    plot_eval_drop_by_ctx(rows)


if __name__ == "__main__":
    main()
