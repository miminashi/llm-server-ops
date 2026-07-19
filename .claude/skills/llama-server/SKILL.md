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

1. unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL — **推奨/デフォルト**、MoE 35B/3B activated、131072 ctx、thinking対応、opencode実ワークロードベンチ最良（judge 4.44、eval 12 t/s）
2. unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M — thinking対応、128k ctx
3. unsloth/gpt-oss-20b-GGUF:Q8_0 — 汎用、64k ctx
4. bartowski/browser-use_bu-30b-a3b-preview-GGUF:Q8_0 — browser-use専用、24k ctx
5. unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M — 大規模MoE、fitモード（128k ctx、B14b OT、eval 10-17.7 t/s）
6. unsloth/Qwen3.6-27B-GGUF:UD-Q4_K_XL — dense 27B、262k native ctx、thinking対応（P100×4 では 131072 ctx で OOM、65536 推奨）
7. unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL — Qwen3.6-27B + MTP（speculative decoding、~1.5-2x高速）
8. unsloth/Qwen3.6-35B-A3B-MTP-GGUF:UD-Q4_K_XL — Qwen3.6-35B-A3B + MTP（tool-heavyワークロードではMTP無効化が多く非MTP推奨）
```

## モデル一覧

| HFモデル名 | 推奨ctx-size | 推奨サーバ | 備考 |
|-----------|-------------|-----------|------|
| `unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M` | 131072 | t120h-p100, mi25 | thinking対応MoEモデル |
| `unsloth/gpt-oss-20b-GGUF:Q8_0` | 65536 | t120h-p100, mi25 | thinking無効化推奨 |
| `bartowski/browser-use_bu-30b-a3b-preview-GGUF:Q8_0` | 24576 | t120h-p100 | browser-use専用 |
| `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M` | fit (128k default) | t120h-p100 | 大規模MoE、Phase U-6 確定プロファイル自動適用 |
| `unsloth/Qwen3.6-27B-GGUF:UD-Q4_K_XL` | 131072 | t120h-p100, mi25 | dense 27B、UD最適4bit |
| `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` | 131072 | t120h-p100, mi25 | thinking対応MoE、UD最適4bit |
| `unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL` | 131072 | t120h-p100 | MTP有効、`--spec-type draft-mtp` 自動適用 |
| `unsloth/Qwen3.6-35B-A3B-MTP-GGUF:UD-Q4_K_XL` | 131072 | t120h-p100 | MoE+MTP、`--spec-type draft-mtp` 自動適用 |

### モデル別サンプリングパラメータ

| モデル | chat-template-kwargs | サンプリング |
|--------|---------------------|-------------|
| Qwen3.5-35B-A3B | なし（thinking有効） | Qwen3.x 共通プロファイル（下記参照） |
| gpt-oss-20b | `'{"enable_thinking": false}'` | `--temp 1.0 --top-p 1.0 --top-k 0` |
| bu-30b-a3b-preview | `'{"enable_thinking": false}'` | `--temp 1.0 --top-p 1.0 --top-k 0` |
| Qwen3.5-122B-A10B | なし（thinking有効） | Qwen3.x 共通プロファイル（下記参照） |
| Qwen3.6-27B / 27B-MTP | なし（thinking有効） | Qwen3.x 共通プロファイル（下記参照） |
| Qwen3.6-35B-A3B / 35B-A3B-MTP | なし（thinking有効） | Qwen3.x 共通プロファイル（下記参照） |

**Qwen3.x 共通サンプリングプロファイル**:

```
--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0
--presence-penalty 1.0
--dry-multiplier 0
```

**注**: Qwen3.5系でthinkingを無効化する場合は `--chat-template-kwargs '{"enable_thinking": false}'` を追加し、サンプリングは `--temp 0.7 --top-p 0.8 --top-k 20 --min-p 0` を使用。

**反復対策パラメータについて**: Qwen3.x thinking モードは opencode 等の長コンテキストで段落単位の verbatim ループに陥ることがあるため、Qwen 公式推奨レンジ (0〜2) の `presence_penalty` を **1.0** でデフォルト有効化している。DRY サンプラはサーバ default では **無効** (`--dry-multiplier 0`、llama.cpp default 値と同じ) — DRY は long path / 識別子末尾を切り落とす副作用が greedy decoding でも観測されたため、必要なクライアントだけがリクエスト JSON で `dry_multiplier` を送れるようにしている（llama.cpp の OpenAI 互換 API 拡張）。

**チューニング履歴**:

- **`fed12136`** (2026-05-25): thinking 段落 verbatim ループ抑制のため `--presence-penalty 1.0 --dry-multiplier 0.8` を default 有効化。
- **2026-05-26 #1**: URL/IP の数字書換副作用 (`10.1.6.5:8001` → `10.1.4.13` 等) に対応して `--dry-allowed-length 4` + `--dry-sequence-breaker . / _` を追加。**当時は気付かなかったが llama.cpp 最新版で `--dry-sequence-breaker` を複数回指定すると最後の値のみ有効** (deprecation 警告)、実質 `_` だけが効いていた。
- **2026-05-26 #2**: ハイフン含み長パス (`rails-upgrade-to-8.1.0`) を tool-call で再現できない問題に対応して `presence-penalty 1.0 → 0.5` 緩和、breakers をカンマ区切りで `.,/,_,-` に集約。しかし greedy decoding でも path 末尾 (`.1.0/config/...` 等) が切れる症状が残った。
- **2026-05-26 #3**: `dry_multiplier=0` をリクエスト側で送ると path が完全再現できることを確認、DRY サーバ default を **完全無効化** (`--dry-multiplier 0`)。thinking ループ抑制は `presence_penalty 0.5` 単独で対応。
- **2026-05-26 #4** (現行): ytdlor セッションで Active Storage 文脈の段落 verbatim ループ再発 (同一段落 10 回以上反復) を観測。`presence_penalty=0.5` 単独では数百〜数千トークン規模の長距離段落反復に抑制不足と判断し、`presence_penalty` を **1.0** へ引き上げ。`fed12136` 時の URL 副作用は DRY=0.8 が原因 (greedy decoding で再現済) であり、`presence_penalty` 単独 1.0 では URL/path リグレッションは観測されない。それでも再発する場合は、クライアント側で `dry_multiplier=0.4` 程度を送る運用に切り替える。

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

## MTP（Multi-Token Prediction）モデル

MTP は self-speculative decoding を可能にする機能で、メインモデル自体に MTP ヘッドが含まれているため draft モデル不要。eval 速度が ~1.5-2x 向上（モデル/タスク依存）。

**前提条件**:
- llama.cpp の MTP サポートは **2026-05-16 mainline マージ**（HEAD ビルドが必要）。
- `--spec-type draft-mtp` フラグは旧 `--spec-type mtp` から 2026-05-13 にリネームされた。HEAD が古い場合は `update_and_build-*.sh` 経由で再ビルド。

**自動適用**:
`start.sh` がモデル名に `MTP` を含むことを検出すると、以下のフラグを自動付与する:

```
--spec-type draft-mtp --spec-draft-n-max 6
```

**起動例**:

```bash
# llama-up 経由 (推奨)
.claude/skills/llama-server/scripts/llama-up.sh t120h-p100 \
  "unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL" 131072

