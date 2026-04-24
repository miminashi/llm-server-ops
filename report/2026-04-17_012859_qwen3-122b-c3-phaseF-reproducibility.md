# Qwen3.5-122B-A10B C-3 NUMA 最適化 Phase F（C-E5 `--numa isolate` 再現性検証 / C-D3 ベースライン再取得）

- **実施日時**: 2026年4月17日 01:28 – 03:30 (JST)
- **作業種別**: 計測・比較（Phase E 未検証事項の検証）

## 添付ファイル

- [実装プラン](attachment/2026-04-17_012859_qwen3-122b-c3-phaseF-reproducibility/plan.md)
- [起動スクリプト](attachment/2026-04-17_012859_qwen3-122b-c3-phaseF-reproducibility/start_phaseF.sh)
- [計測スクリプト](attachment/2026-04-17_012859_qwen3-122b-c3-phaseF-reproducibility/measure_phaseF.sh)
- C-F1a ログ一式: `out_F1a_cpunodebind_threads40/`（C-D3 1 回目）
- C-F2a ログ一式: `out_F2a_numa_isolate/`（C-E5 1 回目）
- C-F1b ログ一式: `out_F1b_cpunodebind_threads40/`（C-D3 2 回目）
- C-F2b ログ一式: `out_F2b_numa_isolate/`（C-E5 2 回目）
- C-F1c ログ一式: `out_F1c_cpunodebind_threads40/`（C-D3 3 回目）
- C-F2c ログ一式: `out_F2c_numa_isolate/`（C-E5 3 回目）
- 副次計測: `out_F2a_continued_10min/`（F2a プロセス継続稼働 ~10 分後の追加 3 run、操作ミスにより取得）

各ディレクトリに `{eval_run{1,2,3}.json, dmon_run{1,2,3}.log, status_run3.txt, numastat_pre.txt, numastat_post.txt, cmdline.txt, timeline.log}` を格納。

## 参照

- 前身レポート: [2026-04-16_225920_qwen3-122b-c3-phaseE-smt.md](2026-04-16_225920_qwen3-122b-c3-phaseE-smt.md)
- C-D3 採用: [2026-04-16_150717_qwen3-122b-c3-phaseD.md](2026-04-16_150717_qwen3-122b-c3-phaseD.md)
- C-3 Phase C: [2026-04-16_072324_qwen3-122b-c3-numa-phaseC.md](2026-04-16_072324_qwen3-122b-c3-numa-phaseC.md)

## 前提・目的

Phase E で以下 2 点が最優先の未検証事項として残っていた:

- **G-5（新規最重要）**: C-E5 (`--numa isolate` 併用) の Phase E 初回 +5.1% (15.00 t/s) が再現するか。再計測 C-E5b では 14.75 t/s で揺らぎ 0.25 t/s、統計的有意性未確定
- **G-6（優先度上昇）**: C-D3 の長時間稼働劣化（Phase D 直後 15.03 → Phase E 1 時間後 14.27、−5.1%）が再起動で回復するか、それとも何らかの環境変化か

本 Phase F はこれら 2 点を 1 セッションで同時検証する。判定には「現行のマシン状態での C-D3 ベースライン」を同一プロトコルで再取得することが必須（Phase D 値 15.03 が今のマシン状態を代表しない可能性があるため）。

### 成功条件

- **採用判定**: M_F2 (C-E5 中央値) ≥ M_F1 (C-D3 中央値) × 1.03 → C-E5 を採用候補に昇格
- **再現判定**: M_F2 − M_F1 ≥ 0.2 t/s → 「再現した」と記録（採用基準未達でも効果あり所見として残す）
- **C-D3 ベースライン**: F1a/F1b/F1c の最大 − 最小が 0.3 t/s 以内なら安定

## 環境情報

