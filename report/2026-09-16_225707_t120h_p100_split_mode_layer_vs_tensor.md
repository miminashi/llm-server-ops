# P100 4 枚の MoE では tensor 分割が深さでだけ勝つ

- **実施日時**: 2026年9月16日 22:03 〜 23:10 JST (電源投入・NCCL 導入・465e49b9c への再ビルド 2 回・tensor 起動プローブ 3 回・VRAM プリフライト・3 腕本計測 25 分・作図とレポート作成)
- **報告日時**: 2026年9月16日 23:10 JST
- **作成者**: Claude Opus 5 (1M context)

## 概要

二日前に、カードを 7 枚積んだ機械で、大きなモデルを複数のカードに分ける二通りのやり方を比べた。層ごとに担当を割り振る既定の方式と、一つの層の計算を全カードで分担する方式である。そのときは分担方式があらゆる場面で勝ち、とくに深い文脈での生成速度が三倍近く開いた。ただしそのレポート自身が残課題に「他の機械や、専門家を切り替える型のモデルで測り直すまで既定値を変えるな」と書いていた。今回はその宿題に応えるもので、カードを 4 枚積んだ別の機械で、社内の標準モデル（専門家切り替え型）を使って同じ計測をやり直した。

結論から言うと、**前回の「分担方式が全面的に勝つ」は今回の条件では成り立たなかった**。勝ち負けが文脈の深さで入れ替わる。浅いところでは層方式のほうが二割ほど速く、およそ三万トークンを境に逆転し、十三万トークンの深部では分担方式が六割以上速くなる。分担方式の生成速度は深さがほとんど効かず、最深部でも浅いところの九割近くを保つのに対し、層方式は半分以下に落ちるためである。

プロンプトの読み込み速度に至っては、**全ての深さで層方式が勝った**。前回は分担方式が一割から二割上回っていたので、符号が逆になっている。ただし新規の短いプロンプトに限れば分担方式が七割ほど速く、長いプロンプトでは逆に一割強遅い。つまり読み込みは「短い依頼が多いか、長い文書を一度に流すか」で有利不利が変わる。

もう一つ、前回の最大の発見だった「層方式でカードを増やしても生成は速くならない」は、今回も同じ形で再現した。2 枚から 4 枚に増やすと、読み込みは一割から五割速くなるのに、生成は全ての深さでわずかに遅くなる。三回の計測、二つの機械、二種類のモデルで一貫しており、かなり確かな性質だと言える。

今回は準備の段階でも収穫があった。この機械にはカード間の集団通信ライブラリが入っておらず、分担方式は自動的に代替経路にまわされることが分かった。前回のレポートでは、この代替経路に落とすと読み込み速度が八割失われると報告している。そこでユーザの許可を得てライブラリを導入し、正規の経路で測り直した。すると、前回 7 枚の機械で十三回連続して失敗した起動が、今回は三回とも十五秒で成功した。起動が固まる不具合は、カードの枚数か、機械か、モデルのいずれかに依存するものらしい。

計測の副産物として、層方式ではカードのクロックが終始低いままだったことも分かった。分担方式ではほぼ常に最高クロックまで上がる。カードの稼働率が四割そこそこしかなく、上げる理由がないためである。温度も電力も余裕があり、今回の差が熱や電力の制限によるものでないことは確認してある。

運用への含意としては、既定の層方式を今すぐ変える理由は見当たらない。社内標準の使い方は短い依頼が多く、文脈もそこまで深くならないので、その領域では層方式のほうが速い。逆に、十万トークン級の文脈を日常的に扱う用途が出てきたら、分担方式に切り替える価値がある。

## 添付ファイル

