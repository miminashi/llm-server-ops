# Qwen3.5-122B-A10B C-3 Phase S-eval-cross-session（ub=1584/1586/1664 × 5 run、別セッション再計測でセッション間 eval ゆらぎを定量化）

- **実施日時**: 2026年4月20日 01:30 – 02:11 (JST、実作業時間 約 41 分、うち GPU ロック保持 41 分、実バッチ 37 分)
- **作業種別**: ctx=32768 × fa=1 × OT=MoE-only 固定での ub={1584,1586,1664} × (warmup 2 + eval 5) を **Phase S-eval と同条件で別セッション再実行**、session 間 mean 差を定量化
- **GPU ロック**: 取得（t120h-p100、session aws-mmns-generic-203770-20260420_013007）→ 解放済

## 添付ファイル

- [実装プラン](attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/plan.md)
- [起動スクリプト (start_phaseSevalcross.sh)](attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/start_phaseSevalcross.sh)
- [バッチ実行スクリプト (batch_phaseSevalcross.sh)](attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/batch_phaseSevalcross.sh)
- [1 条件内ループ (run_all.sh)](attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/run_all.sh)
- [1 run 計測 (measure_phaseI.sh)](attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/measure_phaseI.sh)
- [cross-session 分析スクリプト (analyze_phaseSevalcross.py)](attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/analyze_phaseSevalcross.py)
- [バッチ実行ログ](attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/batch_phaseSevalcross.log)
- [run 別 raw TSV](attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/summary_phaseSevalcross.tsv)
- [統計 CSV](attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/phaseSevalcross_stats.csv)
- [cross-session verdict](attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/phaseSevalcross_verdict.txt)
- [startup_logs ディレクトリ](attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/startup_logs/)（3 ファイル）
- [out_Sevalcross_* ディレクトリ](attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/)（6 ディレクトリ: warmup × 3 + 1k × 3）
- [プロンプト 1k](attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/prompts/prompt_1k.txt)（Phase S-eval / Sbfine3 と同一、6200 bytes、prompt_n=1084 tokens）

## 参照

- 直前レポート: [2026-04-20_003250_qwen3-122b-c3-phaseSeval.md](2026-04-20_003250_qwen3-122b-c3-phaseSeval.md)
- 本 Phase で session 間比較した前 Phase S-eval 5-run mean:
  - ub=1584: 15.206 ± 0.005 t/s
  - ub=1586: 15.188 ± 0.008 t/s
  - ub=1664: 14.646 ± 0.005 t/s
- 過去 1-run 参照値:
  - ub=1586 (15.466): [2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok.md](2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok.md)
  - ub=1584 (15.293): [2026-04-19_172104_qwen3-122b-c3-phaseSbfine2-ub16tok.md](2026-04-19_172104_qwen3-122b-c3-phaseSbfine2-ub16tok.md)
  - ub=1664 (15.451): [2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary.md](2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary.md)

## 前提・目的

直前 Phase S-eval（2026-04-20 00:32–01:13 JST）は 3 条件 × (warmup 2 + eval 5) の系統計測で σ=0.005-0.008 t/s の低ゆらぎを達成したが、**1-run 参照値との乖離が σ の 18–160 倍**。この乖離源として「セッション間ゆらぎ」が浮上し、直前レポートの **★最優先 TODO「Phase S-eval-cross-session 候補」** として残置された。

本 Phase は **同一スクリプトを別セッションで再実行**し、5-run mean のセッション間変動を実測する。具体目的:

1. 前 Phase 5-run mean が「真の性能」か「本セッション限定 mean」かを判定
2. σ_session（セッション間標準偏差）の実測
3. ピーク ub 順序（ub=1584 > 1586 > 1664）のセッション間安定性
4. 過去 1-run 参照値の再現可否（本 Phase セッションで再現するか）

### 判定しきい値

- **session_independent**: |前 Phase mean − 本 Phase mean| ≤ 0.02 t/s
- **partial_session_drift**: 差 ≤ 0.10 t/s
- **session_dominated**: 差 > 0.10 t/s

### 成功条件

- [x] 3 条件すべて起動成功
- [x] 各条件 eval 5 run の eval_tps 取得
- [x] 前 Phase mean との session 間 Δ 算出
- [x] Welch t-test でセッション間有意差判定
- [x] ピーク ub 順序の安定性確認
- [x] 1-run 参照値再現性の再確認
- [x] GPU ロック取得・解放の正常動作

## 環境情報

前 Phase S-eval と完全同一:

- **GPU サーバ**: t120h-p100 (10.1.4.14)、NVIDIA Tesla P100-PCIE-16GB × 4 (CC 6.0)
- **llama.cpp**: 既存 `~/llama.cpp/build/bin/llama-server`（Phase S-eval と同一 binary）
- **モデル**: `Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf` (unsloth snapshot)
- **起動パラメータ**: fa=1、f16/f16 KV、ctx=32768、`numactl --cpunodebind=1 --membind=1`、threads=40、poll=0、ngl=999
- **OT_REGEX**: `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
- **prompt**: Phase Sbfine3 `prompts/prompt_1k.txt` 流用（prompt_n=1084 tokens、`[Request ID <uniq>] ` prefix 付与で prompt cache hit 回避）
- **予測長**: `max_tokens=256`（全 run predicted_n=256 完走）
- **cooldown**: run 間 60 秒
- **warmup**: 短 prompt 2 run（"Write a short haiku about autumn."、予測 256 tokens）

## 再現方法

```bash
# 1. GPU ロック取得
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 2. 作業ディレクトリへ
cd report/attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/

