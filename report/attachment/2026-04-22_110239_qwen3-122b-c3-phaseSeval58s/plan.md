# Phase S-eval-58session 実施計画

## Context

直前レポート [2026-04-22_100502_qwen3-122b-c3-phaseSeval57s.md](../../projects/llm-server-ops/report/2026-04-22_100502_qwen3-122b-c3-phaseSeval57s.md) の S57 で **57-session 史上初の triple collapse (1584+1586+1664 全 ub 同時崩壊)** が発生。同時に多数の最優先未検証事項が発生:

- triple collapse 1 例目 → S58 で 2 連続 or single/double 復帰
- ub=1586 連続崩壊 3 連続達成 → S58 で 4 連続 or normal 復帰
- ub=1664 "11+1+3+1+1+1+崩壊" pattern → S58 で 2 連続崩壊 or normal
- ub=1584 崩壊復帰 (3-session gap) → S58 で 2 連続崩壊 or normal
- Welch (-/-/-) 57-session 2 例目 → S58 で同 subtype 連続性
- 3 ub 全 |t|>10 達成 initial、Welch |t|>15 ub=1664 負方向 initial
- σ_pool 1664 1 位 10 連続 (2 桁) → S58 で 11 連続 or 1586 奪還
- σ_pool 1586 縮小 4 連続、σ_pool 1584 縮小 3 連続、σ_pool 1664 拡大 3 連続
- pool 差 +0.03 帯 2 連続 → S58 で 3 連続 or 帯 shift
- intra-day 11 session 連続 (2026-04-22 cluster) → S58 で 12 連続 or inter-day 切替
- ub=1664 過半数崩壊維持 13 連続、ub=1664 pool min 14.212 維持 7 連続、ub=1664 pool max 15.534 維持 19 連続
- 全 ub reject 復帰 1 fix → S58 で reject 連続 or partial 復帰
- prompt_tps ub=1664 最高 3 連続 → 4 連続 or rotation
- warmup1 hybrid mode 3 連続 → 4 連続 or single mode 復帰
- cool time 18+ 分 sub-zone 復帰 → 連続 or 他 sub-zone

レポートの「検証完了後に実施すべき TODO」セクションでも、`Phase S-eval-58session 候補` が ★最優先 として明示されており、S57 と同条件 (ctx=32768 × fa=1 × OT=MoE-only × ub={1584,1586,1664} × warmup 2 + eval 5) で第 58 session (S58) を追加実行することで上記 ★最優先 群を pooled 290-run へ拡張して同時検証する。

## ゴール (Verification Goals)

n=58 pooled 290-run の確立と、S58 単独で以下を判定:

1. **triple collapse 連続性**: S58 全 ub 崩壊か、single/double 復帰か
2. **ub=1586 連続崩壊**: 3 連続 → 4 連続 or normal 復帰
3. **ub=1664 pattern**: "11+1+3+1+1+1+崩壊" 後の次手 (崩壊 2 連続 or normal)
4. **ub=1584 崩壊間隔**: 3-session gap 復帰 pattern の続行可否
5. **Welch subtype**: (-/-/-) 連続 or shift、3 ub sig 7 連続 → 8 連続 or partial
6. **σ_pool 順序**: 1664 1 位 10 連続 → 11 連続、σ 縮小/拡大 streak の伸長/break
7. **intra-day cluster**: 2026-04-22 で 12 連続到達 or inter-day (2026-04-23) 切替
8. **cool time**: 18+ 分 sub-zone 連続 or 16-18/13-16/<13 復帰

## 実施フェーズ

### 1. GPU ロック取得 (前提)

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 2. レポート用ディレクトリ作成 + 既存スクリプトの sed 流用

S57 添付一式をベースに名前のみ書換:

- ベース: `report/attachment/2026-04-22_100502_qwen3-122b-c3-phaseSeval57s/`
- 新規: `report/attachment/<S58_TS>_qwen3-122b-c3-phaseSeval58s/` (`<S58_TS>` = バッチ実行直後の `date +%Y-%m-%d_%H%M%S`)

`cp -r` 後、対象ファイルで以下の置換:

- `phaseSeval57s` → `phaseSeval58s` (全ファイル)
- `Seval57s` → `Seval58s` (TAG_PREFIX 系)
- `S57` 記述 → `S58` (analyze スクリプトの session 数 limit、verdict 比較ターゲット)
- 過去出力ディレクトリ `out_Seval57s_*` 参照は **元レポートを読みに行く形なので維持** (analyze は S1..S57 を pooled として読み込む)
- analyze スクリプトの session 上限 (S57 → S58) と pooled 285-run → 290-run のラベル更新
- plot_timeseries.py の S57 → S58 ラベル更新

### 3. バッチ実行 (約 36-40 分想定)

