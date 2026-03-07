# llm-server-ops

GPUサーバ上のLLM推論サーバ（llama-server）と関連リソースを管理するClaude Code Skills集です。

## サーバ一覧

| サーバ | GPU | 枚数 | VRAM | プラットフォーム | IP |
|--------|-----|------|------|------------------|-----|
| mi25 | AMD MI25 | 4 | 64GB | ROCm | 10.1.4.13 |
| t120h-p100 | NVIDIA Tesla P100 | 4 | 64GB | CUDA | 10.1.4.14 |
| t120h-m10 | NVIDIA Tesla M10 | 15 | 128GB | CUDA | 10.1.4.15 |

## Skills一覧

| スキル | 説明 |
|--------|------|
| **[gpu-server](.claude/skills/gpu-server/SKILL.md)** | GPUサーバの排他ロック管理、リモートブラウザ管理、サーバ間ファイル転送 |
| **[llama-server](.claude/skills/llama-server/SKILL.md)** | llama-serverの起動・停止・ヘルスチェック、モデル選択、サーバ別最適化パラメータ |
| **[discord-notify](.claude/skills/discord-notify/SKILL.md)** | Discord webhook通知（汎用メッセージ、レポートURL付き通知） |

## クイックスタート

GPUサーバでllama-serverを使用する基本的なワークフローです。

```bash
# 1. ロック状態を確認
.claude/skills/gpu-server/scripts/lock-status.sh

# 2. ロックを取得
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 3. llama-serverを起動
.claude/skills/llama-server/scripts/start.sh t120h-p100 \
  "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M" 131072

# 4. ヘルスチェック（起動完了を待機）
.claude/skills/llama-server/scripts/wait-ready.sh t120h-p100 \
  "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M" 131072

# 5. OpenAI互換APIとして使用
curl http://10.1.4.14:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M", "messages": [{"role": "user", "content": "Hello"}]}'

# 6. llama-serverを停止
.claude/skills/llama-server/scripts/stop.sh t120h-p100

# 7. ロックを解放
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## ディレクトリ構成

```
llm-server-ops/
├── CLAUDE.md
├── README.md
└── .claude/skills/
    ├── gpu-server/
    │   ├── SKILL.md
    │   ├── lock.md
    │   ├── remote-browser.md
    │   └── scripts/
    │       ├── lock.sh / unlock.sh / lock-status.sh
    │       ├── setup-llama-cpp.sh
    │       ├── setup-remote-browser.sh
    │       └── transfer-file.sh
    ├── llama-server/
    │   ├── SKILL.md
    │   ├── scripts/
    │   │   ├── start.sh / stop.sh / wait-ready.sh
    │   │   ├── ttyd-gpu.sh
    │   │   └── monitor-download.sh
    │   └── server-scripts/
    │       └── update_and_build-{server}.sh
    └── discord-notify/
        ├── SKILL.md
        └── scripts/
            └── notify.sh
```

## 制約・注意事項

- **スクリプト実行パス**: すべてのスクリプトはプロジェクトルートからの相対パス（`.claude/skills/...`）で実行してください
- **排他制御**: GPUサーバ使用時は必ずロックを取得してください（読み取り専用の監視・確認はロック不要）
- **サーバ選択の優先順位**: P100 → MI25 → M10（M10は大VRAM用途のみ）
