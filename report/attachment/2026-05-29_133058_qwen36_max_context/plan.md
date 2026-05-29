# Qwen3.6-35B-A3B 実用最大コンテキスト長 調査プラン

## Context（背景・目的）

現在 Qwen3.6-35B-A3B はデフォルト `ctx=131072`（128K）で t120h-p100 上に運用されている（`llama-up.sh` の default、commit `b4a05339`）。しかし調査の結果、このモデルの **native context は 262,144（256K）** で、現状はその半分しか使っていないことが判明した。さらに YaRN で factor=2 → 524K、factor=4 → 約1,010,000（1M）まで拡張可能。

加えて Qwen3.6 系は **Gated DeltaNet（線形 attention）+ Gated Attention のハイブリッド + Sparse MoE** アーキであり、線形 attention 層は ctx に対して KV cache が増えない（固定状態）。full attention 層のみ ctx 線形に増えるため、標準 Transformer より KV メモリが軽い可能性が高い。これが本調査の鍵。

**目的**: t120h-p100（64GB VRAM）で、**品質劣化が許容範囲内に収まる最大の ctx** を段階的ベンチで特定し、推奨運用値をレポートにまとめる。VRAM が物理上限になる場合と、品質が先に劣化する場合を切り分けて報告する。

**確定済みの方針（ユーザ回答）**:
- ゴール: 品質劣化が許容範囲内の最大（簡易 NIAH で long-context 性能を確認、YaRN 時の短文劣化も観察）
- 検証手法: 段階的ベンチ（起動・VRAM・pp/tg 速度・NIAH を各段階で測定）
- 対象サーバ: **t120h-p100 のみ**（64GB, CUDA, flash-attn 有）
- **時間予算: 半日程度**。全段階を走らせつつ NIAH は深さ3点（10/50/99%）× 1回で効率化。
- **自動スコープ縮小**: S0 baseline で pp 速度を実測し、高 ctx 段の所要時間を見積もる。見積もりが半日を大きく超えそうなら、NIAH の深さ点や中間段階を**自動で間引く**（VRAM・起動可否は全段階で維持）。判断根拠はレポートに明記。中断してユーザに相談はしない。
- **VRAM の扱い（当初指示との整合）**: 当初「VRAM は足りる前提」との指示があったが、対象を p100（64GB）に限定したため、**p100 の物理上限を「実用最大」とする方針に確定**。VRAM が品質境界より手前で頭打ちした場合は「実用最大 = VRAM 制約値」として報告する（m10 へのフォールバックや理論計算での補完は行わない）。

## 既知の前提（調査済み）

| 項目 | 値 / 状況 |
|------|-----------|
| native ctx | 262,144（256K）、`original_max_position_embeddings` |
| YaRN | factor=2→524K, factor=4→1M。公式は「long-context 必要時のみ。static YaRN は短文劣化」と警告 |
| モデルファイル | `/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.6-35B-A3B-GGUF/...UD-Q4_K_XL.gguf`（約21GB）t120h-p100 にDL済 |
| アーキ | Gated DeltaNet + Gated Attention hybrid + Sparse MoE（256 experts, 8+1 activated）, 35B総/3B activated |
| 現行 ctx | 131072（`llama-up.sh` default） |
| KV cache | `q8_0`（`start.sh:307` で固定） |
| サーバ opts | `--flash-attn 1 --poll 0 -b 8192 -ub 8192`（`start.sh:179`）, `--parallel 1`, `--n-predict 32768` |
| VRAM | P100 × 4 = 64GB |

## 重要な実装上の課題

1. **`start.sh` に YaRN/rope-scaling を渡す口がない**（`LAUNCH_CMD` は `--ctx-size` のみ）。262K 超の検証には一時改修が必要。
   - 改修方針: 環境変数 `EXTRA_LLAMA_OPTS`（任意）を `LAUNCH_CMD` に挿入できるようにする最小パッチ。検証時のみ `--rope-scaling yarn --rope-scale <f> --yarn-orig-ctx 262144` を渡す。恒久運用に昇格する場合は別途プロファイル化を提案。
2. **unsloth GGUF に YaRN がメタ焼き込み済みか不明**。起動ログの `n_ctx_orig_yarn` / rope 設定行で確認し、焼き込まれていなければ CLI フラグで明示。
3. **llama.cpp の Gated DeltaNet サポート / KV cache 実装**を baseline 起動ログ（`llama_kv_cache_init`, compute buffer 行）で確認。これにより各 ctx での KV 増加量を実測ベースで予測し、到達可能段階を決める（adaptive）。

## 検証段階（ctx の階段）

baseline ログで KV/compute buffer の伸び方を確認した後、下記を順に試行。VRAM 上限（64GB）に当たった段階で停止。

| 段階 | ctx | YaRN factor | 備考 |
|------|-----|------|------|
| S0 | 131,072 | なし | 現行 baseline |
| S1 | 262,144 | なし | native 上限（最重要の節目） |
| S2 | 393,216 | 1.5 | factor = ctx/262144 |
| S3 | 524,288 | 2.0 | factor = ctx/262144 |
| S4 | 786,432 | 3.0 | factor = ctx/262144、VRAM 許せば |
| S5 | 1,010,000 | ≒3.85 | factor = ctx/262144、理論最大 |

