# 過去3ヶ月の llama.cpp 主要変更(P100 / MI25+Vulkan 関連)

- **作成日時**: 2026年06月18日 05:17 (JST)

## 添付ファイル

- [調査プラン](attachment/2026-06-18_051739_llamacpp_3mo_changes_p100_mi25vulkan/plan.md)

## 前提・目的

- **背景**: 当プロジェクトは t120h-p100(CUDA)と mi25(Vulkan/RADV)で llama-server を運用している。upstream llama.cpp の変更が、ビルド可否・性能・安定性にどう波及するかを定期的に棚卸しする必要がある(master 追従/pin 判断、性能チューニングの材料)。
- **目的**: 過去3ヶ月(2026-03-18 以降)の llama.cpp の主要変更のうち、**P100(CUDA/Pascal/cc6.0)** と **MI25+Vulkan(RADV/gfx900)** に関係するものだけを抽出・整理する。
- **対象スコープ**: 上記2ハードウェアに限定。MI25 ROCm 側は対比に必要な範囲のみ言及する。
- **一次情報源**: `src/llama.cpp/`(完全な git 履歴あり、HEAD=`0843245cb` 2026-06-17)。3ヶ月窓のコミット総数は約1292件、うち Vulkan バックエンド 65件・CUDA バックエンド 84件。
- **注意書き**: 性能(prompt/eval)への効果は本レポートでは実機ベンチを取得していない。コード変更の内容から「効きうる/可能性」として記述し、断定はしない。実測は別途ベンチで行う。

## 環境情報

| 項目 | P100 | MI25 + Vulkan |
|------|------|---------------|
| サーバ | t120h-p100 (10.1.4.14) | mi25 (10.1.4.13) |
| GPU | Tesla P100 16GB ×N | Radeon Instinct MI25 (Vega10/gfx900) ×3(実効) |
| バックエンド | CUDA (CUDA 12.9) | Vulkan (Mesa RADV) |
| llama.cpp 追従 | **master 追従(pin 不要)** | **master 追従(pin 不要)** |
| ビルド arch 指定 | `-DCMAKE_CUDA_ARCHITECTURES="60"` 明示 | `-DGGML_VULKAN=ON`(build-vulkan/) |
| 確定構成(参考) | `--flash-attn 1 -ub 4096 --cache-type-k/v q8_0` | `--flash-attn 1 -ub 2048 --cache-type-k/v q8_0` |

**モデルアーキの訂正(重要)**: 運用モデル `unsloth/Qwen3.6-35B-A3B-GGUF` の `general.architecture` は **`qwen35moe`**(実機 GGUF metadata で確認、t120h-p100)。これは llama.cpp の `llm_arch_is_hybrid`(`llama-arch.cpp:878`)で **hybrid と判定される**アーキ(attention + linear/recurrent 層の混在、interleaved SWA(iswa)、MTP 層を内蔵)。**標準的な `qwen3moe`(非 hybrid)ではない**。このため後述の汎用改善のうち **hybrid memory / SWA(iswa)/ recurrent / MTP 関連の変更が当環境に該当する**(両サーバ共通)。

参考: MI25 の **ROCm/HIP** バックエンドのみコミット `0fac87b15`(version 8533)に pin している。理由は後述の `112c78159`(NVFP4)で導入された fp8 e4m3 型を gfx900 が device compile できないため。Vulkan バックエンドは HIP を device compile しないためこの影響を受けず、pin 不要が継続的に妥当である。

## 再現方法(調査手順)

