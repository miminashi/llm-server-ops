# Phase S-eval-51session 実装プラン

## Context

直前レポート [2026-04-22_025948_qwen3-122b-c3-phaseSeval50s.md](../../projects/llm-server-ops/report/2026-04-22_025948_qwen3-122b-c3-phaseSeval50s.md) の「新規項目（本 Phase S-eval-50session で判明・発生）」セクション + 「検証完了後に実施すべき TODO」に ★最優先 マークが多数あり、**Phase S-eval-51session 候補** が明示的に ★最優先として挙げられている。S50 1 セッション追加で同時判定できる未検証 regime が 20+ 存在するため、**Phase S-eval-51session** を S50 と同条件で実施する。

### S50 レポートから継承される「★最優先」未検証 regime（S51 セッション追加で同時判定可能）

1. **mode_E shift (S50 initial)** → S51 mode_E 2 連続 or 他 mode
2. **ub=1664 normal 復帰 (S50 initial、11 連続崩壊 break)** → S51 continuation or 再崩壊
3. **ub=1584 崩壊 5 session ぶり復帰 (S50 initial)** → S51 崩壊 2 連続 or normal 復帰
4. **intra-day 4 session 連続 (S50 initial)** → S51 intra-day 5 session or inter-day 2 例目
5. **Welch (-/not_sig/+) 50-session 0 例 initial subtype** → S51 連続 or 新 subtype
6. **Welch ub=1664 正方向 t=+9.77 50-session 0 例 initial** → S51 連続 or 負方向復帰
7. **Welch |t|>30 4 連続 initial** → S51 5 連続 or 大幅減
8. **σ_pool 1664 1 位 3 連続 initial** → S51 4 連続 or 1586 奪還
9. **σ_pool 1586 縮小 3 連続 initial** → S51 4 連続 or 拡大
10. **pool 差 +0.051 +0.05 帯復帰 1 session fix** → S51 +0.05 帯 2 連続 or +0.04 帯復帰
11. **ub=1664 |Δ_max| 担当復帰 1 session fix** → S51 2 連続 or 他 ub
12. **|Δ_max|=0.852 50-session 2 位級** → S51 更新 or 縮小
13. **ub=1584 崩壊 15/50=30.0%** → S51 16/51 or 15/51
14. **ub=1664 崩壊 28/50=56.0%** → S51 29/51 or 28/51
15. **3 ub Δ pattern (-/+/+) 5 例目** → S51 shift or 連続
16. **ub=1584 eval stdev=0.002 50-session 最小 tied record** → S51 更新 or 拡大
17. **reject 4 連続 (3 ub 全)** → S51 5 連続 or confirm 復帰
18. **prompt_tps ub=1584 最高 3 連続 initial** → S51 4 連続 or rotation
19. **warmup1 out_of_prior_bands 新帯 14.67** → S51 low band continuation or mode 帯復帰
20. **mode_B_delta 復帰 1 session fix** → S51 mode_B_delta 2 連続 or 他 delta
21. **境界帯 20+ 分再到達 1 session fix** → S51 20+ 分 2 連続 or 通常帯
22. **hybrid 10 連続 initial** → S51 pure 復帰 or 11 連続
23. **ub=1664 pool max 15.534 維持 12 連続** → S51 13 連続 or 更新
24. **ub=1586 pool max 15.532 維持 8 連続** → S51 9 連続 or 更新
25. **ub=1664 pool min 14.214 維持 3 連続** → S51 4 連続 or 更新 or 回復
26. **A+B 72.0% 新高値** → S51 75% or 下降

### 期待成果

- S51 1 session 追加で上記 25+ 項目の「★最優先」TODO を同時判定
- 50→51 session 拡張で pooled 255-run 統計、σ_pool trend、inter/intra-day cluster 判定を更新
- 時系列プロット PNG（3 ub trend line 重畳）を S1..S51 へ更新
- **2026-04-22 intra-day 5 session 連続** 可否判定（達成すれば 50-session 新記録）

## 実行条件（S50 踏襲）

