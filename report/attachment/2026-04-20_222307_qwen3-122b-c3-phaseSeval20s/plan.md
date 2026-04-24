# Phase S-eval-20session 実施計画

## Context

直前レポート [2026-04-20_212313_qwen3-122b-c3-phaseSeval19s.md](../../projects/llm-server-ops/report/2026-04-20_212313_qwen3-122b-c3-phaseSeval19s.md) の「検証完了後に実施すべき TODO」筆頭に **★最重要: Phase S-eval-20session 候補** が置かれている。

S19 で観測された 5 大事件（cool time 261 分 + ub=1664 pool min 14.293 更新 + ub=1584 2→非崩壊復帰 + ub=1586 mode_B 単独 1 位 + Welch 2 ub sig 新類型）の継続性を、n=20 で検証する。具体的に追跡する軸:

1. **ub=1584 非崩壊連続性** — S19 15.083 → S20 非崩壊継続 or 再崩壊
2. **ub=1664 下帯 2 連続 or 中/上帯復帰** — S19 14.298 急落後の挙動、pool min 14.293 の再現性
3. **ub=1586 mode_B 単独 1 位持続** — S19 で A/B 均衡が崩れたため、S20 で mode_A 復帰なら再均衡、mode_B 継続なら構造転換固定化
4. **Welch 2 ub sig 類型の周期性** — S19 で初観測、S20 で再観測 or 0/1/3 ub sig 回帰
5. **cool time 効果** — S19 の 261 分 cool time と S20 cool time の差から「長 cool time → 大変動」仮説を補強

所要約 40 分（warmup 2 + eval 5 × 3 条件 + 分析）。既存の S19 スクリプト群を S20 向けに名称変更するだけで実施可能。

## 変更方針

**条件は S1–S19 と完全同一**（変えない）:
- GPU サーバ: t120h-p100、llama.cpp 既存 binary
- モデル: Qwen3.5-122B-A10B-Q4_K_M
- パラメータ: fa=1、f16/f16 KV、ctx=32768、OT=MoE-only、numactl node1、threads=40、poll=0、ngl=999
- ub: {1584, 1586, 1664}、各 warmup 2 + eval 5
- prompt: `prompts/prompt_1k.txt`（S19 から流用）、max_tokens=256、cooldown=60s

**書き換え対象は識別子のみ** (S19→S20 rename):
- ファイル名: `*_phaseSeval19s*` → `*_phaseSeval20s*`
- TAG_PREFIX: `Seval19s` → `Seval20s`
- CUR_SESSION_LABEL, MODE_GROUPS, コメント内のセッション番号（18→19、19→20）

## 実行手順

### 1. 作業ディレクトリ作成と資材コピー

```bash
TS=$(date +%Y-%m-%d_%H%M%S)
BASE=/home/ubuntu/projects/llm-server-ops/report/attachment
SRC=$BASE/2026-04-20_212313_qwen3-122b-c3-phaseSeval19s
DST=$BASE/${TS}_qwen3-122b-c3-phaseSeval20s
mkdir -p "$DST"
cp -r "$SRC"/{start_phaseSeval19s.sh,batch_phaseSeval19s.sh,run_all.sh,measure_phaseI.sh,analyze_phaseSeval19s.py,prompts} "$DST"/
```

`prompts/prompt_1k.txt` は S1 以来 19 session で同一ファイル流用のため、変更しない。

### 2. ファイル名リネームと本文中の識別子置換

- `start_phaseSeval19s.sh` → `start_phaseSeval20s.sh`（本文中の `phaseSeval19s` → `phaseSeval20s`、`Seval19s` → `Seval20s`）
- `batch_phaseSeval19s.sh` → `batch_phaseSeval20s.sh`（同上）
- `analyze_phaseSeval19s.py` → `analyze_phaseSeval20s.py`

### 3. analyze スクリプトの PRIOR_TSVS / CUR_SESSION_LABEL / MODE_GROUPS 更新

- `PRIOR_TSVS` の末尾に S19 を追記:
  ```python
  ("S19_phaseSeval19s",
   SCRIPT_DIR.parent / "2026-04-20_212313_qwen3-122b-c3-phaseSeval19s" / "summary_phaseSeval19s.tsv"),
  ```
- `CUR_SESSION_LABEL` を `"S20_phaseSeval20s"` に変更
- `MODE_GROUPS` に `"prev_S19"`、`"cur_S20"` を追加（S19 定義パターンを踏襲）
- コメント内の "19 session" → "20 session"、"95-run" → "100-run"、"18 transitions" → "19 transitions" 系を書き換え（grep で拾って一括修正）
- Welch t の prior が n_prior=95 になる点に注意（S1–S19 の 19 session × 5 = 95 run）

### 4. GPU ロック取得 → バッチ実行 → 分析 → 解放

