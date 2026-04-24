# Phase H: idle 劣化の再現性検証と `--poll` 値比較

## Context

Phase G (`report/2026-04-17_035831_qwen3-122b-c3-phaseG-longevity.md`) で以下 2 点が未検証項目の最優先に上がった。

- **idle 劣化の再現性検証**: G_aged_t96 (96m idle) で 14.027 t/s (−5.6%)、Phase E C-E1 (60m idle) で 14.27 t/s (−5.1%) が観測された一方、G1 (eval あり 60m) は 14.867 → 14.871 でフラット。「時間経過」ではなく「idle 稼働」が劣化原因の可能性
- **`--poll` パラメータ調査**: 現在は `--poll 0` 固定（polling なし）。idle 時にスレッドが sleep → 再開時のスレッド affinity 復帰遅延が劣化原因の仮説がある。`--poll 50` で防止できるか検証

本 Phase では A/B テスト設計で両仮説を同時に検証する。

## 目的

1. fresh restart → idle 60 分後の eval 速度を計測し、**idle 劣化の再現性**を確認
2. `--poll 0` vs `--poll 50` の同一条件比較で、**poll 値が idle 劣化を防ぐか**を検証
3. 結果をもとに C-D3 の運用推奨（`--poll` デフォルト値、定期再起動の要否）を確定

## 実験設計

### 計測条件

| ID | 起動引数 | t=0 計測 | idle | t=60 計測 |
|:---|:--------|:-------:|-----:|:--------:|
| H1a | `--poll 0` (現行) | ◯ | 60 分 | ◯ (H1b) |
| H2a | `--poll 50` | ◯ | 60 分 | ◯ (H2b) |

- 計測は Phase G と同一プロトコル: `"Write a short haiku about autumn."`, `max_tokens=256`, 3 run × 60 秒 cooldown
- 各測定ポイント ~5 分、idle 60 分、restart/起動 ~3 分 → **合計 ~2 時間 30 分**
- 並列不可（同一サーバ t120h-p100）。直列実行

### 成功条件

- `idle_degraded`: `median(t=60) ≤ median(t=0) × 0.96` かつ差分 ≥ 0.2 t/s
- `idle_stable`: 差分 < 0.1 t/s (1% 以内)

### 判定マトリクス

| H1 (poll=0) | H2 (poll=50) | 結論 |
|:-----------:|:------------:|:-----|
| 劣化あり | 劣化なし | **`--poll 50` が idle 劣化を防ぐ**（対策として採用） |
| 劣化あり | 劣化あり | idle 劣化は poll 以外（THP/page migration 等） |
| 劣化なし | 劣化なし | Phase E/G_aged 劣化は別要因（前プロセス履歴・環境ノイズ） |
| 劣化なし | 劣化あり | `--poll 50` が悪化要因 → 採用不可 |

## ファイル構成

新規作成（`report/attachment/2026-04-17_<HHMMSS>_qwen3-122b-c3-phaseH-idle-poll/` 配下）:

- **`plan.md`** — 本計画の清書版
- **`start_phaseH.sh`** — `start_phaseF.sh` を拡張。`VARIANT=H1`/`H2` で `--poll 0`/`--poll 50` を切替。他パラメータ（`numactl --cpunodebind=1 --membind=1 --`, `--threads 40`, `--flash-attn 1`, `-b 8192 -ub 8192` 等）は同一
- **`measure_phaseH.sh`** — `measure_phaseG.sh` をそのままコピー（スクリプト内容変更なし）
- **`run_phaseH.sh`** — 全体オーケストレーション。ロック取得 → H1 起動 → t=0 計測 → sleep 3600 → t=60 計測 → stop → H2 起動 → t=0 計測 → sleep 3600 → t=60 計測 → stop → ロック解放
- **レポート本体** — `report/2026-04-17_<HHMMSS>_qwen3-122b-c3-phaseH-idle-poll.md`（Phase G 踏襲、「未検証事項」「検証完了後に実施すべき TODO」セクション必須）

## 再利用する既存資産

