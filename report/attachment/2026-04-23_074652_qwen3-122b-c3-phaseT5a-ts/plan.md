# Phase T-5a-ts: tensor-split で B16 化、19+ t/s 突破試行

## Context

**なぜ本 Phase を実施するか**:

直前 Phase T-5a-thr (2026-04-23 早朝) で threads 軸単独では T-5a-ub baseline (eval 18.103 t/s) を更新できず、threads=40 で確定した。歴代最高 18.103 t/s は **B18 × ub=256 × ctx=32k × threads=40 × KV q8_0 × split-mode=layer × flash-attn=1** で達成済。

T-5a OT 再配分 phase (B28→B24→B20→B18) で「CPU 層 4 削減で eval +0.7-0.9 t/s」の強い単調傾向が観測されたが、**B16 化はデフォルト配分で CUDA0 -1,454 MiB 不足で OOM 確実** (dry-start 予測) のため未実施。一方、CUDA0 が 91.8% 飽和 (空き 1,330 MiB) に対し **CUDA1/2/3 は空き 2,500-6,138 MiB と余裕** がある。

**仮説**: `--tensor-split` (`-ts`) で GPU 層配分を CUDA0 → CUDA1/2/3 へ寄せれば、B16 (CPU 16 層) が OOM なしで fit 可能。OT 削減傾向の延長で **eval +0.5-0.7 t/s 期待 (≒ 18.6-18.8 t/s、上振れで 19+ t/s 突破)**。

**意図する成果**:
1. (上振れ) B16 で eval 19+ t/s 突破、歴代最高更新
2. (中位) B16 fit 達成 + eval 18.20+ で新記録、ただし 19+ 未達
3. (最低保証) `-ts` 明示の純効果定量化 + B16 fit 可否の物理境界確定 + B18 cross-session 再現値 3 回目取得

これらは新記録未達でも次 4 Phase の意思決定に直接効く。

## 重要な前提訂正 (既存レポートの誤記)

T-5a-thr 本文「CPU 14 層: 0-3, 24, 31-39」は誤記。**正しい regex `blk\.([0-3]|2[0-4]|3[1-9])` は CPU 18 層 (0-3, 20-24, 31-39) にマッチ**。"B18" の数字の根拠は 18 層。本 Phase 全条件で 18 層 = baseline と扱う。

## 軸選定理由

| 候補 | 期待 | 時間 | 採否 |
|------|------|------|------|
| **(a) tensor-split で B16 化** | **+0.5-0.7 t/s、19+ 突破可能性** | **~110 分** | **採用** |
| (b) ub=200/224/288/320 微細スイープ (T-5a-ub2) | +0.05-0.1 t/s | 80 分 | 次 Phase |
| (c) ctx=65k × ub=256 | eval 通常劣化、Pareto 拡張 | 80 分 | 後回し |
| (d) 2 次回帰 drift 補正実装 | データ再解析のみ、新測定不要 | 30 分 | 統合 (本 Phase の 3 点 bracket で実装) |
| (e) ビルドフラグ (T-6) | P100 効果疑、再ビルド要 | 3-5h | 大幅後回し |

**B14 は本 Phase スコープから除外**: B16 が `-ts` で fit できない / fit しても eval 悪化なら B14 は無意味。B16 が成功なら B14 は ts 比率の更なる調整が必要で「同一 ts 比率での連続外挿」ができず、Phase 内連続検証の前提が崩れる。**B16 まで詰めて結果を見て B14 phase をプランニングするのが情報量効率最大**。

## 設計

### dry probe フェーズ (5 件、~8 分)

`-ts` × OT の OOM 境界を素早く把握。各 75s 程度。

| # | OT_TAG | -ts | 狙い |
|---|--------|-----|------|
| D1 | B18 | (default = 未指定) | 既知 baseline で `start_phaseT5.sh + --tensor-split 対応` の sanity check |
| D2 | B18 | `15,11,10,13` | **default 等価明示** (実測 used 比)。`-ts` 明示自体に副作用がないかの control |
| D3 | B18 | `13,11,12,13` | **CUDA0 軽減比** (CUDA0 -2GB を CUDA2 へ寄せ) |
| D4 | **B16** | `13,11,12,13` | B16 第一候補 |
| D5 | **B16** | `11,12,13,13` | B16 第二候補 (CUDA0 更削減) |

