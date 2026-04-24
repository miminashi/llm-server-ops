# Phase S-eval-48session 実施計画

## Context

直前レポート [2026-04-22_005619_qwen3-122b-c3-phaseSeval47s.md](/home/ubuntu/projects/llm-server-ops/report/2026-04-22_005619_qwen3-122b-c3-phaseSeval47s.md) の「未検証事項 / 検証完了後に実施すべき TODO」の筆頭に **★最優先: Phase S-eval-48session 候補** が挙げられている。S47 で 20+ の regime が initial 化しており、単発か定着かを判別するには **同条件での S48 連続実施** が唯一の手段。本 Phase 1 回で以下の ★最優先 TODO 群を同時検証できる:

1. **ub=1586 大幅崩壊 14.403 → S48 回復 or 連続崩壊**（47-session 0 例の ub=1586 連続崩壊、14 帯 2 連続は S22-S23 以外に 47-session 内で 0 例）
2. **ub=1664 9 連続崩壊 → S48 10 連続 or 離脱**（47-session 0 例の 10 連続崩壊、mixed-band 中 3 + 下 6）
3. **ub=1664 下帯 5 連続 → S48 6 連続 or 離脱**（47-session 0 例の 6 連続下帯、bounded [14.497, 14.714] range）
4. **mode_F 復帰 4 例目 → S48 mode_F 2 連続 or 他 mode**（mode_F 2 連続は S33→S34 以来 14 session 間未発生）
5. **inter-day drift 1 例目 → S48 inter-day 2 例目 or intra-day 再開**（日またぎ drift の再現性判定）
6. **intra-day 25 session 連続 break → S48 intra-day 再開 2 session or inter-day 2 session**（2026-04-22 の intra-day 発展判定）
7. **double collapse (1586/1664) 6 例目 → S48 7 例目 or 離脱**（47-session 0 例の 2 連続 double collapse）
8. **Welch (+/-/-) subtype → S48 連続 or shift**（(+/-/-) が 16-subtype catalog 内か 17 番目かの棚卸し + 連続性判定）
9. **Welch |t|>36 ub=1586 負方向新記録 → S48 |t|>30 or 大幅減**（S46 +4.91 → S47 -36.05 の符号反転 + 大幅拡大の re-establish 可否）
10. **σ_pool 1586 1 位復帰 1 session fix → S48 連続 or 1664 奪還**（47-session 0 例の σ_pool 1586 1 位 2 連続）
11. **σ_pool 1586 +0.016 跳躍拡大 initial → S48 σ_pool 再縮小 or 連続拡大**（47-session 0 例の同 ub σ +0.016 以上の 2 連続）
12. **σ_pool 1584 縮小 3 連続 initial → S48 4 連続 or 拡大**
13. **pool 差 +0.047 (+0.04 帯復帰) → S48 +0.04 帯 2 連続 or +0.05/+0.06 復帰**
14. **|Δ|>0.8 ub=1586 initial → S48 連続大変動 or 定着回復**（47-session 0 例の |Δ|>0.8 2 連続）
15. **ub=1586 |Δ_max| 担当復帰 → S48 連続 or 他 ub**（S45 1586 → S46 1584 → S47 1586 復帰）
16. **3 ub Δ (+/-/+) 復帰 2 例目 → S48 連続 or shift**（S45 (+/-/+) → S46 (-/+/-) → S47 (+/-/+) rotation）
17. **mode 階層 D=F 同率 5 位 initial → S48 F 単独 5 位 or D 単独復帰**
18. **mode_A 外 2 session 連続 initial → S48 mode_A 復帰 or 3 連続外**
19. **境界帯 18+ 分連続 6 → S48 7 連続 or 離脱**（47-session 0 例の 7 連続）
20. **境界帯 20+ 分再到達 initial → S48 20+ 分連続 or 18-20 帯回帰**
21. **hybrid 7 連続 → S48 pure 復帰 or 8 連続**（pure 8 連続否定、subtype shift 可能性）

**さらに本 Phase 固有の重要観点**: S47 が **2026-04-22 inter-day initial** 1 例目。S48 実施時刻が 2026-04-22 intra-day ならば **intra-day 2 session 連続開始 2 例目**、2026-04-23 に跨ぐなら **inter-day 2 session 連続 initial**。両ケースとも multi-day regime drift の初測定となる。

意図する成果: S1-S47 の pooled 235-run に S48 を追加して **pooled 240-run (n=48 session)** 統計へ拡張し、上記 20+ regime の同時検証 + inter-day/intra-day 判定 + 時系列プロット (S1..S48) 更新を 1 回のバッチで完了する。

