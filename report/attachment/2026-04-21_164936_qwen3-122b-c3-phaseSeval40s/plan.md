# Phase S-eval-40session 実施計画

## Context

直前レポート `report/2026-04-21_155525_qwen3-122b-c3-phaseSeval39s.md`（S39）の「未検証事項」★最優先項目は、**同条件で第 40 セッション (S40) を 1 回実行すれば 10+ 個を一括検証できる**構造。S39 で initial 化された多数の regime 現象を S40 で連続/終了判定する。検証対象:

- **mode_B 単独 1 位 initial** → S40 連続 or A=B 再タイ or 他 mode（39-session 0 例の 2 連続）
- **ub=1664 下帯降下 14.473 (Δ=-1.057)** → S40 回復 or pool min 14.213 更新深化
- **ub=1664 pool max 15.534 維持 1 session** → S40 更新 or 維持継続
- **ub=1586 回復 5 連続 initial** → S40 6 連続 or 再崩壊（0 例の 6 連続）
- **mode_A 10 session 外最長** → S40 A 復帰 or 11 連続外（0 例）
- **Welch (+/+/-) 新 subtype initial** → S40 再現 or shift
- **σ_pool 1664 1 位 2 連続 initial** → S40 3 連続 or 1586 奪還（0 例の 3 連続）
- **pool 差 +0.063 (+0.06 帯昇格 initial)** → +0.06 帯定着 or +0.05 帯帰還 or +0.07+拡大
- **ub=1664 |Δ_max| 担当 4 連続** → S40 5 連続可否（0 例の 5 連続）
- **3 ub (+/+/-) Δ pattern initial** → 再現 or shift
- **cool time 境界帯 18+ 分 2 連続 initial** → 3 連続可否
- **pure mode_A 復元 35 session ぶり** → 2 連続可否
- **2 帯跳越 (上→下) transition initial** → 再跳越 or 通常遷移

所要: バッチ実行 37-40 分 + 集計・プロット・レポート作成で合計約 1 時間。GPU ロック t120h-p100 を保持。

## 実施手順

### Step 1: タイムスタンプ確定 & GPU ロック取得

```bash
TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

- `TS` 保持（例: `2026-04-21_170000`）
- レポート名: `qwen3-122b-c3-phaseSeval40s`
- attachment ディレクトリ: `${TS}_qwen3-122b-c3-phaseSeval40s`

### Step 2: attachment ディレクトリ作成 & スクリプトコピー

S39 attachment から `report/attachment/${TS}_qwen3-122b-c3-phaseSeval40s/` へコピー・改名:

| S39 コピー元 | S40 コピー先 | 改変 |
|---|---|---|
| `start_phaseSeval39s.sh` | `start_phaseSeval40s.sh` | `39`→`40` 全置換 |
| `batch_phaseSeval39s.sh` | `batch_phaseSeval40s.sh` | `39`→`40` 全置換 |
| `run_all.sh` | `run_all.sh` | 無改変 |
| `measure_phaseI.sh` | `measure_phaseI.sh` | 無改変 |
| `prompts/prompt_1k.txt` | `prompts/prompt_1k.txt` | 無改変 |
| `analyze_phaseSeval39s.py` | `analyze_phaseSeval40s.py` | (a) `CUR_SESSION_LABEL` → `S40_phaseSeval40s`、(b) `PRIOR_TSVS` 末尾に S39 tsv 追加、(c) 出力名 `phaseSeval39s_*` → `phaseSeval40s_*`、(d) 39-session/prior 38 文言を 40-session/prior 39 に更新 |
| `plot_timeseries.py` | `plot_timeseries.py` | `SESSIONS` リスト末尾に S40 追加 |
| プラン添付 | `plan.md` | `cp /home/ubuntu/.claude/plans/todo-rippling-cat.md plan.md` |

### Step 3: バッチ実行（37-40 分）

```bash
cd report/attachment/${TS}_qwen3-122b-c3-phaseSeval40s
HOST=t120h-p100 bash batch_phaseSeval40s.sh > batch_phaseSeval40s.log 2>&1
```

- 3 条件 (ub=1584/1586/1664) × (warmup 2 + eval 5) = 21 run
- `run_in_background=true` で実行、完了待ちは他作業禁止
- 完走確認: `summary_phaseSeval40s.tsv` が生成されていること

### Step 4: 統計集計 & 時系列プロット

```bash
python3 analyze_phaseSeval40s.py   # phaseSeval40s_stats.csv / verdict.txt / pool 200-run 統計
python3 plot_timeseries.py         # timeseries_eval_tps.png 更新（S1-S40）
```

### Step 5: レポート作成

`report/${TS}_qwen3-122b-c3-phaseSeval40s.md` を S39 レポートをテンプレに以下を含めて作成:

1. タイトル: `# Qwen3.5-122B-A10B C-3 Phase S-eval-40session`
2. 実施日時・作業種別・GPU ロック状況
3. `## 添付ファイル`
4. `## 参照`（直前 S39 + 節目 S1/S15/S22/S30/S35/S38/S39 + Sbfine ref 3 件）
5. `## 前提・目的`（S39 ★最優先 TODO 10+ 項目のバッチ検証）
6. `## 核心発見サマリ`（S40 結果に応じて regime 連続/break を記述）
7. `## 時系列プロット`（画像埋込）
8. `## 判定しきい値` / `## 成功条件`
9. `## 環境情報`（S39 と完全同一明記）
10. `## 再現方法`
11. `## 結果（本 Phase eval フェーズ、5-run mean）`
12. `## Welch t（prior 39-session pool n=195 vs S40 n=5）`
13. `## Pooled 200-run 統計`
14. `## 40-session peak order 1 位頻度` / `## mode 分類 40-session`
15. **`## 未検証事項`** — S39 同形式、★最優先/高/中/低 分類、S39 検証済項目除外、S40 新 regime 追加
16. **`## 検証完了後に実施すべき TODO`** — Phase S-eval-41session 候補を★最優先先頭
17. `## 結論`

