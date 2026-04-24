# Phase T-5a-ts2: B14 × tensor-split で 19+ 突破試行

- **タイトル (レポート用、50 字以内)**: `Phase T-5a-ts2: B14 × tensor-split で 19+ 突破試行` (41 字)
- **対象サーバ**: t120h-p100 (10.1.4.14), P100-PCIE-16GB × 4
- **モデル**: unsloth/Qwen3.5-122B-A10B-GGUF Q4_K_M (48 block)
- **llama.cpp**: `6990e2f1f` (T-1〜T-5a-ts と同一バイナリ、**再ビルド不要**)

---

## Context

Phase T-5a-ts (2026-04-23) で **B16 (CPU 16 層) × `-ts 11,12,13,13` × ub=256 × ctx=32k × thr=40 で eval_mean = 18.417 t/s (5 run stdev 0.004)** を達成し歴代最高を更新した (Phase D 15.030 比 +22.54%)。ただし **19+ t/s には -0.583 t/s 届かず**。以下が判明:

- `-ts` 明示自体に副作用なし (むしろ B18_ts_equal が default 比 +0.155 t/s で +3σ 改善)
- B18 → B16 の 2 層 GPU 戻しで eval raw +0.453 t/s (約 **+0.22 t/s / 層** の感度)
- dry probe 通過で B16 fit 達成 (CUDA0=15,107, CUDA1=14,235, CUDA2=10,185, CUDA3=13,617 MiB)
- session drift が -4.55% に倍増し線形性破綻 (mid 残差 +0.387)、2 次 fit 採用 → 次 Phase は **session 80 分以下** 必須
- 空き VRAM (B16 fit 時): CUDA0=1,164 / CUDA1=2,036 / **CUDA2=6,086** / CUDA3=2,654 MiB

**本プランの狙い**: T-5a-ts report の最優先 TODO (「Phase T-5a-ts2: B14 化 + `-ts` 更調整」) を実施し、CPU 14 層 (layer 2,3 を更に GPU 戻し) + `-ts` で CUDA2 に寄せる配分で **18.85+ t/s、条件次第で 19+ 突破**を狙う。感度 +0.22 t/s/層が維持されれば **+0.4-0.5 t/s 期待値で 18.82-18.92 t/s**、`-ts` 最適化効果で +0.05-0.15 上乗せがあれば 19+ に到達可能。

期待外れ (B14 fit 不能 or eval 低下) の場合も、**fit 境界と CUDA1 VRAM 頭打ち条件**を確定でき次 Phase (B12 試行 / `--main-gpu` 切替) への判断材料となり、情報量は高い。

---

## 目的

1. **B14 OT (CPU 14 層) の fit 可否確定** (dry probe 5-6 件で OOM 境界探索)
2. **B14 × `-ts` 最良配分の特定** (2-3 個の ts 候補を main batch で比較)
3. **歴代 eval 更新 + 可能なら 19+ 突破** (T-5a-ts 18.417 超え、対 19.0 gap 確認)
4. **session ≤80 分** で drift を -0.40 t/s 以内に抑え、線形補正成立させる
5. **B16_ts_skew (11,12,13,13) の cross-session 再現** (T-5a-ts raw 18.417 が session 間で再現するか確認)

---

## 判定基準

| 判定 | 閾値 |
|------|------|
| eval JSON 揃い | 各 5 個、合計 25 個 (5 label) |
| drift 健全 | \|起点 - 終点\| < 0.40 t/s (T-5a-ts 0.818 から半減目標) |
| drift 線形性 | 2-point bracket のため残差指標なし (3 点 mid を取らない割り切り) |
| B14 fit 達成 | main batch で OOM 0 件 |
| 歴代更新 | B14 実測 > 18.417 + 3σ ≈ 18.43 |
| 🎯 19+ 突破 | 実測 or 補正後 > 19.00 |
| OOM 件数 | dry 通過後の main で 0 |

---

## 軸選定 (本 Phase スコープ判断)

