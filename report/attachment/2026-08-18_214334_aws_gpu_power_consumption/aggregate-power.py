#!/usr/bin/env python3
"""aws-gpu01 / aws-gpu02 の電力サンプルをフェーズ別に集計する。

power-sampler.sh / rapl-sampler.sh / dcmi-only-sampler.sh が吐いた CSV を読み、
測定中に起きた llama-server の再起動を境にフェーズへ切り分けて統計を出す。

  A 通常運用   : モデル常駐。旧 llama-server が推論を処理していた時間帯を含む
  B サーバ停止 : llama-server / rpc-server が落ち、GPU に何も載っていない状態
  C モデルロード: 新 llama-server が 153.3 GiB を読み込んで GPU に配っている最中
  D ロード後   : モデル常駐に戻り、推論は流れていない状態

A 期間内の「推論中 / 推論なし」は llama-server ログの launch_slot_ と release の
対から作った実区間で判定する（GPU utilization の 10 秒スナップショットでは
短い推論を取りこぼすため）。

使い方: aggregate-power.py
"""
import csv
import os
from statistics import mean, median

HERE = os.path.dirname(os.path.abspath(__file__))
RAPL_WRAP = 262143328850  # max_energy_range_uj（両機とも同値）
OLD_LLAMA_START = 1787050949  # 旧 llama-server の起動 epoch (20:02:29 JST)

# フェーズ境界（JST）。llama-server ログと ps の起動時刻から確定した。
PHASES = [
    ("A 通常運用（モデル常駐）", 1787054171, 1787055446),   # 20:56:11 - 21:17:26
    ("B サーバ停止（GPU 空）",   1787055446, 1787055590),   # 21:17:26 - 21:19:50
    ("C モデルロード中",         1787055590, 1787055883),   # 21:19:50 - 21:24:43
    ("D ロード後アイドル",       1787055883, 1787060000),   # 21:24:43 -
]


def pct(xs, q):
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def load_power(path):
    rows, missing = [], 0
    with open(path) as f:
        for r in csv.DictReader(f):
            if r["status"] != "ok" or not r["chassis_w"] or not r["gpu_total_w"]:
                missing += 1
                continue
            utils = [int(u) for u in r["gpu_util"].split(";") if u != ""]
            rows.append({"epoch": int(r["epoch"]), "server": r["server"],
                         "chassis": float(r["chassis_w"]), "gpu": float(r["gpu_total_w"]),
                         "busy": sum(utils) > 0})
    return rows, missing


def load_dcmi(path):
    """ssh を張らずに BMC だけで採ったシャーシ電力（測定対象の CPU を起こさない）。"""
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        for r in csv.DictReader(f):
            if r["chassis_w"]:
                rows.append({"epoch": int(r["epoch"]), "server": r["server"],
                             "chassis": float(r["chassis_w"])})
    return rows


def load_rapl(path):
    """累積エネルギーを隣接差分して epoch//10 -> (cpu_w, dram_w) にする。

    gpu02 は CPU2 側に DIMM が無く intel-rapl:1:0 (dram) が存在しないため、
    行の列数は 4 と 5 の両方がありうる。
    """
    rows = []
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("epoch"):
                continue
            parts = line.split(",")
            if len(parts) >= 4:
                rows.append([int(x) for x in parts])
    out = {}
    for prev, cur in zip(rows, rows[1:]):
        dt = cur[0] - prev[0]
        if dt <= 0:
            continue

        def delta(i, prev=prev, cur=cur):
            if i >= len(cur) or i >= len(prev):
                return 0
            d = cur[i] - prev[i]
            return d + RAPL_WRAP if d < 0 else d  # カウンタ一周を補正
        out[cur[0] // 10] = ((delta(1) + delta(2)) / dt / 1e6,
                             (delta(3) + delta(4)) / dt / 1e6)
    return out


def load_llama_intervals(path, start_epoch):
    """llama-server ログの launch_slot_ / release から推論区間を作る。

    ログ先頭の時刻はプロセス起動からの経過 MM.SS.mmm.uuu なので起動 epoch を足す。
    """
    import re
    ivs, open_at = [], None
    pat = re.compile(r"^(\d+)\.(\d+)\.(\d+)\.\d+\s+I slot\s+(launch_slot_|release):")
    if not os.path.exists(path):
        return ivs
    with open(path, errors="replace") as f:
        for line in f:
            m = pat.match(line)
            if not m:
                continue
            t = start_epoch + int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 1000
            if m.group(4) == "launch_slot_":
                open_at = t
            elif open_at is not None:
                ivs.append((open_at, t))
                open_at = None
    return ivs


def line(label, xs, unit="W"):
    if not xs:
        return
    print(f"    {label:<16} mean {mean(xs):7.1f} {unit} | p50 {median(xs):7.1f} | "
          f"p95 {pct(xs, 0.95):7.1f} | min {min(xs):7.1f} | max {max(xs):7.1f}")


