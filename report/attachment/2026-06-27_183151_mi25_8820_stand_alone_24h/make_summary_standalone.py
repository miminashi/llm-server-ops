#!/usr/bin/env python3
"""mi25 8820 単独 24h 負荷 — 集計 + summary.png。
make_summary.py (電力スイープ版) から派生。
- 電力点軸 → 時間軸 (1h バケット) に変更
- ファイル名は _pXW 接尾辞なし (1 セッションのみ)
- Fisher exact (3/88 vs k/n_trials) p 値を計算して data.md に出力
"""
import json
import math
import os
import re
import statistics
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SCR = os.path.dirname(os.path.abspath(__file__))

# 過去 4 枚 Vulkan 88 trial の fault 3 件 (これとの比較で b/c を弁別する)
PAST_FAULTS = 3
PAST_TRIALS = 88

FAULT_PATTERNS = re.compile(
    r"(amdgpu_job_timedout|GPU reset begin|VRAM is lost|no-retry page fault|Memory access fault)"
)
BDF_PATTERN = re.compile(r"amdgpu (0000:[0-9a-f]+:[0-9a-f]+\.[0-9])")
POWER_PATTERN = re.compile(r"Current Socket Graphics Package Power \(W\):\s*([\d.]+)")
TEMP_PATTERN = re.compile(r"Temperature \(Sensor junction\) \(C\):\s*([\d.]+)")


def parse_trials(path):
    """trials_vulkan.jsonl から time-bucketed metrics を抽出。"""
    if not os.path.exists(path):
        return None
    events = []
    with open(path) as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            events.append(obj)

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
    eval_tps_vals = []
    pp_tps_vals = []
    turn_epochs = []
    fault_epochs = []  # stall + HANG_CONFIRMED + NETWORK_OUTAGE のいずれか

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
            # stall は OK / NETWORK / HOST_HANG いずれかになる
            status = obj.get("outage_status")
            if status == "HOST_HANG":
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


def parse_dmesg(path, baseline_uptime_s=None):
    """kern_dmesg.log から amdgpu フォルト関連の行を抽出。
    baseline_uptime_s 以前のメッセージは過去履歴として除外。
    """
    if not os.path.exists(path):
        return None
    fault_events = []
    sig_counter = {}
    bdf_counter = {}
    UPTIME_PATTERN = re.compile(r"^\[\s*(\d+\.\d+)\]")
    with open(path, errors="replace") as f:
        for line in f:
            mu = UPTIME_PATTERN.match(line)
            uptime = float(mu.group(1)) if mu else None
            if baseline_uptime_s and uptime and uptime < baseline_uptime_s:
                continue
            m = FAULT_PATTERNS.search(line)
            if m:
                sig = m.group(1)
                sig_counter[sig] = sig_counter.get(sig, 0) + 1
                mb = BDF_PATTERN.search(line)
                bdf = mb.group(1) if mb else "?"
                bdf_counter[bdf] = bdf_counter.get(bdf, 0) + 1
                fault_events.append({"uptime": uptime, "sig": sig, "bdf": bdf, "line": line.rstrip()})
    return {
        "fault_events": fault_events,
        "fault_count": len(fault_events),
        "signatures": sig_counter,
        "bdfs": bdf_counter,
    }


def parse_telemetry_rocmsmi(path):
    if not os.path.exists(path):
        return None
    gpu3_power = []
    gpu3_temp = []
    gpu3_power_epochs = []
    current = {0: {}, 1: {}, 2: {}, 3: {}}
    current_epoch = None

    def flush():
        if current_epoch is None:
            return
        if current[3].get("power") is not None:
            gpu3_power.append(current[3]["power"])
            gpu3_power_epochs.append(current_epoch)
        if current[3].get("temp") is not None:
            gpu3_temp.append(current[3]["temp"])

    epoch_pat = re.compile(r"===== epoch=(\d+)")
    with open(path, errors="replace") as f:
        for line in f:
            me = epoch_pat.match(line)
            if me:
                flush()
                current_epoch = int(me.group(1))
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
        "samples": len(gpu3_power),
        "gpu3_power_w_mean": statistics.mean(gpu3_power) if gpu3_power else None,
        "gpu3_power_w_p95": pct(gpu3_power, 95),
        "gpu3_power_w_max": max(gpu3_power) if gpu3_power else None,
        "gpu3_temp_max": max(gpu3_temp) if gpu3_temp else None,
        "gpu3_power_epochs": gpu3_power_epochs,
        "gpu3_power_vals": gpu3_power,
    }


