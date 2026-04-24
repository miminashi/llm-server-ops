# Phase S-eval-30session 実施プラン

## Context

直前レポート [2026-04-21_065614_qwen3-122b-c3-phaseSeval29s.md](../../projects/llm-server-ops/report/2026-04-21_065614_qwen3-122b-c3-phaseSeval29s.md) の「新規項目（本 Phase S-eval-29session で判明・発生）」および「検証完了後に実施すべき TODO」の ★最優先項目は、すべて **Phase S-eval-30session (S30)** の実施で同時検証可能である。具体的には以下 5 項目:

1. **ub=1584 非崩壊 3 連続 → S30 4 連続可否**（S27/S28/S29 非崩壊 3 連続達成後の新 regime 方向性確定 — 4 連続なら「高安定 non-崩壊」phase 強化、崩壊なら alternating 破綻後の「3 連続＋1 崩壊」新変形類型）
2. **ub=1586 崩壊後 1-session 回復後の S30 動向**（S22→S23→S24 (13.844→15.133→15.261) pattern 再現可否。S30 15.20-15.30 帯への stepwise climb なら plateau 類型再構築、崩壊なら collapse-recovery-collapse 新 pattern）
3. **ub=1664 3 連続限定現象確定後の S30 動向**（S29 中帯 14.915 復帰後の遷移確率推定。p(中|中)=2/9=22.2% / p(上|中)=4/9=44% / p(下|中)=3/9=33% の 3 分岐判定）
4. **mode_A 10 例新最大値 → S30 mode_A 連続化可否**（過去 mode_A 連続は S1→S2→S3 の 3 連続のみ。S30 mode_A 継続なら 29-session 未観測 event、B/C 等復帰なら mode_A 分散維持）
5. **σ_pool 逆転幅 縮小 direction 確定 (0.006) → S30 動向**（S30 で 0.005 以下なら regime 終結候補 / 0.009 なら alternating 復帰 / 0.012+ なら拡大 rebound の 3 分岐判定）

同時に以下の ★高優先項目も更新する:
- pool 差 1586-1584 +0.05 以下突破後の S30 収束可否（残 +0.035〜+0.045）
- Welch 新 subtype (+1584 sig / not_sig 1586/1664) 再現頻度
- within-σ 0.002-0.007 低位 6 session 連続 → 7 連続可否
- cool time zone 線形モデルの fit ratio 追検証（S29 14'34"×0.410=0.84x）

これら ★最優先 5 項目 + ★高優先項目を 1 回のバッチ実行（約 37-40 分）で同時検証する。pooled 150-run 統計へ拡張、30-session range / σ_session / Welch t、mode 分類、崩壊頻度 Wilson 95% CI を更新する。

## 実施内容

### 1. 添付ディレクトリ・スクリプト準備

S29 の attachment を雛形にコピーし、ファイル名・変数名・REMOTE_LOG prefix を `29s → 30s` に置換:

- 新規レポートファイル名を `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得
- `report/attachment/<新レポート名>/` ディレクトリ作成
- 以下 5 スクリプトをコピーし、`phaseSeval29s → phaseSeval30s` / `Seval29s → Seval30s` / `29s → 30s` を一括置換:
  - `start_phaseSeval29s.sh` → `start_phaseSeval30s.sh`
  - `batch_phaseSeval29s.sh` → `batch_phaseSeval30s.sh`
  - `run_all.sh`（変更なしでコピー）
  - `measure_phaseI.sh`（変更なしでコピー）
  - `analyze_phaseSeval29s.py` → `analyze_phaseSeval30s.py`
  - `prompts/prompt_1k.txt`（変更なしでコピー）
- `analyze_phaseSeval30s.py` の `PRIOR_TSVS` リストに S29 エントリを追加:
  ```python
  ("S29_phaseSeval29s",
   SCRIPT_DIR.parent / "2026-04-21_065614_qwen3-122b-c3-phaseSeval29s" / "summary_phaseSeval29s.tsv"),
  ```
- `CUR_SESSION_LABEL` を `"S30_phaseSeval30s"` に更新
- 集計時のラベル「29-session」「pooled 145-run」を「30-session」「pooled 150-run」へ更新（出力文言のみ、計算ロジックは `n` 自動計算で変更不要のはず）
- `startup_logs/`, `out_Seval30s_*` ディレクトリを作成
- プランファイル自身を `attachment/<新レポート名>/plan.md` にコピー

### 2. GPU ロック取得（t120h-p100）

```bash
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 3. バッチ実行

