# Phase S-eval-59session 実施計画

## Context

直前レポート [2026-04-22_110239_qwen3-122b-c3-phaseSeval58s.md](../../projects/llm-server-ops/report/2026-04-22_110239_qwen3-122b-c3-phaseSeval58s.md) (S58、n=58、pooled 290-run) は「次 Phase 候補（優先順位）」の 1 位に `Phase S-eval-59session 候補` を ★最優先 として掲げている。S59 実施で **単一 phase のみで S58 の ★最優先 未検証事項のうち大多数を同時に消化できる**（条件を全く変えないため追加設計が不要）。

本 phase で消化予定の S58 ★最優先 未検証事項（抜粋、レポート 337-375 行目）:

- **ub=1586 連続崩壊 4 連続 → 5 連続 or normal 復帰**（単一 ub 最長崩壊 streak の継続性判定）
- **ub=1664 normal 復帰 1 fix → normal 2 連続 or 崩壊復帰**（"11+1+3+1+1+1+崩壊+normal" pattern 後の次手）
- **ub=1584 normal 復帰 1 fix → normal 2 連続 or 崩壊復帰**
- **triple collapse 1 例目維持 → 2 例目達成 or single/double**（triple は単発 fix か周期か）
- **Welch (+/-/+) 4 例目 → 連続 or shift**（同一 subtype 連続 pattern 判定）
- **3 ub sig 7 連続 break 1 fix → 全 sig 復帰 or partial 継続**
- **Welch |t|>20 ub=1586 + ub=1664 同時達成 → 連続 or 縮小**（符号反対 |t|>20 pattern の再現性）
- **intra-day 12 session 連続 → 13 session 目 達成 or inter-day 切替 (2026-04-23)**（2026-04-22 cluster 拡大の上限検出）
- **σ_pool 1664 1 位 11 連続 → 12 連続 or 1586 奪還**
- **σ_pool 1584 縮小 4 連続 → 5 連続 or 拡大復帰**（σ 縮小 streak 4 session 上限 confirm の別 ub 再現）
- **pool 差 +0.02 帯復帰 → +0.02 帯 2 連続 or +0.03 帯復帰**
- **ub=1664 |Δ_max| 担当 2 連続 → 3 連続 or 他 ub**
- **|Δ|>0.5 2 連続 → 3 連続 or 縮小**
- **全 ub reject 2 連続 → 3 連続 or partial/confirmed 復帰**
- **cool time 18+ 分 2 連続 → 3 連続 or 他 sub-zone**（18'16" → 18'17" 差 1 秒の極高再現性の継続性）
- **warmup1 hybrid mode 4 連続 → 5 連続 or single mode 復帰**
- **warmup1 hybrid mode_B_band + mode_A_delta 2 連続 → 3 連続 or shift**
- **ub=1664 pool min 14.212 維持 8 連続 / pool max 15.534 維持 20 連続**（record 拡張）

意図する outcome: n=59 pooled 295-run まで標本を拡張し、上記 pattern 連続・break の判定を 1 phase で同時完結させる。

## ゴール (Verification Goals)

1. **ub=1586 連続崩壊**: 4 連続 (S55-S58) → 5 連続 or normal 復帰
2. **ub=1664 / ub=1584 崩壊**: 1 fix normal → normal 2 連続 or 崩壊復帰
3. **triple collapse 連続性**: 単発 fix 事例確定 or 2 例目発生
4. **Welch subtype**: (+/-/+) 連続性、3 ub sig streak 再開判定、|t|>20 2 ub 同時達成の連続性
5. **intra-day cluster**: 2026-04-22 で 13 連続到達 or 2026-04-23 inter-day 2 例目へ切替
6. **σ_pool 順序**: 1664 1 位 12 連続、σ 縮小 streak 4 上限再現検証
7. **cool time**: 18+ 分 sub-zone 連続 or 他帯
8. **verdict_1run**: 全 ub reject 3 連続 or partial 復帰

## 実施フェーズ

### 1. 事前確認

```bash
bash .claude/skills/gpu-server/scripts/lock-status.sh t120h-p100   # 空きの確認
TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S                                  # S59_TS 取得（バッチ終了後にもう一度取得してレポート名へ使う）
```

### 2. GPU ロック取得

```bash
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 3. 添付ディレクトリ作成（S58 → S59 複製・置換）

- ベース: `report/attachment/2026-04-22_110239_qwen3-122b-c3-phaseSeval58s/`
- 新規: `report/attachment/<S59_TS>_qwen3-122b-c3-phaseSeval59s/`

置換ルール:

- `phaseSeval58s` → `phaseSeval59s`（全ファイル）
- `Seval58s` → `Seval59s`（TAG_PREFIX）
- `S58` → `S59`（analyze スクリプトの session 数 limit、verdict 比較ターゲット）
- analyze スクリプトの session 上限 (S58 → S59)、pooled 290-run → 295-run ラベル
- plot_timeseries.py の S58 → S59 ラベル
- 前回ログ (`batch_phaseSeval58s.log` 等) はコピー後に削除（新規実行で上書きされる出力と区別）

過去 session (S1..S58) の pool 参照パスは S58 版 analyze が読み込む各 session の `summary_phaseSeval*s.tsv` 参照を踏襲（S58 のロジックをそのまま S59 用 session 番号へ拡張）。

### 4. バッチ実行（約 36-40 分想定）

S58 と同条件:
- llama-server: numactl `--cpunodebind=1 --membind=1`、threads=40、parallel=1、poll=0
- ub={1584, 1586, 1664} × `-b=-ub`、ctx=32768、fa=1、kv=f16/f16
- OT_REGEX = `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
- 各 ub: warmup 2 + eval 5、cooldown 60s
- prompt: `prompts/prompt_1k.txt` (Sbfine3 と同一、6200 bytes、prompt_n=1086 tokens)

