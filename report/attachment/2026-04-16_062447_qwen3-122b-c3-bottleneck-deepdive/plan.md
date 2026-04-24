# C-3 eval ボトルネック深掘り計測 (Phase A + Phase B)

## Context

レポート `report/2026-04-16_054649_qwen3-122b-c3-eval-bottleneck-profile.md` で、Qwen3.5-122B-A10B C-3 構成 (t120h-p100, PID 17780) の eval 頭打ちは「CPU expert 計算律速」と判定された。GPU sm% 平均 4-5%、CPU us 平均 89-93%。ただし **CPU 飽和の内訳**（FFN 行列演算 vs メモリ帯域待ち vs NUMA inter-socket 転送）、**llama-server の実スレッド数**、**NUMA バインディング影響量**、**CUDA3 txpci 高値の理由** は未検証のまま。

ユーザーの依頼は当該レポートの「未検証事項」から優先度の高い項目を実施すること。本プランは、この 4 項目を 2 段階（再起動不要の /proc 計測 → 必要に応じて numactl 再起動実験）で確定させる。

対象未検証事項と本プランでの扱い:

| # | 項目 | Phase | 扱い |
|---|------|-------|------|
| 1 | CPU 飽和の内訳 | A | /proc + vmstat 差分で定性判定（perf 不使用のため定量は不可） |
| 2 | NUMA 非バインディング影響量 | B | numactl 再起動で eval 速度差測定 |
| 3 | llama-server スレッド数実測 | A | `/proc/$PID/status` の Threads フィールド |
| 4 | メモリ帯域ボトルネック | A | numa_miss/foreign 差分で間接推定 |
| 5 | CUDA3 txpci の理由 | A | llama-server ログから output/lm_head 配置特定 |
| 6 | 量子化ダウン | — | 今回スコープ外（別レポート） |

## 方針

- **Phase A (必須、再起動不要)**: 稼働中 C-3 (PID 17780) に対して既存 `profile.sh` と同じ Run 0-3 構造で並列計測。`perf` / `numastat` / `mpstat` / `pidstat` を活用し、#1, #3, #4, #5 を一度に押さえる
- **Phase B (条件付き、要再起動)**: Phase A の NUMA 分布観測結果が「両ノード分散」の場合のみ、llama-server 停止 → `numactl --cpunodebind=0 --membind=0` 付き再起動 → 再計測。ユーザー承認を取ってから実施
- 事前インストール済みツール: `numactl 2.x`, `numastat`, `perf 5.15.198`, `mpstat`, `pidstat`（`kernel.perf_event_paranoid=1` に設定済）

## 実行手順

### S1. 事前確認

- `.claude/skills/gpu-server/scripts/lock.sh t120h-p100` でロック取得
- `ssh t120h-p100 'pgrep -af llama-server; curl -sf http://127.0.0.1:8000/health'` で PID 17780 と /health の生存確認
- `TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)`、`REPORT_NAME="${TS}_qwen3-122b-c3-bottleneck-deepdive"`、`ATTACH="report/attachment/${REPORT_NAME}"` を定義し `mkdir -p "$ATTACH"`
- プランファイル `/home/ubuntu/.claude/plans/humming-weaving-ullman.md` を `$ATTACH/plan.md` にコピー

### S2. Phase A スクリプト作成

既存 `report/attachment/2026-04-16_054649_qwen3-122b-c3-eval-bottleneck-profile/profile.sh` を土台に `$ATTACH/profile_phaseA.sh` を新規作成。追加する ssh 並列計測:

1. **`perf stat`**: `perf stat -a -e cycles,instructions,cache-misses,cache-references,LLC-loads,LLC-load-misses,mem-loads,mem-stores,node-loads,node-load-misses,dTLB-loads,dTLB-load-misses -- sleep 40` → `perfstat_run${R}.log`。CPU 飽和の内訳を定量（IPC、LLC miss 率、node-load-miss 率）。これが **#1, #4 の本命計測**
2. **`perf record` (Run 3 のみ)**: `perf record -g -F 99 -a -- sleep 40` → `perf.data`、`perf report --stdio --no-children` → `perf_report_run3.txt`。FFN 系（ggml_mul_mat, ggml_compute_forward）のホットスポット確認
3. **`numastat -p $LLAMA_PID`**: eval 開始直前と直後 → `numastat_pre_run${R}.log`, `numastat_post_run${R}.log`。ノード別 heap/stack/private/shared を MB 単位
4. **`mpstat -P ALL 1 40`**: → `mpstat_run${R}.log`。80 論理 CPU の per-core %usr, %sys, %iowait（top より機械可読）
5. **`pidstat -t -p $LLAMA_PID 1 40`**: → `pidstat_run${R}.log`。per-thread %CPU, CPU 番号の時系列
6. **`cat /proc/$LLAMA_PID/status`** 3 秒毎 14 回 → `status_run${R}.log`（Threads, voluntary_ctxt_switches, Cpus_allowed_list）
7. **`cat /proc/$LLAMA_PID/numa_maps`** eval 窓中 1 回 → `numa_maps_run${R}.txt`（モデル mmap の N0/N1 分布確認）
8. **`cat /proc/vmstat`** eval 前後 → `vmstat_{pre,post}_run${R}.log`（numa_hit/miss/foreign/local/other の delta）
9. **`cat /proc/$LLAMA_PID/sched`** 1 回 → `sched_run${R}.log`（nr_migrations で NUMA migration 回数確認）

