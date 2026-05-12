# 統合スクリプト追加: llama-up.sh / llama-down.sh（実機検証フェーズ）

## Context

opencode フォーク（別 Claude セッション）側の README.md に「LLM サーバ起動」セクションを追加する際、現状の起動手順が `power.sh status → power.sh on → ttyd-gpu.sh → start.sh → wait-ready.sh` の 5 ステップ必要で冗長すぎる、という指摘があった。

そこで「電源 OFF 判断 → GPU サーバ起動 → llama-server 起動」を **1 コマンド** で実行できる薄いラッパースクリプトを `llama-server` スキルに追加する。停止側も対称的に `lock-status.sh → stop.sh → power.sh off → unlock.sh` を 1 コマンドに統合する。

これにより opencode 側 README は 1 行コマンド `llama-up.sh` / `llama-down.sh` で済むようになる。

**現在のフェーズ**: スクリプト実装と SKILL.md 更新は前回完了済み（静的検証 V6 PASS）。本計画は **実機検証 V1〜V5** を実施し、既存レポート `report/2026-05-12_051827_llama_up_down_scripts.md` の「実施結果 > 動作検証（未実施）」セクションを実機検証結果で更新するフェーズである。

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
- ログはレポート本文に貼り付けず、`report/attachment/2026-05-12_051827_llama_up_down_scripts/` 配下に保存してリンク

---

## レポート追記計画

既存レポート `report/2026-05-12_051827_llama_up_down_scripts.md` の「## 実施結果 > 動作検証（未実施）」セクションを **書き換え**、以下を追記する:

1. **実機検証セクション** (`### 動作検証（実機実施）`):
   - 検証日時（JST、`TZ=Asia/Tokyo date` で取得）
   - 検証環境（サーバ、モデル、初期状態）
   - 各サイクルの実施結果（V1〜V5 の PASS/FAIL、観測された出力サマリ、所要時間）
   - 想定外挙動があれば原因分析と対応

2. **添付ファイル追加**:
   - サイクルごとの実行ログを `report/attachment/2026-05-12_051827_llama_up_down_scripts/` に保存
   - レポート本文の「## 添付ファイル」セクションにリンク追加

3. **既知の制約セクションへの追記** (必要時):
   - 実機検証で新たに判明したエッジケース・制約があれば追加

レポートのファイル名は変更しない（同一タスクの継続）。

---

## エッジケース・既知の制約

- **電源 ON 後 OS 起動失敗**: SSH 待機 5 分タイムアウトで exit 1。BMC レベル ON / OS hang のケースをユーザに通知する。
- **/health 200 だが異常状態**: 設計上「200 なら既起動」とみなし start.sh をスキップ。500/503 の場合は通常フロー継続するが、start.sh の既存プロセスチェックで exit 1 になる（手動診断推奨の状態）。
- **stop.sh 失敗時の挙動**: 警告のみで power.sh off へ続行（ユーザ確認済み、推奨案を採用）。電源 OFF すれば結果的にプロセスも停止する。
- **power.sh off 失敗時の unlock**: 自分保持ロックは unlock する。サーバが OS hang でも次回 force-off → on で復旧可能にするため、ロックを放置しない方が安全。
- **ヘルスチェックと他者 start のレース**: 設計上考慮外（ロックの責任範囲）。