### Step 6: GPU ロック解放

```bash
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### Step 7: Discord 通知

ユーザ明示依頼時のみ。

## クリティカルファイル

### 既存（参照・流用元）
- `report/2026-04-21_155525_qwen3-122b-c3-phaseSeval39s.md` — 直前レポート
- `report/attachment/2026-04-21_155525_qwen3-122b-c3-phaseSeval39s/` — 流用元スクリプト群
- `report/attachment/2026-04-*_qwen3-122b-c3-phaseSeval*s/summary_phaseSeval*s.tsv` × 39 — pool 統計 prior raw
- `CLAUDE.md` / `REPORT.md`
- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- `.claude/skills/llama-server/scripts/stop.sh`

### 新規作成
- `report/${TS}_qwen3-122b-c3-phaseSeval40s.md`
- `report/attachment/${TS}_qwen3-122b-c3-phaseSeval40s/` 以下のスクリプト・ログ・PNG・tsv/csv 一式
- `report/attachment/${TS}_qwen3-122b-c3-phaseSeval40s/plan.md`（本プランのコピー）

## 検証方法

1. **バッチ実行成功**: `batch_phaseSeval40s.log` に 3 条件 × 「llama-server 起動成功 / /health 200 / 21 run 全完走」、`summary_phaseSeval40s.tsv` に 15 eval + 6 warmup 行、`out_Seval40s_fa1_ctx32768_ub{1584,1586,1664}_1k/` 各に `eval_run{1..5}.json` (predicted_n=256)
2. **統計スクリプト成功**: `analyze_phaseSeval40s.py` non-zero exit しない / pool n=200 / Welch t (prior 39-session n=195 vs S40 n=5) 3 ub 分出力 / `phaseSeval40s_verdict.txt` に 40-session range / σ_session / 崩壊頻度
3. **プロット**: `timeseries_eval_tps.png` が 40 session (S1-S40) + Sbfine ref 3 星マーカー付きで再生成
4. **レポート**: 「未検証事項」「検証完了後に実施すべき TODO」両セクション存在 / S39 ★最優先 TODO 10+ 項目が検証済(x)/継続([ ])分類 / 添付ファイルリンク全て存在
5. **GPU ロック解放**: `ssh t120h-p100 "cat /tmp/gpu_lock_session 2>/dev/null || echo 'no lock'"` で no lock

## リスク・注意事項

- **OOM / ub-reject**: startup 健全性チェックで検出時は該当 ub スキップし他 ub 継続。39 session OOM 発生実績なし。
- **cool time**: S39 終了時刻 = 2026-04-21 16:36:07 JST。S40 開始は現在時刻基準で自動算出。cool time sub-zone を verdict 自動出力。
- **feedback memory 準拠**:
  - Bash で for/$()/複雑パイプを避け、Glob や事前変数展開で書き換え
  - レポートタイトル簡潔化、発見ハイライトは「核心発見サマリ」集約
- **GPU ロック忘却防止**: 途中エラー時も必ず unlock してからユーザ報告
