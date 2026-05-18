# Qwen3.6 4モデル追加: ダウンロード + skill/docs 更新

## Context

ユーザは Qwen3.6 系の 4 モデルを UD-Q4_K_XL 量子化でダウンロードし、本プロジェクトの llama-server skill から利用できるようにしたい。

- `unsloth/Qwen3.6-27B-GGUF`（dense 27B、262k ctx）
- `unsloth/Qwen3.6-35B-A3B-GGUF`（MoE 35B/3B activated、262k ctx）
- `unsloth/Qwen3.6-27B-MTP-GGUF`（27B + MTP ヘッド、speculative decoding 用）
- `unsloth/Qwen3.6-35B-A3B-MTP-GGUF`（35B-A3B + MTP ヘッド）

合計ダウンロードサイズ約 81 GB（27B 17.6 GB + 35B-A3B 22.4 GB + 27B-MTP 17.9 GB + 35B-A3B-MTP 22.9 GB）。t120h-p100 の空き 267 GB なので余裕で収まる。

ユーザ確定方針：
- **サンプリングは Qwen3.5 と同じ** `--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0`（Coding 寄り、precise）
- **MTP は別モデルとして並列登録**（Qwen3.6-27B と Qwen3.6-27B-MTP は別エントリ）

技術発見：
- llama.cpp の MTP サポートは **2026-05-16 マージ**。`--spec-type draft-mtp --spec-draft-n-max 6` が必要（旧名 `--spec-type mtp` から 2026-05-13 リネーム）
- MTP モデルは standalone（draft モデル不要、メインモデルそのものに MTP ヘッドが内包される）
- t120h-p100 の llama.cpp は Marathon ベンチ時点で HEAD ベース（メモリ参照、HEAD 1348f67c5）。MTP マージ後の HEAD を再 pull すれば使える

## 作業手順

### Step 1: ダウンロード（t120h-p100）

ロック取得（GPU 占有しないが安全側）：

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

4 モデルの UD-Q4_K_XL のみダウンロード（既存パターン `--include '*${HF_QUANT}*.gguf'` を踏襲、ssh で順次実行）。並列にすると HF 側のレート制限・帯域競合があるので**逐次**実行。

```bash
HF_TOKEN=<from .env>
for REPO in unsloth/Qwen3.6-27B-GGUF \
            unsloth/Qwen3.6-35B-A3B-GGUF \
            unsloth/Qwen3.6-27B-MTP-GGUF \
            unsloth/Qwen3.6-35B-A3B-MTP-GGUF; do
  ssh t120h-p100 "/home/llm/.local/bin/hf download '$REPO' \
    --include '*UD-Q4_K_XL*.gguf' --token \$HF_TOKEN"
done
```

`.env` から HF_TOKEN を読む、もしくは start.sh の対話セットアップを参考。

進捗監視は既存 `monitor-download.sh` が使える（HFモデル名から自動でファイル glob 生成）。tmux 上ペインで：

```bash
tmux split-window -v -b -d -l 3 \
  .claude/skills/llama-server/scripts/monitor-download.sh \
    t120h-p100 "unsloth/Qwen3.6-35B-A3B-MTP-GGUF:UD-Q4_K_XL"
```

完了確認：

```bash
ssh t120h-p100 "ls -lh ~/.cache/huggingface/hub/models--unsloth--Qwen3.6-*/snapshots/*/Qwen3.6-*-UD-Q4_K_XL*.gguf"
ssh t120h-p100 "df -h /"   # 空き 200 GB 程度を期待
```

ダウンロード後にロック解放：

```bash
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### Step 2: `.claude/skills/llama-server/scripts/start.sh` 編集

#### 2-1. サンプリング自動選択パターンを Qwen3.6 まで拡張

start.sh:197-204
```bash
case "$HF_MODEL" in
  *Qwen3.5*)
    SAMPLING_OPTS="--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0"
    ;;
```
→
```bash
case "$HF_MODEL" in
  *Qwen3.5*|*Qwen3.6*)
    SAMPLING_OPTS="--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0"
    ;;
