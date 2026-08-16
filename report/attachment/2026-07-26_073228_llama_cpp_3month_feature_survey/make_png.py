#!/usr/bin/env python3
"""カテゴリ別コミット数の横棒グラフを生成する。

単一系列 (期間合計コミット数) の magnitude 比較なので単色 1 hue。
dataviz skill の categorical slot 1 (light: #2a78d6) を使用、surface は #fcfcfb。
"""
import csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

SP = "/tmp/claude-1000/-home-ubuntu-projects-llm-server-ops/aef364f9-e763-490b-8e02-b8c9da0546bf/scratchpad"
OUT = ("/home/ubuntu/projects/llm-server-ops/report/attachment/"
       "2026-07-26_073228_llama_cpp_3month_feature_survey/commit_categories.png")

# 日本語フォント (ラベルは英字カテゴリ名だがタイトル/注記が日本語)
_avail = {f.name for f in font_manager.fontManager.ttflist}
for cand in ("Noto Sans CJK JP", "IPAexGothic", "IPAPGothic", "IPAGothic",
             "TakaoGothic", "VL Gothic", "Droid Sans Fallback"):
    if cand in _avail:
        plt.rcParams["font.family"] = cand
        break
else:
    raise SystemExit("日本語フォントが見つからない")
plt.rcParams["axes.unicode_minus"] = False

SURFACE = "#fcfcfb"
SERIES = "#2a78d6"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#dedcd6"

rows = list(csv.reader(open(SP + "/commit_categories.csv")))
header, body = rows[0], rows[1:-1]
data = sorted(((r[0], int(r[-1])) for r in body if r[0] != "other"), key=lambda x: x[1])
other = next(int(r[-1]) for r in body if r[0] == "other")
total = int(rows[-1][-1])

labels = [d[0] for d in data]
vals = [d[1] for d in data]

fig, ax = plt.subplots(figsize=(9.2, 7.4), dpi=160)
fig.patch.set_facecolor(SURFACE)
ax.set_facecolor(SURFACE)

bars = ax.barh(labels, vals, height=0.62, color=SERIES, zorder=3)
# 4px 相当の丸端はランタイムで近似できないため角は角丸なしのまま (matplotlib 制約)

for b, v in zip(bars, vals):
    ax.text(v + max(vals) * 0.012, b.get_y() + b.get_height() / 2, str(v),
            va="center", ha="left", fontsize=9.5, color=INK2, zorder=4)

ax.set_xlim(0, max(vals) * 1.10)
ax.xaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
ax.set_axisbelow(True)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color(GRID)
ax.tick_params(axis="y", length=0, labelsize=10.5, colors=INK)
ax.tick_params(axis="x", length=0, labelsize=9.5, colors=INK2)

ax.set_title("llama.cpp 直近 3 ヶ月のコミット分布 (カテゴリ別)",
             fontsize=14.5, color=INK, pad=36, loc="left")
ax.text(0, 1.012,
        f"2026-04-26 〜 2026-07-25 / 全 {total} commit "
        f"(分類不能な 'other' {other} 件を除く {total - other} 件を表示)",
        transform=ax.transAxes, fontsize=9.5, color=INK2, va="bottom", ha="left")
ax.set_xlabel("コミット数", fontsize=10, color=INK2, labelpad=8)

fig.tight_layout()
fig.savefig(OUT, facecolor=SURFACE)
print("wrote", OUT)
