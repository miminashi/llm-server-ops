# Phase S-eval-49session 実装プラン

## Context

直前レポート [2026-04-22_010836_qwen3-122b-c3-phaseSeval48s.md](../../../projects/llm-server-ops/report/2026-04-22_010836_qwen3-122b-c3-phaseSeval48s.md) の未検証事項 (★最優先 TODO 20+ 項目) を同時検証するため、**Phase S-eval-49session** を S48 と同条件で実施する。

### 問題意識 / 検証したい主な未検証事項（S48 報告の ★最優先群から）

同条件 1 session の追加実行で以下すべてが同時判定できる:

1. **ub=1586 大幅回復 15.105 → S49 連続回復 (15 帯定着) or 再崩壊** — S22→S23→S24 (13.844→15.133→15.261) の再現可否
2. **ub=1664 10 連続崩壊 → S49 11 連続 or 離脱** (48-session 0 例の 11 連続)
3. **ub=1664 下帯 6 連続 → S49 7 連続 or 離脱** (bounded [14.214, 14.714])
4. **mode_A 復帰 19 session ぶり → S49 mode_A 2 連続 or 他 mode**
5. **intra-day 2 session 連続 → S49 intra-day 3 session or inter-day 2 例目** (2026-04-22 cluster 発展)
6. **double collapse break → S49 復帰 or 単独崩壊継続**
7. **ub=1664 pool min 14.214 新記録 → S49 更新 or 回復**
8. **Welch (+/not_sig/-) subtype → S49 連続 or shift**
9. **σ_pool 1664 1 位復帰 1 session fix → S49 連続 or 1586 奪還**
10. **σ_pool 1584 縮小 4 連続 initial → S49 5 連続 or 拡大**
11. **pool 差 +0.04 帯 2 連続 → S49 3 連続 or shift**
12. **ub=1586 |Δ_max| 担当 2 連続 → S49 3 連続 or 他 ub**
13. **3 ub Δ (-/+/-) 復帰 3 例目 → S49 連続 or shift**
14. **境界帯 18+ 分連続 7 / 20+ 分 2 連続 → S49 更新 or 離脱**
15. **hybrid 8 連続 → pure 復帰 or 9 連続**

### 期待成果

- 第 49 session (S49) 1 本追加で上記 20+ 個の ★最優先 TODO を同時判定
- 48→49 session 拡張で pooled 245-run 統計、σ_pool trend、inter/intra-day cluster 判定を更新
- 時系列プロット PNG (trend line 重畳) を S1..S49 へ更新

## 実行条件（S48 踏襲）

- 対象サーバ: **t120h-p100** (10.1.4.14)
- モデル: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- 固定: `ctx=32768` × `fa=1` × `OT=MoE-only (blk.[0-13,21-24,31-47].ffn_*_exps=CPU)` × `numactl --cpunodebind=1 --membind=1` × `threads=40` × `poll=0`
- 走査: `ub ∈ {1584, 1586, 1664}` × 各 (warmup 2 run + 1k eval 5 run)
- 所要予測: 40-48 分（S48 = 36 分 48 秒）

## 実装ステップ

### 1. GPU ロック取得

```bash
.claude/skills/gpu-server/scripts/lock.sh acquire t120h-p100 --reason "phase-Seval-49session"
```

### 2. 添付ディレクトリ作成 + スクリプト複製

```bash
STAMP=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_NAME="${STAMP}_qwen3-122b-c3-phaseSeval49s"
ATTACH="report/attachment/${REPORT_NAME}"
SRC48="report/attachment/2026-04-22_010836_qwen3-122b-c3-phaseSeval48s"

mkdir -p "${ATTACH}/startup_logs"
cp -r "${SRC48}/prompts" "${ATTACH}/"            # 1k prompt（固定の Sbfine 系プロンプト）
cp "${SRC48}/measure_phaseI.sh" "${ATTACH}/"
cp "${SRC48}/run_all.sh" "${ATTACH}/"
```

`start_phaseSeval49s.sh` / `batch_phaseSeval49s.sh` / `analyze_phaseSeval49s.py` / `plot_timeseries.py` は `48` → `49` に置換した新規作成（S48 版からの sed 置換 + PRIOR_TSVS に S48 エントリ追加）。

### 3. バッチ実行

```bash
cd "${ATTACH}"
bash batch_phaseSeval49s.sh 2>&1 | tee batch_phaseSeval49s.log
```

### 4. 集計 + verdict + 時系列プロット

