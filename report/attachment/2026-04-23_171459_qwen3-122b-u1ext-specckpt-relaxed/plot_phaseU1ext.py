#!/usr/bin/env python3
"""plot_phaseU1ext.py - Phase U-1-ext PNG 生成

出力:
  - spec_onoff_eval_ext.png       : config 毎の OFF/ON eval t/s bar
  - spec_onoff_speedup_ext.png    : config 内 ON/OFF 倍率
  - spec_acceptance_ext.png       : acceptance rate (取得できた場合)
  - phaseU1ext_history.png        : 歴代 + U-1-ext best
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
B14B_OFF_REF = 18.664

HISTORY = [
    ("Phase D baseline",       15.030),
    ("Phase T-5 B28",          16.024),
    ("Phase T-5a B18 ub256",   18.103),
    ("Phase T-5a-ts B16",      18.417),
    ("Phase T-5a-ts2 B14b",    18.664),
    ("Phase U-1 B14b OFF mean", 18.736),  # (18.542+18.940+18.726)/3
]

PROMPT_ORDER = ["prompt_1k", "prompt_code", "prompt_repetitive"]


def load_stats(csv_path: Path) -> list:
    rows = []
    if not csv_path.exists():
        return rows
    with csv_path.open() as f:
        reader = csv.DictReader(f)
        for r in reader:
            for k in list(r.keys()):
                if r[k] == "":
                    r[k] = None
                elif k in ("eval_mean", "eval_std", "eval_drift_corrected",
                          "prompt_mean", "prompt_std", "speedup_in_config",
                          "timings_accept_rate"):
                    try:
                        r[k] = float(r[k])
                    except (TypeError, ValueError):
                        r[k] = None
            rows.append(r)
    return rows


def main() -> int:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available", file=sys.stderr)
        return 1

    csv_path = SCRIPT_DIR / "phaseU1ext_stats.csv"
    spec_tsv = SCRIPT_DIR / "spec_stats.tsv"
    rows = load_stats(csv_path)
    if not rows:
        print(f"ERROR: no rows in {csv_path}", file=sys.stderr)
        return 1

    # spec_stats.tsv から accept_rate を tag -> rate の dict で取得
    accept_by_tag = {}
    if spec_tsv.exists():
        with spec_tsv.open() as f:
            header = f.readline().rstrip("\n").split("\t")
            for line in f:
                parts = line.rstrip("\n").split("\t")
                d = dict(zip(header, parts))
                try:
                    ar = float(d.get("accept_rate_tokens") or "")
                except ValueError:
                    ar = None
                accept_by_tag[d["tag"]] = ar

    # config 毎にまとめて描画
    configs = sorted(set((r["config"], r["ot_tag"], int(r["ctx"])) for r in rows))

    # 1) spec_onoff_eval_ext.png: config × prompt × OFF/ON
    n_cfg = len(configs)
    fig, axes = plt.subplots(1, max(n_cfg, 1), figsize=(6 * max(n_cfg, 1), 5), sharey=True)
    if n_cfg == 1:
        axes = [axes]
    for ax, (cfg_id, ot, ctx) in zip(axes, configs):
        x = range(len(PROMPT_ORDER))
        off_vals = []
        on_vals = []
        for p in PROMPT_ORDER:
            off = next((r["eval_mean"] for r in rows
                        if r["config"] == cfg_id and r["prompt"] == p and r["mode"] == "OFF"), None)
            on = next((r["eval_mean"] for r in rows
                       if r["config"] == cfg_id and r["prompt"] == p and r["mode"] == "ON"), None)
            off_vals.append(off if off is not None else 0)
            on_vals.append(on if on is not None else 0)
        w = 0.38
        ax.bar([i - w/2 for i in x], off_vals, w, label="OFF (no spec)", color="#888")
        ax.bar([i + w/2 for i in x], on_vals, w, label="ON (spec ckpt)", color="#2a8")
        ax.axhline(B14B_OFF_REF, color="red", linestyle="--", linewidth=1,
                   label=f"T-5a-ts2 B14b {B14B_OFF_REF}")
        ax.set_xticks(list(x))
        ax.set_xticklabels(PROMPT_ORDER, rotation=15)
        ax.set_title(f"Config {cfg_id} ({ot}, ctx={ctx})", fontsize=11)
        ax.grid(axis="y", alpha=0.3)
        for i, (o, n) in enumerate(zip(off_vals, on_vals)):
            if o: ax.text(i - w/2, o, f"{o:.2f}", ha="center", va="bottom", fontsize=8)
            if n: ax.text(i + w/2, n, f"{n:.2f}", ha="center", va="bottom", fontsize=8)
    axes[0].set_ylabel("eval t/s")
    axes[0].legend(fontsize=8, loc="lower right")
    fig.suptitle("Phase U-1-ext: spec ckpt OFF vs ON (5-run eval)", fontsize=12)
    fig.tight_layout()
    out = SCRIPT_DIR / "spec_onoff_eval_ext.png"
    fig.savefig(out, dpi=120)
    print(f"wrote {out}")
    plt.close(fig)

    # 2) speedup_ext.png
    fig, axes = plt.subplots(1, max(n_cfg, 1), figsize=(6 * max(n_cfg, 1), 5), sharey=True)
    if n_cfg == 1:
        axes = [axes]
    for ax, (cfg_id, ot, ctx) in zip(axes, configs):
        x = range(len(PROMPT_ORDER))
        sps = []
        for p in PROMPT_ORDER:
            sp = next((r["speedup_in_config"] for r in rows
                       if r["config"] == cfg_id and r["prompt"] == p and r["mode"] == "ON"), None)
            sps.append(sp if sp is not None else 0)
        colors = ["#2a8" if s >= 1 else "#d66" for s in sps]
        ax.bar(list(x), sps, color=colors)
        ax.axhline(1.0, color="black", linewidth=1, linestyle="--")
        ax.set_xticks(list(x))
        ax.set_xticklabels(PROMPT_ORDER, rotation=15)
        ax.set_title(f"Config {cfg_id} ({ot})", fontsize=11)
        ax.grid(axis="y", alpha=0.3)
        for i, s in enumerate(sps):
            if s: ax.text(i, s, f"{s:.3f}x", ha="center", va="bottom", fontsize=10)
    axes[0].set_ylabel("ON / OFF eval t/s ratio")
    fig.suptitle("Phase U-1-ext: spec ckpt speedup (within config)", fontsize=12)
    fig.tight_layout()
    out = SCRIPT_DIR / "spec_onoff_speedup_ext.png"
    fig.savefig(out, dpi=120)
    print(f"wrote {out}")
    plt.close(fig)

    # 3) acceptance_ext.png (data があれば)
    has_accept = False
    acc_map = {}
    for r in rows:
        if r["mode"] != "ON": continue
        ctx = int(r["ctx"])
        tag_str = f"U1ext_{r['ot_tag']}_{r['label']}_t40_kvq8_0_smlayer_ctx{ctx}_ub256"
        ar = accept_by_tag.get(tag_str)
        if ar is not None:
            has_accept = True
            acc_map[(r["config"], r["prompt"])] = ar
    if has_accept:
        fig, axes = plt.subplots(1, max(n_cfg, 1), figsize=(6 * max(n_cfg, 1), 5), sharey=True)
        if n_cfg == 1: axes = [axes]
        for ax, (cfg_id, ot, ctx) in zip(axes, configs):
            x = range(len(PROMPT_ORDER))
            ars = [acc_map.get((cfg_id, p), 0) for p in PROMPT_ORDER]
            ax.bar(list(x), ars, color="#48a")
            ax.set_xticks(list(x))
            ax.set_xticklabels(PROMPT_ORDER, rotation=15)
            ax.set_title(f"Config {cfg_id}", fontsize=11)
            ax.set_ylim(0, 1)
            ax.grid(axis="y", alpha=0.3)
            for i, a in enumerate(ars):
                if a: ax.text(i, a, f"{a:.3f}", ha="center", va="bottom", fontsize=9)
        axes[0].set_ylabel("accept rate (#acc / #gen drafts)")
        fig.suptitle("Phase U-1-ext: spec ckpt draft acceptance rate", fontsize=12)
        fig.tight_layout()
        out = SCRIPT_DIR / "spec_acceptance_ext.png"
        fig.savefig(out, dpi=120)
        print(f"wrote {out}")
        plt.close(fig)
    else:
        print("note: no acceptance rate data, skipping acceptance plot")

    # 4) 歴代比較 + U-1-ext best ON (全 config × prompt から max)
    best_on = None
    best_on_label = None
    for r in rows:
        if r["mode"] == "ON" and r.get("eval_mean") is not None:
            if best_on is None or r["eval_mean"] > best_on:
                best_on = r["eval_mean"]
                best_on_label = f"{r['config']} {r['prompt']}"
    # 補正後 best
    best_drift = None
    for r in rows:
        if r["mode"] == "ON" and r.get("eval_drift_corrected") is not None:
            if best_drift is None or r["eval_drift_corrected"] > best_drift:
                best_drift = r["eval_drift_corrected"]

    hist = list(HISTORY)
    if best_on is not None:
        hist.append((f"U-1-ext best ON raw ({best_on_label})", best_on))
    if best_drift is not None:
        hist.append((f"U-1-ext best ON drift-corrected", best_drift))

    labels = [h[0] for h in hist]
    vals = [h[1] for h in hist]
    n_base = len(HISTORY)
    colors = ["#888"] * n_base + ["#2a8"] * (len(hist) - n_base)
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.bar(range(len(hist)), vals, color=colors)
    ax.set_xticks(range(len(hist)))
    ax.set_xticklabels(labels, rotation=22, ha="right", fontsize=9)
    ax.set_ylabel("eval t/s")
    ax.axhline(B14B_OFF_REF, color="red", linestyle="--", linewidth=1, alpha=0.6,
               label=f"B14b_ts_alt {B14B_OFF_REF}")
    ax.set_title("Historical eval t/s: Phase D → Phase U-1-ext")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=8)
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:.3f}", ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    out = SCRIPT_DIR / "phaseU1ext_history.png"
    fig.savefig(out, dpi=120)
    print(f"wrote {out}")
    plt.close(fig)

    return 0


if __name__ == "__main__":
    sys.exit(main())
