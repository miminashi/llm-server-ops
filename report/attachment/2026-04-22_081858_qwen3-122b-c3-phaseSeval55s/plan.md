# Plan: Phase S-eval-55session (第 55 セッション)

## Context

直前レポート [2026-04-22_072412_qwen3-122b-c3-phaseSeval54s.md](file:///home/ubuntu/projects/llm-server-ops/report/2026-04-22_072412_qwen3-122b-c3-phaseSeval54s.md) の「未検証事項」新規項目に **★最優先 26 項目**・**★高優先 7 項目**・**★中優先 3 項目**、「検証完了後に実施すべき TODO」先頭に **★最優先: Phase S-eval-55session 候補** が明示されている。

これら ★最優先 の大半は「次 session を **同条件で実施すれば一度に判定できる連続性/break 観察項目**」であり、個別深掘り (boundary-fine / extended / tensor-dump / markov 推定など) に進むよりも、まず S55 を 1 session 進めて連続記録・break 判定を確定させるのが最も高 ROI。これは S1→S54 までの全 session で採用してきた方針の継続。

本計画の目的:

- **n=55 session / pooled 275-run へ統計拡張**
- **S54 の ★最優先 TODO 群（26 項目）を同条件 1 バッチで一括検証**
  - Welch (-/+/+) 連続 or 新 subtype、ub=1664 "11+1+3+1" pattern 継続、ub=1586 崩壊 1 fix confirm、ub=1584 2-session interval 4 例目 (予測 S56 崩壊)、double collapse (1586/1664) break 2 連続、intra-day 9 session 連続、Welch |t|>60 ub=1586 再拡大 or 縮小、3 ub sig 3/3 5 連続、σ_pool 1664 1 位 8 連続、σ_pool 1586 縮小 2 連続、pool 差 +0.04 帯維持 or +0.05 復帰、ub=1586 |Δ_max| 担当 3 連続、|Δ_max|=1.224 歴代 3 位 record 更新、|Δ|>0.5 連続 6 session、|Δ|>1.0 5 例目、3 ub Δ pattern 新 subtype、initial subtype 6 連続、ub=1664 崩壊 過半数維持 11 session、ub=1586 崩壊 13/55 or 12/55、全 ub reject 4 連続、prompt_tps ub=1586 最高 4 連続、pure mode_B 2 連続、mode_B_delta 連続、cool time 18+ 分 2 連続、ub=1664 pool min 14.212 維持 5 連続 など
- **時系列プロット (S1..S55) および trend line を更新**

**cool time 観察**: S54 終了 (2026-04-22 07:21:56 JST) から現時点 (07:32 JST) で約 11 分経過済。準備整い次第開始する S1..S54 の stance を踏襲し、恣意的時刻合わせはしない。結果として S55 cool time は <13 分 sub-zone / 通常帯 / 境界帯 のいずれかに自然に配置される → それ自体が観察対象。

## 前提条件

- GPU サーバ: **t120h-p100** (10.1.4.14、Tesla P100 × 4、S1..S54 と同一環境)
- モデル: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M` (S1..S54 と同一 snapshot)
- llama.cpp: HEAD（S54 同一ビルド `~/llama.cpp/build` を再利用、rebuild しない）
- 固定パラメータ: `ctx=32768`、`fa=1`、`cache-type-k/v=f16/f16`、`numactl --cpunodebind=1 --membind=1`、`threads=40`、`poll=0`、`parallel=1`、OT_REGEX 不変
- 可変軸: `ub ∈ {1584, 1586, 1664}`、`-b=-ub` (各 ub で一致)
- 試行: warmup 2 run + eval 5 run × 3 ub = **21 run**（S1..S54 と同一設計）
- prompt: `prompts/prompt_1k.txt`（6200 bytes、1086 tokens、S1..S54 と同一ファイル）
- 所要時間目安: 36〜42 分 (S54 実績: 37 分 00 秒)

## 実施手順

### 1. GPU ロック取得

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

Skill `gpu-server` の指示に従う (CLAUDE.md 制約)。取得後は heartbeat 保持確認。

### 2. S54 ディレクトリを S55 として複製 → 文字列置換

複製元: `report/attachment/2026-04-22_072412_qwen3-122b-c3-phaseSeval54s/`

```bash
cd /home/ubuntu/projects/llm-server-ops/report/attachment
NEW_DIR="$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)_qwen3-122b-c3-phaseSeval55s"
cp -r 2026-04-22_072412_qwen3-122b-c3-phaseSeval54s "$NEW_DIR"
cd "$NEW_DIR"
```

新ディレクトリ内での置換:

| 対象 | 置換ルール |
|------|-----------|
| ファイル名 | `*phaseSeval54s*` → `*phaseSeval55s*`、`*Seval54s*` → `*Seval55s*` |
| スクリプト内文字列 | `phaseSeval54s` → `phaseSeval55s`、`Seval54s` → `Seval55s` |
| `analyze_phaseSeval55s.py` 内 `CUR_SESSION_LABEL` | `S54_phaseSeval54s` → `S55_phaseSeval55s` |
| `analyze_phaseSeval55s.py` 内 `PRIOR_TSVS` | S54 の `summary_phaseSeval54s.tsv` パスを末尾に追加 (n=55 pool を構成) |
| `plot_timeseries.py` 内 `S_EVAL_DIRS` | S54 ディレクトリパスを末尾に追加 |
| `out_Seval54s_*/` ディレクトリ (複製された旧 run 成果物) | **全削除** (S55 で再生成) |
| `batch_phaseSeval54s.log` (複製) | 削除 |
| `summary_*`, `*_stats.csv`, `*_verdict.txt`, `timeseries_eval_tps.png`, `startup_logs/*`, `run_*.log` (複製) | 削除 |
| `plan.md` | 本ファイル (S55 plan) で上書き |

### 3. バッチ実行

```bash
cd report/attachment/<new-s55-dir>
bash batch_phaseSeval55s.sh 2>&1 | tee batch_phaseSeval55s.log
```

- GPU ロック lease は batch 中に lapse しないよう適宜更新 (skill `gpu-server` 指示)
- batch 構造: 3 ub × (stop→start→health→warmup2→eval5→stop) 直列ループ

### 4. 集計 + プロット生成

```bash
python3 analyze_phaseSeval55s.py   # summary_phaseSeval55s.tsv / phaseSeval55s_stats.csv / phaseSeval55s_verdict.txt
python3 plot_timeseries.py         # timeseries_eval_tps.png (S1..S55, trend line 重畳)
```

集計結果から以下を抽出:
- 3 ub の eval_tps mean / σ
- session-to-session Δ (S54 → S55) と |Δ_max| 担当 ub
- Welch t-test (prior 54-session pool vs S55) の 3 ub 符号 → subtype 判定
- pool n=275 の mean/σ、σ_pool 順序、pool 差 (1586-1584, 1586-1664, 1664-1584)
- peak order pattern / mode 分類 / peak 1 位 ub
- ub=1584/1586/1664 崩壊判定と頻度更新
- warmup1 ub=1584 の mode_{A..F}_band / _delta 判定
- cool time (S54 終了 07:21:56 → S55 開始) と sub-zone 判定
- verdict_1run (accept/partial/reject) (ref: 1584=15.293, 1586=15.466, 1664=15.451 / Sbfine 系)
- trend line slope (3 ub) の n=55 値

### 5. レポート作成

[REPORT.md](file:///home/ubuntu/projects/llm-server-ops/REPORT.md) ルールに従い生成:

- タイトル: `Qwen3.5-122B-A10B C-3 Phase S-eval-55session`
- 添付ファイル一覧 (plan.md / スクリプト / ログ / TSV / stats.csv / verdict.txt / PNG / prompts / out ディレクトリ / startup_logs)
- 参照: 直前 S54、S53、S52、S50、S47、S38、S22、S15、S1、Sbfine 系
- 前提・目的
- 核心発見サマリ (S54 ★最優先 TODO への回答を項目別に明示)
- intra-day cluster / cool time / mode 分類 / σ_pool / Δ pattern / Welch subtype / prompt_tps / trend line slope 各セクション
- **「未検証事項」セクション** — S55 で確定した連続記録・break/継続を受けて S56 へ引き継ぐ項目を列挙（**必須**、ユーザ指示）
- **「検証完了後に実施すべき TODO」セクション** — 次 Phase 候補を優先順位付き列挙 (S54 末尾構成を踏襲、**必須**、ユーザ指示)

### 6. GPU ロック解放

```bash
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 7. Discord 通知 (任意)

Skill `discord-notify` でレポート URL を通知 (S1..S54 で通知している場合は継続)。

## S55 で一括判定される ★最優先項目（S54 レポート由来、26 項目）

- [ ] Welch (-/-/-) → (-/+/+) shift 53-session 初 → S55 (-/+/+) 連続 or 新 subtype
- [ ] ub=1664 "11+1+3+1" pattern → S55 "11+1+3+2" 崩壊 or "11+1+3+1+1" normal 継続
- [ ] ub=1586 崩壊 1 単発 confirm → S55 崩壊 or normal 3 連続
- [ ] ub=1584 崩壊 2-session interval 3 例目 → S55 normal 復帰 or 4 例目 (S56 崩壊 予測)
- [ ] double collapse (1586/1664) break 1 fix → S55 復帰 or 2 連続 break
- [ ] intra-day 8 session 連続 → S55 intra-day 9 session or inter-day 2 例目
- [ ] Welch |t|>60 ub=1586 → S54 |t|<10 縮小 → S55 再拡大 or 縮小継続
- [ ] 3 ub sig 3/3 達成 4 連続 → S55 5 連続 or partial 復帰
- [ ] σ_pool 1664 1 位 7 連続 → S55 8 連続 or 1586 奪還
- [ ] σ_pool 1586 縮小復帰 1 fix → S55 縮小 2 連続 or 拡大復帰
- [ ] pool 差 +0.04 帯復帰 1 fix (+0.044) → S55 +0.04 維持 or +0.05 帯復帰 or +0.03 帯戻り
- [ ] ub=1586 |Δ_max| 担当 2 連続 → S55 3 連続 or 他 ub
- [ ] |Δ_max|=1.224 53-session 歴代 3 位 record → S55 更新 or 縮小
- [ ] |Δ|>0.5 連続 5 session → S55 6 連続 or 縮小
- [ ] |Δ|>1.0 4 session (全 ub=1586 担当 100%) → S55 5 例目 or 安定
- [ ] 3 ub Δ pattern (-/+/+) → S55 shift or 連続
- [ ] initial subtype 5 連続 (S50-S54) → S55 6 連続 or 既知 subtype 復帰
- [ ] ub=1664 崩壊 31/54=57.4% → S55 32/55 or 31/55 (過半数維持 11 session 判定)
- [ ] ub=1586 崩壊 12/54=22.2% → S55 13/55 or 12/55
- [ ] 全 ub reject 3 連続達成 → S55 4 連続 or partial 復帰
- [ ] prompt_tps ub=1586 最高 3 連続 → S55 4 連続 or rotation
- [ ] warmup1 pure mode_B 復帰 1 fix → S55 pure mode_B 2 連続 or shift
- [ ] warmup1 mode_B_delta 復帰 49 session ぶり → S55 連続 or mode_A/C_delta 復帰
- [ ] cool time 18+ 分復帰 1 fix → S55 18+ 分 2 連続 or 他 sub-zone
- [ ] ub=1664 pool min 14.212 維持 4 連続 → S55 5 連続 or 更新 or 回復

## S55 で判定される ★高優先項目（S54 レポート由来）

- [ ] ub=1664 pool max 15.534 維持 16 連続 → S55 17 連続 or 更新
- [ ] ub=1586 pool max 15.532 維持 12 連続 → S55 13 連続 or 更新
- [ ] ub=1586 pool min 13.840 維持 32 連続 → S55 33 連続 or 比較
- [ ] ub=1584 pool min 13.958 維持 39 連続 → S55 40 連続 or 比較
- [ ] peak 1 位 1586 25/54=46.3% → S55 26/55 or 25/55 (最安定維持)
- [ ] peak order (1664,1586,1584) mode_E 系 subtype 6/54=11.1% → S55 連続 or rotation
- [ ] ub=1664 peak 1 位復帰 1 fix (S50 以来 4 session ぶり) → S55 連続 or break

## リスク・注意点

- **GPU 占有**: バッチ所要 約 37 分。他セッションが並行して t120h-p100 を必要とする場合は事前調整
- **cool time 恣意的制御なし**: S54 終了から現時点 (07:32 JST) で約 11 分経過。lock 取得〜バッチ開始までの自然時間経過を受け入れる (S1..S54 と同 stance)
- **llama.cpp HEAD drift**: S54 と同一 build dir を再利用、rebuild はしない (upstream drift は Phase N で別途検証)
- **disk 容量**: S55 の out ディレクトリ 6 個 (warmup × 3 + 1k × 3) + startup_logs 3 個が生成される。過去同規模で問題なし
- **lock 失敗時**: 他 Claude セッションがロック保持中なら待機 or ユーザに状況確認を依頼

## 重要ファイルのパス

- S54 ディレクトリ (複製元):
  `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-22_072412_qwen3-122b-c3-phaseSeval54s/`
- S54 レポート (参照元):
  `/home/ubuntu/projects/llm-server-ops/report/2026-04-22_072412_qwen3-122b-c3-phaseSeval54s.md`
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
2. `analyze_phaseSeval55s.py` 実行後に `phaseSeval55s_verdict.txt` を開き、3 ub の `verdict_1run` (accept/partial/reject) が出力されていること確認
3. `phaseSeval55s_stats.csv` で n=275 (各 ub n=275) の mean/σ が S54 の n=270 から自然に更新されていること確認
4. `timeseries_eval_tps.png` に S55 の 3 点 (1584/1586/1664) が追加され、trend line が再計算・slope ラベルが更新されていることを目視確認
5. 生成レポートに「未検証事項」と「検証完了後に実施すべき TODO」セクションが含まれていることを確認 (ユーザ明示指示)
6. レポート内参照リンクが S54 / S53 / S52 / S50 / S47 / S38 / S22 / S15 / S1 / Sbfine 系へ適切に張られていること確認
