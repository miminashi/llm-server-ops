#!/usr/bin/env python3
"""Phase P: fa=1 ctx=16384 固定で -b バッチサイズを振った compute buffer の頭打ち検証

目的:
  Phase O で提案した n_eff = min(ctx, -b) 区分モデルが、-b を 2048 / 4096 / 8192 と
  変化させた時に CUDA3 の compute buffer が予測通り min(ctx, -b) × 0.9824 に比例するかを確認。

データ:
  実測は各起動ログ (startup_logs/fa1_ctx16384_b{BS}_ub{UB}.log) から
  compute_buffer_summary.txt 経由で採取した sched_reserve 値。

Phase P 条件:
  P1: -b=2048  -ub=2048  期待 CUDA3 =  2012 MiB = 2048  × 0.9824
  P2: -b=4096  -ub=4096  期待 CUDA3 =  4024 MiB = 4096  × 0.9824
  P3: -b=8192  -ub=8192  期待 CUDA3 =  8048 MiB = 8192  × 0.9824 (Phase O ベースライン)
  P4: -b=8192  -ub=4096  期待 CUDA3 =  8048 MiB (-b=8192 支配なら P3 と同値)

Phase O 値（比較用、同一条件 P3 相当）:
  CUDA0=2784.00, CUDA1/2=2080.25, CUDA3=8048.00, CUDA_Host=704.31

Phase N 4pt フィット係数（fa=1、ctx=1024..8192 で採取、ctx を n_eff で置換して適用）:
  CUDA0:    1.10e-5 · n² + 0.093 · n + 828.09   (近似、Phase O で残差 463 MiB)
  CUDA1/2:  1.91e-6 · n² + 0.2227 · n
  CUDA3:    0.9824 · n
  CUDA_Host:3.81e-6 · n² + 0.0235 · n           (Phase O で残差 256 MiB)
"""
import sys
from pathlib import Path

# ========================================
# 実測データ（compute_buffer_summary.txt から手動転記 or 後で自動化）
# 初期は空 dict、測定後に埋める
# 値の形式: (CUDA0, CUDA1, CUDA2, CUDA3, CUDA_Host)
# ========================================
# 本ファイルは計測完了後に実データで上書きされる
# 以下は期待値（頭打ちモデルによる予測）のプレースホルダ
cond = {
    # (b, ub):  measured compute buffer tuple
    # 計測後に埋める:
    # (2048, 2048): (...),
    # (4096, 4096): (...),
    # (8192, 8192): (...),
    # (8192, 4096): (...),
}

# Phase O ベースライン (P3 相当、ctx=16384 -b=8192 -ub=8192)
PHASE_O_B8192 = (2784.00, 2080.25, 2080.25, 8048.00, 704.31)

GPU_NAMES = ("CUDA0", "CUDA1", "CUDA2", "CUDA3", "CUDA_Host")
CTX = 16384


def parse_sched_reserve(log_path: Path) -> tuple:
    """起動ログから sched_reserve: の compute buffer 値を抽出"""
    vals = {g: None for g in GPU_NAMES}
    if not log_path.exists():
        return tuple(vals[g] for g in GPU_NAMES)
    with log_path.open() as f:
        for line in f:
            # "sched_reserve:      CUDA0 compute buffer size =  2784.00 MiB"
            if "sched_reserve:" not in line or "compute buffer size" not in line:
                continue
            for g in GPU_NAMES:
                if f" {g} " in line:
                    try:
                        size = line.split("=")[-1].strip().split()[0]
                        vals[g] = float(size)
                    except (IndexError, ValueError):
                        pass
                    break
    return tuple(vals[g] for g in GPU_NAMES)


def n_eff(ctx: int, b: int, ub: int = None) -> int:
    """
    Phase P の発見: 真のドライバは -ub（unified batch size）、-b ではない。
    P4 (b=8192 ub=4096) が P2 (b=4096 ub=4096) と compute buffer 完全一致したため、
    n_eff = min(ctx, ub) を採用（ub を渡さない場合は従来の b で互換）
    """
    effective = ub if ub is not None else b
    return min(ctx, effective)


def predict_cuda3(n):
    return 0.9824 * n


def predict_cuda12(n):
    return 1.91e-6 * n * n + 0.2227 * n


def predict_cuda_host(n):
    return 3.81e-6 * n * n + 0.0235 * n


def predict_cuda0(n):
    return 1.10e-5 * n * n + 0.093 * n + 828.09


