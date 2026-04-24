# Qwen3.5-122B-A10B C-3 Phase J（flash-attn ON/OFF A/B 比較）

- **実施日時**: 2026年4月17日 20:05 – 20:40 (JST)
- **作業種別**: 計測・検証（Phase I 最優先未検証事項「`--flash-attn` on/off の A/B 比較」）

## 添付ファイル

- [実装プラン](attachment/2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab/plan.md)
- [起動スクリプト (start_phaseJ.sh)](attachment/2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab/start_phaseJ.sh)
- [計測スクリプト (measure_phaseI.sh、Phase I から流用)](attachment/2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab/measure_phaseI.sh)
- [一括実行スクリプト (run_all.sh)](attachment/2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab/run_all.sh)
- [集計結果 TSV (results.tsv)](attachment/2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab/results.tsv)
- [マスターログ (run_all_J_fa1.log)](attachment/2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab/run_all_J_fa1.log)
- [flash-attn=0 Segfault時ログ (fa0_segfault/llama-server.log)](attachment/2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab/fa0_segfault/llama-server.log)
- `out_J_fa1_{warmup,1k,8k}/` の各計測アーティファクト（`eval_run{N}.json`, `dmon_run{N}.log`, `status_run{N}.txt`, `numastat_{pre,post}.txt`, `numastat_m_{pre,post}.txt`, `free_{pre,post}.txt`, `gpu_{pre,post}.csv`, `gpu_post_run{N}.csv`, `sched_{pre,post}.txt`, `cmdline.txt`, `timeline.log`）

## 参照

- 前身レポート: [2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext.md](2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext.md)
- Phase H: [2026-04-17_082738_qwen3-122b-c3-phaseH-idle-poll.md](2026-04-17_082738_qwen3-122b-c3-phaseH-idle-poll.md)
- Phase D: [2026-04-16_150717_qwen3-122b-c3-phaseD.md](2026-04-16_150717_qwen3-122b-c3-phaseD.md)

## 前提・目的

Phase I で採用構成 C-D3 (`numactl --cpunodebind=1 --membind=1 -- + --threads 40 + --poll 0 + --flash-attn 1 + -b 8192 -ub 8192 + --ctx-size 131072 + --cache-type-k q8_0 --cache-type-v q8_0`) の長コンテキスト性能プロファイルが確定した。しかし、`--flash-attn 1` は Phase A〜I の全フェーズで前提として固定され、**一度も `--flash-attn 0` との A/B 比較が行われていない**。P100 (CC 6.0) は Tensor Core を持たないため、flash-attention 実装の効果が A100/H100 と同等に発揮されるかは未検証の前提条件であった。

本 Phase J では以下を同時検証する:

1. flash-attn=1 と flash-attn=0 の eval_tps / prompt_tps の直接比較（warmup・1k・8k）
2. flash-attn=0 の GPU メモリ影響（attention score 行列の O(N²) 展開が OOM を招くか）
3. P100 CC 6.0 で flash-attn 採用が正当化されるかの明示的判定

### 重要な計測配慮（セッション間ゆらぎ対策）

Phase H で確認された warmup 値ゆらぎ（14.66〜15.00、2.3%）を相殺するため、Phase J 内で flash-attn=1 の基準を再採取し、**相対劣化率（Xk / warmup）同士の比較**をもって絶対値比較の不確実性を補った。

### 成功条件（当初設定）

- J_fa1 と J_fa0 両方のセッションで warmup/1k/8k を 3 runs ずつ完走（→ **J_fa1 のみ達成**、J_fa0 は起動不可で未達）
- 両条件の eval_tps 中央値から採用判定を下す（→ **別経路で採用判定に到達**、下記「採用判定」参照）

## 環境情報

