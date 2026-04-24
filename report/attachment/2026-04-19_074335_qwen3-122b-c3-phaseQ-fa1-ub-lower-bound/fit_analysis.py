#!/usr/bin/env python3
"""Phase Q: fa=1 ctx=16384 固定で -ub 下限探索 (1024/512/256/128)

目的:
  Phase P で確定した CUDA3 = 0.9824 * min(ctx, -ub) MiB の線形性が、
  -ub を 1024 / 512 / 256 / 128 と極小領域まで下げても保たれるか実証。
  さらに Phase P 4 点 + Phase Q 3〜4 点を結合した 7〜8 点フィットで
  係数の信頼区間を求め、log-log 傾きの崩壊点と eval 速度の反転点を検出。

データ:
  Phase P (定数として埋め込み) + Phase Q (startup_logs/ から自動ロード)。

許容値:
  各 Phase Q 条件で |実測 - 0.9824*ub| / 0.9824*ub <= 0.5%
  log-log 傾き 0.95 〜 1.05
  7 点線形フィット係数 0.978 〜 0.987
"""
import json
import math
import statistics
import sys
from pathlib import Path

GPU_NAMES = ("CUDA0", "CUDA1", "CUDA2", "CUDA3", "CUDA_Host")
CTX = 16384

PHASE_P_MEASURED = {
    (2048, 2048): (1048.13, 520.06, 520.06, 2012.00, 176.08),
    (4096, 4096): (1568.27, 1040.13, 1040.13, 4024.00, 352.16),
    (8192, 8192): (2784.00, 2080.25, 2080.25, 8048.00, 704.31),
    (8192, 4096): (1568.27, 1040.13, 1040.13, 4024.00, 352.16),
}

PHASE_P_EVAL_MEDIAN = {
    (2048, 2048): 15.416,
    (4096, 4096): 15.368,
    (8192, 8192): 15.186,
    (8192, 4096): 15.422,
}
PHASE_P_PROMPT_MEDIAN = {
    (2048, 2048): 10.99,
    (4096, 4096): 11.03,
    (8192, 8192): 10.95,
    (8192, 4096): 10.87,
}
PHASE_P_GPU_USED = {
    (2048, 2048): (2859, 10577, 10577, 4205),
    (4096, 4096): (3379, 11097, 11097, 6217),
    (8192, 8192): (4595, 12137, 12137, 10241),
    (8192, 4096): (3379, 11097, 11097, 6217),
}

PHASE_Q_CFGS = [(1024, 1024), (512, 512), (256, 256), (128, 128)]


def parse_sched_reserve(log_path: Path):
    vals = {g: None for g in GPU_NAMES}
    if not log_path.exists():
        return tuple(vals[g] for g in GPU_NAMES)
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
    return tuple(vals[g] for g in GPU_NAMES)


def parse_graph_info(log_path: Path):
    """graph nodes と graph splits の bs 値を抽出"""
    nodes = None
    splits_main = None
    splits_main_bs = None
    splits_bs1 = None
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
                # 例: "graph splits = 136 (with bs=8192), 77 (with bs=1)"
                try:
                    parts = line.split("=", 1)[-1].strip()
                    chunks = [c.strip() for c in parts.split(",")]
                    if chunks:
                        first = chunks[0]
                        splits_main = int(first.split("(")[0].strip())
                        if "(with bs=" in first:
                            bs_str = first.split("(with bs=")[-1].rstrip(")")
                            splits_main_bs = int(bs_str)
                        if len(chunks) >= 2:
                            second = chunks[1]
                            splits_bs1 = int(second.split("(")[0].strip())
                except (ValueError, IndexError):
                    pass
    return (nodes, splits_main, splits_main_bs, splits_bs1)


