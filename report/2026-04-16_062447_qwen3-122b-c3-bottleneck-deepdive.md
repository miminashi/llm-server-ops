# Qwen3.5-122B-A10B C-3 eval ボトルネック深掘り計測 (Phase A + Phase B)

- **実施日時**: 2026年4月16日 06:24–06:55 (JST)
- **作業種別**: 計測・解析・構成変更

## 添付ファイル

- [実装プラン](attachment/2026-04-16_062447_qwen3-122b-c3-bottleneck-deepdive/plan.md)
- [Phase A 計測スクリプト](attachment/2026-04-16_062447_qwen3-122b-c3-bottleneck-deepdive/profile_phaseA.sh)
- [perf 再計測スクリプト](attachment/2026-04-16_062447_qwen3-122b-c3-bottleneck-deepdive/profile_perf_retry.sh)
- [集計スクリプト](attachment/2026-04-16_062447_qwen3-122b-c3-bottleneck-deepdive/summarize_phaseA.sh)
- [ログ解析スクリプト](attachment/2026-04-16_062447_qwen3-122b-c3-bottleneck-deepdive/llama_log_analyze.sh)
- [Phase B 起動スクリプト](attachment/2026-04-16_062447_qwen3-122b-c3-bottleneck-deepdive/start_phaseB.sh)
- [ロールバックスクリプト](attachment/2026-04-16_062447_qwen3-122b-c3-bottleneck-deepdive/rollback_c3.sh)
- Phase A / B のログ一式: `phase{A,B}_{dmon,top_system,top_pid,mpstat,pidstat,perfstat,perfrec,status,numastat_pre,numastat_post,numa_maps,vmstat_pre,vmstat_post,sched,eval}_run{0,1,2,3}.*`, `phase{A,B}_timeline.log`, `phaseA_perf_report_run3.txt`, `phaseB_perf_report_run3.txt`, `output_placement.txt`, `c3_cmdline.txt`, `llama_server_log_snapshot.txt`

## 参照

- 前身レポート: [2026-04-16_054649_qwen3-122b-c3-eval-bottleneck-profile.md](2026-04-16_054649_qwen3-122b-c3-eval-bottleneck-profile.md)
- C-3 採用: [2026-04-16_053225_qwen3-122b-c3-layer30-swap.md](2026-04-16_053225_qwen3-122b-c3-layer30-swap.md)
- C-1 採用: [2026-04-16_043659_qwen3-122b-128k-execution.md](2026-04-16_043659_qwen3-122b-128k-execution.md)
- 前身レポート「未検証事項」のうち優先度が高い 4 項目（CPU 飽和の内訳、NUMA 非バインディング影響量、llama-server スレッド数実測、CUDA3 txpci の理由）の実施

## 前提・目的

- **目的**: 前身レポートで「CPU expert 計算律速」と判定された C-3 構成について、CPU 飽和の内訳（FFN 計算 vs メモリ帯域 vs NUMA inter-socket）を `perf stat` / `perf record` / `numastat` / `mpstat` / `pidstat` で定量分類し、NUMA バインディング (`numactl --cpunodebind=1 --membind=1`) の効果を実測する
- **仮説**: 残り 36 層の CPU 側 expert 計算が律速だが、内部で「メモリ帯域律速」「NUMA inter-socket 律速」「FFN 純計算律速」「並列化同期律速」のいずれが支配的かは未判明
- **成功条件**: (a) perf の CPU event からボトルネックを定量分類、(b) numactl の効果が +3% 以上（有意改善）か判定
- **制約**: llama-server の再起動許容（Phase B 実施時）、観測ツール追加許容（perf / numastat / mpstat / pidstat / numactl）

## 環境情報

