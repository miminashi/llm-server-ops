# Phase S-eval-15session 実施計画

## Context

直前レポート `report/2026-04-20_123152_qwen3-122b-c3-phaseSeval14s.md` の「検証完了後に実施すべき TODO」筆頭 **★最重要: Phase S-eval-15session 候補** を実施する。S14 終了 (13:11 JST) から 14-20 分間隔を維持し、第 15 session (S15) を追加計測する。S14 で S13 の 5 大異常が全て 1 session 限定で回帰したことが確認されたため、S15 で以下複数の ★最優先項目を一度に進捗させる。

## 目的（S14 で残された ★最優先 未検証事項への前進）

1. **ub=1586 peak 1 位 3 連続性検証** — S13/S14 で ub=1586 peak 1 位 2 連続 (14 session 初)。S15 で 3 連続継続なら 1586 優勢化確定、mode_A 復帰 (1584 peak) なら単発揺らぎ。
2. **pool mean 1584-1586 差 +0.010 の収束先** — S13 +0.017 → S14 +0.010 の連続縮小。S15 で逆転 (負値) or mode_A 回帰で拡大 (+0.015 以上)。
3. **ub=1664 「中帯→下帯」翌 session 復帰 3 回目再現後の挙動** — S13/S14 3 回目再現済。S15 で連続下帯 or 再び中帯へ振動。
4. **ub=1584 崩壊 9-session 周期仮説の追跡** — S4 / S13 間隔 9、次予測 S22。S15 は通過点 (周期内 sub-1)、15.0 以上で正常維持が期待。
5. **warmup1「帯 B + delta A」2 軸切替モデルの検証** — S14 単独 (B,A) 観測。S15 で (A,A)/(B,B)/(C,C) 同値復帰なら S14 は揺らぎ、(B,A)/(A,B) 再出現なら独立切替モデル強化。
6. **Welch t 3 ub sig 出現頻度** — n=14 で S13 のみ 3 ub sig (1/14=7.1%)。S15 で再出現なら高頻度、0 ub sig なら S13 は 1/15 限定。
7. **σ_pool 3 ub 同時縮小の継続** — S13 同時拡大 → S14 同時縮小の反転。n=15 で long-term 収束 or 交互 drift 判定。
8. **Welch t / peak order mode_B 急増の継続性** — S14 で mode_B 5 回、mode_A 6 回との差 1 回。S15 で逆転可能性。
9. **崩壊頻度 n=15 更新** — ub=1584 / 1586 / 1664 の Wilson CI 再計算。
10. **pooled 75-run 統計** — 全 ub の mean / stdev / σ_pool 更新、σ_pool / σ_run_avg 比の n=75 挙動。

## アプローチ

S14 の構成を 100% 流用（ctx=32768、fa=1、OT=MoE-only、ub={1584, 1586, 1664} × warmup 2 + eval 5）。スクリプトは "14s" → "15s" 置換のみ。`analyze_phaseSeval15s.py` の `PRIOR_TSVS` に S14 summary を追加。

### セッション間隔方針
- S14 終了 13:11 JST、現在 13:21 JST、**13:25 以降開始** (14 分経過) で S13→S14 と同帯 cool time を維持。
- Cool time 14 分継続 → S14 との連続性担保、cool time 15-18 分で S10-S13 帯にも一致。

## 実施手順

### 1. 作業ディレクトリ作成
- タイムスタンプ取得: `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`
- `report/attachment/{TS}_qwen3-122b-c3-phaseSeval15s/` を作成
- サブディレクトリ: `startup_logs/`、`prompts/`

### 2. スクリプト準備（S14 からコピー・リネーム）
S14 ディレクトリ `report/attachment/2026-04-20_123152_qwen3-122b-c3-phaseSeval14s/` からコピーし、ファイル内の "14s" → "15s"、"Seval14s" → "Seval15s"、"phaseSeval14s" → "phaseSeval15s" に置換:
- `start_phaseSeval14s.sh` → `start_phaseSeval15s.sh`（REMOTE_LOG prefix 変更のみ）
- `batch_phaseSeval14s.sh` → `batch_phaseSeval15s.sh`
- `run_all.sh`（置換不要、そのままコピー）
- `measure_phaseI.sh`（置換不要、そのままコピー）
- `analyze_phaseSeval14s.py` → `analyze_phaseSeval15s.py`
  - `PRIOR_TSVS` に `S14_phaseSeval14s` エントリを追加（14 タプル → 15 タプル前、 prior=14 session）
  - `CUR_SESSION_LABEL = "S15_phaseSeval15s"` に変更
  - `MODE_GROUPS` に `prev_S14` を追加、`cur_S15` に変更
  - 出力ファイル名 / 表記 "14" → "15"、"70-run" → "75-run"、"Prior 13-session" → "Prior 14-session" 等
- `prompts/prompt_1k.txt` → S14 と同一ファイルをコピー（prompt_n=1086 tokens 維持）

### 3. GPU ロック取得
```bash
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 4. バッチ実行（約 37 分）
```bash
cd report/attachment/{TS}_qwen3-122b-c3-phaseSeval15s/
bash batch_phaseSeval15s.sh > batch_phaseSeval15s.log 2>&1
```

### 5. 分析実行
```bash
python3 analyze_phaseSeval15s.py
```
生成物: `summary_phaseSeval15s.tsv`、`phaseSeval15s_stats.csv`、`phaseSeval15s_verdict.txt`

### 6. llama-server 停止・GPU ロック解放
```bash
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 7. レポート作成
ファイル: `report/{TS}_qwen3-122b-c3-phaseSeval15s.md`

