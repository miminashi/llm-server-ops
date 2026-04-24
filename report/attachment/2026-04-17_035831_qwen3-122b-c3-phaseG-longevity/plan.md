# Phase G: C-D3 長時間稼働劣化の定量化

## Context

Phase F (2026-04-17 JST) で C-D3 fresh restart 直後の eval 中央値は 14.80 t/s と確定。一方、Phase E 副次観測で「fresh から 1 時間稼働後 14.27 t/s (−5.1%)」、Phase F の F2 (`--numa isolate`) 継続 10 分で −1.5% という劣化兆候があり、**最優先の未検証事項**として「1 時間超の連続稼働試験 (C-D3 構成)」が残っている。

本 Phase G はこれを定量化し、劣化が再現するなら定期再起動運用を TODO 化する。副次的に「既存の長時間稼働プロセス (PID 65837, etime 5h46m+) を先に計測」して貴重な aged サンプルも確保する。

前身: [Phase F](../projects/llm-server-ops/report/2026-04-17_012859_qwen3-122b-c3-phaseF-reproducibility.md)

## 実験タイムライン（総計 ~1h15min）

| フェーズ | タグ | 経過時間 (fresh=t0 基準) | 所要 | 内容 |
|---|---|---|---|---|
| G0 | `G0_aged_5h46m+` | (既存プロセス, 現在 5h46m+) | ~5min | stop する前に現状計測 |
| restart | — | — | ~2min | stop.sh → start_phaseF.sh F1 → /health |
| G1a | `G1a_fresh_t0` | 0 | ~5min | 起動直後 |
| idle | — | — | 10min | |
| G1b | `G1b_fresh_t15` | 15 | ~5min | |
| idle | — | — | 10min | |
| G1c | `G1c_fresh_t30` | 30 | ~5min | |
| idle | — | — | 25min | |
| G1d | `G1d_fresh_t60` | 60 | ~5min | **Phase E −5.1% 再現判定点** |
| 終了 | — | — | ~1min | unlock（fresh 直後状態のまま運用継続） |

「経過時間」は restart 完了 (t0) からの分。次サイクル開始は `前回計測終了 + (目標 t − 前回計測終了 t) 秒` を sleep。

## スクリプト構成（差分最小化）

- **起動**: 既存 `report/attachment/2026-04-17_012859_qwen3-122b-c3-phaseF-reproducibility/start_phaseF.sh F1` をそのまま使用（C-D3 と同一）
- **計測**: `measure_phaseG.sh` を Phase F の `measure_phaseF.sh` から派生。差分のみ:
  - 各 Run 後に `ssh $HOST "cat /proc/$PID/status | grep -E '...'"` を取得（Phase F は Run 3 のみ）
  - Run 1 前に `snap_extras()` 関数で以下を追加取得:
    - `ssh $HOST "free -w"` → `free_pre.txt`
    - `ssh $HOST "numastat -m | head -30"` → `numastat_m_pre.txt`
    - `ssh $HOST "nvidia-smi --query-gpu=index,memory.used,temperature.gpu,clocks.current.sm --format=csv"` → `gpu_pre.csv`
    - `ssh $HOST "cat /proc/$PID/sched | grep nr_migrations"` → `sched_pre.txt`
  - Run 3 後にも同様の `_post` 版を取得
  - ログ文言 `phaseF` → `phaseG`
- **配置**: `report/attachment/<timestamp>_qwen3-122b-c3-phaseG-longevity/` 配下に `plan.md, measure_phaseG.sh, out_G0_aged_5h46m+/, out_G1{a,b,c,d}_fresh_t{0,15,30,60}/`

## 実行順序（オペレーション）