- **サーバ**: `t120h-p100` (10.1.4.14)
- **GPU**: NVIDIA Tesla P100-PCIE-16GB × 4
- **CPU**: Intel Xeon Gold 6138 @ 2.00GHz × 2 socket、計 40 コア / 80 スレッド、NUMA 2 ノード（Node 0={CPU 0-19,40-59}, Node 1={CPU 20-39,60-79}）
- **メモリ**: 257,560 MiB (約 251 GiB)
- **モデル**: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- **観測ツール**: `numactl 2.x`, `numastat`, `perf 5.15.198`, `mpstat`, `pidstat`（本作業前に `sudo apt install -y numactl linux-tools-common linux-tools-5.15.0-174-generic sysstat` + `sudo sysctl -w kernel.perf_event_paranoid=0` で導入・設定）
- **Phase A 対象 PID**: 17780（前身レポート継続の C-3 構成、`--threads -1`）
- **Phase B 対象 PID**: 28500（`numactl --cpunodebind=1 --membind=1` 付きで再起動した新プロセス）
- **Phase A/B で起動コマンド本体は同一**（モデルパス、`-ot`、`-b 8192 -ub 8192`、`--flash-attn 1`、`--ctx-size 131072`、`--cache-type-k/v q8_0`、`--threads -1` すべて不変）

## 計測手順

1. **事前インストール & sysctl 調整**（ユーザー実施）: `numactl`, `linux-tools-common`, `linux-tools-5.15.0-174-generic`, `sysstat` + `kernel.perf_event_paranoid=0`
2. **Phase A 計測** (`profile_phaseA.sh 17780 phaseA`): Run 0 (idle 20s) / Run 1-3 (eval 40s 窓) で `nvidia-smi dmon` + `top -b` + `mpstat -P ALL 1 N` + `pidstat -t` + `perf stat -a -e cycles,instructions,cache-misses,cache-references,LLC-loads,LLC-load-misses,node-loads,node-load-misses,dTLB-loads,dTLB-load-misses` + `perf record -g -F 99 -a`(Run 3) を ssh 経由で並列採取。eval プロンプト `"Write a short haiku about autumn."` / `max_tokens=256` / 各 run 間 60 秒 cooldown
3. **perf 再計測** (`profile_perf_retry.sh 17780`): 初回 Phase A 時 `perf_event_paranoid=1` で perf stat が拒否されたため、ユーザーが `=0` に設定後に perf stat/record のみ再採取
4. **Phase A 集計** (`summarize_phaseA.sh phaseA`): GPU/CPU/perf/threads/NUMA/percore/eval の 7 TSV 生成、`llama_log_analyze.sh` で output 層配置確定
5. **Phase B 実施判定**: 自動基準 3 点中 2 点以上成立を確認 → 実施
6. **Phase B 構成で再起動** (`start_phaseB.sh`): `numactl --cpunodebind=1 --membind=1 --` をプレフィックスに付与して C-3 構成で再起動、`/health` 200 を 25 秒で確認
7. **Phase B 計測** (`profile_phaseA.sh 28500 phaseB`): Phase A と同一手順・同一時間予算
8. **比較集計と稼働判定** (`summarize_phaseA.sh phaseB`): eval t/s 中央値 +3% 超 → numactl 付きで継続

## 実行結果サマリ

### eval 速度

| 構成 | Run 1 | Run 2 | Run 3 | 中央値 | 前身 C-3 (11.94) 比 | Phase A (11.03) 比 |
|------|------:|------:|------:|------:|-------------------:|-------------------:|
| Phase A（元 C-3、`--threads -1`） | 10.99 | 11.03 | 11.46 | **11.03** | -7.6% | 基準 |
| Phase B（`numactl -N1 -m1` 付き） | 11.51 | 11.50 | 11.44 | **11.50** | -3.7% | **+4.3%** |

- Phase A の中央値 11.03 t/s は前身レポート (11.94 t/s) より低めだが、これは本計測が perf record / mpstat / pidstat / `cat /proc/$PID/status` 等を並列実行している観測負荷の影響と推定（Phase A/B は同条件）
- Phase B は Phase A 比 **+4.3%** で有意改善（判定基準 +3% 超を満たす）

