# 統合スクリプト追加: llama-up.sh / llama-down.sh（設計修正フェーズ）

## Context

opencode フォーク（別 Claude セッション）側の README.md に「LLM サーバ起動」セクションを追加する際、現状の起動手順が `power.sh status → power.sh on → ttyd-gpu.sh → start.sh → wait-ready.sh` の 5 ステップ必要で冗長すぎる、という指摘があった。

そこで「電源 OFF 判断 → GPU サーバ起動 → llama-server 起動」を **1 コマンド** で実行できる薄いラッパースクリプトを `llama-server` スキルに追加する。停止側も対称的に `lock-status.sh → stop.sh → power.sh off → unlock.sh` を 1 コマンドに統合する。

これにより opencode 側 README は 1 行コマンド `llama-up.sh` / `llama-down.sh` で済むようになる。

**現在のフェーズ**: スクリプト実装・SKILL.md 更新・実機検証 V1〜V5 は完了済み。

実機検証 V3（自分ロック停止）で発覚した問題:
> `llama-down.sh` の現状フロー `Step 3: power.sh off → Step 4: unlock.sh` の順序では、power off コマンド送信直後に OS がシャットダウン進行中になり、Step 4 の `unlock.sh` の SSH 接続が失敗する（`llama-down.sh EC=3`）。GPU サーバの `/tmp` が tmpfs なら次回起動時にロックは消えるが、設計の本来の意図とは異なる。

本フェーズでは `llama-down.sh` の Step 順序を修正し、実機検証で V3 PASS（caveat なし）を確認する。修正範囲は本プロジェクト承認時の「既存スクリプト未変更」原則（受け入れ基準 5）を維持: 修正対象は前タスクで追加した `llama-down.sh` と `SKILL.md` のみ。

**設計方針**:
- 既存スクリプト（`power.sh` / `start.sh` / `stop.sh` / `wait-ready.sh` / `lock.sh` / `unlock.sh` / `lock-status.sh`）の中身・引数仕様は **一切変更しない**
- 薄いラッパーに留め、責務は既存スクリプトが担う
- 終了コードは 0=成功 / 1=エラー で統一、進捗は `==> ...` で日本語表示

## 追加・変更ファイル

| ファイル | 種別 | 説明 |
|----------|------|------|
| `.claude/skills/llama-server/scripts/llama-up.sh` | 新規 | 起動統合スクリプト |
| `.claude/skills/llama-server/scripts/llama-down.sh` | 新規 | 停止統合スクリプト |
| `.claude/skills/llama-server/SKILL.md` | 更新 | 「統合スクリプト（推奨）」セクションを既存「start.sh + ttyd-gpu.sh + wait-ready.sh の使い方」セクションの **直前** に追加（先頭推奨配置） |
| `reports/YYYY-MM-DD_llama-up-down.md` | 新規 | [REPORT.md](../../projects/llm-server-ops/REPORT.md) フォーマットに従う簡易レポート（実装内容＋動作確認結果） |

既存スクリプトの差分は **空** であること（受け入れ基準 5）。

---

## llama-up.sh 仕様

**パス**: `.claude/skills/llama-server/scripts/llama-up.sh`

**引数**: `[server] [hf-model] [mode] [fit-ctx]`（全省略可）

**デフォルト値**:
- `server` = `t120h-p100`
- `hf-model` = `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- `mode` = `fit`
- `fit-ctx` = 空（start.sh / wait-ready.sh のプロファイル既定に委譲）

**フロー**:

```
[1/4] power.sh <server> status で電源確認
        ↓ "電源状態 = <On|Off>" をパース（grep -oE 'On|Off' | tail -1）
[2/4] Off の場合: power.sh <server> on → SSH 疎通待ち
        ↓ ssh -o ConnectTimeout=5 -o BatchMode=yes <server> true
        ↓ 5 秒間隔 × 60 回 = 最大 5 分。タイムアウトで exit 1