| 候補 | 期待 | コスト | 採否 |
|------|------|--------|------|
| **(a) B14 × tensor-split** | **+0.4-0.7 t/s、19+ 突破可能性** | **~75 分** | **採用 (本命)** |
| (b) B16 ts 更細粒度 (CUDA2 更寄せ) | +0.05-0.1 t/s | 60 分 | 保留 (次 Phase) |
| (c) cool-down / session 分割 | drift 軽減のみ、peak 据え置き | 作業変更 | **本 Phase に部分採用** (2-pt bracket, 80 分圧縮) |
| (d) B14 × ub/threads 同時 | 過剰軸、交互作用で結果解釈困難 | 150 分 | 不採用 |
| (e) ビルドフラグ | P100 効果疑、再ビルド要 | 3-5h | 大幅後回し |

(c) は「session 80 分圧縮」として main batch 設計に統合。

---

## 実施方法

### A. dry probe (B14 OOM 境界探索、~10 分)

**OT regex (B14 候補):**

- **OT-a 推奨**: `blk\.(20|2[1-4]|3[1-9])\.ffn_.*_exps\.weight=CPU`
  - CPU 14 層: **20, 21, 22, 23, 24, 31, 32, 33, 34, 35, 36, 37, 38, 39**
  - B16 (`[2-3]|2[0-4]|3[1-9]`) から layer 2, 3 を GPU 戻し (B18→B16 で 0, 1 を戻した連続)
- フォールバック: OT-b `blk\.([2-3]|2[0-4]|3[2-9])\.ffn_.*_exps\.weight=CPU` (layer 0-3, 20-24, 32-39 → 計 13 層なので **B13**、調整版) ← これは要らない。OT-a 一本で進める。

**TS 候補 (合計 49 または 50 比率、B16 best `11,12,13,13` 基準):**

- **TS-1 (本命) `11,11,15,13`** — CUDA2 最大寄せ (+2 分、+~1,600 MiB 相当)、CUDA1 据え置き、合計 50
- **TS-2 `10,11,15,14`** — CUDA0 -1 + CUDA3 +1 で CUDA1 を温存、合計 50
- **TS-3 `11,12,14,13`** — B16 最良の最小差分、CUDA2 のみ +1、合計 50 (fit 可能性最高 = 基準線)
- **TS-4 `10,12,15,13`** — CUDA0 最軽量 + CUDA2 寄せ、合計 50
- **TS-5 `11,10,15,14`** — CUDA1 下げ保険、合計 50

**dry probe 実行順** (既知 fit 近い順で OOM を避けつつ CUDA2 荷重に移行):

| # | OT | TS | 期待 | 役割 |
|---|----|----|------|------|
| D1 | B14 | `11,12,14,13` (TS-3) | **OK 期待** | B16 最小差分、fit 基準線 |
| D2 | B14 | `11,11,15,13` (TS-1) | **OK 期待 (本命)** | CUDA2 最大寄せ |
| D3 | B14 | `10,12,15,13` (TS-4) | OK 期待 | CUDA0 軽量 |
| D4 | B14 | `10,11,15,14` (TS-2) | OK 期待 | CUDA1 温存 |
| D5 | B14 | `11,10,15,14` (TS-5) | 判定用 | CUDA1 最小 |
| D6 (任意) | B14 | `9,11,16,14` | **OOM 境界探索** | CUDA0 下限 / CUDA2 上限 |

dry で 2 個以上 OK → 上位 2 個を main batch の primary/alt に採用。
**全滅 (全 OOM) の場合**: B14 不可と判断し、即時 B13 (layer 20 or 24 または 31 のみ GPU 戻し = 15 層) で 1 件だけ追加 dry → main 縮小実施。

### B. main batch (B14 × ts 評価 + drift bracket、~75 分)

**固定パラメータ (T-5a-ts 最良継承)**: ctx=32768, ub=256, batch=256, KV=q8_0, split-mode=layer, threads=40, numactl -N1 -m1, -ngl 999, flash-attn=1, parallel=1, poll=0

**5 label 構成 (2-point drift bracket)**:

