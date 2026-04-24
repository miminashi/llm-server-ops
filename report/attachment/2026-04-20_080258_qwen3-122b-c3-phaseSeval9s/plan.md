# Phase S-eval-9session 実施計画

## Context

直前レポート [2026-04-20_075044_qwen3-122b-c3-phaseSeval8s.md](../../projects/llm-server-ops/report/2026-04-20_075044_qwen3-122b-c3-phaseSeval8s.md) の未検証事項のうち、★最優先項目を同時に潰せる「Phase S-eval-9session」を実施する。

n=8 までで以下の重要発見があり、いずれも n=9 での再現/反証が必要:

1. **ub=1664 の「3 帯分布型」仮説**（下 14.59-14.74 4/8、中 15.04-15.14 2/8、上 15.29-15.38 2/8）の再確認
2. **S8 で出現した新 peak order mode D (1664, 1586, 1584) の再現性** — 可能 6 順序中 4 種既観測、残 2 種（(1584,1664,1586) / (1586,1664,1584)）出現可能性
3. **ub=1586 bouncing 振幅減衰**（0.594 → 0.407 → 0.139）の継続
4. **ub=1584 安定性**（崩壊 S4 のみ、Δ は小振幅）
5. **warmup1 absolute 帯数の漸近**（現在 4 帯、n=10-15 で飽和期待）
6. **ub=1664 warmup=eval 現象**（S8 spike session 特異か）
7. **pooled σ の n=40→45 挙動**（ub=1664 は S8 で σ_pool +14.1% 拡大、拡大継続か）

S1-S8 は当日 2026-04-20 00:35-07:49 の 7h14m 内で実施済（intra-day 8 連続）。S9 を追加することで n=45 pool、9 セッション分の独立確認、peak order 5 種目の可能性検証が可能。作業時間は前 Phase と同等の 40-45 分を見込む。

## 優先度付け

本 Phase は以下の ★最優先（未検証事項セクション）を一度に前進させる:

| 項目 | S9 での前進 |
|---|---|
| ub=1664 3 帯分布の確定 | S9 ub=1664 mean が下/中/上どこに落ちるか確認、n=9 で Wilson CI 再計算 |
| S8 mode D の再現性 | S9 peak order が mode D か新 5 種目か旧 A-C か |
| ub=1586 bouncing 減衰モデル確定 | 振幅 0.139 → S9 で維持/縮小か |
| warmup1 absolute 帯数の漸近 | 5 帯目出現 or 4 帯維持 |
| ub=1664 warmup=eval 現象 | S9 ub=1664 が spike なら再現確認、baseline なら Δ>0 復帰確認 |
| pooled σ の n=40→45 挙動 | ub=1664 σ_pool 拡大継続か反転縮小か |
| ub 別独立変動モデルの再補強 | 3 ub 最近接モードが S7/S8 と異なる分布か |

## 実行プラン

### Phase 1: 準備（作業ディレクトリ作成）

新規添付ディレクトリを作成しスクリプトをコピーする。現在日時 (JST) を取得しレポートファイル名を確定。

```bash
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)  # 例: 2026-04-20_080xxx
REPORT_NAME="${TS}_qwen3-122b-c3-phaseSeval9s"
ATTACH_DIR="report/attachment/${REPORT_NAME}"

mkdir -p "$ATTACH_DIR/startup_logs"
mkdir -p "$ATTACH_DIR/prompts"

# スクリプトコピー（8s をベースに 9s へ rename）
SRC=report/attachment/2026-04-20_075044_qwen3-122b-c3-phaseSeval8s

# prompt_1k.txt は同一ファイルを利用
cp "$SRC/prompts/prompt_1k.txt" "$ATTACH_DIR/prompts/"

# 主要スクリプト: 8s → 9s 置換
for f in start_phaseSeval8s.sh batch_phaseSeval8s.sh run_all.sh measure_phaseI.sh; do
  dst=$(echo "$f" | sed 's/8s/9s/g')
  sed -e 's/Seval8s/Seval9s/g' \
      -e 's/phaseSeval8s/phaseSeval9s/g' \
      -e 's/8session/9session/g' \
      -e 's/S1+S2+S3+S4+S5+S6+S7/S1+S2+S3+S4+S5+S6+S7+S8/g' \
      "$SRC/$f" > "$ATTACH_DIR/$dst"
  chmod --reference="$SRC/$f" "$ATTACH_DIR/$dst"
done

# analyze スクリプト: PRIOR_TSVS に S8 を追加
cp "$SRC/analyze_phaseSeval8s.py" "$ATTACH_DIR/analyze_phaseSeval9s.py"
# PRIOR_TSVS への S8 エントリ追加は Edit で行う（手動）
```

