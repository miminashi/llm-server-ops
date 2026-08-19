# llm-server-ops

GPUサーバ上のLLM推論サーバ（llama-server）と関連リソースを管理するClaude Code Skills集です。

## サーバ一覧

| サーバ | GPU | 枚数 | VRAM | プラットフォーム | IP |
|--------|-----|------|------|------------------|-----|
| mi25 | AMD MI25 | 4 | 64GB | ROCm | 10.1.4.13 |
| t120h-p100 | NVIDIA Tesla P100 | 4 | 64GB | CUDA | 10.1.4.14 |
| t120h-m10 | NVIDIA Tesla M10 | 15 | 128GB | CUDA | 10.1.4.15 |
| aws-gpu01 | NVIDIA Tesla P100 16GB | 7 | 112GB | CUDA | 10.8.2.1 |
| aws-gpu02 | NVIDIA Tesla P100 16GB×4 + 12GB×2 | 6 | 88GB | CUDA | 10.8.2.2 |

aws-gpu01 / aws-gpu02 は **2 台セットで 1 つの llama-server を動かす RPC 分散がデフォルト構成**です（13 GPU / 200GB）。詳細は [llama-server SKILL.md](.claude/skills/llama-server/SKILL.md) の「RPC 分散構成」節。

## エンドポイント

