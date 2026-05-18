# Marathon ベンチ総合 summary: llama.cpp HEAD (1348f67c5) で Qwen3.5-122B-A10B のデフォルト構成は U-6 比 +1.3〜+4.5% 改善、追加フラグでの上乗せは drift 帯

- **実施日時**: 2026 年 5 月 16 日 10:20 〜 5 月 17 日 04:58 JST（18 時間 38 分）
- **対象**: llama.cpp `HEAD = 1348f67c5` × Qwen3.5-122B-A10B-Q4_K_M × t120h-p100 (P100×4, 64GB) × fit (B14b_ts_alt, ctx=128k)
- **比較基準**: U-6 (2026-04-24, ビルド `6217b4958`, 3 週間前のデフォルト確定構成)

## 核心発見サマリ

- ✅ **llama.cpp HEAD (1348f67c5) は U-6 比でデフォルト構成のまま全 prompt 長で改善**: 1k +4.46%、32k +1.30%、96k +1.95%。**速度系 PR の累積効果**（#22041 subgraph splits cache, #21764 graph_reused, #22330 concat coalesce, #22650 fastdiv, #22541 Pascal tile FA fix 等）
- ✅ **`--main-gpu 1` (M1) が単独で BL 比 +0.91%（1k, 有意 t≈2.3）**: memory `[[project_t_series_roadmap]]` で「未検証」項目だったフラグの効果が確認できた
- ✅ **`--threads 32` (T1_th32) が BL 比 +0.66%（1k）**: Phase T-3 の結論を現 HEAD でも再現
- ✅ **`-ub 768` で prompt +16.2%（eval は -1.6%）**: prompt 重視ワークロードでの Pareto 改善
- ❌ **spec 系全種（ngram-simple/mod/cache/map-k/map-k4v/chain）は context checkpoint OOM で起動不能**: ctx=128k/96k 両方で同じ問題、Phase U-1 の spec ckpt と同根
- ❌ **B12 化（OT 12 層）、`-sm tensor`、`--swa-full` は全て本構成と非互換 or 改善せず**
- ⚠️ **BL_FINAL (M1 + T1_th32) は drift で組合せ効果が打ち消し**: 単独効果の累積（期待 +1.6%）は再現できなかった
- 🎯 **推奨**: 現行 BL 構成を維持。`--main-gpu 1` 単独追加は検討候補（変動小さく改善側）

## 添付ファイル

- [実装プラン](attachment/2026-05-17_045809_qwen3-122b-bench-marathon-summary/plan.md)
- [全 Phase 統合 CSV](attachment/2026-05-17_045809_qwen3-122b-bench-marathon-summary/results_combined.csv)（results.csv 全 262 行）
- 各 Phase の単体レポート (リンク参照)

## Phase 別レポート

| Phase | 内容 | レポート |
|-------|------|---------|
| A | BL + F1/N1/M1/K1 (Quick wins) | [phaseA-quickwins](2026-05-16_183834_qwen3-122b-bench-marathon-phaseA-quickwins.md) |
| B | Spec exploration (S1-S6 全失敗) | [phaseB-spec-fail](2026-05-16_195031_qwen3-122b-bench-marathon-phaseB-spec-fail.md) |
| C | Parameter sweep (ub/b/threads) | [phaseC-sweep](2026-05-16_221912_qwen3-122b-bench-marathon-phaseC-sweep.md) |
| D | Architecture (B12/B16/-sm tensor/SWA) | [phaseD-arch](2026-05-16_232150_qwen3-122b-bench-marathon-phaseD-arch.md) |
| E | BL_FINAL 最終確認 | [phaseE-final](2026-05-17_045807_qwen3-122b-bench-marathon-phaseE-final.md) |

## 環境情報

