# Phase T-5: OT 層削減による eval_tps 上限探索

## Context

直前 Phase T-4 で **B32 (CPU 32 層) × threads=40 で eval_mean = 15.494 t/s を達成、歴代最高 Phase S (15.39) を +0.68% 更新** する breakthrough を得た。T-4 結果は「CPU offload 層数の減少 → GPU model buffer 増 → eval_tps monotonic 向上」という強い相関 (32→36 で -0.44 / 36→40 で -0.95 / 40→42 で -0.13) を示した。

本 Phase T-5 は **同一 trend を更に B32 → B28 方向へ延長**し、以下を同時検証する:

1. **Trend 継続性**: B28 が B32 から +0.3〜+0.4 t/s 改善するか (線形外挿で 15.9 t/s 想定)
2. **VRAM 絶対限界の特定**: CUDA3 担当範囲 (layer 36-47 の 12 層) が物理制約。B28 で 40-47 (8 expert 層 ≈ 11136 MiB 模型 + compute ~1700 MiB → CUDA3 total 12836 MiB / 16269 MiB) は fit 見込み、B24 は CUDA3 に 36-47 (12 層 = 16704 MiB) で **確定 OOM**
3. **新記録狙い**: eval 15.5+ t/s 達成で Phase S peak 更新継続
4. **T-3 仮説の追加検証**: B28 × threads=28 は技術上困難 (CPU bind affinity の影響不明) なので代わりに B28 × threads=32 (層 28 ≠ threads 32、不一致条件) で drift 補正ベース

本 Phase は `ctx=32768, ub=1586, KV=q8_0, split=layer, numactl -N1 -m1, flash-attn=1` の **T-4 最良設定を完全継承**し、OT pattern のみを動かす clean な単一軸 sweep。

## Design

### 実験マトリクス (5 条件、推定 90-110 分)

| # | OT TAG | CPU 層数 | GPU 配置追加 | threads | 役割 |
|---|--------|---------|-------------|---------|------|
| 1 | **B32** | 32 | 44-47 (baseline) | 40 | **session drift 起点** (T-4 B32-t40 = 15.494 再現確認) |
| 2 | **B30** | 30 | 42-47 | 40 | **中間点** (B32→B28 の monotonic 検証) |
| 3 | **B28** | 28 | 40-47 | 40 | **本命** (VRAM 限界想定、新記録狙い) |
| 4 | **B28** | 28 | 40-47 | 32 | 層≠threads 不一致条件 (drift 補正用 control) |
| 5 | **B32** | 32 | 44-47 | 40 | **session drift 終点** (drift の大きさ定量化) |

各条件: **warmup 2 run + eval 5 run = 7 measurement**

### OT regex 設計

T-4 の convention を継承 (`blk\.(...)\.ffn_.*_exps\.weight=CPU`):

| tag | regex 中カッコ内 | 含まれる層 (マッチ数) |
|-----|----------------|---------------------|
| **B32** | `[0-9]\|1[0-3]\|2[0-4]\|3[1-9]\|4[0-3]` | 0-9, 10-13, 20-24, 31-39, 40-43 (32) |
| **B30** | `[0-9]\|1[0-3]\|2[0-4]\|3[1-9]\|4[0-1]` | 0-9, 10-13, 20-24, 31-39, 40-41 (30) |
| **B28** | `[0-9]\|1[0-3]\|2[0-4]\|3[1-9]` | 0-9, 10-13, 20-24, 31-39 (28) |

**削減方向の選択根拠**: T-4 dry-start ログより CUDA3 担当範囲は layer 36-47。B32 時点で CUDA3 model buffer = 7261 MiB (44-47 の 4 expert 層)、空き 7024 MiB。ここに 40-43 (B28) の 4 層を追加で載せると 7261 + 5568 = 12829 MiB (fit)。一方 CUDA1 (担当 12-23、現行 14-19 で 9551 MiB、空き 5832 MiB) に `2[0-3]` を CPU→GPU で戻すと +6368 → OOM。**CUDA3 を埋める方向が唯一の実行可能軸**。

### VRAM fit 事前計算