[3/4] IP 解決: ssh -G <server> | grep '^hostname ' | awk '{print $2}'
        ↓ curl -sf -m 5 http://<ip>:8000/health で既起動チェック
        ↓ 200 応答なら "既に起動しています" メッセージで exit 0（冪等）
[4/4] start.sh <server> <hf-model> <mode> [fit-ctx]
        ↓ wait-ready.sh <server> <hf-model> <mode> [fit-ctx]
        ↓ exit 0
```

**重要な実装ポイント**:
- IP 解決は既存 `wait-ready.sh:66` と同じ `ssh -G` パターンを採用（サーバ→IP のハードコードは避ける）
- `FIT_CTX` 空文字を渡さないため、`"$SCRIPT_DIR/start.sh" "$SERVER" "$HF_MODEL" "$MODE" $FIT_CTX`（quote なし）で完全省略
- `curl -sf` は HTTP エラーで非 0 を返すので「200 のみ既起動」と判定可能
- ロック取得はしない（呼び出し側の責務）

---

## llama-down.sh 仕様

**パス**: `.claude/skills/llama-server/scripts/llama-down.sh`

**引数**: `[server] [--force]`

**デフォルト値**: `server` = `t120h-p100`

**フロー**:

```
[1/4] lock-status.sh <server> の出力をパース
        ├ "UNREACHABLE"     → exit 1
        ├ ": available"     → 警告して継続、OWN_LOCK=""
        └ ": LOCKED"        → Holder 行から session_id 抽出
              hostname 抽出: STRIPPED="${HOLDER%-*}"; HOLDER_HOST="${STRIPPED%-*}"
              （注: hostname に "-" を含むため ${var%%-*} は使えない。
                session_id = "<hostname>-<pid>-<timestamp>" の末尾 2 トークンを剥がす）
              ├ HOLDER_HOST = $(hostname) → 自分のロック扱い OWN_LOCK=<session_id>
              └ 他者のロック:
                    --force あり → 警告のみで継続、OWN_LOCK=""（他者ロックは触らない）
                    --force なし → exit 1
[2/4] stop.sh <server>
        ↓ 失敗時も警告のみで継続（電源 OFF すれば結果的に止まる）
[3/4] power.sh <server> off
        ↓ 失敗時も警告のみで unlock 段階へ
[4/4] OWN_LOCK が非空のみ unlock.sh <server> "$OWN_LOCK"
        exit 0
```

**hostname 抽出の根拠**:
- 実行ホスト `aws-mmns-generic` は `-` を含むので `${HOLDER%%-*}` だと先頭の `aws` だけになり誤判定する
- `lock.sh:34` の自動生成形式 `$(hostname)-$$-$(date +%Y%m%d_%H%M%S)` は **末尾 2 セグメントが固定**（`-<pid>-<timestamp>`）
- なので `%-*` を 2 段適用すれば hostname 部分だけ残せる

**--force の扱い**:
- 「他者ロックを無視して停止」のみ。unlock は実行しない（他者のロックを勝手に解放してはいけない）

---

## SKILL.md 追記内容

`.claude/skills/llama-server/SKILL.md` の **85 行目「## start.sh + ttyd-gpu.sh + wait-ready.sh の使い方」の直前** に挿入する。

挿入する内容（要点）:

```markdown
## 統合スクリプト（推奨）

`llama-up.sh` / `llama-down.sh` は電源制御から llama-server 起動・停止までを 1 コマンドに統合します。
日常運用ではこちらを使ってください。個別ステップを制御したい場合のみ、後述の `start.sh` / `wait-ready.sh` / `stop.sh` を使います。

### 起動: llama-up.sh

.claude/skills/llama-server/scripts/llama-up.sh [server] [hf-model] [mode] [fit-ctx]

引数すべて省略可（デフォルト: `t120h-p100` / `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M` / `fit`）。

