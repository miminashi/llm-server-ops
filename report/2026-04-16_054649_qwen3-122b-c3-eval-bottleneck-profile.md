# Qwen3.5-122B-A10B C-3 eval ボトルネック プロファイリング

- **実施日時**: 2026年4月16日 05:46 (JST)
- **作業種別**: 計測・解析

## 添付ファイル

- [実行プラン](attachment/2026-04-16_054649_qwen3-122b-c3-eval-bottleneck-profile/plan.md)
- [プロファイル収集スクリプト](attachment/2026-04-16_054649_qwen3-122b-c3-eval-bottleneck-profile/profile.sh)
- [GPU 集計 TSV](attachment/2026-04-16_054649_qwen3-122b-c3-eval-bottleneck-profile/summary_gpu.tsv)
- [CPU 集計 TSV](attachment/2026-04-16_054649_qwen3-122b-c3-eval-bottleneck-profile/summary_cpu.tsv)
- [タイムライン](attachment/2026-04-16_054649_qwen3-122b-c3-eval-bottleneck-profile/timeline.log)
- dmon / top / eval 生ログ: `dmon_run{0,1,2,3}.log`, `top_system_run{0,1,2,3}.log`, `top_pid_run{0,1,2,3}.log`, `eval_run{1,2,3}.json`

## 参照

- 前身レポート（C-3 採用）: [2026-04-16_053225_qwen3-122b-c3-layer30-swap.md](2026-04-16_053225_qwen3-122b-c3-layer30-swap.md)
- C-2 失敗: [2026-04-16_051249_qwen3-122b-c2-cuda2-expansion.md](2026-04-16_051249_qwen3-122b-c2-cuda2-expansion.md)
- C-1 採用: [2026-04-16_043659_qwen3-122b-128k-execution.md](2026-04-16_043659_qwen3-122b-128k-execution.md)
- 前身レポート「検証完了後に実施すべき TODO（新規項目）」の最優先項目「eval ボトルネック解析」に対応

## 前提・目的

- **目的**: C-3 構成（GPU 層 14-19 + 25-30、計 12 層）で GPU 層を C-1 の 6 層から倍増しても eval が 12.06 → 12.19 t/s（+1.1%）と頭打ちしている要因を、`nvidia-smi dmon` + `top` の並列計測で切り分ける
- **仮説**: 残り 36 層の CPU 側 expert 計算、CPU↔GPU PCIe 転送、GPU 同期待ちのいずれかが支配的と推定。観測で (a) CPU 律速 / (b) GPU compute / PCIe 律速 / (c) 同期律速 を判別する
- **成功条件**: 判定マトリクス（プラン節 3）のいずれかカテゴリに分類でき、次アクションを決定できること。llama-server は再起動せず C-3 稼働のまま観測

## 環境情報

- **サーバ**: `t120h-p100` (10.1.4.14)
- **GPU**: NVIDIA Tesla P100-PCIE-16GB × 4
- **CPU**: Intel(R) Xeon(R) Gold 6138 @ 2.00GHz × 2 socket、計 40 コア / 80 スレッド、NUMA 2 ノード
- **メモリ**: 257,560 MiB (約 251 GiB)
- **モデル**: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- **稼働中 llama-server**: C-3 構成そのまま（再起動なし）、PID=17780
  - `-ot 'blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'`
  - `-b 8192 -ub 8192 --flash-attn 1 --ctx-size 131072 --cache-type-k q8_0 --cache-type-v q8_0 --threads -1`

## 計測手順

1. Run 0（idle）: `nvidia-smi dmon -s pucvmet -d 1 -c 20` と `top -b -d 1 -n 20`（システム全体 + llama-server PID 限定）を並列 20 秒。eval は打たない
2. Run 1-3（eval）: 各 run で dmon / top を 40 秒起動（`-c 40`）、3 秒のウォームアップ後に `POST /v1/chat/completions`（`max_tokens=256`、プロンプト `"Write a short haiku about autumn."`）を 1 回投入
3. Run 間は 60 秒インターバル
4. 各 eval の開始・終了を `TZ=Asia/Tokyo date +%H:%M:%S.%N` で `timeline.log` に記録
5. 集計時、Run 1-3 は `timeline.log` の eval 開始〜終了の時刻窓内に限定して GPU / CPU メトリクスを平均

## 実行結果サマリ

### eval 速度（3 run）