**analyze_phaseSeval9s.py の修正点**:
- `PRIOR_TSVS` リストに S8 エントリ `("S8_phaseSeval8s", SCRIPT_DIR.parent / "2026-04-20_075044_qwen3-122b-c3-phaseSeval8s" / "summary_phaseSeval8s.tsv")` を追加
- `CUR_SESSION_LABEL = "S9_phaseSeval9s"`
- `TAG_PREFIX = "Seval9s_fa1_ctx"`
- `MODE_GROUPS` に `"prev_S8": ["S8_phaseSeval8s"]` と `"cur_S9": ["S9_phaseSeval9s"]` を追加
- コメント/docstring の n=8 → n=9、40-run → 45-run 更新

### Phase 2: GPU ロック取得と実行

```bash
# GPU ロック取得
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 既存 llama-server 停止（他セッションの残骸除去）
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100 || true

# 作業ディレクトリへ移動
cd "$ATTACH_DIR"

# バッチ実行（3 条件 × (warmup 2 + eval 5)、所要約 37 分）
bash batch_phaseSeval9s.sh > batch_phaseSeval9s.log 2>&1

# 分析
python3 analyze_phaseSeval9s.py
```

計測条件（前 8 phase と完全同一、変更禁止）:
- GPU: t120h-p100 (10.1.4.14)、NVIDIA Tesla P100-PCIE-16GB × 4
- モデル: Qwen3.5-122B-A10B-Q4_K_M (unsloth snapshot)
- fa=1、f16 KV、ctx=32768、`numactl --cpunodebind=1 --membind=1`、threads=40、poll=0、ngl=999
- OT_REGEX: `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
- ub ∈ {1584, 1586, 1664}
- prompt: prompt_1k.txt (1084 tokens) + `[Request ID <uniq>] ` prefix（cache hit 回避）
- max_tokens=256、cooldown 60s、warmup 2 run（短 prompt）+ eval 5 run

### Phase 3: レポート作成

ファイル名: `report/${REPORT_NAME}.md`

**必須セクション**:
1. タイトル（日本語）: Qwen3.5-122B-A10B C-3 Phase S-eval-9session（n=9 の 3 ub × 5 run、第 9 セッション追加、3 帯分布 / mode D 再現性検証）
2. 実施日時（JST）、作業種別、GPU ロック状態
3. 添付ファイル（plan.md、各スクリプト、ログ、TSV、stats CSV、verdict、startup_logs、out_Seval9s_* ディレクトリ、prompts）
4. 参照（直前レポート = phaseSeval8s、S1-S8 すべて）
5. 前提・目的（S8 発見の再検証狙い）
6. 環境情報（ctx=32768 × fa=1 × OT=MoE-only、前 Phase と完全同一）
7. 再現方法
8. 実行結果サマリ
   - 本 Phase (S9) eval 5-run ピボット
   - warmup 2-run
   - 9 session mean 時系列（range / mean_of_9 / σ_session / verdict）
   - ピーク順序 9-session 安定性（mode E 出現か確認）
   - ub=1664 時系列パターン（符号/単調性）
   - ub=1586 時系列パターン
   - ub=1584 時系列パターン
   - Prior 8-session pool vs S9 Welch t
   - モード分類比較 (mode A/B/C/D/S7/S8/S9)
   - Pooled 45-run 統計（σ_pool/σ_run_avg 倍率更新）
   - 崩壊頻度（ub 別 Wilson 95% CI）
   - ub 間有意差
   - 起動 compute buffer（9 session 完全一致再確認）
   - prompt_tps（参考）
9. 再現性分析と解釈（S9 結果に応じて動的に）
10. 採用判定（pooled 45-run ベースの推奨 ub 更新）
11. **未検証事項**（直前レポートから継承、本 Phase で潰した項目に [x]、新規項目追加）
12. **検証完了後に実施すべき TODO**（直前レポートから継承、本 Phase 発見を追加）
13. 補足（核心発見サマリ、前 Phase との対照表、作業終了時点の状態）

### Phase 4: 後処理

```bash
# llama-server 停止
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100

