#!/usr/bin/env python3
"""Phase Sb-fine3 4 点を Phase Sb/Sb-fine/Sb-fine2 確定モデルと比較し、CUDA0 区分境界 ub* を 1-4 token 精度で特定する。

Phase Sb-fine2 で確定した状況:
  ub=1584: C0=980.11, 平坦域モデル +3.47 MiB (平坦域最後)
  ub=1600: C0=984.35, 平坦域モデル +7.61 MiB, 線形モデル ±0.00 MiB (境界突破直後、線形域)
  → ub* ∈ (1584, 1600] の 16-token 区間に確定

Phase Sb-fine2 で ub=1584 → 1600 の Δ=+4.24 MiB を解釈:
  - 仮に ub*=1585 とすると、平坦 1 token + 線形 15 token = 0.013 + 4.280 = 4.293 MiB → 実測 4.24 と 1.2% 差
  - 仮に ub*=1586 とすると、平坦 2 token + 線形 14 token = 0.026 + 3.994 = 4.020 MiB → 実測 4.24 と 5.2% 差
  - 仮に ub*=1588 とすると、平坦 4 token + 線形 12 token = 0.050 + 3.424 = 3.474 MiB → 実測 4.24 と 18% 差
  → ub*=1585 付近の可能性大（≈ 1585-1586）

Phase Sb-fine 確定モデル:
  CUDA0 平坦域 (ub <= 1584): 966.50 + 0.0064*ub
  CUDA0 線形域 (ub >= 1600, ctx=32k): 1002.61 + 0.2853*(ub-1664)
  CUDA1/2   = 520.26 + 3.903e-3*Δctx + 0.2538*Δub + 1.910e-6*Δctx*Δub
  CUDA3     = 0.9824 * ub
  CUDA_Host = 176.08 + 7.813e-3*Δctx + 0.0860*Δub + 3.815e-6*Δctx*Δub
  Δctx = ctx - 16384, Δub = ub - 2048

本 Phase は ctx=32768 固定 × ub=1585/1586/1588/1592。
目的: ub* を (1584, 1600] 内で 1-4 token 精度に絞り込む。
     ub* が平坦域最後の点の +1 または +2 トークンに位置する場合、ub=1585/1586 のどちらかで線形域にジャンプする。
"""

# Phase Sb 既測値 (ub, CUDA0, CUDA1, CUDA2, CUDA3, CUDA_Host) MiB
MEAS_SB = [
    (1280, 976.25, 365.04, 365.04, 1257.50, 190.05),
    (1536, 979.50, 438.05, 438.05, 1509.00, 228.06),
    (1792, 1039.12, 511.05, 511.05, 1760.50, 266.07),
]

# Phase Sb-fine 既測値
MEAS_SBF_REF = [
    (1664, 1002.61, 474.55, 474.55, 1634.75, 247.06),
    (1700, 1012.88, 484.82, 484.82, 1670.12, 252.41),
    (1750, 1027.14, 499.08, 499.08, 1719.24, 259.83),
]

# Phase Sb-fine2 既測値 (参照用、ub=1584/1600 が境界の両端点)
MEAS_SBF2_REF = [
    (1552, 979.70, 442.61, 442.61, 1524.72, 230.43),
    (1568, 979.91, 447.17, 447.17, 1540.44, 232.81),
    (1584, 980.11, 451.74, 451.74, 1556.16, 235.19),
    (1600, 984.35, 456.30, 456.30, 1571.88, 237.56),
]

