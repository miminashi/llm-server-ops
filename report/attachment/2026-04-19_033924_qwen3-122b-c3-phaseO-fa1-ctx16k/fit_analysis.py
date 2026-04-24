#!/usr/bin/env python3
"""Phase O compute buffer 分析
Phase N の fa=1 4 点 (ctx=1024/2048/4096/8192) に Phase O で採取した
ctx=16384 のデータを加えた 5 点フィットを実施し、CUDA0 の非線形性の
改善を検証する。

Phase N の fa=1 4 点フィット結果（参照値、比較用）:
  CUDA0:    a=1.10e-5, b=0.093,  c=828.09,  max resid=70.4
  CUDA1/2:  a=1.91e-6, b=0.2227, c~0,       max resid=0.00, log-log k=1.028
  CUDA3:    a=0,       b=0.9824, c=0,       max resid=0.00, log-log k=1.000
  CUDA_Host:a=3.81e-6, b=0.0235, c~0,       max resid=0.00, log-log k=1.332
"""
import numpy as np


def fit_quadratic_ls(xs, ys):
    A = np.array([[x * x, x, 1] for x in xs], dtype=float)
    b = np.array(ys, dtype=float)
    coef, *_ = np.linalg.lstsq(A, b, rcond=None)
    pred = A @ coef
    resid = b - pred
    return coef, resid, pred


def loglog_slope(xs, ys):
    lx = np.log(xs)
    ly = np.log(ys)
    k = np.polyfit(lx, ly, 1)
    return k


# Phase N + Phase O の fa=1 sched_reserve 値 (MiB)
# ctx=1024/2048/4096 は Phase N と Phase L の値 (fa=1 4 点フィットと同じ)
# ctx=8192 は Phase N で採取
# ctx=16384 は Phase O で採取（本レポート）
ctx_pts = [1024, 2048, 4096, 8192, 16384]

fa1_buf = {
    "CUDA0":    (975.00,  994.00, 1428.00, 2320.53, 2784.00),
    "CUDA1":    (230.03,  464.06,  944.13, 1952.25, 2080.25),
    "CUDA2":    (230.03,  464.06,  944.13, 1952.25, 2080.25),
    "CUDA3":   (1006.00, 2012.00, 4024.00, 8048.00, 8048.00),
    "CUDA_Host":(28.04,   64.08,  160.16,  448.31,  704.31),
}

# Phase N の 4 点データ (ctx=1024/2048/4096/8192)
fa1_buf_4pt = {k: v[:4] for k, v in fa1_buf.items()}
ctx_pts_4 = ctx_pts[:4]

print("=" * 80)
print("Phase O: fa=1 compute buffer 5 点フィット (ctx=1024/2048/4096/8192/16384)")
print("=" * 80)

print(f"{'GPU':10s} {'a':>14s} {'b':>10s} {'c':>10s}  resid(max)  resid@16384  k")
fa1_coefs = {}
for g, ys in fa1_buf.items():
    coef, resid, pred = fit_quadratic_ls(ctx_pts, ys)
    a, b, c = coef
    fa1_coefs[g] = (a, b, c)
    maxabs = float(np.max(np.abs(resid)))
    k, _ = loglog_slope(ctx_pts, ys)
    resid_16k = float(resid[-1])
    print(f"{g:10s} {a:14.6e} {b:10.4f} {c:10.2f} {maxabs:10.2f} {resid_16k:12.2f} {k:7.4f}")

print()
print("=" * 80)
print("Phase N 再現: 4 点フィット (ctx=1024..8192) と Phase O ctx=16384 との差分")
print("=" * 80)
print(f"{'GPU':10s} {'4pt_a':>14s} {'4pt_b':>10s} {'4pt_c':>10s}  4pt_resid  pred@16k  obs@16k  err@16k")
for g in fa1_buf.keys():
    ys4 = fa1_buf_4pt[g]
    ys_obs_16k = fa1_buf[g][-1]
    coef4, resid4, _ = fit_quadratic_ls(ctx_pts_4, ys4)
    a4, b4, c4 = coef4
    pred16k = a4 * 16384 ** 2 + b4 * 16384 + c4
    err = pred16k - ys_obs_16k
    maxabs4 = float(np.max(np.abs(resid4)))
    print(f"{g:10s} {a4:14.6e} {b4:10.4f} {c4:10.2f} {maxabs4:10.2f} {pred16k:9.1f} {ys_obs_16k:8.1f} {err:+8.1f}")

print()
print("=" * 80)
print("CUDA3 の頭打ち現象の検証（線形仮説 b=0.9824 の破綻）")
print("=" * 80)
# CUDA3 について、線形仮説 (ctx=8192 まで) と 5 点フィット
cuda3_ys = fa1_buf["CUDA3"]
print(f"ctx=1024-8192 での CUDA3 線形係数 b = (ys[-1] - ys[0]) / (ctx[-1] - ctx[0])")
print(f"  観測: ctx=1024: {cuda3_ys[0]}, ctx=8192: {cuda3_ys[3]}, ctx=16384: {cuda3_ys[4]}")
print(f"  線形仮説 (b=0.9824) での ctx=16384 予測: {0.9824 * 16384:.2f} MiB")
print(f"  実測: {cuda3_ys[4]} MiB")
print(f"  差分: {cuda3_ys[4] - 0.9824 * 16384:+.2f} MiB (ctx=8192 と同値で頭打ち)")

# -b 8192 が上限か検証
print()
print("推定: CUDA3 の compute buffer は `max(ctx, -b=8192) * 0.9824` に相当する可能性")
print("       つまり ctx≥8192 では -b=8192 が支配因子となり頭打ち")

print()
print("=" * 80)
print("合計 compute buffer の推移と外挿比較")
print("=" * 80)
totals = [sum(fa1_buf[g][i] for g in fa1_buf) for i in range(len(ctx_pts))]
for c, t in zip(ctx_pts, totals):
    print(f"  ctx={c:5d}: {t:9.2f} MiB")
coef_tot, resid_tot, _ = fit_quadratic_ls(ctx_pts, totals)
at, bt, ct = coef_tot
k_tot, _ = loglog_slope(ctx_pts, totals)
print(f"合計 5 点フィット: a={at:.4e}, b={bt:.4f}, c={ct:.2f}, log-log k={k_tot:.4f}")
print(f"  max resid: {float(np.max(np.abs(resid_tot))):.2f} MiB")

print()
print("=" * 80)
print("eval 速度の再現性比較 (Phase K vs Phase O, ctx=16384)")
print("=" * 80)
print("  Phase K (2026-04-18): 15.046 t/s (単一 warmup 採取)")
print("  Phase O (2026-04-19): 中央値 15.011 t/s (warmup 3 run: 14.990/15.020/15.011)")
print("  差分: -0.035 t/s (-0.23%) — 実質同一（1 run 間 range 0.030 t/s 内）")
