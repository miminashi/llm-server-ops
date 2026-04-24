#!/usr/bin/env python3
"""Phase S-boundary 3 点を Phase S 4p モデルと比較し、CUDA0 区分境界 ub* を確定する。

Phase S で確定した 2 軸モデル (R² >= 0.99999):
  CUDA1/2   = 520.26 + 3.903e-3*Δctx + 0.2538*Δub + 1.910e-6*Δctx*Δub
  CUDA3     = 0.9824 * ub
  CUDA_Host = 176.08 + 7.813e-3*Δctx + 0.0860*Δub + 3.815e-6*Δctx*Δub
  Δctx = ctx - 16384, Δub = ub - 2048

CUDA0 は区分モデル:
  ub <= 1024 平坦域: 966.50 + 0.0064*ub
  ub >= 2048 急増域: 6p 二次多項式 (R²=0.9918, max_err 236 MiB)

Phase S-boundary 3 点 (ctx=32768 × ub=1280/1536/1792) で境界 ub* を特定する。
"""

MEAS = [
    # (ub, CUDA0, CUDA1, CUDA2, CUDA3, CUDA_Host) MiB
    (1280, 976.25, 365.04, 365.04, 1257.50, 190.05),
    (1536, 979.50, 438.05, 438.05, 1509.00, 228.06),
    (1792, 1039.12, 511.05, 511.05, 1760.50, 266.07),
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
    # ub <= 1024 用の平坦域モデル (Phase S 提案)
    return 966.50 + 0.0064*ub


def cuda0_6p(ub):
    # ub >= 2048 用の 6 パラ二次多項式 (Phase S fit)
    dub = ub - 2048
    return 1116.34 + 4.996e-3*DCTX + 3.670e-8*DCTX**2 + 0.1115*dub + 6.016e-6*DCTX*dub + 9.104e-6*dub**2


def main():
    print(f"{'ub':>5} {'C0':>8} {'C0_flat':>8} {'dFlat':>8} {'C0_6p':>8} {'d6p':>8} | "
          f"{'C1':>8} {'pred':>8} {'dC1':>7} | {'C3':>8} {'pred':>8} {'dC3':>7} | "
          f"{'Host':>7} {'pred':>7} {'dH':>7}")
    print('-'*120)
    for ub, c0, c1, c2, c3, host in MEAS:
        pflat = cuda0_flat(ub)
        p6 = cuda0_6p(ub)
        pc12 = phaseS_cuda12(ub)
        pc3 = phaseS_cuda3(ub)
        phost = phaseS_host(ub)
        print(f"{ub:>5} {c0:>8.2f} {pflat:>8.2f} {c0-pflat:>+8.2f} {p6:>8.2f} {c0-p6:>+8.2f} | "
              f"{c1:>8.2f} {pc12:>8.2f} {c1-pc12:>+7.2f} | {c3:>8.2f} {pc3:>8.2f} {c3-pc3:>+7.3f} | "
              f"{host:>7.2f} {phost:>7.2f} {host-phost:>+7.2f}")

    print()
    print("判定:")
    for ub, c0, *_ in MEAS:
        status = "平坦域 (<=1000)" if c0 < 1000 else "急増域 (>=1000)"
        print(f"  ub={ub}: CUDA0={c0:.2f} -> {status}")
    print()
    print("境界 ub* ∈ (1536, 1792]")


if __name__ == '__main__':
    main()
