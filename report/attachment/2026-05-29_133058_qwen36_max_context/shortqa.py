#!/usr/bin/env python3
"""YaRN 適用時の短文劣化チェック。固定の短い質問を greedy/no-think で投げ答えを記録。
no-YaRN サーバと YaRN サーバで実行し、回答を比較する。"""
import argparse
import json
import sys

import requests

QS = [
    ("17*23", "What is 17 multiplied by 23? Reply with only the number."),
    ("capital_au", "What is the capital city of Australia? Reply with only the city name."),
    ("fox", "Complete with one word: 'The quick brown fox jumps over the lazy ___'. Reply with only the missing word."),
    ("144/12", "What is 144 divided by 12? Reply with only the number."),
    ("primes", "List the first five prime numbers in order, comma-separated."),
    ("antonym", "What is the antonym of 'expand'? Reply with a single word."),
]


def ask(base, q):
    body = {
        "messages": [{"role": "user", "content": q}],
        "max_tokens": 64,
        "temperature": 0,
        "top_k": 1,
        "dry_multiplier": 0,
        "presence_penalty": 0,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    j = requests.post(f"{base}/v1/chat/completions", json=body, timeout=300).json()
    return (j["choices"][0]["message"]["content"] or "").strip().replace("\n", " ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://10.1.4.14:8000")
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", default="/tmp/qwen36_ctx/shortqa_results.jsonl")
    args = ap.parse_args()
    with open(args.out, "a") as f:
        for key, q in QS:
            a = ask(args.base_url, q)
            rec = {"label": args.label, "key": key, "answer": a}
            f.write(json.dumps(rec) + "\n")
            print(f"[{args.label}] {key}: {a[:80]!r}", flush=True)


if __name__ == "__main__":
    main()
