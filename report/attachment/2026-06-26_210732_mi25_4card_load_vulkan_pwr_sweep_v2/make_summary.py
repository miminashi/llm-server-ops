#!/usr/bin/env python3
"""mi25 4枚 Vulkan 負荷 — 電力スイープ集計 + summary.png 生成。
11 電力点 (140-190W / 5W) の trials_*.jsonl + kern_dmesg_*.log + telemetry_rocmsmi_*.log を集計し、
電力 vs time-to-fault / eval_tps / power_p95 / junction_temp_max の表と PNG を生成する。"""
import json
import os
import re
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SCR = os.path.dirname(os.path.abspath(__file__))
WATTS_LIST = [190, 185, 180, 175, 170, 165, 160, 155, 150, 145, 140]
PHASE_CAP_SEC = 3000

FAULT_PATTERNS = re.compile(
    r"(amdgpu_job_timedout|GPU reset begin|VRAM is lost|no-retry page fault|Memory access fault)"
)
BDF_PATTERN = re.compile(r"amdgpu (0000:[0-9a-f]+:[0-9a-f]+\.[0-9])")
POWER_PATTERN = re.compile(r"Current Socket Graphics Package Power \(W\):\s*([\d.]+)")
TEMP_PATTERN = re.compile(r"Temperature \(Sensor junction\) \(C\):\s*([\d.]+)")


def parse_trials(path):
    if not os.path.exists(path):
        return None
    trial_start_epoch = None
    fault_epoch = None
    fault_event = None
    trial_done_count = 0
    eval_tps_vals = []
    pp_tps_vals = []
    with open(path) as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            ev = obj.get("event")
            ep = obj.get("epoch")
            if ev == "trial_start" and trial_start_epoch is None:
                trial_start_epoch = ep
            if ev in ("HANG_CONFIRMED", "server_error_transient", "NETWORK_OUTAGE", "stall") and fault_epoch is None:
                fault_epoch = ep
                fault_event = ev
            if ev == "trial_done":
                trial_done_count += 1
            if ev == "turn":
                ev_t = obj.get("eval_tps")
                pp_t = obj.get("pp_tps")
                if ev_t:
                    eval_tps_vals.append(ev_t)
                if pp_t:
                    pp_tps_vals.append(pp_t)
    t2f = None
    if trial_start_epoch is not None and fault_epoch is not None:
        t2f = fault_epoch - trial_start_epoch
    return {
        "trials_completed": trial_done_count,
        "time_to_fault_s": t2f,
        "fault_event": fault_event,
        "eval_tps_mean": statistics.mean(eval_tps_vals) if eval_tps_vals else None,
        "pp_tps_mean": statistics.mean(pp_tps_vals) if pp_tps_vals else None,
        "turn_samples": len(eval_tps_vals),
    }


def parse_dmesg(path):
    if not os.path.exists(path):
        return None
    sig = None
    bdf = None
    fault_lines = 0
    with open(path, errors="replace") as f:
        for line in f:
            m = FAULT_PATTERNS.search(line)
            if m:
                fault_lines += 1
                if sig is None:
                    sig = m.group(1)
            mb = BDF_PATTERN.search(line)
            if mb and bdf is None and FAULT_PATTERNS.search(line):
                bdf = mb.group(1)
    return {"fault_signature": sig, "fault_card_bdf": bdf, "fault_lines_count": fault_lines}


def parse_telemetry_rocmsmi(path):
    if not os.path.exists(path):
        return None
    gpu3_power = []
    all_power_max = []
    gpu3_temp = []
    all_temp_max = []
    current = {0: {}, 1: {}, 2: {}, 3: {}}

    def flush():
        ps = [current[i].get("power") for i in range(4) if current[i].get("power") is not None]
        ts = [current[i].get("temp") for i in range(4) if current[i].get("temp") is not None]
        if ps:
            all_power_max.append(max(ps))
        if ts:
            all_temp_max.append(max(ts))
        if current[3].get("power") is not None:
            gpu3_power.append(current[3]["power"])
        if current[3].get("temp") is not None:
            gpu3_temp.append(current[3]["temp"])

    with open(path, errors="replace") as f:
        for line in f:
            if line.startswith("===== epoch="):
                flush()
                current = {0: {}, 1: {}, 2: {}, 3: {}}
                continue
            mg = re.match(r"GPU\[(\d)\]\s*:", line)
            if not mg:
                continue
            idx = int(mg.group(1))
            if idx not in current:
                continue
            mp = POWER_PATTERN.search(line)
            mt = TEMP_PATTERN.search(line)
            if mp:
                current[idx]["power"] = float(mp.group(1))
            if mt:
                current[idx]["temp"] = float(mt.group(1))
    flush()

    def pct(arr, p):
        return float(np.percentile(arr, p)) if arr else None

    return {
        "power_w_p95_max": pct(all_power_max, 95),
        "power_w_p95_gpu3": pct(gpu3_power, 95),
        "junction_temp_max_max": max(all_temp_max) if all_temp_max else None,
        "junction_temp_max_gpu3": max(gpu3_temp) if gpu3_temp else None,
        "samples": len(all_power_max),
    }


def fmt(v, dec=1):
    if v is None:
        return "—"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return f"{v:.{dec}f}"
    return str(v)


