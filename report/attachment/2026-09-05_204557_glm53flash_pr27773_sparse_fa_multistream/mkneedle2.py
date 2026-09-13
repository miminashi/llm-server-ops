#!/usr/bin/env python3
"""needle-in-a-haystack 用の日本語長文を生成する（2 か所埋め版）。

2026-08-29 の mkneedle.py を拡張したもの。PR #27754 / #27752 のスレッドで
feni6 が報告した depth collapse の判定条件が「浅い位置と深い位置に埋めた
2 つの合言葉を両方とも正確に答えられること」なので、それに合わせて
合言葉を 2 か所（全体の 12% 地点と 88% 地点）に埋める。

usage: mkneedle2.py <seed> <phrase_shallow> <phrase_deep> <out.json> [n_para] [max_tokens]
"""
import json, random, sys

TOPICS = ["半導体設計", "海洋観測", "都市計画", "醸造技術", "気象予報", "古文書修復",
          "鉄道信号", "農業灌漑", "宇宙望遠鏡", "音響設計", "森林管理", "橋梁点検",
          "電力系統", "港湾荷役", "地質調査", "織物染色", "製紙工程", "冷凍物流"]
VERBS = ["検討が進んでいる", "課題として残っている", "見直しが求められる", "実証が始まった",
         "評価軸の再定義が必要になる", "従来手法との差が縮まりつつある", "標準化の議論が続く",
         "現場の運用と乖離しやすい", "定量化の手法が確立していない", "投資判断が分かれている"]
ADJ = ["段階的な", "限定的な", "抜本的な", "継続的な", "実務的な", "定量的な", "分散的な",
       "局所的な", "累積的な", "横断的な"]
NOUN = ["移行計画", "監視体制", "冗長構成", "保守周期", "試験方法", "調達要件", "教育課程",
        "記録様式", "検収基準", "運用指針"]


def make(seed, phrase_a, phrase_b, n_para):
    rnd = random.Random(seed)
    paras = []
    for i in range(n_para):
        t = rnd.choice(TOPICS)
        sents = []
        for _ in range(rnd.randint(4, 6)):
            sents.append(f"{t}の分野では、{rnd.choice(ADJ)}{rnd.choice(NOUN)}について{rnd.choice(VERBS)}。"
                         f"特に第{rnd.randint(1,99)}節で示された{rnd.choice(NOUN)}は、"
                         f"{rnd.choice(ADJ)}観点から{rnd.choice(VERBS)}とされる。")
        paras.append(f"【第{i+1}項】" + "".join(sents))
    # 深い側から先に挿すことで、浅い側の挿入で添字がずれないようにする
    pos_b = int(n_para * 0.88)
    pos_a = int(n_para * 0.12)
    paras.insert(pos_b, f"【重要B】この文書の第二の合言葉は「{phrase_b}」である。以降の項目でもこの値は変わらない。")
    paras.insert(pos_a, f"【重要A】この文書の第一の合言葉は「{phrase_a}」である。以降の項目でもこの値は変わらない。")
    return "\n\n".join(paras)


if __name__ == "__main__":
    seed = int(sys.argv[1])
    phrase_a = sys.argv[2]
    phrase_b = sys.argv[3]
    out = sys.argv[4]
    n_para = int(sys.argv[5]) if len(sys.argv) > 5 else 170
    max_tokens = int(sys.argv[6]) if len(sys.argv) > 6 else 256
    body = make(seed, phrase_a, phrase_b, n_para)
    prompt = (body + "\n\n---\n\n上の文書には合言葉が二つ書かれています。"
              "第一の合言葉と第二の合言葉を、そのまま順に答えてください。説明は不要です。")
    payload = {"messages": [{"role": "user", "content": prompt}],
               "temperature": 0, "top_p": 1.0, "max_tokens": max_tokens, "stream": False}
    with open(out, "w") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f"{out}: {len(prompt)} chars, A={phrase_a} B={phrase_b}, n_para={n_para}")
