#!/usr/bin/env python3
"""消費電力レポート用のサマリ図を作る。

  (a) 測定 30 分の時系列（シャーシ電力 / GPU 合計、フェーズと推論区間を色帯で表示）
  (b) 状態別の内訳（GPU / CPU / DRAM / その他 の積み上げ、2 台合計）
  (c) 2 台合計を 24 時間連続で回した場合の電気代（月額、単価 3 水準）
"""
import os
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from importlib.machinery import SourceFileLoader

plt.rcParams["font.family"] = "IPAGothic"
plt.rcParams["axes.unicode_minus"] = False

HERE = os.path.dirname(os.path.abspath(__file__))
agg = SourceFileLoader("agg", os.path.join(HERE, "aggregate-power.py")).load_module()

PHASE_COLOR = {"A": "#ffffff", "B": "#e74c3c", "C": "#9b59b6", "D": "#ffffff"}


def main():
    intervals = agg.load_llama_intervals(os.path.join(HERE, "llama-server.log"),
                                         agg.OLD_LLAMA_START)
    data = {}
    for srv in ("aws-gpu01", "aws-gpu02"):
        rows, _ = agg.load_power(os.path.join(HERE, f"power_{srv}.csv"))
        data[srv] = {
            "rows": rows,
            "rapl": agg.load_rapl(os.path.join(HERE, f"rapl_{srv}.csv")),
            "dcmi": agg.load_dcmi(os.path.join(HERE, f"dcmi_{srv}.csv")),
        }

    t0 = data["aws-gpu01"]["rows"][0]["epoch"]
    fig = plt.figure(figsize=(14, 12))
    gs = fig.add_gridspec(3, 1, height_ratios=[1.5, 1.05, 0.95], hspace=0.45)

    # ---- (a) 時系列 ----
    ax = fig.add_subplot(gs[0])
    for srv, cc, cg in (("aws-gpu01", "#c0392b", "#2980b9"), ("aws-gpu02", "#e67e22", "#5dade2")):
        rows = data[srv]["rows"]
        ax.plot([(r["epoch"] - t0) / 60 for r in rows], [r["chassis"] for r in rows],
                lw=1.5, color=cc, label=f"{srv} シャーシ全体 (BMC DCMI)")
        ax.plot([(r["epoch"] - t0) / 60 for r in rows], [r["gpu"] for r in rows],
                lw=1.2, color=cg, ls="-", alpha=0.85, label=f"{srv} GPU 合計 (nvidia-smi)")
        d = data[srv]["dcmi"]
        if d:
            ax.plot([(r["epoch"] - t0) / 60 for r in d], [r["chassis"] for r in d],
                    lw=1.5, color=cc, ls=":", alpha=0.9)
    for name, a, b in agg.PHASES:
        k = name[0]
        if PHASE_COLOR[k] != "#ffffff":
            ax.axvspan((a - t0) / 60, (b - t0) / 60, color=PHASE_COLOR[k], alpha=0.13, lw=0)
        ax.text(((a + min(b, t0 + 2600)) / 2 - t0) / 60, 1480, k, ha="center", fontsize=12,
                fontweight="bold", color="#555")
    for a, b in intervals:
        if b > t0:
            ax.axvspan(max(0, (a - t0) / 60), (b - t0) / 60, color="#f39c12", alpha=0.15, lw=0)
    ax.set_xlim(0, 42)
    ax.set_ylim(150, 1560)
    ax.set_xlabel("経過 [分]（起点 20:56:11 JST）")
    ax.set_ylabel("電力 [W]")
    ax.set_title("測定 30 分＋再測定 10 分の時系列 — A:通常運用 / B:llama-server 停止 / "
                 "C:モデルロード / D:ロード後（点線は ssh を張らない再測定）", fontsize=11)
    ax.grid(alpha=0.3)
    h, l = ax.get_legend_handles_labels()
    ax.legend(h + [Patch(color="#f39c12", alpha=0.15), Patch(color="#e74c3c", alpha=0.13),
                   Patch(color="#9b59b6", alpha=0.13)],
              l + ["推論を処理中", "B: サーバ停止", "C: モデルロード"],
              fontsize=8, ncol=3, loc="upper center")

    # ---- (b) 内訳 ----
    ax = fig.add_subplot(gs[1])
    scen = []
    for label, sel in (
        ("推論中\n(A-1)", lambda r: agg.PHASES[0][1] <= r["epoch"] < agg.PHASES[0][2]
            and any(x <= r["epoch"] <= y for x, y in intervals)),
        ("モデル常駐\nアイドル (A-2)", lambda r: agg.PHASES[0][1] <= r["epoch"] < agg.PHASES[0][2]
            and not any(x <= r["epoch"] <= y for x, y in intervals)),
        ("モデルロード中\n(C)", lambda r: agg.PHASES[2][1] <= r["epoch"] < agg.PHASES[2][2]),
        ("llama-server 停止\nGPU 空 (B)", lambda r: agg.PHASES[1][1] <= r["epoch"] < agg.PHASES[1][2]),
    ):
        tot = {"chassis": 0.0, "gpu": 0.0, "cpu": 0.0, "dram": 0.0}
        for srv in ("aws-gpu01", "aws-gpu02"):
            rows = [r for r in data[srv]["rows"] if sel(r)]
            rapl = data[srv]["rapl"]
            tot["chassis"] += mean([r["chassis"] for r in rows])
            tot["gpu"] += mean([r["gpu"] for r in rows])
            rr = [rapl[r["epoch"] // 10] for r in rows if r["epoch"] // 10 in rapl]
            if rr:
                tot["cpu"] += mean([v[0] for v in rr])
                tot["dram"] += mean([v[1] for v in rr])
        scen.append((label, tot))
    xs = range(len(scen))
    gpu = [s[1]["gpu"] for s in scen]
    cpu = [s[1]["cpu"] for s in scen]
    dram = [s[1]["dram"] for s in scen]
    other = [s[1]["chassis"] - s[1]["gpu"] - s[1]["cpu"] - s[1]["dram"] for s in scen]
    ax.bar(xs, gpu, color="#2980b9", label="GPU 13 枚")
    ax.bar(xs, cpu, bottom=gpu, color="#27ae60", label="CPU パッケージ 4 個 (RAPL)")
    ax.bar(xs, dram, bottom=[a + b for a, b in zip(gpu, cpu)], color="#16a085", label="DRAM (RAPL)")
    bars = ax.bar(xs, other, bottom=[a + b + c for a, b, c in zip(gpu, cpu, dram)],
                  color="#95a5a6", label="その他（ファン / 基板 / PLX / HBA / NIC / PSU 変換損失）")
    for i, b in enumerate(bars):
        if cpu[i] == 0:  # RAPL 未取得の区分は「その他」に CPU が埋もれている
            b.set_hatch("//")
            b.set_edgecolor("#e74c3c")
    for i in xs:
        tot = scen[i][1]["chassis"]
        ax.text(i, tot + 18, f"{tot:.0f} W", ha="center", fontsize=11, fontweight="bold")
        ax.text(i, gpu[i] / 2, f"GPU {gpu[i]:.0f}W", ha="center", fontsize=9, color="white")
        if cpu[i] == 0:
            ax.text(i, tot - other[i] / 2, f"非 GPU {other[i]:.0f}W\n(CPU 未測定・斜線)",
                    ha="center", fontsize=9)
        else:
            ax.text(i, tot - other[i] / 2, f"その他 {other[i]:.0f}W", ha="center", fontsize=9)
            ax.text(i, gpu[i] + (cpu[i] + dram[i]) / 2, f"CPU+DRAM {cpu[i] + dram[i]:.0f}W",
                    ha="center", fontsize=8, color="white")
    ax.set_xticks(list(xs))
    ax.set_xticklabels([s[0] for s in scen], fontsize=9)
    ax.set_ylabel("電力 [W]")
    ax.set_ylim(0, max(s[1]["chassis"] for s in scen) * 1.22)
    ax.set_title("2 台合計シャーシ電力の内訳 — llama-server を止めても 10W しか下がらない",
                 fontsize=11)
    ax.legend(fontsize=8, ncol=2, loc="upper right")
    ax.grid(alpha=0.3, axis="y")

    # ---- (c) 電気代 ----
    ax = fig.add_subplot(gs[2])
    d1 = [r["chassis"] for r in data["aws-gpu01"]["dcmi"]]
    d2 = [r["chassis"] for r in data["aws-gpu02"]["dcmi"]]
    cases = [
        ("推論中\n(24h 連続の上限想定)", scen[0][1]["chassis"]),
        ("モデル常駐アイドル", mean(d1) + mean(d2)),
        ("llama-server 停止直後\n(B・停止処理の過渡含む)", scen[3][1]["chassis"]),
        ("電源 OFF\n(BMC のみ)", 25.0),
    ]
    w = 0.26
    for j, rate in enumerate((20, 30, 40)):
        vals = [c[1] * 24 * 30 / 1000 * rate / 10000 for c in cases]
        bars = ax.bar([i + (j - 1) * w for i in range(len(cases))], vals, w,
                      label=f"{rate} 円/kWh", color=["#bdc3c7", "#e67e22", "#c0392b"][j])
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.1,
                    f"{b.get_height():.2f}", ha="center", fontsize=8)
    ax.set_xticks(range(len(cases)))
    ax.set_xticklabels([f"{c[0]}\n{c[1]:.0f} W" for c in cases], fontsize=9)
    ax.set_ylabel("電気代 [万円/月]")
    ax.set_title("2 台合計を 24 時間連続で維持した場合の電気代（30 日換算）"
                 "※電源 OFF は BMC 待機電力の実測 min 値からの概算", fontsize=11)
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3, axis="y")

    fig.suptitle("aws-gpu01 / aws-gpu02 消費電力実測（2026-08-18 20:56〜21:38 JST）",
                 fontsize=14, y=0.95)
    out = os.path.join(HERE, "summary.png")
    fig.savefig(out, dpi=110, bbox_inches="tight")
    print("wrote", out)


if __name__ == "__main__":
    main()
