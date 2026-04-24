# Phase S-eval-28session 実行プラン

## Context

直前の Phase S-eval-27session（S27、2026-04-21 05:10-05:50 JST）の未検証事項として **★最優先** に分類された 5 項目のうち、以下の 5 点は「同一条件で第 28 セッション (S28) を測定する」ことで同時検証できる：

1. **ub=1584 alternating 6-hop → 7-hop 継続検証** — S22-S27 で 崩壊/非/崩壊/非/崩壊/非 の 6-hop cycle が確立。S28 崩壊なら 7-hop 完全周期性（27-session 最長記録）、非崩壊なら cycle break
2. **ub=1586 plateau 5 連続 → 6 連続 or break** — S23-S27 で 15.13-15.32 範囲の plateau。S28 で同帯なら 6 連続、15.4+ なら stepwise climb 復活、<15.0 なら再崩壊
3. **ub=1664 上帯 stay 2 連続 → 3 連続可否** — S26/S27 上帯 (>15.20) 連続。S28 上帯 stay なら 27-session 初の「上帯 stable regime」
4. **mode_D 連続化可否 + C/D 5 位タイ解消** — S27 mode_D 復活（3 回目、S8/S18/S27）で C と同率 4 位タイ。S28 D なら D 連続化、C なら階層崩し
5. **σ_pool regime change 6 連続 → 7 連続 or 解消** — S22-S27 で σ_pool 1586>1584 6 連続、逆転幅 0.009 (S25 水準に縮小回帰)。S28 で 7 連続 or 解消

また、S27 の「検証完了後に実施すべき TODO」の筆頭も **★最重要: Phase S-eval-28session 候補** であり、本 Phase はそれに該当する。

cool time は S27 終了（05:49:27 JST）から現在（約 2026-04-21 07:xx JST 以降）までが既に通常帯 13-16 分 sub-zone を大きく超過し、別 sub-zone の観測機会となる。

## 方針

S27 と完全同一条件（ctx=32768, fa=1, OT=MoE-only, ub={1584, 1586, 1664}, warmup 2 run + eval 5 run）で 28 セッション目 (S28) を 1 回追加測定する。S27 の attachment を丸ごと複製して `28s` にリネームし、analyze スクリプトの PRIOR_TSVs に S27 の summary_phaseSeval27s.tsv を追加、CUR_SESSION_LABEL を `S28_phaseSeval28s` に変更する。

## 手順

### 1. タイムスタンプ取得と添付ディレクトリ作成

```bash
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REP="${TS}_qwen3-122b-c3-phaseSeval28s"
mkdir -p report/attachment/${REP}
cp /home/ubuntu/.claude/plans/todo-reactive-reef.md report/attachment/${REP}/plan.md
```

### 2. S27 スクリプト一式を S28 用に複製・リネーム

S27 attachment ディレクトリから以下をコピーしリネーム（`27s` → `28s`）:

- `start_phaseSeval27s.sh` → `start_phaseSeval28s.sh`
- `batch_phaseSeval27s.sh` → `batch_phaseSeval28s.sh`
- `run_all.sh` → `run_all.sh`（ファイル名は同じだが TAG_PREFIX のみ 28s に）
- `measure_phaseI.sh` → `measure_phaseI.sh`（中身変更なし）
- `analyze_phaseSeval27s.py` → `analyze_phaseSeval28s.py`
- `prompts/prompt_1k.txt` → 同一コピー

各スクリプト内の文字列置換:
- `phaseSeval27s` → `phaseSeval28s`
- `Seval27s_` → `Seval28s_`
- `S27_phaseSeval27s` → `S28_phaseSeval28s`
- `analyze_phaseSeval27s.py` の `PRIOR_TSVs` リストに S27 の summary_phaseSeval27s.tsv を追加

### 3. GPU ロック取得

