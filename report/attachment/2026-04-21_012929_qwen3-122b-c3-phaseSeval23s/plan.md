# Phase S-eval-23session 実施計画

## Context

直前レポート [2026-04-21_002703_qwen3-122b-c3-phaseSeval22s.md](../../projects/llm-server-ops/report/2026-04-21_002703_qwen3-122b-c3-phaseSeval22s.md) の「検証完了後に実施すべき TODO」新規項目の先頭 **★最重要: Phase S-eval-23session 候補** を実施する。同レポートの「未検証事項」新規項目の **★最優先 5 件**（下記）を S23 session 追加 1 回で同時前進させる唯一のアクションであり、優先度は圧倒的に高い。

**S22 で判明した ★最優先 未検証事項 (5 件)**:

1. **ub=1586 極度崩壊 13.844 の再現性** — S23 で 15.0+ 回復なら単発異常事象、13.x 連続なら「崩壊帯 13.8 まで到達可能」定着
2. **ub=1586 σ_pool 1584 超えの定着** — σ_pool 1586 0.339 > 1584 0.327 の 22-session 初観測が S23+ で維持されるか (分散 regime change か単発か)
3. **「mode_C ⇔ 3 ub sig (1664+/1584−/1586−)」相関の拡大** — S17/S22 で n=2/2 = 100%、S6 は縮約版 (2 ub sig × 1664+)、S23 で新 session 追加による相関検証
4. **ub=1664 中帯復帰の帯間 Markov 遷移** — 上→中 直接遷移は S21→S22 のみ、S22→S23 で中→? 遷移サンプル追加 (中帯 stay / 上帯 / 下帯)
5. **cool time × |Δ_max| 非線形性** — S22 cool time 19'10" × |Δ_max| 1.533 の 2.63 倍増幅、S23 cool time 値次第で「cool time zone」仮説検証

### S23 の観測軸

S22 と同条件での S23 実行で同時に追跡する 5 軸:

- ub=1586 mean (15.0+ 回復 or 13.x 連続 or 中間帯 14.x)
- ub=1584 崩壊判定 (S22 14.830 崩壊 → 7/23 崩壊 or 6/23 非崩壊)
- ub=1664 帯遷移 (S22 中帯 → 中帯 stay / 上帯 / 下帯)
- mode 分類 (mode_C 4 回目 or mode_A/B 均衡復帰 or 他 mode)
- Welch 3 ub sig subtype (1664+/1584−/1586− 定着 or 他 subtype)

### タイムライン

- 現在時刻: 2026-04-21 01:27 JST
- S22 終了: 01:16
- S23 開始見込み: ~01:35 (cool time ≈ 19 分、S22 と同 zone)
- S23 終了見込み: ~02:20 (バッチ 46 分 + warmup 後)

## 実施方針

S22 の scripts を完全再利用し、名前と timestamp だけ差し替える。起動パラメータ・プロンプト・分析ロジックは 22 session 間完全一致しているため、S23 でも一貫性維持。

## 作業ディレクトリ

- **新規**: `report/attachment/2026-04-21_XXXXXX_qwen3-122b-c3-phaseSeval23s/`（XXXXXX は開始時刻）
- **参照**: `report/attachment/2026-04-21_002703_qwen3-122b-c3-phaseSeval22s/`（S22 スクリプト一式をコピー元）

## 手順

### 1. GPU ロック取得
```bash
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 2. 作業ディレクトリ作成とスクリプト複製
S22 ディレクトリから以下をコピー:
- `start_phaseSeval22s.sh` → `start_phaseSeval23s.sh`
- `batch_phaseSeval22s.sh` → `batch_phaseSeval23s.sh`
- `run_all.sh` → `run_all.sh`（変更なし）
- `measure_phaseI.sh` → `measure_phaseI.sh`（変更なし）
- `analyze_phaseSeval22s.py` → `analyze_phaseSeval23s.py`
- `prompts/prompt_1k.txt` → `prompts/prompt_1k.txt`（変更なし）

### 3. 名前・リテラル置換
- 全ファイルで `phaseSeval22s` → `phaseSeval23s`、`Seval22s` → `Seval23s`
- `analyze_phaseSeval23s.py` 内:
  - `CUR_SESSION_LABEL = "S22_phaseSeval22s"` → `"S23_phaseSeval23s"`
  - `PRIOR_TSVS` に S22 entry 追加:
    ```python
    ("S22_phaseSeval22s",
     SCRIPT_DIR.parent / "2026-04-21_002703_qwen3-122b-c3-phaseSeval22s" / "summary_phaseSeval22s.tsv"),
    ```
  - `MODE_GROUPS` の `cur_S22` → `prev_S22`、新規 `cur_S23: ["S23_phaseSeval23s"]` 追加
  - 出力ファイル名 `phaseSeval22s_*` → `phaseSeval23s_*`
  - 22-session → 23-session、prior pool 数 105 → 110、pooled run 数 110 → 115 の更新

### 4. バッチ実行
```bash
cd report/attachment/2026-04-21_XXXXXX_qwen3-122b-c3-phaseSeval23s/
bash batch_phaseSeval23s.sh > batch_phaseSeval23s.log 2>&1
```
- 所要時間: 約 46 分（S22 実績 44'42"）
- 3 ub × (warmup 2 + eval 5) = 21 run

### 5. 分析
```bash
python3 analyze_phaseSeval23s.py
```
出力:
- `summary_phaseSeval23s.tsv`（S23 の raw）
- `phaseSeval23s_stats.csv`（S23 ub 別統計）
- `phaseSeval23s_verdict.txt`（23-session pooled / Welch / mode / 帯分類）

### 6. 停止・ロック解放
```bash
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 7. レポート作成
- パス: `report/2026-04-21_XXXXXX_qwen3-122b-c3-phaseSeval23s.md`
- 形式: S22 レポート同一構造
- 必須セクション（ユーザ明示要件）:
  - **未検証事項** セクション（S22 からの継承 + S23 で判明した新規項目）
  - **検証完了後に実施すべき TODO** セクション（S22 からの継承 + S23 で追加）