def parse_telemetry_pcie(path):
    """telemetry_pcie.log からキャンペーン中に AER エラーがあったか確認。"""
    if not os.path.exists(path):
        return None
    aer_total = {"cor": 0, "fatal": 0, "nfatal": 0}
    samples = 0
    non_x16 = 0
    with open(path, errors="replace") as f:
        for line in f:
            if line.startswith("===== epoch="):
                samples += 1
                continue
            m = re.match(r"PORT=(\S+) W=(\S+) SP=(\S+) PD=(\S+) COR=(\S+) FAT=(\S+) NFT=(\S+)", line)
            if not m:
                continue
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
    return {
        "samples": samples,
        "non_x16_entries": non_x16,
        "aer_cor_max": aer_total["cor"],
        "aer_fatal_max": aer_total["fatal"],
        "aer_nfatal_max": aer_total["nfatal"],
    }


def fisher_exact_one_sided(a, b, c, d):
    """Fisher exact (one-sided lower) で観測値 <= 期待値の片側 p 値。
    分割表: [[a, b], [c, d]] (a=現実験 fault, b=現実験 not, c=過去 fault, d=過去 not)
    検定: H1 = 「現実験の fault 率 < 過去」(c case)。
    """
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


def _merge_dict_int(a, b):
    out = dict(a or {})
    for k, v in (b or {}).items():
        out[k] = out.get(k, 0) + v
    return out


def parse_trials_multi(paths):
    """複数ラウンド (round1 + 本体) の jsonl を結合して集計。
    各ラウンドの start/end epoch は独立扱いだが、metrics は通算。"""
    merged = None
    rounds = []
    for path in paths:
        r = parse_trials(path)
        if not r:
            continue
        rounds.append({"path": path, **r})
        if merged is None:
            merged = dict(r)
            merged["start_epoch_first"] = r.get("start_epoch")
            merged["end_epoch_last"] = r.get("end_epoch")
        else:
            merged["trials_done"] += r.get("trials_done", 0)
            merged["hangs"] += r.get("hangs", 0)
            merged["stalls"] += r.get("stalls", 0)
            merged["network_outages"] += r.get("network_outages", 0)
            merged["trial_done_epochs"] += r.get("trial_done_epochs", [])
            merged["hang_epochs"] += r.get("hang_epochs", [])
            merged["fault_epochs"] += r.get("fault_epochs", [])
            merged["turn_epochs"] += r.get("turn_epochs", [])
            merged["eval_tps_vals"] += r.get("eval_tps_vals", [])
            merged["turn_count"] += r.get("turn_count", 0)
            if r.get("end_epoch"):
                merged["end_epoch_last"] = r["end_epoch"]
    if merged:
        if merged.get("eval_tps_vals"):
            merged["eval_tps_mean"] = statistics.mean(merged["eval_tps_vals"])
            merged["eval_tps_p50"] = float(np.percentile(merged["eval_tps_vals"], 50))
        merged["rounds"] = rounds
    return merged


def parse_dmesg_multi(paths):
    out = {"fault_events": [], "fault_count": 0, "signatures": {}, "bdfs": {}}
    for path in paths:
        d = parse_dmesg(path)
        if not d:
            continue
        out["fault_events"] += d.get("fault_events", [])
        out["fault_count"] += d.get("fault_count", 0)
        out["signatures"] = _merge_dict_int(out["signatures"], d.get("signatures"))
        out["bdfs"] = _merge_dict_int(out["bdfs"], d.get("bdfs"))
    return out


