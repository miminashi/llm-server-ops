# Phase S-eval-35session (S35) 実施プラン

## Context

直前レポート [2026-04-21_112228_qwen3-122b-c3-phaseSeval34s.md](../../projects/llm-server-ops/report/2026-04-21_112228_qwen3-122b-c3-phaseSeval34s.md) の「未検証事項」新規項目には ★最優先 項目が 10 件登録されており、そのほぼ全てが「ctx=32768 × fa=1 × OT=MoE-only 固定、ub={1584,1586,1664} × (warmup 2 + eval 5) を第 35 session (S35) として再実行し統計を積み増す」ことで同時検証可能である。代表例:

- **mode_F 2 連続 → 3 連続可否 / 回帰**（F regime 確定 or 2-session 限定）
- **ub=1586 3 連続崩壊 → 4 連続 or 回復**
- **ub=1664 中帯 stay 4 連続 → 5 連続可否**
- **A=B タイ 4 連続 → 5 連続可否**
- **ub=1584 回復 2 連続 → 3 連続 or 3 cycle 開始**
- **σ_pool 1586 1 位 3 連続 → 4 連続可否**
- **Welch (+/-/+) 2 連続 → 3 連続可否**
- **3 ub 全 σ_pool 縮小 2 連続 → 3 連続可否**
- **pool 差 1586-1584 +0.02 割れ → 収束 or 再拡大**
- **境界帯 18+ 分 sub-zone 3 連続 → 4 連続可否**

「検証完了後に実施すべき TODO」でも ★最重要 として **Phase S-eval-35session** が新規登録済。所要は 37-40 分見込み（S34 実績 37分05秒）。

## 変更の狙い

S34 と完全同一条件で S35 バッチを実行し、pooled 35-session / 175-run 統計へ拡張する。既存 S34 の添付スクリプトを複製して `34s → 35s`（タグ・ファイル名・ラベル）に機械置換し、analyze の prior TSV リストに `S34_phaseSeval34s` を追加するだけで足りる。S33→S34 と同じ差分パターンを適用する。

## 作業手順

### 1. タイムスタンプ取得と添付ディレクトリ作成

```bash
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_BASENAME="${TS}_qwen3-122b-c3-phaseSeval35s"
ATTACH=/home/ubuntu/projects/llm-server-ops/report/attachment/${REPORT_BASENAME}
mkdir -p "${ATTACH}/startup_logs" "${ATTACH}/prompts"
```

### 2. S34 添付をコピーし、35s 名義へ機械置換

コピー対象（再利用可）:
- `start_phaseSeval34s.sh` → `start_phaseSeval35s.sh`
- `batch_phaseSeval34s.sh` → `batch_phaseSeval35s.sh`
- `run_all.sh` → `run_all.sh`（そのまま）
- `measure_phaseI.sh` → `measure_phaseI.sh`（そのまま）
- `prompts/prompt_1k.txt` → `prompts/prompt_1k.txt`（そのまま、6200 bytes / prompt_n=1086）
- `analyze_phaseSeval34s.py` → `analyze_phaseSeval35s.py`

置換ルール（sed ベース）:
- `34s` → `35s`
- `34session` → `35session`
- `S34` → `S35`（MODE_GROUPS の `cur_S34` / `CUR_SESSION_LABEL` / 出力 heading 等）
- `phaseSeval34s` → `phaseSeval35s`
- `Seval34s` → `Seval35s`
- `batchSeval34s` / `start_phaseSeval34s` 等の echo tag も自動連動

analyze_phaseSeval35s.py では追加で:
- `PRIOR_TSVS` に `S34_phaseSeval34s` エントリを追加（`2026-04-21_112228_qwen3-122b-c3-phaseSeval34s/summary_phaseSeval34s.tsv`）
- `MODE_GROUPS` に `prev_S34` を追加、`cur_S34` → `cur_S35` にリネーム
- Pooled 170-run コメント → 175-run、「S1..S34」→「S1..S35」、prior 33-session → prior 34-session

### 3. GPU サーバロック取得

```bash
cd /home/ubuntu/projects/llm-server-ops
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 4. バッチ実行（ub=1584/1586/1664 × warmup 2 + eval 5）

```bash
cd "${ATTACH}"
HOST=t120h-p100 bash batch_phaseSeval35s.sh > batch_phaseSeval35s.log 2>&1
```

所要約 37-40 分。各条件 warmup 2 run + 1k prompt eval 5 run。

### 5. 集計

```bash
cd "${ATTACH}"
python3 analyze_phaseSeval35s.py
```

生成物:
- `summary_phaseSeval35s.tsv`（run 別 raw）
- `phaseSeval35s_stats.csv`（条件別 5-run 統計）
- `phaseSeval35s_verdict.txt`（35-session 時系列・Welch t・pooled 175-run・mode 分類 等）

### 6. ロック解放

```bash
cd /home/ubuntu/projects/llm-server-ops
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 7. レポート執筆

