# Phase S-eval-4session 実施プラン

## Context

直前 Phase S-eval-3session（2026-04-20_022922）の ★最重要 新規 TODO 筆頭として **Phase S-eval-4session 候補** が残置されている。

**背景・問題**:
- Phase S-eval-cross-session (n=2) では ub=1586 を Δ=+0.016 で "session_independent" と判定
- **Phase S-eval-3session (n=3) で ub=1586 の verdict が partial_drift へ降格**（S3 で −0.050 下振れ、range=0.058）
- ub=1664 は 3 session 単調増加（14.646 → 15.042 → 15.135）の片側ドリフト兆候
- ub=1586 は pooled σ が n=10 時 0.010 → n=15 時 0.026 と 2.6 倍拡大

**問い**: n=3 でも verdict が覆ったため、n=4 で σ_session がさらに動くか、ub=1664 単調増加が漸近・反転するか、ピーク順序 1586 vs 1664 (S3 差 +0.011) が逆転するかを検証する。所要目安 50 分。

**本 Phase の成果物**: 4 session range / σ_session / pooled 20-run 統計、S1+S2+S3 pool (n=15) vs S4 (n=5) の Welch t、3-session → 4-session 時の verdict 遷移表。

## スコープ

- Phase S-eval-3session と **完全同条件**（ctx=32768, fa=1, ub={1584, 1586, 1664}, OT=MoE-only, threads=40, poll=0, numactl node1, warmup 2 + eval 5）で **第 4 session (S4) を 1 回** 実行
- ub 配列は 3 点据え置き（新 ub は導入しない）
- 既存 S3 スクリプトを流用して「Seval3s → Seval4s」リネーム、analyze に S3 TSV を prior 追加
- cold-boot / 翌日計測 / ub 境界細密スキャン / tensor-dump は別 Phase 扱い（本 Phase では実施しない）

## 作業手順

### 1. 準備

1. GPU ロック取得: `bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100`
2. タイムスタンプ取得: `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` → 以後 `${TS}`
3. 添付ディレクトリ作成: `report/attachment/${TS}_qwen3-122b-c3-phaseSeval4s/{startup_logs,prompts}`
4. プランコピー: `cp /home/ubuntu/.claude/plans/todo-tidy-oasis.md report/attachment/${TS}_qwen3-122b-c3-phaseSeval4s/plan.md`

### 2. スクリプト複製（流用元: `report/attachment/2026-04-20_022922_qwen3-122b-c3-phaseSeval3s/`）

以下は **コピー後 `Seval3s` → `Seval4s` 文字列置換のみ** で済む:
- `batch_phaseSeval3s.sh` → `batch_phaseSeval4s.sh`（`UBS=(1584 1586 1664)` 据え置き、log 名/tag prefix 変更）
- `start_phaseSeval3s.sh` → `start_phaseSeval4s.sh`（REMOTE_LOG 名変更のみ）
- `run_all.sh`, `measure_phaseI.sh` はそのままコピー（汎用）
- `prompts/prompt_1k.txt` はそのままコピー（prompt_n=1084、Phase Sbfine3 以降共通）

### 3. analyze_phaseSeval4s.py の変更点

ベース: `analyze_phaseSeval3s.py`（行単位で以下のみ変更、他は同一）:
- `PRIOR_TSVS` に S3 を追加:
  ```python
  PRIOR_TSVS = [
    ("S1_phaseSeval", ... / "summary_phaseSeval.tsv"),
    ("S2_phaseSevalcross", ... / "summary_phaseSevalcross.tsv"),
    ("S3_phaseSeval3s", SCRIPT_DIR.parent / "2026-04-20_022922_qwen3-122b-c3-phaseSeval3s" / "summary_phaseSeval3s.tsv"),
  ]
  CUR_SESSION_LABEL = "S4_phaseSeval4s"
  ```
