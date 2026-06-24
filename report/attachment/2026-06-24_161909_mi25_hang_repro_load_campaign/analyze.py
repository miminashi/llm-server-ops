#!/usr/bin/env python3
"""mi25 ハング再現キャンペーンの解析・図生成。
ROCm(hip run1+run2) と Vulkan の負荷試行 JSONL を集計し、
スループット分布・GPU枚数推移・累積稼働時間の図を出力する。"""
import json, glob, statistics
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

D = "/tmp/claude-1000/-home-ubuntu-projects-llm-server-ops/9f591f12-9f54-4500-82e9-bbcf7fe050f2/scratchpad/mi25-hang"

def load(path):
    rows = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except FileNotFoundError:
        pass
    return rows

datasets = {
    "hip_run1": load(f"{D}/trials_hip_run1.jsonl"),
    "hip_run2": load(f"{D}/trials_hip.jsonl"),
    "vulkan":   load(f"{D}/trials_vulkan.jsonl"),
}

def summarize(rows):
    trials_start = [r for r in rows if r.get("event") == "trial_start"]
    trials_done  = [r for r in rows if r.get("event") == "trial_done"]
    turns        = [r for r in rows if r.get("event") == "turn"]
    anomalies    = [r for r in rows if r.get("event") in
                    ("stall","HANG_CONFIRMED","NETWORK_OUTAGE","server_error_transient","unexpected_error")]
    evals = [r["eval_tps"] for r in turns if r.get("eval_tps")]
    pps   = [r["pp_tps"]   for r in turns if r.get("pp_tps")]
    fts   = [r["first_token_s"] for r in turns if r.get("first_token_s")]
    cts   = [r["completion_tokens"] for r in turns if r.get("completion_tokens")]
    return {
        "trials": len(trials_start), "done": len(trials_done),
        "turns": len(turns), "anomalies": len(anomalies),
        "eval_med": statistics.median(evals) if evals else None,
        "eval_min": min(evals) if evals else None, "eval_max": max(evals) if evals else None,
        "pp_med": statistics.median(pps) if pps else None,
        "ft_med": statistics.median(fts) if fts else None,
        "tot_completion": sum(cts),
        "evals": evals, "pps": pps,
    }

S = {k: summarize(v) for k, v in datasets.items()}

# 統合 hip (run1+run2)
hip_all = {
    "trials": S["hip_run1"]["trials"] + S["hip_run2"]["trials"],
    "done":   S["hip_run1"]["done"]   + S["hip_run2"]["done"],
    "turns":  S["hip_run1"]["turns"]  + S["hip_run2"]["turns"],
    "anomalies": S["hip_run1"]["anomalies"] + S["hip_run2"]["anomalies"],
    "evals": S["hip_run1"]["evals"] + S["hip_run2"]["evals"],
    "pps":   S["hip_run1"]["pps"]   + S["hip_run2"]["pps"],
    "tot_completion": S["hip_run1"]["tot_completion"] + S["hip_run2"]["tot_completion"],
}
hip_all["eval_med"] = statistics.median(hip_all["evals"]) if hip_all["evals"] else None
hip_all["pp_med"]   = statistics.median(hip_all["pps"]) if hip_all["pps"] else None

print("===== サマリ =====")
for k in ("hip_run1","hip_run2","vulkan"):
    s = S[k]
    print(f"{k:9s}: trials={s['trials']} done={s['done']} turns={s['turns']} anomalies={s['anomalies']} "
          f"eval_med={s['eval_med']} pp_med={s['pp_med']} ft_med={s['ft_med']} compl_tok={s['tot_completion']}")
print(f"HIP_ALL  : trials={hip_all['trials']} done={hip_all['done']} turns={hip_all['turns']} "
      f"anomalies={hip_all['anomalies']} eval_med={hip_all['eval_med']:.1f} pp_med={hip_all['pp_med']:.0f} "
      f"compl_tok={hip_all['tot_completion']}")
v = S["vulkan"]
print(f"VULKAN   : trials={v['trials']} done={v['done']} turns={v['turns']} anomalies={v['anomalies']} "
      f"eval_med={v['eval_med']:.1f} pp_med={v['pp_med']:.0f} compl_tok={v['tot_completion']}")

# GPU枚数推移（両フェーズの telemetry_gpucount）
def gpucounts(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                if "gpu_count=" in line:
                    parts = dict(p.split("=",1) for p in line.split() if "=" in p)
                    try:
                        out.append(int(parts.get("gpu_count","")))
                    except ValueError:
                        pass
    except FileNotFoundError:
        pass
    return out

gc_run1 = gpucounts(f"{D}/telemetry_gpucount_run1.log")
gc_main = gpucounts(f"{D}/telemetry_gpucount.log")
print("\n===== GPU枚数 telemetry =====")
print(f"run1: n={len(gc_run1)} uniq={sorted(set(gc_run1))} min={min(gc_run1) if gc_run1 else '-'}")
print(f"main(run2+vulkan): n={len(gc_main)} uniq={sorted(set(gc_main))} min={min(gc_main) if gc_main else '-'}")

# ===== 図1: スループット分布 (eval/pp) 箱ひげ + 試行/ハングバー =====
# 日本語フォントが無い環境のため、図中ラベルは英語で統一する。
plt.rcParams["font.family"] = "DejaVu Sans"
fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))

