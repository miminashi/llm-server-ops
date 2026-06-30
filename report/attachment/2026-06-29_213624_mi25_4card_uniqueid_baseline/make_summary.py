#!/usr/bin/env python3
"""
mi25 4 枚装着 baseline サマリ図 (summary.png) を生成する。

論点:
  1. 全 4 枚の Unique ID baseline 取得完了 → 物理カードを Unique ID で一意に追跡可能に
  2. 過去 fault 集中個体 (BDF 87:00.0 = GUID 8820) = card-c48c4 と確定
  3. GUID は BDF 決定論的: 本日 05:25 JST と 21:14 JST の 2 回観測で全 BDF の GUID が完全一致
     → GUID は KFD allocation の BDF 由来値であり物理カード不変ではない

上段: 4 枚 baseline マッピングテーブル (BDF 87:00.0 行を赤背景でハイライト)
下段: 05:25 JST vs 21:14 JST の BDF→GUID 配置一致を示すカテゴリ別色分けマトリックス
      (GUID はカテゴリ値=名義尺度なので棒グラフは不適切、列内の色一致で BDF 決定論性を可視化)
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import Rectangle
from matplotlib import font_manager
import numpy as np

# 日本語フォント設定 (IPAGothic を使用、既存 make_summary.py と同方針)
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


# === 観測データ ===
# 4 枚装着 baseline (本日 21:14 JST 取得)
baseline_rows = [
    # (GPU#, BDF, GUID, Unique ID 末尾 5 桁, カード略称, 過去 fault マーク)
    ("GPU[0]", "04:00.0", 29525, "c3164", "card-c3164", ""),
    ("GPU[1]", "07:00.0", 33301, "a48e4", "card-a48e4", ""),
    ("GPU[2]", "84:00.0", 54068, "448c4", "card-448c4", ""),
    ("GPU[3]", "87:00.0",  8820, "c48c4", "card-c48c4", "★ 過去 fault 集中個体"),
]

# 05:25 JST と 21:14 JST の 2 回観測の BDF→GUID 配置
bdfs = ["04:00.0", "07:00.0", "84:00.0", "87:00.0"]
guids_0525 = [29525, 33301, 54068, 8820]  # 報告: 2026-06-29 0525 JST 4 枚装着初期 swap 直後
guids_2114 = [29525, 33301, 54068, 8820]  # 本日 2114 JST 4 枚装着 baseline


# === Figure ===
fig = plt.figure(figsize=(14, 10))
gs = gridspec.GridSpec(2, 1, height_ratios=[1.4, 1.0], hspace=0.45)

# --- 上段: baseline テーブル ---
ax_t = fig.add_subplot(gs[0])
n_rows = len(baseline_rows)
headers = ["GPU#", "BDF", "GUID\n(KFDランタイム値)", "Unique ID\n末尾 5 桁", "カード略称", "過去 fault マーク"]
n_cols = len(headers)

# 列幅 (相対)
col_widths = np.array([0.8, 1.2, 1.6, 1.4, 1.6, 2.5])
col_widths = col_widths / col_widths.sum() * n_cols
col_x = np.concatenate(([0], np.cumsum(col_widths)))

# ヘッダー行
header_y = n_rows
for j, h in enumerate(headers):
    rect = Rectangle((col_x[j], header_y), col_widths[j], 1.0,
                     facecolor="#444", edgecolor="white", linewidth=1.2)
    ax_t.add_patch(rect)
    ax_t.text(col_x[j] + col_widths[j] / 2, header_y + 0.5, h,
              ha="center", va="center", fontsize=10, color="white", fontweight="bold")

# データ行
for i, row in enumerate(baseline_rows):
    y = n_rows - 1 - i
    is_fault = (row[1] == "87:00.0")
    bg = "#ffd0d0" if is_fault else ("#ffffff" if i % 2 == 0 else "#f4f4f4")
    txtcolor = "#400000" if is_fault else "#222"
    fw = "bold" if is_fault else "normal"
    for j, cell in enumerate(row):
        rect = Rectangle((col_x[j], y), col_widths[j], 1.0,
                         facecolor=bg, edgecolor="#888", linewidth=0.8)
        ax_t.add_patch(rect)
        # Unique ID 列は等幅フォント風に色変え
        if j == 3:
            ax_t.text(col_x[j] + col_widths[j] / 2, y + 0.5, cell,
                      ha="center", va="center", fontsize=11, color=txtcolor,
                      fontweight=fw, family="monospace")
        else:
            ax_t.text(col_x[j] + col_widths[j] / 2, y + 0.5, str(cell),
                      ha="center", va="center", fontsize=10, color=txtcolor,
                      fontweight=fw)

ax_t.set_xlim(0, n_cols)
ax_t.set_ylim(0, n_rows + 1)
ax_t.set_xticks([])
ax_t.set_yticks([])
for spine in ax_t.spines.values():
    spine.set_visible(False)
ax_t.set_title(
    "mi25 4 枚装着 baseline (2026-06-29 21:14 JST 取得) — "
    "BDF 87:00.0 行 = card-c48c4 = 過去 fault 集中個体 (赤背景)",
    fontsize=12, pad=14
)


# --- 下段: 2 回観測比較カテゴリ別色分けマトリックス ---
# GUID はカテゴリ値 (名義尺度) のため、量的比較の棒グラフは不適切。
# 「各 BDF に同じ GUID 値が割り当たるか」という対応関係を、列内の色一致で示す。
ax_b = fig.add_subplot(gs[1])

# GUID ごとに固有色を割り当て (カテゴリパレット、4 値分)
guid_colors = {
    29525: "#4d7ea8",  # blue
    33301: "#5cab7d",  # green
    54068: "#d49a59",  # orange
    8820:  "#c75757",  # red (fault 集中個体)
}
observations = [
    ("2026-06-29 05:25 JST 観測\n(前段レポート初期 swap)", guids_0525),
    ("2026-06-29 21:14 JST 観測\n(本 baseline)",          guids_2114),
]
n_obs = len(observations)
n_bdf = len(bdfs)

# セル描画
for i, (label, row) in enumerate(observations):
    y = n_obs - 1 - i
    for j, guid in enumerate(row):
        rect = Rectangle((j, y), 1.0, 1.0,
                         facecolor=guid_colors[guid], edgecolor="white", linewidth=2.5)
        ax_b.add_patch(rect)
        ax_b.text(j + 0.5, y + 0.5, str(guid),
                  ha="center", va="center", fontsize=14, color="white", fontweight="bold")

# 列下に「✓ 一致」ラベル (両観測が同 GUID なら一致)
for j in range(n_bdf):
    is_match = observations[0][1][j] == observations[1][1][j]
    sym = "✓ 一致" if is_match else "✗ 不一致"
    color = "#1f6f1f" if is_match else "#a01818"
    ax_b.text(j + 0.5, -0.35, sym, ha="center", va="center",
              fontsize=11, color=color, fontweight="bold")

ax_b.set_xlim(0, n_bdf)
ax_b.set_ylim(-0.7, n_obs)
ax_b.set_xticks([j + 0.5 for j in range(n_bdf)])
ax_b.set_xticklabels([f"BDF\n{b}" for b in bdfs], fontsize=10)
ax_b.set_yticks([n_obs - 1 - i + 0.5 for i in range(n_obs)])
ax_b.set_yticklabels([label for label, _ in observations], fontsize=9)
ax_b.tick_params(left=False, bottom=False)
for spine in ax_b.spines.values():
    spine.set_visible(False)
ax_b.set_title(
    "4 枚装着時の BDF → GUID 配置 (2 回観測): "
    "列内の色が上下一致 = 同じ BDF に同じ GUID が再現 → GUID は KFD allocation の BDF 決定論的割当",
    fontsize=11, pad=10
)

# 注記
fig.text(0.5, 0.02,
         "結論: GUID 値は BDF 決定論的 (本日 2 回観測で完全一致)、"
         "Unique ID のみがカード個体不変。"
         "過去レポート群の「GUID 8820 個体」= card-c48c4 (Unique ID 0x21501edbcec48c4) と確定。",
         ha="center", fontsize=10, color="#333", style="italic")

plt.subplots_adjust(left=0.06, right=0.97, top=0.93, bottom=0.08)
out = "report/attachment/2026-06-29_213624_mi25_4card_uniqueid_baseline/summary.png"
plt.savefig(out, dpi=120, bbox_inches="tight")
print(f"Wrote {out}")
