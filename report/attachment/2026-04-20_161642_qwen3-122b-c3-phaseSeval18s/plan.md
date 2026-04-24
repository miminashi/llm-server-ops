# Phase S-eval-18session 実施計画

## Context

直前レポート S17 ([2026-04-20_151741_qwen3-122b-c3-phaseSeval17s.md](/home/ubuntu/projects/llm-server-ops/report/2026-04-20_151741_qwen3-122b-c3-phaseSeval17s.md)) の「未検証事項」セクション最上位の ★最重要 TODO:

> ★最重要: Phase S-eval-18session 候補 — ub=1584 崩壊「2 session 周期」検証（S17 崩壊 → S18 非崩壊 / 崩壊）、ub=1586 peak 1 位復帰 or mode_C 連続、ub=1664 上帯 2 連続 or 中帯/下帯復帰、所要 40 分

を実施する。S17 で発見された以下の 3 仮説を同時追跡:

1. **ub=1584 崩壊「2 session 周期」仮説** — S4→S13(間隔9) → S15(間隔2) → S17(間隔2) で 2 session 周期移行、S18 崩壊なし予測
2. **ub=1586 peak 1 位復帰 or mode_C 連続** — S13-S16 で 4 連続 1 位、S17 で 3 位転落（mode_C 2 回目）、S18 で復帰 or mode_C 2 連続
3. **ub=1664 上帯（>15.20）2 連続 or 中帯/下帯復帰** — S17 で上帯 15.396（pool max 15.400 更新）、S6/S8/S17 の上帯 3 session、間隔は S6→S8=2, S8→S17=9

期待される成果: n=18 session での σ_session 再評価、pooled 90-run 統計、3 ub 独立変動モデル再検定、peak order mode 分布 (A/B 同率 + C/E 同率 + D 孤立) の安定性確認。

## 実施方法

S17 の資材 (`report/attachment/2026-04-20_151741_qwen3-122b-c3-phaseSeval17s/`) をベースに、S18 用へファイル名・TAG/prefix・PRIOR_TSVS のみ書き換えて実行する。起動パラメータ・プロンプト・測定ロジックは一切変更しない。

### 手順

1. **GPU ロック取得**
   ```bash
   bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
   ```

2. **作業ディレクトリ作成とスクリプト準備**
   - タイムスタンプ取得: `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`
   - ディレクトリ: `report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval18s/`
   - S17 から以下をコピーし `17s` → `18s` に一括置換:
     - `start_phaseSeval17s.sh` → `start_phaseSeval18s.sh`
     - `batch_phaseSeval17s.sh` → `batch_phaseSeval18s.sh`
     - `analyze_phaseSeval17s.py` → `analyze_phaseSeval18s.py`
     - `run_all.sh` (変更なし)
     - `measure_phaseI.sh` (変更なし)
     - `prompts/prompt_1k.txt` (変更なし)
   - `analyze_phaseSeval18s.py` の `PRIOR_TSVS` に S17 を追加:
     ```python
     ("S17_phaseSeval17s",
      SCRIPT_DIR.parent / "2026-04-20_151741_qwen3-122b-c3-phaseSeval17s" / "summary_phaseSeval17s.tsv"),
     ```
   - `CUR_SESSION_LABEL = "S18_phaseSeval18s"` に更新
   - `TAG_PREFIX = "Seval18s_fa1_ctx"` に更新
   - `startup_logs/` ディレクトリを作成

3. **バッチ実行**（約 45 分）
   ```bash
   cd report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval18s/
   bash batch_phaseSeval18s.sh > batch_phaseSeval18s.log 2>&1
   ```
   3 条件 (ub=1584, 1586, 1664) × ctx=32768 × fa=1 で各 warmup 2 run + eval 5 run を実行

4. **分析**
   ```bash
   python3 analyze_phaseSeval18s.py
   ```
   出力: `summary_phaseSeval18s.tsv` / `phaseSeval18s_stats.csv` / `phaseSeval18s_verdict.txt`

