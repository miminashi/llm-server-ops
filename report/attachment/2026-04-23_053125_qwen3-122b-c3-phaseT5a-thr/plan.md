# Phase T-5a-thr: B18 × ub=256 × threads 再スイープ

## Context

Phase T-5a-ub で **B18 × ub=256 × threads=40** が **18.103 t/s (実測) / 18.209 t/s (drift 補正後)** を達成し歴代最高 (対 Phase D +20.45%)。しかし threads=40 は T-5a から継承したのみで、**B=18 × ub=256 固有の条件では最適 threads は未検証**。

当該条件では CPU オフロード層が 14 枚 (Phase T-3 の 36 層、T-5 系の 28 層から激減) に変化しており、CPU 側律速の所要 threads 数も変わっている蓋然性が高い。さらに Phase T-3 では **「CPU 層数 ≒ threads で eval_tps が dip する」現象 (CPU 36 層 × threads=36 で -2.08%)** が観測されている — B=18 (CPU 14 層) × threads=14 で再現するなら、メカニズムが確定する科学的価値あり。

本 Phase は未検証事項 (a)-(e) のうち **(a) B18 × threads 再スイープ** を実施する。低リスク・短時間・高情報量で、後続 Phase (tensor-split, ctx=65k) の基礎となる。

## 未検証事項 (a)-(e) のうち (a) を選定した理由

| 選択肢 | 期待利得 | リスク | 時間 | 情報価値 | 判定 |
|--------|----------|--------|------|----------|------|
| **(a) threads 再スイープ** | **+0〜+0.5 t/s (確実に最適値確定)** | **低** | **約 130 分** | **高 (dip 仮説検証)** | **採用** |
| (b) tensor-split | +0.5〜+1.0 t/s (B16/B14 化可能性) | 中 (OOM/配置試行錯誤) | 数 Phase 要 | 最高 | 次 Phase へ |
| (c) compute_buf 境界 | なし (機序調査) | 低 | 中 | 中 (kernel 内部) | 保留 |
| (d) FORCE_MMQ/DMMV | 不明 (P100 CC 6.0 で疑わしい) | 中 (rebuild コスト) | 大 | 中 | 保留 |
| (e) ctx=65k × ub=256 | 通常 eval 劣化 | 低 | 小 | 中 (Pareto 拡張) | 保留 |

**順序理由**: (a) は最も独立性が高く、(b)(e) の結果解釈に threads 最適値が必要。また、(a) で T-3 dip 仮説が再現するかは、(b) tensor-split で CPU 層数が再び変わる場合の threads 最適化指針を与える。

## 測定計画

### 固定条件
- サーバ: **t120h-p100** (NVIDIA Tesla P100-PCIE-16GB × 4、但し CUDA0 のみ使用)
- CPU: Xeon E5-2698 v4 × 2 socket (node1 の 40 物理コア、SMT OFF、numactl -N1 -m1 で束縛)
- モデル: Qwen3-122B (MoE, 6bit quant)
- OT: **B=18** (`blk\.([0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU`)
- ub: **256**, batch: **256**
- ctx: **32768**, KV: **q8_0**
- split-mode: **layer**, flash-attn: **1**, poll: **0**, ngl: **999**
- warmup 2 + eval 5 run (llama-bench の標準)

### 可変条件: threads スイープ 7 点 + drift bracket 2 点

**実測 label 順序 (9 label)**:
```
thr40a → thr14 → thr20 → thr28 → thr32 → thr36 → thr38 → thr40_mid → thr40z
```

- **thr40a, thr40z**: drift bracket (起点・終点)、T-5a-ub の B18_ub256=18.103 と cross-session 再現性を同時検証
- **thr40_mid**: 中央に挟み、drift の **線形性** を初検証 (T-5a-ub が暗黙に前提したが未検証)
- **thr14**: CPU 層数 (14) 一致点、T-3 dip 仮説の再現性検証
- **thr20, thr28, thr32, thr36, thr38**: 中間帯スイープ、T-3 で局所極大だった 32 付近の再評価