def main():
    rows = []
    for w in WATTS_LIST:
        tag = f"p{w}W"
        trials = parse_trials(os.path.join(SCR, f"trials_vulkan_{tag}.jsonl")) or {}
        dmesg = parse_dmesg(os.path.join(SCR, f"kern_dmesg_{tag}.log")) or {}
        rocm = parse_telemetry_rocmsmi(os.path.join(SCR, f"telemetry_rocmsmi_{tag}.log")) or {}
        rows.append({
            "watts": w,
            "trials_completed": trials.get("trials_completed"),
            "time_to_fault_s": trials.get("time_to_fault_s"),
            "fault_event": trials.get("fault_event"),
            "eval_tps_mean": trials.get("eval_tps_mean"),
            "pp_tps_mean": trials.get("pp_tps_mean"),
            "fault_signature": dmesg.get("fault_signature"),
            "fault_card_bdf": dmesg.get("fault_card_bdf"),
            "fault_lines_count": dmesg.get("fault_lines_count"),
            "power_w_p95_max": rocm.get("power_w_p95_max"),
            "power_w_p95_gpu3": rocm.get("power_w_p95_gpu3"),
            "junction_temp_max_max": rocm.get("junction_temp_max_max"),
            "junction_temp_max_gpu3": rocm.get("junction_temp_max_gpu3"),
            "rocm_samples": rocm.get("samples"),
        })

    with open(os.path.join(SCR, "data.md"), "w") as f:
        f.write("# mi25 4 枚 Vulkan 負荷 — 電力スイープ集計表\n\n")
        f.write("| W | trials_done | t2f [s] | fault_event | fault_sig | fault_bdf | eval [t/s] | pp [t/s] | "
                "power_p95_max [W] | power_p95_gpu3 [W] | Tj_max_max [°C] | Tj_max_gpu3 [°C] |\n")
        f.write("|---|---:|---:|---|---|---|---:|---:|---:|---:|---:|---:|\n")
        for r in rows:
            f.write(
                f"| {r['watts']} | {fmt(r['trials_completed'])} | {fmt(r['time_to_fault_s'], 0)} | "
                f"{fmt(r['fault_event'])} | {fmt(r['fault_signature'])} | {fmt(r['fault_card_bdf'])} | "
                f"{fmt(r['eval_tps_mean'])} | {fmt(r['pp_tps_mean'])} | "
                f"{fmt(r['power_w_p95_max'])} | {fmt(r['power_w_p95_gpu3'])} | "
                f"{fmt(r['junction_temp_max_max'], 0)} | {fmt(r['junction_temp_max_gpu3'], 0)} |\n"
            )

    fig, ax1 = plt.subplots(figsize=(13, 6.2))
    xs = [r["watts"] for r in rows]
    t2f_vals = [r["time_to_fault_s"] if r["time_to_fault_s"] is not None else PHASE_CAP_SEC for r in rows]
    t2f_capped = [r["time_to_fault_s"] is None for r in rows]
    colors = ["#3aa055" if c else "#d83a3a" for c in t2f_capped]
    eval_vals = [r["eval_tps_mean"] for r in rows]

    bars = ax1.bar(xs, t2f_vals, width=3.5, color=colors, edgecolor="black", linewidth=0.6, alpha=0.85)
    for b, capped, v in zip(bars, t2f_capped, t2f_vals):
        lbl = "PASS" if capped else f"{int(v)}s"
        ax1.text(b.get_x() + b.get_width() / 2, v + 50, lbl, ha="center", va="bottom",
                 fontsize=9, fontweight="bold", color=("#207040" if capped else "#a02020"))
    ax1.axhline(y=PHASE_CAP_SEC, color="gray", linestyle="--", alpha=0.45, linewidth=1)
    ax1.text(140.5, PHASE_CAP_SEC + 30, f"PHASE_CAP={PHASE_CAP_SEC}s",
             fontsize=8, color="gray", va="bottom")
    ax1.set_xlabel("GPU Power Cap [W]", fontsize=11)
    ax1.set_ylabel("Time to Fault [s] (green = PASS / no fault, red = fault)", fontsize=11)
    ax1.set_xticks(xs)
    ax1.set_xlim(137.5, 192.5)
    ax1.set_ylim(0, max(PHASE_CAP_SEC * 1.25, max(t2f_vals or [0]) * 1.2 or 1))
    ax1.grid(axis="y", alpha=0.3)

    ax2 = ax1.twinx()
    valid = [(x, v) for x, v in zip(xs, eval_vals) if v is not None]
    if valid:
        xs2, ys2 = zip(*valid)
        ax2.plot(xs2, ys2, "o-", color="#2060a0", linewidth=2, markersize=7, label="eval [t/s]")
        ax2.set_ylabel("Eval Throughput [t/s] (blue line)", fontsize=11, color="#2060a0")
        ax2.tick_params(axis="y", labelcolor="#2060a0")

    plt.title("mi25 4-card Vulkan load — time-to-fault vs GPU power cap (140-190W sweep)\n"
              f"Qwen3.6-35B-A3B Q4_K_XL, ctx=131072, {len(WATTS_LIST)} power points x MAX_TRIALS=4",
              fontsize=11.5, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(SCR, "summary.png"), dpi=130, bbox_inches="tight")
    print("summary.png + data.md written")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
