# Phase Sb-src: llama.cpp scheduler 閾値 ub\*=1586 のソース特定

## Context

直前レポート [Phase Sb-fine3](../../../projects/llm-server-ops/report/2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok.md) で以下が確定した:

- Qwen3.5-122B-A10B / ctx=32768 / fa=1 / f16 KV 条件下で、CUDA0 compute buffer に整数閾値 `ub*` が存在する
- 閾値は **ub\* ∈ (1585, 1586]**（1-token 精度、分数推定 1585.18）
- `ub ≤ 1585`: 平坦域（slope 0.0125 MiB/token）
- `ub ≥ 1586`: 線形域（slope 0.2853 MiB/token、8 点 max_err 0.008 MiB）
- 遷移域なし、純 step 関数
- ub=1586 は eval 15.466 t/s で ctx=32k 系列 21 点中の新記録

レポート「未検証事項 / 新規項目」最上位 (★★★) として以下が登録されている:

> **★最優先: llama.cpp scheduler ソースの閾値定数特定** (Phase Sb-fine3 新規 ★★★): 閾値 ub\*=1586 が整数スカラーと判明、`git grep -n "1585\|1586\|n_tokens.*>="` 等で定数リテラルを特定

初期調査で llama.cpp ソースに整数リテラル `1585`/`1586` は **直接存在しない**ことを確認済み（コメント・ビルドアーティファクトのみ）。したがって閾値は**動的計算の結果**として 1586 になる。本 Phase の目的は、その計算式を特定し、1586 という「非自然な定数」の物理的由来を解明することである。

本 Phase は読み取り専用（GPU ロック不要）で、ssh 経由で t120h-p100 上の `~/llama.cpp` ソース (commit 6990e2f1) を解析する。

## アプローチ

### 戦略

閾値は「`n_tokens` (または `n_ubatch`) が特定値を超えたときに compute buffer が線形増加し始める」という挙動である。以下の 2 軸で探索する:

1. **計算式の候補絞り込み**: 既知パラメータから 1586 を導出する式を列挙する
   - Qwen3.5-122B-A10B の hparams: hidden_dim, n_head, n_head_kv, n_embd_head, ffn_dim, n_expert, n_expert_used 等
   - 量子化パラメータ: block size (Q4_K_M は block 32 要素)、super-block 256
   - アラインメント: 16 / 32 / 64 / 128 / 256 / 512 / 1024 等
   - ctx 依存: 32768 と 1586 の関係
   - 既知の 192 MiB KV/GPU, 96 MiB/(16384 ctx)、layer 12 per GPU
   - モデル固有: Gated Delta Net state size (RS buffer 149.06 MiB)、Mamba chunk size

2. **コードパスのトレース**: compute buffer サイズが `n_tokens` でどう分岐するか
   - `ggml_backend_sched_reserve` (ggml-backend.cpp) からモデル graph へ
   - `llama_build_graph` / `llm_build_context` → attention / MoE / GDN 各ブロック
   - Mamba/GDN 系の chunk 化ロジック（`n_chunks = (n_tokens + chunk - 1) / chunk` 型の式）
   - Flash Attention の thread/block tile ベースの tmp バッファ配分
   - `ggml_cuda_op_mul_mat` / `ggml_cuda_op_flash_attn_ext` の temp buffer 決定

### 探索手順

#### Step 1: モデル hparams の取得（約 5 分）

```bash
# HF または GGUF メタから n_embd, n_head, n_head_kv, ffn_dim, n_expert, head_dim 等を抽出
ssh t120h-p100 "cd ~/llama.cpp && ./build/bin/llama-gguf /path/to/qwen3.5-122b.gguf 2>&1 | grep -E 'n_embd|n_head|n_layer|n_expert|head_dim|ffn|vocab'" 2>&1
```

派生値を計算し 1586 に近い値を列挙する:
- `n_embd × k` / `head_dim × k` / `ffn_dim × k` で 1586 近傍を取る係数 k を探す
- `sqrt(some_size × 32768)` 型も試す
- GDN 状態サイズから `1586 = state_size / some_factor` の可能性

#### Step 2: スケジューラのバッファ確保パス解析（約 15 分）

対象ファイル:
- `ggml/src/ggml-backend.cpp` (`ggml_backend_sched_reserve`, `ggml_backend_sched_split_graph`)
- `src/llama-context.cpp` (`graph_reserve`, `build_context` 相当)
- `src/llama-graph.cpp` (attention/ffn/moe/GDN build 関数)
- `src/llama-memory-hybrid.cpp` / `src/llama-memory-recurrent.cpp` (GDN/Mamba state)

