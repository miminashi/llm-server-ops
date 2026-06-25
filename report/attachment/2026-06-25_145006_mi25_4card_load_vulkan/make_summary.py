#!/usr/bin/env python3
"""核心発見サマリ PNG 生成 (Vulkan 負荷追試)。
ROCm 版 (2026-06-25_094641) と Vulkan 版 (本実施) の time-to-fault・完走可否を
構成別に並べて、Vulkan で 4 枚負荷でのみ 8820 が落ち、3 枚なら 8820 を含めても安定、
を視覚化する。日本語フォント不在のため英語ラベルに統一(原レポート踏襲)。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# (config, backend, time_to_fault_or_total_run_s, status: 'fault'|'pass', signature)
ROWS = [
    ("4-card (all)",     "ROCm",   745,  "fault", "UTCL2 page fault @0x100000000"),
    ("4-card (all)",     "Vulkan", 2208, "fault", "amdgpu GPU reset / vk::DeviceLost"),
    ("3-card incl 8820", "ROCm",   1613, "fault", "UTCL2 page fault @0x100000000"),
    ("3-card incl 8820", "Vulkan", 2307, "pass",  "completed 3/3 (no fault)"),
    ("3-card excl 8820", "ROCm",   2361, "pass",  "completed 3/3 (control)"),
    ("3-card excl 8820", "Vulkan", 2210, "pass",  "completed 3/3 (control)"),
]
configs = ["4-card (all)", "3-card incl 8820", "3-card excl 8820"]
backends = ["ROCm", "Vulkan"]

fig, ax = plt.subplots(figsize=(13, 5.7))
x = np.arange(len(configs))
width = 0.38

vals_rocm, vals_vk, colors_rocm, colors_vk, status_rocm, status_vk = [], [], [], [], [], []
for cfg in configs:
    for be in backends:
        for c, b, t, st, sig in ROWS:
            if c == cfg and b == be:
                if be == "ROCm":
                    vals_rocm.append(t)
                    colors_rocm.append("#d83a3a" if st == "fault" else "#3aa055")
                    status_rocm.append(st)
                else:
                    vals_vk.append(t)
                    colors_vk.append("#d83a3a" if st == "fault" else "#3aa055")
                    status_vk.append(st)
                break

b1 = ax.bar(x - width/2, vals_rocm, width, color=colors_rocm, edgecolor="black", linewidth=0.6, label="ROCm")
b2 = ax.bar(x + width/2, vals_vk, width, color=colors_vk, edgecolor="black", linewidth=0.6, label="Vulkan", hatch="//")

# value + status marker
for b, v, st in zip(b1, vals_rocm, status_rocm):
    mark = "X FAULT" if st == "fault" else "OK PASS"
    ax.text(b.get_x() + b.get_width()/2, v + 50, f"{v}s\n{mark}",
            ha="center", va="bottom", fontsize=9.5, fontweight="bold",
            color=("#d83a3a" if st == "fault" else "#207040"))
for b, v, st in zip(b2, vals_vk, status_vk):
    mark = "X FAULT" if st == "fault" else "OK PASS"
    ax.text(b.get_x() + b.get_width()/2, v + 50, f"{v}s\n{mark}",
            ha="center", va="bottom", fontsize=9.5, fontweight="bold",
            color=("#d83a3a" if st == "fault" else "#207040"))

# annotation: ROCm 4-card fault line (745s)
ax.axhline(y=745, color="#d83a3a", linestyle=":", alpha=0.45, linewidth=1)
ax.text(2.55, 760, "ROCm 4-card t2f ~745s", color="#d83a3a", fontsize=8, va="bottom", ha="right")

ax.set_xticks(x)
ax.set_xticklabels([f"{c}\n(Qwen3.6-35B-A3B, ctx=131072)" for c in configs], fontsize=10)
ax.set_ylabel("Continuous load duration [seconds]", fontsize=11)
ax.set_title("mi25 4-card recovery: ROCm vs Vulkan load endurance\n"
             "Vulkan reproduces the 8820 fault at 4-card load, but 3-card incl 8820 stays stable",
             fontsize=12, fontweight="bold")
ax.set_ylim(0, max(vals_rocm + vals_vk) * 1.20)
ax.grid(axis="y", alpha=0.3)

ok_patch = mpatches.Patch(color="#3aa055", label="PASS (completed)")
ng_patch = mpatches.Patch(color="#d83a3a", label="FAULT (8820)")
rocm_patch = mpatches.Patch(facecolor="white", edgecolor="black", label="ROCm/HIP")
vk_patch = mpatches.Patch(facecolor="white", edgecolor="black", hatch="//", label="Vulkan/RADV")
ax.legend(handles=[ok_patch, ng_patch, rocm_patch, vk_patch], loc="upper left", fontsize=9, ncol=2)

ax.text(1, -360,
        "8820 = SLOT6 / BDF 87:00.0. Load = synthetic multi-turn coding chat, trial_sec=720s, MAX_TRIALS=3 (or 12 for Phase 1).\n"
        "Vulkan 4-card fault signature = amdgpu_job_timedout -> GPU reset / VRAM lost -> vk::DeviceLost (distinct from ROCm UTCL2 page fault).",
        fontsize=8, ha="center", style="italic", color="#444")

plt.tight_layout()
plt.savefig("summary.png", dpi=130, bbox_inches="tight")
print("summary.png written")
