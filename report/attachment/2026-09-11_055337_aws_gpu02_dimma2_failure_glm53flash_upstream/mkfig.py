#!/usr/bin/env python3
# 2026-09-10/11 セッションの核心発見サマリ図。
#   左: GLM-5.3-Flash 対応 PR 4 本の HEAD が前回検証 (09-06) 以降どれだけ動いたか
#   右: aws-gpu02 の電源投入の成否（09-05 の対策直後は 227 秒で SSH 到達、今回は 2 回とも POST 停止）
# 数値はハードコード。再測時はここを書き換えて流用する。
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "IPAGothic"

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.5, 5.4))

# ---- 左: PR の HEAD 移動 ----
labels = ["#27773\ntimkhronos", "#27754\nunslothai", "#27917\nMTP (draft)", "#27752\neauchs",
          "smalinin\nmy_glm53_flash"]
# 前回検証 (09-06 22:00 JST) からの新規コミット数。
# smalinin は master 465e49b9c (09-06 16:47) 派生なので、87 ahead がそのまま「09-06 以降」に当たる。
own   = [0, 1, 0, 0, 40]     # 実装に触れたコミット (#27754 は d94f44e79a の 1 本 = 1 行)
oth   = [0, 90, 0, 0, 47]    # マージ・上流取り込み・docs (#27754: 2 merge + 88 upstream / smalinin: docs 等)
colors_own = ["#bbbbbb", "#1f77b4", "#bbbbbb", "#bbbbbb", "#d62728"]
x = range(len(labels))
ax1.bar(x, own, color=colors_own, label="実装に触れたコミット")
ax1.bar(x, oth, bottom=own, color="#aec7e8", label="マージ・上流取り込み・docs")
ax1.set_xticks(list(x)); ax1.set_xticklabels(labels, fontsize=9)
ax1.set_ylabel("前回検証 (09-06) 以降のコミット数")
ax1.set_title("① 上流の動き — 本家マージは 0 件、\n動いたのは #27754 と新顔 smalinin だけ", fontsize=11)
ann = ["不変\n8134115f88\n(master-70)", "計 91\nd94f44e79a\n実質 1 行", "不変\n5b8593b545\ndirty",
       "不変\n1d0c76f3c6\ndirty", "計 87\n271235bb63\n新規フォーク"]
for i, (o, u, a) in enumerate(zip(own, oth, ann)):
    ax1.text(i, o + u + 2.5, a, ha="center", va="bottom", fontsize=8)
ax1.set_ylim(0, 125)
ax1.legend(fontsize=9, loc="upper left")
ax1.grid(axis="y", alpha=0.3)

# ---- 右: aws-gpu02 の起動成否 ----
runs = ["09-05 22:22\nPatrol Scrub\n無効化直後", "09-10 13:55\n1 回目", "09-10 22:08\n2 回目\n(電源サイクル後)"]
secs = [227, 1379, 495]     # SSH 到達までの秒数 / 打ち切りまでの秒数
ok   = [True, False, False]
bars = ax2.bar(runs, secs, color=["#2ca02c" if k else "#d62728" for k in ok])
ax2.set_ylabel("電源投入から SSH 到達 / 打ち切りまで (秒)")
ax2.set_title("② aws-gpu02 は POST を通過しなくなった\n(`No memory DIMM detected: P1-DIMMA2`)", fontsize=11)
for b, s, k in zip(bars, secs, ok):
    ax2.text(b.get_x() + b.get_width()/2, s + 25,
             f"SSH 到達 {s}s" if k else f"POST BB のまま\n{s}s で打ち切り",
             ha="center", va="bottom", fontsize=9)
ax2.axhline(227, ls="--", color="#2ca02c", alpha=0.6)
ax2.set_ylim(0, 1750)
ax2.grid(axis="y", alpha=0.3)

fig.tight_layout()
fig.savefig("summary.png", dpi=110)
print("saved summary.png")