| Run | eval (t/s) | prompt eval (t/s) | eval 時間 |
|-----|-----------|-------------------|-----------|
| 1   | 11.80     | 27.76             | 21.70 s   |
| 2   | 11.94     | 28.88             | 21.44 s   |
| 3   | 11.95     | 28.52             | 21.43 s   |
| **中央値** | **11.94** | 28.52 | 21.44 s |

前身レポート C-3 の eval 中央値 12.19 t/s に対し -0.25 t/s (-2.0%)。試行ばらつき範囲内で、C-3 の定常状態は維持されていることを確認。

### GPU 指標（eval 窓内平均、Run 1-3 の平均値）

| GPU | sm_avg (%) | sm_p95 (%) | sm_peak (%) | mem_avg (%) | pwr_avg (W) | rxpci (MB/s) | txpci (MB/s) | fb (MB) |
|-----|-----------:|-----------:|------------:|------------:|------------:|-------------:|-------------:|--------:|
| CUDA0 | **4.3** | 10.7 | 15.3 | 1.4 | 51.2 | 20.1 | 3.1 | 9799 |
| CUDA1 | **4.6** | 11.7 | 13.3 | 1.6 | 52.7 | 15.7 | 4.6 | 14269 |
| CUDA2 | **4.6** | 11.0 | 20.7 | 1.6 | 45.1 | 22.1 | 4.3 | 14269 |
| CUDA3 | **5.2** | 13.0 | 16.0 | 1.6 | 37.7 | 26.8 | 17.4 | 10581 |

- **idle (Run 0)**: 全 GPU で sm=0%, mem=0%, pwr=34-48W。観測基準線確立
- eval 中でも **SM 平均 4-5%**、ピーク ≤ 38%。P100 の計算資源はほぼ未使用
- **mem% < 2%** → VRAM 帯域も未使用
- **pwr は TDP 250W の 15-20%**
- CUDA 間の sm% 格差 ≤ 0.9pt → 層配置の非均等はなし
- CUDA3 の txpci が 17 MB/s と他 GPU (1-5 MB/s) より高い → 出力 logit を CPU に戻すパスと推定

### CPU 指標（eval 窓内平均、Run 1-3）

| Run | window (JST) | us (%) | sy (%) | id (%) | wa (%) | llama-server %CPU (avg) | p95 | samples |
|-----|--------------|-------:|-------:|-------:|-------:|------------------------:|----:|--------:|
| 0 (idle) | 全体 | 0.01 | 0.04 | 99.89 | 0.00 | 0.2 | 1.0 | 17 |
| 1 | 05:48:41–05:49:04 | **91.07** | 0.10 | 8.83 | 0.00 | **7336** | 8000 | 21 |
| 2 | 05:50:53–05:51:16 | **89.39** | 0.09 | 10.50 | 0.00 | **7304** | 8000 | 18 |
| 3 | 05:53:05–05:53:27 | **92.78** | 0.08 | 7.10 | 0.00 | **7617** | 8000 | 13 |

- **システム全体の us** が eval 中 89-93% → 80 論理 CPU のほぼ全てがユーザー空間計算に飽和
- **llama-server の %CPU** 平均 7300-7600、p95 で 8000（80 コア × 100%）に達する → llama-server だけで全論理 CPU を占有
- **sy (system) ≈ 0.1%**、**wa (I/O wait) = 0** → カーネル呼び出し・ディスク I/O・ページング系の待機はなし
- idle 基準 us=0.01% から eval 中 91% までの変化が直線的 → 観測オーバーヘッドは誤差範囲

## ボトルネック判定

プランの判定マトリクス適用:

| 観測値 | 閾値 | 判定 |
|--------|------|------|
| GPU sm% 平均 | 4-5% | **< 40% 成立** |
| CPU us 平均 | 89-93% | **> 70% 成立** |

→ **「CPU expert 計算律速」カテゴリに明確に分類**（GPU sm<40% かつ CPU us>70%）

### 根拠の重ね合わせ

1. GPU SM 平均 4-5% は「GPU がほとんど待機」を意味する（idle 0% からの上昇は存在するがきわめて小さい）
2. CPU は 80 論理コアがほぼ完全飽和（llama-server の %CPU がシステム総和の 92% を占める）
3. VRAM 帯域（mem%）も 1-2% と低く、GPU 側のメモリ帯域・計算ともに余力が大きい
4. PCIe 転送量（rxpci 12-27 MB/s、txpci 1-21 MB/s）は P100 の PCIe 3.0 x16 の理論帯域 15.75 GB/s に対して無視できる水準 → **PCIe 律速ではない**
5. wa=0 → ページング等の I/O 待ちでもない

