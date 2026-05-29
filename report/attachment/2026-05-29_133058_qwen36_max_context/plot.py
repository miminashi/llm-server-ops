#!/usr/bin/env python3
"""調査結果から 3 枚の PNG を生成 (実データの形に合わせた版)。
入力: stages.csv (label,ctx,yarn,ub,loaded,vram_gb,...,pp_tps,tg_tps), niah_results.jsonl
出力: vram.png / speed.png / niah.png"""
import csv
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

D = "/tmp/qwen36_ctx"


def fnum(x):
    try:
        return float(x)
    except (ValueError, TypeError):
        return None


def load_stages():
    with open(os.path.join(D, "stages.csv")) as f:
        return list(csv.DictReader(f))


def plot_vram(rows):
    rows = [r for r in rows if fnum(r.get("vram_gb"))]
    rows.sort(key=lambda r: int(r["ctx"]))
    labels = [f"{int(r['ctx'])//1024}K\nub={r['ub']}\n{r['yarn']}" for r in rows]
    vram = [fnum(r["vram_gb"]) for r in rows]
    x = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(x, vram, color="#4C72B0", width=0.6)
    ax.axhline(64, color="red", ls="--", lw=1.5, label="64 GB (P100x4 total)")
    ax.axhline(21, color="gray", ls=":", lw=1.2, label="~21 GB model weights")
    for b, v in zip(bars, vram):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.6, f"{v:.1f}", ha="center", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("VRAM used at load (GB, 4-GPU total)")
    ax.set_title("Qwen3.6-35B-A3B / P100x4: VRAM at load vs context\n(hybrid SSM arch -> KV barely grows; ub drives compute buffer)")
    ax.set_ylim(0, 70)
    ax.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(D, "vram.png"), dpi=110)
    print("wrote vram.png")


def plot_speed(rows):
    rows = [r for r in rows if fnum(r.get("pp_tps"))]
    rows.sort(key=lambda r: int(r["ctx"]))
    # x 軸は実測プロンプト長 (prompt_k) を優先。S2 は 524K 構成で ~297K を処理した点に注意。
    ctx = [fnum(r.get("prompt_k")) or int(r["ctx"]) / 1024 for r in rows]
    pp = [fnum(r["pp_tps"]) for r in rows]
    tg = [fnum(r["tg_tps"]) for r in rows]
    fig, ax1 = plt.subplots(figsize=(9, 5))
    l1, = ax1.plot(ctx, pp, "o-", color="#4C72B0", label="prompt processing (pp)")
    ax1.set_xlabel("prompt length processed (K tokens)")
    ax1.set_ylabel("pp throughput (t/s)", color="#4C72B0")
    ax1.tick_params(axis="y", labelcolor="#4C72B0")
    for xi, p in zip(ctx, pp):
        ax1.annotate(f"{p:.0f}", (xi, p), textcoords="offset points", xytext=(0, 8), fontsize=8, color="#4C72B0")
    ax2 = ax1.twinx()
    l2, = ax2.plot(ctx, tg, "s--", color="#C44E52", label="token generation (tg)")
    ax2.set_ylabel("tg throughput (t/s)", color="#C44E52")
    ax2.tick_params(axis="y", labelcolor="#C44E52")
    for xi, t in zip(ctx, tg):
        ax2.annotate(f"{t:.1f}", (xi, t), textcoords="offset points", xytext=(0, -12), fontsize=8, color="#C44E52")
    ax1.set_title("Qwen3.6-35B-A3B / P100x4: throughput vs context\n(full re-process every request; no prompt-cache reuse)")
    ax1.legend(handles=[l1, l2], loc="upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(D, "speed.png"), dpi=110)
    print("wrote speed.png")


def plot_niah():
    rows = []
    with open(os.path.join(D, "niah_results.jsonl")) as fp:
        for line in fp:
            line = line.strip()
            if line and '"label": "S' in line:
                rows.append(json.loads(line))
    # x = prompt_tokens (実測), y = needle position (depth*prompt), color = found
    fig, ax = plt.subplots(figsize=(9, 5))
    for r in rows:
        ptok = (r.get("prompt_n") or r["target_tokens"]) / 1024
        pos = ptok * r["depth"]
        color = "#55A868" if r["found"] else "#C44E52"
        marker = "o" if r["found"] else "X"
        ax.scatter(ptok, pos, c=color, s=180, marker=marker, edgecolors="black", zorder=3)
        ax.annotate(f"{r['label']}\nd={int(r['depth']*100)}%", (ptok, pos),
                    textcoords="offset points", xytext=(8, 6), fontsize=7)
    ax.axhline(262144 / 1024, color="orange", ls="--", lw=1.5, label="native 262K (n_ctx_train)")
    ax.set_xlabel("prompt length (K tokens)")
    ax.set_ylabel("needle position (K tokens)")
    ax.set_title("Qwen3.6-35B-A3B: Needle-in-a-Haystack\n(green O = retrieved, red X = miss)")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(D, "niah.png"), dpi=110)
    print("wrote niah.png")


if __name__ == "__main__":
    s = load_stages()
    plot_vram(s)
    plot_speed(s)
    plot_niah()
