# Phase S-eval-22session 実施計画

## Context

直前レポート [2026-04-20_232604_qwen3-122b-c3-phaseSeval21s.md](../../projects/llm-server-ops/report/2026-04-20_232604_qwen3-122b-c3-phaseSeval21s.md) の「検証完了後に実施すべき TODO」末尾の **★最重要: Phase S-eval-22session 候補** を実施する。これは「新規項目」にある 5 件の ★最優先 未検証事項（ub=1664 帯間振動次遷移 / ub=1584 崩壊帯 15.025 極近接の次動向 / mode_E 3 回目観測の相関 / Welch 2 ub sig 対称 subtype 出現周期 / cool time 通常帯 2 連続での |Δ_max| 変動）を **1 session 追加で同時に前進** させる唯一のアクションであり、優先度は圧倒的に高い。

S22 の 4 軸観測目標:

1. **ub=1584 崩壊再突入判定**: S21 15.025（崩壊閾値 15.0 から +0.025）→ S22 が 15.0 割り込みなら「confirmed 直後崩壊」新類型、非崩壊維持なら崩壊帯吸引力の弱化証拠
2. **ub=1664 帯遷移**: S17/S18 上 → S19/S20 下 → S21 上（2-2-1 振動）→ S22 は上帯 2 連続か、中・下帯復帰か
3. **mode 均衡の継続性**: mode_A/B 7/22 = 7/22 の 33.3% 同率維持 or 崩壊、mode_E 4 回目観測の有無
4. **Welch 類型の S22 分布**: 3 ub sig 回帰 / 2 ub sig 継続（正・負方向）/ 1 ub sig / 0 ub sig のいずれか

S22 は日付跨ぎ observation 継続後の初の純 2026-04-21 intra-day session でもあり、inter-day drift 比較の基盤を作る。

現在時刻 2026-04-21 00:23 JST、S21 終了 00:12 から 11 分経過。計画承認・準備に 10-15 分かかる想定で、バッチ開始時は cool time ≈ 20-25 分（S20→S21 の 15'35" と類似する「通常帯」寄り）。もし開始がそれ以上遅れても、cool time 系列のデータ点としては十分に価値がある。

## 実施方針

S21 の scripts を完全再利用し、名前と timestamp だけ差し替える。起動パラメータ・プロンプト・分析ロジックは変更なし（21 session 間で完全一致しているため、S22 でも一貫性を維持）。

## 作業ディレクトリ

- **新規**: `report/attachment/2026-04-21_XXXXXX_qwen3-122b-c3-phaseSeval22s/`（XXXXXX は開始時刻）
- **参照**: `report/attachment/2026-04-20_232604_qwen3-122b-c3-phaseSeval21s/`（S21 スクリプト一式をコピー元とする）

## 手順

### 1. GPU ロック取得
```bash
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 2. 作業ディレクトリ作成とスクリプト複製
- S21 ディレクトリから以下をコピー:
  - `start_phaseSeval21s.sh` → `start_phaseSeval22s.sh`
  - `batch_phaseSeval21s.sh` → `batch_phaseSeval22s.sh`
  - `run_all.sh` → `run_all.sh`（変更なし）
  - `measure_phaseI.sh` → `measure_phaseI.sh`（変更なし）
  - `analyze_phaseSeval21s.py` → `analyze_phaseSeval22s.py`
  - `prompts/prompt_1k.txt` → `prompts/prompt_1k.txt`（変更なし）

### 3. 名前・リテラル置換
- `phaseSeval21s` → `phaseSeval22s`（全ファイル）
- `Seval21s` → `Seval22s`（TAG、ディレクトリ名等）
- `analyze_phaseSeval22s.py` 内:
  - `CUR_SESSION_LABEL = "S21_phaseSeval21s"` → `"S22_phaseSeval22s"`
  - `PRIOR_TSVS` に S21 entry 追加:
    ```python
    ("S21_phaseSeval21s",
     SCRIPT_DIR.parent / "2026-04-20_232604_qwen3-122b-c3-phaseSeval21s" / "summary_phaseSeval21s.tsv"),
    ```
  - MODE_GROUPS や 21-session 依存ロジックを S22/22-session に拡張（行 76 以降、`prev_S21` エントリ追加、21-session カウントを 22-session へ更新）
  - 出力ファイル名 `phaseSeval21s_*` → `phaseSeval22s_*`
  - 21 → 22, 20 → 21 の数値更新（total session count と prior pool 数、pooled run 数 105 → 110）

### 4. バッチ実行
```bash
cd report/attachment/2026-04-21_XXXXXX_qwen3-122b-c3-phaseSeval22s/
bash batch_phaseSeval22s.sh > batch_phaseSeval22s.log 2>&1
```
- 所要時間: 約 46 分（S21 実績 45'59"）
- 3 ub × (warmup 2 + eval 5) = 21 run

### 5. 分析
```bash
python3 analyze_phaseSeval22s.py
```
出力:
- `summary_phaseSeval22s.tsv`（S22 の raw）
- `phaseSeval22s_stats.csv`（S22 ub 別統計）
- `phaseSeval22s_verdict.txt`（22-session pooled / Welch / mode / 帯分類）

### 6. 停止・ロック解放
```bash
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 7. レポート作成
- パス: `report/2026-04-21_XXXXXX_qwen3-122b-c3-phaseSeval22s.md`
- 形式: S21 レポート ([2026-04-20_232604_qwen3-122b-c3-phaseSeval21s.md](../../projects/llm-server-ops/report/2026-04-20_232604_qwen3-122b-c3-phaseSeval21s.md)) と同一構造
- 必須セクション（既存形式に従う）:
  - タイトル（5 大事件〜6 大事件同時観測の要約、pooled 110-run 統計確定）
  - 実施日時 / 作業種別 / GPU ロック
  - 添付ファイル一覧
  - 参照（S21, S20, S19, S18, S1 への link 継承）
  - 前提・目的（S21 からの継承 + S22 の 4 軸観測目標）
  - 判定しきい値
  - 成功条件（チェックリスト）
  - 環境情報（S1-S21 と同一、セッション間隔表に S22 行追加）
  - 再現方法
  - 実行結果サマリ（eval 5-run ピボット、22-session mean 時系列、Prior 21-session pool vs S22 Welch、ピーク順序 22-session、ub=1664 帯構造、pooled 110-run、ピーク 1 位頻度）
  - **未検証事項** セクション（S21 からの継承 + S22 で判明した新規項目）
  - **検証完了後に実施すべき TODO** セクション（S21 からの継承 + S22 で追加）
  - 補足（核心発見サマリ）