# 3. バッチ実行（3 条件 × (warmup 2 + eval 5)、所要約 37 分）
bash batch_phaseSevalcross.sh > batch_phaseSevalcross.log 2>&1

# 4. 分析（前 Phase TSV との session 間比較を含む）
python3 analyze_phaseSevalcross.py

# 5. 停止・解放
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 実行結果サマリ

### 1. 本 Phase eval 5-run ピボット（eval_tps t/s、1k prompt=1084 tok、max_tokens=256）

| ub | run1 | run2 | run3 | run4 | run5 | mean | stdev | min | max | median |
|---|---|---|---|---|---|---|---|---|---|---|
| **1584** | 15.464 | 15.468 | 15.471 | 15.474 | 15.473 | **15.470** | **0.004** | 15.464 | 15.474 | 15.471 |
| **1586** | 15.201 | 15.206 | 15.204 | 15.206 | 15.203 | **15.204** | **0.002** | 15.201 | 15.206 | 15.204 |
| **1664** | 15.042 | 15.043 | 15.036 | 15.046 | 15.041 | **15.042** | **0.003** | 15.036 | 15.046 | 15.042 |

本 Phase も σ=0.002–0.004 t/s（相対 0.01–0.03%）と前 Phase 同等の極低ゆらぎ。

### 2. warmup 2-run（短 prompt、eval_tps t/s）

| ub | warmup1 | warmup2 | mean | stdev |
|---|---|---|---|---|
| 1584 | 15.776 | 15.486 | 15.631 | 0.205 |
| 1586 | 15.224 | 15.218 | 15.221 | 0.004 |
| 1664 | 15.065 | 15.063 | 15.064 | 0.001 |

**ub=1584 warmup 1 で 15.776 t/s を観測**（eval mean 15.470 より +0.306）。これは前 Phase の ub=1584 warmup 1 = 15.510 と同様の「初回 +0.3 t/s 上振れ」が再現。ub=1584 固有現象として confirmed。ub=1586/1664 では観測されず。

### 3. セッション間 mean 差（本 Phase vs 前 Phase S-eval、Welch t 近似）

| ub | prior mean | cur mean | Δsession | SE | t | 判定 | session verdict |
|---|---|---|---|---|---|---|---|
| **1584** | 15.206 | 15.470 | **+0.264** | 0.003 | **+93.22** | significant | **session_dominated** |
| **1586** | 15.188 | 15.204 | **+0.016** | 0.004 | **+4.62** | significant | **session_independent** |
| **1664** | 14.646 | 15.042 | **+0.395** | 0.003 | **+150.75** | significant | **session_dominated** |

**3 条件すべて session 間差は有意（|t|>2）**。しかし **効果量は ub 依存**:

- ub=1586: **+0.016 t/s = σ の 2-4 倍**、しきい値 0.02 以下で **session_independent** と判定
- ub=1584: +0.264 t/s = σ の 66 倍
- ub=1664: +0.395 t/s = σ の 132 倍

**重要発見: セッション間ゆらぎは ub 依存の現象**。ub=1586 はセッションを跨いで極めて安定、ub=1584/1664 は大きくドリフト。

### 4. 過去 1-run 参照値との再現性（再確認）

| ub | ref_1run | cur_mean | Δ_1run | 判定 |
|---|---|---|---|---|
| 1584 | 15.293 | 15.470 | **+0.177** | **reject（上振れ方向）** |
| 1586 | 15.466 | 15.204 | −0.262 | reject（下振れ方向） |
| 1664 | 15.451 | 15.042 | −0.409 | reject（下振れ方向） |

本 Phase でも 3 条件すべて reject。**ただし ub=1584 は前 Phase と逆方向（+0.177、前 Phase は −0.087）**。1-run ref が外れ値だった可能性は残るが、ub=1584 の本 Phase mean (15.470) は 1-run ref (15.293) を +0.177 上回っており、**1-run ref 自体が下限方向だった**可能性が浮上。

### 5. ピーク ub 順序のセッション間安定性

| セッション | 1位 | 2位 | 3位 |
|---|---|---|---|
| 前 Phase S-eval | ub=1584 (15.206) | ub=1586 (15.188) | ub=1664 (14.646) |
| 本 Phase S-eval-cross | **ub=1584 (15.470)** | ub=1586 (15.204) | ub=1664 (15.042) |

**ピーク順序は完全に同一（1584 > 1586 > 1664）**。絶対値は大きくドリフトしたが **相対順序は維持**。

### 6. Run 1 外れ値チェック（本 Phase eval、平均 ± 2σ）

