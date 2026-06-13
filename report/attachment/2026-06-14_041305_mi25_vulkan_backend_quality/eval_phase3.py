#!/usr/bin/env python3
# Phase 3(傍証): 実タスク正答率。GSM8K(英)とJMMLU(日)を直接DLし、API評価。
# バックエンド等価性比較のため thinking無効・greedy(temp0)で両バックエンド同条件。
import sys, json, urllib.request, re, csv, io

BACKEND = sys.argv[1] if len(sys.argv) > 1 else "rocm"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 40
OUT = f"phase3-{BACKEND}.json"
URL = "http://127.0.0.1:8000/v1/chat/completions"

GSM8K_URL = "https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/test.jsonl"
# JMMLU: 代表3科目(GitHub raw CSV: question,A,B,C,D,answer)
JMMLU_SUBJECTS = ["world_history", "elementary_mathematics", "high_school_physics"]
JMMLU_BASE = "https://raw.githubusercontent.com/nlp-waseda/JMMLU/main/JMMLU/"


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "bench/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def call(prompt, max_tokens):
    body = json.dumps({
        "model": "q", "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0, "top_k": 1, "seed": 1, "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.load(r)
    return d["choices"][0]["message"].get("content") or ""


def last_number(text):
    nums = re.findall(r"-?\d[\d,]*", text.replace(",", ""))
    return nums[-1] if nums else None


def eval_gsm8k(n):
    lines = http_get(GSM8K_URL).strip().split("\n")[:n]
    correct = 0
    recs = []
    for ln in lines:
        ex = json.loads(ln)
        q = ex["question"]
        gold = ex["answer"].split("####")[-1].strip().replace(",", "")
        prompt = q + "\n\n最後の行に『答え: <数値>』の形式で答えてください。"
        try:
            out = call(prompt, 512)
        except Exception as e:
            recs.append({"err": str(e)}); continue
        pred = last_number(out)
        ok = (pred is not None and pred == gold)
        correct += ok
        recs.append({"gold": gold, "pred": pred, "ok": ok})
    return {"n": len(recs), "correct": correct, "acc": round(correct / max(1, len(recs)), 4), "recs": recs}


def parse_jmmlu_csv(text):
    rows = list(csv.reader(io.StringIO(text)))
    out = []
    for r in rows:
        if len(r) < 6:
            continue
        q, a, b, c, d, ans = r[0], r[1], r[2], r[3], r[4], r[5].strip().upper()
        if ans not in ("A", "B", "C", "D"):
            continue
        out.append((q, a, b, c, d, ans))
    return out


def eval_jmmlu(n):
    items = []
    for subj in JMMLU_SUBJECTS:
        try:
            txt = http_get(JMMLU_BASE + subj + ".csv")
            items += parse_jmmlu_csv(txt)
        except Exception as e:
            sys.stderr.write(f"jmmlu {subj} fetch err: {e}\n")
    items = items[:n]
    correct = 0
    recs = []
    for (q, a, b, c, d, gold) in items:
        prompt = (f"次の問題に答えてください。A〜Dから1つ選び、最後の行に『答え: <記号>』の形式だけで答えてください。\n\n"
                  f"問題: {q}\nA. {a}\nB. {b}\nC. {c}\nD. {d}")
        try:
            out = call(prompt, 256)
        except Exception as e:
            recs.append({"err": str(e)}); continue
        # 「答え:」アンカー後の記号を優先、無ければ全体の最後のA-D
        anchor = re.search(r"答え[^A-DＡ-Ｄ]*([A-DＡ-Ｄ])", out)
        if anchor:
            pred = anchor.group(1).translate(str.maketrans("ＡＢＣＤ", "ABCD"))
        else:
            m = re.findall(r"[ABCD]", out.upper())
            pred = m[-1] if m else None
        ok = (pred == gold)
        correct += ok
        recs.append({"gold": gold, "pred": pred, "ok": ok})
    return {"n": len(recs), "correct": correct, "acc": round(correct / max(1, len(recs)), 4), "recs": recs}


result = {"backend": BACKEND, "gsm8k": eval_gsm8k(N), "jmmlu": eval_jmmlu(N)}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
g, j = result["gsm8k"], result["jmmlu"]
sys.stderr.write(f"[{BACKEND}] GSM8K {g['correct']}/{g['n']} acc={g['acc']} | JMMLU {j['correct']}/{j['n']} acc={j['acc']}\n")
sys.stderr.write(f"WROTE {OUT}\n")