grep パターン:
- `n_tokens\s*[<>=!]+` (n_tokens との比較)
- `n_ubatch\s*[<>=!]+`
- `n_tokens\s*\*` (tensor サイズ計算)
- `GGML_PAD` / `pad_to` (アラインメント適用箇所)
- `std::max\|std::min.*n_tokens`

Explore subagent で並列に調査して、1586 を生む式を含む候補箇所を特定する。

#### Step 3: GDN/Mamba chunk 化ロジックの深掘り（約 15 分）

Qwen3.5 は Gated Delta Net を持つハイブリッドアーキテクチャのため、RS buffer が存在する。GDN は通常 chunk-wise scan で処理され、chunk_size が閾値を生む可能性が高い。

対象ファイル:
- `src/llama-memory-recurrent.*`
- `src/llama-model.cpp`（アーキテクチャ定義）
- `ggml/src/ggml-cuda/` 下の mamba/delta-net カーネル

chunk_size × k が 1586 に一致するか、`ceil_div(n_tokens, chunk_size) × chunk_size` の二段階境界が 1586 にあたるかを検証する。

#### Step 4: flash-attention staging 候補（約 10 分）

境界が `fa=1` 条件下で出現しているため、FA のタイル化ロジックも候補:
- `ggml/src/ggml-cuda/fattn*.cu` で block/tile サイズの閾値
- FA では通常 Q/K/V のタイル列数に依存して shared memory 確保が変化する

### 成功判定

以下のいずれかを達成したら Phase Sb-src は成功:

1. **決定的特定**: ソース上で 1586 を生む計算式を exact に同定（slope 0.2853 も同じ式で説明）
2. **候補絞り込み**: 候補式を 1-3 個に絞り、それぞれを検証できる次 Phase の実験プランを提示
3. **否定的結論**: `llama.cpp` 単体では 1586 が生まれないことを示す（例: モデル固有の ffn / MoE expert 配分で決まる、ハードウェア側 cuBLAS の内部動作など）

### 境界 slope 0.2853 MiB/token の検証

`ub ≥ 1586` 域で +1 ub-token ごとに +0.2853 MiB ( = +292 KiB ) 確保される。この値が何に相当するか:

- f16 で 292 KiB = 149,504 バイト / 2 = 74,752 要素
- これが `head_dim × n_head_kv × layer_per_GPU` などに相当するか
- 74,752 = 2^10 × 73 or 128 × 584 or 256 × 292 等の因数分解

この検算を併せて実施する。

## 作業手順

### 実行フロー

```bash
# 1. 調査作業ディレクトリ作成（GPU ロック不要）
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_NAME="${TS}_qwen3-122b-c3-phaseSbsrc-threshold-hunt"
PHASE_DIR="report/attachment/${REPORT_NAME}"
mkdir -p "$PHASE_DIR"

# 2. モデル hparams 取得 (Step 1)
ssh t120h-p100 "./llama.cpp/build/bin/llama-gguf <gguf-path> 2>&1 | head -200" > "$PHASE_DIR/hparams.txt"
# 既存の起動ログからも hparams を抽出可能（compute_buffer_summary.txt の周辺）

# 3. 並列 grep / コード探索 (Step 2-4)
# Explore subagent で以下を並列実施:
# - ggml-backend.cpp / llama-context.cpp の graph_reserve 系
# - llama-graph.cpp の build_attn / build_moe / build_gdn 系
# - llama-memory-recurrent.* の GDN chunk
# 結果を PHASE_DIR/*.txt に保存

# 4. 導出式の数値検証（Python）
python3 <<'EOF' > "$PHASE_DIR/derivation_check.txt"
# Step 1 で得た hparams と候補式から 1586 を導出し、slope 0.2853 も確認
# 例:
#   hidden_dim=6144, head_dim=128, n_head_kv=8, n_layer_per_gpu=12
#   slope/token = head_dim * n_head_kv * n_layer_per_gpu * 2 (f16) / 1024 / 1024
#              = 128 * 8 * 12 * 2 / 1024 / 1024 = 0.0234 MiB
#   → slope 0.2853 と合わない → 別の式
EOF

# 5. レポート作成（添付プラン、探索ログ、検算結果）
cat > "report/${REPORT_NAME}.md" <<'EOF'
# Phase Sb-src: llama.cpp scheduler 閾値 ub*=1586 のソース特定
...（下記レポート構成）
EOF
```

### 所要時間

- Step 1 (hparams 取得): 5 分
- Step 2 (scheduler/graph 探索): 15 分（Explore subagent 並列）
- Step 3 (GDN/Mamba chunk): 15 分
- Step 4 (FA staging): 10 分
- 数値検算 + レポート作成: 15 分
- **合計: 約 1 時間**（GPU ロック不要）

