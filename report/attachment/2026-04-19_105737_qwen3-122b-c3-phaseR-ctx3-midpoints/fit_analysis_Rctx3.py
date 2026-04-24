#!/usr/bin/env python3
"""Phase R-ctx3: 中間 ctx (32768/65536) を加えた 4 点線形フィット

目的:
  Phase Q (ctx=16384) と Phase R (ctx=131072) の 2 点から仮設した線形モデル
    CUDA0     = 951 + 0.077*ub + 0.00987*Δctx
    CUDA1/2   = 0.254*ub + 0.00391*Δctx
    CUDA3     = 0.9824*ub                    (ctx 完全不依存)
    CUDA_Host = 0.086*ub + 0.00781*Δctx
  を、ctx=32768 / 65536 の中間点 2 点で検証し、4 点最小二乗で係数を再推定する。
  成功条件:
    - CUDA0/1/2/Host: R² ≥ 0.99、2 点モデルの予測誤差 ≤ 5%
    - CUDA3: 4 点すべて 2012.0 ± 0.5 MiB（ctx 完全不依存の再確認）
    - KV buffer: ctx 完全比例（3072 × ctx/131072 MiB）
"""
import statistics
import sys
from pathlib import Path

GPU_NAMES = ("CUDA0", "CUDA1", "CUDA2", "CUDA3", "CUDA_Host")

# Phase Q P1 (ctx=16384, ub=2048) 実測 — Phase R 報告書より
REF_CTX_16K = {
    "CUDA0":     1048.13,
    "CUDA1":     520.06,
    "CUDA2":     520.06,
    "CUDA3":     2012.00,
    "CUDA_Host": 176.08,
}

# Phase R R1 (ctx=131072, ub=2048) 実測 — Phase R 報告書より
REF_CTX_131K = {
    "CUDA0":     2180.00,
    "CUDA1":     968.06,
    "CUDA2":     968.06,
    "CUDA3":     2012.00,
    "CUDA_Host": 1072.08,
}

# Phase R 2 点モデル（本 Phase で検証対象）
# measured = ub_const + ub_slope * ub + ctx_slope * Δctx,  Δctx = ctx - 16384
TWO_POINT_MODEL = {
    "CUDA0":     {"ub_const": 951.0,  "ub_slope": 0.077,  "ctx_slope": 0.00987},
    "CUDA1":     {"ub_const": 0.0,    "ub_slope": 0.254,  "ctx_slope": 0.00391},
    "CUDA2":     {"ub_const": 0.0,    "ub_slope": 0.254,  "ctx_slope": 0.00391},
    "CUDA3":     {"ub_const": 0.0,    "ub_slope": 0.9824, "ctx_slope": 0.0},
    "CUDA_Host": {"ub_const": 0.0,    "ub_slope": 0.086,  "ctx_slope": 0.00781},
}

UB = 2048  # Phase R-ctx3 は ub=2048 固定


def parse_sched_reserve(log_path: Path):
    vals = {g: None for g in GPU_NAMES}
    if not log_path.exists():
        return vals
    with log_path.open() as f:
        for line in f:
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
    return vals


def parse_kv_buffer(log_path: Path):
    kv = {g: None for g in GPU_NAMES}
    if not log_path.exists():
        return kv
    with log_path.open() as f:
        for line in f:
            if "KV buffer size" not in line:
                continue
            for g in GPU_NAMES:
                if f"{g} KV buffer" in line or f"{g}  KV buffer" in line:
                    try:
                        size = line.split("=")[-1].strip().split()[0]
                        kv[g] = float(size)
                    except (IndexError, ValueError):
                        pass
                    break
    return kv