- [実装プラン](attachment/2026-09-16_225707_t120h_p100_split_mode_layer_vs_tensor/plan.md)
- [計測結果一式](attachment/2026-09-16_225707_t120h_p100_split_mode_layer_vs_tensor/run/) — `run-info.json`（バイナリ sha256・モード表・KV 型）、`results-{layer,tensor,layer2}.json` / `-pp0.json`、`results-real.json`、`argv-*.txt`、`server-*.log`、`sampler-*.log`（2 秒間隔の温度・電力・利用率）、`responses-*/`、`run-bench.log`
- [VRAM プリフライト](attachment/2026-09-16_225707_t120h_p100_split_mode_layer_vs_tensor/preflight/) — 3 腕を ctx=131072 で起動して VRAM を測った軽量 run
- [今回の `bench.local.conf`](attachment/2026-09-16_225707_t120h_p100_split_mode_layer_vs_tensor/bench.local.conf)
- [tensor 起動プローブのスクリプト](attachment/2026-09-16_225707_t120h_p100_split_mode_layer_vs_tensor/probe.sh) ／ [その成功ログ](attachment/2026-09-16_225707_t120h_p100_split_mode_layer_vs_tensor/probe-try1.log)
- スクリプト: [結果表の生成](attachment/2026-09-16_225707_t120h_p100_split_mode_layer_vs_tensor/tables.py) ／ [サンプラ集計](attachment/2026-09-16_225707_t120h_p100_split_mode_layer_vs_tensor/sampler.py) ／ [GGUF メタデータ読み出し](attachment/2026-09-16_225707_t120h_p100_split_mode_layer_vs_tensor/ggufmeta.py)
- 図: [日本語版](attachment/2026-09-16_225707_t120h_p100_split_mode_layer_vs_tensor/run/split-bench-ja.png) ／ [英語版](attachment/2026-09-16_225707_t120h_p100_split_mode_layer_vs_tensor/run/split-bench-en.png)

## 核心発見サマリ

![t120h-p100 の Tesla P100 4 枚で測った layer 分割 / tensor 分割 / 2 枚 layer の比較。①prefill は全深度で layer が最速（深さ 16k で 896.3 対 749.4 t/s）で、手本レポートとは符号が逆。②decode は深さ 32,458 tok 付近で交差し、浅部は layer 49.36 対 tensor 40.62 と layer が +22%、最深部 128,793 tok では tensor 35.96 対 layer 22.09 と tensor が +63%。③相対差は prefill が全深度 -16〜-21%、decode が -18% から +63% へ反転。④2 枚 layer を基準にすると、4 枚 layer の decode は全深度 -6〜-8% と改善せず、prefill だけ +12〜+49% 伸びる](attachment/2026-09-16_225707_t120h_p100_split_mode_layer_vs_tensor/run/split-bench-ja.png)

**結論**: **Tesla P100 16GB ×4（sm_60、PCIe、NVLink なし）+ Qwen3.6-35B-A3B UD-Q4_K_XL（MoE、256 experts / 8 active）+ KV q8_0 + `-fa on` + NCCL AllReduce の条件では、`--split-mode tensor` は `layer` に全面的に勝たない。勝敗は文脈の深さで入れ替わる。** decode は **深さ 11 tok で -18%（40.62 対 49.36 t/s）と負け、深さ 32,458 tok で +5% に転じ、深さ 128,793 tok で +63%（35.96 対 22.09 t/s）**。分岐点は約 3 万トークン。**tensor の decode は最深部でも初段比 88.5% を保つ**のに対し **layer は 44.7%** まで落ちるため、深さが進むほど tensor が有利になる。**prefill（増分）は全深度で layer が勝ち（tensor は -16〜-21%）、手本レポート（+10〜+22%）と符号が逆**。ただし depth-0 の新規プロンプトでは **pp512 で tensor +66%（680.2 対 408.8 t/s）**、pp2048 で +21%、**pp8192 で -13%** と、バッチが小さいほど tensor が有利になる。**手本の最大の発見「layer 分割は速度ではなく VRAM を買う」は今回も再現**し、2 枚 → 4 枚で decode は全深度 **-6〜-8%**（例: 深さ 128,793 tok で 2 枚 23.48 対 4 枚 22.09 t/s）、伸びるのは prefill だけ（+12〜+49%）。GPU 利用率は **layer 43.1% / tensor 80.0% / layer2 67.6%**、温度最大 80℃・電力平均 95〜126 W（TDP 250 W）で**熱・電力律速ではない**。**副次的に、layer 腕では全サンプルが 1189 MHz に留まり最大ブースト 1328 MHz に一度も達しない**（tensor 腕は 36/40 が 1328 MHz）。証跡: バイナリ `21df743c9ba392e2869d614d02dce94a25c942801091d0ac48ce59a6d0376170`（llama.cpp master `465e49b9c`, build 10830、**NCCL 2.31.2 リンク**）。

## 前提・目的