## 実施条件（S47 と完全同一）

| 項目 | 値 |
|------|------|
| model | Qwen3-235B-A22B (Q4_K_M gguf) via qwen3-122b-a10b preset |
| host | t120h-p100 |
| ctx | 32768 |
| flash-attn | 1 |
| KV cache | f16 / f16 |
| OT regex | `blk\.([0-9]\|1[0-3]\|2[0-4]\|3[1-9]\|4[0-7])\.ffn_.*_exps\.weight=CPU` (MoE-only) |
| ub | 1584, 1586, 1664 |
| threads | 40 |
| poll | 0 |
| numactl | `--cpunodebind=1 --membind=1` |
| warmup | 2 run |
| eval | 5 run |
| prompt | `prompts/prompt_1k.txt` (6200 bytes, prompt_n=1086、S1-S47 と同一) |
| GPU ロック | 取得必須（skill `gpu-server`） |
| 所要時間目安 | 40-50 分（S46=45 分、S47=44'55"） |

## 添付ディレクトリ命名

- レポート時刻: 実行終了時の JST で採番 (`TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`)
- レポートファイル: `report/YYYY-MM-DD_HHMMSS_qwen3-122b-c3-phaseSeval48s.md`
- 添付ディレクトリ: `report/attachment/YYYY-MM-DD_HHMMSS_qwen3-122b-c3-phaseSeval48s/`

## 実装ステップ

### Step 1: 添付ディレクトリ準備と S47 からの複製

```bash
# 実行開始時刻を JST で採番
STAMP=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
NEWDIR="report/attachment/${STAMP}_qwen3-122b-c3-phaseSeval48s"

cp -r report/attachment/2026-04-22_005619_qwen3-122b-c3-phaseSeval47s "$NEWDIR"

# 旧実行成果物を削除（新規実行データのみ残す）
cd "$NEWDIR"
rm -rf out_Seval47s_* startup_logs summary_phaseSeval47s.tsv \
       phaseSeval47s_stats.csv phaseSeval47s_verdict.txt \
       batch_phaseSeval47s.log run_*.log run_all_*.log \
       start_stdout_*.log timeseries_eval_tps.png plan.md
mkdir -p startup_logs
```

### Step 2: スクリプト内参照の書き換え（一括置換）

対象ファイル: `start_phaseSeval47s.sh` / `batch_phaseSeval47s.sh` / `analyze_phaseSeval47s.py` / `plot_timeseries.py` / `run_all.sh`

一括置換キー:
- `47s` → `48s`
- `47session` → `48session`
- `phaseSeval47` → `phaseSeval48`
- `S1..S47` → `S1..S48`
- `n=47` → `n=48`
- `235-run` → `240-run`
- `prior 46-session` → `prior 47-session`
- analyze 内 `PRIOR_N = 230` → `PRIOR_N = 235`
- ファイル名リネーム: `start_phaseSeval47s.sh → start_phaseSeval48s.sh`, `batch_phaseSeval47s.sh → batch_phaseSeval48s.sh`, `analyze_phaseSeval47s.py → analyze_phaseSeval48s.py`

### Step 3: `analyze_phaseSeval48s.py` の PRIOR_TSVS に S47 追記

```python
PRIOR_TSVS = [
    ... (S1..S46 既存)
    ("S46_phaseSeval46s", SCRIPT_DIR.parent /
        "2026-04-21_234926_qwen3-122b-c3-phaseSeval46s" / "summary_phaseSeval46s.tsv"),
    ("S47_phaseSeval47s", SCRIPT_DIR.parent /
        "2026-04-22_005619_qwen3-122b-c3-phaseSeval47s" / "summary_phaseSeval47s.tsv"),
]
CUR_SESSION_LABEL = "S48_phaseSeval48s"
```

### Step 4: `plot_timeseries.py` に S47 + S48 登録

```python
S_EVAL_DIRS = [
    ... (S1..S46 既存)
    ("S47", "2026-04-22_005619_qwen3-122b-c3-phaseSeval47s", "summary_phaseSeval47s.tsv"),
    ("S48", None, "summary_phaseSeval48s.tsv"),  # 本 Phase、None = カレントディレクトリ
]
```

### Step 5: GPU ロック取得 → バッチ実行 → 解放

