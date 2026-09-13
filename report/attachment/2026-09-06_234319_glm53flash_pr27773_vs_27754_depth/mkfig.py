#!/usr/bin/env python3
"""2026-09-06 検証レポートの核心発見サマリ用の図。

同一環境 (13x Tesla P100 / RPC 分散 / GPU only / -fa on / -ub 4096) で
#27773 と #27754 を同一プロンプト (バイト同一) で測り、prefill (pp) と
decode (tg) の深さ依存を比較する。

左   : pp の絶対値。浅いと #27754 が 28% 速いが、深さとともに差が縮み 108k で逆転。
中央 : tg の絶対値。28k までは拮抗し、108k で #27773 が 30% 速くなる。
右   : tg 維持率 (最浅点 = 100%)。PR スレッドで nicholasshirley が報告した
       1x4090 + CPU offload / -fa off の値を破線で重ね、#27754 の落ち込みが
       始まる深さが環境で大きく変わることを示す。
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "IPAGothic"

# --- 本セッションの実測 ---
D = [16, 7349, 11338, 28390, 109917]
PP_73 = [6.0, 49.3, 48.8, 44.2, 28.3]
TG_73 = [9.4, 8.1, 8.5, 8.2, 7.8]
PP_54 = [9.3, 63.2, 59.6, 47.6, 25.5]
TG_54 = [8.5, 8.5, 8.3, 7.9, 6.0]

# --- nicholasshirley (1x4090 + CPU offload, -fa off) ---
D_NS = [20, 7500, 28800]
TG_NS73 = [25.3, 24.0, 23.7]
TG_NS54 = [24.8, 21.1, 14.6]

C73, C54 = "#2b4c7e", "#c46a3a"
C73L, C54L = "#5a8fc4", "#d9a06a"

fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(17.5, 5.4), dpi=130)

# --- 左: pp の絶対値（16 tok は prefill が短すぎて意味がないので除く） ---
ax1.plot(D[1:], PP_54[1:], "s-", lw=2.4, ms=8, color=C54, label="#27754 (629b50552)")
ax1.plot(D[1:], PP_73[1:], "o-", lw=2.4, ms=8, color=C73, label="#27773 (8134115f8)")
for x, y, dy in zip(D[1:], PP_54[1:], [3.0, 3.0, 3.0, -5.5]):
    ax1.text(x, y + dy, f"{y}", ha="center", fontsize=10.5, color=C54)
for x, y, dy in zip(D[1:], PP_73[1:], [-5.5, -5.5, -5.5, 3.0]):
    ax1.text(x, y + dy, f"{y}", ha="center", fontsize=10.5, color=C73)
ax1.annotate("108k で逆転\n(+11%)", xy=(109917, 27.0), xytext=(30000, 12.0),
             fontsize=10.5, color="#a02020", ha="center",
             bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#a02020", alpha=0.95),
             arrowprops=dict(arrowstyle="->", color="#a02020", lw=1.4))
ax1.set_xscale("log")
ax1.set_xlim(4000, 2.6e5)
ax1.set_ylim(0, 72)
ax1.set_xlabel("プロンプト長 (トークン)")
ax1.set_ylabel("pp (t/s)")
ax1.set_title("prefill 速度 — 同一環境・同一プロンプト", fontsize=13)
ax1.legend(loc="lower left", fontsize=10)
ax1.grid(alpha=0.3)

# --- 中央: tg の絶対値 ---
ax2.plot(D, TG_54, "s-", lw=2.4, ms=8, color=C54, label="#27754 (629b50552)")
ax2.plot(D, TG_73, "o-", lw=2.4, ms=8, color=C73, label="#27773 (8134115f8)")
for x, y, dy, ha in zip(D, TG_54, [-0.38, 0.18, -0.38, -0.38, -0.38],
                        ["center", "right", "center", "center", "center"]):
    ax2.text(x, y + dy, f"{y}", ha=ha, fontsize=10.5, color=C54)
for x, y, dy, ha in zip(D, TG_73, [0.18, -0.38, 0.18, 0.18, 0.18],
                        ["center", "center", "left", "center", "center"]):
    ax2.text(x, y + dy, f"{y}", ha=ha, fontsize=10.5, color=C73)
ax2.annotate("108k で 30% 差", xy=(109917, 6.9), xytext=(14000, 6.0),
             fontsize=10.5, color="#a02020", ha="center",
             bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#a02020", alpha=0.95),
             arrowprops=dict(arrowstyle="->", color="#a02020", lw=1.4))
ax2.set_xscale("log")
ax2.set_xlim(10, 2.6e5)
ax2.set_ylim(5.4, 10.2)
ax2.set_xlabel("プロンプト長 (トークン)")
ax2.set_ylabel("tg (t/s)")
ax2.set_title("decode 速度 — 28k まで拮抗、108k で分かれる", fontsize=13)
ax2.legend(loc="lower left", fontsize=10)
ax2.grid(alpha=0.3)

# --- 右: tg 維持率（最浅点 = 100%）と 4090 の報告値 ---
r73 = [t / TG_73[0] * 100 for t in TG_73]
r54 = [t / TG_54[0] * 100 for t in TG_54]
r_ns73 = [t / TG_NS73[0] * 100 for t in TG_NS73]
r_ns54 = [t / TG_NS54[0] * 100 for t in TG_NS54]

ax3.plot(D, r54, "s-", lw=2.4, ms=8, color=C54,
         label="#27754 本セッション (P100 x13 / GPU only / -fa on)")
ax3.plot(D, r73, "o-", lw=2.4, ms=8, color=C73, label="#27773 本セッション (同上)")
ax3.plot(D_NS, r_ns54, "s--", lw=1.7, ms=7, color=C54L,
         label="#27754 nicholasshirley (1x4090 + CPU offload / -fa off)")
ax3.plot(D_NS, r_ns73, "o--", lw=1.7, ms=7, color=C73L, label="#27773 nicholasshirley (同上)")
ax3.axhline(100, color="gray", lw=0.8, ls=":")
for x, r, lab, dy in [(D[-1], r54[-1], f"{r54[-1]:.0f}%", -4.2), (D[-1], r73[-1], f"{r73[-1]:.0f}%", 2.2),
                     (D_NS[-1], r_ns54[-1], f"{r_ns54[-1]:.0f}%", -4.2), (D_NS[-1], r_ns73[-1], f"{r_ns73[-1]:.0f}%", 2.2)]:
    col = C54 if lab in (f"{r54[-1]:.0f}%",) else C73
    ax3.text(x, r + dy, lab, ha="center", fontsize=10, color="#333333")
ax3.text(0.5, 0.955, "#27754 が落ちる深さ: 4090 では 28.8k、P100 では 108k",
         transform=ax3.transAxes, ha="center", va="top", fontsize=10.5, color="#a02020",
         bbox=dict(boxstyle="round,pad=0.32", fc="white", ec="#a02020", alpha=0.95))
ax3.set_xscale("log")
ax3.set_xlim(10, 2.6e5)
ax3.set_ylim(50, 112)
ax3.set_xlabel("プロンプト長 (トークン)")
ax3.set_ylabel("tg 維持率 (最浅点 = 100%)")
ax3.set_title("落ち込みが始まる深さは環境で変わる", fontsize=13)
ax3.legend(loc="lower left", fontsize=8.4)
ax3.grid(alpha=0.3)

fig.tight_layout()
fig.savefig("pr27773_vs_27754_depth.png")
print("ok")