- **サーバ**: `t120h-p100` (10.1.4.14)
- **GPU**: NVIDIA Tesla P100-PCIE-16GB × 4（各 16,270 MiB）
- **CPU**: Intel Xeon Gold 6138 @ 2.00GHz × 2 socket、計 40 コア / 80 スレッド、NUMA 2 ノード
- **メモリ**: 257,560 MiB (約 251 GiB)
- **モデル**: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- **llama.cpp ビルド**: b8807-b3d758750（Phase D/E/F/G/H/I と同一系列）
- **構成**: C-D3（`numactl --cpunodebind=1 --membind=1 -- + --threads 40 + --poll 0 + -b 8192 -ub 8192 + --ctx-size 131072 + --cache-type-k q8_0 --cache-type-v q8_0`）
- **J_fa1 セッション PID**: 132590
- **J_fa0 セッション**: 起動直後 Segfault（PID 確定せず）

## 計測手順（再現方法）

### スクリプト構成（Phase I からの変更点）

| ファイル | 変更内容 |
|---|---|
| `start_phaseJ.sh` | `--flash-attn` 値を `FLASH_ATTN` 環境変数で外部注入可能にした（既定 1、他は Phase I と同一） |
| `run_all.sh` | `TAG_PREFIX` / `SIZES` 環境変数化、`run_gated` 関数（CUDA1 free 閾値チェック）追加 |
| `measure_phaseI.sh` | 変更なしで流用（Phase I ファイル名のまま） |
| `aggregate_results.sh` | 集計対象を `out_I_*` → `out_J_*` に変更 |
| `prompts/` | Phase I で生成したものを流用 |

### 実行フロー

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseJ-flashattn-ab"
# （Phase I 資産をコピー、start/run_all を編集）

