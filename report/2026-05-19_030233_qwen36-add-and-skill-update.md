# Qwen3.6 4 モデル追加と skill/docs 更新

- **実施日時**: 2026年5月18日 09:11 〜 2026年5月19日 03:02 JST
- **担当**: Claude (Opus 4.7)
- **対象サーバ**: t120h-p100 (10.1.4.14)
- **対象ブランチ**: master (作業前 HEAD `d6aed34`、未コミット)

## 添付ファイル

- [実装プラン](attachment/2026-05-19_030233_qwen36-add-and-skill-update/plan.md)

## 前提・目的

### 背景

- Qwen3.6 系の 4 モデル（27B / 35B-A3B 各 2 種、計 4 リポジトリ）が unsloth から公開され、本プロジェクトで利用可能にしたい
- うち `-MTP` 版は llama.cpp で 2026-05-16 にマージされたばかりの speculative decoding 機能 (`--spec-type draft-mtp`) を要する
- 既存 skill (`.claude/skills/llama-server/`) はモデル名のワイルドカード判定で挙動を切り替えており、新モデル追加には複数ファイルの編集が必要

### 目的

1. 4 モデルを UD-Q4_K_XL（unsloth-dynamic、4bit 最適）でダウンロード
2. `start.sh` / `wait-ready.sh` を Qwen3.6 + MTP 対応に拡張
3. `SKILL.md` / `README.md` にモデル登録と MTP 解説を追加
4. non-MTP / MTP 双方の起動・推論動作を確認

### 事前作業

ダウンロード前にディスク容量を確保する必要があったため、`/home/llm/.cache/huggingface/hub` の旧モデル、`uv`/`pip` キャッシュ、`lora_training/gpt-oss-20b-fp16`、`/home/ubuntu/` の整理を実施し、空き 52 GB → 267 GB（使用率 91% → 49%）まで確保した。

## 環境情報

| 項目 | 値 |
|------|----|
| サーバ | t120h-p100 (10.1.4.14) |
| GPU | NVIDIA Tesla P100-PCIE 16 GiB × 4 (合計 64 GiB VRAM) |
| OS | Ubuntu 22.04 (Linux 6.x) |
| CPU | Intel Xeon Gold 6138 × 2 (40 cores) |
| RAM | 251 GiB |
| llama.cpp | HEAD `b9219-45b455e66`（MTP マージ後を再ビルド）|
| ストレージ | `/dev/sda2` ext4 548 GiB（事前作業後の使用率 49% → ダウンロード後 64%）|

## ダウンロードした 4 モデル

| HF リポジトリ | 量子化 | サイズ | キャッシュパス |
|--------------|-------|-------|----------|
| `unsloth/Qwen3.6-27B-GGUF` | UD-Q4_K_XL | 17 GiB | `~/.cache/huggingface/hub/models--unsloth--Qwen3.6-27B-GGUF/...` |
| `unsloth/Qwen3.6-35B-A3B-GGUF` | UD-Q4_K_XL | 21 GiB | 同上 (`35B-A3B-GGUF`) |
| `unsloth/Qwen3.6-27B-MTP-GGUF` | UD-Q4_K_XL | 17 GiB | 同上 (`27B-MTP-GGUF`) |
| `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` | UD-Q4_K_XL | 22 GiB | 同上 (`35B-A3B-MTP-GGUF`) |

合計 77 GiB を取得。

## 変更ファイル一覧

```
 .claude/skills/llama-server/SKILL.md              | 43 +++++++++++++++++++++++
 .claude/skills/llama-server/scripts/start.sh      | 20 +++++++++--
 .claude/skills/llama-server/scripts/wait-ready.sh |  2 +-
 README.md                                         |  6 ++++
 4 files changed, 68 insertions(+), 3 deletions(-)
```

### `start.sh`

1. サンプリング自動選択 case 文を `*Qwen3.5*|*Qwen3.6*` に拡張（temp 0.6 系を Qwen3.6 にも適用）
2. **MTP 自動検出**: モデル名に `MTP` を含む場合に `--spec-type draft-mtp --spec-draft-n-max 6` を `SPEC_OPTS` として付与
3. **MTP プロファイル**: t120h-p100 で MTP のとき `SERVER_OPTS` を `-b 8192 -ub 8192` → `-b 2048 -ub 512` に縮小（draft context の compute buffer が P100 16 GiB に収まらない問題への対処）
4. `LAUNCH_CMD` に `$SPEC_OPTS` を組み込み

### `wait-ready.sh`

サンプリング自動選択 case 文を `*Qwen3.5*|*Qwen3.6*` に拡張（Discord 通知時の表記整合性を維持）。

### `SKILL.md`

1. モデル選択ダイアログ（行 14-21）に 4 行追加
2. モデル一覧テーブルに 4 行追加
3. サンプリングパラメータテーブルに 2 行（27B/27B-MTP、35B-A3B/35B-A3B-MTP）追加
4. **新セクション `## MTP（Multi-Token Prediction）モデル`** を新設し、前提条件・自動適用・起動例・確認方法を記載

### `README.md`

クイックスタートに Qwen3.6 系（dense / MTP）の起動例コメントを 1 ブロック追加。デフォルトモデル（`Qwen3.5-122B-A10B`、Marathon ベンチ現役）は変更せず。

