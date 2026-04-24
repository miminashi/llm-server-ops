# Qwen3.5-122B-A10B C-3 Phase Sb-ctx-boundary（候補 J 棄却・slope の ctx 依存性発見）

- **実施日時**: 2026年4月19日 21:06 – 21:15 (JST、実作業時間 約 10 分、バッチ実行時間 約 9 分)
- **作業種別**: 起動時 compute buffer の ctx × ub 走査（9 条件、eval なし）
- **GPU ロック**: **取得（t120h-p100、session aws-mmns-generic-187983-20260419_210554）→ 解放済み**

## 添付ファイル

- [実装プラン](attachment/2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary/plan.md)
- [起動スクリプト (start_phaseSbctx.sh)](attachment/2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary/start_phaseSbctx.sh)
- [バッチ実行スクリプト (batch_Sbctx.sh)](attachment/2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary/batch_Sbctx.sh)
- [分析スクリプト (analyze_Sbctx.py)](attachment/2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary/analyze_Sbctx.py)
- [バッチ実行ログ](attachment/2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary/batch_Sbctx.log)
- [データ集約 TSV](attachment/2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary/summary_Sbctx.tsv)
- [ピボット表](attachment/2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary/Sbctx_pivot.csv)
- [slope 表](attachment/2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary/Sbctx_slopes.csv)
- [判定結果](attachment/2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary/Sbctx_verdict.txt)
- [startup_logs ディレクトリ](attachment/2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary/startup_logs/)（9 ファイル）

## 参照

- 直前レポート: [2026-04-19_203607_qwen3-122b-c3-phaseSb-alloc.md](2026-04-19_203607_qwen3-122b-c3-phaseSb-alloc.md)
- Phase Sb-fine3 (ctx=32k ベースライン): [2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok.md](2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok.md)
- Phase Sb-src: [2026-04-19_192631_qwen3-122b-c3-phaseSbsrc-threshold-hunt.md](2026-04-19_192631_qwen3-122b-c3-phaseSbsrc-threshold-hunt.md)

## 前提・目的

Phase Sb-alloc で、CUDA0 compute buffer の ub*=1586 境界に対する真因仮説を 2 つに絞り込んだ:

- **候補 J**: 9 層 SSM × VMM 2 MiB granularity 非同期累積（9 層分の alignment padding の累積で境界挙動が生じる）
- **候補 I-c**: build_graph 内の ub 依存離散処理（MoE router / attention tensor の離散 reshape）

本 Phase の目的は、候補 J の**強い予測**である「**境界 ub*=1586 は ctx 非依存**」を ctx ∈ {16k, 65k, 131k} × ub ∈ {1584, 1585, 1586} の 9 条件で検証すること。

### 候補 J の予測と判定基準

- 全 3 ctx で |Δ(1584→1585)| ≤ 0.05 MiB（平坦域）
- 全 3 ctx で Δ(1585→1586) ≥ 0.15 MiB（step）
- 全 3 ctx で Δ(1585→1586) / |Δ(1584→1585)| ≥ 5
- 全 3 ctx で peak_ub (argmax Δ) = 1586

全て満たせば候補 J 支持。1 ctx でも外れれば候補 J 棄却。

### 成功条件

- [x] 9 条件すべてで startup_log 取得
- [x] 各条件で sched_reserve ブロックから CUDA0/1/2/3/Host compute buffer size を抽出
- [x] 候補 J を数値で支持 / 棄却判定
- [x] 次 Phase の方向性を結果に応じて明示

## 環境情報

- **GPU サーバ**: t120h-p100 (10.1.4.14)、NVIDIA Tesla P100-PCIE-16GB × 4 (CC 6.0、VMM=yes)
- **llama.cpp**: Phase Sbf3 と同一ビルド（`~/llama.cpp/build/bin/llama-server`）
- **モデル**: `/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf`
- **baseline 設定**: fa=1, f16 KV, `numactl --cpunodebind=1 --membind=1 --`, threads=40, poll=0, -ngl 999, OT_REGEX で MoE FFN CPU オフロード（Sbf3 完全同一）
- **変動条件**: ctx ∈ {16384, 65536, 131072}, ub=b ∈ {1584, 1585, 1586}
- **既存ベースライン（ctx=32768、Sbf3）**: ub=1585 で CUDA0 980.12 MiB、ub=1586 で 980.36 MiB

