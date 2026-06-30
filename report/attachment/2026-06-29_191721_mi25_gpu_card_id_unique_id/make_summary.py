#!/usr/bin/env python3
"""
mi25 物理スワップ実験の核心発見サマリ図 (summary.png) を生成する。

論点: rocm-smi -i の GUID は不変ではない (Unique ID 必須)。
これを「装着構成 vs 観測値マトリックス」で可視化する。
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.colors import to_rgba
from matplotlib import font_manager

# 日本語フォント設定 (IPAGothic を使用)
for font_path in [
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
]:
    try:
        font_manager.fontManager.addfont(font_path)
    except Exception:
        pass
plt.rcParams["font.family"] = "IPAGothic"
plt.rcParams["axes.unicode_minus"] = False


# 観測データ (jsonl 解析より)
# 列: 装着構成 (試行ラベル)
# 行: 物理カード (Unique ID 末尾 4 桁)
configs = [
    ("4 枚装着\n(初期、05:25 JST)", "4card"),
    ("SLOT8 単独\n(label 8820, 07:45 JST)", "alone1"),
    ("SLOT8 単独\n(label 54068, 13:13 JST)", "alone2"),
    ("SLOT6 単独\n(label 8820, 14:13 JST)", "alone3"),
    ("SLOT6 単独\n(label 54068, 14:27 JST)", "alone4"),
]

# (BDF, GUID, Unique ID 末尾 4 桁 or '?')
data = {
    "c48c4": {  # 付箋「8820」のカード
        "4card":  None,                 # 4 枚装着時はどの BDF か区別困難 (記録なし)
        "alone1": ("84:00.0", 54068, "?"),    # SLOT8 単独 (Unique ID 取得忘れ)
        "alone2": None,                  # 別カード
        "alone3": ("84:00.0", 54068, "c48c4"),
        "alone4": None,
    },
    "a48e4": {  # 付箋「54068」のカード
        "4card":  None,
        "alone1": None,
        "alone2": ("84:00.0", 54068, "?"),
        "alone3": None,
        "alone4": ("84:00.0", 54068, "a48e4"),
    },
    "(他 2 枚)": {  # GUID 29525 + GUID 33301、Unique ID 記録なし
        "4card": "4 枚同時: BDF 04/07/84/87 → GUID 29525/33301/54068/8820",
        "alone1": None, "alone2": None, "alone3": None, "alone4": None,
    },
}

cards = ["c48c4", "a48e4", "(他 2 枚)"]
card_labels = [
    "Unique ID 末尾 c48c4\n(付箋「8820」のカード)",
    "Unique ID 末尾 a48e4\n(付箋「54068」のカード)",
    "他 2 枚 (Unique ID 未記録)\n(SLOT2 / SLOT4 系統)",
]

# Figure
fig, ax = plt.subplots(figsize=(14, 6.5))
nc = len(configs)
nr = len(cards)

# グリッド
for i in range(nr):
    for j in range(nc):
        card = cards[i]
        _, cfg = configs[j]
        cell = data[card][cfg]

        if cell is None:
            color = "#f5f5f5"  # 非装着 (空白)
            text = "—"
            txtcolor = "#999"
        elif isinstance(cell, str):
            color = "#fff4d6"  # 4 枚装着時の集約セル
            text = cell
            txtcolor = "#553f00"
        else:
            bdf, guid, uid = cell
            # GUID 54068 を「不変ではない」ことを強調する色
            color = "#ffd0d0" if guid == 54068 else "#d0ffd0"
            text = f"BDF={bdf}\nGUID={guid}\nUnique ID 末尾={uid}"
            txtcolor = "#400000" if guid == 54068 else "#003300"

        rect = Rectangle((j, nr - 1 - i), 1, 1, facecolor=color, edgecolor="#333", linewidth=1.0)
        ax.add_patch(rect)
        ax.text(j + 0.5, nr - 1 - i + 0.5, text, ha="center", va="center",
                fontsize=9, color=txtcolor)

# 軸
ax.set_xlim(0, nc)
ax.set_ylim(0, nr)
ax.set_xticks([j + 0.5 for j in range(nc)])
ax.set_xticklabels([c[0] for c in configs], fontsize=9)
ax.set_yticks([nr - 1 - i + 0.5 for i in range(nr)])
ax.set_yticklabels(card_labels, fontsize=9)
ax.tick_params(left=False, bottom=False)
for spine in ax.spines.values():
    spine.set_visible(False)

ax.set_title(
    "mi25 物理スワップ実験: 装着構成 × 観測値マトリックス\n"
    "★ 別個体カード 2 枚 (Unique ID c48c4 / a48e4) が SLOT6/SLOT8 単独で両方 GUID 54068 を返す = GUID は個体不変ではない",
    fontsize=11, pad=14
)
ax.text(0.5, -0.32, "凡例: 赤=GUID 54068 (単独構成で同一値に収束)、緑=他 GUID、黄=4 枚装着集約セル",
        transform=ax.transAxes, ha="center", fontsize=9, color="#444")

plt.subplots_adjust(left=0.18, right=0.97, top=0.85, bottom=0.20)
out = "report/attachment/2026-06-29_191721_mi25_gpu_card_id_unique_id/summary.png"
plt.savefig(out, dpi=120, bbox_inches="tight")
print(f"Wrote {out}")
