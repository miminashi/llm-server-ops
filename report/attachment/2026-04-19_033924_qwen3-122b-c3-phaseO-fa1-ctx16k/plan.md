# Phase O: fa=1 ctx=16384 sched_reserve 再採取 + 5 点フィット

## Context

Phase N レポート（2026-04-19_024430）の「検証完了後に実施すべき TODO」に**Phase O 候補**として明記された優先度最高の未検証事項に対応する。

- **問題**: Phase K（2026-04-18_025221）では fa=1 ctx=16384 の compute buffer 値（sched_reserve）が起動ログに記録されず未採取。そのため fa=1 側のフィットは 4 点（ctx=1024/2048/4096/8192）に限定されており、CUDA0 の max resid 70 MiB というモデル不適合が残る。
- **目的**: fa=1 ctx=16384 を改めて起動して sched_reserve 値を取り、既存 4 点に加えて **5 点フィット**することで fa=1 側の compute buffer モデル精度を向上させる（特に CUDA0 の非線形性解消の手掛かり）。
- **期待コスト**: 10 分程度の計測（Phase N で 3 ctx = 約 15 分の実績あり、1 ctx なら約 5 分の計測 + 起動/停止で 10 分）。

## 採用アプローチ

Phase N の資産を全面的に流用する。スクリプトは既に `FLASH_ATTN` / `CTX_SIZE` 環境変数に対応済みなので、コピー + 集計スクリプトの prefix 変更のみで済む。

## 実施ステップ

1. **GPU サーバロック取得** (`.claude/skills/gpu-server/scripts/lock.sh t120h-p100`)
2. **Phase O 添付ディレクトリを作成**
   - `TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)`
   - `PHASE_O_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseO-fa1-ctx16k"`
   - `mkdir -p "$PHASE_O_DIR/startup_logs"`
3. **Phase N 資産のコピーと prefix 変更**
   - `start_phaseN.sh` → `start_phaseO.sh`
   - `measure_phaseI.sh`, `run_all.sh`, `aggregate_results.sh`, `fit_analysis.py`, `prompts/` をコピー
   - `aggregate_results.sh` の `out_N_*` → `out_O_*` への書き換え
   - `fit_analysis.py` に ctx=16384 データ点を追加するよう 5 点フィット版に修正
4. **fa=1 ctx=16384 起動**
   - `cd "$PHASE_O_DIR" && FLASH_ATTN=1 CTX_SIZE=16384 bash start_phaseO.sh`
   - 起動ログを `ssh t120h-p100 "cat /tmp/llama-server_fa1_ctx16384.log"` で取得 → `startup_logs/fa1_ctx16384.log` に保存
5. **計測実行** (`TAG_PREFIX=O_f16_fa1_ctx16384 SIZES="warmup" PID=<取得PID> bash run_all.sh`)
6. **llama-server 停止** (`.claude/skills/llama-server/scripts/stop.sh t120h-p100`)
7. **集計・フィット**
   - `bash aggregate_results.sh > results.tsv`
   - `python3 fit_analysis.py | tee fit_analysis.txt`
   - `compute_buffer_summary.txt` 生成（Phase N と同手順で sched_reserve 行を抽出）
8. **GPU サーバロック解放**
9. **レポート作成** (`report/${TS}_qwen3-122b-c3-phaseO-fa1-ctx16k.md`)
   - `## 前提・目的`：Phase K の未採取を補完、5 点フィットで CUDA0 モデル精度向上
   - `## 実行結果サマリ`：
     - Phase K で既に記録されていた eval 速度 (15.046 t/s) との再現性比較
     - 新規採取の sched_reserve 値（CUDA0/1/2/3/Host）
     - 既存 4 点と合わせた 5 点フィット係数 `a, b, c` と各 GPU の max resid の変化
     - 特に CUDA0 の非線形性モデル精度向上量（Phase N の 70 MiB → Phase O で何 MiB か）
   - `## 未検証事項`（Phase N の未検証事項を継承 + 新規発生項目を追加）
   - `## 検証完了後に実施すべき TODO`（同様に継承 + 新規）

## 重要な参照

- 前身レポート: `report/2026-04-19_024430_qwen3-122b-c3-phaseN-ctx8k-boundary.md`
- 流用資産: `report/attachment/2026-04-19_024430_qwen3-122b-c3-phaseN-ctx8k-boundary/` 配下のスクリプト群
  - ただし Phase N の attachment ディレクトリ名は `2026-04-19_021803_qwen3-122b-c3-phaseN-ctx8k` （git status より）なのでこちらを参照

## 既知リスク

- Phase K で fa=1 ctx=16384 は **起動成功・eval 15.046 t/s** が確認済みなので、再起動でも同等結果が得られるはず。OOM リスクはない。
- ただし warmup 条件（SIZES="warmup"）のみなので、eval 速度 ±3% 程度のゆらぎはあり得る。これは想定内。

## 検証方法

- `results.tsv` に `O_f16_fa1_ctx16384_warmup` 行が 3 つ追加されていること
- `fit_analysis.txt` に 5 点フィット結果が出力されていること
- `compute_buffer_summary.txt` に fa=1 ctx=16384 の 4 GPU 分の `sched_reserve` 値が採取されていること
- CUDA0 の max resid が 70 MiB から減少していること（改善できなければその事実もレポートに明記）
