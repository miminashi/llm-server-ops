#!/usr/bin/env python3
"""比較サマリ図 (summary.png) を生成する。

入力: baseline_speed.csv / abliterated_speed.csv (同ディレクトリ)
      perplexity は ppl_*.log の Final estimate から読む。

3 パネル構成。pp (t/s) / tg (t/s) / perplexity は単位が違うので
1 枚に重ねず必ず別パネルにする (2 軸グラフは作らない)。
"""

import csv
import os
import re
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = os.path.dirname(os.path.abspath(__file__))

# --- 配色 (dataviz スキルの検証済みカテゴリカル slot1/slot2) ---
# validate_palette.js "#2a78d6,#eb6834" --mode light → ALL CHECKS PASS
C_BASE = "#2a78d6"   # slot 1 blue
C_ABL = "#eb6834"    # slot 2 orange
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#d8d7d2"

for cand in ("IPAPGothic", "IPAGothic"):
    if any(f.name == cand for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = cand
        break
plt.rcParams["axes.unicode_minus"] = False


def read_speed(label):
    """measure 行だけを条件ごとに平均する (warmup は除外)。"""
    pp, tg = {}, {}
    path = os.path.join(HERE, f"{label}_speed.csv")
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["kind"] != "measure":
                continue
            pp.setdefault(r["cond"], []).append(float(r["prompt_per_second"]))
            tg.setdefault(r["cond"], []).append(float(r["predicted_per_second"]))
    return ({k: statistics.mean(v) for k, v in pp.items()},
            {k: statistics.mean(v) for k, v in tg.items()})


def read_ppl(label):
    path = os.path.join(HERE, f"ppl_{label}.log")
    txt = open(path, encoding="utf-8", errors="replace").read()
    m = re.search(r"Final estimate: PPL = ([0-9.]+) \+/- ([0-9.]+)", txt)
    return (float(m.group(1)), float(m.group(2))) if m else (float("nan"), 0.0)


def bars(ax, title, ylabel, cats, base_vals, abl_vals, fmt="{:.1f}",
         base_err=None, abl_err=None):
    x = range(len(cats))
    w = 0.34
    gap = 0.02  # 隣接バー間に 2px 相当の surface ギャップを入れる
    b1 = ax.bar([i - w / 2 - gap / 2 for i in x], base_vals, w,
                label="baseline (unsloth UD-Q4_K_XL)", color=C_BASE,
                yerr=base_err, capsize=3, ecolor=INK2)
    b2 = ax.bar([i + w / 2 + gap / 2 for i in x], abl_vals, w,
                label="abliterated (huihui Q4_K)", color=C_ABL,
                yerr=abl_err, capsize=3, ecolor=INK2)
    # エラーバーがある場合はその上端よりさらに上にラベルを置く（重なり防止）
    for bars_, errs in ((b1, base_err), (b2, abl_err)):
        for i, rect in enumerate(bars_):
            top = rect.get_height() + (errs[i] if errs else 0)
            ax.annotate(fmt.format(rect.get_height()),
                        (rect.get_x() + rect.get_width() / 2, top),
                        textcoords="offset points", xytext=(0, 4),
                        ha="center", fontsize=9, color=INK2)
    ax.set_title(title, fontsize=11, color=INK, pad=10)
    ax.set_ylabel(ylabel, fontsize=9, color=INK2)
    ax.set_xticks(list(x))
    ax.set_xticklabels(cats, fontsize=9, color=INK2)
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, length=0)


def main():
    pp_b, tg_b = read_speed("baseline")
    pp_a, tg_a = read_speed("abliterated")
    ppl_b, err_b = read_ppl("baseline")
    ppl_a, err_a = read_ppl("abliterated")

    cats = ["1,187 tok", "19,030 tok"]
    keys = ["pp1k", "pp19k"]

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.4), facecolor=SURFACE)

    bars(axes[0], "prompt eval (pp)", "tokens/sec", cats,
         [pp_b[k] for k in keys], [pp_a[k] for k in keys])
    bars(axes[1], "token generation (tg)", "tokens/sec", cats,
         [tg_b[k] for k in keys], [tg_a[k] for k in keys], fmt="{:.2f}")
    bars(axes[2], "perplexity (wikitext-2, 40 chunks)", "PPL (低いほど良い)",
         ["wiki.test"], [ppl_b], [ppl_a], fmt="{:.4f}",
         base_err=[err_b], abl_err=[err_a])

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False,
               fontsize=10, bbox_to_anchor=(0.5, -0.01))
    fig.suptitle("DeepSeek-V4-Flash abliterated vs 非 abliterated "
                 "(aws-gpu01+02 / 13 GPU RPC, ctx=131072)",
                 fontsize=12, color=INK, y=0.99)
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    out = os.path.join(HERE, "summary.png")
    fig.savefig(out, dpi=140, facecolor=SURFACE)
    print("wrote", out)

    # 数値も標準出力に出しておく (レポート本文への転記用)
    for k, c in zip(keys, cats):
        print(f"pp {c}: base {pp_b[k]:.2f} / abl {pp_a[k]:.2f} "
              f"({(pp_a[k]/pp_b[k]-1)*100:+.1f}%)")
        print(f"tg {c}: base {tg_b[k]:.2f} / abl {tg_a[k]:.2f} "
              f"({(tg_a[k]/tg_b[k]-1)*100:+.1f}%)")
    print(f"ppl: base {ppl_b:.4f}+/-{err_b:.4f} / abl {ppl_a:.4f}+/-{err_a:.4f} "
          f"({(ppl_a/ppl_b-1)*100:+.1f}%)")


if __name__ == "__main__":
    main()