- 対象サーバ: **t120h-p100** (10.1.4.14)
- モデル: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- 固定: `ctx=32768` × `fa=1` × `OT=MoE-only (blk.[0-13,21-24,31-47].ffn_*_exps=CPU)` × `numactl --cpunodebind=1 --membind=1` × `threads=40` × `poll=0`
- 走査: `ub ∈ {1584, 1586, 1664}` × 各 (warmup 2 run + 1k eval 5 run) = 21 run
- 所要予測: 36-42 分（S50 = 36 分 58 秒）

## 実装ステップ

### 1. GPU ロック取得

skill `gpu-server` の lock.sh で t120h-p100 を acquire（reason: `phase-Seval-51session`）。

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 2. 添付ディレクトリ作成 + スクリプト複製

```bash
STAMP=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_NAME="${STAMP}_qwen3-122b-c3-phaseSeval51s"
ATTACH="report/attachment/${REPORT_NAME}"
SRC50="report/attachment/2026-04-22_025948_qwen3-122b-c3-phaseSeval50s"

mkdir -p "${ATTACH}/startup_logs"
cp -r "${SRC50}/prompts" "${ATTACH}/"       # 1k prompt（固定、不変）
cp "${SRC50}/measure_phaseI.sh" "${ATTACH}/"
cp "${SRC50}/run_all.sh" "${ATTACH}/"
cp /home/ubuntu/.claude/plans/todo-sorted-wolf.md "${ATTACH}/plan.md"
```

次の 4 ファイルは `50` → `51` 置換（+ PRIOR_TSVS に S50 エントリ追加）で新規作成：

- `start_phaseSeval51s.sh` — `phaseSeval50s` → `phaseSeval51s` 置換のみ
- `batch_phaseSeval51s.sh` — 同上 + 履歴コメント末尾に `50s` 追記
- `analyze_phaseSeval51s.py` — PRIOR_TSVS に S50 エントリ追加、CURRENT_TAG を `S51_phaseSeval51s` に更新、comparison table を S50 基準で増補
- `plot_timeseries.py` — S50 エントリ追加、title/軸範囲を S51 用に更新（trend line 重畳継続）

### 3. バッチ実行

```bash
cd "${ATTACH}"
bash batch_phaseSeval51s.sh 2>&1 | tee batch_phaseSeval51s.log
```

実行内容: 3 ub × (warmup 2 run + 1k eval 5 run) = 21 run。各 ub 切替で llama-server を停止→起動→health 待ち→計測→停止。

### 4. 集計 + verdict + 時系列プロット

```bash
python3 analyze_phaseSeval51s.py    # summary_phaseSeval51s.tsv, phaseSeval51s_stats.csv, phaseSeval51s_verdict.txt
python3 plot_timeseries.py          # timeseries_eval_tps.png (S1..S51, trend line 重畳)
```

### 5. レポート作成

`report/${REPORT_NAME}.md` を REPORT.md 規約で作成し、以下を含める：

- **実施日時**（JST、分単位、cool time 算出）
- **添付ファイル一覧**（plan.md を含む）
- **参照**（直前 S50 + 関連 session）
- **前提・目的**（S50 ★最優先 regime 群の明示）
- **核心発見サマリ**（S51 での mean / Δ / mode / Welch / σ_pool / pool 差 / 境界帯 / hybrid / peak / 崩壊頻度 / intra-day cluster 状況）
- **環境情報 / 再現方法**
- **未検証事項**（既知項目継続 + S51 で発生する新規「★最優先」群、**ユーザ指示通り「未検証事項」セクションに記載**）
- **検証完了後に実施すべき TODO**（**ユーザ指示通りセクション記載**）

### 6. GPU ロック解放

