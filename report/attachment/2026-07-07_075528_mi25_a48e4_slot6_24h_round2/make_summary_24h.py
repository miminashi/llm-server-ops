#!/usr/bin/env python3
"""mi25 a48e4 SLOT6 / Vulkan stand-alone 24h+ 負荷 — 集計 + summary.png。
make_summary_slot_move.py (8h 版) から派生。差分:
- 8h → 24h+ (PHASE_CAP_SEC=86400、状況見て延長)
- 過去 2 種類との Fisher 比較 (4 枚運用 88/3 と stand_alone_24h SLOT6 147/2) 流用
"""
import json
import math
import os
import re
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SCR = os.path.dirname(os.path.abspath(__file__))

# 比較対象 (両方とのFisher検定を出す)
PAST_4CARD_FAULTS = 3
PAST_4CARD_TRIALS = 88
PAST_SA_FAULTS = 2
PAST_SA_TRIALS = 147

TARGET_GPU_IDX = 3  # a48e4 = GPU[3] (BDF 87:00.0 = SLOT6)

FAULT_PATTERNS = re.compile(
    r"(amdgpu_job_timedout|GPU reset begin|VRAM is lost|no-retry page fault|Memory access fault)"
)
BDF_PATTERN = re.compile(r"amdgpu (0000:[0-9a-f]+:[0-9a-f]+\.[0-9])")
POWER_PATTERN = re.compile(r"Current Socket Graphics Package Power \(W\):\s*([\d.]+)")
TEMP_PATTERN = re.compile(r"Temperature \(Sensor junction\) \(C\):\s*([\d.]+)")


def parse_trials(path):
    if not os.path.exists(path):
        return None
    events = []
    with open(path) as f:
        for line in f:
            try:
                events.append(json.loads(line))
            except Exception:
                continue
    if not events:
        return None
    start_epoch = events[0].get("epoch")
    end_epoch = events[-1].get("epoch")
    trials_done = 0
    hangs = 0
    stalls = 0
    network_outages = 0
    trial_done_epochs = []
    hang_epochs = []
    fault_epochs = []
    eval_tps_vals = []
    pp_tps_vals = []
    turn_epochs = []
    for obj in events:
        ev = obj.get("event")
        ep = obj.get("epoch")
        if ev == "trial_done":
            trials_done += 1
            trial_done_epochs.append(ep)
        elif ev == "HANG_CONFIRMED":
            hangs += 1
            hang_epochs.append(ep)
            fault_epochs.append(ep)
        elif ev == "stall":
            stalls += 1
            if obj.get("outage_status") == "HOST_HANG":
                fault_epochs.append(ep)
        elif ev == "NETWORK_OUTAGE":
            network_outages += 1
        elif ev == "turn":
            ev_t = obj.get("eval_tps")
            pp_t = obj.get("pp_tps")
            if ev_t:
                eval_tps_vals.append(ev_t)
            if pp_t:
                pp_tps_vals.append(pp_t)
            turn_epochs.append(ep)
    return {
        "start_epoch": start_epoch,
        "end_epoch": end_epoch,
        "duration_s": end_epoch - start_epoch if start_epoch and end_epoch else None,
        "trials_done": trials_done,
        "hangs": hangs,
        "stalls": stalls,
        "network_outages": network_outages,
        "trial_done_epochs": trial_done_epochs,
        "hang_epochs": hang_epochs,
        "fault_epochs": fault_epochs,
        "turn_count": len(turn_epochs),
        "eval_tps_mean": statistics.mean(eval_tps_vals) if eval_tps_vals else None,
        "eval_tps_p50": float(np.percentile(eval_tps_vals, 50)) if eval_tps_vals else None,
        "pp_tps_mean": statistics.mean(pp_tps_vals) if pp_tps_vals else None,
        "turn_epochs": turn_epochs,
        "eval_tps_vals": eval_tps_vals,
    }


def parse_dmesg(path, baseline_lines=0):
    if not os.path.exists(path):
        return None
    fault_events = []
    sig_counter = {}
    bdf_counter = {}
    line_no = 0
    with open(path, errors="replace") as f:
        for line in f:
            line_no += 1
            if line_no <= baseline_lines:
                continue
            m = FAULT_PATTERNS.search(line)
            if m:
                sig = m.group(1)
                sig_counter[sig] = sig_counter.get(sig, 0) + 1
                mb = BDF_PATTERN.search(line)
                bdf = mb.group(1) if mb else "?"
                bdf_counter[bdf] = bdf_counter.get(bdf, 0) + 1
                fault_events.append({"sig": sig, "bdf": bdf, "line": line.rstrip()})
    return {
        "fault_events": fault_events,
        "fault_count": len(fault_events),
        "signatures": sig_counter,
        "bdfs": bdf_counter,
        "total_lines": line_no,
        "baseline_lines": baseline_lines,
    }