動作:
1. power.sh status で電源確認
2. Off なら power.sh on → SSH 疎通待ち（最大 5 分）
3. http://<ip>:8000/health に 200 が返れば既起動扱いで exit 0（冪等）
4. start.sh → wait-ready.sh

ロック: 取得しない。必要なら事前に `gpu-server/scripts/lock.sh <server>` を実行。

### 停止: llama-down.sh

.claude/skills/llama-server/scripts/llama-down.sh [server] [--force]

動作:
1. lock-status.sh でロック保持者を確認
   - 自分保持 → 継続、最後に unlock
   - 他者保持 → exit 1（`--force` で警告のみ、unlock はしない）
   - 未ロック → 警告のみで継続
   - UNREACHABLE → exit 1
2. stop.sh → power.sh off
3. 自分保持だったロックのみ unlock

「自分のロック」判定: session_id が `<hostname>-<pid>-<timestamp>` 形式なので、末尾 2 セグメントを剥がした hostname 部分が `$(hostname)` と一致するか比較。
```

既存セクションは順序を変えず、文言も変更しない。

---

## 検証手順

実装後、以下を順に実行する。

### V1: llama-up.sh - 電源 OFF からの一発起動

```bash
# 事前: 排他のためロック取得（実環境では必須）
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 既存 llama-server があれば止める
.claude/skills/llama-server/scripts/stop.sh t120h-p100

# 電源 OFF
.claude/skills/gpu-server/scripts/power.sh t120h-p100 off
sleep 60  # シャットダウン完了待ち

# 一発起動
.claude/skills/llama-server/scripts/llama-up.sh t120h-p100 \
  "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M" 8192
# 期待: power on → SSH 待機 → start → wait-ready 全通過、exit 0
# 期待: curl http://10.1.4.14:8000/health → 200
```

### V2: llama-up.sh - 既起動時の冪等性

```bash
# V1 直後（llama-server 起動中）でもう一度実行
.claude/skills/llama-server/scripts/llama-up.sh t120h-p100
# 期待: 「既に起動しています」メッセージで即 exit 0
# 期待: start.sh は呼ばれない（ttyd 再起動・モデル再ロードが起きない）
```

### V3: llama-down.sh - 自分ロックでの正常停止

```bash
# 自分のロック保持状態で実行
.claude/skills/llama-server/scripts/llama-down.sh t120h-p100
# 期待: stop → power off → unlock 完了、exit 0
# 期待: lock-status.sh で available, power.sh status で Off
```

### V4: llama-down.sh - 他者ロックでの中断

```bash
# 他者ロックをシミュレート（別の session_id を直接書き込む）
.claude/skills/gpu-server/scripts/lock.sh t120h-p100 "other-host-99999-19700101_000000"

.claude/skills/llama-server/scripts/llama-down.sh t120h-p100
# 期待: exit 1、ロック残存、サーバ稼働継続

# --force での強制停止
.claude/skills/llama-server/scripts/llama-down.sh t120h-p100 --force
# 期待: 警告のみ、停止実行、ロックは残存（他者ロックは触らない）

# クリーンアップ
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100  # session_id 省略で強制解除
```

### V5: llama-down.sh - 未ロックでの継続

```bash
# ロックなしの状態で実行（注意メッセージで継続するか確認）
.claude/skills/llama-server/scripts/llama-down.sh t120h-p100
# 期待: 「ロックなしで停止します」メッセージで継続、stop → off → unlock スキップ
```

### V6: 既存スクリプト未変更の確認

```bash
git diff .claude/skills/llama-server/scripts/start.sh \
         .claude/skills/llama-server/scripts/stop.sh \
         .claude/skills/llama-server/scripts/wait-ready.sh \
         .claude/skills/gpu-server/scripts/power.sh \
         .claude/skills/gpu-server/scripts/lock.sh \
         .claude/skills/gpu-server/scripts/unlock.sh \
         .claude/skills/gpu-server/scripts/lock-status.sh