- **サーバ**: `t120h-p100` (10.1.4.14)
- **GPU**: NVIDIA Tesla P100-PCIE-16GB × 4
- **CPU**: Intel Xeon Gold 6138 @ 2.00GHz × 2 socket、計 40 コア / 80 スレッド、NUMA 2 ノード（Node 0={CPU 0-19,40-59}, Node 1={CPU 20-39,60-79}）
- **メモリ**: 257,560 MiB (約 251 GiB)
- **モデル**: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- **llama.cpp ビルド**: b8807-b3d758750（Phase D/E と同一）
- **観測**: `nvidia-smi dmon` (20 秒/run)、`/proc/$PID/status` (Run 3 のみ)、`numastat -p` (各サイクル pre/post 1 回ずつ)
- **ページキャッシュ**: warm（Phase E 終了時から継続、Node 1 に 68 GiB 以上が残存）

## 計測手順（再現方法）

各サイクル共通プロトコル:

1. `.claude/skills/llama-server/scripts/stop.sh t120h-p100` で既存プロセス停止 → 15 秒待機
2. `start_phaseF.sh <F1|F2>` で fresh 起動、`/health` 200 確認
3. llama-server 本体 PID を `ps -eo pid,comm,args | awk '$2=="llama-server" {print $1; exit}'` で取得（Phase E で親 bash 誤検知が判明したため修正）
4. `measure_phaseF.sh <pid> <tag>` 実行
5. 3 run 実施（各 run 前 60 秒 cooldown、eval プロンプト `"Write a short haiku about autumn."`、`max_tokens=256`、`stream=false`）
6. `timings.predicted_per_second` / `timings.prompt_per_second` を記録
7. `numastat -p $PID` を Run 1 直前と Run 3 終了後に取得
8. Run 3 のみ `/proc/$PID/status` スナップショット

### 実行順（交互配置で順序効果を相殺）

```
F1a → F2a → F1b → F2b → F1c → F2c
```

### 各構成の起動差分

| 構成 | プレフィックス | `--threads` | 追加引数 |
|------|--------------|:----------:|---------|
| **C-F1 (= C-D3 追試)** | `numactl --cpunodebind=1 --membind=1 --` | 40 | (なし) |
| **C-F2 (= C-E5 追試)** | `numactl --cpunodebind=1 --membind=1 --` | 40 | **`--numa isolate`** |

共通引数（Phase E と完全同一）: `-ngl 999 -ot 'blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU' --flash-attn 1 --poll 0 -b 8192 -ub 8192 --n-predict 32768 --ctx-size 131072 --parallel 1 --cache-type-k q8_0 --cache-type-v q8_0 --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0`

## 実行結果サマリ

### eval 速度（predicted_per_second）

| サイクル | 構成 | Run 1 | Run 2 | Run 3 | 中央値 | 前サイクル比 |
|---------|------|------:|------:|------:|------:|------------:|
| F1a | C-D3 (初回) | 14.486 | 14.505 | 14.492 | **14.49** | 基準 |
| F2a | C-E5 (1 回目) | 14.752 | 14.752 | 14.640 | **14.75** | +1.8% |
| F1b | C-D3 (2 回目) | 14.856 | 14.804 | 14.792 | **14.80** | +0.3% vs F1a, +2.1% |
| F2b | C-E5 (2 回目) | 14.373 | 14.351 | 14.425 | **14.37** | −2.9% vs F2a, −2.9% |
| F1c | C-D3 (3 回目) | 14.802 | 14.810 | 14.808 | **14.81** | +0.1% vs F1b |
| F2c | C-E5 (3 回目) | 14.442 | 14.434 | 14.475 | **14.44** | +0.5% vs F2b |

### グループ中央値と判定

| グループ | 各サイクル中央値 | **グループ中央値** | **Phase D C-D3 基準 (15.03) 比** |
|---------|:---------------:|:----------------:|:-----------------------------:|
| F1 (C-D3) | 14.49 / 14.80 / 14.81 | **14.80** | −1.5% |
| F2 (C-E5) | 14.75 / 14.37 / 14.44 | **14.44** | −3.9% |

**判定**:

- **M_F2 (14.44) < M_F1 (14.80)** → C-E5 は C-D3 より **0.36 t/s (−2.4%) 遅い**
- **採用基準 (M_F2 ≥ M_F1 × 1.03 = 15.24)**: 未達成（大幅未達）
- **再現基準 (M_F2 − M_F1 ≥ 0.2 t/s)**: **逆方向に差分あり**。Phase E の「C-E5 が +5.1% 速い」は再現しなかった
- **結論**: C-D3 継続採用。C-E5 (`--numa isolate`) は採用しない

