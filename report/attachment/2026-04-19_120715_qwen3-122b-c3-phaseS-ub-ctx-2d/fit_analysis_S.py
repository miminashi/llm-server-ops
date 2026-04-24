#!/usr/bin/env python3
"""Phase S: ub × ctx 2 軸スキャン (ub=512/1024/4096/8192 × ctx=32k/65k) + 既存 Phase Q/R/R-ctx3 を統合した 16 点 2 軸フィット

モデル:
  CUDA0     = a + b·Δctx + c·Δctx² + d·Δub + e·Δctx·Δub + f·Δub²  (6 params, 二変量二次)
  CUDA1/2   = a + b·Δctx + d·Δub                                   (3 params, 2 軸線形)
  CUDA3     = g·ub                                                  (純 ub 比例、ctx 不依存)
  CUDA_Host = a + b·Δctx + d·Δub                                   (3 params, 2 軸線形)
  Δctx = ctx - 16384, Δub = ub - 2048

データ 16 点:
  Phase Q (ctx=16384, ub=128/256/512/1024/2048)  : 5 点 (compute_buffer_summary.txt から)
  Phase R-ctx3 (ub=2048, ctx=32k/65k)             : 2 点 (レポート値)
  Phase R (ub=2048, ctx=131k)                     : 1 点 (レポート値)
  Phase S (新規計測, ub=512/1024/4096/8192 × ctx=32k/65k) : 8 点 (startup_logs から parse)
"""
import sys
from pathlib import Path

GPU_NAMES = ("CUDA0", "CUDA1", "CUDA2", "CUDA3", "CUDA_Host")

# ---------- 既存データ (ctx, ub) → {GPU: MiB} ----------

KNOWN_POINTS = {
    # Phase Q (ctx=16384, ub スキャン)
    (16384, 128):  {"CUDA0": 961.62, "CUDA1": 34.64,  "CUDA2": 34.64,  "CUDA3": 125.75, "CUDA_Host": 11.00},
    (16384, 256):  {"CUDA0": 963.25, "CUDA1": 65.01,  "CUDA2": 65.01,  "CUDA3": 251.50, "CUDA_Host": 22.01},
    (16384, 512):  {"CUDA0": 966.50, "CUDA1": 130.02, "CUDA2": 130.02, "CUDA3": 503.00, "CUDA_Host": 44.02},
    (16384, 1024): {"CUDA0": 973.00, "CUDA1": 260.03, "CUDA2": 260.03, "CUDA3": 1006.00,"CUDA_Host": 88.04},
    (16384, 2048): {"CUDA0": 1048.13,"CUDA1": 520.06, "CUDA2": 520.06, "CUDA3": 2012.00,"CUDA_Host": 176.08},
    # Phase R-ctx3 (ub=2048, ctx スキャン)
    (32768, 2048): {"CUDA0": 1112.13,"CUDA1": 584.06, "CUDA2": 584.06, "CUDA3": 2012.00,"CUDA_Host": 304.08},
    (65536, 2048): {"CUDA0": 1348.00,"CUDA1": 712.06, "CUDA2": 712.06, "CUDA3": 2012.00,"CUDA_Host": 560.08},
    # Phase R (ub=2048, ctx=131072)
    (131072,2048): {"CUDA0": 2180.00,"CUDA1": 968.06, "CUDA2": 968.06, "CUDA3": 2012.00,"CUDA_Host": 1072.08},
}

# Phase S で新規計測する条件 (startup_logs から parse)
PHASE_S_CONDS = [
    (32768, 512), (32768, 1024), (32768, 4096), (32768, 8192),
    (65536, 512), (65536, 1024), (65536, 4096), (65536, 8192),
]

# Phase R-ctx3 単変量モデル (本 Phase の比較対象)
RCTX3_MODEL = {
    "CUDA0":     {"intercept": 1046.29, "ctx_linear": 3.269e-3, "ctx_quad": 5.770e-8, "ub_slope": 0.077},
    "CUDA1":     {"intercept": 520.06,  "ctx_linear": 0.003906, "ctx_quad": 0.0,      "ub_slope": 0.254},
    "CUDA2":     {"intercept": 520.06,  "ctx_linear": 0.003906, "ctx_quad": 0.0,      "ub_slope": 0.254},
    "CUDA3":     {"intercept": 0.0,     "ctx_linear": 0.0,      "ctx_quad": 0.0,      "ub_slope": 0.9824, "is_ub_pure": True},
    "CUDA_Host": {"intercept": 176.08,  "ctx_linear": 0.007812, "ctx_quad": 0.0,      "ub_slope": 0.086},
}


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