## 再現方法

```bash
# 1. GPU ロック取得
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 2. 作業ディレクトリへ
cd report/attachment/2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary/

# 3. 9 条件バッチ実行（所要約 9 分）
bash batch_Sbctx.sh > batch_Sbctx.log 2>&1

# 4. 分析
python3 analyze_Sbctx.py

# 5. ロック解放
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 実行結果サマリ

### 1. 9 条件すべて起動成功 ✅

| 条件 | 健全性 OK (反復×5s) | CUDA0 compute buffer | 備考 |
|---|---|---|---|
| ctx=16384, ub=1584 | 4 (20s) | 980.11 MiB | sched_reserve 正常 |
| ctx=16384, ub=1585 | 4 | 980.12 MiB | sched_reserve 正常 |
| ctx=16384, ub=1586 | 4 | 980.13 MiB | sched_reserve 正常 |
| ctx=65536, ub=1584 | 4 | 1162.22 MiB | sched_reserve 正常 |
| ctx=65536, ub=1585 | 4 | 1162.62 MiB | sched_reserve 正常 |
| ctx=65536, ub=1586 | 4 | 1163.02 MiB | sched_reserve 正常 |
| ctx=131072, ub=1584 | 4 | 1558.22 MiB | sched_reserve 正常 |
| ctx=131072, ub=1585 | 5 (25s) | 1558.87 MiB | sched_reserve 正常 |
| ctx=131072, ub=1586 | 4 | 1559.52 MiB | sched_reserve 正常 |

バッチ 9 条件完了 21:08:22 – 21:15:05（約 7 分）。失敗 0 件。

### 2. ピボット表（CUDA0 compute buffer MiB）

| ctx \ ub | 1584 | 1585 | 1586 | Δ(1584→1585) | Δ(1585→1586) |
|---|---|---|---|---|---|
| **16384** | 980.11 | 980.12 | 980.13 | +0.01 | +0.01 |
| 32768 (Sbf3 既存) | — | 980.12 | 980.36 | — | **+0.24** |
| **65536** | 1162.22 | 1162.62 | 1163.02 | +0.40 | +0.40 |
| **131072** | 1558.22 | 1558.87 | 1559.52 | +0.65 | +0.65 |

### 3. 候補 J 判定 ❌ 棄却

```
candidate_J_support: False
all_pre_delta_within_0.05: False     (ctx=65k で Δ(1584→1585)=+0.40 > 0.05)
all_step_delta_above_0.15: False     (ctx=16k で Δ(1585→1586)=+0.01 < 0.15)
all_ratio_above_5.0: False           (全 ctx で ratio=1.0、step と pre が等しい)
all_peak_ub_equal_1586: False        (ctx=16384 で peak_ub=1585 タイ)
peak_ub_per_ctx: {16384: 1585, 65536: 1586, 131072: 1586}
```

**解釈**: 境界 ub*=1586 の ctx 非依存性予測は完全に崩れた。実際には:

- **ctx=16384**: CUDA0 compute buffer は ub=1584/1585/1586 でほぼ不変（±0.01 MiB）。**境界も step も存在しない**
- **ctx=65536**: 全領域で +0.40 MiB/ub の純線形。**step なし**
- **ctx=131072**: 全領域で +0.65 MiB/ub の純線形。**step なし**
- **ctx=32768 (Sbf3 既存)**: 1585→1586 で +0.24 MiB の step が出る唯一の ctx 値

### 4. graph nodes/splits の ctx・ub 両軸不変性 ✅

全 9 条件で `nodes=4473, splits_pp=136, splits_tg=77` と完全に同じ。ub 軸の不変性は Sb-alloc で確認済み、本 Phase で **ctx 軸の不変性も確認**。

候補 H（graph splits 境界）は ub 軸に加え ctx 軸でも棄却。graph 構造そのものは計算リソース割当に無関係。

### 5. 副次データ: CUDA1/2/3/Host の slope

| ctx | CUDA0 slope | CUDA1 slope | CUDA2 slope | CUDA3 slope | Host slope |
|---|---|---|---|---|---|
| 16384 | 0.010 | 0.25 | 0.25 | 0.98 | 0.085 |
| 65536 | 0.400 | 0.345 | 0.345 | 0.98 | 0.27 |
| 131072 | 0.650 | 0.470 | 0.470 | 0.98 | 0.52 |

- **CUDA3**: 0.98 MiB/ub で ctx 完全不依存（Phase R / Sb-alloc 既知、再確認）
- **CUDA1/2**: slope が ctx 依存（+0.25 → +0.345 → +0.470）。CUDA1/2 も cross 項あり
- **Host**: slope が ctx 依存（+0.085 → +0.27 → +0.52）。Host 側も cross 項あり
- **CUDA0**: 最も強い ctx 依存性（+0.010 → +0.400 → +0.650）、ratio 最大

## ボトルネック・副次発見の分析

### 1. 境界 ub*=1586 は「ctx=32k 固有の現象」

Sb-fine3 で観測された ub=1585→1586 の step は、**ctx=32768 でのみ出現する特異点**であることが確定。ctx=16k では step も線形もなく完全平坦、ctx=65k/131k では境界なしの純線形。

物理解釈: ctx=32k はちょうど「ub 感度ゼロ域」と「ub 感度あり域」の遷移域にあり、ub が小さい領域ではゼロ、ub が大きい領域では線形、という区分線形が出る。ctx が小さすぎると遷移が ub>>1586 領域で起きるため観測されない（常に平坦）。ctx が大きいと遷移が ub<<1584 で起きるため観測されない（常に線形）。

### 2. CUDA0 slope の ctx 依存性（新規、最重要発見）

| ctx | slope (1584-1586 平均) | 
|---|---|
| 16384 | 0.010 MiB/ub |
| 32768 | 区分線形（0.01 → 0.24 step → 0.285/ub）|
| 65536 | 0.400 MiB/ub |
| 131072 | 0.650 MiB/ub |

slope の ctx 依存性は、**CUDA0 compute buffer 内に ub と ctx の cross 項 ∂²Buf/(∂ub ∂ctx) を持つ tensor が存在**することを示す。

cross 項候補:
- **K/V cache 関連の attention workspace**: Q×K^T の中間結果は (n_heads, n_tokens=ub, n_ctx) に比例
- **FlashAttention tile workspace**: FA kernel が ub × ctx に比例する一時領域を確保する可能性
- **causal mask / attention score buffer**: ub × ctx の行列

ctx=16k で slope がほぼゼロである事実は、ctx が小さいと cross 項の絶対値が計算誤差以下になる、または別のボトルネック（定数項）に吸収されていることを示唆。

### 3. 候補 I-c（build_graph 離散）が相対的に浮上

候補 J が棄却されたことで、Sb-alloc で残っていた 2 仮説のうち **候補 I-c（build_graph 内の ub 依存離散処理）が単独最有力**に。
ただし I-c は「ub 離散」のみで「ctx 依存 slope」の説明ができない。**I-c + 新候補 K（FA/attention workspace の ub×ctx cross 項）** の複合モデルが現実的。

### 4. 候補 J の棄却に至った機構的理由

候補 J は「9 層 SSM × VMM granularity」に基づく仮説だったが:
- SSM 層の出力サイズは n_tokens (=ub) の線形で、ctx には依存しない（attention と異なり recurrent なので）
- したがって候補 J が正なら slope は ctx 不変のはず
- 実測では slope が ctx に強く依存 → **SSM 単独では説明不可能**

これは候補 J の根本的な誤りを示す。9 層 SSM は slope の一部（ctx 独立成分）を構成しうるが、全部は説明しない。

### 5. Sb-alloc 確定モデルの更新

Phase Sb-alloc の確定モデル:

```
CUDA0 slope = 0.28125 MiB/tok (GDN 出力線形項、主因)
            + 0.00405 MiB/tok (残差)
