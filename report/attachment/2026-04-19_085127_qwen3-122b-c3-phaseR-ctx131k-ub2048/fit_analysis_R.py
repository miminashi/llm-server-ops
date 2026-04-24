#!/usr/bin/env python3
"""Phase R: 本番 ctx=131072 + -ub=2048 起動試験の予測 vs 実測評価

目的:
  Phase Q で確定した係数 (ctx=16384 まで実証済み) を ctx=131072 に外挿して
  R1 (ctx=131072, -b=2048, -ub=2048) の sched_reserve 実測値と比較する。

Phase Q 係数 (ub=128〜8192 で実証):
  CUDA0     = 951 + 0.077 * n_eff  (定数項漸近値 951, ub 係数 0.077)
  CUDA1/2   = 0.254 * n_eff
  CUDA3     = 0.9824 * n_eff          (誤差 0.002%, R²=1.0)
  CUDA_Host = 0.086 * n_eff          (定数項 ≈ 0)
  n_eff     = min(ctx, -ub)

許容誤差:
  CUDA3 ≤ 0.5%、CUDA1/2 ≤ 1%、CUDA_Host ≤ 3%、CUDA0 ≤ 5%
"""
import json
import math
import statistics
import sys
from pathlib import Path

GPU_NAMES = ("CUDA0", "CUDA1", "CUDA2", "CUDA3", "CUDA_Host")

# Phase Q で確定した係数
COEF = {
    "CUDA0":     (951.0, 0.077),  # (const, slope)
    "CUDA1":     (0.0,   0.254),
    "CUDA2":     (0.0,   0.254),
    "CUDA3":     (0.0,   0.9824),
    "CUDA_Host": (0.0,   0.086),
}
TOL_PCT = {
    "CUDA0":     5.0,
    "CUDA1":     1.0,
    "CUDA2":     1.0,
    "CUDA3":     0.5,
    "CUDA_Host": 3.0,
}

