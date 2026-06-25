#!/usr/bin/env python3
# 核心発見サマリPNG生成: スロット(SLOT2/4/6/8) × 構成(2枚/3枚/4枚) の
# PCIeリンク幅ヒートマップ。装着セル=x16(緑)、未装着セル=グレー。各セルにGUID併記。
# 前回dropoutレポートの「スロット×ブートで赤(x0)多発」図と対をなす構図。
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# 日本語フォント (IPAGothic)
for fp in [
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
]:
    if os.path.exists(fp):
        matplotlib.font_manager.fontManager.addfont(fp)
        matplotlib.rcParams["font.family"] = \
            matplotlib.font_manager.FontProperties(fname=fp).get_name()
        break
matplotlib.rcParams["axes.unicode_minus"] = False

# 列=物理スロット, 行=構成。セル = (装着GUID or None)
SLOTS = ["SLOT2\n(00:02)", "SLOT4\n(00:03)", "SLOT6\n(80:03)", "SLOT8\n(80:02)"]
ROWS = ["2枚構成", "3枚構成", "4枚構成"]
# grid[row][col] = GUID文字列 or None(未装着)
grid = [
    ["29525", "33301", None,    None],     # 2枚
    ["29525", "33301", "54068", None],     # 3枚
    ["29525", "33301", "8820",  "54068"],  # 4枚
]

GREEN = "#2e9e5b"
GRAY = "#c7ccd1"

fig, (ax, axn) = plt.subplots(
    2, 1, figsize=(11.5, 7.4), gridspec_kw={"height_ratios": [3.0, 1.0]}
)

ncol, nrow = len(SLOTS), len(ROWS)
for r in range(nrow):
    for c in range(ncol):
        guid = grid[r][c]
        y = nrow - 1 - r
        if guid is None:
            color, txt, tcol = GRAY, "未装着", "#5a6066"
        else:
            color, txt, tcol = GREEN, "x16 (ok)\nGUID %s" % guid, "white"
        box = FancyBboxPatch(
            (c + 0.06, y + 0.06), 0.88, 0.88,
            boxstyle="round,pad=0.02,rounding_size=0.05",
            linewidth=1.2, edgecolor="white", facecolor=color,
        )
        ax.add_patch(box)
        ax.text(c + 0.5, y + 0.5, txt, ha="center", va="center",
                fontsize=12, color=tcol, fontweight="bold")

ax.set_xlim(0, ncol)
ax.set_ylim(0, nrow)
ax.set_xticks([i + 0.5 for i in range(ncol)])
ax.set_xticklabels(SLOTS, fontsize=11)
ax.set_yticks([nrow - 1 - i + 0.5 for i in range(nrow)])
ax.set_yticklabels(ROWS, fontsize=12)
ax.xaxis.tick_top()
ax.tick_params(length=0)
for s in ax.spines.values():
    s.set_visible(False)
ax.set_title(
    "mi25 段階増設 2→3→4枚: 物理スロット × 構成 の PCIeリンク幅マップ\n"
    "装着した全スロットが Gen3 x16・AER訂正エラー0 で認識（脱落ゼロ）",
    fontsize=13.5, fontweight="bold", pad=26,
)

# 下部: 結論テキストボックス
axn.axis("off")
concl = (
    "■ 結果: 2→3→4枚いずれも装着スロット全数が x16 (ok)・AER TOTAL_ERR_COR=0・dmesg に reset/hang/x0/x8 なし。"
    "4枚64GB(VRAM)を復旧。\n"
    "■ 前回(2026-06-14 dropout)との対比: 当時4枚時は SLOT4(GUID33301)が x0/PresDet-（リンク死）、SLOT8系(GUID8820)が x8/欠落で脱落。\n"
    "   → 33301 は『同一SLOT4』で、8820 は『SLOT8→SLOT6へ移し替え』で健全化（要因は再装着＋挿し替えの両方で切り分けは未完）。\n"
    "■ 要監視: 3枚・4枚とも認識まで『数回の抜き差し』を要した＝接触マージンが低く再発しうる。"
    "前回結論『PCIe物理層(接点/装着)障害』を裏付ける暫定復旧。"
)
axn.text(
    0.01, 0.95, concl, ha="left", va="top", fontsize=10.3, color="#1c2024",
    linespacing=1.55,
    bbox=dict(boxstyle="round,pad=0.7", facecolor="#f3f6f9", edgecolor="#b9c2cb"),
)

plt.tight_layout()
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "summary.png")
plt.savefig(out, dpi=120, bbox_inches="tight", facecolor="white")
print("wrote", out)