**threads=44 は除外**: numactl -N1 は node1 の物理 40 コア束縛、44 は超過で node0 漏れ = NUMA 違反 (drift が crash 的に悪化する既知現象)。上振れ検証は別 Phase で `-N 0,1` を外して実施。

### drift 補正
- 線形補正係数 = (thr40z − thr40a) / (N−1) で全 label 補正 (T-5a-ub と同方式)
- thr40_mid が thr40a/thr40z 線形予測値から ±0.05 t/s 以内なら線形性 OK、外れたら補正手法の見直しを報告

### 所要時間見積もり
- 9 label × (warmup 2 + eval 5 run) ≈ 115 分 (main batch)
- dry probe 不要 (VRAM は ub=256 で確定済)
- lock 取得 + cold warmup 5 分 + analyze/plot 10 分
- **総計 約 130 分**

## 手順

### 1. ロック取得
```bash
.claude/skills/gpu-server/scripts/lock-status.sh t120h-p100
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 2. Topology 記録 (1 回)
```bash
ssh t120h-p100 "nproc && lscpu | grep -E 'Socket|Core|Thread|Model name' && numactl -H" \
  > report/attachment/<report-name>/topology.log
```

### 3. batch script 作成 & 実行
- T-5a-ub の `batch_phaseT5a-ub.sh` を雛形に `batch_phaseT5a-thr.sh` を作成
- 差分: label 命名を thr{N}[a|z|_mid]、-t パラメータのみ可変、-ub/-b は 256 固定
- JSON で出力 (`--output json`)、各 run 5 回
- stdout/stderr を `batch_phaseT5a-thr.log` に保存

### 4. 解析 & プロット
- `analyze_phaseT5a-thr.py` (T-5a-ub の `analyze_phaseT5a-ub.py` を流用)
- drift 補正、線形性チェック (thr40_mid)、7 × (raw/corrected) pivot
- PNG: x=threads (14-40)、y=eval_tps (raw/corrected 2 系列)、T-3 の B28 系列オーバーレイ (比較軸)
- 回帰直線 (線形 + 局所多項式) 重畳

### 5. ロック解放
```bash
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 参考ファイル (流用元)

| 項目 | パス |
|------|------|
| 直前レポート | `report/2026-04-23_034442_qwen3-122b-c3-phaseT5a-ub-resweep.md` |
| batch 雛形 | `report/attachment/2026-04-23_034442_qwen3-122b-c3-phaseT5a-ub-resweep/batch_phaseT5a-ub.sh` |
| analyze 雛形 | `report/attachment/2026-04-23_034442_qwen3-122b-c3-phaseT5a-ub-resweep/analyze_phaseT5a-ub.py` |
| T-3 比較元 | `report/attachment/2026-04-22_181614_qwen3-122b-c3-phaseT3-threads/phaseT3_pivot.md` |
| レポート規約 | `REPORT.md` |
| llama-bench 実行 | `.claude/skills/llama-server/SKILL.md` |
| ロック管理 | `.claude/skills/gpu-server/SKILL.md` |

## 成果物

### レポートファイル
```
report/<TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S>_qwen3-122b-c3-phaseT5a-thr.md
```

### attachment/
```
attachment/<report-name>/
  plan.md                         # 本 plan のコピー
  batch_phaseT5a-thr.sh           # 実行 script
  analyze_phaseT5a-thr.py         # 解析 script
  batch_phaseT5a-thr.log          # 実行ログ
  results.json, results.csv       # 生データ
  topology.log                    # nproc/lscpu/numactl -H
  threads_eval.png                # 核心 PNG (x=threads, y=eval_tps, raw+corrected)
  t3_vs_t5a_dip.png               # T-3 (CPU36) vs T-5a-thr (CPU14) の dip 仮説比較
```

