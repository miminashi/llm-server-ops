# Phase S-eval-39session 実施計画

## Context

直前レポート `report/2026-04-21_145730_qwen3-122b-c3-phaseSeval38s.md`（S38）の「未検証事項」セクションに並ぶ ★最優先 項目は、**同条件で第 39 セッション (S39) を 1 回実行すれば 10+ 個を一気にバッチ検証できる**構造になっている。具体的には:

- mode_D 4 例目 initial → S39 で mode 分岐 or 継続
- ub=1664 上帯 2 連続 → S39 で 3 連続可否（38-session 0 例）
- ub=1664 pool max 15.534 → S39 更新 or 維持
- ub=1586 回復 4 連続 → S39 で 5 連続可否（38-session 0 例）
- A=B タイ 8 連続 → S39 で 9 連続可否（38-session 0 例）
- σ_pool 1664 1 位復帰 → S39 継続 or 1586 奪還
- Welch (not_sig/+/+) 新 subtype → S39 再現 or shift
- pool 差 +0.05-+0.06 安定帯 3 連続 → S39 で 4 連続定着可否
- ub=1664 3 冠 initial → S39 で 2 連続可否（mode_D 物理確定候補昇格条件）
- ub=1664 peak 1 位復活 → S39 で 2 連続可否

これらはすべて「ctx=32768 × fa=1 × OT=MoE-only 固定 × ub ∈ {1584, 1586, 1664} × warmup 2 + eval 5 run」という 38 session 完全同一のプロトコルで計測すれば自動的に取得できる。S38 直前レポートの「検証完了後に実施すべき TODO」でも★最優先トップ項目として「Phase S-eval-39session 候補」が明記されている。

所要は 37-40 分（GPU ロック保持時間 + 集計 + プロット + レポート作成で合計 1 時間程度）。

## 実施手順

### Step 1: タイムスタンプ確定 & GPU ロック取得

```bash
TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S   # レポートファイル名用タイムスタンプ
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

- 確保したタイムスタンプを `TS` 変数として保持（例: `2026-04-21_165000`）
- レポート名（ケバブケース）: `qwen3-122b-c3-phaseSeval39s`
- attachment ディレクトリ名: `${TS}_qwen3-122b-c3-phaseSeval39s`

### Step 2: attachment ディレクトリ作成 & スクリプトコピー

`report/attachment/${TS}_qwen3-122b-c3-phaseSeval39s/` を作成し、S38 の attachment から以下をコピー・改名:

| S38 コピー元 | S39 コピー先 | 改変内容 |
|---|---|---|
| `start_phaseSeval38s.sh` | `start_phaseSeval39s.sh` | `38`→`39` 全置換（シェル変数・ログ名） |
| `batch_phaseSeval38s.sh` | `batch_phaseSeval39s.sh` | `38`→`39` 全置換（TAG_PREFIX, log出力, out ディレクトリ名, start/analyze スクリプト参照） |
| `run_all.sh` | `run_all.sh` | 無改変コピー |
| `measure_phaseI.sh` | `measure_phaseI.sh` | 無改変コピー |
| `prompts/prompt_1k.txt` | `prompts/prompt_1k.txt` | 無改変コピー |
| `analyze_phaseSeval38s.py` | `analyze_phaseSeval39s.py` | (a) `CUR_SESSION_LABEL` を `S39_phaseSeval39s` に、(b) `PRIOR_TSVS` リスト末尾に S38 の tsv エントリを追加、(c) 出力ファイル名 `phaseSeval38s_*` → `phaseSeval39s_*`、(d) 38-session → 39-session / prior 37 → prior 38 の文言更新 |
| `plot_timeseries.py` | `plot_timeseries.py` | S39 を読む点追加（`SESSIONS` リストに S39 を追加）+ 出力ファイル名維持で `timeseries_eval_tps.png` 再生成 |
| プラン添付 (新規) | `plan.md` | `cp /home/ubuntu/.claude/plans/todo-luminous-chipmunk.md plan.md` |

### Step 3: バッチ実行（37-40 分）

```bash
cd report/attachment/${TS}_qwen3-122b-c3-phaseSeval39s
HOST=t120h-p100 bash batch_phaseSeval39s.sh > batch_phaseSeval39s.log 2>&1
```

- 3 条件（ub=1584 / 1586 / 1664）× (warmup 2 + eval 5) = 21 run 総計
- 各 run max_tokens=256、cooldown 60s、CTX=32768、FA=1、threads=40、poll=0、numactl cpubind=membind=node1、OT=MoE-only
- `run_in_background` で実行し、完了待ち中は他作業禁止（GPU ロック保持中）
- 完了後 `summary_phaseSeval39s.tsv` が生成されていることを確認

### Step 4: 統計集計 & 時系列プロット

```bash
python3 analyze_phaseSeval39s.py   # phaseSeval39s_stats.csv / verdict.txt / pool 190+5=195-run 統計
python3 plot_timeseries.py         # timeseries_eval_tps.png 更新（S1-S39）
```

### Step 5: レポート作成

`report/${TS}_qwen3-122b-c3-phaseSeval39s.md` を作成。S38 レポートをテンプレートに以下を記載:

#### 必須セクション
1. タイトル: `# Qwen3.5-122B-A10B C-3 Phase S-eval-39session`
2. 実施日時・作業種別・GPU ロック状況
3. `## 添付ファイル`（plan.md、各スクリプト、tsv/csv、プロット PNG を全列挙）
4. `## 参照`（直前 S38 + 節目 S27/S30/S32/S35/S38 + Sbfine ref 3 件）
5. `## 前提・目的`（S38 ★最優先 TODO 10+ 項目のバッチ検証であることを明記）
6. `## 核心発見サマリ`（ub=1664 上帯 3 連続可否、mode 分岐、A=B タイ 9 連続可否、Welch subtype、pool max 更新、3 冠継続可否等を結果に応じて）
7. `## 時系列プロット`（画像埋込）
8. `## 判定しきい値` / `## 成功条件`
9. `## 環境情報`（S38 と完全同一明記）
10. `## 再現方法`
11. `## 結果（本 Phase eval フェーズ、5-run mean）`
12. `## Welch t（prior 38-session pool vs S39）`
13. `## Pooled 195-run 統計`
14. `## 39-session peak order 1 位頻度` / `## mode 分類 39-session`
15. **`## 未検証事項`** — 直前 S38 と同様、★最優先/高/中/低 でカテゴリ分け。S38 の既知項目で検証済になったものは除外、新規に S39 で発生した regime（例: ub=1664 上帯 N 連続、A=B タイ 9 連続等）を追加
16. **`## 検証完了後に実施すべき TODO`** — S38 と同様、Phase S-eval-40session 候補を★最優先の先頭に置く
17. `## 結論`