def parse_graph_info(log_path: Path):
    nodes = splits_main = splits_main_bs = splits_bs1 = None
    if not log_path.exists():
        return (nodes, splits_main, splits_main_bs, splits_bs1)
    with log_path.open() as f:
        for line in f:
            if "graph nodes" in line:
                try:
                    nodes = int(line.split("=")[-1].strip())
                except ValueError:
                    pass
            if "graph splits" in line:
                try:
                    parts = line.split("=", 1)[-1].strip()
                    chunks = [c.strip() for c in parts.split(",")]
                    if chunks:
                        first = chunks[0]
                        splits_main = int(first.split("(")[0].strip())
                        if "(with bs=" in first:
                            splits_main_bs = int(first.split("(with bs=")[-1].rstrip(")"))
                        if len(chunks) >= 2:
                            second = chunks[1]
                            splits_bs1 = int(second.split("(")[0].strip())
                except (ValueError, IndexError):
                    pass
    return (nodes, splits_main, splits_main_bs, splits_bs1)


def lstsq(xs, ys):
    """最小二乗: y = a + b*x を返す ((a, b), r2)"""
    n = len(xs)
    if n < 2:
        return (None, None), None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return (my, 0.0), 1.0
    b = num / den
    a = my - b * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot != 0 else 1.0
    return (a, b), r2


def predict_two_point(gpu, ctx, ub):
    m = TWO_POINT_MODEL[gpu]
    dctx = ctx - 16384
    return m["ub_const"] + m["ub_slope"] * ub + m["ctx_slope"] * dctx


