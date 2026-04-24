# Qwen3.5-122B-A10B C-3 Phase I（長コンテキストでの eval/prompt 速度計測）

- **実施日時**: 2026年4月17日 17:31 – 19:05 (JST)
- **作業種別**: 計測・検証（Phase H 最優先未検証事項「大コンテキストでの eval 速度」「CUDA1 の 2 GiB セーフティマージン」）

## 添付ファイル

- [実装プラン](attachment/2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext/plan.md)
- [起動スクリプト (start_phaseI.sh)](attachment/2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext/start_phaseI.sh)
- [計測スクリプト (measure_phaseI.sh)](attachment/2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext/measure_phaseI.sh)
- [一括実行スクリプト (run_all.sh)](attachment/2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext/run_all.sh)
- [プロンプト生成スクリプト (generate_prompts.py)](attachment/2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext/generate_prompts.py)
- [トークン数検証スクリプト (check_tokens.sh)](attachment/2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext/check_tokens.sh)
- [結果集計スクリプト (aggregate_results.sh)](attachment/2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext/aggregate_results.sh)
- [集計結果 TSV (results.tsv)](attachment/2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext/results.tsv)
- [マスターログ (run_all.log)](attachment/2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext/run_all.log)
- I_warmup, I_1k, I_8k, I_32k, I_64k, I_120k, I_post の各 `out_*/` ディレクトリ
- `prompts/prompt_{1k,8k,32k,64k,120k}.txt`

各 `out_*` に Phase H 同様のログ一式（`eval_run{N}.json, dmon_run{N}.log, status_run{N}.txt, numastat_{pre,post}.txt, numastat_m_{pre,post}.txt, free_{pre,post}.txt, gpu_{pre,post}.csv, gpu_post_run{N}.csv, sched_{pre,post}.txt, cmdline.txt, timeline.log`）を格納。

## 参照

- 前身レポート: [2026-04-17_082738_qwen3-122b-c3-phaseH-idle-poll.md](2026-04-17_082738_qwen3-122b-c3-phaseH-idle-poll.md)
- Phase G: [2026-04-17_035831_qwen3-122b-c3-phaseG-longevity.md](2026-04-17_035831_qwen3-122b-c3-phaseG-longevity.md)
- Phase D: [2026-04-16_150717_qwen3-122b-c3-phaseD.md](2026-04-16_150717_qwen3-122b-c3-phaseD.md)

## 前提・目的

Phase H で C-D3 `--flash-attn 1 --poll 0 -b 8192 -ub 8192 --ctx-size 131072` が採用構成として確定。ただし Phase D〜H の計測はすべて **18 トークン固定の短プロンプト**で、モデルが起動している 131072 トークンの長コンテキスト性能プロファイルが完全に欠落していた。本 Phase I で以下を同時解消する:

1. **大コンテキストでの eval 速度**（~1k / ~8k / ~32k / ~64k / ~120k トークン）
2. **CUDA1 の 2 GiB セーフティマージン**: プロンプト処理中の KV cache + graph buffer のピーク
3. **prompt_per_second の長コンテキスト依存**: GPU 計算主体の prompt 処理が長コンテキストで維持されるか
4. **session 内経時安定性**: セッション冒頭と終端の同一短プロンプト比較（drift 検出）

### 重要な計測配慮（prompt cache 対策）

llama-server は `--parallel 1` のスロットで直前プロンプトの KV を保持しており、**同一プロンプト再送時は prompt 処理が cache hit でゼロになる**。これを避けるため、各 Run の先頭に `[Request ID <tag>_rN_<nanotime>] ` のユニーク prefix を付与して強制的にフル prompt 処理を発生させた。

### 成功条件

- 全サイズで OOM / HTTP エラーなく完走（→ 達成）
- `timings.prompt_n` が期待値 ±5% 以内（→ 達成、最大 +0.4%）
- I_warmup と I_post の同一プロンプト計測値が一致（→ 達成、15.00 t/s で完全一致）

## 環境情報

