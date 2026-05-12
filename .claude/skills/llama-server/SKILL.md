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
4. unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M — 大規模MoE、fitモード（128k ctx、B14b OT、eval 10-17.7 t/s）
```

## モデル一覧

| HFモデル名 | 推奨ctx-size | 推奨サーバ | 備考 |
|-----------|-------------|-----------|------|
| `unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M` | 131072 | t120h-p100, mi25 | thinking対応MoEモデル |
| `unsloth/gpt-oss-20b-GGUF:Q8_0` | 65536 | t120h-p100, mi25 | thinking無効化推奨 |
| `bartowski/browser-use_bu-30b-a3b-preview-GGUF:Q8_0` | 24576 | t120h-p100 | browser-use専用 |
| `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M` | fit (128k default) | t120h-p100 | 大規模MoE、Phase U-6 確定プロファイル自動適用 |

### モデル別サンプリングパラメータ

| モデル | chat-template-kwargs | サンプリング |
|--------|---------------------|-------------|
| Qwen3.5-35B-A3B | なし（thinking有効） | `--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0` |
| gpt-oss-20b | `'{"enable_thinking": false}'` | `--temp 1.0 --top-p 1.0 --top-k 0` |
| bu-30b-a3b-preview | `'{"enable_thinking": false}'` | `--temp 1.0 --top-p 1.0 --top-k 0` |
| Qwen3.5-122B-A10B | なし（thinking有効） | `--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0` |

**注**: Qwen3.5系でthinkingを無効化する場合は `--chat-template-kwargs '{"enable_thinking": false}'` を追加し、サンプリングは `--temp 0.7 --top-p 0.8 --top-k 20 --min-p 0` を使用。

## fitモード（MoE CPUオフロード）

モデルサイズがVRAMを超えるMoEモデル向けのモード。ctx-size引数に `fit` を指定するとMoEエキスパート重みの一部を CPU (RAM) にオフロードし、アテンション・ルーティング層はGPUに残す。

**挙動はモデルプロファイルで自動切替**:

| モデル | OT パターン | fit-ctx default | プロファイル追加設定 |
|--------|------------|----------------|---------------------|
| Qwen3.5-122B-A10B | `blk.N.ffn_.*_exps.weight=CPU` を N ∈ {2,3,20-23,31-38} (14 層) ぶんカンマ連結 (B14b) | **131072 (128k)** | `-b 2048 -ub 512`, `--tensor-split 11,12,13,14`, `--threads 40`, `numactl --cpunodebind=1 --membind=1` |
| その他 MoE | `ffn_.*_exps.weight=CPU` (全層) | 8192 | サーバ共通設定のみ |

> **OT 表現の実装ノート**: 意味的には `blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU` と等価だが、 `ssh ... bash -c '$CMD'` 経由で渡す際に `()` / `|` が bash のメタキャラとして解釈されて syntax error になるため、llama.cpp 側の `parse_tensor_buffer_overrides` がサポートするカンマ列挙表現 (`pat1,pat2,...`) に分解している。各パターンの `.` は std::regex で「任意 1 文字」となるが、対象テンソル名 (`blk.N.ffn_{gate,up,down}_exps.weight`) では誤マッチしない。

### Qwen3.5-122B-A10B プロファイル (Phase U-6 確定、2026-04-24)

- **eval 実測**: 1k=17.69 t/s、32k=14.36、96k=10.03 (baseline B14b_ts_alt 18.664 @ ctx=32k 比 -5.2〜-46.3%)
- **PP 実測**: 1k=64 t/s、32k=61、96k=53 (96k prompt 処理 ~30 分/run)
- **OT=B14b**: CPU offload = layer {2, 3, 20-23, 31-38} の 14 層のみ、残り 34 層は GPU
- **tensor-split=11,12,13,14**: ctx=128k でフィットする唯一の割付 (min_gpu_free=956 MiB)
- **-ub 1024 は禁忌**: 32k 以下では 1k eval 17.96 t/s と最速だが 96k で CUDA OOM crash
- **サーバは t120h-p100 限定**: mi25/t120h-m10 では VRAM 足りず (4×P100=64 GB の層分散前提)

### fitモード起動例

```bash
# Qwen3.5-122B-A10B: 128k default で起動 (プロファイル自動適用)
.claude/skills/llama-server/scripts/start.sh t120h-p100 \
  "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit

