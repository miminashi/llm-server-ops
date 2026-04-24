# Phase S-eval-52session 実施プラン

## Context

直前レポート `report/2026-04-22_035441_qwen3-122b-c3-phaseSeval51s.md` の「未検証事項」
セクション中、最優先度項目の大半は「S52 で継続観測することで判定可能」な事項である:

- mode_B 復帰 1 session fix → S52 で 2 連続 or 他 mode 判定
- ub=1664 "11+1+N" pattern → S52 で再崩壊 2 連続 or normal 復帰 判定
- ub=1584 崩壊 break 1 session fix → S52 で normal 継続 or 崩壊復帰 判定
- intra-day 5 session 連続 initial → S52 で 6 session 連続 or inter-day 2 例目 判定
- Welch (+/+/-) 51-session 初 subtype 連続判定
- σ_pool 1664 1 位 4 連続 → 5 連続判定
- pool 差 +0.05 帯 2 連続 → 3 連続判定
- ub=1664 pool min 14.212 → S52 更新 or 回復 判定
- prompt_tps ub=1584 最高 4 連続 → 5 連続 or rotation 判定
- pure mode_B 復帰 → 2 連続 or hybrid 復帰 判定
- mode_B_delta 2 連続 → 3 連続判定

加えて「検証完了後に実施すべき TODO」の `Phase S-eval-52session 候補` が明示されており、
この Phase を実施することで上記多数の未検証事項を一度に判定できる。

**目的**: Phase S-eval-52session を S51 と完全同一条件で実施し、n=52 pooled 260-run
統計を確立。上記 ★最優先 項目を一括判定する。

## アプローチ

S51 と同一の 3 条件 (ub={1584, 1586, 1664}) × (warmup 2 + eval 5) を、ctx=32768 ×
fa=1 × OT=MoE-only 固定で第 52 session (S52) として実施。n=52 pooled 260-run へ拡張、
S51 レポートの ★最優先 TODO 群を同時検証、時系列プロット (matplotlib PNG) を
S1..S52 へ更新、3 ub 別線形回帰 (trend line) を継続重畳描画。

## 手順

### 1. 添付ディレクトリ準備

```bash
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_NAME="${TS}_qwen3-122b-c3-phaseSeval52s"
ATTACH_DIR="report/attachment/${REPORT_NAME}"
mkdir -p "$ATTACH_DIR/startup_logs" "$ATTACH_DIR/prompts"
cp /home/ubuntu/.claude/plans/todo-wobbly-planet.md "$ATTACH_DIR/plan.md"
```

### 2. S51 スクリプト群を S52 用に複製し 51→52 置換

対象ファイル（S51 attachment からコピー、ファイル名と中身両方で `51` → `52` / `Seval51s` → `Seval52s` 置換）:

- `start_phaseSeval52s.sh`（`REMOTE_LOG` prefix のみ phaseSeval52s）
- `batch_phaseSeval52s.sh`
- `run_all.sh`（prompt_1k パス参照のみ、置換不要）
- `measure_phaseI.sh`（置換不要、そのままコピー）
- `analyze_phaseSeval52s.py`（PRIOR_TSVS に S51 を追加、CUR_SESSION_LABEL を S52 に、MODE_GROUPS 拡張、TAG_PREFIX を `Seval52s_fa1_ctx` に）
- `plot_timeseries.py`（`S_EVAL_DIRS` に S51 行追加、末尾 S52 行は本 Phase summary TSV）
- `prompts/prompt_1k.txt`（S51 と同一、コピー）

### 3. GPU ロック取得 → バッチ実行 → 集計・プロット → ロック解放

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
cd "$ATTACH_DIR"
bash batch_phaseSeval52s.sh 2>&1 | tee batch_phaseSeval52s.log
python3 analyze_phaseSeval52s.py
python3 plot_timeseries.py
cd -
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

所要時間見積: S51 が 36'54" → S52 ≈ 36-40 分（40 分見込み）

### 4. レポート作成

ファイル: `report/${TS}_qwen3-122b-c3-phaseSeval52s.md`

セクション構成（S51 レポートを踏襲）:
- 添付ファイル
- 参照（直前 S51、S50、S49、S1 等）
- 前提・目的
- 核心発見サマリ（S52 で判明した事項を列挙）
- 環境情報（S51 と同一）
- 再現方法
- **未検証事項**（既知項目継承 + 新規項目）
- **検証完了後に実施すべき TODO**（Phase S-eval-53session 候補ほか）

## 重要ファイル

- 参照: `report/2026-04-22_035441_qwen3-122b-c3-phaseSeval51s.md`（直前 S51）
- 参照: `report/attachment/2026-04-22_035441_qwen3-122b-c3-phaseSeval51s/`（スクリプト雛形・S50 までの PRIOR_TSVS 参照）
- 出力: `report/${TS}_qwen3-122b-c3-phaseSeval52s.md`
- 出力: `report/attachment/${TS}_qwen3-122b-c3-phaseSeval52s/`

## 既存ユーティリティの再利用

- GPU ロック: `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh` / `lock-status.sh`
- llama-server 停止: `.claude/skills/llama-server/scripts/stop.sh`
- S51 scripts (そのまま `sed s/51/52/g` 系で対応可能): `start_phaseSeval51s.sh` → `start_phaseSeval52s.sh` 等

## 検証方法

1. `ls report/attachment/${REPORT_NAME}/out_Seval52s_fa1_ctx32768_ub{1584,1586,1664}_{warmup,1k}/` で
   warmup 2 run + eval 5 run 合計 21 JSON が揃うこと
2. `phaseSeval52s_verdict.txt` に n=52 pooled 260-run、Welch t、崩壊頻度、
   mode 分類 が出力されること
3. `timeseries_eval_tps.png` が S1..S52 の 52 session 折れ線 + trend line + Sbfine ★ ref
   で生成されること
4. レポート MD に「未検証事項」「検証完了後に実施すべき TODO」両セクションが
   含まれ、S52 で新規発見の項目が ★最優先/高優先/中優先 ラベル付きで列挙されること