def solve_lstsq(X, y):
    """X (n×p), y (n) の最小二乗を正規方程式 XᵀX β = Xᵀy で解く。Gaussian elimination、pivoting 付き。"""
    n = len(X)
    p = len(X[0])
    A = [[0.0] * p for _ in range(p)]
    b = [0.0] * p
    for i in range(p):
        for j in range(p):
            A[i][j] = sum(X[k][i] * X[k][j] for k in range(n))
        b[i] = sum(X[k][i] * y[k] for k in range(n))
    # augmented
    for i in range(p):
        A[i].append(b[i])
    # partial pivoting
    for i in range(p):
        max_row = i
        for r in range(i + 1, p):
            if abs(A[r][i]) > abs(A[max_row][i]):
                max_row = r
        if max_row != i:
            A[i], A[max_row] = A[max_row], A[i]
        pivot = A[i][i]
        if abs(pivot) < 1e-15:
            raise ValueError(f"Singular matrix at row {i}")
        for r in range(i + 1, p):
            factor = A[r][i] / pivot
            for c in range(i, p + 1):
                A[r][c] -= factor * A[i][c]
    beta = [0.0] * p
    for i in range(p - 1, -1, -1):
        s = A[i][p]
        for j in range(i + 1, p):
            s -= A[i][j] * beta[j]
        beta[i] = s / A[i][i]
    return beta


def r_squared(y, y_pred):
    if not y:
        return None
    my = sum(y) / len(y)
    ss_tot = sum((v - my) ** 2 for v in y)
    ss_res = sum((v - p) ** 2 for v, p in zip(y, y_pred))
    if ss_tot == 0:
        return 1.0 if ss_res < 1e-12 else 0.0
    return 1.0 - ss_res / ss_tot


def predict_rctx3(g, ctx, ub):
    m = RCTX3_MODEL[g]
    if m.get("is_ub_pure"):
        return m["ub_slope"] * ub
    dctx = ctx - 16384
    dub = ub - 2048
    return (
        m["intercept"]
        + m["ctx_linear"] * dctx
        + m["ctx_quad"] * dctx * dctx
        + m["ub_slope"] * dub
    )


