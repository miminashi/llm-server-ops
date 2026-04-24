# Phase S-eval-42session 実施計画

## Context

直前レポート `report/2026-04-21_174520_qwen3-122b-c3-phaseSeval41s.md`（S41）の「未検証事項」★最優先項目は、**同条件で第 42 セッション (S42) を 1 回実行すれば 17+ 個を一括検証できる**構造。S41 で initial 化された多数の regime 現象（mode_F 3 例目、double collapse (1586/1664) 2 例目、ub=1586 崩壊 10 例目、Welch (+/-/-) shift、σ_pool 1664 1 位 4 連続、σ_pool 逆転幅 +0.026 拡大、pool 差 +0.05 帯帰還 等）を S42 で連続/終了判定する。

本 Phase は S41 のスクリプト群をコピーして `40`→`41`→`42` 置換のみ（分析/プロットは prior pool に S41 を追加）で実装でき、実行も自動化済み。

## 主検証対象（S41「新規項目 ★最優先」17+）

1. **mode_F 3 例目 → S42 連続 or shift**（41-session 0 例の mode_F 2 連続）
2. **double collapse (1586/1664) 2 例目 → S42 連続 or 離脱**（41-session 0 例の連続 double）
3. **ub=1586 崩壊 10 例目 → S42 連続 or 復帰**（崩壊連続 3-session 以上は過去 0 例）
4. **Welch (+/-/-) subtype → S42 連続 or shift**（12-subtype 12-session 連続新記録延長候補）
5. **σ_pool 1664 1 位 4 連続 → S42 5 連続 or 奪還**
6. **σ_pool 逆転幅 +0.026 拡大 initial → S42 連続拡大 or 縮小**
7. **ub=1664 σ_pool 2 連続縮小 → S42 3 連続縮小可否**
8. **pool 差 +0.05 帯帰還 → S42 +0.05 帯定着 or shift**
9. **mode_A 外 12 session → S42 13 連続外 or A 復帰**（S29 以来最長記録更新中）
10. **ub=1586 |Δ_max| 担当 shift → S42 連続 or 1664 奪還**
11. **ub=1586 pool mean 15.106 (-0.008) → S42 mean 動向**
12. **ub=1664 中帯 2 連続 → S42 3 連続 or shift**
13. **ub=1584 peak 1 位奪還 initial → S42 連続 or 喪失**
14. **prompt_tps 最高 ub 9 session rotation → S42 pattern**
15. **|Δ|>0.5 6 例目 ub=1586 → S42 連続 or 減速**
16. **Welch |t|>15 到達 3 session ぶり → S42 |t|>15 再到達 or 減少**
17. **3 ub range 維持 3 session 連続 → S42 4 連続 or 更新**
18. **pool max 15.534 未更新 3 session → S42 更新 or 維持**
19. **ub=1584 confirmed 復帰 3 連続 → S42 4 連続 or break**

所要: バッチ実行 37-40 分 + 集計・プロット・レポート作成で合計約 1 時間。GPU ロック `t120h-p100` を保持。

## 実施手順

### Step 1: タイムスタンプ確定 & GPU ロック取得

```bash
TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

- `TS` 保持（例: `2026-04-21_190000`）
- レポート名: `qwen3-122b-c3-phaseSeval42s`
- attachment ディレクトリ: `report/attachment/${TS}_qwen3-122b-c3-phaseSeval42s/`

### Step 2: attachment ディレクトリ作成 & スクリプトコピー

S41 attachment から `report/attachment/${TS}_qwen3-122b-c3-phaseSeval42s/` へコピー・改名:

| S41 コピー元 | S42 コピー先 | 改変 |
|---|---|---|
| `start_phaseSeval41s.sh` | `start_phaseSeval42s.sh` | `41`→`42` 全置換（phaseSeval41s → phaseSeval42s、Seval41s → Seval42s） |
| `batch_phaseSeval41s.sh` | `batch_phaseSeval42s.sh` | `41`→`42` 全置換、メタデータ文言に「S41 まで + 第 42 session」追記 |
| `run_all.sh` | `run_all.sh` | 無改変 |
| `measure_phaseI.sh` | `measure_phaseI.sh` | 無改変 |
| `prompts/prompt_1k.txt` | `prompts/prompt_1k.txt` | 無改変 |
| `analyze_phaseSeval41s.py` | `analyze_phaseSeval42s.py` | (a) `CUR_SESSION_LABEL` → `S42_phaseSeval42s`、(b) `PRIOR_TSVS` 末尾に S41 エントリ追加、(c) 出力名 `phaseSeval41s_*` → `phaseSeval42s_*`、(d) `TAG_PREFIX = "Seval42s_fa1_ctx"`、(e) `MODE_GROUPS` に `prev_S41`/`cur_S42` 追加 |
| `plot_timeseries.py` | `plot_timeseries.py` | (a) `S_EVAL_DIRS` 末尾に `("S41", "2026-04-21_174520_qwen3-122b-c3-phaseSeval41s", "summary_phaseSeval41s.tsv")` 追加 + `("S42", None, "summary_phaseSeval42s.tsv")` 追加、(b) PNG タイトルを `41-session` → `42-session` 更新 |
| プラン添付 | `plan.md` | `cp /home/ubuntu/.claude/plans/todo-velvety-taco.md plan.md` |

### Step 3: バッチ実行（37-40 分）

```bash
cd report/attachment/${TS}_qwen3-122b-c3-phaseSeval42s
HOST=t120h-p100 bash batch_phaseSeval42s.sh > batch_phaseSeval42s.log 2>&1
```

- 3 条件 (ub=1584/1586/1664) × (warmup 2 + eval 5) = 21 run
- Bash ツールの `run_in_background=true` で実行、完了後に結果確認
- 完走確認: `summary_phaseSeval42s.tsv` に 21 行（15 eval + 6 warmup）

### Step 4: 統計集計 & 時系列プロット

```bash
python3 analyze_phaseSeval42s.py   # phaseSeval42s_stats.csv / verdict.txt / pool 210-run 統計
python3 plot_timeseries.py         # timeseries_eval_tps.png 更新（S1-S42）
```

### Step 5: レポート作成

`report/${TS}_qwen3-122b-c3-phaseSeval42s.md` を S41 レポートをテンプレに以下を含めて作成:

1. タイトル: `# Qwen3.5-122B-A10B C-3 Phase S-eval-42session`
2. 実施日時・作業種別・GPU ロック状況
3. `## 添付ファイル`
4. `## 参照`（直前 S41 + 節目 S1/S9/S15/S22/S30/S33/S35/S38/S40/S41 + Sbfine ref 3 件）
5. `## 前提・目的`（S41 ★最優先 TODO 17+ 項目のバッチ検証）
6. `## 核心発見サマリ`（S42 結果に応じて regime 連続/break を記述）
7. `## 時系列プロット`（画像埋込）
8. `## 判定しきい値` / `## 成功条件`
9. `## 環境情報`（S41 と完全同一明記）
10. `## 再現方法`
11. `## 結果（本 Phase eval フェーズ、5-run mean）`
12. `## Welch t（prior 41-session pool n=205 vs S42 n=5）`
13. `## Pooled 210-run 統計`
14. `## 42-session peak order 1 位頻度` / `## mode 分類 42-session`
15. **`## 未検証事項`** — S41 同形式、★最優先/高/中/低 分類、S41 検証済項目は `[x]` で完了、S42 新 regime を追加
16. **`## 検証完了後に実施すべき TODO`** — Phase S-eval-43session 候補を★最優先先頭
17. `## 結論`

