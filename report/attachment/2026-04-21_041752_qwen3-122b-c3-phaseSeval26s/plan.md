# Phase S-eval-26session 実施プラン

## Context

直前レポート [2026-04-21_032417_qwen3-122b-c3-phaseSeval25s.md](/home/ubuntu/projects/llm-server-ops/report/2026-04-21_032417_qwen3-122b-c3-phaseSeval25s.md) の **★最重要 TODO「Phase S-eval-26session 候補」** を実施する。同レポートの「未検証事項」★最優先 5 項目を単一セッションで同時検証できる唯一の最上位タスクであり、最優先着手に値する：

1. **A 単独 1 位 steady-state の S26+ 継続検証** — S25 A 9/25=36.0% vs B 8/25=32.0% 復帰
2. **ub=1664 下帯 3 連続 stay 可否 / 帯振動パターン** — S24/S25 下帯 2 連続
3. **ub=1584 alternating 2-hop 崩壊 5-hop 継続検証** — S22-S25 崩壊/非/崩壊/非 4-hop 確立
4. **ub=1586 3 連続 non-崩壊 recovery 後の持続性** — 15.133/15.261/15.152 の 4 連続化可否
5. **σ_pool regime change 5 session 連続 / 解消検証** — 1586>1584 逆転 4 連続中

加えて cool time 帯線形モデル精緻化、2 ub sig "not_sig 1586" subtype 頻度仮説、A/B alternating 優位 regime 切替え仮説、下帯連続の session 間隔、recovery 帯収束先予測、pool 差 1586-1584 振動、within-σ 低位回帰も同時に 1 session 追加で進展する。

## 実施方針（S25 と同条件を再実行）

- **GPU サーバ**: t120h-p100（ロック取得必須）
- **条件**: fa=1 × OT=MoE-only × ctx=32768 × ub ∈ {1584, 1586, 1664}、各 warmup 2 + eval 5 run
- **prompt**: Sbfine3 以降と同一 prompt_1k.txt（1086 tokens）
- **cooldown**: run 間 60s、ub 切替時は stop + sleep 5s
- **所要見込み**: 37-40 分（S25 実績 36'43"）

## 再利用する既存資産

すべて S25 attachment (`report/attachment/2026-04-21_032417_qwen3-122b-c3-phaseSeval25s/`) からコピーし、ファイル名・タグ・REMOTE_LOG prefix の `25s` を `26s` に書き換えて再利用：

- `start_phaseSeval25s.sh` → `start_phaseSeval26s.sh`
- `batch_phaseSeval25s.sh` → `batch_phaseSeval26s.sh`
- `run_all.sh`（変更不要、TAG_PREFIX 経由でタグ切替）
- `measure_phaseI.sh`（変更不要）
- `prompts/prompt_1k.txt`（変更不要）
- `analyze_phaseSeval25s.py` → `analyze_phaseSeval26s.py`（n=26 に対応、S1-S25 の session マップに S26 を追加する部分のみ手修正）

他リポ資産：
- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- `.claude/skills/llama-server/scripts/stop.sh`（batch 内で使用）

## 手順

### Step 1: 作業ディレクトリ準備
- `report/attachment/2026-04-21_<HHMMSS>_qwen3-122b-c3-phaseSeval26s/` を作成
- `start_`, `batch_`, `run_all.sh`, `measure_phaseI.sh`, `analyze_*.py`, `prompts/` を S25 から cp し、25s→26s に sed 書き換え

### Step 2: GPU ロック取得
- `bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100` で排他取得

### Step 3: バッチ実行
- `HOST=t120h-p100 bash batch_phaseSeval26s.sh > batch_phaseSeval26s.log 2>&1 &`
- 終了後 summary TSV を生成（既存 measure_phaseI.sh が summary を書き出す形式）

### Step 4: 26-session 統計解析
- `analyze_phaseSeval26s.py` 実行で以下を算出し CSV/verdict に出力：
  - S1-S26 pooled 130-run mean/σ_pool/range
  - 崩壊頻度（各 ub、S26 を加味）
  - mode 分類（A/B/C/D/E、ピーク順序）
  - Welch t-test（prior 25-session pool vs S26、3 ub それぞれ）
  - σ_pool 1584/1586 逆転の 5 連続判定
  - ub=1664 帯分類（下 < 14.80 / 中 14.80-15.20 / 上 > 15.20）と遷移行列
  - ub=1584 alternating 崩壊 5-hop 判定
  - ub=1586 recovery 連続カウント
  - cool time（S25 終了 → S26 開始）記録

### Step 5: GPU ロック解放
- `bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100`

### Step 6: レポート作成
- `report/2026-04-21_<HHMMSS>_qwen3-122b-c3-phaseSeval26s.md` を作成、以下セクション必須：
  - 添付ファイル一覧
  - 参照（S25・S24・S23・S22・S1・過去 1-run 参照値）
  - 前提・目的
  - 判定しきい値・成功条件
  - 環境情報
  - セッション間隔（cool time）
  - 結果（3 ub × 7 run の eval_tps、pooled 130-run 統計、8 大事件 per-topic 観察）
  - **未検証事項** セクション（S25 踏襲の既知項目 + 本 Phase 新規項目）
  - **検証完了後に実施すべき TODO** セクション（S25 踏襲 + 本 Phase 新規）
- `REPORT.md` にエントリ追加（index 更新）

## 検証（end-to-end）

- [ ] `batch_phaseSeval26s.log` に 3 条件 × "measure done" が 3 行出ていること
- [ ] `summary_phaseSeval26s.tsv` が 21 行（warmup 6 + 1k 15）揃うこと
- [ ] `phaseSeval26s_stats.csv` が 3 ub 行生成
- [ ] `phaseSeval26s_verdict.txt` に崩壊/mode/Welch/σ_pool regime/帯判定の各結論
- [ ] GPU ロックが最終的に解放されていること（`lock-status.sh` で確認）
- [ ] レポート md が S25 と同フォーマットで未検証事項/検証完了後 TODO の両セクションを持つこと

## 重要ファイル（作成/参照）

### 作成
- `report/2026-04-21_<HHMMSS>_qwen3-122b-c3-phaseSeval26s.md`
- `report/attachment/2026-04-21_<HHMMSS>_qwen3-122b-c3-phaseSeval26s/` 以下一式
- `REPORT.md`（index 追記）

### 参照のみ
- `report/attachment/2026-04-21_032417_qwen3-122b-c3-phaseSeval25s/` 以下（コピー元）
- `.claude/skills/gpu-server/scripts/lock.sh`, `unlock.sh`
- `.claude/skills/llama-server/scripts/stop.sh`
- `CLAUDE.md`（遵守）
- `REPORT.md`（フォーマット遵守）

## リスク・留意事項

- S26 開始タイミングが S25 終了から大幅に遅延した場合、cool time が「通常帯 13-16 分」「境界帯 17-20 分」「逸脱帯 21+ 分」「長期帯 120+ 分」のどの zone に入るかで |Δ_max| 期待値が変わる。実測値を verdict に必ず記録
- 起動失敗（OOM/ub reject）時は `start_phaseSeval26s.sh` が exit 2/3 で abort するので batch ログで検出可能
- バッチ途中で障害時は、異常 ub のみ再実行する手段として run_all.sh を単独で叩けるが、session 連続性維持のため原則全 ub セットを 1 回で完遂
