---
name: llama-server
description: llama-serverの起動・管理、llama.cppのビルド。モデル選択、起動コマンド、サーバ別最適化パラメータ。
---

# llama-server スキル

llama-server の起動・管理と llama.cpp のビルドに関するスキルです。

## モデル未指定時の振る舞い

**モデルが指定されていない場合は、`AskUserQuestion` でモデル選択ダイアログを表示してください。**

```
以下のモデルから選択してください:

1. unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M — thinking対応、128k ctx
2. unsloth/gpt-oss-20b-GGUF:Q8_0 — 汎用、64k ctx
3. bartowski/browser-use_bu-30b-a3b-preview-GGUF:Q8_0 — browser-use専用、24k ctx
```

## モデル一覧

| HFモデル名 | 推奨ctx-size | 推奨サーバ | 備考 |
|-----------|-------------|-----------|------|
| `unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M` | 131072 | t120h-p100, mi25 | thinking対応MoEモデル |
| `unsloth/gpt-oss-20b-GGUF:Q8_0` | 65536 | t120h-p100, mi25 | thinking無効化推奨 |
| `bartowski/browser-use_bu-30b-a3b-preview-GGUF:Q8_0` | 24576 | t120h-p100 | browser-use専用 |

### モデル別サンプリングパラメータ

| モデル | chat-template-kwargs | サンプリング |
|--------|---------------------|-------------|
| Qwen3.5-35B-A3B | なし（thinking有効） | `--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0` |
| gpt-oss-20b | `'{"enable_thinking": false}'` | `--temp 1.0 --top-p 1.0 --top-k 0` |
| bu-30b-a3b-preview | `'{"enable_thinking": false}'` | `--temp 1.0 --top-p 1.0 --top-k 0` |

**注**: Qwen3.5系でthinkingを無効化する場合は `--chat-template-kwargs '{"enable_thinking": false}'` を追加し、サンプリングは `--temp 0.7 --top-p 0.8 --top-k 20 --min-p 0` を使用。

## スクリプト実行時の注意

**すべてのスクリプトはプロジェクトルートからの相対パス（`.claude/skills/llama-server/scripts/...`）で実行してください。** フルパス（`/home/ubuntu/projects/llm-server-ops/.claude/skills/...`）で実行すると、Claude Code の承認ダイアログが毎回表示されます。

## start.sh + ttyd-gpu.sh + wait-ready.sh の使い方

llama-server の起動は3ステップで行います:

1. **`ttyd-gpu.sh`** — GPU監視をサーバ側でバックグラウンド起動
2. **`start.sh`** — ビルド・llama-serverをサーバ側でバックグラウンド起動
3. **`wait-ready.sh`** — ヘルスチェック・Discord通知

### 例

```bash
# 1. GPU監視
.claude/skills/llama-server/scripts/ttyd-gpu.sh t120h-p100

# 2. ビルド＋llama-server起動
.claude/skills/llama-server/scripts/start.sh t120h-p100 \
  "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M" 131072

# 3. ヘルスチェック＋Discord通知
.claude/skills/llama-server/scripts/wait-ready.sh t120h-p100 \
  "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M" 131072
```

**注**: `ttyd-gpu.sh` と `start.sh` はサーバ側でバックグラウンド起動するため即座に完了します。`run_in_background` は不要です。

### ttyd-gpu.sh の動作

1. nvtop があれば使用、なければ `watch -n 1 nvidia-smi` / `rocm-smi` で代替
2. 既存の ttyd (port 7681) を停止後、サーバ側でバックグラウンド起動
3. ブラウザから `http://<server-ip>:7681` でアクセス可能

### start.sh の動作

1. 既存の llama-server プロセスを確認（起動中なら警告して終了）
2. `server-scripts/update_and_build-<server>.sh` をサーバに転送・実行
3. llama-server をサーバ側でバックグラウンド起動（ログは `/tmp/llama-server.log`）
4. ttyd (port 7682) でログ閲覧UIをバックグラウンド起動
5. ブラウザから `http://<server-ip>:7682` でログを閲覧可能

### wait-ready.sh の動作

1. `/health` エンドポイントでヘルスチェック（最大150秒ポーリング）
2. 成功時にDiscord通知を送信（GPU監視・サーバログのURLを含む）