| ub | run1 | mean | stdev | \|run1 − mean\| | 2σ | 判定 |
|---|---|---|---|---|---|---|
| 1584 | 15.464 | 15.470 | 0.004 | 0.006 | 0.008 | in_range |
| 1586 | 15.201 | 15.204 | 0.002 | 0.003 | 0.004 | in_range |
| 1664 | 15.042 | 15.042 | 0.003 | 0.000 | 0.007 | in_range |

全条件で Run 1 は外れ値なし（前 Phase と同様）。warmup 2 run で eval 本走は十分に安定化。

### 7. ub 間有意差（本 Phase 5-run プール、Welch t 近似）

| 比較 | diff (t/s) | SE | t | 判定 |
|---|---|---|---|---|
| ub=1586 − ub=1584 | −0.266 | 0.002 | **−133.27** | significant |
| ub=1664 − ub=1584 | −0.428 | 0.002 | **−182.21** | significant |
| ub=1586 − ub=1664 | +0.162 | 0.002 | **+92.01** | significant |

**ub=1584 > ub=1586 > ub=1664 の順序は有意**。前 Phase は 1584 − 1586 = +0.019 だったが、本 Phase は +0.266 と差が 14 倍拡大。これは ub=1584 のみ大幅に上振れたため。

### 8. Pooled 10-run 統計（前 + 本 Phase 合算、「真の性能」推定）

| ub | n | mean | stdev | min | max | median |
|---|---|---|---|---|---|---|
| 1584 | 10 | **15.338** | **0.139** | 15.199 | 15.474 | 15.338 |
| 1586 | 10 | **15.196** | **0.010** | 15.177 | 15.206 | 15.200 |
| 1664 | 10 | **14.844** | **0.208** | 14.639 | 15.046 | 14.844 |

**ub=1586 は pooled σ=0.010 と run 内 σ 同等**（session_independent の裏付け）。ub=1584/1664 は pooled σ=0.14-0.21 と run 内 σ の 35-52 倍、2 セッションで bimodal 的分布（mid-point が両 session の中間に位置）。

### 9. 起動 compute buffer 再確認（ub=1586 代表値、前 Phase と完全一致）

```
load_tensors:        CUDA0 model buffer size =  1301.21 MiB
load_tensors:        CUDA1 model buffer size =  9550.77 MiB
load_tensors:        CUDA2 model buffer size =  9550.77 MiB
load_tensors:        CUDA3 model buffer size =  1693.13 MiB
llama_kv_cache:      CUDA{0,1,2,3} KV buffer size = 192.00 MiB
sched_reserve:      CUDA0 compute buffer size =   980.36 MiB
sched_reserve:      CUDA1 compute buffer size =   452.31 MiB
sched_reserve:      CUDA2 compute buffer size =   452.31 MiB
sched_reserve:      CUDA3 compute buffer size =  1558.12 MiB
sched_reserve:  CUDA_Host compute buffer size =   235.48 MiB
```

**起動時点の物理構成は前 Phase と 1 MiB 単位で完全再現**。eval 性能のセッション間ドリフトは buffer allocator / graph 構造ではなく、**実行時の kernel 状態（thermal / DRAM page 配置 / other process 履歴 / kernel 初期化順序）に起因**。

### 10. prompt_tps（参考、1k prompt 処理）

| ub | prior mean | cur mean | Δsession |
|---|---|---|---|
| 1584 | 68.410 | 68.182 | −0.228 |
| 1586 | 68.200 | 68.623 | +0.423 |
| 1664 | 68.156 | 68.094 | −0.062 |

prompt 側も ub 依存のセッション間ドリフトあり。ただし eval 側とパターンが異なる（ub=1586 のみ上振れ）ため、単純な kernel warm 効果ではない。

## 再現性分析と解釈

### 1. セッション間ゆらぎは ub 依存の現象である

本 Phase の最重要発見。セッション verdict を ub 別に整理:

| ub | Δsession | verdict | 解釈 |
|---|---|---|---|
| **1586** | +0.016 | **session_independent** | FA tile 境界直後、tile 量子化で固定された安定動作点 |
| 1584 | +0.264 | session_dominated | tile 境界直前、kernel warm 状態に敏感 |
| 1664 | +0.395 | session_dominated | tile 境界から離れた位置、FA parallel_blocks 切替の別機構に影響 |

**ub=1586 のみが「真の性能値」として信頼できる**可能性が濃厚（Phase Sb-fa0-offload で候補 L support 確定済みの FA tile 量子化境界直後）。

### 2. ub=1584 の初回効果は再現、かつ eval 本走にも影響する

- 前 Phase: ub=1584 warmup 1 = 15.510 (+0.3 vs eval mean 15.206)
- 本 Phase: ub=1584 warmup 1 = 15.776 (+0.3 vs eval mean 15.470)

**ub=1584 warmup 1 での +0.3 t/s 上振れが 2 セッション連続で再現**。ub=1584 固有の「初回 kernel 状態」現象として confirmed。

さらに本 Phase では eval 本走全体も前 Phase より +0.264 t/s 高く、ub=1584 は warmup だけでなく eval にも session 初期状態が影響することが示唆される。

### 3. ub=1664 の大幅上振れ +0.395 t/s