- 出力ファイル名を `summary_phaseSeval4s.tsv` / `phaseSeval4s_stats.csv` / `phaseSeval4s_verdict.txt` に
- TAG_PREFIX を `Seval4s_fa1_ctx` に
- verdict テーブル列見出しを `S1 | S2 | S3 | S4 | range | mean_of_4 | σ_session` に拡張（汎用化は既に session_labels ループで行われているため、列見出し文字列のみ修正）
- `## 5.` の「Prior pool (S1+S2)」を「Prior 3-session pool (S1+S2+S3)」に文言更新（コード上は PRIOR_TSVS をループしているため自動で n=15 対応）
- `## 6.` の「Pooled 15-run」を「Pooled 20-run」に文言更新

### 4. バッチ実行

```bash
cd report/attachment/${TS}_qwen3-122b-c3-phaseSeval4s/
bash batch_phaseSeval4s.sh > batch_phaseSeval4s.log 2>&1
python3 analyze_phaseSeval4s.py
```

所要目安: 37-40 分。

### 5. サーバ停止・ロック解放

```bash
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 6. レポート作成

`report/${TS}_qwen3-122b-c3-phaseSeval4s.md` を作成。S3 レポートの構造を踏襲し、以下を必ず記載:
- 添付ファイル節（plan.md / スクリプト群 / ログ / TSV / stats / verdict / startup_logs）
- 前提・目的（4-session 収束性検証、ub=1586 verdict 更新、ub=1664 単調増加再確認、ピーク順序）
- 再現方法、環境情報、セッション間隔表（S1-S4）
- 実行結果サマリ: 本 Phase (S4) 5-run ピボット / 4 session mean 時系列 / Welch t (S1+S2+S3 vs S4) / ピーク順序 4 session 一覧 / Pooled 20-run / warmup ub=1584 +0.31 再現性 / compute buffer 4 session 一致
- 採用判定、**未検証事項**、**検証完了後に実施すべき TODO** の 2 セクション（S3 の項目を引き継ぎ [x] で更新）

## 変更・参照ファイル

### 新規作成
- `/home/ubuntu/.claude/plans/todo-tidy-oasis.md`（本ファイル）
- `report/attachment/${TS}_qwen3-122b-c3-phaseSeval4s/` 配下一式
- `report/${TS}_qwen3-122b-c3-phaseSeval4s.md`

### 既読・参照
- `report/2026-04-20_022922_qwen3-122b-c3-phaseSeval3s.md`（直前レポート）
- `report/attachment/2026-04-20_022922_qwen3-122b-c3-phaseSeval3s/`（流用元スクリプト群と S3 TSV）
- `report/attachment/2026-04-20_003250_qwen3-122b-c3-phaseSeval/summary_phaseSeval.tsv`（S1 prior）
- `report/attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/summary_phaseSevalcross.tsv`（S2 prior、ファイル名は load_prior_tsv のパス指定と一致させる）
- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- `.claude/skills/llama-server/scripts/stop.sh`
- `REPORT.md`（レポート命名・添付規則）

## 検証方法

- GPU ロック: `bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100` で取得、末尾 `unlock.sh` で解放（ログに `[lock] acquired` / `[unlock] released` が出る）
- 起動健全性: `/health` 200 以内に OK（80*5s 以内）
- eval 完走: 各 ub で 5 JSON × `predicted_n=256`、`summary_phaseSeval4s.tsv` が 3 ub × (warmup 2 + eval 5) = 21 行
- compute buffer: `startup_logs/fa1_ctx32768_b*_ub*.log` の CUDA0-3 compute buffer サイズが S3 と MiB 単位一致
- 統計健全性: `phaseSeval4s_verdict.txt` の `## 6. Pooled 20-run` で各 ub の n=20、`## 5. Welch t` が S1+S2+S3 pool (n=15) vs S4 (n=5) で算出、`## 9.` で 4-session verdict が ub ごとに fully_independent / partial_drift / session_dominated のいずれか
- レポート: 前提・目的・再現方法・環境情報・添付ファイル節・未検証事項・検証完了後に実施すべき TODO が揃う
