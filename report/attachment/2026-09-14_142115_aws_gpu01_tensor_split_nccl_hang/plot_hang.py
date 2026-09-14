import sys, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

lang = sys.argv[1] if len(sys.argv) > 1 else "ja"
out  = sys.argv[2] if len(sys.argv) > 2 else "hang-compare.png"
nccl_tps = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0

if lang == "ja":
    for p in ("/home/ubuntu/.fonts/NotoSansCJKjp-Regular.otf",):
        try:
            font_manager.fontManager.addfont(p)
            plt.rcParams["font.family"] = "Noto Sans CJK JP"
        except Exception:
            pass

T = dict(
    ja=dict(
        title="aws-gpu01 / Tesla P100 x7 / --split-mode tensor の起動ハング切り分け",
        p1="① 起動成功率 (2枚, ctx=8192)", p2="② 起動成功率 (7枚, ctx=8192)",
        p3="③ NCCL 経路での MTP 有無 (2枚)", p4="④ 回避策での decode 速度",
        ylab_rate="起動成功率", ylab_tps="decode (t/s)",
        nccl="NCCL\n(既定)", bf="butterfly", it="internal",
        off="MTP 無効", on="MTP 有効",
        b2="butterfly\n2枚", i2="internal\n2枚", b7="butterfly\n7枚", n2="NCCL\n2枚",
        note="NCCL: 1/15 成功 / 非NCCL: 15/15 成功 (Fisher two-sided p = 9.6e-06)",
    ),
    en=dict(
        title="aws-gpu01 / Tesla P100 x7 / startup hang with --split-mode tensor",
        p1="(1) startup success (2 GPUs, ctx=8192)", p2="(2) startup success (7 GPUs, ctx=8192)",
        p3="(3) MTP on/off over NCCL (2 GPUs)", p4="(4) decode speed with workaround",
        ylab_rate="startup success rate", ylab_tps="decode (t/s)",
        nccl="NCCL\n(default)", bf="butterfly", it="internal",
        off="MTP off", on="MTP on",
        b2="butterfly\n2 GPU", i2="internal\n2 GPU", b7="butterfly\n7 GPU", n2="NCCL\n2 GPU",
        note="NCCL: 1/15 ok / non-NCCL: 15/15 ok (Fisher two-sided p = 9.6e-06)",
    ),
)[lang]

RED, GRN, BLU = "#d1495b", "#2a9d8f", "#3d5a80"
fig, ax = plt.subplots(2, 2, figsize=(12, 8))
fig.suptitle(T["title"], fontsize=13, fontweight="bold")

def bars(a, labels, vals, colors, ylab, ymax, fmt="{:.0%}", ns=None):
    b = a.bar(labels, vals, color=colors, width=0.55)
    a.set_ylabel(ylab); a.set_ylim(0, ymax); a.grid(axis="y", alpha=0.3)
    for i, (r, v) in enumerate(zip(b, vals)):
        lab = fmt.format(v) + (f"\n({ns[i]})" if ns else "")
        a.text(r.get_x()+r.get_width()/2, v + ymax*0.03, lab, ha="center", fontsize=10)

a = ax[0][0]; a.set_title(T["p1"])
bars(a, [T["nccl"], T["bf"], T["it"]], [1/12, 1.0, 1.0], [RED, GRN, BLU],
     T["ylab_rate"], 1.25, ns=["1/12", "6/6", "6/6"])

a = ax[0][1]; a.set_title(T["p2"])
bars(a, [T["nccl"], T["bf"]], [0.0, 1.0], [RED, GRN],
     T["ylab_rate"], 1.25, ns=["0/3", "3/3"])

a = ax[1][0]; a.set_title(T["p3"])
bars(a, [T["off"], T["on"]], [0.0, 1/6], [RED, RED],
     T["ylab_rate"], 1.25, ns=["0/6", "1/6"])
a.text(0.5, 0.90, T["note"], transform=a.transAxes, ha="center", fontsize=9, color="#555")

a = ax[1][1]; a.set_title(T["p4"])
labels = [T["i2"], T["b2"], T["b7"]]; vals = [25.89, 26.95, 19.47]; cols = [BLU, GRN, GRN]
if nccl_tps > 0:
    labels.append(T["n2"]); vals.append(nccl_tps); cols.append(RED)
bars(a, labels, vals, cols, T["ylab_tps"], max(vals)*1.3, fmt="{:.2f}")

fig.tight_layout(rect=[0, 0, 1, 0.96])
fig.savefig(out, dpi=110)
print("saved", out)
