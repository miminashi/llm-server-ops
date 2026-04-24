# Phase S-eval-13session 実施計画

## Context

直前レポート `report/2026-04-20_104503_qwen3-122b-c3-phaseSeval12s.md` の「検証完了後に実施すべき TODO」の筆頭 **★最重要: Phase S-eval-13session 候補** を実施する。S12 終了 (11:25) から約 2 時間経過しており、新規 S13（第 13 session）を追加計測する。

## 目的（S12 で残された未検証事項への前進）

1. **ub=1586「崩壊境界値プラトー」の継続性**（S11 15.048 → S12 15.059 Δ=+0.011）
   - S13 で 3 session 連続プラトーか、再崩壊か、上方離脱か
2. **ub=1664 中帯再出現の有無**（S12 で 14.721 下帯再崩壊、中帯は一過性仮説）
3. **ub=1584 pool 中心 drift 方向検証**（S11→S12 で -0.006 微下降）
4. **崩壊頻度 n=13 更新**（ub=1584 / 1586 / 1664）
5. **peak order mode A 独走拡大の継続**（S12 で 6/12、mode B 4/12 比 +2 差）
6. **pooled 65-run 統計 / σ_pool n=60→65 挙動**
7. **Welch t 3 ub 同方向 drift の再現性**（S12 で 3 ub 全 significant、初観測パターン）

## アプローチ

S12 の構成を 100% 流用（ctx=32768、fa=1、OT=MoE-only、ub={1584, 1586, 1664} × warmup 2 + eval 5）。スクリプトは「12s」→「13s」置換のみ。既存の PRIOR_TSVS に S12 summary を追加。

## 実施手順

### 1. 作業ディレクトリ作成
- `report/attachment/2026-04-20_{HHMMSS}_qwen3-122b-c3-phaseSeval13s/` を作成
- サブディレクトリ: `startup_logs/`、`prompts/`

### 2. スクリプト準備（S12 からコピー・リネーム）
以下を S12 ディレクトリからコピーし、ファイル内の "12s" → "13s"、"Seval12s" → "Seval13s"、"phaseSeval12s" → "phaseSeval13s" に置換:
- `start_phaseSeval12s.sh` → `start_phaseSeval13s.sh`
- `batch_phaseSeval12s.sh` → `batch_phaseSeval13s.sh`
- `run_all.sh` → `run_all.sh`（置換不要）
- `measure_phaseI.sh` → `measure_phaseI.sh`（置換不要）
- `analyze_phaseSeval12s.py` → `analyze_phaseSeval13s.py`
  - PRIOR_TSVS に `S12_phaseSeval12s` エントリを追加
  - CUR_SESSION_LABEL を `S13_phaseSeval13s` に変更
  - MODE_GROUPS に `prev_S12` を追加、`cur_S13` に変更
- `prompts/prompt_1k.txt` → 同一ファイルをコピー（prompt_n=1085 tokens を保持）

### 3. GPU ロック取得
```bash
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 4. バッチ実行（約 37 分）
```bash
cd report/attachment/2026-04-20_{HHMMSS}_qwen3-122b-c3-phaseSeval13s/
bash batch_phaseSeval13s.sh > batch_phaseSeval13s.log 2>&1
```

### 5. 分析実行
```bash
python3 analyze_phaseSeval13s.py
```
生成物: `summary_phaseSeval13s.tsv`、`phaseSeval13s_stats.csv`、`phaseSeval13s_verdict.txt`

### 6. llama-server 停止・GPU ロック解放
```bash
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 7. レポート作成
ファイル: `report/2026-04-20_{HHMMSS}_qwen3-122b-c3-phaseSeval13s.md`

**必須セクション**（本質部分）:
- 前提・目的（S12 で残された TODO / 未検証事項を引用）
- 再現方法
- 実行結果サマリ（5-run pivot、12→13 比較、崩壊頻度、peak order、pooled 65-run 統計、Welch t）
- 前 Phase S12 との対照表
- **未検証事項** セクション（S12 のリストをベースに、S13 で潰したものに [x]、新規で判明したものを追加）
- **検証完了後に実施すべき TODO** セクション（S13 候補で潰したものに [x]、次の Phase 候補を追加）
- 補足

### 8. REPORT.md の更新
- 最新レポートへの参照を追加

### 9. Discord 通知（スキル `discord-notify` 使用）

## 判定しきい値（S12 から踏襲）
- fully_independent: 13-session range ≤ 0.02 t/s
- partial_drift: range ≤ 0.10 t/s
- session_dominated: range > 0.10 t/s
- 崩壊判定: eval_mean < 15.0 t/s（3 ub 共通）

## 成功条件
- [ ] 3 条件すべて起動成功
- [ ] 各条件 eval 5 run の eval_tps 取得
- [ ] 13-session range / σ_session の算出（n=13）
- [ ] Welch t（prior 12-session pool vs S13）で有意差判定
- [ ] ピーク ub 順序の 13 session 安定性確認
- [ ] pooled 65-run 統計の算出
- [ ] 3 ub の崩壊頻度カウント
- [ ] GPU ロック取得・解放の正常動作
- [ ] レポートの「未検証事項」「検証完了後に実施すべき TODO」セクション更新

## 検証（end-to-end）
- llama-server 起動成功: `curl -sf http://10.1.4.14:8000/health`
- 各 ub の eval 5 run 完走: `out_Seval13s_fa1_ctx32768_ub{UB}_1k/` に 5 JSON
- 分析スクリプトが `phaseSeval13s_verdict.txt` を生成
- GPU ロックが解放されたことを確認: `bash .claude/skills/gpu-server/scripts/status.sh t120h-p100`

## 所要時間の見積り
- 環境準備（スクリプトコピー・置換）: 3 分
- GPU ロック取得 + 起動: 2 分
- バッチ実行（3 条件）: 約 37 分
- 分析・レポート作成: 15-20 分
- 合計: 約 60 分（うち GPU ロック占有 40 分）

## 対象ファイル（新規作成）
- `report/attachment/2026-04-20_{HHMMSS}_qwen3-122b-c3-phaseSeval13s/` 配下一式
- `report/2026-04-20_{HHMMSS}_qwen3-122b-c3-phaseSeval13s.md`
- `REPORT.md` 更新（インデックス追記）

## 参照
- 直前レポート: `report/2026-04-20_104503_qwen3-122b-c3-phaseSeval12s.md`
- 再利用スクリプト: `report/attachment/2026-04-20_104503_qwen3-122b-c3-phaseSeval12s/` 配下
- プロンプト: S12 の `prompts/prompt_1k.txt`（1085 tokens、Phase Sbfine3 から継続）
