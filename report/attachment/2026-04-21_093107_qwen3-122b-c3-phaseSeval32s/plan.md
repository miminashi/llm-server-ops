# Phase S-eval-32session 実施プラン

## Context

直前レポート [2026-04-21_083727_qwen3-122b-c3-phaseSeval31s.md](../../../report/2026-04-21_083727_qwen3-122b-c3-phaseSeval31s.md) の「新規項目（本 Phase S-eval-31session で判明・発生）」および「検証完了後に実施すべき TODO」の ★最優先項目は、すべて **Phase S-eval-32session (S32)** の実施で同時検証可能である。S31 で **triple collapse 2 連続否定 (1-session 限定現象類型確定)** + **cool time 通常帯 13-16 分 sub-zone 復帰 (<13 分 S30 単独 event 確定)** + **ub=1586 alternating 4-session pattern 確立** + **ub=1664 下帯→中帯 jump (50% 崩壊頻度突破)** + **mode_B 連続 2 session (S30→S31) 31-session 初** + **A=B=10/31=32.3% 同率 1 位タイ 31-session 初** + **Welch 全 ub sig 正方向 31-session 初 (S30 全負方向との鏡像パターン)** + **σ_pool 1664 1 位 2 連続確立** + **全 ub σ_pool 縮小 31-session 初** + **within-σ 0.002-0.006 低位 8 連続達成** の 12 大事件が同時観測された。S32 で以下 ★最優先 8 項目を一括検証する:

1. **triple collapse 1-session 限定現象類型確立後の S32 triple collapse 再観測 interval**（30 session ぶり or 短 interval 再現の 2 分岐）
2. **mode_B 2 連続 (S30→S31) 後の S32 動向**（mode_B 3 連続 新類型 / mode_A 復帰 11/32 単独 1 位 / 他 mode で A=B 同率タイ維持 の 3 分岐）
3. **A=B=10/31=32.3% 同率 1 位タイ 31-session 初 → S32 動向**（A 単独 1 位 / B 単独 1 位初 / 同率タイ継続 の 3 分岐）
4. **Welch 全正方向 / 全負方向 鏡像パターン (S30-S31) 後の S32 動向**（全符号統一継続で新 regime / 混合符号で 2-session 限定現象確定）
5. **σ_pool 1664 1 位 2 連続 → S32 3 連続可否**（1664 stay → 3 連続新類型 / 1586 復位で 2-session 限定 / 1584 1 位で cyclic 確定）
6. **ub=1664 崩壊頻度 51.6% → 50% 突破後の定着可否**（45-50% 揺れ戻し / 50-55% 定着 / 55%+ 接近 の 3 分岐）
7. **ub=1586 alternating 4-session pattern (崩壊/回復/崩壊/回復) 継続性**（S32 崩壊 → 5-session alternating 確立 / 回復で 2 連続 normal で alternating break）
8. **ub=1584 5-session pattern (非崩壊 3 + 崩壊 1 + 回復 1) 完成後の S32 動向**（非崩壊継続 / 崩壊で第 2 崩壊、alternating 類似 regime）

同時に以下の ★高優先項目も更新する:
- σ_pool 縮小 direction 底打ち示唆（3 連続縮小後 S31 維持）→ S32 動向（底打ち確定 / 継続縮小 / 拡大反転）
- 3 ub 全 σ_pool 縮小 31-session 初 → S32 再現頻度（縮小 regime 確立 / 単独 event）
- ub=1586 peak 1 位率 45.2% (+1.9pt) 新最大値 → S32 動向
- pool 差 1586-1584 = +0.054 で +0.05 維持 → S32 動向
- Welch「3 ub 全負方向 sig」subtype 再観測 interval（S30 初観測 → S31 正方向 shift、S32 以降での再観測）
- |t_welch| 最大 30.52 の S31 以降再現（S31 6.71 → S32 で |t|>25 再現可否）
- within-σ 0.002-0.006 低位 8 連続 → 9 連続可否（S32 で達成なら regime 継続）

これら ★最優先 8 項目 + ★高優先 7 項目を 1 回のバッチ実行（約 37-40 分）で同時検証する。pooled 160-run 統計へ拡張し、32-session range / σ_session / Welch t、mode 分類、崩壊頻度 Wilson 95% CI を更新する。

## 実施内容

### 1. 添付ディレクトリ・スクリプト準備（完了）

S31 の attachment を雛形にコピーし、ファイル名・変数名・REMOTE_LOG prefix を `31s → 32s` に置換:

- 新規レポート attachment: `report/attachment/2026-04-21_093107_qwen3-122b-c3-phaseSeval32s/`
- 以下スクリプトをコピーし、`phaseSeval31s → phaseSeval32s` / `Seval31s → Seval32s` を一括置換:
  - `start_phaseSeval31s.sh` → `start_phaseSeval32s.sh`
  - `batch_phaseSeval31s.sh` → `batch_phaseSeval32s.sh`
  - `run_all.sh`（変更なしでコピー）
  - `measure_phaseI.sh`（変更なしでコピー）
  - `analyze_phaseSeval31s.py` → `analyze_phaseSeval32s.py`
  - `prompts/prompt_1k.txt`（変更なしでコピー）
