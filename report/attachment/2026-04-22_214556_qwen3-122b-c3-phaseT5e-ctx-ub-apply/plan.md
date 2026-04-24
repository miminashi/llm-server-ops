# Phase T-5e: B28 × Phase S 条件 (ctx=65k, ub=512) 適用

## Context

Phase T-5 で **B28 (CPU 28 層) × threads=40 で eval_mean = 16.024 t/s を達成、歴代最高 Phase D (15.03) を +6.62% 更新する新記録**を樹立した。本 Phase T-5e は、T-5 レポートの「**検証完了後に実施すべき TODO・優先度最高**」および未検証事項テーブルの第一項目を実施する:

> **B28 × Phase S 条件 (ctx=65k, ub=512) 適用** — 本 Phase 最良 OT (B28) を Phase S 最良 ctx/ub と組合せ、16.3+ t/s 超え狙い

**軸選定根拠 (ユーザ提示候補 a-e との比較)**:

| 候補 | 期待情報量 | コスト | VRAM リスク | 期待ゲイン | 選定 |
|------|----------|-------|------------|-----------|------|
| **(b) B28 × ctx/ub 最適化 (=T-5e)** | **◎** (2 因子分離 + 新記録狙い) | 100-125 分 | 低 (ub=512 で逆に余裕) | **+0.1〜+0.4 t/s** (線形加算で 16.1、相乗で 16.4) | **★本命** |
| (a) OT 再配分 (CUDA1/2 拡張) | ○ (VRAM 限界探索) | 120+ 分 | **高** (dry-start 3-4 回、多くは OOM) | 不明、+0〜+0.5 | 後回し |
| (c) q8_0 KV + B28 | × (T-5 既定で既検証) | - | - | 0 | 不要 |
| (d) B28 再現性検証 | △ (定量化だが性能向上なし) | 60 分 | 低 | +0 | 後回し |
| (e) ビルドフラグ | △ (P100 で効く保証なし) | **3-5 h** | 中 | 不明 | 後回し |

**本軸が最良な理由**:
1. Phase S で確立した **2 軸 compute buffer 予測モデル** (CUDA3 compute = 0.9824×ub MiB) により、B28 環境下の VRAM 挙動を事前に精確予測可能
2. Phase S (ctx=65k, ub=512) での +0.36 t/s (vs Phase D) の効果が、Phase T-5 B28 (+0.99 t/s vs Phase D) に純加算されるか、相乗効果で更に増えるかを**単一実験で決定**
3. dry-start が 2 つの事前計算ポイント (最大 VRAM = ctx=65k × ub=1586 / 本命 = ctx=65k × ub=512) で済む
4. 既存 `start_phaseT5.sh` は `CTX_SIZE` / `UB_SIZE` / `BATCH_SIZE` が環境変数化済み、scripts 流用コスト最小

## Phase S 2 軸モデルによる B28 × ctx=65k × ub=512 の VRAM 予測

Phase S で導出された compute buffer 予測式 (f16 KV ベース、q8_0 では係数に誤差ありうる):

```
CUDA3 compute = 0.9824 × ub   (ctx 非依存、16 点実測 R²=1.000)
CUDA1/2 compute = 520.26 + 3.903e-3·Δctx + 0.2538·Δub + 1.910e-6·Δctx·Δub
```

Phase T-5 B28 の実測 CUDA3 使用量 (ctx=32k, ub=1586, q8_0):
- model 12,829 MiB + KV 102 MiB + compute 1,558 MiB ≈ **14,489 MiB** (dry-start で 14,522 実測) / 16,269 MiB

**予測: B28 × ctx=65k × ub=512**
- model 12,829 (不変) + KV ~204 (ctx 倍増 → q8_0 で +102) + compute 503 (= 0.9824×512) ≈ **13,536 MiB**
- **ub=1586 ベースより -953 MiB マージン改善**、空き 2,700 MiB (OOM リスク 低)

