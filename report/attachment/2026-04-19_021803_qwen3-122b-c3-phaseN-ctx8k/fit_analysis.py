#!/usr/bin/env python3
"""Phase N compute buffer 分析
fa=0: Phase M 3点厳密解を ctx=8192 に外挿して OOM 値と比較
fa=1: Phase N 新規 3点 (ctx=1024,2048,8192) + Phase L (ctx=4096) の 4点で係数抽出
"""
import numpy as np

def solve3(xs, ys):
    A = np.array([[x*x, x, 1] for x in xs], dtype=float)
    b = np.array(ys, dtype=float)
    return np.linalg.solve(A, b)

def fit_quadratic_ls(xs, ys):
    A = np.array([[x*x, x, 1] for x in xs], dtype=float)
    b = np.array(ys, dtype=float)
    coef, *_ = np.linalg.lstsq(A, b, rcond=None)
    pred = A @ coef
    resid = b - pred
    return coef, resid

def loglog_slope(xs, ys):
    lx = np.log(xs); ly = np.log(ys)
    k = np.polyfit(lx, ly, 1)
    return k

print("="*70)
print("Phase N: fa=0 ctx=8192 CUDA1 OOM 予測 vs 実測")
print("="*70)
# Phase M 3点厳密解 (ctx=1024/2048/4096) for fa=0
fa0_buf = {
    "CUDA0": (1122.00, 1196.00, 2888.00),
    "CUDA1": (268.02, 800.05, 2656.09),
    "CUDA2": (256.02, 776.05, 2608.09),
    "CUDA3": (1006.00, 2012.00, 4024.00),
    "CUDA_Host": (32.03, 72.06, 176.13),
}
ctx_pts = [1024, 2048, 4096]
print(f"{'GPU':10s} {'a':>14s} {'b':>10s} {'c':>10s} {'pred@8192':>12s}")
for g, ys in fa0_buf.items():
    a, b, c = solve3(ctx_pts, ys)
    p8192 = a*8192**2 + b*8192 + c
    print(f"{g:10s} {a:14.6e} {b:10.4f} {c:10.2f} {p8192:12.1f}")
print("fa=0 ctx=8192 OOM 要求 (CUDA1 実測): 9536.19 MiB")

print("\n" + "="*70)
print("Phase N: fa=1 compute buffer の 4 点フィット (ctx=1024/2048/4096/8192)")
print("="*70)
# fa=1: Phase N 新規 + Phase L (ctx=4096 fa=1)
fa1_buf = {
    "CUDA0":    (975.00,  994.00, 1428.00, 2320.53),
    "CUDA1":    (230.03,  464.06,  944.13, 1952.25),
    "CUDA2":    (230.03,  464.06,  944.13, 1952.25),
    "CUDA3":   (1006.00, 2012.00, 4024.00, 8048.00),
    "CUDA_Host":(28.04,   64.08,  160.16,  448.31),
}
ctx_pts_fa1 = [1024, 2048, 4096, 8192]
print(f"{'GPU':10s} {'a':>14s} {'b':>10s} {'c':>10s}  resid(max) log-log k")
fa1_coefs = {}
for g, ys in fa1_buf.items():
    coef, resid = fit_quadratic_ls(ctx_pts_fa1, ys)
    a, b, c = coef
    fa1_coefs[g] = (a, b, c)
    maxabs = float(np.max(np.abs(resid)))
    k, _ = loglog_slope(ctx_pts_fa1, ys)
    print(f"{g:10s} {a:14.6e} {b:10.4f} {c:10.2f} {maxabs:8.2f}   {k:.4f}")

# 合計
print("\nfa=1 合計 compute buffer (4 点)")
totals = [sum(fa1_buf[g][i] for g in fa1_buf) for i in range(4)]
for c, t in zip(ctx_pts_fa1, totals):
    print(f"  ctx={c:5d}: {t:8.2f} MiB")
coef_tot, resid_tot = fit_quadratic_ls(ctx_pts_fa1, totals)
at, bt, ct = coef_tot
k_tot, _ = loglog_slope(ctx_pts_fa1, totals)
print(f"合計 4 点フィット: a={at:.4e}, b={bt:.4f}, c={ct:.2f}, log-log k={k_tot:.4f}")
print(f"  ctx=16384 外挿: quadratic={at*16384**2+bt*16384+ct:.0f}, power={(totals[0]*(16384/1024)**k_tot):.0f}")

print("\n" + "="*70)
print("fa=0 vs fa=1: 同 ctx での compute buffer 比")
print("="*70)
fa0_tot = [sum(fa0_buf[g][i] for g in fa0_buf) for i in range(3)]
print(f"{'ctx':>6s} {'fa=0':>10s} {'fa=1':>10s} {'ratio fa0/fa1':>14s}")
for i, c in enumerate(ctx_pts):
    print(f"{c:6d} {fa0_tot[i]:10.2f} {totals[i]:10.2f} {fa0_tot[i]/totals[i]:14.3f}")
print(f"ctx=8192 fa=0 予測 (3点厳密解 合計 外挿):")
s = 0
for g, ys in fa0_buf.items():
    a, b, c = solve3(ctx_pts, ys)
    s += a*8192**2 + b*8192 + c
print(f"  {s:.1f} MiB (破綻予測、非物理の場合あり)")
print(f"ctx=8192 fa=1 実測合計: {totals[3]:.1f} MiB")

