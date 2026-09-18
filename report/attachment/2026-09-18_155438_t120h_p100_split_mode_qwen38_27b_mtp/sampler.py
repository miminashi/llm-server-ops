#!/usr/bin/env python3
"""sampler-<mode>.log から GPU 利用率・温度・電力の統計を出す。
形式: <ts> <idx>, <temp.gpu>, <temp.mem>, <power>, <util> が GPU ごとに並ぶ。"""
import sys, os, re, statistics

d = sys.argv[1]
modes = sys.argv[2].split(',')
active = {m: int(n) for m, n in (x.split(':') for x in sys.argv[3].split(','))} if len(sys.argv) > 3 else {}

print("| モード | 利用率 平均 | 温度 最大 / 平均 | 電力 最大 / 平均 | サンプル数 |")
print("|---|---:|---:|---:|---:|")
for m in modes:
    p = os.path.join(d, f'sampler-{m}.log')
    if not os.path.exists(p):
        continue
    utils, temps, powers = [], [], []
    n_act = active.get(m)
    with open(p) as f:
        for line in f:
            nums = re.findall(r'(\d+),\s*(\d+),\s*(?:N/A|[\d.]+),\s*([\d.]+),\s*(\d+)', line)
            for idx, temp, pw, ut in nums:
                if n_act is not None and int(idx) >= n_act:
                    continue
                utils.append(int(ut)); temps.append(int(temp)); powers.append(float(pw))
    if utils:
        print(f"| {m} | {statistics.mean(utils):.1f}% | {max(temps)}℃ / {statistics.mean(temps):.1f}℃ "
              f"| {max(powers):.0f} W / {statistics.mean(powers):.0f} W | {len(utils)} |")
    else:
        # フォーマットが違う場合は生の先頭行を見せる
        with open(p) as f:
            print(f"| {m} | (parse failed) | | | |")
            for i, line in enumerate(f):
                if i < 2: print("    raw:", line.strip()[:200])
