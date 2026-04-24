# Phase S-eval-34session 実施プラン

## Context

直前レポート [2026-04-21_102734_qwen3-122b-c3-phaseSeval33s.md](/home/ubuntu/projects/llm-server-ops/report/2026-04-21_102734_qwen3-122b-c3-phaseSeval33s.md) の「未検証事項」セクション中、**新規項目（S33 で判明・発生）** には ★最優先 TODO が 8 個並ぶが、いずれも「S34 を 1 回実施すれば同時検証できる」内容。検証完了後 TODO にも **★最重要: Phase S-eval-34session 候補** と明記済。

S33 で発生した主な未検証 hypothesis:

1. **mode_F 初観測 → 再現頻度 / 連続化**（6-mode 全観測達成後の分布）
2. **ub=1586 2 連続崩壊 alternating break → 3 連続崩壊 or 回復分岐**
3. **ub=1664 中帯 stay 3 連続 → 4 連続可否**
4. **A=B タイ 3 連続 → 4 連続可否**
5. **ub=1584 「崩壊-回復 2 cycle」 7-session pattern → 8-session 延長**
6. **σ_pool 1586 1 位 2 連続 → 3 連続可否**
7. **Welch mixed (+/-/+) subtype → 再現 / 新 subtype 出現**
8. **3 ub 全 σ_pool 縮小 2 例目 → 3 例目 interval**

第 34 session (S34) を S33 と同一条件で実施し、上記を同時検証する。

## 実施概要

- **対象サーバ**: t120h-p100 (10.1.4.14、NVIDIA Tesla P100-PCIE-16GB × 4、GPU ロック必須)
- **条件**: S33 と完全同一 — fa=1, f16/f16 KV, ctx=32768, `numactl --cpunodebind=1 --membind=1`, threads=40, poll=0, ngl=999, OT=MoE-only
- **ub 条件**: {1584, 1586, 1664} × (warmup 2 + eval 5) = 3 条件 × 7 run
- **所要時間**: 37-40 分（S30-S33 実績）＋ロック取得・分析・レポート執筆で計 60-80 分

## cool time 観測方針

S32 終了 10:12:00 → S33 終了 11:07:03、現在 11:18 JST。ロック取得〜開始時点で cool time は自然記録。S32/S33 で境界帯 18+ 分 sub-zone 2 連続観測されており、S34 の cool time が通常帯 (13-16 分) に戻れば境界帯 2 連続限定 event 確定、18+ 分が続けば境界帯定着候補。意図的調整は行わず、レポート側で sub-zone 分類を記録。

## 修正対象ファイル

新規 attachment ディレクトリ: `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-21_<HHMMSS>_qwen3-122b-c3-phaseSeval34s/`

S33 の attachment (`/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-21_102734_qwen3-122b-c3-phaseSeval33s/`) からコピー＆置換:

| コピー元 (S33) | コピー先 (S34) | 置換内容 |
|---|---|---|
| `start_phaseSeval33s.sh` | `start_phaseSeval34s.sh` | `Seval33s` → `Seval34s`, `phaseSeval33s` → `phaseSeval34s`, `[start_phaseSeval33s]` → `[start_phaseSeval34s]` |
| `batch_phaseSeval33s.sh` | `batch_phaseSeval34s.sh` | `Seval33s` → `Seval34s`, `phaseSeval33s` → `phaseSeval34s`, `[batchSeval33s]` → `[batchSeval34s]`, `batch_phaseSeval33s` → `batch_phaseSeval34s`, `start_phaseSeval33s` → `start_phaseSeval34s` |
| `run_all.sh` | `run_all.sh` | 変更なし（汎用） |
| `measure_phaseI.sh` | `measure_phaseI.sh` | 変更なし（汎用） |
| `prompts/prompt_1k.txt` | `prompts/prompt_1k.txt` | 変更なし（Phase Sbfine3 以来流用） |
| `analyze_phaseSeval33s.py` | `analyze_phaseSeval34s.py` | PRIOR_TSVS に S33 追加（attachment/2026-04-21_102734_qwen3-122b-c3-phaseSeval33s/summary_phaseSeval33s.tsv）、`CUR_SESSION_LABEL = "S34_phaseSeval34s"`, `TAG_PREFIX = "Seval34s_fa1_ctx"`, 出力ファイル名を `*_phaseSeval34s.*`, docstring 内の "33 session" → "34 session" / "pooled 165-run" → "pooled 170-run" |
| `plan.md` | `plan.md` | 本 plan ファイル転記 |

