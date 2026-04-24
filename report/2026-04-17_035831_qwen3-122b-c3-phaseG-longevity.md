# Qwen3.5-122B-A10B C-3 Phase G（C-D3 長時間稼働劣化の定量化）

- **実施日時**: 2026年4月17日 03:58 – 07:05 (JST)
- **作業種別**: 計測・検証（Phase F 最優先未検証事項「1 時間超の連続稼働試験」）

## 添付ファイル

- [実装プラン](attachment/2026-04-17_035831_qwen3-122b-c3-phaseG-longevity/plan.md)
- [計測スクリプト](attachment/2026-04-17_035831_qwen3-122b-c3-phaseG-longevity/measure_phaseG.sh)
- G0 ログ一式: `out_G0_aged_27m/`（Phase F 由来プロセス、PID 65837）
- G_aged ログ一式: `out_G_aged_t96/`（Phase F 由来プロセス、PID 67966、96 分稼働時点）
- G1a ログ一式: `out_G1a_fresh_t0/`（新規 restart 直後、PID 70510）
- G1b ログ一式: `out_G1b_fresh_t20/`（restart 後 20 分）
- G1c ログ一式: `out_G1c_fresh_t30/`（restart 後 30 分）
- G1d ログ一式: `out_G1d_fresh_t60/`（restart 後 60 分）

各ディレクトリに `{eval_run{1,2,3}.json, dmon_run{1,2,3}.log, status_run{1,2,3}.txt, numastat_pre.txt, numastat_post.txt, free_pre.txt, free_post.txt, numastat_m_pre.txt, numastat_m_post.txt, gpu_pre.csv, gpu_post.csv, sched_pre.txt, sched_post.txt, cmdline.txt, timeline.log}` を格納。

## 参照

- 前身レポート: [2026-04-17_012859_qwen3-122b-c3-phaseF-reproducibility.md](2026-04-17_012859_qwen3-122b-c3-phaseF-reproducibility.md)
- Phase E: [2026-04-16_225920_qwen3-122b-c3-phaseE-smt.md](2026-04-16_225920_qwen3-122b-c3-phaseE-smt.md)
- Phase D: [2026-04-16_150717_qwen3-122b-c3-phaseD.md](2026-04-16_150717_qwen3-122b-c3-phaseD.md)

## 前提・目的

Phase F で以下 2 点が最優先の未検証事項として残っていた:

- **1 時間超の連続稼働試験**: C-D3 構成での長時間劣化曲線（Phase D/E を通じて繰り返し言及）
- **C-D3 でも 10 分劣化が起きるか**: Phase F で F2 (`--numa isolate`) の 10 分継続稼働で −1.5% が観測されたが、C-D3 でも同様か未検証

背景: Phase E で「C-D3 fresh 直後 15.03 → 1 時間後 14.27 (−5.1%)」という劣化が観測されていた。Phase F ではこの追試を計画したが short-cycle (7 分/サイクル) の比較にとどまった。

本 Phase G では:
1. 現行稼働中の aged プロセスを計測して長時間稼働後の劣化度を確認
2. Fresh restart して 0/20/30/60 分の時系列を取り、劣化カーブを定量化

### 成功条件

- **劣化あり（Phase E 再現）**: `median(G1d t=60) ≤ median(G1a t=0) × 0.96` かつ差分 ≥ 0.2 t/s
- **再起動で回復**: `median(G1a) ≥ median(G_aged) + 0.3 t/s`

## 環境情報

- **サーバ**: `t120h-p100` (10.1.4.14)
- **GPU**: NVIDIA Tesla P100-PCIE-16GB × 4
- **CPU**: Intel Xeon Gold 6138 @ 2.00GHz × 2 socket、計 40 コア / 80 スレッド、NUMA 2 ノード
- **メモリ**: 257,560 MiB (約 251 GiB)
- **モデル**: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- **llama.cpp ビルド**: b8807-b3d758750（Phase D/E/F と同一）
- **構成**: C-D3 のみ（`numactl --cpunodebind=1 --membind=1 -- + --threads 40`）

## 計測手順（再現方法）

### 計測プロトコル

Phase F の `measure_phaseF.sh` を拡張した `measure_phaseG.sh` を使用。Phase F からの差分:

- `/proc/$PID/status` スナップショットを全 Run (1/2/3) で取得（Phase F は Run 3 のみ）
- 各サイクルの pre/post で追加スナップショット: `free -w`, `numastat -m`, `nvidia-smi --query-gpu`, `/proc/$PID/sched`

