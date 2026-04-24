# Phase T-3: threads 中間値スイープ (24/28/32/36/40)

## Context

Phase T シリーズは「パラメータチューニングで qwen3-122b (Q4_K_M, t120h-p100 × 4 GPU) の eval/prompt t/s 改善余地を直接検証」する目的で実施している。

- **Phase T-1 (KV 量子化スイープ)**: q8_0 ub=1586 で 15.016 t/s (Phase D -0.1%)。KV 量子化は頭打ち。副次発見 q8_0 > f16 +4.1%。
- **Phase T-2 (split-mode row vs layer)**: row split は -15〜-22% 劣化、CUDA3 偏在は構造由来で解消不能と判明。最良 14.672 t/s。

残る候補は **T-3 threads 中間値 / T-4 OT pattern 代替 / T-5 ビルドフラグ**。本 Phase では **T-3** を選択する。

### なぜ T-3 か

| 軸 | T-3 threads | T-4 OT 代替 | T-5 ビルドフラグ |
|----|-------------|-------------|------------------|
| コスト | 低 (~60 分、1 バイナリ) | 低 (~60 分、1 バイナリ) | 高 (~3-5 h、4 回再ビルド) |
| 実験設計の clean さ | **◎ 単一変数** | △ OT regex は交絡多い | ○ バイナリ差で clean |
| 既存データの gap | Phase D で 20/40/80 測定、**中間値未測定** | Phase A で blk.14-19 定性検証済、追加変種の根拠弱い | P100 (CC 6.0) 未検証 |
| null 時の次手 | T-4/T-5 への優先度整理 | 依然 T-3/T-5 残 | 最終候補のため終端 |
| hit 時の上振れ期待 | 中 (cache locality 改善) | 低 (Phase T-2 レポートで薄) | 中 (アーキ特化) |

T-3 が **情報量/コスト比が最大**、かつ Phase T-1/T-2 と同一バイナリ・同一 OT・同一 ub で「他条件を完全固定したまま threads のみ動かす」clean な sweep が可能。

### 検証したい仮説

Phase D は threads ∈ {20, 40, 80} で 40 を採択 (40 > 20 > 80)。中間値 {24, 28, 32, 36} は未測定。
- SMT OFF の physical core = 40 (numactl -N1: 片 socket)。
- 40 未満では cache 競合低減 / NUMA memory bandwidth 余裕で eval 改善の可能性、あるいは並列度不足で劣化。
- 仮説: **36 付近に eval_tps の極大**があれば Phase D (15.03) / Phase T-1 q8_0 (15.016) 超え可。

### 判定基準

| 判定 | 閾値 |
|------|------|
| Phase S 超え | eval_mean > 15.39 t/s |
| Phase D 超え | eval_mean > 15.03 t/s |
| Phase T-1 q8_0 超え | eval_mean > 15.016 t/s |
| threads 40 (baseline) 超え | 本 Phase 内 threads=40 条件との +1% 以上 |

## 実装方針

Phase T-2 の添付スクリプト群を雛形として複製・改修する。Explore で確認済みの構造を再利用。

### 固定パラメータ

Phase T-1 最良 = Phase T-2 の `layer × q8_0` 条件を踏襲:
- model: unsloth/Qwen3.5-122B-A10B-GGUF Q4_K_M
- ctx=32768, ub=1586, KV=q8_0 (k/v 両方), split-mode=layer
- flash-attn=1, parallel=1, poll=0, -ngl 999
- OT pattern: `blk.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
- numactl -N1 -m1
- llama.cpp binary: `6990e2f1f` (Phase T-1/T-2 と同一、再ビルド不要)

### スイープ対象

```
THREADS_LIST=(24 28 32 36 40)   # 5 条件
```

実行順序: `40 → 36 → 32 → 28 → 24` (baseline 40 を先頭で session drift 監視)

### 作成ファイル

**新規作成先**: `report/attachment/2026-04-22_<HHMMSS>_qwen3-122b-c3-phaseT3-threads/`

| ファイル | 派生元 | 主な変更 |
|---------|--------|---------|
| `start_phaseT3.sh` | `start_phaseT2.sh` | `SPLIT_MODE` 固定 (`layer`) を明記。`THREADS` 既存変数を明示的に `${THREADS:-40}` で再ラベル。`REMOTE_LOG` に `_t${THREADS}` を含める |
| `batch_phaseT3.sh` | `batch_phaseT2.sh` | 外ループを `THREADS_LIST=(40 36 32 28 24)` に置換。内ループ削除 (KV=q8_0 / SM=layer 固定)。`TAG_COND="t${THR}_kv${KV}_sm${SM}_ctx${CTX}_ub${UB}"` |
| `measure_phaseT3.sh` | `measure_phaseT2.sh` をそのままコピー | 無変更 |
| `run_all.sh` | `run_all.sh` をそのままコピー | 無変更 |
| `analyze_phaseT3.py` | `analyze_phaseT2.py` | `THREADS_LIST` 定数、pivot を行=threads に変更、参照値 `PEAK_PHASE_T2_BEST=14.672` 追加 |
| `plot_phaseT3.py` | `plot_phaseT2.py` | X 軸を threads、Y 軸 eval_tps の折れ線 + 誤差棒 |
| `plan.md` | 本計画の短縮版 | attachment に保存 |

### 起動コマンド骨子

```bash
numactl -N1 -m1 ./build/bin/llama-server \
  -m "<MODEL>" --jinja -ngl 999 -ot "<OT_REGEX>" \
  --split-mode layer --flash-attn 1 --poll 0 -b 1586 -ub 1586 \
  --n-predict 32768 --threads ${THREADS} \
  --ctx-size 32768 --parallel 1 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 \
  --port 8000 --host 0.0.0.0 \
  --alias "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M"
