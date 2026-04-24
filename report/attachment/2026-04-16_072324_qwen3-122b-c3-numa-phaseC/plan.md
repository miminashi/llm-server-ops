# Qwen3.5-122B C-3 未検証事項の深掘り検証計画（NUMA 最適化 Phase C）

## Context

前身レポート [2026-04-16_062447_qwen3-122b-c3-bottleneck-deepdive.md](../../projects/llm-server-ops/report/2026-04-16_062447_qwen3-122b-c3-bottleneck-deepdive.md) で、C-3 構成のボトルネックは **NUMA inter-socket 転送 → OpenMP barrier 拡大** と定量分類され、採用構成 Phase B（`numactl --cpunodebind=1 --membind=1`）で +4.3% 改善を得た。しかし結論セクションで「本質的な最適化は両ノードを使いつつ NUMA リモートアクセスを減らす方向」と指摘されており、その候補（`--numa distribute` / `--interleave=all`）は未検証。加えて Phase A の 11.03 t/s が前身 C-3 の 11.94 t/s を下回ったため、observation-free ベースラインの確立が前提として要る。

本計画では未検証事項のうち**推論速度への寄与が大きい 3 項目** を Phase C として実施する:

1. **C-C1 observation-free Phase B 再測定** — 観測負荷を除いた真の Phase B 基準値を得る（他 2 比較の基準線）
2. **C-C2 `numactl --interleave=all` 試行** — 両ノードメモリストライプで 80 論理 CPU を活用
3. **C-C3 llama.cpp `--numa distribute` 試行** — llama.cpp 側 NUMA-aware スレッド配置

`--threads` 明示値比較は Phase A で「スレッド数 166 固定・メモリ律速」と判明済みのため今回は除外。量子化変更・pcm-memory・大コンテキストは高コスト低即効で次回以降。

## 実施対象と判定基準

| 実験 | 起動方式 | 期待値 | 採用判定 |
|------|---------|--------|---------|
| C-C1 | Phase B と同一（`numactl -N1 -m1`） | Phase B の真値基準線 | 観測負荷 X% を算出するのみ |
| C-C2 | `numactl --interleave=all` のみ（cpunodebind なし）| 両ノード 80 論理 CPU 稼働、node-load-miss rate > 5% でも IPC 改善で eval +3% 超 | C-C1 比 +3% 超で採用 |
| C-C3 | `--numa distribute` + `numactl` なし | llama.cpp がスレッドを両ノード分散、ページ配置も分散 | C-C1 比 +3% 超で採用 |

全実験 3 run 中央値で評価。

## 計測プロトコル（共通）

各実験は次の流れ:

1. GPU サーバロック取得: `.claude/skills/gpu-server/scripts/lock.sh t120h-p100`
2. 既存 llama-server 停止: `.claude/skills/llama-server/scripts/stop.sh t120h-p100`
3. モデルメモリの ページキャッシュ/メモリ状態を揃えるため 60 秒待機
4. 各構成で直接 ssh 起動（start.sh は numactl/--numa 未対応のため手動）
5. `/health` 200 を 60 秒以内に確認
6. **観測負荷最小化版 eval 計測**（perf record/stat・mpstat・pidstat・numastat は**使わない**。`nvidia-smi dmon` のみ 20 秒間 background、Run 3 のみ `/proc/$PID/status` を 1 回取得）
7. 3 run: 各 run 前に 60 秒 cooldown、eval プロンプト `"Write a short haiku about autumn."`、`max_tokens=256`、`stream=false`
8. curl レスポンスの `timings.predicted_per_second` と `timings.prompt_per_second` を記録
9. 必要な場合のみ参考計測として perf stat 1 回（Run 2 のみ、C-C1 で観測負荷量を測る目的）

### 起動コマンドテンプレ

共通部分（MODEL_PATH, -ot 正規表現, その他 C-3 パラメータ）は前身レポート l.184-197 を完全踏襲。プレフィックス/オプションのみ差し替え:

- **C-C1**: `numactl --cpunodebind=1 --membind=1 -- ./build/bin/llama-server ...`
- **C-C2**: `numactl --interleave=all -- ./build/bin/llama-server ...`
- **C-C3**: `./build/bin/llama-server ... --numa distribute`（numactl なし）

llama.cpp の `--numa` サポート確認は事前に `ssh t120h-p100 'cd ~/llama.cpp && ./build/bin/llama-server --help 2>&1 | grep -i numa'` で行う。

## 計測スクリプト

前身レポートの `profile_phaseA.sh` は再利用せず、**新規に軽量版スクリプト `measure_phaseC.sh` を作成**。理由: Phase A/B で perf/mpstat/pidstat/numastat の並列実行が観測負荷源と推定されたため、それらを除外したベースライン計測が本計画の目的の一つ。既存スクリプトからの流用は以下:

