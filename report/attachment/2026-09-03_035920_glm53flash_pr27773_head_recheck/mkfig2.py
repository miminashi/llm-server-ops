#!/usr/bin/env python3
"""レポート用の図を生成する。

左: コミット × shard 1 の配列長 の 2x2 読み込み可否マトリクス（受理側の反転）
右: #27773 の prompt 処理速度の推移（コミット別）と #27754 の参考値
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.family"] = ["IPAGothic", "DejaVu Sans"]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.4),
                               gridspec_kw={"width_ratios": [1.25, 1.0]})

# ---- 左: 2x2 可否マトリクス ----
cols = ["7de5a8e39\n(2026-09-01、前回検証)", "2b533e0950\n(2026-09-02、今回検証)"]
rows = ["Shard_Rewrite 素\nhead_count_kv = 46 要素", "前回のパッチ済み\nhead_count_kv = 45 要素"]
# 1 = OK, 0 = FAIL
mat = np.array([[0, 1],
                [1, 0]])
notes = np.array([["FAIL\nexpected 45, got 46", "OK\n(本セッション実測)"],
                  ["OK\n(前回の回避策)", "FAIL\nexpected 46, got 45"]])

OKC, NGC = "#2e7d32", "#c62828"
for i in range(2):
    for j in range(2):
        c = OKC if mat[i, j] else NGC
        ax1.add_patch(plt.Rectangle((j, 1 - i), 1, 1, facecolor=c, alpha=0.16,
                                    edgecolor=c, linewidth=2.0))
        ax1.text(j + 0.5, 1 - i + 0.5, notes[i, j], ha="center", va="center",
                 fontsize=12.5, color=c, fontweight="bold", linespacing=1.5)
ax1.set_xlim(0, 2); ax1.set_ylim(0, 2)
ax1.set_xticks([0.5, 1.5]); ax1.set_xticklabels(cols, fontsize=10.5)
ax1.set_yticks([1.5, 0.5]); ax1.set_yticklabels(rows, fontsize=10.5)
ax1.tick_params(length=0)
for s in ax1.spines.values():
    s.set_visible(False)
ax1.set_title("PR #27773: どちらの shard 1 が読めるかが反転した", fontsize=13, pad=12)

# ---- 右: pp の推移 ----
labels = ["#27773\n7de5a8e39\n-ub 512", "#27773\n7de5a8e39\n-ub 4096",
          "#27773\n2b533e0950\n-ub 4096", "#27754\n949f7efb09\n-ub 4096"]
vals = [49.2, 49.7, 48.7, 58.8]
colors = ["#90a4ae", "#90a4ae", "#1565c0", "#ef6c00"]
bars = ax2.bar(np.arange(len(vals)), vals, color=colors, width=0.62)
for b, v in zip(bars, vals):
    ax2.text(b.get_x() + b.get_width() / 2, v + 0.9, f"{v}", ha="center",
             fontsize=12, fontweight="bold")
ax2.axhline(49.7, color="#90a4ae", ls="--", lw=1.2)
ax2.set_xticks(np.arange(len(vals)))
ax2.set_xticklabels(labels, fontsize=9.5)
ax2.set_ylabel("prompt eval (t/s)  ※11k needle / ctx 32768 / -fa on", fontsize=10)
ax2.set_ylim(0, 70)
ax2.set_title("kpool 書き直し後も pp はほぼ横ばい (49.7 → 48.7)", fontsize=13, pad=12)
ax2.grid(axis="y", alpha=0.25)
for s in ("top", "right"):
    ax2.spines[s].set_visible(False)

fig.tight_layout()
fig.savefig("head_count_kv_matrix.png", dpi=130, bbox_inches="tight")
print("wrote head_count_kv_matrix.png")
