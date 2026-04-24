# Phase T-5a 実装プラン: OT 再配分で eval 16.5+ t/s 狙い

## Context

Phase T-5f (2026-04-22 夜) で qwen3-122b (Q4_K_M) の eval t/s が **16.455 t/s** に到達 (B28 × ctx=32k × ub=512、Phase D baseline 比 +9.48%)。ただし:

- 改善幅は T-5→T-5e (+2.22%) → T-5e→T-5f (+0.46%) と減速、**プラトー接近の兆候**
- T-5f レポートは次 Phase 候補として「T-6 ビルドフラグ」を最優先に挙げたが、**P100 (CC 6.0) は int8 tensor core 非搭載で MMQ 最適化の恩恵対象外、DMMV は deprecated**。compile-time フラグのため再ビルド必須、ROI に疑義
- 一方、T-5f 起動ログから判明: **CUDA0 が 13,858 MiB 空きで 8 expert 層追加可能**。CPU offload 層を CUDA0 に戻す余地は未検証

本 Phase (T-5a) は **OT 再配分で B28 → B24/B20 へ CPU 層を削減** し、CUDA0 空きを活用して eval を更改善する。ビルド不要・約 95 分で完了、歴代更新 or B28 最適性の確定のいずれかのデータが得られる。T-5a 完了後に T-6 を新 baseline で実施することで、sunk cost を回避できる。

## 採用方針

**Phase T-5a: OT 再配分 (B28 → B24 → B20 → B18) を実施**。Phase T-6 は T-5a 完了後の次々 Phase に後回す。

### 候補比較

| 候補 | 期待改善 | コスト | ビルド要否 | 判定 |
|------|---------|-------|-----------|------|
| **T-5a (OT 再配分)** | +0.5 t/s 可能性 (T-5 jump パターン参照) | 95 分 | 不要 | **採用** |
| T-5f-b (ub plateau 詳細) | +0.02 t/s 程度 | 75 分 | 不要 | 後回し |
| T-6 (ビルドフラグ) | 不定 (P100 では悪化もあり得る) | 2-3 h + 再ビルド | 要 | 次々 Phase |
| T-5g (threads sweep) | +0.05 t/s 程度 | 80 分 | 不要 | 後回し |

## OT パターン設計

**現行 B28**: `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU`
CPU layer = {0-9, 10-13, 20-24, 31-39} = **28 層**

T-5f startup log 実測:
- split-mode=layer round-robin: CUDA0=layer 0-11, CUDA1=layer 12-23, CUDA2=24-35, CUDA3=36-47 (各 12 層)
- 1 expert 層 (ffn_\*_exps) ≈ **1,600 MiB** (CUDA1 model buf 9,551 / GPU 化 6 層 より)
- CUDA0 空き 13,858 MiB、CUDA1 空き 6,138、CUDA2 空き 6,138、CUDA3 空き 2,511

### 候補条件

| タグ | regex | CPU 層数 | CPU→GPU 戻し層 | CUDA0 予測 used | CUDA1 予測 used | 判定 |
|------|-------|---------|----------------|----------------|----------------|------|
| B28 (baseline) | `blk\.([0-9]\|1[0-3]\|2[0-4]\|3[1-9])` | 28 | -- | 2,411 | 9,836 | fit (実測) |
| **B24** | `blk\.([0-9]\|2[0-4]\|3[1-9])` | 24 | 10-13 (+4) | ~5,611 | ~13,036 | **fit** |
| **B20** | `blk\.([0-5]\|2[0-4]\|3[1-9])` | 20 | 6-13 (+8) | ~12,011 | ~13,036 | **fit** (境界) |
| B18 | `blk\.([0-3]\|2[0-4]\|3[1-9])` | 18 | 4-13 (+10) | ~15,211 | ~13,036 | **境界** |
| B16 | `blk\.([01]\|2[0-4]\|3[1-9])` | 16 | 2-13 (+12) | ~18,411 | ~13,036 | **OOM 確実** |

→ **B24 / B20 / B18** の 3 点スイープ + B28 drift bracket が最適。B16 は実施価値なし (確実 OOM)、B18 で OOM 境界をテストすれば十分。

### 固定パラメータ

ctx=32768 / ub=512 / KV=q8_0 / split-mode=layer / threads=40 / numactl -N1 -m1 / flash-attn=1 / parallel=1 / poll=0

## 測定条件と実行順

