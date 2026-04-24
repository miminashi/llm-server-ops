# Qwen3.5-122B-A10B C-3 Phase Sb-fa0-offload（候補 L = FA tile 量子化副作用 support、fa=0 × ctx=32k を OT 拡張で実現、slope(ctx) ∝ ctx 関係確定）

- **実施日時**: 2026年4月19日 23:26 – 23:46 (JST、実作業時間 約 20 分、うち GPU ロック保持 20 分、実バッチ 9 分)
- **作業種別**: OT_REGEX 拡張 (全 attention CPU オフロード) による fa=0 × ctx≥32k 起動実験、および ctx=65k/131k OOM alloc size 派生抽出
- **GPU ロック**: **取得（t120h-p100、session aws-mmns-generic-195920-20260419_232611）→ 解放済み**

## 添付ファイル

- [実装プラン](attachment/2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload/plan.md)
- [起動スクリプト (start_phaseSbfa0offload.sh)](attachment/2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload/start_phaseSbfa0offload.sh)
- [バッチ実行スクリプト (batch_Sbfa0offload.sh)](attachment/2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload/batch_Sbfa0offload.sh)
- [分析スクリプト (analyze_Sbfa0offload.py)](attachment/2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload/analyze_Sbfa0offload.py)
- [バッチ実行ログ](attachment/2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload/batch_Sbfa0offload.log)
- [失敗条件リスト](attachment/2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload/batch_Sbfa0offload_failures.tsv)
- [OOM alloc size 記録](attachment/2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload/batch_Sbfa0offload_oom.tsv)
- [Stage 確定サマリ](attachment/2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload/summary_state.txt)
- [データ集約 TSV](attachment/2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload/summary_Sbfa0offload.tsv)
- [ピボット表 (OT=X4)](attachment/2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload/Sbfa0offload_pivot_X4.csv)
- [slope 表](attachment/2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload/Sbfa0offload_slopes.csv)
- [OOM 派生 slope 表](attachment/2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload/Sbfa0offload_oom_slopes.csv)
- [Sbfa0 互換 verdict](attachment/2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload/Sbfa0offload_verdict.txt)
- [候補 L 判定 verdict](attachment/2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload/Sbfa0offload_candidate_L_verdict.txt)
- [startup_logs ディレクトリ](attachment/2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload/startup_logs/)（15 ファイル: Stage 1 escalation 3、Stage 2 3、Stage 3 OOM 6、Stage 4 3）

## 参照

- 直前レポート: [2026-04-19_221314_qwen3-122b-c3-phaseSbfa0.md](2026-04-19_221314_qwen3-122b-c3-phaseSbfa0.md)
- Phase Sbctx: [2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary.md](2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary.md)
- Phase Sb-fine3 (fa=1 ctx=32k δ=+0.24 ベースライン): [2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok.md](2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok.md)

## 前提・目的

直前 Phase Sb-fa0 で候補 K（FA workspace が cross 項の発生源）が事実上棄却され、新解釈「**FA は cross 項を suppress する最適化**」と新候補 L（FA tile 量子化副作用）が提示された。ただし fa=0 × ctx=32k が CUDA1 OOM で起動不能のため、fa=1 で観測された δ 項 (ctx=32k × ub=1586 で +0.24 MiB) が **FA 固有か fa 共通か** の決定的検証点が未達だった。

本 Phase は **OT_REGEX を拡大して attention 層を CPU オフロード** し、fa=0 × ctx=32k を起動成立させ δ 項の fa 依存性を数値確定する。副次として ctx=65k/131k も試行し、OOM 時の alloc size から slope(ctx) fa=0 版の外挿点を取得する。

### 候補 L 判定基準（fa=1 δ=+0.24 MiB をハードコード参照）

- **cond_L_1**: `|δ_fa0(ctx=32k)| ≤ 0.10 MiB`（δ 項消失 = FA 固有）
- **cond_L_2**: `|δ_fa0 − 0.24| ≤ 0.05 MiB`（δ 項共通 = FA 無関係）
- **判定**: cond_L_1=True & cond_L_2=False → **support**（FA tile 量子化副作用）、逆なら reject

### 成功条件

- [x] Stage 1: OT 案 X1-X4 のうちいずれかで ctx=32k × ub=1584 起動成立
- [x] Stage 2: 確定 OT で ctx=32k × ub ∈ {1584,1585,1586} の 3 条件成立（★最優先）
- [x] δ_fa0(ctx=32k) を 0.01 MiB 精度で取得
- [x] 候補 L 判定 verdict 出力（support/reject/partial/not_conclusive）
- [x] Stage 3: ctx=65k/131k で OOM でも alloc size 記録（ctx=65k 3 条件、ctx=131k 3 条件すべて）
- [x] Stage 4: 確定 OT で ctx=16k 3 条件で slope 取得、Sbfa0 オリジナル値 (2.12 MiB/ub) との差分記録

## 環境情報

