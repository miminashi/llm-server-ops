# Phase S-eval-27session 実施プラン

## Context

直前レポート [2026-04-21_041752_qwen3-122b-c3-phaseSeval26s.md](/home/ubuntu/projects/llm-server-ops/report/2026-04-21_041752_qwen3-122b-c3-phaseSeval26s.md) の **★最重要 TODO「Phase S-eval-27session 候補」** を実施する。同レポートの「未検証事項」 ★最優先 5 項目を **単一セッション 1 回で同時検証できる唯一の最上位タスク**であり、所要 37-40 分で全項目が更新される：

1. **ub=1584 alternating 5-hop 崩壊 → S27 で 6-hop 継続検証** — S22-S26 で「崩壊/非/崩壊/非/崩壊」5-hop、S27 で 非崩壊なら 6-hop 完全周期性、崩壊なら 2 連続崩壊で alternating break
2. **ub=1586 recovery 4 連続後の 15.3+ 帯 stepwise climb 可否** — 4 連続 non-崩壊 15.133/15.261/15.152/**15.319**、15.4+ 復帰なら stepwise climb 類型確定
3. **ub=1664 下→上ジャンプ後の上帯 stay 可否** — S24/S25 下帯 2 連続 → S26 上帯 15.209 ジャンプ、S27 上帯 stay なら「下→上→上 2-hop」新類型
4. **mode_E 連続化可否 + E/A/B trimodal regime 検証** — E 4/26=15.4%（3 位確定）、S27 で 再 E なら E 連続化（26-session 初）、A/B なら trimodal regime
5. **σ_pool regime change 5 連続 → S27 6 連続 or 解消検証** — 1586>1584 が 5 連続（逆転幅 0.009→0.012 拡大）、6 連続で regime change 強化 phase 確定

加えて cool time 16-17 分 sub-zone 線形 fit 精緻化、Welch 3 ub sig sign pattern カタログ化、ub=1664 帯遷移行列、within-σ 低位回帰も同時に進展する。

## 現状確認（2026-04-21 05:07 JST 時点）

- S26 終了: 2026-04-21 04:57:13 JST
- 現在時刻: ~05:08 JST、**cool time 既に ~11 分**
- t120h-p100: **available**（ロック取得可）
- S27 開始タイミング: 準備 2-3 分後 → cool time ~13-14 分 → **通常帯 13-16 分 sub-zone** 予想

## 実施方針（S26 と完全同条件を再実行）

- **GPU サーバ**: t120h-p100（ロック取得必須）
- **条件**: fa=1 × OT=MoE-only × ctx=32768 × ub ∈ {1584, 1586, 1664}、各 warmup 2 + eval 5 run
- **prompt**: Sbfine3 以降と同一 prompt_1k.txt（1086 tokens）
- **cooldown**: run 間 60s、ub 切替時は stop + sleep 5s
- **所要見込み**: 37-40 分（S26 実績 36'49"）

## 再利用する既存資産（S26 からコピーして 26s → 27s 書き換え）

すべて S26 attachment (`report/attachment/2026-04-21_041752_qwen3-122b-c3-phaseSeval26s/`) から：

- `start_phaseSeval26s.sh` → `start_phaseSeval27s.sh`
- `batch_phaseSeval26s.sh` → `batch_phaseSeval27s.sh`
- `run_all.sh`（変更不要、TAG_PREFIX 経由）
- `measure_phaseI.sh`（変更不要）
- `prompts/prompt_1k.txt`（変更不要）
- `analyze_phaseSeval26s.py` → `analyze_phaseSeval27s.py`（n=27 対応、S1-S26 map に S27 追加）

他リポ資産：
- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- `.claude/skills/llama-server/scripts/stop.sh`（batch 内）

## 手順

### Step 1: 作業ディレクトリ準備
- タイムスタンプ `<TS>` は S27 作業開始時点で確定
- `report/attachment/<TS>_qwen3-122b-c3-phaseSeval27s/` を作成
- S26 から一式 cp し、`26s` → `27s`、日付 prefix を sed 置換

### Step 2: GPU ロック取得
- `bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100`

### Step 3: バッチ実行
- `HOST=t120h-p100 bash batch_phaseSeval27s.sh > batch_phaseSeval27s.log 2>&1`
- 終了後 `summary_phaseSeval27s.tsv` が 21 行生成されること確認

### Step 4: 27-session 統計解析
- `analyze_phaseSeval27s.py` 実行、以下を CSV/verdict に出力：
  - S1-S27 pooled 135-run mean/σ_pool/range
  - 崩壊頻度（3 ub、S27 加味）
  - mode 分類（A/B/C/D/E/F のピーク順序）
  - Welch t-test（prior 26-session pool vs S27）
  - σ_pool 1584/1586 逆転 6 連続判定
  - ub=1664 帯分類（下 < 14.80 / 中 14.80-15.20 / 上 > 15.20）と遷移
  - ub=1584 alternating 崩壊 6-hop 判定
  - ub=1586 recovery 連続カウント（5 連続可否）
  - cool time（S26 終了 → S27 開始）記録

### Step 5: GPU ロック解放
- `bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100`

### Step 6: レポート作成
- `report/<TS>_qwen3-122b-c3-phaseSeval27s.md` を作成、必須セクション：
  - 添付ファイル一覧
  - 参照（S26・S25・S24・S23・S22・S1・過去 1-run 参照値）
  - 前提・目的
  - 判定しきい値・成功条件（★最優先 5 項目を明示）
  - 環境情報
  - セッション間隔（cool time）
  - 結果（3 ub × 7 run の eval_tps、pooled 135-run 統計、多大事件 per-topic 観察）
  - **未検証事項** セクション（S26 踏襲の既知項目 + 本 Phase 新規）
  - **検証完了後に実施すべき TODO** セクション（S26 踏襲 + 本 Phase 新規、S-eval-28session を含む）
- `REPORT.md` に index エントリ追加

## 検証（end-to-end）

- [ ] `batch_phaseSeval27s.log` に 3 条件 × "measure done" が 3 行
- [ ] `summary_phaseSeval27s.tsv` が 21 行（warmup 6 + 1k 15）
- [ ] `phaseSeval27s_stats.csv` が 3 ub 行
- [ ] `phaseSeval27s_verdict.txt` に崩壊/mode/Welch/σ_pool regime/帯判定の各結論
- [ ] GPU ロックが最終的に解放（`lock-status.sh` で確認）
- [ ] レポート md が S26 と同フォーマットで「未検証事項」「検証完了後に実施すべき TODO」両セクションを持つ

## 重要ファイル（作成/参照）

### 作成
- `report/<TS>_qwen3-122b-c3-phaseSeval27s.md`
- `report/attachment/<TS>_qwen3-122b-c3-phaseSeval27s/` 一式
- `REPORT.md`（index 追記）

### 参照のみ
- `report/attachment/2026-04-21_041752_qwen3-122b-c3-phaseSeval26s/` 以下（コピー元）
- `.claude/skills/gpu-server/scripts/lock.sh`, `unlock.sh`, `lock-status.sh`
- `.claude/skills/llama-server/scripts/stop.sh`
- `CLAUDE.md`（遵守）
- `REPORT.md`（フォーマット遵守）

## リスク・留意事項

- S27 開始タイミングが当初予想より遅延し cool time が 17+ 分（境界帯）に入った場合でも、そのまま実行し verdict に zone を明記（過去 S22/S23 の境界帯データと比較可）
- 起動失敗（OOM/ub reject）時は `start_phaseSeval27s.sh` が exit 2/3 で abort、batch ログで検出
- バッチ途中障害時は異常 ub のみ `run_all.sh` で再実行可能だが、session 連続性維持のため原則 1 回完遂
- 解析スクリプトの S1-S26 map には S26 の 3 ub mean 値（14.830/15.319/15.209）を追加する必要あり — S26 の `summary_phaseSeval26s.tsv` から確認して map に組み込む
