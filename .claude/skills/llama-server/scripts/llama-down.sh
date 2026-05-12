#!/bin/bash
# llama-server 停止統合スクリプト
#
# ロック検証 → stop.sh → power.sh off → unlock.sh を 1 コマンドで実行する薄いラッパー。
#
# 使い方:
#   llama-down.sh [server] [--force]
#
# 引数:
#   server    GPUサーバ名 (デフォルト: t120h-p100)
#   --force   他者ロック保持時でも停止を強行する（unlock は実行しない）
#
# ロック検証ルール（SKILL.md の「他者使用中の llama-server を勝手に停止しない」原則の機械的強制）:
#   - 自分保持: hostname 部分が一致 → 継続、最後に unlock
#   - 他者保持: --force なしなら exit 1、ありなら警告のみで継続（他者ロックは触らない）
#   - 未ロック (available): 警告して継続、unlock スキップ
#   - UNREACHABLE: exit 1
#
# session_id 形式は lock.sh の自動生成と同じ "<hostname>-<pid>-<YYYYMMDD_HHMMSS>" を想定。
# hostname は "-" を含む可能性があるため、末尾 2 セグメント (-pid-timestamp) を剥がす方式で
# hostname 部分を抽出する。
#
# 終了コード: 0=成功 / 1=エラー（他者ロックで中断含む）。
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
GPU_SCRIPTS_DIR="$(cd "$SKILL_DIR/../gpu-server/scripts" && pwd)"

SERVER="${1:-t120h-p100}"
FORCE=false
if [ "${2:-}" = "--force" ]; then
  FORCE=true
fi

# --- Step 1: ロック検証 ---
echo "==> [1/4] $SERVER のロック状態を確認中..."
LOCK_OUT=$("$GPU_SCRIPTS_DIR/lock-status.sh" "$SERVER")
echo "$LOCK_OUT"

OWN_LOCK=""
case "$LOCK_OUT" in
  *"UNREACHABLE"*)
    echo "ERROR: $SERVER に到達できません" >&2
    exit 1
    ;;
  *": available"*)
    echo "    ロックなしで停止します（注意: 排他制御なし）"
    ;;
  *": LOCKED"*)
    HOLDER=$(echo "$LOCK_OUT" | awk '/Holder:/ {print $2}')
    if [ -z "$HOLDER" ]; then
      echo "ERROR: Holder 行を抽出できませんでした" >&2
      exit 1
    fi
    # session_id = "<hostname>-<pid>-<timestamp>" の末尾 2 セグメントを剥がす
    STRIPPED="${HOLDER%-*}"          # 末尾の -timestamp を除去
    HOLDER_HOST="${STRIPPED%-*}"     # 末尾の -pid を除去 → hostname 部分
    MY_HOST="$(hostname)"
    if [ "$HOLDER_HOST" = "$MY_HOST" ]; then
      echo "    自分のロック (holder=$HOLDER) → 停止後に解放します"
      OWN_LOCK="$HOLDER"
    else
      if [ "$FORCE" = true ]; then
        echo "WARNING: 他者ロック ($HOLDER) を無視して停止します (--force)" >&2
      else
        echo "ERROR: 他者ロック ($HOLDER) のため停止を中止します。" >&2
        echo "  強制停止する場合は --force を指定してください。" >&2
        exit 1
      fi
    fi
    ;;
  *)
    echo "WARNING: lock-status.sh の出力を判定できませんでした。停止を続行します。" >&2
    ;;
esac

# --- Step 2: llama-server 停止 ---
echo "==> [2/4] llama-server を停止中..."
if ! "$SCRIPT_DIR/stop.sh" "$SERVER"; then
  echo "WARNING: stop.sh が失敗しましたが、続行します" >&2
fi

# --- Step 3: 自分保持ロックの解放（power off 前に実行: power off 後は OS シャットダウン進行中で SSH 切断のため）---
if [ -n "$OWN_LOCK" ]; then
  echo "==> [3/4] ロックを解放します..."
  "$GPU_SCRIPTS_DIR/unlock.sh" "$SERVER" "$OWN_LOCK"
else
  echo "==> [3/4] ロック解放スキップ（未保持または --force のため）"
fi

# --- Step 4: 電源 OFF ---
echo "==> [4/4] $SERVER の電源を OFF にします..."
if ! "$GPU_SCRIPTS_DIR/power.sh" "$SERVER" off; then
  echo "WARNING: power.sh off に失敗しました（API エラー等）。" >&2
fi

echo "==> 停止完了"