# GPU ロック解放
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100

# プランファイルを attachment にコピー（REPORT.md 必須手順）
cp /home/ubuntu/.claude/plans/todo-radiant-tiger.md "$ATTACH_DIR/plan.md"

# REPORT.md の更新は原則不要（レポート追加のみ）
```

## 修正対象ファイル（新規作成）

全て `report/attachment/${REPORT_NAME}/` 配下:

- `plan.md` (本計画をコピー)
- `prompts/prompt_1k.txt` (既存から copy)
- `start_phaseSeval9s.sh` (8s → 9s 置換)
- `batch_phaseSeval9s.sh` (8s → 9s 置換)
- `run_all.sh` (8s → 9s 置換)
- `measure_phaseI.sh` (8s から copy、ほぼ変更なし)
- `analyze_phaseSeval9s.py` (8s から copy、PRIOR_TSVS に S8 追加、CUR_SESSION_LABEL 更新)

実行成果物:
- `batch_phaseSeval9s.log`
- `startup_logs/fa1_ctx32768_b{UB}_ub{UB}.log` × 3
- `out_Seval9s_fa1_ctx32768_ub{UB}_{warmup,1k}/` × 6 ディレクトリ
- `summary_phaseSeval9s.tsv`
- `phaseSeval9s_stats.csv`
- `phaseSeval9s_verdict.txt`
- `run_Seval9s_ctx32768_ub{UB}.log` / `run_all_Seval9s_*.log` × 各 3
- `start_stdout_Seval9s_ctx32768_ub{UB}.log` × 3

レポート本体:
- `report/${REPORT_NAME}.md` (新規)

## 再利用する既存ユーティリティ

- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh` (ロック管理)
- `.claude/skills/llama-server/scripts/stop.sh` (サーバ停止)
- `report/attachment/2026-04-20_075044_qwen3-122b-c3-phaseSeval8s/*` (スクリプト雛形)
- `summary_phaseSeval{1-8}s.tsv` 相当の 8 session TSV (prior pool 算出用)

## 検証方法（実行完了後の確認）

1. **起動成功確認**: 3 ub の `startup_logs/*.log` で `HTTP server is listening` と compute buffer MiB 一致確認
2. **計測完走確認**: 各 `out_Seval9s_*_1k/eval_run{1..5}.json` の `timings.predicted_n == 256` 全 15 件で確認
3. **TSV 行数確認**: `summary_phaseSeval9s.tsv` が少なくとも 21 行（warmup 6 + eval 15）
4. **verdict 出力確認**: `phaseSeval9s_verdict.txt` に 9-session verdict、peak order、pooled 45-run 統計が揃う
5. **レポート内整合**: S1-S8 の値が直前レポートと完全一致（改ざんなし）、S9 新値が summary TSV と一致

## 想定リスク / 対処

| リスク | 対処 |
|---|---|
| GPU ロックが他セッションで取得中 | `lock.sh` が失敗したら待機、15 分で解放されない場合は作業中止 |
| 起動タイムアウト（/health 300s） | `start_phaseSeval9s.sh` が `exit 1` で中断、`startup_logs` で原因特定 |
| OOM または `-ub` 拒否 | スクリプトが `exit 2/3` で中断、前 8 session では発生実績ゼロなので低確率 |
| eval run 失敗 | `run_all.sh` / `measure_phaseI.sh` が個別 json を出力、不完全な場合 analyze で警告 |
| S9 結果が前 8 session と大きく逸脱（全 ub 崩壊など） | 発生時は追加 session 候補から外し、即時原因調査（OS 状態、他負荷、温度）に切替 |
