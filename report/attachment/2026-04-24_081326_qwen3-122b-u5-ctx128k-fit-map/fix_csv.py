#!/usr/bin/env python3
"""fix_csv.py - phaseU5_results.csv の ts 列カンマ問題を修正 (22 列 → 19 列に正規化)
ts フィールドが "11,12,13,14" のようにカンマ区切りで書き出されたため、行が 22 列になる。
これを "11-12-13-14" 形式に正規化。"""
import csv
from pathlib import Path
import shutil

SCRIPT_DIR = Path(__file__).parent
CSV = SCRIPT_DIR / "phaseU5_results.csv"
BAK = SCRIPT_DIR / "phaseU5_results.csv.bak"

shutil.copy(CSV, BAK)

with CSV.open() as f:
    lines = f.readlines()

header = lines[0].rstrip("\n")
header_cols = header.split(",")
n_cols = len(header_cols)  # 19

out = [header + "\n"]
for ln in lines[1:]:
    ln = ln.rstrip("\n")
    fields = ln.split(",")
    if len(fields) == n_cols:
        out.append(ln + "\n")
        continue
    # 22 列想定: ts 列 (index 4) がカンマ展開されて 4 フィールドに
    extra = len(fields) - n_cols
    if extra < 0:
        print(f"WARN: short row, skipping: {ln}")
        continue
    # index 4 .. 4+extra を結合 (ハイフン区切りに)
    ts_parts = fields[4 : 5 + extra]
    ts_joined = "-".join(ts_parts)
    new_fields = fields[:4] + [ts_joined] + fields[5 + extra :]
    if len(new_fields) != n_cols:
        print(f"WARN: normalize failed ({len(new_fields)} cols): {ln}")
        continue
    out.append(",".join(new_fields) + "\n")

with CSV.open("w") as f:
    f.writelines(out)

print(f"[fix_csv] wrote {CSV} ({len(out)-1} data rows)")
print(f"[fix_csv] backup: {BAK}")
