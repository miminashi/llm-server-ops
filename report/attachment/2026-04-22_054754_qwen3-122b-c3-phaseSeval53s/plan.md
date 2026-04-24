# Plan: Phase S-eval-53session (第 53 セッション)

## Context

最新レポート [2026-04-22_044633_qwen3-122b-c3-phaseSeval52s.md](file:///home/ubuntu/projects/llm-server-ops/report/2026-04-22_044633_qwen3-122b-c3-phaseSeval52s.md) の「未検証事項」で **★最優先** として挙げられている項目が 20 以上あり、それらの大半は **次 session (S53) を同条件で実施すれば一度に検証できる連続性/カテゴリ観察項目**（mode_B 3 連続、ub=1664 "11+1+3" 拡張、ub=1584 2-session interval 崩壊継続、double collapse 2 連続、intra-day 7 session、Welch (-/-/-) 連続、σ_pool 1664 1 位 6 連続、pool 差 +0.05 帯 4 連続、cool time <13 分 2 連続、mode_C_delta 連続 など）。

個別項目の深掘り（Phase S-eval-boundary-fine、Phase S-eval-extended、Phase Sb-tensor-dump など）は 1 session 単位の観察継続とは別軸の「次 Phase 候補」であり、まずは継続観察を 1 session 進めて連続性を確定するのが高 ROI。したがって本計画は **Phase S-eval-53session を S52 と同条件で実施** する。

**目的**: n=53 session / pooled 265-run へ統計拡張、S52 の ★最優先 TODO 群（連続性判定項目）を同時検証、時系列プロット (S1..S53) および trend line を更新。

## 前提条件

- GPU サーバ: **t120h-p100** (10.1.4.14、Tesla P100 × 4、S1..S52 同一環境)
- モデル: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`（S1..S52 と同一）
- llama.cpp: HEAD（S52 同一ビルド、`~/llama.cpp/build`）
- 固定パラメータ: ctx=32768、fa=1、cache-type-k/v=f16/f16、numactl --cpunodebind=1 --membind=1、threads=40、poll=0、parallel=1、OT_REGEX 不変
- 可変軸: ub ∈ {1584, 1586, 1664}、各 `-b=-ub`
- 試行: warmup 2 run + eval 5 run × 3 ub = 21 run（S52 と同一設計）
- prompt: `prompts/prompt_1k.txt`（6200 bytes、1086 tokens、S1..S52 と同一）

## 実施手順

### 1. GPU ロック取得

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

Skill `gpu-server` の指示に従う（CLAUDE.md 制約）。ロック取得後は lease 保持確認。

### 2. S52 ディレクトリを S53 ディレクトリへ複製

```bash
cd /home/ubuntu/projects/llm-server-ops/report/attachment
cp -r 2026-04-22_044633_qwen3-122b-c3-phaseSeval52s \
      $(date +%Y-%m-%d_%H%M%S)_qwen3-122b-c3-phaseSeval53s
```

新ディレクトリ内で以下を書き換える:

| 対象 | 置換ルール |
|------|-----------|
| スクリプトファイル名 | `*_phaseSeval52s.*` → `*_phaseSeval53s.*` |
| スクリプト内文字列 | `phaseSeval52s` → `phaseSeval53s`、`Seval52s` → `Seval53s` |
| `analyze_phaseSeval53s.py` 内 `CUR_SESSION_LABEL` | `S52_phaseSeval52s` → `S53_phaseSeval53s` |
| `analyze_phaseSeval53s.py` 内 `PRIOR_TSVS` | S52 の summary_phaseSeval52s.tsv パスを末尾に追加 |
| `plot_timeseries.py` 内 `S_EVAL_DIRS` | S52 ディレクトリを末尾に追加 |
| `out_Seval52s_*/` ディレクトリ（複製された旧 run 成果物） | 全削除（S53 で再生成） |
| `batch_phaseSeval52s.log`（複製されたログ） | 削除 |
| `summary_*`、`*_stats.csv`、`*_verdict.txt`（複製された集計結果） | 削除 |

### 3. バッチ実行

```bash
cd report/attachment/<new-s53-dir>
bash batch_phaseSeval53s.sh 2>&1 | tee batch_phaseSeval53s.log
```

- 所要時間目安: S52 で 36 分 53 秒 → S53 も約 37 分を想定
- GPU lock lease は batch 中に lapse しないよう適宜 heartbeat 更新（skill `gpu-server` の指示に従う）

### 4. 集計 + プロット生成

```bash
python3 analyze_phaseSeval53s.py   # summary_phaseSeval53s.tsv / phaseSeval53s_stats.csv / phaseSeval53s_verdict.txt
python3 plot_timeseries.py         # timeseries_eval_tps.png (S1..S53, trend line 重畳)
```

集計結果から下記を抽出:
- 3 ub の eval_tps mean / σ
- session-to-session Δ (S52 → S53) と |Δ_max| 担当 ub
- Welch t-test（prior 52-session pool vs S53）の 3 ub 符号 → subtype 判定
- pool n=265 の mean/σ、σ_pool 順序、pool 差
- peak order pattern / mode 分類
- ub=1584/1586/1664 崩壊判定と頻度更新
- warmup1 ub=1584 の mode_{A..F}_delta 判定
- cool time（S52 終了 → S53 開始）と sub-zone 判定
- verdict_1run (accept/partial/reject)

### 5. レポート作成

[REPORT.md](file:///home/ubuntu/projects/llm-server-ops/REPORT.md) に従って以下のセクションを含むレポートを生成:

- タイトル: `Qwen3.5-122B-A10B C-3 Phase S-eval-53session`
- 添付ファイル一覧（plan.md / スクリプト / ログ / TSV / stats.csv / verdict.txt / PNG / prompts / out ディレクトリ）
- 参照（直前レポート S52、S51、S50、S48、S47、S38、S22、S15、S1 など従来 reference 継承）
- 前提・目的
- 核心発見サマリ（S52 ★最優先 TODO への回答を中心に）
- intra-day cluster / cool time / mode 分類 / σ_pool / Δ pattern / Welch subtype / prompt_tps / trend line slope の各セクション
- **「未検証事項」セクション** — S53 で確定した連続記録・break/継続を受けて S54 へ引き継ぐ項目を列挙
- **「検証完了後に実施すべき TODO」セクション** — 次 Phase 候補を優先順位付き列挙（S52 レポートの末尾構成を踏襲）

### 6. GPU ロック解放

```bash
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 7. REPORT.md / CLAUDE.md 整合性チェック

レポートを追加したことで上位の [REPORT.md](file:///home/ubuntu/projects/llm-server-ops/REPORT.md) にも反映が必要か確認（S52 時点で未反映ならそのまま踏襲）。CLAUDE.md の peak 1 位分類等の数値更新は S52 レポートで既に未反映 TODO 扱いのためここでは deferral。

## S53 で検証される項目（S52 レポートの ★最優先 TODO との対応）

本 session の実施のみで一括判定される項目:

- [ ] mode_B 2 連続 → 3 連続 or 他 mode
- [ ] ub=1664 "11+1+2" → "11+1+3" or normal 復帰
- [ ] ub=1584 崩壊復帰 1 fix → 崩壊 2 連続 or normal
- [ ] double collapse (1584/1664) 復帰 1 fix → 2 連続 or break
- [ ] intra-day 6 → 7 or inter-day 2 例目
- [ ] Welch (-/-/-) 52-session 初 subtype → 連続 or 新 subtype
- [ ] Welch |t|>20 ub=1584/1664 同時 → 連続 or 縮小
- [ ] σ_pool 1664 1 位 5 連続 → 6 連続 or 1586 奪還
- [ ] σ_pool 1586 縮小 5 連続 → 6 連続 or 拡大
- [ ] pool 差 +0.05 帯 3 連続 → 4 連続 or +0.04 帯復帰
- [ ] ub=1584 |Δ_max| 担当復帰 1 fix → 2 連続 or 他 ub
- [ ] |Δ|>0.5 連続 3 session → 4 連続 or 縮小
- [ ] 3 ub Δ (-/-/-) 52-session 初 subtype → shift or 連続
- [ ] initial subtype 3 連続 (S50-S52) → 新 subtype 連続 or 既知 subtype 復帰
- [ ] ub=1586 崩壊 break 5 連続 → 6 連続 or 崩壊復帰
- [ ] ub=1586/1664 reject 6 連続 + ub=1584 reject → 全 ub reject 2 連続 or partial 復帰
- [ ] prompt_tps ub=1586 最高復帰 1 fix → 2 連続 or rotation
- [ ] warmup1 out_of_prior_bands + mode_C_delta 46 session ぶり → 2 連続 or 既知 band 復帰
- [ ] cool time <13 分 1 fix → 2 連続 or 通常帯復帰
- [ ] ub=1664 pool min 14.212 維持 2 連続 → 3 連続 or 更新 or 回復
- [ ] ub=1664 pool max 15.534 維持 14 連続 → 15 連続 or 更新
- [ ] ub=1586 pool max 15.532 維持 10 連続 → 11 連続 or 更新
- [ ] peak 1 位 1586 25/52=48.1% → 26/53 or 24/53
- [ ] double collapse (1586/1664) 復帰なし 5 連続 → 6 連続 or 復帰

## リスク・注意点

- **GPU 占有**: バッチ所要 約 37 分。他セッションが並行して t120h-p100 を必要とする場合は事前調整
- **cool time < 13 分 sub-zone**: S52 で初出現、S53 開始時刻次第で継続判定可否が決まる。恣意的な時刻合わせはせず「準備完了次第開始」を踏襲（S1..S52 と同じ stance）
- **S52 終了 2026-04-22 05:25:18 JST からの間隔**: 現時点で既に数十分経過済みの場合は <13 分 sub-zone は break が確定する可能性あり。いずれにせよ cool time そのものが観察対象 → 恣意的制御なし
- **llama.cpp HEAD drift**: S52 と同一 build dir を再利用。rebuild はしない（ビルド drift は Phase N で別途検証）

## 重要ファイルのパス

- S52 ディレクトリ（複製元）:
  `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-22_044633_qwen3-122b-c3-phaseSeval52s/`
- S52 レポート（参照元）:
  `/home/ubuntu/projects/llm-server-ops/report/2026-04-22_044633_qwen3-122b-c3-phaseSeval52s.md`
- GPU ロックスクリプト:
  `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/lock.sh`
  `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/unlock.sh`
- Skill 定義:
  `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/`
  `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/`
- レポートルール:
  `/home/ubuntu/projects/llm-server-ops/REPORT.md`
- プロジェクト指示:
  `/home/ubuntu/projects/llm-server-ops/CLAUDE.md`

## 検証方法（end-to-end）

1. `ssh t120h-p100 "ps aux | grep llama-server | grep -v grep"` で llama-server プロセスが起動していないこと確認（GPU ロック解放後）
2. `analyze_phaseSeval53s.py` 実行後に `phaseSeval53s_verdict.txt` を開き、3 ub の verdict_1run が出力されていること確認
3. `phaseSeval53s_stats.csv` で n=265 (各 ub n=265) の mean/σ が S52 の n=260 から自然に更新されていること確認
4. `timeseries_eval_tps.png` に S53 の 3 点が追加され、trend line が再計算されていることを目視確認
5. レポートに「未検証事項」と「検証完了後に実施すべき TODO」セクションが入っていることを grep で確認
