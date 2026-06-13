#!/usr/bin/env python3
# 日本語Wikipediaの本文をMediaWiki API経由で取得し、wikitext形式(段落を空行区切り)で保存する。
# datasets不要・標準ライブラリのみ。
import sys, urllib.request, urllib.parse, json, time, re

out_path = sys.argv[1] if len(sys.argv) > 1 else "ja-wiki.raw"
target_bytes = 600_000

titles = ["日本", "東京都", "富士山", "源氏物語", "織田信長", "量子力学", "人工知能",
          "経済学", "ベートーヴェン", "サッカー", "和食", "生物学", "インターネット",
          "数学", "哲学", "鉄道", "気候変動", "オリンピック", "宇宙", "江戸時代",
          "俳句", "稲作", "地震", "茶道", "アイザック・ニュートン", "細胞", "民主主義",
          "映画", "音楽", "化学"]


def fetch(title):
    url = ("https://ja.wikipedia.org/w/api.php?action=query&prop=extracts"
           "&explaintext=1&format=json&redirects=1&titles=" + urllib.parse.quote(title))
    req = urllib.request.Request(url, headers={"User-Agent": "bench-quality/1.0 (research)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    pages = data["query"]["pages"]
    for _, p in pages.items():
        return p.get("extract", "")
    return ""


chunks = []
total = 0
for t in titles:
    try:
        txt = fetch(t)
    except Exception as e:
        sys.stderr.write(f"skip {t}: {e}\n")
        continue
    txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
    if len(txt) < 100:
        continue
    chunks.append(txt)
    total += len(txt.encode("utf-8"))
    if total >= target_bytes:
        break
    time.sleep(0.3)

text = "\n\n".join(chunks)
with open(out_path, "w", encoding="utf-8") as f:
    f.write(text)
sys.stderr.write(f"WROTE {out_path} bytes={len(text.encode('utf-8'))} docs={len(chunks)}\n")
