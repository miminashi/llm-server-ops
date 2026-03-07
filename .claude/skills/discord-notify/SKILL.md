---
name: discord-notify
description: Discordへ通知を送信。汎用メッセージやレポートURL付き通知をwebhook経由で投稿。Discord、通知、webhook、投稿、レポートに関する作業で使用。
---

# Discord通知

Discordへメッセージを投稿するスキルです。レポートURL付きの通知も送信できます。

## スクリプト実行時の注意

**すべてのスクリプトはプロジェクトルートからの相対パス（`.claude/skills/discord-notify/scripts/...`）で実行してください。** フルパス（`/home/ubuntu/projects/llm-server-ops/.claude/skills/...`）で実行すると、Claude Code の承認ダイアログが毎回表示されます。

## 使い方

```bash
# メッセージのみ送信
.claude/skills/discord-notify/scripts/notify.sh "メッセージ"

# レポートURL付きで送信
.claude/skills/discord-notify/scripts/notify.sh "1行要約" "レポートファイルパス"

# 例
.claude/skills/discord-notify/scripts/notify.sh \
  "P100で50回テスト実行、成功率92%を達成" \
  "report/2026-01-02_0609_test_results.md"
```

## 引数

| 引数 | 必須 | 説明 |
|------|------|------|
| 第1引数 | 必須 | メッセージ（Discordに表示される内容） |
| 第2引数 | 任意 | レポートファイルのパス（`report/` からの相対パスまたは絶対パス） |

## URL生成ルール

レポートファイルのパスから自動的にURLを生成します：

| 入力パス | 生成URL |
|---------|---------|
| `report/2026-01-02_test.md` | `http://10.1.6.1:5032/llm-server-ops/report/2026-01-02_test.md` |
| `/home/ubuntu/projects/llm-server-ops/report/test.md` | `http://10.1.6.1:5032/llm-server-ops/report/test.md` |

## 投稿フォーマット

レポートパスあり：
```
**レポート作成**
1行要約

URL: http://10.1.6.1:5032/llm-server-ops/report/...
```

レポートパスなし：
```
メッセージ内容
```

## 設定

Webhook URLは `scripts/notify.sh` 内にハードコードされています。変更が必要な場合はスクリプトを編集してください。
