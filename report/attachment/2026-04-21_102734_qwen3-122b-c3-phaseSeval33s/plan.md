# Phase S-eval-33session 実施プラン

## Context

直前レポート [`report/2026-04-21_093107_qwen3-122b-c3-phaseSeval32s.md`](../../projects/llm-server-ops/report/2026-04-21_093107_qwen3-122b-c3-phaseSeval32s.md) の「未検証事項」および「検証完了後に実施すべき TODO」の ★最優先項目は、ほぼすべて **Phase S-eval-33session (S33)** の実施で同時検証可能である。

S32 で観測された 17 大事件（double collapse (1584/1586) 3 例目、cool time 境界帯 18+ 分 sub-zone 初観測、ub=1584「非3+崩+回+崩」6-session pattern、ub=1586 alternating 5-session pattern 確立、ub=1664 中帯 stay 2 連続 + 崩壊 50.0% exact、mode_C 単独 3 位昇格、A=B=10/32 同率タイ 2 連続、Welch mixed subtype (-/-/+) 初、|t|=27.69 歴代 2 位、σ_pool 1586 1 位奪還 + regime change 11 連続、within-σ 低位 9 連続）の後続動向を、S32 と同条件で第 33 セッションを取得し pooled 165-run 統計として確定する。

S32 レポートの ★最優先 未検証項目:

1. **double collapse (1584/1586) 3 例目 → S33 の 4 例目 interval**（S17→S22=5、S22→S32=10 で延長 trend）
2. **ub=1586 alternating 5-session → S33 6-session 可否**（S33 崩壊なら 2 連続崩壊で alternating break、非崩壊なら 6-session alternating 新記録）
3. **ub=1584「非3+崩+回+崩」6-session pattern 後 → S33 動向**（S33 崩壊なら 2 連続崩壊新類型、非崩壊なら「崩壊-回復 2 cycle」類似 regime）
4. **A=B=10/32 同率 1 位タイ 2 連続 → S33 3 連続可否**（mode_A なら A=11/33 単独 / mode_B なら B=11/33 単独 / 他 mode なら A=B タイ 3 連続 32-session 0 例の初）
5. **mode_C 5 例単独 3 位昇格 → S33 動向**（mode_C 連続化は 32-session 0 例、S33 mode_C なら連続化初）
6. **σ_pool 1586 1 位奪還 → S33 2 連続可否**（1586 1 位継続 or 1664 復位 or 1584 新 1 位）
7. **Welch mixed subtype (-/-/+) 初 → S33 再現頻度**（S30/S31/S32 で全負/全正/mixed 連続、S33 で 4 subtype 目 or 既観測 subtype 再現）
8. **|t_welch|>25 2 例 (S30/S32) → S33 再現**（S33 |t|>25 なら 3 連続近接、|t|<25 なら 2 例止まり）
9. **triple collapse 2 例目 interval**（32-session 1 例 S30 のまま、S33 以降観測）
10. **cool time 4 sub-zone 分類確立後の S33 動向**（S33 cool time が境界帯 18+ 分再観測 / 通常帯 13-16 / 境界帯直前 16-18 のどれか）

同時に ★高優先 項目（ub=1664 中帯 stay 3 連続、ub=1586 崩壊 interval 2 連続後、pool 差 +0.05 割れ後の収束 or 再拡大、σ_pool 1586 拡大 +0.018 の継続、|Δ_max| 担当 同率 5/11 タイ更新 等）も 1 回の実行で同時更新する。

これら ★最優先 10 項目 + ★高優先 項目を 1 回のバッチ実行（約 37-40 分）で同時検証する。pooled 165-run 統計（33 session × 5 run）に拡張し、33-session range / σ_session / Welch t（prior 32-session pool vs S33）、mode 分類、崩壊頻度 Wilson 95% CI を更新する。

## 実施内容

### 1. 添付ディレクトリ・スクリプト準備

新規 attachment ディレクトリ: `report/attachment/<新タイムスタンプ>_qwen3-122b-c3-phaseSeval33s/`（タイムスタンプはバッチ開始時刻）

S32 の attachment を雛形にコピーし、ファイル名・変数名・REMOTE_LOG prefix を `32s → 33s` に置換:

- `start_phaseSeval32s.sh` → `start_phaseSeval33s.sh`
- `batch_phaseSeval32s.sh` → `batch_phaseSeval33s.sh`
- `run_all.sh`（変更なしでコピー）
- `measure_phaseI.sh`（変更なしでコピー）
- `analyze_phaseSeval32s.py` → `analyze_phaseSeval33s.py`
- `prompts/prompt_1k.txt`（変更なしでコピー）

`analyze_phaseSeval33s.py` の修正:
- `PRIOR_TSVS` リストに S32 エントリを追加:
  ```python
  ("S32_phaseSeval32s",
   SCRIPT_DIR.parent / "2026-04-21_093107_qwen3-122b-c3-phaseSeval32s" / "summary_phaseSeval32s.tsv"),
  ```
- `CUR_SESSION_LABEL` を `"S33_phaseSeval33s"` に更新
- `MODE_GROUPS` に `"prev_S32": ["S32_phaseSeval32s"]` 追加、`"cur_S33": ["S33_phaseSeval33s"]` に更新
- 集計ラベル「32-session」「pooled 160-run」→「33-session」「pooled 165-run」へ更新

`startup_logs/`, `out_Seval33s_*` ディレクトリを作成。

### 2. GPU ロック取得

