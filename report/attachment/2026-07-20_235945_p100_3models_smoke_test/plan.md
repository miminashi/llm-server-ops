# P100 3 モデル動作確認 (gemma-4 / north-mini-code / ornith)

## Context

先ほど P100 (`t120h-p100`) にダウンロードが完了した `gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf` を含む 3 モデルの動作確認を実施する。3 モデルとも本プロジェクトでの実行履歴が無く、arch/tokenizer/chat_template がそれぞれ異なるため、chat template パーサや sampling プロファイルの適合を確認しておく価値がある。あわせて、既存の起動スクリプト `.claude/skills/llama-server/scripts/start.sh` は HF リポジトリ ID (`org/repo:quant`) 形式しか受け付けず、ローカル gguf パスに未対応であるため、この機会に最小パッチを当ててスキルに恒久組み込みする。

**対象モデル**:
| # | 起動順 | パス (`/home/llm/models/…`) | サイズ | arch | ctx (native) |
|---|---|---|---|---|---|
| 1 | 1st | `gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf` | 15.8 GB | `gemma4` (MoE 26B/A4B) | 262,144 |
| 2 | 2nd | `North-Mini-Code-1.0-UD-Q4_K_XL.gguf` | 17.9 GB | `cohere2moe` (30B/A3B, SWA-heavy) | 500,000 |
| 3 | 3rd | `ornith-1.0-35b-Q4_K_M.gguf` | 19.7 GB | `qwen35moe` (35B/A3B, SSM+attn hybrid) | 262,144 |

**動作確認方針**: 詳細 (health → chat 単発 → long ctx (131k) 生成 → 簡易 bench)。1 モデル 20〜30 分想定、計 60〜90 分。start.sh 改修込み。

## 前提条件・現状 (2026-07-20 21:2x 時点)

- **P100**: `available` (ロック未取得)、llama-server 未起動、VRAM 各 GPU 空き 15+ GiB (GPU0: 14.95 GiB, GPU1-3: 16.01 GiB)
- **P100 llama.cpp**: build 9690 (`0843245cb`)、CUDA ARCH=600 (Tesla P100 = CC 6.0)
- **P100 空きディスク**: `~/models` 上に 153 GB (`df -h`)
- 3 モデルは `~/models/` 直下に配置済み (HF キャッシュではない)

## Step 1 — start.sh にローカルパス対応パッチを当てる

**対象ファイル**: `.claude/skills/llama-server/scripts/start.sh`

**修正内容** (`# --- モデルパス解決 ---` セクション、L212 前後):

```bash
# 追加: ローカル絶対パス .gguf の場合は HF 解決をスキップ
if [[ "$HF_MODEL" == /*.gguf ]]; then
  MODEL_PATH="$HF_MODEL"
  ALIAS="$(basename "${HF_MODEL%.gguf}")"          # alias を綺麗な basename に
  echo "==> ローカルパス指定を検出: $MODEL_PATH"
else
  # 既存の HF_REPO / HF_QUANT パース + find + hf download 一式をこの else に入れる
  HF_REPO="${HF_MODEL%%:*}"
  HF_QUANT="${HF_MODEL##*:}"
  ALIAS="$HF_MODEL"
  MODEL_PATH=$(ssh "$SERVER" "find ~/.cache/huggingface/hub/models--${HF_REPO//\//--}/ …")
  … 既存処理 …
fi
MODEL_OPT="-m '$MODEL_PATH'"
```

- `wait-ready.sh` / `stop.sh` はローカルパス互換 (既存 case 分岐が unmatched になり generic fallback するのみ)、変更不要。
- 副次修正 (任意): モデルプロファイル (`case "$HF_MODEL" in …`) にも `*gemma-4*` / `*ornith*` / `*North-Mini-Code*` の分岐を追加し、後述の推奨 sampling を default 化。動作確認と同 PR で行うか、確認後に別コミットに切るかは実装時判断。

## Step 2 — 各モデルの起動パラメータ

**共通** (P100 = CUDA、既存 SERVER_OPTS 適用):
- `--flash-attn 1 --poll 0 -b 8192 -ub 8192` (SKILL 記載の P100 default) … ただし 2026-06-03 の `-ub 8192` OOM リグレッションが Qwen3.6-35B 対象だったため、今回の 3 モデルでも OOM したら `-ub 4096` に降格
- `--cache-type-k q8_0 --cache-type-v q8_0` (既存 start.sh の default)
- ctx=32768 で確認 → OK なら 131072 に上げる (詳細モード)

**モデル別 sampling** (gguf 埋め込みの `general.sampling.*` KV を優先):
| モデル | temp | top_p | top_k | 追加 | chat template |
|---|---|---|---|---|---|
| gemma-4-26B-A4B-it | 1.0 | 0.95 | **64** | `--min-p 0` | `--jinja` (specialized parser あり) |
| North-Mini-Code-1.0 | 0.3 | 0.75 | 0 | `--min-p 0` | `--jinja` (Cohere2 専用 parser) |
| ornith-1.0-35b | 1.0 | 0.95 | 20 | `--presence-penalty 1.0 --dry-multiplier 0 --min-p 0` (Qwen3.x 共通) | Jinja parse fail の可能性 → NG なら `--chat-template chatml` |