S57 と同条件:
- llama-server: numactl `--cpunodebind=1 --membind=1`、threads=40、parallel=1、poll=0
- ub={1584, 1586, 1664} × `-b=-ub`、ctx=32768、fa=1、kv=f16/f16
- OT_REGEX = `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
- 各 ub: warmup 2 run + eval 5 run、cooldown 60s
- prompt: `prompts/prompt_1k.txt` (Sbfine3 同一、6200 bytes、prompt_n=1086 tokens)

```bash
cd report/attachment/<S58_TS>_qwen3-122b-c3-phaseSeval58s
bash batch_phaseSeval58s.sh 2>&1 | tee batch_phaseSeval58s.log
```

### 4. 集計 + 時系列プロット

```bash
python3 analyze_phaseSeval58s.py   # summary_phaseSeval58s.tsv, phaseSeval58s_stats.csv, phaseSeval58s_verdict.txt
python3 plot_timeseries.py         # timeseries_eval_tps.png (S1..S58, trend line 重畳)
```

### 5. レポート作成 (REPORT.md 準拠)

`report/<S58_TS>_qwen3-122b-c3-phaseSeval58s.md` を作成。S57 と同型のセクション構成:

- 実施日時 / 作業種別 / GPU ロック
- 添付ファイル一覧
- 参照 (S57, S56, S55, S47 (intra-day initial), 過去 1-run Sbfine 系)
- 前提・目的
- **核心発見サマリ** — タイトルは簡潔に。発見 highlight は本セクション内に記載
- triple collapse 連続/break 判定、ub=1586/1664/1584 各 pattern 結果
- intra-day 12 (or inter-day) 判定、cool time sub-zone
- Welch t-test (S58 vs prior 57-session pool)、3 ub sig 状態
- σ_pool 1664 1 位連続性、σ 縮小/拡大 streak
- pool 差 +0.0X 帯
- |Δ_max| 担当 ub、Δ pattern subtype
- prompt_tps rotation
- warmup1 mode 分類
- trend line slope 更新 (PNG 添付)
- 環境情報、再現方法
- **未検証事項** (S58 で発生・継続する未検証群)
- **検証完了後に実施すべき TODO** (Phase S-eval-59session 等)

### 6. GPU ロック解放

```bash
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 重要な制約・前提

| 制約 | 対応 |
|------|------|
| GPU ロック | `gpu-server` skill 経由で必ず取得・解放 |
| スクリプト実行 | プロジェクトルートからの相対パス |
| sudo | 不要 (本 Phase は sudo 操作なし) |
| llama.cpp | S57 と同一 HEAD ビルド (`~/llama.cpp/build`)、再 build しない |
| モデル | `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M` 既存配置 |
| HF_TOKEN | 既設定済 (S57 まで使用) |
| 並列 Claude セッション | ロックで排他 |
| レポート作成 | plan mode の対なので必須 (本計画) |

## 参考 — 修正・参照する critical files

### 既存・読み込み (S58 では複製元)

- `report/attachment/2026-04-22_100502_qwen3-122b-c3-phaseSeval57s/start_phaseSeval57s.sh`
- `report/attachment/2026-04-22_100502_qwen3-122b-c3-phaseSeval57s/batch_phaseSeval57s.sh`
- `report/attachment/2026-04-22_100502_qwen3-122b-c3-phaseSeval57s/run_all.sh`
- `report/attachment/2026-04-22_100502_qwen3-122b-c3-phaseSeval57s/measure_phaseI.sh`
- `report/attachment/2026-04-22_100502_qwen3-122b-c3-phaseSeval57s/analyze_phaseSeval57s.py`
- `report/attachment/2026-04-22_100502_qwen3-122b-c3-phaseSeval57s/plot_timeseries.py`
- `report/attachment/2026-04-22_100502_qwen3-122b-c3-phaseSeval57s/prompts/prompt_1k.txt`

### Skill scripts 利用 (修正なし)

- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- `.claude/skills/llama-server/scripts/stop.sh` (バッチ内から呼出)

### 新規作成

- `report/attachment/<S58_TS>_qwen3-122b-c3-phaseSeval58s/` (S57 から `cp -r`、内部 sed)
- `report/<S58_TS>_qwen3-122b-c3-phaseSeval58s.md`

## 検証 (End-to-end Verification)

1. **バッチログ**: `batch_phaseSeval58s.log` に 3 ub × (warmup 2 + eval 5) = 21 run の predicted_per_second が記録されていること
2. **TSV/CSV**: `summary_phaseSeval58s.tsv` (run 別) と `phaseSeval58s_stats.csv` (ub 別 mean/stdev/min/max/median) が生成されていること
3. **verdict**: `phaseSeval58s_verdict.txt` に S58 vs prior 57-session pool の Welch t-test (3 ub) 結果と崩壊判定 (eval_mean<15) が記録
4. **PNG**: `timeseries_eval_tps.png` に S1..S58 の系列と trend line が重畳描画
5. **レポート**: `report/<S58_TS>_*.md` が REPORT.md フォーマット (添付一覧、参照、前提目的、核心サマリ、再現、未検証、検証完了後 TODO) を満たす
6. **ロック**: 開始時 lock 取得、終了時 unlock。ロックファイル `~/locks/t120h-p100/lock` の状態確認

## リスク / 注意

- バッチ中に llama-server crash した場合、`stop.sh` で残プロセス整理し、該当 ub のみ再実行
- thermal throttle で eval_tps 異常値が出た場合は cool time 延長して該当 ub 再実行 (S57 までも複数回経験ありうる、analyze 側は標準偏差で吸収)
- S58 後のロック解放忘れに注意 (Discord 通知で常時監視)
