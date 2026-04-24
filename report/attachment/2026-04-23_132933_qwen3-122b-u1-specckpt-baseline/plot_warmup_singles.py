#!/usr/bin/env python3
"""plot_warmup_singles.py - warmup run1 (short haiku) の OFF vs ON 全設定を比較

B14b tight VRAM では ON の eval 5 run が全て crash したため、
warmup run1 (haiku prompt, 短) だけが参考値として取れた。
これをプロットして spec decoding の影響を定性的に示す。
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# (label, outdir basename, description)
WARMUP_RUNS = [
    ("OFF_prompt1k",            "U1_B14b_OFF_prompt1k_t40_kvq8_0_smlayer_ctx32768_ub256_warmup",            "OFF (smoke)"),
    ("OFF_code",                "U1_B14b_OFF_code_t40_kvq8_0_smlayer_ctx32768_ub256_warmup",                 "OFF (main)"),
    ("OFF_repetitive",          "U1_B14b_OFF_repetitive_t40_kvq8_0_smlayer_ctx32768_ub256_warmup",           "OFF (main)"),
    ("ON_ckpt4",                "U1_B14b_ON_prompt1k_t40_kvq8_0_smlayer_ctx32768_ub256_warmup",              "ON ctx-ckpt=4"),
    ("ON_ckpt1_cpent-1",        "U1_B14b_ON_prompt1k_retry_t40_kvq8_0_smlayer_ctx32768_ub256_warmup",        "ON ctx-ckpt=1, cpent=-1"),
    ("ON_ckpt0",                "U1_B14b_ON_prompt1k_nockpt_t40_kvq8_0_smlayer_ctx32768_ub256_warmup",       "ON ctx-ckpt=0"),
    ("ON_ckpt0_cacheram0",      "U1_B14b_ON_prompt1k_nockptcache_t40_kvq8_0_smlayer_ctx32768_ub256_warmup",  "ON ctx-ckpt=0, cache-ram=0"),
    ("ON_ckpt0_draft16",        "U1_B14b_ON_prompt1k_minimal_t40_kvq8_0_smlayer_ctx32768_ub256_warmup",      "ON ctx-ckpt=0, draft-max=16, cache-ram=0"),
    # ON_code_retry warmup run1 (first request after startup)
    ("ON_code_ckpt1",           "U1_B14b_ON_code_retry_t40_kvq8_0_smlayer_ctx32768_ub256_warmup",            "ON code ctx-ckpt=1"),
]

def load_eval(dirname: str, run: int = 1):
    p = SCRIPT_DIR / f"out_{dirname}" / f"eval_run{run}.json"
    if not p.exists():
        return None
    try:
        with p.open() as f:
            d = json.load(f)
        t = d.get("timings", {})
        return t.get("predicted_per_second"), t.get("prompt_per_second"), t.get("prompt_n")
    except Exception:
        return None


def main():
    rows = []
    for lbl, dirn, desc in WARMUP_RUNS:
        v = load_eval(dirn, 1)
        if v is None or v[0] is None:
            rows.append((lbl, None, None, None, desc))
        else:
            rows.append((lbl, float(v[0]), float(v[1]), int(v[2]), desc))

    print("label\teval_t/s\tprompt_t/s\tprompt_n\tdesc")
    for r in rows:
        lbl, ev, pm, pn, desc = r
        ev_s = f"{ev:.3f}" if ev is not None else "n/a"
        pm_s = f"{pm:.3f}" if pm is not None else "n/a"
        pn_s = str(pn) if pn is not None else "n/a"
        print(f"{lbl}\t{ev_s}\t{pm_s}\t{pn_s}\t{desc}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    # warmup haiku (prompt_n ~ 77-82) だけに絞る。OFF_code/OFF_repetitive は warmup も haiku で統一。
    # 全行の prompt_n は 77-82 の short haiku だが, prompt_1k warmup も short haiku (warmup tag=warmup)。
    # ON_code_ckpt1 は warmup 1 が warmup 用 haiku なので同条件。
    filtered = [r for r in rows if r[1] is not None]
    labels = [f"{r[0]}\n({r[4]})" for r in filtered]
    vals = [r[1] for r in filtered]

    colors = []
    for r in filtered:
        if r[0].startswith("OFF"):
            colors.append("#888")
        else:
            colors.append("#2a8")

    fig, ax = plt.subplots(figsize=(13, 6))
    ax.bar(range(len(filtered)), vals, color=colors)
    ax.set_xticks(range(len(filtered)))
    ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=8)
    ax.set_ylabel("eval t/s (warmup run1, short haiku prompt)")
    ax.set_title("Phase U-1: warmup run1 eval t/s - OFF baseline vs ON with various spec config (single-run only, due to VRAM OOM)")
    ax.grid(axis="y", alpha=0.3)
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:.2f}", ha="center", va="bottom", fontsize=8)
    # baseline reference line (OFF mean)
    off_vals = [r[1] for r in filtered if r[0].startswith("OFF") and r[1] is not None]
    if off_vals:
        off_mean = sum(off_vals) / len(off_vals)
        ax.axhline(off_mean, color="red", linestyle="--", linewidth=1,
                   label=f"OFF warmup mean = {off_mean:.3f} t/s")
        ax.legend()
    fig.tight_layout()
    out = SCRIPT_DIR / "spec_warmup_singles.png"
    fig.savefig(out, dpi=120)
    print(f"wrote {out}")
    plt.close(fig)


if __name__ == "__main__":
    main()
