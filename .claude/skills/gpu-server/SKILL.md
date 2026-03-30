---
name: gpu-server
description: GPUサーバ（mi25、t120h-p100、t120h-m10）の管理。排他制御（ロック）、リモートブラウザの管理、エンドポイント情報。GPUサーバ、リモートブラウザ、VRAM、サーバー切り替えに関する作業で使用。
---

# GPUサーバ管理

このSkillはGPUサーバとLLMサーバの管理に関する情報を提供します。

## スクリプト実行時の注意

**すべてのスクリプトはプロジェクトルートからの相対パス（`.claude/skills/gpu-server/scripts/...`）で実行してください。** フルパス（`/home/ubuntu/projects/llm-server-ops/.claude/skills/...`）で実行すると、Claude Code の承認ダイアログが毎回表示されます。

## 利用可能なGPUサーバ

| ホスト名 | GPU | 枚数 | VRAM合計 | プラットフォーム | IPアドレス |
|---------|-----|------|---------|-----------------|-----------|
| `mi25` | AMD MI25 | 4 | 64GB | ROCm | 10.1.4.13 |
| `t120h-p100` | NVIDIA Tesla P100 | 4 | 64GB | CUDA | 10.1.4.14 |
| `t120h-m10` | NVIDIA Tesla M10 | 16 (15使用可) | 128GB | CUDA | 10.1.4.15 |

**t120h-m10の注意事項**:
- nvidia-smiでは16個のGPUが見えるが、llama-cppでは15個のみ使用可能
- CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14 を指定する必要あり
- 他サーバより低速だが、大きなVRAMを活用可能

SSH経由でコマンドを実行できます。

**llama-serverの起動・管理は [`llama-server` スキル](../llama-server/SKILL.md) を参照してください。**

## ベンチマーク結果（2025-12-08測定）

| サーバ | pp512 (t/s) | tg128 (t/s) |
|--------|-------------|-------------|
| mi25 | 347.33 | 51.65 |
| t120h-p100 | 693.12 | 63.79 |

- **pp512**: Prompt Processing（512トークン）
- **tg128**: Token Generation（128トークン）
- t120h-p100はmi25より約2倍高速（Prompt Processing）

## エンドポイント

| サーバ | IPアドレス | OpenAI互換API | CDP（ブラウザ） | ブラウザ再起動API |
|--------|-----------|---------------|----------------|------------------|
| mi25 | `10.1.4.13` | `http://10.1.4.13:8000/v1` | `http://10.1.4.13:9222` | `http://10.1.4.13:9221` |
| t120h-p100 | `10.1.4.14` | `http://10.1.4.14:8000/v1` | `http://10.1.4.14:9222` | `http://10.1.4.14:9221` |
| t120h-m10 | `10.1.4.15` | `http://10.1.4.15:8000/v1` | `http://10.1.4.15:9222` | `http://10.1.4.15:9221` |

**IPアドレスの動的取得**:
```bash
ssh -G mi25 | grep ^hostname
ssh -G t120h-p100 | grep ^hostname
ssh -G t120h-m10 | grep ^hostname
```

## サーバー切り替え

`try-browser-use/main.py` は環境変数でLLMサーバーを切り替えられます：

```bash
# mi25を使用（デフォルト）
cd try-browser-use && ./run.sh

# t120h-p100を使用
cd try-browser-use && LLM_SERVER_HOST=10.1.4.14 MODEL_NAME="bu-30b-a3b:Q8_0" ./run.sh
```

| 環境変数 | デフォルト値 | 説明 |
|---------|-------------|------|
| `LLM_SERVER_HOST` | `10.1.4.13` | LLMサーバーのIPアドレス |
| `MODEL_NAME` | `mi25/unsloth/gpt-oss-20b-GGUF:Q8_0` | モデル名（aliasと一致させる） |

## サーバー選択の方針

GPUサーバーを使用する際は、以下の優先順位で選択してください：

1. **P100（t120h-p100）を優先**: 高速なP100を最優先で使用
2. **P100が使用中ならMI25**: P100がロックされている場合はMI25を使用
3. **M10（t120h-m10）は特別用途**: 大きなVRAM（128GB）が必要な場合のみ使用（他サーバより低速）
4. **全て使用中ならランダム**: どれもロックされている場合はランダムに選択（待機が必要な場合あり）

```bash
# ロック状態を確認してサーバーを選択
.claude/skills/gpu-server/scripts/lock-status.sh
```

## 電源制御（iLO5）

iLO5のRedfish APIを使用して、GPUサーバの電源ON/OFFを行えます。

```bash
# 電源状態を確認
.claude/skills/gpu-server/scripts/power.sh t120h-p100 status

# 電源ON
.claude/skills/gpu-server/scripts/power.sh t120h-p100 on

# グレースフルシャットダウン
.claude/skills/gpu-server/scripts/power.sh t120h-p100 off

# 強制電源OFF
.claude/skills/gpu-server/scripts/power.sh t120h-p100 force-off
```