# Phase Q P1 (ctx=16384, ub=2048) reference for KV / eval comparison
PHASE_Q_P1 = {
    "ctx":        16384,
    "ub":         2048,
    "sched":      (1048.13, 520.06, 520.06, 2012.00, 176.08),
    "eval_med":   15.416,
    "prompt_med": 10.99,
    "gpu_used":   (2859, 10577, 10577, 4205),
    "kv_per_gpu": 96,  # MiB/GPU, f16 KV, ctx=16k baseline
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
    """KV buffer 実測値を GPU 別に取得 (f16 KV, 単位 MiB)"""
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


def predict(gpu_name: str, n_eff: int) -> float:
    c, s = COEF[gpu_name]
    return c + s * n_eff


def compare_predicted(ctx: int, ub: int, measured: dict):
    """予測 vs 実測の差分評価"""
    n_eff = min(ctx, ub)
    rows = []
    all_ok = True
    for g in GPU_NAMES:
        pred = predict(g, n_eff)
        obs = measured.get(g)
        if obs is None:
            rows.append((g, pred, None, None, None, "?"))
            all_ok = False
            continue
        err = obs - pred
        pct = (err / pred) * 100 if pred else 0.0
        tol = TOL_PCT[g]
        verdict = "OK" if abs(pct) <= tol else "NG"
        if verdict == "NG":
            all_ok = False
        rows.append((g, pred, obs, err, pct, verdict))
    return rows, all_ok


def load_eval_results(script_dir: Path, tag_prefix: str):
    """out_R_{TAG}_{size}/eval_run*.json から size 別の eval/prompt 中央値を集計"""
    sizes = ["warmup", "1k", "8k", "32k", "64k", "120k"]
    result = {}
    for size in sizes:
        out_dir = script_dir / f"out_{tag_prefix}_{size}"
        if not out_dir.is_dir():
            continue
        evals = []
        prompts = []
        prompt_ns = []
        pred_ns = []
        gpu_used_rows = []
        for j in sorted(out_dir.glob("eval_run*.json")):
            try:
                d = json.loads(j.read_text())
                t = d.get("timings", {})
                if t.get("predicted_per_second") is not None:
                    evals.append(float(t["predicted_per_second"]))
                if t.get("prompt_per_second") is not None:
                    prompts.append(float(t["prompt_per_second"]))
                if t.get("prompt_n") is not None:
                    prompt_ns.append(int(t["prompt_n"]))
                if t.get("predicted_n") is not None:
                    pred_ns.append(int(t["predicted_n"]))
            except (json.JSONDecodeError, ValueError, KeyError):
                pass
        for csv in sorted(out_dir.glob("gpu_post_run*.csv")):
            try:
                rows = csv.read_text().strip().split("\n")
                used = []
                for r in rows[:4]:
                    parts = [x.strip() for x in r.split(",")]
                    if len(parts) >= 2:
                        used.append(int(parts[1].replace("MiB", "").strip()))
                if len(used) == 4:
                    gpu_used_rows.append(tuple(used))
            except (ValueError, IndexError):
                pass
        result[size] = {
            "eval_med":   statistics.median(evals)   if evals   else None,
            "prompt_med": statistics.median(prompts) if prompts else None,
            "prompt_n":   statistics.median(prompt_ns) if prompt_ns else None,
            "predicted_n": statistics.median(pred_ns) if pred_ns else None,
            "runs":       len(evals),
            "gpu_used":   tuple(int(statistics.median(c)) for c in zip(*gpu_used_rows)) if gpu_used_rows else None,
        }
    return result


def main():
    script_dir = Path(__file__).parent

    # R1 条件（メイン）
    CTX = 131072
    B = 2048
    UB = 2048
    log_path = script_dir / "startup_logs" / f"fa1_ctx{CTX}_b{B}_ub{UB}.log"

    print("=" * 100)
    print(f"Phase R: 本番 ctx={CTX} + -b={B} -ub={UB} 起動試験")
    print("=" * 100)

    if not log_path.exists():
        alt = script_dir / "startup_logs" / f"fa1_ctx{CTX}_b{B}_ub{UB}_FAILED.log"
        if alt.exists():
            print(f"R1 起動ログ: FAILED ({alt.name})")
        else:
            print(f"R1 起動ログなし: {log_path}")
            print("フォールバック条件 R2/R3 のログを探索...")
            # Try fallbacks
            for (b, ub) in [(1024, 1024), (512, 512)]:
                fb_log = script_dir / "startup_logs" / f"fa1_ctx{CTX}_b{b}_ub{ub}.log"
                if fb_log.exists():
                    print(f"フォールバック成功: {fb_log.name}")
                    log_path = fb_log
                    B, UB = b, ub
                    break
            else:
                print("ログが全くありません。計測未完了。", file=sys.stderr)
                return

    # sched_reserve 実測
    measured = parse_sched_reserve(log_path)
    kv_measured = parse_kv_buffer(log_path)
    graph_info = parse_graph_info(log_path)

    print()
    print(f"起動ログ: {log_path.name}")
    print()

    # 1. sched_reserve 実測 + Phase Q 予測 vs 実測
    print("=" * 100)
    print(f"1. compute buffer 予測 vs 実測 (Phase Q 係数外挿, n_eff=min({CTX},{UB})={min(CTX,UB)})")
    print("=" * 100)
    print(f"{'GPU':>12s} {'予測(MiB)':>12s} {'実測(MiB)':>12s} {'誤差(MiB)':>12s} {'誤差%':>10s} {'許容%':>8s} {'判定':>6s}")
    rows, overall_ok = compare_predicted(CTX, UB, measured)
    total_pred = 0.0
    total_obs = 0.0
    for (g, pred, obs, err, pct, verdict) in rows:
        if obs is None:
            print(f"{g:>12s} {pred:12.2f} {'?':>12s} {'?':>12s} {'?':>10s} {TOL_PCT[g]:>8.1f} {verdict:>6s}")
        else:
            print(f"{g:>12s} {pred:12.2f} {obs:12.2f} {err:+12.2f} {pct:+9.3f}% {TOL_PCT[g]:>8.1f} {verdict:>6s}")
        total_pred += pred
        if obs is not None:
            total_obs += obs
    print(f"{'合計':>12s} {total_pred:12.2f} {total_obs:12.2f} {total_obs-total_pred:+12.2f}")
    print(f"全項目判定: {'OK' if overall_ok else 'NG'}")

    # 2. KV buffer ctx 比例性検証
    print()
    print("=" * 100)
    print(f"2. KV buffer ctx 比例性検証 (Phase Q ctx=16384 で {PHASE_Q_P1['kv_per_gpu']} MiB/GPU → ctx=131072 で予測 768 MiB/GPU, f16 KV)")
    print("=" * 100)
    expected_kv = PHASE_Q_P1["kv_per_gpu"] * (CTX / PHASE_Q_P1["ctx"])
    print(f"予測 KV/GPU: {expected_kv:.1f} MiB (ctx 8 倍)")
    any_kv = any(v is not None for v in kv_measured.values())
    if any_kv:
        total_kv = 0.0
        for g in GPU_NAMES:
            v = kv_measured.get(g)
            if v is not None:
                pct = (v - expected_kv) / expected_kv * 100 if expected_kv else 0.0
                verdict = "OK" if abs(pct) <= 10.0 else "NG"
                print(f"  {g:>12s} 実測 {v:10.2f} MiB  誤差 {pct:+6.2f}%  {verdict}")
                total_kv += v
        print(f"  KV 合計 (4 GPU): {total_kv:.2f} MiB  予測 {expected_kv*4:.2f} MiB")
    else:
        print("  KV buffer 行が起動ログから取得できず。log 内容を grep で確認してください。")

    # 3. graph nodes / splits
    print()
    print("=" * 100)
    print(f"3. graph nodes / splits (Phase Q で nodes=4473, splits=136 (bs={PHASE_Q_P1['ub']}) + 77 (bs=1) と同一か)")
    print("=" * 100)
    nodes, sp_main, sp_bs, sp_bs1 = graph_info
    print(f"  nodes         = {nodes}    (Phase Q: 4473)")
    print(f"  splits_main   = {sp_main}     (Phase Q: 136)")
    print(f"  splits_main bs= {sp_bs}      (Phase R 期待値: {UB})")
    print(f"  splits_bs1    = {sp_bs1}     (Phase Q: 77)")
    graph_ok = (nodes == 4473 and sp_main == 136 and sp_bs == UB and sp_bs1 == 77)
    print(f"  判定: {'OK' if graph_ok else 'NG (要調査)'}")

    # 4. eval / prompt 速度
    tag_prefix = f"R_f16_fa1_ctx{CTX}_b{B}_ub{UB}"
    eval_results = load_eval_results(script_dir, tag_prefix)
    print()
    print("=" * 100)
    print(f"4. プロンプトサイズ別 eval / prompt 中央値 (Phase Q ctx=16k/ub=2048 基準)")
    print("=" * 100)
    print(f"{'size':>8s} {'runs':>5s} {'prompt_n':>8s} {'predicted_n':>12s} {'eval_tps':>10s} {'prompt_tps':>12s} {'gpu_total':>10s}")
    for size, r in eval_results.items():
        e = f"{r['eval_med']:10.3f}" if r['eval_med']   is not None else f"{'?':>10s}"
        p = f"{r['prompt_med']:12.3f}" if r['prompt_med'] is not None else f"{'?':>12s}"
        pn = f"{int(r['prompt_n']):>8d}" if r['prompt_n']    is not None else f"{'?':>8s}"
        dn = f"{int(r['predicted_n']):>12d}" if r['predicted_n'] is not None else f"{'?':>12s}"
        gu = f"{sum(r['gpu_used']):>10d}" if r['gpu_used']   is not None else f"{'?':>10s}"
        print(f"{size:>8s} {r['runs']:>5d} {pn} {dn} {e} {p} {gu}")

    print()
    print("=" * 100)
    print(f"Phase Q ctx=16k/ub=2048 基準: eval={PHASE_Q_P1['eval_med']:.3f} t/s, prompt={PHASE_Q_P1['prompt_med']:.2f} t/s, gpu_total={sum(PHASE_Q_P1['gpu_used'])} MiB")
    print("=" * 100)

    # 5. 成功条件サマリ
    print()
    print("=" * 100)
    print("5. 成功条件サマリ")
    print("=" * 100)
    warmup = eval_results.get("warmup", {})
    k1k = eval_results.get("1k", {})
    checks = [
        ("起動成功",              log_path.exists() and measured["CUDA3"] is not None),
        ("compute buffer 全 OK",   overall_ok),
        ("graph 構造同一",        graph_ok),
        ("warmup eval ≥ 14.5",   warmup.get("eval_med") is not None and warmup["eval_med"] >= 14.5),
        ("1k eval ≥ 14.5",        k1k.get("eval_med")    is not None and k1k["eval_med"]    >= 14.5),
    ]
    for label, ok in checks:
        print(f"  [{'OK' if ok else 'NG'}] {label}")


if __name__ == "__main__":
    main()