- eval 呼び出し・cooldown の時間管理構造
- dmon 起動・停止の wrap
- 集計パート（中央値・p95 算出）は `summarize_phaseA.sh` の eval TSV 部分を参考に縮小版

成果物は各構成につき:
- `phaseC_<tag>_eval_run{1,2,3}.json` — curl レスポンス
- `phaseC_<tag>_dmon_run{1,2,3}.log` — nvidia-smi dmon
- `phaseC_<tag>_status_run3.txt` — /proc/$PID/status（Threads と Cpus_allowed_list のみ確認）
- `phaseC_<tag>_perfstat_run2.txt` — C-C1 のみ（観測負荷量の同定）
- `phaseC_<tag>_cmdline.txt` — 起動コマンドライン
- `phaseC_timeline.log` — 全 run のタイムスタンプ

tag は `C1_numactl_N1M1_noobs`, `C2_interleave_all`, `C3_numa_distribute`。

## 採用判定フロー

1. C-C1 中央値を基準線 **T_base** とする
2. C-C2/C-C3 のいずれかが T_base × 1.03 以上で、かつ VRAM OOM 等の異常なし
3. 該当する最速構成に切替、両方該当なら interleave 系を優先（メモリストライプで長時間安定性が期待できるため）
4. いずれも基準未達なら Phase B 構成のまま継続、レポートには観測負荷量の真値のみ反映
5. 採用構成に切替える場合は手動 ssh 起動で確認、**start.sh のプリセット化は TODO 行き**（本計画のスコープ外）

## 重要ファイル・利用する既存コード

- **既存（変更しない）**:
  - `.claude/skills/gpu-server/scripts/lock.sh`, `unlock.sh` — ロック制御
  - `.claude/skills/llama-server/scripts/stop.sh` — プロセス停止
  - `report/attachment/2026-04-16_062447_qwen3-122b-c3-bottleneck-deepdive/start_phaseB.sh` — 起動コマンドライン参照元
  - `report/attachment/2026-04-16_062447_qwen3-122b-c3-bottleneck-deepdive/summarize_phaseA.sh` — eval TSV 集計ロジック参照元
- **新規作成（添付ファイル）**:
  - `measure_phaseC.sh` — 軽量計測（dmon + curl eval + status スナップ）
  - `start_phaseC_<tag>.sh` — 各構成の起動ラッパー（C1/C2/C3 の 3 本）
  - `summarize_phaseC.sh` — 3 構成横断の eval 中央値表生成

## レポート

作業完了後、新規レポート `report/<timestamp>_qwen3-122b-c3-numa-phaseC.md` を作成。含めるセクション:

- 添付ファイル（本プラン + 計測スクリプト群 + 全 run ログ）
- 参照（前身・系統の全レポート）
- 前提・目的（C-C1/C2/C3 の仮説）
- 環境情報
- 計測手順
- 実行結果サマリ（3 構成 × 3 run の eval t/s 表、観測負荷量、GPU 利用率、status スナップ抜粋）
- 採用判定
- 採用した場合の起動コマンド
- **未検証事項セクション**（前身レポートから継続の項目 + 本計画で新たに発生した項目を箇条書き）
- **検証完了後に実施すべき TODO セクション**（前身継続 + 新規発見）
- 補足（作業終了時のプロセス状態・ロック状態）

## 検証手順（エンドツーエンド）

1. llama.cpp `--numa` ヘルプ確認（事前）
2. `.claude/skills/gpu-server/scripts/lock-status.sh` でロック競合なし確認
3. lock.sh → stop.sh → 各構成の start_phaseC_<tag>.sh → wait-ready → measure_phaseC.sh → 次構成へ
4. 3 構成完了後 summarize_phaseC.sh で表生成
5. 採用判定に応じて最終構成に切替 or Phase B 構成に戻して稼働継続
6. ロック解放後にレポート執筆
7. 作業ログでは起動コマンド・curl レスポンス・dmon サマリを全て添付、観測負荷量（C-C1 の perfstat 有無差分）を定量化して末尾に記載

## 想定される失敗モードとハンドリング

- **`--numa distribute` 非サポート**: llama-server ビルドが古く `--numa` 未実装の可能性。`--help` に項目なければ C-C3 スキップ、レポートに「未実装でスキップ」と記載
- **`--interleave=all` 起動失敗**: numactl 単体の interleave は問題ないはず。失敗時は `numactl --interleave=all --cpunodebind=0,1` に fallback
- **OOM / VRAM 不足**: C-C2/C-C3 はモデル常駐位置が動く可能性。起動時の `nvidia-smi` で配分確認、Phase B との差があれば記録
- **1 構成で 5 分以上応答なし**: stop.sh → 次構成へ、該当構成は「不安定」と記録
- **全体時間予算**: 停止+cooldown 60s + 起動 30s + 3 run × (40s eval + 60s cool) = 約 6 分/構成 + 集計 → 約 25 分想定。ロックは最大 40 分まで保持。
