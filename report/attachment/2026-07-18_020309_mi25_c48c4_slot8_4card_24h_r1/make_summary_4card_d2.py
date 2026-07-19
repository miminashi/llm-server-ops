#!/usr/bin/env python3
"""mi25 c48c4 SLOT8 4-card / Vulkan D-2 R1 — 集計 + summary.png。
make_summary_24h.py (D-1 a48e4 SA) から派生。差分:
- 4 枚同時 (0=c3164 / 1=448c4 / 2=c48c4 / 3=a48e4) の per-GPU telemetry 集計
- Session1 (02:07-18:52 = 16.7h) + 電源断中断 + Session2 (23:58-05:36 = 5.6h)
- baseline_lines = 2308 (pre_r1_baseline.txt 記録値)
- 過去比較: SLOT6 4-card 3/88, SLOT6 累積 5/235, SA SLOT8 0/221
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

# 過去比較 (D-2 R1 の主比較対象)
PAST_SLOT6_4CARD = (3, 88)         # c48c4×SLOT6 4-card (電力スイープ系列合算)
PAST_SLOT6_ACC = (5, 235)          # c48c4×SLOT6 累積 (4-card + SA)
PAST_SLOT6_SA = (2, 147)           # c48c4×SLOT6 SA (stand_alone_24h)
PAST_SLOT8_SA = (0, 221)           # c48c4×SLOT8 SA (SLOT8_24h_x2)
PAST_A48E4_SA = (0, 221)           # a48e4×SLOT6 SA (D-1)

# Session boundary (2026-07-18 23:58:15 JST 頃、session2 start_epoch)
SESSION2_START_EPOCH = 1784386695

TARGET_LABELS = {0: "c3164 (SLOT2)", 1: "448c4 (SLOT4)", 2: "c48c4 (SLOT8)★", 3: "a48e4 (SLOT6)"}

FAULT_PATTERNS = re.compile(
    r"(amdgpu_job_timedout|GPU reset begin|VRAM is lost|no-retry page fault|Memory access fault)"
)
BDF_PATTERN = re.compile(r"amdgpu (0000:[0-9a-f]+:[0-9a-f]+\.[0-9])")
POWER_PATTERN = re.compile(r"Current Socket Graphics Package Power \(W\):\s*([\d.]+)")
TEMP_PATTERN = re.compile(r"Temperature \(Sensor junction\) \(C\):\s*([\d.]+)")


def parse_trials(path):
    events = []
    with open(path) as f:
        for line in f:
            try:
                events.append(json.loads(line))
            except Exception:
                continue
    if not events:
        return None
    trial_done_epochs = []
    fault_epochs = []
    hangs = 0
    turn_epochs = []
    eval_tps_vals = []
    pp_tps_vals = []
    for obj in events:
        ev = obj.get("event")
        ep = obj.get("epoch")
        if ev == "trial_done":
            trial_done_epochs.append(ep)
        elif ev == "HANG_CONFIRMED":
            hangs += 1
            fault_epochs.append(ep)
        elif ev == "turn":
            ev_t = obj.get("eval_tps")
            pp_t = obj.get("pp_tps")
            if ev_t:
                eval_tps_vals.append(ev_t)
            if pp_t:
                pp_tps_vals.append(pp_t)
            turn_epochs.append(ep)
    s1_done = [e for e in trial_done_epochs if e < SESSION2_START_EPOCH]
    s2_done = [e for e in trial_done_epochs if e >= SESSION2_START_EPOCH]
    return {
        "trial_done_epochs": trial_done_epochs,
        "s1_done": len(s1_done),
        "s2_done": len(s2_done),
        "total_done": len(trial_done_epochs),
        "fault_epochs": fault_epochs,
        "hangs": hangs,
        "turn_epochs": turn_epochs,
        "eval_tps_vals": eval_tps_vals,
        "pp_tps_vals": pp_tps_vals,
        "eval_tps_mean": statistics.mean(eval_tps_vals) if eval_tps_vals else None,
        "eval_tps_p50": float(np.percentile(eval_tps_vals, 50)) if eval_tps_vals else None,
        "pp_tps_mean": statistics.mean(pp_tps_vals) if pp_tps_vals else None,
        "start_epoch": events[0].get("epoch"),
        "end_epoch": events[-1].get("epoch"),
    }


def parse_dmesg(path, baseline_lines=0):
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
    }


def parse_telemetry_rocmsmi(path):
    """4 枚全 GPU の power/temp を集計"""
    per_gpu = {i: {"power": [], "temp": [], "epochs": []} for i in range(4)}
    current = {i: {} for i in range(4)}
    current_epoch = None

    def flush():
        if current_epoch is None:
            return
        for i in range(4):
            if current[i].get("power") is not None:
                per_gpu[i]["power"].append(current[i]["power"])
                per_gpu[i]["epochs"].append(current_epoch)
            if current[i].get("temp") is not None:
                per_gpu[i]["temp"].append(current[i]["temp"])

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
    result = {}
    for i in range(4):
        pw = per_gpu[i]["power"]
        tp = per_gpu[i]["temp"]
        result[i] = {
            "samples": len(pw),
            "power_mean": statistics.mean(pw) if pw else None,
            "power_p95": pct(pw, 95),
            "power_max": max(pw) if pw else None,
            "temp_mean": statistics.mean(tp) if tp else None,
            "temp_max": max(tp) if tp else None,
            "epochs": per_gpu[i]["epochs"],
            "power_vals": pw,
        }
    return result


def parse_telemetry_pcie(path):
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
                for k, v in (("cor", cor), ("fatal", fat), ("nfatal", nft)):
                    try:
                        aer_total[k] = max(aer_total[k], int(v))
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
    """H1: 本 (a/(a+b)) < 過去 (c/(c+d))"""
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
    baseline_lines = 2308

    t = parse_trials(os.path.join(SCR, "trials_vulkan.jsonl")) or {}
    d = parse_dmesg(os.path.join(SCR, "kern_dmesg.log"), baseline_lines=baseline_lines) or {}
    r = parse_telemetry_rocmsmi(os.path.join(SCR, "telemetry_rocmsmi.log")) or {}
    p = parse_telemetry_pcie(os.path.join(SCR, "telemetry_pcie.log")) or {}

    n_trials = t.get("total_done", 0)
    dmesg_gpu_resets = d.get("signatures", {}).get("GPU reset begin", 0)
    n_faults = max(t.get("hangs", 0), dmesg_gpu_resets)

    # Fisher one-sided (下方向)
    fisher = {}
    for name, (f, n) in [
        ("SLOT6_4card_3_88", PAST_SLOT6_4CARD),
        ("SLOT6_acc_5_235", PAST_SLOT6_ACC),
        ("SLOT6_SA_2_147", PAST_SLOT6_SA),
        ("SLOT8_SA_0_221", PAST_SLOT8_SA),
        ("A48e4_SA_0_221", PAST_A48E4_SA),
    ]:
        if n_trials > 0:
            fisher[name] = fisher_exact_one_sided(
                n_faults, n_trials - n_faults, f, n - f,
            )

    # P(0 fault | true rate p, N)
    prob_zero = {p_true: (1 - p_true/100.0)**n_trials for p_true in [3.41, 2.13, 1.36]}

    # ---- data.md ----
    md = []
    md.append("# mi25 c48c4 SLOT8 4-card / Vulkan D-2 R1 — 集計表\n\n")
    md.append("## 全期間サマリ\n")
    md.append("| 項目 | 値 |\n|---|---|\n")
    md.append(f"| Session1 完了 trial (02:07-18:52 電源断中断) | {t.get('s1_done', 0)} |\n")
    md.append(f"| Session2 完了 trial (23:58-05:36 継続) | {t.get('s2_done', 0)} |\n")
    md.append(f"| **累計 完了 trial** | **{n_trials}** |\n")
    md.append(f"| HANG_CONFIRMED (jsonl) | {t.get('hangs', 0)} |\n")
    md.append(f"| dmesg GPU reset (新規、baseline+{baseline_lines}行以降) | {dmesg_gpu_resets} |\n")
    md.append(f"| **統合 fault 件数** | **{n_faults}** |\n")
    md.append(f"| turn 総数 | {len(t.get('turn_epochs', []))} |\n")
    md.append(f"| eval_tps mean | {(t.get('eval_tps_mean') or 0):.2f} |\n")
    md.append(f"| eval_tps p50 | {(t.get('eval_tps_p50') or 0):.2f} |\n")
    md.append(f"| pp_tps mean | {(t.get('pp_tps_mean') or 0):.2f} |\n")
    md.append(f"| 本試験 fault 率 | {n_faults}/{n_trials} = {(n_faults/n_trials*100 if n_trials else 0):.2f}% |\n\n")

    md.append("## Fisher exact one-sided (H1: D-2 R1 の fault 率 < 過去)\n")
    md.append("| 比較対象 | fault/trial | 発生率 | Fisher p (one-sided) |\n|---|---|---|---|\n")
    for name, (f, n), key in [
        ("c48c4×SLOT6 4-card", PAST_SLOT6_4CARD, "SLOT6_4card_3_88"),
        ("c48c4×SLOT6 累積", PAST_SLOT6_ACC, "SLOT6_acc_5_235"),
        ("c48c4×SLOT6 SA", PAST_SLOT6_SA, "SLOT6_SA_2_147"),
        ("c48c4×SLOT8 SA", PAST_SLOT8_SA, "SLOT8_SA_0_221"),
        ("a48e4×SLOT6 SA (D-1)", PAST_A48E4_SA, "A48e4_SA_0_221"),
    ]:
        p_val = fisher.get(key, 1.0)
        md.append(f"| {name} | {f}/{n} | {f/n*100:.2f}% | {p_val:.4f} |\n")
    md.append("\n")

    md.append("## 検出力 (0 fault 観測時、真の rate を棄却できる確率)\n")
    md.append("| 仮想 真の rate | P(0 fault \\| p, N) | 検出力 |\n|---|---|---|\n")
    for p_true, pz in prob_zero.items():
        md.append(f"| {p_true:.2f}% | {pz*100:.2f}% | {(1-pz)*100:.2f}% |\n")
    md.append("\n")

    md.append("## dmesg amdgpu フォルト集計\n")
    md.append(f"- baseline 行数: {baseline_lines}\n")
    md.append(f"- kern_dmesg.log 全行数: {d.get('total_lines', 0)}\n")
    md.append(f"- 新規 fault 関連検出件数: **{d.get('fault_count', 0)}**\n")
    md.append(f"- シグネチャ別: {d.get('signatures', {})}\n")
    md.append(f"- BDF 別: {d.get('bdfs', {})}\n\n")

    md.append("## PCIe AER (キャンペーン中)\n")
    md.append(f"- samples: {p['samples']}, non-x16 entries: {p['non_x16_entries']}\n")
    md.append(f"- AER COR max: {p['aer_cor_max']}, FATAL max: {p['aer_fatal_max']}, NFATAL max: {p['aer_nfatal_max']}\n")
    md.append(f"- GPU_COUNT min: {p.get('gpu_count_min')}\n\n")

    md.append("## per-GPU テレメトリ\n")
    md.append("| GPU idx | ラベル | samples | power mean [W] | power p95 [W] | power max [W] | Tj max [°C] |\n")
    md.append("|---|---|---|---|---|---|---|\n")
    for i in range(4):
        g = r.get(i, {})
        md.append(
            f"| {i} | {TARGET_LABELS[i]} | {g.get('samples', 0)} | "
            f"{(g.get('power_mean') or 0):.1f} | "
            f"{(g.get('power_p95') or 0):.1f} | "
            f"{(g.get('power_max') or 0):.1f} | "
            f"{g.get('temp_max') or 0} |\n"
        )
    md.append("\n")

    with open(os.path.join(SCR, "data.md"), "w") as f:
        f.write("".join(md))

    # ---- summary.png ----
    fig, axes = plt.subplots(2, 1, figsize=(13, 8), gridspec_kw={"height_ratios": [1.2, 1]})

    # (1) trials_done timeline (session1/2 分割表示)
    ax1 = axes[0]
    if t.get("trial_done_epochs"):
        start = t["start_epoch"]
        s1_epochs = [e for e in t["trial_done_epochs"] if e < SESSION2_START_EPOCH]
        s2_epochs = [e for e in t["trial_done_epochs"] if e >= SESSION2_START_EPOCH]
        s1_hours = [(e - start) / 3600.0 for e in s1_epochs]
        s2_hours = [(e - start) / 3600.0 for e in s2_epochs]
        ax1.scatter(s1_hours, range(1, len(s1_hours)+1), c="#3aa055", s=20,
                    label=f"Session1 ({len(s1_hours)} done)")
        offset = len(s1_hours)
        ax1.scatter(s2_hours, range(offset+1, offset+len(s2_hours)+1), c="#2060a0", s=20,
                    label=f"Session2 ({len(s2_hours)} done)")
        # 電源断中断ライン
        outage_start = (SESSION2_START_EPOCH - start - 300*12) / 3600.0    # session1 最後の trial 開始 + 少し
        outage_end = (SESSION2_START_EPOCH - start) / 3600.0
        ax1.axvspan(16.8, outage_end, color="#f0c060", alpha=0.35,
                    label="Control host power outage (18:52-23:58 JST)")
        ax1.set_xlabel("Hours from R1 start (2026-07-18 02:07:49 JST)")
        ax1.set_ylabel("Cumulative trial_done")
        ax1.set_title(
            f"mi25 c48c4 SLOT8 4-card / Vulkan D-2 R1 — cumulative N={n_trials} trial_done, "
            f"faults={n_faults}\n"
            f"Qwen3-8B Q6_K ctx=131072(cap40960), HIP_VISIBLE_DEVICES=0,1,2,3, target=c48c4(GPU[2]/BDF 84:00.0/SLOT8)",
            fontsize=10, fontweight="bold"
        )
        ax1.legend(loc="lower right")
        ax1.grid(alpha=0.3)

    # (2) per-GPU power p95 comparison
    ax2 = axes[1]
    gpu_labels = [TARGET_LABELS[i] for i in range(4)]
    p_mean = [(r.get(i, {}).get("power_mean") or 0) for i in range(4)]
    p_p95 = [(r.get(i, {}).get("power_p95") or 0) for i in range(4)]
    p_max = [(r.get(i, {}).get("power_max") or 0) for i in range(4)]
    x_pos = np.arange(4)
    width = 0.27
    ax2.bar(x_pos - width, p_mean, width, label="mean", color="#5088c0")
    ax2.bar(x_pos, p_p95, width, label="p95", color="#e0a040")
    ax2.bar(x_pos + width, p_max, width, label="max", color="#d84040")
    ax2.set_xticks(x_pos)
    ax2.set_xticklabels(gpu_labels, fontsize=10)
    ax2.set_ylabel("Power [W]")
    ax2.set_title("per-GPU power distribution (rocm-smi telemetry)", fontsize=10)
    ax2.axhline(160, color="#606060", linestyle="--", linewidth=1, label="cap 160W")
    ax2.legend(loc="upper right", ncol=4, fontsize=9)
    ax2.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(SCR, "summary.png"), dpi=130, bbox_inches="tight")
    print("summary.png + data.md written")
    print(f"total_done={n_trials}, faults={n_faults}")
    print(f"Session1: {t.get('s1_done', 0)}, Session2: {t.get('s2_done', 0)}")
    for name, p_val in fisher.items():
        print(f"Fisher one-sided ({name}) p = {p_val:.4f}")


if __name__ == "__main__":
    main()
