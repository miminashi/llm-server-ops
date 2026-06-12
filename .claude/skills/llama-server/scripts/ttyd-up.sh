#!/bin/bash
set -euo pipefail

# ttyd 起動統合スクリプト（単一の真実源）
#
# GPU 監視 (port 7681) とログ閲覧 (port 7682) の ttyd を冪等に
# kill→再起動し、両ポートの LISTEN を検証する。start.sh / llama-up.sh /
# ttyd-gpu.sh から呼ばれる。
#
# 使い方:
#   ttyd-up.sh <server>
#
# 引数:
#   server   GPUサーバ名 (mi25, t120h-p100, t120h-m10)
#
# ロックは取得しない（ttyd は監視用途。必要なら呼び出し側で取得）。
# 終了コード: 常に 0。LISTEN 検証に失敗したポートは WARNING を stderr に出す
#             （ttyd は監視用途で本体推論には無関係なため、起動全体は止めない）。

if [ $# -lt 1 ]; then
  echo "Usage: ttyd-up.sh <server>" >&2
  echo "  server: mi25, t120h-p100, t120h-m10" >&2
  exit 1
fi

SERVER="$1"

# --- サーバ名バリデーション ---
case "$SERVER" in
  mi25|t120h-p100|t120h-m10) ;;
  *)
    echo "ERROR: 不明なサーバ: $SERVER" >&2
    exit 1
    ;;
esac

# --- サーバ別 GPU 監視コマンド ---
case "$SERVER" in
  mi25) GPU_CMD="watch -n 1 rocm-smi" ;;
  *)    GPU_CMD="nvtop" ;;
esac

LOG_FILE="/tmp/llama-server.log"

# 指定ポートが LISTEN しているか（最大 ~10 秒リトライ）を確認する
wait_listen() {
  local port="$1"
  for _ in $(seq 1 10); do
    if ssh "$SERVER" "ss -tln | grep -q ':$port '"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

echo "==> ttyd を $SERVER で起動中 (port 7681 GPU監視 / 7682 ログ閲覧)..."

# --- 既存 ttyd を停止（ポート完全一致で個別に kill）---
# パターンは '^ttyd' でアンカーする。アンカーしないと pkill -f が
# このリモートコマンド自身 (bash -c "pkill -f 'ttyd --port 7681' ...")
# のコマンドラインにマッチしてセッションを自殺させ、ssh が 255 を返して
# set -e でスクリプトが中断する（ttyd が一切起動しない）。
ssh "$SERVER" "pkill -f '^ttyd --port 7681' 2>/dev/null; pkill -f '^ttyd --port 7682' 2>/dev/null; pkill nvtop 2>/dev/null; true"

# --- ポート解放待ち（古い ttyd がポートを掴んだままの race を回避）---
for _ in $(seq 1 5); do
  if ! ssh "$SERVER" "ss -tln | grep -qE ':(7681|7682) '"; then
    break
  fi
  sleep 1
done

# --- ログファイル担保（未起動時に tail -f が即終了して 7682 が死ぬのを防ぐ）---
ssh "$SERVER" "touch $LOG_FILE"

# --- 再起動（fd リダイレクトは start.sh パターンを踏襲）---
# 7682: ログ閲覧
ssh -f "$SERVER" "nohup ttyd --port 7682 --writable bash -c 'tail -f $LOG_FILE' > /dev/null 2>&1 < /dev/null &" </dev/null >/dev/null 2>&1
# 7681: GPU 監視（TERM を明示しないと nvtop/watch が 'unknown terminal' で即終了する）
# $GPU_CMD はクオートせず展開（"watch -n 1 rocm-smi" の引数分割を意図的に使う）
ssh -f "$SERVER" "nohup ttyd --port 7681 bash -c 'TERM=xterm-256color exec $GPU_CMD' > /dev/null 2>&1 < /dev/null &" </dev/null >/dev/null 2>&1

# --- LISTEN 検証 ---
IP=$(ssh -G "$SERVER" | grep '^hostname ' | awk '{print $2}')
RC=0
if wait_listen 7681; then
  echo "    [OK] GPU監視  : http://${IP}:7681"
else
  echo "WARNING: ttyd 7681 (GPU監視) が LISTEN しません" >&2
  RC=1
fi
if wait_listen 7682; then
  echo "    [OK] ログ閲覧 : http://${IP}:7682"
else
  echo "WARNING: ttyd 7682 (ログ閲覧) が LISTEN しません" >&2
  RC=1
fi

if [ "$RC" -eq 0 ]; then
  echo "==> ttyd 起動完了（7681/7682 とも LISTEN）"
else
  echo "==> ttyd 起動を試みましたが一部ポートが LISTEN していません（監視UIのみ・本体には影響なし）" >&2
fi

# ttyd は監視用途のため、検証失敗でも起動全体は止めない（常に exit 0）
exit 0
