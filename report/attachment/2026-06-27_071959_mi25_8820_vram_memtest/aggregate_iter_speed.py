#!/usr/bin/env python3
"""mt_8820_long.log の iteration 速度を時間経過 bucket で集計。"""
import re
import sys
from statistics import mean

LOG = sys.argv[1] if len(sys.argv) > 1 else "mt_8820_long.log"
RE = re.compile(
    r"^\s*(\d+) iteration\. Passed \s*([\d.]+) seconds\s+"
    r"written:\s+([\d.]+)GB\s+([\d.]+)GB/sec\s+"
    r"checked:\s+([\d.]+)GB\s+([\d.]+)GB/sec"
)

BUCKETS = [
    ("0-1000",       0, 1000),
    ("1000-5000",    1000, 5000),
    ("5000-10000",   5000, 10000),
    ("10000-20000",  10000, 20000),
    ("20000-30000",  20000, 30000),
    ("30000-40000",  30000, 40000),
    ("40000-50000",  40000, 50000),
    ("50000-60000",  50000, 60000),
    ("60000-65000",  60000, 65000),
]

rows = []
with open(LOG) as f:
    for line in f:
        m = RE.search(line)
        if m:
            it = int(m.group(1))
            sec = float(m.group(2))
            w_gb = float(m.group(3))
            w_bw = float(m.group(4))
            c_gb = float(m.group(5))
            c_bw = float(m.group(6))
            rows.append((it, sec, w_gb, w_bw, c_gb, c_bw))

print(f"total iter entries: {len(rows)}")
print(f"final iter: {rows[-1][0]}")
print()
print(f"{'bucket':<14} {'n':>3} {'write_bw[GB/s]':>16} {'check_bw[GB/s]':>16}")
for name, lo, hi in BUCKETS:
    in_b = [r for r in rows if lo <= r[0] < hi]
    if not in_b:
        continue
    w_mean = mean(r[3] for r in in_b)
    c_mean = mean(r[5] for r in in_b)
    print(f"{name:<14} {len(in_b):>3} {w_mean:>15.1f} {c_mean:>16.1f}")

# trend gradient
print()
print("--- trend (write_bw delta from first bucket) ---")
first_w = mean(r[3] for r in rows if r[0] < 1000)
for name, lo, hi in BUCKETS:
    in_b = [r for r in rows if lo <= r[0] < hi]
    if not in_b:
        continue
    w_mean = mean(r[3] for r in in_b)
    print(f"{name:<14} {w_mean - first_w:+7.1f} GB/s ({100*(w_mean - first_w)/first_w:+5.1f}%)")