5. **GPU ロック解放**
   ```bash
   bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
   bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
   ```

6. **レポート作成**
   - ファイル: `report/<timestamp>_qwen3-122b-c3-phaseSeval18s.md`
   - 添付ディレクトリにプランファイル (`plan.md`) をコピー
   - 本文に以下を含める:
     - 直前レポート S17 への参照リンク
     - 18-session mean 時系列テーブル
     - pooled 90-run 統計
     - Welch t (S1..S17 pool vs S18)
     - peak order 18-session 集計
     - **未検証事項セクション**（S17 の未検証事項を引き継ぎ、本 Phase で潰した項目に [x]、新たに発生した項目を追加）
     - **検証完了後に実施すべき TODO セクション**（S17 から継承 + 新規項目）

## 環境情報

S17 と完全同一:

- **GPU サーバ**: t120h-p100 (10.1.4.14)、NVIDIA Tesla P100-PCIE-16GB × 4
- **llama.cpp**: `~/llama.cpp/build/bin/llama-server`
- **モデル**: `Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf` (unsloth snapshot)
- **起動パラメータ**: fa=1、f16/f16 KV、ctx=32768、`numactl --cpunodebind=1 --membind=1`、threads=40、poll=0、ngl=999
- **OT_REGEX**: `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
- **prompt**: S17 と同一 `prompts/prompt_1k.txt`（prompt_n=1086 tokens）
- **予測長**: max_tokens=256
- **cooldown**: run 間 60 秒
- **warmup**: 短 prompt 2 run

## 修正対象ファイル

すべて新規作成（S17 資材のコピー＋書き換え）:

- `report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval18s/start_phaseSeval18s.sh`
- `report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval18s/batch_phaseSeval18s.sh`
- `report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval18s/run_all.sh`
- `report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval18s/measure_phaseI.sh`
- `report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval18s/analyze_phaseSeval18s.py`
- `report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval18s/prompts/prompt_1k.txt`
- `report/attachment/<timestamp>_qwen3-122b-c3-phaseSeval18s/plan.md`（本プランファイルのコピー）
- `report/<timestamp>_qwen3-122b-c3-phaseSeval18s.md`（レポート本体）

## 検証方法

1. **スクリプト動作確認**: `batch_phaseSeval18s.sh` が 3 条件すべて healthy → eval 5 run 完走
2. **データ整合性**: `summary_phaseSeval18s.tsv` に 21 行 (3 ub × (warmup 2 + eval 5)) 格納、NA なし
3. **分析統計**: `phaseSeval18s_verdict.txt` に以下が出力される
   - 18 session mean 時系列（range / σ_session / verdict）
   - Welch t (17-session pool vs S18) で 3 ub の sig 判定
   - ピーク順序 18-session 頻度 (mode_A/B/C/D/E + 未観測 mode)
   - pooled 90-run 統計
   - 崩壊頻度 Wilson 95% CI (ub=1584/1586/1664)
4. **仮説判定**
   - ub=1584 崩壊仮説: S18 eval mean < 15.0 → 崩壊継続 / >= 15.0 → 2 session 周期 部分肯定
   - ub=1586 peak 1 位復帰: S18 で 1586 が 1 位か判定
   - ub=1664 上帯 2 連続: S18 eval mean > 15.20 → 上帯 2 連続
5. **レポート完成度**: 未検証事項・検証完了後 TODO の 2 セクションが存在、S17 からの引継ぎと新規項目の区別が明確

## 注意事項

- S17 と同条件での純粋な再実行であり、新機能追加や既存コード改変は一切ない
- バッチ実行中は GPU ロックを保持（他 session から llama-server / リモートブラウザ使用を排他）
- 所要時間は S17 と同様の 45 分程度想定、GPU ロックはその間保持
- 完了後は必ずロック解放