既存の `nvidia-smi dmon`, `top -b` 2 本, `curl eval` はそのまま残し、`timeline.log` に eval 開始・終了時刻を記録する構造も流用。

**perf 使用時の注意**: `perf stat -a` / `perf record -a` はシステム全体対象。`sudo` 不要で動くが `kernel.perf_event_paranoid=1` が前提（確認済）。サンプリング頻度 99Hz は観測オーバーヘッド小。

### S3. Phase A 集計・判定スクリプト作成

`$ATTACH/summarize_phaseA.sh` を作成:

- `summary_gpu.tsv`, `summary_cpu.tsv`: 既存 profile.sh 相当（dmon / top を eval 窓で集計）
- `summary_perf.tsv`: Run 別の IPC, LLC miss rate, node-load-miss rate, dTLB miss rate（perfstat_run*.log から抽出）。**CPU 律速内訳判定の主データ**
- `summary_threads.tsv`: Run 別 Threads 値、ctxt_switches delta、pidstat から per-thread %CPU p50/p95/max
- `summary_numa.tsv`: numastat のノード別常駐 MB 、numa_hit/miss/foreign/local/other delta、foreign/local ratio
- `summary_percore.tsv`: mpstat から 80 論理コア毎の %usr 平均、NUMA 0 (0-19, 40-59) / NUMA 1 (20-39, 60-79) 集計
- `hotspot_run3.txt`: `perf report` 上位 30 関数（`ggml_*`, `llama_*`, `expert_*` のホット度）
- `phaseA_findings.md`: 下記「Phase B 実施判定基準」への適合と CPU 律速内訳の一次判定を 15-25 行で要約

**Phase B 実施判定基準（3 点中 2 点以上で「Phase B 意義あり」）**:

1. `numastat -p` でモデル常駐が N0 と N1 の両方に **各 30 GiB 以上** 分散している
2. `perf stat` の `node-load-misses / node-loads` 比が 5% 超、または `/proc/vmstat` delta で `numa_miss + numa_other` が `numa_hit` の 5% 以上
3. `mpstat -P ALL` / `pidstat -t` で llama-server スレッドが N0 側（0-19, 40-59）と N1 側（20-39, 60-79）両方に広く分布

### S4. Phase A 実行と解析

- 手元マシンから `bash $ATTACH/profile_phaseA.sh 17780` 実行（約 5-6 分）
- `bash $ATTACH/summarize_phaseA.sh` 実行（約 1 分）
- `$ATTACH/llama_log_analyze.sh`: `ssh t120h-p100 "grep -E 'load_tensors|output|lm_head|token_embd' /tmp/llama-server.log"` → `output_placement.txt`（#5 の CUDA3 txpci 理由確定）
- Run 0 の us が < 2% であることを観測オーバーヘッドの sanity として確認

### S5. Phase B 実施判断（自動）

`phaseA_findings.md` の Phase B 実施判定基準（3 点中 2 点以上）を自動評価:

- **2 点以上 → Phase B 実施**（S6 へ）
- **1 点以下 → Phase B スキップ**（未検証事項に「NUMA 偏在のため binding 効果薄いと推定」と記録し S7 へ）

判定結果と根拠は `phaseA_findings.md` に明記。

### S6. Phase B 実施

numactl は既にインストール済。

1. 現 llama-server 起動コマンドを `ssh t120h-p100 'cat /proc/17780/cmdline | tr "\0" " "'` で取得し `$ATTACH/c3_cmdline.txt` に退避
2. `$ATTACH/rollback_c3.sh`（numactl なしで元の C-3 を再起動するスクリプト）を先に用意
3. `.claude/skills/llama-server/scripts/stop.sh t120h-p100` で停止
4. ssh で `numactl --cpunodebind=0 --membind=0 -- ./build/bin/llama-server <元の全引数>` を nohup で起動
5. `/health` 200 を 120 秒以内に確認できなければ rollback_c3.sh を自動実行しロック保持のまま中断
6. `profile_phaseA.sh` を新 PID で再実行し、出力ファイルは `*_phaseB_*` プレフィックス
7. Phase A/B の中央値で eval t/s 差分を比較

### S7. 終了処理

Phase B 実施時の稼働構成判定（自動）:

- eval t/s 中央値が Phase A 比 **+3% 以上**（= 有意改善）→ numactl 付きで稼働継続
- それ以外（±3% 内 or 劣化）→ `rollback_c3.sh` で元の C-3 に戻して稼働継続

判定根拠はレポート本文と `phaseA_findings.md` に記録。