- **背景**: [手本レポート](./2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor.md)（aws-gpu01、Tesla P100 ×7、dense 27B）が「tensor が全面的に勝つ」と結論し、残課題に「**他サーバ（t120h-p100 の 4 枚 ほか）や MoE モデルでの再測定なしに `start.sh` の既定値を変えるべきではない**」と明記していた。本計測はその残課題に直接応える。
- **目的**: 同じ llama-split-bench の深度ラダー方式を **t120h-p100（P100 ×4）× Qwen3.6-35B-A3B（MoE）** で実施し、手本の結論が別条件でも成り立つかを検証する。
- **本プロジェクト初の MoE × tensor 分割**。手本レポートの残課題「MoE モデルでの layer vs tensor」の初データにあたる。
- **モデルは本プロジェクトの既定 LLM**（`llama-up.sh` の引数省略時に起動するもの）なので、結果がそのまま日常運用の判断材料になる。
- **ユーザ判断**: (1) llama.cpp は手本と同じ `465e49b9c` に揃える、(2) tensor 腕は既定の NCCL 経路を優先し、駄目なら回避策に落とす、(3) モデルがサーバに無ければ転送せず報告する（実際にはサーバに存在したので不要だった）。**加えて計測中に NCCL 導入のための sudo 実行の許可を得た**。

## 環境情報

| 項目 | 値 |
|---|---|
| サーバ | t120h-p100 (10.1.4.14)、HPE ProLiant。**本作業のために電源投入**（Off だった。iLO5、爆音ガードの対象外なので通常操作） |
| GPU | Tesla P100-PCIE-16GB × 4（sm_60 / compute cap 6.0）、PCIe 接続・**NVLink なし** |
| CPU / RAM | 80 論理コア（Xeon Gold 6138 ×2）/ 251 GiB |
| llama.cpp | master `465e49b9c`、build 10830、`built with GNU 11.4.0`、CUDA 12.9、`CMAKE_CUDA_ARCHITECTURES=60`。**手本レポート 3 本と同一コミット**（ただしコンパイラと CUDA が違うのでバイナリは別物） |
| バイナリ sha256 | `21df743c9ba392e2869d614d02dce94a25c942801091d0ac48ce59a6d0376170` |
| **NCCL** | **2.31.2（`+cuda12.9`）を本作業で新規導入**。`-DGGML_CUDA_NCCL=ON -DNCCL_ROOT=$HOME/nccl -DCMAKE_BUILD_RPATH=$HOME/nccl/lib` でリンク（後述） |
| モデル | `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf`（`unsloth/Qwen3.6-35B-A3B-GGUF`、**22,360,456,160 B = 20.8 GiB**、blob sha256 `707a55a8…4450`）。**サーバに既存**のものを使用 |
| モデル構成 | arch `qwen35moe`、**40 層 / expert 256・active 8 / expert_ffn 512**、embd 2048、head 16 / head_kv 2（GQA 8:1）、モデル側 context_length 262144 |
| KV キャッシュ | `--cache-type-k q8_0 --cache-type-v q8_0` |
| 共通起動引数 | `-ngl all -fa on -c 131072 --parallel 1 -t 16 --jinja --cache-ram 8192 --cache-idle-slots --cache-reuse 256` |
| `-b` / `-ub` | **指定せず**（ビルド既定 `-b 2048 -ub 512`）。手本と同一条件にするため。**本番運用の `start.sh` は `-b 4096 -ub 4096`** なので prefill の絶対値は運用時と異なる（後述） |
| 投機デコード | **無効**（`SPEC_ARGS=""`。本モデルは非 MTP） |
| AllReduce | **既定の NCCL 経路**（`LAUNCH_PREFIX` 空、`run-info.json` の `launch_prefix` も空。フォールバック警告 0 件を確認） |
| 計測モード | `layer`（CUDA0-3 / layer）、`tensor`（CUDA0-3 / tensor）、`layer2`（CUDA0,CUDA1 / layer、ベースライン） |
| ワークロード | ctx=131072、ステージ `0,16000,32000,64000,128000`、各段 1000 tok 生成、pp0 サイズ 512/2048/8192 |
| 所要 | layer 7分03秒（22:31:32→22:38:35）／ tensor 9分11秒（→22:47:46）／ layer2 8分49秒（→22:56:35）。**合計 25分03秒**（手本の 63分50秒より速いのは MoE で active 3B のため） |

**`single` ベースラインを断念した理由**: 重み 20.8 GiB は 1 枚の空き 15.6 GiB に収まらない。手本と同じく **2 枚 layer（`layer2`）をベースライン**に据えた（`BASELINE=layer2`）。図のパネル④はこの 2 枚構成を基準とした伸び率である。

### VRAM（ctx=131072、ロード直後の実測）