| # | label | OT | TS | 役割 |
|---|-------|----|-----|------|
| 1 | **B18_default_a** | B18 | (default) | drift 起点 / T-5a-ub 18.103 / T-5a-ts 17.964 cross-session 再現 (4 回目) |
| 2 | **B14_ts_primary** | B14 | TS-1 (or dry 最良) | **本命、新記録第一候補** |
| 3 | **B14_ts_alt** | B14 | TS-3 (or dry 次点) | B14 内 ts 感度評価 |
| 4 | **B16_ts_skew** | B16 | `11,12,13,13` | **T-5a-ts peak 18.417 cross-session 再現 (ベンチマーク)** |
| 5 | **B18_default_z** | B18 | (default) | drift 終点 (2-pt linear bracket) |

`B18_default_mid` (3 点 bracket) / `B18_ts_equal` / `B18_ts_skew` / `B16_ts_alt` は既知のため本 Phase スコープ外。

- warmup 2 + eval 5 = 7 run / label × ~90s/run × 5 label ≒ **53 分 (measurement のみ)**
- server 起動・停止オーバーヘッド ~4 分/label × 5 ≒ 20 分 ⇒ 合計 **~73 分**、80 分閾値内。
- drift per-run 推定: T-5a-ts の idx 1-6 線形 (-0.0588) を採用すると起点-終点差 ≈ -0.29 t/s、目標 < 0.40 達成見込み。

**ordering の意図**: 起点 B18 → B14 本命 → B14 alt → B16 control → 終点 B18。drift 補正対象の B18 default を両端に据え、新条件 (B14) と cross-session control (B16) を中央に。

### C. 成果物 (添付)

1. 実装プラン (本ファイルをコピー)
2. dry probe log + dry_logs/ (各条件の stdout + nvidia-smi + server.log)
3. main batch log + startup_logs/
4. summary TSV (全 run の eval/prompt mean±stdev)
5. pivot Markdown (label × 指標)
6. analyze/plot スクリプト
7. PNG: B14 vs B16 vs B18 eval 比較 / drift 2-pt / VRAM used 条件別

---

## Critical Files (再利用元)

| ファイル | 役割 | 変更量 |
|---------|------|--------|
| `report/attachment/2026-04-23_074652_qwen3-122b-c3-phaseT5a-ts/start_phaseT5.sh` | 起動ラッパ (`-ts` env 対応済み) | **変更不要**、本 Phase でもそのまま再利用 |
| `report/attachment/2026-04-23_074652_qwen3-122b-c3-phaseT5a-ts/dry_probe.sh` | dry probe テンプレ | PROBES 配列を B14 × 5-6 件に差し替え |
| `report/attachment/2026-04-23_074652_qwen3-122b-c3-phaseT5a-ts/batch_phaseT5a-ts.sh` | main batch テンプレ | CONDITIONS 配列を 5 label に差し替え、OT_B14 定義追加 |
| `report/attachment/2026-04-23_074652_qwen3-122b-c3-phaseT5a-ts/run_all.sh` | eval 計測ループ | **変更不要** |
| `report/attachment/2026-04-23_074652_qwen3-122b-c3-phaseT5a-ts/measure_phaseT5.sh` | /completion エンドポイント叩き | **変更不要** |
| `report/attachment/2026-04-23_074652_qwen3-122b-c3-phaseT5a-ts/analyze_phaseT5a-ts.py` | TSV/CSV/pivot 生成 | label リスト差し替え、drift は 2-pt linear に変更 (2 次回帰削除) |
| `report/attachment/2026-04-23_074652_qwen3-122b-c3-phaseT5a-ts/plot_phaseT5a-ts.py` | PNG 生成 | 軸ラベル / 条件差し替え |
| `.claude/skills/gpu-server/scripts/lock.sh` | サーバロック取得 | そのまま使用 |
| `.claude/skills/llama-server/scripts/stop.sh` | llama-server 停止 | そのまま使用 |

新規ディレクトリ: `report/attachment/<報告ファイル名>/` (実施時刻で命名)

---

## 実施手順

