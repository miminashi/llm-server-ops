#!/usr/bin/env bash
# probe_vram.sh - nvidia-smi (2 回) + warm probe /completions の dry-probe
#
# Env 変数:
#   HOST          t120h-p100 (既定)
#   HOST_URL      http://10.1.4.14:8000
#   TAG_COND      出力ファイル prefix
#   SAVE_DIR      startup_logs 配下の保存先
#
# stdout: VRAM 値 + probe 結果を key=value で出力
#   例: STATIC_FREE="3948,1804,6000,2972"
#       AFTER_FREE="3800,1700,5900,2870"
#       PROBE_STATUS=OK  (or  OOM_PROBE)
set -euo pipefail

HOST="${HOST:-t120h-p100}"
HOST_URL="${HOST_URL:-http://10.1.4.14:8000}"
TAG_COND="${TAG_COND:?TAG_COND required}"
SAVE_DIR="${SAVE_DIR:?SAVE_DIR required}"

mkdir -p "$SAVE_DIR"

# --- 1 回目 nvidia-smi (static allocation 後) ---
sleep 10  # KV prealloc / compute buffer reserve 完了待機
SMI_STATIC=$(ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
  "nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv,noheader,nounits" 2>&1 || echo "SSH_FAIL")
echo "$SMI_STATIC" > "${SAVE_DIR}/${TAG_COND}_nvidia_smi_static.csv"

STATIC_FREE=$(echo "$SMI_STATIC" | awk -F', *' 'NF==3 {printf "%s%s", sep, $3; sep=","}')
echo "STATIC_FREE=\"${STATIC_FREE}\""

# --- warm probe (max_tokens=5) ---
PROBE_BODY='{"prompt":"Hello","max_tokens":5,"temperature":0.0}'
PROBE_OUT=$(curl -sS -m 30 -H 'Content-Type: application/json' \
  -d "$PROBE_BODY" "${HOST_URL}/v1/completions" 2>&1 || echo "CURL_FAIL")
echo "$PROBE_OUT" > "${SAVE_DIR}/${TAG_COND}_probe_response.json"

if echo "$PROBE_OUT" | grep -qE '"choices"|"text"'; then
  PROBE_STATUS="OK"
elif echo "$PROBE_OUT" | grep -qE 'out of memory|CUDA error|cudaMalloc'; then
  PROBE_STATUS="OOM_PROBE"
elif [ "$PROBE_OUT" = "CURL_FAIL" ]; then
  PROBE_STATUS="PROBE_FAIL"
else
  PROBE_STATUS="PROBE_UNKNOWN"
fi
echo "PROBE_STATUS=${PROBE_STATUS}"

# --- 2 回目 nvidia-smi (warm probe 後) ---
sleep 2
SMI_AFTER=$(ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
  "nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv,noheader,nounits" 2>&1 || echo "SSH_FAIL")
echo "$SMI_AFTER" > "${SAVE_DIR}/${TAG_COND}_nvidia_smi_after.csv"

AFTER_FREE=$(echo "$SMI_AFTER" | awk -F', *' 'NF==3 {printf "%s%s", sep, $3; sep=","}')
echo "AFTER_FREE=\"${AFTER_FREE}\""
