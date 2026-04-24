# Phase S-eval-7session 実装計画

## Context

直前のレポート [2026-04-20_050710_qwen3-122b-c3-phaseSeval6s.md](/home/ubuntu/projects/llm-server-ops/report/2026-04-20_050710_qwen3-122b-c3-phaseSeval6s.md) の「未検証事項」のうち、以下 5 つの ★最優先 項目を 1 回の追加 session 計測で同時に前進させる。

- **ub=1586 初崩壊（S6 で 14.727 t/s）の原因特定**: S5 上振れ後の反転機構が恒常的か単発か
- **ub=1664 S6 過去最高値（15.292 t/s）の原因特定**: 長期上昇 vs 不規則大上振れの識別
- **ピーク順序 mode C（1664>1584>1586）の再現性**: 6 session 中 1 回のみ、再出現するか
- **2 モード仮説棄却後のモデル（3 モード以上 or ub 別独立変動）**: 更なるデータ点追加
- **S4 型共通低速 vs S6 型 ub 別逆方向 の 2 種類異常 session パターン分類**: 新パターン検出

現行の推定: ub=1584 崩壊頻度 1/6 = 16.7%（Wilson 95% CI [3.0%, 56.4%]）、ub=1586 pooled σ が n=25→30 で 2.8 倍拡大、ub=1664 が 6 session 目で初めて 1 位。n=7 で統計の安定性と mode C の継続性を確認する。

## 実施方針

Phase S-eval-6session と完全同一プロトコル（同一モデル、ctx=32768、fa=1、f16/f16 KV、OT_REGEX=MoE only、numactl node1、threads=40、--poll 0）で第 7 session を計測する。各 ub で warmup 2 run + 1k prompt eval 5 run。

**重要な同一性担保**:
- llama-server 起動パラメータは S6 と MiB 単位で完全一致する必要あり（compute buffer 一致が drift 判定の基礎）
- prompt は S6 で使った `prompts/prompt_1k.txt` （1084 token、6200 bytes）を再利用
- TH_UB1584_COLLAPSE=15.0、TH_CONFIRMED=0.05、TH_PARTIAL=0.10 等しきい値も S6 と同一

## ファイル構成（すべて新規作成、S6 資産からコピー改変）

