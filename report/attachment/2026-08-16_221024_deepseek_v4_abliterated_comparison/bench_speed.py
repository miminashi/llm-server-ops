#!/usr/bin/env python3
"""llama-server の /completion timings から pp / tg スループットを採取する。

両モデル (baseline = unsloth UD-Q4_K_XL / abliterated = huihui Q4_K) に対して
まったく同じプロンプト・同じ回数で実行し、CSV に追記する。

使い方:
    python3 bench_speed.py --label baseline    --url http://10.8.2.1:8000
    python3 bench_speed.py --label abliterated --url http://10.8.2.1:8000

重要:
  * `cache_prompt: false` を必ず送る。既定 true のままだと 2 回目以降が
    prompt cache にヒットして pp が無意味な値になる。
  * OpenAI 互換の /v1/chat/completions ではなくネイティブ /completion を使う。
    chat template のオーバーヘッドを排除し、timings をそのまま採れるため。
"""

import argparse
import csv
import datetime
import json
import os
import subprocess
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

# (条件名, プロンプトファイル, 計測回数, warmup 回数)
CONDS = [
    ("pp1k", "prompt_1k.txt", 3, 1),
    ("pp19k", "prompt_19k.txt", 2, 0),
]

N_PREDICT = 128
COOLDOWN = 15
TIMEOUT = 1200
SEED = 42

CSV_FIELDS = [
    "ts", "label", "cond", "run", "kind",
    "prompt_n", "prompt_ms", "prompt_per_second",
    "predicted_n", "predicted_ms", "predicted_per_second",
]


def now() -> str:
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds")


def completion(url: str, prompt: str) -> dict:
    body = {
        "prompt": prompt,
        "n_predict": N_PREDICT,
        "cache_prompt": False,
        "seed": SEED,
        "temperature": 0.0,
        "top_k": 1,
    }
    req = urllib.request.Request(
        url + "/completion",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.load(resp)


def snapshot_vram(outdir: str, label: str, tag: str) -> None:
    """両サーバの VRAM 使用量を記録する (読み取り専用)。"""
    path = os.path.join(outdir, f"vram_{label}.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"=== {now()} {tag} ===\n")
        for host in ("aws-gpu01", "aws-gpu02"):
            out = subprocess.run(
                ["ssh", host, "nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader"],
                capture_output=True, text=True, timeout=60,
            ).stdout
            f.write(f"--- {host} ---\n{out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, choices=["baseline", "abliterated"])
    ap.add_argument("--url", default="http://10.8.2.1:8000")
    ap.add_argument("--outdir", default=HERE)
    args = ap.parse_args()

    csv_path = os.path.join(args.outdir, f"{args.label}_speed.csv")
    write_header = not os.path.exists(csv_path)

    snapshot_vram(args.outdir, args.label, "before-bench")

    with open(csv_path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        if write_header:
            w.writeheader()

        for cond, pfile, n_runs, n_warm in CONDS:
            with open(os.path.join(HERE, pfile), encoding="utf-8") as f:
                prompt = f.read()

            for i in range(n_warm + n_runs):
                kind = "warmup" if i < n_warm else "measure"
                run = i if kind == "warmup" else i - n_warm + 1
                t0 = time.time()
                res = completion(args.url, prompt)
                t = res["timings"]
                row = {
                    "ts": now(), "label": args.label, "cond": cond, "run": run, "kind": kind,
                    "prompt_n": t["prompt_n"], "prompt_ms": round(t["prompt_ms"], 2),
                    "prompt_per_second": round(t["prompt_per_second"], 3),
                    "predicted_n": t["predicted_n"], "predicted_ms": round(t["predicted_ms"], 2),
                    "predicted_per_second": round(t["predicted_per_second"], 3),
                }
                w.writerow(row)
                fh.flush()
                print(f"[{args.label}] {cond} {kind}#{run}: "
                      f"pp {row['prompt_per_second']} t/s ({row['prompt_n']} tok), "
                      f"tg {row['predicted_per_second']} t/s ({row['predicted_n']} tok), "
                      f"wall {time.time() - t0:.1f}s", flush=True)
                time.sleep(COOLDOWN)

    snapshot_vram(args.outdir, args.label, "after-bench")
    print(f"wrote {csv_path}")


if __name__ == "__main__":
    main()