> **YaRN factor は各段で `factor = 目標ctx / 262144` に一致させる**。factor は「拡張したい最大長 ÷ native」であり、過大な factor は不要なスケールで短文・中距離精度を劣化させるため、段ごとに必要分だけ設定する（`--rope-scaling yarn --rope-scale <factor> --yarn-orig-ctx 262144`）。
>
> 段階数は KV cache の実測増加量に応じて調整。線形 attention ハイブリッドで KV が軽ければ S4/S5 まで届く可能性、重ければ S1〜S2 で VRAM 頭打ち。

## 各段階の測定項目

1. **起動成否 / ロード時間** — `wait-ready.sh` 相当で /health を待つ。OOM・失敗はログ記録。
2. **VRAM 使用量** — 起動直後と NIAH 充填後のピークを `nvidia-smi`（4枚合計）で取得。起動ログから `KV self size` と `compute buffer size` の内訳も記録。
3. **pp / tg 速度** — ctx の約90%を埋めた長プロンプトを投げ、`/v1/completions` のレスポンス（timings: prompt_per_second / predicted_per_second）を記録。
4. **NIAH 品質**（簡易 Needle-in-a-Haystack）:
   - haystack: 反復テキスト or 既存テキスト連結で目標トークン数を充填（tokenizer は `/tokenize` エンドポイントで実測）。
   - needle: `The secret access code is <ランダム8桁>.` を深さ **10% / 50% / 99%（3点、時間予算優先）** に挿入。
   - 質問: `What is the secret access code?` → 回答に8桁が**完全一致**で含まれるか（exact match、judge LLM 不要）。
   - 各 ctx × 各深さでグリッド評価し回収率を出す。時間超過見込み時は深さ点・段階を自動間引き。
5. **YaRN 短文劣化チェック**（S2 以降）— 短い質問を数問（簡単な算数・常識・短いコード）投げ、baseline（YaRN なし）と回答品質を目視比較。劣化が顕著なら「短文用は YaRN なし運用」と明記。

## 必要なスクリプト（検証用、`report/attachment/` 配下に保存）

- `niah.py` — tokenize で長さ管理、needle 埋め込み、API 呼び出し、exact-match 判定、結果を JSON/CSV 出力。
- `bench.py` or curl ワンライナー — pp/tg 速度測定（long prompt 投入、timings 取得）。
- `plot.py`（matplotlib）— 以下3グラフを PNG 生成:
  - ctx vs VRAM（model / KV / compute buffer の積み上げ + 64GB ライン）
  - ctx vs pp / tg tps
  - NIAH 回収率ヒートマップ（ctx × depth）

## 実行手順

1. **ロック取得**: `.claude/skills/gpu-server/scripts/lock.sh t120h-p100`（GPU サーバ使用のため必須）。
2. **start.sh 一時改修**: `EXTRA_LLAMA_OPTS` を `LAUNCH_CMD` に挿入できるよう最小パッチ。
3. **S0 baseline 起動**（`ctx=131072`）→ 起動ログ精読（アーキ・KV cache 実装・rope 設定・KV/buffer サイズ）→ VRAM・pp/tg・NIAH 測定。
   - **ビルドは初回のみ**: `start.sh` は毎回 `update_and_build.sh` を走らせる（166-167行）が、2回目以降は差分なしで高速スキップされる。段階間で ctx を変えるだけの再起動は、既存 llama-server を停止して同一バイナリで再起動する形に留め、ビルド時間を二重に消費しない。
4. **S1（262K, YaRN なし）** 起動 → 同測定。ここまでが「無加工で信頼できる」領域。
5. **S2 以降（YaRN）** を VRAM 上限まで順次。各段で停止→計測→次段。OOM が出たら直前段が VRAM 上限。
6. NIAH 回収率が明確に低下した段階を「品質上限」として記録。VRAM 上限と品質上限の小さい方が「実用上最大」。
7. **サーバ停止 + ロック解放**: `llama-down.sh` 相当 + `unlock.sh t120h-p100`。**運用デフォルトは変更しない**（推奨値はレポートで提案のみ。変更は別途ユーザ承認後）。

## レポート作成（必須）

- 命名: `report/YYYY-MM-DD_HHMMSS_qwen36_max_context.md`（タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`）。タイトルは日本語・50字以内。
- 冒頭に **核心発見サマリ** を設け、3枚の PNG をセクション冒頭に画像埋め込み（VRAM / 速度 / NIAH）。
- 必須セクション: 前提・目的 / 環境情報（t120h-p100, GPU, llama.cpp ビルド版）/ 再現方法 / 添付ファイル。
- 推奨運用値（例: 「262K まで YaRN 不要で安全」「N まで品質維持・速度許容」「運用デフォルトを X に上げる提案」）を結論として明記。
- `## 添付ファイル` に plan.md（このファイルのコピー）と niah.py / bench.py / plot.py / 生ログ・CSV をリンク。

## リスク・注意点

- 1M ctx の NIAH 充填は prompt processing が長時間化する → タイムアウトと進捗監視に注意。各段の haystack 生成は ctx に比例して時間がかかる。
- llama.cpp が Gated DeltaNet を未サポート/部分サポートの場合、起動失敗や KV 実装が想定と異なる可能性 → baseline ログで早期に判明させ、その場合はプランを調整。
- start.sh 改修は検証用の最小変更に留め、調査完了後に運用デフォルトを勝手に変えない。
- sudo は使わない。必要時はユーザにコマンド提示。