# Qwen3.6-35B-A3B-MTP の場合
.claude/skills/llama-server/scripts/llama-up.sh t120h-p100 \
  "unsloth/Qwen3.6-35B-A3B-MTP-GGUF:UD-Q4_K_XL" 131072
```

**確認**:
```bash
ssh t120h-p100 "ps aux | grep llama-server | grep -v grep | grep -o 'spec-type [^ ]*'"
# → spec-type draft-mtp
```

## スクリプト実行時の注意

**すべてのスクリプトはプロジェクトルートからの相対パス（`.claude/skills/llama-server/scripts/...`）で実行してください。** フルパス（`/home/ubuntu/projects/llm-server-ops/.claude/skills/...`）で実行すると、Claude Code の承認ダイアログが毎回表示されます。

## 統合スクリプト（推奨）

`llama-up.sh` / `llama-down.sh` は電源制御から llama-server 起動・停止までを 1 コマンドに統合します。日常運用ではこちらを使ってください。個別ステップを制御したい場合のみ、後述の `start.sh` / `wait-ready.sh` / `stop.sh` を使います。

### 起動: llama-up.sh

```bash
.claude/skills/llama-server/scripts/llama-up.sh [server] [hf-model] [mode] [fit-ctx]
```

引数すべて省略可（デフォルト: `t120h-p100` / `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` / `131072`）。

**mi25 / t120h-p100 両対応**: 電源制御は `power-ctl.sh`（gpu-server）経由で行い、サーバ種別（Supermicro/IPMI か HPE/iLO5 か）を自動判別する。mi25（IPMI）でも統合スクリプトで起動・停止できる。

動作:

1. `power-ctl.sh status` で電源状態を確認（出力は `On`/`Off` に正規化）
2. `Off` なら `power-ctl.sh on` → SSH 疎通待ち（5 秒間隔、最大 5 分）
3. `http://<ip>:8000/health` に 200 が返れば既起動扱い → **`ttyd-up.sh` で ttyd (7681/7682) を担保してから** `exit 0`（冪等。既起動時も監視UIが落ちていれば立て直す）
4. `start.sh` → `wait-ready.sh`（`start.sh` 内で `ttyd-up.sh` を呼ぶ）

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
2. `stop.sh` → 自分保持時のみ `unlock` → `power-ctl.sh off`（グレースフル。HPE=Redfish GracefulShutdown / Supermicro=ACPI soft）

