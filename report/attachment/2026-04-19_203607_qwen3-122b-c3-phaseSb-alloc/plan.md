# Phase Sb-alloc: ggml-alloc.c による境界 ub*=1586 真因特定

## Context

直前レポート [2026-04-19_192631_qwen3-122b-c3-phaseSbsrc-threshold-hunt.md](../../projects/llm-server-ops/report/2026-04-19_192631_qwen3-122b-c3-phaseSbsrc-threshold-hunt.md) の「未検証事項 / 新規項目」最優先 ★★★:

> **`ggml/src/ggml-alloc.c` の pool quantization ロジック詳細解析** — `ggml_tallocr_alloc` / `ggml_backend_sched_alloc_graph` での具体的な境界算出（block size, alignment, padding）の特定。候補 D を完全検証するため必須。

本 Phase はレポート末尾の「次の推奨 Phase」筆頭（Phase Sb-alloc, 読取 1-2 時間、GPU ロック不要）に該当。

### 事前調査で判明した重要事実（Explore サブエージェントによる）

- **非VMM pool**: `ggml-cuda.cu:422` で `look_ahead_size = 256 * ((look_ahead_size + 255)/256)` ⇒ **256 bytes 量子化**
- **VMM pool**: `ggml-cuda.cu:L504-509` で `cuMemGetAllocationGranularity()` の値（典型 2 MiB）で量子化
- **tensor alignment**: `ggml-cuda.cu:772-776` で `ggml_backend_cuda_buffer_type_get_alignment() return 128` ⇒ **128 bytes**
- `ggml-alloc.c:201-303` `ggml_dyn_tallocr_alloc()` では `chunk->max_size = MAX(chunk->max_size, offset + size)` で更新、`ggml-alloc.c:916-919` で `new_size += new_chunk_size` 集計
- **結論**: allocator レイヤには「1 MiB 境界」は存在しない ⇒ **Phase Sb-src の候補 D (1 MiB pool 量子化) は棄却される可能性が高い**

### なぜこの Phase が必要か

- 候補 D 否定で、境界 ub*=1586 の真因は **allocator 以外のレイヤ**（graph build / fused GDN kernel / memory recurrent 管理 / tensor shape の離散化）にある
- slope 0.2853 MiB/tok 由来は既に 98.6% 特定済（Phase Sb-src）、残るは**境界位置を生む step 機構**の同定
- 今回は読取専用で GPU ロック不要、本発見の後に Phase Sb-ctx-boundary (GPU ロック) で実測検証へ接続

## 実施手順

### Step 1: 本 Phase 作業ディレクトリとログ準備

```bash
WORKDIR=/tmp/phase-sb-alloc
mkdir -p $WORKDIR
cd $WORKDIR
```

ローカルミラー `/tmp/llama-cpp-src` が存続していることを確認（直前 Phase Sb-src の生成物）。無ければ rsync で再ミラーリング。

### Step 2: allocator 層の数値検証（候補 D 否定の確証）

Phase Sb-src で観測された per-layer 53.5625 MiB × 9 層 = 482.0625 MiB を、以下の 3 量子化単位でシミュレート：

- 128 B alignment（tensor）
- 256 B pool (非VMM)
- 2 MiB VMM granularity（假定値）

ub=1584, 1585, 1586, 1588, 1600 の 5 条件で各量子化単位適用後の合計を算出し、1585→1586 遷移が step にならないことを数値確認。Python スクリプト `alloc_sim.py` を作成。

### Step 3: graph build 側の候補探索（真因候補の拾い出し）

Phase Sb-src のローカルミラー `/tmp/llama-cpp-src/` を次の観点で再精査（既に file:line は特定済、今回は**境界を生む分岐**を重点的に読む）：

1. **候補 E: fused GDN CUDA kernel の内部 tile 境界**
   - `ggml/src/ggml-cuda/gated_delta_net.cu` の block/grid 計算、shared memory 分岐
   - `attn_score_elems = S_v*H*n_tokens*n_seqs` が何らかの閾値でアルゴリズム経路を切り替えるか
   - ub の丸め: `n_tokens` が block_size の倍数に切り上げられる箇所

2. **候補 F: graph_reserve の worst-case ubatch 処理**
   - `src/llama-context.cpp` の `graph_reserve` 呼び出し、worst-case sub-batch の決定（`n_ubatch` / `n_tokens` 渡し）
   - `llama_ubatch` struct に伸縮する何かがあるか

3. **候補 G: memory_recurrent （RS buffer）の ub 依存成分**
   - Phase Sb-src で確認した `R (f32): 5.06 MiB, S (f32): 144.00 MiB, 48 layers` の他に、**ub に応じて伸びる** intermediate tensor
   - `llama-memory-recurrent.cpp` で prefill/rollup 時の tensor 確保

4. **候補 H: graph splits の境界**
   - 起動ログに `graph splits = 77` と記録がある（Phase Q/S で観測）
   - splits 数が ub 閾値で変化する可能性、`ggml_backend_sched_split_graph` を精読

### Step 4: 候補評価マトリクスと数値テスト

各候補を以下で評価：

