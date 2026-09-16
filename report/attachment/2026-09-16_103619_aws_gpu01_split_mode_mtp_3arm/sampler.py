#!/usr/bin/env python3
"""Summarize sampler-*.log. Averages over the GPUs the arm actually used
(layer2 uses CUDA0-1 only, so averaging over all 7 would understate it)."""
import sys, os
USED = {"layer": range(7), "tensor": range(7), "layer2": range(2)}
for path in sorted(sys.argv[1:]):
    arm = os.path.basename(path).replace("sampler-", "").replace(".log", "")
    keep = set(USED.get(arm, range(7)))
    u, t, p = [], [], []
    for ln in open(path):
        for card in ln.strip().split("|"):
            f = [c.strip() for c in card.split(",")]
            if len(f) < 5 or not f[0].isdigit() or int(f[0]) not in keep:
                continue
            try:
                t.append(float(f[1])); p.append(float(f[3])); u.append(float(f[4]))
            except (ValueError, IndexError):
                pass
    if not u:
        print(f"{os.path.basename(path)}: (no samples)"); continue
    print(f"{arm:7s} (GPU {len(keep)}枚): util mean {sum(u)/len(u):5.1f}% | "
          f"temp max {max(t):.0f}℃ mean {sum(t)/len(t):.1f}℃ | "
          f"power max {max(p):.0f} W mean {sum(p)/len(p):.0f} W")
