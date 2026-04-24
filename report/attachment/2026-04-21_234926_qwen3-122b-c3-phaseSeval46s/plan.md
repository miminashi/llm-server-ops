# Phase S-eval-46session 実施計画

## Context

直前レポート [2026-04-21_224532_qwen3-122b-c3-phaseSeval45s.md](/home/ubuntu/projects/llm-server-ops/report/2026-04-21_224532_qwen3-122b-c3-phaseSeval45s.md) の「未検証事項 / 検証完了後に実施すべき TODO」で **★最重要: Phase S-eval-46session 候補** が筆頭に挙げられている。S45 では 15+ の regime が initial 化した一方で、それらが単発か定着かを判別するには **同条件での S46 連続実施** が唯一の手段。以下の高優先 15+ 項目を同時検証できる:

1. ub=1664 7 連続崩壊 → 8 連続 or 離脱（45-session 0 例の 8 連続候補）
2. ub=1664 下帯 3 連続 → 4 連続 or 離脱（45-session 0 例の 4 連続下帯候補）
3. mode_A 復帰 → 2 連続 or A 外（S29 以来 16 session ぶりの復帰定着性）
4. ub=1584 2 連続回復 15.4 帯 → 定着 or 再崩壊（3 連続 normal initial 継続）
5. Welch (+/not_sig/-) 新 subtype → 連続 or shift（16-subtype 16-session 連続新記録延長可否）
6. ub=1586 not_sig initial → sig 復帰 or 連続（45-session 初の not_sig ub）
7. ub=1584 担当 |t|>20 正方向 → 動向（正方向 |t|>20 initial の再現性）
8. σ_pool 1664 1 位 2 連続 → 3 連続 or 1586 奪還
9. σ_pool 逆転幅 -0.008 縮小転換 → 連続縮小 or 拡大
10. pool 差 +0.06 帯後退 → +0.05 帯 or +0.07 復帰
11. mode_A 外 15 session 最長 break → A 定着 or A 外
12. ub=1586 |Δ_max| 担当 12 session ぶり復帰 → 連続 or 他 ub
13. ub=1586 peak 1 位 50% break → 50% 復帰 or 後退継続
14. |Δ|>0.5 4 連続 break → 5 連続再到達 or 減速継続
15. 境界帯 20+ 分到達 initial → 20+ 分連続 or 回帰

意図する成果: S1-S45 の pooled 225-run に S46 を追加して **pooled 230-run (n=46 session)** 統計へ拡張し、上記 15+ regime の同時検証と時系列プロット (S1..S46) 更新を 1 回のバッチで完了する。

## 実施条件（S45 と完全同一）

| 項目 | 値 |
|------|------|
| model | Qwen3-235B-A22B (Q4_K_M gguf) via qwen3-122b-a10b preset |
| host | t120h-p100 |
| ctx | 32768 |
| flash-attn | 1 |
| KV cache | f16 / f16 |
| OT regex | `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU` (MoE-only) |
| ub | 1584, 1586, 1664 |
| threads | 40 |
| poll | 0 |
| numactl | `--cpunodebind=1 --membind=1` |
| warmup | 2 run |
| eval | 5 run |
| prompt | `prompts/prompt_1k.txt` (6200 bytes, prompt_n=1086、S1-S45 と同一) |
| GPU ロック | 取得必須（skill `gpu-server`） |
| 所要時間目安 | 40-45 分（S45 = 47 分、S44 = 44 分） |

## 添付ディレクトリ命名

- レポート時刻: 実行終了時の JST で採番
- レポートファイル: `/home/ubuntu/projects/llm-server-ops/report/YYYY-MM-DD_HHMMSS_qwen3-122b-c3-phaseSeval46s.md`
- 添付ディレクトリ: `/home/ubuntu/projects/llm-server-ops/report/attachment/YYYY-MM-DD_HHMMSS_qwen3-122b-c3-phaseSeval46s/`

## 実装ステップ

### Step 1: 添付ディレクトリ準備と S45 からの複製

```bash
# S45 添付を S46 用にコピー（実行時点の時刻で)
cp -r report/attachment/2026-04-21_224532_qwen3-122b-c3-phaseSeval45s \
      report/attachment/<新ディレクトリ名>
```

複製対象（全ファイル）:
- `start_phaseSeval45s.sh` → `start_phaseSeval46s.sh`
- `batch_phaseSeval45s.sh` → `batch_phaseSeval46s.sh`
- `run_all.sh`（共通、ファイル名据え置き可）
- `measure_phaseI.sh`（共通、ファイル名据え置き可）
- `analyze_phaseSeval45s.py` → `analyze_phaseSeval46s.py`
- `plot_timeseries.py`（共通、ファイル名据え置き可）
- `prompts/prompt_1k.txt`（S1-S45 と完全同一）
- その他の旧 out_*/summary_*/verdict*/plot*/startup_logs/ はコピー後に **削除** する（新規実行データのみ残す）

### Step 2: スクリプト内参照の書き換え（sed / Edit）

