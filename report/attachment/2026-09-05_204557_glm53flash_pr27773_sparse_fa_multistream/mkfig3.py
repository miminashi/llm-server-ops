#!/usr/bin/env python3
"""2026-09-05 検証レポートの核心発見サマリ用の図。

左: 11k needle の pp / tg を 3 コミットで比較する。#27773 の
    99fdaab443 "Sparse FA for DSA prefill" を挟んでも P100 (sm_60) では
    prefill が伸びていないことを示す。
右: tg の深さ依存を depth~20 を 100% として正規化する。本セッションの
    P100 x13 と、PR スレッドで nicholasshirley が報告した 1x4090 の
    #27773 / #27754 を並べ、#27773 の pooled cache が深さに強いことを見る。
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.family"] = "IPAGothic"

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.2), dpi=130)

# --- 左: 3 コミットの pp / tg ---
labels = ["7de5a8e39\n(09-01)", "2b533e0950\n(09-02)", "8134115f88\n(09-04)"]
pp = [49.7, 48.7, 48.4]
tg = [None, 8.3, 8.4]
x = np.arange(len(labels))
w = 0.36
b1 = ax1.bar(x - w / 2, pp, w, label="prompt (pp)", color="#2b4c7e")
b2 = ax1.bar(x + w / 2, [t if t else 0 for t in tg], w, label="generation (tg)", color="#c46a3a")
for xi, v in zip(x - w / 2, pp):
    ax1.text(xi, v + 0.8, f"{v}", ha="center", fontsize=11)
for xi, v in zip(x + w / 2, tg):
    ax1.text(xi, (v if v else 0) + 0.8, f"{v}" if v else "未測定", ha="center", fontsize=11)
ax1.set_xticks(x); ax1.set_xticklabels(labels, fontsize=10)
ax1.set_ylabel("t/s"); ax1.set_ylim(0, 72)
ax1.set_title("11k needle の速度（#27773 の 3 コミット）", fontsize=13)
ax1.legend(loc="center right", fontsize=10)
ax1.annotate("Sparse FA for DSA prefill\n(99fdaab443) 投入", xy=(2 - w / 2 - 0.10, 46.0),
             xytext=(0.30, 63.0), fontsize=10.5, color="#a02020",
             ha="center", va="center",
             bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#a02020", alpha=0.95),
             arrowprops=dict(arrowstyle="->", color="#a02020", lw=1.4))
ax1.text(1.62, 63.0, "P100 (sm_60) では\nprefill は伸びず横ばい",
         ha="center", va="center", fontsize=10.5, color="#a02020",
         bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#a02020", alpha=0.95))
ax1.grid(axis="y", alpha=0.3)

# --- 右: tg の深さ依存（depth~20 = 100%） ---
d_ours = [16, 7349, 11338, 28390]
t_ours = [9.4, 8.5, 8.4, 8.2]
r_ours = [t / t_ours[0] * 100 for t in t_ours]
d_ns73 = [20, 7500, 28800]; t_ns73 = [25.3, 24.0, 23.7]
r_ns73 = [t / t_ns73[0] * 100 for t in t_ns73]
d_ns54 = [20, 7500, 28800]; t_ns54 = [24.8, 21.1, 14.6]
r_ns54 = [t / t_ns54[0] * 100 for t in t_ns54]

ax2.plot(d_ours, r_ours, "o-", lw=2.4, ms=8, color="#2b4c7e",
         label="#27773 本セッション (P100 x13 / RPC)")
ax2.plot(d_ns73, r_ns73, "s--", lw=1.8, ms=7, color="#5a8fc4",
         label="#27773 nicholasshirley (1x4090)")
ax2.plot(d_ns54, r_ns54, "^--", lw=1.8, ms=7, color="#c46a3a",
         label="#27754 nicholasshirley (1x4090)")
for xd, yr, tv, dy in zip(d_ours, r_ours, t_ours, [2.2, 2.4, -4.4, 2.4]):
    ax2.text(xd, yr + dy, f"{tv} t/s", ha="center", fontsize=10, color="#2b4c7e")
ax2.set_xscale("symlog", linthresh=1000)
ax2.set_xlabel("プロンプト長 (トークン)")
ax2.set_ylabel("tg 維持率 (深さ ~20 を 100%)")
ax2.set_ylim(50, 112)
ax2.set_title("tg の深さ依存 — pooled cache の効き方", fontsize=13)
ax2.legend(loc="lower left", fontsize=9.5)
ax2.grid(alpha=0.3)

fig.tight_layout()
fig.savefig("sparse_fa_and_tg_depth.png")
print("ok")
