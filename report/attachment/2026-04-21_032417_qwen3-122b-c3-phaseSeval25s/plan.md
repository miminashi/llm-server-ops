# Phase S-eval-25session (S25) 実施計画

## Context

直前レポート [2026-04-21_023213_qwen3-122b-c3-phaseSeval24s.md](../../projects/llm-server-ops/report/2026-04-21_023213_qwen3-122b-c3-phaseSeval24s.md) の「検証完了後に実施すべき TODO / 新規項目」における **★最重要: Phase S-eval-25session 候補** を実施する。

S24 では「ub=1584 崩壊再突入 14.971 (alternating 2-hop 新類型) + ub=1586 非崩壊 15.261 (大落下後 2 連続回復) + ub=1664 下帯再落下 14.652 (中帯 3 連続 stay 不成立) + mode_B 復帰 A/B 8/8 再均衡 + Welch 3 ub sig 新 subtype (+1586/−1584/−1664) + σ_pool regime change 3 session 連続確定 + cool time 14'59" × |Δ_max|=0.437 zone 線形比 validated」の 8 大事件が同時観測された。

本 Phase S25 は、S24 レポートが指定する以下の ★最優先 5 軸を同時検証する。これらはすべて単一の「S1-S24 と同条件での n=25 セッション目の追加計測」で達成できるため、1 本のレポートで集約する。

1. **A/B 再均衡 steady-state の S25+ 継続検証** (A/B 8/8=33.3% 再均衡 → S25 で 9/25 or 8/25 再均衡 or 他 mode 遷移)
2. **ub=1664 下帯 stay 可否 + 帯振動パターン** (S22/S23/S24「中中下」→ S25 で 下 stay か中/上 復帰か)
3. **ub=1584 alternating 2-hop 崩壊継続検証** (S22/S23/S24「崩壊/非/崩壊」→ S25 で 非なら 2-hop stable cycle、崩壊なら break)
4. **ub=1586 S22 大落下後 3 連続回復可否** (S22 13.844 → S23 15.133 → S24 15.261 → S25 で 15.3+ or 15.0-15.2 stay or 再崩壊)
5. **σ_pool regime change 4 session 連続 / 解消検証** (S22/S23/S24 で 1586>1584 が 3 連続確定 → S25 で 4 連続 or 解消)

所要時間は S24 と同等の約 37-40 分（実行 36'45" + 起動・解析）。

## 前提条件

- **cool time の管理**: S24 終了が 2026-04-21 03:11 JST、現在 03:21 JST（経過 10 分）。通常帯 (13-16 分) 到達は 03:24-03:27。開始直前に再確認し、可能なら 通常帯内で開始することで cool time zone 線形比検証の追加標本を得る
- **GPU ロック**: 現在 `t120h-p100: available`。batch 実行前に `lock.sh t120h-p100` を取得する
- **`sudo` 不使用**: S24 と同様、`sudo` 権限は使用しない（drop_caches 等は行わない）
- **構成の完全同一性維持**: 既存 24 session と同じ fa=1 / f16 KV / ctx=32768 / numactl / threads=40 / poll=0 / ngl=999 / OT_REGEX を維持（構成変更は session effect を別方向にシフトさせるため厳守）

## 実装ステップ

### Step 1: レポートディレクトリと attachment 準備

