# P100 7 枚では tensor 分割が layer 分割を全面的に上回る

- **実施日時**: 2026年9月14日 09:15 〜 11:05 JST (llama-split-bench の初回導入・aws-gpu01 単体での電源投入・モデル取得・スモーク・3 モード本計測 64 分・結果回収とレポート作成)
- **報告日時**: 2026年9月14日 11:05 JST
- **作成者**: Claude Opus 5 (1M context)

## 概要

> **【2026-09-14 14:34 JST 追記】本レポートの結論（tensor 分割が layer 分割を上回る）は覆っていない。
> ただし `--split-mode tensor` には、起動が確率的に失敗する不具合があることが後日判明した。**
> 既定の NCCL AllReduce を使うと、起動直後の最初の GPU 実行で高確率（本計測では 15 回中 14 回）固まる。
> 本レポートの tensor 腕は**起動に成功した 1 回**の上で測定されている（起動さえ抜ければ以後は安定し、実際 20 分以上完走している）ため、
> **測定値そのものは有効**である。ただし tensor 分割を運用の既定にするなら、
> `GGML_CUDA_ALLREDUCE=butterfly` を併せて設定すること。詳細は[原因調査レポート](./2026-09-14_142115_aws_gpu01_tensor_split_nccl_hang.md)。

複数の GPU に大きなモデルを分けて載せるとき、llama.cpp には分け方が二通りある。ひとつは層ごとに担当を割り振る方式で、これが既定であり、本プロジェクトの起動スクリプトも固定でこれを使ってきた。もうひとつは一つの層の計算そのものを全カードで分担する方式である。どちらが速いかは機械ごとに違うはずだが、これまで本環境で正面から測ったことはなかった。今回、その比較を専門に行う外部ツールを導入し、初めて実測した。

対象にしたのは 16 GB のカードを 7 枚積んだ機械である。本来この機械は二台一組で動かす前提だが、相方が先週メモリ故障で起動しなくなっており、既定の大きなモデルは載せられない。そこでユーザの判断で単体運用とし、手持ちのモデルを確認したところ、単体の容量に収まるものが実質なかったため、27B 級のモデルを新たに取得して臨んだ。取得は同一拠点の利点がそのまま出て、三分足らずで終わった。

測定は、プロンプトを段階的に伸ばしながら各深さでの読み込み速度と生成速度を記録するという方式で、最深部はおよそ 13 万トークンに達する。比較の腕は三本用意した。7 枚での層分割、7 枚での分担分割、そして「枚数を増やすこと自体の効果」を測るための 2 枚での層分割である。単一カードでの基準は、モデルの重みが一枚に収まらなかったため断念し、代わりに 2 枚構成を基準に据えた。

結果は一方的だった。分担分割があらゆる深さ、あらゆる指標で層分割を上回った。とくに差が大きかったのは生成速度で、浅いところでは六割ほどの差だったものが、最深部では三倍近くまで開いた。理由は明快で、層分割は各カードが順番待ちをするため、七枚あっても実際に働いているのは三割弱の時間しかない。分担分割では同じ場面で四分の三以上が稼働していた。

さらに踏み込んだ発見がある。層分割のまま枚数を 2 枚から 7 枚に増やしても、生成速度はまったく改善しないどころか、わずかに悪化した。増えるのは読み込み速度だけである。つまり層分割で枚数を増やす行為は、速度ではなく容量を買っているにすぎないという、ツール作者が別の機械で得た結論が、まったく違う世代・違う構成の本環境でも再現したことになる。

温度と消費電力も記録したが、どちらも余裕があり、今回の差が熱や電力の制限によるものではないことを確認している。生成物と正確な起動引数、実行したバイナリの指紋も一式残してあるので、後から第三者が検証できる。

運用上の含意としては、起動スクリプトが既定で層分割に固定している点を見直す余地がある。ただし今回測ったのは特定の一モデル・特定の量子化・カード間が高速リンクで結ばれていない構成での話なので、構成の異なる他の機械にそのまま持ち込めるとは限らない。相方の機械が直り二台構成に戻ったとき、既定の大きなモデルで同じ比較をやり直すことを次の課題として残す。