def parse_telemetry_rocmsmi(path, target_idx=TARGET_GPU_IDX):
    if not os.path.exists(path):
        return None
    target_power = []
    target_temp = []
    target_power_epochs = []
    current = {i: {} for i in range(4)}
    current_epoch = None

    def flush():
        if current_epoch is None:
            return
        if current[target_idx].get("power") is not None:
            target_power.append(current[target_idx]["power"])
            target_power_epochs.append(current_epoch)
        if current[target_idx].get("temp") is not None:
            target_temp.append(current[target_idx]["temp"])

    epoch_pat = re.compile(r"===== epoch=(\d+)")
    with open(path, errors="replace") as f:
        for line in f:
            me = epoch_pat.match(line)
            if me:
                flush()
                current_epoch = int(me.group(1))
                current = {i: {} for i in range(4)}
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
        "samples": len(target_power),
        "target_power_w_mean": statistics.mean(target_power) if target_power else None,
        "target_power_w_p95": pct(target_power, 95),
        "target_power_w_max": max(target_power) if target_power else None,
        "target_temp_max": max(target_temp) if target_temp else None,
        "target_power_epochs": target_power_epochs,
        "target_power_vals": target_power,
    }


def parse_telemetry_pcie(path):
    if not os.path.exists(path):
        return None
    aer_total = {"cor": 0, "fatal": 0, "nfatal": 0}
    samples = 0
    non_x16 = 0
    gpu_count_min = None
    with open(path, errors="replace") as f:
        for line in f:
            if line.startswith("===== epoch="):
                samples += 1
                continue
            m = re.match(r"PORT=(\S+) W=(\S+) SP=(\S+) PD=(\S+) COR=(\S+) FAT=(\S+) NFT=(\S+)", line)
            if m:
                w = m.group(2)
                cor = m.group(5)
                fat = m.group(6)
                nft = m.group(7)
                if w not in ("Widthx16", "?"):
                    non_x16 += 1
                try:
                    aer_total["cor"] = max(aer_total["cor"], int(cor))
                except ValueError:
                    pass
                try:
                    aer_total["fatal"] = max(aer_total["fatal"], int(fat))
                except ValueError:
                    pass
                try:
                    aer_total["nfatal"] = max(aer_total["nfatal"], int(nft))
                except ValueError:
                    pass
                continue
            mg = re.match(r"GPU_COUNT=(\d+)", line)
            if mg:
                gc = int(mg.group(1))
                if gpu_count_min is None or gc < gpu_count_min:
                    gpu_count_min = gc
    return {
        "samples": samples,
        "non_x16_entries": non_x16,
        "aer_cor_max": aer_total["cor"],
        "aer_fatal_max": aer_total["fatal"],
        "aer_nfatal_max": aer_total["nfatal"],
        "gpu_count_min": gpu_count_min,
    }


def fisher_exact_one_sided(a, b, c, d):
    n = a + b + c + d
    total_fault = a + c
    n_current = a + b
    def log_choose(n, k):
        if k < 0 or k > n:
            return -math.inf
        return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
    def hyper_logp(k):
        return log_choose(n_current, k) + log_choose(n - n_current, total_fault - k) - log_choose(n, total_fault)
    log_terms = [hyper_logp(k) for k in range(0, a + 1)]
    log_terms = [t for t in log_terms if t > -math.inf]
    if not log_terms:
        return 1.0
    lmax = max(log_terms)
    return math.exp(lmax) * sum(math.exp(t - lmax) for t in log_terms)