# 期待: 空 diff（追加ファイルと SKILL.md のみ変更）
```

---

## 実機検証実施計画（本フェーズで実施）

### 前提条件

- **対象サーバ**: `t120h-p100`（事前確認で電源 OFF、ロックなし状態）
- **検証モデル**: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M` モード `fit`（llama-up.sh のデフォルト）
- **gpu-server スキル必須**: CLAUDE.md の規約に従い、サーバ操作前にロック取得する
- **ロック取得タイミング**: 電源 OFF 状態では SSH 不可のためロック取得不能。**llama-up.sh で起動後**、SSH 疎通可能になってから取得する

### サイクル構成

V3（自分ロック停止）と V5（未ロック停止）はいずれも `llama-down.sh` を停止段階まで進めるため、両方を厳密に検証するには起動を 3 回必要とする。実機検証は **3 サイクル** で実施する。

#### サイクル 1: V1, V2, V4 検証

```
状態: 電源 OFF, ロックなし

A-1. llama-up.sh t120h-p100  (引数省略でデフォルト適用)
     期待[V1]: power on → SSH 待ち → start → wait-ready 全通過、exit 0
     計測: 各 Phase の所要秒数を記録

A-2. llama-up.sh t120h-p100  (連続実行)
     期待[V2]: 「既に起動しています」即 exit 0、start.sh は呼ばれない
     計測: 実行時間（5 秒程度想定）

B-1. lock.sh t120h-p100 "other-host-99999-19700101_000000"
     他者ロックをシミュレート

B-2. llama-down.sh t120h-p100
     期待[V4 part1]: 「他者ロック」エラーで exit 1、サーバ稼働継続

B-3. lock-status.sh t120h-p100
     期待: ロック残存確認（"LOCKED" + Holder: other-host-...）

B-4. llama-down.sh t120h-p100 --force
     期待[V4 part2]: 警告「他者ロックを無視」→ stop → power off 完了、ロックは残存

B-5. unlock.sh t120h-p100  (session_id 省略 = 強制解除)
     クリーンアップ

状態: 電源 OFF, ロックなし
```

#### サイクル 2: V3 検証

```
状態: 電源 OFF, ロックなし

C-1. llama-up.sh t120h-p100
     再起動（V1 と同じだが V3 のセットアップ用、再検証はしない）

C-2. lock.sh t120h-p100
     自分のロック取得（session_id 自動生成 = "aws-mmns-generic-PID-TIMESTAMP"）

C-3. llama-down.sh t120h-p100
     期待[V3]: 「自分のロック」検出 → stop → power off → unlock 完了、exit 0

C-4. lock-status.sh t120h-p100
     期待: "available" (ロック解放確認)

状態: 電源 OFF, ロックなし
```

#### サイクル 3: V5 検証

```
状態: 電源 OFF, ロックなし

D-1. llama-up.sh t120h-p100
     再起動

D-2. (ロック取得せず) llama-down.sh t120h-p100
     期待[V5]: 「ロックなしで停止します」警告で継続 → stop → power off → 「ロック解放スキップ」、exit 0

D-3. lock-status.sh t120h-p100, power.sh t120h-p100 status
     期待: available + 電源 Off

状態: 電源 OFF, ロックなし
```

### 各サイクルの所要時間見積もり

| サイクル | 主要操作 | 想定時間 |
|---------|---------|----------|
| 1 | 電源 ON+起動 (8-12 分) + V2 (5 秒) + V4 (停止 2-3 分) | 約 15 分 |
| 2 | 起動 (5-10 分、キャッシュ済みなら速い) + V3 停止 (2-3 分) | 約 10 分 |
| 3 | 起動 (5-10 分) + V5 停止 (2-3 分) | 約 10 分 |
| **合計** | | **約 35-45 分** |

