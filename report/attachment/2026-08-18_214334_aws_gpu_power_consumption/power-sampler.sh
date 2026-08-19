#!/usr/bin/env bash
# aws-gpu01 / aws-gpu02 の消費電力サンプラー（読み取り専用）。
#
# 制御ホスト（ワークステーション）から一定間隔で
#   - BMC の IPMI DCMI (dcmi power reading) → シャーシ全体の瞬時電力 [W]
#   - ssh 越しの nvidia-smi                 → GPU 個別の power.draw / utilization
# を同時に採り、1 行 1 サンプルの CSV に追記する。
#
# 既存の report/attachment/2026-06-27_*/telemetry.sh と同じ「制御ホスト側で ssh 越しに
# 一定間隔サンプリングし、ローカルへ追記する」構造を踏襲している。
#
# 使い方: power-sampler.sh <server> <out_csv> [interval_sec] [duration_sec]
# 停止  : pidfile (<out_csv>.pid) の PID を kill する（pkill -f は自分にマッチするので使わない）
#
# CSV 列:
#   epoch, iso_ts, server, chassis_w, gpu_total_w, gpu_busy_count, gpu_w, gpu_util, status
#     gpu_w / gpu_util : GPU 枚数ぶんを ';' 区切りで並べたもの
#     status           : ok / ipmi_fail / nvsmi_fail / both_fail（欠測の弁別用）
set -u

SERVER="${1:?usage: power-sampler.sh <server> <out_csv> [interval] [duration]}"
OUT="${2:?}"
INTERVAL="${3:-10}"
DURATION="${4:-1800}"

ENV_FILE="${GPU_SERVER_ENV:-${XDG_CONFIG_HOME:-$HOME/.config}/gpu-server/.env}"
VAR_PREFIX="BMC_$(echo "$SERVER" | tr '[:lower:]-' '[:upper:]_')"
BMC_HOST=$(grep "^${VAR_PREFIX}_HOST=" "$ENV_FILE" | cut -d= -f2-)
BMC_USER=$(grep "^${VAR_PREFIX}_USER=" "$ENV_FILE" | cut -d= -f2-)
BMC_PASS=$(grep "^${VAR_PREFIX}_PASS=" "$ENV_FILE" | cut -d= -f2-)
if [[ -z "$BMC_HOST" || -z "$BMC_USER" || -z "$BMC_PASS" ]]; then
    echo "エラー: ${SERVER} の BMC 認証情報が ${ENV_FILE} にありません" >&2
    exit 10
fi

echo "$$" > "${OUT}.pid"
if [[ ! -s "$OUT" ]]; then
    echo "epoch,iso_ts,server,chassis_w,gpu_total_w,gpu_busy_count,gpu_w,gpu_util,status" > "$OUT"
fi

END=$(( $(date +%s) + DURATION ))

while [[ $(date +%s) -lt $END ]]; do
    EPOCH=$(date +%s)
    ISO=$(TZ=Asia/Tokyo date -d "@$EPOCH" +%Y-%m-%dT%H:%M:%S)

    CHASSIS=$(timeout 25 ipmitool -I lanplus -H "$BMC_HOST" -U "$BMC_USER" -P "$BMC_PASS" \
        dcmi power reading 2>/dev/null | sed -n 's/^[[:space:]]*Instantaneous power reading:[[:space:]]*\([0-9]*\).*/\1/p')

    NV=$(timeout 20 ssh -o ConnectTimeout=8 -o BatchMode=yes "$SERVER" \
        "nvidia-smi --query-gpu=power.draw,utilization.gpu --format=csv,noheader,nounits" 2>/dev/null)

    STATUS="ok"
    [[ -z "$CHASSIS" ]] && STATUS="ipmi_fail"
    if [[ -z "$NV" ]]; then
        [[ "$STATUS" == "ipmi_fail" ]] && STATUS="both_fail" || STATUS="nvsmi_fail"
    fi

    GPU_W="" GPU_UTIL="" TOTAL="" BUSY=""
    if [[ -n "$NV" ]]; then
        GPU_W=$(echo "$NV" | awk -F', *' '{printf "%s%s", (NR>1?";":""), $1}')
        GPU_UTIL=$(echo "$NV" | awk -F', *' '{printf "%s%s", (NR>1?";":""), $2}')
        TOTAL=$(echo "$NV" | awk -F', *' '{s+=$1} END {printf "%.2f", s}')
        BUSY=$(echo "$NV" | awk -F', *' '$2>0 {c++} END {printf "%d", c+0}')
    fi

    echo "${EPOCH},${ISO},${SERVER},${CHASSIS},${TOTAL},${BUSY},${GPU_W},${GPU_UTIL},${STATUS}" >> "$OUT"

    # 採取に要した時間を差し引いて間隔を守る
    ELAPSED=$(( $(date +%s) - EPOCH ))
    SLEEP=$(( INTERVAL - ELAPSED ))
    [[ $SLEEP -gt 0 ]] && sleep "$SLEEP"
done

rm -f "${OUT}.pid"