**予測: B28 × ctx=65k × ub=1586** (因子分離用)
- model 12,829 + KV 204 + compute 1,558 ≈ **14,591 MiB**
- 空き 1,678 MiB (ub=1586 の `ctx=32k` 時より +70 MiB のみ、**最も VRAM タイト**、dry-start 必須)

**B28 × ctx=32k × ub=512** (ub 単独効果分離用)
- model 12,829 + KV 102 + compute 503 ≈ **13,434 MiB** (最余裕)

## Design

### 実験マトリクス (5 条件、推定 100-125 分)

| # | label | ctx | ub | OT | threads | 役割 |
|---|-------|-----|-----|----|---------|------|
| 1 | **B28_32k_1586_a** | 32768 | 1586 | B28 | 40 | **drift 起点** (T-5 B28 = 16.024 再現確認) |
| 2 | **B28_65k_ub512** | 65536 | 512 | B28 | 40 | **★本命** (Phase S 条件適用、16.3+ 狙い) |
| 3 | **B28_65k_ub1586** | 65536 | 1586 | B28 | 40 | ctx 単独効果分離 |
| 4 | **B28_32k_ub512** | 32768 | 512 | B28 | 40 | ub 単独効果分離 |
| 5 | **B28_32k_1586_z** | 32768 | 1586 | B28 | 40 | **drift 終点** |

各条件: warmup 2 run + eval 5 run = 7 measurement
5 条件 × 7 run = **35 measurement**

**固定パラメータ (T-5 から完全継承)**:
- OT = B28 = `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU`
- KV = q8_0 (k/v 両方)
- split-mode = layer
- flash-attn = 1, parallel = 1, poll = 0, -ngl 999
- numactl --cpunodebind=1 --membind=1, threads = 40
- llama.cpp `6990e2f1f` (Phase T-1〜T-5 と同一バイナリ、**再ビルド不要**)

### 実行順序 (session drift mitigation)

```
[1] B28_32k_1586_a    drift 起点 (T-5 B28 = 16.024 再現)   ≈ 18 min
[2] B28_65k_ub512     ★本命 (Phase S 条件適用)             ≈ 22 min  (ctx=65k で KV 割当 +時間)
[3] B28_65k_ub1586    ctx 単独 (因子分離)                   ≈ 22 min
[4] B28_32k_ub512     ub 単独 (因子分離)                    ≈ 18 min
[5] B28_32k_1586_z    drift 終点                            ≈ 18 min
                      + overhead 20 min
                      ≈ 118 min
```

順序の根拠:
- drift 起点/終点を B28_32k_1586 (T-5 最良の基準条件) に固定、session 間 drift を定量化 (T-5 実績 0.003 t/s / 0.02%、健全継続期待)
- 本命 (B28_65k_ub512) を 2 番目に置き、session warmup 恩恵を受けやすい位置に
- 因子分離条件 (3, 4) で 2×2 factorial な analysis 可能 (B28_a / B28_65k_ub512 / B28_65k_ub1586 / B28_32k_ub512 の 4 点)

### 判定基準

| 判定 | 閾値 |
|------|------|
| **歴代新記録** (Phase T-5 超え) | B28_65k_ub512 eval_mean > 16.024 t/s |
| **Phase S 条件の純加算効果** | B28_65k_ub512 − B28_32k_1586_a ≥ +0.07 t/s (Phase S の ub/ctx 相対効果 +0.44% を踏襲) |
| **相乗効果 (本命の追加効果)** | B28_65k_ub512 − (B28_65k_ub1586 + B28_32k_ub512 − B28_a) > 0 |
| trend (ctx 効果) | B28_65k_ub1586 vs B28_a の差 (正: ctx 増で有利) |
| trend (ub 効果) | B28_32k_ub512 vs B28_a の差 (正: ub 減で有利) |
| drift 健全 | B28_a と B28_z の差 < 0.2 t/s (T-5 実績 0.003 継続期待) |
| output 品質 | 全 5 条件で Thinking Process 構造保持 |