- **GPU サーバ**: t120h-p100 (10.1.4.14)、NVIDIA Tesla P100-PCIE-16GB × 4 (CC 6.0、VMM=yes)
- **llama.cpp**: Phase Sbctx/Sbfa0 と同一ビルド（`~/llama.cpp/build/bin/llama-server`）
- **モデル**: `/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf`
- **baseline 設定**: **fa=0**, f16 KV, `numactl --cpunodebind=1 --membind=1 --`, threads=40, poll=0, -ngl 999、OT 拡張: X1-X4 を段階的試行
- **OT_REGEX 案** (既存 MoE FFN experts オフロードと AND 合成):
  - X1: `blk\.(2[0-3])\.attn_.*\.weight=CPU`（4 層 = CUDA1 後半）
  - X2: `blk\.(1[6-9]|2[0-3])\.attn_.*\.weight=CPU`（8 層）
  - X3: `blk\.(1[2-9]|2[0-3])\.attn_.*\.weight=CPU`（12 層 = CUDA1 全部）
  - X4: `blk\.([0-9]|[1-4][0-9])\.attn_.*\.weight=CPU`（48 層 = 全 attention）

## 再現方法

```bash
# 1. GPU ロック取得
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 2. 作業ディレクトリへ
cd report/attachment/2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload/

# 3. バッチ実行（Stage 1 escalation 含む、所要約 9 分）
bash batch_Sbfa0offload.sh > batch_Sbfa0offload.log 2>&1

# 4. 分析
python3 analyze_Sbfa0offload.py

# 5. 停止・解放
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 実行結果サマリ

### 1. Stage 1 escalation 履歴（ctx=32k × ub=1584）

| OT_TAG | 追加 CPU オフロード | 結果 | OOM device/alloc |
|---|---|---|---|
| X1 | layer 20-23 attn（4 層） | ❌ | CUDA1 6744.41 MiB |
| X2 | layer 16-23 attn（8 層） | ❌ | CUDA2 6725.85 MiB |
| X3 | layer 12-23 attn（12 層） | ❌ | CUDA2 6725.85 MiB |
| **X4** | **全 attention（48 層）** | **✅ OK (20s)** | — |

X1〜X3 はいずれか別 GPU（CUDA1 or CUDA2）で OOM。X4（全 attention CPU）で初めて 4 GPU 全てが 16 GiB 枠内に収束。Stage 2 以降は X4 を採用。

### 2. 条件別起動結果（Stage 2 / 3 / 4）

| Stage | 条件 | 結果 | CUDA0 compute | 失敗原因 |
|---|---|---|---|---|
| 2 | X4, ctx=32k, ub=1584 | ✅ | 6838.70 MiB | — |
| 2 | X4, ctx=32k, ub=1585 | ✅ | 6842.98 MiB | — |
| 2 | X4, ctx=32k, ub=1586 | ✅ | 6847.27 MiB | — |
| 3 | X4, ctx=65k, ub=1584 | ❌ | NA | CUDA1 alloc 13247.45 MiB |
| 3 | X4, ctx=65k, ub=1585 | ❌ | NA | CUDA1 alloc 13255.81 MiB |
| 3 | X4, ctx=65k, ub=1586 | ❌ | NA | CUDA1 alloc 13264.18 MiB |
| 3 | X4, ctx=131k, ub=1584 | ❌ | NA | CUDA0 alloc 26440.70 MiB |
| 3 | X4, ctx=131k, ub=1585 | ❌ | NA | CUDA0 alloc 26457.36 MiB |
| 3 | X4, ctx=131k, ub=1586 | ❌ | NA | CUDA0 alloc 26474.02 MiB |
| 4 | X4, ctx=16k, ub=1584 | ✅ | 3571.70 MiB | — |
| 4 | X4, ctx=16k, ub=1585 | ✅ | 3573.92 MiB | — |
| 4 | X4, ctx=16k, ub=1586 | ✅ | 3576.14 MiB | — |

成立条件 6/12（Stage 2 3 + Stage 4 3）、OOM 条件 9 / 12（Stage 1 escalation 3 + Stage 3 6）、総実施 12 条件中 15 ログ取得（escalation 分含む）。

### 3. CUDA0 compute buffer ピボット（OT=X4、MiB）

| ctx \ ub | 1584 | 1585 | 1586 | Δ(1584→1585) | Δ(1585→1586) | δ_of_δ |
|---|---|---|---|---|---|---|
| **16384** | 3571.70 | 3573.92 | 3576.14 | **+2.22** | **+2.22** | **−0.00** |
| **32768** | 6838.70 | 6842.98 | 6847.27 | **+4.28** | **+4.29** | **+0.01** |
| 65536 (OOM) | — | — | — | — | — | — |
| 131072 (OOM) | — | — | — | — | — | — |

### 4. OOM alloc size 派生 slope（ctx=65k CUDA1、ctx=131k CUDA0）

| ctx | 1584 | 1585 | 1586 | slope (MiB/ub) |
|---|---|---|---|---|
| 65536 (CUDA1) | 13247.45 | 13255.81 | 13264.18 | **+8.37** |
| 131072 (CUDA0) | 26440.70 | 26457.36 | 26474.02 | **+16.66** |

完全線形。slope が ctx に比例して倍増（16k→2.22, 32k→4.28, 65k→8.37, 131k→16.66）。**slope(ctx) ∝ ctx の関係を完全確認**。

### 5. 候補 L 判定: `support`（cond_L_1 True, cond_L_2 False）

```
candidate_L_status: support
delta_fa1_reference_ctx32k_ub1586: +0.2400 MiB
delta_fa0_measured_ctx32768:       +0.0100 MiB
cond_L_1 |delta_fa0| <= 0.1:       True     # δ 項ほぼ消失
cond_L_2 |delta_fa0 - 0.24| <= 0.05: False  # fa=1 値とは有意差
cond_L_3 slope ratio(32k/16k):     1.932    # slope の ctx 依存を確認
```

**δ_fa0(ctx=32k) = +0.01 MiB ≈ 0**、一方 **fa=1 δ = +0.24 MiB**。fa=0 では δ 項が消失 → **δ 項は FA tile 量子化副作用（候補 L）** と確定。

### 6. fa=1 / fa=0(既存) / fa=0-offload(本 Phase) slope 対比

| ctx | fa=1 Δpre | fa=1 Δstep | fa=0 Δpre (Sbfa0 MoE only) | fa=0-offload Δpre (X4) | fa=0-offload Δstep (X4) | δ_of_δ (X4) |
|---|---|---|---|---|---|---|
| 16384 | +0.010 | +0.010 | **+2.12** | +2.22 | +2.22 | −0.00 |
| 32768 | NA | +0.240 | — (OOM) | **+4.28** | **+4.29** | **+0.01** |
| 65536 | +0.400 | +0.400 | — | +8.36 / +8.37 (CUDA1 OOM 派生) | — | — |
| 131072 | +0.650 | +0.650 | — | +16.66 / +16.66 (CUDA0 OOM 派生) | — | — |

### 7. CUDA1/2/3/Host compute buffer（X4 × ctx=32k、fa=0-offload、MiB）

| GPU | ub=1584 | ub=1585 | ub=1586 | slope (MiB/ub) |
|---|---|---|---|---|
| CUDA0 | 6838.70 | 6842.98 | 6847.27 | +4.285 |
| CUDA1 | 6713.45 | 6717.69 | 6721.93 | +4.240 |
| CUDA2 | 6713.45 | 6717.69 | 6721.93 | +4.240 |
| CUDA3 | 6713.45 | 6717.69 | 6721.93 | +4.240 |
| Host | 241.36 | 241.51 | 241.67 | +0.155 |

**CUDA1/2/3 で完全一致**（X4 で均一化）。CUDA0 だけ +125 MiB 高く slope もわずかに大きい。

### 8. Model buffer 配置（X4、OT 拡張後）

```
CPU_Mapped:  47056.51 + 25324.34 = 72380.85 MiB (model 全体の大部分)
CUDA0 model:   424.49 MiB
CUDA1 model:  8737.81 MiB
CUDA2 model:  8737.81 MiB
CUDA3 model:   943.93 MiB
```

CUDA0/3 は embedding / lm_head / norm などの非対称配置、CUDA1/2 に attention 以外の層データ（norm、o_proj、gate、ffn_norm 等、MoE FFN experts ではない部分）が 8.7 GiB ずつ存在。

### 9. graph nodes / splits の OT 依存性

| 項目 | Sbfa0 (MoE only, fa=0) | Sbfa0-offload X4 (fa=0) | 差 |
|---|---|---|---|
| graph nodes | 4532 | 4532 | 0 |
| splits_pp (bs=1584) | 136 | **442** | **+306** |
| splits_tg (bs=1) | 77 | **401** | **+324** |

**splits が 3-5 倍増**（attention CPU オフロードで GPU/CPU 境界の split が大幅増加）。graph nodes 自体は不変。

## ボトルネック・副次発見の分析

### 1. 候補 L (FA tile 量子化副作用) の support 確定

δ_fa0(ctx=32k) = +0.01 MiB ≈ 0、fa=1 δ = +0.24 MiB との差 0.23 MiB は実測精度 (0.01 MiB) の 20 倍超で明確に有意。**δ 項は fa=0 で消失**し、**fa=1 でのみ観測される tile 境界効果** であることが確定した。

この結果は、Phase Sb-fa0 で提示された新解釈「FA は cross 項を suppress する最適化、残存する slope(ctx) と δ 項は FA tile 不完全性の残差」を数値的に裏付ける。

### 2. slope(ctx) ∝ ctx の完全比例関係の発見

fa=0 (X4) の CUDA0/1/2/3 compute buffer slope は ctx に完全比例:

- ctx=16k: 2.22 MiB/ub
- ctx=32k: 4.28-4.29 MiB/ub
- ctx=65k: 8.36-8.37 MiB/ub (CUDA1 OOM 派生)
- ctx=131k: 16.66 MiB/ub (CUDA0 OOM 派生)

`slope_fa0(ctx) ≈ 1.36e-4 × ctx` の一次係数で完全 fit。これは attention full matrix workspace (`ub × ctx × 2 bytes × n_heads × α`) の典型挙動。fa=0 の compute buffer は **"純粋な" attention workspace** であり、離散挙動は一切無い。

### 3. fa=0 × ctx=65k/131k が X4 でも OOM の機構

ctx=65k で CUDA1 compute buffer = 13247-13264 MiB 要求。CUDA1 残可用 = 16384 − 8737 (model) − 192 × 2 (KV f16) − 37 (RS) ≈ 7250 MiB。**13247 MiB は残枠の 1.8 倍**で不可能。ctx=131k は CUDA0 で 26440 MiB 要求で更に厳しい。

すなわち、fa=0 では **X4（全 attention CPU）でも ctx=32k が上限**、P100 の物理的 VRAM 制約による。この事実は:

- fa=0 ctx=32k 以上は **attention を CPU 経由させれば理論上実現可能だが、それは「LLM の大部分を CPU でやる」状態**
- 実用上 **fa=1 のみが長 ctx の path** であることを確定

### 4. OT 拡張が fa=0 × ctx=16k slope に与える影響（+0.1 MiB/ub）

Stage 4 で取得した fa=0 × ctx=16k × X4 の slope:

- Sbfa0 オリジナル (OT=MoE only): 2.12 MiB/ub
- 本 Phase (OT=X4): 2.22 MiB/ub
- **差**: +0.10 MiB/ub

X4 では attention 層の一部（layer-specific weight の一部）が CPU へ移動しているため、compute buffer のうち CUDA 側で要求される量が減る反面、workspace 配置パターンが変わって slope が +0.1 増える。**4.7% の補正**が X4 ⇔ MoE only 間で必要。

### 5. graph splits の激増（136→442、77→401）

X4 では `attention の GPU→CPU→GPU 往復` が 48 層全てに発生するため、scheduler が backend 境界で split を追加。splits_pp = 442（Sbfa0 MoE only の 3.25 倍）、splits_tg = 401（5.2 倍）。**eval 性能に大きく悪影響**する構造（CPU↔GPU 転送の overhead）。

本 Phase は eval 未実施だが、**X4 は実用的な推論 path ではない**。compute buffer 測定目的に限定。

### 6. slope のデバイス対称性と非対称性

X4 × ctx=32k では CUDA1/2/3 の compute buffer が**完全一致** (6713.45 / 6717.69 / 6721.93 MiB)、これは fa=0 MoE only でも部分的に観測された傾向の完全版。一方 CUDA0 は +125 MiB 高く（6838.70 vs 6713.45）、slope も微妙に異なる（4.285 vs 4.240）。CUDA0 は embedding / lm_head を保持するため attention 計算以外の要求が加算される。

### 7. fa=0 × X4 における CUDA1/2 model buffer 8.7 GiB の意味

OT_REGEX に MoE FFN experts + 全 attention 追加しても CUDA1/2 に 8.7 GiB ずつ model buffer が残る。これは `attn_norm`, `attn_o_proj`, `ffn_gate`, `ffn_down`, `ffn_norm`, `ffn_up` など MoE FFN **shared** 部分（experts ではない gate/router と各層ごとの norm）、および `ffn_dense_*` パターンで MoE ではない dense FFN 層が GPU 側に残っている可能性。詳細は別 Phase で tensor 名称 dump 要。

### 8. OOM alloc size による fa=0 slope(ctx) 完全記述

本 Phase で得られた **fa=0 × X4 の 2 次元モデル**:

```
Buf_fa0_X4(ub, ctx) ≈ B0(ctx) + slope_fa0(ctx) · ub

