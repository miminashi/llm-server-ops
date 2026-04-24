# Phase S-eval-24session 実施計画

## Context

直前レポート [2026-04-21_012929_qwen3-122b-c3-phaseSeval23s.md](../../../projects/llm-server-ops/report/2026-04-21_012929_qwen3-122b-c3-phaseSeval23s.md) の「未検証事項 / 新規項目」★最優先は全て **Phase S-eval-24session** へ集約されている。S23 終了は 02:19、S24 開始は本計画実施時点（02:30 台）で cool time **約 15 分**（通常帯 13-16 分 復帰 or 境界 17-20 分 への境界）、S22/S23 の 2 連続大変動（Δ=−1.533 / +1.289）直後の第 24 セッションで以下 5 軸を同時観測する:

1. **mode_A 優位定着 (S22 以前 14 session A/B 7/7 均衡が S23 で解消、mode_A 8/23=34.8% 単独 1 位) の継続性** — S24 が mode_A 9/24=37.5% か、mode_B 復帰 8/24=33.3% 再均衡か、他 mode 遷移か
2. **ub=1664 中帯 3 連続 stay 可否** — S22/S23 中帯 2 連続（S2→S3 以来 2 例目）、23-session 未観測の 3 連続 stay → 「中帯 stable regime」新類型判定
3. **ub=1586 大変動の symmetric 再現** — S22 Δ=−1.533 / S23 Δ=+1.289 の符号反転大変動連続後、S24 で 14.x 再落下 or 15.1 帯安定の判定
4. **σ_pool 1586 > 1584 逆転 3 session 連続** — S22/S23 で 2 連続、S24 連続なら regime change 確定
5. **Welch 2 ub sig (+1584/+1664/not_sig 1586) subtype 再発** — mode_A ⇔ 2 ub sig の相関仮説検証 (n=1/1 確信度低)

併せて cool time × |Δ_max| zone 線形比 0.16/min を S24 cool time で追観測、pooled 120-run (115+5×3) 統計確定、崩壊頻度 CI 絞り込み。

## 実施手順

### 1. 添付ディレクトリ準備（S23 構造をベースに 24s へ rename）

```bash
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_NAME="${TS}_qwen3-122b-c3-phaseSeval24s"
BASE=/home/ubuntu/projects/llm-server-ops/report
mkdir -p "$BASE/attachment/$REPORT_NAME/startup_logs"
mkdir -p "$BASE/attachment/$REPORT_NAME/prompts"
# S23 ディレクトリからスクリプト & prompt コピー（出力ディレクトリ・ログは含めない）
SRC=$BASE/attachment/2026-04-21_012929_qwen3-122b-c3-phaseSeval23s
cp $SRC/prompts/prompt_1k.txt $BASE/attachment/$REPORT_NAME/prompts/
cp $SRC/measure_phaseI.sh     $BASE/attachment/$REPORT_NAME/
cp $SRC/run_all.sh            $BASE/attachment/$REPORT_NAME/
# バッチ・起動・分析スクリプトは 23s → 24s へ sed 置換してコピー
sed 's/phaseSeval23s/phaseSeval24s/g; s/Seval23s/Seval24s/g; s/S23/S24/g; s/23-session/24-session/g; s/22-session/23-session/g; s/115-run/120-run/g; s/pool vs S23/pool vs S24/g; s/第 22 session/第 23 session/g; s/第 23 session/第 24 session/g' \
  $SRC/batch_phaseSeval23s.sh > $BASE/attachment/$REPORT_NAME/batch_phaseSeval24s.sh
sed 's/phaseSeval23s/phaseSeval24s/g; s/Seval23s/Seval24s/g; s/S23/S24/g' \
  $SRC/start_phaseSeval23s.sh > $BASE/attachment/$REPORT_NAME/start_phaseSeval24s.sh
chmod +x $BASE/attachment/$REPORT_NAME/*.sh
# プランファイル配置
cp /home/ubuntu/.claude/plans/todo-shiny-lark.md $BASE/attachment/$REPORT_NAME/plan.md
```

### 2. analyze_phaseSeval24s.py の生成

S23 版 `analyze_phaseSeval23s.py` を基に:
- `PRIOR_TSVS` に `("S23_phaseSeval23s", SCRIPT_DIR.parent / "2026-04-21_012929_qwen3-122b-c3-phaseSeval23s" / "summary_phaseSeval23s.tsv")` を追加
- `CUR_SESSION_LABEL = "S24_phaseSeval24s"`
- `TAG_PREFIX = "Seval24s_fa1_ctx"`
- `MODE_GROUPS` に `"prev_S23": ["S23_phaseSeval23s"]` 追加
- 全ての `23-session` → `24-session`、`115-run` → `120-run`、`22-session pool` → `23-session pool` 表記を更新
- 出力ファイル名 `summary_phaseSeval24s.tsv` / `phaseSeval24s_stats.csv` / `phaseSeval24s_verdict.txt`