```bash
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 重要ファイル

### 複製・流用（そのままコピー）

- `report/attachment/2026-04-22_025948_qwen3-122b-c3-phaseSeval50s/measure_phaseI.sh`
- `report/attachment/2026-04-22_025948_qwen3-122b-c3-phaseSeval50s/run_all.sh`
- `report/attachment/2026-04-22_025948_qwen3-122b-c3-phaseSeval50s/prompts/prompt_1k.txt`

### 修正コピー（`50` → `51` 置換）

- `start_phaseSeval51s.sh` — remote_log prefix / echo prefix を `phaseSeval51s` に統一
- `batch_phaseSeval51s.sh` — 履歴コメント末尾に `50s` 追記、start 呼び出しを 51 版に置換
- `analyze_phaseSeval51s.py` — PRIOR_TSVS に S50 エントリ追加、CURRENT_TAG 更新、tables 増補
- `plot_timeseries.py` — S50 point 追加、title/軸更新（trend line 継続）

### 変更ファイル（プロジェクト側）

- 新規: `report/${STAMP}_qwen3-122b-c3-phaseSeval51s.md`
- 新規: `report/attachment/${STAMP}_qwen3-122b-c3-phaseSeval51s/...`
- 触らない: `CLAUDE.md`, `REPORT.md`, skill 本体

## 再利用する既存関数・スキル

- `.claude/skills/gpu-server/scripts/lock.sh` — ロック acquire
- `.claude/skills/gpu-server/scripts/unlock.sh` — ロック release
- `.claude/skills/llama-server/scripts/stop.sh` — llama-server 停止（batch 内で呼び出し）
- `.claude/skills/discord-notify/` — バッチ完了通知（任意）
- S50 の `measure_phaseI.sh` / `run_all.sh` — 無変更で流用
- S50 の `analyze_phaseSeval50s.py` の既存関数（`compute_welch_t`、`mode_classify`、`cohen_d` 等） — 50→51 差分のみ更新

## 検証手順（end-to-end）

1. `.claude/skills/gpu-server/scripts/lock-status.sh t120h-p100` でロック保持確認
2. `curl -sf http://10.1.4.14:8000/health` で /health OK
3. `batch_phaseSeval51s.log` に 3 ub 全てで `measure done` 出力
4. `summary_phaseSeval51s.tsv` に 3 ub × (2 warmup + 5 eval) = 21 行
5. `phaseSeval51s_stats.csv` で n=51 session 集計値が出力
6. `phaseSeval51s_verdict.txt` で verdict 成立（`ctx=32768 × fa=1 × OT-MoE 3 ub` pool mean / σ / 崩壊頻度 / mode 連続 / 下帯連続等の再現判定）
7. `timeseries_eval_tps.png` に S1..S51 × 3 ub × trend line 描画
8. レポート本文に S51 mean 3 値、3 ub Δ 符号、mode 分類、Welch 結果、intra-day cluster 情報、ロック release 記録が含まれる
9. GPU ロックが確実に release されている（`lock-status.sh` で空）

## 中断時リカバリ

- 途中 OOM / ub-reject: `start_phaseSeval51s.sh` が exit 2/3 で abort → batch 続行せず原因確認
- /health 不達: 80*5s=400s 待ちで abort、`startup_logs/` に保存済ログを確認
- バッチ後も必ず `bash .claude/skills/llama-server/scripts/stop.sh t120h-p100` + ロック release を実行

## 判定される regime の帰結パターン（要約）

S51 1 session 追加で、主要 regime（mode_E 連続、ub=1664 normal 復帰 continuation、ub=1584 崩壊 2 連続、intra-day 5 session、Welch subtype 連続、σ_pool 1 位連続、pool 差 +0.05 帯連続、|Δ_max| 更新、hybrid 連続、peak rotation 等）が「連続延長」「shift」「break」のいずれかに確定し、51-session 節目の pooled 統計 / σ_pool trend / trend-line slope が更新される。

**cool time 予測**: S50 終了 (2026-04-22 03:42:45 JST) から plan 承認までの待機時間に依存。現時点 (03:52 JST) で約 10 分経過。S51 開始時点で cool time が通常帯 13-16 分 → 境界帯直前 16-18 分のいずれかに収まる見込み（境界帯 20+ 分 2 連続は cool time 20 分超え必要）。