| # | label | OT | 役割 |
|---|-------|----|------|
| 1 | B28_run1 | B28 | **drift 起点** (T-5f 16.455 再現検証、session 独立性テスト) |
| 2 | B24_run1 | B24 | 主候補 (+4 層 GPU 戻し) |
| 3 | B20_run1 | B20 | 主候補 (+8 層、境界付近) |
| 4 | B18_run1 | B18 | OOM 境界テスト (OOM なら skip、fit なら実測) |
| 5 | B20_run2 | B20 | 再現性検証 |
| 6 | B24_run2 | B24 | 再現性検証 |
| 7 | B28_run2 | B28 | **drift 終点** |

- warmup 2 + eval 5 = 7 measurement / 条件 × 7 条件 = **49 measurement**
- B18 OOM 時は 42 measurement
- 想定所要時間: **95-105 分** (T-5f 実績 13.4 分/条件から按分)

## 成功/失敗判定

| 判定 | 閾値 | 意味・次アクション |
|------|------|------|
| **SUCCESS (歴代更新)** | B20 or B24 or B18 のいずれかで eval_mean > 16.455 | 新記録。B14-B16 の細粒度スイープを次 Phase へ |
| partial | 最良 > 16.380 (T-5e 超) | drift 補正後判定、微改善としてカタログ化 |
| **B28 最適確定** | 全ての B24/B20/B18 < B28 信頼区間下限 (16.44 目安) | **OT 削減飽和**、次 Phase は T-6 ビルドフラグへ |
| OOM data | B18 が cudaMalloc failed | CUDA0 限界 layer 境界データ、B19 で再トライ候補 |
| drift 不健全 | \|B28_run1 - B28_run2\| > 0.15 t/s | 絶対値比較不能、drift 補正計算必須 |

T-5f で drift -0.25% だった実績を踏まえ、閾値は 0.15 t/s (T-5f の 4 倍) を unhealthy 境界とする。

## 既存スクリプト流用 (新規は 3 ファイルのみ)

### 完全再利用

- `start_phaseT5.sh`: OT_TAG / OT_REGEX を envvar で受ける実装 (T-5f で確認済)。変更不要
- `run_all.sh` / `measure_phaseT5.sh` / `prompts/`: warmup 2 + eval 5 × 1k prompt、完全流用

### 新規 (3 ファイル)

1. **`batch_phaseT5a.sh`**: T-5f の batch を CONDITIONS 配列のみ差し替え
   ```bash
   CONDITIONS=(
     'B28_run1#32768#512#B28#blk\.([0-9]|1[0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
     'B24_run1#32768#512#B24#blk\.([0-9]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
     'B20_run1#32768#512#B20#blk\.([0-5]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
     'B18_run1#32768#512#B18#blk\.([0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
     'B20_run2#32768#512#B20#blk\.([0-5]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
     'B24_run2#32768#512#B24#blk\.([0-9]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
     'B28_run2#32768#512#B28#blk\.([0-9]|1[0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'
   )
   # loop 内で IFS='#' read -r LABEL CTX UB OT_TAG_LOCAL OT_REGEX_LOCAL <<< "$COND"
   # 各条件で OT_TAG="$OT_TAG_LOCAL" OT_REGEX="$OT_REGEX_LOCAL" を start_phaseT5.sh に envvar 渡し
   ```
2. **`analyze_phaseT5a.py`**: T-5f の analyze を x 軸 (ub → CPU 層数) に差し替え、stats CSV の phase 比較カラムを T-5f (16.455) 基準に変更
3. **`plot_phaseT5a.py`**: x 軸が CPU 層数の trend line + drift bracket + (あれば) Pareto

## Critical Files (reference & to create)

### 参照 (read-only)

- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-22_232010_qwen3-122b-c3-phaseT5f-ub-fine-sweep/start_phaseT5.sh` — 起動スクリプト、envvar 仕様確認済
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-22_232010_qwen3-122b-c3-phaseT5f-ub-fine-sweep/batch_phaseT5f.sh` — batch ひな型
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-22_232010_qwen3-122b-c3-phaseT5f-ub-fine-sweep/run_all.sh` / `measure_phaseT5.sh` / `prompts/`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-22_232010_qwen3-122b-c3-phaseT5f-ub-fine-sweep/analyze_phaseT5f.py` / `plot_phaseT5f.py` — analyze/plot ひな型
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-22_232010_qwen3-122b-c3-phaseT5f-ub-fine-sweep/startup_logs/T5f_B28_32k_ub512a_*.log` — CUDA VRAM 実測
- `/home/ubuntu/projects/llm-server-ops/REPORT.md` — レポート作成ルール
- `.claude/skills/gpu-server/scripts/` — ロック管理
- `.claude/skills/llama-server/scripts/stop.sh` — 停止スクリプト

### 作成 (plan 承認後)

- `report/attachment/<TS>_qwen3-122b-c3-phaseT5a-ot-redistribution/batch_phaseT5a.sh`
- `report/attachment/<TS>_qwen3-122b-c3-phaseT5a-ot-redistribution/analyze_phaseT5a.py`
- `report/attachment/<TS>_qwen3-122b-c3-phaseT5a-ot-redistribution/plot_phaseT5a.py`
- `report/attachment/<TS>_qwen3-122b-c3-phaseT5a-ot-redistribution/plan.md` (本 plan のコピー)
- `report/attachment/<TS>_qwen3-122b-c3-phaseT5a-ot-redistribution/{start_phaseT5.sh, run_all.sh, measure_phaseT5.sh, prompts/}` (cp で複製)
- `report/<TS>_qwen3-122b-c3-phaseT5a-ot-redistribution.md` — レポート本体 (T-5f テンプレ流用)

## 実行手順

### Step 1: attachment 準備

```bash
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_NAME="${TS}_qwen3-122b-c3-phaseT5a-ot-redistribution"
ATTACH_DIR="/home/ubuntu/projects/llm-server-ops/report/attachment/${REPORT_NAME}"
SRC_DIR="/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-22_232010_qwen3-122b-c3-phaseT5f-ub-fine-sweep"
mkdir -p "${ATTACH_DIR}/startup_logs"
cp "${SRC_DIR}/start_phaseT5.sh" "${SRC_DIR}/run_all.sh" "${SRC_DIR}/measure_phaseT5.sh" "${ATTACH_DIR}/"
cp -r "${SRC_DIR}/prompts" "${ATTACH_DIR}/"
cp /home/ubuntu/.claude/plans/phase-t-5f-ub-cheeky-sedgewick.md "${ATTACH_DIR}/plan.md"
# batch_phaseT5a.sh, analyze_phaseT5a.py, plot_phaseT5a.py を新規作成
```

### Step 2: ロック取得

```bash
bash /home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### Step 3: Dry-start で B18 VRAM 事前確認

```bash
cd "${ATTACH_DIR}"
FLASH_ATTN=1 CTX_SIZE=32768 BATCH_SIZE=512 UB_SIZE=512 \
  CACHE_TYPE_K=q8_0 CACHE_TYPE_V=q8_0 SPLIT_MODE=layer THREADS=40 \
  OT_TAG=B18 OT_REGEX='blk\.([0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU' \
  bash start_phaseT5.sh 2>&1 | tee startup_logs/drystart_B18.log
# 成功なら SKIP_LABELS を空に、OOM なら SKIP_LABELS=B18_run1 を指定
bash /home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh t120h-p100
```

### Step 4: バッチ実行 (約 95-105 分、B18 skip なら 80 分)

```bash
cd "${ATTACH_DIR}"
nohup bash batch_phaseT5a.sh > batch_phaseT5a.log 2>&1 &
# B18 OOM なら: SKIP_LABELS=B18_run1 nohup bash batch_phaseT5a.sh ...
```

進捗監視は `tail -f batch_phaseT5a.log`。

### Step 5: 解析とプロット

```bash
python3 analyze_phaseT5a.py    # summary_phaseT5a.tsv / phaseT5a_stats.csv / phaseT5a_pivot.md
python3 plot_phaseT5a.py       # phaseT5a_trend.png (x=CPU 層数) / phaseT5a_drift.png / phaseT5a_pareto.png
```

### Step 6: ロック解放