### prompt 処理速度（prompt_per_second）

| サイクル | Run 1 | Run 2 | Run 3 | 中央値 |
|---------|------:|------:|------:|------:|
| F1a | 28.53 | 32.83 | 32.89 | **32.83** |
| F2a | 28.54 | 32.87 | 32.75 | **32.75** |
| F1b | 28.95 | 32.76 | 32.95 | **32.76** |
| F2b | 28.73 | 32.98 | 32.94 | **32.94** |
| F1c | 28.67 | 32.29 | 32.81 | **32.29** |
| F2c | 28.61 | 32.63 | 32.15 | **32.63** |

- 全サイクルで Run 1 のみ 28.5〜29.0 に低下、Run 2/3 は 32.2〜33.0 → **prompt キャッシュの warm-up 効果**（Run 2 以降は KV キャッシュが活きる）

### プロセス状態（Run 3 後の /proc/$PID/status）

| 指標 | F1a | F2a | F1b | F2b | F1c | F2c |
|------|----:|----:|----:|----:|----:|----:|
| Threads | 126 | 126 | 126 | 126 | 126 | 126 |
| Cpus_allowed_list | 20-39,60-79 | **0-79** | 20-39,60-79 | **0-79** | 20-39,60-79 | **0-79** |
| voluntary_ctxt_switches | **3910** | 355 | 283 | 364 | 285 | 359 |
| nonvoluntary_ctxt_switches | 203 | 137 | 83 | 195 | 79 | 119 |

- **F1 (`--cpunodebind=1`) は Cpus_allowed_list=20-39,60-79** で Node 1 に拘束、**F2 (`--numa isolate`) は Cpus_allowed_list=0-79** で全 80 CPU に解放（Phase E と同挙動を確認）
- F1a のみ voluntary_ctxt_switches=3910 と突出（他は 283〜364）。他のサイクル初回（F2a=355, F1b=283）と比較しても異常値で、F1a だけで何らかの初期化ノイズが発生している可能性

### NUMA メモリ配置（numastat -p、Run 3 後）

| サイクル | Node 0 | Node 1 | Total | N0 比率 |
|---------|-------:|-------:|------:|--------:|
| F1a | 8.46 MiB | 69,077 MiB | 69,086 MiB | 0.012% |
| F2a | 8.49 MiB | 68,312 MiB | 68,321 MiB | 0.012% |
| F1b | 8.28 MiB | 69,077 MiB | 69,086 MiB | 0.012% |
| F2b | 8.46 MiB | 68,313 MiB | 68,322 MiB | 0.012% |
| F1c | 8.42 MiB | 69,077 MiB | 69,086 MiB | 0.012% |
| F2c | 8.41 MiB | 68,314 MiB | 68,322 MiB | 0.012% |

- 全サイクルで Node 1 比率 >99.98%（`--membind=1` が有効）
- F1 系は 69,077 MiB、F2 系は 68,313 MiB で約 764 MiB 少ない（`--numa isolate` がメモリ確保パターンを変更している可能性）

## ボトルネック・副次発見の分析

### 1. C-E5 (`--numa isolate`) は C-D3 より遅い（Phase E とは逆結論）

Phase E では C-E5 = 15.00（初回）/14.75（再計測）で C-E1 14.27 より +5.1%/+3.4%。しかし Phase F では C-E5 中央値 14.44 で C-D3 中央値 14.80 より **−2.4%**。

仮説:
- Phase E 初回 C-E5 の 15.00 は **順序効果**。Phase E では C-E1 → C-E2 → C-E3 → C-E4 → C-E5 と 5 variant 連続計測した最後に C-E5 を実施。それまでの 4 variant で累積 80 分稼働した後に fresh restart したため、Node 1 のページキャッシュが極めて温まっていた
- Phase F の初回サイクル効果は **variant ごとに逆方向**: F1a だけ 14.49（F1b/c より −0.3）、F2a だけ 14.75（F2b/c より +0.3）。これはサイクル順序（F1a が第 1 サイクル、F2a が第 2 サイクル）に起因する warm-up の効き方の違いの可能性

