#!/usr/bin/env python3
"""
合成 opencode 負荷ドライバ（1試行 = 多ターンのコーディング会話）。

opencode の build フェーズを模し、Rails アプリへの機能実装をモデルに繰り返し指示して
assistant 出力を会話に積み上げ、1試行 wall-clock が TRIAL_SECONDS に達するまで
連続推論を続ける。各ターンを JSONL に記録する。

ストリーミングのチャンク間タイムアウトでホストハングを素早く検出する:
  リクエストが ReadTimeout / 接続断 → 三点確認(health + ping + ssh)。
  ホストハング確定 → hang_info.json を書き出し exit 42。
  単なるサーバ不調(三点はOK) → エラー記録し当該試行を打ち切り exit 0。

Usage:
  load_driver.py --endpoint http://10.1.4.13:8000 --model <m> --server mi25 \
      --backend hip --trial-seconds 600 --trial-no 1 \
      --jsonl out.jsonl --hang-json hang_info.json
"""
import argparse, json, time, sys, subprocess, socket, urllib.request, urllib.error
import http.client

import requests  # type: ignore

SYSTEM_PROMPT = """You are a senior Ruby on Rails engineer working inside an autonomous coding agent (opencode).
You implement features end-to-end: read the request, think step by step, then output complete, runnable code
with file paths, migrations, models, controllers, views, and RSpec tests. Be thorough and production-grade.
Follow Rails 8 conventions. Always include tests. Explain your reasoning before the code."""

# opencode bench と同テーマ（search / pagination / disk-usage）のコーディング指示を周回させる
TASKS = [
    "Implement case-insensitive full-text search over the Video model's title and description using ILIKE, "
    "with a controller scope, a search form, empty-query handling, and RSpec request + model specs. Show all files.",
    "Add pagination to the videos index using the kaminari gem: 20 per page, page navigation at the bottom, "
    "and tests covering page boundaries. Provide the Gemfile change, controller, view, and specs.",
    "Add a disk-usage dashboard block to the videos index that shows total capacity, free space, and the app's "
    "ActiveStorage usage (sum of blob byte_size), using the sys-filesystem gem. Include a service object and specs.",
    "Refactor the search to support multiple keywords (AND semantics across title/description), keep it "
    "case-insensitive, add a scope, and write specs for multi-term queries and the empty case.",
    "Add sorting (by created_at and by title, asc/desc) to the paginated, searchable videos index. Keep pagination "
    "and search working together. Provide controller, view, helper, and request specs.",
]

def now():
    return time.time()

BMC_IP = "10.1.4.7"               # mi25 BMC（ホストとは別経路・別電源。生死判定の鍵）
SITE_REFS = ["10.1.5.1", "10.1.1.1"]  # mi25 と同一拠点の常時稼働参照。
# 注意: 制御ホストと同拠点の参照(例 10.1.6.4)は mi25 拠点側の NW 障害を検出できないため使わない。
# 真のホストハング判定には「BMC 到達可 かつ mi25拠点参照 到達可（＝拠点NWとBMCは生存、ホストのみ死）」を要求する。

def _ping(ip, count=2, wait=2):
    return subprocess.run(["ping", "-c", str(count), "-W", str(wait), ip],
                          capture_output=True).returncode == 0

def classify_outage(server, endpoint):
    """三点確認(health/ping/ssh)が全滅したとき、BMC と外部参照の到達性で原因を分類する。
    戻り値 status: 'OK'(まだ生存/一過性) / 'HOST_HANG'(ホストのみ死=真のハング) /
                   'NETWORK'(BMC や参照も不達=ネットワーク障害, リセット不要)。
    ※ 三点全滅でも NETWORK の場合があるため、BMC 到達性を弁別子に使う(これが今回の教訓)。"""
    res = {}
    try:
        r = requests.get(endpoint + "/health", timeout=5)
        res["health"] = r.status_code
    except Exception as e:
        res["health"] = "000:" + type(e).__name__
    ip = endpoint.split("//")[1].split(":")[0]
    res["host_ping"] = _ping(ip)
    res["ssh_ok"] = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", server, "true"],
        capture_output=True).returncode == 0
    host_dead = (str(res["health"]).startswith("000")) and (not res["host_ping"]) and (not res["ssh_ok"])
    if not host_dead:
        res["status"] = "OK"
        return "OK", res
    # ホスト三点死 → BMC と「mi25拠点」参照で弁別
    res["bmc_ping"] = _ping(BMC_IP)
    res["site_refs"] = {ip: _ping(ip) for ip in SITE_REFS}
    site_up = any(res["site_refs"].values())
    if res["bmc_ping"] and site_up:
        # mi25拠点NWもBMCも生存・ホストだけ死 = 真のホストハング
        res["status"] = "HOST_HANG"
    else:
        # BMC不達 か mi25拠点参照も全滅 = 拠点/経路のネットワーク障害（ホストは生存の可能性大）
        res["status"] = "NETWORK"
    return res["status"], res