### 「CPU 律速」の内部構造（本計測での推定）

- モデル構造: Qwen3.5-122B-A10B は n_layer=48, n_expert=256, n_expert_used=8 の MoE
- C-3 では 36 層分の `ffn_*_exps.weight`（各 expert の FFN 重み）を CPU 側に置いている
- 1 トークン生成ごとに、36 層 × 8 active experts × FFN 行列演算が CPU で実行される
- Q4_K_M 量子化済みでも重み総量は概算 60 GiB 超（4 bit × 数十 B params）で、メモリ帯域律速（Xeon 6138 のメモリ帯域 ≈ 120 GB/s）に近い可能性
- GPU 側は KV cache と 12 層分の expert のみ担当しており、CPU の完了を待ってから次層に進む逐次構造

## 結論と次アクション

### 結論

- **eval 頭打ちの要因は CPU 側の MoE expert 計算**で、GPU 層の追加では eval 改善幅が小さいことと整合する（C-1 → C-3 で GPU 層倍増 (6→12) しても +1.1% 止まり）
- GPU 側は完全に余力があり、sm% は 5% 未満。つまり **GPU 利用率を上げる方向の最適化は本質的解決にならない**
- ただし「CPU 側の層を減らす＝ GPU 側の層を増やす」方向であれば eval 改善に寄与しうる。CPU 律速である以上、**CPU 負担を減らすこと自体**が効く

### 次アクション（優先度付き）

1. **VRAM 確保 → 大幅な GPU 層増加**: C-3 は既に CUDA1/2 が 2 GiB マージンまで詰まっているため「12 層 → 例えば 24 層」に増やすには追加 VRAM が必要。`-ub 4096` で compute buffer を削減して空間を作り、layer 10-13 / 36-39 など CPU 側層を大幅に GPU 復帰させる。C-3 別派生実験（以下「C-4」）として別レポート化
2. **NUMA バインディング**: 2 socket × 40 core 構成で NUMA 未制御のまま稼働。`numactl --cpunodebind=0 --membind=0` でソケット 0 のみに制限すれば、inter-socket UPI を避けて CPU 計算速度が向上する可能性
3. **スレッド数明示制御**: `--threads -1`（自動）ではなく `--threads 40`（物理コア数）や `--threads 20` で HT 制御の比較
4. **量子化ダウン試験**: Q4_K_M → Q3_K_M / Q2_K の試行で、CPU 側の FFN 計算量を削減

### C-3 採用継続の妥当性

本計測で C-3 が CPU 律速であることが判明したが、これは「C-3 が悪い」意味ではない。C-1 (6 層) と C-3 (12 層) の差は +1.1% しかないが、**GPU は 5% 以下しか使っていないので電力・熱・安定性の観点で C-3 に不利な点もない**。従って C-3 採用を継続し、次は「CPU 層を減らすための VRAM 確保策」を試すのが合理的。

## 未検証事項

本レポート時点で未検証の事項（前身レポートから継続の既知項目を含む）:

### 既知項目（前身レポートから継続）

- [ ] **長時間安定性**: C-3 構成での連続稼働は累計約 15 分の実績のみ。1 時間超での安定性は未検証
- [ ] **大コンテキストでの eval 速度**: 16k〜128k の実プロンプトでの速度は未計測。本計測も短プロンプト（18 tokens in）のみ
- [ ] **flash-attn off との比較**: P100 CC 6.0 で `--flash-attn 1` が最適か未検証
- [ ] **CUDA1 の 2 GiB セーフティマージン**: プロンプト処理中のピーク使用量は未計測
- [ ] **層→GPU アライメントのソース解析**: llama.cpp の `--split-mode layer` 既定配置ロジックは未解析

### 新規項目（本レポートで判明）

