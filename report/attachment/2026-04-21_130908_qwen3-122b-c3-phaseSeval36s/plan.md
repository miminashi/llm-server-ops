# Phase S-eval-36session (S36) 実施プラン

## Context

直前レポート [2026-04-21_121546_qwen3-122b-c3-phaseSeval35s.md](../../projects/llm-server-ops/report/2026-04-21_121546_qwen3-122b-c3-phaseSeval35s.md) の「未検証事項」新規項目には ★最優先 項目が 9 件登録されており、そのほぼ全てが「ctx=32768 × fa=1 × OT=MoE-only 固定、ub={1584,1586,1664} × (warmup 2 + eval 5) を第 36 session (S36) として再実行し統計を積み増す」ことで同時検証可能である。代表例：

- **mode_E 復活 5 例目 → S36 mode_E 連続化 or 単発**（S13/S15/S21/S26/S35、連続化はこれまで 0 例）
- **ub=1586 回復 → S36 崩壊再開 or 継続回復**（「崩壊 regime 復帰」 vs 「高値帯定着」）
- **ub=1584 3 cycle 開始 → S36 動向**（4 cycle initial or 2 連続崩壊）
- **ub=1664 下帯復帰 → S36 中帯 / 上帯 / 下帯継続**
- **A=B タイ 5 連続 → S36 6 連続可否**（35-session 0 例の 6 連続）
- **σ_pool 1586 1 位 4 連続 → S36 5 連続可否**（35-session 0 例の 5 連続）
- **Welch (-/+/-) 新 subtype → S36 再現頻度**（S35 initial observation）
- **pool 差 +0.02 再突破 (+0.037) → S36 収束 or さらに拡大**
- **double collapse (1584/1664) 3 例目 → S36 4 例目 interval**（S4/S24/S35、interval 20/11）

「検証完了後に実施すべき TODO」でも ★最重要 として **Phase S-eval-36session** が新規登録済。所要は 37-40 分見込み（S35 実績 37 分 05 秒）。

## 変更の狙い

S35 と完全同一条件で S36 バッチを実行し、pooled 36-session / 180-run 統計へ拡張する。既存 S35 の添付スクリプトを複製して `35s → 36s`（タグ・ファイル名・ラベル）に機械置換し、analyze の prior TSV リストに `S35_phaseSeval35s` を追加するだけで足りる。S34→S35 と同じ差分パターンを適用する。

## 作業手順

### 1. タイムスタンプ取得と添付ディレクトリ作成

```bash
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_BASENAME="${TS}_qwen3-122b-c3-phaseSeval36s"
ATTACH=/home/ubuntu/projects/llm-server-ops/report/attachment/${REPORT_BASENAME}
mkdir -p "${ATTACH}/startup_logs" "${ATTACH}/prompts"
```

### 2. S35 添付をコピーし、36s 名義へ機械置換

コピー対象（再利用可）：
- `start_phaseSeval35s.sh` → `start_phaseSeval36s.sh`
- `batch_phaseSeval35s.sh` → `batch_phaseSeval36s.sh`
- `run_all.sh` → `run_all.sh`（そのまま）
- `measure_phaseI.sh` → `measure_phaseI.sh`（そのまま）
- `prompts/prompt_1k.txt` → `prompts/prompt_1k.txt`（そのまま、6200 bytes / prompt_n=1086）
- `analyze_phaseSeval35s.py` → `analyze_phaseSeval36s.py`

置換ルール（sed ベース）：
- `35s` → `36s`
- `35session` → `36session`
- `S35` → `S36`（MODE_GROUPS の `cur_S35` / `CUR_SESSION_LABEL` / 出力 heading 等）
- `phaseSeval35s` → `phaseSeval36s`
- `Seval35s` → `Seval36s`
- `batchSeval35s` / `start_phaseSeval35s` 等の echo tag も自動連動

analyze_phaseSeval36s.py では追加で：
- `PRIOR_TSVS` に `S35_phaseSeval35s` エントリを追加（`2026-04-21_121546_qwen3-122b-c3-phaseSeval35s/summary_phaseSeval35s.tsv`）
- `MODE_GROUPS` に `prev_S35` を追加、`cur_S35` → `cur_S36` にリネーム
- Pooled 175-run コメント → 180-run、「S1..S35」→「S1..S36」、prior 34-session → prior 35-session

### 3. GPU サーバロック取得