### 3. 実行

```bash
# GPU ロック取得（gpu-server skill 経由）
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 作業ディレクトリへ移動してバッチ実行（3 条件 × (warmup 2 + eval 5)、所要約 45 分）
cd report/attachment/$REPORT_NAME
bash batch_phaseSeval24s.sh > batch_phaseSeval24s.log 2>&1

# 分析（S1-S23 TSV + 本 Phase S24 を合算し 24-session 統計生成）
python3 analyze_phaseSeval24s.py

# llama-server 停止 & GPU ロック解放
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 4. レポート作成

`$BASE/$REPORT_NAME.md` を作成。構造は S23 レポートに倣い:

- **タイトル**: cool time 実測 + 5 軸の実観測結果を踏まえた一行要約
- **実施日時** / **作業種別** / **GPU ロック**
- **添付ファイル** / **参照** / **前提・目的**
- **環境情報** / **セッション間隔**（S24 追加）
- **再現方法**
- **実行結果サマリ**
  1. 本 Phase S24 eval 5-run ピボット
  2. 24 session mean 時系列抜粋
  3. Prior 23-session pool vs S24 Welch t
  4. ピーク ub 順序 24-session 集計（mode 分布）
  5. ub=1664 帯構造 24-session
  6. pooled 120-run 統計
  7. ピーク 1 位 24-session
- **未検証事項**（S23 から継続 + 新規）
- **検証完了後に実施すべき TODO**
- **補足**（Phase S-eval-24session の核心発見サマリ・結論 1-N）

### 5. REPORT.md との整合

S23 で `- [x] Phase S-eval-23session` としたのに倣い、S24 の TODO セクションに `- [x] Phase S-eval-24session — 本 Phase で実施` を含める。ただし作業は `REPORT.md` ルール（添付必須・JST 表記・添付パス規則）に厳守。

## 重要な判断事項

- **cool time 実測**: S23 終了は `phaseSeval23s_verdict.txt` ではなく S23 レポート `2026-04-21_012929_qwen3-122b-c3-phaseSeval23s.md` line 3 記載の 02:19 を基準に、S24 batch 開始時刻との差分を算出し、zone 分類（通常 13-16 分 / 境界 17-20 分 / 逸脱 21+）を記載
- **5 軸の成功条件**: 5 軸いずれの結果（肯定・否定・不定）でも有効なデータ。特に否定結果（regime change 解消 / mode_A 優位後退 / ub=1586 14.x 再崩壊）も important finding として記載
- **GPU ロックの確実性**: gpu-server skill を必ず使用

## 重要ファイル（修正・作成対象）

- 新規作成:
  - `report/<TS>_qwen3-122b-c3-phaseSeval24s.md`（レポート本体）
  - `report/attachment/<同>/batch_phaseSeval24s.sh`
  - `report/attachment/<同>/start_phaseSeval24s.sh`
  - `report/attachment/<同>/run_all.sh`（S23 からコピー）
  - `report/attachment/<同>/measure_phaseI.sh`（S23 からコピー）
  - `report/attachment/<同>/prompts/prompt_1k.txt`（S23 からコピー）
  - `report/attachment/<同>/analyze_phaseSeval24s.py`（S23 版を拡張）
  - `report/attachment/<同>/plan.md`（本計画のコピー）
- 実行中に生成: startup_logs/、out_Seval24s_*、summary_phaseSeval24s.tsv、phaseSeval24s_stats.csv、phaseSeval24s_verdict.txt、batch_phaseSeval24s.log 等

## 検証方法（end-to-end）

1. `batch_phaseSeval24s.log` で 3 条件すべての /health OK + run_all 完走を確認
2. `out_Seval24s_fa1_ctx32768_ub{1584,1586,1664}_1k/eval_run{1..5}.json` の 15 ファイルがすべて存在 & `timings.predicted_per_second` が取得できることを確認
3. `phaseSeval24s_verdict.txt` § 2 で n=24 session の時系列 + range / σ_session が出力されていること
4. § 5 Welch t (prior 23-session pool vs S24) の 3 行が揃うこと
5. § 6 pooled 120-run の n=120 (= 24 × 5) が出ていること
6. 崩壊頻度 § 10 で 3 ub すべて Wilson CI 付きで出力されること
7. レポート本文に上記 7 表 + 未検証事項 + TODO セクションが揃うこと