## 変更 / 作成するファイル

### 作成
- `report/<TS>_qwen3-122b-c3-phaseSbsrc-threshold-hunt.md`: 本 Phase のレポート（未検証事項 / 検証完了後 TODO を含む）
- `report/attachment/<REPORT_NAME>/plan.md`: 本プランファイルをコピー
- `report/attachment/<REPORT_NAME>/hparams.txt`: モデル hparams
- `report/attachment/<REPORT_NAME>/grep_results.txt`: scheduler / graph / memory 系のコード grep 結果
- `report/attachment/<REPORT_NAME>/candidate_formulas.md`: 1586 候補式一覧と検算
- `report/attachment/<REPORT_NAME>/derivation_check.py` + `.txt`: 候補式の数値検証スクリプトと結果

### 変更
- なし（読み取り専用 Phase、skill / CLAUDE.md 更新は「未検証事項」に記載して次 Phase へ）

## 参照する既存ファイル・関数

- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`: 本 Phase は **不要**（読み取りのみ）
- 直前レポート: `report/2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok.md`
- llama.cpp ソース on t120h-p100: `~/llama.cpp` (commit 6990e2f1)
  - `ggml/src/ggml-backend.cpp`: `ggml_backend_sched_reserve` / `ggml_backend_sched_alloc_graph`
  - `src/llama-graph.cpp`: `llm_build_*` 関数群
  - `src/llama-context.cpp`: `graph_reserve`
  - `src/llama-memory-hybrid*.cpp` / `src/llama-memory-recurrent.*`: GDN/Mamba state
  - `ggml/src/ggml-cuda/fattn-*.cu`: flash-attention カーネル

## レポート構成（事前設計）

```markdown
# Phase Sb-src: llama.cpp scheduler 閾値 ub*=1586 のソース特定

- 実施日時
- 添付ファイル（plan.md, hparams.txt, grep_results.txt, candidate_formulas.md, derivation_check.py/txt）
- 参照（直前レポート Phase Sb-fine3）
- 前提・目的（Phase Sb-fine3 の ub*=1586 を受けたソース特定）
- 環境情報（llama.cpp commit, モデル, サーバ）
- 再現方法（grep コマンド一覧、検算スクリプト）
- 調査結果:
  1. モデル hparams サマリ
  2. scheduler コードパス（ggml_backend_sched_reserve → build graph → reserve）
  3. 候補式一覧と数値検算
  4. 最有力候補とその根拠
  5. slope 0.2853 MiB/token の同時説明可否
- 結論: 特定/絞り込み/否定のいずれか
- 未検証事項（本 Phase で潰せなかった項目 + 次 Phase へ繰越し分）
- 検証完了後に実施すべき TODO（skill / CLAUDE.md 更新、次 Phase 候補）
```

## 検証（end-to-end）

- [ ] `report/<REPORT_NAME>.md` が REPORT.md のルール（日時、JST、再現方法、環境情報、添付）に準拠
- [ ] `plan.md` が `report/attachment/<REPORT_NAME>/` にコピーされている
- [ ] `hparams.txt` にモデルの主要パラメータ（n_embd, n_head, n_head_kv, head_dim, n_layer, n_expert, ffn_dim）が含まれる
- [ ] `grep_results.txt` が主要対象ファイル（ggml-backend.cpp, llama-graph.cpp, llama-context.cpp, llama-memory-*.cpp）を網羅
- [ ] `candidate_formulas.md` に候補式が最低 3 件列挙され、各々について 1586 と slope 0.2853 の一致度が数値検証されている
- [ ] 結論セクションで「特定 / 絞り込み / 否定」のいずれかを明示
- [ ] 未検証事項 / TODO セクションが直前レポート Phase Sb-fine3 の形式に沿って列挙されている
- [ ] 本 Phase で GPU ロックは取得していない（読み取り専用）ことをレポートに明記

## 留意点

- ssh 経由の `grep` / `find` は Bash ツールで実行する（リモート実行なので Grep ツールは使えない）
- 大量の grep 出力は Explore subagent に委譲して parent context を保護する
- 1586 の由来が「llama.cpp ソース単体では説明できない」という否定的結論も十分ありうる。その場合も価値ある結論であり、次 Phase（GDN chunk の実測 / cuBLAS ワークスペースのプロファイル等）へ繋ぐ
- 本 Phase が成功した場合、次 Phase（Phase Sb-ctx-boundary: 境界 ub\* の ctx 依存性、Phase S-eval: ub=1586 5-10 run 再現性）に優先順位が上がる
