#!/usr/bin/env python3
"""簡易 Needle-in-a-Haystack + 速度計測。

指定トークン長の haystack を組み立て、needle(8桁コード)を深さ%位置に埋め込み、
greedy/no-think でサーバへ投げて回収可否と pp/tg 速度を記録する。
/tokenize で長さを実測してから組み立てるため、目標長に正確に合わせられる。
"""
import argparse
import json
import random
import re
import sys
import time

import requests

FILLER = (
    "The city of Verlund kept its archives in a quiet stone hall by the river. "
    "Clerks copied ledgers by hand, noting harvests, tariffs, and the names of ships. "
    "Each morning the bells rang twice, and the market filled with traders from the coast. "
    "Scholars argued about tides, comets, and the proper way to bind a book. "
    "In the evening the lamps were lit, and the streets smelled of bread and rain. "
)


def tokenize_count(base_url, text, timeout=120):
    r = requests.post(f"{base_url}/tokenize", json={"content": text}, timeout=timeout)
    r.raise_for_status()
    return len(r.json()["tokens"])


def build_prompt(base_url, target_tokens, depth_frac, code):
    """目標トークン長の haystack を作り、depth_frac の位置に needle を挿入する。"""
    needle = f" The secret access code is {code}. Remember this code. "
    question = (
        "\n\nBased on the text above, what is the secret access code? "
        "Answer with only the 8-digit number and nothing else."
    )
    overhead = tokenize_count(base_url, needle + question)
    body_target = max(64, target_tokens - overhead)

    per = tokenize_count(base_url, FILLER)
    reps = max(1, round(body_target / per))
    body = FILLER * reps
    # 微調整: 目標 ±2% に収める
    while tokenize_count(base_url, body) > body_target and reps > 1:
        reps -= 1
        body = FILLER * reps
    while tokenize_count(base_url, body) < body_target * 0.98:
        reps += 1
        body = FILLER * reps

    # depth 位置(文字数ベースで近似)に needle 挿入
    cut = int(len(body) * depth_frac)
    # 文の途中を避け、最寄りのスペースへ
    sp = body.find(" ", cut)
    if sp == -1:
        sp = cut
    prompt = body[:sp] + needle + body[sp:] + question
    return prompt


def run_one(base_url, target_tokens, depth_frac, max_tokens, timeout):
    code = f"{random.randint(10000000, 99999999):d}"  # 先頭ゼロなしの8桁
    prompt = build_prompt(base_url, target_tokens, depth_frac, code)
    prompt_tokens = tokenize_count(base_url, prompt)
    body = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "top_k": 1,
        "dry_multiplier": 0,  # サーバ default の DRY 末尾切断を回避 (数字列の末尾欠落対策)
        "presence_penalty": 0,  # greedy 回収を阻害しないよう抑止
        "cache_prompt": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    t0 = time.time()
    r = requests.post(f"{base_url}/v1/chat/completions", json=body, timeout=timeout)
    wall = time.time() - t0
    r.raise_for_status()
    j = r.json()
    answer = j["choices"][0]["message"]["content"] or ""
    # think ブロックを除去してからコード照合(保険)
    clean = re.sub(r"<think>.*?</think>", "", answer, flags=re.S)
    found = code in clean.replace(",", "").replace(" ", "") or code in answer
    usage = j.get("usage", {})
    timings = j.get("timings", {}) or {}
    pp_tps = timings.get("prompt_per_second")
    tg_tps = timings.get("predicted_per_second")
    pred_n = timings.get("predicted_n") or usage.get("completion_tokens")
    # timings 欠落時は wall-clock 近似
    if tg_tps is None and pred_n:
        tg_tps = pred_n / wall if wall > 0 else None
    return {
        "target_tokens": target_tokens,
        "prompt_tokens": prompt_tokens,
        "depth": round(depth_frac, 3),
        "code": code,
        "found": found,
        "answer": answer[:200],
        "pp_tps": pp_tps,
        "tg_tps": tg_tps,
        "prompt_n": timings.get("prompt_n") or usage.get("prompt_tokens"),
        "predicted_n": pred_n,
        "wall_s": round(wall, 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://10.1.4.14:8000")
    ap.add_argument("--ctx", type=int, required=True, help="目標プロンプトトークン長")
    ap.add_argument("--depths", default="0.1,0.5,0.99")
    ap.add_argument("--label", default="", help="段階ラベル(S0等)")
    ap.add_argument("--max-tokens", type=int, default=64)
    ap.add_argument("--timeout", type=int, default=5400)
    ap.add_argument("--out", default="/tmp/qwen36_ctx/niah_results.jsonl")
    args = ap.parse_args()

    depths = [float(x) for x in args.depths.split(",")]
    with open(args.out, "a") as f:
        for d in depths:
            res = run_one(args.base_url, args.ctx, d, args.max_tokens, args.timeout)
            res["label"] = args.label
            f.write(json.dumps(res) + "\n")
            f.flush()
            ok = "OK " if res["found"] else "MISS"
            print(
                f"[{args.label}] ctx={args.ctx} depth={d:.2f} "
                f"prompt_n={res['prompt_n']} found={ok} "
                f"pp={res['pp_tps']:.1f}t/s tg={res['tg_tps']:.1f}t/s "
                f"wall={res['wall_s']}s ans={res['answer'][:40]!r}",
                flush=True,
            )


if __name__ == "__main__":
    main()
