#!/usr/bin/env python3
"""telemetry_rocmsmi.log から per-card power を期間別に集計する。"""
import re
import sys
from statistics import mean, quantiles

LOG = sys.argv[1] if len(sys.argv) > 1 else "telemetry_rocmsmi.log"

# 8820 long = epoch 1782514804 (08:00:04) 〜 1782522007 (10:00:07)
# healthy 3 = 1782513696 (07:41:36) 〜 1782514384 (07:59:44)
# short addn = 1782522036 (10:00:36) 〜 1782522756 (10:12:36)
PHASES = [
    # 07:41:36 〜 07:47:39 SLOT2 (Vulkan menu 4 / HIP idx 0 / GPU[0])
    ("SLOT2_only_phase", 1782513696, 1782514059),
    # 07:47:39 〜 07:53:40 SLOT4 (HIP idx 1 / GPU[1])
    ("SLOT4_only_phase", 1782514059, 1782514420),
    # 07:53:40 〜 07:59:44 SLOT8 (HIP idx 2 / GPU[2])
    ("SLOT8_only_phase", 1782514420, 1782514784),
    # 08:00:04 〜 10:00:07 8820 long (HIP idx 3 / GPU[3])
    ("8820_long_120min", 1782514804, 1782522007),
    # 10:00:36 〜 10:06:33 pass03 + 10:06:33 〜 10:12:36 pass04
    ("8820_short_addn", 1782522036, 1782522756),
    # 全 memtest 期間
    ("ALL_memtest_period", 1782513696, 1782522756),
]


def parse(path):
    samples = []  # (epoch, [power0, power1, power2, power3])
    epoch = None
    current = {}
    re_epoch = re.compile(r"epoch=(\d+)")
    re_power = re.compile(r"GPU\[(\d+)\].*Current Socket Graphics Package Power \(W\):\s*([\d.]+)")
    with open(path) as f:
        for line in f:
            m = re_epoch.search(line)
            if m:
                if current and epoch is not None:
                    samples.append((epoch, current))
                epoch = int(m.group(1))
                current = {}
                continue
            m = re_power.search(line)
            if m:
                idx = int(m.group(1))
                p = float(m.group(2))
                current[idx] = p
        if current and epoch is not None:
            samples.append((epoch, current))
    return samples


def stat(values):
    if not values:
        return None
    vs = sorted(values)
    n = len(vs)
    p95 = vs[min(n - 1, int(n * 0.95))]
    return {
        "n": n,
        "min": min(vs),
        "mean": round(mean(vs), 2),
        "p95": p95,
        "max": max(vs),
    }


def main():
    samples = parse(LOG)
    print(f"total samples: {len(samples)}")
    print(f"epoch range: {samples[0][0]} 〜 {samples[-1][0]}")
    for name, t0, t1 in PHASES:
        print(f"\n=== {name} (epoch {t0}-{t1}) ===")
        in_phase = [s for s in samples if t0 <= s[0] <= t1]
        print(f"samples in phase: {len(in_phase)}")
        for gpu in range(4):
            vals = [s[1].get(gpu) for s in in_phase if gpu in s[1]]
            vals = [v for v in vals if v is not None]
            if not vals:
                continue
            s = stat(vals)
            print(f"  GPU[{gpu}]: n={s['n']} min={s['min']:.1f} mean={s['mean']:.2f} p95={s['p95']:.1f} max={s['max']:.1f} W")


if __name__ == "__main__":
    main()