| OT | CUDA0 | CUDA1 (14-19) | CUDA2 (25-30) | CUDA3 追加層 | CUDA3 model (MiB) | CUDA3 total (MiB) | 空き | 判定 |
|----|-------|---------------|---------------|--------------|-------------------|-------------------|-----|------|
| B32 (実測) | 1301 | 9551 | 9551 | 44-47 (4) | 7261 | 8954 | 7024 | OK |
| **B30** (予想) | 1301 | 9551 | 9551 | 42-47 (6) | ~10045 | ~11738 | ~4531 | **OK** |
| **B28** (予想) | 1301 | 9551 | 9551 | 40-47 (8) | ~12829 | ~14522 | ~1747 | **OK (タイト)** |
| B24 (NG) | 1301 | 9551 | 9551 | 36-47 (12) | ~16704 | ~18397 | **負** | **OOM 確定** |

B28 は CUDA3 total 14522 MiB 想定、空き 1747 MiB。ctx=32768 の KV は q8_0 で per-layer ~50 MiB × 12 (CUDA3 担当) = 600 MiB 程度。余裕 1100 MiB で推論 compute buffer を賄えるか dry-start で確認必須。

### 実行順序 (session drift mitigation 付き)

```
[1] B32-t40  (drift 起点)         ≈ 18 min
[2] B30-t40                      ≈ 18 min
[3] B28-t40  ★本命               ≈ 18 min
[4] B28-t32  (不一致 control)    ≈ 18 min
[5] B32-t40  (drift 終点)        ≈ 18 min
             ----------------
             = 90 min + overhead 20 min ≈ 110 min
```

順序の根拠:
- B32 を最初と最後に挟むことで session drift を定量化 (T-4 で判明した ~3-5% 変動を補正)
- B30 を中間に置き trend の線形性を確認
- B28-t32 は低リスク (VRAM 的に B28-t40 と同じ) で最後に

### 判定基準

| 判定 | 閾値 |
|------|------|
| **Phase T-4 (15.494) 超え** | eval_mean > 15.494 t/s |
| trend 線形性 STRONG | B28 > B30 > B32 で単調増、差 ≥ 0.1 t/s |
| trend NEUTRAL | B28 ≈ B32 (差 < 0.05 t/s)、plateau 到達示唆 |
| trend REVERSE | B28 < B32 (差 > 0.1 t/s)、GPU saturate 仮説支持 |
| drift 健全 | B32 起点・終点の差 < 0.2 t/s (< 1.3%) |
| drift 大 | B32 起点・終点の差 ≥ 0.2 t/s、絶対値比較は drift 補正前提 |

### scripts 流用計画

Phase T-4 の scripts はほぼそのまま再利用可能 (start_phaseT4.sh は `OT_REGEX` 環境変数化済、measure/run_all/analyze は命名変更のみ):

| ファイル | Phase T-5 対応 | 変更点 |
|---------|---------------|-------|
| `start_phaseT4.sh` | `start_phaseT5.sh` (sed 置換のみ) | ログ命名 `phaseT4` → `phaseT5` |
| `measure_phaseT4.sh` | `measure_phaseT5.sh` | 命名のみ |
| `run_all.sh` | `run_all.sh` | `measure_phaseT4.sh` → `measure_phaseT5.sh` |
| `batch_phaseT4.sh` | **`batch_phaseT5.sh` (新規)** | CONDITIONS 配列を 5 条件に書換、regex 3 種 |
| `analyze_phaseT4.py` | **`analyze_phaseT5.py` (新規)** | CONDITIONS、OT_LAYER_EFFECTIVE、PEAK_PHASE_T4=15.494 追加 |
| `plot_phaseT4.py` | **`plot_phaseT5.py` (新規)** | x 軸 = CPU 層数 (32/30/28)、session drift の両端 B32 を可視化 |

### 実行ステップ

1. **GPU ロック取得**
   ```bash
   .claude/skills/gpu-server/scripts/lock.sh t120h-p100
   ```