def main():
    script_dir = Path(__file__).parent

    ctxs_to_measure = [32768, 65536]
    logs = {
        16384:  None,  # placeholder (参照値のみ、実ログはなし)
        32768:  script_dir / "startup_logs" / f"fa1_ctx32768_b2048_ub2048.log",
        65536:  script_dir / "startup_logs" / f"fa1_ctx65536_b2048_ub2048.log",
        131072: None,  # placeholder (Phase R の実測値使用)
    }

    measured = {
        16384:  dict(REF_CTX_16K),
        32768:  None,
        65536:  None,
        131072: dict(REF_CTX_131K),
    }
    kv_measured = {
        16384:  {"CUDA0": 96.0, "CUDA1": 96.0, "CUDA2": 96.0, "CUDA3": 96.0},
        32768:  None,
        65536:  None,
        131072: {"CUDA0": 768.0, "CUDA1": 768.0, "CUDA2": 768.0, "CUDA3": 768.0},
    }

    print("=" * 100)
    print("Phase R-ctx3: 4 点 (ctx=16384/32768/65536/131072) 線形フィット解析")
    print("=" * 100)
    print()

    for ctx in ctxs_to_measure:
        log_path = logs[ctx]
        if log_path is None or not log_path.exists():
            print(f"  WARN: ctx={ctx} 起動ログが未取得 ({log_path})", file=sys.stderr)
            continue
        m = parse_sched_reserve(log_path)
        k = parse_kv_buffer(log_path)
        measured[ctx] = m
        kv_measured[ctx] = k
        print(f"  取得: ctx={ctx:>6d}  log={log_path.name}")

    print()
    print("=" * 100)
    print("1. compute buffer 実測 (4 ctx 点, ub=2048 固定)")
    print("=" * 100)
    print(f"{'GPU':>12s} " + " ".join(f"{ctx:>12d}" for ctx in (16384, 32768, 65536, 131072)))
    for g in GPU_NAMES:
        cells = []
        for ctx in (16384, 32768, 65536, 131072):
            v = measured.get(ctx, {}).get(g) if measured.get(ctx) else None
            cells.append(f"{v:12.2f}" if v is not None else f"{'?':>12s}")
        print(f"{g:>12s} " + " ".join(cells))

    # 2. 4 点最小二乗フィット
    print()
    print("=" * 100)
    print("2. ctx 依存成分の 4 点最小二乗フィット (y = intercept + ctx_slope * Δctx, Δctx=ctx-16384)")
    print("=" * 100)
    print(f"{'GPU':>12s} {'intercept':>14s} {'ctx_slope(MiB/token)':>22s} {'R²':>12s} {'2点モデル':>14s} {'diff':>10s}")
    fit_results = {}
    all_r2_ok = True
    for g in GPU_NAMES:
        xs = []
        ys = []
        for ctx in (16384, 32768, 65536, 131072):
            if measured.get(ctx) and measured[ctx].get(g) is not None:
                xs.append(ctx - 16384)
                ys.append(measured[ctx][g])
        (a, b), r2 = lstsq(xs, ys)
        fit_results[g] = {"intercept": a, "ctx_slope": b, "r2": r2, "n": len(xs)}
        two_pt = TWO_POINT_MODEL[g]["ctx_slope"]
        if b is None:
            print(f"{g:>12s} {'?':>14s} {'?':>22s} {'?':>12s}  データ不足 (n={len(xs)})")
            continue
        diff = b - two_pt
        r2_ok = (r2 is None) or (r2 >= 0.99) or (g == "CUDA3")  # CUDA3 は slope=0 近辺で R² 意味薄
        if not r2_ok and len(xs) >= 3:
            all_r2_ok = False
        print(f"{g:>12s} {a:14.4f} {b:22.6f} {r2:12.8f} {two_pt:14.5f} {diff:+10.6f}")

    # 2b. CUDA0 の quadratic fit (線形の R² が 0.99 未満の場合に有効)
    print()
    print("=" * 100)
    print("2b. CUDA0 二次フィット (y = a + b·Δctx + c·Δctx²)")
    print("=" * 100)
    xs0 = []
    ys0 = []
    for ctx in (16384, 32768, 65536, 131072):
        if measured.get(ctx) and measured[ctx].get("CUDA0") is not None:
            xs0.append(ctx - 16384)
            ys0.append(measured[ctx]["CUDA0"])
    if len(xs0) >= 3:
        # 正規方程式 (3x3) を手動で解く
        n = len(xs0)
        S0 = n
        S1 = sum(xs0)
        S2 = sum(x * x for x in xs0)
        S3 = sum(x ** 3 for x in xs0)
        S4 = sum(x ** 4 for x in xs0)
        T0 = sum(ys0)
        T1 = sum(x * y for x, y in zip(xs0, ys0))
        T2 = sum(x * x * y for x, y in zip(xs0, ys0))
        # [[S0,S1,S2],[S1,S2,S3],[S2,S3,S4]] [a;b;c] = [T0;T1;T2]
        M = [
            [S0, S1, S2, T0],
            [S1, S2, S3, T1],
            [S2, S3, S4, T2],
        ]
        # Gaussian elimination
        for i in range(3):
            pivot = M[i][i]
            for j in range(i + 1, 3):
                factor = M[j][i] / pivot
                for k in range(i, 4):
                    M[j][k] -= factor * M[i][k]
        c = M[2][3] / M[2][2]
        b = (M[1][3] - M[1][2] * c) / M[1][1]
        a = (M[0][3] - M[0][1] * b - M[0][2] * c) / M[0][0]
        ss_tot = sum((y - sum(ys0) / n) ** 2 for y in ys0)
        preds = [a + b * x + c * x * x for x in xs0]
        ss_res = sum((y - p) ** 2 for y, p in zip(ys0, preds))
        r2_quad = 1 - ss_res / ss_tot if ss_tot != 0 else 1.0
        print(f"  a (intercept)  = {a:.4f}")
        print(f"  b (linear)     = {b:.6e}")
        print(f"  c (quadratic)  = {c:.6e}")
        print(f"  R²            = {r2_quad:.8f}")
        print(f"  予測値:")
        for x, y, p in zip(xs0, ys0, preds):
            err = y - p
            pct = (err / y) * 100 if y else 0.0
            print(f"    Δctx={x:>6d}  実測={y:8.2f}  予測={p:8.2f}  誤差={err:+7.3f} MiB ({pct:+5.3f}%)")

    # 3. 2 点モデル予測と 4 点実測の差分
    print()
    print("=" * 100)
    print("3. 2 点モデル予測 vs 実測 (中間点 ctx=32768/65536 のみ)")
    print("=" * 100)
    print(f"{'GPU':>12s} {'ctx':>8s} {'予測 MiB':>12s} {'実測 MiB':>12s} {'誤差 MiB':>12s} {'誤差 %':>10s} {'許容 5%':>10s}")
    all_within_5pct = True
    for ctx in ctxs_to_measure:
        if not measured.get(ctx):
            continue
        for g in GPU_NAMES:
            obs = measured[ctx].get(g)
            if obs is None:
                continue
            pred = predict_two_point(g, ctx, UB)
            err = obs - pred
            pct = (err / pred) * 100 if pred != 0 else float("nan")
            verdict = "OK" if abs(pct) <= 5.0 else "NG"
            if verdict == "NG":
                all_within_5pct = False
            print(f"{g:>12s} {ctx:>8d} {pred:12.2f} {obs:12.2f} {err:+12.2f} {pct:+9.3f}% {verdict:>10s}")

    # 4. CUDA3 の ctx 完全不依存を 4 点で再確認
    print()
    print("=" * 100)
    print("4. CUDA3 ctx 完全不依存性の 4 点再確認 (全点 2012.0 ± 0.5 MiB 期待)")
    print("=" * 100)
    cuda3_vals = []
    for ctx in (16384, 32768, 65536, 131072):
        if measured.get(ctx) and measured[ctx].get("CUDA3") is not None:
            v = measured[ctx]["CUDA3"]
            dev = v - 2012.00
            verdict = "OK" if abs(dev) <= 0.5 else "NG"
            print(f"  ctx={ctx:>6d}  CUDA3={v:>8.2f} MiB  偏差 {dev:+6.3f}  {verdict}")
            cuda3_vals.append(v)
    if cuda3_vals:
        cuda3_range = max(cuda3_vals) - min(cuda3_vals)
        print(f"  CUDA3 変動幅 (max - min): {cuda3_range:.3f} MiB (期待 ≤ 1.0 MiB)")

    # 5. KV buffer ctx 比例性
    print()
    print("=" * 100)
    print("5. KV buffer ctx 比例性 (per GPU, f16 KV)")
    print("=" * 100)
    print(f"{'ctx':>8s} {'予測 MiB/GPU':>14s} {'CUDA0':>10s} {'CUDA1':>10s} {'CUDA2':>10s} {'CUDA3':>10s} {'誤差 %':>10s}")
    for ctx in (16384, 32768, 65536, 131072):
        k = kv_measured.get(ctx)
        if not k:
            continue
        expected = 96.0 * (ctx / 16384)
        cells = []
        max_err_pct = 0.0
        for g in ("CUDA0", "CUDA1", "CUDA2", "CUDA3"):
            v = k.get(g)
            if v is None:
                cells.append(f"{'?':>10s}")
                continue
            cells.append(f"{v:10.2f}")
            err_pct = (v - expected) / expected * 100 if expected else 0.0
            max_err_pct = max(max_err_pct, abs(err_pct))
        print(f"{ctx:>8d} {expected:14.2f} " + " ".join(cells) + f" {max_err_pct:+9.3f}%")

    # 6. 成功条件サマリ
    print()
    print("=" * 100)
    print("6. 成功条件サマリ")
    print("=" * 100)
    cuda3_ok = all(abs(v - 2012.00) <= 0.5 for v in cuda3_vals) if cuda3_vals else False
    data_complete = all(measured[c] for c in (32768, 65536))
    r2_check = all((fit_results[g]["r2"] or 0) >= 0.99 for g in ("CUDA0", "CUDA1", "CUDA2", "CUDA_Host")
                    if fit_results[g]["n"] >= 3)
    checks = [
        ("4 ctx 点データ取得完了", data_complete),
        ("CUDA3 ctx 不依存 (4 点全 ± 0.5 MiB)", cuda3_ok),
        ("CUDA0/1/2/Host R² ≥ 0.99", r2_check),
        ("2 点モデル予測誤差 ≤ 5%", all_within_5pct),
    ]
    for label, ok in checks:
        print(f"  [{'OK' if ok else 'NG'}] {label}")


if __name__ == "__main__":
    main()