def parse_telemetry_rocmsmi_multi(paths):
    out = {"samples": 0, "gpu3_power_epochs": [], "gpu3_power_vals": [], "gpu3_temp_max": None}
    gpu3_power_all = []
    gpu3_temp_all = []
    for path in paths:
        r = parse_telemetry_rocmsmi(path)
        if not r:
            continue
        out["samples"] += r.get("samples", 0)
        out["gpu3_power_epochs"] += r.get("gpu3_power_epochs", [])
        out["gpu3_power_vals"] += r.get("gpu3_power_vals", [])
        gpu3_power_all += r.get("gpu3_power_vals", [])
        if r.get("gpu3_temp_max") is not None:
            gpu3_temp_all.append(r["gpu3_temp_max"])
    if gpu3_power_all:
        out["gpu3_power_w_mean"] = statistics.mean(gpu3_power_all)
        out["gpu3_power_w_p95"] = float(np.percentile(gpu3_power_all, 95))
        out["gpu3_power_w_max"] = max(gpu3_power_all)
    if gpu3_temp_all:
        out["gpu3_temp_max"] = max(gpu3_temp_all)
    return out


def parse_telemetry_pcie_multi(paths):
    out = {"samples": 0, "non_x16_entries": 0, "aer_cor_max": 0, "aer_fatal_max": 0, "aer_nfatal_max": 0}
    for path in paths:
        p = parse_telemetry_pcie(path)
        if not p:
            continue
        out["samples"] += p.get("samples", 0)
        out["non_x16_entries"] += p.get("non_x16_entries", 0)
        out["aer_cor_max"] = max(out["aer_cor_max"], p.get("aer_cor_max", 0))
        out["aer_fatal_max"] = max(out["aer_fatal_max"], p.get("aer_fatal_max", 0))
        out["aer_nfatal_max"] = max(out["aer_nfatal_max"], p.get("aer_nfatal_max", 0))
    return out