「自分のロック」判定: session_id が `<hostname>-<pid>-<timestamp>` 形式なので、末尾 2 セグメントを剥がした `hostname` 部分が `$(hostname)` と一致するか比較します（`hostname` が `-` を含むケースに対応）。

`stop.sh` または `power-ctl.sh off` が失敗しても警告のみで後続ステップを継続します（電源 OFF すれば結果的にプロセスも止まるため）。

## start.sh + wait-ready.sh の使い方

llama-server の起動は2ステップで行います（ttyd は `start.sh` が内部で `ttyd-up.sh` を呼んで自動起動するため、ttyd を手動で立てる必要はありません）:

1. **`start.sh`** — ビルド・llama-server をサーバ側でバックグラウンド起動し、**`ttyd-up.sh` で ttyd (7681 GPU監視 / 7682 ログ閲覧) を起動・LISTEN検証**
2. **`wait-ready.sh`** — ヘルスチェック・Discord通知

### 例

```bash
# 1. ビルド＋llama-server起動（ttyd 7681/7682 も自動起動）
.claude/skills/llama-server/scripts/start.sh t120h-p100 \
  "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M" 131072

# 2. ヘルスチェック＋Discord通知
.claude/skills/llama-server/scripts/wait-ready.sh t120h-p100 \
  "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M" 131072
```

**注**: `start.sh` はサーバ側でバックグラウンド起動するため即座に完了します。`run_in_background` は不要です。

### ttyd-up.sh の動作（ttyd 起動の単一の真実源）

**前提**: サーバ側に `ttyd` バイナリが導入されていること (Ubuntu なら `sudo apt install ttyd`)。未導入の場合、`ttyd-up.sh` は silent fail する (LISTEN 検証は WARNING を出すが常に exit 0)。導入確認: `ssh <server> "command -v ttyd"`。

```bash
.claude/skills/llama-server/scripts/ttyd-up.sh <server>
```

1. 既存の ttyd (7681/7682) と nvtop を停止し、ポート解放を待つ（冪等）
2. `/tmp/llama-server.log` を `touch`（未起動時に 7682 の `tail -f` が即終了するのを防ぐ）
3. ttyd を起動: 7681 = GPU監視（NVIDIA は `nvtop`、MI25 は `watch -n 1 rocm-smi`）、7682 = ログ閲覧
   - GPU監視は `bash -c 'TERM=xterm-256color exec ...'` でラップ（TERM 未設定だと nvtop/watch が `Error opening terminal: unknown.` で即終了するため）
4. 両ポートの LISTEN を検証。落ちていれば WARNING を出すが、ttyd は監視用途なので **常に exit 0**（本体起動は止めない）
5. ブラウザから `http://<server-ip>:7681`（GPU監視）/ `:7682`（ログ閲覧）でアクセス可能

