#!/usr/bin/env python3
"""
llama.cpp の fine-tuning 保守活動タイムラインを描画する。

エンコーディング方針 (dataviz スキル準拠):
  - form: change-over-time なので月次の縦棒。強調は「1 系列を色付け、残りをグレー」
    (anti-patterns.md の「Emphasis (highlight one, gray the rest)」)
  - color: 識別を担うのは「training 機能そのものへの変更」1 系列のみ = categorical slot 1
    (#2a78d6)。「他所のリファクタの巻き添え」は識別ではなく地なので muted 中立色
    (#898781) を当てる。validate_palette.js の結果は
      Lightness band PASS / CVD separation PASS (ΔE 15.9) /
      Normal-vision floor PASS (ΔE 17.8) / Contrast vs surface PASS
      Chroma floor は FAIL だが、これは中立色を意図的に使っているためで想定内
      (同チェックは identity を担う categorical hue に対するもの)
  - 凡例を必ず出し、色のみに依存させない。時代帯にもテキストラベルを入れる
  - 単軸のみ。dual-axis は使わない
"""

import re
import subprocess
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

# ---------------------------------------------------------------- design tokens
SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
SERIES_FUNC = "#2a78d6"   # categorical slot 1 — 識別を担う唯一の系列
SERIES_COLL = "#898781"   # 中立の地 (identity ではない)
STATUS_CRITICAL = "#d03b3b"
STATUS_WARNING = "#fab219"
STATUS_GOOD = "#0ca30c"