**注意**: 起動スクリプトはデフォルトのサンプリングパラメータ（`--temp 1.0 --top-p 1.0 --top-k 0`）を使用します。モデル別の推奨パラメータが異なる場合（Qwen3.5等）は、手動でコマンドを構築してください。

## stop.sh の使い方

```bash
.claude/skills/llama-server/scripts/stop.sh <server>
```

### 例

```bash
# P100 の llama-server を停止
.claude/skills/llama-server/scripts/stop.sh t120h-p100
```

### 動作

1. `pgrep` で `./build/bin/llama-server` プロセスを検索
2. `kill` で停止（最大10秒待機）
3. Discord通知を送信（サーバ名、モデル名）

## monitor-download.sh の使い方

モデルダウンロードの進捗をリアルタイム監視します。tmuxの上ペインで表示する使い方を想定しています。

**ロック不要**: このスクリプトはファイルサイズを `stat` で読み取るだけで、GPUリソースを専有しません。他セッションがロック中でも実行できます。

```bash
# tmux上ペインで監視
tmux split-window -v -b -d -l 3 \
  .claude/skills/llama-server/scripts/monitor-download.sh t120h-p100 "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M"
```

### 動作

1. HFモデル名からキャッシュディレクトリのglobパターンを生成
2. SSH接続1本でサーバ側ループ（1秒間隔）
3. `.downloadInProgress` ファイルを自動検出、なければ完成ファイルを探す
4. タイムスタンプ、MB、Mbps、ファイル名を `\r` で上書き表示
5. ダウンロード完了（`.downloadInProgress` が消えた）時点で終了

## サーバ別最適化パラメータ

| サーバ | 固有パラメータ | 理由 |
|--------|--------------|------|
| mi25 | `-b 4096 -ub 4096` | ROCm標準設定 |
| t120h-p100 | `--flash-attn 1 --poll 0 -b 8192 -ub 8192` | Flash Attention有効、マルチGPUポーリング無効 |
| t120h-m10 | `CUDA_VISIBLE_DEVICES=0..14 -b 4096 -ub 4096` | GPU 15は使用不可 |

## server-scripts/ について

`server-scripts/` にはGPUサーバの `~/llama.cpp/` に転送して実行するビルドスクリプトがあります。**ローカルで直接実行しないでください。**

`start.sh` が自動で転送・実行しますが、手動で転送する場合:

```bash
scp .claude/skills/llama-server/server-scripts/update_and_build-t120h-p100.sh \
  t120h-p100:~/llama.cpp/update_and_build.sh
ssh -t t120h-p100 "cd ~/llama.cpp && ./update_and_build.sh"
```

## 起動前の確認

**重要**: 起動前に既存のllama-serverプロセスがないか確認してください。

```bash
ssh mi25 "ps aux | grep llama-server | grep -v grep"
ssh t120h-p100 "ps aux | grep llama-server | grep -v grep"
ssh t120h-m10 "ps aux | grep llama-server | grep -v grep"
```

**注意**: 既存のllama-serverが起動している場合、**勝手に終了しないでください**。人間や他のエージェントが使用中の可能性があります。自分で起動していないllama-serverを終了する必要がある場合は、必ずユーザに確認を取ってください。

## VRAM確認

```bash
# NVIDIA (P100/M10)
ssh t120h-p100 "nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv"
ssh t120h-m10 "nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv"

# AMD (MI25)
ssh mi25 "rocm-smi --showmeminfo vram"
```

## その他のllama.cppコマンド

```bash
# ベンチマーク実行
ssh mi25 "cd ~/llama.cpp && ./build/bin/llama-bench -hf unsloth/gpt-oss-20b-GGUF:Q8_0 -ngl 999"

# llama-cli でテスト
ssh mi25 "cd ~/llama.cpp && ./build/bin/llama-cli -hf unsloth/gpt-oss-20b-GGUF:Q8_0 -p 'Hello' -n 50"

# ログ確認
ssh t120h-p100 "tail -50 /tmp/llama-server.log"
```

## 排他制御

llama-serverを操作する前に、必ず `gpu-server` スキルでロックを取得してください。

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
# ... llama-server操作 ...
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

**例外**: 読み取り専用の操作（`monitor-download.sh`、VRAM確認、プロセス確認、ログ確認など）はロック不要です。