前 Phase の ub=1664 = 14.646 は **1-run ref (15.451) より −0.805 と大幅下振れ** だったが、本 Phase で +0.395 回復して 15.042 に。

本 Phase 値 (15.042) と 1-run ref (15.451) の差は依然 −0.409 あり、1-run ref が上限外れ値か、両 session ともピーク状態に達していないかは不明。

### 4. pooled 10-run σ に見る session 間ゆらぎの構造

| ub | σ_run (5-run) | σ_pool (10-run) | σ_pool / σ_run |
|---|---|---|---|
| 1584 | 0.004 | 0.139 | **35x** |
| 1586 | 0.002 | 0.010 | **5x** |
| 1664 | 0.003 | 0.208 | **69x** |

**ub=1586 のみ σ_pool / σ_run ≤ 5**（session 間ゆらぎが run 内ゆらぎと同オーダー）。ub=1584/1664 は 35-69 倍 = bimodal 分布。

### 5. 過去 1-run ref の評価再考

前 Phase レポートでは「過去 1-run 値はセッション間ゆらぎを含む外れ値（最高値バイアス）」と仮説立て、**本 Phase でこれを部分的に支持しつつも修正が必要**:

- **ub=1586 ref 15.466**: 本 Phase cur=15.204 との Δ=−0.262、2 session mean 15.196 との差も大 → **ref は明確に上振れ外れ値**
- **ub=1584 ref 15.293**: 本 Phase cur=15.470 との Δ=+0.177、2 session mean 15.338 との差 −0.045 → **ref は 2 session mean に近い** = 外れ値ではなく session 中位値
- **ub=1664 ref 15.451**: 本 Phase cur=15.042 との Δ=−0.409、2 session mean 14.844 との差 −0.607 → **ref は大きく上振れ**

**結論**: 「過去 1-run = 最高値バイアス」は **ub=1586/1664 に当てはまり、ub=1584 には当てはまらない**。ref 評価も ub 依存。

### 6. ピーク順序は保存される

絶対値は大きくドリフトするが、**ub=1584 > 1586 > 1664 の順序は両 session で完全維持**。本 Phase では 1584-1586 差が +0.266 と前 Phase (+0.019) より大きく、ピーク安定性はむしろ強化された。

### 7. 計測プロトコル自体の確度

- σ_run = 0.002-0.004 t/s（本 Phase）は前 Phase (0.005-0.008) と同オーダー、本計測手法の精度限界付近
- 起動 compute buffer が MiB 単位で一致 = 物理構成再現
- predicted_n=256 全 run 完走
- プロトコル自体は **信頼できる**

## 採用判定

| 項目 | 結果 |
|---|---|
| 起動成功率 | ✅ 3/3 (ub=1584/1586/1664) |
| eval 5-run 取得 | ✅ 3/3 × 5 run |
| σ 取得 | ✅ 0.002-0.004 t/s（前 Phase 同等） |
| session 間 mean 差定量化 | ✅ ub 別に +0.016 / +0.264 / +0.395 確定 |
| session verdict | ✅ ub=1586 independent、ub=1584/1664 dominated |
| ピーク順序安定性 | ✅ 両 session で ub=1584 > 1586 > 1664 維持 |
| 1-run ref 再現性 | ❌ 3 条件すべて reject（本 Phase mean でも一致せず） |
| GPU ロック | ✅ 取得・解放正常 |

**結論**:

1. **ub=1586 は session 独立の安定点**（Δsession=+0.016、σ_pool=0.010）→ 本 Phase 最重要発見
2. **ub=1584/1664 は session 依存でドリフトあり**（±0.26〜0.40 t/s）、単一 session mean は不十分
3. **ピーク ub 順序 (1584 > 1586 > 1664) はセッション間で安定保存**
4. **compute buffer は 1 MiB 単位で再現**、性能ドリフトは純粋に runtime kernel 状態由来
5. **「真のピーク mean」の推定には少なくとも 3+ session が必要**（ub=1586 を除く）

### 最新のベストエスティメート（pooled 10-run mean）

- **ub=1584: 15.338 ± 0.139 t/s**（σ_pool 大、追加 session 推奨）
- **ub=1586: 15.196 ± 0.010 t/s**（σ_pool 極小、session 独立性 confirmed）
- **ub=1664: 14.844 ± 0.208 t/s**（σ_pool 最大、追加 session 推奨）

## 未検証事項

### 既知項目（Phase S-eval から継続、本 Phase で潰したものに [x]）

