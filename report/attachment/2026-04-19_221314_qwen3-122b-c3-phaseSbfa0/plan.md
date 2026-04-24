# Phase Sb-fa0 (拡張版): 候補 K (FA workspace の ub×ctx cross 項) 検証

## Context

直前レポート [Phase Sb-ctx-boundary](/home/ubuntu/projects/llm-server-ops/report/2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary.md) の「未検証事項」で**★最優先・次の推奨 Phase #1** として提示された項目を実施する。

Phase Sb-ctx-boundary では CUDA0 compute buffer について:
- 候補 J (9 層 SSM × VMM 非同期累積) を**棄却**
- **slope(ctx) の ctx 依存性**を発見: fa=1 で ctx=16k→0.010, 65k→0.400, 131k→0.650 MiB/ub
- ctx=32k 特異な区分項 δ(ub, ctx) ≈ +0.24 MiB @ ub=1586
- 新候補 K (FA/attention workspace の ub×ctx cross 項) を提示

**本 Phase の目的**: 候補 K の**強い予測**である「FA を無効にすれば slope(ctx) の ctx 依存性が消え、δ 項も消失する」を、fa=0 × ctx ∈ {16k, 32k, 65k, 131k} × ub ∈ {1584, 1585, 1586} の 12 条件で数値検証する。

fa=1 (前 Phase) との対照により:
- 候補 K **支持**: FA workspace が cross 項の主因 → 次 Phase で FA kernel dump
- 候補 K **棄却**: FA と無関係な別候補 (L/M) が必要 → 新候補の設計
- **部分支持**: slope の一部のみ FA 由来 → I-c との複合モデル確定

## 条件

| 項目 | 値 |
|---|---|
| FA | **0**（fa=1 との対照、前 Phase との唯一の差異） |
| ctx | 16384, **32768**, 65536, 131072 (前 Phase は 32k なし) |
| ub (= b) | 1584, 1585, 1586 |
| KV 量子化 | f16 (前 Phase 同一) |
| numactl | `--cpunodebind=1 --membind=1` |
| threads | 40 |
| poll | 0 |
| -ngl | 999 + OT_REGEX で MoE FFN CPU オフロード |
| 測定 | startup の sched_reserve ブロックのみ (eval なし) |
| 条件数 | **12** |
| 所要想定 | 25-30 分 (起動 2-5 min × 12) |

## 判定基準 (候補 K 3 条件)

前 Phase fa=1 の実測 slope:
- ctx=16k: 0.010 MiB/ub (≒ 0)
- ctx=32k: 区分線形 (Δ(1584→1585)=0.01, Δ(1585→1586)=0.24)
- ctx=65k: 0.400 MiB/ub
- ctx=131k: 0.650 MiB/ub

候補 K 支持条件:
1. **slope 縮小**: 全 ctx × 両 Δ で ≤ 0.05 MiB/ub (fa=1 ctx=16k レベル)
2. **ctx 非依存化**: 全 8 値 (4 ctx × 2 Δ) の max/min ≤ 2.0
3. **δ 項消失**: ctx=32k で |Δ(1585→1586)| ≤ 0.05 MiB

3/3 → support、1-2/3 → partial、0/3 → reject。

## Critical Files (参照する既存スクリプト)

- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary/start_phaseSbctx.sh` — 起動スクリプト、FLASH_ATTN/CTX_SIZE/BATCH_SIZE/UB_SIZE/MAX_ITER を環境変数で受け取る (行 10, 12, 14-15, 17)
- `.../batch_Sbctx.sh` — 9 条件ループ、`health_iter_for()` (行 25-32)、ssh cat によるログ転送 (行 84-86)、部分失敗継続
- `.../analyze_Sbctx.py` — sched_reserve regex 抽出 (行 50-64)、pivot/slope/verdict 出力 (行 91-176)
- `.../Sbctx_pivot.csv`, `.../Sbctx_slopes.csv` — fa=1 実測値 (対比表のハードコード元)
- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh` — GPU ロック管理
- `.claude/skills/llama-server/scripts/stop.sh` — llama-server 停止