### scripts 流用計画

Phase T-5 の scripts は `CTX_SIZE` / `BATCH_SIZE` / `UB_SIZE` が環境変数化済なので、`batch_phaseT5e.sh` の CONDITIONS 配列定義だけで対応可能:

| ファイル | T-5e 対応 | 変更点 |
|---------|----------|-------|
| `start_phaseT5.sh` | **そのまま流用** (sed で `T5` → `T5e` のログ名変換のみ) | なし or 最小 |
| `measure_phaseT5.sh` | そのまま流用 | なし |
| `run_all.sh` | そのまま流用 | なし |
| `batch_phaseT5e.sh` | **新規** | CONDITIONS 配列を 5 条件 (ctx, ub) の組合せに書換 |
| `analyze_phaseT5e.py` | **新規** | CONDITIONS、PEAK_PHASE_T5=16.024 定数追加、pivot 表に (ctx, ub) 列 |
| `plot_phaseT5e.py` | **新規** | x 軸 = 条件ラベル、色分け = (ctx, ub)、Phase D/S/T-4/T-5 peak 基準線 |

### 実行ステップ

1. **GPU ロック取得** (`.claude/skills/gpu-server` 使用)
   ```bash
   .claude/skills/gpu-server/scripts/lock.sh t120h-p100
   ```

2. **添付ディレクトリ準備 + scripts コピー**
   ```bash
   REPORT_TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
   ATTACH="report/attachment/${REPORT_TS}_qwen3-122b-c3-phaseT5e-ctx-ub-apply"
   mkdir -p "${ATTACH}/startup_logs"
   SRC="report/attachment/2026-04-22_201929_qwen3-122b-c3-phaseT5-ot-aggressive"
   cp "${SRC}"/{start_phaseT5.sh,measure_phaseT5.sh,run_all.sh} "${ATTACH}/"
   cp -r "${SRC}/prompts" "${ATTACH}/"
   # plan.md を添付
   cp /home/ubuntu/.claude/plans/phase-t-5-ot-rustling-rain.md "${ATTACH}/plan.md"
   ```