- [ ] **CPU 飽和の内訳**: CPU us 91% の内訳（FFN 行列演算 vs メモリ帯域待ち vs NUMA inter-socket 転送）は不明。`perf record -g` や `vmstat`、`numastat` でプロファイル必要
- [ ] **NUMA 非バインディングの影響量**: 現状 2 socket 40 コアを NUMA 制御なしで使用中。`numactl --cpunodebind=0` でソケット 0 に固定した場合の eval 速度変化は未計測
- [ ] **llama-server のスレッド数実測**: `--threads -1` で実際に 80 スレッドが動いているか、HT を含む論理コア全部か物理 40 コアか、top の `THR` 列では識別困難。`/proc/$PID/status` の `Threads` 確認が必要
- [ ] **メモリ帯域ボトルネックの可能性**: Xeon 6138 のメモリ帯域 ≈ 120 GB/s に対し、36 層分の expert 重み（数十 GiB）を毎トークン読み出す場合、帯域律速の可能性がある。`pcm-memory` や `perf stat -e mem_load_retired` による実測が必要
- [ ] **CUDA3 の txpci が他より高い理由**: run 中 17-21 MB/s と他 GPU (1-5 MB/s) より一桁大きい。output 層が CUDA3 にあると推定されるが未確定
- [ ] **量子化を下げた場合の eval 向上量**: Q4_K_M → Q3_K_M / Q2_K_M / IQ2_XXS で CPU 側計算量がどれだけ減るか未計測

## 検証完了後に実施すべき TODO

次に実施すべき作業（前身レポートからの既知項目を含む）:

### 既知項目（前身レポートから継続）

- [ ] **start.sh の拡張**: `LLAMA_OT_OVERRIDE` 相当の環境変数サポートを追加し、C-3 を start.sh から起動可能にする
- [ ] **CUDA1 セーフティマージン OOM フォールバック実装**: 退避プランのドキュメント化
- [ ] **flash-attn off ベンチマーク**: compute buffer 増加とのトレードオフを計測
- [ ] **大コンテキスト実プロンプトでの eval 計測**: 16k / 32k / 64k / 128k での速度を体系的に測定
- [ ] **1 時間超の連続稼働試験**
- [ ] **層→GPU アライメントのソースコード解析**
- [ ] **eval ボトルネック解析**（→ **本レポートで完了。CPU expert 律速と判定**）
- [ ] **CUDA0/3 compute buffer 削減案 (`-ub 4096`)**（→ 下記「C-4 実験」として再定義）
- [ ] **layer 境界の詳細推定**（layer 20-23 / 31-35 の配置）
- [ ] **C-3 採用構成の start.sh プリセット化**

### 新規項目（本レポートで発見）

- [ ] **C-4 実験: `-ub 4096` + 大幅な GPU 層追加**: 本レポートで「CPU 律速」と判明したため、compute buffer 削減で確保できる VRAM を使って CPU 層を大幅（12 → 例えば 20-24 層）に GPU に移す。単なる layer 10-13 追加ではなく、可能な限り多く移す設計
- [ ] **NUMA バインディング試行**: `numactl --cpunodebind=0 --membind=0 -- ./llama-server ...` で片方 socket 固定の eval 変化を測定。メモリが 1 socket に収まるか（現状モデル常駐量 < 128 GiB なので可能）確認
- [ ] **`--threads` 明示値比較**: `--threads 40`（物理コア）/ `--threads 80`（HT 込み論理コア）/ `--threads 20`（1 socket 物理）/ `--threads -1`（自動）の 4 パターンで eval 比較
- [ ] **量子化変更比較**: Q4_K_M（現行）vs Q3_K_M vs IQ2_XXS での eval 速度と出力品質の比較
- [ ] **`perf` による CPU プロファイル**: `perf record -g -p <llama-pid> sleep 20` を eval 中に取得、`perf report` で expert FFN のホットスポット特定
- [ ] **`pcm-memory` / `perf stat -e` によるメモリ帯域実測**: expert 重み読み出しが DRAM 帯域律速かを判定
- [ ] **CUDA3 txpci 高値の理由特定**: llama-server ログや load_tensors 出力から output 層の配置 GPU を確定

## 補足

- C-3 構成は稼働継続（本計測は観測のみ、再起動なし）
- 作業終了時点の VRAM 分布（計測直前の nvidia-smi）: CUDA0 used 9799 / CUDA1 14269 / CUDA2 14269 / CUDA3 10581 MiB（前身レポートと一致）
- 観測オーバーヘッド確認済み: idle 時 us=0.01%、eval 時 us=91%、idle の dmon+top 3 本が同時実行されても CPU us は 0.01%、つまり観測ツール自身の負荷は誤差範囲
- 計測総所要時間: 約 5 分（idle 20s + eval×3 40s + cooldown×2 60s + ssh 接続オーバーヘッド）
- ロック解放は本レポート作成後に実施
