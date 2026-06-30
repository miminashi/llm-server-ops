#!/usr/bin/env python3
"""memtest_vulkan ログをパースして data.md + summary.png を生成する。

memtest_vulkan v0.5.0 の出力フォーマット:
  https://github.com/GpuZelenograd/memtest_vulkan v0.5.0 by GpuZelenograd
  1: Bus=0x87:00 DevId=0x6860   16GB Radeon Instinct MI25 (RADV VEGA10)
  ...
  Standard 5-minute test of N: Bus=0xXX:00 ...
   <iter> iteration. Passed <sec> seconds  written: <W>GB <Wbw>GB/sec  checked: <C>GB <Cbw>GB/sec
  Standard 5-minute test PASSed! Just press Ctrl+C unless you plan long test run.
  memtest_vulkan: no any errors, testing PASSed.
  [error case]
  Error found. Mode <INITIAL_READ|NEXT_RE_READ>, total errors 0xNNN out of 0xMMM
  Errors address range: 0xAAA..=0xBBB

集計対象: 各ログ 1 つにつき (gpu_bus, iters, secs, checked_gb_total,
total_errors, addr_range, status [PASS|EXTENDED|TIMEOUT|ERROR])
"""
import glob
import os
import re
import sys

SCR = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))

RE_BUS = re.compile(r"Standard 5-minute test of \d+:\s*Bus=0x([0-9a-f]+):", re.I)
RE_ITER = re.compile(r"^\s*(\d+)\s+iteration\.\s+Passed\s+([\d.]+)\s+seconds.*checked:\s+([\d.]+)GB", re.M)
RE_STD_PASS = re.compile(r"Standard 5-minute test PASSed", re.I)
RE_NO_ERR = re.compile(r"no any errors, testing PASSed", re.I)
RE_ERR = re.compile(r"Error found\.\s*Mode\s*(\w+).*total errors\s*0x([0-9a-f]+)\s*out of\s*0x([0-9a-f]+)", re.I)
RE_ADDR = re.compile(r"Errors address range:\s*0x([0-9a-f]+)\.\.=0x([0-9a-f]+)", re.I)

BUS_TO_GUID = {
    "87": ("8820", "SLOT6"),
    "84": ("54068", "SLOT8"),
    "07": ("33301", "SLOT4"),
    "04": ("29525", "SLOT2"),
}


def parse(path):
    with open(path) as f:
        text = f.read()
    m_bus = RE_BUS.search(text)
    bus = m_bus.group(1).lower().lstrip("0") or "0"
    iters_all = RE_ITER.findall(text)
    last_iter = int(iters_all[-1][0]) if iters_all else 0
    # 各 iteration ブロックの "Passed X seconds" の総和ではなく、最後の wall-time
    # 概算: 各行は前回 iteration からの delta seconds。合算で全 elapsed.
    elapsed = sum(float(s) for _, s, _ in iters_all)
    checked_total = sum(float(c) for _, _, c in iters_all)
    std_pass = bool(RE_STD_PASS.search(text))
    no_err = bool(RE_NO_ERR.search(text))
    err_blocks = RE_ERR.findall(text)
    total_errors = sum(int(e[1], 16) for e in err_blocks)
    addr_min = addr_max = None
    addr_blocks = RE_ADDR.findall(text)
    if addr_blocks:
        addr_min = min(int(a[0], 16) for a in addr_blocks)
        addr_max = max(int(a[1], 16) for a in addr_blocks)
    if err_blocks:
        status = "ERROR"
    elif no_err:
        status = "PASS"
    elif std_pass:
        status = "EXTENDED"
    else:
        status = "TIMEOUT"
    return {
        "path": path,
        "bus": bus,
        "iters": last_iter,
        "elapsed_s": round(elapsed, 1),
        "checked_gb": round(checked_total, 1),
        "std_pass": std_pass,
        "no_err": no_err,
        "err_blocks": len(err_blocks),
        "total_errors": total_errors,
        "addr_min": addr_min,
        "addr_max": addr_max,
        "status": status,
    }