レポート timestamp は実施直前に `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得する。添付ディレクトリは `report/attachment/<TS>_qwen3-122b-c3-phaseSeval7s/` 下に配置。

### 複製元: S6 添付ディレクトリ

`report/attachment/2026-04-20_050710_qwen3-122b-c3-phaseSeval6s/`

### 新規作成ファイル

1. `batch_phaseSeval7s.sh` — S6 batch から `6s` → `7s` 置換。ubs=(1584 1586 1664) 順で warmup+eval。
2. `start_phaseSeval7s.sh` — S6 start から `phaseSeval6s` → `phaseSeval7s` 置換。その他完全同一。
3. `run_all.sh`, `measure_phaseI.sh` — S6 から変更なしでコピー。
4. `prompts/prompt_1k.txt` — S6 と同一ファイル（6200 bytes、prompt_n=1084）をコピー。
5. `analyze_phaseSeval7s.py` — S6 の analyze を拡張:
   - `PRIOR_TSVS` に S6 を追加（合計 6 prior）
   - `CUR_SESSION_LABEL = "S7_phaseSeval7s"`
   - `MODE_GROUPS` に `mode_C_S6 = ["S6_phaseSeval6s"]` を追加し、`S7` と 3 モード全部の Welch t を計算
   - 7-session ピーク順序、n=35 pooled 統計、ub=1584/1586 崩壊頻度（Wilson 95% CI）、ub=1664 時系列単調性
   - warmup1 Δ モード帯判定に mode_C (+0.017) を追加

### 修正ファイル

なし（既存 skill scripts は一切触らない）。

## 実行フロー

1. **GPU サーバロック取得**: skill `gpu-server` 経由で `t120h-p100` をロック。
2. **作業ディレクトリ準備**: 新 TS で attachment ディレクトリを作成し、S6 から 5 ファイルをコピーして改変。
3. **バッチ実行**: `batch_phaseSeval7s.sh` 実行。所要約 50 分（ub 3 × (起動 4 分 + warmup 2 run + eval 5 run + stop 5 秒) ≈ 15 分/ub × 3）。
4. **解析**: `analyze_phaseSeval7s.py` を実行し `summary_phaseSeval7s.tsv`、`phaseSeval7s_stats.csv`、`phaseSeval7s_verdict.txt` を生成。
5. **レポート作成**: `<TS>_qwen3-122b-c3-phaseSeval7s.md` を作成。直前レポートと同様に「未検証事項」「検証完了後に実施すべき TODO」セクションを含める。
6. **ロック解放**: skill `gpu-server` のアンロックを実行。
7. **REPORT.md 索引追加**: レポート一覧の先頭に新規レポートへのリンクを追記（既存のルール順)。

## 重要な観察ポイント

レポート本文の判定フロー:

| 観察 | 解釈 |
|------|------|
| S7 peak order = 1664>1584>1586 | mode C 再現 → 3 モード仮説強化 |
| S7 peak order = 1584>1586>1664 or 1586>1584>1664 | mode A/B 復帰 → S6 は外れ値候補 |
| S7 peak order がすべて新規 | 4 モード以上 or ub 別独立モデル濃厚 |
| ub=1586 が S7 も < 15.0 | ub=1586 崩壊が連鎖 → 反転機構ではなく transitions |
| ub=1584 崩壊頻度 k/7 | Wilson CI 幅を 0-16%pt 絞り込み |
| compute buffer MiB 一致 | drift は runtime 状態（定説維持） |

## 検証方法

1. **バッチログ確認**: `batch_phaseSeval7s.log` と `run_all_*.log` で 3 ub すべて 5 eval run 完了を確認。
2. **TSV 整合性**: `summary_phaseSeval7s.tsv` が 3 ub × (2 warmup + 5 eval) = 21 行存在。
3. **analyze 実行**: `phaseSeval7s_verdict.txt` の 7-session 時系列、Welch t、ピーク順序集計、崩壊頻度を確認。
4. **compute buffer 検証**: `startup_logs/fa1_ctx32768_b<ub>_ub<ub>.log` から CUDA0/1/2 compute buffer が S1-S6 と MiB 単位完全一致することを確認（特に ub=1586 の 235.48 MiB など）。
5. **異常検出**: ub=1664 が S4/S6 とも異なる挙動を示した場合、mode 数更新。

## 前提・リスク

- **セッション間隔**: S6 終了が 2026-04-20 06:04 JST、本計画開始時刻 06:07 JST。S6-S7 間隔は batch 開始時点で 3 分未満になる可能性が高く、これまでの最短 11 分（S4-S5）より短い。**極めて短い cool time での drift 観察は新データ点として価値あり**（未検証事項「S4-S5 間隔 11 分（最短 cool time）でも崩壊回避した機構」を拡張確認）。ただし「3 分未満」はどの過去 session でも観測していない条件のため、これまでの「時間帯依存」仮説とは別条件となる。報告時はその旨明示する。
- **モデルダウンロード不要**: S6 で既に使用した snapshot がサーバに残存（Qwen3.5-122B-A10B-Q4_K_M）。
- **GPU サーバ干渉**: 他プロセスが無いこと（skill ロックで保証）。

## 参照する既存資産

- バッチスクリプト雛形: `report/attachment/2026-04-20_050710_qwen3-122b-c3-phaseSeval6s/batch_phaseSeval6s.sh`
- 起動スクリプト雛形: `report/attachment/2026-04-20_050710_qwen3-122b-c3-phaseSeval6s/start_phaseSeval6s.sh`
- 解析スクリプト雛形: `report/attachment/2026-04-20_050710_qwen3-122b-c3-phaseSeval6s/analyze_phaseSeval6s.py`
- 測定スクリプト: `report/attachment/2026-04-20_050710_qwen3-122b-c3-phaseSeval6s/measure_phaseI.sh`, `run_all.sh`
- プロンプト: `report/attachment/2026-04-20_050710_qwen3-122b-c3-phaseSeval6s/prompts/prompt_1k.txt`
- S1-S6 summary TSV: 各 `report/attachment/2026-04-20_*_qwen3-122b-c3-phaseSeval*/summary_phaseSeval*.tsv`
- Skill: `.claude/skills/gpu-server/`、`.claude/skills/llama-server/scripts/stop.sh`

## レポート必須セクション

- 添付ファイル（plan.md へのリンク）
- 参照（S1-S6 レポート全部へのリンク）
- 前提・目的
- 環境情報
- セッション間隔（S1-S7）
- 再現方法
- 実行結果サマリ（analyze 出力の各セクション）
- 再現性分析と解釈
- 採用判定（pooled 35-run mean / ピーク順序集計）
- **未検証事項**（S6 レポート既知項目 + 本 Phase で潰したものは [x]、新規項目）
- **検証完了後に実施すべき TODO**（S6 レポート既知項目 + 新規項目）
- 補足（核心発見サマリ、前 Phase 対照）