```

#### 2-2. MTP モデル検出 → spec フラグ自動付与

`--- モデル別サンプリングパラメータ ---` セクション直後（行 ~205）に追加：

```bash
# --- MTP (Multi-Token Prediction) 自動検出 ---
# llama.cpp 2026-05-16 マージ機能。リポジトリ名に "MTP" を含むモデルで自動有効化。
SPEC_OPTS=""
case "$HF_MODEL" in
  *MTP*)
    SPEC_OPTS="--spec-type draft-mtp --spec-draft-n-max 6"
    ;;
esac
```

そして `LAUNCH_CMD` 組み立て部（行 268-275）の引数に `$SPEC_OPTS` を追加：

```bash
LAUNCH_CMD="${ENV_PREFIX:+$ENV_PREFIX }./build/bin/llama-server \
  $MODEL_OPT \
  $CHAT_TEMPLATE_OPTS $NGL_OPTS \
  $SERVER_OPTS --n-predict 32768 $THREADS_OPT \
  $CTX_OPTS --parallel 1 --cache-type-k q8_0 --cache-type-v q8_0 \
  --defrag-thold 0.1 $SAMPLING_OPTS $SPEC_OPTS \
  --port 8000 --host 0.0.0.0 \
  --alias '$ALIAS'"
```

### Step 3: `.claude/skills/llama-server/scripts/wait-ready.sh` 編集

サンプリング自動選択を同じパターンに拡張（行 55-63 周辺）：

```bash
case "$HF_MODEL" in
  *Qwen3.5*|*Qwen3.6*)
    SAMPLING_OPTS="--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0"
    ;;
```

fit-ctx default は Qwen3.6 では当面 fit モード使う予定がない（VRAM 内に余裕で収まる）ため、`*Qwen3.5-122B-A10B*` のみ 131072 default の挙動を維持（変更不要）。

### Step 4: `.claude/skills/llama-server/SKILL.md` 編集

#### 4-1. モデル選択ダイアログ（行 14-21）に 4 行追加

既存 4 モデルの後に：

```
5. unsloth/Qwen3.6-27B-GGUF:UD-Q4_K_XL — dense 27B、262k ctx、thinking対応
6. unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL — MoE 35B/3B、262k ctx、thinking対応
7. unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL — Qwen3.6-27B + MTP（speculative decoding、~1.5-2x高速）
8. unsloth/Qwen3.6-35B-A3B-MTP-GGUF:UD-Q4_K_XL — Qwen3.6-35B-A3B + MTP
```

#### 4-2. モデル一覧テーブル（行 25-30）に 4 行追加

```markdown
| `unsloth/Qwen3.6-27B-GGUF:UD-Q4_K_XL` | 131072 | t120h-p100, mi25 | dense 27B、UD最適4bit |
| `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` | 131072 | t120h-p100, mi25 | thinking対応MoE、UD最適4bit |
| `unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL` | 131072 | t120h-p100 | MTP有効、`--spec-type draft-mtp` 自動適用 |
| `unsloth/Qwen3.6-35B-A3B-MTP-GGUF:UD-Q4_K_XL` | 131072 | t120h-p100 | MoE+MTP、`--spec-type draft-mtp` 自動適用 |
```

#### 4-3. サンプリングパラメータテーブル（行 32-41）に 4 行追加

```markdown
| Qwen3.6-27B / 27B-MTP | なし（thinking有効） | `--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0` |
| Qwen3.6-35B-A3B / 35B-A3B-MTP | なし（thinking有効） | `--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0` |
```

#### 4-4. 新セクション「MTP（Multi-Token Prediction）モデル」を追加

`### Qwen3.5-122B-A10B プロファイル (Phase U-6 確定、2026-04-24)` の後に挿入。内容：

- MTP とは speculative decoding の self-speculative 版（~1.5-2x 高速）
- llama.cpp 2026-05-16 マージ。HEAD ビルドが必要
- standalone モデル（draft 不要）
- `start.sh` がモデル名に `MTP` を含むことを検出し `--spec-type draft-mtp --spec-draft-n-max 6` を自動付与
- 起動例：
  ```bash
  .claude/skills/llama-server/scripts/llama-up.sh t120h-p100 \
    "unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL" 131072
  ```

