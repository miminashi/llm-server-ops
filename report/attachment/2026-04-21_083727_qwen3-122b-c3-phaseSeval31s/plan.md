# Phase S-eval-31session 実施プラン

## Context

直前レポート [2026-04-21_074512_qwen3-122b-c3-phaseSeval30s.md](../../projects/llm-server-ops/report/2026-04-21_074512_qwen3-122b-c3-phaseSeval30s.md) の「新規項目（本 Phase S-eval-30session で判明・発生）」および「検証完了後に実施すべき TODO」の ★最優先項目は、すべて **Phase S-eval-31session (S31)** の実施で同時検証可能である。S30 で **triple collapse 30-session 初観測** + **cool time 通常帯下端外 <13 分 新 sub-zone 初観測** + **σ_pool 1664 1 位奪取** + **ub=1586 崩壊-回復-崩壊 新 pattern** + **ub=1664 下帯 drop 14.215 pool min 更新** + **mode_A → mode_B 隣接 pattern 再現** + **Welch 3 ub 全負方向 sig 30-session 初観測** の 7 大事件が同時観測された。S31 で以下 ★最優先 6 項目を一括検証する:

1. **triple collapse 30-session 初観測 → S31 連続 triple collapse 可否**（2 連続なら「triple collapse phase」確立、部分崩壊 or 全非崩壊なら 1-session 限定現象、<13 分 cool time との相関 trigger 候補切り分け）
2. **cool time 通常帯下端外 <13 分 新 sub-zone → S31 以降の再現頻度**（S31 cool time が <13 分なら 2 例目で相関検証、13+ 分なら S30 単独 event）
3. **σ_pool 1664 1 位奪取後の S31 動向**（1664 stay なら「σ_pool 順序 regime change」確立、1586 復位なら single-event、1584 1 位なら 3 ub cyclic 確定）
4. **ub=1586 崩壊-回復-崩壊 pattern → S31 動向**（再崩壊なら「beat pattern」、回復なら「alternating oscillation regime」、stepwise climb なら recovery-climb pattern）
5. **ub=1664 下帯 drop 14.215 後の S31 動向**（下帯 stay なら下帯 2 連続新類型、中帯 jump なら recovery、上帯 jump なら下→上 big swing、p(下|下)=3/11=27.3% は最低値で stay 確率低い）
6. **mode_A→mode_B 隣接 pattern 再現性検証**（S31 mode_B 継続なら mode_B 2 連続 stable regime 候補、mode_A 復帰なら A 10→11 例 pile-up 継続）

同時に以下の ★高優先項目も更新する:
- Welch「3 ub 全負方向 sig」subtype 再観測 interval 解析
- |t_welch| 最大 30.52 の S31 以降再現（|t|>25 の分布把握）
- ub=1664 σ_pool 拡大 +0.025 の持続性
- pool 差 1586-1584 +0.05 再突破後の収束可否
- within-σ 0.002-0.006 低位 7 連続 → 8 連続可否
- mode_B 復活 9 例目 + interval 漸増 trend の継続判定

これら ★最優先 6 項目 + ★高優先 6 項目を 1 回のバッチ実行（約 37-40 分）で同時検証する。pooled 155-run 統計へ拡張し、31-session range / σ_session / Welch t、mode 分類、崩壊頻度 Wilson 95% CI を更新する。

## 実施内容

### 1. 添付ディレクトリ・スクリプト準備

S30 の attachment を雛形にコピーし、ファイル名・変数名・REMOTE_LOG prefix を `30s → 31s` に置換:

- 新規レポートファイル名を `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得
- `report/attachment/<新レポート名>/` ディレクトリ作成
- 以下スクリプトをコピーし、`phaseSeval30s → phaseSeval31s` / `Seval30s → Seval31s` / `30s → 31s` を一括置換:
  - `start_phaseSeval30s.sh` → `start_phaseSeval31s.sh`
  - `batch_phaseSeval30s.sh` → `batch_phaseSeval31s.sh`
  - `run_all.sh`（変更なしでコピー）
  - `measure_phaseI.sh`（変更なしでコピー）
  - `analyze_phaseSeval30s.py` → `analyze_phaseSeval31s.py`
  - `prompts/prompt_1k.txt`（変更なしでコピー）
- `analyze_phaseSeval31s.py` の `PRIOR_TSVS` リストに S30 エントリを追加:
  ```python
  ("S30_phaseSeval30s",
   SCRIPT_DIR.parent / "2026-04-21_074512_qwen3-122b-c3-phaseSeval30s" / "summary_phaseSeval30s.tsv"),
  ```
- `CUR_SESSION_LABEL` を `"S31_phaseSeval31s"` に更新
- 集計時のラベル「30-session」「pooled 150-run」を「31-session」「pooled 155-run」へ更新（`n` 自動計算で計算ロジックは変更不要のはず）
- `startup_logs/`, `out_Seval31s_*` ディレクトリを作成
- プランファイル自身を `attachment/<新レポート名>/plan.md` にコピー

### 2. GPU ロック取得（t120h-p100）

```bash
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 3. バッチ実行