OOM/通過判定: 既存 `start_phaseT5.sh` の判定パターン (`cudaMalloc failed: out of memory`, `failed to allocate CUDA[0-9] buffer`, `graph_reserve: failed to allocate`, `failed to allocate KV`) で自動検出。通過時は `nvidia-smi --query-gpu=memory.used,memory.free --format=csv` で各 GPU の実 free MiB を記録。

**dry probe スキップ条件**: D2 (default 等価) で eval 影響の早期 sanity だけ実施し、D3-D5 は OOM 通過確認のみ (eval 計測なし)。

### B16 用 OT regex 設計

B18 = 18 層 (0-3, 20-24, 31-39) から 2 層を GPU に戻す。

**採用案: layer 0, 1 を GPU 戻し → CPU 16 層 (2-3, 20-24, 31-39)**:

```
blk\.([2-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU
```

理由: layer 0/1 は通常 CUDA0 に round-robin される最若番だが、`-ts` で CUDA0 を絞ることで CUDA1/2 に流れ、配置の予測性が高い。1 expert layer ≈ 1,392 MiB (Q4_K_M expert weight サイズ) は層位置に依らず一定 (T-5a 報告値)、よって "small layer か large layer か" の選択は eval 影響に効かない。

### main batch 設計 (7 label、~75 min)

| # | label | OT | -ts | 役割 | 想定時間 |
|---|-------|-----|-----|------|---------|
| 1 | **B18_default_a** | B18 | (未指定) | **drift 起点・T-5a-ub 18.103 cross-session 再現 (3 回目)** | 9 min |
| 2 | B18_ts_equal | B18 | `15,11,10,13` | **`-ts` 明示の副作用 control** (default 等価比) | 9 min |
| 3 | B18_ts_skew | B18 | `13,11,12,13` | **`-ts` 純効果** (CUDA0 -2GB) | 9 min |
| 4 | **B16_ts_skew** | B16 | dry probe 通過の最良 | **本 Phase 本命、新記録第一候補** | 11 min |
| 5 | B16_ts_alt | B16 | dry probe 通過の次善 | B16 内 ts 感度・再現性 | 11 min |
| 6 | B18_default_mid | B18 | (未指定) | **drift 線形性中央点** (3 点 bracket) | 9 min |
| 7 | **B18_default_z** | B18 | (未指定) | **drift 終点** | 9 min |

合計 67 min + warmup/stop overhead 8 min ≈ **75 min** (T-5a-thr の 110 min より大幅短縮、drift 線形性回復見込み)。

dry probe で B16 全滅 (D4, D5 とも OOM) 時の **フォールバック**: label 4, 5 を B18 + 別 ts 比 (例 `11,12,13,13` と `12,12,12,13`) に置換。-ts 効果の精密化 phase に転換。

### drift 補正手法

