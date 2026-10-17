import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, sys
out = sys.argv[1]
plt.rcParams["font.family"] = "Noto Sans CJK JP"
fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.2))
lab = ["layer・MTPなし\n(9/18 合成, 深さ11)", "tensor・MTPあり\n(9/18 合成, 深さ11)", "tensor・MTPあり\n(10/15 実リクエスト)"]
val = [11.20, 48.14, 41.56]; col = ["#9aa5b1", "#5b8def", "#1f4fbf"]
r = a.bar(lab, val, color=col)
a.bar_label(r, fmt="%.1f"); a.set_ylabel("decode (t/s)"); a.set_title("decode 速度")
a.set_ylim(0, 56); a.tick_params(axis="x", labelsize=8.5)
g = range(4); w = 0.38
L = [10563, 10633, 10871, 11605]; T = [9497] * 4
b.bar([i - w/2 for i in g], L, w, label="layer・MTPなし", color="#9aa5b1")
b.bar([i + w/2 for i in g], T, w, label="tensor・MTPあり", color="#1f4fbf")
b.axhline(16384, color="#c0392b", ls="--", lw=1); b.text(3.5, 16000, "16 GiB", ha="right", va="top", color="#c0392b", fontsize=8)
b.set_xticks(list(g)); b.set_xticklabels([f"CUDA{i}" for i in g]); b.set_ylabel("MiB")
b.set_title("ロード直後の VRAM (ctx=131072, -ub 4096, 10/15 実測)"); b.set_ylim(0, 17500); b.legend(fontsize=8, loc="lower right")
fig.tight_layout(); fig.savefig(out, dpi=130)