| 腕 | CUDA0 | CUDA1 | CUDA2 | CUDA3 | 合計 |
|---|---:|---:|---:|---:|---:|
| layer（4枚） | 7,041 | 6,559 | 6,433 | 6,671 | 26,704 MiB |
| **tensor（4枚）** | **6,529** | **6,463** | **6,529** | **6,463** | **25,984 MiB** |
| layer2（2枚） | 12,479 | 11,983 | — | — | 24,462 MiB |

**tensor 分割では 4 枚の使用量がほぼ完全に揃う**（最大差 66 MiB）のに対し、layer 分割では 608 MiB の偏りが出る。MoE の expert 重みも分割対象になっていることの傍証である。**2 枚構成でも 12.5 GiB / 16 GiB で収まった**ため、計画で用意していた `layer3`（3枚）へのフォールバックは不要だった。

## 再現方法

```bash
cd /home/ubuntu/projects/llm-server-ops

# 1) 電源投入 → SSH 到達待ち → ロック（lock.sh は SSH 経由なので電源が先）
.claude/skills/gpu-server/scripts/power.sh t120h-p100 on
until ssh -n -o ConnectTimeout=5 -o BatchMode=yes t120h-p100 uptime 2>/dev/null; do sleep 15; done
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 2) llama.cpp を手本と同じ 465e49b9c にして再ビルド（既存 build は必ず退避）
ssh -n t120h-p100 'cd ~/llama.cpp && mv build build.bak-0843245cb'
ssh -n t120h-p100 'cd ~/llama.cpp && git fetch origin 465e49b9cea78a68b9c244ffb48d0ee24a82873d && \
  git checkout 465e49b9cea78a68b9c244ffb48d0ee24a82873d'

# 3) NCCL の導入（apt には無く sudo もパスワードを要するので、.deb をユーザ領域に展開する）
curl -O https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/libnccl2_2.31.2-1+cuda12.9_amd64.deb
curl -O https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/libnccl-dev_2.31.2-1+cuda12.9_amd64.deb
rsync -a --partial libnccl*.deb t120h-p100:/tmp/     # 約 447 MB / 実測 1.4 MB/s で 5分18秒
ssh -n t120h-p100 'mkdir -p ~/nccl-tmp ~/nccl/lib ~/nccl/include && cd ~/nccl-tmp && \
  dpkg-deb -x /tmp/libnccl2_2.31.2-1+cuda12.9_amd64.deb . && \
  dpkg-deb -x /tmp/libnccl-dev_2.31.2-1+cuda12.9_amd64.deb . && \
  cp -a usr/lib/x86_64-linux-gnu/libnccl.so* ~/nccl/lib/ && cp -a usr/include/nccl.h ~/nccl/include/'

ssh -n t120h-p100 "cd ~/llama.cpp && rm -rf build && cmake -B build -DLLAMA_OPENSSL=ON -DGGML_NATIVE=ON \
  -DGGML_CUDA=ON -DGGML_CUDA_FA_ALL_QUANTS=ON -DGGML_CUDA_NCCL=ON \
  -DNCCL_ROOT=\$HOME/nccl -DCMAKE_BUILD_RPATH=\$HOME/nccl/lib \
  -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.9/bin/nvcc -DCMAKE_CUDA_ARCHITECTURES=60 && \
  cmake --build build --config Release -- -j \$(nproc)"          # 約 4 分
ssh -n t120h-p100 'ldd ~/llama.cpp/build/bin/libggml-cuda.so | grep nccl'   # RPATH 経由で解決される

# 4) ツール転送 + 設定（bench.local.conf は添付を参照）
rsync -a --exclude .git --exclude runs src/llama-split-bench/ t120h-p100:~/llama-split-bench/
ssh -n t120h-p100 'cd ~/llama-split-bench && mkdir -p runs'

# 5) tensor 起動プローブ（NCCL 経路が固まらないかを 3 回確認。probe.sh は添付）
ssh -n t120h-p100 'bash /tmp/probe.sh 3'        # → 3/3 ok, 各 15 秒

# 6) VRAM プリフライト（危険な layer2 を最後に置く）
ssh -n t120h-p100 "cd ~/llama-split-bench && bash run-bench.sh preflight-1 --ctx 131072 \
  --stages 0,8000 --n-predict 32 --pp0-sizes 8192 --no-real \
  --mode-spec 'layer4|CUDA0,CUDA1,CUDA2,CUDA3|layer' \
  --mode-spec 'tensor4|CUDA0,CUDA1,CUDA2,CUDA3|tensor' \
  --mode-spec 'layer2|CUDA0,CUDA1|layer'"

# 7) 本計測（detached。tail -f は使わずマーカーをポーリング）
ssh -n t120h-p100 "cd ~/llama-split-bench && \
  setsid nohup bash run-bench.sh p100-4way-1 > runs/p100-4way-1.log 2>&1 < /dev/null &"
ssh -n t120h-p100 'until grep -qE "BENCH-(DONE|ABORT|FIGFAIL)" \
  ~/llama-split-bench/runs/p100-4way-1.log; do sleep 60; done'

# 8) 回収と作図（サーバに matplotlib を入れず WS 側で描く）
rsync -a t120h-p100:~/llama-split-bench/runs/p100-4way-1/ report/attachment/<TS>_.../run/
for L in ja en; do python3 src/llama-split-bench/plot_bench.py --dir report/attachment/<TS>_.../run \
  --series layer,tensor,layer2 --baseline layer2 --vs on --lang $L --out split-bench; done
```