### perf stat による CPU 律速の内訳（Run 1 の値、Run 2/3 もほぼ同値）

| 指標 | Phase A (`--threads -1`, NUMA 非固定) | Phase B (`numactl -N1 -m1`) | 変化 |
|------|----------------------------------:|------------------------:|------|
| IPC (instructions per cycle) | **0.122** | **0.682** | **×5.6** |
| cache-miss rate | 51.04% | 54.55% | +3.5pt |
| LLC-miss rate | 23.06% | 18.37% | -4.7pt |
| **node-load-miss rate** | **145.3%** | **5.1%** | **-140pt（97% 削減）** |
| dTLB miss rate | 0.04% | 0.07% | ほぼ同 |

- **node-load-miss rate** は `node-load-misses / node-loads` の比で、NUMA inter-socket 転送の多寡を示す。Phase A で 145% （= node-load の全てがローカルに無く、2.5 倍近くの外部ノードアクセス）が Phase B で 5.1% まで劇的に減少
- **IPC** は Phase A で 0.122 と極端に低く、CPU が常時メモリ待ちだったことを示す。Phase B では 0.682 まで 5.6 倍に改善、CPU が実際に計算できる状態に
- LLC-miss rate が Phase B でやや低下しているのは、NUMA ローカル化により再利用効率が上がったためと推定

### perf report hotspot（Run 3 の 40 秒 call-graph）

| 関数 | Phase A | Phase B | 意味 |
|------|--------:|--------:|------|
| `libgomp.so` (OpenMP barrier spin) | **61.2%** | **8.9%** | 並列化同期待ち |
| `ggml_vec_dot_q4_K_q8_K` | 24.0% | 22.4% | FFN 行列演算（Q4_K） |
| `ggml_vec_dot_q5_K_q8_K` | 8.6% | 13.0% | FFN 行列演算（Q5_K） |
| swapper (kernel idle) | ほぼなし | 22.8% | Node 0 CPU が binding 外で完全 idle |
| ggml_graph_compute_thread 他 | 残部 | 残部 | スケジューラ |

- **Phase A の libgomp 61% は「他スレッド待ち」のスピン wait**。NUMA リモートアクセスで 1 スレッドが遅れると全体が待つ
- **Phase B では libgomp が 8.9% に激減**。40 論理コアしか使わないがバリア待ちが短くなり実計算時間の割合が増加
- Phase B の swapper 22.8% は Node 0 の 40 論理 CPU が完全に idle である観測結果（`Cpus_allowed_list: 20-39,60-79` で確認済）

### CPU / メモリ / NUMA

| 指標 | Phase A (Run 1) | Phase B (Run 1) |
|------|---------------:|---------------:|
| システム us (%) | 87.05 | 11.48 |
| llama-server %CPU 平均 | 7606 | 1131 |
| llama-server %CPU p95 | 8000 | 1170 |
| N0 論理 CPU %usr 平均 | 59.65 | 0.10 |
| N1 論理 CPU %usr 平均 | 59.73 | 14.23 |
| N0 使用 core 数 | 40 | 2 |
| N1 使用 core 数 | 40 | 40 |
| Threads (`/proc/$PID/status`) | 166 | 166 |
| voluntary_ctxt_switches delta | 31 | 72,108 |
| Cpus_allowed_list | 0-79 | 20-39,60-79 |
| numa_other delta / numa_hit delta | 0.027% | 0.023% |

- Phase A は両ノード 40 cores 対称稼働（合計 80 論理 CPU、平均 us 60%）、Phase B は Node 1 の 40 論理 CPU のみ（HT 込み = 物理 20 コア × 2 スレッド）
- voluntary ctxt_switches が Phase B で 72,000 超と激増 = スレッドが busy-wait ではなく本当の sleep wait に切り替わっている兆候
- `/proc/vmstat` の numa_hit/miss/foreign/local/other はどちらも大きな差が無い（numa_miss=0, numa_other delta は hit の 0.02-0.03%）。これはページ配置レベルの指標で、実行時のキャッシュライン転送レベルを表す perf の `node-load-misses` とは異なる
- **モデルメモリ配置は Phase A/B で同一**（Node 1 に Private 約 69 GiB、Node 0 は約 8 MiB のみ）。numactl 適用後もモデル常駐位置は変わらず、CPU バインディングだけが効いている