```bash
cd report/attachment/<新レポート名>
HOST=t120h-p100 bash batch_phaseSeval30s.sh > batch_phaseSeval30s.log 2>&1
```

- ub={1584, 1586, 1664} × warmup 2 run + 1k eval 5 run
- 各条件で `llama-server` 起動 → `/health` 確認 → warmup → eval → `stop.sh` の標準フロー
- 所要時間: 約 37-40 分

### 4. 集計・analyze スクリプト実行

```bash
python3 analyze_phaseSeval30s.py
```

- 30-session verdict
- pooled 150-run 統計（mean / σ_pool / min / max / median / range）
- Welch t（prior 29-session pool vs S30）
- 崩壊頻度（ub=1584/1586/1664）Wilson 95% CI
- mode 分類 30-session
- σ_pool regime change 判定（1586 > 1584 が 9 連続か否か）

### 5. GPU ロック解放

```bash
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 6. レポート作成

ファイル名: `report/<タイムスタンプ>_qwen3-122b-c3-phaseSeval30s.md`

S29 レポートのフォーマットを踏襲し、以下を含める:

- 冒頭タイトル（S30 結果サマリを含む長文タイトル、★最優先 5 項目の検証結果を網羅）
- 添付ファイル・参照リスト（S22/S28/S29 へのリンク）
- 前提・目的（S29 の ★最優先 TODO 群を列挙）
- 判定しきい値・成功条件
- 環境情報・セッション間隔（S29 終了時刻と S30 開始時刻から cool time 算出）
- 再現方法
- 結果（本 Phase eval、Welch t、pooled 150-run、30-session peak order、mode 分類）
- **「未検証事項」セクション**（S29 の該当セクションを基に更新、★最優先の 5 項目について S30 結果で `[x]` マーク、新規 ★最優先項目を S31 向けに追加）
- **「検証完了後に実施すべき TODO」セクション**（Phase S-eval-31session 候補 等、新規項目を追加）
- 結論

## 重要な判断基準

- **崩壊判定**: eval_mean < 15.0 t/s（3 ub 共通）
- **ub=1664 帯分類**: 下帯 < 14.80、中帯 14.80-15.20、上帯 > 15.20
- **cool time zone 分類**: 通常帯 13-16 分、境界帯直前 sub-zone 16-18 分、境界帯 18+ 分
- **σ_pool regime**: 1586 > 1584 で 9 連続（S22-S30）

## 修正対象ファイル（重要パス）

- `/home/ubuntu/projects/llm-server-ops/report/<新レポート名>.md`（新規作成）
- `/home/ubuntu/projects/llm-server-ops/report/attachment/<新レポート名>/`（新規作成、S29 attachment 流用）

## 参照する既存ファイル

- S29 雛形: `report/attachment/2026-04-21_065614_qwen3-122b-c3-phaseSeval29s/`（全スクリプト・プロンプト）
- GPU ロック: `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- llama-server 停止: `.claude/skills/llama-server/scripts/stop.sh`
- プロンプト: S29 `prompts/prompt_1k.txt`（Phase Sbfine3 と同一、6200 bytes、prompt_n=1086 tokens）

## 検証方法（end-to-end）

1. 3 条件すべて起動成功（/health OK）
2. 各条件で eval_tps 5 値取得完了
3. `summary_phaseSeval30s.tsv` に 3 ub × 5 run の 15 行 + warmup 行が記録される
4. `phaseSeval30s_stats.csv` に 30-session 集計行が 3 ub 分出力される
5. `phaseSeval30s_verdict.txt` に verdict / Welch / mode / 崩壊頻度 が記録される
6. pool_n=150（30 session × 5 run）、30-session mode 分類・σ_pool regime の更新確認
7. GPU ロック解放の正常動作

## 想定所要時間

- 準備（スクリプトコピー・編集）: 5 分
- GPU ロック取得: 1 分
- バッチ実行（3 条件 × 約 12 分）: 37-40 分
- analyze 実行: 1 分
- GPU ロック解放: 1 分
- レポート作成: 15-20 分
- **合計**: 約 60-70 分