```

### 測定プロトコル (Phase T-2 踏襲)

- 各条件で warmup 2 run + eval 5 run (prompt ~1k)
- 所要時間: 5 条件 × 7 run × ~1.5 分 = **~55-65 分**
- 測定指標: eval_tps, prompt_tps (predicted_per_second / prompt_per_second)
- 出力: `out_T3_t${THR}_kv${KV}_sm${SM}_ctx32768_ub1586_{warmup,1k}/eval_run[1-5].json`
- 監視: dmon_runN.log (GPU), numastat (NUMA)

## 実行ステップ

1. **GPU サーバロック取得**: Skill `gpu-server` で `t120h-p100` を lock
2. **アタッチメントディレクトリ作成**: `report/attachment/2026-04-22_<HHMMSS>_qwen3-122b-c3-phaseT3-threads/`
3. **スクリプト複製・改修**: Phase T-2 から 6 ファイル複製、THREADS 可変化
4. **リハーサル**: `THREADS=40 bash start_phaseT3.sh` で healthy 起動と OOM 回避を確認後すぐに停止
5. **バッチ実行**: `bash batch_phaseT3.sh 2>&1 | tee batch_phaseT3.log` (背景実行、Monitor で進捗追跡)
6. **解析**: `python3 analyze_phaseT3.py && python3 plot_phaseT3.py`
7. **レポート作成**: `report/2026-04-22_<HHMMSS>_qwen3-122b-c3-phaseT3-threads.md`
   - タイトル: 「Phase T-3: threads 中間値スイープ (24-40)」(50 字以内)
   - **核心発見サマリに PNG 埋め込み** (CLAUDE.md ルール)
   - Phase D (15.03) / Phase S (15.39) / Phase T-1 q8_0 (15.016) / Phase T-2 最良 (14.672) との比較表を本文に明記
   - 「未検証事項」「検証完了後に実施すべき TODO」セクション必須
8. **ロック解放**: Skill `gpu-server` で unlock
9. **Discord 通知**: Skill `discord-notify` でレポート URL 付き通知

## 重要な参照ファイル

### 雛形元 (読み取り専用参照)

- `report/attachment/2026-04-22_165843_qwen3-122b-c3-phaseT2-splitmode/start_phaseT2.sh` — LAUNCH_CMD 構造
- `report/attachment/2026-04-22_165843_qwen3-122b-c3-phaseT2-splitmode/batch_phaseT2.sh` — スイープループ骨格
- `report/attachment/2026-04-22_165843_qwen3-122b-c3-phaseT2-splitmode/measure_phaseT2.sh` — prompt 送信・メトリクス収集 (無変更でコピー)
- `report/attachment/2026-04-22_165843_qwen3-122b-c3-phaseT2-splitmode/run_all.sh` — warmup/eval ラウンド (無変更でコピー)
- `report/attachment/2026-04-22_165843_qwen3-122b-c3-phaseT2-splitmode/analyze_phaseT2.py` — 統計・pivot 生成ロジック
- `report/attachment/2026-04-22_165843_qwen3-122b-c3-phaseT2-splitmode/plot_phaseT2.py` — bar chart 生成

### ドキュメント参照

- `REPORT.md` — レポートフォーマット (タイトル 50 字、PNG 埋め込み箇所)
- `CLAUDE.md` — GPU サーバは Skill 必須、スクリプトは相対パス
- `.claude/skills/gpu-server/` — ロック管理
- `.claude/skills/llama-server/` — 起動パラメータ参照
- `.claude/skills/discord-notify/` — 通知送信

## 検証 (End-to-End テスト)

1. **スクリプト構文**: `bash -n start_phaseT3.sh batch_phaseT3.sh run_all.sh measure_phaseT3.sh`
2. **起動リハーサル**: `THREADS=40 bash start_phaseT3.sh` で `/health` が 200 を返すこと、`llama-server` プロセスが t120h-p100 で走っていること
3. **バッチ完走**: 5 条件 × 7 run = 35 measurement すべて完了、各 `eval_run[1-5].json` に `predicted_per_second` フィールドがあること
4. **解析成果物**:
   - `summary_phaseT3.tsv` に 5 × 7 = 35 行 (条件別) 生成
   - `phaseT3_stats.csv` に 5 条件分の mean/stdev/min/max/median
   - `phaseT3_pivot.md` に threads 別の eval/prompt t/s 比較表
   - `phaseT3_eval_tps.png` に X=threads Y=eval_tps 折れ線
5. **レポート整合性**: 比較表に Phase D/S/T-1 q8_0/T-2 最良の 4 ベースラインすべて明記、判定列が各行に付与

## 期待される成果物

- 添付ディレクトリ: `report/attachment/2026-04-22_<HHMMSS>_qwen3-122b-c3-phaseT3-threads/`
- レポート: `report/2026-04-22_<HHMMSS>_qwen3-122b-c3-phaseT3-threads.md`
- 本 Phase の最良 threads が確定、Phase D/T-1 baseline との有意差の有無が明確化
- 後続 Phase (T-4 OT 代替 / T-5 ビルドフラグ) の優先度を最終判定できるデータ基盤
