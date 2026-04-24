# Plan: Phase S-eval-43session

## Context

直前レポート [2026-04-21_184122_qwen3-122b-c3-phaseSeval42s.md](../../../projects/llm-server-ops/report/2026-04-21_184122_qwen3-122b-c3-phaseSeval42s.md) の「未検証事項」欄には、S43（第 43 セッション）を同条件で追加すれば一括検証できる★最優先項目が 12 件以上積み上がっている。主なもの:

- ub=1586 +0.746 大幅回復 → S43 で定着か再崩壊か
- ub=1664 4 連続崩壊 + 中帯 3 連続 → 5 連続 or 離脱（42-session 0 例の未踏領域）
- Welch (+/+/0) 新 subtype → 連続 or shift（13-subtype 連続新記録継続可否）
- σ_pool 1664 1 位 4 連続 break（0.303 vs 0.302、差 0.001 拮抗）→ 再奪還 or 1586 定着
- σ_pool 逆転幅 +0.032 拡大 2 連続 → 連続拡大 or 縮小
- ub=1664/1584 σ_pool 3 連続縮小 → 4 連続縮小可否
- pool 差 +0.06 帯復帰 → 定着 or shift
- mode_A 外 13 session → 14 連続外 or A 復帰（S29 以来の最長更新中）
- ub=1586 |Δ_max| 担当 2 連続 → 3 連続可否
- ub=1586 pool max 15.532 更新（S13 以来 29 session ぶり）→ 更新 or 維持
- ub=1586 peak 1 位奪還 → 連続 or 喪失
- mode_B 1 session interval 復帰 → 連続 or 他 mode

検証完了後 TODO の筆頭にも「★最重要: Phase S-eval-43session 候補」が記載されている。

本 Plan はこれを S42 と同条件（ctx=32768 × fa=1 × OT=MoE-only × ub ∈ {1584, 1586, 1664} × warmup 2 + eval 5 run）で実施して一括検証する。

## 実施手順

### 1. GPU ロック取得

```bash
cd /home/ubuntu/projects/llm-server-ops
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 2. 添付ディレクトリ作成（S42 からコピー＋改名）

新ディレクトリ: `report/attachment/<YYYY-MM-DD_HHMMSS>_qwen3-122b-c3-phaseSeval43s/`

以下を S42 から複製:
- `start_phaseSeval42s.sh` → `start_phaseSeval43s.sh`
- `batch_phaseSeval42s.sh` → `batch_phaseSeval43s.sh`
- `run_all.sh`（書き換え不要）
- `measure_phaseI.sh`（書き換え不要）
- `analyze_phaseSeval42s.py` → `analyze_phaseSeval43s.py`
- `plot_timeseries.py`
- `prompts/prompt_1k.txt`（S42 のものを流用、prompt_n=1086）

Explore agent の報告に基づく書き換えポイント:
- `start_phaseSeval43s.sh` L2, L22: `phaseSeval42s` → `phaseSeval43s`
- `batch_phaseSeval43s.sh` L2, L16, L19-21, L23-27, L40-42, L67-68, L70: `42s` → `43s`（phase 名・ログ出力先）
- `analyze_phaseSeval43s.py`:
  - L113 相当: S42 の TSV パスをリスト末尾に追加
  - L116 相当: `CUR_SESSION_LABEL = "S43_phaseSeval43s"`
  - L156 相当: MODE_GROUPS で `cur_S42` → `prev_S42`、`cur_S43` 追加
  - L168 相当: `TAG_PREFIX = "Seval43s_fa1_ctx"`
- `plot_timeseries.py` L88 相当: `S_EVAL_DIRS` 末尾に `("S43", "<43s-dir>", "summary_phaseSeval43s.tsv")` を追加

### 3. バッチ実行

```bash
cd report/attachment/<43s-dir>
HOST=t120h-p100 bash batch_phaseSeval43s.sh > batch_phaseSeval43s.log 2>&1
```

- 所要時間: ~40-45 分（S42 は 44'58"）
- 3 条件 × (warmup 2 + eval 5) = 21 run、cooldown 60 秒

### 4. 分析と時系列プロット

```bash
python3 analyze_phaseSeval43s.py
python3 plot_timeseries.py
```

出力:
- `summary_phaseSeval43s.tsv`（run 別 raw）
- `phaseSeval43s_stats.csv`（統計）
- `phaseSeval43s_verdict.txt`（43-session 判定）
- `timeseries_eval_tps.png`（S0 Sbfine 参照点 + S1..S43）

### 5. レポート作成

- 場所: `report/<YYYY-MM-DD_HHMMSS>_qwen3-122b-c3-phaseSeval43s.md`
- フォーマット: [REPORT.md](../../../projects/llm-server-ops/REPORT.md) に準拠、かつ S42 レポートと同構造
- 必須セクション: 「未検証事項」「検証完了後に実施すべき TODO」
- 時系列プロット PNG を本文に埋め込み
- 直前 S42 の★最優先 TODO 19+ 項目の検証結果を個別記載

### 6. GPU ロック解放

```bash
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 修正対象ファイル（すべて新規作成）

- `report/attachment/<43s-dir>/start_phaseSeval43s.sh`
- `report/attachment/<43s-dir>/batch_phaseSeval43s.sh`
- `report/attachment/<43s-dir>/run_all.sh`（コピーのみ）
- `report/attachment/<43s-dir>/measure_phaseI.sh`（コピーのみ）
- `report/attachment/<43s-dir>/analyze_phaseSeval43s.py`
- `report/attachment/<43s-dir>/plot_timeseries.py`
- `report/attachment/<43s-dir>/prompts/prompt_1k.txt`（コピーのみ）
- `report/<43s-timestamp>_qwen3-122b-c3-phaseSeval43s.md`

## 参照する既存ファイル

- S42 スクリプト群: `report/attachment/2026-04-21_184122_qwen3-122b-c3-phaseSeval42s/`
- 直前レポート: `report/2026-04-21_184122_qwen3-122b-c3-phaseSeval42s.md`
- llama-server stop: `.claude/skills/llama-server/scripts/stop.sh`
- GPU ロック: `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- レポート作成ルール: `REPORT.md`

## 検証方法（end-to-end）

1. バッチ実行ログに 21 run 全完走、predicted_n=256 を確認
2. `analyze_phaseSeval43s.py` が n=43 session、pool_n=215 の統計を出力
3. `timeseries_eval_tps.png` が S0(Sbfine)+S1..S43 の連続折れ線を描画
4. ★最優先 TODO 12+ 項目の「連続 or shift」判定を verdict に記録
5. レポート本文「未検証事項」に S43 時点で残る項目、「検証完了後に実施すべき TODO」に S44 候補と skill/CLAUDE.md 訂正案を記載
6. GPU ロックが release されていること