### 2. 「初回サイクル効果」の観測

- F1a (第 1 サイクル) = 14.49 → 他の F1 より −0.31
- F2a (第 2 サイクル) = 14.75 → 他の F2 より +0.31〜+0.38
- F1b/c と F2b/c は安定（中央値 14.80/14.81 と 14.37/14.44）

第 1 サイクル起動直後はメモリ確保が新鮮だが ctxt_switches が多発（F1a: 3910 vs 他 283〜364）、第 2 サイクル以降は ctxt_switches が落ち着く。これが F1a の−0.3 t/s の原因の可能性。

F2a が F2b/c より速かったのは、第 2 サイクルの起動直後に Node 1 ページキャッシュがまだ第 1 サイクル (F1a) の残存で温まっていたため、と推測。第 3・5 サイクルでは F2 起動前に F1 が走ったため、ページキャッシュが F1 ワークロード向けに再配置されていた可能性。

この「warm-up の方向性差」は再現性の難しさを意味する。**C-E5 の Phase E 初回 15.00 も同様の一回限りの揺らぎの可能性が極めて高い**。

### 3. F2 プロセス継続稼働 10 分後の劣化（副次観測）

操作ミスで F2 プロセス (PID 59354) が停止されずに 10 分経過した後の追加 3 run (`out_F2a_continued_10min`):

| 時点 | Run 1 | Run 2 | Run 3 | 中央値 | F2a 比 |
|------|------:|------:|------:|------:|-------:|
| F2a (初回) | 14.752 | 14.752 | 14.640 | 14.75 | 基準 |
| F2a_continued (+10 分) | 14.532 | 14.529 | 14.517 | **14.53** | **−1.5%** |

- F2 (`--numa isolate`) プロセスを停止せずに 10 分経過で −0.22 t/s の劣化
- Phase E の C-E5 (15.00) → C-E5b (14.75) の −0.25 t/s と同水準の劣化率
- **`--numa isolate` は short-term (10 分) で劣化する**という所見を支持

### 4. C-D3 は Phase D 値 (15.03) を再現しない

F1b/F1c 中央値 14.80/14.81 は Phase D 値 15.03 より −1.5%。fresh restart 直後ですら 15.03 には届かない。

仮説:
- Phase D 計測時 (4/16 15:07) と Phase F 計測時 (4/17 01:28) の間の 10 時間強で、何らかの環境変化（他プロセスの活動履歴、メモリ断片化、ページキャッシュの再配置）が蓄積している
- あるいは Phase D の 15.03 自体が 1 回限りの上振れだった可能性（Phase D でも 3 run 平均で計測しており統計的信頼度は中程度）

**現時点の C-D3 実効値は 14.80 t/s 程度**と再評価するのが妥当。

### 5. F1a の voluntary_ctxt_switches=3910 の異常

| サイクル | 順序 | voluntary_ctxt_switches |
|---------|:----:|------------------------:|
| F1a | 1 | **3910** |
| F2a | 2 | 355 |
| F1b | 3 | 283 |
| F2b | 4 | 364 |
| F1c | 5 | 285 |
| F2c | 6 | 359 |

F1a のみ 10 倍突出。**他のサイクル初回（F1b, F1c）は 283〜285 で安定**。Phase E の C-D3 (273) / C-E1 (3300) もこの振れ幅を確認していた。

F1a の速度低下 (14.49 vs 14.80) と ctxt_switches 多発が相関しているように見える。**「fresh restart 直後の第 1 サイクル」は何か特別な初期化ノイズがある**可能性。Phase E も 1 時間稼働後の C-E1 で ctxt_switches が増えていた。

## 採用判定

| 構成 | F1 中央値 | F2 中央値 | 採用 |
|------|---------:|---------:|:----:|
| **C-D3 (現行採用)** | **14.80** | ― | **継続採用** |
| C-E5 (`--numa isolate`) | ― | 14.44 | **非採用確定** |

**新採用なし。C-D3 (`numactl --cpunodebind=1 --membind=1 -- + --threads 40`) を継続採用。**