```bash
python3 analyze_phaseSeval49s.py    # summary_phaseSeval49s.tsv, phaseSeval49s_stats.csv, phaseSeval49s_verdict.txt
python3 plot_timeseries.py          # timeseries_eval_tps.png (S1..S49, trend line 重畳)
```

### 5. レポート作成（plan モードの必須対応）

`report/${REPORT_NAME}.md` を REPORT.md 規約で作成し:

- **実施日時（JST、分単位）**
- **添付ファイル一覧**（plan.md を含む。`cp /home/ubuntu/.claude/plans/todo-stateful-hejlsberg.md ${ATTACH}/plan.md`）
- **参照**（直前 S48 + 関連 session）
- **前提・目的**
- **核心発見サマリ**（S49 での mean / Δ / mode / Welch / σ_pool / pool 差 / 境界帯 / hybrid / peak / 崩壊頻度 / 14→15 帯 rebound の再現）
- **環境情報 / 再現方法**
- **未検証事項**（既知項目継続 + 新規 ★最優先群、ユーザ指示通り記載）
- **検証完了後に実施すべき TODO**（ユーザ指示通り記載）

### 6. GPU ロック解放

```bash
.claude/skills/gpu-server/scripts/lock.sh release t120h-p100
```

## 重要ファイル

### 複製・流用（そのままコピー）

- `report/attachment/2026-04-22_010836_qwen3-122b-c3-phaseSeval48s/measure_phaseI.sh`
- `report/attachment/2026-04-22_010836_qwen3-122b-c3-phaseSeval48s/run_all.sh`
- `report/attachment/2026-04-22_010836_qwen3-122b-c3-phaseSeval48s/prompts/prompt_1k.txt`

### 修正コピー（`48` → `49` 置換）

- `start_phaseSeval49s.sh` — `phaseSeval48s` 文字列を `phaseSeval49s` に置換のみ
- `batch_phaseSeval49s.sh` — 同上 + 履歴コメント末尾に `48s` 追記
- `analyze_phaseSeval49s.py` — PRIOR_TSVS に S48 エントリ追加、CURRENT_TAG を `S49_phaseSeval49s` に更新、scripted comparison table を S48 基準で増補
- `plot_timeseries.py` — S48 エントリ追加、軸範囲・title を S49 用に更新

### 変更ファイル（プロジェクト側）

- 新規: `report/${STAMP}_qwen3-122b-c3-phaseSeval49s.md`
- 新規: `report/attachment/${STAMP}_qwen3-122b-c3-phaseSeval49s/...`
- 触らない: `CLAUDE.md`, `REPORT.md`, skill 系（既存 stop.sh のみ呼び出し）

## 再利用する既存関数・スキル

- `.claude/skills/gpu-server/scripts/lock.sh` — ロック acquire / release
- `.claude/skills/llama-server/scripts/stop.sh` — llama-server 停止（batch 内で呼び出し）
- `measure_phaseI.sh` / `run_all.sh` — 無変更で流用
- `analyze_phaseSeval48s.py` の既存 `CRITICAL_THRESHOLD` / `compute_welch_t` / `mode_classify` / `cohen_d` 等の関数（48→49 差分のみ更新）

## 検証手順（end-to-end）

1. `.claude/skills/gpu-server/scripts/lock-status.sh t120h-p100` でロック保持確認
2. `curl -sf http://10.1.4.14:8000/health` で /health OK
3. `batch_phaseSeval49s.log` に 3 ub 全てで `measure done` 出力
4. `summary_phaseSeval49s.tsv` に 3 ub × (2 warmup + 5 eval) = 21 行
5. `phaseSeval49s_stats.csv` で n=49 session 集計値が出力
6. `phaseSeval49s_verdict.txt` で verdict 成立（`ctx=32768 × fa=1 × OT-MoE 3 ub` pool mean / σ / 崩壊頻度 / 14→15 帯 rebound 再現判定）
7. `timeseries_eval_tps.png` に S1..S49 × 3 ub × trend line 描画
8. レポート本文に S49 mean 3 値、3 ub Δ 符号、mode 分類、Welch 結果、ロック release 記録が含まれる
9. GPU ロックが確実に release されている（`lock-status.sh` で空）

## 中断時リカバリ

- 途中 OOM / ub-reject: `start_phaseSeval49s.sh` が exit 2 / 3 で abort → batch 続行せず原因確認
- /health 不達: 80*5s=400s 待ちで abort、`startup_logs/` に保存済ログを確認
- バッチ後も必ず `bash .claude/skills/llama-server/scripts/stop.sh t120h-p100` + ロック release を実行