| 候補 | step 機構を生むか | ub=1586 境界位置との整合 | 追加検証方法 |
|---|---|---|---|
| D (棄却候補) | × (256B/128B は細かすぎ) | × | 本 Phase で形式的棄却 |
| E (GDN tile) | ? | ? | kernel ソースの block size 読み |
| F (graph_reserve) | ? | ? | context build 経路の再読 |
| G (recurrent) | ? | ? | mem-r ソースの ub 依存成分確認 |
| H (splits) | ? | ? | splits=77 の生成ロジック追跡 |

評価の結果、最有力候補 1-2 個に絞り込む。

### Step 5: runtime ログ再解析（VMM / 非VMM 判定）

Phase Sb-fine3 の startup_log `report/attachment/2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok/startup_logs/fa1_ctx32768_b1586_ub1586.log` を再読し、以下を確認：

- `ggml_cuda_init` 時点で VMM が有効か無効か（通常 log に "CUDA_VISIBLE_DEVICES" 等と同時に VMM flag が出る）
- `CUDA0 compute buffer size` の報告値 1002.61 MiB が chunk 合計か buffer_size 合計か

読取監視は GPU ロック不要（CLAUDE.md 明記）。ログは既にローカルに添付済なので ssh も不要。

### Step 6: 次 Phase 提案

本 Phase の絞り込み結果に応じて、以下を提案：

- **候補 E が有力**: Phase Sb-kernel (nvprof/ncu で GDN kernel 起動時 grid/block dim 計測、GPU ロック要、30 分)
- **候補 F/G が有力**: Phase Sb-ctx-boundary (ctx=16k/65k × ub=1584-1586 で境界の ctx 依存性計測、GPU ロック要、1.5 時間)
- **候補 H が有力**: Phase Sb-splits (ub sweep で graph splits 数の出力を採取、GPU ロック要、40 分)

### Step 7: レポート作成

`report/2026-04-19_<HHMMSS>_qwen3-122b-c3-phaseSb-alloc.md` に直前レポートと同じフォーマットで作成：

- 実施日時（JST）、作業種別、GPU ロック（未取得）
- 添付ファイル（plan.md, alloc_sim.py, 数値検証 csv, source grep 結果）
- 前提・目的、環境情報、再現方法
- 実行結果サマリ（候補 D 棄却、候補 E/F/G/H の評価）
- 採用判定
- **未検証事項** セクション（Phase Sb-src から継続 + 本 Phase 新規）
- **検証完了後に実施すべき TODO** セクション
- 補足（核心発見サマリ、次 Phase 提案）

## 対象ファイル（変更なし、読取のみ）

| 優先 | パス | 目的 |
|---|---|---|
| ★★★ | `/tmp/llama-cpp-src/ggml/src/ggml-alloc.c` | chunk 管理・境界算出 |
| ★★★ | `/tmp/llama-cpp-src/ggml/src/ggml-cuda/ggml-cuda.cu` | 256B/VMM pool 量子化 |
| ★★★ | `/tmp/llama-cpp-src/ggml/src/ggml-cuda/gated_delta_net.cu` | 候補 E 検証 |
| ★★ | `/tmp/llama-cpp-src/src/llama-context.cpp` | graph_reserve 経路 (候補 F) |
| ★★ | `/tmp/llama-cpp-src/src/llama-memory-recurrent.cpp` | 候補 G (RS buffer の ub 依存性) |
| ★ | `/tmp/llama-cpp-src/ggml/src/ggml-backend.cpp` | sched split / splits=77 (候補 H) |
| ★ | `/tmp/llama-cpp-src/ggml/src/ggml-backend-impl.h` | buffer_type / alloc_size API |

## 生成物

- `plan.md` (本ファイルをコピー)
- `alloc_sim.py` / `alloc_sim.csv` (Step 2 の数値検証)
- `grep_results.txt` (Step 3 の候補 E/F/G/H の file:line 集約)
- `candidate_matrix.md` (Step 4 の候補評価表)
- `runtime_log_vmm_check.txt` (Step 5 の VMM/非VMM 判定抜粋)

## 検証方法（エンドツーエンド）

1. `alloc_sim.py` を `python3` で実行 → 期待: ub=1585→1586 で 256B/128B/2MiB いずれの量子化でも step 発生しないことを数値確認
2. `grep_results.txt` に候補 E/F/G/H 各 1 個以上の file:line が記録されていること
3. `candidate_matrix.md` で最有力候補 1-2 個に絞り込みされていること
4. レポートの「採用判定」セクションで「候補 D 棄却」と「次 Phase 提案」が明示されていること

## GPU ロック

**不要**。本 Phase は完全読取専用（ローカルミラーと過去のログのみ参照）。t120h-p100 への ssh は行わない（または監視用途のみ）。

## 所要時間

1-2 時間見積（レポート作成を含む）。

## 成功条件

- [ ] 候補 D (1 MiB pool 量子化) が allocator レイヤ由来ではないことの数値/コード証拠
- [ ] 候補 E/F/G/H のうち少なくとも 1 つの最有力候補を提示
- [ ] 次 Phase（GPU ロック要の実測 Phase）の方向性を明示
- [ ] レポートに「未検証事項」「検証完了後に実施すべき TODO」セクションあり