## Step 3 — 動作確認プロトコル (各モデル)

**a. ロック取得**:
```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

**b. 起動**:
```bash
.claude/skills/llama-server/scripts/start.sh t120h-p100 \
  /home/llm/models/gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf 32768
.claude/skills/llama-server/scripts/wait-ready.sh t120h-p100 \
  /home/llm/models/gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf 32768
```

**c. 起動ログ確認** (VRAM/tensor split/chat template/警告):
```bash
ssh t120h-p100 "grep -E 'llama_model_load|print_info|special|control|swa|template|VRAM|CUDA' /tmp/llama-server.log | tail -60"
ssh t120h-p100 "nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv"
```

**d. health**:
```bash
curl -s http://10.1.4.14:8000/health   # → {"status":"ok"}
```

**e. 単発 chat (EOG 停止確認)**:
```bash
curl -sN http://10.1.4.14:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"'"$ALIAS"'","messages":[
      {"role":"system","content":"You are a helpful assistant."},
      {"role":"user","content":"日本語で「こんにちは」と一言だけ返してください。"}
    ],"max_tokens":50,"stream":false}' | jq -r '.choices[0].message.content, .choices[0].finish_reason'
```
- `finish_reason` が `stop` になっていれば EOG 正常検知。`length` なら stop トークン未登録の疑い。

**f. long ctx (131k 相当) 生成**:
- 32k で健全 → 一旦 stop → `-c 131072` で再起動
- 100 KB 程度のダミー prompt を投げて OOM せず応答するか、`/v1/completions` で `n_predict=128`。VRAM 使用のスキュー (特に gemma-4 の layer 毎 n_head_kv) を `nvidia-smi` で確認。

**g. 簡易 bench** (詳細モードのみ、gemma-4 のみ実施推奨):
```bash
ssh t120h-p100 "cd ~/llama.cpp && ./build/bin/llama-bench \
  -m /home/llm/models/gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf -ngl 999 -fa 1"
```
pp512 / tg128 が Qwen3.6-35B-A3B (t120h-p100 baseline pp=693 / tg=63) と比較して妥当なオーダーか確認。

**h. 停止**:
```bash
.claude/skills/llama-server/scripts/stop.sh t120h-p100
```

**i. 次モデルへ移行** (a→h を 3 回繰り返し)

**j. 全モデル完了後、ロック解放**:
```bash
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## Step 4 — レポート作成

CLAUDE.md ルール (plan mode 完了時はレポート必須) に従い `REPORT.md` フォーマットで作成:
- パス: `report/2026-07-20_<HHMMSS>_p100_3models_smoke_test.md`
- 必須セクション: **概要** (核心発見サマリ)、環境、モデル別結果表、既知の落とし穴 (Jinja parse fail 等)、フォローアップ (start.sh のモデル別プロファイル追加、レポート化していない bench の位置付け)
- 添付: 起動ログ抜粋、`nvidia-smi` の VRAM 使用スナップショット (`report/attachment/<date>_p100_3models_smoke_test/` へ)
- タイトルは 50 字以内、核心発見サマリを冒頭に (memory ルール)

## 想定リスクとフォールバック

| # | リスク | 検知 | フォールバック |
|---|---|---|---|
| 1 | `-ub 8192` OOM (llama.cpp 2026-06-02 リグレッション再現) | 起動ログの `CUDA out of memory` / `/health` が 000 | `-ub 4096` で再起動 (`SERVER_OPTS` 上書き) |
| 2 | P100 の CC 6.0 で `--flash-attn 1` 未対応 kernel エラー | 起動時のクラッシュログ | `--flash-attn 0` に切替 (SKILL default 逸脱するが動作優先) |
| 3 | ornith の Jinja parse fail で chat 応答が壊れる | 応答本文が空 / タグ混入 | `--chat-template chatml` を手動指定 (start.sh の `CHAT_TEMPLATE_OPTS` 上書き) |
| 4 | gemma-4 の layer 毎 `n_head_kv` で GPU VRAM スキュー → 1 枚だけ OOM | `nvidia-smi` の使用量が不均等 | `--tensor-split` を実測に合わせて手動指定 (default `1,1,1,1` から比率変更) |
| 5 | north-mini の `special_eos_id is not in special_eog_ids` 警告で生成停止せず | `finish_reason=length` が連発 | `stop` パラメータに `<|END_OF_TURN_TOKEN|>` を明示指定 |

## Verification

- 3 モデルとも起動 → `/health` 200 → chat 応答が意味を成し EOG 停止 → long ctx (131k) で OOM せず応答継続 → 停止クリーン (プロセス残らず、VRAM 解放)
- start.sh のパッチが plugin cache 由来ではなく `.claude/skills/llama-server/scripts/start.sh` 実体を修正していること (`git diff` で確認)
- start.sh の HF リポジトリ ID 起動が退行していないこと (`unsloth/Qwen3.6-27B-GGUF:UD-Q4_K_XL` あたりで smoke test。131k までは要さず 32k で十分)
- ロック解放後、`.claude/skills/gpu-server/scripts/lock-status.sh` で P100 が `available` に戻る
- レポート生成、Discord 通知 (wait-ready.sh 自動送信) が届く
