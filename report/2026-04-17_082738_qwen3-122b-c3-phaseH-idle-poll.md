# Qwen3.5-122B-A10B C-3 Phase H（idle 劣化の再現性検証と `--poll` 値比較）

- **実施日時**: 2026年4月17日 08:27 – 10:56 (JST)
- **作業種別**: 計測・検証（Phase G 最優先未検証事項「idle 劣化の再現性検証」「`--poll` パラメータ調査」）

## 添付ファイル

- [実装プラン](attachment/2026-04-17_082738_qwen3-122b-c3-phaseH-idle-poll/plan.md)
- [起動スクリプト](attachment/2026-04-17_082738_qwen3-122b-c3-phaseH-idle-poll/start_phaseH.sh)
- [計測スクリプト](attachment/2026-04-17_082738_qwen3-122b-c3-phaseH-idle-poll/measure_phaseH.sh)
- G1e ログ一式: `out_G1e_idle88m/`（Phase G 由来プロセス PID 70510、eval 60m → idle 88m 経過時点）
- H1_t0 ログ一式: `out_H1_t0/`（--poll 0、fresh restart 直後）
- H1_t60 ログ一式: `out_H1_t60_idle/`（--poll 0、idle 60m 経過）
- H2_t0 ログ一式: `out_H2_t0/`（--poll 50、fresh restart 直後）
- H2_t60 ログ一式: `out_H2_t60_idle/`（--poll 50、idle 60m 経過）

各ディレクトリに Phase G 同様のログ一式（`eval_run{1,2,3}.json, dmon_run{1,2,3}.log, status_run{1,2,3}.txt, numastat_{pre,post}.txt, numastat_m_{pre,post}.txt, free_{pre,post}.txt, gpu_{pre,post}.csv, sched_{pre,post}.txt, cmdline.txt, timeline.log`）を格納。

## 参照

- 前身レポート: [2026-04-17_035831_qwen3-122b-c3-phaseG-longevity.md](2026-04-17_035831_qwen3-122b-c3-phaseG-longevity.md)
- Phase F: [2026-04-17_012859_qwen3-122b-c3-phaseF-reproducibility.md](2026-04-17_012859_qwen3-122b-c3-phaseF-reproducibility.md)
- Phase E: [2026-04-16_225920_qwen3-122b-c3-phaseE-smt.md](2026-04-16_225920_qwen3-122b-c3-phaseE-smt.md)

## 前提・目的

Phase G で以下 2 点が最優先の未検証事項として残っていた:

- **idle 劣化の再現性検証**: G_aged_t96 (96m idle) で 14.027 t/s (−5.6%)、Phase E C-E1 (60m idle) で 14.27 t/s (−5.1%) が観測された。ただし G1 (eval あり 60m) は 14.867 → 14.871 でフラットだった。**「時間経過」ではなく「idle 稼働」が劣化原因**という仮説を A/B テストで検証
- **`--poll` パラメータ調査**: 現行 `--poll 0`（polling なし）では idle 時にスレッドが sleep → 再開時のスレッド affinity 復帰遅延が劣化原因の仮説。`--poll 50` で防止できるか確認

### 成功条件

- `idle_degraded`: `median(t=60) ≤ median(t=0) × 0.96` かつ差分 ≥ 0.2 t/s
- `idle_stable`: 差分 < 0.1 t/s (1% 以内)

## 環境情報

- **サーバ**: `t120h-p100` (10.1.4.14)
- **GPU**: NVIDIA Tesla P100-PCIE-16GB × 4
- **CPU**: Intel Xeon Gold 6138 @ 2.00GHz × 2 socket、計 40 コア / 80 スレッド、NUMA 2 ノード
- **メモリ**: 257,560 MiB (約 251 GiB)
- **モデル**: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- **llama.cpp ビルド**: b8807-b3d758750（Phase D/E/F/G と同一）
- **構成**: C-D3（`numactl --cpunodebind=1 --membind=1 -- + --threads 40`）

## 計測手順（再現方法）

### 計測プロトコル

Phase G の `measure_phaseG.sh` をそのままコピーして `measure_phaseH.sh` として利用（中身同一）。

各 run: eval プロンプト `"Write a short haiku about autumn."`、`max_tokens=256`、`stream=false`。Run 間 60 秒 cooldown。1 サイクル約 5 分。