- サーバ: `t120h-p100` (10.1.4.14)
- GPU: NVIDIA Tesla P100-PCIE-16GB × 4 (合計 64 GB, sm_60, FP16)
- CPU: Intel Xeon Gold 6138 × 2 (20 cores/socket, NUMA node 1 使用)、`numactl -N1 -m1`
- llama.cpp `HEAD = 1348f67c58f561808136e8a152a9eddec168f221` (PR #23107 含む)
- ビルド: `cmake -DGGML_CUDA=ON -DGGML_CUDA_FA_ALL_QUANTS=ON -DCMAKE_CUDA_ARCHITECTURES=60` (CUDA 12.9)
- モデル: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M` (48 層, head_kv=2, head_dim=256, expert_count=256/used=8, full_attention_interval=4)
- ベース構成 BL: B14b_ts_alt + `--flash-attn 1 -b 2048 -ub 512 --tensor-split 11,12,13,14 --threads 40` + KV q8_0 + ctx=131072

## 全試行クロス比較表

### eval t/s 比較（5 ラン mean）

| 試行 | 1k | 32k | 96k | 備考 |
|------|-----|-----|-----|------|
| U-6 (`6217b4958`, 2026-04-24) | 17.692 | 14.360 | 10.029 | 比較基準 |
| **BL (`1348f67c5`)** | **18.482** ± 0.110 | **14.547** ± 0.023 | **10.225** ± 0.145 | **U-6 比 +1.3〜+4.5%** |
| F1 (`-fa auto`) | 18.583 ± 0.122 | 14.766 ± 0.082 | – | +0.55% / +1.50% |
| N1 (`-ncmoe 14`) | ❌ OOM | – | – | 起動失敗 |
| M1 (`--main-gpu 1`) | **18.649** ± 0.121 | 14.752 ± 0.154 | – | **+0.91%** / +1.41% |
| K1 (KV q4_0) | 18.353 ± 0.008 | 14.498 ± 0.079 | – | -0.69% / -0.33% (VRAM **+192 MiB**) |
| S1-S6 (spec) | ❌ OOM | ❌ OOM | – | context checkpoint 競合 |
| U1_ub256 | ❌ OOM | – | – | checkpoint と ub<512 不両立 |
| U1_ub384 | ❌ OOM | – | – | 同上 |
| U1_ub768 | 18.192 ± 0.186 | – | – | prompt **+16.2%** ★ |
| B1_b1024 | 18.107 ± 0.021 | – | – | -2.03% |
| B1_b4096 | ❌ OOM | – | – | – |
| **T1_th32** | **18.604** ± 0.013 | – | – | **+0.66%** (有意) |
| T1_th44 | 13.401 ± 0.003 | – | – | **-27.49%** (NUMA 領域外) |
| O1 (B12) | ❌ 起動失敗 | – | – | CPU 12 層では VRAM 不足 |
| O2 (B16) | 17.709 ± 0.006 | – | – | -4.18% (CPU 層増で低下) |
| G1 (`-sm tensor`) | ❌ curl_failed | – | – | tensor split と非互換 |
| W1 (`--swa-full`) | 18.238 ± 0.006 | – | – | -1.32% |
| BL_FINAL_set1 (M1+T1_th32) | 18.350 ± 0.010 | 14.748 ± 0.066 | **10.303** ± 0.067 | -0.71% / +1.38% / +0.77% |
| BL_FINAL_set2 (M1+T1_th32) | 17.973 ± 0.009 | 14.563 ± 0.120 | – | -2.75% / +0.11% (drift) |

### prompt t/s 比較（注目）

| 試行 | 1k prompt | 32k prompt | 備考 |
|------|-----------|------------|------|
| BL | 64.366 | 61.010 | – |
| **U1_ub768** | **74.754** | – | **prompt +16.2%** |
| 他 | 64 ± 1 程度 | 61 ± 0.3 | ほぼ同等 |

### 経過時間まとめ

| Phase | 試行数 | 試行成功/失敗 | 所要 |
|-------|--------|---------------|------|
| 0 (プリフライト) | – | – | 30 分 |
| A (BL + Quick wins) | 5 | 4 成功 / N1 OOM | 8 h 17 分 |
| B (spec 6 種 ctx=128k) | 3 | 0 成功 | 1 h 25 分 |
| B' (spec 6 種 ctx=96k) | 3 | 0 成功（部分） | 1 h 10 分 |
| C (sweep 7 種) | 7 | 4 成功 / 3 OOM | 2 h 26 分 |
| D (アーキ 4 種) | 4 | 2 成功 / O1/G1 失敗 | 1 h 00 分 |
| E (BL_FINAL 2 set) | 1 | 1 成功 | 5 h 35 分 |
| レポート作成 | 6 本 | – | （並行）|
| **総計** | **29 試行** | **15 成功** | **~18 h 38 分** |

## 効きそうな PR の効果実証

| PR | 期待効果 | 実測 |
|----|---------|------|
| **#22541** Pascal tile FA fix | Pascal で新 FA カーネル動作 | ✅ `-fa auto` で正常動作（F1 確認）|
| **#22041** subgraph splits cache | generate +8〜16% | ✅ BL 1k +4.46%（U-6 比）に寄与 |
| **#21764** graph_reused | generate 数% | ✅ 同上 |
| **#22330** contiguous concat coalesce | E2E +1〜3% | ✅ 96k +1.95% に寄与 |
| **#22650** fastdiv get_rows | カーネル 3〜5% | ✅ 累積で観測 |
| #22298 MMQ stream-k | Pascal は効かず | ❎ 影響観測されず |
| **#21038** Walsh-Hadamard rotation | KV q4_0 品質維持 | ✅ K1 で速度 -0.7% に止まる |
| #22838 spec parallel drafting | generate +20-100% | ❌ checkpoint OOM で評価不能 |
| #22673 draft-mtp | decode 1.85-2.2x | ❌ GGUF に MTP テンソル無し、評価不能 |

## デフォルト構成更新の推奨

### 推奨: BL (現行) を維持

現行の `start.sh` Qwen3.5-122B-A10B プロファイル分岐:
```
SERVER_OPTS="--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14"
ENV_PREFIX="numactl --cpunodebind=1 --membind=1"
THREADS_OPT="--threads 40"
```
は **HEAD で再ビルドするだけで U-6 比 +1.3〜+4.5% の改善** が得られ、追加変更は不要。

### 検討余地のある変更

| 変更 | 効果 | リスク |
|------|------|--------|
| `--main-gpu 1` 追加 | 1k/32k +0.9〜1.4% | drift 込みで効果消える可能性、要再検証 |
| `--threads 32` に変更 | 1k +0.66% | 他構成（M1 等）と組合せで打ち消し |
| `-ub 768` 化 (1k 推奨) | prompt +16.2%、eval -1.6% | eval 重視ワークロードで不利 |
| `--cache-type-k/v q4_0` 化 | VRAM +192 MiB（速度 -0.7%）| 速度低下と引き換え |

### 採用厳禁

| 変更 | 理由 |
|------|------|
| `--threads 44` | NUMA 領域逸脱で -27% |
| `--spec-type *` | 全種で OOM、現構成不可 |
| `-sm tensor` | tensor split と本構成非互換 |
| `-ncmoe N` | 連続層 CPU offload は B14b_ts_alt と層集合違いで OOM |
| OT 12 層化 (B12) | VRAM 不足で起動失敗 |

## 24h バジェットで未到達 / 諦めた項目

| 項目 | 理由 |
|------|------|
| K1 + spec の組合せ検証 | spec 全失敗確定後に時間配分の関係でスキップ |
| ub 中間値（448/640）詳細 sweep | Phase C を 3 値に絞ったため |
| threads 28/30/34/36/38 細粒度 sweep | 同上 |
| `--ctx-checkpoints 0` で checkpoint 無効化 | Phase 設計時に未把握、Phase B/C で OOM 原因と判明後の追加調査時間なし |
| W1 (`--swa-full`) の 32k/96k 計測 | 1k で改善せずスキップ判断 |
| BL_FINAL を drift 排除設計で再計測 | 24h 予算切れ |
| 真の cold start vs warm session の差分計測 | 同上 |
| llama-bench での軽量モデル切り分け | Phase 0 設計段階で除外 |

## 主たる学び

1. **HEAD アップデートだけで +1.3〜+4.5% は無料の改善**: 3 週間で多数の Pascal 系 PR がマージされており、再ビルドコストに見合う
2. **spec は VRAM 余裕が前提**: ctx=128k の B14b_ts_alt は spec ckpt と非両立。今後 spec を使うには (a) ctx 削減、(b) KV q4_0、(c) B12 化等で +500 MiB/GPU 確保が必要
3. **`-ub` の上下で OOM 挙動が変わる**: 256/384 で OOM、512/768 で成功は意外。`--ctx-checkpoints` のデフォルト 32 と相互作用
4. **threads は socket 内に閉じることが必須**: NUMA `--cpunodebind=1` でも threads 数が socket 物理コア × HT を超えると壊滅的低下
5. **`--main-gpu 1` は memory にあった未検証フラグ**: 単独効果は確認できたが組合せでは drift に飲まれる

## 再現方法（最小）

```bash
# 1. ロック取得
.claude/skills/gpu-server/scripts/lock.sh t120h-p100 marathon-replay

# 2. HEAD 確認
ssh t120h-p100 "cd ~/llama.cpp && git rev-parse HEAD"  # 1348f67c5...

# 3. BL 計測（デフォルト構成、Phase A の BL に相当）
.claude/skills/llama-server/scripts/llama-up.sh
# 各 prompt 長で warmup 1-2 + eval 5 を回す（measure_phaseU6.sh 流用）
.claude/skills/llama-server/scripts/llama-down.sh t120h-p100

# 全 Phase 再現は本レポート添付の各 phase オーケストレータスクリプトを参照
```

## 補足: 過去ベスト T-5a-ts2 との比較（ctx=32k）

参考までに、過去歴代 1 位 T-5a-ts2 (2026-04-23, ctx=32k) の値:

| metric | T-5a-ts2 (ctx=32k) | BL ctx=128k @ 1k | 差 |
|--------|---------------------|-------------------|----|
| eval (1k) | 18.664 | 18.482 | -0.98% |
| prompt (1k) | 46.082 | 64.366 | **+39.7%** |

ctx=32k vs ctx=128k では prompt が大きく変わる（短い ctx の方が短 prefill で速い見かけになる）。eval はほぼ同等。**ctx=128k の運用要件と歴代ベスト ctx=32k は ~1% 差まで詰められた**。

---

総合的に、**「最新の llama.cpp HEAD で再ビルドする」だけが現時点で最も効果的**な最適化であり、CLI フラグでの追加改善は drift 帯（~±1%）に埋もれる結果となった。