- その他セクション（既存形式踏襲）:
  - タイトル（S23 で観測した事象の要約、pooled 115-run 統計確定）
  - 実施日時 / 作業種別 / GPU ロック / 添付ファイル一覧 / 参照 / 前提・目的 / 判定しきい値 / 成功条件 / 環境情報 / 再現方法 / 実行結果サマリ / 補足

### 8. REPORT.md の index 更新
- `REPORT.md` の index リストに S23 レポート行を追加（S22 行の直下）

## 再利用する既存資産

- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh` — ロック管理
- `.claude/skills/llama-server/scripts/stop.sh` — llama-server 停止
- `report/attachment/2026-04-21_002703_qwen3-122b-c3-phaseSeval22s/` 配下全ファイル — 複製元
- `prompts/prompt_1k.txt`（6200 bytes、prompt_n=1086 tokens）— Phase Sbfine3 以来同一

## 新規作成するファイル

- `report/attachment/2026-04-21_XXXXXX_qwen3-122b-c3-phaseSeval23s/` ディレクトリ一式（script/asset + batch log + out_Seval23s_* 6 directories + startup_logs/ + 3 statistics output）
- `report/2026-04-21_XXXXXX_qwen3-122b-c3-phaseSeval23s.md` — 本レポート
- 既存 `REPORT.md` の index 行追加

## 検証 (verification)

測定と分析の成功判定:

1. **起動ヘルス**: 3 ub すべてで `start_phaseSeval23s.sh` が "ready" → 本番ログで確認
2. **eval run 完走**: 各 ub で 5 run × `predicted_n=256` 完走 → `summary_phaseSeval23s.tsv` の行数 = 3 ub × (2 warmup + 5 eval) = 21 行
3. **統計生成**: `phaseSeval23s_verdict.txt` に 23-session 系列（S1-S23）が欠損なし
4. **崩壊頻度**: 3 ub ごとに 23-session の崩壊カウント（ub=1584 × 6-7/23、ub=1586 × 4-5/23、ub=1664 × 11-12/23 予測範囲）
5. **compute buffer 23 session 完全一致**: ub=1586 CUDA0=980.36 / CUDA1=452.31 / CUDA2=452.31 / CUDA3=1558.12 / Host=235.48 MiB

5 軸観測の結果記録（いずれの結果も想定範囲内でレポートに事実として記録）:

- ub=1586 S23 mean_eval (13.x 連続 / 15.0+ 回復 / 14.x 中間)
- ub=1586 σ_pool vs ub=1584 σ_pool の順位
- mode_C 4 回目観測 有無 × Welch 3 ub sig subtype
- ub=1664 S23 帯 (中 stay / 上 / 下) で Markov 遷移データ追加
- S22→S23 cool time × |Δ_max| 関係

## リスク

- **cool time**: 計画承認・準備に 10 分前後かかる想定で S23 開始は ~01:35、cool time ~19 分（S22 と同 zone 19'10" 近似）。別 zone を狙う場合は待機時間調整が必要だが、本 Phase は S22 同条件比較が目的なので特に待機は行わない。
- **所要時間**: バッチ 46 分 + 分析 2 分 + レポート作成 15 分 = 約 1 時間 GPU ロック保持。
- **日付は純 2026-04-21 intra-day 2 session 目** (S22 に続く)、inter-day drift 検証の基盤積み上げ。

## 重要な注意点

- CLAUDE.md より: GPU サーバ使用時は Skill `gpu-server` 経由でロック管理
- 相対パス `.claude/skills/...` で実行（フルパス禁止）
- plan mode → auto mode で自動続行
- sudo は Claude からは実行しない（今回不要）