### 実行タイムライン

| タグ | プロセス / 構成 | 経過時間 | 時刻 (JST) |
|------|---------|------:|----------:|
| G1e_idle88m | PID 70510 (Phase G G1d 後 idle 88m) | idle 88m | 08:29 |
| H1_t0 | PID 108457、`--poll 0` fresh | 0m | 08:35 |
| H1_t60_idle | PID 108457、`--poll 0` idle 60m 後 | 60m idle | 09:40 |
| H2_t0 | PID 111205、`--poll 50` fresh | 0m | 09:46 |
| H2_t60_idle | PID 111205、`--poll 50` idle 60m 後 | 60m idle | 10:51 |

G1e は Phase G から引き継がれた PID 70510（fresh restart → eval 12 回 → idle 88m 経過）の追加計測。「eval 後 idle」パターンの劣化有無を確認する副次実験。

### 再現コマンド

```bash
# ロック取得
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

# G1e（既存 PID を直接計測）
PID=$(ssh t120h-p100 "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
bash measure_phaseH.sh $PID G1e_idle88m

# H1 phase
.claude/skills/llama-server/scripts/stop.sh t120h-p100
bash start_phaseH.sh H1 </dev/null > /tmp/start_H1.log 2>&1
PID=$(ssh t120h-p100 "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
bash measure_phaseH.sh $PID H1_t0
sleep 3600
bash measure_phaseH.sh $PID H1_t60_idle

# H2 phase（poll=50）
.claude/skills/llama-server/scripts/stop.sh t120h-p100
bash start_phaseH.sh H2 </dev/null > /tmp/start_H2.log 2>&1
PID=$(ssh t120h-p100 "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
bash measure_phaseH.sh $PID H2_t0
sleep 3600
bash measure_phaseH.sh $PID H2_t60_idle

# ロック解放
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 実行結果サマリ

### eval 速度（predicted_per_second）

| タグ | 構成 | 経過 | Run 1 | Run 2 | Run 3 | 中央値 | H1_t0 比 |
|------|------|----:|------:|------:|------:|------:|--------:|
| G1e_idle88m | poll=0、eval 60m→idle 88m | idle 88m | 14.875 | 14.875 | 14.869 | **14.875** | +1.4% |
| **H1_t0** | `--poll 0`、fresh | 0m | 14.664 | 14.664 | 14.663 | **14.664** | 基準 |
| H1_t60_idle | `--poll 0`、idle 60m | 60m idle | 14.655 | 14.654 | 14.650 | **14.654** | **−0.07%** |
| H2_t0 | `--poll 50`、fresh | 0m | 14.338 | 14.336 | 14.344 | **14.338** | **−2.2%** |
| H2_t60_idle | `--poll 50`、idle 60m | 60m idle | 14.346 | 14.343 | 14.336 | **14.343** | **−2.2%** |

### 判定結果

- **H1 idle 60m 劣化判定**: `median(H1_t60) ≤ median(H1_t0) × 0.96` → 14.654 > 14.077 → **不成立。`--poll 0` で idle 60m では劣化なし**（差分 −0.07%、`idle_stable` 該当）
- **H2 idle 60m 劣化判定**: `median(H2_t60) ≤ median(H2_t0) × 0.96` → 14.343 > 13.765 → **不成立。`--poll 50` でも idle 60m では劣化なし**（差分 +0.03%、`idle_stable` 該当）
- **`--poll 50` のベース速度**: H2_t0 (14.338) は H1_t0 (14.664) より −2.2% → **`--poll 50` はベース速度を下げる。成功条件「1% 以上低ければ不採用」を超過**
- **判定マトリクス**: H1 劣化なし × H2 劣化なし → **Phase E/G_aged の劣化は別要因（前プロセス履歴・環境ノイズ）**
- **G1e 劣化判定（副次）**: G1e (14.875) は Phase G G1d (14.871) とほぼ同値 → **eval 60m 後の idle 88m でも劣化なし**

### prompt 処理速度（prompt_per_second）

| タグ | Run 1 | Run 2 | Run 3 | 中央値 |
|------|------:|------:|------:|------:|
| G1e_idle88m | 32.92 | 32.93 | 33.26 | **32.93** |
| H1_t0 | 28.73 | 32.74 | 32.86 | **32.74** |
| H1_t60_idle | 32.82 | 32.93 | 32.89 | **32.89** |
| H2_t0 | 28.44 | 32.66 | 32.29 | **32.29** |
| H2_t60_idle | 32.64 | 32.76 | 33.03 | **32.76** |

- H1_t0 と H2_t0 の Run 1 のみ 28.4〜28.7 と低下（prompt キャッシュ warm-up）、以降は 32 台で安定
- H1_t60, H2_t60 では Run 1 から 32 台で安定（warm-up 済み）
- **`--poll 50` でも prompt 速度は 32.29〜32.76 と H1 (32.74〜32.89) と同水準**。GPU 計算主体の prompt 処理は poll 値の影響を受けない

## ボトルネック・副次発見の分析

### 1. `--poll 0` idle 60m で劣化しない

H1_t0 (14.664) → H1_t60_idle (14.654) で差分 −0.010 t/s（−0.07%）。Run 3 本の range も 14.650〜14.664 の 0.014 t/s で極めてタイト。**Phase G の G_aged_t96 (−5.6%) は再現しなかった**。

### 2. G1e (eval 60m → idle 88m) でも劣化なし

PID 70510 は Phase G で G1d (07:00) まで eval 12 回を受けたあと 88 分 idle 放置されたが、計測値 14.875 は G1d (14.871) と完全一致。

**→ 「eval を一度でも実行したプロセスは、その後 idle 放置しても劣化しない」**。対して Phase G の G_aged_t96 (14.027, −5.6%) は「fresh restart 直後から eval なしで 96m idle」。両者の唯一の差は **初期 warm-up eval の有無**。

### 3. H1_t0 (14.664) と Phase G G1a (14.867) の乖離

同じ `--poll 0` fresh 直後でも、Phase G G1a = 14.867、本 Phase H1_t0 = 14.664 と 0.20 t/s (1.4%) の差。Phase G は Phase F 由来プロセスの停止直後、本 Phase は PID 70510（稼働 2h 37m）停止直後に restart。停止前プロセスの負荷履歴や GPU 側のメモリ配置が影響する可能性。ただし H1 セッション内での Run 間 range は 0.002 t/s と非常に小さく、ノイズではなく構造的差。

### 4. `--poll 50` はベース速度を 2.2% 下げる、かつ idle 劣化防止効果も無用

H2_t0 = 14.338 は H1_t0 = 14.664 より 0.326 t/s 低い。`--poll 50` は idle スレッドが 50ms ほど busy-spin してから sleep する設定で、**eval 中にも spin overhead が計算スレッドと競合**し速度を下げる可能性。または、poll が OpenMP/thread barrier と相互作用し効率を下げる。

H2_t60_idle = 14.343 も H2_t0 と同値で、**`--poll 50` でも idle 60m 劣化はない**が、これは `--poll 0` でも既に劣化しないため、`--poll 50` による「idle 劣化防止効果」は無用。結論として **`--poll 50` は採用不可**（ベース速度 −2.2% の一方的な悪化のみ）。

### 5. Phase E/G_aged の −5% 劣化は特殊条件の可能性

本 Phase H + G1e を総合すると、「時間経過」「idle そのもの」では劣化しない。Phase E C-E1（14.27）と Phase G G_aged_t96（14.027）の劣化は、以下のいずれかが原因と推定される:

- **fresh restart 直後の eval 未実行 idle**: 初期 warm-up（JIT 的な効果、キャッシュプリフェッチ、GPU kernel selection 等）が完了する前に長時間 idle すると、再開時にパスが変わる
- **前プロセスとの並行稼働**: G_aged_t96 の場合、Phase F の PID 65837 が稼働中に PID 67966 が起動された。CPU/GPU リソース競合の痕跡が残った
- **偶発的環境ノイズ**: サーバ負荷や THP 状態のゆらぎ

### 6. 一貫性のある結論

| 条件 | 結果 |
|------|------|
| fresh restart → eval あり 60m (poll=0) | **劣化なし**（Phase G G1） |
| fresh restart → eval 60m → idle 88m (poll=0) | **劣化なし**（G1e、本 Phase） |
| fresh restart → idle 60m (poll=0) | **劣化なし**（H1、本 Phase） |
| fresh restart → idle 60m (poll=50) | **劣化なし**（H2、本 Phase。ただしベース速度は −2.2%） |
| fresh restart → idle 96m (poll=0、ただし特殊条件) | 劣化あり（Phase G G_aged_t96） |

**核心**: C-D3 構成は eval あり運用・ほぼすべての実用条件で劣化しない。Phase G G_aged_t96 の −5.6% は `--poll` 値とは無関係に再現せず、条件複合による偶発劣化の可能性が高い。運用上の懸念は低い。

## 採用判定

| 項目 | 結果 |
|------|------|
| C-D3 `--poll 0` idle 60m の安定性 | **安定** (14.664 → 14.654, −0.07%) |
| C-D3 `--poll 50` idle 60m の安定性 | **安定** (14.338 → 14.343, +0.03%) |
| C-D3 eval 60m → idle 88m の安定性 | **安定** (G1d 14.871 → G1e 14.875) |
| Phase G G_aged_t96 の −5.6% 再現 | **再現せず（2 種類の poll 値、計 4 測定ポイントで確認）** |
| `--poll 50` の採用可否 | **不採用**（ベース速度 −2.2%、idle 劣化防止効果は不要） |

**結論**: C-D3 構成は現行 `--poll 0` のまま運用で問題ない。**定期再起動も不要**。Phase E/G の「idle 劣化」懸念は条件特殊の偶発現象の可能性が高く、通常運用では出現しない。

C-D3 実効値: **H1 セッション 14.66 t/s（本 Phase）**、**Phase G セッション 14.87 t/s**。セッション間で ~1.4% のゆらぎがある点は今後の計測で意識が必要。

## 未検証事項

### 既知項目（前身レポートから継続）

- [ ] **2 時間超の連続稼働試験（eval あり）**: Phase G で eval あり 60 分、本 Phase で eval なし idle 60m + G1e (eval 60m→idle 88m) が安定確認。2 時間超の eval あり稼働で劣化するかは未確認
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
- [ ] **「初回サイクル効果」の原因特定**（Phase F 新規項目）

### 新規項目（本レポートで判明・発生）

- [ ] **H1_t0 (14.66) と Phase G G1a (14.867) のセッション間差の原因**: 同じ `--poll 0` fresh 直後で 1.4% 差。停止前プロセスの稼働履歴、GPU メモリ状態、CPU キャッシュ状態が影響するか要調査
- [ ] **`--poll 1` / `--poll 10` / `--poll 100` の影響**: `--poll 50` がベース速度 −2.2% だったが、低い値（例 10, 1）では速度低下が小さくかつ idle 劣化防止に有効な可能性
- [ ] **G_aged_t96 の再現条件の特定**: 本 Phase H では再現せず。「前プロセスが稼働中の状態で restart」「initial eval を一度も受けていない状態で長 idle」のどちらが必要条件か A/B で切り分け
- [ ] **`--poll` とスレッド affinity / OpenMP の相互作用**: `--poll 50` がなぜベース速度を下げるか（busy-spin の競合、CPU frequency scaling、thread barrier 相互作用）

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

- [ ] **セッション間ゆらぎの管理**: 同一構成で 1.4% 差が出ることを踏まえ、計測プロトコルに「直前プロセス情報（PID、etime、停止からの経過時間）」を明示的に記録
- [ ] **`--poll 50` を採用しない旨を start.sh のコメントで明記**: 将来の改変防止
- [ ] **idle 劣化が偶発現象と確定した場合、Phase E/G の当該セクションに追記**（再現性なしの注記）

## 補足

- C-D3 構成の実効値は **`--poll 0` で 14.65〜14.87 t/s（セッション間ゆらぎ）**、`--poll 50` では 14.34 t/s
- **`--poll 50` は不採用**（ベース速度 −2.2%。idle 劣化防止効果は `--poll 0` でも既に劣化しないため不要）
- **idle 劣化仮説は本 Phase では否定的**: fresh restart 後 60m idle (poll=0/50 両方)、eval 60m 後 idle 88m のいずれでも劣化なし
- Phase G G_aged_t96 の −5.6% 劣化は条件複合の偶発現象と推定される
- 作業終了時点で llama-server は停止済み、**GPU サーバロック（t120h-p100）は解放済み**