```

は ctx=32768 に特化したモデルだった。より一般的には:

```
CUDA0 compute buffer = f(ub, ctx) ≈ A(ctx) + B(ctx)·ub + 区分項
  A(ctx): 定数項、ctx で 980 / 1162 / 1558 MiB
  B(ctx): slope 項、ctx で 0.010 / 0.40 / 0.65 MiB/ub
  区分項: 特定 (ctx, ub) で離散的に加算（ctx=32k, ub=1586 近傍のみ +0.24 MiB）
```

の形式が実態。ctx=16k/65k/131k では区分項が消失（遷移域が観測域外）。

### 6. 区分項の ctx 依存性 — 新仮説

区分項 ≈ 0.24 MiB が ctx=32k でのみ観測される理由:

- 候補 K (FA workspace cross 項) が ctx=32k では 「ちょうど ub=1586 で VMM granularity 2 MiB の整数倍を跨ぐ」ため量子化ジャンプが出る
- ctx=16k では cross 項が小さすぎて 1 block 内に収まる → 跨がない
- ctx=65k/131k では cross 項が大きすぎて全 ub で線形的に block を跨ぎ続ける → step が埋まる

この仮説は **Phase Sb-tensor-dump** で FA workspace の実サイズを per-node dump すれば確定可能。

## 採用判定

| 項目 | 結果 |
|---|---|
| 9 条件すべてで起動成功 | ✅ 失敗 0 件 |
| CUDA0 compute buffer の sched_reserve 取得 | ✅ 全条件 |
| 候補 J の ctx 非依存性予測 | **❌ 棄却** |
| graph nodes/splits の ctx×ub 両軸不変性 | ✅ 確認（nodes=4473, splits=136/77） |
| CUDA1/2/Host の ctx 依存 slope 発見 | ✅ 副次発見（cross 項存在） |
| CUDA3 の ctx 不依存 slope 再確認 | ✅ 0.98 MiB/ub（Phase R と一致） |
| 候補 J → I-c + 新候補 K への方向性更新 | ✅ 区分項の ctx 依存機構として提示 |
| GPU ロック取得・解放 | ✅ 正常動作、他セッションへの影響なし |

**結論**: **Phase Sb-ctx-boundary は主目的を達成**（候補 J の棄却）。さらに slope の ctx 依存性という重要な新知見を獲得。次 Phase は **Phase Sb-fa0** で fa=0 に切り替えた slope 測定により、候補 K（FA workspace cross 項）を検証するのが最短 path。

## 確定モデル（更新版）

**境界 ub*=1586 の解釈を根本から更新**:

旧（Sb-alloc 時点）:
- 候補 J (9 層 SSM × VMM 非同期累積) 最有力 / 候補 I-c 候補

新（本 Phase 後）:
- **候補 J 棄却**（ctx 非依存性が成り立たない）
- **候補 I-c 単独残存**（ub 離散は説明するが slope ctx 依存は未説明）
- **新候補 K（FA/attention workspace の ub×ctx cross 項）** 追加、I-c と複合

**CUDA0 compute buffer の 2 次元モデル（暫定）**:

```
Buf(ub, ctx) ≈ Buf0(ctx) + slope(ctx)·ub + δ(ub, ctx)
  Buf0(ctx) : ctx=16k→980, 32k→980, 65k→1162, 131k→1558 MiB (定数項)
  slope(ctx): ctx=16k→0.010, 65k→0.400, 131k→0.650 MiB/ub
  δ(ub,ctx) : ctx=32k × ub=1586 近傍のみ +0.24 MiB
