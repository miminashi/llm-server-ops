#!/usr/bin/env python3
"""ベンチ用の固定長プロンプトを決定論的に生成する。

素材は wikitext-2-raw の validation split (wiki.valid.raw)。
llama-server の /tokenize エンドポイントで実トークン数を測り、
二分探索で目標トークン数に最も近い文字数の切り出しを求める。

使い方:
    python3 mkprompt.py [--url http://10.8.2.1:8000]

出力:
    prompt_1k.txt  (目標 1215 token)
    prompt_19k.txt (目標 19015 token)

目標値は前回セッション (report/2026-08-16_175749_deepseek_v4_rpc_dual_gpu_server.md)
の計測条件 1,215 tok / 19,015 tok に合わせている。
"""

import argparse
import json
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "wiki.valid.raw")

# 生成する (出力ファイル名, 目標トークン数)
TARGETS = [
    ("prompt_1k.txt", 1215),
    ("prompt_19k.txt", 19015),
]

# 素材の先頭は空行や短い見出しが続くのでオフセットを置く
SKIP_CHARS = 200


def count_tokens(url: str, text: str) -> int:
    req = urllib.request.Request(
        url + "/tokenize",
        data=json.dumps({"content": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return len(json.load(resp)["tokens"])


def cut(raw: str, n_chars: int) -> str:
    """先頭 n_chars を切り出し、最後の改行で丸める (途中の語で切らない)。"""
    s = raw[SKIP_CHARS : SKIP_CHARS + n_chars]
    nl = s.rfind("\n")
    if nl > 0:
        s = s[:nl]
    return s.strip()


def find_text(url: str, raw: str, target: int) -> tuple[str, int]:
    """目標トークン数に最も近い切り出しを二分探索で求める。"""
    lo, hi = 1, len(raw) - SKIP_CHARS
    best = None
    for _ in range(24):
        mid = (lo + hi) // 2
        text = cut(raw, mid)
        n = count_tokens(url, text)
        if best is None or abs(n - target) < abs(best[1] - target):
            best = (text, n)
        if n < target:
            lo = mid + 1
        elif n > target:
            hi = mid - 1
        else:
            break
        if lo > hi:
            break
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://10.8.2.1:8000")
    args = ap.parse_args()

    with open(SRC, encoding="utf-8") as f:
        raw = f.read()

    for name, target in TARGETS:
        text, n = find_text(args.url, raw, target)
        path = os.path.join(HERE, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"{name}: {n} tokens (target {target}), {len(text)} chars")


if __name__ == "__main__":
    main()
