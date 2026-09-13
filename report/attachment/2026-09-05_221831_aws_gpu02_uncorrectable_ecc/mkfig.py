#!/usr/bin/env python3
"""aws-gpu02 の uncorrectable ECC 調査のサマリ図を生成する。

左2枚: 2026-09-02 と 2026-09-05 の各時間帯について、OS ブートセッション・ハング・
       BMC SEL / BIOS SMBIOS Event Log が記録した uncorrectable ECC を並べた時系列
右1枚: BIOS が OS に見せているメモリ (96GB) と iMC が実際に訓練しているメモリ (160GB) の差
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Patch
from datetime import datetime

plt.rcParams["font.family"] = "IPAGothic"
plt.rcParams["axes.unicode_minus"] = False
T = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
N = lambda s: mdates.date2num(T(s))

# journalctl --list-boots より (JST)。hang=True は痕跡なしで停止した回
BOOTS = [
    ("2026-09-01 22:27:33", "2026-09-02 00:35:01", True),
    ("2026-09-02 01:16:10", "2026-09-02 01:17:12", True),
    ("2026-09-02 13:47:00", "2026-09-02 16:09:36", False),
    ("2026-09-05 18:04:10", "2026-09-05 20:28:42", True),
    ("2026-09-05 20:43:18", "2026-09-05 20:45:51", True),
    ("2026-09-05 22:21:01", "2026-09-05 22:29:04", False),
    ("2026-09-05 22:31:20", "2026-09-05 22:38:04", False),
    ("2026-09-05 22:39:36", "2026-09-06 21:53:00", False),   # 対策後。23h14m 無停止で継続中
]
SEL_UCE = ["2026-09-02 01:15:26", "2026-09-02 01:15:26", "2026-09-02 01:20:07",
           "2026-09-02 01:20:08", "2026-09-02 13:46:23", "2026-09-02 13:46:23",
           "2026-09-05 20:29:04", "2026-09-05 20:29:04", "2026-09-05 20:42:36",
           "2026-09-05 21:00:17", "2026-09-05 21:00:17"]
BIOS_UCE = [("2026-09-02 01:15:28", 1), ("2026-09-02 01:15:28", 1),
            ("2026-09-02 01:20:09", 1), ("2026-09-02 01:20:09", 1),
            ("2026-09-02 13:46:23", 0), ("2026-09-02 13:46:23", 0),
            ("2026-09-05 20:29:07", 1), ("2026-09-05 20:42:37", 1),
            ("2026-09-05 21:00:19", 1), ("2026-09-05 21:00:19", 1)]
# POST がブートを抜けられなかった回 (ジャーナルが残っていないので手動)
POST_STUCK = [("2026-09-05 20:52:00", "2026-09-05 21:02:00"),
              ("2026-09-05 21:53:55", "2026-09-05 22:01:30")]

fig = plt.figure(figsize=(15.5, 6.0))
gs = fig.add_gridspec(1, 3, width_ratios=[1.0, 1.55, 1.15], wspace=0.32)
axA, axB, ax2 = (fig.add_subplot(gs[0]), fig.add_subplot(gs[1]), fig.add_subplot(gs[2]))

def draw(ax, lo, hi, title, ylabels):
    for s, e, hung in BOOTS:
        ax.barh(0, N(e) - N(s), left=N(s), height=0.42,
                color="#c0392b" if hung else "#27ae60", alpha=0.75)
        if hung:
            ax.plot(N(e), 0, marker="x", ms=13, mew=3, color="#7b241c", zorder=6)
    for s, e in POST_STUCK:
        ax.barh(0, N(e) - N(s), left=N(s), height=0.42,
                color="#7f8c8d", alpha=0.75, hatch="//")
    for t in SEL_UCE:
        ax.plot(N(t), 1.0, marker="v", ms=11, color="#e67e22", zorder=5)
    for t, ok in BIOS_UCE:
        ax.plot(N(t), 1.75, marker="v", ms=11,
                color="#8e44ad" if ok else "#95a5a6", zorder=5)
    ax.set_ylim(-0.55, 2.45)
    ax.set_xlim(N(lo), N(hi))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(axis="x", alpha=0.3)
    ax.set_title(title, fontsize=11)
    ax.set_yticks([0, 1.0, 1.75])
    ax.set_yticklabels(ylabels, fontsize=9)

draw(axA, "2026-09-02 00:20:00", "2026-09-02 02:00:00", "2026-09-02 未明",
     ["OS ブートセッション", "BMC SEL", "BIOS Event Log"])
axA.xaxis.set_major_locator(mdates.MinuteLocator(interval=30))
draw(axB, "2026-09-05 20:20:00", "2026-09-05 23:00:00", "2026-09-05 夜（本セッション）",
     ["", "", ""])
axB.xaxis.set_major_locator(mdates.MinuteLocator(interval=30))
axA.set_yticklabels(["OS ブートセッション", "BMC SEL\nUncorrectable ECC",
                     "BIOS SMBIOS Event Log"], fontsize=9)

axB.axvline(N("2026-09-05 22:37:30"), color="#2c3e50", ls="--", lw=1.8)
axB.text(N("2026-09-05 22:36:40"), -0.5, "Patrol Scrub を Disable ",
         fontsize=9.5, va="bottom", ha="right", color="#2c3e50", weight="bold")
axB.annotate("23h14m 無停止で継続中\n(09-06 21:53 時点)", xy=(N("2026-09-05 22:58:00"), 0),
             xytext=(N("2026-09-05 22:22:00"), 0.62), fontsize=9, color="#1e8449", weight="bold",
             ha="center", va="bottom",
             arrowprops=dict(arrowstyle="->", color="#1e8449", lw=1.6))
axB.legend(handles=[Patch(color="#27ae60", alpha=.75, label="正常稼働"),
                    Patch(color="#c0392b", alpha=.75, label="痕跡なしでハング"),
                    Patch(color="#7f8c8d", alpha=.75, hatch="//", label="POST / ブートで停止"),
                    plt.Line2D([], [], marker="v", ls="", color="#e67e22", label="SEL: Uncorrectable ECC"),
                    plt.Line2D([], [], marker="v", ls="", color="#8e44ad", label="BIOS: P2_DIMME1"),
                    plt.Line2D([], [], marker="v", ls="", color="#95a5a6", label="BIOS: 位置デコード破損")],
           loc="upper left", fontsize=8, ncol=2, framealpha=.92)

# ---- 右: BIOS が見せるメモリ vs iMC が訓練しているメモリ ----
labels = ["P1_DIMMA1\n(Kingston)", "P1_DIMMA2\n(Micron)", "P1_DIMMA3\n(Micron)",
          "P2_DIMME1", "P2_DIMME2"]
mapped  = [32, 32, 32, 0, 0]
hidden  = [0, 0, 0, 32, 32]
x = list(range(len(labels)))
ax2.bar(x, mapped, color="#27ae60", alpha=.85, label="OS のアドレス空間にある（計 96GB）")
ax2.bar(x, hidden, color="#c0392b", alpha=.5, hatch="//",
        label="iMC は訓練済みだが OS からは\n見えない（計 64GB）")
ax2.set_xticks(x); ax2.set_xticklabels(labels, fontsize=8.5)
ax2.set_ylabel("容量 (GB)"); ax2.set_ylim(0, 46)
ax2.annotate("Uncorrectable ECC は\nここで起きている", xy=(2.7, 30), xytext=(1.45, 20),
             fontsize=9.5, color="#7b241c", ha="center", weight="bold",
             bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="#7b241c", alpha=.95),
             arrowprops=dict(arrowstyle="->", color="#7b241c", lw=1.7))
ax2.grid(axis="y", alpha=0.3)
ax2.legend(fontsize=8, loc="upper left", framealpha=.92)
ax2.set_title("故障 DIMM は OS の外側にある\nEDAC mc0 = 65,536MB / numactl node1 = 0MB", fontsize=11)

fig.savefig("summary.png", dpi=130, bbox_inches="tight")
print("wrote summary.png")