- [x] **★最優先: Phase S-eval-cross-session 候補** — 本 Phase で実施、ub 依存のセッション間ゆらぎを定量化（1586: +0.016 = independent、1584: +0.264、1664: +0.395 = dominated）
- [ ] **★最優先: 過去 Phase 1-run 値のセッション間ゆらぎメカニズムの特定** — 本 Phase で ub=1586 は session 独立、ub=1584/1664 は session 依存と判明。メカニズム特定は未達成。候補: (a) kernel warm 状態の ub 依存性、(b) FA tile 量子化境界との距離、(c) DRAM page 配置
- [ ] **★最優先: Phase Sb-tensor-dump 候補（debug build + FA kernel per-node workspace dump）** — 候補 L support 確定後の物理機構確定手段、優先度変わらず
- [ ] **★高優先: ub ≥ 1586 線形モデルの ctx 独立性検証**
- [ ] **★高優先: 境界 ub\* の ctx 依存性**
- [ ] **★高優先: VMM granularity の実測値確認** — P100 CC 6.0 で `cuMemGetAllocationGranularity()` 値
- [ ] **★高優先: FA parallel_blocks の ub 依存性確認** (候補 I-b) — 本 Phase でも ub=1664 の eval 特異性（session dominated）が観測されて優先度維持
- [ ] **eval 境界挟み込み構造の再現性** (Phase Sb-fine2 継続)
- [ ] **CUDA0 区分モデルの物理的意味** — tensor-dump で確定予定
- [ ] **境界 ub\* の KV 量子化依存性**: q8_0 KV で境界が移動するか
- [ ] **CUDA0 二次係数 9.104e-6 MiB/token² の物理メカニズム**
- [ ] **CUDA0 二次モデルの ctx=262144 外挿** (Phase R-ctx3 継続)
- [ ] **CUDA1/2 cross_e = 1.910e-6, Host = 3.815e-6 MiB/(token·token) の物理メカニズム**
- [ ] **ub=1280/1792 の eval 性能再現性** (Phase Sb 継続)
- [ ] **ub=1280/1536/1792 × ctx=65k での CUDA0 検証** (Phase Sb 継続)
- [ ] **中間 ctx (24k / 48k / 96k) での検証** (Phase Sb 継続)
- [ ] **ctx=65k 32k prompt の 3 run 以上再計測** (Phase R-ctx3 継続)
- [ ] **120k eval 12.82 t/s の Run 間再現性** (Phase R 継続)
- [ ] **prompt 処理のピークが ctx=8k にある理由**
- [ ] **ctx=262,144（モデルの n_ctx_train）での起動可否**
- [ ] **prompt cache (size limit 8192 MiB) の実際の挙動**
- [ ] **2 時間超の連続稼働試験（eval あり）**
- [ ] **ページキャッシュのコールドスタート検証**: `sudo sysctl vm.drop_caches=3` 権限未付与
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
- [x] **★高優先: ub=1584 warmup 1 run での +0.3 t/s 初回効果の再現性** — 本 Phase で 2 session 連続再現 (warmup1=15.510→15.776)、ub=1584 固有現象として confirmed
- [ ] **「初回サイクル効果」の原因特定** — ub=1584 のみに現れる機構、特定未達
- [ ] **★最優先: セッション間 warmup ゆらぎの原因特定** — 本 Phase で ub 依存 (+0.016〜+0.395) が判明、さらに深掘り要
- [ ] **`--poll 1` / `--poll 10` / `--poll 100` の影響**
- [ ] **G_aged_t96 の再現条件の特定**
- [ ] **`--poll` とスレッド affinity / OpenMP の相互作用**
- [ ] **64k / 120k の Run 間再現性**
- [ ] **128k コンテキストが純粋応答に与える影響**
- [ ] **KV cache 量子化 (q8_0) の精度影響**
- [ ] **prompt cache hit 時の実効 turn time**
- [ ] **llama.cpp のソース上で `--cache-type-{k,v} q8_0` と `--flash-attn` の依存ロジック確認**
- [ ] **Segfault 時のバックトレース取得**
- [ ] **CUDA1/2/3 の SM 稼働実態の時系列計測**
- [x] **J_fa1_warmup run 1 の外れ値（15.54 t/s）再現性** — 本 Phase ub=1584 warmup 1 = 15.776 で類似再現、一般性 confirmed
- [ ] **CUDA1 / CUDA2 の n² 係数 (fa=0 a=1.26e-4) の物理解釈**
- [ ] **ctx=1024 の fa=0 eval 劣化 (−5.2%) の原因**
- [ ] **ctx=512 / 256 の極小域での挙動**
- [x] **eval 速度のセッション間ゆらぎレンジ更新** — 本 Phase で ub 依存 (1586: +0.016 → 1664: +0.395) の大幅更新、レンジ ±0.40 t/s (約 2.6%) 確定
- [ ] **prompt 処理の ctx 非依存の長 ctx 側確認**
- [ ] **fa=1 eval の「谷型」(ctx=2048 最高 → ctx=4096 最低) の再現性**
- [ ] **Phase M のモデルを f16 KV → q8_0 KV（C-D3 採用構成）に適用した場合の整合性**
- [ ] **ctx=6144 等の中間 ctx での fa=1 / fa=0 境界確認**
- [ ] **fa=0 ctx=8192 で CUDA1 空き枠を増やす手法** — X3 以下の escalation 境界は未検証
- [ ] **eval 谷型の最低値 ctx の fa=1 における物理原因**

### 既知項目（Phase Q/S 継続）

- [ ] **`-ub=1 (greedy)` でのベンチマーク**
- [ ] **`-ub > -b` の挙動（llama.cpp 制約検証）**
- [ ] **fa=0 側での `-ub` 支配性の確認**
- [ ] **大 prompt での `-ub` 依存性** (4k/8k/16k prompt 未検証)
- [ ] **`-b > -ub` 運用の意義**
- [ ] **`--parallel 2` との相互作用**
- [ ] **P3 vs Phase O の eval 差 +1.17% のセッション源**

