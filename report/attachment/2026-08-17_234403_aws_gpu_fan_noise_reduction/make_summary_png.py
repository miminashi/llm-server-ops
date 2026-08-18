#!/usr/bin/env python3
"""ファン静音化レポート用のサマリ PNG を生成する。"""
import csv
import statistics
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

plt.rcParams["font.family"] = "IPAGothic"
plt.rcParams["axes.unicode_minus"] = False

SCR = "/tmp/claude-1000/-home-ubuntu-projects-llm-server-ops/89bdaa24-b37f-42ec-8348-69258b1ae1b5/scratchpad"
SURFACE = "#fcfcfb"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#8a8984"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"


def fan_mean(row):
    """1 行の FAN1..FAN8 の平均（空欄は除外）。読めない行は None。"""
    vals = [float(row[k]) for k in ("fan1", "fan2", "fan3", "fan4", "fan5",
                                    "fan6", "fan7", "fan8") if row.get(k)]
    return sum(vals) / len(vals) if vals else None


def load_boot(path):
    xs, ys = [], []
    with open(f"{SCR}/{path}") as f:
        for row in csv.DictReader(f):
            m = fan_mean(row)
            if m is not None:
                xs.append(int(row["elapsed_s"]))
                ys.append(m)
    return xs, ys


fig, axes = plt.subplots(1, 3, figsize=(16.5, 5.4), facecolor=SURFACE)
for ax in axes:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(axis="y", color="#e6e5e1", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v):,}"))

# --- (1) duty ↔ RPM 特性 ------------------------------------------------
ax = axes[0]
duty = [8, 12, 16, 24, 32, 100]
rpm = [2100, 2500, 2900, 3800, 4600, 11900]
ax.plot(duty, rpm, color=BLUE, linewidth=2, marker="o", markersize=8,
        markerfacecolor=BLUE, markeredgecolor=SURFACE, markeredgewidth=2,
        label="実測 duty→RPM")
ax.scatter([50], [6500], s=150, marker="X", color=ORANGE, zorder=5,
           edgecolor=SURFACE, linewidth=2)
ax.annotate("変更前: BMC Optimal\n50% / 約6,500rpm", (50, 6500),
            textcoords="offset points", xytext=(-6, 26), fontsize=10,
            color=ORANGE, ha="right", fontweight="bold")
ax.scatter([16], [2900], s=150, marker="X", color=AQUA, zorder=5,
           edgecolor=SURFACE, linewidth=2)
ax.annotate("変更後: 下限 16%\n2,900rpm", (16, 2900),
            textcoords="offset points", xytext=(12, -34), fontsize=10,
            color="#0f7d57", fontweight="bold")
ax.set_title("① duty と回転数の実測特性", color=INK, fontsize=12,
             fontweight="bold", loc="left", pad=12)
ax.set_xlabel("duty (%)", color=INK2, fontsize=10)
ax.set_ylabel("ファン回転数 (rpm)", color=INK2, fontsize=10)
ax.set_xlim(0, 105)
ax.set_ylim(0, 13000)

# --- (2) POST 中の RPM 推移 --------------------------------------------
ax = axes[1]
XMAX = 160  # OS 起動後（smc-fanctl が引き継いだ後）は比較対象外なので切る
series = [
    ("boot_gpu02_suppress.csv", "初期実装 2秒間隔 (BIOS変更前)", ORANGE),
    ("boot_gpu02_after_bios.csv", "初期実装 0.5秒間隔 (BIOS変更後)", BLUE),
    ("boot_gpu02_final.csv", "現行実装 (fan mode を書き直さない)", AQUA),
]
for path, label, color in series:
    xs, ys = load_boot(path)
    pts = [(x, y) for x, y in zip(xs, ys) if x <= XMAX]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    med = statistics.median(ys)  # サンプル数が偶数のときは中央 2 値の平均
    ax.plot(xs, ys, color=color, linewidth=2, marker="o", markersize=4.5,
            markerfacecolor=color, markeredgecolor=SURFACE, markeredgewidth=1.2,
            label=f"{label} — 中央値 {med:,.0f}rpm")
ax.axhline(2900, color=MUTED, linewidth=1.2, linestyle="--")
ax.annotate("定常運転 2,900rpm", (XMAX - 2, 2400), fontsize=9, color=INK2, ha="right")
ax.set_title("② 起動 (POST) 中の平均回転数 — 実装の修正で解消", color=INK, fontsize=12,
             fontweight="bold", loc="left", pad=12)
ax.set_xlabel("電源投入・リセットからの経過秒（値が飛ぶ区間は BMC がセンサ未応答）",
              color=INK2, fontsize=9)
ax.set_ylabel("FAN1-8 平均 (rpm)", color=INK2, fontsize=10)
ax.set_xlim(-4, XMAX)
ax.set_ylim(0, 13000)
leg = ax.legend(frameon=False, fontsize=8.5, loc="upper right")
for t in leg.get_texts():
    t.set_color(INK2)

# --- (3) 定常運転の duty 比較 -------------------------------------------
ax = axes[2]
groups = ["アイドル", "実負荷 (推論)"]
before = [50, 69]     # BMC Optimal の実測 duty（負荷時は 68-70%）
after = [16, 28]      # smc-fanctl（負荷時のピーク）
xpos = [0, 1]
w = 0.36
b1 = ax.bar([x - w / 2 - 0.01 for x in xpos], before, w, color=ORANGE,
            label="変更前: BMC Optimal", edgecolor=SURFACE, linewidth=2)
b2 = ax.bar([x + w / 2 + 0.01 for x in xpos], after, w, color=AQUA,
            label="変更後: smc-fanctl", edgecolor=SURFACE, linewidth=2)
for bars, vals, rpms in ((b1, before, ["約6,500rpm", "約8,500rpm"]),
                         (b2, after, ["2,900rpm", "4,200rpm"])):
    for bar, v, r in zip(bars, vals, rpms):
        ax.annotate(f"{v}%\n{r}", (bar.get_x() + bar.get_width() / 2, v),
                    textcoords="offset points", xytext=(0, 6), ha="center",
                    fontsize=10, color=INK2, fontweight="bold")
ax.set_xticks(xpos)
ax.set_xticklabels(groups, color=INK2, fontsize=10)
ax.set_title("③ 定常運転の duty (低いほど静か)", color=INK, fontsize=12,
             fontweight="bold", loc="left", pad=12)
ax.set_ylabel("duty (%)", color=INK2, fontsize=10)
ax.set_ylim(0, 88)
leg = ax.legend(frameon=False, fontsize=9, loc="upper left")
for t in leg.get_texts():
    t.set_color(INK2)

fig.suptitle("aws-gpu01 / aws-gpu02 ファン静音化の実測サマリ (2026-08-17〜18)",
             color=INK, fontsize=14, fontweight="bold", x=0.012, ha="left", y=0.985)
fig.tight_layout(rect=(0, 0, 1, 0.94))
out = f"{SCR}/summary.png"
fig.savefig(out, dpi=140, facecolor=SURFACE)
print("saved:", out)
