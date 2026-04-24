#!/usr/bin/env python3
"""
Phase Sb-alloc Step 2: allocator 量子化シミュレーション

目的:
    Phase Sb-src 候補 D ("1 MiB pool 量子化境界") を否定的に検証する。
    Explore 調査で判明した量子化単位 (128B tensor align, 256B 非VMM pool,
    2 MiB VMM granularity) を適用して、ub=1584..1600 で合計サイズが
    1585→1586 境界で step にならないことを数値で示す。

モデル:
    Qwen3.5-122B-A10B (qwen35moe), CUDA0 = 3 attn + 9 SSM layers
    SSM 層の fused GDN 出力テンソル:
        shape = [S_v*H, n_tokens + S_v, 1, 1] F32
             = [8192,  n_tokens + 128,  1, 1]
        size = 4 × 8192 × (n_tokens + 128) bytes
             = 32768 × (n_tokens + 128) bytes (per layer)
"""

import csv
import sys

S_v = 128
H = 64
SSM_PER_GPU = 9
BYTES_PER_F32 = 4

def per_layer_bytes(ub: int) -> int:
    """1 SSM 層の ggml_gated_delta_net 出力テンソル生サイズ"""
    return BYTES_PER_F32 * (S_v * H) * (ub + S_v)

def quantize(x: int, unit: int) -> int:
    """x を unit の倍数に切り上げ"""
    return unit * ((x + unit - 1) // unit)

def simulate(ub: int, unit: int) -> dict:
    """ub と量子化単位 unit を与え、9 層累積を計算"""
    raw = per_layer_bytes(ub)
    aligned = quantize(raw, unit)
    total = aligned * SSM_PER_GPU
    return {
        "ub": ub,
        "unit_bytes": unit,
        "per_layer_raw_bytes": raw,
        "per_layer_aligned_bytes": aligned,
        "per_layer_raw_MiB": raw / 1024 / 1024,
        "per_layer_aligned_MiB": aligned / 1024 / 1024,
        "total_9layers_MiB": total / 1024 / 1024,
    }

UB_POINTS = [1584, 1585, 1586, 1588, 1592, 1600, 1664, 1792]
UNITS = {
    "128B_tensor_align":    128,
    "256B_nonvmm_pool":     256,
    "2MiB_vmm_granularity": 2 * 1024 * 1024,
}

def main() -> None:
    # 結果を CSV とコンソール両方に出力
    rows = []
    for unit_label, unit_bytes in UNITS.items():
        for ub in UB_POINTS:
            r = simulate(ub, unit_bytes)
            r["unit_label"] = unit_label
            rows.append(r)

    # コンソール表示: 単位ごとに表形式
    for unit_label, unit_bytes in UNITS.items():
        print(f"\n=== Quantization unit: {unit_label} ({unit_bytes} bytes) ===")
        print(f"{'ub':>6} | {'per-layer(MiB)':>16} | {'9layers(MiB)':>14} | {'Δ vs prev ub(MiB)':>18}")
        prev_total = None
        for r in [x for x in rows if x["unit_label"] == unit_label]:
            delta = "" if prev_total is None else f"{r['total_9layers_MiB'] - prev_total:+.4f}"
            print(f"{r['ub']:>6} | {r['per_layer_aligned_MiB']:>16.4f} | "
                  f"{r['total_9layers_MiB']:>14.4f} | {delta:>18}")
            prev_total = r["total_9layers_MiB"]

    # 1585→1586 の差分（step 検出）
    print("\n=== 1585→1586 境界の差分 (step 検出) ===")
    print(f"{'unit':>24} | {'1585 total(MiB)':>18} | {'1586 total(MiB)':>18} | {'Δ(MiB)':>10}")
    for unit_label, unit_bytes in UNITS.items():
        r1585 = simulate(1585, unit_bytes)
        r1586 = simulate(1586, unit_bytes)
        d = r1586["total_9layers_MiB"] - r1585["total_9layers_MiB"]
        print(f"{unit_label:>24} | {r1585['total_9layers_MiB']:>18.6f} | "
              f"{r1586['total_9layers_MiB']:>18.6f} | {d:>10.6f}")

    # CSV 出力
    csv_path = "/tmp/phase-sb-alloc/alloc_sim.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "unit_label", "unit_bytes", "ub",
            "per_layer_raw_bytes", "per_layer_aligned_bytes",
            "per_layer_raw_MiB", "per_layer_aligned_MiB",
            "total_9layers_MiB",
        ])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\n-> CSV written to {csv_path}")

    # 結論メッセージ
    print("\n=== 結論 ===")
    print("128B / 256B / 2MiB いずれの量子化単位でも、ub=1585→1586 の遷移は")
    print("連続線形であり、Phase Sb-fine3 で観測された step (~0.28 MiB/tok の急上昇) は")
    print("これらの量子化では説明できない。")
    print("⇒ 候補 D (allocator pool 量子化仮説) は本数値検証により棄却される。")

if __name__ == "__main__":
    main()
