#!/usr/bin/env python3
"""Phase Sb-fine 4 点を Phase Sb 確定モデルと比較し、CUDA0 区分境界 ub* を 64-token 精度で特定する。

Phase Sb (ub=1280/1536/1792) で確定した状況:
  ub=1280: C0=976.25, 平坦域モデル +1.56 MiB (継続)
  ub=1536: C0=979.50, 平坦域モデル +3.17 MiB (継続)
  ub=1792: C0=1039.12, 平坦域モデル +61.15 MiB (境界突破済み)
  → ub* ∈ (1536, 1792]

Phase Sb 確定モデル (19 点検証済み):
  CUDA0 平坦域 (ub <= 1536): 966.50 + 0.0064*ub
  CUDA1/2   = 520.26 + 3.903e-3*Δctx + 0.2538*Δub + 1.910e-6*Δctx*Δub
  CUDA3     = 0.9824 * ub
  CUDA_Host = 176.08 + 7.813e-3*Δctx + 0.0860*Δub + 3.815e-6*Δctx*Δub
  Δctx = ctx - 16384, Δub = ub - 2048

本 Phase は ctx=32768 固定 × ub=1600/1664/1700/1750。
"""

# Phase Sb 参考値 + 本 Phase 実測値 (ub, CUDA0, CUDA1, CUDA2, CUDA3, CUDA_Host) MiB
# 本 Phase 計測後に実測値を差し込む（None をタプルに置き換え）
MEAS_SB = [
    (1280, 976.25, 365.04, 365.04, 1257.50, 190.05),
    (1536, 979.50, 438.05, 438.05, 1509.00, 228.06),
    (1792, 1039.12, 511.05, 511.05, 1760.50, 266.07),
]

# 本 Phase 実測値 (compute_buffer_summary.txt から抽出)
MEAS_SBF = [
    (1600,  984.35, 456.30, 456.30, 1571.88, 237.56),
    (1664, 1002.61, 474.55, 474.55, 1634.75, 247.06),
    (1700, 1012.88, 484.82, 484.82, 1670.12, 252.41),
    (1750, 1027.14, 499.08, 499.08, 1719.24, 259.83),
]

CTX = 32768
DCTX = CTX - 16384


def phaseS_cuda12(ub):
    dub = ub - 2048
    return 520.26 + 3.903e-3*DCTX + 0.2538*dub + 1.910e-6*DCTX*dub


def phaseS_host(ub):
    dub = ub - 2048
    return 176.08 + 7.813e-3*DCTX + 0.0860*dub + 3.815e-6*DCTX*dub


def phaseS_cuda3(ub):
    return 0.9824 * ub


def cuda0_flat(ub):
    return 966.50 + 0.0064*ub


def cuda0_6p(ub):
    dub = ub - 2048
    return 1116.34 + 4.996e-3*DCTX + 3.670e-8*DCTX**2 + 0.1115*dub + 6.016e-6*DCTX*dub + 9.104e-6*dub**2


# 本 Phase で発見した ub >= 1600 の線形モデル (4 点 fit、anchor=ub=1664)
def cuda0_linear_high(ub):
    return 1002.61 + 0.2853*(ub - 1664)


def classify(c0, pflat, plin):
    """平坦域モデルと ub>=1600 線形モデルのどちらに近いか判定"""
    d_flat = c0 - pflat
    d_lin = c0 - plin
    if abs(d_flat) < 5 and abs(d_lin) > 10:
        return "平坦域"
    if abs(d_lin) < 0.5 and abs(d_flat) > 5:
        return "線形域"
    return "境界付近"