def main():
    trials_path = os.path.join(SCR, "trials_vulkan.jsonl")
    dmesg_path = os.path.join(SCR, "kern_dmesg.log")
    rocm_path = os.path.join(SCR, "telemetry_rocmsmi.log")
    pcie_path = os.path.join(SCR, "telemetry_pcie.log")

    baseline_lines = 2319  # R2: pre_r2_baseline.txt に記録 (a48e4-slot6-24h-r2)

    t = parse_trials(trials_path) or {}
    d = parse_dmesg(dmesg_path, baseline_lines=baseline_lines) or {}
    r = parse_telemetry_rocmsmi(rocm_path) or {}
    p = parse_telemetry_pcie(pcie_path) or {}

    n_trials = t.get("trials_done", 0)
    dmesg_gpu_resets = d.get("signatures", {}).get("GPU reset begin", 0)
    n_faults = max(t.get("hangs", 0), dmesg_gpu_resets)
    duration_h = (t.get("duration_s") or 0) / 3600.0

    p_vs_4card = fisher_exact_one_sided(
        n_faults, n_trials - n_faults, PAST_4CARD_FAULTS, PAST_4CARD_TRIALS - PAST_4CARD_FAULTS,
    ) if n_trials > 0 else None
    p_vs_sa = fisher_exact_one_sided(
        n_faults, n_trials - n_faults, PAST_SA_FAULTS, PAST_SA_TRIALS - PAST_SA_FAULTS,
    ) if n_trials > 0 else None

    buckets = []
    if t.get("start_epoch") and t.get("duration_s"):
        n_buckets = int(math.ceil(duration_h))
        for b in range(n_buckets):
            b_start = t["start_epoch"] + b * 3600
            b_end = b_start + 3600
            trials_in = sum(1 for e in t["trial_done_epochs"] if b_start <= e < b_end)
            faults_in = sum(1 for e in t["fault_epochs"] if b_start <= e < b_end)
            evals_in = [ev for tp, ev in zip(t["turn_epochs"], t["eval_tps_vals"])
                        if b_start <= tp < b_end]
            powers_in = [pw for ep, pw in zip(r.get("target_power_epochs", []),
                                              r.get("target_power_vals", []))
                         if b_start <= ep < b_end]
            buckets.append({
                "hour": b,
                "trials": trials_in,
                "faults": faults_in,
                "eval_p50": float(np.percentile(evals_in, 50)) if evals_in else None,
                "power_p95": float(np.percentile(powers_in, 95)) if powers_in else None,
            })

    md = []
    md.append("# mi25 a48e4 SLOT6 / Vulkan stand-alone 24h+ 負荷 — 集計表\n\n")
    md.append("## 全期間サマリ\n")
    md.append("| 項目 | 値 |\n|---|---|\n")
    md.append(f"| キャンペーン期間 [h] | {duration_h:.2f} |\n")
    md.append(f"| 完了 trial 数 (trial_done) | {n_trials} |\n")
    md.append(f"| HANG_CONFIRMED (jsonl) | {t.get('hangs', 0)} |\n")
    md.append(f"| dmesg GPU reset (新規 baseline+{baseline_lines}行以降) | {dmesg_gpu_resets} |\n")
    md.append(f"| 統合 fault 件数 | {n_faults} |\n")
    md.append(f"| stall 件数 | {t.get('stalls', 0)} |\n")
    md.append(f"| ネットワーク障害 件数 | {t.get('network_outages', 0)} |\n")
    md.append(f"| turn 総数 | {t.get('turn_count', 0)} |\n")
    md.append(f"| eval_tps mean | {(t.get('eval_tps_mean') or 0):.2f} |\n")
    md.append(f"| eval_tps p50 | {(t.get('eval_tps_p50') or 0):.2f} |\n")
    md.append(f"| pp_tps mean | {(t.get('pp_tps_mean') or 0):.2f} |\n")
    md.append(f"| 本試験 fault 率 | {n_faults}/{n_trials} = {(n_faults/n_trials*100 if n_trials else 0):.2f}% |\n")
    md.append(f"| 過去 4 枚運用 fault 率 | {PAST_4CARD_FAULTS}/{PAST_4CARD_TRIALS} = {PAST_4CARD_FAULTS/PAST_4CARD_TRIALS*100:.2f}% |\n")
    md.append(f"| 過去 stand_alone_24h SLOT6 fault 率 | {PAST_SA_FAULTS}/{PAST_SA_TRIALS} = {PAST_SA_FAULTS/PAST_SA_TRIALS*100:.2f}% |\n")
    if p_vs_4card is not None:
        md.append(f"| Fisher (本 vs 4 枚運用、H1: 本 < 4 枚) | p = {p_vs_4card:.4f} |\n")
    if p_vs_sa is not None:
        md.append(f"| Fisher (本 vs stand_alone_24h、H1: 本 < SA) | p = {p_vs_sa:.4f} |\n")
    md.append("\n")

    md.append("## dmesg amdgpu フォルト集計\n")
    md.append(f"- baseline 行数: {baseline_lines}\n")
    md.append(f"- kern_dmesg.log 全行数: {d.get('total_lines', 0)}\n")
    md.append(f"- 新規 fault 関連検出件数: {d.get('fault_count', 0)}\n")
    md.append(f"- シグネチャ別: {d.get('signatures', {})}\n")
    md.append(f"- BDF 別: {d.get('bdfs', {})}\n\n")

    md.append("## PCIe AER (キャンペーン中)\n")
    if p:
        md.append(f"- samples: {p['samples']}, non-x16 entries: {p['non_x16_entries']}\n")
        md.append(f"- AER COR max: {p['aer_cor_max']}, FATAL max: {p['aer_fatal_max']}, NFATAL max: {p['aer_nfatal_max']}\n")
        md.append(f"- GPU_COUNT min: {p.get('gpu_count_min')}\n\n")

    md.append(f"## GPU[{TARGET_GPU_IDX}] (a48e4) テレメトリ\n")
    if r:
        md.append(f"- rocm-smi samples: {r['samples']}\n")
        md.append(f"- power [W]: mean {(r.get('target_power_w_mean') or 0):.1f}, "
                  f"p95 {(r.get('target_power_w_p95') or 0):.1f}, "
                  f"max {(r.get('target_power_w_max') or 0):.1f}\n")
        md.append(f"- Tj junction max: {r.get('target_temp_max')} °C\n\n")

    md.append("## 1h バケット推移\n")
    md.append("| hour | trials | faults | eval p50 [t/s] | GPU[2] power p95 [W] |\n")
    md.append("|---:|---:|---:|---:|---:|\n")
    for b in buckets:
        md.append(
            f"| {b['hour']} | {b['trials']} | {b['faults']} | "
            f"{(b['eval_p50'] or 0):.2f} | "
            f"{(b['power_p95'] or 0):.1f} |\n"
        )

    with open(os.path.join(SCR, "data.md"), "w") as f:
        f.write("".join(md))

    fig, ax1 = plt.subplots(figsize=(13, 6.2))
    if buckets:
        hours = [b["hour"] for b in buckets]
        trials_per_h = [b["trials"] for b in buckets]
        faults_per_h = [b["faults"] for b in buckets]
        eval_p50 = [(b["eval_p50"] or 0) for b in buckets]
        ax1.bar(hours, trials_per_h, width=0.8, color="#3aa055", edgecolor="black",
                linewidth=0.6, alpha=0.8, label="trials_done / h")
        for h, f_, t_ in zip(hours, faults_per_h, trials_per_h):
            if f_ > 0:
                ax1.text(h, t_ + 0.3, f"FAULT x{f_}", ha="center", va="bottom",
                         fontsize=10, fontweight="bold", color="#d83a3a")
        ax1.set_xlabel("Hour from campaign start", fontsize=11)
        ax1.set_ylabel("trials_done / h (green bars)", fontsize=11, color="#207040")
        ax1.tick_params(axis="y", labelcolor="#207040")
        ax1.set_xticks(hours)
        ax1.grid(axis="y", alpha=0.3)
        ax2 = ax1.twinx()
        ax2.plot(hours, eval_p50, "o-", color="#2060a0", linewidth=2, markersize=7,
                 label="eval p50 [t/s]")
        ax2.set_ylabel("Eval p50 [t/s] (blue)", fontsize=11, color="#2060a0")
        ax2.tick_params(axis="y", labelcolor="#2060a0")

    title = (
        f"mi25 a48e4 SLOT6 / Vulkan stand-alone {duration_h:.1f}h — "
        f"{n_trials} trials_done, {n_faults} faults "
        f"({(n_faults/n_trials*100 if n_trials else 0):.2f}% "
        f"vs past 4card 3/88=3.41%, vs past SA 2/147=1.36%)\n"
        f"Qwen3-8B Q6_K, ctx=131072(cap40960), GGML_VK_VISIBLE_DEVICES=2 (BDF 84:00.0)"
    )
    plt.title(title, fontsize=11, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(SCR, "summary.png"), dpi=130, bbox_inches="tight")
    print("summary.png + data.md written")
    print(f"trials_done={n_trials}, faults={n_faults}, duration={duration_h:.2f}h")
    if p_vs_4card is not None:
        print(f"Fisher (vs 4card 3/88) p (one-sided lower) = {p_vs_4card:.4f}")
    if p_vs_sa is not None:
        print(f"Fisher (vs stand_alone 2/147) p (one-sided lower) = {p_vs_sa:.4f}")


if __name__ == "__main__":
    main()