plt.rcParams["font.family"] = ["IPAGothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ---------------------------------------------------------------- data
SRC = "/home/ubuntu/projects/llm-server-ops/src/llama.cpp"
PATHS = [
    "examples/baby-llama",
    "examples/train-text-from-scratch",
    "examples/finetune",
    "examples/training",
    "common/train.cpp",
    "common/train.h",
    "ggml/src/ggml-opt.cpp",
    "ggml/include/ggml-opt.h",
    "src/llama-model-saver.cpp",
]

# subject が training 機能そのものへの変更を指すか判定する規則。
# 分類結果は scratchpad/classify.py で全 115 件を目視検証済み。
FUNC_RE = re.compile(
    r"\b(train|training|finetune|fine-tune|baby-llama|ggml-opt|ggml_opt|lora|"
    r"backward|optimizer|adamw|sgd|opt-step|model-saver|model_saver|"
    r"optimization interface)\b",
    re.IGNORECASE,
)
COLLATERAL_RE = re.compile(
    r"\b(typo|readme|rename|comment|whitespace|warning|warnings|include|includes|"
    r"cmake|flake|docker|nix|gitignore|format|formatting|no ci)\b",
    re.IGNORECASE,
)
# 正規表現では拾えない/落とせない個別コミットの手動オーバーライド
FORCE_FUNC = {"8a43e940a", "6c35981a6"}   # ggml/988 新 opt IF, ggml-opt の segfault 修正
FORCE_COLL: set[str] = set()


def load_commits():
    out = subprocess.run(
        ["git", "log", "--reverse", "--format=%h\t%ad\t%s", "--date=short", "--"] + PATHS,
        cwd=SRC, capture_output=True, text=True, check=True,
    ).stdout.strip().split("\n")
    rows = []
    for line in out:
        sha, date, subject = line.split("\t", 2)
        if sha in FORCE_FUNC:
            is_func = True
        elif sha in FORCE_COLL:
            is_func = False
        else:
            is_func = bool(FUNC_RE.search(subject)) and not COLLATERAL_RE.search(subject)
        rows.append((sha, date[:7], subject, is_func))
    return rows


def month_range(start="2023-04", end="2026-07"):
    sy, sm = (int(x) for x in start.split("-"))
    ey, em = (int(x) for x in end.split("-"))
    months, y, m = [], sy, sm
    while (y, m) <= (ey, em):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return months


rows = load_commits()
months = month_range()
idx = {mo: i for i, mo in enumerate(months)}
func_ct = Counter(mo for _, mo, _, f in rows if f)
coll_ct = Counter(mo for _, mo, _, f in rows if not f)
func = [func_ct.get(mo, 0) for mo in months]
coll = [coll_ct.get(mo, 0) for mo in months]

# ---------------------------------------------------------------- eras / events
# (開始月, 終了月(含む), ラベル, 帯の色, 塗り透明度, ハッチ)
ERAS = [
    ("2023-04", "2023-10", "xaedes 期\n個人が単独で実装", STATUS_GOOD, 0.07, None),
    ("2023-11", "2024-06", "漂流期 ①\n作者離脱・周辺修正のみ", STATUS_WARNING, 0.13, None),
    ("2024-07", "2025-04", "fine-tune ツール不在\n(水面下で ggml_opt 再構築)", STATUS_CRITICAL, 0.10, "///"),
    ("2025-05", "2025-08", "Gäßler 期\nggml_opt で再構築", STATUS_GOOD, 0.07, None),
    ("2025-09", "2026-07", "漂流期 ②\n新機能ゼロ (修正 2 件のみ)・壊れたまま", STATUS_CRITICAL, 0.10, "///"),
]

# (月, ラベル, 注記の段 0/1/2)
EVENTS = [
    ("2023-05", "#1360 backward pass 実装\n(baby-llama 誕生)", 2),
    ("2023-09", "#2632 finetune LORA 誕生", 1),
    ("2023-11", "xaedes 最終コミット\n(#3974) → 離脱", 0),
    ("2024-05", "#7463 FA backward を\nGGML_ABORT 化", 2),
    ("2024-07", "#8669 finetune /\ntrain-from-scratch 削除", 0),
    ("2024-11", "ggml/988 新 opt IF\n+ test-grad0 撤去", 1),
    ("2025-05", "#10544 再実装\n(96 行の finetune.cpp)", 2),
    ("2025-07", "#14285 KV cache →\nSET_ROWS 移行", 0),
    ("2025-08", "#13873 最後の機能追加", 1),
    ("2026-01", "#18805 起票 → 2h 後に\nAI slop としてクローズ", 2),
]

# ---------------------------------------------------------------- figure
fig, ax = plt.subplots(figsize=(16.5, 8.2), dpi=150)
fig.patch.set_facecolor(SURFACE)
ax.set_facecolor(SURFACE)

DATA_TOP = 12.0          # 棒グラフ領域の上端
ANNOT_BASE = 13.2        # 注記段の開始
ANNOT_STEP = 2.35
ERA_BAND = 20.6          # 時代帯ラベル専用の帯 (注記段と重ならせない)
Y_MAX = 23.6

# --- 時代帯
for start, end, label, color, alpha, hatch in ERAS:
    x0, x1 = idx[start] - 0.5, idx[end] + 0.5
    ax.axvspan(x0, x1, ymin=0, ymax=1, facecolor=color, alpha=alpha,
               hatch=hatch, edgecolor=color, linewidth=0, zorder=0)
    ax.axvline(x1, color=BASELINE, linewidth=0.8, zorder=1)
    ax.text((x0 + x1) / 2, ERA_BAND + 0.45, label, ha="center", va="bottom",
            fontsize=11, color=INK_SECONDARY, linespacing=1.35, zorder=6)
ax.axhline(ERA_BAND, color=BASELINE, linewidth=0.8, zorder=2)

# --- グリッド (水平のみ・ヘアライン)
for yv in range(2, int(DATA_TOP), 2):
    ax.axhline(yv, color=GRIDLINE, linewidth=0.8, zorder=1)

# --- 棒 (積み上げ。surface 色のエッジで 2px 相当の隙間をつくる)
bars_f = ax.bar(range(len(months)), func, width=0.80, color=SERIES_FUNC,
                edgecolor=SURFACE, linewidth=1.3, zorder=4)
bars_c = ax.bar(range(len(months)), coll, width=0.80, bottom=func, color=SERIES_COLL,
                edgecolor=SURFACE, linewidth=1.3, zorder=3)

# --- 機能変更が発生した月のみ直接ラベル (全点ラベルはしない)
for i, v in enumerate(func):
    if v > 0:
        ax.text(i, func[i] + coll[i] + 0.35, str(v), ha="center", va="bottom",
                fontsize=8.5, color=SERIES_FUNC, fontweight="bold", zorder=6)

# --- イベント注記
for mo, label, tier in EVENTS:
    x = idx[mo]
    y = ANNOT_BASE + ANNOT_STEP * tier
    ax.plot([x, x], [func[x] + coll[x] + 0.6, y - 0.32], color=INK_MUTED,
            linewidth=0.9, zorder=5)
    ax.plot([x], [func[x] + coll[x] + 0.6], marker="o", markersize=4.5,
            color=INK_SECONDARY, zorder=6)
    ax.text(x, y, label, ha="center", va="bottom", fontsize=9.2,
            color=INK_PRIMARY, linespacing=1.3, zorder=6,
            bbox=dict(boxstyle="round,pad=0.34", facecolor=SURFACE,
                      edgecolor=BASELINE, linewidth=0.7))

# --- 軸
ax.set_xlim(-0.8, len(months) - 0.2)
ax.set_ylim(0, Y_MAX)
ax.set_yticks(range(0, int(DATA_TOP), 2))
ax.set_ylabel("月あたりコミット数", fontsize=11, color=INK_SECONDARY, labelpad=8)

xticks = [i for i, mo in enumerate(months) if mo.endswith(("-01", "-07"))]
ax.set_xticks(xticks)
ax.set_xticklabels([months[i] for i in xticks], rotation=45, ha="right", fontsize=9)

ax.tick_params(axis="both", colors=INK_SECONDARY, length=0, pad=5)
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_color(BASELINE)
ax.spines["bottom"].set_linewidth(1.0)

# --- 凡例 (2 系列あるので必ず出す)
ax.legend(
    handles=[
        Patch(facecolor=SERIES_FUNC, edgecolor=SURFACE,
              label="training 機能そのものへの変更"),
        Patch(facecolor=SERIES_COLL, edgecolor=SURFACE,
              label="他所のリファクタの巻き添え"),
    ],
    loc="center left", bbox_to_anchor=(0.515, 0.19), frameon=True,
    facecolor=SURFACE, edgecolor=BASELINE, fontsize=10, labelcolor=INK_SECONDARY,
)

ax.set_title(
    "llama.cpp の fine-tuning 保守活動 — 2 度作られ、2 度放置された",
    fontsize=15.5, color=INK_PRIMARY, pad=16, loc="left", fontweight="bold",
)
fig.text(
    0.5, 0.012,
    "対象パス: examples/{baby-llama, train-text-from-scratch, finetune, training} / "
    "common/train.{cpp,h} / ggml/{src/ggml-opt.cpp, include/ggml-opt.h} / src/llama-model-saver.cpp"
    "   —   llama.cpp HEAD 95a923a64 (2026-07-24) 時点、全 10,118 コミットから抽出",
    ha="center", fontsize=8.6, color=INK_MUTED,
)

fig.tight_layout(rect=(0, 0.028, 1, 1))
OUT = ("/home/ubuntu/projects/llm-server-ops/report/attachment/"
       "2026-07-25_200322_llama-cpp-finetune-history/finetune_timeline.png")
fig.savefig(OUT, facecolor=SURFACE, bbox_inches="tight")
print("wrote:", OUT)
print(f"機能変更 {sum(func)} 件 / 巻き添え {sum(coll)} 件 / 合計 {sum(func)+sum(coll)} 件")
print("2025-09 以降の機能変更:", sum(v for mo, v in zip(months, func) if mo >= "2025-09"))