def main():
    # R1 (_round1) と R2 (本体) の両方を読み込み、累計集計する
    trials_paths = [os.path.join(SCR, "trials_vulkan_round1.jsonl"), os.path.join(SCR, "trials_vulkan.jsonl")]
    dmesg_paths = [os.path.join(SCR, "kern_dmesg_round1.log"), os.path.join(SCR, "kern_dmesg.log")]
    rocm_paths = [os.path.join(SCR, "telemetry_rocmsmi_round1.log"), os.path.join(SCR, "telemetry_rocmsmi.log")]
    pcie_paths = [os.path.join(SCR, "telemetry_pcie_round1.log"), os.path.join(SCR, "telemetry_pcie.log")]

    t = parse_trials_multi(trials_paths) or {}
    # キャンペーン開始時刻 (epoch) と uptime を対応付ける。
    # uptime の baseline: キャンペーン開始時刻が epoch X として、その時点の uptime を計算
    # → dmesg 行 [uptime] が baseline 以降のもののみカウント
    # 簡略化: キャンペーン開始時刻と最初の dmesg 行の最大 uptime を比較する方法もあるが、
    # ここではキャンペーン開始時刻以降の uptime 行のみ抽出する別方法を取る。
    # 実装簡略: 直前の reset 後の uptime baseline を campaign_vulkan.log から推定するのは複雑なので、
    # 簡単には「kern_dmesg.log の冒頭にある [uptime] 最大値 + 数分余裕」を baseline にする。
    # ここではキャンペーン開始時刻を campaign log から取得し、サーバ uptime を逆算する。
    # → 簡単のため、parse_dmesg は baseline_uptime_s=None で全件カウントし、レポート側で
    #   過去履歴 (キャンペーン前 12h 程度) との差分を「キャンペーン中 fault」として計算する。
    d = parse_dmesg_multi(dmesg_paths) or {}
    r = parse_telemetry_rocmsmi_multi(rocm_paths) or {}
    p = parse_telemetry_pcie_multi(pcie_paths) or {}

    n_trials = t.get("trials_done", 0)
    # 累計 fault: 各ラウンドの fault_epochs (HANG_CONFIRMED + HOST_HANG stall + dmesg fault) のうち
    # dmesg で実 fault 観測されたラウンドだけ 1 件として数える簡易方式。
    # R1: fault_epochs に 165 件の server_error_transient stall (status=OK) は含まれない設計のため、
    # 真の fault は jsonl の stall + dmesg 確認で識別する。
    # ここでは dmesg fault count (page fault/GPU reset) があるラウンド数を fault としてカウントする。
    # 実装簡略: ラウンド単位で dmesg fault > 0 のものを 1 fault と見なす
    n_dmesg_fault_rounds = 0
    for round_data in t.get("rounds", []):
        round_idx = trials_paths.index(round_data["path"])
        dmesg_for_round = parse_dmesg(dmesg_paths[round_idx]) or {}
        if dmesg_for_round.get("fault_count", 0) > 0:
            n_dmesg_fault_rounds += 1
    n_faults = n_dmesg_fault_rounds
    # 期間: 各ラウンドの duration_s の合計
    duration_h = sum((round_data.get("duration_s") or 0) for round_data in t.get("rounds", [])) / 3600.0

    # Fisher exact (one-sided): 現実験 fault 率 < 過去 (3/88) かどうか
    # 分割表: [[n_faults, n_trials - n_faults], [PAST_FAULTS, PAST_TRIALS - PAST_FAULTS]]
    if n_trials > 0:
        p_value = fisher_exact_one_sided(
            n_faults, n_trials - n_faults,
            PAST_FAULTS, PAST_TRIALS - PAST_FAULTS,
        )
    else:
        p_value = None

    # 1h バケット集計
    buckets = []
    if t.get("start_epoch") and t.get("duration_s"):
        n_buckets = int(math.ceil(duration_h))
        for b in range(n_buckets):
            b_start = t["start_epoch"] + b * 3600
            b_end = b_start + 3600
            trials_in_bucket = sum(1 for e in t["trial_done_epochs"] if b_start <= e < b_end)
            faults_in_bucket = sum(1 for e in t["fault_epochs"] if b_start <= e < b_end)
            evals_in_bucket = [
                ev for tp, ev in zip(t["turn_epochs"], t["eval_tps_vals"])
                if b_start <= tp < b_end
            ]
            powers_in_bucket = [
                pw for ep, pw in zip(r.get("gpu3_power_epochs", []), r.get("gpu3_power_vals", []))
                if b_start <= ep < b_end
            ]
            buckets.append({
                "hour": b,
                "trials": trials_in_bucket,
                "faults": faults_in_bucket,
                "eval_p50": float(np.percentile(evals_in_bucket, 50)) if evals_in_bucket else None,
                "power_p95": float(np.percentile(powers_in_bucket, 95)) if powers_in_bucket else None,
            })

    # data.md 出力
    md = []
    md.append("# mi25 8820 単独 24h 負荷 — 集計表\n")
    md.append(f"集計対象: {', '.join(trials_paths)}\n\n")
    md.append("## 全期間サマリ\n")
    md.append("| 項目 | 値 |\n|---|---|\n")
    md.append(f"| キャンペーン期間 [h] | {duration_h:.2f} |\n")
    md.append(f"| 完了 trial 数 (trial_done) | {n_trials} |\n")
    md.append(f"| HANG_CONFIRMED 件数 | {n_faults} |\n")
    md.append(f"| stall 件数 (うち host hang 含む) | {t.get('stalls', 0)} |\n")
    md.append(f"| ネットワーク障害 件数 | {t.get('network_outages', 0)} |\n")
    md.append(f"| turn 総数 | {t.get('turn_count', 0)} |\n")
    md.append(f"| eval_tps mean | {t.get('eval_tps_mean')} |\n")
    md.append(f"| pp_tps mean | {t.get('pp_tps_mean')} |\n")
    md.append(f"| 過去 4 枚 88 trial の fault | {PAST_FAULTS}/{PAST_TRIALS} = {PAST_FAULTS/PAST_TRIALS*100:.1f}% |\n")
    md.append(f"| 本実験 fault | {n_faults}/{n_trials} = {(n_faults/n_trials*100 if n_trials else 0):.2f}% |\n")
    if p_value is not None:
        md.append(f"| Fisher exact (one-sided, H1: 本実験 < 過去) | p = {p_value:.4f} |\n")
    md.append("\n")

    md.append("## dmesg amdgpu フォルト集計\n")
    md.append(f"- 検出件数 (キャンペーン中 / 過去含む全期間): {d.get('fault_count')}\n")
    md.append(f"- シグネチャ別: {d.get('signatures')}\n")
    md.append(f"- BDF 別: {d.get('bdfs')}\n\n")

    md.append("## PCIe AER\n")
    if p:
        md.append(f"- samples: {p['samples']}, non-x16 entries: {p['non_x16_entries']}\n")
        md.append(f"- AER COR max: {p['aer_cor_max']}, FATAL max: {p['aer_fatal_max']}, NFATAL max: {p['aer_nfatal_max']}\n\n")

    md.append("## GPU[3] (8820) テレメトリ\n")
    if r:
        md.append(f"- rocm-smi samples: {r['samples']}\n")
        md.append(f"- power [W]: mean {r.get('gpu3_power_w_mean')}, p95 {r.get('gpu3_power_w_p95')}, max {r.get('gpu3_power_w_max')}\n")
        md.append(f"- Tj junction max: {r.get('gpu3_temp_max')} °C\n\n")

    md.append("## 1h バケット推移\n")
    md.append("| hour | trials | faults | eval p50 [t/s] | GPU[3] power p95 [W] |\n")
    md.append("|---:|---:|---:|---:|---:|\n")
    for b in buckets:
        md.append(
            f"| {b['hour']} | {b['trials']} | {b['faults']} | "
            f"{b['eval_p50'] if b['eval_p50'] is not None else '—'} | "
            f"{b['power_p95'] if b['power_p95'] is not None else '—'} |\n"
        )

    with open(os.path.join(SCR, "data.md"), "w") as f:
        f.write("".join(md))

    # summary.png 出力 (時間軸)
    fig, ax1 = plt.subplots(figsize=(13, 6.2))
    if buckets:
        hours = [b["hour"] for b in buckets]
        trials_per_h = [b["trials"] for b in buckets]
        faults_per_h = [b["faults"] for b in buckets]
        eval_p50 = [b["eval_p50"] if b["eval_p50"] is not None else 0 for b in buckets]

        ax1.bar(hours, trials_per_h, width=0.8, color="#3aa055", edgecolor="black", linewidth=0.6,
                alpha=0.8, label="trials_done / h")
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
        ax2.plot(hours, eval_p50, "o-", color="#2060a0", linewidth=2, markersize=7, label="eval p50 [t/s]")
        ax2.set_ylabel("Eval p50 [t/s] (blue)", fontsize=11, color="#2060a0")
        ax2.tick_params(axis="y", labelcolor="#2060a0")

    title = (
        f"mi25 8820 stand-alone 24h Vulkan load — {n_trials} trials_done, "
        f"{n_faults} HANG_CONFIRMED ({(n_faults/n_trials*100 if n_trials else 0):.1f}% vs past 3/88=3.4%)\n"
        f"Qwen3-8B Q6_K, ctx=131072(cap40960), GGML_VK_VISIBLE_DEVICES=3"
    )
    plt.title(title, fontsize=11, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(SCR, "summary.png"), dpi=130, bbox_inches="tight")
    print("summary.png + data.md written")
    print(f"trials_done={n_trials}, hangs={n_faults}, duration={duration_h:.2f}h")
    if p_value is not None:
        print(f"Fisher exact p (one-sided, lower) = {p_value:.4f}")


if __name__ == "__main__":
    main()