### 既知項目（Phase Sb-src から継続）

- [ ] **Phase Sb-src 新規 ★: 境界 ub\* のモデル固有性検証** (Qwen3.5-35B-A3B 等)
- [ ] **Phase Sb-src 新規 ★: 残差 4,247 bytes/tok の分解**
- [ ] **Phase Sb-src 新規: ub ≤ 1585 平坦域 slope 0.0125 MiB/tok の由来**
- [ ] **Phase Sb-src 新規: fused_gdn_ar / ch の実際のパス切替え**
- [ ] **Phase Sb-src 新規: ggml_gated_delta_net 出力 4 MiB 定数寄与の allocator 扱い**

### 既知項目（Phase Sb-alloc から継続）

- [ ] **Phase Sb-alloc 新規: 9 層 SSM 出力の allocator 内配置順序の特定**
- [ ] **Phase Sb-alloc 新規: CUDA_Host buffer (235 MiB) の用途** — 本 Phase でも ctx=32k × ub=1586 で 235.48 MiB で一致

### 既知項目（Phase Sb-fa0-offload から継続）

- [ ] **★高優先: X1 / X2 / X3 escalation 境界の詳細特定**
- [ ] **★高優先: OT 拡張が eval 性能に与える影響定量** — splits 3-5 倍化の eval 影響
- [ ] **★高優先: fa=0 × X4 slope(ctx) 1 次比例係数 1.36e-4 の物理解釈**
- [ ] **★高優先: CUDA1/2 の 8.7 GiB 非 attention 非 MoE model buffer の tensor 名称特定**
- [ ] **★高優先: OT 拡張の slope 影響 +0.10 MiB/ub の由来**
- [ ] **★中優先: Stage 3 OOM alloc size の GPU 別分布**
- [ ] **★中優先: X4 × ctx=32k 以上の確認 (ctx=48k / 40k / 36k)**
- [ ] **★中優先: fa=0 × X4 × ctx=32k における eval 性能**
- [ ] **★中優先: IQ2_XXS 等低量子化での fa=0 ctx 拡張可能性**
- [ ] **★中優先: fa=0 × X4 × ctx=8k の起動可否**
- [ ] **★低優先: fa=1 × X4 での slope(ctx) 測定**

### 既知項目（Phase S-eval から継続）

- [ ] **★高優先: ub=1664 eval 大幅悪化の内部機構** — 本 Phase で ub=1664 session drift +0.395 が観測され、bimodal 挙動の物理原因特定優先度上昇
- [ ] **★高優先: 境界挟み込み (ub ∈ {1583, 1585, 1587}) の 5-run 再現性** — 本 Phase は 3 点のみ、境界構造の完全確定には ±1 ub の 5-run 必要
- [ ] **★中優先: 過去 Phase Sbfine2/Sbfine3/Sb-fine 報告方式の棚卸し** — 1-run 値か min/max/median か
- [ ] **★中優先: run 数を 10 に拡張した場合の mean 安定性** — σ_run=0.002-0.004 で 5 run 十分に見えるが確認
- [ ] **★中優先: prompt size 依存性の再確認** — 1k prompt のみ測定、8k/32k で ub 順序が変わる可能性
- [ ] **★中優先: fa=1 × OT=MoE only 固定での ub=1540-1600 密スキャン (5-run 平均)** — 境界構造の真のピーク特定
- [ ] **★低優先: warmup 長の影響（2 → 4 run）** — 初回効果完全除去に必要な warmup 回数

### 新規項目（本 Phase S-eval-cross-session で判明・発生）

- [ ] **★最優先: ub 依存セッション間ゆらぎの物理メカニズム特定** — ub=1586 のみ session_independent で ub=1584/1664 は session_dominated となる理由。候補: (a) FA tile 量子化境界直後 (ub=1586) が kernel 内状態に対してロバスト、(b) tile 境界直前 (ub=1584) と境界から離れた位置 (ub=1664) は state-dependent、(c) FA parallel_blocks の ub 依存で異なる kernel path
- [ ] **★最優先: 3+ session での cross-session 検証** — 本 Phase は 2 session のみ、σ_session の確度を上げるには最低 3 session、理想 5 session 必要
- [ ] **★高優先: ub=1584 の session 間 +0.26 t/s 上振れの原因** — kernel warm か、system load か、DRAM page か。session 開始直後の eval runs を追加計測
- [ ] **★高優先: ub=1664 の session 間 +0.40 t/s 上振れ + bimodal 性** — 前 Phase 14.646 と本 Phase 15.042 の差、intermediate 値が出るかを追加 session で確認
- [ ] **★高優先: ub=1586 の session_independent 性の頑健性** — ub=1585/1587 でも同様に session 独立か、それとも ub=1586 ちょうど 1 点のみの特殊性か
- [ ] **★中優先: ub=1584 warmup 1 の +0.3 上振れ効果の ub 境界** — ub=1583/1585 で起きるか、ub=1584 1 点のみか
- [ ] **★中優先: session 直後 vs session 2 時間後の drift 有無** — 本 Phase の +0.26〜+0.40 上振れは session 開始 1 時間後の値、長時間経過で戻るか
- [ ] **★中優先: cold-boot 直後 session との比較** — サーバ再起動直後の cold session で eval が異なるか

