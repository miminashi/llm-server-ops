#!/usr/bin/env bash
# aws-gpu01 + aws-gpu02 の RPC 分散構成を 1 コマンドで立ち上げる。
#
# これが aws-gpu01 / aws-gpu02 の**デフォルト構成**（2026-08-18 制定）。
# 2 台の VRAM を合算して 13 GPU / 200 GiB を 1 プロセスから使う。
# API エンドポイントは aws-gpu01 側の http://10.8.2.1:8000/v1 のみ
# （aws-gpu02 は RPC ワーカーなので 8000 番では待ち受けない）。
#
# 電源確認 → ヘルスチェック（既起動なら冪等スキップ）→ rpc-up.sh
#   → rpc-llama-up.sh → ttyd-up.sh → Discord 通知
#
# 使い方:
#   rpc-stack-up.sh [model-path] [ctx-size]
#
# 引数（すべて省略可）:
#   model-path  メインホスト上のモデルパス（省略時: rpc-llama-up.sh のデフォルト構成モデル）
#   ctx-size    コンテキストサイズ（省略時: 131072）
#
# 環境変数:
#   MAIN / WORKER      メインホスト / RPC ワーカー（既定 aws-gpu01 / aws-gpu02）
#   ALIAS / SAMPLING_OPTS / EXTRA_LLAMA_OPTS / WAIT_SECS   rpc-llama-up.sh にそのまま渡る
#   ALLOW_FAN_NOISE=1  電源 Off のときに電源投入を許可する（既定は拒否）
#
# ロックは取得しない（必要なら事前に gpu-server/scripts/lock.sh を両機に対して実行）。
# 終了コード: 0=成功 / 1=エラー。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
GPU_SCRIPTS_DIR="$(cd "$SKILL_DIR/../gpu-server/scripts" && pwd)"
NOTIFY_SCRIPT="$(cd "$SKILL_DIR/../discord-notify/scripts" && pwd)/notify.sh"

MODEL="${1:-}"
CTX="${2:-131072}"
MAIN="${MAIN:-aws-gpu01}"
WORKER="${WORKER:-aws-gpu02}"

# --- Step 1: 両機の電源確認 ---
# 電源投入は既定で拒否する。aws-gpu01/02 は起動 (POST) 中にファンが爆音になるため、
# ユーザの明確な指示なしに電源を入れない運用になっている（CLAUDE.md の制約）。
echo "==> [1/5] $MAIN / $WORKER の電源状態を確認中..."
for S in "$MAIN" "$WORKER"; do
  STATE=$("$GPU_SCRIPTS_DIR/power-ctl.sh" "$S" status)
  if [ "$STATE" = "On" ]; then
    echo "    $S: On"
    continue
  fi
  if [ "$STATE" != "Off" ]; then
    echo "ERROR: $S の電源状態を判定できませんでした ($STATE)" >&2
    exit 1
  fi
  if [ "${ALLOW_FAN_NOISE:-}" != "1" ]; then
    echo "ERROR: $S の電源が Off です。起動時にファンが爆音になるため、" >&2
    echo "       ユーザの明確な指示なしに電源投入はしません。" >&2
    echo "       指示を得た場合のみ ALLOW_FAN_NOISE=1 を付けて再実行してください。" >&2
    exit 1
  fi
  echo "    $S: Off → 電源を ON にします (ALLOW_FAN_NOISE=1)"
  "$GPU_SCRIPTS_DIR/power-ctl.sh" "$S" on
  echo "    SSH 疎通を待機中（最大 5 分）..."
  SSH_READY=false
  for i in $(seq 1 60); do
    if ssh -o ConnectTimeout=5 -o BatchMode=yes "$S" true 2>/dev/null; then
      SSH_READY=true
      break
    fi
    sleep 5
  done
  if [ "$SSH_READY" != true ]; then
    echo "ERROR: $S への SSH 疎通がタイムアウトしました（5 分）" >&2
    exit 1
  fi
done

IP=$(ssh -G "$MAIN" | awk '/^hostname /{print $2}')
if [ -z "$IP" ]; then
  echo "ERROR: $MAIN の IP を ssh -G で解決できませんでした" >&2
  exit 1
fi

# --- Step 2: ヘルスチェック（既起動なら冪等スキップ）---
echo "==> [2/5] llama-server の起動状態を確認中..."
if curl -sf -m 5 "http://${IP}:8000/health" >/dev/null 2>&1; then
  echo "    既に起動しています (http://${IP}:8000/health → 200)"
  "$SCRIPT_DIR/ttyd-up.sh" "$MAIN"
  TTYD_LOG_FILE=/tmp/rpc-server.log "$SCRIPT_DIR/ttyd-up.sh" "$WORKER"
  echo "==> 完了（冪等スキップ）"
  exit 0
fi
echo "    /health 応答なし。起動を開始します。"

# --- Step 3: RPC ワーカー ---
# パターンを [b]in/... と書くのは ssh 越しの自己マッチ回避のため（SKILL.md 参照）。
echo "==> [3/5] RPC ワーカー ($WORKER) を確認中..."
if ssh -n "$WORKER" "pgrep -f '[b]in/(ggml-)?rpc-server' > /dev/null"; then
  echo "    既に稼働中。起動をスキップします。"
else
  "$SCRIPT_DIR/rpc-up.sh" "$WORKER"
fi

# --- Step 4: llama-server ---
echo "==> [4/5] llama-server を起動中（cold ロードは 15 分程度かかる）..."
# NOTE: $MODEL は必ずクォートすること。MODEL 未指定（デフォルト構成）のとき素の $MODEL は
#       空展開で消え、"$CTX" が第 1 引数 = model-path に繰り上がる（2026-08-18 実測で
#       「failed to load model from 131072」）。引数ごと省く ${MODEL:+...} も同じ結果になる。
#       rpc-llama-up.sh は MODEL="${1:-$DEFAULT_MODEL}" なので、空文字を渡せばデフォルト
#       構成のモデルに落ちる。
SERVER="$MAIN" "$SCRIPT_DIR/rpc-llama-up.sh" "$MODEL" "$CTX"

# --- Step 5: 監視 UI + 通知 ---
# 13 GPU のうち 6 枚はワーカー側にあるので、監視 UI は両機に立てる。
# ワーカーには llama-server のログが無いので、7682 は rpc-server のログを見せる。
echo "==> [5/5] 監視 UI を起動中..."
"$SCRIPT_DIR/ttyd-up.sh" "$MAIN"
TTYD_LOG_FILE=/tmp/rpc-server.log "$SCRIPT_DIR/ttyd-up.sh" "$WORKER"

if [ -x "$NOTIFY_SCRIPT" ]; then
  MODEL_DISP="${MODEL:-（デフォルト構成モデル）}"
  NOTIFY_MSG="llama-server 起動完了 (RPC 分散)
- 構成: ${MAIN} (メイン) + ${WORKER} (RPC ワーカー) / 13 GPU / 200 GiB
- モデル: ${MODEL_DISP}
- ctx-size: ${CTX}
- エンドポイント: http://${IP}:8000/v1
- GPU監視: http://${IP}:7681 (メイン) / http://$(ssh -G "$WORKER" | awk '/^hostname /{print $2}'):7681 (ワーカー)
- サーバログ: http://${IP}:7682"
  ("$NOTIFY_SCRIPT" "$NOTIFY_MSG" || echo "WARNING: Discord通知の送信に失敗しました" >&2) || true
fi

echo "==> 起動完了: http://${IP}:8000/v1"