各 run: eval プロンプト `"Write a short haiku about autumn."`、`max_tokens=256`、`stream=false`。Run 間 60 秒 cooldown。1 サイクル約 5 分。

### 実行タイムライン

当初計画は restart 後 0/15/30/60 分の 4 点を取る予定だったが、`start_phaseF.sh` 実行時に Bash ツールのバックグラウンド化誤動作が発生し、最初の restart プロセス (PID 67966) が 96 分間 idle 稼働する事態となった。この結果、計測は 2 フェーズに分かれた:

**フェーズ 1: aged プロセス計測**

| タグ | プロセス | etime | 時刻 (JST) |
|------|---------|------:|----------:|
| G0_aged_27m | PID 65837 (Phase F 由来) | 27 分 | 04:00 |
| G_aged_t96 | PID 67966 (restart 後 idle 稼働) | 96 分 | 05:44 |

**フェーズ 2: fresh restart 後の時系列計測**

| タグ | 経過時間 | 時刻 (JST) |
|------|-------:|----------:|
| G1a_fresh_t0 | 0 分 | 06:00 |
| G1b_fresh_t20 | 20 分 | 06:20 |
| G1c_fresh_t30 | 30 分 | 06:30 |
| G1d_fresh_t60 | 60 分 | 07:00 |

### 再現コマンド

```bash
# aged プロセスの計測（既存プロセスの PID を指定）
PID=$(ssh t120h-p100 "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
bash measure_phaseG.sh $PID G0_aged_27m

# restart
.claude/skills/llama-server/scripts/stop.sh t120h-p100
bash start_phaseF.sh F1 </dev/null > /tmp/start.log 2>&1
PID=$(ssh t120h-p100 "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
T0=$(date +%s)

# 時系列計測
bash measure_phaseG.sh $PID G1a_fresh_t0
sleep $((T0 + 20*60 - $(date +%s))); bash measure_phaseG.sh $PID G1b_fresh_t20
sleep $((T0 + 30*60 - $(date +%s))); bash measure_phaseG.sh $PID G1c_fresh_t30
sleep $((T0 + 60*60 - $(date +%s))); bash measure_phaseG.sh $PID G1d_fresh_t60
```

## 実行結果サマリ

### eval 速度（predicted_per_second）

| タグ | 経過時間 | Run 1 | Run 2 | Run 3 | 中央値 | G1a 比 |
|------|-------:|------:|------:|------:|------:|-------:|
| **G0_aged_27m** | 27m (別PID) | 14.908 | 14.905 | 14.917 | **14.908** | +0.3% |
| **G_aged_t96** | 96m (別PID) | 14.027 | 14.035 | 14.021 | **14.027** | **−5.6%** |
| G1a_fresh_t0 | 0m | 14.867 | 14.865 | 14.875 | **14.867** | 基準 |
| G1b_fresh_t20 | 20m | 14.878 | 14.877 | 14.871 | **14.877** | +0.1% |
| G1c_fresh_t30 | 30m | 14.868 | 14.867 | 14.867 | **14.867** | ±0.0% |
| G1d_fresh_t60 | 60m | 14.873 | 14.871 | 14.863 | **14.871** | ±0.0% |

### 判定結果

- **劣化あり（Phase E 再現）基準**: `median(G1d) ≤ median(G1a) × 0.96` → 14.871 > 14.272 → **不成立。60 分では劣化なし**
- **aged 劣化**: G_aged_t96 = 14.027 は G1a = 14.867 の 94.4% → **−5.6% 劣化を観測**（ただし別プロセス・別条件）
- **再起動で回復**: G1a (14.867) ≥ G_aged_t96 (14.027) + 0.3 → 14.867 ≥ 14.327 → **成立。再起動で回復**

### prompt 処理速度（prompt_per_second）

| タグ | Run 1 | Run 2 | Run 3 | 中央値 |
|------|------:|------:|------:|------:|
| G0_aged_27m | 28.72 | 32.84 | 33.28 | **32.84** |
| G_aged_t96 | 28.54 | 32.62 | 33.05 | **32.62** |
| G1a_fresh_t0 | 28.74 | 32.85 | 32.99 | **32.85** |
| G1b_fresh_t20 | 32.80 | 32.53 | 32.88 | **32.80** |
| G1c_fresh_t30 | 32.96 | 33.24 | 33.26 | **33.24** |
| G1d_fresh_t60 | 33.22 | 33.25 | 33.26 | **33.25** |