- レポート `report/${REPORT_NAME}.md` を REPORT.md の規約に沿って作成。章構成:
  - 添付ファイル / 参照（前身レポート 054649）/ 前提・目的 / 環境情報 / 計測手順 / 実行結果サマリ（Phase A 表, Phase B 表）/ ボトルネック内訳判定 / 結論 / **未検証事項** / **検証完了後に実施すべき TODO** / 補足
  - 未検証事項には量子化ダウン（#6）、perf 本格導入、pcm-memory 実測を継続項目として列挙
  - TODO には前身の C-4 実験や start.sh プリセット化など既知項目を継承
- ロック解放

## 成功条件

- #1: `perf stat` の IPC + LLC miss rate + node-load-miss rate + `perf report` hotspot から、CPU 飽和が「FFN 計算主（IPC 高・miss 低）」「メモリ帯域待ち主（LLC miss 高・IPC 低）」「NUMA inter-socket 主（node-load-miss 高）」のいずれかに定量分類
- #3: `/proc/$PID/status` の Threads 値と、`pidstat -t` の実稼働スレッド数が確定
- #4: `numastat -p` で N0/N1 それぞれの常駐 MB が確定し、メモリ帯域律速の仮説への一次回答が得られる
- #5: llama-server ログから output / lm_head の配置 GPU が 1 個に特定（CUDA3 txpci の説明）
- Phase B 実施時: numactl 有無で eval t/s 中央値の差分を ±3% / +5% 超 / 劣化 のいずれかに判定

## 失敗条件・リスク

- Phase B の numactl 付き再起動で /health が 60 秒以内に 200 を返さない → rollback_c3.sh 即実行、Phase B 結果は「環境制約により未計測」として未検証事項に残す
- `sudo apt install numactl` が sudo 権限不足で失敗 → Phase B 全スキップ
- 計測中に llama-server が OOM / クラッシュ → ロック保持のまま現状記録して中断、rollback_c3.sh で復旧

## 計測所要時間見積もり

- Phase A 実計測: 約 6 分（idle 20s + eval×3 40s + cooldown 60s×2 + 集計）
- Phase A 解析＋ユーザー確認: 5-10 分
- Phase B（実施時のみ）: 再起動 2 分 + 計測 6 分 + 集計 1 分 = 約 9 分
- レポート作成: 15-20 分
- **合計**: Phase A のみで完結時 約 30 分、Phase B まで 約 55-65 分

## 修正／新規作成ファイル

**新規 (attachment 配下 `report/attachment/${REPORT_NAME}/`)**:

- `plan.md`（本プランのコピー）
- `profile_phaseA.sh`, `summarize_phaseA.sh`, `llama_log_analyze.sh`
- `rollback_c3.sh`, `c3_cmdline.txt`（Phase B 実施時のみ）
- ログ: `dmon_run{0-3}.log`, `top_system_run{0-3}.log`, `top_pid_run{0-3}.log`, `perfstat_run{0-3}.log`, `perf.data` / `perf_report_run3.txt`（Run 3 のみ）, `numastat_{pre,post}_run{0-3}.log`, `numa_maps_run{0-3}.txt`, `vmstat_{pre,post}_run{0-3}.log`, `mpstat_run{0-3}.log`, `pidstat_run{0-3}.log`, `status_run{0-3}.log`, `sched_run{0-3}.log`, `eval_run{1-3}.json`, `timeline.log`
- 集計: `summary_gpu.tsv`, `summary_cpu.tsv`, `summary_perf.tsv`, `summary_threads.tsv`, `summary_numa.tsv`, `summary_percore.tsv`, `hotspot_run3.txt`, `output_placement.txt`, `phaseA_findings.md`
- Phase B 実施時は上記の `*_phaseB_*` プレフィックス版を追加

**新規 (report 本体)**:

- `report/${REPORT_NAME}.md`

**修正なし**: 既存 `profile.sh` と既存レポート本文は touch しない（参照のみ）。

## 参照する既存ファイル

- `/home/ubuntu/projects/llm-server-ops/report/2026-04-16_054649_qwen3-122b-c3-eval-bottleneck-profile.md` — 前身レポート
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-16_054649_qwen3-122b-c3-eval-bottleneck-profile/profile.sh` — 計測スクリプト雛形
- `/home/ubuntu/projects/llm-server-ops/REPORT.md` — レポート作成規約
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/lock.sh` — ロック取得
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh` — Phase B 時の停止

## 検証（end-to-end 確認）

1. Phase A 完了時に `summary_threads.tsv` / `summary_numa.tsv` が非空で生成されていること
2. `output_placement.txt` に output もしくは lm_head の行が 1 件以上含まれ、CUDA 番号が 1 個特定できること
3. Run 0 (idle) の CPU us が < 2% で、観測オーバーヘッドが誤差内であること
4. Phase B 実施時は `/health` 200 応答と eval 3 回成功、`eval_phaseB_run{1-3}.json` の `eval/s` が取得できること
5. レポート `report/${REPORT_NAME}.md` に「未検証事項」「検証完了後に実施すべき TODO」セクションが存在すること
