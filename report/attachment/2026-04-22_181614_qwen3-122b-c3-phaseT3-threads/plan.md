# Phase T-3 実装プラン: threads 中間値スイープ

## 目的

Phase D で threads ∈ {20, 40, 80} で 40 を採択。**中間値 {24, 28, 32, 36} は未測定**。40 未満で cache locality 改善 / NUMA memory bandwidth 余裕による eval 改善の可能性を検証。

## スイープ条件

- THREADS ∈ {24, 28, 32, 36, 40} の 5 条件
- 固定: KV=q8_0 (k/v), split-mode=layer, ctx=32768, ub=1586, flash-attn=1, OT=MoE only, numactl -N1 -m1, -ngl 999
- バイナリ: `6990e2f1f` (Phase T-1/T-2 と同一、再ビルド不要)

## ベースライン

- Phase D: 15.03 t/s (threads=40)
- Phase S: 15.39 t/s (ctx=65k, ub=512)
- Phase T-1 q8_0 最良: 15.016 t/s
- Phase T-2 最良: 14.672 t/s (session drift で下振れ)

## 判定基準

| 判定 | 閾値 |
|------|------|
| Phase S 超え | eval_mean > 15.39 |
| Phase D 超え | eval_mean > 15.03 |
| Phase T-1 q8_0 超え | eval_mean > 15.016 |
| threads=40 (baseline) 超え | 本 Phase 内 40 との +1% 以上 |

## 実行順序

`40 → 36 → 32 → 28 → 24` (baseline 40 を先頭で session drift 監視)

## 測定プロトコル

各条件 warmup 2 run + eval 5 run、所要 ~55-65 分。

## T-2 から T-3 への変更点

| ファイル | 変更 |
|---------|------|
| `start_phaseT3.sh` | `THREADS` を `${THREADS:-40}` 可変化。`REMOTE_LOG` に `_t${THREADS}` 含める。KV デフォルト q8_0 |
| `batch_phaseT3.sh` | 外ループを `THREADS_LIST=(40 36 32 28 24)` に置換。KV/SM 固定 |
| `measure_phaseT3.sh` | 変更なし (T-2 と同一) |
| `run_all.sh` | measure スクリプト名を `measure_phaseT3.sh` に差し替え |
| `analyze_phaseT3.py` | 集計軸を threads に変更。`PEAK_PHASE_T2_BEST=14.672` 追加 |
| `plot_phaseT3.py` | X 軸 threads の折れ線グラフ (eval / prompt の 2 サブプロット) |