- G1a の Run 1 のみ 28.74 に低下（prompt キャッシュ warm-up）、Run 2 以降は 32.8〜33.3 で安定
- G1b 以降は Run 1 から 32.5+ で安定（warm-up 完了済み）
- G_aged_t96 でも prompt 速度は正常 (32.62)。**劣化は eval (token generation) のみ**

### プロセス状態（/proc/$PID/status、Run 3 時点）

| タグ | PID | Threads | Cpus_allowed_list | vol_ctxt | nonvol_ctxt |
|------|----:|--------:|:------------------|---------:|------------:|
| G0_aged_27m | 65837 | 126 | 20-39,60-79 | 1,985 | 76 |
| G_aged_t96 | 67966 | 126 | 20-39,60-79 | 6,174 | 78 |
| G1a_fresh_t0 | 70510 | 126 | 20-39,60-79 | 812 | 161 |
| G1b_fresh_t20 | 70510 | 126 | 20-39,60-79 | 1,986 | 265 |
| G1c_fresh_t30 | 70510 | 126 | 20-39,60-79 | 2,514 | 408 |
| G1d_fresh_t60 | 70510 | 126 | 20-39,60-79 | 4,262 | 532 |

- Cpus_allowed_list は全サイクルで 20-39,60-79（Node 1 に拘束、正常）
- voluntary_ctxt_switches は累積値。G1 プロセスでの増加レート ~68/min、G_aged プロセスでも ~65/min で同等

### スケジューラ統計（/proc/$PID/sched）

| タグ | nr_migrations | nr_voluntary_switches | nr_involuntary_switches |
|------|--------------:|----------------------:|------------------------:|
| G0_aged_27m (post) | 1 | 2,005 | 76 |
| G_aged_t96 (post) | 1 | 6,192 | 78 |
| G1a_fresh_t0 (post) | 1 | 831 | 161 |
| G1d_fresh_t60 (post) | 4 | 4,281 | 532 |

- nr_migrations: G1d で 4 回（G_aged は 1 回）。マイグレーション数と劣化は非相関
- G_aged_t96 の nonvoluntary_ctxt_switches=78 は G1d の 532 より大幅に少ない → **G_aged プロセスは idle 時間中に eval を受けていないため nonvoluntary が少ない**

### NUMA メモリ配置（numastat -p、post 時点）

| タグ | PID | Node 0 (MiB) | Node 1 (MiB) | Total (MiB) |
|------|----:|-------------:|-------------:|------------:|
| G0_aged_27m | 65837 | 8.48 | 69,077 | 69,086 |
| G_aged_t96 | 67966 | 8.47 | 69,078 | 69,086 |
| G1a_fresh_t0 | 70510 | 8.32 | 69,077 | 69,086 |
| G1d_fresh_t60 | 70510 | 8.32 | 70,452 | 70,460 |

- `--membind=1` により全サイクルで Node 1 比率 >99.98%
- G1d で +1,374 MiB 増加（eval 12 回の KV キャッシュ成長）。**メモリ増加にもかかわらず速度は安定**
- G_aged_t96 は 69,086 MiB で G0 と同値。**メモリ使用量と劣化は非相関**

### GPU メモリ・温度（nvidia-smi、pre 時点）

| タグ | GPU 0 mem | GPU 1 mem | GPU 2 mem | GPU 3 mem | GPU 0 temp |
|------|----------:|----------:|----------:|----------:|-----------:|
| G0_aged_27m | 9,703 | 14,173 | 14,173 | 10,485 | 75°C |
| G_aged_t96 | 9,703 | 14,173 | 14,173 | 10,485 | 76°C |
| G1a_fresh_t0 | 9,703 | 14,173 | 14,173 | 10,485 | 75°C |
| G1d_fresh_t60 | 9,799 | 14,269 | 14,269 | 10,581 | 75°C |

- G1d で各 GPU +96 MiB 増加（eval 繰り返しによる GPU メモリ成長）
- GPU クロックは全サイクルで 1,189 MHz（GPU サーマルスロットリングなし）
- G_aged_t96 と他で GPU メモリ・温度に差異なし → **GPU は劣化原因ではない**

### システムメモリ状態（free -w、pre 時点、単位 KB）

| タグ | used | free | cache | available |
|------|-----:|-----:|------:|----------:|
| G0_aged_27m | 8,379,128 | 173,287,900 | 81,997,344 | 249,249,792 |
| G_aged_t96 | 8,392,600 | 172,860,656 | 82,409,512 | 249,230,740 |
| G1a_fresh_t0 | 8,390,448 | 172,862,772 | 82,409,204 | 249,233,040 |
| G1d_fresh_t60 | 9,775,536 | 170,071,720 | 83,884,440 | 247,797,408 |