```bash
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

※ 現在 (2026-04-21 10:25 JST) GPU は available。

### 3. バッチ実行

```bash
cd report/attachment/<新タイムスタンプ>_qwen3-122b-c3-phaseSeval33s
HOST=t120h-p100 bash batch_phaseSeval33s.sh > batch_phaseSeval33s.log 2>&1
```

- ub={1584, 1586, 1664} × warmup 2 run + 1k eval 5 run
- 各条件で `llama-server` 起動 → `/health` 確認 → warmup → eval → `stop.sh` の標準フロー（S32 と完全同一）
- 起動パラメータ: fa=1、f16/f16 KV、ctx=32768、`numactl --cpunodebind=1 --membind=1`、threads=40、poll=0、ngl=999、`OT_REGEX` 同一
- 所要時間: 約 37-40 分

### 4. 集計・analyze スクリプト実行

```bash
python3 analyze_phaseSeval33s.py
```

出力:
- `summary_phaseSeval33s.tsv`: 3 ub × (warmup 2 + eval 5) の raw 記録
- `phaseSeval33s_stats.csv`: 33-session 集計（mean / σ_session / min / max / median / range）
- `phaseSeval33s_verdict.txt`: verdict / Welch / mode / 崩壊頻度 Wilson 95% CI
- pooled 165-run 統計（mean / σ_pool / min / max / median / range）
- Welch t（prior 32-session pool vs S33）
- 33-session mode 分類 + σ_pool regime change 判定

### 5. GPU ロック解放

```bash
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 6. レポート作成

ファイル名: `report/<タイムスタンプ>_qwen3-122b-c3-phaseSeval33s.md`

S32 レポートのフォーマットを踏襲し、以下を含める:

- 冒頭タイトル（S33 結果サマリを含む長文タイトル、★最優先 10 項目の検証結果を網羅）
- 添付ファイル・参照リスト（S17/S22/S28/S29/S30/S31/S32 へのリンク）
- 前提・目的（S32 の ★最優先 TODO 群を列挙）
- 判定しきい値・成功条件
- 環境情報・セッション間隔（S32 終了時刻 2026-04-21 10:12:00 JST と S33 開始時刻から cool time 算出、4 sub-zone 分類）
- 再現方法
- 結果（本 Phase eval、Welch t、pooled 165-run、33-session peak order、mode 分類）
- **「未検証事項」セクション**（S32 の該当セクションを基に更新、★最優先 10 項目について S33 結果で `[x]` マーク、新規 ★最優先項目を S34 向けに追加）
- **「検証完了後に実施すべき TODO」セクション**（Phase S-eval-34session 候補 等、新規項目を追加）
- 結論

## 重要な判断基準

- **崩壊判定**: eval_mean < 15.0 t/s（3 ub 共通）
- **ub=1664 帯分類**: 下帯 < 14.80、中帯 14.80-15.20、上帯 > 15.20
- **triple collapse 判定**: 3 ub 同時崩壊（全て eval_mean < 15.0）
- **double collapse (1584/1586)**: ub=1584 + ub=1586 同時崩壊、ub=1664 normal
- **cool time 4 sub-zone 分類**: <13 分 / 通常帯 13-16 分 / 境界帯直前 16-18 分 / 境界帯 18+ 分
- **σ_pool regime**: 1586 > 1584 は S22-S32 で 11 連続（S33 継続なら 12 連続最長更新）、1664 1 位は S30-S31 の 2 連続限定（S32 で break 済）
- **mode 分類**: A (1584,1586,1664) / B (1586,1584,1664) / C (1664,1584,1586) / D (1664,1586,1584) / E (1586,1664,1584) / F (1584,1664,1586)
- **32-session 現状**: A=B=10/32=31.3% タイ 1 位、C=5/32=15.6% 単独 3 位、E=4/32=12.5%、D=3/32=9.4%、F=0

## 修正対象ファイル（重要パス）

- `/home/ubuntu/projects/llm-server-ops/report/<新レポート名>.md`（新規作成）
- `/home/ubuntu/projects/llm-server-ops/report/attachment/<新タイムスタンプ>_qwen3-122b-c3-phaseSeval33s/`（新規作成、S32 attachment 流用）

## 参照する既存ファイル

- **S32 雛形**: `report/attachment/2026-04-21_093107_qwen3-122b-c3-phaseSeval32s/`（全スクリプト・プロンプト流用）
- **GPU ロック**: `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh` / `lock-status.sh`
- **llama-server 停止**: `.claude/skills/llama-server/scripts/stop.sh`
- **プロンプト**: S32 `prompts/prompt_1k.txt`（Phase Sbfine3 と同一、6200 bytes、prompt_n=1086 tokens）
- **レポートフォーマット**: [`REPORT.md`](../../projects/llm-server-ops/REPORT.md)

## 検証方法（end-to-end）

1. 3 条件すべて起動成功（/health OK）
2. 各条件で eval_tps 5 値取得完了
3. `summary_phaseSeval33s.tsv` に 3 ub × 5 run の 15 行 + warmup 行が記録される
4. `phaseSeval33s_stats.csv` に 33-session 集計行が 3 ub 分出力される
5. `phaseSeval33s_verdict.txt` に verdict / Welch / mode / 崩壊頻度 が記録される
6. pool_n=165（33 session × 5 run）、33-session mode 分類・σ_pool regime の更新確認
7. GPU ロック解放の正常動作
8. レポート末尾に「未検証事項」「検証完了後に実施すべき TODO」の 2 セクションが存在

## 想定所要時間

- 準備（attachment ディレクトリ作成・スクリプトコピー・編集）: 5 分
- GPU ロック取得: 1 分
- バッチ実行（3 条件 × 約 12 分）: 37-40 分
- analyze 実行: 1 分
- GPU ロック解放: 1 分
- レポート作成: 15-20 分
- **合計**: 約 60-70 分