- `analyze_phaseSeval32s.py` の `PRIOR_TSVS` リストに S31 エントリを追加:
  ```python
  ("S31_phaseSeval31s",
   SCRIPT_DIR.parent / "2026-04-21_083727_qwen3-122b-c3-phaseSeval31s" / "summary_phaseSeval31s.tsv"),
  ```
- `CUR_SESSION_LABEL` を `"S32_phaseSeval32s"` に更新
- `MODE_GROUPS` に `"prev_S31": ["S31_phaseSeval31s"]` 追加、`"cur_S32": ["S32_phaseSeval32s"]` に更新
- 集計時のラベル「31-session」「pooled 155-run」を「32-session」「pooled 160-run」へ更新
- `startup_logs/`, `out_Seval32s_*` ディレクトリを作成

### 2. GPU ロック取得（t120h-p100）

```bash
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 3. バッチ実行

```bash
cd report/attachment/2026-04-21_093107_qwen3-122b-c3-phaseSeval32s
HOST=t120h-p100 bash batch_phaseSeval32s.sh > batch_phaseSeval32s.log 2>&1
```

- ub={1584, 1586, 1664} × warmup 2 run + 1k eval 5 run
- 各条件で `llama-server` 起動 → `/health` 確認 → warmup → eval → `stop.sh` の標準フロー
- 所要時間: 約 37-40 分

### 4. 集計・analyze スクリプト実行

```bash
python3 analyze_phaseSeval32s.py
```

- 32-session verdict
- pooled 160-run 統計（mean / σ_pool / min / max / median / range）
- Welch t（prior 31-session pool vs S32）
- 崩壊頻度（ub=1584/1586/1664）Wilson 95% CI
- mode 分類 32-session
- σ_pool regime change 判定（1586 > 1584 が 11 連続か否か、1664 1 位 3 連続か否か）

### 5. GPU ロック解放

```bash
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 6. レポート作成

ファイル名: `report/<タイムスタンプ>_qwen3-122b-c3-phaseSeval32s.md`

S31 レポートのフォーマットを踏襲し、以下を含める:

- 冒頭タイトル（S32 結果サマリを含む長文タイトル、★最優先 8 項目の検証結果を網羅）
- 添付ファイル・参照リスト（S22/S28/S29/S30/S31 へのリンク）
- 前提・目的（S31 の ★最優先 TODO 群を列挙）
- 判定しきい値・成功条件
- 環境情報・セッション間隔（S31 終了時刻 09:16:21 JST と S32 開始時刻から cool time 算出）
- 再現方法
- 結果（本 Phase eval、Welch t、pooled 160-run、32-session peak order、mode 分類）
- **「未検証事項」セクション**（S31 の該当セクションを基に更新、★最優先 8 項目について S32 結果で `[x]` マーク、新規 ★最優先項目を S33 向けに追加）
- **「検証完了後に実施すべき TODO」セクション**（Phase S-eval-33session 候補 等、新規項目を追加）
- 結論

## 重要な判断基準

- **崩壊判定**: eval_mean < 15.0 t/s（3 ub 共通）
- **ub=1664 帯分類**: 下帯 < 14.80、中帯 14.80-15.20、上帯 > 15.20
- **triple collapse 判定**: 3 ub 同時崩壊
- **cool time zone 分類**: 通常帯 13-16 分、通常帯下端外 sub-zone <13 分、境界帯直前 sub-zone 16-18 分、境界帯 18+ 分
- **σ_pool regime**: 1586 > 1584 で S22-S31 の 10 連続、1664 1 位は S30-S31 の 2 連続

## 修正対象ファイル（重要パス）

- `/home/ubuntu/projects/llm-server-ops/report/<新レポート名>.md`（新規作成）
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-21_093107_qwen3-122b-c3-phaseSeval32s/`（作成済み、S31 attachment 流用）

## 参照する既存ファイル

- S31 雛形: `report/attachment/2026-04-21_083727_qwen3-122b-c3-phaseSeval31s/`（全スクリプト・プロンプト）
- GPU ロック: `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- llama-server 停止: `.claude/skills/llama-server/scripts/stop.sh`
- プロンプト: S31 `prompts/prompt_1k.txt`（Phase Sbfine3 と同一、6200 bytes、prompt_n=1086 tokens）

## 検証方法（end-to-end）

1. 3 条件すべて起動成功（/health OK）
2. 各条件で eval_tps 5 値取得完了
3. `summary_phaseSeval32s.tsv` に 3 ub × 5 run の 15 行 + warmup 行が記録される
4. `phaseSeval32s_stats.csv` に 32-session 集計行が 3 ub 分出力される
5. `phaseSeval32s_verdict.txt` に verdict / Welch / mode / 崩壊頻度 が記録される
6. pool_n=160（32 session × 5 run）、32-session mode 分類・σ_pool regime の更新確認
7. GPU ロック解放の正常動作

## 想定所要時間

- 準備（スクリプトコピー・編集）: 5 分（完了）
- GPU ロック取得: 1 分
- バッチ実行（3 条件 × 約 12 分）: 37-40 分
- analyze 実行: 1 分
- GPU ロック解放: 1 分
- レポート作成: 15-20 分
- **合計**: 約 60-70 分
