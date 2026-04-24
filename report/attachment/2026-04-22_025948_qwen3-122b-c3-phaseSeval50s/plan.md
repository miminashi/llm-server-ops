# Phase S-eval-50session 実装プラン

## Context

直前レポート [2026-04-22_020513_qwen3-122b-c3-phaseSeval49s.md](../../projects/llm-server-ops/report/2026-04-22_020513_qwen3-122b-c3-phaseSeval49s.md) の未検証事項「★最優先」群 20+ 項目（「次 Phase 候補」でも **Phase S-eval-50session** が ★最優先に明記）を同時検証するため、**Phase S-eval-50session** を S49 と同条件で実施する。

### 問題意識 / S49 レポートから継承される「★最優先」未検証 regime（n=50 session 追加で同時判定可能）

1. **mode_A 2 連続 → S50 mode_A 3 連続 or 他 mode**（49-session 0 例の 3 連続 mode_A）
2. **ub=1664 11 連続崩壊 → S50 12 連続 or 離脱**（49-session 0 例、mixed-band 中帯 3 + 下帯 8）
3. **ub=1664 下帯 7 連続 → S50 8 連続 or 離脱**（bounded range [14.214, 14.714]）
4. **intra-day 3 session 連続 → S50 intra-day 4 session or inter-day 2 例目**（2026-04-22 cluster 発展）
5. **ub=1664 単独崩壊 2 連続 → S50 3 連続 or double 復帰**
6. **|Δ_max|=0.047 最小 record → S50 更新 or 大幅拡大**（49-session 最小 stability record）
7. **ub=1586 |Δ_max| 担当 3 連続 → S50 4 連続 or 他 ub**
8. **ub=1664 |Δ_max| 担当なし 7 連続 → S50 8 連続 or 担当復帰**
9. **3 ub 全 |Δ|<0.1 pattern → S50 連続 or 大変動**
10. **Welch (+/-/-) subtype → S50 連続 or shift**
11. **Welch |t|>30 3 連続 → S50 4 連続 or 大幅減**
12. **σ_pool 1664 1 位 2 連続 → S50 3 連続 or 1586 奪還**
13. **σ_pool 1584 縮小 5 連続 → S50 6 連続 or 拡大**
14. **σ_pool 1586 縮小 2 連続 → S50 3 連続 or 拡大**
15. **σ_pool 1664 +0.010 拡大 2 連続 → S50 3 連続 or 縮小**
16. **pool 差 +0.041 (+0.04 帯 3 連続) → S50 +0.04 帯 4 連続 or shift**
17. **ub=1584 peak 1 位 3 連続 → S50 4 連続 or 1586 peak 復帰**
18. **prompt_tps ub=1584 最高 2 連続 → S50 3 連続 or rotation**（14 session rotation 2 巡目 4 session 目）
19. **3 ub Δ (+/-/+) 復帰 8 例目 → S50 (-/+/-) 9 例目 or 他**（2 session interval rotation 4 巡目）
20. **境界帯 18+ 分連続 7 break → S50 18+ 再到達 or 通常帯定着**
21. **hybrid 9 連続 → S50 pure 復帰 or 10 連続**
22. **mode_A_delta 維持 2 連続 → S50 3 連続 or 他**
23. **ub=1664 pool max 15.534 維持 11 連続 → S50 維持 or 更新**
24. **ub=1586 pool max 15.532 維持 7 連続 → S50 維持 or 更新**
25. **ub=1664 pool min 14.214 維持 2 連続 → S50 更新 or 回復**

### 期待成果

- 第 50 session (S50) 1 本追加で上記 25+ 個の「★最優先」TODO を同時判定
- 49→50 session 拡張で pooled 250-run 統計、σ_pool trend、inter/intra-day cluster 判定を更新
- 時系列プロット PNG（3 ub trend line 重畳）を S1..S50 へ更新
- **節目の n=50 session 到達**（50-session 集計 initial）

## 実行条件（S49 踏襲）

- 対象サーバ: **t120h-p100** (10.1.4.14)
- モデル: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- 固定: `ctx=32768` × `fa=1` × `OT=MoE-only (blk.[0-13,21-24,31-47].ffn_*_exps=CPU)` × `numactl --cpunodebind=1 --membind=1` × `threads=40` × `poll=0`
- 走査: `ub ∈ {1584, 1586, 1664}` × 各 (warmup 2 run + 1k eval 5 run)
- 所要予測: 36-42 分（S49 = 36 分 38 秒）

## 実装ステップ

### 1. GPU ロック取得

skill `gpu-server` の lock.sh で t120h-p100 を acquire（reason: `phase-Seval-50session`）。

### 2. 添付ディレクトリ作成 + スクリプト複製

```bash
STAMP=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_NAME="${STAMP}_qwen3-122b-c3-phaseSeval50s"
ATTACH="report/attachment/${REPORT_NAME}"
SRC49="report/attachment/2026-04-22_020513_qwen3-122b-c3-phaseSeval49s"

mkdir -p "${ATTACH}/startup_logs"
cp -r "${SRC49}/prompts" "${ATTACH}/"       # 1k prompt（固定の Sbfine 系プロンプト、不変）
cp "${SRC49}/measure_phaseI.sh" "${ATTACH}/"
cp "${SRC49}/run_all.sh" "${ATTACH}/"
```

次の 4 ファイルは `49` → `50` 置換（+ PRIOR_TSVS に S49 エントリ追加）で新規作成：