```bash
cd src/llama.cpp
# 対象窓のバックエンド別コミット一覧
git log --since='2026-03-18' --oneline -- ggml/src/ggml-vulkan   # 65件
git log --since='2026-03-18' --oneline -- ggml/src/ggml-cuda     # 84件
# 個別コミットの内容確認
git show -s --format="%h | %ci | %s" <hash>
git show --stat <hash>
git show <hash>

# 「ハードウェア非依存の汎用改善」セクションの調査領域(両バックエンド共通)
git log --since='2026-03-18' --oneline -- tools/server   # 211件
git log --since='2026-03-18' --oneline -- src            # 150件(llama 本体)
git log --since='2026-03-18' --oneline -- common         # 188件
git log --since='2026-03-18' --oneline -- ggml/src/ggml.c ggml/src/ggml-alloc.c ggml/src/ggml-backend.cpp  # ggml 共通

# 運用モデルの arch 確認(実機、読み取り専用)
ssh t120h-p100 "head -c 3M '<gguf path>' | strings -n 5 | grep -A1 general.architecture"  # → qwen35moe
```

**バックエンド固有**の採録コミット(P100 8件 + Vulkan 14件 + ROCm pin commit)は、上記でハッシュ・日付・件名・窓内実在を確認済み。差分本文は主要コミット(`e82aaf258`, `112c78159`, `241cbd41d`, `3e037f313` および UMA 関連の `32120c10e`/`4d8cc0c56`/`3e7bd4f39`/`558e221b7`/`fdc3db9b6`)を直接精査した。**「ハードウェア非依存の汎用改善」セクション**は server/src/common/ggml 共通を別途調査したもので、各コミットに検証ステータス(✔=直接確認 / △=サブエージェント報告)を付与している(同セクション参照)。

**重要な訂正経緯**: 初期のサブエージェント調査は「MI25 は UMA デバイス」という誤前提を含んでおり、UMA 専用最適化を MI25 向け高重要度と誤判定していた。本レポートでは `ggml-vulkan.cpp` の `uma` 判定ロジック(`deviceType == IntegratedGPU` のみ true)を確認し、MI25 がディスクリート GPU で `uma=false` であることを根拠に該当コミットを「非該当」へ訂正済み。残る Vulkan コミットの内容要約はサブエージェント調査に基づく推定を含むため、運用判断の前には実機での実測・確認を推奨する。

---

## 核心発見サマリ

### P100(CUDA/Pascal)
- **最重要は `e82aaf258`(tile FA kernel on Pascal 修正)**。P100 は Tensor Core 非搭載で **mma(matrix multiply accumulate)系の Flash Attention を使えず、tile FA 経路に依存**する。この修正と一連の tile/mma FA 拡張(`046e28443`, `7b8443ac7`, `88458164c`, `86221cf6d`)が、P100 の FA 利用に直接関わる。
- 新型量子化 **NVFP4(`112c78159`)は DP4A(cc6.1+)前提で、cc6.0 の P100 では非利用**。同コミットが MI25 ROCm pin の原因でもある。
- CMake の**デフォルト** CUDA arch には cc60 ネイティブが含まれない(`50/61/70-virtual`)が、**当環境はビルドスクリプトで `-DCMAKE_CUDA_ARCHITECTURES=60` を明示**しており、master 追従で正常ビルド・動作している。**「サポート対象外」ではない**(なお `50-virtual` PTX は cc6.0 上で JIT 動作可能なため、明示なしでも一応動く)。

### MI25+Vulkan(RADV/gfx900)
- **重要な前提訂正**: MI25 は **ディスクリート GPU(16GB HBM2、PCIe 接続)であり UMA(統合メモリ)ではない**。llama.cpp の Vulkan `uma` フラグは `device->properties.deviceType == IntegratedGPU` のときのみ true(`ggml-vulkan.cpp` L5729/L6526)で、MI25 は discrete のため **`uma=false`**。
- したがって今期目立った **UMA 専用最適化は MI25 では発動しない**: `32120c10e`(host-visible memory 優先)と `3e7bd4f39`(memcpy read への barrier)はいずれも `uma` 分岐内のコード。さらに `4d8cc0c56` は条件が `AMD && architecture != AMD_GCN && !uma` であり、**GCN5 の MI25 は対象外**(初期サブエージェント報告の「GCN だから有効化」は条件の逆読みで誤り)。
- MI25 に効きうるのは **`uma` 非依存の汎用変更**に限られる: 並行性(`55ac0909e` device mutex 非保持、`bef69f130` host memory lock 競合削減)、安定性(`91eb8f4fa` memory logger 安全性)、汎用転送(`fdc3db9b6`、`558e221b7`)、生成系・量子化演算(`c6e408837` MUL_MAT_VEC F16/32、`19620004f` Q3_K/Q6_K block-load、`d6d0ce821` iq1 shared memory)。
- **coopmat2 / Hopper PDL / BF16 専用 / Apple・Asahi ARM 系、および UMA 専用・AMD 非 GCN 専用の最適化は gfx900・P100 いずれにも非該当**。

