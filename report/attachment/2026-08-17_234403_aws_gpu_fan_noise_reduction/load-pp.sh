#!/usr/bin/env bash
# prompt processing 主体の負荷（compute-bound）。長大プロンプトを毎回異なる冒頭で投げ、
# llama-server のプレフィックスキャッシュを外して pp を連続で回す。
#   使い方: load-pp.sh <duration_sec> [parallel] [prompt_chars]
set -uo pipefail
DUR="${1:-900}"; PAR="${2:-2}"; CHARS="${3:-60000}"

python3 - "$CHARS" <<'PY' > /tmp/pp_body.txt
import sys
n = int(sys.argv[1])
unit = ("大規模言語モデルの推論最適化について、KVキャッシュの配置、量子化の影響、"
        "テンソル並列とパイプライン並列の使い分け、RDMA を用いた RPC 転送の帯域特性、"
        "MoE ルーティングの負荷分散、投機的デコードの受理率をそれぞれ検討する。")
sys.stdout.write((unit * (n // len(unit) + 1))[:n])
PY

worker() {
    local id="$1" end=$((SECONDS + DUR)) n=0
    while (( SECONDS < end )); do
        python3 - "$id" "$n" <<'PY' > "/tmp/pp_req_$id.json"
import json, sys
head = f"[req {sys.argv[1]}-{sys.argv[2]} {'x' * (int(sys.argv[2]) % 97 + 1)}] "
body = open('/tmp/pp_body.txt').read()
print(json.dumps({"messages": [{"role": "user", "content": head + body + "\n\n上記を3行で要約してください。"}],
                  "max_tokens": 32, "temperature": 1.0, "cache_prompt": False}))
PY
        curl -s --max-time 900 -X POST http://10.8.2.1:8000/v1/chat/completions \
            -H 'Content-Type: application/json' -d "@/tmp/pp_req_$id.json" > /dev/null
        n=$((n+1))
    done
    echo "worker $id: $n pp requests"
}

echo "pp 負荷開始: ${DUR}s, 並列 ${PAR}, プロンプト ${CHARS} 文字"
for i in $(seq 1 "$PAR"); do worker "$i" & done
wait
echo "pp 負荷終了"
