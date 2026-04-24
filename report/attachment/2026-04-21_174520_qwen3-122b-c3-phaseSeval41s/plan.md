# Phase S-eval-41session 実施計画

## Context

直前レポート `report/2026-04-21_164936_qwen3-122b-c3-phaseSeval40s.md`（S40）の「未検証事項」★最優先項目は、**同条件で第 41 セッション (S41) を 1 回実行すれば 12+ 個を一括検証できる**構造。S40 で initial 化された多数の regime 現象を S41 で連続/終了判定する。主検証対象 (S40「新規項目★最優先」):

- **mode_B 単独 1 位 2 連続 initial** → S41 3 連続 or A/他 mode（40-session 0 例の連続 3）
- **ub=1586 回復 6 連続 initial** → S41 7 連続 or 崩壊（0 例の 7 連続）
- **ub=1586 peak 1 位 2 連続 initial** → S41 3 連続 or 喪失（19/40=47.5% 史上最高）
- **mode_A 外 11 session 最長** → S41 12 連続外 or A 復帰
- **ub=1664 |Δ_max| 担当 5 連続 initial** → S41 6 連続可否
- **ub=1664 単独崩壊 2 連続 initial** → S41 3 連続 or 離脱（累計 14/40=35.0%）
- **Welch (+/+/-) 2 連続 initial** → S41 3 連続 or shift（11 subtype 11-session 連続記録延長候補）
- **σ_pool 1664 1 位 3 連続 initial** → S41 4 連続 or 奪還
- **σ_pool 逆転幅 +0.024 2 連続同値 initial** → S41 3 連続同値 or 拡大
- **pool 差 +0.06 帯 2 連続 initial (+0.063)** → S41 3 連続定着 or 拡大 or 帰還
- **3 ub 全 σ_pool 縮小 initial** → S41 再現 or shift
- **3 ub 全 + Δ pattern (+/+/+) initial** → S41 再現 or shift
- **cool time 境界帯 18+ 分 3 連続 initial** → S41 4 連続 or 離脱
- **pure mode_A 復元 2 連続 initial** → S41 3 連続 or hybrid 回帰
- **ub=1664 中帯復帰後** → 再下帯降下 / 中帯維持 / 上帯昇格
- **A+B = 22/40=55.0% 超半数 initial** → S41 継続 or 縮小
- **|t|>20 interval 1 session break** → S41 再到達 or 2 session interval
- **pool max 15.534 未更新 2 session** → S41 更新 or 維持

所要: バッチ実行 37-40 分 + 集計・プロット・レポート作成で合計約 1 時間。GPU ロック t120h-p100 を保持。

## 実施手順

### Step 1: タイムスタンプ確定 & GPU ロック取得

```bash
TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

- `TS` 保持（例: `2026-04-21_180000`）
- レポート名: `qwen3-122b-c3-phaseSeval41s`
- attachment ディレクトリ: `${TS}_qwen3-122b-c3-phaseSeval41s`

### Step 2: attachment ディレクトリ作成 & スクリプトコピー

S40 attachment から `report/attachment/${TS}_qwen3-122b-c3-phaseSeval41s/` へコピー・改名:

| S40 コピー元 | S41 コピー先 | 改変 |
|---|---|---|
| `start_phaseSeval40s.sh` | `start_phaseSeval41s.sh` | `40`→`41` 全置換（phaseSeval40s → phaseSeval41s、Seval40s → Seval41s） |
| `batch_phaseSeval40s.sh` | `batch_phaseSeval41s.sh` | `40`→`41` 全置換、メタデータ文言に「S40 まで + 第 41 session」追記 |
| `run_all.sh` | `run_all.sh` | 無改変 |
| `measure_phaseI.sh` | `measure_phaseI.sh` | 無改変 |
| `prompts/prompt_1k.txt` | `prompts/prompt_1k.txt` | 無改変 |
| `analyze_phaseSeval40s.py` | `analyze_phaseSeval41s.py` | (a) `CUR_SESSION_LABEL` → `S41_phaseSeval41s`、(b) `PRIOR_TSVS` 末尾に S40 エントリ追加、(c) 出力名 `phaseSeval40s_*` → `phaseSeval41s_*`、(d) `TAG_PREFIX = "Seval41s_fa1_ctx"`、(e) `MODE_GROUPS` に `prev_S40`/`cur_S41` 追加 |
| `plot_timeseries.py` | `plot_timeseries.py` | (a) `S_EVAL_DIRS` 末尾に `("S40", "2026-04-21_164936_qwen3-122b-c3-phaseSeval40s", "summary_phaseSeval40s.tsv")` 追加 + `("S41", None, "summary_phaseSeval41s.tsv")` 追加、(b) PNG タイトルを `40-session` → `41-session` 更新 |
| プラン添付 | `plan.md` | `cp /home/ubuntu/.claude/plans/todo-wise-cupcake.md plan.md` |

### Step 3: バッチ実行（37-40 分）

```bash
cd report/attachment/${TS}_qwen3-122b-c3-phaseSeval41s
HOST=t120h-p100 bash batch_phaseSeval41s.sh > batch_phaseSeval41s.log 2>&1
```

- 3 条件 (ub=1584/1586/1664) × (warmup 2 + eval 5) = 21 run
- Bash ツールの `run_in_background=true` で実行、完了待ちは他作業禁止
- 完走確認: `summary_phaseSeval41s.tsv` に 21 行（15 eval + 6 warmup）

### Step 4: 統計集計 & 時系列プロット

```bash
python3 analyze_phaseSeval41s.py   # phaseSeval41s_stats.csv / verdict.txt / pool 205-run 統計
python3 plot_timeseries.py         # timeseries_eval_tps.png 更新（S1-S41）
```

### Step 5: レポート作成

`report/${TS}_qwen3-122b-c3-phaseSeval41s.md` を S40 レポートをテンプレに以下を含めて作成:

1. タイトル: `# Qwen3.5-122B-A10B C-3 Phase S-eval-41session`
2. 実施日時・作業種別・GPU ロック状況
3. `## 添付ファイル`
4. `## 参照`（直前 S40 + 節目 S1/S15/S22/S30/S35/S38/S39/S40 + Sbfine ref 3 件）
5. `## 前提・目的`（S40 ★最優先 TODO 12+ 項目のバッチ検証）
6. `## 核心発見サマリ`（S41 結果に応じて regime 連続/break を記述）
7. `## 時系列プロット`（画像埋込）
8. `## 判定しきい値` / `## 成功条件`
9. `## 環境情報`（S40 と完全同一明記）
10. `## 再現方法`
11. `## 結果（本 Phase eval フェーズ、5-run mean）`
12. `## Welch t（prior 40-session pool n=200 vs S41 n=5）`
13. `## Pooled 205-run 統計`
14. `## 41-session peak order 1 位頻度` / `## mode 分類 41-session`
15. **`## 未検証事項`** — S40 同形式、★最優先/高/中/低 分類、S40 検証済項目除外、S41 新 regime 追加
16. **`## 検証完了後に実施すべき TODO`** — Phase S-eval-42session 候補を★最優先先頭
17. `## 結論`

