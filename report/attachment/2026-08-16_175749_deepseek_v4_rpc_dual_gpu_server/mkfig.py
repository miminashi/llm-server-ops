#!/usr/bin/env python3
"""DeepSeek-V4-Flash RPC 分散構成のサマリ図を生成する。

パレットは dataviz skill の categorical slot 1 (blue) / slot 2 (orange)。
validate_palette.js で ALL CHECKS PASS 済み。
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
matplotlib.rcParams["font.family"] = ["IPAPGothic", "IPAGothic", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
from matplotlib.patches import Patch

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#d8d7d2"
BLUE = "#2a78d6"   # aws-gpu01 (メインホスト)
ORANGE = "#eb6834"  # aws-gpu02 (RPC ワーカー)

# ctx=131072 起動時の nvidia-smi 実測 (MiB)
gpu01_used = [11298, 14712, 11094, 14712, 11298, 14712, 8214]
gpu01_cap = [16384] * 7
gpu02_used = [14666, 14848, 11434, 11230, 11434, 11230]
gpu02_cap = [16384, 16384, 16384, 12288, 16384, 12288]

used = gpu01_used + gpu02_used
cap = gpu01_cap + gpu02_cap
colors = [BLUE] * 7 + [ORANGE] * 6
labels = [f"01:{i}" for i in range(7)] + [f"02:{i}" for i in range(6)]

fig, (ax1, ax2) = plt.subplots(
    1, 2, figsize=(13.5, 5.5), gridspec_kw={"width_ratios": [2.05, 1]}
)
fig.patch.set_facecolor(SURFACE)

# ---- 左: GPU ごとの VRAM 使用量 ----
ax1.set_facecolor(SURFACE)
x = range(13)
# 容量を背景バーで示す (2px 相当の隙間は bar width で確保)
ax1.bar(x, [c / 1024 for c in cap], width=0.74, color=MUTED, zorder=1)
ax1.bar(x, [u / 1024 for u in used], width=0.74, color=colors, zorder=2)

for i, (u, c) in enumerate(zip(used, cap)):
    ax1.text(i, u / 1024 - 0.55, f"{u/1024:.1f}", ha="center", va="top",
             fontsize=8.5, color="white", zorder=3)
    ax1.text(i, c / 1024 + 0.18, f"空 {(c-u)/1024:.1f}", ha="center", va="bottom",
             fontsize=7.5, color=INK2, zorder=3)

ax1.set_xticks(list(x))
ax1.set_xticklabels(labels, fontsize=9, color=INK2)
ax1.set_ylabel("VRAM (GiB)", fontsize=10, color=INK2)
ax1.set_ylim(0, 18.4)
ax1.set_title(
    "13 枚への配分 — 重み 144.4 GiB を含め計 157.1 GiB\n"
    "最小空き 1.03 GiB (aws-gpu02 の 12GB カード)",
    fontsize=11, color=INK, loc="left", pad=12,
)
ax1.spines[["top", "right"]].set_visible(False)
ax1.spines[["left", "bottom"]].set_color(MUTED)
ax1.tick_params(colors=INK2, length=0)
ax1.grid(axis="y", color=MUTED, linewidth=0.7, alpha=0.6, zorder=0)
ax1.set_axisbelow(True)
ax1.legend(
    handles=[
        Patch(facecolor=BLUE, label="aws-gpu01 — メインホスト (P100 16GB x7)"),
        Patch(facecolor=ORANGE, label="aws-gpu02 — RPC ワーカー (16GB x4 + 12GB x2)"),
        Patch(facecolor=MUTED, label="カード容量"),
    ],
    fontsize=8.5, frameon=False, loc="upper left", bbox_to_anchor=(0.0, -0.10),
    labelcolor=INK2, ncol=3, handlelength=1.4, columnspacing=1.6,
)

# ---- 右: スループット ----
ax2.set_facecolor(SURFACE)
groups = ["prompt eval\n(1,215 tok)", "prompt eval\n(19,015 tok)", "token gen\n(1,215 tok)", "token gen\n(19,015 tok)"]
vals = [89.7, 81.7, 13.6, 12.7]
bar_colors = [BLUE, BLUE, ORANGE, ORANGE]
xs = range(4)
ax2.bar(xs, vals, width=0.62, color=bar_colors, zorder=2)
for i, v in enumerate(vals):
    ax2.text(i, v + 2.0, f"{v:.1f}", ha="center", va="bottom",
             fontsize=10, color=INK, zorder=3)

ax2.set_xticks(list(xs))
ax2.set_xticklabels(groups, fontsize=8.5, color=INK2)
ax2.set_ylabel("t/s", fontsize=10, color=INK2)
ax2.set_ylim(0, 104)
ax2.set_title(
    "ctx=131072 でのスループット\n19k トークン時点でも劣化は約 8%",
    fontsize=11, color=INK, loc="left", pad=12,
)
ax2.spines[["top", "right"]].set_visible(False)
ax2.spines[["left", "bottom"]].set_color(MUTED)
ax2.tick_params(colors=INK2, length=0)
ax2.grid(axis="y", color=MUTED, linewidth=0.7, alpha=0.6, zorder=0)
ax2.set_axisbelow(True)

fig.suptitle(
    "DeepSeek-V4-Flash-0731 UD-Q4_K_XL — aws-gpu01 + aws-gpu02 の RPC 分散 (100GbE / RoCEv2)",
    fontsize=13, color=INK, x=0.008, ha="left", y=0.985,
)
fig.tight_layout(rect=[0, 0.055, 1, 0.93])
import sys
fig.savefig(sys.argv[1], dpi=140, facecolor=SURFACE)
print("saved", sys.argv[1])