```bash
# 1) GPU ロック取得（skill 経由）
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 2) バッチ実行（カレントを新添付ディレクトリに移して実行）
cd "$NEWDIR"
bash batch_phaseSeval48s.sh 2>&1 | tee batch_phaseSeval48s.log
# → 各 ub ∈ {1584, 1586, 1664} について:
#    - skill 経由 stop → start (phase script) → wait /health → warmup 2 + eval 5 → stop
# → summary_phaseSeval48s.tsv (3 ub × 7 run = 21 行) 生成

# 3) 分析 & プロット
python3 analyze_phaseSeval48s.py > phaseSeval48s_verdict.txt
python3 plot_timeseries.py  # → timeseries_eval_tps.png を S1..S48 で更新

# 4) GPU ロック解放
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### Step 6: レポート執筆

`report/YYYY-MM-DD_HHMMSS_qwen3-122b-c3-phaseSeval48s.md` を [REPORT.md](/home/ubuntu/projects/llm-server-ops/REPORT.md) フォーマットに準拠して作成。

必須セクション:
- **添付ファイル** 一覧（plan.md 必須）
- **参照**（直前 S47、S45/S46、S33/S34 mode_F 2 連続、S22 pool min、S1、Sbfine 系 1-run 参照）
- **前提・目的**（S47 の ★最優先 20+ 項目同時検証 + inter-day/intra-day 判定）
- **核心発見サマリ**（mode pattern / peak order / Welch / σ_pool / pool 差 / |Δ_max| / |Δ|>0.5 / 境界帯 / **inter-day 2 例目 or intra-day 復帰判定**）
- **定量結果**（5-run mean、pooled 240-run、Welch t 3 ub、cool time、**S47 からの経過時間**）
- **時系列プロット PNG**（S1..S48 + Sbfine ref）
- **未検証事項** セクション（S47 の残項目 + S48 で判明した新規項目）
- **検証完了後に実施すべき TODO** セクション（Phase S-eval-49session 候補 + CLAUDE.md 更新 + skill 更新 等）
- **結論**

### Step 7: plan.md 添付

```bash
cp /home/ubuntu/.claude/plans/todo-majestic-wombat.md "$NEWDIR/plan.md"
```

## 重要な参照ファイル

| 役割 | パス |
|------|------|
| S47 スクリプト参照元（複製元） | `report/attachment/2026-04-22_005619_qwen3-122b-c3-phaseSeval47s/` 配下一式 |
| GPU ロック skill | `.claude/skills/gpu-server/scripts/{lock,unlock,lock-status}.sh` |
| llama-server stop/start skill | `.claude/skills/llama-server/scripts/{stop,start}.sh` |
| REPORT フォーマット | [REPORT.md](/home/ubuntu/projects/llm-server-ops/REPORT.md) |
| 直前レポート（S47） | [2026-04-22_005619_qwen3-122b-c3-phaseSeval47s.md](/home/ubuntu/projects/llm-server-ops/report/2026-04-22_005619_qwen3-122b-c3-phaseSeval47s.md) |

## 検証方法（end-to-end 確認）

1. `summary_phaseSeval48s.tsv` が 3 ub × 7 run = **21 行揃う** こと
2. `phaseSeval48s_verdict.txt` に 3 ub の Welch t / pooled 240-run mean/σ / verdict（normal/COLLAPSE）が出力されること
3. `timeseries_eval_tps.png` に **S1..S48 の折れ線（3 ub）** が描画されること
4. 各 `eval_run{1..5}.json` に `"timings"` ブロックが存在し `eval_tps` が NaN でないこと
5. llama-server が実行後 skill 経由で完全停止（`ssh t120h-p100 "pgrep -f llama-server"` が empty）
6. GPU ロック解放確認（`.claude/skills/gpu-server/scripts/lock-status.sh t120h-p100`）
7. **cool time（S47 終了 2026-04-22 00:52:30 JST からの経過）記録** — 境界帯連続 6 or 離脱 + inter-day/intra-day 判定
8. **日またぎ確認**: S48 開始時刻が 2026-04-22 中であれば intra-day 2 session 開始、2026-04-23 以降であれば inter-day 2 session 連続

## 留意事項

- **sudo は使わない**（skill 内コマンドも sudo 不要）
- 実行は **プロジェクトルートからの相対パス** で呼び出す（CLAUDE.md 制約）
- レポートは plan mode 対として **必ず作成** する（CLAUDE.md 制約、ユーザから明示的に不要と指示された場合を除く）
- S48 終了時刻の JST でディレクトリ名・レポート名を確定
- cool time（S47 終了からの経過）を分単位で記録（境界帯 18+ 分連続 7 検証 + inter-day/intra-day 判定）
- 48 分 × 3 ub ≈ 45 分の GPU ロック保持を想定。その間は他セッションに影響しないよう lock-status の monitoring 不要（skill が排他管理）
- レポートに「**未検証事項**」と「**検証完了後に実施すべき TODO**」セクションを S47 と同構成で記載すること（ユーザ明示指示）