### Step 6: GPU ロック解放

```bash
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### Step 7: Discord 通知

ユーザ明示依頼時のみ。

## クリティカルファイル

### 既存（参照・流用元）
- `report/2026-04-21_164936_qwen3-122b-c3-phaseSeval40s.md` — 直前レポート
- `report/attachment/2026-04-21_164936_qwen3-122b-c3-phaseSeval40s/` — 流用元スクリプト群（start/batch/run_all/measure_phaseI/analyze/plot）
- `report/attachment/2026-04-*_qwen3-122b-c3-phaseSeval*s/summary_phaseSeval*s.tsv` × 40 — pool 統計 prior raw
- `CLAUDE.md` / `REPORT.md`
- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- `.claude/skills/llama-server/scripts/stop.sh`

### 新規作成
- `report/${TS}_qwen3-122b-c3-phaseSeval41s.md`
- `report/attachment/${TS}_qwen3-122b-c3-phaseSeval41s/` 以下のスクリプト・ログ・PNG・tsv/csv 一式
- `report/attachment/${TS}_qwen3-122b-c3-phaseSeval41s/plan.md`（本プランのコピー）

## 検証方法

1. **バッチ実行成功**: `batch_phaseSeval41s.log` に 3 条件 × 「llama-server 起動成功 / /health 200 / 21 run 全完走」、`summary_phaseSeval41s.tsv` に 15 eval + 6 warmup 行、`out_Seval41s_fa1_ctx32768_ub{1584,1586,1664}_1k/` 各に `eval_run{1..5}.json` (predicted_n=256)
2. **統計スクリプト成功**: `analyze_phaseSeval41s.py` non-zero exit しない / pool n=205 / Welch t (prior 40-session n=200 vs S41 n=5) 3 ub 分出力 / `phaseSeval41s_verdict.txt` に 41-session range / σ_session / 崩壊頻度
3. **プロット**: `timeseries_eval_tps.png` が 41 session (S1-S41) + Sbfine ref 3 星マーカー付きで再生成
4. **レポート**: 「未検証事項」「検証完了後に実施すべき TODO」両セクション存在 / S40 ★最優先 TODO 12+ 項目が検証済(x)/継続([ ])分類 / 添付ファイルリンク全て存在
5. **GPU ロック解放**: `ssh t120h-p100 "cat /tmp/gpu_lock_session 2>/dev/null || echo 'no lock'"` で no lock

## リスク・注意事項

- **OOM / ub-reject**: startup 健全性チェックで検出時は該当 ub スキップし他 ub 継続。40 session OOM 発生実績なし。
- **cool time**: S40 終了時刻 = 2026-04-21 17:31:33 JST。S41 開始は現在時刻基準で自動算出。cool time sub-zone を verdict 自動出力。
- **feedback memory 準拠**:
  - Bash で for/$()/複雑パイプを避け、Glob や事前変数展開で書き換え
  - レポートタイトル簡潔化、発見ハイライトは「核心発見サマリ」集約
- **GPU ロック忘却防止**: 途中エラー時も必ず unlock してからユーザ報告