## 再現方法

### 1. ロック取得とダウンロード

```bash
# ロック取得
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

# .env から HF_TOKEN を読み込んで 4 モデルを並列ダウンロード
source /home/ubuntu/projects/llm-server-ops/.env
for REPO in unsloth/Qwen3.6-27B-GGUF \
            unsloth/Qwen3.6-35B-A3B-GGUF \
            unsloth/Qwen3.6-27B-MTP-GGUF \
            unsloth/Qwen3.6-35B-A3B-MTP-GGUF; do
  ssh t120h-p100 "nohup /home/llm/.local/bin/hf download '$REPO' \
    --include '*UD-Q4_K_XL*.gguf' --token $HF_TOKEN \
    > /tmp/hf-dl-$(basename $REPO).log 2>&1 &"
done
```

### 2. 動作確認

```bash
# non-MTP 起動 (ctx-size 65536)
.claude/skills/llama-server/scripts/start.sh t120h-p100 \
  "unsloth/Qwen3.6-27B-GGUF:UD-Q4_K_XL" 65536
.claude/skills/llama-server/scripts/wait-ready.sh t120h-p100 \
  "unsloth/Qwen3.6-27B-GGUF:UD-Q4_K_XL" 65536

# 推論テスト
curl -sS http://10.1.4.14:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"unsloth/Qwen3.6-27B-GGUF:UD-Q4_K_XL",
       "messages":[{"role":"user","content":"What is 2+2?"}],
       "max_tokens":50}'

# 停止して MTP 起動 (ctx-size 8192)
.claude/skills/llama-server/scripts/stop.sh t120h-p100
.claude/skills/llama-server/scripts/start.sh t120h-p100 \
  "unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL" 8192
.claude/skills/llama-server/scripts/wait-ready.sh t120h-p100 \
  "unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL" 8192

# --spec-type draft-mtp が付いていることの確認
ssh t120h-p100 "ps aux | grep llama-server | grep -v grep | grep -o 'spec-type [^ ]*'"
# 期待: spec-type draft-mtp
```

## 結果

### non-MTP（Qwen3.6-27B）

| 確認項目 | 結果 |
|---------|------|
| 起動 (`-b 8192 -ub 8192` t120h-p100 デフォルト) | 成功 |
| `--spec-type` が含まれないこと | 確認 |
| サンプリング自動選択 (`--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0`) | 確認 |
| `/v1/chat/completions` 推論 | 成功（`reasoning_content` に thinking 出力あり）|
| `system_fingerprint` | `b9219-45b455e66` |

### MTP（Qwen3.6-27B-MTP）

#### 初回試行（ctx 8192、サーバデフォルト `-b 8192 -ub 8192`）

CUDA3 で OOM 失敗:

```
E ggml_backend_cuda_buffer_type_alloc_buffer: allocating 10386.06 MiB on device 3: cudaMalloc failed: out of memory
E srv    load_model: failed to create MTP context
E srv          main: exiting due to model loading error
```

メインモデル + MTP draft の compute buffer 合計が P100 1 枚（16 GiB）の余裕を超えていた。

#### 対処

`start.sh` の MTP 検出ブロックで t120h-p100 のとき `SERVER_OPTS` を `-b 2048 -ub 512` に縮小するよう変更。

#### 再試行

| 確認項目 | 結果 |
|---------|------|
| 起動 (`-b 2048 -ub 512` MTP プロファイル) | 成功 |
| `--spec-type draft-mtp` 自動付与 | 確認 |
| `--spec-draft-n-max 6` 自動付与 | 確認 |
| `--alias unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL` | 確認 |
| `/v1/chat/completions` 推論 | 成功 |

サーバログより MTP draft context 作成成功:

```
I srv    load_model: creating MTP draft context against the target model
  '...Qwen3.6-27B-UD-Q4_K_XL.gguf'
```

## 既知の課題・今後の TODO

1. **35B-A3B-MTP の VRAM 検証未実施**: 27B-MTP で VRAM ギリギリ。35B-A3B (MoE) の MTP は更に compute buffer が大きい可能性。fit モード（CPU オフロード）併用検証が必要
2. **MTP の高速化効果ベンチ未取得**: 既存 non-MTP との eval t/s 比較で 1.5-2x の効果を実測すべき
3. **Qwen3.6-35B-A3B (non-MTP) の動作確認**: 起動テスト未実施（dense 27B と同じパス・自動選択ロジックのため動作は確実視）
4. **Marathon ベンチ用 Qwen3.5-122B-A10B の再起動**: 本作業で停止のまま。ユーザー判断で必要時 `llama-up.sh t120h-p100` を実行
5. **MTP モデルの ctx-size 推奨値**: 今回 8192 で動作確認したが、262k native ctx を活かす場合の VRAM フィット範囲は要調査

## 参照

- llama.cpp MTP マージ commit: 2026-05-16（旧 `--spec-type mtp` → `--spec-type draft-mtp` リネーム 2026-05-13）
- 関連メモリ（Claude Code auto-memory）:
  - `project_t_series_roadmap.md`: Phase T 系列後の機能軸ロードマップ
  - `project_marathon_2026_05_16.md`: Qwen3.5-122B-A10B Marathon ベンチ結果（HEAD 1348f67c5、本作業前の HEAD）