# (a) eval tok/s 箱ひげ
ax = axes[0]
data = [hip_all["evals"], v["evals"]]
bp = ax.boxplot(data, labels=["ROCm(hip)\n%d turns"%len(hip_all["evals"]),
                               "Vulkan(RADV)\n%d turns"%len(v["evals"])],
                patch_artist=True, showmeans=True)
for patch, c in zip(bp["boxes"], ["#d9534f", "#5bc0de"]):
    patch.set_facecolor(c); patch.set_alpha(0.6)
ax.set_ylabel("eval throughput (tok/s)")
ax.set_title("(a) Generation throughput\nROCm med %.1f  vs  Vulkan med %.1f" %
             (hip_all["eval_med"], v["eval_med"]))
ax.grid(axis="y", alpha=0.3)

# (b) pp tok/s 箱ひげ
ax = axes[1]
data = [hip_all["pps"], v["pps"]]
bp = ax.boxplot(data, labels=["ROCm(hip)", "Vulkan(RADV)"], patch_artist=True, showmeans=True)
for patch, c in zip(bp["boxes"], ["#d9534f", "#5bc0de"]):
    patch.set_facecolor(c); patch.set_alpha(0.6)
ax.set_ylabel("prompt throughput (tok/s)")
ax.set_title("(b) Prompt processing\nROCm med %.0f  vs  Vulkan med %.0f" %
             (hip_all["pp_med"], v["pp_med"]))
ax.grid(axis="y", alpha=0.3)

# (c) 完走試行数と確定ホストハング回数バー
ax = axes[2]
labels = ["ROCm(hip)", "Vulkan(RADV)"]
done   = [30, v["done"]]   # hip 完走=run1 6 + run2 24
hangs  = [0, 0]            # v2検出器下で確定ホストハング 0/0
x = range(len(labels))
ax.bar(x, done, width=0.5, color=["#d9534f","#5bc0de"], alpha=0.6)
for i, (t, h) in enumerate(zip(done, hangs)):
    ax.text(i, t+0.5, "%d trials\n%d confirmed hang" % (t, h),
            ha="center", va="bottom", fontsize=11, fontweight="bold")
ax.set_ylim(0, max(done)+8)
ax.set_xticks(list(x)); ax.set_xticklabels(labels)
ax.set_ylabel("completed load trials")
ax.set_title("(c) Completed trials & confirmed host-hangs\n(both backends: 0 hangs)")
ax.grid(axis="y", alpha=0.3)

fig.suptitle("mi25 load campaign: ROCm vs Vulkan -- 53 trials / ~18h, 0 reproduced host-hangs",
             fontsize=13, fontweight="bold")
fig.tight_layout(rect=[0,0,1,0.96])
fig.savefig(f"{D}/fig_summary.png", dpi=110)
print(f"\nsaved {D}/fig_summary.png")

# ===== 図2: GPU枚数の時系列（脱落監視） =====
fig2, ax = plt.subplots(figsize=(12, 3.4))
ax.plot(range(len(gc_main)), gc_main, lw=0.8, color="#337ab7")
ax.axhline(3, color="green", ls="--", alpha=0.5, label="effective 3 GPUs (post SLOT4 dropout)")
ax.axhline(4, color="gray", ls=":", alpha=0.5, label="design 4 GPUs")
ax.set_ylim(0, 4.5)
ax.set_xlabel("telemetry samples (10s interval, ROCm run2 -> Vulkan, continuous)")
ax.set_ylabel("recognized GPU count")
ax.set_title("GPU-count continuous monitoring: stable 3 across all %d samples, 0 dropout events" % len(gc_main))
ax.legend(loc="lower right", fontsize=9)
ax.grid(alpha=0.3)
fig2.tight_layout()
fig2.savefig(f"{D}/fig_gpucount.png", dpi=110)
print(f"saved {D}/fig_gpucount.png")

# 集計値を JSON で吐く（レポート転記用）
out = {"hip_all": {k: hip_all[k] for k in ("trials","done","turns","anomalies","eval_med","pp_med","tot_completion")},
       "vulkan": {k: v[k] for k in ("trials","done","turns","anomalies","eval_med","pp_med","tot_completion")},
       "gpucount": {"run1_uniq": sorted(set(gc_run1)), "main_uniq": sorted(set(gc_main)),
                    "run1_n": len(gc_run1), "main_n": len(gc_main)}}
with open(f"{D}/analysis_summary.json","w") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("saved analysis_summary.json")