def main():
    all_pts = sorted(MEAS_SB + MEAS_SBF)
    print(f"ctx={CTX} 系列 CUDA0 / CUDA1/2 / CUDA3 / CUDA_Host の Phase Sb モデル残差")
    print(f"{'ub':>5} {'C0':>8} {'C0_flat':>8} {'dFlat':>8} {'C0_lin':>8} {'dLin':>7} "
          f"{'ΔC0':>8} {'判定':<10} | {'C1':>8} {'pred':>8} {'dC1':>7} | "
          f"{'C3':>8} {'pred':>8} {'dC3':>7} | {'Host':>7} {'pred':>7} {'dH':>6}")
    print('-'*160)
    prev_c0 = None
    prev_ub = None
    for rec in all_pts:
        ub, c0, c1, c2, c3, host = rec
        pflat = cuda0_flat(ub)
        plin = cuda0_linear_high(ub)
        pc12 = phaseS_cuda12(ub)
        pc3 = phaseS_cuda3(ub)
        phost = phaseS_host(ub)
        dc0 = (c0 - prev_c0) if prev_c0 is not None else 0.0
        cls = classify(c0, pflat, plin)
        print(f"{ub:>5} {c0:>8.2f} {pflat:>8.2f} {c0-pflat:>+8.2f} {plin:>8.2f} {c0-plin:>+7.2f} "
              f"{dc0:>+8.2f} {cls:<10} | {c1:>8.2f} {pc12:>8.2f} {c1-pc12:>+7.2f} | "
              f"{c3:>8.2f} {pc3:>8.2f} {c3-pc3:>+7.3f} | "
              f"{host:>7.2f} {phost:>7.2f} {host-phost:>+6.2f}")
        prev_c0 = c0
        prev_ub = ub

    # 境界 ub* の最終確定
    print()
    print("境界 ub* 判定 (ub >= 1600 線形モデル `C0 = 1002.61 + 0.2853·(ub-1664)` との一致):")
    last_off_ub = None
    first_on_ub = None
    for rec in all_pts:
        ub, c0, *_ = rec
        plin = cuda0_linear_high(ub)
        on_linear = abs(c0 - plin) < 0.5
        if on_linear and first_on_ub is None:
            first_on_ub = ub
        if not on_linear:
            last_off_ub = ub
        print(f"  ub={ub}: C0_lin={plin:.2f}, 実測={c0:.2f}, Δ={c0-plin:+.2f}, "
              f"線形モデル上={on_linear}")

    if last_off_ub is not None and first_on_ub is not None:
        print(f"\n  境界 ub* ∈ ({last_off_ub}, {first_on_ub}]  "
              f"(精度: {first_on_ub - last_off_ub} token)")

    # Phase Sb モデル残差サマリ (本 Phase 新 4 点)
    print()
    print("Phase Sb 確定モデルの本 Phase 新 4 点残差:")
    max_dc12 = max(abs(c1 - phaseS_cuda12(ub)) for ub, _, c1, _, _, _ in MEAS_SBF)
    max_dc3 = max(abs(c3 - phaseS_cuda3(ub)) for ub, _, _, _, c3, _ in MEAS_SBF)
    max_dh = max(abs(host - phaseS_host(ub)) for ub, _, _, _, _, host in MEAS_SBF)
    print(f"  CUDA1/2 max_err: {max_dc12:.3f} MiB")
    print(f"  CUDA3  max_err: {max_dc3:.3f} MiB")
    print(f"  Host   max_err: {max_dh:.3f} MiB")

    # ub >= 1600 での線形モデル max_err (本 Phase 4 点 + Phase Sb の ub=1792/2048)
    ub_high_pts = [(ub, c0) for ub, c0, *_ in MEAS_SBF if ub >= 1600]
    ub_high_pts += [(1792, 1039.12), (2048, 1112.13)]
    max_dlin = max(abs(c0 - cuda0_linear_high(ub)) for ub, c0 in ub_high_pts)
    print(f"\n  ub >= 1600 線形モデル max_err (4 点 + Phase Sb の 1792/2048): {max_dlin:.3f} MiB")
    for ub, c0 in sorted(ub_high_pts):
        plin = cuda0_linear_high(ub)
        print(f"    ub={ub}: 実測 {c0:.2f}, 予測 {plin:.2f}, Δ={c0-plin:+.3f}")


if __name__ == '__main__':
    main()
