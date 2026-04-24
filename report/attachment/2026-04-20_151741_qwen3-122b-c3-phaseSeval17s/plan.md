# Phase S-eval-17session 実施計画

## Context

直前レポート [2026-04-20_142019_qwen3-122b-c3-phaseSeval16s.md](/home/ubuntu/projects/llm-server-ops/report/2026-04-20_142019_qwen3-122b-c3-phaseSeval16s.md) の未検証事項のうち、**最優先** かつ所要 40 分で即実行可能な以下を実施する：

> **★最重要: Phase S-eval-17session 候補** — ub=1586 peak 1 位 5 連続 or mode_A 復帰、ub=1664 中帯/下帯交互 5 session 目確認、ub=1584 崩壊 1 session 限定の 2 session 目静穏継続、所要 40 分

### 検証目的（3 軸）

1. **ub=1586 peak 1 位 5 連続**: S13/S14/S15/S16 で 4 連続達成、S17 で 5 連続 or mode_A (1584,1586,1664) 復帰
2. **ub=1664 中帯/下帯 5 session 目交互**: S13 中 15.104 / S14 下 14.869 / S15 中 15.001 / S16 下 14.593、bimodal 周期 2 仮説の S17 予測「中帯 ≥15.0」
3. **ub=1584 崩壊→復帰後の 2 session 目静穏**: S15 崩壊 13.964 → S16 +1.174 回復 → S17 静穏継続? もしくは再崩壊か

また、S16 で判明した以下の新規最優先項目も同時追跡：
- **ub=1584 崩壊→直後回復幅 +1.174 の物理最大性**: S17 以降の類似現象監視
- **cool time 感受性**: S13-S15 は 14 分、S16 は 13 分、S17 では現在 15:15 時点で既に S16 終了（15:06）から 9 分経過 → S17 cool time 15-20 分想定

## Approach

S16 の attachment を S17 用に複製し、session label と REMOTE_LOG prefix を更新。条件は完全同一で再現性確保。

### 実施条件（S1-S16 と同一）

- GPU: t120h-p100 (10.1.4.14)、P100 × 4
- モデル: Qwen3.5-122B-A10B-Q4_K_M
- ctx=32768, fa=1, f16/f16 KV, `numactl --cpunodebind=1 --membind=1`, threads=40, poll=0, ngl=999
- OT_REGEX: `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
- ub ∈ {1584, 1586, 1664}, 各 warmup 2 run + eval 5 run
- prompt: `prompts/prompt_1k.txt` (1086 tok)、max_tokens=256、cooldown 60s

### 実行ステップ

1. **作業ディレクトリ作成**: `report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval17s/`
2. **スクリプト複製・改名**（S16 → S17）:
   - `start_phaseSeval17s.sh` — REMOTE_LOG を `phaseSeval17s` に変更
   - `batch_phaseSeval17s.sh` — TAG_PREFIX を `Seval17s` に、log ファイル名も更新
   - `run_all.sh` — そのまま複製（内容不変）
   - `measure_phaseI.sh` — そのまま複製
   - `analyze_phaseSeval17s.py` — `PRIOR_TSVS` に S16 エントリ追加、`CUR_SESSION_LABEL` = `S17_phaseSeval17s`、`MODE_GROUPS` の `prev_S16` / `cur_S17` に更新、スクリプト名と出力 CSV/verdict 名を `17s` に
   - `prompts/prompt_1k.txt` — S16 から複製（同一ファイル）
3. **GPU ロック取得**: `bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100`
4. **バッチ実行**: `bash batch_phaseSeval17s.sh > batch_phaseSeval17s.log 2>&1`（約 45 分）
5. **分析**: `python3 analyze_phaseSeval17s.py`
6. **llama-server 停止**: `bash .claude/skills/llama-server/scripts/stop.sh t120h-p100`
7. **GPU ロック解放**: `bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100`
8. **レポート作成**: `report/<timestamp>_qwen3-122b-c3-phaseSeval17s.md`（S16 と同構造）
   - **未検証事項** と **検証完了後に実施すべき TODO** のセクションを含める（ユーザ指示）

### 成功条件

- [x] 3 条件起動成功
- [x] 各条件 eval 5 run の eval_tps 取得
- [x] 17-session range / σ_session の算出
- [x] Welch t (prior 16-session pool vs S17) で有意差判定
- [x] ピーク ub 順序の 17 session 安定性確認
- [x] pooled 85-run 統計の算出
- [x] ub=1586 peak 1 位 5 連続検証
- [x] ub=1664 中帯/下帯 5 session 目交互検証（S17 予測「中帯」）
- [x] ub=1584 崩壊 1 session 限定の 2 session 目静穏検証
- [x] GPU ロック取得・解放の正常動作

## 修正対象ファイル

新規作成（既存の S16 ファイルを複製・改名）:
- `report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval17s/start_phaseSeval17s.sh`
- `report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval17s/batch_phaseSeval17s.sh`
- `report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval17s/run_all.sh`
- `report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval17s/measure_phaseI.sh`
- `report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval17s/analyze_phaseSeval17s.py`
- `report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval17s/prompts/prompt_1k.txt`
- `report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval17s/plan.md`（本計画のコピー）
- `report/<timestamp>_qwen3-122b-c3-phaseSeval17s.md`

既存参照のみ（変更なし）:
- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- `.claude/skills/llama-server/scripts/stop.sh`
- S1-S16 summary TSV（分析スクリプトから参照）

## 再利用する既存ユーティリティ

- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh` — GPU ロック排他制御
- `.claude/skills/llama-server/scripts/stop.sh` — llama-server 停止
- S16 の `run_all.sh`, `measure_phaseI.sh`, `prompts/prompt_1k.txt` — 内容変更不要、そのまま再利用

## 検証手順（end-to-end）

1. 計画承認後、Auto モードで即時実行
2. 各条件で `/health` OK 確認 → warmup 2 run → eval 5 run、合計 3 条件 × 7 run = 21 run
3. `summary_phaseSeval17s.tsv` が 21 行生成されることを確認
4. `phaseSeval17s_verdict.txt` に 17-session σ/range、peak order 集計、崩壊頻度、Welch t が出力されることを確認
5. レポート作成後、git status で stray file が無いことを確認

## レポート記載の必須セクション

- 前提・目的（S17 検証 3 軸）
- 環境情報（S1-S16 と同一）
- 再現方法
- 実行結果サマリ（5-run ピボット、17-session 時系列、Welch t、pooled 85-run、peak order、崩壊頻度、warmup1 band/delta）
- **未検証事項**（本 Phase で潰した項目は [x]、継続項目は [ ]）
- **検証完了後に実施すべき TODO**（S18 候補を新規追加）
- 補足（核心発見サマリ）