- G1d で cache +1.5 GB, used +1.4 GB（eval 繰り返しの影響）
- G_aged_t96 と G1a はほぼ同値 → **システムメモリ状態は劣化原因ではない**

## ボトルネック・副次発見の分析

### 1. Fresh restart 後 60 分では劣化しない

G1a (t=0) = 14.867 → G1d (t=60) = 14.871 で、60 分間の時系列は完全にフラット。Phase E 主張の「1 時間後 −5.1%」は本 Phase G では **再現しなかった**。

Run 間のばらつきも極めて小さい: G1 全 4 サイクル × 3 run = 12 値の range は 14.863〜14.878 (0.015 t/s, 0.1%)。

### 2. G_aged_t96 (14.027) の劣化は観測されたが、原因は時間経過そのものではない

G_aged_t96 プロセス (PID 67966) は fresh restart 後 96 分間 **eval を受けずに idle 稼働**していた。一方、G1 プロセス (PID 70510) は 60 分間で 12 回の eval を受けながら稼働し、劣化しなかった。

| 比較 | G_aged_t96 (PID 67966) | G1d (PID 70510) |
|------|:----------------------:|:---------------:|
| 稼働時間 | 96 分 | 60 分 |
| eval 回数 | 0 回（idle） | 12 回（3 run × 4 サイクル） |
| eval 速度 | **14.027** (−5.6%) | **14.871** (±0.0%) |
| Node 1 mem | 69,078 MiB | 70,452 MiB |
| GPU mem | 同値 | +96 MiB/GPU |
| nr_migrations | 1 | 4 |

**仮説**: 劣化は「時間経過 + idle」の組み合わせか、G_aged_t96 プロセスの起動環境（Phase F 終了直後の環境、バックグラウンド Bash プロセスとの並行実行）に起因する可能性がある。

### 3. Phase E の C-E1 (14.27) との対応

Phase E の C-E1 は Phase D 計測後 1 時間の **idle 稼働後** に 14.27 を記録した。G_aged_t96 (96 分 idle 稼働) = 14.027 もほぼ同水準。**idle 稼働後の劣化**というパターンは 2 回観測されたことになる。

ただし、G1 プロセスでの 60 分間（eval あり）稼働で劣化しなかったため、**「時間劣化」ではなく「idle 劣化」の可能性が浮上**。

idle 劣化の仮説:
- llama.cpp の `--poll 0`（polling なし）設定により、idle 時にスレッドが sleep → 再開時のスレッド affinity 復帰に遅延が発生する可能性
- OS のページ管理: idle 中に THP (Transparent Huge Pages) の再編成やページマイグレーションが発生し、メモリアクセスパターンが崩れる可能性
- ただし numastat では Node 0 への漏出は 8.5 MiB で変化なし → NUMA レベルのメモリ移動は発生していない

### 4. G0 (aged 27m) = 14.908 は Fresh restart より高い

G0 (PID 65837, Phase F 由来) は 14.908 で、G1a (PID 70510, fresh restart) の 14.867 より +0.3% 高い。Phase F の F1b/c (14.80/14.81) よりも高い。

仮説: G0 プロセスは Phase F で 6 サイクル（計 18 回 eval）を実行した後の warm-up 効果が残存していた。

### 5. eval 速度と prompt 速度の挙動差

G_aged_t96 では eval が −5.6% 劣化した一方、prompt 速度は 32.62 で正常 (G1a の 32.85 と同水準)。**劣化は token generation (eval) のみに影響**している。

eval はスレッド数に依存する CPU 計算（FFN の expert 層）が支配的で、prompt 処理は GPU の行列積が支配的。これは劣化原因が **CPU 側のスレッド管理やメモリアクセスに局在**していることを示唆する。

## 採用判定

| 項目 | 結果 |
|------|------|
| C-D3 60 分間の安定性 | **安定** (14.867 → 14.871, ±0.0%) |
| Phase E 「1 時間後 −5.1%」の再現 | **再現せず** |
| aged プロセスの劣化 | **観測** (14.027, −5.6%、ただし idle 稼働の条件付き) |
| restart による回復 | **確認** (14.027 → 14.867, +6.0%) |

**C-D3 構成は 60 分間の連続稼働（eval ありの実用条件）で劣化しない**。定期再起動は現時点では不要。ただし idle 長時間稼働での劣化は観測されたため、idle 劣化の原因特定と、より長時間（2 時間超）の eval ありの稼働試験が未検証事項として残る。

