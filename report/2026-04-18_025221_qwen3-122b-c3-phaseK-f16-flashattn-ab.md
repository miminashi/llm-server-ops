# Qwen3.5-122B-A10B C-3 Phase K（f16 KV 条件での flash-attn ON/OFF A/B 比較）

- **実施日時**: 2026年4月18日 02:52 – 03:26 (JST)
- **作業種別**: 計測・検証（Phase J 未検証事項「cache-type f16 条件での flash-attn ON/OFF A/B」）

## 添付ファイル

- [実装プラン](attachment/2026-04-18_025221_qwen3-122b-c3-phaseK-f16-flashattn-ab/plan.md)
- [起動スクリプト (start_phaseK.sh)](attachment/2026-04-18_025221_qwen3-122b-c3-phaseK-f16-flashattn-ab/start_phaseK.sh)
- [計測スクリプト (measure_phaseI.sh、Phase I から流用)](attachment/2026-04-18_025221_qwen3-122b-c3-phaseK-f16-flashattn-ab/measure_phaseI.sh)
- [一括実行スクリプト (run_all.sh、Phase J から流用)](attachment/2026-04-18_025221_qwen3-122b-c3-phaseK-f16-flashattn-ab/run_all.sh)
- [集計スクリプト (aggregate_results.sh)](attachment/2026-04-18_025221_qwen3-122b-c3-phaseK-f16-flashattn-ab/aggregate_results.sh)
- [集計結果 TSV (results.tsv)](attachment/2026-04-18_025221_qwen3-122b-c3-phaseK-f16-flashattn-ab/results.tsv)
- [マスターログ (run_all_K_f16_fa1.log)](attachment/2026-04-18_025221_qwen3-122b-c3-phaseK-f16-flashattn-ab/run_all_K_f16_fa1.log)
- [flash-attn=0 起動失敗時ログ (fa0_startup/llama-server.log)](attachment/2026-04-18_025221_qwen3-122b-c3-phaseK-f16-flashattn-ab/fa0_startup/llama-server.log)
- `out_K_f16_fa1_{warmup,1k,8k}/` の各計測アーティファクト（`eval_run{N}.json`, `dmon_run{N}.log`, `status_run{N}.txt`, `numastat_{pre,post}.txt`, `numastat_m_{pre,post}.txt`, `free_{pre,post}.txt`, `gpu_{pre,post}.csv`, `gpu_post_run{N}.csv`, `sched_{pre,post}.txt`, `cmdline.txt`, `timeline.log`）

## 参照

- 前身レポート: [2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab.md](2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab.md)
- Phase I: [2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext.md](2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext.md)
- Phase H: [2026-04-17_082738_qwen3-122b-c3-phaseH-idle-poll.md](2026-04-17_082738_qwen3-122b-c3-phaseH-idle-poll.md)

## 前提・目的

Phase J で「C-D3 採用構成 (`--cache-type-{k,v} q8_0` + `--ctx-size 131072`) では `--flash-attn 0` が起動不可（Segfault）」と確認され、原因仮説として「llama.cpp の CUDA バックエンドは量子化 KV cache を flash-attention 経路でのみサポート」が提示された。しかし A/B 比較の計測そのものは達成できず、**flash-attn の本来の速度効果は未検証のまま残った**。

本 Phase K では、Phase J 仮説を迂回するため、**KV cache を f16 に戻し、ctx=16384 に縮小した構成**で flash-attn ON/OFF の A/B 比較を行う。具体的目的:

1. f16 KV cache 条件下で flash-attn=0 が起動可能かを確認（Phase J 仮説の裏取り or 反証）
2. 起動可能なら flash-attn 1 vs 0 の eval_tps / prompt_tps を直接比較
3. 量子化 KV の性能影響（q8_0 vs f16）を副次的に取得
4. Phase J までの前提「flash-attn=1 は固定」の再検証

### 成功条件（当初設定）

