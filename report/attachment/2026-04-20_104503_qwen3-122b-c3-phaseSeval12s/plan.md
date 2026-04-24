# Plan: Phase S-eval-12session（第 12 セッション追加、n=12）

## Context

直前レポート Phase S-eval-11session（`report/2026-04-20_094934_qwen3-122b-c3-phaseSeval11s.md`）で **最優先かつ具体的に実施可能な項目**として、以下が明記されている（「検証完了後に実施すべき TODO」セクション line 730）:

> ★最重要: Phase S-eval-12session 候補 — ub=1586 Markov 崩壊予測 S12-S16 の検証、ub=1664 中帯 3 点 + 中-下間 1 点 の帯分離確定、ub=1584 Welch t not_sig 再現性、所要 40 分

本 Phase は S12 を実施し、S11 レポートの**★最優先未検証事項**を同時に前進させる:

1. **ub=1586 Markov 連鎖モデルの次崩壊予測 S12-S16** — S11 で境界値 15.048（崩壊閾値 15.0 の +0.048）に接近して非崩壊。Markov モデル（崩壊 20% / 復帰 100%）の S12 での継続支持を確認
2. **ub=1664 帯構造（4 モード分布）の再確認** — n=11 で下 5 / 中-下間 1 / 中 3 / 上 2 の 4 モード確定、S12 で中帯 vs 中-下間の帯分離確定（n=15-20 途中経過）
3. **ub=1584 pooled mean 収束性** — S11 で Welch t=+1.47 not_sig 初観測。pool mean 15.205 への収束兆候、S12 drift 方向検証
4. **ub=1664 Δ=+0.093 帯遷移ステップ再現性** — S2→S3 と S10→S11 の 2 例の帯間固有遷移ステップが再発するか
5. **peak order 残 2 種類** — 11 session で (1584,1664,1586) / (1586,1664,1584) が 0 観測、Wilson 上限 28.5% の絞り込み
6. **崩壊頻度 n=12 更新** — ub=1584 9.1% / ub=1586 18.2% / ub=1664 54.5% の Wilson CI 絞り込み
7. **pooled 60-run 統計 / σ_pool n=55→60 挙動**
8. **warmup ≒ eval 現象 ub 別独立 4 session 連続** — S9/S10/S11 で 3 session 連続立証済、S12 での継続性

条件は S11 と完全同一（fa=1、ctx=32768、OT=MoE-only、ub={1584,1586,1664}、warmup 2 + eval 5、cool 60 秒、1k prompt）。S11 の attachment をひな形として複製し、`11s` → `12s` 一括置換、analyze スクリプトの `PRIOR_TSVS` に S11 TSV を追加、`CUR_SESSION_LABEL` を `S12_phaseSeval12s` に変更する以外は変更なし。

## Key Files

### ひな形（複製元）

- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-20_094934_qwen3-122b-c3-phaseSeval11s/`
  - `start_phaseSeval11s.sh`
  - `batch_phaseSeval11s.sh`
  - `run_all.sh`
  - `measure_phaseI.sh`
  - `analyze_phaseSeval11s.py`
  - `prompts/prompt_1k.txt`
  - `plan.md`（参考用）

### 新規作成（S12 attachment ディレクトリ配下）

timestamp `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` を実行直前に取得し `<TS>_qwen3-122b-c3-phaseSeval12s/` を作成。

- `start_phaseSeval12s.sh` — tag `phaseSeval12s`、出力 dir prefix `out_Seval12s_`
- `batch_phaseSeval12s.sh` — 3 ub ループ、スクリプトファイル参照を `Seval12s` に更新
- `run_all.sh`、`measure_phaseI.sh` — ログ tag のみ更新（ロジック変更なし）
- `analyze_phaseSeval12s.py` — `PRIOR_TSVS` に S11 TSV を末尾追加、`CUR_SESSION_LABEL = "S12_phaseSeval12s"`、出力ファイル名を `12s` 仕様に、pooled 60-run 対応
- `plan.md` — 本プランを複製
- `prompts/prompt_1k.txt` — S11 からコピー（Phase Sbfine3 と同一、prompt_n=1085 tokens）

### スキル

- `.claude/skills/gpu-server/scripts/lock.sh t120h-p100` — ロック取得
- `.claude/skills/llama-server/scripts/stop.sh t120h-p100` — llama-server 停止
- `.claude/skills/gpu-server/scripts/unlock.sh t120h-p100` — ロック解放

## Steps

1. **GPU ロック取得**
   ```bash
   bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
   ```

2. **attachment ディレクトリ作成と S11 からの複製**
   ```bash
   TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
   DST="report/attachment/${TS}_qwen3-122b-c3-phaseSeval12s"
   mkdir -p "$DST/prompts"
   SRC="report/attachment/2026-04-20_094934_qwen3-122b-c3-phaseSeval11s"
   cp "$SRC/start_phaseSeval11s.sh" "$DST/start_phaseSeval12s.sh"
   cp "$SRC/batch_phaseSeval11s.sh" "$DST/batch_phaseSeval12s.sh"
   cp "$SRC/run_all.sh" "$DST/run_all.sh"
   cp "$SRC/measure_phaseI.sh" "$DST/measure_phaseI.sh"
   cp "$SRC/analyze_phaseSeval11s.py" "$DST/analyze_phaseSeval12s.py"
   cp "$SRC/prompts/prompt_1k.txt" "$DST/prompts/prompt_1k.txt"
   ```
   - ファイル内の `11s` → `12s`、`Seval11s` → `Seval12s`、`phaseSeval11s` → `phaseSeval12s` を一括置換（Edit tool で各ファイル確認しつつ置換）

3. **analyze_phaseSeval12s.py の調整**
   - `PRIOR_TSVS` 末尾に S11 TSV を追加:
     ```python
     ("S11_phaseSeval11s",
      SCRIPT_DIR.parent / "2026-04-20_094934_qwen3-122b-c3-phaseSeval11s" / "summary_phaseSeval11s.tsv"),
     ```
   - `CUR_SESSION_LABEL = "S12_phaseSeval12s"`
   - Welch t の比較対象 prior pool を 11-session に変更（55-run）、現 S12 と対比
   - pooled 60-run 統計、11-session verdict → 12-session verdict

4. **バッチ実行（約 37 分）**
   ```bash
   cd "$DST"
   bash batch_phaseSeval12s.sh > batch_phaseSeval12s.log 2>&1
   ```
   - 3 ub × (warmup 2 + eval 5) = 21 run、cool 60 秒
   - 各 ub で llama-server 起動 → health → warmup 2 → eval 5 → 停止

5. **analyze 実行**
   ```bash
   python3 analyze_phaseSeval12s.py
   ```
   - 出力: `summary_phaseSeval12s.tsv` / `phaseSeval12s_stats.csv` / `phaseSeval12s_verdict.txt`

6. **llama-server 停止 + GPU ロック解放**
   ```bash
   bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
   bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
   ```

7. **レポート作成**
   - `report/<TS>_qwen3-122b-c3-phaseSeval12s.md` を S11 レポート構造に準拠して作成
   - 必須セクション: 添付ファイル、参照、前提・目的、判定しきい値、成功条件、環境情報、セッション間隔表（S1-S12）、再現方法、実行結果サマリ（1〜15 相当）、再現性分析と解釈、採用判定、**未検証事項**、**検証完了後に実施すべき TODO**、補足
   - 未検証事項は S11 の項目を継承、本 Phase で潰した項目に `[x]`、新規項目を末尾に追加
   - 検証完了後 TODO も同様に S11 から継承、本 Phase 実施項目に `[x]`

## Verification

- [ ] 3 条件すべて起動成功（compute buffer CUDA0=980.36 / CUDA1=452.31 / CUDA2=452.31 / CUDA3=1558.12 / Host=235.48 MiB が S11 と完全一致すること）
- [ ] 各条件 eval 5 run の eval_tps が欠損なく取得できている
- [ ] 12-session range / σ_session の算出（n=12）
- [ ] Welch t（prior 11-session pool vs S12）で 3 ub の有意差判定
- [ ] pooled 60-run 統計の算出
- [ ] ub=1586 Markov 予測: S12 で崩壊 or 非崩壊のいずれか観測し Markov モデル継続/再考
- [ ] ub=1664 帯分布: S12 で中帯 / 中-下間 / 下帯 / 上帯 のどのモードに落ちるか
- [ ] peak order 12 session 集計（残 2 種類の初観測または 0 継続、Wilson 上限更新）
- [ ] ub=1584 pool mean 収束: Welch t not_sig が継続するか / drift 方向
- [ ] GPU ロック取得・解放の正常動作

## Out of Scope

- analyze_phaseSeval{N}s.py の汎用化（★中優先、未検証事項から継続、別 Phase）
- 単独 ub 連続実行系（ub1664-midband / ub1586-markov / ub1584-converge、別 Phase）
- cool time 変動スキャン（Phase S-eval-cooltime-scan 候補、別 Phase）
- cold boot / nextday / prompt size 依存性（別 Phase）