### Step 5: README.md 編集（軽微）

現状クイックスタートは Qwen3.5-122B-A10B デフォルト。Qwen3.6 系も同様に動くことを示すため、起動例セクションに 1 行追加：

```bash
# Qwen3.6-27B (MTP) を起動
.claude/skills/llama-server/scripts/llama-up.sh t120h-p100 \
  "unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL" 131072
```

`llama-up.sh` のデフォルトモデル（行 31 `HF_MODEL="${2:-unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M}"`）は **変更しない**（Marathon ベンチ用の現役モデル）。

## 検証手順

各ステップの検証：

1. **ダウンロード完了確認**
   ```bash
   ssh t120h-p100 "find ~/.cache/huggingface/hub -name '*UD-Q4_K_XL*.gguf' -not -name '*.incomplete' | xargs ls -lh"
   ssh t120h-p100 "df -h /"  # 使用率 49% → 65% 程度
   ```

2. **start.sh の編集差分確認**
   ```bash
   git diff .claude/skills/llama-server/scripts/start.sh
   git diff .claude/skills/llama-server/scripts/wait-ready.sh
   ```
   - サンプリングの case 文に `*Qwen3.6*` が入っていること
   - `SPEC_OPTS` が定義され `LAUNCH_CMD` に含まれていること

3. **non-MTP モデル起動テスト**（Qwen3.6-27B）
   ```bash
   .claude/skills/gpu-server/scripts/lock.sh t120h-p100
   .claude/skills/llama-server/scripts/llama-up.sh t120h-p100 \
     "unsloth/Qwen3.6-27B-GGUF:UD-Q4_K_XL" 131072
   # /health が 200 を返すまで wait-ready が成功
   curl http://10.1.4.14:8000/v1/models  # alias 確認
   ssh t120h-p100 "tail -50 /tmp/llama-server.log"  # サンプリング値確認
   ```

4. **MTP モデル起動テスト**（Qwen3.6-27B-MTP）
   ```bash
   .claude/skills/llama-server/scripts/llama-down.sh t120h-p100
   .claude/skills/llama-server/scripts/llama-up.sh t120h-p100 \
     "unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL" 131072
   ssh t120h-p100 "ps aux | grep llama-server | grep -v grep"
   # コマンドラインに `--spec-type draft-mtp --spec-draft-n-max 6` が含まれていること
   ```

5. **簡単な推論テスト**
   ```bash
   curl -s http://10.1.4.14:8000/v1/chat/completions \
     -H 'Content-Type: application/json' \
     -d '{"model":"unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL",
          "messages":[{"role":"user","content":"2+2=?"}],
          "max_tokens":50}'
   ```

6. **後片付け**
   ```bash
   .claude/skills/llama-server/scripts/llama-down.sh t120h-p100
   # llama-down がロック解放まで実施
   ```

## 修正対象ファイル一覧

| ファイル | 主な変更点 |
|---------|----------|
| `.claude/skills/llama-server/scripts/start.sh` | `*Qwen3.5*\|*Qwen3.6*` への拡張 + `SPEC_OPTS` 新規 + `LAUNCH_CMD` への組込 |
| `.claude/skills/llama-server/scripts/wait-ready.sh` | サンプリング case 文の拡張 |
| `.claude/skills/llama-server/SKILL.md` | モデル一覧 / サンプリング表 / MTP セクション追加 |
| `README.md` | Qwen3.6 起動例 1 行追加（軽微） |

`llama-up.sh` / `llama-down.sh` / `monitor-download.sh` / `install-global.sh` / `server-scripts/*` は **変更不要**。既存のモデル名汎用扱いと `--include` ベースのキャッシュ管理がそのまま使える。

## 確認済みの非変更項目

- llama-up.sh のデフォルトモデル: Qwen3.5-122B-A10B のまま（Marathon 現役）
- fit モード default: Qwen3.5-122B-A10B 限定の 131072 挙動はそのまま
- gpu-server skill / power.sh / ttyd-gpu.sh: 変更不要