**注**: 初回起動でモデルがキャッシュにない場合、`Qwen3.5-122B-A10B` は約 70 GB のダウンロードが発生し、初回サイクルが大幅に長引く可能性がある。事前に t120h-p100 上のキャッシュ状況を確認することは電源 OFF 状態では不可。

### 検証実行時の運用注意

- `start.sh` のビルドフェーズ（cmake + make）は 120 秒を超えることがあるため、`llama-up.sh` を Bash ツールで実行する際は **`timeout: 600000` (10 分)** または `run_in_background` を指定する
- `wait-ready.sh` は fit モードで最大 300 秒ポーリング（既存仕様）。タイムアウト時のリトライ判断はユーザに委ねる
- 各サイクル間で **強制 unlock** を実行し、次のサイクルが「ロックなし」状態から始まることを保証する
- 検証中、別セッションからの t120h-p100 操作を避ける（ロック取得は他者保護にもなる）
- 失敗時のクリーンアップ: 強制 unlock + 必要に応じて `power.sh force-off` + `stop.sh`

### 検証ログの取得方法

- 各コマンドの標準出力と終了コード（`$?`）を記録
- 期待挙動と異なる場合は、追加で `lock-status.sh`, `power.sh status`, `ssh <server> 'ps aux | grep llama-server'`, `tail /tmp/llama-server.log` を取得して原因分析
- Phase 2 完了時点のログは `report/attachment/2026-05-12_051827_llama_up_down_scripts/verification/` 配下に保存済み（前レポートで参照中）

> **Phase 2 のレポート追記は完了済み**（前レポート `report/2026-05-12_051827_llama_up_down_scripts.md`）。Phase 3 では既存レポートを **修正せず**、新規レポートを作成する（後述 `### 新規レポート作成` を参照）。

---

## エッジケース・既知の制約

- **電源 ON 後 OS 起動失敗**: SSH 待機 5 分タイムアウトで exit 1。BMC レベル ON / OS hang のケースをユーザに通知する。
- **/health 200 だが異常状態**: 設計上「200 なら既起動」とみなし start.sh をスキップ。500/503 の場合は通常フロー継続するが、start.sh の既存プロセスチェックで exit 1 になる（手動診断推奨の状態）。
- **stop.sh 失敗時の挙動**: 警告のみで unlock + power off へ続行（ユーザ確認済み、推奨案を採用）。電源 OFF すれば結果的にプロセスも停止する。
- **power.sh off 失敗時のロック状態**: unlock は power off の **前** に実行する設計に変更（設計修正フェーズで対応）。これにより power off API エラー時もロックは事前に解放済み。
- **ヘルスチェックと他者 start のレース**: 設計上考慮外（ロックの責任範囲）。

---

## Phase 3: 設計修正（本フェーズ）

### 修正対象ファイル

| ファイル | 変更内容 |
|----------|---------|
| `.claude/skills/llama-server/scripts/llama-down.sh` | Step 3 (`power.sh off`) と Step 4 (`unlock.sh`) の順序を入れ替え。新フロー: Step 2 stop → Step 3 unlock → Step 4 power off |
| `.claude/skills/llama-server/SKILL.md` | 「### 停止: llama-down.sh」セクションの動作説明を新順序に合わせて更新 |

`gpu-server` 配下のスクリプトおよびそれ以外の `llama-server` スクリプトは未変更（受け入れ基準 5 を継続維持）。

### llama-down.sh の修正詳細

**変更前** (lines 80-98):