## 作業ディレクトリ

```
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
WORKDIR=/home/ubuntu/projects/llm-server-ops/report/attachment/${TS}_qwen3-122b-c3-phaseSbfa0
```

`startup_logs/` サブディレクトリを作成。

## 実装ステップ

### 1. 準備

- GPU ロック取得: `bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100`
- `WORKDIR` 作成、plan.md コピー

### 2. スクリプト作成 (既存を diff ベースでコピー)

#### `start_phaseSbfa0.sh` (start_phaseSbctx.sh 派生)

- ヘッダコメント: 「Phase Sb-fa0: 候補 K (FA workspace の ub×ctx cross) 検証」
- `FLASH_ATTN="${FLASH_ATTN:-0}"` (デフォルト 0 に反転)
- `REMOTE_LOG=/tmp/llama-server_phaseSbfa0_fa${FLASH_ATTN}_ctx${CTX_SIZE}_b${BATCH_SIZE}_ub${UB_SIZE}.log`
- ログタグ: `[start_phaseSbfa0]`
- それ以外（MODEL_PATH、OT_REGEX、numactl、threads=40、poll=0、-ngl 999、f16 KV、--flash-attn 変数展開、MAX_ITER=120、OOM/ub-reject 検出、PID 取得）は**完全維持**

#### `batch_Sbfa0.sh` (batch_Sbctx.sh 派生)

- ヘッダ更新: 12 条件
- `CONDS` を 12 要素に拡張 (小 ctx → 大 ctx 順):
  ```
  "16384 1584" "16384 1585" "16384 1586"
  "32768 1584" "32768 1585" "32768 1586"
  "65536 1584" "65536 1585" "65536 1586"
  "131072 1584" "131072 1585" "131072 1586"
  ```
- `health_iter_for()` に `32768) echo 75 ;;` 追加 (= 375s)
- `FAIL_LOG=batch_Sbfa0_failures.tsv`
- 起動行: `FLASH_ATTN=0 CTX_SIZE=... UB_SIZE=... MAX_ITER=... bash start_phaseSbfa0.sh`
- remote cat: `/tmp/llama-server_phaseSbfa0_fa0_ctx${CTX}_b${UB}_ub${UB}.log`
- ローカル: `startup_logs/fa0_${TAG}.log`
- 完了メッセージ「all 12 conditions succeeded」

#### `analyze_Sbfa0.py` (analyze_Sbctx.py 派生)

- `CTXS = [16384, 32768, 65536, 131072]`
- 判定閾値を候補 K 用に置換:
  - `SLOPE_MAX_K = 0.05` (全 ctx × 両 Δ が 0.05 MiB/ub 以下)
  - `SLOPE_RATIO_K = 2.0` (max/min)
  - `DELTA_32K_UB1586_MAX = 0.05` (ctx=32k で δ 消失)
- glob を `fa0_ctx*_ub*.log` へ
- slope 集計を 4 ctx 対応に拡張、各 ctx の Δ と最大 slope を出力
- **新規判定ロジック**: 3 条件 (slope 縮小 / ctx 非依存 / δ 消失) → support/partial/reject
- 出力: `Sbfa0_pivot.csv`, `Sbfa0_slopes.csv`, `Sbfa0_verdict.txt`, `Sbfa0_candidate_K_verdict.txt`
- **対比表**: fa=1 の既知 slope を定数 dict で埋め込み (Sbctx_pivot.csv 参照不要、自己完結)、verdict 末尾に `fa1_slope vs fa0_slope` 4 ctx 表を出力

### 3. バッチ実行

```bash
cd ${WORKDIR}
bash batch_Sbfa0.sh 2>&1 | tee batch_Sbfa0.log
```

