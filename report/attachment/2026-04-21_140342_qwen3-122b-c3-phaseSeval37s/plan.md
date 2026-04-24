# Phase S-eval-37session (S37) 実施プラン

## Context

直前レポート [2026-04-21_130908_qwen3-122b-c3-phaseSeval36s.md](../../projects/llm-server-ops/report/2026-04-21_130908_qwen3-122b-c3-phaseSeval36s.md) の「未検証事項 > 新規項目」には ★最優先 項目が 9 件登録されており、そのほぼ全てが「ctx=32768 × fa=1 × OT=MoE-only 固定、ub={1584,1586,1664} × (warmup 2 + eval 5) を第 37 session (S37) として再実行し統計を積み増す」ことで同時検証可能である。代表例:

- **mode_E 連続化 2 連続 → S37 3 連続 or 回帰**（36-session 初の 2 連続達成後の次 session 動向、3 連続は 36-session 0 例）
- **ub=1584 2 連続崩壊 → S37 3 連続 or 回復**（S4 以来 32 session ぶりの新 pattern、3 連続崩壊 initial 候補）
- **ub=1586 回復 2 連続 → S37 継続回復 or 再崩壊**（高値帯定着 regime 確定の試金石）
- **ub=1664 下→中 transition → S37 帯分岐**（中帯継続 2 連続 / 下帯再降下 / 上帯 shift の 3 分岐）
- **A=B タイ 6 連続 → S37 7 連続可否**（36-session 0 例の 7 連続、A-B 差 0pt 6 連続維持）
- **σ_pool 1586 1 位 5 連続 → S37 6 連続可否**（36-session 0 例の 6 連続）
- **Welch (-/+/+) 新 subtype → S37 再現頻度**（S36 initial observation、7 subtype 7-session 連続）
- **pool 差 +0.050 (+0.05 安定帯復帰) → S37 +0.05-+0.06 定着 or 再拡大 or 収束**
- **mode_E 単独 3 位 → S37 順位分岐**（4 位降格で single event、3 位維持で regime 確定）

「検証完了後に実施すべき TODO」でも ★最重要 として **Phase S-eval-37session** が新規登録済（S36 レポート 544 行目）。所要は 37-40 分見込み（S36 実績 36 分 57 秒）。

## 変更の狙い

S36 と完全同一条件で S37 バッチを実行し、pooled 37-session / 185-run 統計へ拡張する。既存 S36 の添付スクリプトを複製して `36s → 37s`（タグ・ファイル名・ラベル）に機械置換し、analyze の prior TSV リストに `S36_phaseSeval36s` を追加するだけで足りる。S35→S36 と同じ差分パターンを適用する。

## 作業手順

### 1. タイムスタンプ取得と添付ディレクトリ作成

```bash
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_BASENAME="${TS}_qwen3-122b-c3-phaseSeval37s"
ATTACH=/home/ubuntu/projects/llm-server-ops/report/attachment/${REPORT_BASENAME}
mkdir -p "${ATTACH}/startup_logs" "${ATTACH}/prompts"
```

### 2. S36 添付をコピーし、37s 名義へ機械置換

コピー対象（再利用可）:
- `start_phaseSeval36s.sh` → `start_phaseSeval37s.sh`
- `batch_phaseSeval36s.sh` → `batch_phaseSeval37s.sh`
- `run_all.sh` → そのまま
- `measure_phaseI.sh` → そのまま
- `prompts/prompt_1k.txt` → そのまま（6200 bytes / prompt_n=1086）
- `analyze_phaseSeval36s.py` → `analyze_phaseSeval37s.py`

置換ルール（sed ベース）:
- `36s` → `37s`
- `36session` → `37session`
- `S36` → `S37`（MODE_GROUPS の `cur_S36` / `CUR_SESSION_LABEL` / 出力 heading 等）
- `phaseSeval36s` → `phaseSeval37s`
- `Seval36s` → `Seval37s`
- `batchSeval36s` / `start_phaseSeval36s` 等の echo tag も連動

analyze_phaseSeval37s.py では追加で:
- `PRIOR_TSVS` に `S36_phaseSeval36s` エントリを追加（`2026-04-21_130908_qwen3-122b-c3-phaseSeval36s/summary_phaseSeval36s.tsv`）
- `MODE_GROUPS` に `prev_S36` を追加、`cur_S36` → `cur_S37` にリネーム
- Pooled 180-run コメント → 185-run、「S1..S36」→「S1..S37」、prior 35-session → prior 36-session

### 3. GPU サーバロック取得