```bash
# 0. 作業ブランチとロック
cd /home/ubuntu/projects/llm-server-ops
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 1. ディレクトリ作成 + テンプレコピー
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_NAME="${TS}_qwen3-122b-c3-phaseT5a-ts2"
ATT="report/attachment/${REPORT_NAME}"
mkdir -p "$ATT"
cp report/attachment/2026-04-23_074652_qwen3-122b-c3-phaseT5a-ts/{start_phaseT5.sh,run_all.sh,measure_phaseT5.sh,analyze_phaseT5a-ts.py,plot_phaseT5a-ts.py} "$ATT/"
cp -r report/attachment/2026-04-23_074652_qwen3-122b-c3-phaseT5a-ts/prompts "$ATT/"
cp /home/ubuntu/.claude/plans/phase-t-5a-ts-b16-tensor-split-declarative-lecun.md "$ATT/plan.md"

# 2. dry_probe_T5ats2.sh / batch_T5ats2.sh を新規作成 (上の OT_B14 + PROBES / CONDITIONS で)

# 3. Topology 記録
ssh t120h-p100 "nproc && lscpu | grep -E 'Socket|Core|Thread|Model name|NUMA' && numactl -H \
  && nvidia-smi --query-gpu=index,memory.total,memory.used,memory.free --format=csv" > "$ATT/topology.log"

# 4. dry probe (~10 分)
cd "$ATT" && nohup bash dry_probe_T5ats2.sh > dry_probe.log 2>&1
cd -

# 5. dry 結果を確認し primary/alt の TS を確定 (プラン TS-1/TS-3 or dry で判明した最良 2 個)

# 6. main batch (~75 分)
cd "$ATT" && nohup bash batch_T5ats2.sh > batch_T5ats2.log 2>&1 &
# 完了後:
cd -

# 7. 解析・プロット
cd "$ATT" && python3 analyze_phaseT5a-ts2.py && python3 plot_phaseT5a-ts2.py
cd -

# 8. レポート生成 (REPORT.md の規約に従う)
# ファイル名: report/${REPORT_NAME}.md
# 必須セクション: 添付ファイル / 核心発見サマリ (+PNG 埋め込み) / 前提・目的 / 環境情報 /
#                再現方法 / 結果詳細 / 仮説解釈 / 未検証事項 / 検証完了後 TODO / 全 Phase 比較 /
#                参照レポート

# 9. ロック解放
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

---

## 検証方法

1. **fit 健全性**: `startup_logs/*` で `cudaMalloc failed` / `OOM` / `failed to allocate CUDA` が 0 件であること。nvidia-smi の used が 16,384 の **95% 未満**であること。
2. **eval 安定性**: 各 label で eval stdev < 0.02 t/s (T-5a-ts 実測 0.002-0.006 水準の維持)。
3. **drift bracket**: `B18_default_a - B18_default_z` の絶対差 < 0.40 t/s。超過時は線形補正を適用して参考値扱い。
4. **cross-session 再現**: B16_ts_skew が 18.40 ± 0.10 で再現すること (T-5a-ts 18.417 実測)。大幅乖離時は測定系異常を疑い原因調査。
5. **新記録判定**: B14 label の eval_mean > 18.43 t/s で歴代更新、> 19.00 で 19+ 突破。
6. **OOM 全滅 fallback**: dry 全 OOM → 即時 B13 化に軸変更し main 縮小。main で 1 件以上 OOM → 該当 ts を除外して再実行 (session 時間延長は避ける)。

---

## 未検証事項 (レポート本体必須セクション、本 Phase スコープ外)

| 項目 | 次 Phase 候補 |
|------|---------------|
| B12 化 (CPU 10 層) | Phase T-5a-ts3 (B14 fit + 新記録成立時) |
| B14 内 ub 微細 (200/224/288/320) | Phase T-5a-ts2-ub |
| `--main-gpu` 1→2 切替 | Phase T-5a-mg |
| `-ts` 明示効果の cross-session 再現 (T-5a-ts B18_ts_equal +0.155 の真偽) | Phase T-5a-tsR |
| drift 倍増機序 (thermal / memory frag) | dmon 追加で独立調査 |
| 3-point 2 次 fit の overfit 検証 (4-5 点 bracket) | wider bracket Phase |
| ctx=65k × B14 Pareto | Phase T-5a-ts2-ctx |
| ビルドフラグ (MMQ/DMMV/CUBLAS) | Phase T-6 |
| KV 量子化 perplexity 品質評価 | wikitext-2 / JMMLU |
| NUMA 解除 + threads 44-56 | Phase T-7 |

## 検証完了後 TODO (レポート本体必須セクション)

### 短期 (最優先)

1. **結果が > 18.5 なら Phase T-5a-ts3: B12 化** (更 2 層 GPU 戻し、19+ 目指す) を次プランに
2. **結果が < 18.43 なら Phase T-5a-mg: `--main-gpu` 切替** に進路変更 (B16_ts に対して main-gpu=1 or 2 で CUDA0 依存解消)
3. **19+ 達成時は perplexity 評価** (wikitext-2 で Q4_K_M × q8_0 KV の品質劣化確認)
4. **drift < 0.40 達成したら「session 80 分運用ルール」を skill 化** (llama-server skill に記載)

### 中期

5. Phase T-5a-ts2-ub: 本 Phase 最良 × ub ∈ {200,224,288,320} スイープ
6. Phase T-5a-tsR: `-ts` 明示単独効果の cross-session 再現 (B18 default vs B18_ts_equal)
7. 3-point 2 次 fit の妥当性検証 (4-5 点 bracket)

### 長期

8. Phase T-6: ビルドフラグ AB
9. Phase T-7: NUMA 解除 + threads 44-56
10. session 長管理ルール策定 (80 分以下、起動回数上限 6 等)

---

## 全 Phase 比較 (レポート本体必須セクション骨格)

| Phase | 条件 (要点) | eval mean (t/s) | 対 T-5a-ts (18.417) 差 |
|-------|-------------|-----------------|--------------------------|
| D | threads=40, ub=1586, ctx=32k, OT=A36 | 15.030 | -18.39% |
| S | ctx=65k, ub=512, threads=40, A36 | 15.390 | -16.43% |
| T-5 best | B28 × threads=40, ub=1586 | 16.024 | -12.99% |
| T-5e best | B28 × ctx=32k × ub=512 | 16.380 | -11.06% |
| T-5f best | B28 × ub=512 微細 | 16.455 | -10.65% |
| T-5a best | B18 × ub=512 × thr=40 | 18.006 | -2.23% |
| T-5a-ub best | B18 × ub=256 × thr=40 | 18.103 | -1.71% |
| T-5a-thr best | B18 × ub=256 × thr=40 再測定 | 17.988 | -2.33% |
| **T-5a-ts best** | **B16 × `-ts 11,12,13,13`** | **18.417** | **baseline (直前歴代 #1)** |
| **T-5a-ts2 (本 Phase)** | B14 × `-ts TS-1 or TS-3` (予定) | **TBD** | **TBD** |

---

## 想定リスクと回避策

| リスク | 対策 |
|--------|------|
| B14 fit 全滅 (全 ts OOM) | D6 で CUDA0=9 まで振って再確認。不可なら B13 (= 15 層) に軸変更して 1 件だけ main 実施 |
| CUDA1 が B14 時に 92% を超えて eval 低下 | TS-5 (CUDA1=10) を primary に昇格、または CUDA1 比率を下げる ts を追加 |
| drift ≥ 0.40 t/s | ordering 見直し。事後解析で 2-pt linear 補正を適用し参考値扱い |
| B16_ts_skew cross-session が 18.30 を下回る | 測定系異常 / サーバ負荷変動を疑い該当時間帯の topology/nvidia-smi を確認、必要なら再測定 |
| session 80 分超過 | B14_ts_alt を削除し 4 label 構成に圧縮、pivot も簡略化 |
| T-5a-ts で残った 2 次 fit vs linear fit の判定不能 | 本 Phase は 2-pt linear 前提。drift 大きい場合は quadratic は使わず「参考値」として明示のみ |
