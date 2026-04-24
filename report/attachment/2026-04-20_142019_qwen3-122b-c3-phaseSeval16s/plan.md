# Phase S-eval-16session (S16) 実行プラン

## Context

直前レポート [2026-04-20_132400_qwen3-122b-c3-phaseSeval15s.md](../../projects/llm-server-ops/report/2026-04-20_132400_qwen3-122b-c3-phaseSeval15s.md) の「検証完了後に実施すべき TODO」冒頭（★最重要）:

> ★最重要: Phase S-eval-16session 候補 — ub=1586 peak 1 位 4 連続 or mode_A 復帰、ub=1584 崩壊連続 or 復帰、pool 差 -0.093 維持 or 復帰、静穏/大変動交互パターン検証、所要 40 分

を最優先として実施する。S15 で判明した以下の仮説を検証する:

1. **ub=1586 peak 1 位 4 連続性** — S13/S14/S15 で 3 連続達成、S16 で継続 or mode_A 復帰か
2. **ub=1584 崩壊間隔減少仮説** — S4→S13 = 9 session / S13→S15 = 2 session → S15→S16 = 1 or 2 か（連続崩壊 or 復帰）
3. **pool 差 1584−1586 符号反転後の安定性** — S15 −0.093、S16 で −0.1 以下維持なら 1586 単独 1 位確定
4. **静穏/大変動 2-session 交互パターン** — S12/S14 静穏、S13/S15 大変動 → **S16 静穏予測**（3 ub 全方向内 Welch |t|<5）
5. **cool time 14 分 3 回目固定** — S13/S14/S15 と同 14 分で cool time の影響切り分け
6. **warmup1 band 4 + delta 3 再出現頻度** — S15 単独か複数 session で出現か

## 実施内容

S15 と完全同条件の 3-ub × (warmup 2 + eval 5) バッチを第 16 セッションとして実行する。添付物は S15 からコピーし、Phase 名・ログ prefix のみ `phaseSeval16s` に書き換える。

### 実行設定（S1-S15 と完全同一）

- GPU サーバ: t120h-p100 (10.1.4.14)
- モデル: `Qwen3.5-122B-A10B-Q4_K_M`
- fa=1 / f16 KV / ctx=32768 / OT=MoE-only / NUMA=1 / threads=40 / poll=0 / ngl=999
- ub: {1584, 1586, 1664} の 3 条件
- warmup 2 + eval 5（1k prompt = 1086 tok、max_tokens=256、cooldown 60 秒）
- OT_REGEX: `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
- compute buffer (ub=1586) 期待値: CUDA0=980.36 / CUDA1=452.31 / CUDA2=452.31 / CUDA3=1558.12 / Host=235.48 MiB（15 session 完全一致）

### 判定しきい値

- fully_independent: 16-session range (max−min) ≤ 0.02 t/s
- partial_drift: range ≤ 0.10 t/s
- session_dominated: range > 0.10 t/s
- 崩壊判定: eval_mean < 15.0 t/s

## 作業ステップ

1. **レポートディレクトリ作成**
   - `report/attachment/2026-04-20_<HHMMSS>_qwen3-122b-c3-phaseSeval16s/`
   - ディレクトリ配下に `startup_logs/` と `prompts/` を作成

2. **S15 の添付物をコピー**（現カレント `report/attachment/2026-04-20_132400_qwen3-122b-c3-phaseSeval15s/`）
   - `start_phaseSeval15s.sh` → `start_phaseSeval16s.sh`
   - `batch_phaseSeval15s.sh` → `batch_phaseSeval16s.sh`
   - `run_all.sh` / `measure_phaseI.sh` → そのまま
   - `analyze_phaseSeval15s.py` → `analyze_phaseSeval16s.py`
   - `prompts/prompt_1k.txt` → コピー（Sbfine3 由来、6200 bytes）
   - `plan.md` → 新規作成（本ファイル相当）

3. **スクリプトの sed 書き換え**
   - `phaseSeval15s` → `phaseSeval16s` 全置換
   - `Seval15s_` → `Seval16s_` 全置換
   - `analyze_phaseSeval16s.py` の `PRIOR_TSVS` に S15 エントリ追加、S1-S15 を prior として扱い本 Phase を S16 として集計

4. **GPU ロック取得** (必須、CLAUDE.md の制約)
   - `bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100`

5. **バッチ実行**（所要 約 43 分）
   - `bash batch_phaseSeval16s.sh > batch_phaseSeval16s.log 2>&1`
   - 3 条件 × (起動 + warmup 2 + eval 5 + 停止) を順次実行

6. **集計・分析**
   - `python3 analyze_phaseSeval16s.py` → `phaseSeval16s_stats.csv` / `phaseSeval16s_verdict.txt` 生成
   - S15 同様の 16-session σ_pool / peak order / Welch t / mode 分類 / 崩壊頻度 Wilson CI

7. **GPU ロック解放**
   - `bash .claude/skills/llama-server/scripts/stop.sh t120h-p100`
   - `bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100`

8. **レポート作成** `report/2026-04-20_<HHMMSS>_qwen3-122b-c3-phaseSeval16s.md`
   - フォーマットは [REPORT.md](../../projects/llm-server-ops/REPORT.md) 準拠、S15 レポート構造を踏襲
   - **「未検証事項」と「検証完了後に実施すべき TODO」のセクションを必ず含める**（ユーザ明示指定）
   - 本プランで挙げた 6 つの仮説について結果を反映し、新たな仮説・優先 TODO を追加

## 検証方法

- 3 条件すべて起動成功（`/health` OK）・各 eval 5 run 完走（`predicted_n=256` 完走）
- `summary_phaseSeval16s.tsv` が 3 ub × (2 warmup + 5 eval) = 21 行で生成される
- `phaseSeval16s_verdict.txt` で 16-session verdict（range / σ / peak order / Welch t / mode 分類）が出力される
- compute buffer が 15 session と一致（ub=1586 で CUDA3=1558.12 MiB 等）

## 重要な参照ファイル

- 直前レポート本文: `report/2026-04-20_132400_qwen3-122b-c3-phaseSeval15s.md:377-573`（未検証事項・TODO）
- S15 バッチ: `report/attachment/2026-04-20_132400_qwen3-122b-c3-phaseSeval15s/batch_phaseSeval15s.sh`
- S15 起動: `report/attachment/2026-04-20_132400_qwen3-122b-c3-phaseSeval15s/start_phaseSeval15s.sh`
- S15 集計: `report/attachment/2026-04-20_132400_qwen3-122b-c3-phaseSeval15s/analyze_phaseSeval15s.py`
- レポート規約: `REPORT.md`
- GPU ロック / llama-server 起動: skill `gpu-server` / `llama-server`