```bash
# --- Step 2: llama-server 停止 ---
echo "==> [2/4] llama-server を停止中..."
if ! "$SCRIPT_DIR/stop.sh" "$SERVER"; then
  echo "WARNING: stop.sh が失敗しましたが、power off を続行します" >&2
fi

# --- Step 3: 電源 OFF ---
echo "==> [3/4] $SERVER の電源を OFF にします..."
if ! "$GPU_SCRIPTS_DIR/power.sh" "$SERVER" off; then
  echo "WARNING: power.sh off に失敗しました（API エラー等）。unlock 段階へ進みます。" >&2
fi

# --- Step 4: 自分保持ロックの解放 ---
if [ -n "$OWN_LOCK" ]; then
  echo "==> [4/4] ロックを解放します..."
  "$GPU_SCRIPTS_DIR/unlock.sh" "$SERVER" "$OWN_LOCK"
else
  echo "==> [4/4] ロック解放スキップ（未保持または --force のため）"
fi
```

**変更後**:

```bash
# --- Step 2: llama-server 停止 ---
echo "==> [2/4] llama-server を停止中..."
if ! "$SCRIPT_DIR/stop.sh" "$SERVER"; then
  echo "WARNING: stop.sh が失敗しましたが、続行します" >&2
fi

# --- Step 3: 自分保持ロックの解放（power off 前に実行: power off 後は SSH 切断のため）---
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
```

ヘッダーコメント（lines 16-19）の「ロック検証ルール」は変更不要（Step 順序の説明はないため）。

### SKILL.md の修正詳細

`.claude/skills/llama-server/SKILL.md` の「### 停止: llama-down.sh」セクション内の動作説明を更新する。

**変更前** (lines 121-122):
```
2. `stop.sh` → `power.sh off`
3. 自分保持だったロックのみ `unlock`
```

**変更後**:
```
2. `stop.sh` → 自分保持時のみ `unlock` → `power.sh off`
```

下部の補足文 (line 126):
```
`stop.sh` または `power.sh off` が失敗しても警告のみで後続ステップを継続します（電源 OFF すれば結果的にプロセスも止まるため）。
```
は変更不要（修正後も同じ意味で成立する）。

### 修正の根拠

実機検証 V3 で取得したログ（`cycle2_v3_own-lock-stop.log`）に以下が記録されている:

```
==> [3/4] t120h-p100 の電源を OFF にします...
t120h-p100: off コマンドを送信しました (ResetType: GracefulShutdown)
==> [4/4] ロックを解放します...
Error: SSH connection to t120h-p100 failed
llama-down.sh EC=3
```

`power.sh off` の Redfish API 経由のグレースフルシャットダウン要求は iLO 側で即時受理される（HTTP 2xx）が、OS のシャットダウン処理は数秒〜数十秒かかる。その間に `unlock.sh` の SSH 接続（ConnectTimeout=5）を試みても失敗する。

unlock を power off の前に移動すれば、SSH 接続が確実に有効な状態で unlock を実行できる（stop.sh が成功した直後なので接続も生きている）。

### 修正後の実機検証

**条件**: V3 のみ再検証。V1/V2/V4/V5 は前回 PASS 済みなので対象外。

**手順**:

1. **電源状態確認** (read-only): `power.sh t120h-p100 status` で Off 確認
2. **再起動**: `llama-up.sh t120h-p100` で再起動 (`run_in_background` + Monitor で進捗観察、ビルド差分なしのため 8-10 分想定)
3. **wrapper 強制停止**: `==> 起動完了` 検出後 `TaskStop` で wrapper を kill (前回観察した ssh -f fd 継承ハング回避)
4. **ヘルスチェック確認**: `curl -sf http://10.1.4.14:8000/health` → `{"status":"ok"}`
5. **自分ロック取得**: `lock.sh t120h-p100`（自動生成 session_id を取得）
6. **lock-status 確認**: `Holder` が `$(hostname)-...` で始まることを確認
7. **修正版 llama-down.sh 実行**: `llama-down.sh t120h-p100`
   - 期待出力順序:
     ```
     ==> [1/4] ... 自分のロック (holder=...) → 停止後に解放します
     ==> [2/4] llama-server を停止中...
     ==> [3/4] ロックを解放します...
     Lock released: t120h-p100 (was held by: ...)
     ==> [4/4] t120h-p100 の電源を OFF にします...
     ==> 停止完了
     ```
   - 期待終了コード: `0`