2. **添付ディレクトリ準備**
   ```bash
   REPORT_TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
   ATTACH_DIR="report/attachment/${REPORT_TS}_qwen3-122b-c3-phaseT5-ot-aggressive"
   mkdir -p "${ATTACH_DIR}/startup_logs"
   # T-4 から流用
   cp report/attachment/2026-04-22_183234_qwen3-122b-c3-phaseT4-ot-layer-range/{start_phaseT4.sh,measure_phaseT4.sh,run_all.sh} "${ATTACH_DIR}/"
   cd "${ATTACH_DIR}"
   sed -i 's/phaseT4/phaseT5/g; s/PhaseT4/PhaseT5/g; s/T4_/T5_/g' start_phaseT5.sh measure_phaseT5.sh run_all.sh
   ```

3. **B28 dry-start (VRAM 事前確認)**
   ```bash
   FLASH_ATTN=1 CTX_SIZE=32768 BATCH_SIZE=1586 UB_SIZE=1586 \
     CACHE_TYPE_K=q8_0 CACHE_TYPE_V=q8_0 SPLIT_MODE=layer THREADS=40 \
     OT_TAG=B28 OT_REGEX='blk\.([0-9]|1[0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU' \
     bash start_phaseT5.sh 2>&1 | tee startup_logs/T5_drystart_B28_t40.log
   ssh t120h-p100 "grep -E '(projected memory|CUDA[0-3].*total|OOM|error)' /tmp/llama-server_phaseT5_B28_*.log | head -30"
   bash /home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh t120h-p100
   ```
   - `projected to use` 行で CUDA3 が 16269 MiB を超えない & `cannot fit` エラーがない ことを確認
   - OOM の場合は **B28 を skip し B30 のみ実測** (plan 修正)

4. **本番 batch 実行** (5 条件 × 7 run)
   ```bash
   nohup bash batch_phaseT5.sh > batch_phaseT5.log 2>&1 &
   tail -f batch_phaseT5.log
   ```

5. **解析 & 作図**
   ```bash
   python3 analyze_phaseT5.py
   python3 plot_phaseT5.py
   ```

6. **ロック解放**
   ```bash
   .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
   ```

### 作成ファイル一覧

**plan 添付先** (本 plan のコピー):
- `report/attachment/<timestamp>_qwen3-122b-c3-phaseT5-ot-aggressive/plan.md`

**batch 実行系** (T-4 流用 + 新規):
- `start_phaseT5.sh` (流用)
- `measure_phaseT5.sh` (流用)
- `run_all.sh` (流用)
- `batch_phaseT5.sh` (新規、CONDITIONS 配列 5 条件)

**解析系** (新規):
- `analyze_phaseT5.py` (CONDITIONS 5、PEAK_PHASE_T4=15.494 定数追加)
- `plot_phaseT5.py` (x=CPU 層数 {28,30,32}、B32 drift 両端プロット)

**出力**:
- `summary_phaseT5.tsv` / `phaseT5_stats.csv` / `phaseT5_pivot.md`
- `phaseT5_eval_tps.png` / `phaseT5_heatmap.png` (核心発見サマリに埋め込む PNG)
- `startup_logs/T5_drystart_B28_t40.log` (dry-start VRAM 確認用)
- `startup_logs/T5_{cond}_*.log` (条件別起動ログ)

## 重要参照ファイル

**Phase T-4 (直前、scripts 流用元)**:
- [`2026-04-22_183234_qwen3-122b-c3-phaseT4-ot-layer-range.md`](../../projects/llm-server-ops/report/2026-04-22_183234_qwen3-122b-c3-phaseT4-ot-layer-range.md)
- scripts: `report/attachment/2026-04-22_183234_qwen3-122b-c3-phaseT4-ot-layer-range/`
- VRAM 計算根拠: `startup_logs/T4_drystart_B32_t40.log`

**過去 Phase 比較用 (analyze_phaseT5.py で参照)**:
- Phase D peak: 15.03 t/s
- Phase S peak: 15.39 t/s
- Phase T-1 best: 15.016 t/s
- Phase T-3 best: 14.860 t/s
- **Phase T-4 best: 15.494 t/s (現歴代最高)**

## 検証方法 (end-to-end)