```bash
# lock
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 実行
cd "$DST"
bash batch_phaseSeval20s.sh > batch_phaseSeval20s.log 2>&1

# 分析
python3 analyze_phaseSeval20s.py

# 停止・解放
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

所要時間: バッチ実行 約 45 分 + 分析数分。

### 5. レポート作成

`report/YYYY-MM-DD_HHMMSS_qwen3-122b-c3-phaseSeval20s.md` を [REPORT.md](../../projects/llm-server-ops/REPORT.md) フォーマットに従って作成。S19 レポートの構成を踏襲し、以下のセクションを必ず含める:

- ★タイトル 1 行サマリ、実施日時、GPU ロック取得/解放
- 添付ファイル、参照、前提・目的（S19 → S20 の cool time と 追跡軸）
- 判定しきい値、成功条件、環境情報、セッション間隔（S19 終了時刻から S20 開始時刻までの cool time を明記）
- 再現方法、実行結果サマリ（S19 同構成: 20 session 時系列 / Welch t / pooled 100-run / ピーク順序 / 崩壊頻度 / within-σ / warmup band/delta / Δ パターン / 帯構造）
- **「未検証事項」セクション** — S19 レポートの未検証事項から、本 Phase で潰したものに `[x]`、未潰しは `[ ]` で継続。本 Phase S-eval-20session で判明した新規項目を「新規項目（本 Phase S-eval-20session で判明・発生）」として追加
- **「検証完了後に実施すべき TODO」セクション** — S19 レポートから継承、本 Phase で追加される TODO（Phase S-eval-21session 候補など）を新規項目として追記
- 補足（核心発見のサマリ）

## 重要な批判的判定ポイント

- **eval_tps が崩壊判定 (<15.0) か否か** を ub ごとに記録
- **ub=1664 が下帯 (<14.80) / 中帯 / 上帯 (>15.20) のどれか** を判定、S19 下帯の 2 連続なら「下帯 2 連続初観測」
- **peak order の mode** が A/B/C/D/E のどれか、未観測 mode (1584,1664,1586) が出現したかをチェック
- Welch t の sig 数（0/1/2/3 ub sig）をカウント、S19 の 2 ub sig 類型再観測は要注目
- pool max/min の更新有無、特に ub=1664 pool min 14.293 を下回ったら再度記録

## 注意・制約

- **sudo 不要**: このバッチ処理には sudo 権限は必要ない（llama-server 起動は ssh リモートで nohup 実行、NUMA は numactl ラッパで OK）
- **GPU ロック必須**: `gpu-server` skill で必ず取得・解放
- **スクリプト実行は相対パス**: プロジェクトルートから `.claude/skills/...` で呼ぶ（CLAUDE.md 制約）
- **途中で llama-server の起動に失敗した場合** (OOM / ubatch lower bound 等): `startup_logs/` のログを確認し、原因を特定してから再試行。Phase 続行を強行しない。
- **ロック解放は必ず実施**: 成功・失敗に関わらず最後に `unlock.sh` を呼ぶ

## 検証方法（end-to-end）

1. `batch_phaseSeval20s.log` 末尾で 3 条件 × 7 run すべて完走したことを確認
2. `summary_phaseSeval20s.tsv` が 21 行（ヘッダ + 3 ub × 7 run）生成されている
3. `phaseSeval20s_stats.csv`、`phaseSeval20s_verdict.txt` が生成されている
4. 分析結果の「20 session mean 時系列」表に S20 列が追加、pooled 100-run の n が各 ub で 100 になっている
5. GPU ロックが解放済であることを `gpu-server` skill で確認
6. レポートに未検証事項 / 検証完了後 TODO が両セクションとも存在する

## 変更対象ファイルパス

- **新規作成（リネームコピー）**:
  - `report/attachment/YYYY-MM-DD_HHMMSS_qwen3-122b-c3-phaseSeval20s/start_phaseSeval20s.sh`
  - `report/attachment/YYYY-MM-DD_HHMMSS_qwen3-122b-c3-phaseSeval20s/batch_phaseSeval20s.sh`
  - `report/attachment/YYYY-MM-DD_HHMMSS_qwen3-122b-c3-phaseSeval20s/analyze_phaseSeval20s.py`
  - `report/attachment/YYYY-MM-DD_HHMMSS_qwen3-122b-c3-phaseSeval20s/run_all.sh`（S19 流用、無改変）
  - `report/attachment/YYYY-MM-DD_HHMMSS_qwen3-122b-c3-phaseSeval20s/measure_phaseI.sh`（S19 流用、無改変）
  - `report/attachment/YYYY-MM-DD_HHMMSS_qwen3-122b-c3-phaseSeval20s/prompts/prompt_1k.txt`（S19 流用、無改変）
- **新規作成（レポート本体）**:
  - `report/YYYY-MM-DD_HHMMSS_qwen3-122b-c3-phaseSeval20s.md`
- **更新（レポート索引）**:
  - `REPORT.md`（レポート追記ルールに従う）

## 再利用する既存資産

- GPU ロック: `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- llama-server 停止: `.claude/skills/llama-server/scripts/stop.sh`
- 計測・分析・バッチ: S19 ディレクトリ配下スクリプト（すべてリネームコピー元）
- プロンプト: `prompts/prompt_1k.txt`（Phase Sbfine3 由来、S1 以降共通）