### レポート構造 (REPORT.md 準拠)
1. 前提・目的
2. 環境情報 (topology.log 参照)
3. 再現方法
4. 参照レポート (T-5a-ub, T-3, T-5a, T-5f)
5. **核心発見サマリ** (冒頭に `threads_eval.png` 埋め込み、最適 threads 値、dip 仮説判定、対 T-5a-ub 改善率)
6. 全 Phase 比較表 (D/S/T-1〜T-5/T-5a/T-5a-ub/**T-5a-thr**)
7. drift 線形性検証結果 (thr40_mid)
8. T-3 dip 仮説再現性 (t3_vs_t5a_dip.png)
9. 未検証事項 (本 Phase で生じた新規事項)
10. 検証完了後 TODO (次 Phase 候補)
11. 添付ファイル

### タイトル
`Phase T-5a-thr: B18×ub=256 threads 再スイープ` (50 字以内)

## 検証完了後 TODO (次 Phase 候補)

本 Phase の結果に応じて優先度付け:
1. **Phase T-5a-ts** (tensor-split): `-ts 4,1,1,1` 等で CPU 層を CUDA1/2/3 に分散、B16/B14 化。threads は本 Phase の最適値を使用。
2. **Phase T-5a-ub2** (ub 微細): ub ∈ {200, 224, 256, 288, 320} の微細スイープ。18.3+ t/s 狙い。
3. **Phase T-5a-ctx** (長コンテキスト): ctx=65k × ub=256 × threads=(本 Phase 最適値)。Pareto 拡張。
4. **Phase T-6** (ビルドフラグ AB): `GGML_CUDA_FORCE_MMQ` / `FORCE_DMMV` の rebuild 比較。P100 効果確定。
5. **Phase T-7** (SMT/NUMA 解除 AB): numactl 束縛解除 + threads 44-56 での挙動。NUMA 違反の定量化。

## リスク・対策

| リスク | 対策 |
|--------|------|
| drift 線形性崩壊 (thr40_mid が予測から外れる) | thr40_mid 検証で早期検知、外れたら 2 次回帰や区間別補正に切替 |
| threads=14 での測定時間超過 (CPU 律速で延長) | 夜間バッチ前提、総時間 150 分想定でバッファ確保 |
| session 間 drift (T-5a-ub 18.103 から離れる) | bracket で absolute drift 計測、0.3 t/s 超なら Phase 中断して再実行 |
| GPU ロック競合 | 事前に lock-status 確認、取得後即 batch 開始 |

## 期待される発見

1. **高確率 (80%)**: threads=40 が依然最良、対 T-5a-ub ub=256 で ±0.1 t/s 以内で再現 (B=18 は CPU 律速が軽いため threads 鈍感の仮説)
2. **中確率 (15%)**: threads=32 or 36 で +0.2〜+0.5 t/s の僅少改善 (CPU 層 14 に比して threads 過多説の検証)
3. **低確率 (5%)**: threads=14 で dip (CPU 層 ≒ threads 仮説成立)、T-3 現象の一般性確認

いずれの結果も「B=18 × ub=256 での最適 threads 確定 + dip 仮説の B=18 検証」は達成される。

## 検証方法 (本 Phase 完了時のテスト)

- [ ] topology.log が attachment に存在し、40 コア SMT OFF を記録
- [ ] results.csv に 9 label 全て記載、各 5 run の stdev < 0.03 t/s
- [ ] drift 補正後 thr40a ≒ thr40z ≒ 18.103 (T-5a-ub 再現性 ±0.05)
- [ ] thr40_mid が thr40a と thr40z の線形予測値 ±0.05 t/s 以内
- [ ] threads_eval.png が 2 系列 (raw/corrected) + 回帰線で可読
- [ ] レポート「核心発見サマリ」冒頭に PNG 埋め込み
- [ ] 全 Phase 比較表に T-5a-thr 行追加
- [ ] 未検証事項・検証完了後 TODO セクション記載
- [ ] タイトル 50 字以内