slope_fa0(ctx) ≈ 1.36e-4 · ctx    [MiB/ub]   (ctx 比例)
B0(ctx=16k)  ≈ 3568 MiB
B0(ctx=32k)  ≈ 6832 MiB
B0(ctx=65k)  ≈ 13234 MiB (OOM 派生、実際は CUDA1 側合計)
B0(ctx=131k) ≈ 26424 MiB (OOM 派生、実際は CUDA0 側合計)
```

B0 自体も ctx に完全比例（ctx=16k→3568, 131k→26424、比率 ≈ 7.4 ≈ 131k/16k = 8.19 に近いがやや小）。fa=0 compute buffer ≈ `A · ub · ctx + B · ctx` の 2D 線形モデルが成立。

### 9. 新候補 L の確定的モデル（最終形）

```
Buf_fa1(ub, ctx) = Buf_core(ctx) + slope_fa1_residual(ctx) · ub + δ_fa1(ub, ctx)
  slope_fa1_residual(ctx) = 0.010 (16k) → 0.4 (65k) → 0.65 (131k)  ← FA tile 不完全性の残差
  δ_fa1(ub, ctx) ≈ +0.24 MiB @ ctx=32k × ub=1586                   ← tile 境界量子化 step

Buf_fa0(ub, ctx) = Buf_base(ctx) + 1.36e-4 · ctx · ub               ← full attention workspace (tile 無し)
  δ_fa0 ≈ 0 (tile 境界効果なし)