8. **検証**:
   - `lock-status.sh t120h-p100` → 即座に `UNREACHABLE` か `available`（既に unlock 済み + 電源 OFF 進行中）
   - 1-2 分後 `power.sh status` → `Off`

**ログ保存先**: `report/attachment/<新規レポート名>/verification/cycle4_v3_after_fix.log`（実装時にタイムスタンプから確定）

### 静的検証

```bash
bash -n .claude/skills/llama-server/scripts/llama-down.sh
git diff --stat \
  .claude/skills/llama-server/scripts/start.sh \
  .claude/skills/llama-server/scripts/stop.sh \
  .claude/skills/llama-server/scripts/wait-ready.sh \
  .claude/skills/llama-server/scripts/llama-up.sh \
  .claude/skills/gpu-server/scripts/*.sh
# → 空（既存スクリプト・llama-up.sh は無変更）
```

### 新規レポート作成

既存レポート `report/2026-05-12_051827_llama_up_down_scripts.md` は **修正しない**（前タスクの実機検証フェーズの記録として保持）。

本フェーズの成果は **新規レポート** として作成する。

**ファイル名**: `report/<yyyy-mm-dd_hhmmss>_llama_down_unlock_order_fix.md`

タイムスタンプは実装時に `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得して確定する。

**フォーマット**: [REPORT.md](../../projects/llm-server-ops/REPORT.md) に従う。

**含めるセクション**:

1. **タイトル**: `llama-down.sh unlock 順序修正（Step 3/4 入れ替え）`
2. **実施日時** (JST、分まで)
3. **添付ファイル**:
   - 設計修正フェーズのプラン (`attachment/<reportname>/plan.md`)
   - 修正後再検証ログ (`attachment/<reportname>/verification/cycle4_v3_after_fix.log`)
4. **前提・目的**:
   - 背景: 前タスクの実機検証で V3 PASS with caveat（unlock SSH 失敗）が判明
   - 参照リンク: 前レポート `report/2026-05-12_051827_llama_up_down_scripts.md`
   - 目的: `llama-down.sh` の Step 順序を入れ替えて V3 を caveat なし PASS にする
5. **環境情報**: t120h-p100、検証モデル（Qwen3.5-122B-A10B fit）、llama.cpp バージョン
6. **修正内容**:
   - 修正対象ファイルと差分概要（`llama-down.sh` の Step 3/4 入れ替え、SKILL.md 表記更新）
   - 修正前後の Step フロー比較
7. **再現方法**: bash -n、git diff、実機再検証手順
8. **実施結果**:
   - 静的検証（bash -n PASS、既存スクリプト差分空）
   - 実機再検証（V3 再実施）: 観測ログ要約、終了コード、所要時間
9. **既知の制約・今後の改修**:
   - 残課題として `start.sh` の `ssh -f` fd 継承問題に言及（前タスクで観測済み、本フェーズ範囲外）

**添付ディレクトリ**: `report/attachment/<reportname>/`
- `plan.md`: 設計修正フェーズ含む最終プラン（本ファイルをコピー）
- `verification/cycle4_v3_after_fix.log`: 再検証実行ログ

### 全体フロー

```
[Phase 3 開始]
  電源 OFF（前回 V5 検証後の状態）
   ↓
[修正]
  llama-down.sh の Step 3/4 入れ替え
  SKILL.md の動作説明更新
  bash -n PASS、git diff で既存スクリプト未変更を確認
   ↓
[実機再検証 V3]
  llama-up.sh で再起動 → 自分ロック取得 → 修正版 llama-down.sh → 期待挙動を確認
   ↓
[新規レポート作成]
  report/<新ファイル名>.md を作成、本プランと再検証ログを添付
   ↓
[Phase 3 完了]
  電源 OFF、ロックなし、新規レポート作成済み
```
