#!/usr/bin/env python3
# Phase1(KLD/PPLログ) + Phase2(破綻JSON) + Phase3(正答率JSON)を集計し、
# results.json と 核心サマリPNG(summary.png)を生成する。
import json, re, sys, os, difflib

D = sys.argv[1] if len(sys.argv) > 1 else "."


def parse_kld_log(path):
    if not os.path.exists(path):
        return None
    txt = open(path, encoding="utf-8", errors="replace").read()

    def g(pat):
        m = re.search(pat, txt)
        return float(m.group(1)) if m else None
    return {
        "ppl_q": g(r"Mean PPL\(Q\)\s*:\s*([0-9.]+)"),
        "ppl_base": g(r"Mean PPL\(base\)\s*:\s*([0-9.]+)"),
        "ppl_ratio": g(r"Mean PPL\(Q\)/PPL\(base\)\s*:\s*([0-9.]+)"),
        "mean_kld": g(r"Mean\s+KLD:\s*([0-9.\-]+)"),
        "median_kld": g(r"Median\s+KLD:\s*([0-9.\-]+)"),
        "kld_99": g(r"99\.0%\s+KLD:\s*([0-9.\-]+)"),
        "max_kld": g(r"Maximum KLD:\s*([0-9.\-]+)"),
        "same_top": g(r"Same top p:\s*([0-9.]+)"),
    }


def load_json(path):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None


phase1 = {
    "en": parse_kld_log(os.path.join(D, "ppl/vulkan-en-kld.log")),
    "ja": parse_kld_log(os.path.join(D, "ppl/vulkan-ja-kld.log")),
    "control_en": parse_kld_log(os.path.join(D, "ppl/vulkan-en-ctrlkld.log")),
}

p2r = load_json(os.path.join(D, "phase2-rocm.json"))
p2v = load_json(os.path.join(D, "phase2-vulkan.json"))
p3r = load_json(os.path.join(D, "phase3-rocm.json"))
p3v = load_json(os.path.join(D, "phase3-vulkan.json"))

# Phase2比較: 破綻フラグ集計 + ROCm/Vulkan出力の一致(類似度)
phase2 = {"rocm_break": [], "vulkan_break": [], "pairs": []}


def break_flags(rec):
    return {
        "lang": rec.get("lang"), "kind": rec.get("kind"),
        "empty": rec.get("empty"), "finish": rec.get("finish_reason"),
        "max_rep": rec.get("max_rep"), "garble": rec.get("garble_ratio"),
        "len": rec.get("len_chars"),
    }


if p2r and p2v:
    vr = {(r["lang"], r["kind"]): r for r in p2v if "content" in r}
    for r in p2r:
        if "content" not in r:
            continue
        key = (r["lang"], r["kind"])
        v = vr.get(key)
        phase2["rocm_break"].append(break_flags(r))
        if v:
            phase2["vulkan_break"].append(break_flags(v))
            sim = difflib.SequenceMatcher(None, r["content"], v["content"]).ratio()
            phase2["pairs"].append({
                "lang": r["lang"], "kind": r["kind"],
                "similarity": round(sim, 3),
                "rocm_len": r["len_chars"], "vulkan_len": v["len_chars"],
                "vulkan_garble": v.get("garble_ratio"), "vulkan_rep": v.get("max_rep"),
                "vulkan_finish": v.get("finish_reason"),
            })

phase3 = {
    "rocm": {"gsm8k": p3r["gsm8k"]["acc"] if p3r else None, "jmmlu": p3r["jmmlu"]["acc"] if p3r else None,
             "gsm8k_n": p3r["gsm8k"]["n"] if p3r else None, "jmmlu_n": p3r["jmmlu"]["n"] if p3r else None,
             "gsm8k_c": p3r["gsm8k"]["correct"] if p3r else None, "jmmlu_c": p3r["jmmlu"]["correct"] if p3r else None},
    "vulkan": {"gsm8k": p3v["gsm8k"]["acc"] if p3v else None, "jmmlu": p3v["jmmlu"]["acc"] if p3v else None,
               "gsm8k_n": p3v["gsm8k"]["n"] if p3v else None, "jmmlu_n": p3v["jmmlu"]["n"] if p3v else None,
               "gsm8k_c": p3v["gsm8k"]["correct"] if p3v else None, "jmmlu_c": p3v["jmmlu"]["correct"] if p3v else None},
}