```bash
bash /home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### Step 7: レポート作成

`report/${REPORT_NAME}.md` を T-5f レポートテンプレ流用で作成。必須セクション:

- **タイトル**: 50 字以内 (例: `Phase T-5a: OT 再配分で eval X.XXX t/s (CPU NN 層最適)`)
- **核心発見サマリ**: 冒頭に PNG 3 枚埋め込み (trend / drift / pareto)
- **全 Phase 比較表**: D, S, T-4, T-5, T-5e, T-5f, T-5a の eval_mean を 1 表で
- **未検証事項** + **検証完了後に実施すべき TODO** (後述)

### Step 8: Discord 通知 (2 回)

- バッチ実行開始時: 「Phase T-5a 開始、予想 95-105 分、B28→B24→B20→B18 + drift bracket」
- レポート作成完了時: レポート URL + 結果サマリ (歴代更新/B28 確定/OOM境界)

## 検証方法 (End-to-end)

1. **VRAM 実測検証**: step 3 dry-start で B18 の CUDA0 used が 15,200 MiB 前後 (± 300) であれば予測モデル妥当
2. **drift 健全性**: B28_run1 と B28_run2 の eval_mean 差 < 0.15 t/s
3. **OT regex syntax 検証**: 各 dry-start で llama-server ログに `load_tensors: CPU_Mapped model buffer size = XXX MiB` と `offloaded 49/49 layers to GPU` が出力され、CPU 層数が B 数と整合
4. **measurement 品質**: eval 5 run の stdev < 0.03 t/s (T-5f 並) を期待、0.05 超なら再測定
5. **結果の実用性**: 最良条件での生成品質チェック (短い prompt 1 本を手動で eval して日本語応答が正常か)

## 未検証事項 (本 Phase スコープ外)

| 項目 | 候補 Phase | 優先度 | メモ |
|------|-----------|------|------|
| **ビルドフラグ × T-5a 最良 baseline** | T-6 | **高** (本 Phase 後最優先) | P100 で期待値低いが「最後の未探索軸」 |
| **tensor-split 明示で CUDA0 偏重** | T-5a2 | 中 | `-ts 4,1,1,1` で CUDA0 に集中配置 |
| **main-gpu=0/3 × B20** | T-5a3 | 中 | main-gpu 主担当 GPU 変更の影響 |
| **T-5a 最良 × ub plateau 再検証** | T-5a-b | 中 | B20 で ub=384/448/512/640 sweep |
| **threads 精密 sweep × B20** | T-5g | 中 | OT=B20 環境での threads 最適 |
| **ub=256 dip 原因究明 (Nsight)** | T-5f-profile | 低 | profile tool 要準備 |
| **ctx 微細 sweep × T-5a 最良** | T-5a-ctx | 低 | ctx={16k, 24k, 40k, 48k} |
| **KV 量子化 perplexity 定量** | wikitext-2 | 低 | 品質 vs 性能 trade-off |

## 検証完了後に実施すべき TODO

### 短期 (Phase T-5a 完了後すぐ)

1. **Phase T-5a が新記録達成時**: B14-B18 の細粒度スイープ (OOM 境界特定) を Phase T-5a-fine で実施、上限 CPU 層数を確定
2. **Phase T-5a が B28 最適確定時**: ただちに **Phase T-6 ビルドフラグ** へ移行 (B28_32k_ub512 baseline で GGML_CUDA_FORCE_MMQ ON/OFF の 2 条件、DMMV は deprecated のため除外、CC 6.0 固定 + ccache で再ビルド 30-60 分 × 1 回)
3. **drift 不健全時**: session 内 drift 原因深掘り Phase (nvidia-smi dmon + numastat 同期取得)

### 中期

4. Phase T-5a2/3: tensor-split / main-gpu 明示
5. Phase T-5g: threads × OT 最良 sweep
6. Phase T-5a-b: ub plateau × OT 最良

### 長期

7. SMT ON + 2D sweep (BIOS 要変更)
8. KV quant perplexity 定量評価
9. 別モデル knowledge 転移 (Qwen3.5-A3B 等)

## 想定結果シナリオと次アクション

| シナリオ | 確率 | 最良 eval (予測) | 次アクション |
|---------|------|----------------|------------|
| 楽観: 線形外挿 | 25% | B20 = 16.95 t/s (+3.0%) | B14-B18 細粒度へ |
| 中庸: T-5 jump 再現 | 40% | B20 = 16.85 t/s (+2.4%) | B18-B22 細粒度 + T-5a2 |
| 現状維持: 境界 plateau | 25% | B24 ≈ 16.50 t/s (+0.3%) | T-6 ビルドフラグへ |
| 飽和: B28 が最適 | 10% | 全条件 < 16.44 | T-6 ビルドフラグ直行 |

シナリオ 3 以上なら **16.5+ 突破の確率 65%**、シナリオ 4 でも B18 OOM データ + B28 最適性確定で情報価値は保持。

## 本 plan 固有の注意点

1. **B16 は意図的に除外** (CUDA0 予測 used 18,411 MiB で OOM 確実、実施すれば 5 分無駄)。B18 で境界テストすれば十分
2. **OT regex の `[01]` / `[0-5]` 表記**は巡回順序に影響しないため Plan agent 提案のままで OK
3. **split-mode=row は使用禁止** (T-2 で -15〜-22% 悪化確認済)
4. **tensor-split 明示 (`-ts`) は本 Phase で使わない** — 同軸の混乱を避け、OT のみで再配分を測定。T-5a2 以降に分離
5. **レポートタイトルは 50 字以内**、核心発見サマリ冒頭に PNG 3 枚を必ず埋め込み (memory feedback_report_title.md に従う)