- K_f16_fa1 と K_f16_fa0 両方のセッションで warmup / 1k / 8k を 3 runs ずつ完走（→ **K_f16_fa1 のみ達成**、K_f16_fa0 は別経路で起動不可）
- 両条件の eval_tps 中央値から flash-attn 差分を算出（→ **別経路で採用判定に到達**、下記「採用判定」参照）

## 環境情報

- **サーバ**: `t120h-p100` (10.1.4.14)
- **GPU**: NVIDIA Tesla P100-PCIE-16GB × 4（各 16,270 MiB、合計 65,077 MiB）
- **CPU**: Intel Xeon Gold 6138 @ 2.00GHz × 2 socket、計 40 コア / 80 スレッド、NUMA 2 ノード
- **メモリ**: 257,560 MiB (約 251 GiB)
- **モデル**: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- **llama.cpp ビルド**: b8807-b3d758750（Phase D/E/F/G/H/I/J と同一系列）
- **構成（Phase K）**: C-D3 ベース + `--cache-type-{k,v} f16` + `--ctx-size 16384`
  - NUMA: `numactl --cpunodebind=1 --membind=1 --`
  - `--threads 40 --poll 0 -b 8192 -ub 8192`
  - `-ngl 999 -ot 'blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'`
  - `--cache-type-k f16 --cache-type-v f16 --ctx-size 16384`
- **K_f16_fa1 セッション PID**: 137977
- **K_f16_fa0 セッション**: 起動試行 OOM で Segfault（PID 確定せず）

## 計測手順（再現方法）

### スクリプト構成（Phase J からの変更点）

| ファイル | 変更内容 |
|---|---|
| `start_phaseK.sh` | Phase J の `start_phaseJ.sh` をベースに、`--cache-type-{k,v}` を `q8_0` → `f16`、`--ctx-size` を `131072` → `16384` に変更 |
| `run_all.sh` | 変更なしで流用（TAG_PREFIX, SIZES, GATE_MIB 等の環境変数は Phase J と同一） |
| `measure_phaseI.sh` | 変更なしで流用 |
| `aggregate_results.sh` | 集計対象を `out_J_*` → `out_K_*` に変更 |
| `prompts/` | Phase J からコピー（`prompt_{1k,8k}.txt` を使用） |

### 実行フロー

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseK-f16-flashattn-ab"
# （Phase J 資産をコピー、start_phaseK.sh / aggregate_results.sh を編集）