中断条件: 個別条件の OOM / タイムアウトは継続（`batch_Sbfa0_failures.tsv` に記録）。全 12 条件完了または明示的中断まで継続。

### 4. 分析

```bash
python3 analyze_Sbfa0.py
```

生成:
- `summary_Sbfa0.tsv` (12 行 × 10 列)
- `Sbfa0_pivot.csv` (4 ctx × 3 ub)
- `Sbfa0_slopes.csv` (4 行: ctx, v1584, v1585, v1586, Δpre, Δstep, ratio, peak_ub)
- `Sbfa0_verdict.txt` (既存 Sbctx_verdict.txt と同形式)
- `Sbfa0_candidate_K_verdict.txt` (新規: support/partial/reject の 3 値判定 + fa1 対比表)

### 5. 停止・解放

```bash
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 6. レポート作成

`report/${TS}_qwen3-122b-c3-phaseSbfa0.md` を REPORT.md 形式で作成。

必須セクション:
- 実施日時 (JST)、作業種別、GPU ロック取得/解放
- 添付ファイル一覧 (plan.md, start_phaseSbfa0.sh, batch_Sbfa0.sh, analyze_Sbfa0.py, batch_Sbfa0.log, summary_Sbfa0.tsv, Sbfa0_pivot.csv, Sbfa0_slopes.csv, Sbfa0_verdict.txt, Sbfa0_candidate_K_verdict.txt, startup_logs/ (12))
- 参照: 直前レポート、Phase Sbf3、Phase Sb-alloc、Phase Sb-ctx-boundary
- 前提・目的・成功条件
- 環境情報 (t120h-p100、llama.cpp ビルド、モデルパス)
- 再現方法 (上記 1-5)
- 実行結果サマリ (起動成功数、pivot 表、slope 表、候補 K 判定)
- ボトルネック・副次発見の分析 (support/partial/reject に応じた解釈)
- 採用判定・確定モデル更新
- **「未検証事項」セクション** (直前レポートから継承、本 Phase で潰したものに [x]、新規項目を追加)
- **「検証完了後に実施すべき TODO」セクション** (直前レポートから継承、本 Phase 結果を反映して更新)
- 補足 (核心発見サマリ、直前 Phase との対照、作業終了時点の状態)

## リスクと緩和

| リスク | 緩和 |
|---|---|
| fa=0 で KV cache 倍増 → ctx=131k OOM | health_iter_for=120 (600s)、条件単位 continue、OOM は failures.tsv に記録 |
| fa=0 × ctx=32k で 375s 超過 | `health_iter_for` を 90 (450s) にエスカレーション可 |
| fa=0 で nodes/splits 構造変化 | analyze 側で unique 値集合を出力し fa=1 (4473/136/77) と差分確認 |
| llama.cpp が fa=0 で特定 ub を拒否 | `start_phaseSbfa0.sh` 既存の -ub 下限拒否検出 (exit 3) で条件スキップ |

## Verification (end-to-end テスト)

1. `startup_logs/` に `fa0_ctx{16384,32768,65536,131072}_ub{1584,1585,1586}.log` の **12 ファイル**が存在する
2. 各ログに `sched_reserve:      CUDA0 compute buffer size = <N> MiB` 行が 1 つ以上ある
3. `summary_Sbfa0.tsv` が 12 行 + ヘッダ
4. `Sbfa0_pivot.csv` が 4 ctx × 3 ub の 4 行 + ヘッダ
5. `Sbfa0_slopes.csv` が 4 行 (各 ctx 1 行)
6. `Sbfa0_candidate_K_verdict.txt` に `candidate_K_status: (support|partial_support|reject)` が 1 行含まれる
7. verdict 末尾に fa=1 vs fa=0 slope 対比表 (4 ctx × 2 列) が含まれる
8. GPU ロックが正常に解放されている (`ls -la /tmp/gpu-server-locks/t120h-p100.lock` が無い)
9. `ps aux | grep llama-server` でリモート側プロセスが残っていない