# 短 ctx (32k) を明示指定したい場合 (プロファイルは適用される)
.claude/skills/llama-server/scripts/start.sh t120h-p100 \
  "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit 32768

# ヘルスチェック (start.sh と同じ引数)
.claude/skills/llama-server/scripts/wait-ready.sh t120h-p100 \
  "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit
```

## スクリプト実行時の注意

**すべてのスクリプトはプロジェクトルートからの相対パス（`.claude/skills/llama-server/scripts/...`）で実行してください。** フルパス（`/home/ubuntu/projects/llm-server-ops/.claude/skills/...`）で実行すると、Claude Code の承認ダイアログが毎回表示されます。

## 統合スクリプト（推奨）

`llama-up.sh` / `llama-down.sh` は電源制御から llama-server 起動・停止までを 1 コマンドに統合します。日常運用ではこちらを使ってください。個別ステップを制御したい場合のみ、後述の `start.sh` / `wait-ready.sh` / `stop.sh` を使います。

### 起動: llama-up.sh

```bash
.claude/skills/llama-server/scripts/llama-up.sh [server] [hf-model] [mode] [fit-ctx]
```

引数すべて省略可（デフォルト: `t120h-p100` / `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M` / `fit`）。

動作:

1. `power.sh status` で電源状態を確認
2. `Off` なら `power.sh on` → SSH 疎通待ち（5 秒間隔、最大 5 分）
3. `http://<ip>:8000/health` に 200 が返れば既起動扱いで即 `exit 0`（冪等）
4. `start.sh` → `wait-ready.sh`

ロック: 取得しない。必要なら事前に `gpu-server/scripts/lock.sh <server>` を実行してください。

### 停止: llama-down.sh

```bash
.claude/skills/llama-server/scripts/llama-down.sh [server] [--force]
```

`server` 省略時のデフォルトは `t120h-p100`。

動作:

1. `lock-status.sh` でロック保持者を確認
   - **自分保持** → 継続、最後に `unlock`
   - **他者保持** → `exit 1`（`--force` で警告のみ、ただし `unlock` はしない）
   - **未ロック** (`available`) → 警告のみで継続、`unlock` スキップ
   - **UNREACHABLE** → `exit 1`
2. `stop.sh` → 自分保持時のみ `unlock` → `power.sh off`

「自分のロック」判定: session_id が `<hostname>-<pid>-<timestamp>` 形式なので、末尾 2 セグメントを剥がした `hostname` 部分が `$(hostname)` と一致するか比較します（`hostname` が `-` を含むケースに対応）。

`stop.sh` または `power.sh off` が失敗しても警告のみで後続ステップを継続します（電源 OFF すれば結果的にプロセスも止まるため）。

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

1. NVIDIAサーバは `nvtop`、MI25は `watch -n 1 rocm-smi` を使用
2. 既存の ttyd (port 7681) を停止後、サーバ側でバックグラウンド起動
3. ブラウザから `http://<server-ip>:7681` でアクセス可能

### start.sh の動作

1. 既存の llama-server プロセスを確認（起動中なら警告して終了）
2. `server-scripts/update_and_build-<server>.sh` をサーバに転送・実行
3. llama-server をサーバ側でバックグラウンド起動（ログは `/tmp/llama-server.log`）
4. ttyd (port 7682) でログ閲覧UIをバックグラウンド起動
5. ブラウザから `http://<server-ip>:7682` でログを閲覧可能

**注意**: ビルドフェーズ（cmake + make）が120秒以上かかることがあります。Bashツールで実行する場合は `timeout: 300000` を指定するか、`run_in_background` での実行を推奨します。

### wait-ready.sh の動作

1. `/health` エンドポイントでヘルスチェック（通常: 最大150秒、fitモード/大コンテキスト時: 最大300秒ポーリング）
2. 成功時にDiscord通知を送信（GPU監視・サーバログのURLを含む）

**注**: 起動スクリプトはモデル名に基づいてサンプリングパラメータを自動選択します（Qwen3.5系: `--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0`、その他: `--temp 1.0 --top-p 1.0 --top-k 0`）。

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
| t120h-p100 × Qwen3.5-122B-A10B | `--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14 --threads 40` + `numactl --cpunodebind=1 --membind=1` | Phase U-6 確定 128k fit プロファイル |
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