```bash
cd report/attachment/<新レポート名>
HOST=t120h-p100 bash batch_phaseSeval31s.sh > batch_phaseSeval31s.log 2>&1
```

- ub={1584, 1586, 1664} × warmup 2 run + 1k eval 5 run
- 各条件で `llama-server` 起動 → `/health` 確認 → warmup → eval → `stop.sh` の標準フロー
- 所要時間: 約 37-40 分

### 4. 集計・analyze スクリプト実行

```bash
python3 analyze_phaseSeval31s.py
```

- 31-session verdict
- pooled 155-run 統計（mean / σ_pool / min / max / median / range）
- Welch t（prior 30-session pool vs S31）
- 崩壊頻度（ub=1584/1586/1664）Wilson 95% CI
- mode 分類 31-session
- σ_pool regime change 判定（1586 > 1584 が 10 連続か否か、S30 で 1664 1 位奪取の影響も含む）

### 5. GPU ロック解放

```bash
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 6. レポート作成

ファイル名: `report/<タイムスタンプ>_qwen3-122b-c3-phaseSeval31s.md`

S30 レポートのフォーマットを踏襲し、以下を含める:

- 冒頭タイトル（S31 結果サマリを含む長文タイトル、★最優先 6 項目の検証結果を網羅）
- 添付ファイル・参照リスト（S22/S28/S29/S30 へのリンク）
- 前提・目的（S30 の ★最優先 TODO 群を列挙）
- 判定しきい値・成功条件
- 環境情報・セッション間隔（S30 終了時刻 08:23:59 JST と S31 開始時刻から cool time 算出）
- 再現方法
- 結果（本 Phase eval、Welch t、pooled 155-run、31-session peak order、mode 分類）
- **「未検証事項」セクション**（S30 の該当セクションを基に更新、★最優先 6 項目について S31 結果で `[x]` マーク、新規 ★最優先項目を S32 向けに追加）
- **「検証完了後に実施すべき TODO」セクション**（Phase S-eval-32session 候補 等、新規項目を追加）
- 結論

## 重要な判断基準

- **崩壊判定**: eval_mean < 15.0 t/s（3 ub 共通）
- **ub=1664 帯分類**: 下帯 < 14.80、中帯 14.80-15.20、上帯 > 15.20
- **triple collapse 判定**: 3 ub 同時崩壊
- **cool time zone 分類**: 通常帯 13-16 分、通常帯下端外 sub-zone <13 分、境界帯直前 sub-zone 16-18 分、境界帯 18+ 分
- **σ_pool regime**: 1586 > 1584 で S22-S30 の 9 連続、1664 1 位は S30 初

## 修正対象ファイル（重要パス）

- `/home/ubuntu/projects/llm-server-ops/report/<新レポート名>.md`（新規作成）
- `/home/ubuntu/projects/llm-server-ops/report/attachment/<新レポート名>/`（新規作成、S30 attachment 流用）

## 参照する既存ファイル

- S30 雛形: `report/attachment/2026-04-21_074512_qwen3-122b-c3-phaseSeval30s/`（全スクリプト・プロンプト）
- GPU ロック: `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- llama-server 停止: `.claude/skills/llama-server/scripts/stop.sh`
- プロンプト: S30 `prompts/prompt_1k.txt`（Phase Sbfine3 と同一、6200 bytes、prompt_n=1086 tokens）

## 検証方法（end-to-end）

1. 3 条件すべて起動成功（/health OK）
2. 各条件で eval_tps 5 値取得完了
3. `summary_phaseSeval31s.tsv` に 3 ub × 5 run の 15 行 + warmup 行が記録される
4. `phaseSeval31s_stats.csv` に 31-session 集計行が 3 ub 分出力される
5. `phaseSeval31s_verdict.txt` に verdict / Welch / mode / 崩壊頻度 が記録される
6. pool_n=155（31 session × 5 run）、31-session mode 分類・σ_pool regime の更新確認
7. GPU ロック解放の正常動作

## 想定所要時間

- 準備（スクリプトコピー・編集）: 5 分
- GPU ロック取得: 1 分
- バッチ実行（3 条件 × 約 12 分）: 37-40 分
- analyze 実行: 1 分
- GPU ロック解放: 1 分
- レポート作成: 15-20 分
- **合計**: 約 60-70 分