1. 開始時刻タイムスタンプを `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得
2. `report/` 直下にレポート本体ファイル名 `<timestamp>_qwen3-122b-c3-phaseSeval25s.md` を予約
3. `report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval25s/` ディレクトリ作成
4. S24 の attachment ディレクトリから以下の 5 スクリプトと `prompts/prompt_1k.txt` を新ディレクトリへコピー:
   - `start_phaseSeval24s.sh` → `start_phaseSeval25s.sh`
   - `batch_phaseSeval24s.sh` → `batch_phaseSeval25s.sh`
   - `run_all.sh` (そのまま、内部に Phase 名の固定参照なし想定、要確認)
   - `measure_phaseI.sh` (そのまま流用、Phase 名の固定参照なし想定、要確認)
   - `analyze_phaseSeval24s.py` → `analyze_phaseSeval25s.py`
5. コピー後に `phaseSeval24s` → `phaseSeval25s` / `Seval24s` → `Seval25s` / `S24` → `S25` を grep して書き換え（Edit tool で最小置換）

### Step 2: analyze スクリプトの更新

- `analyze_phaseSeval25s.py` の `PRIOR_TSVS` リストに S24 の summary TSV パスを追加:
  ```
  .../report/attachment/2026-04-21_023213_qwen3-122b-c3-phaseSeval24s/summary_phaseSeval24s.tsv
  ```
- 現在セッションラベルを `S25_phaseSeval25s` に変更
- ラベル別時系列表示時に S24 を含むよう内部ループの n_sessions を 25 に更新

### Step 3: GPU ロック取得と実行

1. `bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100` でロック取得
2. `cd report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval25s/`
3. `bash batch_phaseSeval25s.sh > batch_phaseSeval25s.log 2>&1` （バックグラウンド実行、約 37 分）
4. 実行中は `tail -f batch_phaseSeval25s.log` で進捗監視

### Step 4: 解析

1. バッチ完了後、`python3 analyze_phaseSeval25s.py` で 25-session 統計 (`phaseSeval25s_stats.csv` / `phaseSeval25s_verdict.txt`) を生成
2. 5-run ピボット、Welch t (prior 120-run pool vs S25)、ピーク順序分類、帯遷移、pooled 125-run 統計を出力
3. verdict を目視確認し、S24 レポートの 5 軸 TODO に対する回答を整理

### Step 5: llama-server 停止・ロック解放

- `bash .claude/skills/llama-server/scripts/stop.sh t120h-p100`
- `bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100`

### Step 6: レポート作成

S24 レポートと同構造で、以下を記述:
- 冒頭 H1: S25 の 5 軸検証結果を事件数列挙形式で圧縮記述
- 前提・目的: S24 レポートの ★最優先 5 軸 TODO を列挙、S25 での検証結果サマリ
- 実施日時、GPU ロック状態（取得/解放）、作業種別
- 添付ファイル一覧（プラン、起動/batch/run/measure/analyze スクリプト、ログ、TSV、CSV、verdict、startup_logs ディレクトリ、out ディレクトリ、prompt）
- 参照: 直前 S24、S23-S22、S1、過去 1-run 参照値（ub=1584/1586/1664）
- 判定しきい値、成功条件チェックリスト
- 環境情報、セッション間隔表（S17-S25 で S25 行追加）
- 再現方法（bash コマンド列）
- 実行結果サマリ: S25 5-run ピボット / 25-session 時系列抜粋 / Welch 表 / mode 分布 / 帯構造 / pooled 125-run 統計 / 1 位 ub 出現頻度 / ub 間有意差
- **未検証事項**（S24 からの継続 + S25 新規）
- **検証完了後に実施すべき TODO**（S24 からの継続 + S25 新規）
- 補足: 核心発見サマリ、結論 1-8、次期テーマ

## 書き換え対象ファイル（Step 1-2 時点）

- `report/attachment/<ts>_qwen3-122b-c3-phaseSeval25s/start_phaseSeval25s.sh`
- `report/attachment/<ts>_qwen3-122b-c3-phaseSeval25s/batch_phaseSeval25s.sh`
- `report/attachment/<ts>_qwen3-122b-c3-phaseSeval25s/run_all.sh`（要確認 — 置換対象がない場合スキップ可）
- `report/attachment/<ts>_qwen3-122b-c3-phaseSeval25s/measure_phaseI.sh`（要確認）
- `report/attachment/<ts>_qwen3-122b-c3-phaseSeval25s/analyze_phaseSeval25s.py`

## 再利用する既存資産

- **GPU ロック scripts**: `.claude/skills/gpu-server/scripts/{lock,unlock,lock-status}.sh`（skill `gpu-server`）
- **llama-server 停止**: `.claude/skills/llama-server/scripts/stop.sh`
- **prompt ファイル**: `report/attachment/2026-04-21_023213_qwen3-122b-c3-phaseSeval24s/prompts/prompt_1k.txt` をコピーして流用（Phase Sbfine3 以降 全 session 共通、6200 bytes / 1086 tokens）
- **S1-S24 の summary TSV**: S24 レポートの `analyze_phaseSeval24s.py` に同じ絶対パス列挙があるためそのまま流用 + S24 パスを追加

## 検証方法

1. **構成再現性チェック**: batch 実行後、`startup_logs/` 内の llama-server 起動ログで「compute buffer = CUDA0 980.36 / CUDA1 452.31 / CUDA2 452.31 / CUDA3 1558.12 / Host 235.48 MiB」が 24 session 同値か確認（外れた場合 allocator 側変動が発生）
2. **5-run σ**: 各 ub の within-session σ が 0.002-0.004 の低位帯に収まるか確認
3. **25-session verdict**: `phaseSeval25s_verdict.txt` を目視し、すべての 成功条件 TODO にチェックが付与されるか確認
4. **レポート本体の整合性**: 添付ファイル全パスが実在するか `ls` で確認

## リスク

- **cool time の zone 境界をまたぐ可能性**: 開始タイミングを 03:24-03:27 に合わせれば通常帯。仮に 03:24 より早くなった場合の「境界帯前 (10-12 分)」zone は未観測であり、新 zone 標本としてむしろ有益
- **llama-server 起動失敗**: 24 session 全て正常起動のため確率は低いが、起動失敗時は 1 回のみリトライし、2 度目失敗なら Phase 中断しロック解放
- **ビルド差分**: 既存 `~/llama.cpp/build/bin/llama-server` を流用するため変更なし

## 完了の判定

- [ ] S25 の 3 条件すべてで eval 5-run 完走
- [ ] `phaseSeval25s_verdict.txt` 生成完了
- [ ] レポート本体ファイル作成完了、添付ディレクトリ全ファイル実在
- [ ] GPU ロック解放済
- [ ] `未検証事項` と `検証完了後に実施すべき TODO` の 2 セクションが S24 同様の形式で揃っている