```bash
cd /home/ubuntu/projects/llm-server-ops
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 4. バッチ実行（ub=1584/1586/1664 × warmup 2 + eval 5）

```bash
cd "${ATTACH}"
HOST=t120h-p100 bash batch_phaseSeval37s.sh > batch_phaseSeval37s.log 2>&1
```

所要約 37-40 分。各条件 warmup 2 run + 1k prompt eval 5 run。

### 5. 集計

```bash
cd "${ATTACH}"
python3 analyze_phaseSeval37s.py
```

生成物:
- `summary_phaseSeval37s.tsv`（run 別 raw）
- `phaseSeval37s_stats.csv`（条件別 5-run 統計）
- `phaseSeval37s_verdict.txt`（37-session 時系列・Welch t・pooled 185-run・mode 分類 等）

### 6. ロック解放

```bash
cd /home/ubuntu/projects/llm-server-ops
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 7. レポート執筆

パス: `report/${REPORT_BASENAME}.md`

セクション構成（S36 レポートに準拠、必須セクション）:
- 冒頭（実施日時、作業種別、GPU ロック）
- 添付ファイル
- 参照（直前 S36 / 主要過去 session）
- 前提・目的
- 核心発見サマリ（S36 比、連続化 / 破断、mode_E 3 連続 / ub=1584 3 連続崩壊 / ub=1586 再崩壊 / ub=1664 帯分岐 / A=B 7 連続 / σ_pool 6 連続 / Welch 再現 / pool 差 等）
- 判定しきい値
- 成功条件
- 環境情報（S36 と完全同一、セッション間隔）
- 再現方法
- 結果（5-run mean、Welch t prior 36-session pool vs S37、pooled 185-run、ピーク 1 位頻度、mode 分類）
- **未検証事項**（既知項目の引継ぎ + 新規項目、ユーザ要求）
- **検証完了後に実施すべき TODO**（既知項目の引継ぎ + Phase S-eval-38session 候補追加、ユーザ要求）
- 結論

プランファイル添付:
```bash
cp /home/ubuntu/.claude/plans/todo-logical-quiche.md "${ATTACH}/plan.md"
```

## 変更対象ファイル

### 新規作成

- `report/${REPORT_BASENAME}.md`
- `report/attachment/${REPORT_BASENAME}/`
  - `plan.md`（コピー）
  - `start_phaseSeval37s.sh`（S36 複製 + 置換）
  - `batch_phaseSeval37s.sh`（S36 複製 + 置換）
  - `run_all.sh`（S36 からコピー）
  - `measure_phaseI.sh`（S36 からコピー）
  - `analyze_phaseSeval37s.py`（S36 複製 + 置換 + prior S36 追加 + 180→185 更新）
  - `prompts/prompt_1k.txt`（S36 からコピー）
  - `startup_logs/`（空ディレクトリ、実行時に 3 ファイル生成）
  - 実行時生成物: `batch_phaseSeval37s.log`, `summary_phaseSeval37s.tsv`, `phaseSeval37s_stats.csv`, `phaseSeval37s_verdict.txt`, `start_stdout_*` / `run_Seval37s_*` / `run_all_Seval37s_*` 各 3 ファイル, `out_Seval37s_*` 計 6 ディレクトリ

### 既存更新

- 無し（CLAUDE.md 更新は★最重要 TODO として残すが、S37 レポート内に記載するのみで CLAUDE.md 本体は修正しない ← S34/S35/S36 踏襲）

## 重要ファイル

- 直前 S36 添付: `report/attachment/2026-04-21_130908_qwen3-122b-c3-phaseSeval36s/`
- 過去 TSV (S1-S35): `report/attachment/2026-04-{20,21}_*_qwen3-122b-c3-phaseSeval*s/summary_phaseSeval*s.tsv`
- GPU ロック skill: `.claude/skills/gpu-server/scripts/{lock,unlock}.sh`
- llama-server stop skill: `.claude/skills/llama-server/scripts/stop.sh`

## 検証

1. **ロック状態**: 実行前に `lock.sh` が他セッションとの競合が無いことを確認。
2. **llama-server 起動健全性**: 各 ub で `curl -sf http://10.1.4.14:8000/health` が 300 秒以内に 200 を返すこと。`start_phaseSeval37s.sh` 内で実装済（コピー元 S36 版の仕様踏襲）。
3. **run 完走**: `summary_phaseSeval37s.tsv` に 3 ub × (warmup 2 + eval 5) = 21 行 + header が揃うこと。
4. **eval 5-run 結果**: `phaseSeval37s_stats.csv` に 3 ub × eval で `n=5`、stdev が概ね < 0.01。
5. **Welch t**: `phaseSeval37s_verdict.txt` で prior 36-session pool vs S37 の t 値が ub 別に出力。
6. **Pooled 185-run**: `ub=1584/1586/1664` で `pool_n=185` が出力。
7. **ピーク順序**: 37 session 分の peak order が列挙され、各 ub の 1 位頻度が更新。
8. **ロック解放**: `unlock.sh` 実行後、他セッションが取得可能な状態になる。

## レポート要件（ユーザ指定）

- **「未検証事項」セクション**を含める（直前 S36 レポート踏襲）
- **「検証完了後に実施すべき TODO」セクション**を含める（直前 S36 レポート踏襲）

本プランはプラン承認後、自動継続（auto mode）で全ステップを順次実行する。