def stream_chat(endpoint, model, messages, max_tokens, read_timeout):
    """ストリーミングで1ターン生成。テキストとusage、first-token遅延を返す。
    ReadTimeout/接続断は例外を投げる(呼び出し側でハング判定)。"""
    url = endpoint + "/v1/chat/completions"
    payload = {
        "model": model, "messages": messages, "max_tokens": max_tokens,
        "temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0,
        "stream": True, "stream_options": {"include_usage": True},
    }
    t0 = now()
    content = []
    reasoning = []
    first_tok = None
    usage = None
    with requests.post(url, json=payload, stream=True, timeout=(10, read_timeout)) as r:
        r.raise_for_status()
        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: "):
                line = line[6:]
            if line.strip() == "[DONE]":
                break
            try:
                obj = json.loads(line)
            except Exception:
                continue
            ch = obj.get("choices") or []
            if ch:
                delta = ch[0].get("delta", {})
                # Qwen3.6 thinking: 出力は content または reasoning_content に出る
                piece = delta.get("content") or ""
                rpiece = delta.get("reasoning_content") or ""
                if piece or rpiece:
                    if first_tok is None:
                        first_tok = now() - t0
                if piece:
                    content.append(piece)
                if rpiece:
                    reasoning.append(rpiece)
            if obj.get("usage"):
                usage = obj["usage"]
    return "".join(content), "".join(reasoning), usage, first_tok, now() - t0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--server", required=True)
    ap.add_argument("--backend", required=True)
    ap.add_argument("--trial-seconds", type=int, default=600)
    ap.add_argument("--trial-no", type=int, required=True)
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--read-timeout", type=int, default=200)
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--hang-json", required=True)
    args = ap.parse_args()

    jf = open(args.jsonl, "a")
    def rec(d):
        d["epoch"] = now()
        d["trial"] = args.trial_no
        d["backend"] = args.backend
        jf.write(json.dumps(d, ensure_ascii=False) + "\n")
        jf.flush()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    trial_start = now()
    turn = 0
    rec({"event": "trial_start", "trial_seconds": args.trial_seconds})
    while now() - trial_start < args.trial_seconds:
        task = TASKS[turn % len(TASKS)]
        # 会話を膨らませつつ、各ターンで新しい指示を追加
        messages.append({"role": "user", "content": task})
        turn += 1
        try:
            text, reasoning, usage, ftok, dur = stream_chat(
                args.endpoint, args.model, messages, args.max_tokens, args.read_timeout)
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError, http.client.IncompleteRead,
                socket.timeout) as e:
            # ストール検出 → BMC/参照込みで原因分類
            status, detail = classify_outage(args.server, args.endpoint)
            ctx_est = sum(len(m["content"]) for m in messages)//4
            rec({"event": "stall", "turn": turn, "error": type(e).__name__,
                 "outage_status": status, "detail": detail, "ctx_tokens_est": ctx_est})
            if status == "HOST_HANG":
                hi = {"trial": args.trial_no, "turn": turn, "backend": args.backend,
                      "epoch": now(), "elapsed_trial_s": now()-trial_start,
                      "error": type(e).__name__, "detail": detail, "last_task": task,
                      "ctx_tokens_est": ctx_est}
                with open(args.hang_json, "w") as hf:
                    json.dump(hi, hf, ensure_ascii=False, indent=2)
                rec({"event": "HANG_CONFIRMED", "turn": turn, "detail": detail})
                jf.close()
                sys.exit(42)
            elif status == "NETWORK":
                # ネットワーク障害（ホストは生存の可能性大）→ リセット不要。
                # オーケストレータに待機させるため専用コードで抜ける。
                rec({"event": "NETWORK_OUTAGE", "turn": turn, "detail": detail})
                jf.close()
                sys.exit(43)
            else:
                # 一過性/サーバ不調だがホストは生存 → 試行打ち切り
                rec({"event": "server_error_transient", "turn": turn, "detail": detail})
                jf.close()
                sys.exit(0)
        except Exception as e:
            rec({"event": "unexpected_error", "turn": turn, "error": repr(e)})
            time.sleep(3)
            continue

        pt = (usage or {}).get("prompt_tokens")
        ct = (usage or {}).get("completion_tokens")
        pp_ts = (pt / ftok) if (pt and ftok) else None
        eval_ts = (ct / (dur - ftok)) if (ct and ftok and dur > ftok) else None
        rec({"event": "turn", "turn": turn, "task_idx": (turn-1) % len(TASKS),
             "first_token_s": round(ftok, 2) if ftok else None,
             "dur_s": round(dur, 2), "prompt_tokens": pt, "completion_tokens": ct,
             "pp_tps": round(pp_ts, 1) if pp_ts else None,
             "eval_tps": round(eval_ts, 1) if eval_ts else None,
             "resp_chars": len(text), "reasoning_chars": len(reasoning)})
        # assistant 応答を会話に積む（context 成長）。thinking モードで content が空なら
        # reasoning を代用して context を伸ばす。1ターンあたり最大 ~6000 字に丸めて turn を回す。
        grow = text if text.strip() else reasoning
        if len(grow) > 6000:
            grow = grow[:6000]
        messages.append({"role": "assistant", "content": grow if grow.strip() else "(no content)"})

    rec({"event": "trial_done", "turns": turn, "elapsed_s": round(now()-trial_start, 1)})
    jf.close()
    sys.exit(0)

if __name__ == "__main__":
    main()