results = {"phase1_kld_ppl": phase1, "phase2_break": phase2, "phase3_accuracy": phase3}
with open(os.path.join(D, "results.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("WROTE results.json")
print(json.dumps(results, ensure_ascii=False, indent=2)[:1500])

# ---- PNG ----
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    # 日本語フォント探索(無ければASCIIラベルで継続)
    for fp in ["/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
               "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
               "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"]:
        if os.path.exists(fp):
            fm.fontManager.addfont(fp)
            matplotlib.rcParams["font.family"] = fm.FontProperties(fname=fp).get_name()
            break

    fig, ax = plt.subplots(2, 2, figsize=(12, 9))
    fig.suptitle("mi25 Qwen3.6-35B-A3B: ROCm(v8533) vs Vulkan(v9620) Quality Equivalence", fontsize=13)

    # (a) Same-top
    labels = ["EN", "JA", "Control\n(VK vs VK)"]
    vals = [phase1["en"]["same_top"], phase1["ja"]["same_top"],
            phase1["control_en"]["same_top"] if phase1["control_en"] else None]
    ax[0, 0].bar(labels, vals, color=["#4C72B0", "#DD8452", "#55A868"])
    ax[0, 0].axhline(99, ls="--", c="gray", lw=1)
    ax[0, 0].set_title("Same top-token agreement (%)")
    ax[0, 0].set_ylim(90, 101)
    for i, v in enumerate(vals):
        if v is not None:
            ax[0, 0].text(i, v + 0.1, f"{v:.2f}", ha="center", fontsize=9)

    # (b) PPL grouped
    import numpy as np
    x = np.arange(2)
    w = 0.35
    ppl_r = [phase1["en"]["ppl_base"], phase1["ja"]["ppl_base"]]
    ppl_v = [phase1["en"]["ppl_q"], phase1["ja"]["ppl_q"]]
    ax[0, 1].bar(x - w/2, ppl_r, w, label="ROCm", color="#4C72B0")
    ax[0, 1].bar(x + w/2, ppl_v, w, label="Vulkan", color="#DD8452")
    ax[0, 1].set_xticks(x); ax[0, 1].set_xticklabels(["EN", "JA"])
    ax[0, 1].set_title("Perplexity (lower=better)"); ax[0, 1].legend()
    for i in range(2):
        ax[0, 1].text(i - w/2, ppl_r[i] + 0.02, f"{ppl_r[i]:.3f}", ha="center", fontsize=8)
        ax[0, 1].text(i + w/2, ppl_v[i] + 0.02, f"{ppl_v[i]:.3f}", ha="center", fontsize=8)

    # (c) Mean KLD
    kld = [phase1["en"]["mean_kld"], phase1["ja"]["mean_kld"],
           phase1["control_en"]["mean_kld"] if phase1["control_en"] else 0]
    ax[1, 0].bar(labels, kld, color=["#4C72B0", "#DD8452", "#55A868"])
    ax[1, 0].axhline(0.01, ls="--", c="gray", lw=1)
    ax[1, 0].set_title("Mean KL divergence (nats, lower=better)")
    for i, v in enumerate(kld):
        if v is not None:
            ax[1, 0].text(i, v, f"{v:.4f}", ha="center", va="bottom", fontsize=9)

    # (d) Accuracy grouped
    accr = [phase3["rocm"]["gsm8k"], phase3["rocm"]["jmmlu"]]
    accv = [phase3["vulkan"]["gsm8k"], phase3["vulkan"]["jmmlu"]]
    ax[1, 1].bar(x - w/2, accr, w, label="ROCm", color="#4C72B0")
    ax[1, 1].bar(x + w/2, accv, w, label="Vulkan", color="#DD8452")
    ax[1, 1].set_xticks(x); ax[1, 1].set_xticklabels(["GSM8K(EN)", "JMMLU(JA)"])
    ax[1, 1].set_title("Task accuracy"); ax[1, 1].set_ylim(0, 1.05); ax[1, 1].legend()
    for i in range(2):
        if accr[i] is not None:
            ax[1, 1].text(i - w/2, accr[i] + 0.01, f"{accr[i]:.2f}", ha="center", fontsize=8)
        if accv[i] is not None:
            ax[1, 1].text(i + w/2, accv[i] + 0.01, f"{accv[i]:.2f}", ha="center", fontsize=8)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    plt.savefig(os.path.join(D, "summary.png"), dpi=110)
    print("WROTE summary.png")
except Exception as e:
    print(f"PNG skipped: {e}")
