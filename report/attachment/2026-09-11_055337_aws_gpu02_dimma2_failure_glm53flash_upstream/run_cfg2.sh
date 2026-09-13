#!/usr/bin/env bash
# llama-server を指定構成で再起動し、起動可否を判定してログを退避する。
# run_cfg.sh (2026-09-05/06 セッション) からの派生。差分は EXTRA_ENV のみ:
#   環境変数 EXTRA_ENV に "KEY=VAL KEY2=VAL2" を入れると env に追加で渡す。
#   smalinin フォークの A/B スイッチ (LLAMA_GLM5_POOL_CACHE=0 等) を再ビルドなしで切り替えるため。
# usage: [EXTRA_ENV="K=V ..."] run_cfg2.sh <tag> <model.gguf> <ctx> <ub> [extra args...]
set -u
TAG="$1"; MODEL="$2"; CTX="$3"; UB="$4"; shift 4
EXTRA_ENV="${EXTRA_ENV:-}"
cd ~/llama.cpp
pkill -f 'build/bin/llama-serv' 2>/dev/null
for i in $(seq 1 60); do pgrep -f 'build/bin/llama-serv' >/dev/null || break; sleep 2; done
sleep 3
echo "ENV: NVIDIA_TF32_OVERRIDE=0 ${EXTRA_ENV}"
setsid nohup env NVIDIA_TF32_OVERRIDE=0 ${EXTRA_ENV} ./build/bin/llama-server \
  --model "$MODEL" --alias 'GLM-5.3-Flash-UD-IQ4_XS' --rpc 192.168.100.2:50052 \
  --n-gpu-layers 999 --ctx-size "$CTX" \
  -fa on --poll 0 -b 512 -ub "$UB" \
  --jinja --temp 1.0 --top-p 0.95 --host 0.0.0.0 --port 8000 "$@" \
  > /tmp/llama-server.log 2>&1 < /dev/null &
# 起動判定。graph_reserve の失敗は警告なので致命扱いしない (2026-08-29 レポートの副次発見)
for i in $(seq 1 180); do
  if grep -q 'listening on' /tmp/llama-server.log; then echo "RESULT $TAG OK"; break; fi
  if grep -qiE 'exiting due to model loading error|terminate called|CUDA error' /tmp/llama-server.log; then
    echo "RESULT $TAG FAIL"; break; fi
  sleep 10
done
grep -qE 'listening on|exiting due to' /tmp/llama-server.log || echo "RESULT $TAG TIMEOUT"
grep -iE 'failed to allocate|graph_reserve|exiting due to|listening on' /tmp/llama-server.log | tail -6
cp /tmp/llama-server.log "/tmp/log_${TAG}.log"