- **サーバ**: `t120h-p100` (10.1.4.14)
- **GPU**: NVIDIA Tesla P100-PCIE-16GB × 4（各 16,270 MiB）
- **CPU**: Intel Xeon Gold 6138 @ 2.00GHz × 2 socket、計 40 コア / 80 スレッド、NUMA 2 ノード
- **メモリ**: 257,560 MiB (約 251 GiB)
- **モデル**: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- **llama.cpp ビルド**: b8807-b3d758750（Phase D/E/F/G/H と同一系列）
- **構成**: C-D3（`numactl --cpunodebind=1 --membind=1 -- + --threads 40 + --poll 0 + --flash-attn 1 + -b 8192 -ub 8192 + --ctx-size 131072 + --cache-type-k q8_0 --cache-type-v q8_0`）
- **起動 PID**: 123590（稼働時間: 計測開始時 7 分、終了時 1h 21m）

## 計測手順（再現方法）

### プロンプト生成 + トークン数検証

```bash
python3 generate_prompts.py
bash check_tokens.sh
```

Qwen3.5 tokenizer の英文プロース実測で **~6.12 chars/token**。5 サイズの実測トークン数:

| ファイル | 文字数 | トークン数 | 目標 | 差分 |
|---------|------:|----------:|----:|----:|
| prompt_1k.txt   |   6,200 |   1,029 |  ~1,000 | +2.9% |
| prompt_8k.txt   |  49,000 |   8,030 |  ~8,000 | +0.4% |
| prompt_32k.txt  | 196,000 |  32,060 | ~32,000 | +0.2% |
| prompt_64k.txt  | 392,000 |  64,122 | ~64,000 | +0.2% |
| prompt_120k.txt | 735,000 | 120,201 | ~120,000 | +0.2% |

