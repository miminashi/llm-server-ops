# Plan: Phase S-eval-54session (第 54 セッション)

## Context

直前レポート [2026-04-22_054754_qwen3-122b-c3-phaseSeval53s.md](file:///home/ubuntu/projects/llm-server-ops/report/2026-04-22_054754_qwen3-122b-c3-phaseSeval53s.md) の「未検証事項」に **★最優先 24 項目**、「検証完了後に実施すべき TODO」先頭に **★最優先: Phase S-eval-54session 候補** が明示されている。

これら ★最優先 の大半は「次 session を **同条件で実施すれば一度に判定できる連続性/カテゴリ観察項目**」であり、個別深掘り (boundary-fine / extended / tensor-dump 等) に進むよりも、まず S54 を 1 session 進めて連続記録・break 判定を確定させるのが最も高 ROI。これは S1→S53 までの全 session で採用してきた方針の継続。

本計画の目的:

- **n=54 session / pooled 270-run へ統計拡張**
- **S53 の ★最優先 TODO 群（24 項目）を同条件 1 バッチで一括検証**（mode_B 復帰、"11+1+4" or 崩壊復帰、ub=1586 崩壊 2 連続、ub=1584 2-session interval 再発、double collapse (1586/1664) 2 連続、intra-day 8 session、Welch (-/-/-) 3 連続、|t|>60 継続、σ_pool 1664 1 位 7 連続、pool 差 +0.05 復帰、|Δ_max| 歴代 3 位 更新、|Δ|>0.5 5 連続、全 ub reject 3 連続、cool time 20+ 分 2 連続、ub=1664 pool min 4 連続 など）
- **時系列プロット (S1..S54) および trend line を更新**

**cool time 観察**: 現時点 (2026-04-22 06:38 JST) で S53 終了 (06:26:10) から約 12 分経過済。準備整い次第開始する S1..S53 の stance を踏襲し、恣意的時刻合わせはしない。結果として S54 cool time は <13 分 sub-zone 再発 / 通常帯復帰 / 境界帯 のいずれかに自然に配置される → それ自体が観察対象。

## 前提条件

- GPU サーバ: **t120h-p100** (10.1.4.14、Tesla P100 × 4、S1..S53 と同一環境)
- モデル: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M` (S1..S53 と同一 snapshot)
- llama.cpp: HEAD（S53 同一ビルド `~/llama.cpp/build` を再利用、rebuild しない）
- 固定パラメータ: `ctx=32768`、`fa=1`、`cache-type-k/v=f16/f16`、`numactl --cpunodebind=1 --membind=1`、`threads=40`、`poll=0`、`parallel=1`、OT_REGEX 不変
- 可変軸: `ub ∈ {1584, 1586, 1664}`、`-b=-ub` (各 ub で一致)
- 試行: warmup 2 run + eval 5 run × 3 ub = **21 run**（S1..S53 と同一設計）
- prompt: `prompts/prompt_1k.txt`（6200 bytes、1086 tokens、S1..S53 と同一ファイル）
- 所要時間目安: 36〜42 分 (S53 実績: 36 分 43 秒)

## 実施手順

### 1. GPU ロック取得

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

Skill `gpu-server` の指示に従う (CLAUDE.md 制約)。取得後は heartbeat 保持確認。

### 2. S53 ディレクトリを S54 として複製 → 文字列置換

複製元: `report/attachment/2026-04-22_054754_qwen3-122b-c3-phaseSeval53s/`

```bash
cd /home/ubuntu/projects/llm-server-ops/report/attachment
NEW_DIR="$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)_qwen3-122b-c3-phaseSeval54s"
cp -r 2026-04-22_054754_qwen3-122b-c3-phaseSeval53s "$NEW_DIR"
cd "$NEW_DIR"
```

新ディレクトリ内での置換:

| 対象 | 置換ルール |
|------|-----------|
| ファイル名 | `*phaseSeval53s*` → `*phaseSeval54s*`、`*Seval53s*` → `*Seval54s*` |
| スクリプト内文字列 | `phaseSeval53s` → `phaseSeval54s`、`Seval53s` → `Seval54s`、ヘッダの説明行 `52s / 53s` 日付系のコメントは実測時刻で更新 |
| `analyze_phaseSeval54s.py` 内 `CUR_SESSION_LABEL` | `S53_phaseSeval53s` → `S54_phaseSeval54s` |
| `analyze_phaseSeval54s.py` 内 `PRIOR_TSVS` | S53 の `summary_phaseSeval53s.tsv` パスを末尾に追加 (n=54 pool を構成) |
| `plot_timeseries.py` 内 `S_EVAL_DIRS` | S53 ディレクトリパスを末尾に追加 |
| `out_Seval53s_*/` ディレクトリ (複製された旧 run 成果物) | **全削除** (S54 で再生成) |
| `batch_phaseSeval53s.log` (複製) | 削除 |
| `summary_*`, `*_stats.csv`, `*_verdict.txt`, `timeseries_eval_tps.png`, `startup_logs/*`, `run_*.log` (複製) | 削除 |
| `plan.md` | 本ファイル (S54 plan) で上書き |

### 3. バッチ実行

```bash
cd report/attachment/<new-s54-dir>
bash batch_phaseSeval54s.sh 2>&1 | tee batch_phaseSeval54s.log
```

- GPU ロック lease は batch 中に lapse しないよう適宜更新 (skill `gpu-server` 指示)
- batch 構造: 3 ub × (stop→start→health→warmup2→eval5→stop) 直列ループ

### 4. 集計 + プロット生成

```bash
python3 analyze_phaseSeval54s.py   # summary_phaseSeval54s.tsv / phaseSeval54s_stats.csv / phaseSeval54s_verdict.txt
python3 plot_timeseries.py         # timeseries_eval_tps.png (S1..S54, trend line 重畳)
```

集計結果から以下を抽出:
- 3 ub の eval_tps mean / σ
- session-to-session Δ (S53 → S54) と |Δ_max| 担当 ub
- Welch t-test (prior 53-session pool vs S54) の 3 ub 符号 → subtype 判定
- pool n=270 の mean/σ、σ_pool 順序、pool 差 (1586-1584, 1586-1664, 1664-1584)
- peak order pattern / mode 分類 / peak 1 位 ub
- ub=1584/1586/1664 崩壊判定と頻度更新
- warmup1 ub=1584 の mode_{A..F}_band / _delta 判定
- cool time (S53 終了 06:26:10 → S54 開始) と sub-zone 判定
- verdict_1run (accept/partial/reject) (ref: 1584=15.293, 1586=15.466, 1664=15.451 / Sbfine 系)
- trend line slope (3 ub) の n=54 値

### 5. レポート作成

[REPORT.md](file:///home/ubuntu/projects/llm-server-ops/REPORT.md) ルールに従い生成:

- タイトル: `Qwen3.5-122B-A10B C-3 Phase S-eval-54session`
- 添付ファイル一覧 (plan.md / スクリプト / ログ / TSV / stats.csv / verdict.txt / PNG / prompts / out ディレクトリ / startup_logs)
- 参照: 直前 S53、S52、S51、S50、S47、S38、S22、S15、S1、Sbfine 系
- 前提・目的
- 核心発見サマリ (S53 ★最優先 TODO への回答を項目別に明示)
- intra-day cluster / cool time / mode 分類 / σ_pool / Δ pattern / Welch subtype / prompt_tps / trend line slope 各セクション
- **「未検証事項」セクション** — S54 で確定した連続記録・break/継続を受けて S55 へ引き継ぐ項目を列挙（**必須**、ユーザ指示）
- **「検証完了後に実施すべき TODO」セクション** — 次 Phase 候補を優先順位付き列挙 (S53 末尾構成を踏襲、**必須**、ユーザ指示)

### 6. GPU ロック解放

```bash
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 7. Discord 通知 (任意)

Skill `discord-notify` でレポート URL を通知 (S1..S53 で通知している場合は継続)。

## S54 で一括判定される ★最優先項目（S53 レポート由来、24 項目）

- [ ] Welch (-/-/-) 2 連続 → S54 3 連続 or 新 subtype
- [ ] ub=1664 "11+1+3" 崩壊 → S54 "11+1+4" or normal 復帰
- [ ] ub=1586 崩壊復帰 1 fix → S54 2 連続 or normal 復帰
- [ ] ub=1584 崩壊 2-session interval break → S54 崩壊 or normal
- [ ] double collapse (1586/1664) 復帰 1 fix → S54 2 連続 or break
- [ ] intra-day 7 session → S54 8 session or inter-day 2 例目
- [ ] Welch |t|>60 ub=1586 initial → S54 継続 or 縮小
- [ ] 3 ub sig 3/3 達成 3 連続 → S54 4 連続 or partial
- [ ] σ_pool 1664 1 位 6 連続 → S54 7 連続 or 1586 奪還
- [ ] σ_pool 1586 拡大 break → S54 縮小復帰 or 拡大継続
- [ ] pool 差 +0.05 帯 3 連続 break (+0.036) → S54 +0.05 帯復帰 or +0.03 帯継続
- [ ] ub=1586 |Δ_max| 担当復帰 1 fix → S54 2 連続 or 他 ub
- [ ] |Δ_max|=1.110 52-session 3 位級 → S54 更新 or 縮小
- [ ] |Δ|>0.5 連続 4 session → S54 5 連続 or 縮小
- [ ] |Δ|>1.0 3 session (全 ub=1586 担当) → S54 4 例目 or 安定
- [ ] 3 ub Δ pattern (+/-/+) → S54 shift or 連続
- [ ] initial subtype 4 連続 (S50-S53) → S54 5 連続 or 既知 subtype
- [ ] ub=1664 崩壊 31/53=58.5% → S54 32/54 or 31/54 (過半数維持 10 判定)
- [ ] ub=1586 崩壊 12/53=22.6% → S54 13/54 or 12/54
- [ ] 全 ub reject 2 連続達成 → S54 3 連続 or partial 復帰
- [ ] prompt_tps ub=1586 最高 2 連続 → S54 3 連続 or rotation
- [ ] warmup1 hybrid (mode_B_band + mode_A_delta) 復帰 1 fix → S54 2 連続 or shift
- [ ] cool time 20+ 分復帰 1 fix → S54 2 連続 or 他 sub-zone
- [ ] ub=1664 pool min 14.212 維持 3 連続 → S54 4 連続 or 更新 or 回復

## S54 で判定される ★高優先項目（S53 レポート由来）

- [ ] ub=1664 pool max 15.534 維持 15 連続 → S54 16 連続 or 更新
- [ ] ub=1586 pool max 15.532 維持 11 連続 → S54 12 連続 or 更新
- [ ] ub=1586 pool min 13.840 維持 31 連続 → S54 32 連続 or 13.949 との比較
- [ ] peak 1 位 1586 25/53=47.2% → S54 26/54 or 25/54
- [ ] peak order (1584,1664,1586) minor pattern 5/53=9.4% → S54 連続 or rotation

## リスク・注意点

- **GPU 占有**: バッチ所要 約 37 分。他セッションが並行して t120h-p100 を必要とする場合は事前調整
- **cool time 恣意的制御なし**: S53 終了から現時点 (06:38 JST) で約 12 分経過。lock 取得〜バッチ開始までの自然時間経過を受け入れる (S1..S53 と同 stance)
- **llama.cpp HEAD drift**: S53 と同一 build dir を再利用、rebuild はしない (upstream drift は Phase N で別途検証)
- **disk 容量**: S54 の out ディレクトリ 6 個 (warmup × 3 + 1k × 3) + startup_logs 3 個が生成される。過去同規模で問題なし
- **lock 失敗時**: 他 Claude セッションがロック保持中なら待機 or ユーザに状況確認を依頼

## 重要ファイルのパス

- S53 ディレクトリ (複製元):
  `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-22_054754_qwen3-122b-c3-phaseSeval53s/`
- S53 レポート (参照元):
  `/home/ubuntu/projects/llm-server-ops/report/2026-04-22_054754_qwen3-122b-c3-phaseSeval53s.md`
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
2. `analyze_phaseSeval54s.py` 実行後に `phaseSeval54s_verdict.txt` を開き、3 ub の `verdict_1run` (accept/partial/reject) が出力されていること確認
3. `phaseSeval54s_stats.csv` で n=270 (各 ub n=270) の mean/σ が S53 の n=265 から自然に更新されていること確認
4. `timeseries_eval_tps.png` に S54 の 3 点 (1584/1586/1664) が追加され、trend line が再計算・slope ラベルが更新されていることを目視確認
5. 生成レポートに「未検証事項」と「検証完了後に実施すべき TODO」セクションが含まれていることを確認 (ユーザ明示指示)
6. レポート内参照リンクが S53 / S52 / S47 / S38 / S22 / S15 / S1 / Sbfine 系へ適切に張られていること確認
