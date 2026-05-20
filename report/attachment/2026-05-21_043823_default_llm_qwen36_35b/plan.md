# デフォルトLLMをQwen3.6-35B-A3Bに切り替える

## Context

opencodeのベンチマーク（[2026-05-21_032451_qwen36_5model_bench.md](http://10.1.6.4:5032/opencode/report/2026-05-21_032451_qwen36_5model_bench.md/raw)）で、現行運用モデル `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M` の置換候補として5モデルを評価した結果、**`unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`（非MTP、ctx=131072、通常起動）** が以下の理由で唯一判定式をクリアした：

- judge_score 4.44（122B の 3.89 を +0.55 上回り全モデル中最高）
- wall_time 365s vs 122B 1047s（×2.9 高速、eval_tps 12.0）
- 9/9 全完走（唯一の100%成功）
- MTP 版は tool-heavy ワークロードで draft 無効化により逆効果、judge 3.56 で失格

本プロジェクト `llm-server-ops` のデフォルトLLM（`llama-up.sh` の引数省略時に起動するモデル）をこの推奨モデルに切り替える。

## 変更内容

### 1. `.claude/skills/llama-server/scripts/llama-up.sh`

| 行 | 変更前 | 変更後 |
|----|-------|-------|
| 12 | `# hf-model ... (デフォルト: unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M)` | `# hf-model ... (デフォルト: unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL)` |
| 13 | `# mode      ctx-size or "fit"          (デフォルト: fit)` | `# mode      ctx-size or "fit"          (デフォルト: 131072)` |
| 18 | `# 例: ... "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M" 8192` | `# 例: ... 旧 122B を fit 起動: ... "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit` |
| 31 | `HF_MODEL="${2:-unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M}"` | `HF_MODEL="${2:-unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL}"` |
| 32 | `MODE="${3:-fit}"` | `MODE="${3:-131072}"` |

**理由**: Qwen3.6-35B-A3B にはfitプロファイルが定義されていないため、`MODE=fit` のままだと全層 CPU offload + ctx=8192 で起動し、ベンチ結果（ctx=131072 通常起動で eval 12 t/s）が再現しない。

### 2. `.claude/skills/llama-server/SKILL.md`

- **行 12-25「モデル未指定時の振る舞い」のダイアログ**: モデル選択肢の並びを変更し、Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL を **1番目**（推奨と明記）に。現在の1番目（Qwen3.5-35B-A3B）以降は順序を1つずつ後ろにずらす。例:
  ```
  1. unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL — **推奨**、MoE 35B/3B activated、262k native ctx、thinking対応、opencodeベンチ最良
  2. unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M — thinking対応、128k ctx
  ...
  ```
- **行 138「引数すべて省略可（デフォルト: ... / unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M / fit）」**: 新デフォルトに置換 → `t120h-p100 / unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL / 131072`

その他の参照箇所（モデル一覧表 行 35-38、サンプリングパラメータ表 行 48-49、fitモード説明、MTP説明）は事実情報なので変更不要。

### 3. `README.md`

- **行 33-40「クイックスタート」の起動例**: 先頭の `Qwen3.5-35B-A3B` の例を `Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` ctx=131072 に置換。コメント例は「Qwen3.5 系を起動する場合の例」として下に残す（後方互換情報として）。
- **行 45 の curl 例**: `"model": "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M"` → `"model": "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL"`。

### 4. レポート作成（CLAUDE.md ルール準拠）

REPORT.md に従い `report/yyyy-mm-dd_HHMMSS_default_llm_qwen36_35b.md` を作成：

- タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得
- セクション: 前提・目的 / 環境情報 / 変更内容 / 再現方法 / 添付ファイル（plan.md）
- 参照: 上記ベンチマークレポート URL
- 添付: 本 plan ファイルを `report/attachment/<reportname>/plan.md` にコピー

## 変更しないもの

- `start.sh` の `*Qwen3.5*|*Qwen3.6*` サンプリングパラメータ分岐（既に Qwen3.6 対応済み、行 196-204）
- `start.sh` の MTP 自動検出ロジック（行 206-220、デフォルトでは非MTP版なので発動しない）
- `start.sh` の `Qwen3.5-122B-A10B` 用 `qwen3_122b` プロファイル（旧モデルを引数指定で使う際に必要、行 117-121, 190-194）
- 新規プロファイルの追加（Qwen3.6-35B-A3B は通常起動でフィット）

## 変更対象ファイル一覧

- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/llama-up.sh`
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/SKILL.md`
- `/home/ubuntu/projects/llm-server-ops/README.md`
- `/home/ubuntu/projects/llm-server-ops/report/<新規レポート>.md`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/<新規レポート>/plan.md`（plan のコピー）

## 検証

1. **スクリプト dry-check**: 編集後 `bash -n llama-up.sh` で構文エラーがないこと
2. **デフォルト動作確認**（オプション、ユーザ実行で）:
   ```bash
   # 引数なしでデフォルトモデルが Qwen3.6-35B-A3B、ctx=131072 で渡ることをdry runで確認
   bash -x .claude/skills/llama-server/scripts/llama-up.sh 2>&1 | grep -E '(HF_MODEL|MODE|CTX)' | head
   ```
3. **実起動テスト**（任意・ユーザ判断）: t120h-p100 で gpu-server skill のロック取得後、引数なしで `llama-up.sh` を起動 → `/health` 200 応答 → `/v1/chat/completions` で疎通確認 → `llama-down.sh` で停止。ベンチ済みなので必須ではない。
4. **レポート公開URL確認**: 作成後 `http://10.1.6.4:5032/opencode/report/...` 相当の自プロジェクト用URLでアクセス可能か（プロジェクト側のレポート公開設定がある場合）。