**`ttyd-gpu.sh`** は後方互換のため残しているが、中身は `ttyd-up.sh` への薄いラッパー。監視UIだけ立て直したい場合は `ttyd-up.sh <server>`（または `ttyd-gpu.sh <server>`）を単独実行すればよい（llama-server 起動中でも安全・ロック不要）。

### start.sh の動作

1. 既存の llama-server プロセスを確認（起動中なら警告して終了）
2. `server-scripts/update_and_build-<server>.sh` をサーバに転送・実行
3. llama-server をサーバ側でバックグラウンド起動（ログは `/tmp/llama-server.log`）
4. **`ttyd-up.sh` を呼び、ttyd (7681/7682) を起動・LISTEN検証**
5. ブラウザから `http://<server-ip>:7682`（ログ）/ `:7681`（GPU監視）でアクセス可能

**注意**: ビルドフェーズ（cmake + make）が120秒以上かかることがあります。Bashツールで実行する場合は `timeout: 300000` を指定するか、`run_in_background` での実行を推奨します。

### wait-ready.sh の動作

1. `/health` エンドポイントでヘルスチェック（通常: 最大150秒、fitモード/大コンテキスト時: 最大300秒ポーリング）
2. 通知前に 7681/7682 の LISTEN を `ss` で確認し、落ちているポートは通知本文に「(未起動)」と明記（ここでは ttyd の再起動はしない）
3. 成功時にDiscord通知を送信（GPU監視・サーバログのURLを含む）

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
| mi25 (ROCm/hip, 既定) | `--flash-attn 1 --poll 0 -b 2048 -ub 2048` | gfx900 では ub=2048 が速度・VRAM 両面の最適点。ub=4096 は GPU0 が 16GiB を超え OOM（ub を上げると遅くもなる）。`--flash-attn 1` を明示し auto 挙動に依存しない。`start.sh` が自動適用 |
| mi25 (Vulkan/RADV, `MI25_BACKEND=vulkan`) | `--flash-attn 1 --poll 0 -b 2048 -ub 2048`（同値）／ `GGML_VK_VISIBLE_DEVICES` は**起動時に vulkaninfo で RADV 物理 GPU を自動検出**（llvmpipe 除外、実効3枚→`0,1,2`/4枚→`0,1,2,3`） | Vulkan は ub が VRAM/速度にほぼ無影響（ub=4096 でも OOM せず）だが ROCm と同値を踏襲。prompt は ROCm の約3.3倍・eval は約0.6倍。FA=0+q8_0 不可、本番は KV q8_0 固定。詳細は下記「mi25 のバックエンド切替」 |
| t120h-p100 | `--flash-attn 1 --poll 0 -b 4096 -ub 4096` | Flash Attention有効、マルチGPUポーリング無効。**`-ub 8192` は CUDA OOM**（下記参照） |
| t120h-p100 × Qwen3.5-122B-A10B | `--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14 --threads 40` + `numactl --cpunodebind=1 --membind=1` | Phase U-6 確定 128k fit プロファイル |
| t120h-m10 | `CUDA_VISIBLE_DEVICES=0..14 -b 4096 -ub 4096` | GPU 15は使用不可 |

### mi25 のバックエンド切替（ROCm / Vulkan）

mi25 は2つのバックエンドを持つ。**既定は ROCm（hip）**。環境変数 `MI25_BACKEND=vulkan` を付けると Vulkan（RADV）に切り替わる（`start.sh` が `build-vulkan/bin` を使用）。

```bash
# ROCm（既定）
.claude/skills/llama-server/scripts/start.sh mi25 "<model>" 131072
# Vulkan
MI25_BACKEND=vulkan .claude/skills/llama-server/scripts/start.sh mi25 "<model>" 131072
```