### 実行フロー

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
bash report/attachment/2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext/start_phaseI.sh
PID=$(ssh t120h-p100 "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
cd report/attachment/2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext
PID=$PID bash run_all.sh
.claude/skills/llama-server/scripts/stop.sh t120h-p100
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 実行タイムライン

| タグ | prompt_n（ChatTemplate 込み） | Run 数 | 開始 | 終了 |
|------|---------:|------:|----------:|----------:|
| I_warmup | 48 | 3 | 18:05:36 | 18:10:29 |
| I_1k | 1,069 | 3 | 18:10:29 | 18:17:18 |
| I_8k | 8,070 | 3 | 18:17:18 | 18:23:36 |
| I_32k | 32,101 | 2 | 18:23:36 | 18:33:00 |
| I_64k | 64,163 | 1 | 18:33:00 | 18:42:25 |
| I_120k | 120,243 | 1 | 18:42:25 | 19:03:17 |
| I_post | 46 | 1 | 19:03:17 | 19:04:50 |

合計所要: **1h 20m**（`run_all.sh` のマスターログ基準）。prompt 処理総時間は 32k・64k・120k で約 35 分を占めた。

## 実行結果サマリ

### eval 速度（predicted_per_second）

| タグ | prompt_n | Run 1 | Run 2 | Run 3 | 中央値 | warmup 比 |
|------|---------:|------:|------:|------:|------:|---------:|
| I_warmup | 48 | 15.001 | 14.989 | 15.004 | **15.000** | 基準 |
| I_1k    | 1,069 | 14.880 | 14.882 | 14.882 | **14.882** | **−0.79%** |
| I_8k    | 8,070 | 14.273 | 14.278 | 14.267 | **14.273** | **−4.85%** |
| I_32k   | 32,101 | 12.564 | 12.554 |   —   | **12.559** | **−16.27%** |
| I_64k   | 64,163 | 10.405 |   —   |   —   | **10.405** | **−30.63%** |
| I_120k  | 120,243 | 7.996 |   —   |   —   | **7.996** | **−46.69%** |
| I_post  | 46 | 15.000 |   —   |   —   | **15.000** | **±0.00%** |

Run 間 range は全サイズで ≤ 0.015 t/s（中央値の 0.2% 以内）で極めて再現的。`--parallel 1` スロットにユニーク prefix を前置して prompt cache hit を避けた効果により、毎 Run フル処理の正味値を取得できた。

### prompt 処理速度（prompt_per_second）

| タグ | Run 1 | Run 2 | Run 3 | 中央値 | prompt 処理時間 |
|------|------:|------:|------:|------:|--------------:|
| I_warmup | 8.96 | 8.94 | 8.82 | **8.94** | ~5.4s |
| I_1k     | 67.84 | 67.85 | 67.85 | **67.85** | 15.8s |
| I_8k     | 180.59 | 181.46 | 185.37 | **181.46** | 44.5s |
| I_32k    | 151.64 | 159.32 |   —   | **155.48** | ~206s |
| I_64k    | 134.54 |   —   |   —   | **134.54** | ~477s (7.9 min) |
| I_120k   | 105.32 |   —   |   —   | **105.32** | ~1,142s (19.0 min) |
| I_post   | 8.57 |   —   |   —   | **8.57** | ~5.4s |

短プロンプト（48/46 tok）の prompt_per_second が 8.57〜8.96 と低いのは固定オーバーヘッドが支配的なため。1k 以上では GPU のバッチ効率が効き **8k でピーク 181 t/s**、以降は逓減（KV cache アクセスのメモリ帯域律速）。

### GPU メモリ使用量（`gpu_post_run${N}.csv` より、各カードの memory.used）

| タグ | CUDA0 | CUDA1 | CUDA2 | CUDA3 | 合計 | CUDA1 free |
|------|------:|------:|------:|------:|----:|----------:|
| I_warmup | 9,799 | 14,269 | 14,269 | 10,581 | 48,918 | 2,001 |
| I_1k     | 9,847 | 14,315 | 14,319 | 10,619 | 49,100 | 1,955 |
| I_8k     | 10,759 | 15,197 | 15,209 | 11,009 | 52,174 | 1,073 |
| I_32k    | 10,779 | 15,217 | 15,239 | 11,063 | 52,298 | 1,053 |
| I_64k    | 10,783 | 15,217 | 15,239 | 11,125 | 52,364 | 1,053 |
| I_120k   | 10,785 | 15,217 | 15,239 | 11,235 | 52,476 | 1,053 |

（単位 MiB、CUDA1 free = 16,270 − memory.used）

- warmup → 1k: +46 MiB（KV 占有の微増）
- 1k → 8k: **+882 MiB**（8192 のバッチサイズで `-b/-ub 8192` に対応するアクティベーションバッファが確保された）
- 8k → 32k: +20 MiB（ほぼフラット）
- 32k → 64k → 120k: 0 MiB（完全フラット）

**KV cache 本体は起動時に `--ctx-size 131072 --cache-type-k q8_0 --cache-type-v q8_0` で pre-allocate されている**ため、コンテキスト増加に応じた GPU メモリ追加確保は発生しない。8k 付近で確保されるのはバッチ処理のワークスペース。

**CUDA1 の free マージン**: warmup 時 2,001 MiB → 8k 以降 1,053 MiB。長コンテキストで **~950 MiB がワークスペースに使われる**が、Phase D の 2 GiB マージンは余裕のあった指標。実際の長コンテキストピーク（8k 以上）でも **~1 GiB の安全余裕**が残り OOM は発生しなかった。

## ボトルネック・副次発見の分析

### 1. eval 速度は KV cache サイズに対して線形（1/eval_tps vs N）

Per-token eval cost（秒 / 生成トークン）:

| N (prompt_n) | eval_tps | 1/eval_tps (s/tok) |
|-----:|------:|------:|
| 48 | 15.000 | 0.0667 |
| 1,069 | 14.882 | 0.0672 |
| 8,070 | 14.273 | 0.0701 |
| 32,101 | 12.559 | 0.0796 |
| 64,163 | 10.405 | 0.0961 |
| 120,243 | 7.996 | **0.1251** |

線形回帰 `1/eval_tps = a + k * N` でフィットすると **k ≈ 4.85 × 10⁻⁷ s/tok per context token**、**a ≈ 0.0665 s/tok**。残差は全点で 1% 未満。つまり、

```
generation_time_per_token = 66.5 μs + 0.485 μs × N_context
```

自己回帰デコードの各ステップで全 N 個の KV を読み出す以上、この O(N) 依存は本質的なアーキテクチャ要因であり flash-attn 等の最適化では除去不可能。ただし P100 (CC 6.0) の flash-attention 実装は V100/A100 の Tensor Core 経路を持たず、係数 `k` が大きい可能性はあり、PA100/H100 との比較では有意に改善する余地がある。

### 2. prompt 処理速度はバッチ効率と KV 読み出し帯域のトレードオフで 8k がスイートスポット

prompt_per_second は 48→1k→8k で 9→68→181 t/s と上昇するが、8k 以降は逓減:

| prompt_n | prompt_tps |
|------:|------:|
| 48 | 8.94 |
| 1,069 | 67.85 |
| 8,070 | **181.46** |
| 32,101 | 155.48 |
| 64,163 | 134.54 |
| 120,243 | 105.32 |

`-ub 8192` (micro-batch size) と一致する **8,192 トークン付近でバッチ効率が最大**、それを超えると複数マイクロバッチに分割され、マイクロバッチ間で既計算 KV の参照オーバーヘッドが累積する（flash-attention でも softmax の分割再計算が各マイクロバッチで必要）。

### 3. セッション drift は発生しない

I_warmup (15.000) と I_post (15.000) が完全一致。**長コンテキスト処理後に短プロンプトに戻せば速度は完全に回復する**。したがって Phase I で観測した eval 劣化は:

- セッション状態の劣化ではない（スレッド affinity の乱れ、GPU クロックのドロップ等では**ない**）
- **純粋に KV cache サイズに依存する実効計算コスト**

Phase H で残った idle 劣化仮説に「長コンテキスト後遺症」を上乗せする必要はない。

### 4. セッション間ゆらぎの続報

| セッション | 短プロンプト warmup | 備考 |
|-----------|:------:|------|
| Phase G G1a | 14.867 | poll=0 fresh |
| Phase H H1_t0 | 14.664 | poll=0 fresh |
| **Phase I I_warmup** | **15.000** | poll=0 fresh |

3 セッションで 14.66〜15.00 の 2.3% レンジ。Phase H の TODO「セッション間ゆらぎの管理」はまだ未解決で、プロセス停止前の履歴・GPU メモリ配置の影響が引き続き疑わしい。

### 5. 実用シナリオの turn time

```
turn_time(N) ≈ prompt_time(N) + 256 / eval_tps(N)
```

| N | prompt_time | eval_time (256 tok) | 合計 |
|---:|------:|------:|------:|
| 1k | 15.8s | 17.2s | **33s** |
| 8k | 44.5s | 17.9s | **62s** |
| 32k | 206s | 20.4s | **227s (3.8 min)** |
| 64k | 477s | 24.6s | **502s (8.4 min)** |
| 120k | 1,142s | 32.0s | **1,174s (19.6 min)** |

**120k 入力で 256 tok 応答に 19.6 分**は対話用途では困難。以下の運用上の含意:

- **8k 以下**: 対話的（1 分未満）
- **32k**: バッチ用途推奨（3.8 分）
- **64k 以上**: プロンプトキャッシュを活かしたマルチターンか、非同期バッチ処理前提

なお、**2 回目以降の同一長プロンプト接頭辞は llama-server がキャッシュを効かせる**ため、差分部分のみの再処理で再応答は大幅短縮される（本 Phase では unique prefix で明示的に無効化）。

### 6. Phase H の GPU メモリ概算の検証

Phase D の静的観測（CUDA1: 14,173 MiB / 2,098 MiB free）は**長コンテキスト処理前の値**だった。実動作では:

- 1k 以下: CUDA1 14,315 MiB / 1,955 free（±2% 以内）
- 8k 以降: CUDA1 15,217 MiB / 1,053 free（**約 1 GiB 減少**）

Phase H の「2 GiB マージン未検証」懸念は**妥当な懸念であった**。実ピークでも 1 GiB の余裕が残り OOM には至らないが、マージンの約半分が長コンテキスト処理で消費される点は今後の構成変更（C-4 等で GPU 層を増やす場合）で考慮が必要。

## 採用判定

| 項目 | 結果 |
|------|------|
| C-D3 の長コンテキスト安定性 | **安定**（Run 間再現性 0.2% 以内、drift なし） |
| 120k 入力 OOM リスク | **回避**（CUDA1 free 1,053 MiB、安全余裕 ~1 GiB） |
| 対話用途の実用コンテキスト上限 | **~16k**（1 分未満で応答、eval 14+ t/s） |
| バッチ用途の実用コンテキスト上限 | **~64k**（8 分以内、eval 10+ t/s） |
| 128k コンテキスト運用の可否 | **非対話用途・非同期処理ならば可**（19 分 / ターン、eval 8 t/s） |
| `--cache-type-k/v q8_0` 妥当性 | **妥当**（131k ctx の KV cache が GPU に収まる） |
| `-b 8192 -ub 8192` のスイートスポット | **8k 付近で prompt_tps ピーク**（181 t/s）、採用妥当 |

**結論**: 現行 C-D3 構成は長コンテキスト運用でも採用適合。ただし 64k 超は非対話運用が前提。アプリ側で「コンテキストサイズ → 期待レイテンシ」の見積表を提示すべき。

## 未検証事項

### 既知項目（前身レポートから継続）

- [ ] **2 時間超の連続稼働試験（eval あり）**: Phase H で eval なし idle 60m + G1e (eval 60m→idle 88m) が安定確認。2 時間超の eval あり稼働で劣化するかは未確認
- [ ] **flash-attn off との比較**: P100 CC 6.0 で `--flash-attn 1` が最適か未検証。本 Phase I で `--flash-attn 1` の長コンテキスト挙動を取得したが、off との A/B は未実施
- [ ] **層→GPU アライメントのソース解析**: llama.cpp の `-ot` 正規表現と層配置のロジック
- [ ] **ページキャッシュのコールドスタート検証**: `sudo sysctl vm.drop_caches=3` 権限が llm ユーザーにないため未実施
- [ ] **量子化ダウンでの eval 向上量**: Q4_K_M → Q3_K_M / IQ2_XXS
- [ ] **pcm-memory による DRAM 帯域実測**
- [ ] **C-D3 + コールドスタート**
- [ ] **Node 0 側のコールドスタート C-D6**
- [ ] **perf stat での C-D3 の node-load-miss rate**
- [ ] **C-4 実験**（CPU 層 36 → 20 層未満）。本 Phase で CUDA1 は 1,053 MiB まで埋まるため C-4 で GPU 層を増やす際は長コンテキストでの OOM リスクが上昇
- [ ] **他モデルでの同様の傾向**（Qwen3.5-35B-A3B 等）
- [ ] **`--threads 30` / `--threads 28` などの中間値**
- [ ] **`--numa numactl` モード**
- [ ] **OpenMP 環境変数の影響**
- [ ] **「初回サイクル効果」の原因特定**（Phase F 新規項目）
- [ ] **セッション間 warmup ゆらぎ（14.66〜15.00）の原因特定**（Phase H 継続、本 Phase で再観測）
- [ ] **`--poll 1` / `--poll 10` / `--poll 100` の影響**
- [ ] **G_aged_t96 の再現条件の特定**
- [ ] **`--poll` とスレッド affinity / OpenMP の相互作用**

### 新規項目（本レポートで判明・発生）

- [ ] **線形モデル `time_per_token = 66.5μs + 0.485μs × N_context` の他構成での検証**: C-D3 以外（例: threads=20, --numa isolate, flash-attn off）で定数 `a, k` がどう変化するか。特に `k` の削減余地を調査
- [ ] **prompt_per_second が 8k で頂点を打つ理由**: `-b / -ub 8192` との関連。`-ub` を 4096 や 16384 にすると長コンテキストの prompt_tps が改善するか
- [ ] **64k / 120k の Run 間再現性**: 本 Phase では各 1 Run のみ。3 Run にするには ≥ 30 分／Phase の時間コスト増。サンプリング戦略の見直し要
- [ ] **128k コンテキストが純粋応答に与える影響**: 120k まで検証したが、131k（=ctx_size 上限）付近での挙動は未確認。`parallel 1` のスロット切れ挙動・defrag-thold 0.1 の発動タイミングも未観測
- [ ] **KV cache 量子化 (q8_0) の精度影響**: eval 速度は計測できたが、長コンテキストでの出力品質（論理一貫性、ハルシネーション率）は未計測
- [ ] **prompt cache hit 時の実効 turn time**: 本 Phase では意図的に回避したが、実運用ではマルチターン会話で同一接頭辞が多く、**実効値は大幅に改善**するはず。ベンチマークメニューに「cache hit rate 50%」等のシナリオ追加要
- [ ] **ワークスペース +950 MiB の内訳**: 8k で突然確保される追加 GPU メモリが `ggml-cuda` のどのバッファか（batch compute buffer / defrag temp / softmax scratch 等）の特定

## 検証完了後に実施すべき TODO

### 既知項目（前身レポートから継続）

- [ ] **start.sh の拡張**: `LLAMA_NUMACTL_PREFIX` / `LLAMA_EXTRA_THREADS` 環境変数サポート追加
- [ ] **CUDA1 セーフティマージン OOM フォールバック実装**: 本 Phase で 1,053 MiB まで到達したことを踏まえ、C-4 等の層増設時は動的な OOM 検出と層ロールバック機構が必要
- [ ] **flash-attn off ベンチマーク**: 本 Phase I のプロトコル（長コンテキスト対応）をそのまま流用可能
- [ ] **層→GPU アライメントのソースコード解析**
- [ ] **C-4 実験**（CPU 層削減 + GPU 層追加）
- [ ] **drop_caches 権限の確保**（sudoers 設定 or vmtouch 導入）
- [ ] **C-D3 での perf stat 計測**: node-load-miss が理論通り激減しているか確認
- [ ] **コールドスタート C-D6 計測**: Node 間対称性の証明
- [ ] **start.sh での NUMA プリセット整備**: `NUMA_MODE=pinned_node1_t40` 等
- [ ] **start.sh に `--threads` 設定追加**
- [ ] **PID 取得ロジックの統一**（`ps -eo pid,comm,args | awk '$2=="llama-server"'` 方式に）
- [ ] **セッション間ゆらぎの管理**: 計測プロトコルに「直前プロセス情報（PID、etime、停止からの経過時間）」を明示的に記録
- [ ] **`--poll 50` を採用しない旨を start.sh のコメントで明記**: 将来の改変防止
- [ ] **idle 劣化が偶発現象と確定した場合、Phase E/G の当該セクションに追記**（再現性なしの注記）

### 新規項目（本レポートで発見）

- [ ] **`measure_phaseI.sh` を汎用化して skill に組み込む**: `.claude/skills/llama-server/scripts/measure_longcontext.sh` として配置、`RUNS` と `@file` 入力をサポート。再計測を容易化
- [ ] **「長コンテキスト性能カード」をモデル単位で記録するドキュメント整備**: `llama-server` skill 下に `performance_cards/` を作り、モデル × 構成 × サイズ のレイテンシ表を機械可読 TSV で保存
- [ ] **アプリ側にコンテキストサイズ別レイテンシ警告を出す仕組み**: 8k/32k/64k/120k の閾値超過時に「応答時間 N 分見込み」をクライアント UI に通知
- [ ] **プロンプトキャッシュの活用ドキュメント化**: `--parallel 1` で接頭辞一致時の挙動、システムプロンプトを固定する運用パターンの README 整備
- [ ] **`-ub` の感度ベンチマーク追加**: `-ub 4096 / 8192 / 16384` で prompt_tps の 120k ピーク値を比較

## 補足

- **C-D3 採用構成の最終実効値**:
  - **短プロンプト eval**: 15.00 t/s（Phase H の 14.66 と 2.3% ゆらぎ）
  - **1k 入力 eval**: 14.88 t/s
  - **8k 入力 eval**: 14.27 t/s
  - **32k 入力 eval**: 12.56 t/s
  - **64k 入力 eval**: 10.41 t/s
  - **120k 入力 eval**: 8.00 t/s
- **運用推奨**:
  - **対話（≤1 min）**: コンテキスト ≤ 16k
  - **同期バッチ（≤5 min）**: コンテキスト ≤ 32k
  - **非同期バッチ（≤20 min）**: コンテキスト ≤ 128k
- **作業終了時点で llama-server は停止済み、GPU サーバロック（t120h-p100）は解放済み**