ユーザからの明示要件として「未検証事項」と「検証完了後に実施すべき TODO」のセクションを必ず含める。

### 8. REPORT.md の index 更新
- `REPORT.md` の index リストに S22 レポート行を追加（S21 行の直下）

## 再利用する既存資産

- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh` — ロック管理
- `.claude/skills/llama-server/scripts/stop.sh` — 停止
- `report/attachment/2026-04-20_232604_qwen3-122b-c3-phaseSeval21s/` 配下全ファイル — 複製元
- `report/attachment/2026-04-20_003250_qwen3-122b-c3-phaseSeval/prompts/prompt_1k.txt` 系列 — 同一プロンプト

## 新規作成するファイル

- `report/attachment/2026-04-21_XXXXXX_qwen3-122b-c3-phaseSeval22s/` ディレクトリ一式（7 script/asset + batch log + out_Seval22s_* 6 directories + startup_logs/ + 3 statistics output）
- `report/2026-04-21_XXXXXX_qwen3-122b-c3-phaseSeval22s.md` — 本レポート
- 既存 `REPORT.md` の index 行追加

## 検証（verification）

測定と分析の成功判定:

1. **起動ヘルス**: 3 ub すべてで `start_phaseSeval22s.sh` が "ready" → 本番ログで確認
2. **eval run 完走**: 各 ub で 5 run × `predicted_n=256` 完走 → `summary_phaseSeval22s.tsv` の行数 = 3 ub × (2 warmup + 5 eval) = 21 行
3. **統計生成**: `phaseSeval22s_verdict.txt` に 12 セクション出力、22-session 系列（S1-S22）が欠損なし
4. **崩壊頻度**: 3 ub ごとに 22-session の崩壊カウントと Wilson 95% CI 出力
5. **compute buffer 22 session 完全一致**: ub=1586 CUDA0=980.36 / CUDA1=452.31 / CUDA2=452.31 / CUDA3=1558.12 / Host=235.48 MiB

4 軸観測の結果記録（いずれの結果でも想定範囲内で、レポートに事実として記録）:

- ub=1584 S22 mean_eval と「崩壊 (<15.0) or 非崩壊」判定
- ub=1664 S22 mean_eval と「上帯 / 中帯 / 下帯」分類
- S22 ピーク順序（6 mode のいずれか）と 22-session mode 分布
- S22 vs prior 21-session pool Welch t（3 ub 分、sig 数カウント）

## リスク

- **cool time 短縮**: 開始が 00:28 なら cool time 16 分、00:35 なら 23 分。通常帯（13-16 分）を若干逸脱する可能性。データ点としては有効だがレポート内で cool time 明記。
- **所要時間 46 分**: バッチ 46 分 + 分析 2 分 + レポート作成 15 分 = 約 1 時間。GPU ロック保持時間が長くなるが、他の claude session が使用中でないことをロック取得時に確認。
- **日付跨ぎ**: S22 は 2026-04-21 intra-day 予定だが、開始が遅れれば跨ぎ再発の可能性。開始時刻は記録。

## 重要な注意点

- CLAUDE.md より: GPU サーバ使用時は Skill `gpu-server` 経由でロック管理
- 相対パス `.claude/skills/...` で実行（フルパス禁止）
- plan mode → auto mode での実行は確認済み（auto mode active）
- sudo は Claude からは実行しない（今回の作業では不要）