なお副次的に、取得したモデルには使われていない追加ヘッドが含まれていることがログから判明した。これを有効にすると生成がさらに速くなる可能性があるが、今回は比較の純度を保つため無効のまま測っている。

## 添付ファイル

- [実装プラン](attachment/2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor/plan.md)
- [計測結果一式](attachment/2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor/run/) — `run-info.json`（バイナリ sha256・モード表・KV 型）、モード別の `results-*.json` / `results-*-pp0.json`、`results-real.json`、`argv-*.txt`（正確な server argv）、`server-*.log`、`sampler-*.log`（2 秒間隔の温度・電力・利用率）、`responses-*/`（各段の生成物と送信プロンプト）
- 図: [日本語版](attachment/2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor/run/split-bench-ja.png) ／ [英語版](attachment/2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor/run/split-bench-en.png)

## 核心発見サマリ

![aws-gpu01 の Tesla P100 7 枚で測った layer 分割 / tensor 分割 / 2 枚 layer の比較。①prefill は tensor が全深度で上回り、深さ 0 の新規 512 トークンでは 384.4 対 130.6 t/s と約 3 倍。②decode は tensor が深さ 13 万トークンでも 17.61 t/s とほぼ落ちないのに対し layer は 11.26 から 6.23 へ半減。③相対差は decode で +63% から +183% へ深さとともに拡大。④2 枚 layer を基準にすると、7 枚 layer の decode は全深度で基準を下回る（-4〜-7%）一方、7 枚 tensor は +51〜+168%](attachment/2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor/run/split-bench-ja.png)

**結論**: **Tesla P100 16GB ×7（sm_60、PCIe、NVLink なし）+ Qwen3.8-27B UD-Q4_K_XL + KV q8_0 + `-fa on` の条件で、`--split-mode tensor` が prefill / decode の全深度・全指標で `--split-mode layer` を上回った**。decode の差は **深さ 11 tok で +63%（18.34 対 11.26 t/s）、深さ 128,793 tok で +183%（17.61 対 6.23 t/s）** と深さとともに拡大する。**tensor の decode は深さ 128,793 tok でも初段比 96.0% を維持**（18.34 → 17.61）するのに対し、**layer は 55.3% まで落ちる**（11.26 → 6.23）。prefill は新規プロンプトで差が最大になり、**pp512 で +194%（384.4 対 130.6 t/s）**、pp2048 で +88%、pp8192 で +27%、ラダー深部では +10〜+22% に収束する。**さらに決定的なのはパネル④で、layer 分割のまま 2 枚 → 7 枚に増やしても decode は改善せず全深度で -4〜-7% と微減する**（例: 深さ 32,458 tok で 2 枚 10.25 t/s に対し 7 枚 9.79 t/s）。増えるのは prefill だけ（同深度 +105%）で、**「layer 分割は速度ではなく VRAM を買う」というツール作者の結論（2×V100, sm_70）が、sm_60 / 7-way という別条件で再現した**。原因は GPU 利用率に表れており、**サンプラ平均で layer 27.5% に対し tensor 75.9%**（2 枚 layer は 18.2%）。温度は最大 67〜71℃、電力平均 58〜97 W（TDP 250 W）で**熱・電力律速ではない**。証跡: バイナリ `ca54f4dd8a4750198b85ebf4bd195c580c77bc98bf1b772388581c1cd8593886`（llama.cpp master `465e49b9c`, build 10830）。

## 前提・目的

