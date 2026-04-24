# Phase S-eval-57session 実施計画

## Context

直前レポート [2026-04-22_091115_qwen3-122b-c3-phaseSeval56s.md](../../projects/llm-server-ops/report/2026-04-22_091115_qwen3-122b-c3-phaseSeval56s.md) の「新規項目（本 Phase S-eval-56session で判明・発生）」セクションには ★最優先の未検証項目が 24 個並んでおり、その多くは **S57 を 1 回実施するだけで同時に判定可能** な性質（session-to-session の連続 pattern、intra-day cluster、pool 統計更新、Welch 符号連続、peak 1 位連続 ほか）を持つ。

したがって、未検証事項の最優先群を消化する最効率のアクションは **Phase S-eval-57session** を S56 と同条件（ctx=32768 × fa=1 × OT=MoE-only × ub∈{1584, 1586, 1664}、warmup 2 + eval 5、prompt_1k）で実施し、pooled 285-run 統計へ拡張することである。

S57 で同時検証される主な最優先 TODO（S56 レポートより抜粋）:

- Welch (+/-/+) 2 連続 → S57 3 連続 or 新 subtype
- ub=1664 "11+1+3+1+1+1" pattern → S57 normal 4 連続 or 崩壊復帰
- ub=1586 連続崩壊 2 連続 initial → S57 崩壊 3 連続 or normal 復帰
- ub=1584 normal 2 連続 → S57 崩壊復帰 or normal 3 連続
- intra-day 10 session 連続 → S57 intra-day 11 session or inter-day
- Welch |t|>20 ub=1584 + ub=1664 同時達成 initial → S57 同時連続判定
- 3 ub sig 3/3 達成 6 連続 → S57 7 連続 or partial 復帰
- σ_pool 1664 1 位 9 連続 → S57 10 連続 or 1586 奪還
- σ_pool 1586 縮小 3 連続 → S57 4 連続 or 拡大復帰
- pool 差 +0.03 帯復帰 → S57 +0.03 維持 or +0.04 復帰 or +0.02 戻り
- ub=1584 |Δ_max| 担当 2 連続 → S57 3 連続 or 他 ub
- |Δ|>0.5 6 連続 break → S57 復帰 or 縮小継続
- 3 ub Δ pattern (+/-/+) 2 連続 → S57 3 連続 or shift
- ub=1664 崩壊 31/56=55.4% → S57 32/57 or 31/57（過半数 13 連続判定）
- ub=1664 partial 復帰 → S57 accept or reject or partial 連続
- prompt_tps ub=1664 最高 2 連続 → S57 3 連続 or rotation
- warmup1 mode_A_band 復帰 (53 session ぶり) → S57 連続 or break
- cool time 16-18 分 2 連続 → S57 3 連続 or 他 sub-zone
- ub=1664 pool min 14.212 維持 6 連続 → S57 7 連続 or 更新
- ub=1584 pool max 15.477 更新 → S57 維持 or 更新 or reject
- ub=1584 peak 1 位復帰 → S57 連続 or 他 ub
- ub=1586 崩壊 14/56=25.0% → S57 15/57 or 14/57
- ub=1664 pool max 15.534 維持 18 連続 → S57 19 連続 or 更新
- ub=1586 pool max 15.532 維持 14 連続 → S57 15 連続 or 更新

## 実施条件（S56 と完全同一）

| 項目 | 値 |
|------|------|
| GPU サーバ | t120h-p100 (10.1.4.14) |
| モデル | `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M` |
| ctx-size | 32768 |
| flash-attn | 1 |
| cache-type-k/v | f16/f16 |
| OT_REGEX | `blk\.([0-9]\|1[0-3]\|2[0-4]\|3[1-9]\|4[0-7])\.ffn_.*_exps\.weight=CPU` |
| ub / b | {1584, 1586, 1664}、`-b` = `-ub` |
| threads / poll / parallel | 40 / 0 / 1 |
| prompt | `prompts/prompt_1k.txt`（既存コピー、6200 bytes、1086 tokens） |
| warmup / eval | 2 run + 5 run（各 ub） |

所要時間見込: 実バッチ 約 37-40 分、GPU ロック保持 約 40-45 分。

## 実施手順

### ステップ 1: 添付ディレクトリ作成と scripts のコピー

S56 の添付一式を新規ディレクトリにコピーする。

```bash
SRC=report/attachment/2026-04-22_091115_qwen3-122b-c3-phaseSeval56s
# DST timestamp はバッチ終了時刻で決まるので、実施時に決定。
# ここでは仮に DST_TS="YYYY-MM-DD_HHMMSS_qwen3-122b-c3-phaseSeval57s" とする。
DST=report/attachment/${DST_TS}
mkdir -p ${DST}
cp ${SRC}/{batch_phaseSeval56s.sh,start_phaseSeval56s.sh,run_all.sh,measure_phaseI.sh,analyze_phaseSeval56s.py,plot_timeseries.py} ${DST}/
cp -r ${SRC}/prompts ${DST}/
```

コピー後にリネーム:
- `batch_phaseSeval56s.sh` → `batch_phaseSeval57s.sh`
- `start_phaseSeval56s.sh` → `start_phaseSeval57s.sh`
- `analyze_phaseSeval56s.py` → `analyze_phaseSeval57s.py`

### ステップ 2: スクリプト書き換え（機械的な 56 → 57 置換）

変更対象と要点:

- **`batch_phaseSeval57s.sh`**: ファイル名参照（`start_phaseSeval5{6→7}s.sh`）、タグ `Seval5{6→7}s`、ログ `batch_phaseSeval5{6→7}s.log`、echo ラベル `[batchSeval5{6→7}s]`
- **`start_phaseSeval57s.sh`**: セッション識別子、startup_logs ファイル名
- **`run_all.sh`**: タグ（`Seval5{6→7}s_...`）、out ディレクトリプレフィックス
- **`measure_phaseI.sh`**: 参照されるタグ文字列のみ（多くはそのまま）
- **`analyze_phaseSeval57s.py`**:
  - `CUR_SESSION_LABEL = "S57_phaseSeval57s"`
  - `TAG_PREFIX = "Seval57s_fa1_ctx"`
  - `PRIOR_TSVS` リストに S56 の TSV 行（`report/attachment/2026-04-22_091115_qwen3-122b-c3-phaseSeval56s/summary_phaseSeval56s.tsv` + `S56_phaseSeval56s`）を追記
  - 出力: `summary_phaseSeval57s.tsv`、`phaseSeval57s_stats.csv`、`phaseSeval57s_verdict.txt`
- **`plot_timeseries.py`**: S56→S57 ラベル、PNG 出力パスそのまま。S1..S57 の session 一覧へ S57 row 追加。

セッション識別子以外のロジックは一切触らない。

### ステップ 3: GPU ロック取得

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### ステップ 4: バッチ実行

```bash
cd report/attachment/${DST_TS}
bash batch_phaseSeval57s.sh 2>&1 | tee batch_phaseSeval57s.log
```

内容（S56 と同一）:
1. 3 ub 各々で `start_phaseSeval57s.sh` により llama-server を起動
2. `run_all.sh` が warmup 2 + eval 5 run を実行
3. 終了後 llama-server 停止

### ステップ 5: 集計とプロット

```bash
python3 analyze_phaseSeval57s.py    # summary/stats/verdict 生成
python3 plot_timeseries.py          # timeseries_eval_tps.png (S1..S57)
```

### ステップ 6: GPU ロック解放

```bash
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### ステップ 7: レポート作成

バッチ終了時刻で timestamp を確定し、`report/2026-04-22_HHMMSS_qwen3-122b-c3-phaseSeval57s.md` を作成。

レポート構成は S56 と同形式 + 以下の必須セクション:
- 前提・目的（S56 からの継承 TODO を明記）
- 核心発見サマリ（S57 での新記録・break・継続項目）
- pooled 285-run 統計
- intra-day cluster 進行（2026-04-22 intra-day 11 session 目か否か）
- Welch 再計算（3 ub t-stat、subtype）
- **未検証事項** セクション（ユーザ指示の必須項目）
- **検証完了後に実施すべき TODO** セクション（同上）

`plan.md` として本ファイルの内容をそのまま `attachment/${DST_TS}/plan.md` へ配置。

## Critical files

- S56 テンプレ: `report/attachment/2026-04-22_091115_qwen3-122b-c3-phaseSeval56s/*`
- GPU ロック: `.claude/skills/gpu-server/scripts/{lock,unlock}.sh`
- REPORT.md: `REPORT.md`
- CLAUDE.md: `CLAUDE.md`

## 再利用される既存機能

- **S56 scripts**: そのままコピー + 機械的 56→57 置換のみで流用（ロジック差分ゼロ、差分は参照行追加と識別子のみ）
- **gpu-server skill**: `lock.sh` / `unlock.sh`
- **llama-server skill**: 起動パターンは S56 start_phaseSeval56s.sh がそのまま再利用可
- **prompts/prompt_1k.txt**: 既存ファイルを再コピー（同一内容で継続）

## 検証 (end-to-end)

- [ ] ロック取得後、ロックファイルを `.claude/skills/gpu-server/scripts/lock-status.sh t120h-p100` で確認
- [ ] バッチ実行ログ `batch_phaseSeval57s.log` の末尾で 3 ub 全て warmup 2 + eval 5 が完了していること
- [ ] `summary_phaseSeval57s.tsv` に **S57 + 過去 S1-S56** の全 run（warmup と eval 別フラグ）が並んでいること
- [ ] `phaseSeval57s_stats.csv` に pooled 285-run の mean/σ/min/max/Welch t-stat が出ていること
- [ ] `timeseries_eval_tps.png` が S1..S57 の 57 点 + 3 ub の trend line 付きで生成されていること
- [ ] ロック解放後に `.claude/skills/gpu-server/scripts/lock-status.sh` で解放確認
- [ ] レポート内の添付リンクが全て有効（attachment/ ディレクトリ配下にファイル存在）

## 注意事項

- **ロック取得失敗時**: 他セッションが t120h-p100 を使用中なら即時中止、ユーザへ報告して指示待ち。
- **llama-server 起動失敗時**: S56 と同一 VRAM 構成なので通常成功するはずだが、起動ログ `startup_logs/` を確認し、OOM などあれば中止。
- **バッチ中断時**: GPU ロックを必ず解放してから報告する。
- **日付**: 今日は 2026-04-22。S47-S56 の 10 session が既に 2026-04-22 intra-day。S57 も同日なら intra-day 11 session 連続、日をまたげば inter-day 2 例目（2026-04-23）となり意味が変わる。レポートの「intra-day か inter-day か」判定はバッチ開始時刻で決まる。
