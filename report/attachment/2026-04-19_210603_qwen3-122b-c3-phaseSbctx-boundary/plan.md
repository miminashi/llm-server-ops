# Phase Sb-ctx-boundary: 候補 J の ctx 非依存性検証

## Context

直前レポート [report/2026-04-19_203607_qwen3-122b-c3-phaseSb-alloc.md](../../projects/llm-server-ops/report/2026-04-19_203607_qwen3-122b-c3-phaseSb-alloc.md) で、CUDA0 compute buffer の ub*=1586 境界の真因を「**候補 J: 9 層 SSM × VMM granularity (2 MiB) 非同期累積**」と「**候補 I-c: build_graph 内 ub 依存離散処理**」の 2 つに絞り込んだ。Phase Sb-alloc の未検証事項「新規項目」の ★最優先 3 つ:

1. Phase Sb-tensor-dump (debug build 必要、2-3 時間)
2. **Phase Sb-ctx-boundary (1.5 時間)** ← 本 Phase で実施
3. Phase Sb-fa0 (1 時間)

ctx-boundary を先行実施する理由:
- 候補 J は「境界位置 ub*=1586 が ctx 非依存」という強い予測を持つ
- 既存 release build をそのまま使用可（debug build 不要）
- 1.5 時間の最短コスト。結果に応じて tensor-dump / fa0 の実施要否を判断可能
- 候補 J の ctx 非依存予測が崩れれば tensor-dump の優先度が跳ね上がる

本 Phase の目的:
1. ctx ∈ {16384, 65536, 131072} × ub ∈ {1584, 1585, 1586} の 9 条件で startup のみ実施
2. CUDA0 compute buffer の step 位置が全 ctx で ub=1586 に一致するか確認
3. 候補 J の ctx 非依存性予測を支持 / 棄却する

## Critical files

- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok/start_phaseSbf3.sh` — 起動スクリプトの土台（ほぼそのまま流用、ログプレフィックスのみ変更）
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok/batch_boundary_fine3.sh` — バッチスクリプトの土台（eval 部分を削除、ctx タイムアウト可変化、部分失敗 continue 化）
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/lock.sh` — GPU ロック取得（t120h-p100）
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh` — llama-server 停止

## 条件

| 変数 | 値 |
|---|---|
| ctx | 16384, 65536, 131072 |
| ub (=-b=-ub) | 1584, 1585, 1586 |
| fa | 1 (Sbf3 と同一 baseline) |
| KV cache | f16 (Sbf3 と同一) |
| NUMA | `numactl --cpunodebind=1 --membind=1 --` |
| threads | 40 |
| poll | 0 |
| eval | **実施しない**（compute buffer と graph nodes/splits のみ記録） |

合計 9 条件、所要約 20 分（ロック取得 + スクリプト実行 + 解放）。

## 実施手順

