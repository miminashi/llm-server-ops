#!/usr/bin/env python3
"""GPU 枚数スイープ図 (2..7 枚 x layer/tensor)。

使い方:
  plot_sweep.py --layer-dir runs/gpu01-sweep-layer --tensor-dir runs/gpu01-sweep-tensor \
                --lang ja --out runs/gpu01-sweep-layer/sweep-ja.png

各 run ディレクトリから results-<arm>.json / results-<arm>-pp0.json / sampler-<arm>.log を読む。
腕名は layer2..layer6 / layer (=7枚)、tensor2..tensor6 / tensor (=7枚)。
"""
import argparse, json, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

C_LAYER = "#1f77b4"
C_TENSOR = "#d62728"


def arms(prefix):
    """(枚数, 腕名) の昇順リスト。7 枚の腕は数字なしの prefix 自身。"""
    return [(n, f"{prefix}{n}") for n in range(2, 7)] + [(7, prefix)]


def load(run_dir, prefix):
    """{枚数: {"ladder": [...], "pp0": {...}, "sampler": path}} を返す。欠測腕は飛ばす。"""
    out = {}
    for n, arm in arms(prefix):
        f = os.path.join(run_dir, f"results-{arm}.json")
        if not os.path.exists(f):
            continue
        with open(f) as fh:
            lad = json.load(fh)
        if isinstance(lad, dict) or not lad:
            continue                      # {"aborted": ...} や空は捨てる
        rec = {"arm": arm, "ladder": lad, "pp0": None, "sampler": None}
        p = os.path.join(run_dir, f"results-{arm}-pp0.json")
        if os.path.exists(p):
            with open(p) as fh:
                rec["pp0"] = json.load(fh)
        s = os.path.join(run_dir, f"sampler-{arm}.log")
        if os.path.exists(s):
            rec["sampler"] = s
        out[n] = rec
    return out


def sampler_util(path, ncards):
    """その腕が実際に使った 0..ncards-1 の GPU だけで利用率・温度・電力を平均する。"""
    keep = set(range(ncards))
    u, t, p = [], [], []
    with open(path) as fh:
        for ln in fh:
            for card in ln.strip().split("|"):
                f = [c.strip() for c in card.split(",")]
                if len(f) < 5 or not f[0].isdigit() or int(f[0]) not in keep:
                    continue
                try:
                    t.append(float(f[1])); p.append(float(f[3])); u.append(float(f[4]))
                except (ValueError, IndexError):
                    pass
    if not u:
        return None
    return {"util": sum(u) / len(u), "temp_max": max(t), "temp_mean": sum(t) / len(t),
            "pw_max": max(p), "pw_mean": sum(p) / len(p)}


def vram_total(rec, ncards):
    """stage 0 の gpu_before から、使用カードの VRAM 合計 (MiB) を拾う。"""
    g = rec["ladder"][0].get("gpu_before") or ""
    tot = 0
    for ln in g.splitlines():
        f = [c.strip() for c in ln.split(",")]
        if len(f) < 2 or not f[0].isdigit() or int(f[0]) >= ncards:
            continue
        tot += float(f[1].split()[0])
    return tot or None


def series(data, key, stage_idx):
    xs, ys = [], []
    for n in sorted(data):
        lad = data[n]["ladder"]
        if stage_idx < len(lad) and lad[stage_idx].get(key) is not None:
            xs.append(n); ys.append(lad[stage_idx][key])
    return xs, ys


