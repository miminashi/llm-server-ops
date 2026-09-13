#!/usr/bin/env python3
"""vision 検証用の画像 2 枚と、それを含む chat completions ペイロードを生成する。

nicholasshirley が PR #27773 で報告した vision 動作確認 (1500x500 のロゴと
2875x1500 の図表) に寸法を合わせている。読ませる情報は英数字と日本語を
混在させ、OCR の成否を明確に判定できるコード文字列を含める。
"""
import base64, json, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

plt.rcParams["font.family"] = "IPAGothic"

# --- 1) ロゴ相当 1500x500 ---
fig = plt.figure(figsize=(15, 5), dpi=100)
ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off")
ax.add_patch(FancyBboxPatch((0.02, 0.08), 0.96, 0.84, boxstyle="round,pad=0.01",
                            fc="#f3f6fb", ec="#2b4c7e", lw=4))
ax.text(0.5, 0.66, "GLM-5.3-Flash", ha="center", va="center", fontsize=64, color="#2b4c7e", weight="bold")
ax.text(0.5, 0.34, "SERIAL P100-RPC-7429 / 13 GPU", ha="center", va="center", fontsize=34, color="#333333")
fig.savefig("vis_logo.png"); plt.close(fig)

# --- 2) 図表相当 2875x1500 ---
fig = plt.figure(figsize=(28.75, 15), dpi=100)
ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off")
ax.set_xlim(0, 1); ax.set_ylim(0, 1)
ax.text(0.5, 0.93, "RPC 分散構成図", ha="center", fontsize=54, weight="bold")

def box(x, y, w, h, title, lines, fc):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.008", fc=fc, ec="#333333", lw=3))
    ax.text(x + w / 2, y + h - 0.07, title, ha="center", fontsize=42, weight="bold")
    for i, ln in enumerate(lines):
        ax.text(x + w / 2, y + h - 0.16 - i * 0.09, ln, ha="center", fontsize=34)

box(0.06, 0.36, 0.34, 0.45, "aws-gpu01", ["MAIN HOST", "Tesla P100 x 7", "VRAM 112 GB", "CODE ALPHA-4821"], "#dce9f7")
box(0.60, 0.36, 0.34, 0.45, "aws-gpu02", ["RPC WORKER", "Tesla P100 x 6", "VRAM 88 GB", "CODE BRAVO-1935"], "#f7e6dc")
ax.add_patch(FancyArrowPatch((0.40, 0.58), (0.60, 0.58), arrowstyle="<->", mutation_scale=60, lw=5, color="#2b4c7e"))
ax.text(0.50, 0.62, "100GbE", ha="center", fontsize=38, color="#2b4c7e", weight="bold")
ax.text(0.50, 0.545, "port 50052", ha="center", fontsize=32, color="#2b4c7e")
ax.text(0.5, 0.22, "MODEL SIZE 153.3 GiB   /   CTX 131072", ha="center", fontsize=40)
ax.text(0.5, 0.13, "合言葉は「南天5518」である", ha="center", fontsize=40, color="#a02020")
fig.savefig("vis_diagram.png"); plt.close(fig)


def payload(img, question, max_tokens=384):
    b64 = base64.b64encode(open(img, "rb").read()).decode()
    return {"messages": [{"role": "user", "content": [
        {"type": "text", "text": question},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}]}],
        "temperature": 0, "top_p": 1.0, "max_tokens": max_tokens, "stream": False}


json.dump(payload("vis_logo.png", "この画像に書かれている文字列をすべてそのまま書き出してください。"),
          open("vision_logo.json", "w"), ensure_ascii=False)
json.dump(payload("vis_diagram.png",
                  "この図に書かれている内容を読み取ってください。2 台のホスト名、それぞれの CODE、"
                  "接続に使うポート番号、モデルサイズ、そして合言葉を答えてください。"),
          open("vision_diagram.json", "w"), ensure_ascii=False)
print("ok")