### 1. GPU ロック取得
```bash
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 2. 作業ディレクトリとスクリプト作成

`report/attachment/<TS>_qwen3-122b-c3-phaseSbctx-boundary/` を作成:
- `start_phaseSbctx.sh` — Sbf3 からの差分: ログプレフィックス `phaseSbctx_`、`MAX_ITER` を 120 (600s) に拡張（ctx=131k 対応）
- `batch_Sbctx.sh` — 9 条件ループ、eval 省略、ctx 依存タイムアウト、部分失敗 continue
- `startup_logs/` — 出力先

### 3. バッチ実行
```bash
cd report/attachment/<TS>_qwen3-122b-c3-phaseSbctx-boundary/
bash batch_Sbctx.sh 2>&1 | tee batch_Sbctx.log
```

ctx=16k→65k→131k の順（失敗時でも低 ctx データは確保）。タイムアウトは ctx=16k:300s, 65k:450s, 131k:600s。1 条件失敗時は `batch_Sbctx_failures.tsv` に記録し次条件へ。

### 4. データ集約

`startup_logs/fa1_ctx*.log` から `awk` で以下を抽出し `summary_Sbctx.tsv` 化:
- ctx, ub, cuda0_MiB (sched_reserve), graph nodes, graph splits (pp, tg)

### 5. 分析 `analyze_Sbctx.py`

出力:
- `Sbctx_pivot.csv` — ctx × ub の CUDA0 MiB ピボット（3×3）
- `Sbctx_slopes.csv` — 各 ctx の Δ(1584→1585), Δ(1585→1586)
- `Sbctx_verdict.txt` — 候補 J 支持/棄却判定

判定基準（決定論的、1 run のため統計検定は不可）:
- 全 3 ctx で `|Δ(1584→1585)| ≤ 0.05 MiB`（平坦域）
- 全 3 ctx で `Δ(1585→1586) ≥ 0.15 MiB`（step）
- 全 3 ctx で `Δ(1585→1586) / |Δ(1584→1585)| ≥ 5`
- 全 3 ctx で step 位置（argmax Δ）= 1586

全て満たせば **候補 J 支持**。1 ctx でも step 位置が 1585 or 1587 にずれれば **候補 J 棄却**。

### 6. 停止とロック解放
```bash
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 7. レポート作成

`report/<TS>_qwen3-122b-c3-phaseSbctx-boundary.md` を [REPORT.md](../../projects/llm-server-ops/REPORT.md) に従って作成。「未検証事項」と「検証完了後に実施すべき TODO」セクションを含める（Phase Sb-alloc と同様）。結果に応じて次 Phase（候補 J 支持なら Sb-fa0 で補強、棄却なら Sb-tensor-dump へ直行）を提示。

## 想定リスクと緩和策

| リスク | 緩和策 |
|---|---|
| ctx=131072 OOM / 起動 600s 超 | 条件単位 continue、低 ctx データで候補 J 検証可能 |
| ub=1584 が llama.cpp 下限拒否 | start_phaseSbctx.sh 既存の `-ub lower-bound rejection` 検出維持。最悪 {1585, 1586} のみで「step 位置一致」検証可能 |
| llama-server 残留プロセス | 条件開始前に `SKILL_STOP` + sleep 5 |
| sched_reserve 欠落 | 転送後に grep 検証、欠落時は failures.tsv に記録 |
| 他ユーザー占有 | lock.sh で排他、取得失敗時即終了 |

## 検証方法（end-to-end）

1. `startup_logs/fa1_ctx*.log` × 9 ファイルがすべて生成される
2. 各ログに `sched_reserve: CUDA0 compute buffer size = ... MiB` が含まれる
3. `summary_Sbctx.tsv` が 9 行 + ヘッダ
4. `Sbctx_verdict.txt` に `candidate_J_support: True/False` と `peak_ub_per_ctx: {...}` が記録される
5. レポートに「未検証事項」「検証完了後に実施すべき TODO」が含まれる

## 成果物一覧

- `start_phaseSbctx.sh`
- `batch_Sbctx.sh`
- `startup_logs/fa1_ctx{16384,65536,131072}_ub{1584,1585,1586}.log` (9 ファイル)
- `batch_Sbctx.log`, `batch_Sbctx_failures.tsv`
- `summary_Sbctx.tsv`
- `analyze_Sbctx.py`
- `Sbctx_pivot.csv`, `Sbctx_slopes.csv`, `Sbctx_verdict.txt`
- `plan.md` (この plan ファイルのコピー)
- `report/<TS>_qwen3-122b-c3-phaseSbctx-boundary.md`

## 明示的な非対象

- fa=0 系の検証（Phase Sb-fa0 で別実施）
- debug build + per-node dump（Phase Sb-tensor-dump で別実施）
- eval benchmark（reproducibility は Phase S-eval で別実施）
- ctx=32768 は Phase Sb-fine3 で既に 4 点取得済み、本 Phase では重複回避