def load_phase_q(script_dir: Path):
    measured = {}
    graph_info = {}
    failed = []
    logs_dir = script_dir / "startup_logs"
    for cfg in PHASE_Q_CFGS:
        b, ub = cfg
        log = logs_dir / f"fa1_ctx{CTX}_b{b}_ub{ub}.log"
        if not log.exists():
            failed_log = logs_dir / f"fa1_ctx{CTX}_b{b}_ub{ub}_FAILED.log"
            if failed_log.exists():
                failed.append((cfg, "FAILED log saved"))
            continue
        vals = parse_sched_reserve(log)
        if all(v is not None for v in vals):
            measured[cfg] = vals
            graph_info[cfg] = parse_graph_info(log)
        else:
            failed.append((cfg, "log unparsable"))
    return measured, graph_info, failed


def load_eval_medians(script_dir: Path, q_cfgs):
    """Phase Q の各条件について out_Q_*/eval_run*.json から eval_tps 中央値を集計"""
    eval_med = {}
    prompt_med = {}
    gpu_used = {}
    for cfg in q_cfgs:
        b, ub = cfg
        out_dir = script_dir / f"out_Q_f16_fa1_ctx{CTX}_b{b}_ub{ub}_warmup"
        if not out_dir.is_dir():
            continue
        eval_vals = []
        prompt_vals = []
        gpu_rows = []
        for json_path in sorted(out_dir.glob("eval_run*.json")):
            try:
                d = json.loads(json_path.read_text())
                e = d.get("timings", {}).get("predicted_per_second")
                p = d.get("timings", {}).get("prompt_per_second")
                if e is not None:
                    eval_vals.append(float(e))
                if p is not None:
                    prompt_vals.append(float(p))
            except (json.JSONDecodeError, ValueError):
                pass
        for csv_path in sorted(out_dir.glob("gpu_post_run*.csv")):
            try:
                rows = csv_path.read_text().strip().split("\n")
                used = []
                for r in rows[:4]:
                    parts = [x.strip() for x in r.split(",")]
                    if len(parts) >= 2:
                        v = parts[1].replace("MiB", "").strip()
                        used.append(int(v))
                if len(used) == 4:
                    gpu_rows.append(tuple(used))
            except (ValueError, IndexError):
                pass
        if eval_vals:
            eval_med[cfg] = statistics.median(eval_vals)
        if prompt_vals:
            prompt_med[cfg] = statistics.median(prompt_vals)
        if gpu_rows:
            cols = list(zip(*gpu_rows))
            gpu_used[cfg] = tuple(int(statistics.median(c)) for c in cols)
    return eval_med, prompt_med, gpu_used


def linfit(xs, ys):
    """y = a*x + b  を numpy なしで最小二乗"""
    n = len(xs)
    if n < 2:
        return None
    sx = sum(xs); sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    denom = n * sxx - sx * sx
    if denom == 0:
        return None
    a = (n * sxy - sx * sy) / denom
    b = (sy - a * sx) / n
    # R^2
    y_mean = sy / n
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (a * x + b)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return (a, b, r2)