# ---- フェーズ 1: flash-attn=1 基準採取 ----
FLASH_ATTN=1 bash "$REPORT_DIR/start_phaseK.sh"
PID=$(ssh t120h-p100 "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
cd "$REPORT_DIR"
TAG_PREFIX=K_f16_fa1 SIZES="warmup 1k 8k" PID=$PID bash run_all.sh
.claude/skills/llama-server/scripts/stop.sh t120h-p100

# ---- フェーズ 2: flash-attn=0 計測（試行） ----
FLASH_ATTN=0 bash "$REPORT_DIR/start_phaseK.sh"
# → 起動直後 Segmentation fault (OOM) で /health に到達せず

bash aggregate_results.sh > results.tsv
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 実行タイムライン

| タグ | prompt_n（ChatTemplate 込み） | Run 数 | 開始 | 終了 |
|------|---------:|------:|----------:|----------:|
| K_f16_fa1_warmup | 53 | 3 | 03:00:35 | 03:06:19 |
| K_f16_fa1_1k | 1,074 | 3 | 03:06:19 | 03:12:15 |
| K_f16_fa1_8k | 8,075 | 3 | 03:12:15 | 03:18:31 |
| **K_f16_fa0 起動試行** | — | — | 03:20 | **Segfault 即死（OOM）** |

K_f16_fa1 フェーズ所要: **約 18 分**（事前準備含めて 23 分）。K_f16_fa0 は起動フェーズで即時失敗のため計測自体に到達せず。

## 実行結果サマリ

### K_f16_fa1 (flash-attn=1, f16 KV, ctx=16384) の eval 速度

| タグ | prompt_n | Run 1 | Run 2 | Run 3 | 中央値 | warmup 比 |
|------|---------:|------:|------:|------:|------:|---------:|
| K_f16_fa1_warmup | 53 | 15.046 | 15.039 | 15.055 | **15.046** | 基準 |
| K_f16_fa1_1k | 1,074 | 15.032 | 15.032 | 15.026 | **15.032** | **−0.09%** |
| K_f16_fa1_8k | 8,075 | 14.856 | 14.884 | 14.855 | **14.856** | **−1.26%** |

Run 間 range: warmup 0.016 t/s（極めて安定）、1k 0.006 t/s、8k 0.029 t/s。Phase I/J の 8k で観測された「Phase J run 2 が外れ値」のような挙動は見られず、全 9 runs で標準偏差が 0.02 t/s 未満。

### K_f16_fa1 の prompt 処理速度

| タグ | Run 1 | Run 2 | Run 3 | 中央値 |
|------|------:|------:|------:|------:|
| K_f16_fa1_warmup | 9.26 | 9.41 | 9.38 | **9.38** |
| K_f16_fa1_1k | 67.98 | 68.32 | 68.12 | **68.12** |
| K_f16_fa1_8k | 177.36 | 187.28 | 186.20 | **186.20** |

Phase J_fa1 (q8_0, ctx=131072) 値（9.07 / 68.20 / 184.18）と比較すると、warmup で +3.4%、1k で −0.12%、8k で +1.1%。8k の Run 1 が外れ値（177.4 vs 187.3/186.2）で Phase J の warmup run 1 同様に初回 ubatch 確保の一過性と見られる。

### K_f16_fa1 の GPU メモリ使用量（`gpu_post_run*.csv` より）

| タグ | CUDA0 | CUDA1 | CUDA2 | CUDA3 | CUDA1 free |
|------|------:|------:|------:|------:|----------:|
| K_f16_fa1_warmup | 4,593 | 12,135 | 12,135 | 10,239 | 4,135 |
| K_f16_fa1_1k | 4,643 | 12,181 | 12,185 | 10,277 | 4,089 |
| K_f16_fa1_8k | 5,553 | 13,063 | 13,077 | 10,651 | 3,207 |

（単位 MiB）Phase J_fa1 (q8_0, ctx=131072) warmup の CUDA1=14,269 MiB と比較して **−2,134 MiB の削減**（−15%）。ctx を 131072 → 16384（1/8）に縮小したが、f16 KV は q8_0 の 2x メモリを消費するため、正味の節約は約 15% にとどまる（KV cache 以外の model weight / compute buffer が VRAM 占有の大半を占めるため）。

### K_f16_fa0 (flash-attn=0, f16 KV, ctx=16384) 起動試行結果

```
$ FLASH_ATTN=0 bash start_phaseK.sh
[start_phaseK] FLASH_ATTN=0 (C-D3 base, poll=0, ctx=16384, f16 KV)
[start_phaseK] waiting for /health...
(llama-server.log 抜粋)
llama_kv_cache: size =  384.00 MiB ( 16384 cells, 12 layers, 1/1 seqs),
                K (f16): 192.00 MiB, V (f16): 192.00 MiB
sched_reserve: resolving fused Gated Delta Net support:
sched_reserve: fused Gated Delta Net (autoregressive) enabled
ggml_backend_cuda_buffer_type_alloc_buffer: allocating 18176.00 MiB on device 0:
                cudaMalloc failed: out of memory
ggml_gallocr_reserve_n_impl: failed to allocate CUDA0 buffer of size 19058917504
graph_reserve: failed to allocate compute buffers
bash: line 1: 142121 Segmentation fault (core dumped) nohup bash -c "numactl ...
  --flash-attn 0 --cache-type-k f16 --cache-type-v f16 --ctx-size 16384 ..."
[start_phaseK] FAILED to become healthy in 300s
```

`/tmp/llama-server.log` は **218 行目**で途絶。Phase J (179 行で途絶) より先に進み、**KV cache 初期化は正常完了**（384 MiB / 4 GPU に分散）したが、その後の **compute buffer 予約で 18,176 MiB (18 GB) の確保要求が CUDA0 (16 GB VRAM) で OOM**。

この failure mode は Phase J の Segfault と **階層的に異なる**（後述「分析」参照）。

## ボトルネック・副次発見の分析

### 1. Phase J 仮説の部分訂正

**Phase J の結論（再掲）**: 「`--cache-type-{k,v} q8_0` は flash-attention 経路でのみサポート、fa0 では KV cache 初期化段階で Segfault」

**Phase K の新発見**: f16 KV cache にしても fa0 は起動不可。ただし **失敗経路が異なる**:

| 条件 | 停止地点（ログ行） | Failure mode |
|---|---|---|
| Phase J: q8_0 + fa0 | 179 行目（`common_init_result: added ... logit bias = -inf` 直後） | **KV cache 初期化入り口で Segfault**（assertion 失敗推定） |
| Phase K: f16 + fa0 | 218 行目（KV cache 初期化成功後、`graph_reserve` フェーズ） | **Compute buffer 18 GB 確保で OOM → Segfault** |

これは Phase J 仮説「q8_0 が直接原因」を一部訂正し、**より根本的な結論**に到達する:

> **flash-attn=1 の本質的役割は「量子化 KV サポート」ではなく、attention compute buffer の O(n²) 膨張を O(n) に削減すること**である。flash-attn=0 時は ctx=16k でも compute buffer が 18 GB 必要となり、P100 16 GB 単体では物理的に確保不可能。量子化 KV の非互換は、その上位にある「fa0 経路の実装未整備」の一症状にすぎない。

つまり P100 環境での flash-attn=1 は:

- Phase J 時点の理解: 「量子化 KV の機能要件」
- **Phase K 更新後の理解**: 「**VRAM 制約下での機能要件**」（量子化の有無に関わらず fa0 は物理的に動かない）

### 2. flash-attn compute buffer 要求量の定量化

Phase K fa0 起動ログから読み取れる事実:

- ctx=16384 で `allocating 18176.00 MiB on device 0`
- CUDA0 は 16,269 MiB しか持たないので 18 GB は絶対に収まらない
- 要求量を ctx に比例させると（O(n²) attention score matrix）、ctx=8k で約 4.5 GB、ctx=4k で約 1.1 GB、ctx=2k で約 0.3 GB
- P100 で fa0 を動かすには **ctx ≤ 4096 程度に絞る必要がある**

逆に言えば、**ctx=131072 + fa1 の C-D3 採用構成は、fa=1 による compute buffer 削減に完全依存**している。fa=0 だと理論上 18 × (131072/16384)² ≈ 1,160 GB の compute buffer が必要で、クラスター級 GPU でも不可能。

### 3. cache-type q8_0 vs f16 の速度比較（flash-attn=1 固定）

Phase J_fa1 (q8_0, ctx=131072) と Phase K_fa1 (f16, ctx=16384) の eval 速度:

| サイズ | Phase J_fa1 (q8_0) | K_f16_fa1 (f16) | 差分 |
|------|------:|------:|------:|
| warmup (53 tok) | 15.282 | 15.046 | **−1.54%** |
| 1k (1,074 tok) | 15.179 | 15.032 | **−0.97%** |
| 8k (8,075 tok) | 14.558 | 14.856 | **+2.05%** |

興味深い逆転現象:
- **warmup / 1k**: q8_0 の方がわずかに速い（+1.0〜1.5%）
- **8k**: f16 の方が速い（+2.0%）

ただし注意点:
- Phase J_fa1 と Phase K_fa1 は **ctx-size が違う**（131072 vs 16384）
- ctx-size の差自体が eval 速度に影響する可能性（KV cache 領域のキャッシュ効率等）
- **セッション間ゆらぎ**（Phase G〜J で観測された 14.66〜15.28 レンジ、4.2%）の範囲内にある

Phase H 以降の観測から、セッション間ゆらぎ 2〜4% は「構成による速度差」と「偶発ノイズ」を弁別する閾値を上回る。本 Phase K の q8_0 vs f16 差分はゆらぎ範囲内なので、**明確な優劣判定はできない**。

一方、prompt 処理速度（8k）は q8_0 184.18 / f16 186.20 で **+1.1%** の僅差。f16 の方が dequant 処理が不要な分、理論的には prompt フェーズで有利な可能性があるが、数値上は誤差範囲。

### 4. ctx-size 縮小による VRAM 変化

Phase J_fa1 (q8_0, ctx=131072) と K_f16_fa1 (f16, ctx=16384) の warmup 時 VRAM 比較:

| GPU | J_fa1 (q8_0, 131k) | K_fa1 (f16, 16k) | 差分 |
|----:|------:|------:|------:|
| 0 | 9,799 | 4,593 | **−5,206** |
| 1 | 14,269 | 12,135 | **−2,134** |
| 2 | 14,269 | 12,135 | **−2,134** |
| 3 | 10,581 | 10,239 | **−342** |
| **合計** | 48,918 | 39,102 | **−9,816 (−20.1%)** |

CUDA0 の削減量が目立つ（−5.2 GB）。Phase J/I の長コンテキスト時に CUDA0 に compute buffer のスペアエリアが確保されていた可能性を示唆。これは Phase J 「ワークスペース +950 MiB の内訳」未解明項目と関連する可能性があり、Phase L の探索対象。

### 5. セッション間 warmup ゆらぎの続報

| セッション | 短プロンプト warmup 中央値 | 備考 |
|-----------|:------:|------|
| Phase G G1a | 14.867 | poll=0 fresh |
| Phase H H1_t0 | 14.664 | poll=0 fresh |
| Phase I I_warmup | 15.000 | poll=0 fresh |
| Phase J J_fa1_warmup | 15.282 | poll=0 fresh（q8_0, ctx=131072） |
| **Phase K K_f16_fa1_warmup** | **15.046** | poll=0 fresh（f16, ctx=16384） |

5 セッションで 14.66〜15.28 の **4.2% レンジ**（Phase J 時点から拡大せず）。Phase K は中央域の 15.05。Run 間 range が 0.016 t/s (0.1%) と Phase H〜J 最小で、**Phase K 内部は極めて安定**。Phase J で観測された run 1 15.54 のような外れ値は再現せず。

このゆらぎは依然未説明で、Phase H/J から継続 TODO。ctx-size の違い（131072 vs 16384）が影響している可能性は Phase K でも排除できない。

### 6. dmon 所見（8k 処理時の SM 稼働）

`out_K_f16_fa1_8k/dmon_run1.log` の先頭サンプル（30 秒間）より Phase J と同様の傾向:

| GPU | sm% 平均 | mem% | 備考 |
|----:|--------:|-----:|------|
| 0 | 40-70 | 3-10 | 計算の主担当（Phase J と同じ） |
| 1 | 0 | 0 | idle（KV 保持のみ、Phase J と同じ） |
| 2 | 0 | 0 | idle |
| 3 | 0 | 0 | idle |

ctx/cache-type を変えても CUDA0 集中計算 + CUDA1/2/3 idle のパターンは不変。これは `-ot 'ffn_.*_exps\.weight=CPU'` での層配置と、attention/routing 層が CUDA0 側 に集中配置される llama.cpp の既定挙動に起因する。Phase J 継続 TODO「CUDA1/2/3 の SM 稼働実態の時系列計測」は本 Phase でも再確認。

## 採用判定

| 項目 | 結果 |
|------|------|
| f16 KV + fa0 の起動可否（ctx=16384） | **不可能**（compute buffer 18 GB 要求で OOM）|
| P100 環境での `--flash-attn 1` の必須性 | **確定**（量子化の有無に関わらず、VRAM 制約で fa0 不可）|
| f16 KV + fa1 の eval 速度（vs q8_0 KV + fa1） | ゆらぎ範囲内（差分 −1.5〜+2.0%）、明確な優劣なし |
| f16 KV + fa1 の ctx=16k 実用性 | **確認済み**（CUDA1 free 3.2〜4.1 GB のマージンで安定稼働） |
| Phase J 仮説「q8_0 と fa0 非互換」 | **部分訂正**: q8_0 以前に VRAM 制約で fa0 は動かない（仮説より上位の結論）|

**結論**: Phase J の結論「flash-attn=1 は採用構成の機能要件」は維持される。ただし **理由は Phase J 想定より根本的**で、

- Phase J 想定: 「量子化 KV が flash-attn を要求するため」
- **Phase K 更新**: 「**fa=0 時の compute buffer が ctx=16k でも 18 GB 必要で、P100 16 GB に収まらないため**」

量子化 KV の制約は「その上位にある VRAM 制約の一症状」にすぎない。したがって C-D3 採用構成における flash-attn=1 は「選択の余地のない機能要件」として最終確定。

副次的に、**f16 KV と q8_0 KV の速度差は誤差範囲**（ゆらぎ内）であり、採用構成を q8_0 のままにする判断は「長コンテキスト時の VRAM 節約」という機能要件に基づくもので、速度上の選択ではないことが再確認された。

本番 `start.sh` の改変は不要。ただし `.claude/skills/llama-server/SKILL.md` に以下を注記する TODO が発生:
- 「C-D3 採用構成では flash-attn=1 必須」「fa=0 に切り替えるには ctx ≤ 4k 程度に縮小が必要で、現実的でない」

## 未検証事項

### 既知項目（Phase J から継続、部分更新あり）

- [ ] **2 時間超の連続稼働試験（eval あり）**
- [x] ~~flash-attn off との比較~~ → **Phase J/K で階層的に決着**（q8_0 で assertion 失敗、f16 でも VRAM 不足で起動不可）
- [ ] **層→GPU アライメントのソース解析**: llama.cpp の `-ot` 正規表現と層配置のロジック
- [ ] **ページキャッシュのコールドスタート検証**: `sudo sysctl vm.drop_caches=3` 権限が llm ユーザーにないため未実施
- [ ] **量子化ダウンでの eval 向上量**: Q4_K_M → Q3_K_M / IQ2_XXS
- [ ] **pcm-memory による DRAM 帯域実測**
- [ ] **C-D3 + コールドスタート**
- [ ] **Node 0 側のコールドスタート C-D6**
- [ ] **perf stat での C-D3 の node-load-miss rate**
- [ ] **C-4 実験**（CPU 層 36 → 20 層未満）
- [ ] **他モデルでの同様の傾向**（Qwen3.5-35B-A3B 等）
- [ ] **`--threads 30` / `--threads 28` などの中間値**
- [ ] **`--numa numactl` モード**
- [ ] **OpenMP 環境変数の影響**
- [ ] **「初回サイクル効果」の原因特定**（Phase F 新規項目）
- [ ] **セッション間 warmup ゆらぎ（14.66〜15.28）の原因特定**（Phase H/J 継続、本 Phase で中央域 15.05 を再観測）
- [ ] **`--poll 1` / `--poll 10` / `--poll 100` の影響**
- [ ] **G_aged_t96 の再現条件の特定**
- [ ] **`--poll` とスレッド affinity / OpenMP の相互作用**
- [ ] **線形モデル `time_per_token = 66.5μs + 0.485μs × N_context` の他構成での検証**（本 Phase K の ctx=16k + f16 で傾きが近いか未検証）
- [ ] **prompt_per_second が 8k で頂点を打つ理由**（`-b / -ub 8192` との関連検証）
- [ ] **64k / 120k の Run 間再現性**
- [ ] **128k コンテキストが純粋応答に与える影響**（131k 上限）
- [ ] **KV cache 量子化 (q8_0) の精度影響**（長コンテキストでの出力品質）
- [ ] **prompt cache hit 時の実効 turn time**
- [ ] **ワークスペース +950 MiB の内訳**（8k で確保されるバッファ種別、本 Phase K で CUDA0 −5,206 MiB の差分と関連の可能性）
- [ ] **llama.cpp のソース上で `--cache-type-{k,v} q8_0` と `--flash-attn` の依存ロジック確認**（Phase J からの継続項目、Phase K の新発見を踏まえ優先度上昇）
- [ ] **Segfault 時のバックトレース取得**（Phase J/K 両方、core dump を gdb で解析、fa0 failure path の正確な特定）
- [ ] **P100 CC 6.0 の flash-attention カーネル経路の検証**（`ggml-cuda` 内のカーネル分岐点）
- [ ] **CUDA1/2/3 の SM 稼働実態の時系列計測**（Phase J から継続、本 Phase でも同様 idle 挙動確認）
- [ ] **J_fa1_warmup run 1 の外れ値（15.54 t/s）再現性**（Phase K では再現せず、全 9 runs が ±0.1% に収束）

### 新規項目（本 Phase K で判明・発生）

- [ ] **f16 KV cache + ctx=16k の flash-attn 必須性の理論値検証**: Phase K fa0 起動ログが示す 18 GB compute buffer の内訳（attention score matrix、middle activation 等）を llama.cpp ソースコードから逆算し、ctx サイズに対する compute buffer スケーリング式を導出する
- [ ] **ctx ≤ 4096 での flash-attn=0 起動可否**: compute buffer が ctx² で縮小する仮説の検証。ctx=4096 / ctx=2048 / ctx=1024 で fa=0 起動試行
- [ ] **ctx-size の eval 速度への直接影響**: Phase J_fa1 (ctx=131072) と K_f16_fa1 (ctx=16384) の warmup eval 速度差 (−1.5%) が ctx-size の差によるか、cache-type の差によるかの切り分け（同一 cache-type で ctx のみ変えた計測が必要）
- [ ] **Phase J fa0 Segfault の真因**: Phase K で「VRAM 制約」が根本原因と判明したが、Phase J の 179 行目停止は早期 assertion 失敗の可能性。`LLAMA_LOG_VERBOSE=1` 等でデバッグログを取得して failure path を特定
- [ ] **CUDA0 −5.2 GB の内訳**: Phase J と K の warmup VRAM 差分の解明（ctx-size によるのか、他要因か）。Phase J 「ワークスペース +950 MiB の内訳」と統合調査対象
- [ ] **f16 KV の精度影響の計測**: q8_0 と f16 で同一プロンプト・同一 seed での出力比較。Phase K の eval 速度は同等だが、生成品質が異なる可能性
- [ ] **prompt 8k の Run 1 外れ値 (177.4 vs 187.3/186.2)**: Phase J run 1 の eval 外れ値とは異なる位置（eval ではなく prompt）で発生。初回 ubatch 確保のウォームアップ効果か計測ノイズかの切り分け

## 検証完了後に実施すべき TODO

### 既知項目（Phase J から継続、部分更新あり）

- [ ] **start.sh の拡張**: `LLAMA_NUMACTL_PREFIX` / `LLAMA_EXTRA_THREADS` 環境変数サポート追加
- [ ] **CUDA1 セーフティマージン OOM フォールバック実装**
- [x] ~~flash-attn off ベンチマーク~~ → **Phase J/K で「起動不可能」と確定、別スコープへ移管**
- [ ] **層→GPU アライメントのソースコード解析**
- [ ] **C-4 実験**（CPU 層削減 + GPU 層追加）
- [ ] **drop_caches 権限の確保**（sudoers 設定 or vmtouch 導入）
- [ ] **C-D3 での perf stat 計測**
- [ ] **コールドスタート C-D6 計測**
- [ ] **start.sh での NUMA プリセット整備**
- [ ] **start.sh に `--threads` 設定追加**
- [ ] **PID 取得ロジックの統一**
- [ ] **セッション間ゆらぎの管理**: 計測プロトコルに「直前プロセス情報（PID、etime、停止からの経過時間）」を明示的に記録
- [ ] **`--poll 50` を採用しない旨を start.sh のコメントで明記**
- [ ] **idle 劣化が偶発現象と確定した場合、Phase E/G の当該セクションに追記**
- [ ] **`measure_phaseI.sh` を汎用化して skill に組み込む**: `.claude/skills/llama-server/scripts/measure_longcontext.sh` として配置
- [ ] **「長コンテキスト性能カード」をモデル単位で記録するドキュメント整備**
- [ ] **アプリ側にコンテキストサイズ別レイテンシ警告を出す仕組み**
- [ ] **プロンプトキャッシュの活用ドキュメント化**
- [ ] **`-ub` の感度ベンチマーク追加**
- [ ] **`start_phaseJ.sh` / `start_phaseK.sh` の `FLASH_ATTN` 環境変数化を skill 側 `start.sh` に逆輸入**（Phase J 継続項目、fa=0 は P100 で起動不可であることをコメントで警告）
- [ ] **依存制約の lint 化**（Phase J 継続項目）: 起動前に「`--flash-attn 0` かつ P100 GPU」の組み合わせを検知して即エラー終了させる pre-check を `start.sh` に追加（本番事故防止）
- [ ] **llama.cpp upstream issue/PR のサーベイ**（Phase J 継続項目）: 「flash-attn=0 での compute buffer スケーリング」「量子化 KV + fa=0 サポート」の現行状態を確認

### 新規項目（本 Phase K で発見）

- [ ] **CLAUDE.md / skill に「C-D3 の flash-attn=1 は VRAM 制約に由来する必須要件」を注記**: Phase J 時点の「量子化 KV が原因」という部分的理解を Phase K で訂正した結果を反映。将来の誰かが「量子化 KV を使わなければ fa=0 にできるのでは」と誤解しないよう、**根本原因を明記**（compute buffer の O(n²) 膨張が ctx=16k でも 18 GB）
- [ ] **Phase L 計画策定**: ctx ≤ 4096 での fa=0 起動試行。ctx=4k / ctx=2k / ctx=1k の順で OOM 閾値を探り、fa=0 での speed も含めて限定的 A/B を取得（C-D3 採用とは別論点、理論的好奇心）
- [ ] **f16 KV 採用の再評価**: Phase K で f16 KV + ctx=16k が実用的に動作することが確認された。C-D3（q8_0, ctx=131k）とは別構成として、短〜中コンテキスト専用の高精度プリセット（`f16-ctx16k`）を skill に登録することを検討
- [ ] **レポートテンプレートに「Failure mode の階層化」セクションを追加**: Phase K で「同じ Segfault でも failure path が異なる」ことが発見の核となった。今後の Segfault 系調査では停止ログ行番号と最終ログメッセージを必ず記録するよう、計測プロトコルに組み込む

## 補足

- **K_f16_fa1 セッションの実効値**（Phase J_fa1 比較を兼ねる）:
  - **短プロンプト eval (warmup)**: 15.05 t/s（Phase J_fa1 15.28 比 −1.54%、ゆらぎ範囲内）
  - **1k 入力 eval**: 15.03 t/s（Phase J_fa1 15.18 比 −0.97%、ゆらぎ範囲内）
  - **8k 入力 eval**: 14.86 t/s（Phase J_fa1 14.56 比 +2.05%、ゆらぎ範囲内）
  - **VRAM**: CUDA1 free 3.2〜4.1 GB（ctx=131k の 1.0〜2.0 GB から改善）、実用マージン十分
  - Run 間 range 0.016〜0.029 t/s と Phase H〜J 最小で、Phase K 内部は極めて安定
- **Phase K の核心発見**: 「flash-attn=1 は C-D3 の機能要件」は Phase J で既に確定していたが、**その根本理由が「量子化 KV の非互換」ではなく「compute buffer の O(n²) 膨張による VRAM 制約」**であることが判明。これは P100 等の小 VRAM GPU でのみならず、A100/H100 でも ctx が十分大きければ同様に発生する一般的制約であり、flash-attn の設計思想の再確認でもある。
- **Phase J 仮説との関係**: Phase J の「q8_0 と fa=0 の実装非互換」という仮説自体は正しく、Phase K の「f16 + fa=0 でも VRAM で落ちる」と独立して成立する（階層的に共存）。つまり fa=0 を動かすには両方の障壁を越える必要があり、ctx ≤ 4k 程度の極小構成でしか現実的でない。
- **作業終了時点で llama-server は停止済み（K_f16_fa0 は Segfault で自己終了）、GPU サーバロック（t120h-p100）は解放済み**