- `start_phaseSeval50s.sh` — `phaseSeval49s` → `phaseSeval50s` 置換のみ
- `batch_phaseSeval50s.sh` — 同上 + 履歴コメント末尾に `49s` 追記
- `analyze_phaseSeval50s.py` — PRIOR_TSVS に S49 エントリ追加、CURRENT_TAG を `S50_phaseSeval50s` に更新、scripted comparison table を S49 基準で増補
- `plot_timeseries.py` — S49 エントリ追加、軸範囲・title を S50 用に更新（trend line 重畳継続）

### 3. バッチ実行

```bash
cd "${ATTACH}"
bash batch_phaseSeval50s.sh 2>&1 | tee batch_phaseSeval50s.log
```

実行内容: 3 ub × (warmup 2 run + 1k eval 5 run) = 21 run。各 ub 切替で llama-server を停止→起動→health 待ち→計測→停止。

### 4. 集計 + verdict + 時系列プロット

```bash
python3 analyze_phaseSeval50s.py    # summary_phaseSeval50s.tsv, phaseSeval50s_stats.csv, phaseSeval50s_verdict.txt
python3 plot_timeseries.py          # timeseries_eval_tps.png (S1..S50, trend line 重畳)
```

### 5. レポート作成

`report/${REPORT_NAME}.md` を REPORT.md 規約で作成し、以下を含める：

- **実施日時**（JST、分単位）
- **添付ファイル一覧**（plan.md を含む。`cp /home/ubuntu/.claude/plans/todo-lazy-bear.md ${ATTACH}/plan.md`）
- **参照**（直前 S49 + 関連 session）
- **前提・目的**
- **核心発見サマリ**（S50 での mean / Δ / mode / Welch / σ_pool / pool 差 / 境界帯 / hybrid / peak / 崩壊頻度 / mode_A 連続状況）
- **環境情報 / 再現方法**
- **未検証事項**（既知項目継続 + 新規「★最優先」群、ユーザ指示通り記載）
- **検証完了後に実施すべき TODO**（ユーザ指示通り記載）

### 6. GPU ロック解放

skill `gpu-server` の lock.sh で t120h-p100 を release。

## 重要ファイル

### 複製・流用（そのままコピー）

- `report/attachment/2026-04-22_020513_qwen3-122b-c3-phaseSeval49s/measure_phaseI.sh`
- `report/attachment/2026-04-22_020513_qwen3-122b-c3-phaseSeval49s/run_all.sh`
- `report/attachment/2026-04-22_020513_qwen3-122b-c3-phaseSeval49s/prompts/prompt_1k.txt`

### 修正コピー（`49` → `50` 置換）

- `start_phaseSeval50s.sh` — remote_log prefix / echo prefix を `phaseSeval50s` に統一
- `batch_phaseSeval50s.sh` — 履歴コメント末尾に `49s` 追記、start 呼び出しを 50 版に置換
- `analyze_phaseSeval50s.py` — PRIOR_TSVS に S49 エントリ追加、CURRENT_TAG 更新、tables 増補
- `plot_timeseries.py` — S49 point 追加、title/軸更新（trend line 継続）

### 変更ファイル（プロジェクト側）

- 新規: `report/${STAMP}_qwen3-122b-c3-phaseSeval50s.md`
- 新規: `report/attachment/${STAMP}_qwen3-122b-c3-phaseSeval50s/...`
- 触らない: `CLAUDE.md`, `REPORT.md`, skill 本体（skill script の呼び出しのみ）

## 再利用する既存関数・スキル

- `.claude/skills/gpu-server/scripts/lock.sh` — ロック acquire / release
- `.claude/skills/llama-server/scripts/stop.sh` — llama-server 停止（batch 内で呼び出し）
- `measure_phaseI.sh` / `run_all.sh` — 無変更で流用
- `analyze_phaseSeval49s.py` の既存 `CRITICAL_THRESHOLD` / `compute_welch_t` / `mode_classify` / `cohen_d` 等の関数（49→50 差分のみ更新）

## 検証手順（end-to-end）

1. `.claude/skills/gpu-server/scripts/lock-status.sh t120h-p100` でロック保持確認
2. `curl -sf http://10.1.4.14:8000/health` で /health OK
3. `batch_phaseSeval50s.log` に 3 ub 全てで `measure done` 出力
4. `summary_phaseSeval50s.tsv` に 3 ub × (2 warmup + 5 eval) = 21 行
5. `phaseSeval50s_stats.csv` で n=50 session 集計値が出力
6. `phaseSeval50s_verdict.txt` で verdict 成立（`ctx=32768 × fa=1 × OT-MoE 3 ub` pool mean / σ / 崩壊頻度 / mode_A 連続 / 下帯連続等の再現判定）
7. `timeseries_eval_tps.png` に S1..S50 × 3 ub × trend line 描画
8. レポート本文に S50 mean 3 値、3 ub Δ 符号、mode 分類、Welch 結果、ロック release 記録が含まれる
9. GPU ロックが確実に release されている（`lock-status.sh` で空）

## 中断時リカバリ

- 途中 OOM / ub-reject: `start_phaseSeval50s.sh` が exit 2 / 3 で abort → batch 続行せず原因確認
- /health 不達: 80*5s=400s 待ちで abort、`startup_logs/` に保存済ログを確認
- バッチ後も必ず `bash .claude/skills/llama-server/scripts/stop.sh t120h-p100` + ロック release を実行

## 判定される regime の帰結パターン（要約）

S50 1 session 追加で、主要 regime（mode_A 連続、ub=1664 崩壊連続、下帯連続、|Δ_max| stability record、Welch subtype 連続、σ_pool 1 位連続、pool 差 +0.04 帯連続、境界帯、hybrid、peak rotation 等）が「連続延長」「shift」「break」のいずれかに確定し、50-session 初となる節目 (n=50) の pooled 統計 / σ_pool trend / trend-line slope が更新される。