### iLO5認証情報が未設定の場合

認証情報がない状態で電源制御を実行すると、終了コード `10` でエラーになります。その場合は `AskUserQuestion` でユーザに以下を問い合わせてください：

1. iLOのIPアドレスまたはホスト名
2. iLOのユーザ名
3. iLOのパスワード

取得後、`setup` コマンドで認証テスト＋永続化を行います：

```bash
.claude/skills/gpu-server/scripts/power.sh t120h-p100 setup <ilo_host> <ilo_user> <ilo_pass>
```

認証に成功すると `~/.config/gpu-server/.env` に `ILO_<SERVER>_HOST/USER/PASS` として保存されます（環境変数 `GPU_SERVER_ENV` でパスを上書き可能）。

| サーバ | iLOホスト |
|--------|----------|
| t120h-p100 | 10.1.4.8 |

## 排他制御（重要）

複数のClaudeセッションがGPUサーバに同時アクセスすることを防ぐため、**GPUサーバを使用する前に必ずロックを取得してください**。

**ロックが必要な操作**:
- llama-serverの起動・停止・使用
- リモートブラウザの起動・再起動・使用
- `try-browser-use/main.py` の実行（llama-server + リモートブラウザを両方使用）

```bash
# ロック状態を確認
.claude/skills/gpu-server/scripts/lock-status.sh

# ロック取得（GPUサーバ使用前）
.claude/skills/gpu-server/scripts/lock.sh t120h-p100   # または mi25, t120h-m10

# ロック解放（GPUサーバ使用後）
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

詳細は [排他制御のドキュメント](./lock.md) を参照してください。

## GPUサーバ環境

### 利用可能なツール

| ツール | パス | 説明 |
|--------|------|------|
| `uv` | `/home/llm/.local/bin/uv` | Pythonパッケージマネージャ |

```bash
# GPUサーバでuvを使用する例
ssh t120h-p100 "/home/llm/.local/bin/uv --version"
ssh mi25 "/home/llm/.local/bin/uv run python script.py"
```

## 初期セットアップ

新しいGPUサーバや、llama.cpp/リモートブラウザが未セットアップのサーバに対して、以下のスクリプトでセットアップできます。

### llama.cpp セットアップ

```bash
# llama.cpp のクローン・ビルドスクリプト配置・ビルド
.claude/skills/gpu-server/scripts/setup-llama-cpp.sh <server>

# 例
.claude/skills/gpu-server/scripts/setup-llama-cpp.sh t120h-m10
```

このスクリプトは以下を行います：
1. `~/llama.cpp` がなければ GitHub からクローン
2. サーバに応じた `update_and_build.sh` を配置（MI25はROCm、P100/M10はCUDA）
3. ビルド環境の確認（nvcc/hipcc）
4. 必要に応じてビルド実行

**前提条件**:
- MI25: ROCm がインストール済み
- P100/M10: CUDA Toolkit がインストール済み（`nvcc` が使える状態）

nvccがない場合はインストール方法を案内します。

### リモートブラウザ セットアップ

```bash
# chrome-novnc-cdp のクローン・Dockerイメージビルド
.claude/skills/gpu-server/scripts/setup-remote-browser.sh <server>

# 例
.claude/skills/gpu-server/scripts/setup-remote-browser.sh t120h-m10
```

このスクリプトは以下を行います：
1. Docker の動作確認
2. `~/chrome-novnc-cdp` がなければ GitHub からクローン
3. 最新版かチェック、更新があれば pull
4. Docker イメージのビルド
5. コンテナ起動（オプション）
6. CDP 接続確認

**前提条件**:
- Docker がインストール済み
- ユーザーが docker グループに属している

Dockerがインストールされていない場合は、インストール方法を案内します。

### サーバ間ファイル転送

GPUサーバ間で大きなファイル（モデルファイル等）を転送できます。

```bash
# ファイル転送
.claude/skills/gpu-server/scripts/transfer-file.sh <src-server> <src-path> <dst-server> <dst-path>

# 例: P100からM10にモデルファイルを転送
.claude/skills/gpu-server/scripts/transfer-file.sh t120h-p100 ~/models/model.gguf t120h-m10 ~/models/model.gguf
```

**仕組み**:
1. 転送元でPython HTTPサーバを一時起動（ポート8888-8899）
2. 転送先からcurlでダウンロード
3. 転送完了後にHTTPサーバを自動停止

**特徴**:
- SSHを経由しないため大容量ファイルの転送が高速
- プログレス表示あり
- ファイルサイズの整合性チェック

---

## 詳細リファレンス

- [排他制御（ロック）](./lock.md) - GPUサーバの排他制御
- [リモートブラウザ管理](./remote-browser.md) - Docker起動、再起動、注意事項
- [llama-server起動・管理](../llama-server/SKILL.md) - 起動コマンド、パラメータ、モデル設定（別スキル）
