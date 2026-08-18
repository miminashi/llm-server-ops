import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sys
import matplotlib.pyplot as _p
matplotlib.rcParams["font.family"] = "IPAGothic"

out = sys.argv[1]
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2), gridspec_kw={"width_ratios": [1, 1.25]})

# 左: 起動時間比較
labels = ["変更前\n(全12スロット Legacy)", "変更後\n(11スロット Disabled)"]
vals = [146, 144]
bars = ax1.bar(labels, vals, color=["#4C72B0", "#DD8452"], width=0.55)
for b, v in zip(bars, vals):
    ax1.text(b.get_x() + b.get_width()/2, v + 2, f"{v} s", ha="center", fontsize=13, fontweight="bold")
ax1.set_ylabel("reset → SSH 応答 (秒)", fontsize=11)
ax1.set_ylim(0, 175)
ax1.set_title("POST 短縮効果は −2 秒（誤差範囲）", fontsize=12, fontweight="bold")
ax1.grid(axis="y", alpha=0.3)

# 右: スロット対応表
ax2.axis("off")
rows = [
    ("CPU1 Slot1",  "09:00.0", "PLX#2 upstream", "Disabled"),
    ("CPU1 Slot2",  "ff:00.0", "（空き）",        "Disabled"),
    ("CPU1 Slot3",  "08:00.0", "Tesla P100",     "Disabled"),
    ("CPU1 Slot4",  "07:00.0", "Tesla P100",     "Disabled"),
    ("CPU1 Slot5",  "05:00.0", "Tesla P100",     "Disabled"),
    ("CPU2 Slot6",  "01:00.0※", "SAS HBA 82:00.0", "Legacy"),
    ("CPU1 Slot7",  "ff:00.0", "（空き）",        "Disabled"),
    ("CPU1 Slot8",  "0b:00.0", "ConnectX-4",     "Disabled"),
    ("CPU1 Slot9",  "0d:00.0", "Tesla P100",     "Disabled"),
    ("CPU1 Slot10", "0f:00.0", "Tesla P100",     "Disabled"),
    ("CPU1 Slot11", "0e:00.0", "Tesla P100",     "Disabled"),
    ("CPU1 Slot12", "0c:00.0", "Tesla P100",     "Disabled"),
]
tbl = ax2.table(
    cellText=rows,
    colLabels=["BIOS 項目", "SMBIOS Bus Addr", "実デバイス", "今回の設定"],
    cellLoc="left", loc="center",
)
tbl.auto_set_font_size(False)
tbl.set_fontsize(9.5)
tbl.scale(1, 1.32)
for j in range(4):
    tbl[(0, j)].set_facecolor("#333333")
    tbl[(0, j)].set_text_props(color="white", fontweight="bold")
for j in range(4):
    tbl[(6, j)].set_facecolor("#FFE08A")
    tbl[(6, j)].set_text_props(fontweight="bold")
ax2.set_title("aws-gpu01 の BIOS スロット項目 ↔ 実デバイス\n※ Slot6 の Bus Address は BIOS の誤報告（01:00.0 は空）",
              fontsize=11.5, fontweight="bold")

fig.suptitle("aws-gpu01: SAS HBA は BIOS の「CPU2 Slot6」— OPROM 無効化の POST 短縮効果はほぼ無し",
             fontsize=13.5, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.94])
fig.savefig(out, dpi=110)
print("saved", out)