1. **Dry-start 成功確認**: `startup_logs/T5_drystart_B28_t40.log` 内に `llama_params_fit: successfully fit` があり、`cannot fit` / `OOM` がないこと
2. **本番 batch 完走確認**: `batch_phaseT5.log` 末尾に `[batchT5] end at` があり、途中で `ERROR:` が出ていないこと
3. **解析出力確認**: `summary_phaseT5.tsv` に 5 条件 × 7 run = 35 行、`phaseT5_stats.csv` に 5 行、`phaseT5_pivot.md` に比較表
4. **グラフ生成確認**: `phaseT5_eval_tps.png` に 5 条件の mean±stdev 点、B32 drift の両端、Phase D/S/T-4 基準線
5. **出力品質確認**: 各条件 run1 の reasoning_content 冒頭が thinking process 構造を保持 (崩壊チェック)
6. **レポート作成** (必須): 以下を含むレポートを `report/` に作成
   - タイトル 50 字以内、例: 「Phase T-5: OT 層削減 (B28) による eval_tps 上限探索」
   - 核心発見サマリ冒頭に `phaseT5_eval_tps.png` を画像埋め込み
   - 全 Phase 比較表 (D/S/T-1/T-2/T-3/T-4/**T-5**)
   - 未検証事項セクション
   - 検証完了後に実施すべき TODO セクション
   - 参照レポートリンク (T-4, S, D)

## 未検証事項と次 Phase 候補 (T-5 完了後の布石)

以下は T-5 スコープ外、T-6 以降で扱う:

| 項目 | 候補 Phase | 理由 |
|------|-----------|------|
| **T-6: ビルドフラグ (GGML_CUDA_FORCE_MMQ/DMMV)** | 最大コスト枠 | 本命残り。B28 (or T-5 最良) baseline で再ビルド 4 種 |
| **B28 × Phase S 条件 (ctx=65k, ub=512) 適用** | Phase T-4e 再設計 | T-5 最良 OT を Phase S 最良 ctx/ub と組合せ |
| **split-mode=tensor + OT** | Phase T-2b | CUDA1/2 のボトルネックを分散で回避、更なる削減可能性 |
| **main-gpu=3 + B28 (CUDA3 を主担当に)** | 要検討 | CUDA3 空き活用でスケジューラ負荷分散 |
| **OMP_SCHEDULE / GOMP_SPINCOUNT 明示指定** | 要検討 | T-3 仮説 (層=threads drop) の cleanseparation |
| **KV 量子化 perplexity (wikitext-2 / JMMLU)** | 品質枠 | 現状目視のみ |

## 検証完了後に実施すべき TODO (T-5 レポート側にも記載)

### 短期 (最優先)

1. **T-5 最良条件 × Phase S ctx/ub (ctx=65536, ub=512) 適用 (Phase T-5e)** (優先度: **最高**)
   - T-5 ベスト (B28 or B30) + Phase S 最良 ctx/ub で 15.7+ t/s 狙い
   - ~60 分の追加 batch

2. **Phase T-6: ビルドフラグ 4 条件 × B28** (優先度: 高)
   - `GGML_CUDA_FORCE_MMQ` ON/OFF × `GGML_CUDA_FORCE_DMMV` ON/OFF
   - 再ビルド 4 回 + 各 15 分 batch = 3-5 時間

3. **Session drift 定量化 Phase** (優先度: 中)
   - 同一条件 (B32 or B28) × t40 を 10-20 回連続測定
   - drift pattern を時系列プロット、平均・分散・自己相関を算出

### 中期

4. **split-mode=tensor + B28 の組合せ (Phase T-2b)** — 4 GPU 均等化で更なる削減可能性
5. **B28 × threads 精密 sweep (Phase T-3 拡張)** — threads ∈ {28, 30, 34, 38, 42} で「層=threads drop」最終判定
6. **KV 非対称 (K=q5_0 V=q8_0 等)** — B28 baseline 下で Phase T-1 残穴調査

### 長期

7. **SMT ON + OT/threads 2D 再スイープ** (BIOS 変更要)
8. **KV 量子化の perplexity 定量評価** (wikitext-2 / JMMLU)
9. **Phase U 以降**: 異なるモデル (Qwen3.5-A3B、DeepSeek-R1) への knowledge 転移検証