一括置換:
- `45s → 46s`
- `45session → 46session`
- `S1..S45 → S1..S46`
- `n=45 → n=46`
- `225-run → 230-run`
- `prior 44-session → prior 45-session`
- `PRIOR_N = 220 → PRIOR_N = 225`（analyze 内 prior pool run 数）

### Step 3: `analyze_phaseSeval46s.py` の PRIOR_TSVS に S45 追記

```python
PRIOR_TSVS = [
    ... (S1..S44 既存)
    ("S44_phaseSeval44s", SCRIPT_DIR.parent /
        "2026-04-21_214018_qwen3-122b-c3-phaseSeval44s" / "summary_phaseSeval44s.tsv"),
    ("S45_phaseSeval45s", SCRIPT_DIR.parent /
        "2026-04-21_224532_qwen3-122b-c3-phaseSeval45s" / "summary_phaseSeval45s.tsv"),
]
CUR_SESSION_LABEL = "S46_phaseSeval46s"
```

### Step 4: `plot_timeseries.py` に S45 + S46 登録

```python
S_EVAL_DIRS = [
    ... (S1..S44 既存)
    ("S45", "2026-04-21_224532_qwen3-122b-c3-phaseSeval45s", "summary_phaseSeval45s.tsv"),
    ("S46", None, "summary_phaseSeval46s.tsv"),  # 本 Phase、None = カレントディレクトリ
]
```

### Step 5: GPU ロック取得 → バッチ実行 → 解放

```bash
# 1) GPU ロック取得（skill 経由）
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 2) バッチ実行（バックグラウンド、完了 ~45 分）
cd report/attachment/<新ディレクトリ>
bash batch_phaseSeval46s.sh 2>&1 | tee batch_phaseSeval46s.log
# → 各 ub について:
#    - stop (skill) / start (phase script) / wait /health / warmup 2 + eval 5 / stop
# → summary_phaseSeval46s.tsv (3 ub × 7 run = 21 行) 生成

# 3) 分析
python3 analyze_phaseSeval46s.py > phaseSeval46s_verdict.txt
python3 plot_timeseries.py  # → timeseries_eval_tps.png を S1..S46 で更新

# 4) GPU ロック解放
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### Step 6: レポート執筆

`report/YYYY-MM-DD_HHMMSS_qwen3-122b-c3-phaseSeval46s.md` を [REPORT.md](/home/ubuntu/projects/llm-server-ops/REPORT.md) のフォーマットに準拠して作成:

- 添付ファイル一覧
- 参照（直前: S45、S22/S29/S33/S38 等）
- 前提・目的（S45 の ★最優先 15+ 項目同時検証）
- 核心発見サマリ（mode pattern / peak order / Welch / σ_pool / pool 差 / |Δ_max| 担当 / |Δ|>0.5 / 境界帯）
- 定量結果（5-run mean、pooled 230-run、Welch t 3 ub、cool time）
- 時系列プロット PNG
- **「未検証事項」セクション**（S45 の残項目 + S46 で判明した新規項目）
- **「検証完了後に実施すべき TODO」セクション**（CLAUDE.md 更新・性能カード更新・Phase S-eval-47session 候補 等）
- 結論

## 重要な参照ファイル（変更対象）

| 役割 | パス |
|------|------|
| S45 スクリプト参照元 | `report/attachment/2026-04-21_224532_qwen3-122b-c3-phaseSeval45s/` 配下一式 |
| GPU ロック skill | `.claude/skills/gpu-server/scripts/{lock,unlock,lock-status}.sh` |
| llama-server stop | `.claude/skills/llama-server/scripts/stop.sh` |
| REPORT フォーマット | [REPORT.md](/home/ubuntu/projects/llm-server-ops/REPORT.md) |
| 直前レポート | [2026-04-21_224532_qwen3-122b-c3-phaseSeval45s.md](/home/ubuntu/projects/llm-server-ops/report/2026-04-21_224532_qwen3-122b-c3-phaseSeval45s.md) |

## 検証方法（end-to-end 確認）

1. `summary_phaseSeval46s.tsv` が 3 ub × 7 run = 21 行揃うこと
2. `phaseSeval46s_verdict.txt` に 3 ub の Welch t、pooled 230-run mean/σ、verdict（normal/COLLAPSE）が出力されること
3. `timeseries_eval_tps.png` に S1..S46 の折れ線（3 ub）が描画されること
4. 各 `eval_run{1..5}.json` に `"timings"` ブロックが存在し eval_tps が NaN でないこと
5. llama-server が実行後 skill 経由で完全停止（`ssh t120h-p100 "pgrep -f llama-server"` が empty）
6. GPU ロック解放確認（`.claude/skills/gpu-server/scripts/lock-status.sh t120h-p100`）

## 留意事項

- sudo は使わない（skill 内のコマンドも sudo 不要）
- 実行は **プロジェクトルートからの相対パス** で呼び出す
- レポートは plan mode で計画した対として**必ず**作成する（CLAUDE.md 制約）
- S46 終了時刻の JST でディレクトリ名・レポート名を確定
- cool time（S45 終了からの経過）を記録（境界帯 20+ 分連続検証のため）