Phase E の「C-E5 +5.1%」は **1 回限りの順序効果による上振れ** と結論。以降の Phase では `--numa isolate` は検討対象から外してよい。

## 採用構成（C-D3）の再起動コマンド

Phase D / Phase E と同一:

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
.claude/skills/llama-server/scripts/stop.sh t120h-p100

MODEL_PATH="/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf"

LAUNCH_CMD="numactl --cpunodebind=1 --membind=1 -- ./build/bin/llama-server \
  -m '$MODEL_PATH' --jinja \
  -ngl 999 -ot 'blk\\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\\.ffn_.*_exps\\.weight=CPU' \
  --flash-attn 1 --poll 0 -b 8192 -ub 8192 \
  --n-predict 32768 --threads 40 \
  --ctx-size 131072 --parallel 1 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 \
  --port 8000 --host 0.0.0.0 \
  --alias 'unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M'"

ssh -f t120h-p100 "cd ~/llama.cpp && nohup bash -c \"\$LAUNCH_CMD\" > /tmp/llama-server.log 2>&1 < /dev/null &"
until curl -sf http://10.1.4.14:8000/health > /dev/null; do sleep 5; done
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 未検証事項

### 既知項目（前身レポートから継続）

- [ ] **1 時間超の連続稼働試験**: 本 Phase F は短サイクル（各 restart 間隔 ~7 分）で計測。本格的な長時間劣化曲線（30 分おきに計測 × 2 時間等）は未実施
- [ ] **大コンテキストでの eval 速度**: 16k〜128k の実プロンプトでの速度は未計測
- [ ] **flash-attn off との比較**: P100 CC 6.0 で `--flash-attn 1` が最適か未検証
- [ ] **CUDA1 の 2 GiB セーフティマージン**: プロンプト処理中のピーク使用量は未計測
- [ ] **層→GPU アライメントのソース解析**: llama.cpp の `--split-mode layer` 既定配置ロジックは未解析
- [ ] **ページキャッシュのコールドスタート検証**: `sudo sysctl vm.drop_caches=3` 権限が llm ユーザーにないため未実施
- [ ] **量子化ダウンでの eval 向上量**: Q4_K_M → Q3_K_M / IQ2_XXS
- [ ] **pcm-memory による DRAM 帯域実測**
- [ ] **C-D3 + コールドスタート**
- [ ] **Node 0 側のコールドスタート C-D6**
- [ ] **perf stat での C-D3 の node-load-miss rate**
- [ ] **C-4 実験**（CPU 層 36 → 20 層未満）
- [ ] **他モデルでの同様の傾向**（Qwen3.5-35B-A3B 等）
- [ ] **`--threads 30` / `--threads 28` などの中間値**（Phase E から継続）
- [ ] **`--numa numactl` モード**（llama.cpp フラグ）: isolate / distribute / numactl の 3 モードあるが numactl モードは未検証
- [ ] **OpenMP 環境変数の影響**: `OMP_PROC_BIND=close` / `OMP_PLACES=cores` 等を明示設定した場合の挙動

### 新規項目（本レポートで判明・発生）

- [ ] **「初回サイクル効果」の原因特定**: 第 1 サイクル fresh restart だけ voluntary_ctxt_switches が 10 倍 (3910 vs 283) 突出、速度も −0.3 t/s 低下する。メモリアロケーション初期化、OpenMP thread affinity の初期化、あるいは GPU 側の warm-up のいずれが主因か不明。第 1 サイクルを破棄する運用が妥当か要検証
- [ ] **「サイクル順序依存の warm-up」の影響**: F2a (14.75) と F2b/c (14.37/14.44) の 0.3 t/s 差は、直前の F1 サイクルのページキャッシュ状態に影響されている可能性。variant 切り替え時のキャッシュ状態を制御した再計測が必要
- [ ] **Phase D 値 (15.03) の再現性**: Phase D の 15.03 は Phase F の fresh restart 3 回（14.49/14.80/14.81）いずれも再現しない。Phase D 計測が 1 回限りの上振れだった可能性が高いが、再計測で確認が必要
- [ ] **F2 (`--numa isolate`) の 10 分劣化メカニズム**: F2a 14.75 → F2a_continued_10min 14.53 (−1.5%) の劣化は、`--numa isolate` 特有の現象か、C-D3 でも同様に発生するか未検証。F1 (C-D3) 継続稼働での 10 分後計測が必要
- [ ] **F1a の voluntary_ctxt_switches=3910 の原因特定**: 他サイクル (283〜364) の 10 倍。fresh restart 直後の初期化負荷か、あるいは stop.sh が前プロセス (Phase E の PID 57017/57018) の終了直後だった特殊状況か

