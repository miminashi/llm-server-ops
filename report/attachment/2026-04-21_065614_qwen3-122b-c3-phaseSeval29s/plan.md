# Phase S-eval-29session 実施プラン

## Context

直前レポート [2026-04-21_060329_qwen3-122b-c3-phaseSeval28s.md](../../projects/llm-server-ops/report/2026-04-21_060329_qwen3-122b-c3-phaseSeval28s.md) の「新規項目（本 Phase S-eval-28session で判明・発生）」および「検証完了後に実施すべき TODO」の ★最優先項目は、すべて **Phase S-eval-29session** の実施で同時検証可能である。具体的には以下 5 項目:

1. **ub=1584 非崩壊 2 連続 → S29 3 連続可否**（cycle BREAK 後の next regime 判定）
2. **ub=1586 再崩壊 14.869 後の S29 回復 or 連続崩壊**（plateau → collapse → recovery パターン検証）
3. **ub=1664 上帯 stay 3 連続 → S29 4 連続可否**（「上帯 stable regime」強化判定）
4. **mode_C 連続化可否 + C/E 同率 3 位タイ解消検証**（新階層 A>B>C=E>D の stability 判定）
5. **σ_pool 逆転幅 alternating 候補 S25-S28 (0.009/0.012/0.009/0.012) → S29 0.009 予測**

これら 5 つの ★最優先項目をすべて 1 回のバッチ実行（約 37-40 分）で同時検証する。pooled 145-run 統計へ拡張、29-session range / σ_session / Welch t、mode 分類、崩壊頻度 Wilson 95% CI を更新する。

## 実施内容

### 1. 添付ディレクトリ・スクリプト準備

S28 の attachment を雛形にコピーし、ファイル名・変数名・REMOTE_LOG prefix を `28s → 29s` に置換:

- 新規レポートファイル名を `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得
- `report/attachment/<新レポート名>/` ディレクトリ作成
- 以下 5 スクリプトをコピーし、`phaseSeval28s → phaseSeval29s` / `Seval28s → Seval29s` / `28s → 29s` を一括置換:
  - `start_phaseSeval28s.sh` → `start_phaseSeval29s.sh`
  - `batch_phaseSeval28s.sh` → `batch_phaseSeval29s.sh`
  - `run_all.sh`（変更なしでコピー）
  - `measure_phaseI.sh`（変更なしでコピー）
  - `analyze_phaseSeval28s.py` → `analyze_phaseSeval29s.py`
  - `prompts/prompt_1k.txt`（変更なしでコピー）
- `analyze_phaseSeval29s.py` の `PRIOR_TSVS` リストに S28 エントリを追加:
  ```python
  ("S28_phaseSeval28s",
   SCRIPT_DIR.parent / "2026-04-21_060329_qwen3-122b-c3-phaseSeval28s" / "summary_phaseSeval28s.tsv"),
  ```
- 集計時のラベル「27-session」「pooled 140-run」を「28-session」「pooled 145-run」へ更新（出力文言のみ、計算ロジックは `n` 自動計算で変更不要のはず）
- `startup_logs/`, `out_Seval29s_*` ディレクトリを作成

### 2. GPU ロック取得（t120h-p100）

```bash
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 3. バッチ実行

```bash
cd report/attachment/<新レポート名>
HOST=t120h-p100 bash batch_phaseSeval29s.sh > batch_phaseSeval29s.log 2>&1
```

- ub={1584, 1586, 1664} × warmup 2 run + 1k eval 5 run
- 各条件で `llama-server` 起動 → `/health` 確認 → warmup → eval → `stop.sh` の標準フロー
- 所要時間: 約 37-40 分

### 4. 集計・analyze スクリプト実行

```bash
python3 analyze_phaseSeval29s.py
```

- 29-session verdict
- pooled 145-run 統計（mean / σ_pool / min / max / median / range）
- Welch t（prior 28-session pool vs S29）
- 崩壊頻度（ub=1584/1586/1664）Wilson 95% CI
- mode 分類 29-session
- σ_pool regime change 判定（1586 > 1584 が 8 連続か否か）

### 5. GPU ロック解放

```bash
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 6. レポート作成

ファイル名: `report/<タイムスタンプ>_qwen3-122b-c3-phaseSeval29s.md`

S28 レポートのフォーマットを踏襲し、以下を含める:

- 冒頭タイトル（S29 結果サマリを含む長文タイトル、★最優先 5 項目の検証結果を網羅）
- 添付ファイル・参照リスト（S27/S28 へのリンク）
- 前提・目的（S28 の ★最優先 TODO 群を列挙）
- 判定しきい値・成功条件
- 環境情報・セッション間隔（S28 終了時刻と S29 開始時刻から cool time 算出）
- 再現方法
- 結果（本 Phase eval、Welch t、pooled 145-run、29-session peak order、mode 分類）
- **「未検証事項」セクション**（S28 の該当セクションを基に更新、★最優先の 5 項目について S29 結果で `[x]` マーク、新規 ★最優先項目を S30 向けに追加）
- **「検証完了後に実施すべき TODO」セクション**（Phase S-eval-30session 候補 等、新規項目を追加）
- 結論

## 重要な判断基準

- **崩壊判定**: eval_mean < 15.0 t/s（3 ub 共通）
- **ub=1664 帯分類**: 下帯 < 14.80、中帯 14.80-15.20、上帯 > 15.20
- **cool time zone 分類**: 通常帯 13-16 分、境界帯直前 sub-zone 16-18 分、境界帯 18+ 分

## 修正対象ファイル（重要パス）

- `/home/ubuntu/projects/llm-server-ops/report/<新レポート名>.md`（新規作成）
- `/home/ubuntu/projects/llm-server-ops/report/attachment/<新レポート名>/`（新規作成、S28 attachment 流用）

## 参照する既存ファイル

- S28 雛形: `report/attachment/2026-04-21_060329_qwen3-122b-c3-phaseSeval28s/`（全スクリプト・プロンプト）
- GPU ロック: `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- llama-server 停止: `.claude/skills/llama-server/scripts/stop.sh`
- プロンプト: S28 `prompts/prompt_1k.txt`（Phase Sbfine3 と同一、6200 bytes、prompt_n=1086 tokens）

## 検証方法（end-to-end）

1. 3 条件すべて起動成功（/health OK）
2. 各条件で eval_tps 5 値取得完了
3. `summary_phaseSeval29s.tsv` に 3 ub × 5 run の 15 行 + warmup 行が記録される
4. `phaseSeval29s_stats.csv` に 29-session 集計行が 3 ub 分出力される
5. `phaseSeval29s_verdict.txt` に verdict / Welch / mode / 崩壊頻度 が記録される
6. pool_n=145（29 session × 5 run）、29-session mode 分類・σ_pool regime の更新確認
7. GPU ロック解放の正常動作

## 想定所要時間

- 準備（スクリプトコピー・編集）: 5 分
- GPU ロック取得: 1 分
- バッチ実行（3 条件 × 約 12 分）: 37-40 分
- analyze 実行: 1 分
- GPU ロック解放: 1 分
- レポート作成: 15-20 分
- **合計**: 約 60-70 分