### Step 6: GPU ロック解放

```bash
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### Step 7: Discord 通知

ユーザ明示依頼時のみ。

## クリティカルファイル

### 既存（参照・流用元）
- `report/2026-04-21_174520_qwen3-122b-c3-phaseSeval41s.md` — 直前レポート
- `report/attachment/2026-04-21_174520_qwen3-122b-c3-phaseSeval41s/` — 流用元スクリプト群（start/batch/run_all/measure_phaseI/analyze/plot）
- `report/attachment/2026-04-*_qwen3-122b-c3-phaseSeval*s/summary_phaseSeval*s.tsv` × 41 — pool 統計 prior raw
- `CLAUDE.md` / `REPORT.md`
- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- `.claude/skills/llama-server/scripts/stop.sh`

### 新規作成
- `report/${TS}_qwen3-122b-c3-phaseSeval42s.md`
- `report/attachment/${TS}_qwen3-122b-c3-phaseSeval42s/` 以下のスクリプト・ログ・PNG・tsv/csv 一式
- `report/attachment/${TS}_qwen3-122b-c3-phaseSeval42s/plan.md`（本プランのコピー）

## 検証方法

1. **バッチ実行成功**: `batch_phaseSeval42s.log` に 3 条件 × 「llama-server 起動成功 / /health 200 / 21 run 全完走」、`summary_phaseSeval42s.tsv` に 15 eval + 6 warmup 行、`out_Seval42s_fa1_ctx32768_ub{1584,1586,1664}_1k/` 各に `eval_run{1..5}.json` (predicted_n=256)
2. **統計スクリプト成功**: `analyze_phaseSeval42s.py` non-zero exit しない / pool n=210 / Welch t (prior 41-session n=205 vs S42 n=5) 3 ub 分出力 / `phaseSeval42s_verdict.txt` に 42-session range / σ_session / 崩壊頻度
3. **プロット**: `timeseries_eval_tps.png` が 42 session (S1-S42) + Sbfine ref 3 星マーカー付きで再生成
4. **レポート**: 「未検証事項」「検証完了後に実施すべき TODO」両セクション存在 / S41 ★最優先 TODO 17+ 項目が検証済(x)/継続([ ])分類 / 添付ファイルリンク全て存在
5. **GPU ロック解放**: `ssh t120h-p100 "cat /tmp/gpu_lock_session 2>/dev/null || echo 'no lock'"` で no lock

## リスク・注意事項

- **OOM / ub-reject**: startup 健全性チェックで検出時は該当 ub スキップし他 ub 継続。41 session OOM 発生実績なし。
- **cool time**: S41 終了時刻 = 2026-04-21 18:26:45 JST。S42 開始は現在時刻基準で自動算出。cool time sub-zone を verdict 自動出力。
- **feedback memory 準拠**:
  - Bash で `for` / `$()` / 複雑パイプを避け、Glob や事前変数展開で書き換え
  - レポートタイトル簡潔化、発見ハイライトは「核心発見サマリ」集約
- **GPU ロック忘却防止**: 途中エラー時も必ず unlock してからユーザ報告
- **Plan mode**: 本計画は plan mode で作成。実装は approval 後に開始。
