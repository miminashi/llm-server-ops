# Qwen3.6 thinking ループ対策: presence_penalty + DRY デフォルト有効化

- **実施日時**: 2026年5月25日 11:51 (JST)

## 前提・目的

- **背景**: opencode から t120h-p100 上の Qwen3.6-35B-A3B (UD-Q4_K_XL, ctx=131072) を使用中、thinking モードで段落単位の verbatim ループに陥る事例が発生。ユーザから「`ブラウザで取得したURLも、同じSECRET_KEY_BASEで署名されている。…signatureが一致するはずなのに404になる。待って、…`」というブロックが完全一致で 10 回以上連続する出力サンプルが提示された。
- **目的**: パラメータ調整でループを抑制可能か調査し、可能であれば `start.sh` のデフォルトサンプリングに組み込む。
- **前提条件**: 既存サーバ起動コマンドの引数構成 (`--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0`) を維持しつつ、追加パラメータのみで対処する。

## 環境情報

- サーバ: t120h-p100 (10.1.4.14)
- GPU: NVIDIA Tesla P100 16GB × 4
- モデル: `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`
- llama.cpp: 2026-05-21 時点の HEAD (デフォルト LLM 切替時にビルド)
- ctx-size: 131072 / `-b 8192 -ub 8192` / `--flash-attn 1 --poll 0`
- クライアント: opencode (TUI コーディング agent、OpenAI 互換 API)

## 調査結果

### ループの正体

提示された出力は典型的な **Qwen3 thinking 系の自己強化型ループ**。同じ思考連鎖 (「待って、…でも…」) が完全 verbatim で繰り返される。Qwen3 シリーズの既知症状で、特に長 thinking + tool-use コンテキストで `presence_penalty=0` の場合に発生しやすい。

### 現行起動コマンドの確認

```
./build/bin/llama-server ... --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0
  --port 8000 --host 0.0.0.0 --alias unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL
```

反復抑制系のパラメータ (`--repeat-penalty`, `--presence-penalty`, `--frequency-penalty`, `--dry-multiplier`) はすべてデフォルト=無効。

### 対策候補

| 対策 | 効果 | 副作用 |
|------|------|--------|
| `--presence-penalty 1.0` | Qwen 公式が「反復時は 0〜2 で調整」と推奨 | 中庸値、coding でも実用上問題なし |
| `--dry-multiplier 0.8` (DRY 有効化) | n>=allowed_length のトークン列の verbatim 再生成を狙い撃ち抑制 | breakers (`\n : " *`) と allowed_length=2 デフォルトで coding における識別子の反復は守られる |
| `--repeat-penalty 1.1` | 直近 N トークンの単純反復に重い罰 | コードトークン (`def`, `}`, `;` 等) を歪める可能性あり、今回は採用見送り |
| `--frequency-penalty` | presence と類似 | 並用は過剰、見送り |

**採用**: `--presence-penalty 1.0 --dry-multiplier 0.8` の組み合わせ。Qwen 公式推奨と DRY のターゲット抑制で 2 段防御。

## 変更内容

### `.claude/skills/llama-server/scripts/start.sh`

```diff
 # --- モデル別サンプリングパラメータ ---
+# Qwen3.x thinking モードは opencode 等の長コンテキストで段落単位の verbatim ループに陥ることがある。
+# 公式推奨どおり presence_penalty を併用し、加えて DRY サンプラで verbatim 長文ループを抑制する。
+# DRY breakers は llama.cpp default の '\n', ':', '"', '*'、allowed-length=2 のまま使用。
 case "$HF_MODEL" in
   *Qwen3.5*|*Qwen3.6*)
-    SAMPLING_OPTS="--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0"
+    SAMPLING_OPTS="--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 --presence-penalty 1.0 --dry-multiplier 0.8"
     ;;
   *)
     SAMPLING_OPTS="--temp 1.0 --top-p 1.0 --top-k 0"
     ;;
 esac
```

### `.claude/skills/llama-server/SKILL.md`

サンプリング表 (Qwen3.5-35B-A3B / Qwen3.5-122B-A10B / Qwen3.6-27B / Qwen3.6-35B-A3B 各行) を新パラメータに更新し、「反復対策パラメータについて」の注記を追加。

## 再現方法

### 旧パラメータでループを再現

1. start.sh の変更前 (commit `965275d0` 時点) で起動:
   ```bash
   .claude/skills/llama-server/scripts/llama-up.sh t120h-p100 \
     "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
   ```
2. opencode から長い thinking が必要なデバッグ系プロンプト (例: `ActiveStorage::DiskController` の signature 検証が 404 になる原因調査) を投げる
3. thinking 内で同一段落が verbatim でループする出力が発生する

### 新パラメータで検証

1. ファイル更新後に再起動:
   ```bash
   .claude/skills/gpu-server/scripts/lock.sh t120h-p100
   .claude/skills/llama-server/scripts/llama-down.sh t120h-p100
   .claude/skills/llama-server/scripts/llama-up.sh t120h-p100
   ```
2. 起動コマンド確認:
   ```bash
   ssh t120h-p100 "ps aux | grep llama-server | grep -v grep | grep -o 'presence-penalty [^ ]*\|dry-multiplier [^ ]*'"
   # → presence-penalty 1.0
   # → dry-multiplier 0.8
   ```
3. 同様のプロンプトを opencode から投げて、ループが解消することを確認

## 適用状況

- ファイル更新: 完了 (未コミット、master ブランチ)
- サーバ再起動: **ユーザが後で実施予定**。現在動いている PID 11493 は旧パラメータのまま稼働中
- 反映タイミング: 次回 `llama-up` 実行時に自動適用される

## フォールバック案

`--presence-penalty 1.0 + DRY 0.8` で抑え切れない場合の段階的強化:

1. `--presence-penalty` を 1.5 に引き上げ (Qwen 推奨レンジ 0〜2 の上位寄り)
2. `--dry-multiplier` を 1.0 に引き上げ
3. `--repeat-penalty 1.1 --repeat-last-n 256` を追加 (副作用大、最終手段)

## 参照

- 直近のデフォルト LLM 切替: [2026-05-21 default_llm_qwen36_35b](2026-05-21_043823_default_llm_qwen36_35b.md)
- Qwen3.6 モデル追加: [2026-05-19 qwen36-add-and-skill-update](2026-05-19_030233_qwen36-add-and-skill-update.md)