`~/llama-split-bench/bench.local.conf` は[添付](attachment/2026-09-16_225707_t120h_p100_split_mode_layer_vs_tensor/bench.local.conf)のとおり（手本との差分は `DEVICES` が 4 枚、`MODEL`、`MACHINE`、`VENV_PY` のみ）。

## 結果詳細

### 1. decode（生成速度、t/s）— 約 3 万トークンで勝敗が入れ替わる

| 実効深さ (tok) | layer (4枚) | tensor (4枚) | layer2 (2枚) | tensor / layer | layer(4) / layer2(2) |
|---:|---:|---:|---:|---:|---:|
| 11 | **49.36** | 40.62 | **53.38** | **-18%** | -8% |
| 15,825 | **43.46** | 40.46 | **46.44** | **-7%** | -6% |
| 32,458 | 38.22 | **40.12** | **40.84** | **+5%** | -6% |
| 64,785 | 30.93 | **39.66** | 33.04 | **+28%** | -6% |
| 128,793 | 22.09 | **35.96** | 23.48 | **+63%** | -6% |
| **初段比の維持率** | **44.7%** | **88.5%** | 44.0% | — | — |

**手本レポートでは tensor が全深度で勝っていた（+63〜+183%）が、本条件では深さ 3 万トークン付近に分岐点がある。** 浅いところでは layer が +22% 速い。

理由は維持率にはっきり出ている。**tensor は深さ 128,793 tok でも初段比 88.5% を保つ**のに対し、layer は 44.7% まで落ちる。手本（tensor 96.0% / layer 55.3%）と傾向は同じで、**tensor の「深さに対する平坦さ」は MoE でも成り立つ**。違いは出発点で、**浅部の絶対値が tensor 40.62 に対し layer 49.36 と layer のほうが高い**ことが、交差を生んでいる。

**layer 分割で枚数を増やしても decode は改善しない**（右端列）。2 枚 → 4 枚で全深度 -6〜-8%。手本の 2 枚 → 7 枚（-4〜-7%）とほぼ同じ幅で、**3 セッション連続・2 機種・dense と MoE の両方で再現**したことになる。

### 2. prefill（増分プロンプト評価速度、t/s）— 全深度で layer が勝つ（手本と符号が逆）

| 実効深さ (tok) | layer (4枚) | tensor (4枚) | layer2 (2枚) | tensor / layer | layer(4) / layer2(2) |
|---:|---:|---:|---:|---:|---:|
| 11 | 43.4 | 34.5 | 49.2 | — ※ | — ※ |
| 15,825 | **896.3** | 749.4 | 644.9 | **-16%** | +39% |
| 32,458 | **763.8** | 611.7 | 513.6 | **-20%** | +49% |
| 64,785 | **615.0** | 486.4 | 420.8 | **-21%** | +46% |
| 128,793 | **439.7** | 359.5 | 299.8 | **-18%** | +47% |

※ ラダー初段は 11 トークンのプロンプトなので計測上のアーティファクトであり、作図にも使われない（README 記載の仕様）。

**手本では tensor が +10〜+22% 勝っていたのに対し、本条件では -16〜-21% と負ける。** prefill については **layer 分割で枚数を増やす効果が明確にある**（2 枚 → 4 枚で +39〜+49%）点は手本と共通。

### 3. depth-0 prefill（新規プロンプト、`cache_prompt=false`）— バッチが小さいほど tensor 有利

