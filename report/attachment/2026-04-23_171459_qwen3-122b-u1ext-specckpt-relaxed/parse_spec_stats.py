#!/usr/bin/env python3
"""parse_spec_stats.py - サーバログから spec stats を抽出

ログ形式例:
  statistics ngram_mod: #calls(b,g,a) = 5 887 7, #gen drafts = 7, #acc drafts = 7,
                        #gen tokens = 448, #acc tokens = 148, dur(b,g,a) = 0.88, 2.66, 4.75 ms
  draft acceptance rate = 1.00000 (X accepted / Y generated)  ← per-request
  slot create_check: ... created context checkpoint N of M ...
  out of memory / CUDA error: out of memory

出力: spec_stats.tsv
  TAG_COND, n_gen_drafts_final, n_acc_drafts_final, n_gen_tokens_final,
  n_acc_tokens_final, accept_rate_tokens, ckpt_created_total, oom_detected, reset_count
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
STARTUP_DIR = SCRIPT_DIR / "startup_logs"

# ngram_mod の累積 stats 行 (毎回 request 後に 1 行)
RE_NGRAM = re.compile(
    r"statistics ngram_mod.*?#gen\s+drafts\s*=\s*(\d+).*?#acc\s+drafts\s*=\s*(\d+)"
    r".*?#gen\s+tokens\s*=\s*(\d+).*?#acc\s+tokens\s*=\s*(\d+)",
    re.IGNORECASE,
)
RE_CKPT = re.compile(r"created context checkpoint \d+ of \d+")
RE_OOM = re.compile(r"out of memory|CUDA error: out of memory|cuMemCreate", re.IGNORECASE)
RE_RESET = re.compile(r"low acceptance streak.*resetting ngram_mod", re.IGNORECASE)
RE_ACC_RATE = re.compile(r"draft acceptance rate\s*=\s*([0-9.]+)\s*\(\s*(\d+)\s+accepted\s*/\s*(\d+)\s+generated\s*\)")


def parse_server_log(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(errors="replace")
    ngram_matches = RE_NGRAM.findall(text)
    # 最後 (cumulative) のエントリを採用
    if ngram_matches:
        last = ngram_matches[-1]
        n_gen_drafts, n_acc_drafts, n_gen_tokens, n_acc_tokens = (int(x) for x in last)
    else:
        n_gen_drafts = n_acc_drafts = n_gen_tokens = n_acc_tokens = None
    ckpt_n = len(RE_CKPT.findall(text))
    oom = bool(RE_OOM.search(text))
    reset_n = len(RE_RESET.findall(text))

    # 各 request ごとの acceptance rate / accepted / generated
    per_req = RE_ACC_RATE.findall(text)
    rates = [float(r) for r, _, _ in per_req]
    accs = [int(a) for _, a, _ in per_req]
    gens = [int(g) for _, _, g in per_req]

    return dict(
        n_gen_drafts_final=n_gen_drafts,
        n_acc_drafts_final=n_acc_drafts,
        n_gen_tokens_final=n_gen_tokens,
        n_acc_tokens_final=n_acc_tokens,
        accept_rate_tokens=(n_acc_tokens / n_gen_tokens) if (n_gen_tokens and n_gen_tokens > 0) else None,
        ckpt_created=ckpt_n,
        oom_detected=oom,
        reset_count=reset_n,
        per_req_n=len(per_req),
        per_req_rates_mean=(sum(rates) / len(rates)) if rates else None,
        per_req_total_accepted=sum(accs) if accs else None,
        per_req_total_generated=sum(gens) if gens else None,
    )


def main() -> int:
    rows = []
    if not STARTUP_DIR.exists():
        print(f"ERROR: {STARTUP_DIR} not found", file=sys.stderr)
        return 1
    for log in sorted(STARTUP_DIR.glob("*.log")):
        if log.name.endswith("_preeval.log"):
            continue
        tag = log.stem
        rows.append(dict(tag=tag, **parse_server_log(log)))

    headers = ["tag", "n_gen_drafts_final", "n_acc_drafts_final",
               "n_gen_tokens_final", "n_acc_tokens_final", "accept_rate_tokens",
               "ckpt_created", "oom_detected", "reset_count",
               "per_req_n", "per_req_rates_mean",
               "per_req_total_accepted", "per_req_total_generated"]
    out = SCRIPT_DIR / "spec_stats.tsv"
    with out.open("w") as f:
        f.write("\t".join(headers) + "\n")
        for r in rows:
            vals = []
            for h in headers:
                v = r.get(h)
                if v is None:
                    vals.append("")
                elif isinstance(v, float):
                    vals.append(f"{v:.4f}")
                elif isinstance(v, bool):
                    vals.append("1" if v else "0")
                else:
                    vals.append(str(v))
            f.write("\t".join(vals) + "\n")
    print(f"wrote {out} ({len(rows)} rows)")

    # readable table
    print()
    print(f"{'tag':<72} {'gd':>5} {'ad':>5} {'gt':>6} {'at':>6} {'rate':>6} {'ckpt':>5} {'rst':>4} {'oom':>4}")
    for r in rows:
        tag = r["tag"][:72]
        gd = r.get("n_gen_drafts_final") or 0
        ad = r.get("n_acc_drafts_final") or 0
        gt = r.get("n_gen_tokens_final") or 0
        at = r.get("n_acc_tokens_final") or 0
        ar = r.get("accept_rate_tokens")
        ar_s = f"{ar:.3f}" if ar is not None else "-"
        ck = r.get("ckpt_created") or 0
        rst = r.get("reset_count") or 0
        oom = "YES" if r.get("oom_detected") else "-"
        print(f"{tag:<72} {gd:>5} {ad:>5} {gt:>6} {at:>6} {ar_s:>6} {ck:>5} {rst:>4} {oom:>4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
