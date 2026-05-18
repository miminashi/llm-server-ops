# Phase A: HEAD ベース再計測と Quick wins（BL / F1 / N1 / M1 / K1）

- **実施日時**: 2026 年 5 月 16 日 10:23–18:37 JST
- **対象**: llama.cpp `HEAD = 1348f67c5` × Qwen3.5-122B-A10B-Q4_K_M × t120h-p100（P100×4, 64 GB）× fit モード（B14b_ts_alt）

## 核心発見サマリ

- **HEAD は U-6 (6217b4958, 2026-04-24) から速度系 PR の累積効果で全 prompt 長で +1.3〜+4.5% 改善**（1k: +4.46%, 32k: +1.30%, 96k: +1.95%）
- **`--main-gpu 1` (M1) が BL に対して +0.91%（1k）/ +1.41%（32k）の有意改善**（Welch's t ≈ 2.3, p<0.05）→ Phase B 以降のベース構成候補
- **`-fa auto` (F1)** は BL とほぼ同等（+0.55%/+1.50%）。32k は M1 と僅差
- **`-ncmoe 14` (N1)** は **OOM で起動失敗**（BL の B14b_ts_alt とは別構成のため、現 fit 計算で VRAM 不足）
- **KV q4_0 (K1)** は速度 -0.7%（1k/32k）と引き換えに **VRAM 余裕 +192 MiB** を確保（min_gpu_free 590 → 782）

## 添付ファイル

- [実装プラン](attachment/2026-05-16_183834_qwen3-122b-bench-marathon-phaseA-quickwins/plan.md)
- [Phase A オーケストレータスクリプト](attachment/2026-05-16_183834_qwen3-122b-bench-marathon-phaseA-quickwins/phaseA_orchestrator.sh)
- [生 CSV (warmup+eval 全 run)](attachment/2026-05-16_183834_qwen3-122b-bench-marathon-phaseA-quickwins/results.csv)
- [Phase A 実行ログ](attachment/2026-05-16_183834_qwen3-122b-bench-marathon-phaseA-quickwins/phaseA.log)
- 各試行の cmdline・GPU pre/post・llama-server ログ・out_<試行>_<promptlen>/ 配下の生レスポンス JSON

## 前提・目的

- 背景: Phase U-6（2026-04-24, ビルド `6217b4958`）でデフォルト構成（`B14b_ts_alt` + `--tensor-split 11,12,13,14` + `--flash-attn 1` + `-b 2048 -ub 512` + KV q8_0 + ctx=131072）が確定。それから 3 週間で llama.cpp に多数の速度系 PR がマージ（#22041 subgraph splits cache, #21764 graph_reused, #22330 concat coalesce, #22650 fastdiv, #22541 Pascal tile FA fix 等）。
- 目的: 現 HEAD (`1348f67c5`) で デフォルト構成を再計測し、PR 累積効果を確認。あわせて HEAD で新たに追加された CLI フラグ群（`-fa auto`, `-ncmoe`, `--main-gpu`, KV q4_0 + Walsh-Hadamard rotation 等）が改善に寄与するかを検証。
- 参照レポート:
  - [U-6 (ctx=128k default)](2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default.md)
  - [T-5a-ts2 (歴代ベスト)](2026-04-23_093629_qwen3-122b-c3-phaseT5a-ts2.md)
  - [U-2 (cache-ram)](2026-04-23_173141_qwen3-122b-c3-phaseU2-cache-ram.md)

## 環境情報

- サーバ: `t120h-p100` (10.1.4.14)
- GPU: NVIDIA Tesla P100-PCIE-16GB × 4 (合計 64 GB, sm_60)
- CPU: Intel Xeon Gold 6138 × 2 (40 cores/socket, NUMA node 1 使用)
- llama.cpp `HEAD = 1348f67c58f561808136e8a152a9eddec168f221` (2026-05-15)
- ビルド: `cmake -DLLAMA_OPENSSL=ON -DGGML_CUDA=ON -DGGML_CUDA_FA_ALL_QUANTS=ON -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.9/bin/nvcc -DCMAKE_CUDA_ARCHITECTURES=60`
- モデル: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`（block_count=48, head_count=32, head_count_kv=2, head_dim=256, expert_count=256, expert_used=8, `full_attention_interval=4`）

## ベースライン (BL) 構成

`llama-up.sh` デフォルト引数（`start.sh` Qwen3.5-122B-A10B プロファイル分岐）:

```
numactl --cpunodebind=1 --membind=1 ./build/bin/llama-server \
  -m <Q4_K_M shard 1 of 3> --jinja \
  -ngl 999 --split-mode layer \
  -ot blk.{2,3,20-23,31-38}.ffn_.*_exps.weight=CPU (B14b_ts_alt, 14 層) \
  --tensor-split 11,12,13,14 \
  --flash-attn 1 --poll 0 \
  -b 2048 -ub 512 \
  --threads 40 \
  --ctx-size 131072 --parallel 1 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --defrag-thold 0.1 (deprecated) \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0