def write_data_md(rows, out):
    lines = ["# memtest_vulkan results (data.md)\n"]
    lines.append("| File | Bus | GUID | SLOT | iters | elapsed[s] | checked[GB] | std_pass | err_blocks | total_errors | addr_min | addr_max | status |")
    lines.append("|---|---|---|---|---:|---:|---:|---|---:|---:|---|---|---|")
    for r in rows:
        guid, slot = BUS_TO_GUID.get(r["bus"].zfill(2), ("?", "?"))
        addr_min = f"0x{r['addr_min']:x}" if r["addr_min"] is not None else "-"
        addr_max = f"0x{r['addr_max']:x}" if r["addr_max"] is not None else "-"
        lines.append(
            f"| {os.path.basename(r['path'])} | 0x{r['bus']:>02}:00 | {guid} | {slot} | "
            f"{r['iters']} | {r['elapsed_s']} | {r['checked_gb']} | "
            f"{'Y' if r['std_pass'] else 'N'} | {r['err_blocks']} | {r['total_errors']} | "
            f"{addr_min} | {addr_max} | {r['status']} |"
        )
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")


def write_png(rows, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    total_err = sum(r["total_errors"] for r in rows)
    if total_err > 0:
        # 棒グラフ
        labels = [
            f"{BUS_TO_GUID.get(r['bus'].zfill(2), ('?','?'))[1]}\n"
            f"{os.path.basename(r['path']).replace('mt_','').replace('.log','')}"
            for r in rows
        ]
        vals = [r["total_errors"] for r in rows]
        colors = ["red" if v > 0 else "green" for v in vals]
        fig, ax = plt.subplots(figsize=(max(8, len(rows) * 0.9), 5))
        bars = ax.bar(labels, vals, color=colors)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v, str(v), ha="center", va="bottom", fontsize=8)
        ax.set_ylabel("total_errors (memtest_vulkan)")
        ax.set_title("mi25 memtest_vulkan: total errors by GPU/Run")
        plt.xticks(rotation=30, ha="right", fontsize=8)
        plt.tight_layout()
        plt.savefig(out, dpi=120)
    else:
        # 全 PASS: 表ラスタライズ
        fig, ax = plt.subplots(figsize=(11, max(2, 0.4 * len(rows) + 1.5)))
        ax.axis("off")
        total_checked = sum(r["checked_gb"] for r in rows)
        total_iters = sum(r["iters"] for r in rows)
        header = f"ALL PASS - 0 bad pages detected across {total_checked:.1f} GB checked / {total_iters} iterations"
        ax.set_title(f"mi25 memtest_vulkan summary\n{header}", fontsize=11)
        col_labels = ["File", "GUID", "SLOT", "iters", "elapsed[s]", "checked[GB]", "status"]
        cell_text = []
        for r in rows:
            guid, slot = BUS_TO_GUID.get(r["bus"].zfill(2), ("?", "?"))
            cell_text.append([
                os.path.basename(r["path"]),
                guid, slot, str(r["iters"]),
                f"{r['elapsed_s']:.0f}",
                f"{r['checked_gb']:.0f}",
                r["status"],
            ])
        tbl = ax.table(cellText=cell_text, colLabels=col_labels, cellLoc="center", loc="center")
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(8)
        tbl.scale(1.0, 1.4)
        plt.tight_layout()
        plt.savefig(out, dpi=120)


def main():
    paths = sorted(glob.glob(os.path.join(SCR, "mt_*.log")))
    rows = []
    for p in paths:
        try:
            rows.append(parse(p))
        except Exception as e:
            print(f"PARSE_ERR {p}: {e}", file=sys.stderr)
    write_data_md(rows, os.path.join(SCR, "data.md"))
    write_png(rows, os.path.join(SCR, "summary.png"))
    for r in rows:
        print(f"{os.path.basename(r['path']):40s}  bus=0x{r['bus']:>02}:00  iters={r['iters']:>6}  "
              f"checked={r['checked_gb']:>7.0f}GB  err={r['total_errors']:>4}  status={r['status']}")
    total_err = sum(r["total_errors"] for r in rows)
    total_checked = sum(r["checked_gb"] for r in rows)
    print(f"---\nTOTAL: errors={total_err}  checked={total_checked:.0f}GB  runs={len(rows)}")


if __name__ == "__main__":
    main()