## 検証完了後に実施すべき TODO

### 既知項目（前身レポートから継続）

- [ ] **start.sh の拡張**: `LLAMA_NUMACTL_PREFIX` / `LLAMA_EXTRA_THREADS` 環境変数サポート追加。C-D3 (`-N1 -m1 + threads=40`) を start.sh から起動可能にする
- [ ] **CUDA1 セーフティマージン OOM フォールバック実装**
- [ ] **flash-attn off ベンチマーク**
- [ ] **大コンテキスト実プロンプトでの eval 計測**（16k / 32k / 64k / 128k）
- [ ] **1 時間超の連続稼働試験**（C-D3 構成で）← **Phase E/F で未着手、引き続き優先度高**
- [ ] **層→GPU アライメントのソースコード解析**
- [ ] **C-4 実験**（CPU 層削減 + GPU 層追加）
- [ ] **drop_caches 権限の確保**（sudoers 設定 or vmtouch 導入）
- [ ] **C-D3 での perf stat 計測**: node-load-miss が理論通り激減しているか確認
- [ ] **コールドスタート C-D6 計測**: Node 間対称性の証明
- [ ] **start.sh での NUMA プリセット整備**: `NUMA_MODE=pinned_node1_t40` 等
- [ ] **start.sh に `--threads` 設定追加**: C-E2 (t=20) と C-E1 (t=40) が同等なら、省電力・共存重視のシナリオで t=20 を選べるようにする（Phase E から継続）

### 新規項目（本レポートで発見）

- [ ] **計測プロトコルから「第 1 サイクル破棄」の導入検討**: F1a/F2a が他サイクルより異常値を出したため、今後の variant 比較では第 1 サイクルを warm-up として破棄し、第 2 サイクル以降のみで中央値を算出する方針を検討
- [ ] **`--numa isolate` の評価対象からの除外**: Phase F で採用可能性が否定されたため、以降の NUMA 関連実験では候補から外す。`--numa distribute` / `--numa numactl` モードも同様に低期待値だが、念のため 1 回ずつ計測しておくとよい
- [ ] **「ページキャッシュ状態のスナップショット取得」を計測プロトコルに追加**: 各サイクルの `free -w` / `numastat -m` を記録して、variant 間のキャッシュ配置差を追跡可能にする
- [ ] **PID 取得ロジックの統一**: 本 Phase F では `ps -eo pid,comm,args | awk '$2=="llama-server" {print $1; exit}'` を採用し正常動作を確認。運用スクリプト全体で同方式に切り替えを検討（Phase E から継続）
- [ ] **compound bash コマンドでの `cd` ミス対策**: 本 Phase F のサイクル 3 開始時に cwd の不整合で stop.sh が不発し、F2 プロセスが継続稼働したまま F1b を計測する事故が発生（リカバリ済、ログは `out_F2a_continued_10min/` として保存）。各サイクルを単発 bash コマンドに分割する運用に変更

## 補足

- 作業終了時点で **C-D3 構成（`numactl --cpunodebind=1 --membind=1 -- + --threads 40`）で再稼働中**（PID 65837、--port 8000）
- GPU サーバロック（t120h-p100）は解放済み
- 本 Phase F で **Phase E の「C-E5 +5.1%」は再現せず、1 回限りの上振れと結論**
- 副次的に **C-D3 Phase D 値 15.03 も再現せず**、現時点の実効値は **14.80 t/s** と再評価
- Phase E の 2 要因整理（「メモリ局所性 + 非オーバーサブスクリプション」）は本 Phase でも維持
