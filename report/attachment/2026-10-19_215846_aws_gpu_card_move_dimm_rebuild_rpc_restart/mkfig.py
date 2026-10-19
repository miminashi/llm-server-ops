#!/usr/bin/env python3
"""RPC 分散の速度比較図 (summary.png) を生成する。

入力: 2026-08-16 の abliterated_speed.csv（GPU 7+6 枚構成）と、
      同ディレクトリの abliterated_speed.csv（2026-10-19、GPU 9+4 枚構成）。
      どちらも同じ bench_speed.py・同じプロンプト・同じ回数で採ったもの。

pp と tg は桁が違うので 2 パネルに分ける (2 軸グラフは作らない)。
"""

import csv
import os
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = os.path.dirname(os.path.abspath(__file__))
AUG = os.path.join(HERE, "..", "2026-08-16_221024_deepseek_v4_abliterated_comparison", "abliterated_speed.csv")
OCT = os.path.join(HERE, "abliterated_speed.csv")

# --- 配色 (dataviz スキルの検証済みカテゴリカル slot1/slot2、2026-08-16 の図と同じ) ---
C_AUG = "#2a78d6"   # slot 1 blue
C_OCT = "#eb6834"   # slot 2 orange
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#d8d7d2"

for cand in ("IPAPGothic", "IPAGothic"):
    if any(f.name == cand for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = cand
        break
plt.rcParams["axes.unicode_minus"] = False


def read_speed(path):
    """measure 行だけを条件ごとに平均する (warmup は除外)。"""
    acc = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["kind"] != "measure":
                continue
            d = acc.setdefault(r["cond"], {"pp": [], "tg": []})
            d["pp"].append(float(r["prompt_per_second"]))
            d["tg"].append(float(r["predicted_per_second"]))
    return {c: {k: statistics.mean(v) for k, v in d.items()} for c, d in acc.items()}


aug, oct_ = read_speed(AUG), read_speed(OCT)
conds = [("pp1k", "1,187 tok"), ("pp19k", "19,030 tok")]

fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), facecolor=SURFACE)
for ax, key, title in zip(axes, ("pp", "tg"), ("プロンプト処理 pp (t/s)", "生成 tg (t/s)")):
    ax.set_facecolor(SURFACE)
    w = 0.36
    for i, (c, lab) in enumerate(conds):
        a, o = aug[c][key], oct_[c][key]
        ax.bar(i - w / 2 - 0.01, a, w, color=C_AUG, label="2026-08-16（GPU 7+6 枚）" if i == 0 else None)
        ax.bar(i + w / 2 + 0.01, o, w, color=C_OCT, label="2026-10-19（GPU 9+4 枚）" if i == 0 else None)
        ax.text(i - w / 2 - 0.01, a, f"{a:.1f}", ha="center", va="bottom", fontsize=9, color=INK)
        ax.text(i + w / 2 + 0.01, o, f"{o:.1f}\n({(o / a - 1) * 100:+.0f}%)", ha="center", va="bottom", fontsize=9, color=INK)
    ax.set_xticks(range(len(conds)), [lab for _, lab in conds], color=INK2)
    ax.set_title(title, color=INK, fontsize=11, loc="left")
    ax.set_ylim(0, max(max(aug[c][key], oct_[c][key]) for c, _ in conds) * 1.25)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2)
axes[0].legend(frameon=False, fontsize=9, labelcolor=INK2, loc="upper left")
fig.suptitle("DeepSeek-V4-Flash abliterated Q4_K / RPC 分散 13 GPU / 同一スクリプト・同一プロンプト（measure 平均）",
             color=INK, fontsize=10)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "summary.png"), dpi=130, facecolor=SURFACE)
for c, _ in conds:
    print(c, {k: (round(aug[c][k], 2), round(oct_[c][k], 2), f"{(oct_[c][k] / aug[c][k] - 1) * 100:+.1f}%") for k in ("pp", "tg")})
