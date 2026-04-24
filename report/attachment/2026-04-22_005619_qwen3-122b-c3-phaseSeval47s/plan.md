# Phase S-eval-47session 実施計画

## Context

直前レポート [2026-04-21_234926_qwen3-122b-c3-phaseSeval46s.md](/home/ubuntu/projects/llm-server-ops/report/2026-04-21_234926_qwen3-122b-c3-phaseSeval46s.md) の「未検証事項 / 検証完了後に実施すべき TODO」の筆頭に **★最優先: Phase S-eval-47session 候補** が挙げられている。S46 で 16+ の regime が initial 化しており、単発か定着かを判別するには **同条件での S47 連続実施** が唯一の手段。本 Phase 1 回で以下の ★最優先 TODO 群を同時検証できる:

1. **ub=1664 8 連続崩壊** → S47 9 連続 or 離脱（46-session 0 例の 9 連続候補、mixed-band 中 3 + 下 5 → 中/下/上 のどれに遷移するか）
2. **ub=1664 下帯 4 連続** → S47 5 連続 or 離脱（46-session 0 例、bounded [14.497, 14.714] range）
3. **mode_B 1 位復帰** → S47 mode_B 2 連続 or 他 mode（B-A-B alternation pattern の継続可否）
4. **A-B 1 session interval alternation 3 session** → S47 pattern 継続 or break（ABAB periodic or BAB stabilize）
5. **mode_A 復帰 1 session 限定** → S47 再復帰 or 外定着
6. **ub=1584 15.4 帯定着 break** → S47 15.4 帯再到達 or 15.1 帯定着
7. **Welch (+/+/-) 復帰 1 session fix** → S47 3 連続 or shift（46-session 0 例）
8. **ub=1586 sig 復帰 1 session fix** → S47 連続 or not_sig 再発
9. **σ_pool 1664 1 位 3 連続** → S47 4 連続 or 1586 奪還（46-session 0 例）
10. **σ_pool 1664-1586 逆転幅 +0.010** → S47 拡大 or 縮小
11. **σ_pool ub=1584/1586 縮小 2 連続** → S47 3 連続 or 拡大（46-session 0 例）
12. **pool 差 +0.067 維持 (+0.06 帯 2 連続)** → S47 +0.06 帯 3 連続 or shift
13. **ub=1664 単独崩壊 3 連続** → S47 4 連続 or 離脱
14. **ub=1664 |Δ_max| 担当なし 4 連続** → S47 5 連続 or 担当復帰
15. **3 ub Δ pattern (-/+/-) 新 subtype** → S47 連続 or shift（8-pattern 全出現達成後の rotation）
16. **3 ub sig 復帰 1 session fix** → S47 2 連続 or break
17. **境界帯 18+ 分連続 5** → S47 6 連続 or 離脱（bounded [18'49", 20'01"]）
18. **hybrid 6 連続** → S47 pure 復帰 or 7 連続（pure は S40 以来 7 session 否定）
19. **ub=1586 peak 1 位 50.0% 復帰** → S47 50% 維持 or 後退
20. **prompt_tps ub=1586 最高復帰** → S47 rotation 継続（13-14 session rotation pattern）

**さらに本 Phase 固有の重要観点**: S22-S46 は **2026-04-21 intra-day 25 session 連続**。S47 実施時刻は **2026-04-22** に入るため、**inter-day drift 初計測**（★最優先「Phase S-eval-nextday 候補」筆頭）が同時達成される。intra-day 25 session 連続 break も確定。

意図する成果: S1-S46 の pooled 230-run に S47 を追加して **pooled 235-run (n=47 session)** 統計へ拡張し、上記 20+ regime の同時検証 + inter-day 初検証 + 時系列プロット (S1..S47) 更新を 1 回のバッチで完了する。

## 実施条件（S46 と完全同一）

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
| prompt | `prompts/prompt_1k.txt` (6200 bytes, prompt_n=1086、S1-S46 と同一) |
| GPU ロック | 取得必須（skill `gpu-server`） |
| 所要時間目安 | 40-48 分（S45=47 分、S46=45 分） |

## 添付ディレクトリ命名

- レポート時刻: 実行終了時の JST で採番 (`TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`)
- レポートファイル: `report/YYYY-MM-DD_HHMMSS_qwen3-122b-c3-phaseSeval47s.md`
- 添付ディレクトリ: `report/attachment/YYYY-MM-DD_HHMMSS_qwen3-122b-c3-phaseSeval47s/`

## 実装ステップ

### Step 1: 添付ディレクトリ準備と S46 からの複製

```bash
# 実行開始時刻を JST で採番
STAMP=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
NEWDIR="report/attachment/${STAMP}_qwen3-122b-c3-phaseSeval47s"

cp -r report/attachment/2026-04-21_234926_qwen3-122b-c3-phaseSeval46s "$NEWDIR"

# 旧実行成果物を削除（新規実行データのみ残す）
cd "$NEWDIR"
rm -rf out_Seval46s_* startup_logs summary_phaseSeval46s.tsv \
       phaseSeval46s_stats.csv phaseSeval46s_verdict.txt \
       batch_phaseSeval46s.log run_*.log run_all_*.log \
       start_stdout_*.log timeseries_eval_tps.png plan.md
```

### Step 2: スクリプト内参照の書き換え（一括置換）

対象ファイル: `start_phaseSeval46s.sh` / `batch_phaseSeval46s.sh` / `analyze_phaseSeval46s.py` / `plot_timeseries.py` / `run_all.sh`

一括置換キー:
- `46s` → `47s`
- `46session` → `47session`
- `phaseSeval46` → `phaseSeval47`
- `S1..S46` → `S1..S47`
- `n=46` → `n=47`
- `230-run` → `235-run`
- `prior 45-session` → `prior 46-session`
- analyze 内 `PRIOR_N = 225` → `PRIOR_N = 230`
- ファイル名リネーム: `start_phaseSeval46s.sh → start_phaseSeval47s.sh`, `batch_phaseSeval46s.sh → batch_phaseSeval47s.sh`, `analyze_phaseSeval46s.py → analyze_phaseSeval47s.py`

### Step 3: `analyze_phaseSeval47s.py` の PRIOR_TSVS に S46 追記

```python
PRIOR_TSVS = [
    ... (S1..S45 既存)
    ("S45_phaseSeval45s", SCRIPT_DIR.parent /
        "2026-04-21_224532_qwen3-122b-c3-phaseSeval45s" / "summary_phaseSeval45s.tsv"),
    ("S46_phaseSeval46s", SCRIPT_DIR.parent /
        "2026-04-21_234926_qwen3-122b-c3-phaseSeval46s" / "summary_phaseSeval46s.tsv"),
]
CUR_SESSION_LABEL = "S47_phaseSeval47s"
```

### Step 4: `plot_timeseries.py` に S46 + S47 登録

```python
S_EVAL_DIRS = [
    ... (S1..S45 既存)
    ("S46", "2026-04-21_234926_qwen3-122b-c3-phaseSeval46s", "summary_phaseSeval46s.tsv"),
    ("S47", None, "summary_phaseSeval47s.tsv"),  # 本 Phase、None = カレントディレクトリ
]
```

### Step 5: GPU ロック取得 → バッチ実行 → 解放

```bash
# 1) GPU ロック取得（skill 経由）
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 2) バッチ実行（カレントを新添付ディレクトリに移して実行）
cd "$NEWDIR"
bash batch_phaseSeval47s.sh 2>&1 | tee batch_phaseSeval47s.log
# → 各 ub ∈ {1584, 1586, 1664} について:
#    - skill 経由 stop → start (phase script) → wait /health → warmup 2 + eval 5 → stop
# → summary_phaseSeval47s.tsv (3 ub × 7 run = 21 行) 生成

# 3) 分析 & プロット
python3 analyze_phaseSeval47s.py > phaseSeval47s_verdict.txt
python3 plot_timeseries.py  # → timeseries_eval_tps.png を S1..S47 で更新

# 4) GPU ロック解放
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### Step 6: レポート執筆

`report/YYYY-MM-DD_HHMMSS_qwen3-122b-c3-phaseSeval47s.md` を [REPORT.md](/home/ubuntu/projects/llm-server-ops/REPORT.md) フォーマットに準拠して作成:

必須セクション:
- **添付ファイル** 一覧（plan.md 必須）
- **参照**（直前 S46、S44/S45、S29 mode_A、S22 pool min、S1、Sbfine 系 1-run 参照）
- **前提・目的**（S46 の ★最優先 20+ 項目同時検証 + inter-day 初検証）
- **核心発見サマリ**（mode pattern / peak order / Welch / σ_pool / pool 差 / |Δ_max| / |Δ|>0.5 / 境界帯 / **inter-day drift 観測**）
- **定量結果**（5-run mean、pooled 235-run、Welch t 3 ub、cool time、**日またぎ経過時間**）
- **時系列プロット PNG**（S1..S47 + Sbfine ref）
- **未検証事項** セクション（S46 の残項目 + S47 で判明した新規項目）
- **検証完了後に実施すべき TODO** セクション（Phase S-eval-48session 候補 + CLAUDE.md 更新 + skill 更新 等）
- **結論**

### Step 7: plan.md 添付

```bash
cp /home/ubuntu/.claude/plans/todo-calm-pancake.md "$NEWDIR/plan.md"
```

## 重要な参照ファイル

| 役割 | パス |
|------|------|
| S46 スクリプト参照元（複製元） | `report/attachment/2026-04-21_234926_qwen3-122b-c3-phaseSeval46s/` 配下一式 |
| GPU ロック skill | `.claude/skills/gpu-server/scripts/{lock,unlock,lock-status}.sh` |
| llama-server stop/start skill | `.claude/skills/llama-server/scripts/{stop,start}.sh` |
| REPORT フォーマット | [REPORT.md](/home/ubuntu/projects/llm-server-ops/REPORT.md) |
| 直前レポート（S46） | [2026-04-21_234926_qwen3-122b-c3-phaseSeval46s.md](/home/ubuntu/projects/llm-server-ops/report/2026-04-21_234926_qwen3-122b-c3-phaseSeval46s.md) |

## 検証方法（end-to-end 確認）

1. `summary_phaseSeval47s.tsv` が 3 ub × 7 run = **21 行揃う** こと
2. `phaseSeval47s_verdict.txt` に 3 ub の Welch t / pooled 235-run mean/σ / verdict（normal/COLLAPSE）が出力されること
3. `timeseries_eval_tps.png` に **S1..S47 の折れ線（3 ub）** が描画されること
4. 各 `eval_run{1..5}.json` に `"timings"` ブロックが存在し `eval_tps` が NaN でないこと
5. llama-server が実行後 skill 経由で完全停止（`ssh t120h-p100 "pgrep -f llama-server"` が empty）
6. GPU ロック解放確認（`.claude/skills/gpu-server/scripts/lock-status.sh t120h-p100`）
7. **cool time（S46 終了 2026-04-21 23:46:33 JST からの経過）記録** — 境界帯連続 5 + inter-day 検証
8. **日またぎ確認**: S47 開始が 2026-04-22 00:00 以降であること（intra-day 25 連続 break）

## 留意事項

- **sudo は使わない**（skill 内コマンドも sudo 不要）
- 実行は **プロジェクトルートからの相対パス** で呼び出す（CLAUDE.md 制約）
- レポートは plan mode 対として **必ず作成** する（CLAUDE.md 制約、ユーザから明示的に不要と指示された場合を除く）
- S47 終了時刻の JST でディレクトリ名・レポート名を確定
- cool time（S46 終了からの経過）を分単位で記録（境界帯 18+ 分連続 6 検証 + inter-day drift 分離）
- 48 分 × 3 ub ≈ 45 分の GPU ロック保持を想定。その間は他セッションに影響しないよう lock-status の monitoring 不要（skill が排他管理）