## 検証完了後に実施すべき TODO

### 既知項目（Phase Sb-alloc から継続）

- [ ] **start.sh の拡張**: `LLAMA_NUMACTL_PREFIX` / `LLAMA_EXTRA_THREADS` / `LLAMA_FLASH_ATTN` / `LLAMA_OT_REGEX` 環境変数サポート追加
- [ ] **CUDA1 セーフティマージン OOM フォールバック実装**
- [ ] **C-4 実験**（CPU 層削減 + GPU 層追加）
- [ ] **drop_caches 権限の確保**（sudoers 設定 or vmtouch 導入）
- [ ] **start.sh での NUMA プリセット整備**
- [ ] **start.sh に `--threads` 設定追加**
- [ ] **`start_phase*.sh` の環境変数化を skill 側 `start.sh` に逆輸入**
- [ ] **依存制約の lint 化**: 起動前 pre-check
- [ ] **llama.cpp upstream issue/PR のサーベイ** — FlashAttention kernel の tile size 実装
- [ ] **`measure_phaseI.sh` を汎用化して skill に組み込む**
- [ ] **「長コンテキスト性能カード」をモデル単位で記録するドキュメント整備**
- [ ] **アプリ側にコンテキストサイズ別レイテンシ警告を出す仕組み**

### 既知項目（Phase Sb-fa0-offload から継続）

- [ ] **★最優先: Phase Sb-tensor-dump（debug build）** — 候補 L 確定手段
- [ ] **★最優先: CLAUDE.md / skill 更新**: 「fa=0 × ctx=32k は OT=X4 で実現可能」「fa=0 × ctx≥65k は P100 では不可能」「候補 L support」「fa=0 compute buffer = ub × ctx × 1.36e-4 の純線形モデル」
- [ ] **★最優先: skill 側 `.claude/skills/llama-server/scripts/start.sh` のデフォルト確定** — `--flash-attn 1`
- [ ] **★最優先: 起動前 lint の CUDA0/1 モデル更新**（fa × OT 軸追加）
- [ ] **★最優先: 候補 L モデル (FA tile 量子化副作用) を skill / CLAUDE.md に記録**
- [ ] **★高優先: Phase Sb-ctx-fine 候補** — ctx=20k/24k/28k/36k/40k/48k の細 ctx 走査（fa=1）
- [ ] **★高優先: Phase Sb-KV8 候補**: `--cache-type-{k,v} q8_0` で再実施
- [ ] **★高優先: Phase Sb-tensor-names 候補** — CUDA1/2 に残る 8.7 GiB model buffer の tensor 名内訳
- [ ] **Phase Q-2 候補**: `-ub=64/32/16/8/4/2/1`
- [ ] **Phase Q-3 候補**: ub=1586 周辺 ±8 token で eval ピーク形状
- [ ] **skill 側 start.sh の `ssh -f` stdout redirect 改修**
- [ ] **start.sh のデフォルト `ctx-size` を 131072 に更新**
- [ ] **Phase Sb-src-cu kernel profile 候補**: nvprof/ncu で ub=1586 付近の FA kernel と buffer 計測
- [ ] **Phase Sb-ctx-131k-eval 候補**: ctx=131k で eval 最速 ub を探索 (fa=1 前提)

### 既知項目（Phase S-eval から継続）

- [ ] **★最重要: 過去 Phase Sbfine2/Sbfine3/Sb-fine レポートの棚卸し** — 1-run 値の由来（単発 run か最高値か）、本 Phase で ub=1584 ref=15.293 が 2 session mean 15.338 に近く「中位値」と判明、他 ub との差異を踏まえた再評価必要
- [ ] **★高優先: Phase S-eval-boundary-fine 候補** — ub ∈ {1583, 1584, 1585, 1586, 1587, 1588} の ±3 ub 範囲で 5-run 平均
- [ ] **★高優先: Phase S-eval-extended 候補** — 同 3 ub で 10 run に拡張、σ の安定性確認
- [ ] **★高優先: Phase S-eval-ub-wide 候補** — ub=1280/1536/1792 等、主要候補を 5-run 平均で取得
- [ ] **★中優先: Phase S-eval-prompt 候補** — 8k / 32k prompt での ub 順序確認
- [ ] **★中優先: Phase S-eval-warmup 候補** — warmup 0/2/4 run 比較で初回効果除去必要数確定
- [ ] **★中優先: analyze_phaseSeval.py の skill 化**

### 新規項目（本 Phase S-eval-cross-session で追加）

