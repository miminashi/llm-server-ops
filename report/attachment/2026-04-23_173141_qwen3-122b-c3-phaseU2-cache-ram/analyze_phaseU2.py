#!/usr/bin/env python3
"""analyze_phaseU2.py - Phase U-2: --cache-ram (PR #16391) 独立検証

入力 (batch_U2.sh 実行後):
  out_U2_{TAG_COND}_ttft/ttft_summary.tsv
  out_U2_{TAG_COND}_prefix/prefix_summary.tsv
  out_U2_{TAG_COND}_1k/eval_run{N}.json   (regression)
  out_U2_{TAG_COND}_warmup/eval_run{N}.json

出力:
  u2_stats.csv
  u2_pivot.md
  ttft_vs_cache_ram.png
  cache_hit_rate_vs_size.png
  eval_tps_drift.png
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# 固定構成 (B14b_ts_alt 継承)
KV = "q8_0"
SM = "layer"
CTX = 32768
UB = 256
THR = 40
OT_TAG = "B14b"
TS = "11,12,13,14"
WARMUP_RUNS = 2
EVAL_RUNS = 5
N_HITS = 4

CACHE_RAM_VALUES = [0, 128, 256, 512, 1024, 2048]

# Cross-session 比較 (既存 Phase 歴代)
BASELINE_T5A_TS2_B14B = 18.664   # Phase T-5a-ts2 B14b_ts_alt (cache_ram=default 8192)
BASELINE_T5A_TS_BEST = 18.417    # Phase T-5a-ts best
BASELINE_T5A_UB = 18.103         # Phase T-5a-ub
BASELINE_PHASE_D = 15.030        # Phase D (古い)
PHASE_U1_CONFIG_A = None         # U-1 Config A (OOM で未完走)
PHASE_U1_EXT_BEST = 13.145       # U-1-ext spec ON (-21〜-33% 遅延)


def ts_tag(ts: str) -> str:
    return ("_ts" + ts.replace(",", "-")) if ts else ""


def cond_tag(cache_ram: int) -> str:
    return f"{OT_TAG}_t{THR}_kv{KV}_sm{SM}_ctx{CTX}_ub{UB}{ts_tag(TS)}_cram{cache_ram}"


def load_tsv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        return list(reader)


def load_eval_run(outdir: Path, run: int) -> dict:
    p = outdir / f"eval_run{run}.json"
    if not p.exists():
        return {}
    try:
        with p.open() as f:
            data = json.load(f)
    except Exception:
        return {}
    t = data.get("timings", {})
    return {
        "eval_tps": t.get("predicted_per_second"),
        "prompt_tps": t.get("prompt_per_second"),
        "prompt_n": t.get("prompt_n"),
        "predicted_n": t.get("predicted_n"),
        "cache_n": t.get("cache_n"),
        "prompt_ms": t.get("prompt_ms"),
    }


def stats(values):
    vs = [float(v) for v in values if v is not None and v != "" and v != "n/a"]
    if not vs:
        return None
    return {
        "n": len(vs),
        "mean": statistics.mean(vs),
        "stdev": statistics.pstdev(vs) if len(vs) < 2 else statistics.stdev(vs),
        "min": min(vs),
        "max": max(vs),
        "median": statistics.median(vs),
    }


def safe_float(x):
    try:
        if x is None or x == "" or x == "n/a":
            return None
        return float(x)
    except (ValueError, TypeError):
        return None


def collect() -> dict:
    """Collect per-cache-ram data: {cache_ram: {ttft:[], prefix:[], eval:[], warmup:[]}}"""
    result = {}
    for cram in CACHE_RAM_VALUES:
        tag = cond_tag(cram)
        # batch_U2.sh では TAG_PREFIX="U2_${TAG_COND}" で run_all_U2.sh を呼ぶ。
        # run_all_U2.sh は ${TAG_PREFIX}_warmup / _1k を measure_phaseT5.sh に渡す。
        # measure_phaseT5.sh は OUTDIR=./out_${TAG} を作成。
        # → 実ディレクトリは out_U2_${TAG_COND}_warmup, out_U2_${TAG_COND}_1k
        ttft_dir = SCRIPT_DIR / f"out_U2_{tag}_ttft"
        prefix_dir = SCRIPT_DIR / f"out_U2_{tag}_prefix"
        eval_dir = SCRIPT_DIR / f"out_U2_{tag}_1k"
        warmup_dir = SCRIPT_DIR / f"out_U2_{tag}_warmup"

        ttft = load_tsv(ttft_dir / "ttft_summary.tsv")
        prefix = load_tsv(prefix_dir / "prefix_summary.tsv")
        eval_runs = [load_eval_run(eval_dir, r) for r in range(1, EVAL_RUNS + 1)]
        warmup_runs = [load_eval_run(warmup_dir, r) for r in range(1, WARMUP_RUNS + 1)]

        result[cram] = {
            "ttft": ttft,
            "prefix": prefix,
            "eval": [e for e in eval_runs if e],
            "warmup": [w for w in warmup_runs if w],
            "ttft_dir": str(ttft_dir),
            "prefix_dir": str(prefix_dir),
            "eval_dir": str(eval_dir),
        }
    return result


def write_stats_csv(data: dict, path: Path):
    with path.open("w") as f:
        w = csv.writer(f)
        w.writerow([
            "cache_ram", "run_kind", "run_id", "prompt_n", "cache_n",
            "cache_hit_ratio", "prompt_ms", "predicted_ms", "eval_tps", "wall_ms"
        ])
        for cram, d in data.items():
            # TTFT runs
            for row in d["ttft"]:
                pn = safe_float(row.get("prompt_n"))
                cn = safe_float(row.get("cache_n"))
                hit = (cn / pn) if (pn and cn is not None) else None
                w.writerow([
                    cram, f"ttft_{row.get('kind','?')}", row.get("run"),
                    row.get("prompt_n"), row.get("cache_n"),
                    f"{hit:.4f}" if hit is not None else "",
                    row.get("prompt_ms"), row.get("predicted_ms"),
                    row.get("eval_tps"), row.get("wall_ms"),
                ])
            # Prefix runs
            for row in d["prefix"]:
                pn = safe_float(row.get("prompt_n"))
                cn = safe_float(row.get("cache_n"))
                hit = (cn / pn) if (pn and cn is not None) else None
                w.writerow([
                    cram, f"prefix_{row.get('suffix_id','?')}", row.get("idx"),
                    row.get("prompt_n"), row.get("cache_n"),
                    f"{hit:.4f}" if hit is not None else "",
                    row.get("prompt_ms"), row.get("predicted_ms"),
                    row.get("eval_tps"), row.get("wall_ms"),
                ])
            # Eval regression (marker 付き、cache miss 強制)
            for k, e in enumerate(d["eval"], start=1):
                pn = e.get("prompt_n")
                cn = e.get("cache_n")
                hit = (cn / pn) if (pn and cn is not None) else None
                w.writerow([
                    cram, "eval_regression", k,
                    pn, cn,
                    f"{hit:.4f}" if hit is not None else "",
                    e.get("prompt_ms"), "", e.get("eval_tps"), "",
                ])
    print(f"[analyze] wrote {path}")


def write_pivot(data: dict, path: Path):
    with path.open("w") as f:
        f.write("# Phase U-2: --cache-ram (PR #16391) pivot\n\n")
        f.write(f"- 固定構成: B14b_ts_alt (OT-b, ts={TS}, ctx={CTX}, ub={UB}, kv={KV}, sm={SM}, thr={THR}, fa=1, numactl node1, poll=0)\n")
        f.write(f"- 軸: `--cache-ram` ∈ {CACHE_RAM_VALUES} MiB\n")
        f.write(f"- TTFT: 同一 prompt (system_fixed.txt ~570 tok) を miss (Run 0) + hit {N_HITS} 連投\n")
        f.write(f"- Prefix: 固定 system + 5 pattern user suffix (shared prefix hit)\n")
        f.write(f"- Eval regression: marker 付き 1k prompt warmup {WARMUP_RUNS} + eval {EVAL_RUNS} (cache miss 強制)\n\n")

        f.write(f"## Cross-session baseline\n")
        f.write(f"- Phase T-5a-ts2 B14b_ts_alt (cache_ram=default 8192): **{BASELINE_T5A_TS2_B14B} t/s** (歴代最高)\n")
        f.write(f"- Phase T-5a-ts best: {BASELINE_T5A_TS_BEST} t/s\n")
        f.write(f"- Phase T-5a-ub: {BASELINE_T5A_UB} t/s\n")
        f.write(f"- Phase U-1 Config A (spec ON + cram=256): OOM, 未完走\n")
        f.write(f"- Phase U-1-ext spec ON 最良: {PHASE_U1_EXT_BEST} t/s (-21〜-33% vs OFF)\n\n")

        # Section A: TTFT
        f.write("## (A) TTFT: 同一 prompt 連投 (prompt_ms median, lower is better)\n\n")
        f.write("| cache_ram | Run 0 (miss) | Run 1 (hit) | Run 2 (hit) | Run 3 (hit) | Run 4 (hit) | hit / miss 比 | cache_n (Run 1) |\n")
        f.write("|-----------|--------------|-------------|-------------|-------------|-------------|----------------|------------------|\n")
        for cram in CACHE_RAM_VALUES:
            ttft_rows = {int(r["run"]): r for r in data[cram]["ttft"] if r.get("run", "").isdigit()}
            cells = []
            miss_ms = None
            hit_ms_list = []
            cache_n_r1 = None
            for r in range(0, N_HITS + 1):
                row = ttft_rows.get(r)
                if row is None:
                    cells.append("n/a")
                    continue
                pm = safe_float(row.get("prompt_ms"))
                if pm is None:
                    cells.append("n/a")
                    continue
                cells.append(f"{pm:.1f}")
                if r == 0:
                    miss_ms = pm
                else:
                    hit_ms_list.append(pm)
                if r == 1:
                    cache_n_r1 = row.get("cache_n")
            if miss_ms and hit_ms_list:
                ratio = (statistics.median(hit_ms_list) / miss_ms) * 100
                ratio_str = f"{ratio:.1f}%"
            else:
                ratio_str = "n/a"
            cn_str = cache_n_r1 if cache_n_r1 is not None else "n/a"
            f.write(f"| {cram} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} | {cells[4]} | {ratio_str} | {cn_str} |\n")
        f.write("\n")

        # Section B: Prefix
        f.write("## (B) Shared-prefix: 固定 system + 5 suffix (prompt_ms / cache_n)\n\n")
        # 各 cache_ram 行
        f.write("| cache_ram | s1 (ms / cache_n) | s2 | s3 | s4 | s5 |\n")
        f.write("|-----------|-------------------|-----|-----|-----|-----|\n")
        for cram in CACHE_RAM_VALUES:
            cells = []
            for row in data[cram]["prefix"]:
                pm = safe_float(row.get("prompt_ms"))
                cn = row.get("cache_n", "n/a")
                cells.append(f"{pm:.1f} / {cn}" if pm is not None else f"n/a / {cn}")
            while len(cells) < 5:
                cells.append("n/a")
            f.write(f"| {cram} | " + " | ".join(cells[:5]) + " |\n")
        f.write("\n")

        # Section C: Regression eval
        f.write("## (C) Eval regression: marker 付き 1k (cache miss 強制)\n\n")
        f.write("| cache_ram | eval_mean ± stdev | eval_median | prompt_tps median | drift vs B14b (18.664) | drift pct |\n")
        f.write("|-----------|--------------------|-------------|-------------------|-------------------------|-----------|\n")
        for cram in CACHE_RAM_VALUES:
            ev_values = [safe_float(e.get("eval_tps")) for e in data[cram]["eval"]]
            se = stats(ev_values)
            if se is None:
                f.write(f"| {cram} | no_data | -- | -- | -- | -- |\n")
                continue
            prompt_tps = [safe_float(e.get("prompt_tps")) for e in data[cram]["eval"]]
            sp = stats(prompt_tps)
            prompt_med = f"{sp['median']:.2f}" if sp else "n/a"
            drift = se["mean"] - BASELINE_T5A_TS2_B14B
            drift_pct = drift / BASELINE_T5A_TS2_B14B * 100
            # 正方向 drift は問題なし。負方向のみ regression として警告
            flag = ""
            if drift_pct >= -0.5:
                flag = " ✅"
            elif drift_pct >= -1.0:
                flag = " ⚠️"
            else:
                flag = " ❌"
            f.write(f"| {cram} | {se['mean']:.3f} ± {se['stdev']:.3f} | {se['median']:.3f} | {prompt_med} | {drift:+.3f}{flag} | {drift_pct:+.2f}% |\n")
        f.write("\n")

        # Best cache ram for TTFT
        f.write("## 結果サマリ\n\n")
        best_ttft = None
        best_hit_ms = None
        for cram in CACHE_RAM_VALUES:
            ttft_rows = {int(r["run"]): r for r in data[cram]["ttft"] if r.get("run", "").isdigit()}
            hits = [safe_float(ttft_rows[r].get("prompt_ms")) for r in range(1, N_HITS + 1) if r in ttft_rows]
            hits = [h for h in hits if h is not None]
            if not hits:
                continue
            med = statistics.median(hits)
            if best_hit_ms is None or med < best_hit_ms:
                best_hit_ms = med
                best_ttft = cram

        if best_ttft is not None:
            f.write(f"- **TTFT 最良** (hit median): cache_ram={best_ttft} MiB, prompt_ms={best_hit_ms:.1f}\n")

        # Report eval regression range
        eval_means = []
        for cram in CACHE_RAM_VALUES:
            ev = [safe_float(e.get("eval_tps")) for e in data[cram]["eval"]]
            s = stats(ev)
            if s:
                eval_means.append((cram, s["mean"]))
        if eval_means:
            best_ev = max(eval_means, key=lambda x: x[1])
            worst_ev = min(eval_means, key=lambda x: x[1])
            f.write(f"- **eval 最大**: cache_ram={best_ev[0]}, eval={best_ev[1]:.3f} t/s (B14b 18.664 比 {best_ev[1]-BASELINE_T5A_TS2_B14B:+.3f})\n")
            f.write(f"- **eval 最小**: cache_ram={worst_ev[0]}, eval={worst_ev[1]:.3f} t/s (B14b 18.664 比 {worst_ev[1]-BASELINE_T5A_TS2_B14B:+.3f})\n")
            eval_range = best_ev[1] - worst_ev[1]
            f.write(f"- eval 振れ幅: {eval_range:.3f} t/s ({eval_range/BASELINE_T5A_TS2_B14B*100:.2f}%)\n")

    print(f"[analyze] wrote {path}")


def plot_all(data: dict):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[analyze] matplotlib not available, skipping PNG", file=sys.stderr)
        return

    # Plot 1: TTFT vs cache_ram
    fig, ax = plt.subplots(figsize=(8, 5))
    cram_x = []
    miss_ms = []
    hit_med_ms = []
    hit_min_ms = []
    hit_max_ms = []
    for cram in CACHE_RAM_VALUES:
        ttft_rows = {int(r["run"]): r for r in data[cram]["ttft"] if r.get("run", "").isdigit()}
        miss = safe_float(ttft_rows.get(0, {}).get("prompt_ms"))
        hits = [safe_float(ttft_rows[r].get("prompt_ms")) for r in range(1, N_HITS + 1) if r in ttft_rows]
        hits = [h for h in hits if h is not None]
        cram_x.append(cram)
        miss_ms.append(miss if miss else float("nan"))
        if hits:
            hit_med_ms.append(statistics.median(hits))
            hit_min_ms.append(min(hits))
            hit_max_ms.append(max(hits))
        else:
            hit_med_ms.append(float("nan"))
            hit_min_ms.append(float("nan"))
            hit_max_ms.append(float("nan"))
    ax.plot(cram_x, miss_ms, marker="o", label="miss (Run 0)", color="C3")
    ax.plot(cram_x, hit_med_ms, marker="s", label=f"hit median (Run 1..{N_HITS})", color="C0")
    import numpy as np
    low_err = [m - lo if (m == m and lo == lo) else 0 for m, lo in zip(hit_med_ms, hit_min_ms)]
    high_err = [hi - m if (m == m and hi == hi) else 0 for m, hi in zip(hit_med_ms, hit_max_ms)]
    try:
        ax.errorbar(cram_x, hit_med_ms, yerr=[low_err, high_err], fmt="none", ecolor="C0", alpha=0.4)
    except Exception:
        pass
    ax.set_xlabel("cache-ram (MiB)")
    ax.set_ylabel("prompt_ms (TTFT proxy)")
    ax.set_title("TTFT vs --cache-ram (B14b_ts_alt, same prompt repeated)")
    ax.set_xscale("symlog", linthresh=64)
    ax.set_xticks(cram_x)
    ax.set_xticklabels([str(c) for c in cram_x])
    ax.grid(True, alpha=0.3)
    ax.legend()
    out1 = SCRIPT_DIR / "ttft_vs_cache_ram.png"
    fig.tight_layout()
    fig.savefig(out1, dpi=120)
    plt.close(fig)
    print(f"[analyze] wrote {out1}")

    # Plot 2: cache hit rate vs size
    fig, ax = plt.subplots(figsize=(8, 5))
    ttft_hit_ratios = []
    prefix_hit_ratios = []
    for cram in CACHE_RAM_VALUES:
        ttft_rows = {int(r["run"]): r for r in data[cram]["ttft"] if r.get("run", "").isdigit()}
        ratios = []
        for r in range(1, N_HITS + 1):
            if r not in ttft_rows:
                continue
            pn = safe_float(ttft_rows[r].get("prompt_n"))
            cn = safe_float(ttft_rows[r].get("cache_n"))
            if pn and cn is not None:
                ratios.append(cn / pn)
        ttft_hit_ratios.append(statistics.median(ratios) if ratios else float("nan"))
        # prefix ratios (2nd..5th, 1st は miss)
        p_ratios = []
        for i, row in enumerate(data[cram]["prefix"][1:], start=2):
            pn = safe_float(row.get("prompt_n"))
            cn = safe_float(row.get("cache_n"))
            if pn and cn is not None:
                p_ratios.append(cn / pn)
        prefix_hit_ratios.append(statistics.median(p_ratios) if p_ratios else float("nan"))
    ax.plot(cram_x, ttft_hit_ratios, marker="o", label="TTFT (same prompt repeat)")
    ax.plot(cram_x, prefix_hit_ratios, marker="s", label="Prefix (shared system + vary suffix)")
    ax.set_xlabel("cache-ram (MiB)")
    ax.set_ylabel("cache_n / prompt_n (hit ratio)")
    ax.set_title("Cache hit ratio vs --cache-ram")
    ax.set_xscale("symlog", linthresh=64)
    ax.set_xticks(cram_x)
    ax.set_xticklabels([str(c) for c in cram_x])
    ax.set_ylim(-0.05, 1.05)
    ax.grid(True, alpha=0.3)
    ax.legend()
    out2 = SCRIPT_DIR / "cache_hit_rate_vs_size.png"
    fig.tight_layout()
    fig.savefig(out2, dpi=120)
    plt.close(fig)
    print(f"[analyze] wrote {out2}")

    # Plot 3: Eval regression drift
    fig, ax = plt.subplots(figsize=(8, 5))
    eval_means = []
    eval_stdevs = []
    for cram in CACHE_RAM_VALUES:
        ev = [safe_float(e.get("eval_tps")) for e in data[cram]["eval"]]
        s = stats(ev)
        eval_means.append(s["mean"] if s else float("nan"))
        eval_stdevs.append(s["stdev"] if s else 0.0)
    ax.errorbar(cram_x, eval_means, yerr=eval_stdevs, marker="o", capsize=4, label="Phase U-2 B14b_ts_alt")
    ax.axhline(BASELINE_T5A_TS2_B14B, color="C2", linestyle="--", label=f"T-5a-ts2 B14b baseline ({BASELINE_T5A_TS2_B14B})")
    ax.axhline(BASELINE_T5A_TS2_B14B * 0.995, color="C2", linestyle=":", alpha=0.5, label="±0.5%")
    ax.axhline(BASELINE_T5A_TS2_B14B * 1.005, color="C2", linestyle=":", alpha=0.5)
    ax.set_xlabel("cache-ram (MiB)")
    ax.set_ylabel("eval_tps (t/s)")
    ax.set_title("Eval regression: 1k prompt with marker (cache miss forced)")
    ax.set_xscale("symlog", linthresh=64)
    ax.set_xticks(cram_x)
    ax.set_xticklabels([str(c) for c in cram_x])
    ax.grid(True, alpha=0.3)
    ax.legend()
    out3 = SCRIPT_DIR / "eval_tps_drift.png"
    fig.tight_layout()
    fig.savefig(out3, dpi=120)
    plt.close(fig)
    print(f"[analyze] wrote {out3}")


def main() -> int:
    data = collect()
    # Debug summary
    for cram, d in data.items():
        print(f"  cache_ram={cram}: ttft={len(d['ttft'])} prefix={len(d['prefix'])} eval={len(d['eval'])}")
    write_stats_csv(data, SCRIPT_DIR / "u2_stats.csv")
    write_pivot(data, SCRIPT_DIR / "u2_pivot.md")
    plot_all(data)
    with (SCRIPT_DIR / "u2_pivot.md").open() as f:
        print(f.read())
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
