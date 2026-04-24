# Phase S-eval-21session 実施計画

## Context

最新レポート [2026-04-20_231300_qwen3-122b-c3-phaseSeval20s.md](../../../projects/llm-server-ops/report/2026-04-20_231300_qwen3-122b-c3-phaseSeval20s.md)（S20、23:13終了）に記載された「新規項目（本 Phase S-eval-20session で判明・発生）」のうち、★最優先 5 項目はすべて同一条件（ub={1584,1586,1664} × ctx=32768 × fa=1、warmup 2 + eval 5）の **第 21 セッション（S21）** を実施することで同時検証可能。

S20 は「cool time 15 分 13 秒 = 通常帯復帰 + ub=1664 下帯 2 連続初観測 + ub=1584 confirmed 復帰 + A/B 同率再均衡 + 3 ub sig 回帰 + ub=1586 Δ=+0.023 最小動揺」の 5 大事件同時観測。S21 はこれらの連続性（3 連続 or 脱出）を測り、Markov 遷移確率の精度を高める。

**同時検証する未検証事項（S20 ★最優先）:**
1. ub=1664 下帯 2 連続 → 「3 連続 or 脱出」
2. ub=1586 Δ=+0.023 最小動揺の再現性
3. ub=1584 3 連続非崩壊 + confirmed 継続定着
4. mode_A/mode_B 7/7 均衡 steady-state 定着
5. 3 ub sig 類型 5/20=25.0% 頻度の Welch 非独立性

所要時間 約50分（バッチ45分 + 分析+レポート 5-10分）。現在 23:22、S20 終了 23:10 から cool time 約12分経過、S21 開始時点では 15 分帯に入る。

## 実施ステップ

### 1. GPU ロック取得
```bash
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 2. 作業ディレクトリ・資材複製
- タイムスタンプ取得: `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` → `<TS>`
- 添付ディレクトリ: `report/attachment/<TS>_qwen3-122b-c3-phaseSeval21s/`
- S20 attachment からスクリプト群をコピー & リネーム:
  - `start_phaseSeval20s.sh` → `start_phaseSeval21s.sh`
  - `batch_phaseSeval20s.sh` → `batch_phaseSeval21s.sh`
  - `run_all.sh` / `measure_phaseI.sh` はそのままコピー
  - `prompts/prompt_1k.txt` をコピー
  - `analyze_phaseSeval20s.py` → `analyze_phaseSeval21s.py`
  - `startup_logs/` ディレクトリ作成
- スクリプト内の `Seval20s` / `phaseSeval20s` を `Seval21s` / `phaseSeval21s` に置換
- `analyze_phaseSeval21s.py` に S20 の TSV を PRIOR_TSVS に追加、`CUR_SESSION_LABEL = "S21_phaseSeval21s"`

### 3. バッチ実行
```bash
cd report/attachment/<TS>_qwen3-122b-c3-phaseSeval21s/
bash batch_phaseSeval21s.sh > batch_phaseSeval21s.log 2>&1
```

- 3 条件 (ub=1584/1586/1664) × (warmup 2 + eval 5) = 21 run
- 所要 約45分
- 各 ub 間で llama-server 再起動

### 4. 分析
```bash
python3 analyze_phaseSeval21s.py
```
- 21-session range / σ_session / Welch t / ピーク順序 / pooled 105-run 統計生成
- 出力: `summary_phaseSeval21s.tsv`, `phaseSeval21s_stats.csv`, `phaseSeval21s_verdict.txt`

### 5. レポート作成
- パス: `report/<TS>_qwen3-122b-c3-phaseSeval21s.md`
- [REPORT.md](../../projects/llm-server-ops/REPORT.md) 準拠（日時 JST、添付リンク、環境情報、再現方法）
- セクション構成（S20 レポートと同構造）:
  - 前提・目的（5 検証対象を明記）
  - 環境情報
  - 再現方法
  - 実行結果サマリ（eval ピボット、21-session 時系列、Welch t、mode 分類、pooled 105-run、cool time 勾配、帯分布）
  - **未検証事項**（S20 から継続 + S21 で新規に発生したもの）
  - **検証完了後に実施すべき TODO**（S20 から継続分 + S21 新規）
  - 補足（S21 核心発見サマリ）
- プランファイル添付: `cp /home/ubuntu/.claude/plans/todo-logical-newt.md report/attachment/<TS>_qwen3-122b-c3-phaseSeval21s/plan.md`

### 6. 停止・解放
```bash
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 修正対象ファイル（すべて新規作成、既存改変なし）

- `report/attachment/<TS>_qwen3-122b-c3-phaseSeval21s/start_phaseSeval21s.sh`
- `report/attachment/<TS>_qwen3-122b-c3-phaseSeval21s/batch_phaseSeval21s.sh`
- `report/attachment/<TS>_qwen3-122b-c3-phaseSeval21s/run_all.sh`（S20 と同一）
- `report/attachment/<TS>_qwen3-122b-c3-phaseSeval21s/measure_phaseI.sh`（S20 と同一）
- `report/attachment/<TS>_qwen3-122b-c3-phaseSeval21s/analyze_phaseSeval21s.py`
- `report/attachment/<TS>_qwen3-122b-c3-phaseSeval21s/prompts/prompt_1k.txt`（S20 と同一）
- `report/attachment/<TS>_qwen3-122b-c3-phaseSeval21s/plan.md`（本ファイルをコピー）
- `report/<TS>_qwen3-122b-c3-phaseSeval21s.md`

## 再利用する既存資産

- Skill `gpu-server` (`.claude/skills/gpu-server/scripts/lock.sh`, `unlock.sh`)
- Skill `llama-server` (`.claude/skills/llama-server/scripts/stop.sh`)
- 過去 20 session の TSV (`report/attachment/*_qwen3-122b-c3-phaseSeval*/summary_phaseSeval*.tsv`)
- S20 attachment の全スクリプト（丸ごとコピー → 改名）

## 検証方法（end-to-end）

1. バッチログ確認: `batch_phaseSeval21s.log` 末尾に `end at ...` あり、ERROR なし
2. 各条件で 5 run 完走: `out_Seval21s_fa1_ctx32768_ub{1584,1586,1664}_1k/` に 5 ファイルずつ
3. 分析出力確認:
   - `phaseSeval21s_stats.csv`: 3 ub × 21 session の range/σ/verdict
   - `phaseSeval21s_verdict.txt`: ub=1664 下帯 episode 長、mode 分類、Welch sig 数、pool 極値更新
4. レポートの 5 検証対象が「★最優先」として明示され、結果が判定されている（成立/不成立/継続観測）

## 注意

- Auto mode 実行中、ロック取得失敗時は 5 分待機で再試行（既存 skill 挙動）
- 途中 health チェック失敗時は skill `stop.sh` で明示停止してから次の ub へ移行
- S21 終了後は必ず GPU ロック解放