## 実施手順

1. **GPU ロック取得**:
   ```bash
   bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
   ```

2. **attachment ディレクトリ作成**:
   - 開始時刻で `2026-04-21_<HHMMSS>_qwen3-122b-c3-phaseSeval34s/` を決定
   - S33 attachment から全ファイルをコピー
   - prompts ディレクトリも同時にコピー

3. **スクリプト置換**: 上表のとおり sed/Edit で置換

4. **バッチ実行**:
   ```bash
   cd report/attachment/2026-04-21_<HHMMSS>_qwen3-122b-c3-phaseSeval34s
   HOST=t120h-p100 bash batch_phaseSeval34s.sh > batch_phaseSeval34s.log 2>&1
   python3 analyze_phaseSeval34s.py
   ```

5. **GPU ロック解放**:
   ```bash
   bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
   ```

6. **レポート作成**: [REPORT.md](/home/ubuntu/projects/llm-server-ops/REPORT.md) のフォーマットに従う。`REPORT.md` のインデックス更新も実施。

## レポート記載必須項目

S33 レポート踏襲:
- タイトル、実施日時、作業種別、GPU ロック取得状況
- 添付ファイルリスト
- 参照（直前 S33 へのリンク必須）
- 前提・目的（S33 の ★最優先 TODO 群を明示）
- 核心発見サマリ（mode 分類、ub=1586 動向、ub=1664 帯、ub=1584 動向、Welch t、σ_pool、pool 差、within-σ、cool time、compute buffer、ピーク 1 位、warmup1 hybrid、prompt_tps）
- 判定しきい値、成功条件
- 環境情報（S33 と完全同一であること明記）
- セッション間隔（S33 終了 → S34 開始 cool time、sub-zone 分類）
- 再現方法（bash 手順）
- 結果（eval 5-run 集計、Welch t、pooled 170-run、34-session peak 頻度、mode 分類 34-session）
- **未検証事項** セクション（S33 レポートの構造を継承、今回 [x] で完了した項目を反映、S34 新規発見を追記）
- **検証完了後に実施すべき TODO** セクション（S33 踏襲 + 本 Phase 追加）
- 結論

## 想定される主な分析観点（S34）

- **mode 分類 34-session**: mode_F 2 例目 or 1 例止まり。A/B/C/D/E/F 分布変化
- **ub=1586**: 3 連続崩壊 → 新類型 / 回復 → 2 連続崩壊限定確定
- **ub=1664**: 中帯 4 連続 or 他帯 jump
- **ub=1584**: 8-session pattern extension
- **A/B タイ**: 3 連続 → 4 連続 or tie break
- **σ_pool**: 1586 3 連続 1 位 or 順位変動
- **pooled 170-run**: σ_pool 170-run 再計算、pool 差 1586-1584 の収束速度（+0.02 以下到達可否）
- **Welch t (prior 33-session pool=165-run vs S34=5-run)**: 5 subtype 目出現可否
- **3 ub 全 σ_pool 縮小**: 3 例目 interval
- **cool time sub-zone**: S34 の cool time 測定、zone 3 連続判定

## 検証方法（成否確認）

- 3 条件すべてで llama-server 起動成功（startup_logs/ に health OK 記録）
- 各条件 eval 5 run で predicted_n=256 完走
- `summary_phaseSeval34s.tsv` に warmup 2 + eval 5 = 7 行 × 3 ub = 21 行（tag 列で区別）
- `phaseSeval34s_stats.csv` に 3 ub の 5-run 集計、pooled 170-run 統計、Welch t 出力
- `phaseSeval34s_verdict.txt` に 34-session peak 順位 / mode 分類 / 崩壊頻度
- compute buffer 34 session 連続完全一致確認
- GPU ロックが `unlock.sh` で正常解放（exit 0）
- REPORT.md インデックスに S34 エントリ追加確認

## 参照

- 直前レポート: [2026-04-21_102734_qwen3-122b-c3-phaseSeval33s.md](/home/ubuntu/projects/llm-server-ops/report/2026-04-21_102734_qwen3-122b-c3-phaseSeval33s.md)
- S33 attachment: `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-21_102734_qwen3-122b-c3-phaseSeval33s/`
- REPORT.md フォーマット: [/home/ubuntu/projects/llm-server-ops/REPORT.md](/home/ubuntu/projects/llm-server-ops/REPORT.md)
- gpu-server skill: `.claude/skills/gpu-server/`
- llama-server skill: `.claude/skills/llama-server/`