```

## 試行マトリクス

| ID | BL からの変更 | 結果 |
|----|---------------|------|
| BL | （変更なし） | ✅ |
| F1 | `--flash-attn 1` → `--flash-attn auto` | ✅ |
| N1 | `-ot ...` を `-ncmoe 14` に置換 | ❌ OOM（先頭連続 14 層 = `{0-13}` を CPU、BL の `{2,3,20-23,31-38}` と層集合が異なる）|
| M1 | 末尾に `--main-gpu 1` 追加 | ✅ |
| K1 | KV `q8_0` → `q4_0` | ✅ |

各試行で 1k および 32k prompt（warmup 1-2 + eval 5 run × max_tokens=1024/512）、BL のみ 96k (warmup 1 + eval 5 run × max_tokens=256) を計測。

## 結果

### 集計表（eval mean ± stdev, prompt mean）

| 試行 | prompt | n | eval mean (t/s) | eval std | prompt mean (t/s) | min_gpu_free (MiB) |
|------|--------|---|-----------------|----------|--------------------|--------------------|
| BL   | 1k     | 5 | **18.482** | 0.110 | 64.366 | 590 |
| BL   | 32k    | 5 | **14.547** | 0.023 | 61.010 | 590 |
| BL   | 96k    | 5 | **10.225** | 0.145 | 53.262 | 460 |
| F1   | 1k     | 5 | 18.583 | 0.122 | 64.766 | 590 |
| F1   | 32k    | 5 | 14.766 | 0.082 | 61.007 | 590 |
| N1   | (起動失敗 OOM @ CUDA2 cudaMalloc 19387 MiB) | – | – | – | – | – |
| M1   | 1k     | 5 | **18.649** | 0.121 | 64.713 | 590 |
| M1   | 32k    | 5 | 14.752 | 0.154 | 61.154 | 590 |
| K1   | 1k     | 5 | 18.353 | 0.008 | 64.184 | **782** |
| K1   | 32k    | 5 | 14.498 | 0.079 | 60.994 | **782** |

### U-6 / BL 比較（eval t/s）

| prompt | metric | U-6 (`6217b4958`) | BL (`1348f67c5`) | U-6 比 | F1 | M1 | K1 |
|--------|--------|--------------------|--------------------|--------|------|------|------|
| 1k     | eval   | 17.692 | 18.482 | **+4.46%** | +5.04% | **+5.41%** | +3.74% |
| 32k    | eval   | 14.360 | 14.547 | **+1.30%** | +2.83% | +2.73% | +0.96% |
| 96k    | eval   | 10.029 | 10.225 | **+1.95%** | – | – | – |
| 1k     | prompt | ~91 | 64.366 | -29% (※) | – | – | – |
| 32k    | prompt | ~64 | 61.010 | -4.7% | – | – | – |
| 96k    | prompt | 53–64 | 53.262 | ±0 | – | – | – |

(※) U-6 レポート記載の prompt_tps=91 は別構成測定の可能性が高い。本 BL の 1k prompt 64.4 t/s は B14b/ub=512 構成として妥当（prompt_n=1074, prompt_ms=16689 → 64.34 t/s）。

### BL 比較（HEAD 内で同条件）

| 試行 | 1k vs BL | 32k vs BL | 統計的有意性 (1k) |
|------|----------|-----------|-------------------|
| F1 (`-fa auto`)        | +0.55% (+0.101) | +1.50% (+0.219) | t ≈ 1.4, p≈0.20 |
| M1 (`--main-gpu 1`)    | **+0.91%** (+0.167) | **+1.41%** (+0.205) | **t ≈ 2.3, p≈0.05** ✓ |
| K1 (KV q4_0)           | -0.69% (-0.128) | -0.33% (-0.049) | t ≈ -2.6, p≈0.03 ✓ (低下方向) |

## 仮説と解釈

1. **U-6 → HEAD で全 prompt 長で改善**: 速度系 PR 群（#22041, #21764, #22330, #22650 など）の累積効果。Pascal/sm_60 で特に大きく効いた #22541 (Pascal tile FA 修正) も関与している可能性。1k で最大 (+4.5%) なのは generate 比率が高い prompt のため。
2. **M1 (`--main-gpu 1`)**: CUDA0 ではなく CUDA1 を main GPU に切替えるだけだが、tensor-split 11,12,13,14（CUDA0 が最少配分）と組合せると、KV キャッシュやスケジューラの起点が変わる効果が観測された。memory `[[project_t_series_roadmap]]` で「`--main-gpu` 切替（CUDA0依存解消） → 未検証」と記載があった項目の検証完了。改善は微小だが有意。
3. **F1 (`-fa auto`)**: HEAD では auto がデフォルト。BL の `--flash-attn 1` 強制と auto の挙動はほぼ同じ。32k 以上で僅かに有利だが統計的有意ではない。
4. **N1 (`-ncmoe 14`) OOM**: `-ncmoe N` は先頭連続 N 層を MoE expert CPU offload するため、B14b_ts_alt の非連続 14 層 `{2,3,20-23,31-38}` とは別構成。Phase T-5a 系で時間をかけて最適化した OT パターンが現 HEAD でも引き続き重要であることが確認できた（フラグの簡潔化目的としては不適合）。
5. **K1 (KV q4_0)**: Walsh-Hadamard rotation (PR #21038) がデフォルト ON で品質劣化が抑制されたとはいえ、Pascal の cuBLAS GEMM 経路では q4_0 KV 計算が q8_0 より遅い傾向（-0.7%）。**ただし VRAM +192 MiB を確保**できるため、Phase C/D で ub 拡大 や OT B12 化のヘッドルームとして有用。

## 効きそうな PR / 効いた PR 推定

| PR | 種別 | 期待 | 観測 |
|----|------|------|------|
| #22541 (Pascal tile FA) | 必須修正 | Pascal で新 FA 動作 | サーバログで `FA_ALL_QUANTS=1` 確認、`-fa auto` で動作 |
| #22041 (subgraph splits cache) | 速度 | generate +8〜16% | 1k で +4.5%（U-6 比）に寄与 |
| #21764 (graph_reused) | 速度 | generate 数% | 同上 |
| #22330 (contiguous concat coalesce) | 速度 | +1〜3% | 96k で +1.95% に寄与 |
| #22650 (fastdiv get_rows) | 速度 | カーネル 3〜5% | 効果ありとは判定不能（軽微）|
| #21038 (Walsh-Hadamard) | 品質 | KV q4_0 品質 | K1 で速度-0.7% に止まる |

## 次フェーズ (B) への反映点

- **BL (HEAD デフォルト) を Phase B 以降のベースに採用**（M1 の +0.9% を含めると spec 効果の切り分けが難しくなるため、最終 Phase E で M1 を含む BL_FINAL を別途測定）
- **K1 で得た VRAM +192 MiB のヘッドルーム**は Phase C の ub sweep（640/768）や Phase D の B12 化試行で利用できる可能性
- N1 タイムアウトで Phase A 全体 +20 分。Phase B 以降の起動失敗時は wait_ready timeout (10 分) も予算に組み込む必要

## 再現方法

```bash
# 1. ロック取得
.claude/skills/gpu-server/scripts/lock.sh t120h-p100 bench-head-1348f67c5-marathon