# 本 Phase Sb-fine3 実測値 (compute_buffer_summary.txt から抽出)
MEAS_SBF3 = [
    (1585, 980.12, 452.02, 452.02, 1557.14, 235.33),
    (1586, 980.36, 452.31, 452.31, 1558.12, 235.48),
    (1588, 980.93, 452.88, 452.88, 1560.09, 235.78),
    (1592, 982.07, 454.02, 454.02, 1564.02, 236.37),
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
    if not MEAS_SBF3:
        print("MEAS_SBF3 が空です。計測後に実測値を書き込んでください。")
        return

    all_pts = sorted(MEAS_SB + MEAS_SBF_REF + MEAS_SBF2_REF + MEAS_SBF3)
    print(f"ctx={CTX} 系列 CUDA0 / CUDA1/2 / CUDA3 / CUDA_Host の Phase Sb/Sb-fine/Sb-fine2 モデル残差")
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

    # 境界 ub* の最終確定 (1-4 token 精度)
    print()
    print("境界 ub* 判定 (ΔC0 が 0.025 MiB 未満=平坦域継続、1 MiB 以上=線形域到達で判定):")
    FLAT_STEP_MAX = 0.025  # 平坦域 slope 0.0125 × 2 token を許容
    LINEAR_JUMP_MIN = 1.0  # 境界突破後の ジャンプは 16-token で 4.24 MiB → 1-token で 0.285 MiB 以上
    last_flat_ub = None
    first_linear_ub = None
    prev_c0 = None
    prev_ub = None
    for rec in all_pts:
        ub, c0, *_ = rec
        pflat = cuda0_flat(ub)
        plin = cuda0_linear_high(ub)
        if prev_c0 is not None:
            dc0 = c0 - prev_c0
            dub = ub - prev_ub
            slope = dc0 / dub if dub > 0 else 0
            # 判定基準: slope < 0.05 → 平坦、slope > 0.15 → 線形
            if slope < 0.05:
                cls = "平坦域継続"
                last_flat_ub = ub
            elif slope > 0.15:
                cls = "線形域到達"
                if first_linear_ub is None:
                    first_linear_ub = ub
            else:
                cls = "境界遷移中"
            print(f"  ub={prev_ub}→{ub} ({dub:+d}t): C0 {prev_c0:.2f}→{c0:.2f} ({dc0:+.3f} MiB, slope {slope:+.4f} MiB/t) → {cls}")
        prev_c0 = c0
        prev_ub = ub

    if last_flat_ub is not None and first_linear_ub is not None:
        print(f"\n  境界 ub* ∈ ({last_flat_ub}, {first_linear_ub}]  "
              f"(精度: {first_linear_ub - last_flat_ub} token)")

    # Phase Sb モデル残差サマリ (本 Phase 新 4 点)
    print()
    print("Phase Sb 確定モデルの本 Phase Sb-fine3 新 4 点残差:")
    max_dc12 = max(abs(c1 - phaseS_cuda12(ub)) for ub, _, c1, _, _, _ in MEAS_SBF3)
    max_dc3 = max(abs(c3 - phaseS_cuda3(ub)) for ub, _, _, _, c3, _ in MEAS_SBF3)
    max_dh = max(abs(host - phaseS_host(ub)) for ub, _, _, _, _, host in MEAS_SBF3)
    print(f"  CUDA1/2 max_err: {max_dc12:.3f} MiB")
    print(f"  CUDA3  max_err: {max_dc3:.3f} MiB")
    print(f"  Host   max_err: {max_dh:.3f} MiB")

    # ub ≥ boundary の新しい線形モデル確認 (境界越えた後の点)
    print()
    print("ub >= 1600 線形モデル max_err (Sb-fine 3 + Sb-fine2 の 1600 + 本 Phase 境界越え点 + Sb の 1792):")
    ub_high_pts = [(ub, c0) for ub, c0, *_ in MEAS_SBF_REF if ub >= 1600]
    ub_high_pts += [(1600, 984.35), (1792, 1039.12)]
    ub_high_pts += [(ub, c0) for ub, c0, *_ in MEAS_SBF3 if c0 > 984.0]  # 境界越えた点のみ
    max_dlin = max(abs(c0 - cuda0_linear_high(ub)) for ub, c0 in ub_high_pts)
    print(f"  max_err: {max_dlin:.3f} MiB")
    for ub, c0 in sorted(set(ub_high_pts)):
        plin = cuda0_linear_high(ub)
        print(f"    ub={ub}: 実測 {c0:.2f}, 予測 {plin:.2f}, Δ={c0-plin:+.3f}")

    # 境界 ub* の推定値 (ΔC0 = α·(平坦残り token) + β·(線形 token) から逆算)
    print()
    print("境界 ub* の推定 (ub=1584→各点 ΔC0 を平坦+線形モデルで分解):")
    BASE_UB = 1584
    BASE_C0 = 980.11
    FLAT_SLOPE = 0.0125  # MiB/token
    LINEAR_SLOPE = 0.2853  # MiB/token
    for ub, c0, *_ in MEAS_SBF3:
        dub = ub - BASE_UB
        dc0 = c0 - BASE_C0
        # ub* = BASE_UB + x とすると: 平坦 x token + 線形 (dub-x) token
        # dc0 = FLAT_SLOPE*x + LINEAR_SLOPE*(dub-x)
        # → x = (LINEAR_SLOPE*dub - dc0) / (LINEAR_SLOPE - FLAT_SLOPE)
        if LINEAR_SLOPE - FLAT_SLOPE > 0:
            x = (LINEAR_SLOPE*dub - dc0) / (LINEAR_SLOPE - FLAT_SLOPE)
            ub_star = BASE_UB + x
            print(f"  ub={ub}: ΔC0={dc0:+.3f} MiB, 平坦寄与 x={x:.2f} token → ub* ≈ {ub_star:.2f}")


if __name__ == '__main__':
    main()