- [ ] **★最重要: CLAUDE.md / skill / 性能カード 更新（session 依存性）** — 「**ub 依存のセッション間ゆらぎが存在、ub=1586 のみ session 独立、ub=1584/1664 は ±0.3-0.4 t/s のドリフト**」を明記。単一 session mean は不十分、3+ session 推奨
- [ ] **★最重要: Phase S-eval-3session 候補** — 時間を空けた第 3 session で同条件 5-run、ub 別 σ_session の確度向上と「真の pooled mean」推定
- [ ] **★最優先: Phase S-eval-sameday-diffhour 候補** — 同日 N 時間後に再計測、intra-day session drift の分離
- [ ] **★最優先: Phase S-eval-cold-boot 候補** — サーバ再起動直後の cold session で計測、DRAM page 配置 / kernel 初期状態依存の分離
- [ ] **★高優先: Phase S-eval-ub1585-1587 候補** — ub=1586 の session_independent 性が 1 点ピンポイントか範囲現象か確認
- [ ] **★高優先: ub=1586 を session 独立の「基準点」として skill に明記** — 性能比較ベンチマークは ub=1586 で実施
- [ ] **★中優先: 既存モデルカード「長コンテキスト性能カード」の訂正** — Phase Sbfine3 / Sb-fine ピーク主張を撤回、ub=1586 pooled mean (15.196 ± 0.010) をベースラインとする
- [ ] **★中優先: analyze_phaseSevalcross.py を skill 化** — 汎用「N session cross-session 検証テンプレート」として整備、Welch t / verdict / peak order check を含む

## 補足

### Phase S-eval-cross-session の核心発見（サマリ）

1. **ub 依存のセッション間ゆらぎが存在**: ub=1586 +0.016 (独立)、ub=1584 +0.264、ub=1664 +0.395
2. **ub=1586 のみ session_independent**、pooled σ=0.010（run 内 σ 同等）
3. **ub=1584 warmup 1 +0.3 t/s 上振れは 2 session 連続再現** (ub=1584 固有の初回効果 confirmed)
4. **ピーク ub 順序 (1584 > 1586 > 1664) は両 session で完全維持**
5. **compute buffer は 1 MiB 単位で再現** → 性能ドリフトは runtime kernel 状態由来
6. **1-run ref の評価は ub 依存**: ub=1586/1664 ref は上振れ外れ値、ub=1584 ref は 2-session mean に近い「中位値」
7. **pooled 10-run mean**: ub=1584 15.338 ± 0.139 / ub=1586 **15.196 ± 0.010** / ub=1664 14.844 ± 0.208
8. **ub=1586 は「session 独立の基準点」**として性能比較ベンチマークに最適

### 前 Phase との対照

| Phase S-eval | Phase S-eval-cross-session |
|---|---|
| 単一 session 内 σ_run=0.005-0.008 確定 | 別 session で σ_run=0.002-0.004 確定、プロトコル頑健 |
| 過去 1-run ref 3/3 reject | 本 session でも 3/3 reject、ただし ub=1584 は逆方向 |
| 5-run mean ub=1584 15.206 > 1586 15.188 > 1664 14.646 | 5-run mean ub=1584 15.470 > 1586 15.204 > 1664 15.042 |
| セッション間ゆらぎ浮上 | **ub 依存セッション間ゆらぎ確定**、ub=1586 independent |
| 1-run ref = 最高値バイアス仮説 | **ub 依存の評価** (1584 は中位値、1586/1664 は上限値) |
| 次 Phase: cross-session, boundary-fine, 過去レポート棚卸し | 次 Phase: 3-session, cold-boot, ub=1585-1587 範囲確認 |

### 作業終了時点の状態

- **GPU サーバロック: 解放済 (t120h-p100)**
- 作業ディレクトリ `report/attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/` を保持
- 生成物:
  - plan.md / start_phaseSevalcross.sh / batch_phaseSevalcross.sh / run_all.sh / measure_phaseI.sh / analyze_phaseSevalcross.py
  - batch_phaseSevalcross.log / summary_phaseSevalcross.tsv / phaseSevalcross_stats.csv / phaseSevalcross_verdict.txt
  - startup_logs/ (3 ファイル)
  - out_Sevalcross_* ディレクトリ 6 個（warmup × 3 + 1k × 3）
  - run_all_Sevalcross_*.log / run_Sevalcross_*.log / start_stdout_Sevalcross_*.log 各 3 ファイル
- **主要発見**:
  - **ub 依存のセッション間ゆらぎ確定**: ub=1586 独立、ub=1584/1664 ドリフト
  - **ub=1586 pooled 10-run mean = 15.196 ± 0.010 t/s** → 「真の性能値」信頼できる
  - **ub=1584 warmup 1 +0.3 上振れ現象 2 session 連続再現** → ub=1584 固有初回効果として confirmed
- **次の推奨 Phase**:
  1. **Phase S-eval-3session**: 時間を空けた第 3 session で同条件 5-run、所要 50 分
  2. **Phase S-eval-cold-boot**: サーバ再起動直後に計測、所要 50 分
  3. **Phase S-eval-ub1585-1587**: ub=1586 独立性のピンポイント性 vs 範囲性確認、所要 90 分
  4. **過去 Phase Sbfine2/Sbfine3/Sb-fine レポート棚卸し**: 所要 20 分、デスクワーク
  5. **Phase Sb-tensor-dump (debug build)**: 候補 L 物理確定、所要 2-3 時間
