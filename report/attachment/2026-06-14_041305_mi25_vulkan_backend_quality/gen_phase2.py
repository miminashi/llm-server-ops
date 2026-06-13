#!/usr/bin/env python3
# Phase 2: greedy生成の破綻チェック。
# 日英の代表プロンプトをtemp=0/seed固定で /v1/chat/completions に送り、出力と破綻指標を保存する。
import sys, json, urllib.request, re, time

BACKEND = sys.argv[1] if len(sys.argv) > 1 else "rocm"
OUT = sys.argv[2] if len(sys.argv) > 2 else f"phase2-{BACKEND}.json"
URL = "http://127.0.0.1:8000/v1/chat/completions"

PROMPTS = [
    ("ja", "qa",      "光合成の仕組みを3文で説明してください。"),
    ("ja", "summary", "次の文章を1文で要約してください:『人工知能は近年急速に発展し、画像認識や自然言語処理など多くの分野で人間に匹敵する性能を示すようになった。一方で、計算資源の消費やバイアスといった課題も指摘されている。』"),
    ("ja", "code",     "Pythonでフィボナッチ数列の最初の10項を返す関数を書いてください。コードのみ示してください。"),
    ("ja", "reason",   "数列 3, 6, 11, 18, 27 の次に来る数は何ですか。理由も述べてください。"),
    ("ja", "format",   "日本の都道府県を3つ、JSON配列の形式だけで出力してください。"),
    ("en", "qa",       "Explain how photosynthesis works in three sentences."),
    ("en", "summary",  "Summarize the following in one sentence: 'Artificial intelligence has advanced rapidly in recent years, achieving human-level performance in many areas such as image recognition and natural language processing. At the same time, concerns about compute consumption and bias have been raised.'"),
    ("en", "code",     "Write a Python function that returns the first 10 Fibonacci numbers. Show only the code."),
    ("en", "reason",   "What number comes next in the sequence 3, 6, 11, 18, 27? Explain your reasoning."),
    ("en", "format",   "Output exactly three Japanese prefectures as a JSON array, nothing else."),
]


def call(prompt):
    # thinking無効化で完結した回答を得る(破綻/整合性の比較を明瞭にするため)
    body = json.dumps({
        "model": "qwen",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0, "top_k": 1, "seed": 1, "max_tokens": 512,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def max_ngram_rep(text, n=8):
    # 連続するn語(空白区切りが無い日本語はn文字)の最大反復回数の指標
    toks = text.split()
    if len(toks) < n * 3:
        toks = list(text)  # 日本語向け: 文字単位
        n = 12
    grams = {}
    mx = 0
    for i in range(len(toks) - n):
        g = tuple(toks[i:i+n])
        grams[g] = grams.get(g, 0) + 1
        mx = max(mx, grams[g])
    return mx


def garble_ratio(text):
    if not text:
        return 0.0
    bad = sum(1 for c in text if c == "�" or (ord(c) < 32 and c not in "\n\t\r"))
    return bad / len(text)


results = []
for lang, kind, prompt in PROMPTS:
    t0 = time.time()
    try:
        resp = call(prompt)
        choice = resp["choices"][0]
        content = choice["message"]["content"] or ""
        finish = choice.get("finish_reason")
    except Exception as e:
        results.append({"lang": lang, "kind": kind, "error": str(e)})
        sys.stderr.write(f"[{BACKEND}] {lang}/{kind} ERROR {e}\n")
        continue
    rec = {
        "lang": lang, "kind": kind, "prompt": prompt, "content": content,
        "finish_reason": finish, "len_chars": len(content),
        "empty": len(content.strip()) == 0,
        "max_rep": max_ngram_rep(content),
        "garble_ratio": round(garble_ratio(content), 5),
        "elapsed_s": round(time.time() - t0, 1),
    }
    results.append(rec)
    sys.stderr.write(f"[{BACKEND}] {lang}/{kind} len={rec['len_chars']} fin={finish} rep={rec['max_rep']} garble={rec['garble_ratio']} {rec['elapsed_s']}s\n")

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
sys.stderr.write(f"WROTE {OUT} ({len(results)} records)\n")
