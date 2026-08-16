#!/usr/bin/env python3
"""Plot loss curve for PR #25428 CPU-only Qwen2.5-0.5B finetune verification.

Compares:
- new: PR #25428 + sched_reserve 8x local patch, Qwen2.5-0.5B AdamW lr=1e-5 (main result)
- reference: prior b6290 broken hack loss curve (from prev report), for contrast
"""
import re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ATTACH_NEW = "/home/ubuntu/projects/llm-server-ops/report/attachment/2026-07-25_054901_llama-cpp-cpu-finetune-pr25428-verify"
ATTACH_OLD = "/home/ubuntu/projects/llm-server-ops/report/attachment/2026-07-25_045111_llama-cpp-cpu-finetune-broken"


def parse_with_epoch(path):
    x, y = [], []
    raw = open(path, "rb").read().replace(b"\r", b"\n").decode("utf-8", errors="replace")
    prev_step = 0
    prev_phase = None
    epoch_train = 0
    for line in raw.split("\n"):
        m = re.match(r"(train|val):\s*\[.*?\]\s+data=(\d+)/(\d+)\s+loss=([\d.]+)", line)
        if not m:
            continue
        phase = m.group(1)
        step = int(m.group(2))
        total = int(m.group(3))
        loss = float(m.group(4))
        if phase == "train":
            if step == 1 and prev_step > 1 and prev_phase == "val":
                epoch_train += 1
            x.append(epoch_train * total + step)
            y.append(loss)
        prev_step = step
        prev_phase = phase
    return x, y


fig, ax = plt.subplots(figsize=(11, 6))

# Main result: PR #25428 (+ local sched 8x patch) on Qwen2.5-0.5B at lr=1e-5
x_new, y_new = parse_with_epoch(f"{ATTACH_NEW}/pr25428_ft_qwen.log")
if x_new:
    total = max(x_new)
    x_new_frac = [xi / total for xi in x_new]
    ax.plot(x_new_frac, y_new,
            label=f"PR #25428 + sched 8x patch — Qwen2.5-0.5B AdamW lr=1e-5 (this session, N={len(x_new)}, final 6.23)",
            color="#2ca02c", linewidth=1.4, alpha=0.95)

# Companion: lr=1e-6 (10x smaller) — shows less damage but still degrades
x_lr6, y_lr6 = parse_with_epoch(f"{ATTACH_NEW}/pr25428_ft_qwen_lr6_probe.log")
if x_lr6:
    total = max(x_lr6)
    x_lr6_frac = [xi / total for xi in x_lr6]
    ax.plot(x_lr6_frac, y_lr6,
            label=f"PR #25428 + sched 8x patch — Qwen2.5-0.5B AdamW lr=1e-6 (10x smaller, N={len(x_lr6)}, final 3.25, PPL 22.7)",
            color="#1f77b4", linewidth=1.4, alpha=0.95)

# Winner: lr=1e-7 (100x smaller than lr=1e-5) — CONVERGES, PPL improves 13.9→10.2
x_lr7, y_lr7 = parse_with_epoch(f"{ATTACH_NEW}/pr25428_ft_qwen_lr7_probe.log")
if x_lr7:
    total = max(x_lr7)
    x_lr7_frac = [xi / total for xi in x_lr7]
    ax.plot(x_lr7_frac, y_lr7,
            label=f"PR #25428 + sched 8x patch — Qwen2.5-0.5B AdamW lr=1e-7 (100x smaller, N={len(x_lr7)}, final 2.68, PPL 10.2 ← CONVERGED)",
            color="#9467bd", linewidth=1.6, alpha=1.0)

# Reference: b6290 divergent hack on SmolLM2-135M from prior report
x_old, y_old = parse_with_epoch(f"{ATTACH_OLD}/ft_smollm_b6290p.log")
if x_old:
    total_old = max(x_old)
    x_old_frac = [xi / total_old for xi in x_old]
    ax.plot(x_old_frac, y_old,
            label=f"prev report ref: b6290 patched hack — SmolLM2-135M AdamW lr=1e-5 (broken, N={len(x_old)})",
            color="#d62728", linewidth=1.0, alpha=0.6, linestyle="--")

# Base model loss reference (from prior report, SmolLM2 ≈2.78, Qwen0.5B ≈2.5)
ax.axhline(y=2.5, color="#666666", linestyle=":", linewidth=1,
           label="Qwen2.5-0.5B initial loss ≈ 2.5")

ax.set_xlabel("epoch progress (0 = start of epoch, 1 = end)")
ax.set_ylabel("train loss (cross-entropy)")
ax.set_title("llama-finetune train loss — PR #25428 sweeps lr on Qwen2.5-0.5B, CPU-only (lr=1e-7 CONVERGES: PPL 13.9→10.2)")
ax.set_ylim(0, 20)
ax.legend(loc="upper left", fontsize=8)
ax.grid(True, alpha=0.3)

out = f"{ATTACH_NEW}/pr25428_loss_curve.png"
fig.tight_layout()
fig.savefig(out, dpi=110)
print(f"wrote {out}")