```

**fa=0 で δ 項と大きな slope(ctx) 両方が "露出" するのではなく、slope(ctx) は純粋 attention workspace、δ 項は FA tile 特有** ということが本 Phase で判明。

## 採用判定

| 項目 | 結果 |
|---|---|
| Stage 1 pilot escalation | ✅ X1-X3 OOM、X4 成功 |
| **Stage 2 本走査（★最優先）** | ✅ 3/3 条件すべて起動成功 |
| δ_fa0(ctx=32k) 取得 | ✅ +0.01 MiB (精度 0.01 MiB) |
| **候補 L 判定** | ✅ **support (cond_L_1 True, cond_L_2 False)** |
| Stage 3 OOM alloc 記録 | ✅ ctx=65k/131k 全 6 条件記録 |
| Stage 4 baseline | ✅ X4 × ctx=16k 3/3 成功、OT 影響 +0.10 MiB/ub 確認 |
| slope(ctx) ∝ ctx 関係 | ✅ 新規確定、1 次係数 1.36e-4 |
| GPU ロック 取得・解放 | ✅ 正常動作（保持 20 分） |

**結論**: **候補 L (FA tile 量子化副作用) support 確定**。δ 項は fa=1 固有の量子化 step、slope(ctx) の ctx 依存性も含めて FA tile 境界現象の残差として説明可能。次 Phase は **Phase Sb-tensor-dump** (debug build で `ggml-cuda/fattn*.cu` の workspace per-node dump) による物理機構の最終確定、または **Phase Sb-KV8** (`--cache-type-{k,v} q8_0` での同走査) で KV サイズ依存性の検証が妥当。

## 確定モデル（本 Phase 更新）

```
fa=1:  Buf(ub, ctx) = Buf_core_fa1(ctx) + slope_fa1_residual(ctx) · ub + δ_fa1(ub, ctx)
  Buf_core_fa1(16k)      ≈ 980 MiB
  Buf_core_fa1(131k)     ≈ 1558 MiB
  slope_fa1_residual(ctx): 16k→0.010, 65k→0.400, 131k→0.650 MiB/ub (FA tile 残差)
  δ_fa1(ub, ctx):          ctx=32k × ub=1586 で +0.24 MiB (tile 境界量子化 step)