- **ROCm**: `update_and_build-mi25.sh` で gfx900 ビルド可能コミットに **pin**（master は `__hip_fp8_e4m3` を gfx900 で参照しビルド不能）。起動パラメータは上表のとおり ub=2048 が最適。
- **Vulkan**: `build-vulkan/` を使用、**pin 不要（master 追従）**。ub は VRAM/速度にほぼ無影響だが ROCm と同値（ub=2048）を踏襲。**prompt は ROCm の約3.3倍・eval は約0.6倍**。KV は **q8_0 固定**（f16 は高負荷でホスト不安定、`FA=0`+q8_0 は不可）。
- **Vulkan の GPU 可視性（自動検出）**: `start.sh` は**起動前に `vulkaninfo --summary` で RADV 物理 GPU の index のみを検出**し（`deviceType=PHYSICAL_DEVICE_TYPE_CPU` の llvmpipe/lavapipe を除外）、`GGML_VK_VISIBLE_DEVICES` に設定する（実効3枚→`0,1,2`／4枚→`0,1,2,3`）。mi25 は SLOT4 等の PCIe 物理層障害で**実効枚数が間欠的に変動**する（[原因究明レポート](../../../report/2026-06-14_131713_mi25_gpu4_pcie_dropout.md)）ため、旧来の固定値 `0,1,2,3` は3枚構成時に index 3 の llvmpipe(CPU) を拾い `ErrorOutOfDeviceMemory` で破綻していた（[param sweep レポート](../../../report/2026-06-18_084557_mi25_vulkan_param_sweep.md)）。検出した index は vulkaninfo の `GPUn` 順 = ggml-vulkan の `Vulkann` 順と一致する（`--list-devices` で確認済み・ICD 列挙順に依存するためドライバ更新時は要再確認）。vulkaninfo が使えない等で検出に失敗した場合は `GGML_VK_VISIBLE_DEVICES` を**未設定**で起動し警告する（現行 master の ggml は未設定時に llvmpipe を自動除外する）。
- **GPU 枚数チェック**: `start.sh` は起動時に実効 GPU 枚数（mi25 Vulkan=RADV 検出数／mi25 ROCm=`rocminfo` の gfx900 Agent 数／t120h-p100=`nvidia-smi` 枚数）が**期待枚数（mi25=4／p100=4）を下回ると stderr に警告**を出す。ただし**起動は中断しない**（実効枚数で VRAM が足りなければモデルロード時に llama-server 自体が失敗するため、それに委ねる）。ROCm/CUDA は可視性を触らず（auto で実効枚数のみ使用）、警告のみ。

### 既知の問題: llama.cpp `-ub 8192` の CUDA OOM (2026-06-02 master リグレッション)

- **症状**: t120h-p100 で Qwen3.6-35B-A3B / ctx=131072 / KV q8_0 を `-ub 8192` で起動すると、
  モデルロードと初回の小リクエストは成功するが、**2回目以降の大きめリクエストで CUDA out of
  memory・クラッシュ**（`/health` が 000 に）。ログ: `ggml_cuda_pool_vmm::alloc` →
  `cuMemCreate(&handle, reserve_size, …)`、`current device: 0`。直前に context checkpoint の
  `forcing full prompt re-processing` / `erased invalidated context checkpoint` 警告。
- **原因**: 2026-06-02 頃の llama.cpp master で **1 ubatch あたりの compute buffer 確保が約2倍に増加**。
  `-ub 8192` だとロード時点で VRAM 15.3/16 GiB（空き ~0.6 GiB）まで埋まり、大リクエスト時の
  VMM プール成長分が device 0 の僅かな空きを超えて OOM。`af6528e6d`(2026-06-01) では同 `-ub 8192`
  でも ~10 GiB だった（リグレッション）。context checkpoint 自体は原因ではない（host RAM 保存、
  `--ctx-checkpoints 0` でも OOM は解消しない）。
- **対策**: **`-ub 4096`**（`start.sh` の t120h-p100 default 済み）。ロード時 VRAM 10.6 GiB
  （空き ~5.4 GiB）に下がり OOM 解消。eval ~39 t/s 維持、context checkpoint も有効のまま
  （同一プレフィクスの再リクエストは ~3倍高速）。prompt processing は ub=8192 比で ~30% 低下
  （pp 693→489 t/s 相当）するが、ctx=131072 と eval 速度は維持。
- **注意**: 上流が compute buffer 確保を元に戻せば `-ub 8192` へ戻して pp 速度を回復できる。
  検証は report/2026-06-03_*_llama_cpp_oom_regression_fix.md 参照。

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