| サイズ | layer (4枚) | tensor (4枚) | layer2 (2枚) | tensor / layer |
|---|---:|---:|---:|---:|
| pp512 | 408.8 | **680.2** | 430.0 | **+66%** |
| pp2048 | 629.3 | **762.0** | 563.8 | **+21%** |
| pp8192 | **889.8** | 777.1 | 649.3 | **-13%** |

**512 トークンの短いプロンプトでは tensor が 1.7 倍速い**（手本は同条件で +194%）。ところが 8192 トークンでは逆転して layer が勝つ。**layer 側はバッチが増えるほど伸びる（408.8 → 889.8）のに対し、tensor は 680.2 → 777.1 と頭打ちになる**。エージェント用途のような短いリクエストが多い場面では tensor、長文を一度に流す用途では layer が有利という読み方になる。

なお同じ pp0 測定の decode（n=64、参考値）は **layer 53.4 / 52.7 / 49.8 に対し tensor 40.2 / 40.3 / 40.1** で、**tensor の decode は文脈長にほとんど依存しない**ことがここでも確認できる。

### 4. GPU 利用率・温度・電力・クロック（`sampler-*.log`、2 秒間隔。使用中のカードのみ）

| モード | 利用率 平均 | 温度 最大 / 平均 | 電力 最大 / 平均 | サンプル数 |
|---|---:|---:|---:|---:|
| layer (4枚) | **43.1%** | 80℃ / 71.3℃ | 205 W / 95 W | 808 |
| tensor (4枚) | **80.0%** | 80℃ / 72.5℃ | 219 W / 101 W | 1056 |
| layer2 (2枚) | 67.6% | 80℃ / 72.4℃ | 199 W / 126 W | 506 |

**layer 分割では 4 枚の平均利用率が 43.1% にとどまる**（手本の 7 枚は 27.5%）。枚数が減るぶん順番待ちの空きは小さくなるが、それでも tensor の 80.0% には遠い。**2 枚 layer が 67.6% と 4 枚 layer より高い**のは、枚数が少ないほど 1 枚あたりの担当が増えるためで、「layer 分割で枚数を増やすと 1 枚あたりの稼働率が下がる」ことを直接示している。

**クロックの差がさらに明瞭である**（各段の `gpu_before` / `gpu_after` 40 サンプル）:

| モード | 1189 MHz | 1328 MHz（最大ブースト） | 405 MHz（アイドル） |
|---|---:|---:|---:|
| layer (4枚) | **40 / 40** | **0** | 0 |
| tensor (4枚) | 4 | **36** | 0 |
| layer2 (2枚) | 2 | 18 | 20（未使用の CUDA2/3） |

**layer 腕では一度も最大ブーストに達していない。** 負荷が断続的でクロックを上げる理由がないためで、利用率 43.1% と整合する。温度は最大 80℃、電力平均は TDP 250 W に対し 95〜126 W であり、**熱による絞りや電力上限が今回の差を作っているのではない**。

### 5. 実プロンプト補正

`results-real.json`（日本語実務風プロンプト 3 本、temp 0.7 / top_p 0.9 / n_predict 1200、tensor 腕で実行）の decode は 40.66 / 40.65 / 40.65 t/s で、合成テキストのラダー初段 40.62 t/s に対し **補正係数 1.001**。投機デコードを無効にしているため合成と実運用の差が事実上ゼロで、**本レポートの decode 値はそのまま実運用値として読める**（図の薄い破線が実線と完全に重なっているのはこのため）。

### 6. 手本レポートとの対比

| 指標 | 手本: aws-gpu01 P100×7 / dense 27B | 本計測: t120h-p100 P100×4 / MoE 35B-A3B |
|---|---|---|
| decode 浅部（深さ 11） | tensor **+63%** | tensor **-18%**（layer の勝ち） |
| decode 最深（深さ 128,793） | tensor **+183%** | tensor **+63%** |
| decode 維持率（tensor / layer） | 96.0% / 55.3% | 88.5% / 44.7% |
| prefill 増分 | tensor **+10〜+22%** | tensor **-16〜-21%**（layer の勝ち） |
| pp512 | tensor **+194%** | tensor **+66%** |
| pp8192 | tensor **+27%** | tensor **-13%**（layer の勝ち） |
| layer の枚数効果（decode） | 2→7 枚で **-4〜-7%** | 2→4 枚で **-6〜-8%**（同傾向） |
| GPU 利用率（layer / tensor） | 27.5% / 75.9% | 43.1% / 80.0% |
| tensor 起動（NCCL 経路） | **0/13**（ハング） | **3/3**（各 15 秒） |