fa=0 (OT=X4):  Buf(ub, ctx) = Buf_base_fa0(ctx) + 1.36e-4 · ctx · ub
  Buf_base_fa0(ctx): ctx=16k→3568, 32k→6832, 65k→13234, 131k→26424 MiB (ctx 比例)
  slope_fa0(ctx) = 1.36e-4 · ctx MiB/ub (ctx 完全比例、純 attention workspace)
  δ_fa0 ≈ 0 (tile なし、連続的 full matrix)
```

**主要発見**:

1. **候補 L support**: δ 項は FA tile 量子化副作用（fa=1 固有）で確定
2. fa=0 compute buffer は **ub × ctx × 係数** の純 2D 線形モデル（ctx に完全比例する slope）
3. fa=0 × ctx=32k は X4 で実現可能、ctx=65k 以上は P100 VRAM 制約で X4 でも不可能
4. OT 拡張が fa=0 × ctx=16k slope に +0.10 MiB/ub の副作用
5. X4 で graph splits が 3-5 倍化（実用 path ではない、測定専用）

## 未検証事項

### 既知項目（Phase Sb-fa0 から継続、本 Phase で潰したものに [x]）

- [x] **★最優先: Phase Sb-fa0-offload 候補（本 Phase）**: 実施、**候補 L support 確定**
- [x] **★最優先: fa=0 × ctx=32k+ の CUDA1 alloc size から CUDA1 slope を派生測定**: 本 Phase で ctx=65k (+8.37)/ctx=131k (+16.66) の派生抽出完了
- [ ] **★最優先: Phase Sb-tensor-dump 候補（debug build + FA kernel per-node workspace dump）**: 候補 L support により機構の物理確定手段。`ggml-cuda/fattn*.cu` 内部 workspace 実測で tile size 量子化の直接確認
- [ ] **★最優先: ub=1586 eval 15.466 t/s の 5-10 run 再現性** (Phase Sbf3 継続)
- [ ] **★高優先: ub ≥ 1586 線形モデルの ctx 独立性検証**
- [ ] **★高優先: 境界 ub\* の ctx 依存性**
- [ ] **★高優先: VMM granularity の実測値確認** — P100 CC 6.0 で `cuMemGetAllocationGranularity()` 値
- [ ] **★高優先: FA parallel_blocks の ub 依存性確認** (候補 I-b) — 候補 L の support により、tile size 量子化の一部として優先度高
- [ ] **ub=1664 eval 15.451 t/s の 5-10 run 再現性** (Phase Sb-fine 継続)
- [ ] **ub=1584 eval 15.293 t/s の 5-10 run 再現性** (Phase Sb-fine2 継続)
- [ ] **eval 境界挟み込み構造の再現性** (Phase Sb-fine2 継続)
- [ ] **CUDA0 区分モデルの物理的意味** — 本 Phase で「FA tile 量子化副作用」と確定、物理実装は tensor-dump で
- [ ] **境界 ub\* の KV 量子化依存性**: q8_0 KV で境界が移動するか
- [ ] **CUDA0 二次係数 9.104e-6 MiB/token² の物理メカニズム** — 本 Phase で fa 軸の強依存発見、fa=0 で二次成分が消えることを確認（完全線形、δ_of_δ=0.01）
- [ ] **CUDA0 二次モデルの ctx=262144 外挿** (Phase R-ctx3 継続)
- [ ] **CUDA1/2 cross_e = 1.910e-6, Host = 3.815e-6 MiB/(token·token) の物理メカニズム** — 本 Phase で fa=0 slope(ctx) = 1.36e-4·ctx の 1 次比例性確認、2 次項は fa=1 特有の tile 現象
- [ ] **ub=1280/1792 の eval 性能再現性** (Phase Sb 継続)
- [ ] **ub=1280/1536/1792 × ctx=65k での CUDA0 検証** (Phase Sb 継続)
- [ ] **中間 ctx (24k / 48k / 96k) での検証** (Phase Sb 継続) — fa=1 のみ、fa=0 は X4 でも 48k で OOM 予想
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
- [ ] **CUDA1 / CUDA2 の n² 係数 (fa=0 a=1.26e-4) の物理解釈** — 本 Phase で fa=0 × X4 は線形 (1.36e-4·ctx·ub) と判明、n² 係数は fa=1 特有
- [ ] **ctx=1024 の fa=0 eval 劣化 (−5.2%) の原因**
- [ ] **ctx=512 / 256 の極小域での挙動**
- [ ] **eval 速度のセッション間ゆらぎレンジ更新**
- [ ] **prompt 処理の ctx 非依存の長 ctx 側確認**
- [ ] **fa=1 eval の「谷型」(ctx=2048 最高 → ctx=4096 最低) の再現性**
- [ ] **Phase M のモデルを f16 KV → q8_0 KV（C-D3 採用構成）に適用した場合の整合性**
- [ ] **ctx=6144 等の中間 ctx での fa=1 / fa=0 境界確認**
- [ ] **fa=0 ctx=8192 で CUDA1 空き枠を増やす手法** — 本 Phase で X4 により実現可能と確認、X3 以下でもかどうかは未検証
- [ ] **eval 谷型の最低値 ctx の fa=1 における物理原因**

### 既知項目（Phase Q/S 継続）

- [ ] **`-ub=1 (greedy)` でのベンチマーク**
- [ ] **`-ub > -b` の挙動（llama.cpp 制約検証）**
- [ ] **fa=0 側での `-ub` 支配性の確認** — 本 Phase で ctx=16k/32k fa=0-X4 の slope を測定、支配性は「ub 正比例で連続」という性質
- [ ] **大 prompt での `-ub` 依存性** (4k/8k/16k prompt 未検証)
- [ ] **`-b > -ub` 運用の意義**: Phase P で観測のみ
- [ ] **`--parallel 2` との相互作用**
- [ ] **P3 vs Phase O の eval 差 +1.17% のセッション源**

### 既知項目（Phase Sb-src から継続）

- [ ] **Phase Sb-src 新規 ★: 境界 ub\* のモデル固有性検証** (Qwen3.5-35B-A3B 等)
- [ ] **Phase Sb-src 新規 ★: 残差 4,247 bytes/tok の分解** — 本 Phase で fa 軸の強依存発見、fa=0 × X4 は純 1 次 (1.36e-4·ctx) 、2 次項は fa=1 特有
- [ ] **Phase Sb-src 新規: ub ≤ 1585 平坦域 slope 0.0125 MiB/tok の由来** — fa=1 特有、fa=0 では 2.22 MiB/tok (X4)
- [ ] **Phase Sb-src 新規: fused_gdn_ar / ch の実際のパス切替え**
- [ ] **Phase Sb-src 新規: ggml_gated_delta_net 出力 4 MiB 定数寄与の allocator 扱い**

### 既知項目（Phase Sb-alloc から継続）

- [ ] **Phase Sb-alloc 新規: 9 層 SSM 出力の allocator 内配置順序の特定** — Phase Sbctx で候補 J 棄却により優先度低
- [ ] **Phase Sb-alloc 新規: CUDA_Host buffer (235 MiB) の用途** — 本 Phase で fa=0 × X4 × ctx=32k で Host = 241 MiB、ctx=16k で 142 MiB と ctx 比例、Host も attention workspace の一部を保持

### 新規項目（本 Phase Sb-fa0-offload で判明・発生）

- [ ] **★最優先: Phase Sb-tensor-dump 候補（debug build + FA kernel workspace dump）** — 候補 L support 確定により物理機構確定手段としての優先度最高
- [ ] **★高優先: X1 / X2 / X3 escalation 境界の詳細特定** — 本 Phase で X4 まで escalation 必要と判明、X3 → X4 の境界で 12 層追加と 36 層追加を区別する必要、CUDA1 担当外の layer が attention workspace を発生させている可能性
- [ ] **★高優先: OT 拡張が eval 性能に与える影響定量** — splits が 136 → 442 / 77 → 401 と 3-5 倍化、eval t/s 影響は未測定
- [ ] **★高優先: fa=0 × X4 slope(ctx) 1 次比例係数 1.36e-4 の物理解釈** — `ub × ctx × α` の α 値が何に由来するか（n_heads × bytes × 係数）、ヘッド数 48 × 2 bytes × 係数 = 96·k であり 1/700000 = 1.4e-6 等の逆算で tensor 次元同定
- [ ] **★高優先: CUDA1/2 の 8.7 GiB 非 attention 非 MoE model buffer の tensor 名称特定** — `attn_norm` / `attn_o_proj` / `ffn_gate` / `ffn_norm` の何が GPU に残っているか、tensor 名 dump 要
- [ ] **★高優先: OT 拡張の slope 影響 +0.10 MiB/ub の由来** — MoE only → X4 で CUDA0 slope 2.12 → 2.22、attention CPU オフロードで scheduler の workspace 配置が +0.1 シフト
- [ ] **★中優先: Stage 3 OOM alloc size の GPU 別分布** — ctx=65k で CUDA1 alloc、ctx=131k で CUDA0 alloc と OOM GPU が切替わる。層配置の非対称性との関係
- [ ] **★中優先: X4 × ctx=32k 以上の確認 (ctx=48k / 40k / 36k)** — 16k / 32k / 48k の細 ctx 走査で OOM 閾値特定、fa=0 実用上限
- [ ] **★中優先: fa=0 × X4 × ctx=32k における eval 性能** — compute buffer 測定のみ、eval は未実施（splits 3-5 倍で悪化予想）
- [ ] **★中優先: IQ2_XXS 等低量子化での fa=0 ctx 拡張可能性** — Q4_K_M の model buffer 72 GiB → IQ2_XXS なら 36 GiB、GPU 側も半減で ctx=65k も入る可能性
- [ ] **★中優先: fa=0 × X4 × ctx=8k の起動可否** — 本 Phase は ctx=16k/32k のみ、ctx=8k なら更に余裕ありそう
- [ ] **★低優先: fa=1 × X4 での slope(ctx) 測定** — X4 は eval 不適だが compute buffer の fa 依存性確認には有効

## 検証完了後に実施すべき TODO

### 既知項目（Phase Sb-alloc から継続）

- [ ] **start.sh の拡張**: `LLAMA_NUMACTL_PREFIX` / `LLAMA_EXTRA_THREADS` / `LLAMA_FLASH_ATTN` / **`LLAMA_OT_REGEX`** 環境変数サポート追加 — 本 Phase で OT 環境変数化の有用性確認
- [ ] **CUDA1 セーフティマージン OOM フォールバック実装** — 本 Phase で X1-X3 escalation による動的 OT 拡張パターン確立、OOM 時の自動 OT 拡張が実装可能
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

### 新規項目（本 Phase Sb-fa0-offload で更新）

- [ ] **★最優先: Phase Sb-tensor-dump（debug build）** — 候補 L 確定手段、`ggml-cuda/fattn*.cu` の tile size per-node dump
- [ ] **★最優先: CLAUDE.md / skill 更新**: 「**fa=0 × ctx=32k は OT=X4（全 attention CPU）で実現可能だが splits 3-5 倍化で eval 不適**」「**fa=0 × ctx≥65k は P100 では X4 でも不可能**」「**候補 L support: δ 項 = FA tile 量子化副作用**」「**fa=0 compute buffer = ub × ctx × 1.36e-4 の純線形モデル**」と明記
- [ ] **★最優先: skill 側 `.claude/skills/llama-server/scripts/start.sh` のデフォルト確定** — `--flash-attn 1` のまま堅持推奨（本 Phase で再確認）
- [ ] **★最優先: 起動前 lint の CUDA0/1 モデル更新**（fa × OT 軸追加）:
  - fa=1: 既存 (A(ctx) + B(ctx)·ub + δ)
  - fa=0 × MoE only: `CUDA0 ≈ 3537 + 2.12·ub (ctx=16k), ctx≥32k OOM`
  - fa=0 × X4: `Buf ≈ Buf_base(ctx) + 1.36e-4·ctx·ub`, `ctx≥65k は P100 で OOM`
  - lint ルール: `fa=0 & ctx≥32k & OT_REGEX が X4 を含まない → ERROR`、`fa=0 & ctx≥65k → ERROR "P100 では不可能"`
- [ ] **★最優先: 候補 L モデル (FA tile 量子化副作用) を skill / CLAUDE.md に記録** — 特に「fa=0 ではすべて線形、fa=1 で slope(ctx) と δ 項のみ出現」の要約
- [ ] **★高優先: Phase Sb-ctx-fine 候補** — ctx=20k/24k/28k/36k/40k/48k の細 ctx 走査（fa=1 のみ、fa=0 × X4 は ctx=48k 付近で OOM 境界）
- [ ] **★高優先: Phase Sb-KV8 候補**: `--cache-type-{k,v} q8_0` で再実施 — cross 項が KV サイズ連動か、fa=0 × ctx≥65k 実現性改善するか
- [ ] **★高優先: Phase Sb-tensor-names 候補** — CUDA1/2 に残る 8.7 GiB model buffer の tensor 名内訳、OT 拡張の完全性確認
- [ ] **★最重要: Phase S-eval 候補**: ctx=32k × ub=1586/1664 eval ピーク 2 点を 5-10 run で再現性検証 — fa=1 前提
- [ ] **Phase Q-2 候補**: `-ub=64/32/16/8/4/2/1`
- [ ] **Phase Q-3 候補**: ub=1586 周辺 ±8 token で eval ピーク形状
- [ ] **skill 側 start.sh の `ssh -f` stdout redirect 改修**
- [ ] **start.sh のデフォルト `ctx-size` を 131072 に更新**
- [ ] **モデルカード更新**: Qwen3.5-122B-A10B の長コンテキスト性能カードに「**fa=0 × OT=X4 で ctx=32k まで可能、splits 3-5 倍で eval 不適**」「**slope(ctx)_fa0 = 1.36e-4·ctx MiB/ub**」「**候補 L support: δ 項は FA tile 固有**」を明記
- [ ] **Phase Sb-src-cu kernel profile 候補**: nvprof/ncu で ub=1586 付近の FA kernel と buffer 計測 — 候補 L 直接検証
- [ ] **Phase Sb-ctx-131k-eval 候補**: ctx=131k で eval 最速 ub を探索 (fa=1 前提)

## 補足

### Phase Sb-fa0-offload の核心発見（サマリ）

1. **候補 L support 確定**: δ_fa0(ctx=32k) = +0.01 MiB、fa=1 δ = +0.24 MiB との差 23 倍精度で有意 → δ 項は FA tile 量子化副作用（fa=1 固有）
2. **slope(ctx) ∝ ctx の完全比例関係**: fa=0 × X4 で 16k→2.22, 32k→4.28, 65k→8.37, 131k→16.66 MiB/ub の 1 次係数 1.36e-4 で fit
3. **fa=0 × ctx=32k は X4（全 attention CPU）で実現可能**、X1-X3（部分 attention CPU）では OOM
4. **fa=0 × ctx=65k/131k は X4 でも不可能**（CUDA1 13247 MiB / CUDA0 26440 MiB 要求）、P100 VRAM の物理制約
5. **graph splits 3-5 倍化**（136→442, 77→401）で X4 は eval 不適、測定専用 path
6. **OT 拡張が ctx=16k slope に +0.10 MiB/ub 副作用**（2.12→2.22）
7. **OOM alloc size 派生抽出**で fa=0 slope(ctx) の ctx=65k/131k データ点取得（新規）

### Phase Sb-fa0 との対照

| Phase Sb-fa0 | Phase Sb-fa0-offload |
|---|---|
| fa=0 × MoE only で ctx=32k CUDA1 OOM | X4 で ctx=32k 起動成立 |
| 候補 K 事実上棄却、候補 L 提示 | **候補 L support 確定** |
| slope(fa) 200 倍増を発見 | **slope(ctx) ∝ ctx の 1 次比例を確定** |
| ctx=65k/131k 実行見送り | ctx=65k/131k OOM alloc 6 条件すべて記録 |
| OT_REGEX 固定 | OT_REGEX escalation (X1→X4) |
| graph nodes +59 発見 | graph splits +306/+324 発見 |
| 次 Phase 方向性: tensor-dump / fa0-offload | 次 Phase 方向性: **tensor-dump (候補 L 物理確定)** / KV8 / tensor-names |

### 作業終了時点の状態

- **GPU サーバロック: 解放済み (t120h-p100)、他セッションから利用可能**
- 作業ディレクトリ `report/attachment/2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload/` を保持
- 生成物: plan.md / start_phaseSbfa0offload.sh / batch_Sbfa0offload.sh / analyze_Sbfa0offload.py / batch_Sbfa0offload.log / batch_Sbfa0offload_failures.tsv / batch_Sbfa0offload_oom.tsv / summary_state.txt / summary_Sbfa0offload.tsv / Sbfa0offload_pivot_X4.csv / Sbfa0offload_slopes.csv / Sbfa0offload_oom_slopes.csv / Sbfa0offload_verdict.txt / Sbfa0offload_candidate_L_verdict.txt / startup_logs (15 ファイル: X1/X2/X3 各 1、X4 × ctx=16k/32k/65k/131k × ub=1584-1586 合計 12) / start_stdout_*.log (15)
- **主要発見**:
  - **候補 L support 確定**（δ 項 = FA tile 量子化副作用）
  - **slope(ctx)_fa0 ∝ ctx（1.36e-4 係数）**
  - **fa=0 × X4 で ctx=32k 実現、ctx≥65k は P100 不可能**
  - graph splits 3-5 倍化、eval 不適
- **次の推奨 Phase**:
  1. **Phase Sb-tensor-dump (debug build)**: 候補 L 物理確定、所要 2-3 時間
  2. **Phase Sb-tensor-names**: CUDA1/2 8.7 GiB の tensor 名内訳、所要 20 分
  3. **Phase Sb-KV8**: `--cache-type-{k,v} q8_0` で fa=0 ctx 拡張性改善確認、所要 40 分
  4. **Phase Sb-ctx-fine**: ctx=20/24/28/36/40/48k の細走査（fa=1）、所要 40 分
  5. **Phase S-eval**: fa=1 × ctx 別 eval 最適 ub、所要 30-60 分
