#!/usr/bin/env python3
"""レポート用の図を生成する。

左: PR ごとの -ub 上限と prompt 処理速度 (ctx=32768 / -fa on / 11k needle)
右: depth collapse 再現マトリクス (報告者ごとのバックエンドと本セッションの P100 結果)
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

plt.rcParams["font.family"] = ["IPAGothic", "DejaVu Sans"]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.6))

# ---- 左: -ub × pp ----
UBS = [64, 512, 1024, 2048, 4096]
x = np.arange(len(UBS))

# 2026-09-02 実測 (本セッション)
pr27773 = [None, 49.2, None, None, 49.7]
pr27754 = [None, 59.0, 58.8, 58.9, 58.8]
# 2026-08-29 実測 (前回セッション、比較用)
prev754 = [34.6, 57.9, 67.9, None, None]

def plot(ax, vals, **kw):
    xs = [i for i, v in enumerate(vals) if v is not None]
    ys = [v for v in vals if v is not None]
    ax.plot(xs, ys, **kw)

plot(ax1, pr27754, marker="o", ms=9, lw=2.4, color="#1f77b4", label="#27754 (2026-09-02, 949f7efb09)")
plot(ax1, pr27773, marker="s", ms=9, lw=2.4, color="#d62728", label="#27773 (2026-09-02, 7de5a8e39)")
plot(ax1, prev754, marker="^", ms=8, lw=1.8, ls="--", color="#7f7f7f",
     label="#27754 (2026-08-29, f30bed8871)")

# 前回の起動上限を示す
ax1.axvspan(2.5, 4.5, color="#ffcccc", alpha=0.35, zorder=0)
ax1.text(3.5, 20, "前回 #27754 は\nここで起動不可\n(#27752 は 512 も不可)",
         ha="center", va="center", fontsize=10, color="#8b0000")

ax1.set_xticks(x); ax1.set_xticklabels([str(u) for u in UBS])
ax1.set_xlabel("-ub (物理 microbatch)")
ax1.set_ylabel("prompt 処理速度 [tok/s]")
ax1.set_title("-ub 上限と prompt 速度 (ctx=32768 / -fa on / 11k needle)\n"
              "両 PR とも -ub 4096 まで通るようになった", fontsize=11)
ax1.set_ylim(0, 80); ax1.grid(alpha=0.3); ax1.legend(fontsize=9, loc="lower right")

# ---- 右: depth collapse マトリクス ----
rows = [
    ("feni6\nMetal (M3 Ultra)\nUD-Q4_K_XL", "-fa off / ub 512",  "#27754", "collapse"),
    ("feni6\nMetal (M3 Ultra)\nUD-Q4_K_XL", "-fa off / ub 128",  "#27754", "ok"),
    ("feni6\nMetal\n(cross-check)",          "-fa off / ub 512",  "#27752", "collapse"),
    ("matteoscalabrini\nCUDA 5x RTX 3090\n(sm_86)", "-fa on / ub 4096", "#27752", "ok"),
    ("本セッション\nCUDA 13x P100 (sm_60)\nRPC 分散 / UD-IQ4_XS", "-fa on / ub 4096", "#27754", "ok"),
    ("本セッション\nCUDA 13x P100 (sm_60)\nRPC 分散 / UD-IQ4_XS", "-fa on / ub 4096", "#27773", "ok"),
]
COL = {"collapse": "#d62728", "ok": "#2ca02c", "na": "#cccccc"}
LBL = {"collapse": "@@@@ 崩壊", "ok": "正常 (合言葉 2 か所とも正解)"}

for i, (env, cfg, pr, res) in enumerate(rows):
    y = len(rows) - 1 - i
    ax2.barh(y, 1.0, color=COL[res], alpha=0.85, height=0.62)
    ax2.text(0.02, y, f"{pr}  /  {cfg}", va="center", ha="left",
             fontsize=10, color="white", fontweight="bold")
    ax2.text(-0.03, y, env, va="center", ha="right", fontsize=8.5)

ax2.set_xlim(0, 1); ax2.set_ylim(-0.6, len(rows) - 0.4)
ax2.set_xticks([]); ax2.set_yticks([])
for s in ax2.spines.values():
    s.set_visible(False)
ax2.set_title("深い文脈での depth collapse 再現状況\n"
              "prompt 約 108k tok / 埋めた合言葉 2 か所の正答で判定", fontsize=11)
ax2.legend(handles=[Patch(color=COL["collapse"], label=LBL["collapse"]),
                    Patch(color=COL["ok"], label=LBL["ok"])],
           fontsize=9, loc="lower center", bbox_to_anchor=(0.5, -0.16), ncol=2)

fig.tight_layout()
fig.savefig("startup_and_collapse.png", dpi=130, bbox_inches="tight")
print("wrote startup_and_collapse.png")