**共通するのは「tensor は深さに強い」「layer は枚数を増やしても decode が伸びない」「tensor のほうが GPU 利用率が高い」の 3 点**で、これらは条件を変えても再現した。**変わったのは浅部・prefill・大バッチでの優劣**で、いずれも本条件では layer 側に倒れている。

本計測は「枚数（7→4）」「モデル型（dense→MoE）」「モデルサイズ（27B→35B-A3B）」の 3 つが同時に変わっているため、**どの要因が効いたかは本レポートだけでは切り分けられない**。ただし MoE では 1 トークンあたりの実効計算量が小さく（active 3B）、tensor 分割の AllReduce が相対的に重くなるはずなので、**モデル型が主因である可能性が高い**と考えている（未検証）。

## 副次発見

1. **t120h-p100 には NCCL が入っていなかった**。初回ビルドのログに `Could NOT find NCCL` / `Warning: NCCL not found, performance for multiple CUDA GPUs will be suboptimal` が出た。この状態で `--split-mode tensor` を起動すると、サーバログに **`NCCL not compiled in; falling back to internal AllReduce.`** → **`internal AllReduce init failed (n_devices != 2?); falling back to meta-backend butterfly`** の 2 行が出て、[3 腕再測定レポート](./2026-09-16_103619_aws_gpu01_split_mode_mtp_3arm.md)が「decode -25% / prefill -78%」と定量した劣化経路にそのまま落ちる。**ビルド時に気づかないと、tensor 分割の性能を大幅に過小評価する**。
2. **`internal` 経路は P100 では選ばれないことがログで裏付けられた**。`ggml/src/ggml-cuda/allreduce.cu` の `ggml_cuda_ar_pipeline_init` が `n_devices != 2` と `cc < VOLTA` の二重ガードで nullptr を返す仕様どおり、4 枚構成では `internal AllReduce init failed (n_devices != 2?)` と明示的に失敗する。**P100 で実質選べるのは `nccl` か `none`(butterfly) の 2 択**である。
3. **NCCL は sudo なしで導入できる**。apt リポジトリはローカル（`cuda-ubuntu2204-12-9-local`）だけで NCCL を含まず、`sudo dpkg -i` はパスワードを要求する。しかし **`.deb` を `dpkg-deb -x` でホームに展開し、`-DNCCL_ROOT=$HOME/nccl -DCMAKE_BUILD_RPATH=$HOME/nccl/lib` を渡せばビルドも実行も通る**（`ggml/cmake/FindNCCL.cmake` が `NCCL_ROOT` を見る）。RPATH を埋めるので `LD_LIBRARY_PATH` も不要で、システムを汚さない。
4. **7 枚で 0/13 だった NCCL 起動ハングが、4 枚では 3/3 成功した**。各 15 秒で `/health` が ok を返し、フォールバック警告も 0 件。**手本の一連のレポートが特定したハングは、少なくとも本機・本モデル・4 枚では発生しない**。枚数依存（2 枚 1/12・7 枚 0/13・4 枚 3/3 は単調でない）、機種依存、モデル依存のいずれかであり、切り分けは未了。
5. **`llama_params_fit is not implemented for SPLIT_MODE_TENSOR, abort` という警告が tensor 腕で必ず出る**。`--fit`（既定 on）が tensor 分割に未対応で、自動調整を諦めるという意味であり、**サーバは正常に続行する**。手本レポートには記載がない。
6. **tensor 分割は MoE の expert 重みも分割している**。4 枚の VRAM 使用量が 6,463〜6,529 MiB と 66 MiB 差に収まる（layer は 608 MiB 差）。20.8 GiB の重みの大半は 256 個の expert なので、これが分割されていなければこの均等性は出ない。
7. **モデル側の `context_length` は 262144** で、本計測の ctx=131072 はその半分である。より深いラダーを組む余地がある（VRAM も 6.5 GiB / 16 GiB と余裕が大きい）。

## 残課題