#### タイトル・命名の注意（feedback memory）
- レポートタイトルは簡潔に、発見ハイライトは「核心発見サマリ」セクションで表現（タイトルに詰め込まない）

### Step 6: GPU ロック解放 & REPORT.md 更新（不要。REPORT.md はルール定義ファイル）

```bash
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### Step 7: Discord 通知（ユーザが許可すれば）

ユーザ指示がなければ実施しない。明示依頼があった場合のみ:

```bash
bash .claude/skills/discord-notify/scripts/notify.sh "S39 完了要約" "report/${TS}_qwen3-122b-c3-phaseSeval39s.md"
```

## クリティカルファイル

### 既存（参照・流用元）
- `report/2026-04-21_145730_qwen3-122b-c3-phaseSeval38s.md` — 直前レポート
- `report/attachment/2026-04-21_145730_qwen3-122b-c3-phaseSeval38s/` — 流用元スクリプト群
- `report/attachment/2026-04-21_*_qwen3-122b-c3-phaseSeval*s/summary_phaseSeval*s.tsv` × 38 — pool 統計の prior セッション raw data
- `CLAUDE.md` / `REPORT.md` — レポート作成ルール
- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- `.claude/skills/discord-notify/scripts/notify.sh`

### 新規作成
- `report/${TS}_qwen3-122b-c3-phaseSeval39s.md`
- `report/attachment/${TS}_qwen3-122b-c3-phaseSeval39s/` 以下のスクリプト・ログ・PNG・tsv/csv 一式
- `report/attachment/${TS}_qwen3-122b-c3-phaseSeval39s/plan.md`（本プランファイルのコピー）

## 検証方法

1. **バッチ実行の成功確認**:
   - `batch_phaseSeval39s.log` に各条件の「llama-server 起動成功」「/health 200」「21 run 全完走」が記録されている
   - `summary_phaseSeval39s.tsv` に 3 ub × 5 eval = 15 行の eval データ + 3 ub × 2 warmup = 6 行の warmup データが揃っている
   - `out_Seval39s_fa1_ctx32768_ub{1584,1586,1664}_1k/` 各ディレクトリに `eval_run{1..5}.json` が完走（predicted_n=256）

2. **統計スクリプトの実行確認**:
   - `analyze_phaseSeval39s.py` が non-zero exit しない
   - pool n が 195（= 39 × 5）になっている
   - Welch t（prior 38-session pool n=190 vs S39 n=5）の出力行が 3 ub 分ある
   - `phaseSeval39s_verdict.txt` に 39-session range / σ_session / 崩壊頻度が含まれる

3. **時系列プロットの確認**:
   - `timeseries_eval_tps.png` が 38 session 分 + S39 が追加された状態で再生成されている
   - Sbfine ref 3 点（星型 marker）が描画されている

4. **レポートの完成度確認**:
   - 「未検証事項」「検証完了後に実施すべき TODO」両セクションが存在
   - S38 の ★最優先 TODO 10+ 項目が全て検証済（x）または継続（[ ]）として分類記載されている
   - 添付ファイルリンクが全て存在ファイルを指している

5. **GPU ロック解放確認**:
   - `ssh t120h-p100 "cat /tmp/gpu_lock_session 2>/dev/null || echo 'no lock'"` で no lock 状態に戻っている

## リスク・注意事項

- **OOM / ub-reject 検知**: start_phaseSeval39s.sh の startup 健全性チェックで OOM を検出したら該当 ub のみスキップし他 ub 継続。38 session で OOM 発生実績はなし（compute buffer 完全一致継続中）
- **cool time**: S38 終了時刻 = 2026-04-21 15:39:07 JST。S39 開始は現在時刻（Step 1 のタイムスタンプ）基準で自動算出 → cool time sub-zone を verdict に自動出力
- **feedback memory 準拠**:
  - Bash ツールでは for / $() / 複雑パイプを避け、Glob や事前変数展開で書き換え
  - レポートタイトルを簡潔にし、発見ハイライトは「核心発見サマリ」に集約
- **GPU ロック忘却防止**: バッチ実行完了後必ず unlock.sh を呼ぶ。途中でエラーが発生した場合も unlock してからユーザに報告
- **Plan mode 解除**: ExitPlanMode で承認を得てから実装フェーズに入る
