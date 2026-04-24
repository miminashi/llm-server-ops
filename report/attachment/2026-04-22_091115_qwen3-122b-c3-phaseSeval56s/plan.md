# Plan: Phase S-eval-56session (第 56 セッション)

## Context

直前レポート [2026-04-22_081858_qwen3-122b-c3-phaseSeval55s.md](file:///home/ubuntu/projects/llm-server-ops/report/2026-04-22_081858_qwen3-122b-c3-phaseSeval55s.md) の「未検証事項」新規項目に **★最優先 25 項目**・**★高優先 8 項目**・**★中優先 5 項目**、「検証完了後に実施すべき TODO」先頭に **★最優先: Phase S-eval-56session 候補** が明示されている。

これら ★最優先 の大半は「次 session を **同条件で実施すれば一度に判定できる連続性/break 観察項目**」であり、個別深掘り (boundary-fine / extended / tensor-dump / markov 推定など) に進むよりも、まず S56 を 1 session 進めて連続記録・break 判定を確定させるのが最高 ROI。これは S1→S55 までの全 session で採用してきた方針の継続。

本計画の目的:

- **n=56 session / pooled 280-run へ統計拡張**
- **S55 の ★最優先 TODO 群（25 項目）を同条件 1 バッチで一括検証**
  - Welch (+/-/+) 復帰 1 fix → S56 (+/-/+) 連続 or 新 subtype
  - ub=1664 "11+1+3+1+1" pattern → "11+1+3+2+1" 崩壊 or "11+1+3+1+1+1" normal 3 連続
  - ub=1586 崩壊 1 fix confirm → 崩壊 2 連続 or normal 復帰 (1-normal-gap 2 例目の続行)
  - ub=1584 崩壊復帰 1 fix → 偶数 session 崩壊 4 例目 (予測 S56) or normal 2 連続
  - double collapse (1586/1664) break 2 連続 → 3 連続 or 復帰
  - intra-day 9 session 連続 (2026-04-22 cluster 9) → 10 session 達成 or 日跨ぎ
  - Welch |t|>20 ub=1664 担当 55-session 初 → 再拡大 or 縮小
  - 3 ub sig 3/3 5 連続 → 6 連続 or partial 復帰
  - σ_pool 1664 1 位 8 連続 → 9 連続 or 1586 奪還
  - σ_pool 1586 縮小 2 連続 → 3 連続 or 拡大復帰
  - pool 差 +0.04 帯 2 連続 (+0.040) → 維持 or +0.05 帯復帰
  - ub=1584 |Δ_max| 担当復帰 1 fix → 2 連続 or 他 ub
  - |Δ|>0.5 連続 6 session → 7 連続 or 縮小
  - |Δ|>1.0 4 session 維持 → 5 例目 (ub=1586 集中 pattern) or 安定
  - 3 ub Δ pattern (+/-/+) → 連続 or shift
  - initial subtype 6 連続 (S50-S55) → 7 連続 or 既知 subtype 復帰
  - ub=1664 崩壊 31/55=56.4% → 過半数維持 12 session 判定
  - ub=1586 崩壊 13/55=23.6% → 14/56 or 13/56
  - 全 ub reject 4 連続 → 5 連続 or partial 復帰
  - prompt_tps ub=1664 最高復帰 → 2 連続 or rotation (14 session rotation 2 巡目 10 session 目)
  - warmup1 S7_band 復帰 48 session ぶり → 連続 or 別帯
  - warmup1 out_of_prior_delta_bands initial → 連続 or 既知 delta 帯復帰
  - cool time 16-18 分復帰 1 fix → 2 連続 or 他 sub-zone
  - ub=1664 pool min 14.212 維持 5 連続 → 6 連続 or 更新
  - ub=1664 peak 1 位 2 連続達成 3 例目 → 3 連続 (歴代初) or break
- **時系列プロット (S1..S56) および trend line を更新**

**cool time 観察**: S55 バッチ終了 (2026-04-22 08:16:30 JST) から現時点 (約 08:27 JST) で約 11 分経過済。準備整い次第開始する S1..S55 の stance を踏襲し、恣意的時刻合わせはしない。結果として S56 cool time は <13 分 / 13-16 分 / 16-18 分 / 18+ 分 のいずれかに自然に配置される → それ自体が観察対象。

## 前提条件

- GPU サーバ: **t120h-p100** (10.1.4.14、Tesla P100 × 4、S1..S55 と同一環境)
- モデル: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M` (S1..S55 と同一 snapshot)
- llama.cpp: HEAD（S55 同一ビルド `~/llama.cpp/build` を再利用、rebuild しない）
- 固定パラメータ: `ctx=32768`、`fa=1`、`cache-type-k/v=f16/f16`、`numactl --cpunodebind=1 --membind=1`、`threads=40`、`poll=0`、`parallel=1`、OT_REGEX 不変
- 可変軸: `ub ∈ {1584, 1586, 1664}`、`-b=-ub` (各 ub で一致)
- 試行: warmup 2 run + eval 5 run × 3 ub = **21 run**（S1..S55 と同一設計）
- prompt: `prompts/prompt_1k.txt`（6200 bytes、1086 tokens、S1..S55 と同一ファイル）
- 所要時間目安: 36〜42 分 (S55 実績: 37 分 10 秒)

## 実施手順

### 1. GPU ロック取得

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

Skill `gpu-server` の指示に従う (CLAUDE.md 制約)。取得後は heartbeat 保持確認。

### 2. S55 ディレクトリを S56 として複製 → 文字列置換

複製元: `report/attachment/2026-04-22_081858_qwen3-122b-c3-phaseSeval55s/`

```bash
cd /home/ubuntu/projects/llm-server-ops/report/attachment
NEW_DIR="$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)_qwen3-122b-c3-phaseSeval56s"
cp -r 2026-04-22_081858_qwen3-122b-c3-phaseSeval55s "$NEW_DIR"
cd "$NEW_DIR"
```

新ディレクトリ内での置換:

| 対象 | 置換ルール |
|------|-----------|
| ファイル名 | `*phaseSeval55s*` → `*phaseSeval56s*`、`*Seval55s*` → `*Seval56s*` |
| スクリプト内文字列 | `phaseSeval55s` → `phaseSeval56s`、`Seval55s` → `Seval56s` |
| `analyze_phaseSeval56s.py` 内 `CUR_SESSION_LABEL` | `S55_phaseSeval55s` → `S56_phaseSeval56s` |
| `analyze_phaseSeval56s.py` 内 `PRIOR_TSVS` | S55 の `summary_phaseSeval55s.tsv` パスを末尾に追加 (n=56 pool を構成) |
| `plot_timeseries.py` 内 `S_EVAL_DIRS` | S55 ディレクトリパスを末尾に追加 |
| `out_Seval55s_*/` ディレクトリ (複製された旧 run 成果物) | **全削除** (S56 で再生成) |
| `batch_phaseSeval55s.log` (複製) | 削除 |
| `summary_*`, `*_stats.csv`, `*_verdict.txt`, `timeseries_eval_tps.png`, `startup_logs/*`, `run_*.log` (複製) | 削除 |
| `plan.md` | 本ファイル (S56 plan) で上書き |

### 3. バッチ実行

```bash
cd report/attachment/<new-s56-dir>
bash batch_phaseSeval56s.sh 2>&1 | tee batch_phaseSeval56s.log
```

- GPU ロック lease は batch 中に lapse しないよう適宜更新 (skill `gpu-server` 指示)
- batch 構造: 3 ub × (stop→start→health→warmup2→eval5→stop) 直列ループ

### 4. 集計 + プロット生成

```bash
python3 analyze_phaseSeval56s.py   # summary_phaseSeval56s.tsv / phaseSeval56s_stats.csv / phaseSeval56s_verdict.txt
python3 plot_timeseries.py         # timeseries_eval_tps.png (S1..S56, trend line 重畳)
```

集計結果から以下を抽出:
- 3 ub の eval_tps mean / σ
- session-to-session Δ (S55 → S56) と |Δ_max| 担当 ub
- Welch t-test (prior 55-session pool vs S56) の 3 ub 符号 → subtype 判定
- pool n=280 の mean/σ、σ_pool 順序、pool 差 (1586-1584, 1586-1664, 1664-1584)
- peak order pattern / mode 分類 / peak 1 位 ub
- ub=1584/1586/1664 崩壊判定と頻度更新
- warmup1 ub=1584 の mode_{A..F}_band / _delta 判定
- cool time (S55 終了 08:16:30 → S56 開始) と sub-zone 判定
- verdict_1run (accept/partial/reject) (ref: 1584=15.293, 1586=15.466, 1664=15.451 / Sbfine 系)
- trend line slope (3 ub) の n=56 値

### 5. レポート作成

[REPORT.md](file:///home/ubuntu/projects/llm-server-ops/REPORT.md) ルールに従い生成:

- タイトル: `Qwen3.5-122B-A10B C-3 Phase S-eval-56session`
- 添付ファイル一覧 (plan.md / スクリプト / ログ / TSV / stats.csv / verdict.txt / PNG / prompts / out ディレクトリ / startup_logs)
- 参照: 直前 S55、S54、S53、S52、S50、S47、S38、S22、S15、S1、Sbfine 系
- 前提・目的
- 核心発見サマリ (S55 ★最優先 TODO への回答を項目別に明示)
- intra-day cluster / cool time / mode 分類 / σ_pool / Δ pattern / Welch subtype / prompt_tps / trend line slope 各セクション
- **「未検証事項」セクション** — S56 で確定した連続記録・break/継続を受けて S57 へ引き継ぐ項目を列挙（**必須**、ユーザ指示）
- **「検証完了後に実施すべき TODO」セクション** — 次 Phase 候補を優先順位付き列挙 (S55 末尾構成を踏襲、**必須**、ユーザ指示)

### 6. GPU ロック解放

```bash
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 7. Discord 通知 (任意)

Skill `discord-notify` でレポート URL を通知 (S1..S55 で通知している場合は継続)。

## S56 で一括判定される ★最優先項目（S55 レポート由来、25 項目）

- [ ] Welch (+/-/+) 復帰 1 fix → S56 (+/-/+) 連続 or 新 subtype
- [ ] ub=1664 "11+1+3+1+1" pattern → S56 "11+1+3+2+1" 崩壊 or "11+1+3+1+1+1" normal 3 連続
- [ ] ub=1586 崩壊 1 fix confirm → S56 崩壊 2 連続 or normal 復帰
- [ ] ub=1584 崩壊復帰 1 fix → S56 崩壊 (2-session interval 4 例目) or normal 2 連続
- [ ] double collapse (1586/1664) break 2 連続 → S56 復帰 or 3 連続 break
- [ ] intra-day 9 session 連続 → S56 intra-day 10 session or inter-day 2 例目
- [ ] Welch |t|>20 ub=1664 担当 → S56 再拡大 or 縮小
- [ ] 3 ub sig 3/3 達成 5 連続 → S56 6 連続 or partial 復帰
- [ ] σ_pool 1664 1 位 8 連続 → S56 9 連続 or 1586 奪還
- [ ] σ_pool 1586 縮小 2 連続 → S56 3 連続 or 拡大復帰
- [ ] pool 差 +0.04 帯 2 連続 (+0.040) → S56 +0.04 維持 or +0.05 帯復帰 or +0.03 帯戻り
- [ ] ub=1584 |Δ_max| 担当復帰 1 fix → S56 2 連続 or 他 ub
- [ ] |Δ|>0.5 連続 6 session → S56 7 連続 or 縮小
- [ ] |Δ|>1.0 4 session 維持 → S56 5 例目 or 安定
- [ ] 3 ub Δ pattern (+/-/+) → S56 shift or 連続
- [ ] initial subtype 6 連続 (S50-S55) → S56 7 連続 or 既知 subtype 復帰
- [ ] ub=1664 崩壊 31/55=56.4% → S56 32/56 or 31/56 (過半数維持 12 session 判定)
- [ ] ub=1586 崩壊 13/55=23.6% → S56 14/56 or 13/56
- [ ] 全 ub reject 4 連続達成 → S56 5 連続 or partial 復帰
- [ ] prompt_tps ub=1664 最高復帰 → S56 2 連続 or rotation
- [ ] warmup1 S7_band 復帰 48 session ぶり → S56 連続 or 別帯
- [ ] warmup1 out_of_prior_delta_bands initial → S56 連続 or 既知 delta 帯復帰
- [ ] cool time 16-18 分復帰 1 fix → S56 16-18 分 2 連続 or 他 sub-zone
- [ ] ub=1664 pool min 14.212 維持 5 連続 → S56 6 連続 or 更新 or 回復
- [ ] ub=1664 peak 1 位 2 連続達成 3 例目 → S56 3 連続 (歴代初) or break

## S56 で判定される ★高優先項目（S55 レポート由来、8 項目）

- [ ] ub=1664 pool max 15.534 維持 17 連続 → S56 18 連続 or 更新
- [ ] ub=1586 pool max 15.532 維持 13 連続 → S56 14 連続 or 更新
- [ ] ub=1586 pool min 13.840 維持 33 連続 → S56 34 連続 or 比較
- [ ] ub=1584 pool min 13.958 維持 40 連続 → S56 41 連続 or 比較
- [ ] peak 1 位 1586 25/55=45.5% → S56 26/56 or 25/56 (最安定維持)
- [ ] peak order (1664,1584,1586) mode_F 系 subtype 6/55=10.9% → S56 連続 or rotation
- [ ] ub=1586 単独崩壊 pattern 3 例目 initial → S56 連続 or break

## リスク・注意点

- **GPU 占有**: バッチ所要 約 37 分。他セッションが並行して t120h-p100 を必要とする場合は事前調整
- **cool time 恣意的制御なし**: S55 バッチ終了 (08:16:30 JST) から現時点 (約 08:27 JST) で約 11 分経過。lock 取得〜バッチ開始までの自然時間経過を受け入れる (S1..S55 と同 stance)
- **llama.cpp HEAD drift**: S55 と同一 build dir を再利用、rebuild はしない (upstream drift は Phase N で別途検証)
- **disk 容量**: S56 の out ディレクトリ 6 個 (warmup × 3 + 1k × 3) + startup_logs 3 個が生成される。過去同規模で問題なし
- **lock 失敗時**: 他 Claude セッションがロック保持中なら待機 or ユーザに状況確認を依頼

## 重要ファイルのパス

- S55 ディレクトリ (複製元):
  `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-22_081858_qwen3-122b-c3-phaseSeval55s/`
- S55 レポート (参照元):
  `/home/ubuntu/projects/llm-server-ops/report/2026-04-22_081858_qwen3-122b-c3-phaseSeval55s.md`
- GPU ロックスクリプト:
  `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/lock.sh`
  `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/unlock.sh`
- Skill 定義:
  `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/`
  `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/`
- レポートルール: `/home/ubuntu/projects/llm-server-ops/REPORT.md`
- プロジェクト指示: `/home/ubuntu/projects/llm-server-ops/CLAUDE.md`

## 検証方法（end-to-end）

1. GPU ロック解放後、`ssh t120h-p100 "ps aux | grep llama-server | grep -v grep"` で llama-server プロセスが残っていないこと確認
2. `analyze_phaseSeval56s.py` 実行後に `phaseSeval56s_verdict.txt` を開き、3 ub の `verdict_1run` (accept/partial/reject) が出力されていること確認
3. `phaseSeval56s_stats.csv` で n=280 (各 ub n=280) の mean/σ が S55 の n=275 から自然に更新されていること確認
4. `timeseries_eval_tps.png` に S56 の 3 点 (1584/1586/1664) が追加され、trend line が再計算・slope ラベルが更新されていることを目視確認
5. 生成レポートに「未検証事項」と「検証完了後に実施すべき TODO」セクションが含まれていることを確認 (ユーザ明示指示)
6. レポート内参照リンクが S55 / S54 / S53 / S52 / S50 / S47 / S38 / S22 / S15 / S1 / Sbfine 系へ適切に張られていること確認