```

ctx=32768 の「境界 ub*=1586」は δ 項の観測境界であり、**モデル普遍的な境界ではない**。

## 未検証事項

### 既知項目（Phase Sb-alloc から継続、本 Phase で潰したものに [x]）

- [x] **★最優先: Phase Sb-ctx-boundary 候補（本 Phase）**: 実施、**候補 J 棄却**
- [ ] **★最優先: Phase Sb-tensor-dump 候補（debug build + 全 node size dump）**: 本 Phase で候補 J 棄却、新候補 K 浮上により優先度上昇。FA workspace の per-node size dump で cross 項の実態を確定可能
- [ ] **★最優先: Phase Sb-fa0 候補**: 本 Phase 結果を受けて優先度が更に上昇（候補 K の FA 依存検証として核心）。fa=0 × ctx ∈ {16k, 32k, 65k, 131k} × ub ∈ {1584, 1585, 1586} の 12 条件で slope(ctx) が消えるか確認
- [ ] **★最優先: ub=1586 eval 15.466 t/s の 5-10 run 再現性** (Phase Sbf3 継続) — 本 Phase で「ub*=1586 は ctx=32k 固有」と判明し、eval ピークの ctx 依存性も検証必要
- [ ] **★高優先: ub ≥ 1586 線形モデルの ctx 独立性検証** — 本 Phase で **ctx 依存性が顕著に発見された**、ctx ≥ 32k で個別にモデル再構築必要
- [ ] **★高優先: 境界 ub\* の ctx 依存性** — 本 Phase で **「境界は ctx=32k でのみ出現」と確定**、ctx=20k/24k/28k/36k/40k/48k の細 ctx 走査で遷移メカニズムを特定
- [ ] **★高優先: VMM granularity の実測値確認** — P100 CC 6.0 で `cuMemGetAllocationGranularity()` の戻り値を 1 回計測（新候補 K の量子化閾値の根拠確認）
- [ ] **★高優先: FA parallel_blocks の ub 依存性確認** (候補 I-b) — 本 Phase で FA workspace 仮説が浮上したため優先度上昇
- [ ] **ub=1664 eval 15.451 t/s の 5-10 run 再現性** (Phase Sb-fine 継続)
- [ ] **ub=1584 eval 15.293 t/s の 5-10 run 再現性** (Phase Sb-fine2 継続)
- [ ] **eval 境界挟み込み構造の再現性** (Phase Sb-fine2 継続)
- [ ] **CUDA0 区分モデルの物理的意味** (Phase Sb-fine 継続) — 本 Phase で「ctx=32k 固有の区分項」と位置づけ直し
- [ ] **境界 ub\* の fa 依存性** — Phase Sb-fa0 で検証
- [ ] **境界 ub\* の KV 量子化依存性**: q8_0 KV で境界が移動するか
- [ ] **CUDA0 二次係数 9.104e-6 MiB/token² の物理メカニズム** — 本 Phase の cross 項発見と関連、fa/KV 切替で検証
- [ ] **CUDA0 二次モデルの ctx=262144 外挿** (Phase R-ctx3 継続)
- [ ] **CUDA1/2 cross_e = 1.910e-6, Host = 3.815e-6 MiB/(token·token) の物理メカニズム** — 本 Phase で CUDA1/2/Host 全てで slope の ctx 依存確認、cross 項の存在を数値で裏付け
- [ ] **ub=1280/1792 の eval 性能再現性** (Phase Sb 継続)
- [ ] **ub=1280/1536/1792 × ctx=65k での CUDA0 検証** (Phase Sb 継続) — 本 Phase で ctx=65k slope=0.40 MiB/ub 判明、ub 外挿が可能
- [ ] **中間 ctx (24k / 48k / 96k) での検証** (Phase Sb 継続) — 本 Phase で ctx=16k/32k/65k/131k 4 点、中間点追加で slope(ctx) curve を精密化
- [ ] **ctx=65k 32k prompt の 3 run 以上再計測** (Phase R-ctx3 継続)
- [ ] **CUDA3 が ctx 完全不依存となる物理メカニズム** (Phase R 継続) — 本 Phase で 0.98 MiB/ub を 3 ctx 値で再々確認
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
- [ ] **「初回サイクル効果」の原因特定**
- [ ] **セッション間 warmup ゆらぎの原因特定**
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
- [ ] **J_fa1_warmup run 1 の外れ値（15.54 t/s）再現性**
- [ ] **CUDA1 / CUDA2 の n² 係数 (fa=0 a=1.26e-4) の物理解釈**
- [ ] **ctx=1024 の fa=0 eval 劣化 (−5.2%) の原因**
- [ ] **ctx=512 / 256 の極小域での挙動**
- [ ] **eval 速度のセッション間ゆらぎレンジ更新**
- [ ] **prompt 処理の ctx 非依存の長 ctx 側確認**
- [ ] **fa=1 eval の「谷型」(ctx=2048 最高 → ctx=4096 最低) の再現性**
- [ ] **Phase M のモデルを f16 KV → q8_0 KV（C-D3 採用構成）に適用した場合の整合性**
- [ ] **ctx=6144 等の中間 ctx での fa=1 / fa=0 境界確認**
- [ ] **fa=0 ctx=8192 で CUDA1 空き枠を増やす手法**
- [ ] **eval 谷型の最低値 ctx の fa=1 における物理原因**

### 既知項目（Phase Q/S 継続）

- [ ] **`-ub=1 (greedy)` でのベンチマーク**
- [ ] **`-ub > -b` の挙動（llama.cpp 制約検証）**
- [ ] **fa=0 側での `-ub` 支配性の確認**
- [ ] **大 prompt での `-ub` 依存性** (4k/8k/16k prompt 未検証)
- [ ] **`-b > -ub` 運用の意義**: Phase P で観測のみ
- [ ] **`--parallel 2` との相互作用**
- [ ] **P3 vs Phase O の eval 差 +1.17% のセッション源**

### 既知項目（Phase Sb-src から継続）

- [ ] **Phase Sb-src 新規 ★: 境界 ub\* のモデル固有性検証** (Qwen3.5-35B-A3B 等)
- [ ] **Phase Sb-src 新規 ★: 境界 ub\* の fa 依存性** — Phase Sb-fa0 で検証
- [ ] **Phase Sb-src 新規 ★: 残差 4,247 bytes/tok の分解** — 本 Phase の cross 項発見で分解方向が見えた
- [ ] **Phase Sb-src 新規: ub ≤ 1585 平坦域 slope 0.0125 MiB/tok の由来** — 本 Phase で「ctx=16k では 0.010 MiB/tok」と類似の超平坦を確認
- [ ] **Phase Sb-src 新規: fused_gdn_ar / ch の実際のパス切替え**
- [ ] **Phase Sb-src 新規: ggml_gated_delta_net 出力 4 MiB 定数寄与の allocator 扱い**
- [x] **Phase Sb-src 新規: ncols1=4 による 4-token 周期性の観測可能性** (Sb-alloc で棄却済み、本 Phase で変更なし)

### 既知項目（Phase Sb-alloc から継続、本 Phase で部分解消または更新）

- [x] **★最優先: Phase Sb-ctx-boundary 候補** — 本 Phase で実施、**候補 J 棄却**
- [ ] **Phase Sb-alloc 新規: 9 層 SSM 出力の allocator 内配置順序の特定** — 本 Phase で候補 J 棄却により優先度低下
- [ ] **Phase Sb-alloc 新規: CUDA_Host buffer (235 MiB) の用途** — 本 Phase で Host slope の ctx 依存確認（0.085 → 0.52）、cross 項が Host にも存在

### 新規項目（本 Phase Sb-ctx-boundary で判明・発生）

- [ ] **★最優先: 新候補 K の仕様化と検証** — 本 Phase で「CUDA0 slope の ctx 依存性 (0.010→0.400→0.650 MiB/ub)」を発見。FA/attention workspace の ub×ctx cross 項が有力候補。Phase Sb-tensor-dump で `flash_attn_ext.cu` / `soft_max.cu` の workspace tensor size を dump
- [ ] **★最優先: 区分項 δ(ub, ctx) の ctx 依存性機構** — 本 Phase で「区分項 +0.24 MiB は ctx=32k でのみ出現」と確定。ctx=20k/24k/28k/36k/40k/48k の細 ctx 走査で δ(ub=1586, ctx) の形状を特定
- [ ] **★最優先: CUDA1/2/Host の cross 項の定量的 fitting** — 本 Phase で CUDA1/2 slope が 0.25→0.345→0.470、Host が 0.085→0.27→0.52 と判明。slope = a + b·ctx で fit 可能かを検証
- [ ] **★高優先: Phase Sb-fa0 の設計拡張** — 元プランは fa=0 × ctx=32k × ub=1580-1592 の 6 条件。本 Phase 結果を受けて fa=0 × ctx ∈ {16k, 32k, 65k, 131k} × ub ∈ {1584, 1585, 1586} の 12 条件に拡張推奨（slope の ctx 依存が FA に起因するか検証）
- [ ] **★高優先: ctx × ub の 2D 完全走査** — ctx ∈ {16k, 24k, 32k, 40k, 48k, 65k, 96k, 131k} × ub ∈ {1584, 1586, 1600, 1664} の 32 条件で slope(ctx) curve を精密化（Phase Sb-ctx-fine 候補）
- [ ] **★中優先: CUDA3 slope 0.98 MiB/ub の物理根拠** — 本 Phase でも完全 ctx 不依存を再確認。CUDA3 は純粋に n_tokens 線形項のみで構成される tensor を保持（attention に関与しない層のみ割当）と推定、ソース確認が必要
- [ ] **★中優先: ub=1584 が llama.cpp 下限拒否にならなかった確認** — Phase Q で -ub 内部下限が観測されたが、本 Phase では 1584 が通った。ub の下限は「-b=-ub」条件でない場合に出現する可能性

## 検証完了後に実施すべき TODO

### 既知項目（Phase Sb-alloc から継続）

- [ ] **start.sh の拡張**: `LLAMA_NUMACTL_PREFIX` / `LLAMA_EXTRA_THREADS` 環境変数サポート追加
- [ ] **CUDA1 セーフティマージン OOM フォールバック実装**
- [ ] **C-4 実験**（CPU 層削減 + GPU 層追加）
- [ ] **drop_caches 権限の確保**（sudoers 設定 or vmtouch 導入）
- [ ] **start.sh での NUMA プリセット整備**
- [ ] **start.sh に `--threads` 設定追加**
- [ ] **`start_phaseJ.sh` 〜 `start_phaseSbctx.sh` の環境変数化を skill 側 `start.sh` に逆輸入**
- [ ] **依存制約の lint 化**: 起動前 pre-check
- [ ] **llama.cpp upstream issue/PR のサーベイ**
- [ ] **`measure_phaseI.sh` を汎用化して skill に組み込む**
- [ ] **「長コンテキスト性能カード」をモデル単位で記録するドキュメント整備**
- [ ] **アプリ側にコンテキストサイズ別レイテンシ警告を出す仕組み**

### 新規項目（本 Phase Sb-ctx-boundary で更新）

- [ ] **★最優先: Phase Sb-tensor-dump（debug build）** — 優先度上昇。本 Phase で候補 J 棄却・新候補 K 浮上、per-node dump で FA workspace の cross 項を確定
- [ ] **★最優先: CLAUDE.md / skill 更新**: 「**境界 ub*=1586 は ctx=32k 固有の現象であり、モデル普遍的境界ではない。CUDA0 compute buffer は 2 次元モデル Buf(ub, ctx) = Buf0(ctx) + slope(ctx)·ub + δ(ub, ctx) の形式**」と記載
- [ ] **★最優先: 起動前 lint の CUDA0 モデル更新**（本 Phase で大幅変更必要）:
  - 旧: `ub ≤ 1585: CUDA0 ≈ 966.5 + 0.0064·ub`, `ub ≥ 1586: 1002.61 + 0.2853·(ub-1664)` の 2 区分（ctx=32k 前提）
  - 新: `CUDA0 ≈ A(ctx) + B(ctx)·ub` + ctx=32k 近傍で δ 項
    - A(ctx=16k) ≈ 980.11 MiB, B(ctx=16k) ≈ 0.010 MiB/ub
    - A(ctx=32k) ≈ 980.0 MiB, B(ctx=32k) 区分（1585 以下 ≈ 0.01、1586 以上 ≈ 0.285）
    - A(ctx=65k) ≈ 1162.22 MiB, B(ctx=65k) ≈ 0.40 MiB/ub
    - A(ctx=131k) ≈ 1558.22 MiB, B(ctx=131k) ≈ 0.65 MiB/ub
    - 線形補間は非推奨（slope が非線形に ctx 増加）
  - マージン: 線形域では +20 MiB、ctx=32k 近傍 ub=1586 遷移域では +30 MiB
- [ ] **★最優先: 4p cross 項モデル 31 点版組み込み** (Phase Sb-fine2 から継続) — 本 Phase の cross 項発見と整合性確認
- [ ] **★最優先: compute buffer 予測モデル（本 Phase 確定 2D 版）を skill / CLAUDE.md に記録**
- [ ] **★最優先: skill 側 `.claude/skills/llama-server/scripts/start.sh:155` のデフォルト判断保留** — 「ub=1586 eval 最速」は ctx=32k 固有の可能性が大、ctx 別に再検証必要
- [ ] **★高優先: Phase Sb-fa0 の拡張実施** — 本 Phase 結果を受けて fa=0 × 4 ctx × 3 ub (12 条件) で candidate K 検証
- [ ] **★高優先: Phase Sb-ctx-fine 候補** — ctx=20k/24k/28k/36k/40k/48k の細 ctx 走査（8 ctx × 3 ub = 24 条件）で δ 項の ctx 依存性を特定
- [ ] **★高優先: Phase Sb-KV8 候補**: `--cache-type-{k,v} q8_0` で再実施 — 本 Phase cross 項が KV サイズ連動なら q8_0 で slope が半減するはず
- [ ] **★最重要: Phase S-eval 候補**: ctx=32k × ub=1586/1664 eval ピーク 2 点を 5-10 run で再現性検証 — 本 Phase で eval 最適 ub が ctx=32k 固有である可能性が示唆されたため、ctx 別 eval 最適 ub も合わせて測定検討
- [ ] **Phase Q-2 候補**: `-ub=64/32/16/8/4/2/1`
- [ ] **Phase Q-3 候補**: ub=1586 周辺 ±8 token で eval ピーク形状
- [ ] **skill 側 start.sh の `ssh -f` stdout redirect 改修**
- [ ] **start.sh のデフォルト `ctx-size` を 131072 に更新**
- [ ] **モデルカード更新**: Qwen3.5-122B-A10B の長コンテキスト性能カードに「**CUDA0 compute buffer は 2 次元モデル Buf(ub, ctx) で表現。ub*=1586 境界は ctx=32k 固有**」を明記
- [ ] **Phase Sb-src-cu kernel profile 候補**: nvprof/ncu でub=1586 付近の FA kernel と buffer 計測 — 新候補 K 直接検証
- [ ] **Phase Sb-ctx-131k-eval 候補**: ctx=131k で eval 最速 ub を探索（本 Phase で ctx=131k が最大 slope と判明、ub 小さめが有利な可能性）

## 補足

### Phase Sb-ctx-boundary の核心発見（サマリ）

1. **候補 J 棄却**: 境界 ub*=1586 は ctx 非依存ではなく、**ctx=32k 固有の現象**であることが確定。9 条件中 ctx=32k 以外では step は一切観測されず
2. **slope(ctx) の強 ctx 依存性発見**: CUDA0 slope は ctx=16k で 0.010、ctx=65k で 0.400、ctx=131k で 0.650 MiB/ub と ctx に強く依存。**cross 項 ∂²Buf/(∂ub ∂ctx) の存在を数値で確認**
3. **graph nodes/splits の ctx×ub 両軸不変**: 4473/136/77 が全条件で不変。graph 構造仮説（候補 H）は ub に加え ctx でも棄却
4. **CUDA1/2/Host も cross 項あり**: CUDA0 以外の buffer でも ctx 依存 slope を観測（CUDA3 は例外、純 ub 線形）
5. **新候補 K 浮上**: FA/attention workspace の ub × ctx cross 項が最有力。Q × K^T 中間結果 ∝ ub × ctx で説明可能
6. **候補 I-c も残存**: ub 離散処理（build_graph）は説明必要、I-c + K の複合モデルが現実的
7. **2D compute buffer モデル**: `Buf(ub, ctx) = Buf0(ctx) + slope(ctx)·ub + δ(ub, ctx)` の形式に更新。δ は ctx=32k 近傍で観測、他 ctx では 0

### Phase Sb-alloc との対照

| Phase Sb-alloc | Phase Sb-ctx-boundary |
|---|---|
| 候補 D (1 MiB alloc 量子化) 棄却、候補 J 最有力 / 候補 I-c 候補 | 候補 J **棄却**、I-c 残存、新候補 K 浮上 |
| 境界 ub\*=1586 は ctx 非依存と予測 | 境界 ub\*=1586 は **ctx=32k 固有**と確定 |
| 9 層 SSM × VMM 非同期累積で説明 | SSM は ctx 非依存 → 新候補 K (FA/attention cross 項) が必要 |
| 次 Phase: Sb-tensor-dump / Sb-ctx-boundary / Sb-fa0 | Sb-fa0 (拡張) / Sb-tensor-dump / Sb-ctx-fine の優先度上昇 |

### 作業終了時点の状態

- **GPU サーバロック: 解放済み (t120h-p100)、他セッションから利用可能**
- 作業ディレクトリ `report/attachment/2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary/` を保持
- 生成物: plan.md / start_phaseSbctx.sh / batch_Sbctx.sh / batch_Sbctx.log / startup_logs/ (9 ファイル) / summary_Sbctx.tsv / Sbctx_pivot.csv / Sbctx_slopes.csv / Sbctx_verdict.txt / analyze_Sbctx.py
- **主要発見**:
  - Phase Sb-alloc 候補 J の**棄却**
  - slope(ctx) の ctx 依存性発見（新候補 K）
  - 境界 ub\*=1586 は ctx=32k 固有
  - CUDA0 compute buffer の 2 次元モデル形式確立
- **次の推奨 Phase**:
  1. **Phase Sb-fa0 (拡張版)**: fa=0 × 4 ctx × 3 ub = 12 条件、所要約 25 分（新候補 K の FA 検証）
  2. **Phase Sb-ctx-fine**: 細 ctx 走査で δ(ub=1586, ctx) の形状特定、所要約 40 分
  3. **Phase Sb-tensor-dump**: debug build で per-node dump、候補 K 確定、所要 2-3 時間
  4. **Phase S-eval**: ctx 別 eval 最適 ub 再検証、所要 30-60 分
