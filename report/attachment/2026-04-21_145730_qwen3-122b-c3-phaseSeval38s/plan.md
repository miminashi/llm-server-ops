# Phase S-eval-38session 実施計画

## Context

直前レポート [2026-04-21_140342_qwen3-122b-c3-phaseSeval37s.md](../../projects/llm-server-ops/report/2026-04-21_140342_qwen3-122b-c3-phaseSeval37s.md) の「未検証事項 > 新規項目」および「検証完了後に実施すべき TODO」で **★最優先** および **★最重要** とされた Phase S-eval-38session を実施する。S35→S36→S37 で判明した複数の regime 変化・連続記録を、次 session (S38) で延伸 or break 判定する。同時検証できる ★最優先 TODO は以下の通り（いずれも n=38 の 1 session 追加で白黒がつく）:

1. **mode_E 3 連続 → S38 4 連続 or 回帰** (37-session 0 例の 4 連続可否)
2. **ub=1584 3 連続崩壊 → S38 4 連続 or 回復** (崩壊 3-session 限定 vs 4 連続)
3. **ub=1586 回復 3 連続 → S38 4 連続回復 or 再崩壊** (高値帯定着 regime 持続性)
4. **ub=1664 上帯 → S38 帯分岐** (上帯継続 / 上→中 / 上→下 jump の分岐)
5. **A=B タイ 7 連続 → S38 8 連続可否** (equilibrium regime 持続性)
6. **σ_pool 1586 1 位 6 連続 → S38 7 連続可否**
7. **Welch (-/+/+) 2 連続 → S38 3 連続 or subtype shift**
8. **pool 差 +0.05-+0.06 安定帯 2 連続 → S38 3 連続定着 or 再拡大 or 収束**
9. **ub=1586 3 冠 3 連続 → S38 4 連続可否** (peak + σ_pool + mean 1 位)
10. **ub=1664 peak 1 位 5 連続停滞 → S38 6 連続 or 復調**

いずれも S37 と同条件 (ctx=32768 × fa=1 × OT=MoE-only 固定、ub={1584,1586,1664}) での n=38 追加計測で判定可能。

## 実施アプローチ

S37 実装 (`report/attachment/2026-04-21_140342_qwen3-122b-c3-phaseSeval37s/`) を雛形とし、以下を **新タイムスタンプディレクトリへコピー＆リネーム**:

- `batch_phaseSeval37s.sh` → `batch_phaseSeval38s.sh`
- `start_phaseSeval37s.sh` → `start_phaseSeval38s.sh`
- `run_all.sh`, `measure_phaseI.sh` — 変更なしでコピー
- `prompts/prompt_1k.txt` — 変更なしでコピー（Sbfine3/全 S-eval と同一 6200 bytes）
- `analyze_phaseSeval37s.py` → `analyze_phaseSeval38s.py` （`PRIOR_TSVS` に S37 を追加、出力ファイル名を `phaseSeval38s_*` に変更）

スクリプト内の識別子 (ラベル、REMOTE_LOG prefix、出力ファイル名) は `Seval37s` / `phaseSeval37s` → `Seval38s` / `phaseSeval38s` に一括置換。起動パラメータ・測定条件は **完全同一** を維持（比較可能性確保）。

## 対象ファイル（新規作成）

新規ディレクトリ: `/home/ubuntu/projects/llm-server-ops/report/attachment/<YYYY-MM-DD_HHMMSS>_qwen3-122b-c3-phaseSeval38s/`

- `plan.md` — 実施プラン（本計画の写し）
- `batch_phaseSeval38s.sh` — 3 条件バッチ実行
- `start_phaseSeval38s.sh` — llama-server 起動
- `run_all.sh` — 1 条件内 warmup 2 + eval 5 ループ（S37 からコピー）
- `measure_phaseI.sh` — 1 run 計測（S37 からコピー）
- `analyze_phaseSeval38s.py` — 38-session 集計、pooled 190-run 統計、Welch t (prior 37-session pool vs S38)、崩壊頻度、mode 分類、σ_pool 推移、ピーク順序頻度
- `prompts/prompt_1k.txt` — S37 からコピー
- `startup_logs/` — 作成（3 ファイル格納先）

レポート: `/home/ubuntu/projects/llm-server-ops/report/<YYYY-MM-DD_HHMMSS>_qwen3-122b-c3-phaseSeval38s.md`

## 再利用する既存スクリプト

- `.claude/skills/gpu-server/scripts/lock.sh t120h-p100` — ロック取得
- `.claude/skills/gpu-server/scripts/unlock.sh t120h-p100` — ロック解放
- `.claude/skills/llama-server/scripts/stop.sh` — batch 内で使用（ub 切替時の停止）
- S37 attachment の全スクリプト群（完全コピー＆識別子置換のみ）

## 手順

1. GPU ロック取得（Skill `gpu-server` 経由）
2. 新タイムスタンプディレクトリ作成、S37 attachment を一括コピー
3. 識別子 `Seval37s`/`phaseSeval37s` → `Seval38s`/`phaseSeval38s` 置換
4. `analyze_phaseSeval38s.py` の `PRIOR_TSVS` に S37 エントリ追加
5. `batch_phaseSeval38s.sh` 実行（37 分前後、3 条件 × (warmup 2 + eval 5)）
6. `analyze_phaseSeval38s.py` 実行で集計・38-session verdict 生成
7. GPU ロック解放
8. レポート作成（`REPORT.md` 準拠、「未検証事項」「検証完了後に実施すべき TODO」セクション必須、S37 と同じ構造で 38-session 結果へ更新）
9. Discord 通知（Skill `discord-notify`）

## 検証方法

- `batch_phaseSeval38s.log` で 3 条件全てで `/health OK` 確認
- `summary_phaseSeval38s.tsv` に ub=1584/1586/1664 の warmup 2 + eval 5 = **21 行** (7 × 3) 出力確認
- `phaseSeval38s_stats.csv` で各 ub の mean/stdev/min/max/median 算出確認
- `phaseSeval38s_verdict.txt` で 38-session range / pooled 190-run / Welch / 崩壊頻度の集計確認
- S37 との比較で上記 ★最優先 TODO 10 項目の判定（連続記録延伸 or break）

## リスク・考慮事項

- ctx=32k × fa=1 での起動は S1-S37 で 100% 成功、OOM/ub-reject の確率低
- 所要時間 37-40 分、GPU ロックは取得から解放まで保持
- S37 終了から十分な cool time 経過後に実施（cool time sub-zone 記録のため時刻は記録する）
- 結果が S37 で確定した regime を **break** した場合でも valid データとして記録（回帰はネガティブ結果ではない）

## レポートに含めるセクション（ユーザ指示の明示）

- 「**未検証事項**」— S37 から継続する ★優先 項目 + S38 で新規判明した項目
- 「**検証完了後に実施すべき TODO**」— CLAUDE.md 更新候補、次 session 候補、派生 Phase 候補