- **背景**: `src/llama-split-bench/` は 2026-09-14 に外部リポジトリ（[kuraneko1/llama-split-bench](https://github.com/kuraneko1/llama-split-bench)）からクローンされたばかりで、本プロジェクトでは未実行だった（`report/` に言及ゼロ、`runs/` も `bench.local.conf` も未作成）。
- **目的**: aws-gpu01 単体で本ツールを実行し、`--split-mode layer`（既定）と `--split-mode tensor` のどちらが速いかを実測する。本プロジェクトの `start.sh:215` は `--split-mode layer` を固定で使っており、その既定値を実測で再検証する。
- **単体運用の理由**: aws-gpu02 が 2026-09-10 に `P1_DIMMA2` の新規故障で POST を通過しなくなり、既定の RPC 分散構成（13 GPU / 200 GiB）が使えない。aws-gpu01 単体（112 GiB）は SKILL.md 上「未検証」の構成であり、本計測はその構成の初回データでもある。
- **ツール側の未検証領域**: 作者は README で「E2E 実走は Linux + CUDA（sm70、V100×2）のみ。TP=3 以上は同一コード経路だが未検証」と明記している。**本計測は本ツールにとって初の 7-way（TP=7）ケース**にあたる。
- **電源投入**: aws-gpu01 / aws-gpu02 とも電源 OFF だったため、ファン爆音の制約に従い**ユーザの明示的な許可を得て aws-gpu01 のみ投入**した（aws-gpu02 には一切触れていない）。

## 環境情報

| 項目 | 値 |
|---|---|
| サーバ | aws-gpu01 (10.8.2.1)、Supermicro SYS-4028GR-TRT2 |
| GPU | Tesla P100-PCIE-16GB × 7（sm_60 / compute cap 6.0）、PCIe 接続・**NVLink なし**。BDF `05/07/08/0C/0D/0E/0F:00.0` |
| CPU / RAM | 48 コア / 157 GiB |
| llama.cpp | master `465e49b9c`、build 10830、`built with GNU 13.3.0`。`tools/server/server-http.cpp` に `--ui-mcp-proxy` 404 修正パッチ（前回セッションからの無変更） |
| バイナリ sha256 | `ca54f4dd8a4750198b85ebf4bd195c580c77bc98bf1b772388581c1cd8593886` |
| モデル | `Qwen3.8-27B-UD-Q4_K_XL.gguf`（`unsloth/Qwen3.8-27B-GGUF`、**17,559,178,144 B = 16.35 GiB**、dense 27B、本計測のために新規取得） |
| KV キャッシュ | `--cache-type-k q8_0 --cache-type-v q8_0` |
| 共通起動引数 | `-ngl all -fa on -c 131072 --parallel 1 -t 16 --jinja --cache-ram 8192 --cache-idle-slots --cache-reuse 256` |
| 投機デコード | **無効**（`SPEC_ARGS=""`。既定の `--spec-type draft-mtp` を外した） |
| ベンチツール | llama-split-bench（`~/llama-split-bench`、`bench.local.conf` は本レポートの「再現方法」参照） |
| 計測モード | `layer`（CUDA0-6 / layer）、`tensor`（CUDA0-6 / tensor）、`layer2`（CUDA0,CUDA1 / layer、ベースライン） |
| ワークロード | ctx=131072、ステージ `0,16000,32000,64000,128000`、各段 1000 tok 生成、pp0 サイズ 512/2048/8192 |
| 所要 | layer 19分01秒（09:44:58→10:03:59）／ tensor 16分25秒（→10:20:24、実プロンプト補正を含む）／ layer2 28分24秒（→10:48:48）。**合計 63分50秒** |

**`single` ベースラインを断念した理由**: 重み 16.35 GiB は 1 枚の空き 15.6 GiB に収まらない。代わりに **2 枚 layer（`layer2`）をベースライン**に据えた（`BASELINE=layer2`）。図のパネル④はこの 2 枚構成を基準とした伸び率を示す。

## 再現方法

```bash
# 1) ロック取得 → 電源投入（爆音のためユーザの明示的許可が要る）
.claude/skills/gpu-server/scripts/lock.sh aws-gpu01
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 on

# 2) モデル取得（同一拠点なのでサーバから HF 直。実測 2分35秒 / 約108 MB/s）
source ~/.config/gpu-server/.env
ssh -n aws-gpu01 "setsid nohup env HF_TOKEN='$HF_TOKEN' HF_HUB_ENABLE_HF_TRANSFER=1 \
  ~/.local/bin/hf download unsloth/Qwen3.8-27B-GGUF --include 'Qwen3.8-27B-UD-Q4_K_XL.gguf' \
  --local-dir ~/models/Qwen3.8-27B-GGUF > /tmp/hfdl.log 2>&1 < /dev/null &"

# 3) ツール転送 + 作図 venv + 日本語フォント（sudo 不要）
rsync -a --exclude .git --exclude runs src/llama-split-bench/ aws-gpu01:~/llama-split-bench/
ssh -n aws-gpu01 "python3 -m venv ~/.venvs/bench-plot && ~/.venvs/bench-plot/bin/pip install matplotlib"
ssh -n aws-gpu01 "mkdir -p ~/.fonts && curl -sL -o ~/.fonts/NotoSansCJKjp-Regular.otf \
  'https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf' \
  && fc-cache -f ~/.fonts && rm -rf ~/.cache/matplotlib"

# 4) スモーク（約4分）
ssh -n aws-gpu01 "cd ~/llama-split-bench && bash run-bench.sh smoke --modes layer,tensor \
  --stages 0,4000 --n-predict 100 --ctx 8192 --pp0-sizes 512,2048 --no-real"

# 5) 本計測（detached。tail -f は使わずマーカーをポーリング）
ssh -n aws-gpu01 "cd ~/llama-split-bench && \
  setsid nohup bash run-bench.sh gpu01-7way-1 > runs/gpu01-7way-1.log 2>&1 < /dev/null &"
ssh -n aws-gpu01 'until grep -qE "BENCH-(DONE|ABORT|FIGFAIL)" ~/llama-split-bench/runs/gpu01-7way-1.log; do sleep 60; done'
```

`~/llama-split-bench/bench.local.conf`:

```bash
BIN=$HOME/llama.cpp/build/bin/llama-server
MODEL=$HOME/models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf
DEVICES=CUDA0,CUDA1,CUDA2,CUDA3,CUDA4,CUDA5,CUDA6
MODES=( "layer|CUDA0,CUDA1,CUDA2,CUDA3,CUDA4,CUDA5,CUDA6|layer" \
        "tensor|CUDA0,CUDA1,CUDA2,CUDA3,CUDA4,CUDA5,CUDA6|tensor" \
        "layer2|CUDA0,CUDA1|layer" )
BASELINE=layer2
CTX=131072
STAGES=0,16000,32000,64000,128000
N_PREDICT=1000
PP0_SIZES=512,2048,8192
THREADS=16
SPEC_ARGS=""          # Qwen3.8-27B (non-MTP) — draft-mtp を外す
VENV_PY=$HOME/.venvs/bench-plot/bin/python
MACHINE="aws-gpu01 - Tesla P100-PCIE-16GB x7 (sm_60, PCIe, no NVLink)"
```

## 結果詳細

### 1. decode（生成速度、t/s）— tensor は深さでほぼ落ちない

| 実効深さ (tok) | layer (7枚) | tensor (7枚) | layer2 (2枚) | tensor / layer | layer(7) / layer2(2) |
|---:|---:|---:|---:|---:|---:|
| 11 | 11.26 | **18.34** | 12.11 | **+63%** | **-7%** |
| 15,825 | 10.38 | **18.17** | 11.15 | **+75%** | **-7%** |
| 32,458 | 9.79 | **18.09** | 10.25 | **+85%** | **-4%** |
| 64,785 | 8.29 | **17.86** | 8.71 | **+115%** | **-5%** |
| 128,793 | 6.23 | **17.61** | 6.57 | **+183%** | **-5%** |
| **初段比の維持率** | **55.3%** | **96.0%** | 54.3% | — | — |

**tensor の decode は 13 万トークンの深さでも 17.61 t/s を保ち、初段 18.34 t/s から 4.0% しか落ちない**。layer は 44.7% 落ちる。この「深さに対する平坦さ」が両者の最大の違いである。

**layer 分割で枚数を増やしても decode は改善しない**（右端列）。2 枚 → 7 枚で全深度 -4〜-7%。パイプライン段数が増えるぶん、わずかに不利になる。

### 2. prefill（増分プロンプト評価速度、t/s）

| 実効深さ (tok) | layer (7枚) | tensor (7枚) | layer2 (2枚) | tensor / layer | layer(7) / layer2(2) |
|---:|---:|---:|---:|---:|---:|
| 11 | 18.9 | 21.3 | 26.8 | — ※ | — ※ |
| 15,825 | 349.5 | **427.4** | 181.6 | +22% | +92% |
| 32,458 | 326.2 | **379.4** | 159.3 | +16% | +105% |
| 64,785 | 290.5 | **324.5** | 134.7 | +12% | +116% |
| 128,793 | 229.1 | **251.4** | 102.7 | +10% | +123% |

※ ラダー初段は 11 トークンのプロンプトなので計測上のアーティファクトであり、作図にも使われない（README 記載の仕様）。深さ 0 の正しい prefill は次表。

**prefill については layer 分割で枚数を増やす効果が明確にある**（2 枚 → 7 枚で +92〜+123%）。tensor との差は深部ほど縮む（+22% → +10%）。

### 3. depth-0 prefill（新規プロンプト、`cache_prompt=false`）— 小バッチで差が最大

| サイズ | layer (7枚) | tensor (7枚) | layer2 (2枚) | tensor / layer |
|---|---:|---:|---:|---:|
| pp512 | 130.6 | **384.4** | 134.3 | **+194%** |
| pp2048 | 224.8 | **423.6** | 171.4 | **+88%** |
| pp8192 | 346.2 | **438.7** | 186.2 | **+27%** |

**512 トークンの短いプロンプトでは layer 分割の 7 枚が 2 枚（134.3 t/s）とほぼ同じ 130.6 t/s しか出ない**。バッチが小さいうちはパイプラインが埋まらず、枚数がまったく効かない。tensor は同条件で 384.4 t/s を出す。エージェント用途のように短いリクエストが多い場面では、この差がそのまま応答遅延に効く。

### 4. GPU 利用率・温度・電力（`sampler-*.log`、2 秒間隔）

| モード | 利用率 平均 | 温度 最大 / 平均 | 電力 最大 / 平均 |
|---|---:|---:|---:|
| layer (7枚) | **27.5%** | 67℃ / 57.5℃ | 212 W / 77 W |
| tensor (7枚) | **75.9%** | 67℃ / 60.6℃ | 213 W / 97 W |
| layer2 (2枚) | 18.2% | 71℃ / 49.4℃ | 216 W / 58 W |

**layer 分割では 7 枚の平均利用率が 27.5% にとどまる**。順番待ちが支配的で、7 枚のうち実質 2 枚分しか働いていない計算になる。tensor では 75.9% まで上がる。これが decode 差の直接の説明になっている。

温度は最大でも 71℃、電力平均は TDP 250 W に対し 58〜97 W であり、**熱による絞りや電力上限が今回の差を作っているのではない**ことを確認した。

### 5. 実プロンプト補正

`results-real.json`（日本語実務風プロンプト 3 本、temp 0.7 / top_p 0.9 / n_predict 1200、tensor モードで実行）の decode は 18.22 / 18.21 / 18.2 t/s で、合成テキストのラダー初段 18.34 t/s に対し **補正係数 0.993**。投機デコードを無効にしているため合成と実運用の差がほぼ無く、**本レポートの decode 値はそのまま実運用値として読める**（図の薄い破線が実線とほぼ重なっているのはこのため）。

## 副次発見

1. **取得した GGUF には MTP（NextN）ヘッドが含まれている**。`server-tensor.log` に `model has unused tensor blk.64.nextn.eh_proj.weight ... -- ignoring` 等が出ており、`blk.64` 一式（`attn_*`, `ffn_*`, `nextn.*`）が未使用として読み飛ばされている。`--spec-type draft-mtp` を付ければ self-speculative decoding が使える可能性があるが、**今回は layer / tensor 比較の純度を保つため無効のまま計測した**。
2. **ラダー初段（11 トークン）の prefill は 2 枚構成が最も速い**（26.8 > 21.3 > 18.9 t/s）。分割数が増えるほど固定オーバーヘッドが乗ることを示すが、これは作図から除外される仕様の値である。
3. **aws-gpu01 単体運用（SKILL.md 上「未検証」）は問題なく動いた**。7 枚すべてが `llama.cpp` から `CUDA0..CUDA6`（各 16,020 MiB free）として見え、ctx=131072 の 2 枚構成でも GPU0 10.9 GiB + GPU1 12.2 GiB と余裕があった。
4. **llama-split-bench の TP≥3 経路は 7-way で問題なく動作した**（作者未検証領域）。外部プロセスガード（`guarding GPU indices ['0'..'6']`）、サンプラ、同一タグ拒否、完了マーカーいずれも期待どおり機能した。
5. **日本語図は `~/.fonts` への Noto Sans CJK JP 配置で sudo なしに解決できる**。`plot_bench.py:102` が `font.family = ["Noto Sans CJK JP"]` を固定で要求するため、未導入だと日本語版 PNG が豆腐になる（スモーク時に `findfont: Font family 'Noto Sans CJK JP' not found.` が多発した）。`fc-cache -f ~/.fonts` の後に `rm -rf ~/.cache/matplotlib` が要る。
6. **`pkill -f <パターン>` はリモート実行でも自殺する**。`ssh aws-gpu01 "pkill -f 'port 18099'"` がリモート側の bash 自身にマッチして exit 255 になった。`pkill -x llama-server`（プロセス名の完全一致）なら安全。

## 残課題

- **`start.sh` の `--split-mode layer` 固定の見直し**。少なくとも aws-gpu01 のような多数枚・NVLink なし構成では tensor が全面的に有利である。ただし今回の結果は **dense 27B / UD-Q4_K_XL / KV q8_0 / sm_60 / PCIe** という一点の測定であり、他サーバ（mi25 の Vulkan、t120h-p100 の 4 枚、t120h-m10 の 15 枚）や MoE モデルでの再測定なしに既定値を変えるべきではない。
- **MoE モデルでの layer vs tensor**。既定モデル（DeepSeek-V4-Flash 系）は MoE であり、エキスパート重みの分割は dense とは挙動が異なりうる。aws-gpu02 の `P1_DIMMA2` を物理抜去して RPC 分散が復旧したら、13 GPU 構成で同じ比較を行う価値がある（ただし RPC バックエンドを跨いだ `--split-mode tensor` が成立するかは未確認）。
- **MTP を有効にした再測定**。副次発見 1 のとおりモデル側にヘッドがあるため、`SPEC_ARGS` を既定に戻した腕を追加すれば、投機デコード込みの実力が測れる（本ツールは採択率も記録する）。
- **`--tensor-split` による不均等配分**。今回は自動配分（`TENSOR_SPLIT` 空）。7 枚均等なので必要性は低いが、aws-gpu02 の 12 GB 混在構成では効いてくる。
- **ツール作者への報告素材**。TP=7 / sm_60 での初の E2E 実走データであり、作者が README で「未検証」としている領域を埋める。投稿する場合は AI に投稿文を書かせない運用（[llama.cpp #27773 の事例](./2026-09-06_234319_glm53flash_pr27773_vs_27754_depth.md)）に従い、素材の提示に留める。
- **電源とロック**: 本レポート作成時点で aws-gpu01 は通電中・ロック保持中。ユーザの指示を得てから `bmc-power.sh aws-gpu01 soft` で停止し `unlock.sh` する。

## 参照レポート

- [aws-gpu02 が別の DIMM 故障で起動しなくなり実機検証が中断](./2026-09-11_055337_aws_gpu02_dimma2_failure_glm53flash_upstream.md) — 単体運用に至った背景（`P1_DIMMA2` の新規故障）
- [aws-gpu02 の uncorrectable ECC](./2026-09-05_221831_aws_gpu02_uncorrectable_ecc.md) — 先行する `P2_DIMME1` 故障と `Patrol Scrub` 回避策
- [Qwen3.5-122B Phase T-2 split-mode 比較](./2026-04-22_165843_qwen3-122b-c3-phaseT2-splitmode.md) — 本プロジェクトで唯一の先行する split-mode 比較（`row` vs `layer`、t120h-p100 4 枚。当時 `tensor` は未評価）
- [GLM-5.3-Flash の 2 つの PR を深さで比較](./2026-09-06_234319_glm53flash_pr27773_vs_27754_depth.md) — 深度ラダー方式による比較の先行例