**必須セクション**:
- 添付ファイル（実装プラン、スクリプト、ログ、分析結果）
- 参照（S14 以前のセッションリンク）
- 前提・目的（S14 の ★最優先 TODO を引用、本 Phase で検証する項目明示）
- 判定しきい値 / 成功条件
- 環境情報（S14 と同一）
- セッション間隔表（S1-S15 の 15 行）
- 再現方法
- 実行結果サマリ
  - 5-run pivot（S15）
  - 15 session mean 時系列
  - 1-run ref 再現性
  - peak ub 順序の 15-session 集計
  - prior 14-session pool vs S15 Welch t
  - Pooled 75-run 統計
  - run 1 外れ値チェック
  - ub 間有意差
  - 15-session verdict
  - 崩壊頻度 n=15
  - ub 別時系列パターン（1664/1586/1584）
  - peak 1 位 ub 出現頻度
  - モード分類比較
  - warmup1 ub=1584 帯 + delta 判定
  - prompt_tps 要約
- 前 Phase S14 との対照
- **未検証事項**: S14 のリストをベースに、S15 で潰したものに [x]、新規を追加
- **検証完了後に実施すべき TODO**: S14 候補で潰したものに [x]、次 Phase 候補を追加
- 補足（核心発見 / 作業終了時点の状態）

### 8. REPORT.md の更新
- 最新レポート行を S14 → S15 に置換（インデックス追記）

### 9. Discord 通知（スキル `discord-notify` 使用）
レポート URL を通知。

## 判定しきい値（S14 から踏襲）
- fully_independent: 15-session range (max−min) ≤ 0.02 t/s
- partial_drift: range ≤ 0.10 t/s
- session_dominated: range > 0.10 t/s
- 崩壊判定: eval_mean < 15.0 t/s（3 ub 共通）

## 成功条件
- [ ] 3 条件すべて起動成功（/health OK）
- [ ] 各条件 eval 5 run の eval_tps 取得（3 × 5 = 15 JSON）
- [ ] 15-session range / σ_session の算出（n=15）
- [ ] Welch t（prior 14-session pool vs S15）で有意差判定
- [ ] ピーク ub 順序の 15-session 集計
- [ ] pooled 75-run 統計の算出
- [ ] 3 ub の崩壊頻度カウント + Wilson 95% CI
- [ ] GPU ロック取得・解放の正常動作
- [ ] レポートの「未検証事項」「検証完了後に実施すべき TODO」セクション更新

## 検証（end-to-end）
- llama-server 起動成功: `curl -sf http://10.1.4.14:8000/health`
- 各 ub の eval 5 run 完走: `out_Seval15s_fa1_ctx32768_ub{UB}_1k/` に 5 JSON
- 分析スクリプトが `phaseSeval15s_verdict.txt` を生成
- 15 session mean 時系列が 3 ub すべてで 15 列を出力
- GPU ロックが解放されたことを確認: `bash .claude/skills/gpu-server/scripts/status.sh t120h-p100`

## 所要時間の見積り
- 環境準備（スクリプトコピー・置換）: 3 分
- GPU ロック取得 + 起動: 2 分
- バッチ実行（3 条件 × warmup 2 + eval 5）: 約 37 分
- 分析・レポート作成: 20 分
- 合計: 約 65 分（うち GPU ロック占有 約 40 分）

## 対象ファイル（新規作成）
- `report/attachment/{TS}_qwen3-122b-c3-phaseSeval15s/`
  - `start_phaseSeval15s.sh`
  - `batch_phaseSeval15s.sh`
  - `run_all.sh`
  - `measure_phaseI.sh`
  - `analyze_phaseSeval15s.py`
  - `prompts/prompt_1k.txt`
  - `plan.md`（本ファイルをコピー）
- `report/{TS}_qwen3-122b-c3-phaseSeval15s.md`
- `REPORT.md` 更新

## 参照（再利用ソース）
- 直前レポート: `report/2026-04-20_123152_qwen3-122b-c3-phaseSeval14s.md`
- 再利用スクリプト: `report/attachment/2026-04-20_123152_qwen3-122b-c3-phaseSeval14s/` 配下
- プロンプト: S14 の `prompts/prompt_1k.txt`（1086 tokens、Phase Sbfine3 から継続）

## 注意点（S14 運用で確認された落とし穴）
- `batch_phaseSeval*.sh` は `$SCRIPT_DIR` に `cd` するので、プロジェクトルートからフルパス実行でも相対参照 OK。
- `start_phaseSeval*.sh` は `ssh -f` で起動後、`/health` ポーリング 300s。OOM / -ub 拒否パターンを正規表現で検出。
- `stop.sh` 後に 5s sleep で PID 解放待機。
- cool time は stdout log の timestamp で実測する（batch 開始・終了時刻を記録）。

## S15 で追加すべき未検証項目の候補（レポート作成時に更新）
- ub=1586 peak 1 位 3 連続時の pool 差の挙動
- ub=1664 中帯/下帯の時系列 autocorrelation（15 session 以上必要）
- warmup1 帯 × delta × peak_order の 3 軸独立性の Chi-square 検定
- 15 session で 6 種類目 peak order (1584,1664,1586) が出現するか
