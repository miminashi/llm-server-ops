#!/usr/bin/env python3
"""固定プロンプト集への応答を採取して、モデル間の品質比較に使う。

quality_prompts.jsonl の各問を temp=0.0 (決定論) と temp=1.0 (実運用推奨値) の
2 系統で投げ、応答本文・reasoning_content・timings を保存する。

使い方:
    python3 bench_quality.py --label baseline    --url http://10.8.2.1:8000
    python3 bench_quality.py --label abliterated --url http://10.8.2.1:8000

出力:
    <label>_responses/<id>_t<temp>.json   生レスポンス
    <label>_responses/<id>_t<temp>.txt    本文のみ (diff 用)
    <label>_quality.csv                   1 行 1 応答のメタデータ
"""

import argparse
import csv
import datetime
import json
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

# DeepSeek-V4 は reasoning モデルで、512 tok だと thinking だけで打ち切られ
# content が空になることを実測で確認したため 2048 に引き上げている。
MAX_TOKENS = 2048
SEED = 42
TIMEOUT = 1200
COOLDOWN = 5

# (系統名, temperature, top_p, min_p)
#   t00 : 決定論的な diff 比較用
#   t10 : DeepSeek-V4 の推奨サンプリング (前回セッションの llama-server 起動値と同じ)
VARIANTS = [
    ("t00", 0.0, 1.0, 0.0),
    ("t10", 1.0, 1.0, 0.01),
]

# t10 (確率的サンプリング) は所要時間が長いので代表 3 問のみに絞る。
# t00 は全問実行する。
T10_IDS = {"ja1_reasoning", "en1_reasoning", "code1_impl"}

CSV_FIELDS = [
    "ts", "label", "id", "category", "variant", "temp",
    "prompt_n", "predicted_n", "content_chars", "reasoning_chars",
    "stop_reason", "prompt_per_second", "predicted_per_second",
]


def now() -> str:
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds")


def load_prompts() -> list[dict]:
    items = []
    with open(os.path.join(HERE, "quality_prompts.jsonl"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if "prompt_file" in item:
                with open(os.path.join(HERE, item["prompt_file"]), encoding="utf-8") as pf:
                    body = pf.read()
                item["prompt"] = item.get("prompt_prefix", "") + body + item.get("prompt_suffix", "")
            items.append(item)
    return items


def chat(url: str, prompt: str, temp: float, top_p: float, min_p: float, max_tokens: int) -> dict:
    body = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temp,
        "top_p": top_p,
        "min_p": min_p,
        "seed": SEED,
        "cache_prompt": False,
    }
    if temp == 0.0:
        body["top_k"] = 1
    req = urllib.request.Request(
        url + "/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.load(resp)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, choices=["baseline", "abliterated"])
    ap.add_argument("--url", default="http://10.8.2.1:8000")
    ap.add_argument("--outdir", default=HERE)
    ap.add_argument("--only", default=None,
                    help="この id の問だけ実行する (追加採取用)")
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS,
                    help="max_tokens の上書き (既定 2048)")
    ap.add_argument("--variant-suffix", default="",
                    help="出力ファイル名の variant に付ける接尾辞 (例 _ext4k)")
    args = ap.parse_args()

    respdir = os.path.join(args.outdir, f"{args.label}_responses")
    os.makedirs(respdir, exist_ok=True)
    csv_path = os.path.join(args.outdir, f"{args.label}_quality.csv")
    write_header = not os.path.exists(csv_path)

    prompts = load_prompts()

    with open(csv_path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        if write_header:
            w.writeheader()

        for item in prompts:
            if args.only and item["id"] != args.only:
                continue
            for vname, temp, top_p, min_p in VARIANTS:
                if vname == "t10" and item["id"] not in T10_IDS:
                    continue
                if args.only and vname != "t00":
                    continue
                vname = vname + args.variant_suffix
                t0 = time.time()
                res = chat(args.url, item["prompt"], temp, top_p, min_p, args.max_tokens)
                msg = res["choices"][0]["message"]
                content = msg.get("content") or ""
                reasoning = msg.get("reasoning_content") or ""
                timings = res.get("timings", {})

                base = os.path.join(respdir, f"{item['id']}_{vname}")
                with open(base + ".json", "w", encoding="utf-8") as f:
                    json.dump(res, f, ensure_ascii=False, indent=2)
                with open(base + ".txt", "w", encoding="utf-8") as f:
                    f.write(content)

                w.writerow({
                    "ts": now(), "label": args.label, "id": item["id"],
                    "category": item["category"], "variant": vname, "temp": temp,
                    "prompt_n": timings.get("prompt_n"), "predicted_n": timings.get("predicted_n"),
                    "content_chars": len(content), "reasoning_chars": len(reasoning),
                    "stop_reason": res["choices"][0].get("finish_reason"),
                    "prompt_per_second": round(timings.get("prompt_per_second", 0), 3),
                    "predicted_per_second": round(timings.get("predicted_per_second", 0), 3),
                })
                fh.flush()
                print(f"[{args.label}] {item['id']} {vname}: "
                      f"{len(content)} chars content / {len(reasoning)} chars reasoning, "
                      f"finish={res['choices'][0].get('finish_reason')}, "
                      f"wall {time.time() - t0:.1f}s", flush=True)
                time.sleep(COOLDOWN)

    print(f"wrote {csv_path} and {respdir}/")


if __name__ == "__main__":
    main()