- `report/attachment/2026-04-17_012859_qwen3-122b-c3-phaseF-reproducibility/start_phaseF.sh` — 起動スクリプトのベース
- `report/attachment/2026-04-17_035831_qwen3-122b-c3-phaseG-longevity/measure_phaseG.sh` — 計測スクリプト（そのまま流用）
- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh` — t120h-p100 ロック管理
- `.claude/skills/llama-server/scripts/stop.sh` — llama-server 停止

## 実行ステップ

1. **ロック取得**: `bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100`
2. **既存 llama-server 停止**: `bash .claude/skills/llama-server/scripts/stop.sh t120h-p100`
3. **添付ディレクトリ作成 + スクリプト配置**
4. **H1 phase (poll=0)**:
   - 起動: `bash start_phaseH.sh H1 </dev/null > /tmp/start_H1.log 2>&1`
   - PID 取得: `ps -eo pid,comm,args | awk '$2=="llama-server"'`
   - t=0 計測: `bash measure_phaseH.sh $PID H1_t0`
   - idle 60 分待機（eval 投入なし）
   - t=60 計測: `bash measure_phaseH.sh $PID H1_t60_idle`
   - 停止: `bash .claude/skills/llama-server/scripts/stop.sh t120h-p100`
5. **H2 phase (poll=50)**: 4 と同様の手順で `VARIANT=H2`
6. **ロック解放**: `bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100`
7. **レポート作成**

### Bash ツール運用上の注意

- `start_phaseH.sh` は `</dev/null > /tmp/start_HN.log 2>&1` でリダイレクトしないと Bash ツールで意図せずバックグラウンド化される（Phase G で既知）
- 長時間 sleep (3600 秒) は `run_in_background: true` で回し、`ScheduleWakeup` で ~2.5h 後に回収するか、継続監視する
- sudo 操作は発生しない想定（既存 llama-server 起動/停止は llm ユーザー権限）

## リスク

- **時間コスト ~2.5 時間**: t120h-p100 を 2.5h 占有。他作業不可
- **idle 劣化が再現しない**: Phase E / G_aged が偶発ノイズだった可能性。この場合「再現性なし、現行 `--poll 0` 維持、定期再起動不要」で結論
- **`--poll 50` がベース速度を下げる**: H2a (t=0) が H1a (t=0) より 1% 以上低ければ不採用
- **prompt キャッシュ warm-up**: t=60 計測 Run 1 は warm-up 直後になるため、`predicted_per_second` (eval) のみで判定

## 失敗時の次ステップ

- **両条件とも劣化なし** → Phase I で 2 時間超の eval あり稼働試験に移行
- **両条件とも劣化** → Phase I で `/proc/$PID/sched`・`perf stat -e node-load-misses,cache-misses`・THP 状態を idle 中/再開後で差分比較
- **H2 のみ劣化なし** → `--poll 50` を start.sh の推奨デフォルトに昇格候補。eval ベース速度への影響を Phase I で 2 時間連続稼働で追加検証

## 検証方法（end-to-end）

1. ロック取得後、`ssh t120h-p100 "ps aux | grep llama-server | grep -v grep"` で既存プロセスなしを確認
2. 各計測後、`ls out_{H1,H2}_{t0,t60_idle}/eval_run{1,2,3}.json` で 12 ファイル全て生成されていることを確認
3. `jq '.timings.predicted_per_second' out_*/eval_run*.json` で速度値を抽出、中央値比較
4. `/proc/$PID/status` の `Cpus_allowed_list` が全サイクルで `20-39,60-79` であることを確認（NUMA 拘束維持の検証）
5. ロック解放後、`bash .claude/skills/gpu-server/scripts/check.sh t120h-p100` でロック解除を確認

## 重要ファイル一覧

- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-17_035831_qwen3-122b-c3-phaseG-longevity/measure_phaseG.sh`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-17_012859_qwen3-122b-c3-phaseF-reproducibility/start_phaseF.sh`
- `/home/ubuntu/projects/llm-server-ops/report/2026-04-17_035831_qwen3-122b-c3-phaseG-longevity.md`
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/lock.sh`
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh`
- `/home/ubuntu/projects/llm-server-ops/CLAUDE.md`
- `/home/ubuntu/projects/llm-server-ops/REPORT.md`