**3 点 bracket (起点 #1 + 中央 #6 + 終点 #7) で線形 fit + 2 次回帰補助検証**:

- 線形 fit: per_run drift = (B18_default_z - B18_default_a) / 6
- 2 次回帰: 3 点で 2 次多項式 fit、線形 R² < 0.95 のときのみ採用 (hybrid 方式)
- 中央点 (run_index 6) の線形予測残差 < 0.05 t/s なら線形性 OK、超過なら 2 次採用

T-5a-thr の教訓「session 110 分超で非線形」は本 Phase の 75 min 設計で回避見込み。

## 判定基準

| 判定 | 閾値 |
|------|------|
| **eval JSON 揃い** | 各 condition 5 個、合計 35 個 |
| **drift 健全** | \|B18_default_a − B18_default_z\| < 0.30 t/s (T-5a-thr の 0.439 を教訓に厳格化) |
| **drift 線形性** | B18_default_mid 残差 < 0.05 t/s |
| **`-ts` 副作用なし** | B18_ts_equal が B18_default_a の ±0.10 t/s 以内 |
| **B16 fit 達成** | B16_ts_skew が main batch で OOM なし |
| **新記録更新** | いずれかの label で eval_mean > 18.103 + 3σ ≈ **18.20** |
| **19+ 突破** | 補正後 > 19.00 (本 Phase 主目標) |
| **OOM 件数** | dry probe 通過した条件の main batch 中 OOM = 0 |

### 撤退基準 (Phase 中で動的判定)

| 兆候 | 対応 |
|------|------|
| B18_ts_equal が B18_default_a の **-0.30 t/s 超低下** | `-ts` 明示自体に副作用あり、B16 試行は中止し B18_z で session 締め |
| B18_ts_skew が **-0.50 t/s 超低下** | CUDA0 偏重崩しの kernel 効率低下が確定、B16 スキップして session 締め |
| B16_ts_skew が main で OOM | B16 dry 結果と差異あり、ts 比率を更に CUDA0 削減方向で 1 回再試行 |
| dry probe で B16 全滅 (D4, D5 とも OOM) | label 4, 5 を B18 + 別 ts 比に置換 |
| nvidia-smi temp > 80°C | 各 label 間に 30s wait 追加 |

## 実装変更点

### 編集対象ファイル (新 Phase 用に複製)

新規 attachment ディレクトリ作成 + 既存スクリプト複製 + 1 行修正:

```bash
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
mkdir -p report/attachment/${TS}_qwen3-122b-c3-phaseT5a-ts/
cd report/attachment/${TS}_qwen3-122b-c3-phaseT5a-ts/
cp ../2026-04-23_053125_qwen3-122b-c3-phaseT5a-thr/start_phaseT5.sh .
cp ../2026-04-23_053125_qwen3-122b-c3-phaseT5a-thr/run_all.sh .
cp ../2026-04-23_053125_qwen3-122b-c3-phaseT5a-thr/measure_phaseT5.sh .
cp -r ../2026-04-23_053125_qwen3-122b-c3-phaseT5a-thr/prompts .
```

### `start_phaseT5.sh` 改修 (1 行追加)

`-ngl 999 -ot '${OT_REGEX}'` 行を以下に変更:

```bash
-ngl 999 -ot '${OT_REGEX}' ${TS:+--tensor-split ${TS}}
```

`TS` 環境変数が未設定なら `-ts` は付与されず default 挙動 (T-5a-ub と同一)。設定時のみ `--tensor-split <値>` が追加される。

### 新規スクリプト

- `dry_probe.sh`: D1-D5 を順次起動・nvidia-smi 記録・stop。出力 `dry_probe_<TAG>.log`、各条件 75s。
- `batch_phaseT5a-ts.sh`: T-5a-thr の `batch_phaseT5a-thr.sh` を複製し、CONDITIONS を本 Phase の 7 label (LABEL#OT_TAG#OT_REGEX#TS) 形式で再定義。
- `analyze_phaseT5a-ts.py`: T-5a-thr の解析スクリプトを複製し、3 点 bracket での線形/2 次 hybrid drift 補正に対応。
- `plot_phaseT5a-ts.py`: ts ratio × eval、B18 vs B16、drift bracket の 3 PNG。

### Critical files for implementation

- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-23_053125_qwen3-122b-c3-phaseT5a-thr/start_phaseT5.sh` — 起動スクリプトの改修元
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-23_053125_qwen3-122b-c3-phaseT5a-thr/batch_phaseT5a-thr.sh` — バッチスクリプト改修元
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-23_053125_qwen3-122b-c3-phaseT5a-thr/analyze_phaseT5a-thr.py` — 解析スクリプト改修元 (3 点 bracket 対応追加)
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-23_053125_qwen3-122b-c3-phaseT5a-thr/plot_phaseT5a-thr.py` — プロットスクリプト改修元
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/lock.sh` — GPU サーバロック取得 (必須)
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh` — 各 label 間で実行

## 時間見積もり

| フェーズ | 時間 |
|---------|------|
| 準備 (attachment dir、scripts 複製・改修、lock 取得) | 7 min |
| dry probe (5 件 × 75s + 解析) | 9 min |
| main batch (7 label) | 75 min |
| 解析 + plot + pivot 生成 | 12 min |
| report.md ドラフト + 添付整理 | 15 min |
| **合計** | **約 118 分** |

main batch の **session 内測定時間は 75 分**で、T-5a-thr の 110 分から大幅短縮。drift 非線形化リスク回避を優先。

## 検証 (実行手順サマリ)

1. `bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100`
2. attachment ディレクトリ作成 + scripts 複製 + `start_phaseT5.sh` 1 行改修
3. topology 記録: `ssh t120h-p100 "nproc && lscpu | grep -E 'Socket|Core|Thread|Model name|NUMA' && numactl -H && nvidia-smi --query-gpu=index,memory.total,memory.used,memory.free --format=csv" > topology.log`
4. `nohup bash dry_probe.sh > dry_probe.log 2>&1` (~9 分、完了後 OOM/通過の集計)
5. dry probe 結果に基づき `batch_phaseT5a-ts.sh` の B16 ts 比率を確定 (D4/D5 のうち通過した最良 + 次善)
6. `nohup bash batch_phaseT5a-ts.sh > batch_phaseT5a-ts.log 2>&1` (~75 分)
7. `python3 analyze_phaseT5a-ts.py && python3 plot_phaseT5a-ts.py`
8. `bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100`
9. report.md 作成 (タイトル: "Phase T-5a-ts: tensor-split で B16 化試行" など 50 字以内)、未検証事項・検証完了後 TODO・全 Phase 比較表を必須記載

### 健全性チェック (実行中・実行後)

- 各 label 起動直後に `ssh t120h-p100 "grep -E 'CUDA[0-9]|sched_reserve|llama_kv|tensor.split' /tmp/llama-server_phaseT5_*.log | head -40"` で配置確認
- 5 run の eval stdev > 0.05 t/s なら不安定、warmup 追加検討
- 全 label 完了後、3 点 bracket で drift 線形性 R² と 2 次 fit を比較し、補正手法を選択

## 全 Phase 比較 (本 Phase で更新する基準値)

| Phase | 条件 | eval (t/s) |
|-------|------|-----------|
| D | threads=40, ub=1586, ctx=32k, OT=A36 | 15.030 |
| S | ctx=65k, ub=512, threads=40, A36 | 15.390 |
| T-4 | B32 × threads=40 | 15.494 |
| T-5 | B28 × ub=1586 | 16.024 |
| T-5e | B28 × ctx=32k × ub=512 | 16.380 |
| T-5f | B28 × ub=512 微細 | 16.455 |
| T-5a | B18 × ub=512 × thr=40 | 18.006 |
| **T-5a-ub** | **B18 × ub=256 × thr=40 (歴代 #1)** | **18.103** |
| T-5a-thr | B18 × ub=256 × thr=40 (本日早朝、再測定) | 17.988 |
| **T-5a-ts (本 Phase 目標)** | **B16 × ub=256 × thr=40 + -ts** | **目標: 18.6-19.5** |

## 未検証事項 (本 Phase スコープ外、後続 Phase 候補)

| 項目 | 候補 Phase | 優先度 | 理由・期待 |
|------|-----------|-------|-----------|
| **B14 化** (`-ts` 更調整 + CPU 4 層戻し) | Phase T-5a-ts2 | **本 Phase で B16 が成功した場合の最優先** | +0.3-0.5 t/s 期待 |
| **`--main-gpu` 切替** (CUDA0 → CUDA1/2 主担当) | Phase T-5a-mg | 中 | tensor-split 配分判明後の更最適化 |
| **本 Phase 最良 OT/ts での ub 微細** | Phase T-5a-ub2 | 中 | 局所最適化、+0.05-0.1 t/s |
| **ctx=65k × ub=256 × ts** | Phase T-5a-ctx | 低 | 長コンテキスト Pareto 拡張 |
| **ビルドフラグ AB** (FORCE_MMQ/DMMV) | Phase T-6 | 低 | P100 CC 6.0 効果疑、最後の軸 |
| **NUMA 解除 + threads=44-56** | Phase T-7 | 低 | drift 機序解明後 |
| **KV 量子化 perplexity 評価** | wikitext-2 / JMMLU | 低 | 18+ 構成の品質保証 |