```
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

# G0: 既存プロセス計測
PID=$(ssh t120h-p100 "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
bash measure_phaseG.sh $PID G0_aged_5h46m+

# restart
.claude/skills/llama-server/scripts/stop.sh t120h-p100
PID=$(bash start_phaseF.sh F1 | tail -1)   # fresh restart、PID 返却
T0=$(date +%s)

# G1a: t=0 計測
bash measure_phaseG.sh $PID G1a_fresh_t0

# idle → G1b (t=15)
sleep $((T0 + 15*60 - $(date +%s)))
bash measure_phaseG.sh $PID G1b_fresh_t15

# idle → G1c (t=30)
sleep $((T0 + 30*60 - $(date +%s)))
bash measure_phaseG.sh $PID G1c_fresh_t30

# idle → G1d (t=60)
sleep $((T0 + 60*60 - $(date +%s)))
bash measure_phaseG.sh $PID G1d_fresh_t60

.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

各 `measure_phaseG.sh` 実行は `run_in_background: false`（~5min で完了）。sleep も同様に同期実行。セッション切断リスクは低いが、中断時は完了済み `out_G*/` から部分集計可能。

## 計測項目

各サイクル（G0, G1a-d）の出力:
- `eval_run{1,2,3}.json`（`timings.predicted_per_second` / `prompt_per_second`）
- `dmon_run{1,2,3}.log`（nvidia-smi dmon 20s × 3）
- `status_run{1,2,3}.txt`（Threads / Cpus_allowed_list / voluntary_ctxt_switches / nonvoluntary_ctxt_switches）**← Phase F との差分（全 Run 取得）**
- `numastat_pre.txt` / `numastat_post.txt`（`numastat -p $PID`）
- `free_pre.txt` / `free_post.txt` **← 追加**
- `numastat_m_pre.txt` / `numastat_m_post.txt` **← 追加**
- `gpu_pre.csv` / `gpu_post.csv` **← 追加**
- `sched_pre.txt` / `sched_post.txt` **← 追加**
- `cmdline.txt`, `timeline.log`

## 判定基準

- **劣化あり（Phase E 再現）**: `median(G1d) ≤ median(G1a) × 0.96` かつ `median(G1a) − median(G1d) ≥ 0.2 t/s`
- **早期劣化（Phase F F2 現象の C-D3 波及）**: `median(G1b) − median(G1a) ≤ −0.15 t/s`
- **長時間稼働劣化の確証**: `median(G0) ≤ median(G1a) − 0.3 t/s`（5h46m+ は fresh より明確に遅い）
- **再起動で回復**: `median(G1a) ≥ median(G0) + 0.3 t/s`
- 劣化あり & 回復ありが両立 → 「定期再起動 (e.g., 1h 毎) の運用検証」を次 Phase の TODO に昇格

## 終了処理

G1d 計測時点で稼働 60 分+5min ≈ 65 分。その状態で運用継続（＝restart しない）。理由: 判定を「劣化あり」にするなら結果として 60 分劣化プロセスが残るが、ユーザの判断（次 Phase で再起動運用を入れるか否か）までは fresh restart を繰り返さない方が観察継続できる。ロックのみ解放。

## レポート（REPORT.md 準拠）

`report/<timestamp>_qwen3-122b-c3-phaseG-longevity.md` に以下の章立て:

1. **前提・目的** — Phase E/F 経緯、残課題、本 Phase の狙い
2. **添付ファイル** — plan.md, measure_phaseG.sh, 各 out_G*/ ディレクトリ
3. **参照** — Phase F / Phase E / Phase D レポートへのリンク
4. **環境情報** — Phase F と同一 (t120h-p100, Tesla P100 ×4, b8807-b3d758750)
5. **計測手順（再現方法）** — タイムライン表、各サイクルコマンド
6. **実行結果サマリ** — t=0/15/30/60 の eval/prompt 時系列表、G0 の aged 値
7. **ボトルネック・副次発見の分析** — ctxt_switches, numastat, free, GPU clock の時系列変化
8. **採用判定** — 上記判定基準に対する結果
9. **未検証事項**（Phase F からの継続項目 + 本 Phase で判明した新規項目）
10. **検証完了後に実施すべき TODO**（同上）

プランファイル添付: `mkdir -p report/attachment/<timestamp>_qwen3-122b-c3-phaseG-longevity/` → `cp /home/ubuntu/.claude/plans/playful-wibbling-origami.md report/attachment/<timestamp>_qwen3-122b-c3-phaseG-longevity/plan.md`

## 検証方法（end-to-end）

1. `ssh t120h-p100 "ps -eo pid,etime,args | grep llama-server | grep -v grep"` で PID 65837 が継続稼働中を確認
2. 上記「実行順序」を順次実行
3. 各 `out_G*/` ディレクトリに `eval_run{1,2,3}.json` が生成され、`jq '.timings.predicted_per_second' out_G*/eval_run*.json` で値が抽出可能であることを確認
4. `timeline.log` の JST タイムスタンプが計画通り（t=0, 15, 30, 60 分 ±1 分）になっていることを確認
5. 5 サイクルの中央値時系列が判定基準の閾値を満たすかチェック
6. 最後に `.claude/skills/gpu-server/scripts/unlock.sh t120h-p100` でロック解放確認

## Critical files

- 流用元: `report/attachment/2026-04-17_012859_qwen3-122b-c3-phaseF-reproducibility/measure_phaseF.sh`
- 流用元: `report/attachment/2026-04-17_012859_qwen3-122b-c3-phaseF-reproducibility/start_phaseF.sh`
- 新規: `report/attachment/<timestamp>_qwen3-122b-c3-phaseG-longevity/measure_phaseG.sh`
- 新規: `report/attachment/<timestamp>_qwen3-122b-c3-phaseG-longevity/plan.md` (本ファイルのコピー)
- 新規: `report/<timestamp>_qwen3-122b-c3-phaseG-longevity.md`
- 利用: `.claude/skills/gpu-server/scripts/lock.sh`, `unlock.sh`
- 利用: `.claude/skills/llama-server/scripts/stop.sh`
