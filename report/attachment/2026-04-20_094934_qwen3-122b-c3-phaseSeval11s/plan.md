# Plan: Phase S-eval-11session（第 11 セッション追加、n=11）

## Context

直前レポート Phase S-eval-10session（2026-04-20_085556）では、「未検証事項」および「検証完了後に実施すべき TODO」の**新規項目で最重要**として **Phase S-eval-11session** が明記されている（line 704）:

> ★最重要: Phase S-eval-11session 候補 — ub=1586 崩壊-復帰 Markov 連鎖の次崩壊 S11-S13 予測、ub=1664 帯分布の中-下帯間頻度、所要 40 分

本 Phase はこれを実施し、次の**最優先**未検証事項を同時に前進させる:

1. **ub=1586 崩壊-復帰 Markov 連鎖モデル** — S6→S7 / S9→S10 の 2 周期目復帰（100%）・崩壊確率 20% 単純 Markov 連鎖の S11 予測検証
2. **ub=1664 帯構造の再定義** — S10 14.945 の「中-下帯間」新位置が再現するか（3 帯 vs 4 帯 vs 連続多峰の判定へ 1 点追加）
3. **peak order 残 2 種類** — (1584,1664,1586) / (1586,1664,1584) が 10 session で 0 観測、Wilson 上限 30.8% の絞り込み
4. **ub=1664 の 2 位観測** — 10 session で 0/10、Wilson 上限 30.8% を n=11 で更新
5. **崩壊頻度の n=11 更新** — ub=1584 10%、ub=1586 20%、ub=1664 60% の Wilson CI 絞り込み
6. **pooled 55-run 統計 / σ_pool の n=50→55 挙動**
7. **Welch t（prior 10-session pool vs S11）** — ub=1664 S10 初 not_sig の次発展
8. **warmup ≒ eval 現象の ub 別独立制御** — S10 で ub=1584 のみ復帰、S11 での切替パターン

条件は S10 と完全同一（fa=1、ctx=32768、OT=MoE-only、ub={1584,1586,1664}、warmup 2 + eval 5、cool 60 秒）。S10 の attachment をひな形として複製し、`10s` → `11s` 一括置換、analyze スクリプトの `PRIOR_TSVS` に S10 TSV を追加、`CUR_SESSION_LABEL` を `S11_phaseSeval11s` に変更する以外は変更なし。

## Key Files

### ひな形（複製元）

- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-20_085556_qwen3-122b-c3-phaseSeval10s/start_phaseSeval10s.sh`
- 同上 `batch_phaseSeval10s.sh`、`run_all.sh`、`measure_phaseI.sh`、`analyze_phaseSeval10s.py`、`plan.md`、`prompts/prompt_1k.txt`

### 新規作成（S11 attachment ディレクトリ配下）

timestamp `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` を実行直前に取得し `<TS>_qwen3-122b-c3-phaseSeval11s/` を作る。

- `start_phaseSeval11s.sh` — tag `phaseSeval11s`、出力 dir prefix `out_Seval11s_`
- `batch_phaseSeval11s.sh` — 3 ub ループ、スクリプトファイル参照を `Seval11s` に更新
- `run_all.sh`、`measure_phaseI.sh` — ログ tag のみ更新（ロジック変更なし）
- `analyze_phaseSeval11s.py` — `PRIOR_TSVS` に S10 TSV を末尾追加、`CUR_SESSION_LABEL = "S11_phaseSeval11s"`、出力ファイル名を `11s` 仕様に
- `plan.md` — 本プランを複製、S11 の実施記録として利用
- `prompts/prompt_1k.txt` — S10 からコピー（Phase Sbfine3 と同一、prompt_n=1085 tokens）

### スキル

- `.claude/skills/gpu-server/scripts/lock.sh t120h-p100` — ロック取得
- `.claude/skills/llama-server/scripts/stop.sh t120h-p100` — llama-server 停止
- `.claude/skills/gpu-server/scripts/unlock.sh t120h-p100` — ロック解放

## Steps

1. **GPU ロック取得**
   - `bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100`

2. **attachment ディレクトリ作成と S10 からの複製**
   - `TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)` を取得
   - `mkdir -p report/attachment/${TS}_qwen3-122b-c3-phaseSeval11s`
   - S10 attachment からスクリプト 6 本 + `prompts/prompt_1k.txt` を複製
   - ファイル名 / 内部参照 / ログ tag を `10s` → `11s`、`Seval10s` → `Seval11s`、`phaseSeval10s` → `phaseSeval11s` で一括置換

3. **analyze_phaseSeval11s.py の調整**
   - `PRIOR_TSVS` 末尾に S10 TSV を追加:
     ```python
     ("S10_phaseSeval10s",
      SCRIPT_DIR.parent / "2026-04-20_085556_qwen3-122b-c3-phaseSeval10s" / "summary_phaseSeval10s.tsv"),
     ```
   - `CUR_SESSION_LABEL = "S11_phaseSeval11s"`
   - Welch t prior 10-session pool vs S11 に更新
   - pooled 55-run 統計、10-session verdict → 11-session verdict

4. **バッチ実行（約 37 分）**
   - `cd report/attachment/${TS}_qwen3-122b-c3-phaseSeval11s`
   - `bash batch_phaseSeval11s.sh > batch_phaseSeval11s.log 2>&1`
   - 3 ub × (warmup 2 + eval 5) = 21 run、cool 60 秒

5. **analyze 実行**
   - `python3 analyze_phaseSeval11s.py`
   - 出力: `summary_phaseSeval11s.tsv` / `phaseSeval11s_stats.csv` / `phaseSeval11s_verdict.txt`

6. **llama-server 停止 + GPU ロック解放**
   - `bash .claude/skills/llama-server/scripts/stop.sh t120h-p100`
   - `bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100`

7. **レポート作成**
   - `report/<TS>_qwen3-122b-c3-phaseSeval11s.md` を S10 レポート構造に準拠して作成
   - 必須セクション: 前提・目的、判定しきい値、成功条件、環境情報、セッション間隔表（S1-S11）、再現方法、実行結果サマリ（1〜15 相当）、再現性分析と解釈、採用判定、**未検証事項**、**検証完了後に実施すべき TODO**、補足
   - 未検証事項は S10 の項目を継承、本 Phase で潰した項目に `[x]`、新規項目を末尾に追加

## Verification

- [ ] 3 条件すべて起動成功（compute buffer CUDA0=980.36 / CUDA1=452.31 / CUDA2=452.31 / CUDA3=1558.12 / Host=235.48 MiB が S10 と完全一致すること）
- [ ] 各条件 eval 5 run の eval_tps が取得できている（欠損なし）
- [ ] 11-session range / σ_session の算出（n=11）
- [ ] Welch t（prior 10-session pool vs S11）で 3 ub の有意差判定
- [ ] pooled 55-run 統計の算出
- [ ] ub=1586 崩壊予測: 復帰後の S11 は通常動作（崩壊なし）が Markov 連鎖モデル予測、崩壊すれば復帰 → 即再崩壊の新パターンで Markov モデル再考
- [ ] ub=1664 帯分布: S10 14.945 の中-下帯間が S11 で再現するか / 別の帯に落ちるか
- [ ] peak order 11 session 集計（残 2 種類の初観測または 0 継続）
- [ ] GPU ロック取得・解放の正常動作

## Out of Scope

- analyze_phaseSeval{N}s.py の汎用化（★中優先、未検証事項から継続、別 Phase）
- 単独 ub 連続実行系（ub1664-deepband / ub1586-markov / ub1584-stable、別 Phase で扱う）
- cool time 変動スキャン（Phase S-eval-cooltime-scan 候補、別 Phase）