```bash
cd /home/ubuntu/projects/llm-server-ops
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 4. バッチ実行（ub=1584/1586/1664 × warmup 2 + eval 5）

```bash
cd "${ATTACH}"
HOST=t120h-p100 bash batch_phaseSeval36s.sh > batch_phaseSeval36s.log 2>&1
```

所要約 37-40 分。各条件 warmup 2 run + 1k prompt eval 5 run。

### 5. 集計

```bash
cd "${ATTACH}"
python3 analyze_phaseSeval36s.py
```

生成物：
- `summary_phaseSeval36s.tsv`（run 別 raw）
- `phaseSeval36s_stats.csv`（条件別 5-run 統計）
- `phaseSeval36s_verdict.txt`（36-session 時系列・Welch t・pooled 180-run・mode 分類 等）

### 6. ロック解放

```bash
cd /home/ubuntu/projects/llm-server-ops
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 7. レポート執筆

パス：`report/${REPORT_BASENAME}.md`

セクション構成（S35 レポートに準拠）：
- 冒頭（実施日時、作業種別、GPU ロック）
- 添付ファイル
- 参照（直前 S35 / 主要過去 session）
- 前提・目的
- 核心発見サマリ（S35 比、連続化 / 破断、mode_E 連続 / ub=1586 再崩壊 / ub=1584 4 cycle / A=B 6 連続 / σ_pool 5 連続 / Welch 再現 / pool 差 / 下帯後帯分岐 等）
- 判定しきい値
- 成功条件
- 環境情報（S35 と完全同一、セッション間隔）
- 再現方法
- 結果（5-run mean、Welch t prior 35-session pool vs S36、pooled 180-run、ピーク 1 位頻度、mode 分類）
- **未検証事項**（既知項目の引継ぎ + 新規項目）
- **検証完了後に実施すべき TODO**（既知項目の引継ぎ + Phase S-eval-37session 候補追加）
- 結論

プランファイル添付：
```bash
cp /home/ubuntu/.claude/plans/todo-immutable-beacon.md "${ATTACH}/plan.md"
```

## 変更対象ファイル

### 新規作成

- `report/${REPORT_BASENAME}.md`
- `report/attachment/${REPORT_BASENAME}/`
  - `plan.md`（コピー）
  - `start_phaseSeval36s.sh`（S35 複製 + 置換）
  - `batch_phaseSeval36s.sh`（S35 複製 + 置換）
  - `run_all.sh`（S35 からコピー）
  - `measure_phaseI.sh`（S35 からコピー）
  - `analyze_phaseSeval36s.py`（S35 複製 + 置換 + prior S35 追加 + 175→180 更新）
  - `prompts/prompt_1k.txt`（S35 からコピー）
  - `startup_logs/`（空ディレクトリ、実行時に 3 ファイル生成）
  - 実行時生成物: `batch_phaseSeval36s.log`, `summary_phaseSeval36s.tsv`, `phaseSeval36s_stats.csv`, `phaseSeval36s_verdict.txt`, `start_stdout_*` / `run_Seval36s_*` / `run_all_Seval36s_*` 各 3 ファイル, `out_Seval36s_*` 計 6 ディレクトリ

### 既存更新

- 無し（CLAUDE.md 更新は★最重要 TODO として残すが、S36 レポート内に記載するのみで CLAUDE.md 本体は修正しない ← S34/S35 でも未実施のため踏襲）

## 重要ファイル

- 直前 S35 添付: `report/attachment/2026-04-21_121546_qwen3-122b-c3-phaseSeval35s/`
- 過去 TSV (S1-S34): `report/attachment/2026-04-{20,21}_*_qwen3-122b-c3-phaseSeval*s/summary_phaseSeval*s.tsv`
- GPU ロック skill: `.claude/skills/gpu-server/scripts/{lock,unlock}.sh`
- llama-server stop skill: `.claude/skills/llama-server/scripts/stop.sh`

## 検証

1. **ロック状態**: 実行前に `cat /home/ubuntu/.claude/skills/gpu-server/locks/t120h-p100.lock` 等で他セッションとの競合が無いことを確認（`lock.sh` が担当）。
2. **llama-server 起動健全性**: 各 ub で `curl -sf http://10.1.4.14:8000/health` が 300 秒以内に 200 を返すこと。`start_phaseSeval36s.sh` 内で実装済（コピー元 S35 版の仕様踏襲）。
3. **run 完走**: `summary_phaseSeval36s.tsv` に 3 ub × (warmup 2 + eval 5) = 21 行 + header が揃うこと。
4. **eval 5-run 結果**: `phaseSeval36s_stats.csv` に 3 ub × eval で `n=5`、stdev が概ね < 0.01。
5. **Welch t**: `phaseSeval36s_verdict.txt` で prior 35-session pool vs S36 の t 値が ub 別に出力。
6. **Pooled 180-run**: `ub=1584/1586/1664` で `pool_n=180` が出力。
7. **ピーク順序**: 36 session 分の peak order が列挙され、各 ub の 1 位頻度が更新。
8. **ロック解放**: `unlock.sh` 実行後、他セッションが取得可能な状態になる。

本プランはプラン承認後、自動継続（auto mode）で全ステップを順次実行する。