```bash
cd report/attachment/<S59_TS>_qwen3-122b-c3-phaseSeval59s
bash batch_phaseSeval59s.sh 2>&1 | tee batch_phaseSeval59s.log
```

### 5. 集計 + 時系列プロット

```bash
python3 analyze_phaseSeval59s.py   # summary_phaseSeval59s.tsv, phaseSeval59s_stats.csv, phaseSeval59s_verdict.txt
python3 plot_timeseries.py         # timeseries_eval_tps.png (S1..S59, trend line 重畳)
```

### 6. レポート作成

`report/<S59_TS>_qwen3-122b-c3-phaseSeval59s.md` を作成、S58 と同型のセクション構成:

- 実施日時 / 作業種別 / GPU ロック
- 添付ファイル一覧
- 参照（S58/S57/S56/S55、S47 intra-day initial、過去 Sbfine 1-run 系）
- 前提・目的
- **核心発見サマリ** — タイトルは簡潔に（feedback memory: 発見 highlight は「核心発見サマリ」セクション内に記載、タイトルには入れない）
- ub=1586 連続崩壊 5/normal、ub=1664・1584 崩壊/normal 判定
- triple collapse 連続性、Welch subtype、3 ub sig 状態、|t|>20 2 ub 同時性
- intra-day 13 (or inter-day 2 例目) 判定、cool time sub-zone
- σ_pool 順序・縮小/拡大 streak、pool 差 +0.0X 帯
- |Δ_max| 担当 ub、Δ pattern subtype
- prompt_tps rotation、warmup1 mode 分類
- trend line slope 更新（PNG 添付）
- 環境情報、再現方法
- **未検証事項** — ★必須セクション（ユーザ指示）: S58 の残課題で S59 で消化されなかったもの + S59 で新たに発生した pattern
- **検証完了後に実施すべき TODO** — ★必須セクション（ユーザ指示）: Phase Sb-tensor-dump、Phase S-eval-60session 候補、CLAUDE.md 訂正、その他長期 TODO

### 7. GPU ロック解放

```bash
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 重要な制約・前提

| 制約 | 対応 |
|------|------|
| GPU ロック | `gpu-server` skill 経由で必ず取得・解放 |
| スクリプト実行 | プロジェクトルートからの相対パス（フルパスは避ける） |
| sudo | 不要 |
| llama.cpp | S58 と同一 HEAD ビルド（`~/llama.cpp/build`）、再 build しない |
| モデル | `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M` 既存配置 |
| HF_TOKEN | 既設定済 |
| 並列 Claude セッション | ロックで排他 |
| レポート作成 | plan mode なので必須 |
| レポートタイトル | 簡潔に（発見 highlight はタイトルに入れず「核心発見サマリ」内へ） |

## 参考 — 修正・参照する critical files

### 既存・読み込み（S59 では複製元）

- `report/attachment/2026-04-22_110239_qwen3-122b-c3-phaseSeval58s/start_phaseSeval58s.sh`
- `report/attachment/2026-04-22_110239_qwen3-122b-c3-phaseSeval58s/batch_phaseSeval58s.sh`
- `report/attachment/2026-04-22_110239_qwen3-122b-c3-phaseSeval58s/run_all.sh`
- `report/attachment/2026-04-22_110239_qwen3-122b-c3-phaseSeval58s/measure_phaseI.sh`
- `report/attachment/2026-04-22_110239_qwen3-122b-c3-phaseSeval58s/analyze_phaseSeval58s.py`
- `report/attachment/2026-04-22_110239_qwen3-122b-c3-phaseSeval58s/plot_timeseries.py`
- `report/attachment/2026-04-22_110239_qwen3-122b-c3-phaseSeval58s/prompts/prompt_1k.txt`

### Skill scripts 利用（修正なし）

- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh` / `lock-status.sh`
- `.claude/skills/llama-server/scripts/start.sh` / `stop.sh`（バッチ内から呼出）

### 新規作成

- `report/attachment/<S59_TS>_qwen3-122b-c3-phaseSeval59s/`（S58 から `cp -r`、sed 置換）
- `report/<S59_TS>_qwen3-122b-c3-phaseSeval59s.md`

## 検証 (End-to-end Verification)

1. **バッチログ**: `batch_phaseSeval59s.log` に 3 ub × (warmup 2 + eval 5) = 21 run の predicted_per_second が記録
2. **TSV/CSV**: `summary_phaseSeval59s.tsv`（run 別）と `phaseSeval59s_stats.csv`（ub 別 mean/stdev/min/max/median）が生成
3. **verdict**: `phaseSeval59s_verdict.txt` に S59 vs prior 58-session pool の Welch t-test（3 ub）結果と崩壊判定（eval_mean<15）
4. **PNG**: `timeseries_eval_tps.png` に S1..S59 の系列と trend line が重畳
5. **レポート**: `report/<S59_TS>_*.md` が REPORT.md フォーマット（添付一覧、参照、前提目的、核心サマリ、再現、環境、**未検証事項**、**検証完了後に実施すべき TODO**）を満たす
6. **ロック**: 開始時取得、終了時解放。`lock-status.sh t120h-p100` で `available` 状態を最終確認

## リスク / 注意

- バッチ中に llama-server crash した場合、`stop.sh` で残プロセス整理し該当 ub のみ再実行
- thermal throttle で eval_tps 異常値が出た場合は cool time 延長して該当 ub を再実行（analyze 側は stdev で吸収）
- **S59 後のロック解放忘れに注意**（plan 最終ステップで明示）
