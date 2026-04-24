# Qwen3.5-122B-A10B 128k コンテキスト VRAM 最適化 — 調査レポート作成計画

## Context

ユーザから「qwen3.5 122B 実行時に VRAM に余裕があるように見える。ctx 128k を確保しつつ expert 重みを可能な限り VRAM に載せる設定を検討してほしい」という依頼を受け、現在 `t120h-p100` で稼働中の llama-server の状態（プロセス情報・nvidia-smi・起動ログ）を読み取り専用で調査した。実行は行わず、調査結果と提案を **レポート化して残す** のがこの計画のゴール。

レポートには「対立する仮説が存在する場合は複数案示す」という要求があるため、単一の最適解ではなく、仮説ごとに複数のプランを併記する。

## 作成するファイル

- 本体: `report/2026-04-10_161331_qwen3-122b-128k-vram-tuning.md`
- 添付: `report/attachment/2026-04-10_161331_qwen3-122b-128k-vram-tuning/plan.md`
  - `/home/ubuntu/.claude/plans/glistening-knitting-crown.md`（このファイル）をコピー

参照: 既存レポート `report/2026-04-04_224541_fix_hf_token_validation.md`（関連性は薄いが列挙の参考）。REPORT.md のルール（プランファイル添付必須、JST、`date +%Y-%m-%d_%H%M%S` で取得済み → `2026-04-10_161331`）。

## レポートの構成（見出し案）

1. **タイトル**: 「Qwen3.5-122B-A10B 128k コンテキスト化と VRAM 配置の検討」
2. **実施日時**: 2026年4月10日 16:13 (JST)
3. **添付ファイル**: 本プランへのリンク
4. **前提・目的**:
   - 依頼内容の要約
   - 実行はしないこと、計画のみであること
   - 対立仮説がある場合は複数案を示す方針
5. **環境情報**:
   - サーバ `t120h-p100` (10.1.4.14)、Tesla P100-PCIE-16GB × 4（合計 64 GiB）
   - RAM 251 GiB（available 234 GiB）
   - モデル: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
   - llama-server の現行起動コマンド（ログから抜粋）
6. **調査方法**:
   - `ssh t120h-p100` による read-only 確認（プロセス、nvidia-smi、/props、起動ログ grep）
   - `.claude/skills/llama-server/scripts/start.sh` の読み取り
7. **調査で分かったこと**:
   - 7.1 モデル構造: `n_layer=48, n_head_kv=2, n_embd_k/v_gqa=512, n_expert=256, n_expert_used=8, n_ctx_train=262144`、hybrid (attention + recurrent)
   - 7.2 GPU 別メモリ内訳テーブル（model/KV/RS/compute buffer）
   - 7.3 CPU_Mapped 合計 72.27 GiB、1 層あたり expert ≈ 1.50 GiB
   - 7.4 compute buffer が支配的（GPU3 で 8 GiB）→ ボトルネックは GPU3
   - 7.5 KV buffer が意外と小さい（合計 816 MiB）理由 = hybrid 構造
   - 7.6 ctx 倍化で増える VRAM は KV buffer 分の **+204 MiB/GPU** のみ（H1 前提）
8. **対立する仮説**:
   - H1: compute buffer は ctx-size に非依存（flash-attention 前提）
   - H2: compute buffer は ctx-size に弱く比例
   - H3: GPU 間不均衡は layer split 起因で、tensor-split 介入で緩和可能
9. **提案（複数プラン併記）**:
   - プラン A: ctx 131072 化のみ（最小変更・仮説検証用）
   - プラン B: `-ot 'ffn_(gate|up)_exps\.weight=CPU'` で down_proj のみ GPU 復帰
   - プラン C: 層単位の選択的復帰（C-1 控えめ / C-2 攻め）
   - プラン D: `-b 4096 -ub 4096` で compute buffer 縮小 + B 併用
   - それぞれで **狙い・コマンド差分・期待 VRAM・期待 eval 改善・リスク** を併記
10. **推奨実行順**: A → B → (OOM なら) D → (さらに困ったら) C-1 という段階検証
11. **再現方法（将来実行する場合の手順）**:
    - ロック取得 → 既存 llama-server 停止 → 起動 → nvidia-smi / ログ計測 → 解放
    - `start.sh` の fit モード引数でプラン A をカバーできる旨と、B/C/D は `start.sh:206-212` の `-ot` 固定値を改修するか手動コマンドで回す必要がある旨を明記
12. **未検証事項 / 今後の TODO**:
    - layer → GPU マッピングの実地確認（推定ベース）
    - compute buffer の ctx 依存性（実測で H1/H2 判定）
    - プラン B の GPU3 での成否（実測必須）
    - eval 速度の定量測定

## 書き込みの方針

- 実測値は必ず出典（コマンド or ログ）を添える。
- 数式・計算式は読み手が検算できる形で示す（1 層 expert サイズ、KV per-token の算出など）。
- 「今回は実行していない」「実測依存」であることを随所に明記し、レポートを過信させない。
- 絵文字は使わない。コードブロックは bash / テーブルは Markdown。

## ワークフロー（レポート作成手順）

1. 添付ディレクトリ作成: `mkdir -p report/attachment/2026-04-10_161331_qwen3-122b-128k-vram-tuning/`
2. プランファイルをコピー: `cp /home/ubuntu/.claude/plans/glistening-knitting-crown.md report/attachment/2026-04-10_161331_qwen3-122b-128k-vram-tuning/plan.md`
3. レポート本体を Write: `report/2026-04-10_161331_qwen3-122b-128k-vram-tuning.md`
4. レポート末尾から添付へのリンクを確認
5. REPORT.md ルール遵守を最終チェック（タイトル日本語、JST、添付リンク、前提・目的・環境・再現方法セクションあり）

## 触らないもの

- `.claude/skills/llama-server/scripts/start.sh`（今回の計画は実行含まないので編集不要）
- その他プロジェクトコード・設定・ドキュメント
- GPU サーバ上のプロセス（読み取り専用確認のみ、停止・起動・コマンド投入はしない）

## 成果物の使われ方

このレポートは将来のセッションで「実行フェーズ」に入る際の出発点になる。ロックが取れたタイミングで別セッションを立て、本レポートの推奨順に沿って段階的に実測する想定。