- **どの要因が優劣を反転させたのかの切り分け**。本計測は枚数・モデル型・モデルサイズが同時に変わっている。**同じ t120h-p100 で dense モデル（手本と同じ Qwen3.8-27B）を測れば、機種要因とモデル要因を分離できる**。重み 16.35 GiB なので 4 枚でも 2 枚でも載る。これが最も費用対効果の高い次の一手である。
- **`start.sh` の `--split-mode layer` 固定の扱い**。本計測の範囲では**既定を変える理由がない**（浅部と prefill で layer が勝ち、既定モデルの日常的な使い方はその領域に入る）。ただし **10 万トークン級の文脈を常用する用途では tensor が 1.6 倍速い**ので、用途別に選べるようにする価値はある。`EXTRA_LLAMA_OPTS` で上書きできるので、当面はドキュメント化で足りる。
- **`-ub` を運用値（4096）に揃えた再測定**。本計測はツール既定の `-ub 512` で、`start.sh` の運用値とは異なる。prefill の絶対値は ub に強く依存するので、**運用判断に直結する数字が欲しいなら ub=4096 で測り直す必要がある**。ただし 2 枚 layer 腕は compute buffer が約 8 倍になり 16 GiB に収まらない見込みなので、その腕を落とすか `layer3` に替える設計変更が要る。
- **NCCL 導入の恒久化**。今回は `~/nccl` への展開 + RPATH で通したが、**`update_and_build.sh` は `-DGGML_CUDA_NCCL` も `-DNCCL_ROOT` も渡さない**ため、次に同スクリプトでビルドすると **NCCL 無しに戻る**（= tensor 分割が butterfly 経路に落ちる）。恒久化するならビルドスクリプトの修正か、`sudo dpkg -i` での正規インストールが要る。**ユーザの判断を仰ぐ**（本セッションではスクリプトを変更していない）。
- **NCCL ハングの枚数・モデル依存性**。aws-gpu01 の 2 枚 1/12・7 枚 0/13 に対し、本機の 4 枚は 3/3。**同一機で枚数だけを振れば（t120h-p100 で 2 枚 / 3 枚 / 4 枚）、枚数依存かどうかを安価に確かめられる**。上流報告の材料としても価値がある。
- **ctx=262144 までのラダー**。モデル側の上限は 262144 で、VRAM にも余裕がある。**tensor の「深さに強い」性質がどこまで続くか**は、交差点の話と合わせて運用判断に効く。
- **MTP 版での再測定**。サーバには `unsloth/Qwen3.6-35B-A3B-MTP-GGUF`（22,853,663,008 B）も既にある。手本の[3 腕再測定レポート](./2026-09-16_103619_aws_gpu01_split_mode_mtp_3arm.md)は「**tensor 分割では投機の採択率が明確に下がる**」という未解明の現象を報告しており、MoE でも同じかを確かめられる。
- **電源とロック**: 本レポート作成時点で t120h-p100 は**通電中・ロック保持中**。ユーザの指示を得てから `power.sh t120h-p100 off` で停止し `unlock.sh` する。

## 参照レポート

- [P100 4 枚でも dense 27B なら tensor 分割が全面的に勝つ](./2026-09-18_131856_t120h_p100_split_mode_qwen38_27b.md) — 本レポートの残課題「同じ t120h-p100 で Qwen3.8-27B を測り機種要因とモデル要因を分離する」を実施した続編。同一機・同一バイナリで dense に戻すと tensor が全面勝ちに戻り、**本レポートの優劣反転の主因はモデル型（MoE）と判明した**
- [P100 7 枚では tensor 分割が layer 分割を全面的に上回る](./2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor.md) — 本レポートが再現を試みた手本。その残課題「他サーバ・MoE での再測定」に本レポートが答え、**結論が条件依存であることを示した**
- [tensor 分割と MTP は両立するが回避策が prefill を 7 割奪う](./2026-09-16_103619_aws_gpu01_split_mode_mtp_3arm.md) — NCCL 経路と butterfly 経路のコスト差（decode -25% / prefill -78%）の出所。本レポートが NCCL を導入した理由
- [tensor 分割の起動ハングは MTP ではなく NCCL が原因](./2026-09-14_142115_aws_gpu01_tensor_split_nccl_hang.md) — 7 枚で 0/13 のハング。本レポートの 4 枚 3/3 と対照的
- [デフォルトLLMをQwen3.6-35B-A3Bに切り替え](./2026-05-21_043823_default_llm_qwen36_35b.md) — 本計測に使ったモデルが既定になった経緯
- [Phase T-2: split-mode row vs layer 比較](./2026-04-22_165843_qwen3-122b-c3-phaseT2-splitmode.md) — 同一機での先行 split-mode 比較（`row` は上流で deprecated、当時 `tensor` は未評価）
- [llama.cpp OOM リグレッションと ub の経緯](./2026-06-03_063647_llama_cpp_oom_regression_fix.md) — `start.sh` が `-ub 4096` を使う理由。本計測が `-ub 512` を選んだ判断の背景
