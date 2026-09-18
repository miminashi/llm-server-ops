# t120h-p100 × Qwen3.8-27B で split-mode ベンチを MTP on で再実施

## Context

- 直前の [2026-09-18 レポート](report/2026-09-18_131856_t120h_p100_split_mode_qwen38_27b.md)（P100×4 / Qwen3.8-27B dense / **MTP 無効** / NCCL）は「tensor が全面勝ち」。残課題に「MTP 併用」を挙げていた。
- aws-gpu01×7 の [MTP 3 腕レポート](report/2026-09-16_103619_aws_gpu01_split_mode_mtp_3arm.md) は NCCL 起動ハング（0/13）のため tensor 腕を `GGML_CUDA_ALLREDUCE=none` で測るしかなく、「tensor で採択率が下がる」「回避策が prefill を 7〜8 割奪う」が交絡していた。
- t120h-p100 4 枚は NCCL で tensor が起動する（3/3）ので、**tensor × NCCL × MTP を初めて実測できる**。これで (1) 同一機・同一モデルでの MTP on/off 差、(2) 採択率低下が tensor 分割そのものの性質か `none` 経路の副作用か、が分かる。

## 現状（確認済み）

- t120h-p100: **通電中**、GPU 4 枚アイドル、llama-server なし。
- ロック: `aws-mmns-generic-1069874-20260918_120129`（= 前回セッション、12:01 取得のまま保持）。前回作業は完了済みなので `unlock.sh` → `lock.sh` で本セッションに取り直す。
- モデル `~/models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf` あり（MTP ヘッド `blk.64` 同梱）。`draft-mtp` は同梱ヘッドを使うので、別ファイル `MTP/mtp-Qwen3.8-27B-Q4_0.gguf` は使わない（aws-gpu01 系列と同条件）。
- バイナリ・`~/llama-split-bench` は前回のまま（sha256 `21df743c…6170`、NCCL 2.31.2）。

## 手順

1. **ロック取り直し**: `.claude/skills/gpu-server/scripts/unlock.sh t120h-p100` → `lock.sh t120h-p100`。バイナリ sha256・`ldd | grep nccl` を再確認。
2. **conf**: サーバの現 conf を `bench.local.conf.qwen38-27b-nomtp` に退避し、前回添付の conf から **`SPEC_ARGS="--spec-type draft-mtp --spec-draft-n-max 2"` の 1 行だけ変更**（aws-gpu01 MTP 系列と同値）。`LAUNCH_PREFIX=""`（NCCL）、腕 `layer`/`tensor`/`layer2`、ctx・ステージ・N_PREDICT・pp0 はすべて前回と同一。
3. **tensor+MTP 起動プローブ（NCCL、3 回）**: 前回の `probe.sh` に `--spec-type draft-mtp --spec-draft-n-max 2` を足した版で 3 回。ハングした場合は `none` に落とすと比較の意味が変わるため、**そこで止めてユーザに相談**。kill 後に `--list-devices` で CUDA 生存確認（壊れたら `nvidia_uvm` 再ロードはユーザに sudo 依頼）。
4. **VRAM プリフライト**（`preflight-q38-mtp-1`、前回と同じ引数、layer2 を最後）。layer2 の CUDA1 は aws 実績で約 13.9 GiB / 16 GiB の見込み。
5. **本計測**（detached、タグ `p100-4way-q38-mtp-1`）→ `BENCH-(DONE|ABORT|FIGFAIL)` をポーリング。想定 70〜80 分。
6. **腕別の実プロンプト補正**: ツールは tensor 腕のみ測るので、aws の `real-arm.sh` をサーバに置いて `layer` / `layer2` を個別取得（各 4 分程度）。
7. **回収・作図（WS）**: `rsync` で `report/attachment/<TS>_t120h_p100_split_mode_qwen38_27b_mtp/run/`。
   - 標準図: `src/llama-split-bench/plot_bench.py`（ja/en、`--series layer,tensor,layer2 --baseline layer2 --vs on`）。
   - MTP on/off 比較図: aws 添付 `plot_mtp2.py` をコピーし、ラベル（7枚→4枚）とタイトルの機種名だけ直す。`--off` は前回 run（`report/attachment/2026-09-18_131856_…/run/`）、`--on` は今回 run。
   - 表: aws 添付 `tables.py`（on/off・採択率・腕別実プロンプト）と前回添付 `sampler.py` を流用。
8. **レポート作成**（REPORT.md 準拠、タイトル 50 字以内、核心発見サマリ冒頭に PNG）。主な節:
   - decode / prefill / pp0 の MTP on/off × 3 腕、採択率（合成・実プロンプト）、腕別補正後 decode、利用率・温度・電力。
   - **aws-gpu01×7（tensor は `none`）との対比**で、採択率低下と prefill 変化が NCCL 経路でも起きるかを結論づける。
   - 前回レポートと aws MTP 3 腕レポートの「参照レポート」に 1 行ずつ追記。
9. **後始末**: llama-server 停止を確認（`pkill -x`）。conf は今回版のまま残し、電源とロックは**ユーザの指示待ち**（レポートに明記）。

## 再利用するもの

- `src/llama-split-bench/`（`run-bench.sh`、`plot_bench.py`、サーバ側 `measure_real.py`）
- `report/attachment/2026-09-18_131856_t120h_p100_split_mode_qwen38_27b/{bench.local.conf,probe.sh,sampler.py,tables.py}`
- `report/attachment/2026-09-16_103619_aws_gpu01_split_mode_mtp_3arm/{real-arm.sh,plot_mtp2.py,tables.py}`
- `.claude/skills/gpu-server/scripts/{lock.sh,unlock.sh,lock-status.sh}`

## 検証

- `run-info.json` のバイナリ sha256・`launch_prefix` 空・`spec_args` に draft-mtp があること。tensor 腕 server log に `falling back` / `unknown GGML_CUDA_ALLREDUCE` 0 件。
- 各段の JSON に `draft_n` / `draft_n_accepted` が入っていること（MTP が実際に効いている証拠）。
- 3 腕 × 5 段 + pp0 3 サイズ + real（tensor 分 + layer/layer2 個別）が揃い `BENCH-DONE|FIGFAIL` で終了。
- layer 腕の MTP 効果が aws-gpu01 の layer 系（decode +76〜107%、prefill -10〜-37%）と桁が合うかで妥当性を確認。