def main():
    # startup_logs/ から実測値を自動ロード
    script_dir = Path(__file__).parent
    logs_dir = script_dir / "startup_logs"
    measured = {}
    for cfg in [(2048, 2048), (4096, 4096), (8192, 8192), (8192, 4096)]:
        b, ub = cfg
        log = logs_dir / f"fa1_ctx{CTX}_b{b}_ub{ub}.log"
        vals = parse_sched_reserve(log)
        if all(v is not None for v in vals):
            measured[cfg] = vals
        else:
            print(f"[warn] log not parsable: {log}", file=sys.stderr)

    if not measured:
        print("No measured data available. Run measurements first.")
        return

    print("=" * 90)
    print("Phase P: fa=1 ctx=16384 固定での -b 感度スキャン (sched_reserve 実測 MiB)")
    print("=" * 90)
    print(f"{'cond':>18s}  {'CUDA0':>10s} {'CUDA1':>10s} {'CUDA2':>10s} {'CUDA3':>10s} {'CUDA_Host':>10s} {'合計':>10s}")
    for cfg, vals in measured.items():
        b, ub = cfg
        total = sum(vals)
        print(f"  b={b:5d} ub={ub:5d}  " + "".join(f"{v:10.2f} " for v in vals) + f"{total:10.2f}")

    print()
    print("=" * 90)
    print("CUDA3 頭打ちモデル検証: CUDA3 ≈ min(ctx=16384, -b) × 0.9824")
    print("=" * 90)
    print(f"{'cond':>18s}  {'n_eff':>6s} {'予測':>10s} {'実測':>10s} {'誤差 MiB':>10s} {'誤差 %':>10s}")
    for cfg, vals in measured.items():
        b, ub = cfg
        n = n_eff(CTX, b, ub)
        pred = predict_cuda3(n)
        obs = vals[3]  # CUDA3
        err = obs - pred
        pct = (err / pred) * 100 if pred else 0.0
        print(f"  b={b:5d} ub={ub:5d}  {n:6d} {pred:10.2f} {obs:10.2f} {err:+10.2f} {pct:+9.3f}%")

    print()
    print("=" * 90)
    print("CUDA1/2 モデル検証: Phase N 係数 (1.91e-6·n_eff² + 0.2227·n_eff)")
    print("=" * 90)
    print(f"{'cond':>18s}  {'n_eff':>6s} {'予測':>10s} {'実測':>10s} {'誤差 MiB':>10s} {'誤差 %':>10s}")
    for cfg, vals in measured.items():
        b, ub = cfg
        n = n_eff(CTX, b, ub)
        pred = predict_cuda12(n)
        obs = vals[1]  # CUDA1 (CUDA2 と同値のはず)
        err = obs - pred
        pct = (err / pred) * 100 if pred else 0.0
        print(f"  b={b:5d} ub={ub:5d}  {n:6d} {pred:10.2f} {obs:10.2f} {err:+10.2f} {pct:+9.3f}%")

    print()
    print("=" * 90)
    print("CUDA_Host モデル検証: Phase N 係数 (3.81e-6·n_eff² + 0.0235·n_eff)")
    print("=" * 90)
    print(f"{'cond':>18s}  {'n_eff':>6s} {'予測':>10s} {'実測':>10s} {'誤差 MiB':>10s} {'誤差 %':>10s}")
    for cfg, vals in measured.items():
        b, ub = cfg
        n = n_eff(CTX, b, ub)
        pred = predict_cuda_host(n)
        obs = vals[4]
        err = obs - pred
        pct = (err / pred) * 100 if pred else 0.0
        print(f"  b={b:5d} ub={ub:5d}  {n:6d} {pred:10.2f} {obs:10.2f} {err:+10.2f} {pct:+9.3f}%")

    print()
    print("=" * 90)
    print("CUDA0 モデル検証 (参考): Phase N 係数 (1.10e-5·n_eff² + 0.093·n_eff + 828.09)")
    print("=" * 90)
    print(f"{'cond':>18s}  {'n_eff':>6s} {'予測':>10s} {'実測':>10s} {'誤差 MiB':>10s} {'誤差 %':>10s}")
    for cfg, vals in measured.items():
        b, ub = cfg
        n = n_eff(CTX, b, ub)
        pred = predict_cuda0(n)
        obs = vals[0]
        err = obs - pred
        pct = (err / pred) * 100 if pred else 0.0
        print(f"  b={b:5d} ub={ub:5d}  {n:6d} {pred:10.2f} {obs:10.2f} {err:+10.2f} {pct:+9.3f}%")

    # P3 vs Phase O 再現性
    if (8192, 8192) in measured:
        print()
        print("=" * 90)
        print("P3 (b=8192 ub=8192) vs Phase O ベースラインの再現性")
        print("=" * 90)
        p3 = measured[(8192, 8192)]
        print(f"{'GPU':10s} {'Phase O':>12s} {'Phase P':>12s} {'差':>10s}")
        for i, g in enumerate(GPU_NAMES):
            diff = p3[i] - PHASE_O_B8192[i]
            print(f"{g:10s} {PHASE_O_B8192[i]:12.2f} {p3[i]:12.2f} {diff:+10.2f}")

    # P3 vs P4 (-ub 単独効果)
    if (8192, 8192) in measured and (8192, 4096) in measured:
        print()
        print("=" * 90)
        print("P3 (ub=8192) vs P4 (ub=4096) の -ub 単独効果 (-b=8192 固定)")
        print("=" * 90)
        p3 = measured[(8192, 8192)]
        p4 = measured[(8192, 4096)]
        print(f"{'GPU':10s} {'ub=8192':>12s} {'ub=4096':>12s} {'差':>10s}")
        for i, g in enumerate(GPU_NAMES):
            diff = p4[i] - p3[i]
            print(f"{g:10s} {p3[i]:12.2f} {p4[i]:12.2f} {diff:+10.2f}")

    # log-log 傾き確認 (P1, P2, P3)
    print()
    print("=" * 90)
    print("CUDA3 log-log 傾き (P1 → P2 → P3 の b 倍増に対する比)")
    print("=" * 90)
    import math
    seq = [(2048, 2048), (4096, 4096), (8192, 8192)]
    if all(c in measured for c in seq):
        for i in range(1, len(seq)):
            b_prev, _ = seq[i - 1]
            b_cur, _ = seq[i]
            v_prev = measured[seq[i - 1]][3]
            v_cur = measured[seq[i]][3]
            slope = math.log(v_cur / v_prev) / math.log(b_cur / b_prev)
            print(f"  b={b_prev}→{b_cur}: CUDA3 {v_prev:.2f}→{v_cur:.2f}, log-log 傾き={slope:.4f}")


if __name__ == "__main__":
    main()