## 未検証事項

### 既知項目（前身レポートから継続）

- [ ] **2 時間超の連続稼働試験（eval あり）**: 本 Phase G で 60 分までは安定を確認。Phase E 主張の −5.1% は再現しなかった。2 時間以上の eval あり稼働で劣化するかは未確認
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
- [ ] **`--threads 30` / `--threads 28` などの中間値**
- [ ] **`--numa numactl` モード**
- [ ] **OpenMP 環境変数の影響**
- [ ] **「初回サイクル効果」の原因特定**（Phase F 新規項目、本 Phase では該当せず）

### 新規項目（本レポートで判明・発生）

- [ ] **idle 長時間稼働での劣化メカニズム**: G_aged_t96 (idle 96m) で −5.6% 劣化が観測されたが、G1 (eval あり 60m) では劣化なし。idle と eval あり稼働の差異が劣化を引き起こす可能性。`--poll 0` 設定との関係、スレッド sleep/wake パターン、THP 再編成の影響を調査する必要がある
- [ ] **idle 劣化の再現性検証**: G_aged_t96 の劣化が idle そのものに起因するかを確認するため、fresh restart → idle 90 分 → eval 計測 → restart → eval あり 90 分 → eval 計測 の A/B テストが有効
- [ ] **`--poll 50` 等の poll 値による idle 劣化防止**: `--poll 0` (polling なし) が idle 中のスレッド挙動に影響している可能性。poll 値を変更して idle 劣化が防止できるか確認
- [ ] **eval あり 2 時間超の稼働試験**: 本 Phase で 60 分は安定確認済み。120 分/180 分でも安定か確認
- [ ] **Bash ツールの `start_phaseF.sh` バックグラウンド化対策**: `ssh -f` を含むスクリプトが Bash ツールで意図せずバックグラウンド化される問題。`</dev/null > /tmp/log 2>&1` リダイレクトで回避可能（本 Phase の 2 回目 restart で確認）

## 検証完了後に実施すべき TODO

### 既知項目（前身レポートから継続）

- [ ] **start.sh の拡張**: `LLAMA_NUMACTL_PREFIX` / `LLAMA_EXTRA_THREADS` 環境変数サポート追加
- [ ] **CUDA1 セーフティマージン OOM フォールバック実装**
- [ ] **flash-attn off ベンチマーク**
- [ ] **大コンテキスト実プロンプトでの eval 計測**（16k / 32k / 64k / 128k）
- [ ] **層→GPU アライメントのソースコード解析**
- [ ] **C-4 実験**（CPU 層削減 + GPU 層追加）
- [ ] **drop_caches 権限の確保**（sudoers 設定 or vmtouch 導入）
- [ ] **C-D3 での perf stat 計測**: node-load-miss が理論通り激減しているか確認
- [ ] **コールドスタート C-D6 計測**: Node 間対称性の証明
- [ ] **start.sh での NUMA プリセット整備**: `NUMA_MODE=pinned_node1_t40` 等
- [ ] **start.sh に `--threads` 設定追加**
- [ ] **PID 取得ロジックの統一**（`ps -eo pid,comm,args | awk '$2=="llama-server"'` 方式に）

### 新規項目（本レポートで発見）

- [ ] **idle 劣化対策の検討**: idle 劣化が確認された場合、定期的な keepalive eval（例: 10 分ごとに 1 token 生成）で劣化を防止できるか検証
- [ ] **`--poll` パラメータの調査**: llama.cpp の `--poll` がスレッド管理にどう影響するかをソースコードレベルで確認し、idle 劣化との関連を調査
- [ ] **計測プロトコルへの追加事項**: `start_phaseF.sh` を Bash ツールで実行する際は `</dev/null > /tmp/log 2>&1` で同期化する手順を標準化

## 補足

- 作業終了時点で **PID 70510 が C-D3 構成で稼働中**（起動 06:00 JST、etime ~65 分）
- GPU サーバロック（t120h-p100）は解放済み
- **Phase E 「C-D3 1 時間後 −5.1%」は再現しなかった**。60 分間の eval あり稼働で速度は完全に安定 (14.867 → 14.871)
- aged プロセス (96 分 idle 稼働) での −5.6% 劣化は観測されたが、eval あり稼働との差異から、**「時間劣化」ではなく「idle 劣化」の可能性**が浮上
- C-D3 実効値は **14.87 t/s**（Phase F の 14.80 から +0.5% 上方修正、fresh restart 直後の 12 run 中央値）