| サーバ | OpenAI互換API | GPU監視 (ttyd) | ログ閲覧 (ttyd) | ブラウザ CDP | ブラウザ再起動API |
|--------|---------------|----------------|-----------------|--------------|-------------------|
| mi25 | [http://10.1.4.13:8000/v1](http://10.1.4.13:8000/v1) | [http://10.1.4.13:7681](http://10.1.4.13:7681) | [http://10.1.4.13:7682](http://10.1.4.13:7682) | [http://10.1.4.13:9222](http://10.1.4.13:9222) | [http://10.1.4.13:9221](http://10.1.4.13:9221) |
| t120h-p100 | [http://10.1.4.14:8000/v1](http://10.1.4.14:8000/v1) | [http://10.1.4.14:7681](http://10.1.4.14:7681) | [http://10.1.4.14:7682](http://10.1.4.14:7682) | [http://10.1.4.14:9222](http://10.1.4.14:9222) | [http://10.1.4.14:9221](http://10.1.4.14:9221) |
| t120h-m10 | [http://10.1.4.15:8000/v1](http://10.1.4.15:8000/v1) | [http://10.1.4.15:7681](http://10.1.4.15:7681) | [http://10.1.4.15:7682](http://10.1.4.15:7682) | [http://10.1.4.15:9222](http://10.1.4.15:9222) | [http://10.1.4.15:9221](http://10.1.4.15:9221) |
| aws-gpu01 | [http://10.8.2.1:8000/v1](http://10.8.2.1:8000/v1) | [http://10.8.2.1:7681](http://10.8.2.1:7681) | [http://10.8.2.1:7682](http://10.8.2.1:7682) | （未整備） | （未整備） |
| aws-gpu02 | （RPC ワーカーのため無し） | [http://10.8.2.2:7681](http://10.8.2.2:7681) | [http://10.8.2.2:7682](http://10.8.2.2:7682) | （未整備） | （未整備） |

- **ttyd（7681 GPU監視 / 7682 ログ閲覧）は llama-server の起動時に一緒に立ち上がります**。単独で立て直したい場合は `.claude/skills/llama-server/scripts/ttyd-up.sh <server>` を実行してください（llama-server 稼働中でも安全・ロック不要）。
- aws-gpu01 / aws-gpu02 は RPC 分散構成のため、**API は aws-gpu01 側の 1 つだけ**です。GPU 監視は 13 枚のうち 6 枚がワーカー側にあるので**両機に立ちます**。ログ閲覧はメインが llama-server、ワーカーが rpc-server のログを表示します。
- aws-gpu01 / aws-gpu02 は docker 未導入のためリモートブラウザは未整備です。

## Skills一覧

| スキル | 説明 |
|--------|------|
| **[gpu-server](.claude/skills/gpu-server/SKILL.md)** | GPUサーバの排他ロック管理、リモートブラウザ管理、サーバ間ファイル転送 |
| **[llama-server](.claude/skills/llama-server/SKILL.md)** | llama-serverの起動・停止・ヘルスチェック、モデル選択、サーバ別最適化パラメータ |
| **[discord-notify](.claude/skills/discord-notify/SKILL.md)** | Discord webhook通知（汎用メッセージ、レポートURL付き通知） |

## クイックスタート

GPUサーバでllama-serverを使用する基本的なワークフローです。`llama-up.sh` / `llama-down.sh` は電源制御から起動・停止までを 1 コマンドに統合した推奨スクリプトです。

```bash
# 1. ロック状態を確認
.claude/skills/gpu-server/scripts/lock-status.sh

# 2. ロックを取得
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 3. llama-serverを起動（電源OFFなら自動でON→SSH疎通待ち→start→wait-ready）
#    引数なしで起動するとデフォルト（Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL、ctx=131072）が使われる
.claude/skills/llama-server/scripts/llama-up.sh t120h-p100 \
  "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072

# 旧 Qwen3.5 系を起動する場合の例:
#   .claude/skills/llama-server/scripts/llama-up.sh t120h-p100 \
#     "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M" 131072
#   .claude/skills/llama-server/scripts/llama-up.sh t120h-p100 \
#     "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit    # 122B は fit プロファイル必須

# その他 Qwen3.6 系の例:
#   .claude/skills/llama-server/scripts/llama-up.sh t120h-p100 \
#     "unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL" 131072   # --spec-type draft-mtp 自動付与

# 4. OpenAI互換APIとして使用
curl http://10.1.4.14:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL", "messages": [{"role": "user", "content": "Hello"}]}'

# 5. llama-serverを停止（stop → 自分保持ロックの自動解放 → 電源OFF）
.claude/skills/llama-server/scripts/llama-down.sh t120h-p100
```

個別ステップ（`start.sh` / `wait-ready.sh` / `stop.sh`）で細かく制御したい場合は [llama-server SKILL.md](.claude/skills/llama-server/SKILL.md) を参照してください。

## グローバルインストール（オプション）

通常はプロジェクトルートから `.claude/skills/...` の相対パスでスクリプトを実行しますが、複数プロジェクトや他の Claude Code セッションからも同じ Skill を呼び出したい場合は、グローバル Claude Code プラグインとして `~/.claude/plugins/` に登録できます。

### 前提条件

- `jq` がインストール済み（未インストールの場合: `sudo apt install jq`）
- Claude Code が `~/.claude` にインストール済み

### インストール

```bash
# プロジェクトルートから実行（gpu-server と llama-server をまとめて登録）
.claude/skills/install-all-global.sh
```

実行すると以下が行われます:

- `gpu-server` / `llama-server` スキルを `~/.claude/plugins/cache/` 配下にコピー
- SKILL.md 内の相対パス参照を絶対パスに書き換え
- `~/.claude/settings.json` に各スクリプトの実行パーミッションを登録
- プロジェクトの `.env` を `~/.config/gpu-server/.env` に冪等マージ（HF_TOKEN 等）

インストール完了後、**Claude Code を再起動してください**（`/exit` で終了し再度起動）。

### アンインストール

```bash
.claude/skills/install-all-global.sh --uninstall
```

### 個別インストール / ヘルプ

```bash
# ヘルプ表示
.claude/skills/install-all-global.sh --help

# Skill 単位でインストール（一括ではなく個別に入れたい場合）
.claude/skills/gpu-server/scripts/install-global.sh
.claude/skills/llama-server/scripts/install-global.sh
```

## ディレクトリ構成

```
llm-server-ops/
├── CLAUDE.md
├── README.md
└── .claude/skills/
    ├── install-all-global.sh           # 全スキルを一括グローバル登録
    ├── gpu-server/
    │   ├── SKILL.md
    │   ├── lock.md
    │   ├── remote-browser.md
    │   └── scripts/
    │       ├── install-global.sh       # gpu-server を単独でグローバル登録
    │       ├── lock.sh / unlock.sh / lock-status.sh
    │       ├── setup-llama-cpp.sh
    │       ├── setup-remote-browser.sh
    │       └── transfer-file.sh
    ├── llama-server/
    │   ├── SKILL.md
    │   ├── scripts/
    │   │   ├── install-global.sh                # llama-server を単独でグローバル登録
    │   │   ├── llama-up.sh / llama-down.sh      # 統合スクリプト（電源+起動/停止、推奨）
    │   │   ├── start.sh / stop.sh / wait-ready.sh
    │   │   ├── rpc-stack-up.sh / rpc-stack-down.sh  # aws-gpu01+02 の RPC 分散（既定構成）
    │   │   ├── rpc-up.sh / rpc-down.sh / rpc-llama-up.sh
    │   │   ├── ttyd-up.sh / ttyd-gpu.sh         # 監視UI（7681 GPU監視 / 7682 ログ閲覧）
    │   │   └── monitor-download.sh / monitor-hf-download.sh
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