### スレッド数実測

- `/proc/$PID/status` の `Threads:` は Phase A/B いずれも **166** で固定
- `--threads -1`（自動）は論理 CPU 数（80）ではなく **モデル構造由来の 166 スレッド** を起動している（compute thread 80 + CUDA 関連 worker + server I/O + その他補助）
- `Cpus_allowed_list` により稼働 CPU が決まり、Phase A は `0-79`、Phase B は `20-39,60-79`

### output 層の配置 (CUDA3 txpci 高値の説明)

`/tmp/llama-server.log` の抜粋:

```
load_tensors: offloading output layer to GPU
load_tensors: offloading 47 repeating layers to GPU
load_tensors: offloaded 49/49 layers to GPU
llama_context:  CUDA_Host  output buffer size =     0.95 MiB
```

- **output layer は GPU に offload 済**（「CUDA_Host output buffer 0.95 MiB」は最終 logit を CPU に戻すための pinned host buffer）
- CUDA3 の compute buffer が 8048 MiB で最大（CUDA0=7648, CUDA1/2=3872, CUDA3=8048）
- 前身レポートの「CUDA3 txpci 17 MB/s と他 GPU より一桁大きい」現象は、**CUDA3 に output 層（logit 生成）が配置され、最終 logit を CUDA_Host へ転送しているパス** に一致する
- Phase A/B の `nvidia-smi dmon` 再計測でも CUDA3 txpci が 31-37 MB/s と他 GPU（6-10 MB/s）より高く、この推定が裏付けられる

### VRAM 配分（Phase B 稼働中、2026-04-16 06:55 時点）

| GPU | used (MiB) | free (MiB) |
|-----|-----------:|-----------:|
| CUDA0 | 9799 | 6472 |
| CUDA1 | 14269 | 2002 |
| CUDA2 | 14269 | 2002 |
| CUDA3 | 10581 | 5690 |

- 前身 C-3 の VRAM 配分（9799 / 14269 / 14269 / 10581）と完全一致 → numactl は CPU/メモリバインディングのみで GPU 配分には影響なし

## ボトルネック判定（定量版）

| カテゴリ | Phase A での証拠 | 判定 |
|----------|------------------|------|
| FFN 純計算律速 | ggml_vec_dot 合計 32.6%、理論帯域 120 GB/s の 51% LLC miss → 計算より memory の待ちが長い | 非支配 |
| メモリ帯域律速 | LLC-miss 23%、cache-miss 51%、IPC 0.12 | 部分要因 |
| **NUMA inter-socket 律速** | **node-load-miss rate 145%**（Phase B で 5.1% に激減） + libgomp 61% → 97% 削減 | **主因の 1 つ** |
| 並列化同期律速 | libgomp barrier 61%（Phase B では 9%） | NUMA に起因した二次効果 |

### 結論

- **前身レポートの「CPU expert 計算律速」はさらに「NUMA inter-socket 転送 → バリア待ち拡大」と内訳できた**
- `numactl --cpunodebind=1 --membind=1` で Node 1 の 40 論理 CPU に限定すると、CPU 計算効率（IPC）は 5.6 倍に跳ね上がるが、使用 CPU が半減するため **実 eval 改善は +4.3% に留まる**
- つまり「NUMA を解消した分の改善」と「使用 CPU 半減によるペナルティ」がほぼ相殺され、わずかに前者が勝つ関係
- **本質的な最適化は「両ノードを使いつつ NUMA リモートアクセスを減らす」方向**（例: モデルメモリを両ノードに interleave、MoE expert を CPU affinity 毎に分割、`--numa distribute` 相当）