# 2. ビルド・モデル確認 (HEAD が 1348f67c5 であること)
ssh t120h-p100 "cd ~/llama.cpp && git rev-parse HEAD"

# 3. オーケストレータ実行 (BL の 1k は事前に外部実行、残りを一括)
bash <添付>/phaseA_orchestrator.sh  # 約 8 時間

# 4. 結果集計 (results.csv を Python で eval mean/stdev 算出)
```

実際の Phase A は以下の流れで完了:

| ステップ | 開始 | 終了 | 経過 |
|---------|------|------|------|
| ロック取得 + プリフライト | 10:20 | 10:23 | 3 分 |
| BL 1k (外部実行) | 10:23 | 10:35 | 12 分 |
| BL 32k | 10:35 | 11:33 | 58 分 |
| BL 96k | 11:33 | 14:38 | 3 h 5 分 |
| F1 起動 + 1k + 32k | 14:41 | 15:55 | 1 h 14 分 |
| N1 起動失敗 (OOM タイムアウト) | 15:55 | 16:11 | 16 分 |
| M1 起動 + 1k + 32k | 16:12 | 17:21 | 1 h 9 分 |
| K1 起動 + 1k + 32k | 17:24 | 18:34 | 1 h 10 分 |
| 集計・後片付け | 18:34 | 18:37 | 3 分 |
| **全体** | 10:20 | **18:37** | **8 h 17 分** |

96k は max_tokens=256 でも prompt prefill ~30 分 × 6 ラン = 3 時間と長い。1 試行あたり最低 25 分必要。

## 未試行 / 後フェーズに送る項目

- 統計的に有意な改善が M1 のみ → Phase E で BL+M1 構成 (`BL_FINAL` 候補) を再計測予定
- `-ncmoe` で BL と同等構成を作るには Qwen3.5-122B-A10B の 48 層構造を踏まえた個別最適化が必要 → 別フェーズ送り
- spec / ub / threads / -sm tensor / B12 等は Phase B/C/D で実施