パス: `report/${REPORT_BASENAME}.md`

セクション構成（S34 レポートに準拠）:
- 冒頭（実施日時、作業種別、GPU ロック）
- 添付ファイル
- 参照（直前 S34 / 主要過去 session）
- 前提・目的
- 核心発見サマリ（S34 比、連続化 / 破断、mode_F / ub=1586 / 中帯 / A=B / 回復 / σ_pool / Welch / 境界帯 等）
- 判定しきい値
- 成功条件
- 環境情報（S34 と完全同一、セッション間隔）
- 再現方法
- 結果（5-run mean、Welch t、pooled 175-run、ピーク 1 位頻度、mode 分類）
- **未検証事項**（既知項目の引継ぎ + 新規項目）
- **検証完了後に実施すべき TODO**（既知項目の引継ぎ + Phase S-eval-36session 候補追加）
- 結論

プランファイル添付:
```bash
cp /home/ubuntu/.claude/plans/todo-cached-origami.md "${ATTACH}/plan.md"
```

## 変更対象ファイル

### 新規作成

- `report/${REPORT_BASENAME}.md`
- `report/attachment/${REPORT_BASENAME}/`
  - `plan.md`（コピー）
  - `start_phaseSeval35s.sh`（S34 複製 + 置換）
  - `batch_phaseSeval35s.sh`（S34 複製 + 置換）
  - `run_all.sh`（S34 からコピー）
  - `measure_phaseI.sh`（S34 からコピー）
  - `analyze_phaseSeval35s.py`（S34 複製 + 置換 + prior S34 追加 + 170→175 更新）
  - `prompts/prompt_1k.txt`（S34 からコピー）
  - `startup_logs/`（空ディレクトリ、実行時に 3 ファイル生成）
  - 実行時生成物: `batch_phaseSeval35s.log`, `summary_phaseSeval35s.tsv`, `phaseSeval35s_stats.csv`, `phaseSeval35s_verdict.txt`, `start_stdout_*` / `run_Seval35s_*` / `run_all_Seval35s_*` 各 3 ファイル, `out_Seval35s_*` 計 6 ディレクトリ

### 既存更新

- 無し（CLAUDE.md 更新は★最重要 TODO として残すが、S35 レポート内に記載するのみで CLAUDE.md 本体は修正しない ← S34 でも未実施のため踏襲）

## 重要ファイル

- 直前 S34 添付: `report/attachment/2026-04-21_112228_qwen3-122b-c3-phaseSeval34s/`
- 過去 TSV (S1-S33): `report/attachment/2026-04-{20,21}_*_qwen3-122b-c3-phaseSeval*s/summary_phaseSeval*s.tsv`
- GPU ロック skill: `.claude/skills/gpu-server/scripts/{lock,unlock}.sh`
- llama-server stop skill: `.claude/skills/llama-server/scripts/stop.sh`

## 検証

1. **ロック状態**: 実行前に `cat /home/ubuntu/.claude/skills/gpu-server/locks/t120h-p100.lock` 等で他セッションとの競合が無いことを確認（`lock.sh` が担当）。
2. **llama-server 起動健全性**: 各 ub で `curl -sf http://10.1.4.14:8000/health` が 300 秒以内に 200 を返すこと。`start_phaseSeval35s.sh` 内で実装済。
3. **run 完走**: `summary_phaseSeval35s.tsv` に 3 ub × (warmup 2 + eval 5) = 21 行 + header が揃うこと。
4. **eval 5-run 結果**: `phaseSeval35s_stats.csv` に 3 ub × eval で `n=5`、stdev が概ね < 0.01 (within-σ 低位継続の見込み)。
5. **Welch t**: `phaseSeval35s_verdict.txt` で prior 34-session pool vs S35 の t 値が ub 別に出力。
6. **Pooled 175-run**: `ub=1584/1586/1664` で `pool_n=175` が出力。
7. **ピーク順序**: 35 session 分の peak order が列挙され、各 ub の 1 位頻度が更新。
8. **ロック解放**: `unlock.sh` 実行後、他セッションが取得可能な状態になる。

本プランはプラン承認後、自動継続（auto mode）で全ステップを順次実行する。