def main():
    script_dir = Path(__file__).parent
    q_measured, q_graph, q_failed = load_phase_q(script_dir)
    q_eval, q_prompt, q_gpu = load_eval_medians(script_dir, list(q_measured.keys()))

    if not q_measured:
        print("Phase Q 計測データ無し。startup_logs/ を確認", file=sys.stderr)

    # 全結合データセット (Phase P + Phase Q)
    combined = {}
    combined.update(PHASE_P_MEASURED)
    combined.update(q_measured)

    print("=" * 100)
    print("Phase Q: fa=1 ctx=16384 固定 -ub 下限探索 (sched_reserve 実測 MiB)")
    print("=" * 100)
    print(f"{'cond':>16s}  {'CUDA0':>10s} {'CUDA1':>10s} {'CUDA2':>10s} {'CUDA3':>10s} {'CUDA_Host':>10s} {'合計':>10s} {'src':>6s}")
    for cfg in sorted(combined.keys(), key=lambda c: (c[1], c[0])):
        b, ub = cfg
        vals = combined[cfg]
        total = sum(vals)
        src = "Q" if cfg in q_measured else "P"
        print(f"  b={b:5d} ub={ub:5d}  " + "".join(f"{v:10.2f} " for v in vals) + f"{total:10.2f}  {src:>5s}")

    if q_failed:
        print()
        print("=" * 100)
        print("Phase Q 起動失敗 (llama.cpp -ub 下限拒否 or OOM)")
        print("=" * 100)
        for cfg, reason in q_failed:
            print(f"  b={cfg[0]:5d} ub={cfg[1]:5d}  -> {reason}")

    # CUDA3 線形性検証
    print()
    print("=" * 100)
    print("CUDA3 線形性検証: CUDA3 ≈ 0.9824 * min(ctx, ub)  [許容: ≤ 0.5%]")
    print("=" * 100)
    print(f"{'cond':>16s}  {'n_eff':>6s} {'予測':>10s} {'実測':>10s} {'誤差':>10s} {'誤差%':>10s}  {'判定':>6s}")
    for cfg in sorted(combined.keys(), key=lambda c: c[1]):
        b, ub = cfg
        n = min(CTX, ub)
        pred = 0.9824 * n
        obs = combined[cfg][3]
        err = obs - pred
        pct = (err / pred) * 100 if pred else 0.0
        verdict = "OK" if abs(pct) <= 0.5 else "NG"
        print(f"  b={b:5d} ub={ub:5d}  {n:6d} {pred:10.2f} {obs:10.2f} {err:+10.2f} {pct:+9.3f}%   {verdict:>4s}")

    # log-log 傾き全区間
    print()
    print("=" * 100)
    print("CUDA3 log-log 傾き (隣接 ub 区間、傾き 1.00 で完全線形)")
    print("=" * 100)
    sorted_ubs = sorted({c[1] for c in combined if c[0] == c[1]})
    print(f"  ub 系列: {sorted_ubs}")
    print(f"{'区間':>16s}  {'CUDA3比':>10s} {'ub比':>8s}  {'log-log傾き':>12s}  {'判定':>6s}")
    for i in range(1, len(sorted_ubs)):
        ub_prev = sorted_ubs[i - 1]; ub_cur = sorted_ubs[i]
        cfg_prev = (ub_prev, ub_prev); cfg_cur = (ub_cur, ub_cur)
        if cfg_prev not in combined or cfg_cur not in combined:
            continue
        v_prev = combined[cfg_prev][3]; v_cur = combined[cfg_cur][3]
        ratio_v = v_cur / v_prev
        ratio_ub = ub_cur / ub_prev
        slope = math.log(ratio_v) / math.log(ratio_ub)
        verdict = "OK" if 0.95 <= slope <= 1.05 else "NG"
        print(f"  ub {ub_prev:4d}->{ub_cur:4d}  {ratio_v:10.4f} {ratio_ub:8.2f}  {slope:12.4f}  {verdict:>6s}")

    # 7-8 点フィット (CUDA3、ub == b の主系列のみ)
    print()
    print("=" * 100)
    print("CUDA3 多点フィット (ub = b 系列、Phase P + Phase Q 統合)")
    print("=" * 100)
    pts = []
    for cfg in combined:
        if cfg[0] == cfg[1]:
            pts.append((cfg[1], combined[cfg][3]))
    pts.sort()
    if len(pts) >= 2:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        # 線形フィット y = a*x + b
        fit_lin = linfit(xs, ys)
        if fit_lin:
            a, b, r2 = fit_lin
            print(f"  線形:  CUDA3 = {a:.6f} * ub + {b:+.4f}   R²={r2:.8f}   傾き判定={'OK' if 0.978 <= a <= 0.987 else 'NG'}")
        # log-log フィット
        log_xs = [math.log(x) for x in xs]
        log_ys = [math.log(y) for y in ys]
        fit_log = linfit(log_xs, log_ys)
        if fit_log:
            alpha, beta, r2 = fit_log
            print(f"  log-log: log(CUDA3) = {alpha:.6f} * log(ub) + {beta:+.4f}   exp(β)={math.exp(beta):.4f}   R²={r2:.8f}")
            print(f"           α=1 仮説 (純線形): |α-1|={abs(alpha-1):.4f}  判定={'OK' if abs(alpha-1) <= 0.05 else 'NG'}")
        print(f"  使用点 (ub, CUDA3): {pts}")

    # graph 情報追跡
    print()
    print("=" * 100)
    print("graph nodes / splits 追跡 (Phase Q)")
    print("=" * 100)
    print(f"{'cond':>16s}  {'nodes':>8s}  {'splits_main':>12s}  {'bs=':>8s}  {'splits_bs1':>10s}  {'bs=ub一致':>10s}")
    for cfg in sorted(q_graph.keys(), key=lambda c: c[1]):
        b, ub = cfg
        nodes, sp_main, sp_bs, sp_bs1 = q_graph[cfg]
        ok = "YES" if sp_bs == ub else "NO"
        n_str = f"{nodes}" if nodes is not None else "?"
        sp_str = f"{sp_main}" if sp_main is not None else "?"
        bs_str = f"{sp_bs}" if sp_bs is not None else "?"
        bs1_str = f"{sp_bs1}" if sp_bs1 is not None else "?"
        print(f"  b={b:5d} ub={ub:5d}  {n_str:>8s}  {sp_str:>12s}  {bs_str:>8s}  {bs1_str:>10s}  {ok:>10s}")

    # eval / prompt 速度トレンド
    print()
    print("=" * 100)
    print("eval / prompt 速度トレンド (ub 関数、Phase P + Phase Q 統合)")
    print("=" * 100)
    eval_combined = dict(PHASE_P_EVAL_MEDIAN)
    eval_combined.update(q_eval)
    prompt_combined = dict(PHASE_P_PROMPT_MEDIAN)
    prompt_combined.update(q_prompt)
    gpu_combined = dict(PHASE_P_GPU_USED)
    gpu_combined.update(q_gpu)
    print(f"{'ub':>6s}  {'eval_med':>10s} {'prompt_med':>10s} {'compute_buf':>12s} {'gpu_used_合計':>14s}  {'src':>4s}")
    main_series = sorted({c for c in eval_combined if c[0] == c[1]}, key=lambda c: c[1])
    eval_seq = []
    for cfg in main_series:
        ub = cfg[1]
        e = eval_combined.get(cfg)
        p = prompt_combined.get(cfg)
        cb = sum(combined[cfg]) if cfg in combined else None
        g = gpu_combined.get(cfg)
        g_total = sum(g) if g else None
        e_str = f"{e:10.3f}" if e is not None else f"{'?':>10s}"
        p_str = f"{p:10.3f}" if p is not None else f"{'?':>10s}"
        cb_str = f"{cb:12.2f}" if cb is not None else f"{'?':>12s}"
        g_str = f"{g_total:14d}" if g_total is not None else f"{'?':>14s}"
        src = "Q" if cfg in q_eval else "P"
        print(f"  {ub:>6d}  {e_str} {p_str} {cb_str} {g_str}  {src:>4s}")
        if e is not None:
            eval_seq.append((ub, e))

    # 反転点検出 (eval が単調減少から単調増加に転じる ub)
    print()
    print("eval 速度反転点検出 (隣接 ub 間で eval の符号変化を検出):")
    eval_seq.sort()
    if len(eval_seq) >= 3:
        diffs = []
        for i in range(1, len(eval_seq)):
            ub_prev, e_prev = eval_seq[i - 1]
            ub_cur, e_cur = eval_seq[i]
            diffs.append((ub_prev, ub_cur, e_cur - e_prev))
        for d in diffs:
            sign = "+" if d[2] > 0 else ("-" if d[2] < 0 else "0")
            print(f"  ub {d[0]:>5d}→{d[1]:>5d}: Δeval={d[2]:+.4f}  ({sign})")
        sign_changes = []
        for i in range(1, len(diffs)):
            if diffs[i - 1][2] * diffs[i][2] < 0:
                sign_changes.append(diffs[i][0])
        if sign_changes:
            print(f"  符号変化 (反転) 検出: ub = {sign_changes}")
        else:
            print("  符号変化なし (全域で単調)")
    else:
        print("  データ点不足 (≥3 必要)")


if __name__ == "__main__":
    main()