```bash
cd /home/ubuntu/projects/llm-server-ops
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 4. バッチ実行（約 37-40 分）

```bash
cd report/attachment/${REP}
HOST=t120h-p100 bash batch_phaseSeval28s.sh > batch_phaseSeval28s.log 2>&1
```

バッチは 3 ub × (warmup 2 + eval 5) = 21 run、run 間 cooldown 60 秒、3 条件間で llama-server を再起動。

### 5. 分析

```bash
python3 analyze_phaseSeval28s.py
```

以下を出力:
- `summary_phaseSeval28s.tsv` (21 行の raw eval_tps)
- `phaseSeval28s_stats.csv` (3 ub の 5-run mean/stdev/min/max/median)
- `phaseSeval28s_verdict.txt` (28-session pooled 統計 + Welch t + mode + σ_pool + 崩壊頻度判定)

### 6. GPU ロック解放

```bash
cd /home/ubuntu/projects/llm-server-ops
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 7. レポート作成

`report/${TS}_qwen3-122b-c3-phaseSeval28s.md` を作成し、以下を含める:

- 前提・目的（5 項目の ★最優先 検証）
- 実施日時（JST）/ 作業種別 / GPU ロック状態
- 参照（S27 + 主要過去セッション）
- 結果テーブル（3 ub の 5-run mean）
- Welch t（prior 27-session pool vs S28）
- Pooled 140-run 統計（= 28 session × 5 run/ub）
- 28-session peak order 1 位頻度 + mode 分類
- 5 項目の ★最優先 検証結果サマリ
- **未検証事項** セクション（直前の S27 レポートと同様のフォーマットで、S28 で判明・発生した新規 ★最優先 / ★高優先 項目を追加）
- **検証完了後に実施すべき TODO** セクション（S29 候補、CLAUDE.md 訂正候補、性能カード更新等）
- 結論

## Critical files

- 作成: `/home/ubuntu/projects/llm-server-ops/report/${TS}_qwen3-122b-c3-phaseSeval28s.md`
- 作成: `/home/ubuntu/projects/llm-server-ops/report/attachment/${TS}_qwen3-122b-c3-phaseSeval28s/` 配下一式
- 参照（コピー元）: `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-21_051039_qwen3-122b-c3-phaseSeval27s/`
- 参照（スキル）: `.claude/skills/gpu-server/scripts/{lock,unlock}.sh`、`.claude/skills/llama-server/scripts/{start,stop,wait-ready}.sh`
- 参照（Prior TSV 追加対象）: `report/attachment/2026-04-21_051039_qwen3-122b-c3-phaseSeval27s/summary_phaseSeval27s.tsv`

## 検証（end-to-end）

1. `bash .claude/skills/gpu-server/scripts/lock-status.sh t120h-p100` でロックが自分のセッションで取得されていること
2. `batch_phaseSeval28s.log` に 3 条件 × 7 run（warmup 2 + eval 5）の完了が記録されていること、全 run で `predicted_n=256` 完走
3. `summary_phaseSeval28s.tsv` が 21 行（header + 21 run）、`phaseSeval28s_stats.csv` が 3 ub 行
4. `phaseSeval28s_verdict.txt` に 28-session 統計（pool 140-run per ub）、5 ★最優先 項目の判定、σ_pool 1586 vs 1584 比較が出力されていること
5. バッチ後 `ssh t120h-p100 "ps aux | grep llama-server | grep -v grep"` で残存プロセスがないこと
6. レポート Markdown が REPORT.md ルール準拠（ファイル名、JST 表記、添付 plan.md リンク、未検証事項/TODO セクション）

## リスクと対処

- **ub=1664 で compute buffer OOM** — 過去 27 session 全て成功、allocator も 27 session 完全一致のため再現性高い。もし発生した場合はログを残し条件から除外せず報告
- **cool time が長すぎて「通常帯外」になる** — 実施時刻により 16 分以上〜数時間になる可能性。どの sub-zone に該当するかを実測 cool time で判定し、線形モデル fit に含める（別 sub-zone でも 5 ★最優先 検証自体は影響なし）
- **セッション途中でロック競合** — lock.sh 取得失敗時は作業中断、ユーザに報告
