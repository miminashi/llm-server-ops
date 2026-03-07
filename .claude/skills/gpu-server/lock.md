# 排他制御（ロック）

複数のClaudeセッションがGPUサーバに同時アクセスすることを防ぐための排他制御機能です。

## ロックが必要な操作

以下の操作を行う前に、必ず対象サーバのロックを取得してください：

| 操作 | 説明 |
|------|------|
| llama-serverの起動・停止 | GPUリソースを占有 |
| llama-serverへのリクエスト | 推論中のコンテキスト競合を防止 |
| リモートブラウザの起動・再起動 | ブラウザセッションの競合を防止 |
| リモートブラウザへのCDP接続 | ブラウザ操作の競合を防止 |
| `try-browser-use/main.py` の実行 | 上記すべてを使用 |

## 仕組み

シンボリックリンクのアトミック性を利用したロック機構です：

- **ロックファイル**: `/tmp/gpu-server-locks/<server>.lock`
- **アトミック性**: `ln -s` は既存ファイルがあると失敗するため、複数プロセスが同時にロックを取得しようとしても1つのみ成功
- **ロック情報**: シンボリックリンクの参照先にセッションIDを格納

## 使い方

### ロック取得

```bash
.claude/skills/gpu-server/scripts/lock.sh <server> [session_id]
```

| 引数 | 説明 |
|------|------|
| `server` | サーバ名（`mi25`、`t120h-p100`、または `t120h-m10`） |
| `session_id` | セッション識別子（省略時: `hostname-pid-timestamp`） |

```bash
# 例: t120h-p100のロックを取得
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 例: セッションIDを指定して取得
.claude/skills/gpu-server/scripts/lock.sh t120h-p100 "claude-session-001"
```

**終了コード**:
- `0`: ロック取得成功
- `1`: 既に他のセッションがロックを保持
- `2`: 引数エラー

### ロック解放

```bash
.claude/skills/gpu-server/scripts/unlock.sh <server> [session_id]
```

| 引数 | 説明 |
|------|------|
| `server` | サーバ名（`mi25`、`t120h-p100`、または `t120h-m10`） |
| `session_id` | セッション識別子（指定すると所有権を検証） |

```bash
# 例: t120h-p100のロックを解放
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100

# 例: セッションIDを検証して解放（自分のロックのみ解放可能）
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100 "claude-session-001"
```

**終了コード**:
- `0`: ロック解放成功（またはロックが存在しない）
- `1`: 異なるセッションがロックを保持している
- `2`: 引数エラー

### ロック状態確認

```bash
.claude/skills/gpu-server/scripts/lock-status.sh [server]
```

```bash
# 例: 全サーバのロック状態を表示
.claude/skills/gpu-server/scripts/lock-status.sh

# 例: 特定サーバのロック状態を表示
.claude/skills/gpu-server/scripts/lock-status.sh t120h-p100
```

**出力例**:
```
=== GPU Server Lock Status ===

mi25: available

t120h-p100: LOCKED
  Holder: ubuntu-12345-20251226_120000
  Since:  2025-12-26 12:00:00
```

---

## 推奨ワークフロー

### GPUサーバを使用する前

```bash
# 1. ロック状態を確認
.claude/skills/gpu-server/scripts/lock-status.sh

# 2. ロックを取得
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 作業完了後

```bash
# ロックを解放
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 他のセッションがロックを保持している場合

ロック取得に失敗した場合は、以下を確認してください：

1. **ロック保持者を確認**: `lock-status.sh` でセッションIDを確認
2. **待機**: 他のセッションの作業完了を待つ
3. **古いロックの確認**: 長時間経過している場合は、人間に確認してから手動で解放

```bash
# 強制解放（セッションIDを指定しない）
# 注意: 他のセッションの作業に影響を与える可能性があります
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

---

## 注意事項

- **プロセス異常終了時**: ロックは自動解放されません。`lock-status.sh` で確認し、必要に応じて手動解放してください
- **サーバ再起動時**: `/tmp` のファイルはクリアされるため、ロックも解放されます
- **複数リソース**: 現在はサーバ単位のロックのみ対応しています（llama-serverとリモートブラウザを個別にロックすることはできません）
