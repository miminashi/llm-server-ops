# Phase S-eval-19session 実施計画

## Context

直前レポート `report/2026-04-20_161642_qwen3-122b-c3-phaseSeval18s.md` の「未検証事項」★最優先項目の筆頭は **Phase S-eval-19session 候補**。S18 は「ub=1584 崩壊 3 session 連続 + ub=1664 上帯 2 連続 + mode_D 10 session ぶり再発 + Welch t 3 ub 同時 sig 2 session 連続」の 4 大事件同時観測で、S19 での連続 / 復帰は複数仮説を同時検証できる。

S19 で同時に検証する仮説:
1. **ub=1584 崩壊間隔単調減少 {9,2,2,1}** — 次崩壊 S19 は 1 session ギャップ (連続崩壊 4 連続) or 非崩壊か。「崩壊帯吸引子」仮説の検証。
2. **ub=1664 上帯 3 連続 or 下/中帯復帰** — 上帯 Markov 自己遷移確率 p(上|上) の初推定値 1/3 を改訂、3 連続なら steady-state 推定精度向上。
3. **ub=1586 peak 1 位 3 連続失敗 or 復帰** — S17/S18 で 2 連続 2 位、S19 復帰で「1 位頻度 45%±」確定、3 連続失敗ならモード構造変化を示唆。
4. **mode_D/C/E 再発周期性（10-11 session）** — S19 モード次第で「副モード周期」の観測継続。
5. **Welch t 3 ub sig 3 連続 or 収束** — S17→S18 連続から S19 で途切れる or 3 連続の初観測。
6. **cool time の影響** — S18 終了 17:03 から S19 開始 21:21+ で cool time 約 4 時間 18 分、これまでの 13-14 分帯から大幅逸脱、初の「intra-day 長時間帯」cool time session。

この観測自体が「cool time sensitivity」仮説（新規項目 ★高優先）に直接寄与する。

## アプローチ

既存 S18 のスクリプト群をそのまま流用（Phase S-eval / cross / 3s 〜 18s と **完全同一条件** で反復計測することが S-eval series の本質）。変更するのはファイル名・TAG prefix・PRIOR_TSVS の 1 行追加のみ。

### 同一条件（変更なし）

- **GPU サーバ**: t120h-p100、P100×4
- **起動パラメータ**: fa=1 / f16 KV / ctx=32768 / numactl cpunodebind=1 membind=1 / threads=40 / poll=0 / ngl=999
- **OT_REGEX**: `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
- **ub**: {1584, 1586, 1664} 3 条件固定
- **warmup**: 2 run（短 prompt haiku）
- **eval**: 5 run × (prompt=1k, max_tokens=256)
- **cooldown**: run 間 60 秒
- **prompt**: S1-S18 と同一 `prompts/prompt_1k.txt`（6200 bytes / 1086 tokens）、`[Request ID <uniq>] ` prefix で cache hit 回避

### 成果物ディレクトリ

`report/attachment/2026-04-20_{HHMMSS}_qwen3-122b-c3-phaseSeval19s/` 以下に:
- `plan.md`（本計画の要約）
- `start_phaseSeval19s.sh`（S18 を sed 置換: `18s`→`19s`, `18session`→`19session`）
- `batch_phaseSeval19s.sh`（同上）
- `run_all.sh` / `measure_phaseI.sh`（そのままコピー）
- `analyze_phaseSeval19s.py`（S18 の `PRIOR_TSVS` に S18 TSV 1 行追加 + `CUR_SESSION_LABEL` を `S19_phaseSeval19s` に変更、`MODE_GROUPS` 等のラベルは S18 分を `prev_S18` に移す）
- `prompts/prompt_1k.txt`（S18 のコピー）
- 実行後: `summary_phaseSeval19s.tsv` / `phaseSeval19s_stats.csv` / `phaseSeval19s_verdict.txt` / 各種 log

### 実行フロー

```bash
# 1. GPU ロック取得
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 2. 作業ディレクトリ作成・ファイル生成
TS=$(date +%Y-%m-%d_%H%M%S)
mkdir -p report/attachment/${TS}_qwen3-122b-c3-phaseSeval19s/{prompts,startup_logs}
# S18 から流用 + 必要箇所を sed / 手動編集

# 3. バッチ実行（所要 約 45 分）
cd report/attachment/${TS}_qwen3-122b-c3-phaseSeval19s/
bash batch_phaseSeval19s.sh > batch_phaseSeval19s.log 2>&1

# 4. 分析
python3 analyze_phaseSeval19s.py

# 5. ロック解放
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 参照・再利用する既存ファイル

- **S18 スクリプト一式**: `report/attachment/2026-04-20_161642_qwen3-122b-c3-phaseSeval18s/` — `start_phaseSeval18s.sh`, `batch_phaseSeval18s.sh`, `run_all.sh`, `measure_phaseI.sh`, `analyze_phaseSeval18s.py`, `prompts/prompt_1k.txt`
- **GPU ロック**: `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- **llama-server 停止**: `.claude/skills/llama-server/scripts/stop.sh`
- **過去 S1-S18 summary TSV**: 各 `report/attachment/2026-04-20_*_qwen3-122b-c3-phaseSeval*s/summary_phaseSeval*s.tsv`（analyze スクリプトが参照）

## 判定しきい値（S18 と同一）

- fully_independent: 19-session range (max−min) ≤ 0.02 t/s
- partial_drift: range ≤ 0.10 t/s
- session_dominated: range > 0.10 t/s
- 崩壊判定: eval_mean < 15.0 t/s
- ub=1664 帯分類: 下帯 < 14.80、中帯 14.80-15.20、上帯 > 15.20
- Welch sig: |t| ≥ 2.0

## レポート構成（REPORT.md に従う）

作成先: `report/2026-04-20_{HHMMSS}_qwen3-122b-c3-phaseSeval19s.md`

セクション:
1. 見出し（S18 と同形式）
2. 実施日時 / 作業種別 / GPU ロック
3. 添付ファイル
4. 参照
5. 前提・目的（S18 → S19 の仮説リスト）
6. 判定しきい値 / 成功条件
7. 環境情報 / セッション間隔（**cool time 約 4 時間 18 分 = 長時間帯初観測**を明記）
8. 再現方法
9. 実行結果サマリ（S18 と同項目 #1-#12）
10. **未検証事項**（S18 の既知項目を引き継ぎ + S19 新規項目）
11. **検証完了後に実施すべき TODO**（同上）
12. 補足（S19 の核心発見サマリ）

## 検証方法（end-to-end）

1. バッチ実行中に `curl http://10.1.4.14:8000/health` で health 確認
2. バッチ完了後に `summary_phaseSeval19s.tsv` に 3 ub × 7 run（warmup 2 + eval 5）= 21 行の TSV が存在
3. `analyze_phaseSeval19s.py` 実行で `phaseSeval19s_verdict.txt` に 19-session 統計・Welch t・peak order 出力
4. pooled 95-run (5 run × 19 session) 統計が算出されていること
5. 本番レポート md ファイルに必須セクション（未検証事項・TODO）が揃っていること

## リスク・注意点

- **長 cool time (4 時間)** で何らかの異常（GPU 温度低下、DRAM refresh 等）が初回に発生する可能性。S17→S18 が 14 分、S19 は 4+ 時間で不連続。初の観測点として価値がある反面、異常値が出ても「長 cool time 効果」として記録する。
- GPU ロック必須（CLAUDE.md 制約）。
- sudo は使用しない（起動・停止・評価スクリプトは sudo 不要で動作）。