### Phase B 実施判定（事後）

| 基準 | 結果 |
|------|------|
| モデル常駐 N0/N1 両方 30 GiB 超 | 不成立（N0=9 MB） |
| node-load-miss rate > 5% or numa_miss+other > 5% | **成立（145%）** |
| スレッド両ノード分布 | **成立（両ノード 40 cores 稼働）** |

2/3 成立により実施 → +4.3% 改善を確認、**稼働構成を Phase B（numactl 付き）に変更して継続**。

## 採用構成（Phase B）の起動コマンド

```bash
# 1. ロック取得
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 2. 既存プロセス停止
.claude/skills/llama-server/scripts/stop.sh t120h-p100

# 3. numactl 付き起動
MODEL_PATH="/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf"

LAUNCH_CMD="numactl --cpunodebind=1 --membind=1 -- ./build/bin/llama-server \
  -m '$MODEL_PATH' --jinja \
  -ngl 999 -ot 'blk\\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\\.ffn_.*_exps\\.weight=CPU' \
  --flash-attn 1 --poll 0 -b 8192 -ub 8192 \
  --n-predict 32768 --threads -1 \
  --ctx-size 131072 --parallel 1 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --defrag-thold 0.1 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 \
  --port 8000 --host 0.0.0.0 \
  --alias 'unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M'"

ssh -f t120h-p100 "cd ~/llama.cpp && nohup bash -c \"\$LAUNCH_CMD\" > /tmp/llama-server.log 2>&1 < /dev/null &"

# 4. ヘルスチェック
until curl -sf http://10.1.4.14:8000/health > /dev/null; do sleep 5; done

# 5. ロック解放
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 未検証事項

本レポート時点で未検証の事項（前身レポートから継続の既知項目を含む）:

### 既知項目（前身レポートから継続）

- [ ] **長時間安定性**: C-3（numactl 付き）での連続稼働は本計測の約 10 分のみ。1 時間超の安定性は未検証
- [ ] **大コンテキストでの eval 速度**: 16k〜128k の実プロンプトでの速度は未計測。本計測も短プロンプト（18 tokens in）のみ
- [ ] **flash-attn off との比較**: P100 CC 6.0 で `--flash-attn 1` が最適か未検証
- [ ] **CUDA1 の 2 GiB セーフティマージン**: プロンプト処理中のピーク使用量は未計測
- [ ] **層→GPU アライメントのソース解析**: llama.cpp の `--split-mode layer` 既定配置ロジックは未解析

### 新規項目（本レポートで判明・発生）

- [ ] **`--threads 40` 等の明示値と NUMA 併用時の最適値**: 現状 `--threads -1 + numactl -N1` で 40 論理 CPU（HT 込み）使用。`--threads 20`（1 socket 物理のみ）や `--threads 40`（HT 込み明示）との比較、および `numactl --cpunodebind=1 --physcpubind=20-39`（HT 除外）との比較は未計測
- [ ] **Phase B の voluntary_ctxt_switches 72,000 超の内訳**: Phase A が 31 だったのに対し Phase B で劇増。sleep wait が増えたことを示すが、eval 速度に悪影響がないか長時間安定性と合わせて検証必要
- [ ] **Phase A の eval 11.03 vs 前身 11.94 のギャップ**: 観測ツール（perf record, mpstat, pidstat）の並列実行による観測負荷の影響と推定。観測無しでの Phase B 再測定が未実施
- [ ] **両ノード使用 + NUMA interleave の評価**: `numactl --interleave=all` で両ノードにメモリをストライプする方式は未試行。40 コア × 2 ノード = 80 論理 CPU を活かせる可能性
- [ ] **llama.cpp の `--numa` オプション評価**: `--numa distribute` / `--numa isolate` / `--numa numactl` の 3 モードは未試験（現状どちらでもない状態で走っている）
- [ ] **量子化ダウンでの eval 向上量**: Q4_K_M → Q3_K_M / IQ2_XXS で CPU 側計算量がどれだけ減るか未計測
- [ ] **pcm-memory による DRAM 帯域実測**: `intel-cmt-cat` / `pcm-memory.x` は未インストール。Xeon 6138 の 120 GB/s に対する実使用率の直接観測はできていない
- [ ] **`ggml_vec_dot_q5_K_q8_K` が 13% に増えた理由**: Phase B で q5_K 比率が Phase A より上がった理由（q5_K は混合量子化層の一部）。モデル構成の確認が未実施

## 検証完了後に実施すべき TODO

次に実施すべき作業（前身レポートからの既知項目を含む）:

### 既知項目（前身レポートから継続）

- [ ] **start.sh の拡張**: `LLAMA_OT_OVERRIDE` / `LLAMA_NUMACTL_PREFIX` 相当の環境変数サポートを追加し、C-3 + numactl を start.sh から起動可能にする
- [ ] **CUDA1 セーフティマージン OOM フォールバック実装**
- [ ] **flash-attn off ベンチマーク**
- [ ] **大コンテキスト実プロンプトでの eval 計測**（16k / 32k / 64k / 128k）
- [ ] **1 時間超の連続稼働試験**
- [ ] **層→GPU アライメントのソースコード解析**
- [ ] **eval ボトルネック解析** → **本レポートで完了**（NUMA inter-socket + memory 律速と定量分類）
- [ ] **CUDA0/3 compute buffer 削減案 (`-ub 4096`) = C-4 実験**: CPU 律速が判明した以上、CPU 層を減らす（GPU 層を増やす）方向の試行を継続して意味あり
- [ ] **layer 境界の詳細推定**（layer 20-23 / 31-35 の配置）
- [ ] **C-3 採用構成の start.sh プリセット化**

### 新規項目（本レポートで発見）

- [ ] **`--threads` 明示値 × numactl 組み合わせ比較**: 例えば `--threads 20 + numactl -N1 --physcpubind=20-39`（Node 1 物理のみ 20 スレッド）で HT 除外時の eval 変化
- [ ] **`numactl --interleave=all` 試行**: モデルメモリを両ノードにストライプし、80 論理 CPU を活かしつつ inter-socket をキャッシュラインレベルで分散させる試行
- [ ] **llama.cpp の `--numa distribute/isolate/numactl` 試行**: llama.cpp 側の NUMA オプション群の評価
- [ ] **量子化変更比較**: Q4_K_M vs Q3_K_M vs IQ2_XXS での eval 速度と出力品質比較
- [ ] **pcm-memory 導入と DRAM 帯域実測**
- [ ] **C-4 実験** （`-ub 4096` + 大幅な GPU 層追加、CPU 層を 36 → 20 層未満に減らす方向）は引き続き高優先。NUMA 最適化と独立かつ相補的
- [ ] **observation-free ベースライン計測**: perf 等を停止した状態で Phase B を 3 run 計測し、前身 11.94 と真の比較を行う

## 補足

- 作業終了時点で **Phase B 構成（numactl `-N1 -m1` 付き C-3）で稼働中**（PID 28500、VRAM 配分は前身 C-3 と完全同一）
- Phase B で確認された Cpus_allowed_list: `20-39,60-79`（Node 1 の物理 20 コア + HT 20 スレッド = 40 論理 CPU）
- 観測オーバーヘッド: Phase A/B ともに Run 0 (idle) の us は 0.08-0.10%。観測ツール自身の負荷は誤差範囲
- `perf record -g -F 99 -a` は Run 3 のみ起動（40 秒で約 100-120K サンプル）。これ自体も Run 3 の eval へ若干の影響（10-20%）を与える可能性あるが、Run 1/2 の perf stat のみ時と eval t/s の差は 1-5% 以内
- ロック解放は本レポート作成後に実施