3. **Dry-start (2 ポイント、タイトケースと本命ケース)**
   ```bash
   # 3a. 本命の B28 × ctx=65k × ub=512 (VRAM 余裕想定)
   FLASH_ATTN=1 CTX_SIZE=65536 BATCH_SIZE=512 UB_SIZE=512 \
     CACHE_TYPE_K=q8_0 CACHE_TYPE_V=q8_0 SPLIT_MODE=layer THREADS=40 \
     OT_TAG=B28 OT_REGEX='blk\.([0-9]|1[0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU' \
     bash start_phaseT5.sh 2>&1 | tee startup_logs/T5e_drystart_B28_65k_ub512.log
   ssh t120h-p100 "tail -60 /tmp/llama-server_phaseT5_B28_t40_*ctx65536_b512_ub512.log"
   bash /home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh t120h-p100

   # 3b. 最も VRAM タイト: B28 × ctx=65k × ub=1586 (Phase S モデル予測: CUDA3 total ≈ 14,591 MiB)
   FLASH_ATTN=1 CTX_SIZE=65536 BATCH_SIZE=1586 UB_SIZE=1586 \
     CACHE_TYPE_K=q8_0 CACHE_TYPE_V=q8_0 SPLIT_MODE=layer THREADS=40 \
     OT_TAG=B28 OT_REGEX='blk\.([0-9]|1[0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU' \
     bash start_phaseT5.sh 2>&1 | tee startup_logs/T5e_drystart_B28_65k_ub1586.log
   bash /home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh t120h-p100
   ```
   - OOM 時は該当条件を skip (特に 3b が OOM なら `B28_65k_ub1586` を条件 #3 から除外、4 条件実行に短縮)

4. **本番 batch 実行** (5 or 4 条件 × 7 run = 35/28 measurement)
   ```bash
   nohup bash batch_phaseT5e.sh > batch_phaseT5e.log 2>&1 &
   tail -f batch_phaseT5e.log
   ```

5. **解析 & 作図**
   ```bash
   python3 analyze_phaseT5e.py    # TSV / CSV / pivot Markdown
   python3 plot_phaseT5e.py       # 条件別 eval_tps / prompt_tps 比較 (Phase D/S/T-5 基準線付き)
   ```

6. **ロック解放**
   ```bash
   .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
   ```

### batch_phaseT5e.sh の CONDITIONS 配列設計

```bash
# LABEL#CTX#UB#THREADS  (OT は B28 固定、KV q8_0 固定、SM layer 固定)
CONDITIONS=(
  'B28_32k_1586a#32768#1586#40'
  'B28_65k_ub512#65536#512#40'
  'B28_65k_ub1586#65536#1586#40'
  'B28_32k_ub512#32768#512#40'
  'B28_32k_1586z#32768#1586#40'
)
```

batch 内で `CTX_SIZE`, `BATCH_SIZE`=`UB_SIZE`, `THREADS` を環境変数として `start_phaseT5.sh` に渡す (OT_TAG/OT_REGEX/KV は全条件共通で batch 冒頭に定数化)。

### 作成ファイル一覧

**plan 添付先** (本 plan のコピー):
- `report/attachment/<timestamp>_qwen3-122b-c3-phaseT5e-ctx-ub-apply/plan.md`

**batch 実行系**:
- `start_phaseT5.sh` (T-5 流用、変更なし)
- `measure_phaseT5.sh` (T-5 流用、変更なし)
- `run_all.sh` (T-5 流用、変更なし)
- `batch_phaseT5e.sh` (**新規、CONDITIONS 配列 5 条件**)

**解析系**:
- `analyze_phaseT5e.py` (PEAK_PHASE_T5=16.024 定数追加、pivot 表に `ctx` / `ub` 列)
- `plot_phaseT5e.py` (条件別 eval/prompt の bar 比較、Phase D/S/T-5 peak 水平線)

**出力**:
- `summary_phaseT5e.tsv` / `phaseT5e_stats.csv` / `phaseT5e_pivot.md`
- `phaseT5e_eval_tps.png` (**核心発見サマリ冒頭に画像埋め込み用**)
- `phaseT5e_drift.png` (session drift 可視化)
- `startup_logs/T5e_drystart_B28_65k_ub512.log` / `T5e_drystart_B28_65k_ub1586.log`
- `startup_logs/T5e_{cond}_*.log`

## 検証方法 (end-to-end)

1. **Dry-start 成功確認**: `startup_logs/T5e_drystart_*.log` に `llama_params_fit` 成功、`cannot fit` / OOM なし
2. **本番 batch 完走確認**: `batch_phaseT5e.log` 末尾に `[batchT5e] end at`、`ERROR:` なし
3. **解析出力確認**: `summary_phaseT5e.tsv` に 5 条件 × 7 run = 35 行 (or 4 条件時 28 行)、`phaseT5e_stats.csv` に 5/4 行
4. **グラフ生成確認**: `phaseT5e_eval_tps.png` で 5 条件の mean±stdev、Phase D/S/T-4/T-5 peak 水平線、drift 起点/終点の色分け可視
5. **出力品質確認**: 各条件 run1 の `reasoning_content` 冒頭に Thinking Process 構造あり (崩壊なし)
6. **判定**: B28_65k_ub512 の eval_mean が **16.024 t/s (T-5 peak) を超えるか**、および Phase S 条件の加算効果が純加算か相乗効果かを判定

## レポート作成ルール (CLAUDE.md / REPORT.md 遵守)

- タイトル ≤ 50 字、候補: 「Phase T-5e: B28 × Phase S 条件 (ctx=65k, ub=512) 適用」(23 字)
- 核心発見サマリ冒頭に `phaseT5e_eval_tps.png` を画像埋め込み (REPORT.md 必須)
- 全 Phase 比較表 (D/S/T-1/T-2/T-3/T-4/T-5/**T-5e**)
- Phase T-5 の未検証事項 TODO を本 Phase で「完了」としてマーク
- 新たな未検証事項セクションと TODO セクションを必ず含める
  - T-5f (main-gpu=3), T-5g (threads 精密 sweep), T-5a (OT 再配分), T-6 (build flag) への布石
- 参照レポートリンク: Phase T-5, Phase S, Phase D, Phase T-4

## 重要参照ファイル

- **Phase T-5 (直前、16.024 新記録)**: `report/2026-04-22_201929_qwen3-122b-c3-phaseT5-ot-aggressive.md`
  - scripts 流用元: `report/attachment/2026-04-22_201929_qwen3-122b-c3-phaseT5-ot-aggressive/`
  - B28 VRAM 実測: `startup_logs/T5_drystart_B28_t40.log`
- **Phase S (ctx/ub 2D スイープ、2 軸モデル確立)**: `report/2026-04-19_120715_qwen3-122b-c3-phaseS-ub-ctx-2d.md`
  - 2 軸予測式: CUDA3 = 0.9824·ub / CUDA1/2 = 520.26 + 3.903e-3·Δctx + 0.2538·Δub + 1.910e-6·Δctx·Δub
  - Phase S 条件 = A36 (CPU 36 層) × ctx=65k × ub=512 × **f16 KV** (本 Phase T-5e は q8_0 で係数に 5〜10% 誤差想定)

## 未検証事項と次 Phase 候補 (T-5e 完了後の布石)

本 Phase でも扱わない軸:

| 項目 | 候補 Phase | 理由 |
|------|-----------|------|
| **OT 再配分 (CUDA0 拡張 via -ts)** | Phase T-5a | CUDA0 空き 13+ GB を tensor-split 明示指定で活用、B24 領域を開拓 |
| **main-gpu=3 + B28** | Phase T-5f | CUDA3 完結仮説の直接検証 |
| **threads 精密 sweep × B28** | Phase T-5g | threads ∈ {36, 38, 40, 42} |
| **ビルドフラグ** | Phase T-6 | `GGML_CUDA_FORCE_MMQ` / `GGML_CUDA_FORCE_DMMV`、最大工数枠 |
| **KV 非対称 × B28** | Phase T-1b | K=q5_0 V=q8_0 等 |
| **split-mode=tensor + B28** | Phase T-2b | 4 GPU 均等化 |
| **B28 の Nsight profiling** | 要検討 | qualitative jump の原因分析 |
| **perplexity 評価** | wikitext-2 / JMMLU | 現状目視のみ |

## 検証完了後に実施すべき TODO (T-5e レポート側に継承)

### 短期 (最優先)

1. **T-5e 結果に応じた分岐**:
   - **新記録 (eval > 16.024) 達成時**: Phase T-6 (build flag) を T-5e 最良条件 baseline で実施、再ビルド 4 回
   - **null (eval ≤ 16.024) 時**: T-5f (main-gpu=3) or T-5a (OT 再配分) で別軸探索
2. **session drift の定量化 Phase** (T-5 B28 を 10-20 回連続測定、自己相関構造)

### 中期

3. T-5g (threads 精密 sweep × B28_best)
4. T-2b (split-mode=tensor + B28)
5. T-1b (KV 非対称 × B28 baseline)

### 長期

6. SMT ON + 2D 再スイープ (BIOS 変更要)
7. KV 量子化 perplexity 定量評価
8. Phase U 以降: 別モデル knowledge 転移
