# CLAUDE.md

このファイルは、Claude Code (claude.ai/code) がこのリポジトリのコードを扱う際のガイダンスを提供します。

**応答言語**: Claudeは日本語で応答してください。

---

## GPUサーバとLLM

**重要**: GPUサーバを使用する場合は、**必ず Skill `gpu-server` を使用してください**。このスキルはサーバのロック管理を行い、複数のClaudeセッションが同時にサーバを使用することを防ぎます。

- GPUサーバ（mi25、t120h-p100、t120h-m10）の管理、リモートブラウザの管理に関する情報は `.claude/skills/gpu-server/` にあります。
- llama-serverの起動・管理、モデル選択に関する情報は `.claude/skills/llama-server/` にあります。

### ロックが必要なケース

| ケース | ロック必要 | 理由 |
|--------|-----------|------|
| GPUサーバでllama-serverを使用 | **必要** | 他セッションとの競合を防ぐ |
| GPUサーバでリモートブラウザを使用 | **必要** | 同上 |
| **ローカルでブラウザを実行**（CDPプロキシ経由） | 不要 | GPUサーバのリソースを使用しない |
| **読み取り専用の監視・確認**（ダウンロード進捗、VRAM確認、プロセス確認、ログ確認） | 不要 | リソースを専有しない |

**注**: ローカルでDockerコンテナのブラウザを起動し、LLMサーバのみGPUサーバを使用する場合は、LLM使用のためロックが必要です。

### クイックリファレンス

| サーバ | IPアドレス | OpenAI互換API |
|--------|-----------|---------------|
| mi25 | 10.1.4.13 | `http://10.1.4.13:8000/v1` |
| t120h-p100 | 10.1.4.14 | `http://10.1.4.14:8000/v1` |

```bash
# llama-server確認
ssh t120h-p100 "ps aux | grep llama-server | grep -v grep"

# リモートブラウザ確認
ssh t120h-p100 "docker ps | grep chrome-novnc-cdp"
```

---

## Discord通知

レポート作成時や汎用的な通知をDiscordに送信してください。

```bash
# メッセージのみ送信
.claude/skills/discord-notify/scripts/notify.sh "メッセージ"

# レポートURL付きで送信
.claude/skills/discord-notify/scripts/notify.sh "1行要約" "レポートパス"
```

**例**:
```bash
# 汎用通知
.claude/skills/discord-notify/scripts/notify.sh "デプロイ完了しました"

# レポート通知
.claude/skills/discord-notify/scripts/notify.sh \
  "P100で50回テスト、成功率92%を達成" \
  "report/2026-01-02_1200_test_results.md"
```

詳細は `.claude/skills/discord-notify/SKILL.md` を参照してください。

---

## 重要な制約

| 制約 | 説明 |
|------|------|
| GPUサーバ使用 | **必ず Skill `gpu-server` を使用**（ロック管理のため） |
| スクリプト実行 | **プロジェクトルートからの相対パス**（`.claude/skills/...`）で実行すること。フルパス（`/home/ubuntu/projects/...`）は使用しない |