def main():
    script_dir = Path(__file__).parent

    # Phase S 新規計測値を startup_logs から取り込み
    all_points = dict(KNOWN_POINTS)
    kv_data = {}
    graph_data = {}

    # 既知データの KV/graph (Phase R-ctx3 / Phase R 既定値)
    for (ctx, ub) in KNOWN_POINTS:
        kv_data[(ctx, ub)] = {
            "CUDA0": 96.0 * (ctx / 16384.0),
            "CUDA1": 96.0 * (ctx / 16384.0),
            "CUDA2": 96.0 * (ctx / 16384.0),
            "CUDA3": 96.0 * (ctx / 16384.0),
        }
        graph_data[(ctx, ub)] = (4473, 136, ub, 77)

    print("=" * 110)
    print("Phase S: ub × ctx 2 軸 (16 点) fit 解析")
    print("=" * 110)
    print()

    print("-- Phase S 新規計測値の取り込み --")
    missing_logs = []
    for (ctx, ub) in PHASE_S_CONDS:
        log = script_dir / "startup_logs" / f"fa1_ctx{ctx}_b{ub}_ub{ub}.log"
        if not log.exists():
            missing_logs.append(log.name)
            continue
        m = parse_sched_reserve(log)
        if any(v is None for v in m.values()):
            print(f"  WARN: ctx={ctx} ub={ub} partial parse: {m}", file=sys.stderr)
        all_points[(ctx, ub)] = m
        kv_data[(ctx, ub)] = parse_kv_buffer(log)
        graph_data[(ctx, ub)] = parse_graph_info(log)
        print(f"  取得: ctx={ctx:>6d} ub={ub:>5d}  CUDA0={m.get('CUDA0')} CUDA3={m.get('CUDA3')}")
    if missing_logs:
        print(f"  WARN: 以下のログが未取得 (fit 点数減少): {missing_logs}", file=sys.stderr)

    # --- 1. データ点サマリ ---
    print()
    print("=" * 110)
    print("1. 全 16 点データサマリ (compute buffer 実測 MiB)")
    print("=" * 110)
    print(f"{'ctx':>8s} {'ub':>6s}  " + "  ".join(f"{g:>10s}" for g in GPU_NAMES))
    for (ctx, ub) in sorted(all_points.keys()):
        row = all_points[(ctx, ub)]
        cells = [f"{row.get(g):>10.2f}" if row.get(g) is not None else f"{'?':>10s}" for g in GPU_NAMES]
        print(f"{ctx:>8d} {ub:>6d}  " + "  ".join(cells))

    # --- 2. CUDA3 の ub 純比例フィット (ctx 依存性は ub 純比例であることの再確認) ---
    print()
    print("=" * 110)
    print("2. CUDA3: g·ub 純比例フィット (切片ゼロ強制、全 16 点)")
    print("=" * 110)
    xs_ub = []
    ys = []
    for (ctx, ub), row in all_points.items():
        v = row.get("CUDA3")
        if v is None:
            continue
        xs_ub.append(ub)
        ys.append(v)
    if xs_ub:
        num = sum(x * y for x, y in zip(xs_ub, ys))
        den = sum(x * x for x in xs_ub)
        g_slope = num / den if den else 0.0
        preds = [g_slope * x for x in xs_ub]
        r2 = r_squared(ys, preds)
        max_err = max(abs(y - p) for y, p in zip(ys, preds))
        print(f"  g (ub slope) = {g_slope:.6f}  R² = {r2:.8f}  max_err = {max_err:.3f} MiB (Rctx3 モデル: 0.9824)")

    # --- 3. CUDA0: 2 軸二次 (6 params) fit ---
    print()
    print("=" * 110)
    print("3. CUDA0: 2 軸二次フィット (6 params: a + b·Δctx + c·Δctx² + d·Δub + e·Δctx·Δub + f·Δub²)")
    print("=" * 110)
    X = []
    y = []
    points = []
    for (ctx, ub), row in all_points.items():
        v = row.get("CUDA0")
        if v is None:
            continue
        dctx = ctx - 16384
        dub = ub - 2048
        X.append([1.0, dctx, dctx * dctx, dub, dctx * dub, dub * dub])
        y.append(v)
        points.append((ctx, ub, v))
    try:
        beta = solve_lstsq(X, y)
        preds = [sum(xi * bi for xi, bi in zip(row, beta)) for row in X]
        r2_cuda0_6p = r_squared(y, preds)
        labels = ["a (intercept)", "b (Δctx)", "c (Δctx²)", "d (Δub)", "e (Δctx·Δub)", "f (Δub²)"]
        for lbl, bv in zip(labels, beta):
            print(f"  {lbl:>16s} = {bv:+.6e}")
        print(f"  R² = {r2_cuda0_6p:.8f}  N = {len(y)}")
        # 相互作用項 e の有意性: |e · max(Δctx) · max(Δub)| / median(y)
        max_dctx = max(abs(row[1]) for row in X)
        max_dub  = max(abs(row[3]) for row in X)
        ymed = sorted(y)[len(y)//2]
        interaction_magnitude = abs(beta[4]) * max_dctx * max_dub
        pct = interaction_magnitude / ymed * 100 if ymed else 0.0
        print(f"  相互作用項 e の影響量: |e·max(Δctx)·max(Δub)| = {interaction_magnitude:.3f} MiB "
              f"({pct:.3f}% of median CUDA0={ymed:.2f}) → "
              f"{'独立可分 OK' if pct < 1.0 else '相互作用あり (要 e 項)'}")
        print()
        print("  各点の予測誤差:")
        print(f"  {'ctx':>8s} {'ub':>6s}  {'実測':>10s}  {'予測 (6p)':>12s}  {'誤差':>10s}  {'%':>8s}")
        for (ctx, ub, obs), p in zip(points, preds):
            err = obs - p
            pct = err / obs * 100 if obs else 0.0
            print(f"  {ctx:>8d} {ub:>6d}  {obs:>10.2f}  {p:>12.2f}  {err:>+10.3f}  {pct:>+7.3f}%")

        cuda0_beta = beta
        cuda0_r2 = r2_cuda0_6p
    except ValueError as ex:
        print(f"  ERROR: {ex}", file=sys.stderr)
        cuda0_beta = None
        cuda0_r2 = None

    # --- 3b. CUDA0: 4 params (cross のみ) と 7 params (すべて + Δub·Δctx²) 比較 ---
    print()
    print("=" * 110)
    print("3b. CUDA0: モデル選択比較 (4p / 5p / 6p / 7p)")
    print("=" * 110)
    Xmod = {"4p": [], "5p": [], "6p": [], "7p": []}
    ymod = []
    for (ctx, ub), row in all_points.items():
        v = row.get("CUDA0")
        if v is None:
            continue
        dc = ctx - 16384
        du = ub - 2048
        Xmod["4p"].append([1.0, dc, du, dc * du])
        Xmod["5p"].append([1.0, dc, du, dc * du, du * du])
        Xmod["6p"].append([1.0, dc, dc * dc, du, dc * du, du * du])
        Xmod["7p"].append([1.0, dc, dc * dc, du, dc * du, du * du, dc * dc * du])
        ymod.append(v)
    for key in ("4p", "5p", "6p", "7p"):
        try:
            b = solve_lstsq(Xmod[key], ymod)
            preds = [sum(xi * bi for xi, bi in zip(rw, b)) for rw in Xmod[key]]
            r2 = r_squared(ymod, preds)
            max_err = max(abs(yv - p) for yv, p in zip(ymod, preds))
            print(f"  CUDA0 {key}: R²={r2:.8f}  max_err={max_err:.3f}  β={['%+.3e' % v for v in b]}")
        except ValueError as ex:
            print(f"  CUDA0 {key}: ERROR {ex}", file=sys.stderr)

    # --- 4. CUDA1/2/Host: 2 軸線形 (3 params) fit + 相互作用 (4 params) fit 比較 ---
    print()
    print("=" * 110)
    print("4. CUDA1 / CUDA2 / CUDA_Host: 2 軸 3 params vs 4 params (相互作用項 e 付き)")
    print("=" * 110)
    linear_fits = {}
    for g in ("CUDA1", "CUDA2", "CUDA_Host"):
        X3 = []
        X4 = []
        yg = []
        pts_g = []
        for (ctx, ub), row in all_points.items():
            v = row.get(g)
            if v is None:
                continue
            dc = ctx - 16384
            du = ub - 2048
            X3.append([1.0, dc, du])
            X4.append([1.0, dc, du, dc * du])
            yg.append(v)
            pts_g.append((ctx, ub, v))
        try:
            b3 = solve_lstsq(X3, yg)
            preds3 = [sum(xi * bi for xi, bi in zip(rw, b3)) for rw in X3]
            r2_3 = r_squared(yg, preds3)
            max_err3 = max(abs(y_ - p) for y_, p in zip(yg, preds3))
            b4 = solve_lstsq(X4, yg)
            preds4 = [sum(xi * bi for xi, bi in zip(rw, b4)) for rw in X4]
            r2_4 = r_squared(yg, preds4)
            max_err4 = max(abs(y_ - p) for y_, p in zip(yg, preds4))
            linear_fits[g] = {"beta3": b3, "r2_3": r2_3, "beta4": b4, "r2_4": r2_4,
                              "max_err3": max_err3, "max_err4": max_err4}
            print(f"  {g:>10s}:")
            print(f"    3p: intercept={b3[0]:8.4f}  ctx_slope={b3[1]:.6e}  ub_slope={b3[2]:.6f}"
                  f"  R²={r2_3:.8f}  max_err={max_err3:.3f} MiB")
            print(f"    4p: intercept={b4[0]:8.4f}  ctx_slope={b4[1]:.6e}  ub_slope={b4[2]:.6f}"
                  f"  cross_e={b4[3]:.6e}  R²={r2_4:.8f}  max_err={max_err4:.3f} MiB")
        except ValueError as ex:
            print(f"  {g:>10s}: ERROR {ex}", file=sys.stderr)
            linear_fits[g] = None

    # --- 5. Phase R-ctx3 単変量モデル vs 16 点実測 ---
    print()
    print("=" * 110)
    print("5. Phase R-ctx3 単変量モデル予測 vs 16 点実測 (誤差 %)")
    print("=" * 110)
    header = f"{'ctx':>8s} {'ub':>6s}  " + "  ".join(f"{g:>9s}" for g in GPU_NAMES)
    print(header)
    worst = {"gpu": None, "pct": 0.0, "ctx": 0, "ub": 0}
    for (ctx, ub) in sorted(all_points.keys()):
        row = all_points[(ctx, ub)]
        cells = []
        for g in GPU_NAMES:
            obs = row.get(g)
            if obs is None:
                cells.append(f"{'?':>9s}")
                continue
            pred = predict_rctx3(g, ctx, ub)
            pct = (obs - pred) / pred * 100 if pred != 0 else 0.0
            cells.append(f"{pct:>+8.2f}%")
            if abs(pct) > abs(worst["pct"]):
                worst = {"gpu": g, "pct": pct, "ctx": ctx, "ub": ub}
        print(f"{ctx:>8d} {ub:>6d}  " + "  ".join(cells))
    print()
    print(f"  最大誤差: {worst['gpu']} at ctx={worst['ctx']} ub={worst['ub']}: {worst['pct']:+.3f}%")

    # --- 6. KV buffer ctx 比例性 (16 点) ---
    print()
    print("=" * 110)
    print("6. KV buffer ctx 比例性 (全 16 点、期待値: 96.0 · (ctx/16384) MiB/GPU)")
    print("=" * 110)
    max_kv_err = 0.0
    for (ctx, ub) in sorted(kv_data.keys()):
        expected = 96.0 * (ctx / 16384.0)
        k = kv_data[(ctx, ub)]
        errs = []
        for g in ("CUDA0", "CUDA1", "CUDA2", "CUDA3"):
            v = k.get(g)
            if v is None:
                continue
            errs.append(abs(v - expected))
            max_kv_err = max(max_kv_err, abs(v - expected))
        e_s = "  ".join(f"{k.get(g):>6.2f}" if k.get(g) is not None else f"{'?':>6s}"
                        for g in ("CUDA0", "CUDA1", "CUDA2", "CUDA3"))
        print(f"  ctx={ctx:>6d} ub={ub:>5d}  exp={expected:>7.2f}  " + e_s + f"  max_err={max(errs) if errs else 0:.2f}")
    print(f"\n  全点最大 KV 誤差: {max_kv_err:.3f} MiB")

    # --- 7. graph 構造不変性 (16 点) ---
    print()
    print("=" * 110)
    print("7. graph 構造不変性 (nodes=4473, splits=136+77 期待)")
    print("=" * 110)
    unique_nodes = set()
    unique_splits_bs1 = set()
    for (ctx, ub), g in graph_data.items():
        if g and g[0]:
            unique_nodes.add(g[0])
        if g and g[3]:
            unique_splits_bs1.add(g[3])
    print(f"  unique nodes: {sorted(unique_nodes)} (期待 [4473])")
    print(f"  unique splits_bs1: {sorted(unique_splits_bs1)} (期待 [77])")

    # --- 8. 成功条件サマリ ---
    print()
    print("=" * 110)
    print("8. 成功条件サマリ")
    print("=" * 110)
    data_complete = len([p for p in all_points.values() if all(p.get(g) is not None for g in GPU_NAMES)]) >= 16
    cuda3_ok = False
    cuda3_vals = [row["CUDA3"] for row in all_points.values() if row.get("CUDA3") is not None]
    if cuda3_vals:
        # 純比例式 0.9824·ub との最大偏差
        max_dev = 0.0
        for (ctx, ub), row in all_points.items():
            if row.get("CUDA3") is not None:
                dev = abs(row["CUDA3"] - 0.9824 * ub)
                max_dev = max(max_dev, dev)
        cuda3_ok = max_dev <= 2.0
    cuda0_ok = cuda0_r2 is not None and cuda0_r2 >= 0.999
    linear_ok = all(lf is not None and lf.get("r2_4", 0) >= 0.999 for lf in linear_fits.values())
    graph_ok = unique_nodes == {4473} and unique_splits_bs1 == {77}
    kv_ok = max_kv_err < 1.0
    checks = [
        ("全 16 点データ取得完了", data_complete),
        ("CUDA3 ≈ 0.9824·ub (偏差 ≤ 2 MiB)", cuda3_ok),
        ("CUDA0 二変量二次 R² ≥ 0.999", cuda0_ok),
        ("CUDA1/2/Host 2 軸線形 R² ≥ 0.999", linear_ok),
        ("graph nodes=4473 全一致", graph_ok),
        ("KV buffer 誤差 < 1 MiB", kv_ok),
    ]
    for label, ok in checks:
        print(f"  [{'OK' if ok else 'NG'}] {label}")


if __name__ == "__main__":
    main()