def pp0_series(data, size):
    xs, ys = [], []
    for n in sorted(data):
        pp = data[n]["pp0"]
        if pp and size in pp and pp[size].get("prompt_per_second"):
            xs.append(n); ys.append(pp[size]["prompt_per_second"])
    return xs, ys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layer-dir", required=True)
    ap.add_argument("--tensor-dir", default="")
    ap.add_argument("--lang", default="ja", choices=["ja", "en"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--title-extra", default="")
    a = ap.parse_args()
    ja = a.lang == "ja"
    if ja:
        plt.rcParams["font.family"] = ["Noto Sans CJK JP"]
    plt.rcParams["axes.unicode_minus"] = False

    L = load(a.layer_dir, "layer")
    T = load(a.tensor_dir, "tensor") if a.tensor_dir else {}
    if not L and not T:
        sys.exit("no arms found")

    ref = L or T
    any_lad = next(iter(ref.values()))["ladder"]
    depths = [r["effective_depth"] for r in any_lad]
    i_shallow, i_deep = 0, len(depths) - 1
    i_mid = 1 if len(depths) > 1 else 0

    fig, axes = plt.subplots(2, 3, figsize=(19, 10.5))
    ax1, ax2, ax3, ax4, ax5, ax6 = axes.flat
    XT = list(range(2, 8))

    def style(ax, title, ylabel):
        ax.set_title(title, fontsize=12, pad=8)
        ax.set_xlabel("GPU 枚数" if ja else "GPU count")
        ax.set_ylabel(ylabel)
        ax.set_xticks(XT)
        ax.grid(color="#eeeeee")

    def plot_pair(ax, key, idx, dash, tag):
        for data, col, name in ((L, C_LAYER, "layer"), (T, C_TENSOR, "tensor")):
            if not data:
                continue
            xs, ys = series(data, key, idx)
            if xs:
                ax.plot(xs, ys, color=col, ls=dash, marker="o", ms=4, lw=1.9,
                        label=f"{name} / {tag}")

    # (1) decode
    plot_pair(ax1, "predicted_per_second", i_shallow, "-",
              (f"深さ {depths[i_shallow]:,} tok" if ja else f"depth {depths[i_shallow]:,}"))
    plot_pair(ax1, "predicted_per_second", i_deep, "--",
              (f"深さ {depths[i_deep]:,} tok" if ja else f"depth {depths[i_deep]:,}"))
    style(ax1, "① decode (生成速度)" if ja else "(1) decode", "t/s")
    ax1.legend(fontsize=8.5)

    # (2) incremental prefill
    plot_pair(ax2, "prompt_per_second", i_mid, "-",
              (f"深さ {depths[i_mid]:,} tok" if ja else f"depth {depths[i_mid]:,}"))
    plot_pair(ax2, "prompt_per_second", i_deep, "--",
              (f"深さ {depths[i_deep]:,} tok" if ja else f"depth {depths[i_deep]:,}"))
    style(ax2, "② 増分 prefill" if ja else "(2) incremental prefill", "t/s")
    ax2.legend(fontsize=8.5)

    # (3) depth-0 prefill
    for size, dash in (("pp512", "-"), ("pp2048", "--"), ("pp8192", ":")):
        for data, col, name in ((L, C_LAYER, "layer"), (T, C_TENSOR, "tensor")):
            if not data:
                continue
            xs, ys = pp0_series(data, size)
            if xs:
                ax3.plot(xs, ys, color=col, ls=dash, marker="s", ms=3.5, lw=1.7,
                         label=f"{name} / {size}")
    style(ax3, "③ depth-0 prefill (新規プロンプト)" if ja else "(3) depth-0 prefill", "t/s")
    ax3.legend(fontsize=7.5, ncol=2)

    # (4) scaling vs 2 cards
    for data, col, name in ((L, C_LAYER, "layer"), (T, C_TENSOR, "tensor")):
        if not data or 2 not in data:
            continue
        for key, idx, dash, lab in (("predicted_per_second", i_deep, "-", "decode"),
                                    ("prompt_per_second", i_deep, "--", "prefill")):
            xs, ys = series(data, key, idx)
            if not xs or xs[0] != 2:
                continue
            base = ys[0]
            ax4.plot(xs, [y / base for y in ys], color=col, ls=dash, marker="o", ms=4,
                     lw=1.9, label=f"{name} / {lab}")
    ax4.plot(XT, [n / 2 for n in XT], color="#999999", ls="-.", lw=1.2,
             label="理想 (枚数比例)" if ja else "ideal (linear)")
    ax4.axhline(1.0, color="#666666", lw=0.8)
    style(ax4, "④ 2 枚を 1.0 としたスケーリング (最深部)" if ja
          else "(4) scaling vs 2 cards (deepest)", "×")
    ax4.legend(fontsize=8)

    # (5) GPU utilization
    for data, col, name in ((L, C_LAYER, "layer"), (T, C_TENSOR, "tensor")):
        xs, ys = [], []
        for n in sorted(data):
            s = data[n]["sampler"]
            if not s:
                continue
            m = sampler_util(s, n)
            if m:
                xs.append(n); ys.append(m["util"])
        if xs:
            ax5.plot(xs, ys, color=col, marker="o", ms=4, lw=1.9, label=name)
            for x, y in zip(xs, ys):
                ax5.annotate(f"{y:.0f}", (x, y), textcoords="offset points",
                             xytext=(0, 6), ha="center", fontsize=7.5, color=col)
    style(ax5, "⑤ GPU 利用率平均 (使用カードのみ)" if ja
          else "(5) mean GPU utilization (used cards)", "%")
    ax5.set_ylim(0, 100)
    ax5.legend(fontsize=8.5)

    # (6) VRAM
    for data, col, name in ((L, C_LAYER, "layer"), (T, C_TENSOR, "tensor")):
        xs, tot, per = [], [], []
        for n in sorted(data):
            v = vram_total(data[n], n)
            if v:
                xs.append(n); tot.append(v / 1024); per.append(v / 1024 / n)
        if xs:
            ax6.plot(xs, tot, color=col, marker="o", ms=4, lw=1.9, label=f"{name} / 合計" if ja else f"{name} / total")
            ax6.plot(xs, per, color=col, ls="--", marker="^", ms=4, lw=1.5,
                     label=f"{name} / 1 枚あたり" if ja else f"{name} / per card")
    ax6.axhline(15.9, color="#999999", ls=":", lw=1.0)
    ax6.annotate("1 枚の容量 16 GB" if ja else "16 GB per card", (2, 15.9),
                 textcoords="offset points", xytext=(4, -12), fontsize=7.5, color="#777777")
    style(ax6, "⑥ VRAM (モデルロード直後)" if ja else "(6) VRAM after load", "GiB")
    ax6.legend(fontsize=8)

    info = ""
    for d in (a.layer_dir, a.tensor_dir):
        ri = os.path.join(d, "run-info.json") if d else ""
        if ri and os.path.exists(ri):
            with open(ri) as fh:
                j = json.load(fh)
            info = f"{j.get('machine','')} / ctx={j.get('ctx')} / {j.get('date','')[:10]}"
            break
    head = ("aws-gpu01 — GPU 枚数 2→7 スイープ: layer 分割 vs tensor 分割"
            if ja else "aws-gpu01 — GPU count sweep 2→7: layer vs tensor split")
    sub = (info + ("  ／ tensor 腕は GGML_CUDA_ALLREDUCE=none 経路" if ja
                   else "  / tensor arms use GGML_CUDA_ALLREDUCE=none")) + a.title_extra
    fig.suptitle(head + "\n" + sub, fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(a.out, dpi=140)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