---

## P100(CUDA/Pascal)関連の変更

| ハッシュ | 日付 | 件名(PR) | P100 への影響 | 重要度 |
|---------|------|----------|--------------|--------|
| `e82aaf258` | 04-30 | CUDA: fix tile FA kernel on Pascal (#22541) | **Pascal 明示の修正。** DKQ=320/DV=256 の tile FA config を SRAM 制約に合わせ GQA ratio 32→16 に調整。tile FA は「mma を使えない GPU(Pascal 以前)」専用経路であり P100 が直接該当 | **高** |
| `7b8443ac7` | 04-28 | flash-attn DKQ=320/DV=256 with ncols2=32 (#22286) | 大 head-dim 向け FA サポート追加。`e82aaf258` がこの設定を Pascal 向けに後追い修正した流れ | 中 |
| `046e28443` | 05-09 | Add flash attention MMA / Tiles to support MiMo-V2.5 (#22812) | MMA と **Tiles** 両経路を拡張。Tile 側は P100 の FA 経路に効く(特定モデルの head-dim 対応) | 中 |
| `88458164c` | 04-01 | CUDA: Add Flash Attention Support for Head Dimension 512 (#20998) | head-dim 512 の FA 対応。Qwen 系など通常モデルでは未使用だが FA 経路の拡張 | 低-中 |
| `86221cf6d` | 04-01 | CUDA: fix FA kernel selection logic (#21271) | FA カーネル選択ロジックのバグ修正。P100 が tile 経路へ正しく振り分けられる正確性に関わる | 中 |
| `ff5ef8278` | 04-11 | CUDA: skip compilation of superfluous FA kernels (#21768) | 不要 FA カーネルのコンパイル省略。実行時性能ではなくビルド時間/バイナリサイズの最適化 | 低 |
| `112c78159` | 03-26 | ggml-cuda: Add NVFP4 dp4a kernel (#20644) | NVFP4 量子化の dp4a 高速 kernel(`ggml_cuda_dp4a` + `FP8_AVAILABLE` 使用)。DP4A は cc610+ 前提で P100(cc600)は非対応。**当環境は NVFP4 フォーマットを使わないため P100 運用への影響はなし**。同時に導入された fp8 e4m3 型が **MI25 ROCm の gfx900 ビルド不能(=pin)の原因** | 中 |
| `241cbd41d` | 05-29 | cuda: disables launch_fattn PDL enrollment due to compiler bug (#23825) | FA 起動の共通コード `fattn-common.cuh` で PDL enrollment を無効化するコンパイラバグ修正。PDL 自体は Hopper+ 機能で **P100 はもともと非使用のため実害はゼロ**だが、全 GPU 共通の FA 経路に入る変更のため参考として記載 | 低 |

### 補足: ビルド対象アーキテクチャ

現行 `ggml/src/ggml-cuda/CMakeLists.txt` のデフォルトは GPU 非接続時に `50-virtual 61-virtual 70-virtual` を指定し、**cc60(P100 ネイティブ)を含まない**。ただし:
- 当環境のビルドスクリプト `update_and_build-t120h-p100.sh` は `-DCMAKE_CUDA_ARCHITECTURES="60"` を明示しており、P100 ネイティブコードを生成している。
- 仮に明示しなくても `50-virtual` の PTX は cc6.0 上で JIT 実行可能(前方互換)。
- よって **P100 は upstream のサポート対象から外れていない**。サブエージェント初期報告の「サポート対象外の可能性」は不正確であり、本レポートでは否定する。

### 参考: upstream 変更が P100 運用に波及した実例

スコープ外(2026-03-18 以前/CUDA 共通領域)だが、2026-06-02 頃の master で compute buffer 確保が約2倍に増えるリグレッションが発生し、t120h-p100 で `-ub 8192` 起動時に OOM が顕在化した。対策として `-ub 4096` を採用済み(詳細は参照レポート [llama_cpp_oom_regression_fix](2026-06-03_063647_llama_cpp_oom_regression_fix.md))。**master 追従では今後も同種の波及がありうるため ub・VRAM headroom の監視が必要**という教訓。

---

## MI25+Vulkan(RADV/gfx900)関連の変更

| ハッシュ | 日付 | 件名(PR) | MI25/gfx900 への影響 | 重要度 |
|---------|------|----------|---------------------|--------|
| `32120c10e` | 06-16 | vulkan: prefer host-visible memory buffers on UMA devices (#22930) | `uma`(=IntegratedGPU)分岐内の最適化。**MI25 はディスクリート GPU で `uma=false` のため非該当** | **非該当** |
| `4d8cc0c56` | 05-27 | vulkan: avoid preferring transfer queue on AMD UMA devices (#22455) | 条件は `AMD && architecture != AMD_GCN && !uma`。**MI25 は GCN5 かつ discrete のため対象外**(「GCN だから有効」は条件の逆読み) | **非該当** |
| `558e221b7` | 06-17 | vulkan: record actual memory properties during buffer creation (#24326) | バッファ作成時に実メモリプロパティを記録(`uma` 非依存の汎用基盤修正)。MI25 でも有効 | 中 |
| `3e7bd4f39` | 06-12 | vulkan: add pipeline barriers for memcpy read operations (#23770) | barrier 追加箇所は `vk_buffer_read_2d` の `eHostVisible && uma` ブロック内。**MI25(uma=false)はこの経路を通らず非該当** | **非該当** |
| `55ac0909e` | 06-01 | vulkan: don't hold the device mutex while compiling pipelines (#23641) | pipeline コンパイル中に device mutex を保持しない。並行実行時のロック競合削減 | 中 |
| `bef69f130` | 06-01 | vulkan: reduce host memory lock contention (#23376) | host memory 周りのロック競合を削減(shared_mutex 化) | 中 |
| `fdc3db9b6` | 06-11 | vulkan: add fast path for contiguous buffer transfers (#23973) | 連続バッファ転送の高速経路(`uma` 非依存の汎用最適化)。MI25 でも効きうる | 中 |
| `c6e408837` | 05-27 | vulkan: Switch MUL_MAT_VEC to 4 K per iteration for F16/32 (#22887) | 生成フェーズの行列ベクトル積(F16/F32)をループアンロール最適化。**eval 改善の可能性**(要実測) | 中 |
| `19620004f` | 06-01 | vulkan: Block-load Q3_K/Q6_K block data and subtract on 32b ints (#23056) | Q3_K/Q6_K のブロック読み込み最適化(Mesa/RADV 向け)。当環境で一般的な量子化形式 | 中 |
| `d6d0ce821` | 06-09 | vulkan: reduce iq1 shared memory usage for mul_mm (#24287) | IQ1 の共有メモリ削減。レジスタ/SRAM 圧力低減(全 GPU 対象) | 低-中 |
| `b4e3dc613` | 06-09 | vulkan: add `v_dot2_f32_f16` support in matmul and Flash Attention (#24123) | dot2 f16 命令サポート(`device->dot2_f16` で条件付き利用)。**gfx900 で当該拡張が有効かは実機確認が必要** | 低-中 |
| `a6d6183db` | 05-17 | ggml-vulkan/CMakeLists: add a check for SPIRV-Headers (#22009) | SPIRV-Headers チェック追加。当環境は spirv-headers 必須のため、早期エラー検出として有益 | 中 |
| `95405ac65` | 05-23 | vulkan: fix windows find_package of SPIRV-Headers (#23215) | **Windows 限定**の修正。Linux 運用の MI25 には直接無関係(注記のみ) | — |
| `91eb8f4fa` | 05-28 | vulkan: Fix memory logger unsafe iterator access (#23667) | memory logger のイテレータ安全性。クラッシュ防止 | 低 |

### 注意点(因果の扱い)

- `3e7bd4f39`(pipeline barrier)等を「f16 KV 破損防止に直接寄与」と断定はしない。本レポートでは **同期強化/安定性向上**という事実ベースの記述に留める。当環境の f16 KV 不安定問題(本番は q8_0 限定)との因果は未検証。
- `c6e408837`(MUL_MAT_VEC)や `19620004f`(Q3_K/Q6_K)の性能効果は、当環境の eval 遅さ(ROCm 比 0.6倍)への寄与可能性として挙げるが、実測はしていない。

---

## ハードウェア非依存の汎用改善(P100・MI25 Vulkan 両方が恩恵)

ggml-cuda / ggml-vulkan のバックエンド固有変更とは別に、**llama-server・推論コア(src/)・ggml 共通基盤**には両バックエンドが等しく恩恵を受ける汎用改善がある。当環境(llama-server、Qwen3.6=`qwen35moe` hybrid、ctx=131072、FA=1、KV q8_0、継続バッチ)で実利のあるものを抽出した。

**検証ステータス**: ✔=本レポート作成者が `git show`/コードで直接確認、△=サブエージェント調査報告(内容要約は未独立検証、運用前に実機確認推奨)。

### A. VRAM/メモリ削減(両バックエンド・FA 時に直接効く)

| ハッシュ | 日付 | 件名(PR) | 効果 | 検証 | 重要度 |
|---------|------|----------|------|------|--------|
| `031ddb2e0` | 05-29 | llama: use f16 mask for FA to save VRAM (#23764) | `src/llama-graph.cpp` で FA の attention mask を F32→F16 化(バックエンド非依存)。**mask テンソル分の VRAM が半減**。ctx=131072 ではマスクが大きく効果的(全 VRAM の半減ではない点に注意) | ✔ | **高** |
| `de6f727aa` | 06-01 | llama: limit max outputs of `llama_context` (#23861) | `n_outputs_max` を実並列数に合わせ縮小し出力バッファ VRAM 削減 | △ | 中 |

### B. hybrid / SWA(iswa)/ MTP 関連(当環境 arch=`qwen35moe` に該当)

| ハッシュ | 日付 | 件名(PR) | 効果 | 検証 | 重要度 |
|---------|------|----------|------|------|--------|
| `e1cb81748` | 04-01 | memory: respect unified KV cache in hybrid memory for eval tasks (#21224) | hybrid memory パス(`llama-memory-hybrid*.cpp`)が unified KV フラグを無視していた問題を修正。**Qwen3.5/3.6 等 hybrid モデルの eval(hellaswag 等、n_parallel≥4)失敗を解消**。サーバ対話運用(低並列)への効果は限定的 | ✔ | 中 |
| `236531595` | 06-02 | kv-cache: SWA checkpoints store only non-masked cells (#23981) | SWA(iswa)状態保存で window 外セルを除外し checkpoint サイズ削減 | △ | 中 |
| `166fe2949` | 06-04 | qwen35: post-norm hidden state for MTP (#24025) | Qwen3.5/3.6 の MTP 層の特徴抽出を pre-norm→post-norm に修正(精度向上)。**当環境で MTP/spec を有効化する場合に該当** | △ | 中 |

### C. グラフ・推論オーバーヘッド削減(両バックエンド)

| ハッシュ | 日付 | 件名(PR) | 効果 | 検証 | 重要度 |
|---------|------|----------|------|------|--------|
| `3f7c29d31` | 04-16 | ggml: add graph_reused (#21764) | 計算グラフに atomic version id を付与しグラフ再利用を検出(`ggml` 共通=バックエンド非依存)。eval ループの再構築オーバーヘッド削減。**ただし高速化の度合いはバックエンド依存(CUDA graph で顕著、Vulkan では効果差あり)、要実測** | ✔ | 中 |
| `3c81c8dee` | 05-19 | server: print graphs reused in slot timings (#23279) | slot timings に graphs reused カウンタ追加(上記効果の可視化、チューニング用) | △ | 低 |

### D. prompt / checkpoint キャッシュ効率(server、長コンテキスト対話)

| ハッシュ | 日付 | 件名(PR) | 効果 | 検証 | 重要度 |
|---------|------|----------|------|------|--------|
| `e2ef8fe42` | 05-25 | server: fix checkpoints creation (#22929) | chat template の message 境界で checkpoint を作成、中途 checkpoint を回避。`--checkpoint-min-step` 追加。対話の prompt 再処理削減 | △ | 高 |
| `6f3a9f3de` | 06-04 | server: avoid unnecessary checkpoint restore when new tokens are present (#24110) | 新規トークンがある場合の不要な checkpoint 復元を回避 | △ | 中 |
| `961e9a3e4` | 06-09 | server: do not clear slots without unified KV cache (#24190) | 非 unified KV 運用で idle スロットを破棄せず prompt cache に保持し再処理を削減 | △ | 中 |

### E. 安定性・汎用バグ修正

| ハッシュ | 日付 | 件名(PR) | 効果 | 検証 | 重要度 |
|---------|------|----------|------|------|--------|
| `fa9704152` | 05-21 | ggml-alloc: fix out-of-bounds read in ggml_dyn_tallocr_remove_block | メモリアロケータのブロック削除時の境界外読み取り修正(`ggml-alloc` は全バックエンド共通、潜在クラッシュ回避) | △ | 中 |
| `3ba12fed0` | 04-08 | kv-cache: extend cache quantization checks (#21586) | KV 量子化 + FA の互換性チェックを `auto` だけでなく `enabled` 構成でも実施。**当環境(FA=1 明示 + q8_0)で不正構成を早期検出** | ✔ | 中 |
| `52fb93a2b` | 05-21 | server: free draft/MTP resources on sleep to fix VRAM leak (#23461) | sleep 時に draft/MTP の GPU リソースを解放し VRAM リークを修正(MTP/spec 利用時) | △ | 中 |

### F. サンプリング / テンプレート品質(汎用、Qwen3.6 で使う機能に応じて)

| ハッシュ | 日付 | 件名(PR) | 効果 | 検証 | 重要度 |
|---------|------|----------|------|------|--------|
| `d77599234` | 04-29 | server: reasoning budget に prompt token を渡さない (#22488) | thinking budget の計算から prompt token を除外し overrun を防止(thinking 利用時) | △ | 中 |
| `9e3b928fd` | 06-07 | common: relax sampler name matching (#23744) | サンプラー名照合を大小文字/別名許容に(`dry`/`top_k`/`min_p` 等の指定信頼性向上) | △ | 低 |

### 当環境では該当しない/除外したもの(誤採用防止のため明示)

- **LFM2 / LFM2.5 固有の tool-call・json_schema・reasoning 修正**(`7dad2f1a1`, `98d5e8ba8`, `d2462f8f7`, `da87e9b61` 等): LFM2 は別の hybrid モデルで Qwen3.6 とは無関係。サブエージェントが「高重要度」としていたが**当環境には非該当**。
- **EAGLE3 / 一部 spec metrics**(`a1824902b`, `635b65ad7`): 当環境で当該 spec 手法は未使用。
- **Tensor Parallelism 専用**(`8e6fff84d`, `3fc6f1aed`): TP 構成時のみ。
- **activation rotation / Walsh-Hadamard**(`744c0c731`, `a817a22bc`): 既定で無効の特殊量子化機能。当環境で有効化していなければ非該当。

> 注: D・F カテゴリと B の `236531595`/`166fe2949` は検証ステータス △(サブエージェント報告)であり、件名・日付・窓内実在は確認済みだが、効果と当環境適合の最終判断には実機確認・実測を推奨する。MTP/spec 系は当環境での有効化状況(サーバ設定)に依存する。

---

## 無関係と判定したカテゴリ(明示)

以下は P100(cc6.0)・gfx900(GCN5)いずれのハードウェアにも非関連であり、本レポートから除外した:

- **coopmat / coopmat2(協調行列)**: NVIDIA(Volta+)や RDNA3+ 等の新しいハードウェア機能。gfx900 は非搭載
- **Hopper PDL(Programmatic Dependent Launch)等の Hopper/Blackwell 向け最適化**: P100 は非対象
- **BF16 専用パス**: P100・gfx900 とも BF16 非対応(当環境のモデルは q8_0 等の量子化中心。KV キャッシュも本番は q8_0 限定)
- **Apple / Asahi Linux(ARM GPU)向け変更**: 別ハードウェア
- **UMA(統合 GPU)専用の最適化**(例: `32120c10e`, `3e7bd4f39`): MI25 はディスクリート GPU で `uma=false` のため非発動
- **AMD 非 GCN dGPU 専用の最適化**(例: `4d8cc0c56`): MI25 は GCN5 で対象外
- **AMD RDNA3/RDNA4/CDNA 向けの MMA(tensor core)FA・チューニング**(例: `3e037f313` 05-14 `HIP: RDNA3 mma FA, faster AMD transpose, tune AMD`): 件名に "AMD" を含み MI25 関連に見えるが、**(a) gfx900(GCN5)は tensor core 非搭載で MMA FA 非該当**、**(b) これは ROCm/HIP バックエンドの変更**で MI25 は Vulkan 運用のため二重にスコープ外

---

## 運用への示唆

- **P100(CUDA)**: master 追従の継続で問題なし。FA は tile 経路の改善が今期も継続しており(`e82aaf258` 他)、追従の恩恵がある。一方、CUDA 共通領域のリグレッション(2026-06-02 の OOM 例)が運用に波及しうるため、更新後は **ub・VRAM headroom の監視**を継続する。
- **MI25+Vulkan**: pin 不要の前提(HIP を device compile しない)は今期も維持される。**ただし今期の Vulkan 改善の目玉である UMA 専用最適化(`32120c10e` 他)・AMD 非 GCN 向け最適化(`4d8cc0c56`)は、MI25 がディスクリート GPU かつ GCN5 のため恩恵を受けない**。MI25 に効くのは汎用の並行性・安定性・演算最適化に限られる。eval の遅さに効きうる `c6e408837`(MUL_MAT_VEC)などは **次回ベンチで実測する価値がある**。`b4e3dc613` の dot2_f16 が gfx900 で有効化されるかも実機確認の候補。
- **汎用改善(両環境共通)**: バックエンド固有変更より、むしろ**両環境が等しく恩恵を受ける汎用改善**(上記セクション)の方が運用インパクトが大きい場合がある。特に `031ddb2e0`(FA mask の F16 化)は ctx=131072 の VRAM 余裕を即座に増やせる検証済みの改善で、両環境で次回ビルド時に効く。checkpoint/prompt cache 改善(`e2ef8fe42` 他)は対話運用の prompt 再処理を削減。**運用モデルが hybrid(`qwen35moe`)である**ため、hybrid/SWA/MTP 系の改善(B カテゴリ)も追従の恩恵対象になる点は今後の更新で留意。

## 参照レポート

- [llama.cpp CUDA OOM リグレッション対策(P100)](2026-06-03_063647_llama_cpp_oom_regression_fix.md)
- [mi25 ROCm 基準構成(Qwen3.6 128k)](2026-06-13_112006_mi25_qwen36_128k.md)
- [mi25 Vulkan 性能・pin 不要実証](2026-06-14_001107_mi25_vulkan_qwen36_128k.md)
- [mi25 Vulkan バックエンド品質等価検証](2026-06-14_041305_mi25_vulkan_backend_quality.md)
