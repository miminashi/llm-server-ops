# t120h-p100 × Qwen3.8-27B で split-mode layer vs tensor ベンチ

## Context

- 手本 [2026-09-14 aws-gpu01 レポート](report/2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor.md)（P100×7 / Qwen3.8-27B dense）は「tensor が全面勝ち」。
- 前回 [2026-09-16 t120h-p100 レポート](report/2026-09-16_225707_t120h_p100_split_mode_layer_vs_tensor.md)（P100×4 / Qwen3.6-35B-A3B MoE）は「勝敗が深さで入れ替わる、prefill は layer 勝ち」と逆の結果になり、残課題の筆頭に
  「**同じ t120h-p100 で手本と同じ Qwen3.8-27B を測れば、機種要因とモデル要因を分離できる**」を挙げていた。今回はそれを実施する。
- 比較軸: 同一機 (p100×4) で MoE→dense を変えた差 ＝ モデル要因。aws-gpu01 の枚数スイープ報告 ([2026-09-16_182920](report/2026-09-16_182920_aws_gpu01_split_mode_gpu_count_sweep.md)) にある **aws-gpu01 4 枚 layer（同モデル）** と並べれば機種要因も見える（同報告の tensor4 は `ALLREDUCE=none` 経路なので参考扱い）。

## 現状（確認済み）

- t120h-p100: **電源 OFF**（iLO5、爆音ガード対象外。前回も通常操作で投入）。
- Qwen3.8-27B: **WS に無い**。サーバ側（`/home/llm/.cache/huggingface/hub` / `~/models`）にあるかは電源投入後に確認。
- サーバ側は前回セッションで llama.cpp `465e49b9c` + NCCL 2.31.2（`~/nccl`、RPATH）ビルド済み、`~/llama-split-bench` 配置済みのはず → 投入後に sha256 `21df743c…6170` と `ldd | grep nccl` で確認。
- 前回レポート（09-16）と手本への追記 1 行は**未コミット**のまま。本作業では触らずそのまま残す（コミットは依頼があれば）。

## 手順

1. **電源投入 → SSH 待ち → ロック**
   `.claude/skills/gpu-server/scripts/power.sh t120h-p100 on` → SSH 到達待ち → `lock.sh t120h-p100`。
2. **状態確認**（読み取りのみ）: モデル有無（`find /home/llm/.cache/huggingface ~/models -iname '*Qwen3.8*'`）、`df -h`、バイナリ sha256・NCCL リンク、`git log -1`、`nvidia-smi topo -m`（手本機のスイッチ構成との対比用に記録）。
   - バイナリが変わっていたら前回レポートの再現手順 2〜3（`465e49b9c` + NCCL 再ビルド、既存 build は退避）でそろえる。
3. **モデル取得（サーバに無い場合）** — CLAUDE.md の 2 段階ルール:
   - WS: `hf download unsloth/Qwen3.8-27B-GGUF --include 'Qwen3.8-27B-UD-Q4_K_XL.gguf' --local-dir ~/models/Qwen3.8-27B-GGUF --token $HF_TOKEN`（約 17.56 GB、18 MB/s で約 16 分）。サイズ 17,559,178,144 B を確認。
   - WS→p100: `rsync -a --partial --progress` で `~/models/Qwen3.8-27B-GGUF/` へ。**前回実測 1.4 MB/s だと約 3.5 時間**。バックグラウンドで流し完了をポーリング。最初の数分で速度を測り、単一ストリーム律速なら `split -n 4` の 4 並列 rsync → サーバで `cat` 結合に切り替える。
   - 完了後 `stat -c %s` と sha256 を WS/サーバで照合。WS 側の一時ファイルは検証後に削除。
   - 転送待ちの間に手順 4・5 を先行実施（モデル不要な部分）。
4. **bench.local.conf 作成**: 前回添付の conf をベースに `MODEL=$HOME/models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf`、`MACHINE` のみ変更（コメントも Qwen3.8-27B dense に）。他は手本と同一（`CTX=131072`、`STAGES=0,16000,32000,64000,128000`、`N_PREDICT=1000`、`PP0_SIZES=512,2048,8192`、`SPEC_ARGS=""`、`-b/-ub` 未指定、`LAUNCH_PREFIX=""` = NCCL 経路、腕は `layer`(4枚) / `tensor`(4枚) / `layer2`(2枚、BASELINE)）。
5. **tensor 起動プローブ**: 前回添付の `probe.sh` を MODEL だけ差し替えて 3 回（NCCL ハングがモデル依存かの追加データにもなる）。固まる場合は NCCL で 3 回までリトライし、それでも駄目ならユーザに相談（`none` 経路に落とすと prefill が大幅劣化し比較の意味が変わるため）。
6. **VRAM プリフライト**: 前回と同じ `run-bench.sh preflight-1 --ctx 131072 --stages 0,8000 --n-predict 32 --pp0-sizes 8192 --no-real`（layer2 を最後）。手本では 2 枚 layer が 10.9 + 12.2 GiB なので収まる見込み。
7. **本計測**（detached、タグ `p100-4way-q38-1`）: `setsid nohup bash run-bench.sh p100-4way-q38-1 > runs/p100-4way-q38-1.log ...` → `BENCH-(DONE|ABORT|FIGFAIL)` をポーリング。所要は手本 7 枚の約 64 分前後を想定。
8. **回収・作図**: `rsync` で `report/attachment/<TS>_t120h_p100_split_mode_qwen38_27b/run/` へ。WS 側で `src/llama-split-bench/plot_bench.py`（ja/en、`--series layer,tensor,layer2 --baseline layer2 --vs on`）。表・サンプラ集計は前回添付の `tables.py` / `sampler.py` を流用。
9. **レポート作成**（REPORT.md 準拠、タイトル 50 字以内、核心発見サマリ冒頭に PNG）:
   - 結果表 5 種（decode / prefill / pp0 / 利用率・温度・電力・クロック / 実プロンプト補正）を手本・前回と同形式で。
   - **3 者対比表**: aws-gpu01×7 dense / p100×4 MoE / p100×4 dense ＋ aws-gpu01×4 layer（スイープ報告）で、優劣反転がモデル要因か機種要因かを結論づける。
   - 手本と前回レポートの「参照レポート」節に本レポートへのリンクを 1 行追記。
10. **後始末**: llama-server が残っていないことを確認。電源とロックは前回同様**ユーザの指示を待って** `power.sh t120h-p100 off` / `unlock.sh`（レポートに現状を明記）。

## 再利用するもの

- `src/llama-split-bench/`（`run-bench.sh`、`plot_bench.py`）
- 前回添付: `report/attachment/2026-09-16_225707_t120h_p100_split_mode_layer_vs_tensor/{bench.local.conf,probe.sh,tables.py,sampler.py,ggufmeta.py}`
- `.claude/skills/gpu-server/scripts/{power.sh,lock.sh,unlock.sh}`

## 検証

- `run-info.json` のバイナリ sha256・`launch_prefix` 空・モデルパス、tensor 腕の server log にフォールバック警告（`falling back`）が 0 件であること。
- 3 腕 × 5 段 + pp0 3 サイズ + real 3 本がすべて揃い、`BENCH-DONE`（または作図のみ失敗の `BENCH-FIGFAIL`）で終わっていること。
- 手本の aws-gpu01 と同一モデル・同一ファイル（サイズ一致）であること。