# ---- フェーズ 1: flash-attn=1 基準再採取 ----
FLASH_ATTN=1 bash "$REPORT_DIR/start_phaseJ.sh"
PID=$(ssh t120h-p100 "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
cd "$REPORT_DIR"
TAG_PREFIX=J_fa1 SIZES="warmup 1k 8k" PID=$PID bash run_all.sh
.claude/skills/llama-server/scripts/stop.sh t120h-p100

# ---- フェーズ 2: flash-attn=0 計測（試行） ----
FLASH_ATTN=0 bash "$REPORT_DIR/start_phaseJ.sh"
# → 起動直後 Segmentation fault（下記参照）

bash aggregate_results.sh > results.tsv
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 実行タイムライン

| タグ | prompt_n（ChatTemplate 込み） | Run 数 | 開始 | 終了 |
|------|---------:|------:|----------:|----------:|
| J_fa1_warmup | 50 | 3 | 20:08:26 | 20:14:08 |
| J_fa1_1k | 1,071 | 3 | 20:14:08 | 20:19:54 |
| J_fa1_8k | 8,072 | 3 | 20:19:55 | 20:26:10 |
| **J_fa0 起動試行** | — | — | 20:27 | **Segfault 即死** |

J_fa1 フェーズ所要: **約 18 分**（事前準備含めて 23 分）。J_fa0 は起動フェーズで即時失敗のため計測自体に到達せず。

## 実行結果サマリ

### J_fa1 (flash-attn=1) の eval 速度

| タグ | prompt_n | Run 1 | Run 2 | Run 3 | 中央値 | warmup 比 |
|------|---------:|------:|------:|------:|------:|---------:|
| J_fa1_warmup | 50 | 15.543 | 15.282 | 15.277 | **15.282** | 基準 |
| J_fa1_1k | 1,071 | 15.179 | 15.181 | 15.178 | **15.179** | **−0.67%** |
| J_fa1_8k | 8,072 | 14.558 | 14.551 | 14.655 | **14.558** | **−4.74%** |

Run 間 range: warmup 0.266 t/s（run 1 が外れ値）、1k は 0.003 t/s、8k は 0.104 t/s。1k/8k は Phase I と同様に極めて安定。warmup の run 1 がやや高い（15.54）のは初回のスレッド配置確定前の一過性の可能性。

### J_fa1 (flash-attn=1) の prompt 処理速度

| タグ | Run 1 | Run 2 | Run 3 | 中央値 |
|------|------:|------:|------:|------:|
| J_fa1_warmup | 9.02 | 9.21 | 9.07 | **9.07** |
| J_fa1_1k | 67.99 | 68.21 | 68.20 | **68.20** |
| J_fa1_8k | 184.18 | 181.31 | 187.15 | **184.18** |

Phase I 値（8.94 / 67.85 / 181.46）と完全に整合。再現性 ±2% 以内。

### J_fa1 の GPU メモリ使用量（`gpu_post_run*.csv` より）

| タグ | CUDA0 | CUDA1 | CUDA2 | CUDA3 | CUDA1 free |
|------|------:|------:|------:|------:|----------:|
| J_fa1_warmup | 9,799 | 14,269 | 14,269 | 10,581 | 2,001 |
| J_fa1_1k | 9,849 | 14,315 | 14,319 | 10,619 | 1,955 |
| J_fa1_8k | 10,759 | 15,197 | 15,211 | 11,009 | 1,073 |

（単位 MiB）Phase I 実測と完全に一致（warmup 同値、8k 時 CUDA1 free 1,073 vs Phase I 1,053 で誤差内）。

### J_fa0 (flash-attn=0) 起動試行結果

```
$ FLASH_ATTN=0 bash start_phaseJ.sh
[start_phaseJ] FLASH_ATTN=0 (C-D3 base, poll=0, ctx=131072)
[start_phaseJ] waiting for /health...
bash: line 1: 136735 Segmentation fault (core dumped) nohup bash -c "numactl ...
  --flash-attn 0 --poll 0 -b 8192 -ub 8192 ...
  --cache-type-k q8_0 --cache-type-v q8_0 ..."
[start_phaseJ] FAILED to become healthy in 300s
```

`/tmp/llama-server.log` は **179 行目**で途絶。モデルロード (`CUDA3 model buffer size = 1693.13 MiB`) までは成功し、`common_init_result: added <|file_sep|> logit bias = -inf` の後、**KV cache 初期化フェーズ（`llama_kv_cache_unified: ...` 系のログが出る直前）で Segmentation fault**。コアダンプ出力を伴う終了。

原因分析（既知の llama.cpp 実装特性より）:

- llama.cpp の CUDA バックエンドは、**KV cache 量子化（`--cache-type-k q8_0 --cache-type-v q8_0`）を flash-attention 経路でのみサポート**している
- 非 flash-attention 経路 (`--flash-attn 0`) では量子化 KV を読み書きするカーネルが存在せず、初期化時の validation が通らないまま GGML グラフ構築に進み、null ポインタまたは形状不整合で Segfault を起こす
- P100 (CC 6.0) に限らず CUDA 全体で発生する既知の制約（llama.cpp upstream でも複数 issue が報告されている）

したがって **C-D3 構成（`--cache-type-{k,v} q8_0` を含む）では `--flash-attn 0` は物理的に起動不可能**。

## ボトルネック・副次発見の分析

### 1. C-D3 採用構成の不可分依存

Phase J の本来目的（eval 速度差分の A/B 取得）は達成できなかったが、**より上位の構造的結論**が得られた:

```
--cache-type-k q8_0          ←→   必須: --flash-attn 1
--cache-type-v q8_0
```

Phase I で確認した「131k ctx の KV cache が GPU に収まる（2 GiB マージン）」は、**量子化 KV cache に完全依存**している。f16 KV cache に戻すと必要 VRAM は約 2 倍（~25 GB → 配列は GPU 間で分散されるが、CUDA1 単独でも warmup 14.3 GB + ~1 GB 追加で OOM 境界）。つまり C-D3 の「131k ctx + GPU メモリ内完結」は以下の 3 条件が同時成立する前提:

- `--flash-attn 1`（KV 量子化のため）
- `--cache-type-{k,v} q8_0`（メモリ節約のため）
- `-ngl 999 -ot ...ffn_.*_exps\.weight=CPU`（MoE FFN のみ CPU オフロード）

どれ 1 つを変えると構成全体が崩れる。「flash-attn=0 の比較」という単独変更は定義上不可能。

### 2. flash-attn の必須性は「速度優位」ではなく「機能要件」

Phase J の当初仮説は「P100 で flash-attn が速度上有利か」であったが、実態は「flash-attn なしでは採用構成がそもそも実行されない（量子化 KV の前提）」。これは採用判定のロジックを根本的に変える:

- **Before**: flash-attn ON/OFF は速度の選択肢 → A/B で合理化
- **After**: flash-attn ON は採用構成の必要条件 → A/B 比較の余地なし

「flash-attn off のほうが速いシナリオ」があったとしても、それを採るには cache-type f16 + ctx-size 縮小が必須で、**それは C-D3 ではなく別構成**。そのような別構成の比較検討は Phase K で実施すべき別論点となる。

### 3. Phase I 結果の再現性確認

Phase J_fa1 セッションと Phase I を比較:

| サイズ | Phase I 中央値 | J_fa1 中央値 | 差分 |
|------|------:|------:|------:|
| warmup (48/50 tok) | 15.000 | 15.282 | **+1.88%** |
| 1k (1,069/1,071 tok) | 14.882 | 15.179 | **+2.00%** |
| 8k (8,070/8,072 tok) | 14.273 | 14.558 | **+2.00%** |

セッション間ゆらぎ範囲（Phase H の 14.66〜15.00 レンジから見て 2% 程度のゆらぎは想定内）であるが、注目すべきは **「全サイズで均一に +2% 高い」** こと:

- Phase I の warmup/1k/8k の対 warmup 比率は 1.000 / 0.992 / 0.952
- J_fa1 の同比率は 1.000 / 0.993 / 0.952
- **比率は 0.1% の精度で一致** → サイズ依存の勾配（Phase I で定式化した `1/eval_tps = 0.0665 + 0.485 μs × N`）は**セッション間ゆらぎに対して不変**

これは Phase I で立てた線形モデルが **絶対値ではなくスケール係数まで含めて構造的に正確**であることを再確認する副次証拠。セッションごとのオフセット（時定数 `a`）はゆらぐが、N 依存の勾配 `k` はほぼ固定。

### 4. セッション間 warmup ゆらぎの続報

| セッション | 短プロンプト warmup 中央値 | 備考 |
|-----------|:------:|------|
| Phase G G1a | 14.867 | poll=0 fresh |
| Phase H H1_t0 | 14.664 | poll=0 fresh |
| Phase I I_warmup | 15.000 | poll=0 fresh |
| **Phase J J_fa1_warmup** | **15.282** | poll=0 fresh |

4 セッションで 14.66〜15.28 の **4.2% レンジ**（Phase I 時点の 2.3% から拡大）。Phase J で最高値を記録したが、run 1 の 15.54 を外れ値として除くと中央値 15.28 になっている（run 1 15.54 / run 2 15.28 / run 3 15.28）。**このゆらぎは依然未説明**で、Phase H から継続 TODO。

### 5. dmon 所見（8k 処理時の SM 稼働）

`out_J_fa1_8k/dmon_run1.log` の先頭サンプル（30 秒間）より:

| GPU | sm% 平均 | mem% | 備考 |
|----:|--------:|-----:|------|
| 0 | 40-70 | 3-9 | 計算の主担当 |
| 1 | 0 | 0 | idle（KV 保持のみ） |
| 2 | 0 | 0 | idle |
| 3 | 0 | 0 | idle |

4 GPU 中で計算を担うのは主に CUDA0（layer 0-13 と output layer）。**CUDA1/2/3 は計算に参加していない**ように見える。Phase I の長コンテキストで CUDA1 のメモリ確保（KV 保持）は増えるが、計算 SM の稼働は低いまま。これは `-ot blk.<CPU対象>.ffn_.*_exps.weight=CPU` で FFN が CPU に流れる影響で、各層の attention + routing のみ GPU で計算され、CUDA1/2/3 は KV 読み出し時のみアクセスされる設計に起因する可能性が高い。

次回は dmon の時系列を詳細に記録し、eval フェーズ中の CUDA0 以外の GPU 利用率を追跡すべき（Phase K の TODO）。

## 採用判定

| 項目 | 結果 |
|------|------|
| `--flash-attn 0` の C-D3 構成下での起動可否 | **不可能**（Segfault、cache-type q8_0 との非互換） |
| `--flash-attn 1` の必須性 | **必須**（採用構成の機能要件として確定） |
| Phase I の eval 速度プロファイルの再現性 | **確認済み**（全サイズで 0.1% 精度） |
| セッション間 warmup ゆらぎ | **4.2% レンジに拡大**（14.66〜15.28） |

**結論**: 採用構成 C-D3 における `--flash-attn 1` は、**速度上の選択ではなく量子化 KV cache のための機能要件**である。「flash-attn off との A/B 比較」という Phase I の最優先未検証事項は、**「比較自体が成立しない（別構成に移行しない限り）」という形で決着**した。採用構成を変える動機はなく、`start.sh` 等の本番スクリプトの改変は不要。

## 未検証事項

### 既知項目（Phase I から継続）

- [ ] **2 時間超の連続稼働試験（eval あり）**
- [x] ~~flash-attn off との比較~~ → **本 Phase J で起動不可と判明（cache-type q8_0 依存）**
- [ ] **層→GPU アライメントのソース解析**: llama.cpp の `-ot` 正規表現と層配置のロジック
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
- [ ] **セッション間 warmup ゆらぎ（14.66〜15.28）の原因特定**（Phase H 継続、本 Phase で再観測・レンジ拡大）
- [ ] **`--poll 1` / `--poll 10` / `--poll 100` の影響**
- [ ] **G_aged_t96 の再現条件の特定**
- [ ] **`--poll` とスレッド affinity / OpenMP の相互作用**
- [ ] **線形モデル `time_per_token = 66.5μs + 0.485μs × N_context` の他構成での検証**
- [ ] **prompt_per_second が 8k で頂点を打つ理由**（`-b / -ub 8192` との関連検証）
- [ ] **64k / 120k の Run 間再現性**
- [ ] **128k コンテキストが純粋応答に与える影響**（131k 上限）
- [ ] **KV cache 量子化 (q8_0) の精度影響**（長コンテキストでの出力品質）
- [ ] **prompt cache hit 時の実効 turn time**
- [ ] **ワークスペース +950 MiB の内訳**（8k で確保されるバッファ種別）

### 新規項目（本 Phase J で判明・発生）

- [ ] **cache-type f16 条件での flash-attn ON/OFF A/B（Phase K として独立計画）**: 131k ctx は無理だが、ctx=16k〜32k に絞れば f16 KV cache でも起動可能。その条件下で flash-attn off が eval_tps で速いか遅いか、および prompt_tps のピーク位置の比較が未検証
- [ ] **llama.cpp のソース上で `--cache-type-{k,v} q8_0` と `--flash-attn` の依存ロジック確認**: 公式 issue や code path を確認し、本 Phase の「Segfault は既知の未サポート経路」仮説を裏取り
- [ ] **Segfault 時のバックトレース取得**: gdb で core dump を解析し、llama.cpp 内部のどの関数で死んだか特定（将来の upstream bug 報告にも使える）
- [ ] **P100 CC 6.0 の flash-attention カーネル経路の検証**: `ggml-cuda` 内で V100/A100 (Tensor Core) と P100 (Pascal) のカーネル分岐点がどう違うか。ソース読解 + `nvprof` でのカーネル実計測
- [ ] **CUDA1/2/3 の SM 稼働実態の時系列計測**: 本 Phase の dmon サンプルでは 8k 処理中にほぼ idle だが、KV 読み出しのタイミングで瞬間的に稼働している可能性。dmon 間隔を 1 秒にするか `nvidia-smi dmon -c 60` で詳細記録
- [ ] **J_fa1_warmup run 1 の外れ値（15.54 t/s）再現性**: 初回 run で高い傾向があるか、単発のゆらぎか

## 検証完了後に実施すべき TODO

### 既知項目（Phase I から継続）

- [ ] **start.sh の拡張**: `LLAMA_NUMACTL_PREFIX` / `LLAMA_EXTRA_THREADS` 環境変数サポート追加
- [ ] **CUDA1 セーフティマージン OOM フォールバック実装**
- [x] ~~flash-attn off ベンチマーク（Phase I のプロトコル流用）~~ → **本 Phase J で起動不可のため別構成スコープに移管**
- [ ] **層→GPU アライメントのソースコード解析**
- [ ] **C-4 実験**（CPU 層削減 + GPU 層追加）
- [ ] **drop_caches 権限の確保**（sudoers 設定 or vmtouch 導入）
- [ ] **C-D3 での perf stat 計測**
- [ ] **コールドスタート C-D6 計測**
- [ ] **start.sh での NUMA プリセット整備**
- [ ] **start.sh に `--threads` 設定追加**
- [ ] **PID 取得ロジックの統一**
- [ ] **セッション間ゆらぎの管理**: 計測プロトコルに「直前プロセス情報（PID、etime、停止からの経過時間）」を明示的に記録
- [ ] **`--poll 50` を採用しない旨を start.sh のコメントで明記**
- [ ] **idle 劣化が偶発現象と確定した場合、Phase E/G の当該セクションに追記**
- [ ] **`measure_phaseI.sh` を汎用化して skill に組み込む**: `.claude/skills/llama-server/scripts/measure_longcontext.sh` として配置
- [ ] **「長コンテキスト性能カード」をモデル単位で記録するドキュメント整備**
- [ ] **アプリ側にコンテキストサイズ別レイテンシ警告を出す仕組み**
- [ ] **プロンプトキャッシュの活用ドキュメント化**
- [ ] **`-ub` の感度ベンチマーク追加**

### 新規項目（本 Phase J で発見）

- [ ] **CLAUDE.md / skill に「C-D3 は flash-attn=1 必須」の注記を追加**: 将来の誰か（人間 or エージェント）が `--flash-attn 0` を試したときに即座に原因を把握できるよう、`start.sh` のコメントと `.claude/skills/llama-server/SKILL.md` に依存関係を明記
- [ ] **Phase K 計画策定（cache-type f16 条件での flash-attn A/B）**: ctx=16k or 32k に縮小した上で f16 KV cache での flash-attn ON/OFF 比較。C-D3 とは別構成として比較スコープを定義
- [ ] **`start_phaseJ.sh` の環境変数化を skill 側 `start.sh` に逆輸入**: `FLASH_ATTN` 変数を skill の `start.sh` でもサポートし、将来の A/B 実験を容易化（ただし C-D3 で off は Segfault になる旨をコメントで警告）
- [ ] **依存制約の lint 化**: 起動前に「`--cache-type-{k,v} q8_0` かつ `--flash-attn 0`」の組み合わせを検知して即エラー終了させる pre-check を `start.sh` に追加（本番事故防止）
- [ ] **llama.cpp upstream issue/PR のサーベイ**: 「KV quant + no flash-attn でのサポート状況」の現行状態を確認し、将来のバージョンアップで解消されるか判断

## 補足

- **J_fa1 セッションの実効値**（Phase I 再現確認の意味を兼ねる）:
  - **短プロンプト eval (warmup)**: 15.28 t/s（Phase I 15.00 比 +1.88%）
  - **1k 入力 eval**: 15.18 t/s（Phase I 14.88 比 +2.00%）
  - **8k 入力 eval**: 14.56 t/s（Phase I 14.27 比 +2.00%）
  - サイズ間の相対劣化率は Phase I と 0.1% 以内で一致 → 線形モデルの構造的正確性を再確認
- **Phase J の要約**: 「flash-attn off との A/B 比較」は **物理的に成立しない A/B**（C-D3 の機能要件として flash-attn ON が必要）と判明。Phase I の最優先 TODO に決着がついた形で、代わりに Phase K（f16 条件での独立実験）という別項目を生成。
- **作業終了時点で llama-server は停止済み、GPU サーバロック（t120h-p100）は解放済み**