def report(title, rows, rapl, n_note=""):
    if not rows:
        return
    print(f"\n  ## {title}  (n={len(rows)}{n_note})")
    line("シャーシ全体", [r["chassis"] for r in rows])
    line("GPU 合計", [r["gpu"] for r in rows])
    cpu = [rapl[r["epoch"] // 10][0] for r in rows if r["epoch"] // 10 in rapl]
    dram = [rapl[r["epoch"] // 10][1] for r in rows if r["epoch"] // 10 in rapl]
    if cpu:
        line("CPU パッケージ", cpu)
        line("DRAM", dram)
        other = [r["chassis"] - r["gpu"] - rapl[r["epoch"] // 10][0] - rapl[r["epoch"] // 10][1]
                 for r in rows if r["epoch"] // 10 in rapl]
        line("その他", other)
        print("      （その他 = ファン / 基板 / PLX / HBA / NIC / ドライブ / PSU 変換損失）")
    else:
        line("非 GPU 分", [r["chassis"] - r["gpu"] for r in rows])


def cost(watt, label):
    kwh_d = watt * 24 / 1000
    print(f"\n  {label}: {watt:.0f} W → {kwh_d:.2f} kWh/日 / {kwh_d * 30:.1f} kWh/月 / "
          f"{kwh_d * 365:.0f} kWh/年")
    for rate in (20, 30, 40):
        print(f"      {rate} 円/kWh : {kwh_d * rate:6.0f} 円/日 | "
              f"{kwh_d * 30 * rate:8.0f} 円/月 | {kwh_d * 365 * rate:9.0f} 円/年")


def main():
    intervals = load_llama_intervals(os.path.join(HERE, "llama-server.log"), OLD_LLAMA_START)
    print(f"旧 llama-server ログから推論区間 {len(intervals)} 件 "
          f"(合計 {sum(b - a for a, b in intervals) / 60:.1f} 分) を読み込み")

    store = {}
    for srv in ("aws-gpu01", "aws-gpu02"):
        rows, missing = load_power(os.path.join(HERE, f"power_{srv}.csv"))
        dcmi = load_dcmi(os.path.join(HERE, f"dcmi_{srv}.csv"))
        rapl = load_rapl(os.path.join(HERE, f"rapl_{srv}.csv"))
        store[srv] = {"rows": rows, "dcmi": dcmi, "rapl": rapl, "missing": missing}

        print(f"\n{'=' * 74}\n# {srv}   有効 {len(rows)} / 欠測 {missing} "
              f"({100 * missing / max(1, len(rows) + missing):.1f}%)\n{'=' * 74}")
        for name, a, b in PHASES:
            sub = [r for r in rows if a <= r["epoch"] < b]
            report(name, sub, rapl)
            if name.startswith("A"):
                inf = [r for r in sub if any(x <= r["epoch"] <= y for x, y in intervals)]
                idl = [r for r in sub if not any(x <= r["epoch"] <= y for x, y in intervals)]
                report("A-1 うち推論中（llama ログ基準）", inf, rapl)
                report("A-2 うち推論なし（モデル常駐アイドル）", idl, rapl)
        if dcmi:
            print(f"\n  ## D' ssh を張らない再測定（BMC のみ・モデル常駐アイドル）  (n={len(dcmi)})")
            line("シャーシ全体", [r["chassis"] for r in dcmi])
            rr = [r for r in dcmi if r["epoch"] // 10 in rapl]
            if rr:
                line("CPU パッケージ", [rapl[r["epoch"] // 10][0] for r in rr])
                line("DRAM", [rapl[r["epoch"] // 10][1] for r in rr])

    # ---- 2 台合計 ----
    print(f"\n{'=' * 74}\n# aws-gpu01 + aws-gpu02 合計（RPC 分散スタック全体）\n{'=' * 74}")
    b2 = {r["epoch"] // 10: r for r in store["aws-gpu02"]["rows"]}
    joined = []
    for r in store["aws-gpu01"]["rows"]:
        k = r["epoch"] // 10
        m = b2.get(k) or b2.get(k - 1) or b2.get(k + 1)
        if m:
            joined.append({"epoch": r["epoch"], "chassis": r["chassis"] + m["chassis"],
                           "gpu": r["gpu"] + m["gpu"], "busy": r["busy"] or m["busy"]})
    d2 = {r["epoch"] // 10: r for r in store["aws-gpu02"]["dcmi"]}
    jd = []
    for r in store["aws-gpu01"]["dcmi"]:
        k = r["epoch"] // 10
        m = d2.get(k) or d2.get(k - 1) or d2.get(k + 1)
        if m:
            jd.append({"epoch": r["epoch"], "chassis": r["chassis"] + m["chassis"]})

    scen = {}
    for name, a, b in PHASES:
        sub = [r for r in joined if a <= r["epoch"] < b]
        report(name, sub, {})
        if name.startswith("A"):
            inf = [r for r in sub if any(x <= r["epoch"] <= y for x, y in intervals)]
            idl = [r for r in sub if not any(x <= r["epoch"] <= y for x, y in intervals)]
            report("A-1 うち推論中", inf, {})
            report("A-2 うち推論なし（モデル常駐アイドル）", idl, {})
            if inf:
                scen["推論中"] = mean([r["chassis"] for r in inf])
            if idl:
                scen["モデル常駐アイドル"] = mean([r["chassis"] for r in idl])
        elif name.startswith("B") and sub:
            scen["サーバ停止（GPU 空・OS 稼働）"] = mean([r["chassis"] for r in sub])
        elif name.startswith("C") and sub:
            scen["モデルロード中"] = mean([r["chassis"] for r in sub])
    if jd:
        print(f"\n  ## D' ssh を張らない再測定（BMC のみ）  (n={len(jd)})")
        line("シャーシ全体", [r["chassis"] for r in jd])
        scen["モデル常駐アイドル（BMC のみで再測定）"] = mean([r["chassis"] for r in jd])

    print(f"\n{'=' * 74}\n# 電気代試算（2 台合計・24 時間連続換算）\n{'=' * 74}")
    for k, v in scen.items():
        cost(v, k)


if __name__ == "__main__":
    main()
