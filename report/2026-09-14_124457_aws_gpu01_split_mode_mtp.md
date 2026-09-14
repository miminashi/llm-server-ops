# MTP は layer 分割を大きく速くするが tensor 分割とは併用できない

- **実施日時**: 2026年9月14日 11:05 〜 12:50 JST (MTP 有効化の可否判定・tensor 併用ハングの切り分け・2 腕での本計測 50 分・比較図作成とレポート)
- **報告日時**: 2026年9月14日 12:50 JST
- **作成者**: Claude Opus 5 (1M context)

## 概要

同じ日の午前に、カードを 7 枚積んだ機械で大きなモデルを分けて載せる二つのやり方を比較し、一つの層の計算を全カードで分担するやり方が、層ごとに担当を割り振るやり方をあらゆる場面で上回るという結果を得た。ただしその測定では、モデルが自分の次の単語を先読みして生成を加速する仕組みを、比較の純度を保つためにわざと切ってあった。今回はその仕組みを入れ直して測り直した。前回の宿題にあたる。

まず最初に分かったのは、その先読み機構と分担分割は同時に使えないということだった。両方を有効にすると、モデルの読み込みは終わるのに初期化がそこで止まり、カードが全部 100% で回りっぱなしのまま前に進まなくなる。7 枚でも 2 枚でも同じで、片方だけなら何の問題もなく動く。つまり組み合わせ固有の不具合である。このため、今回の測定では分担分割の腕を取ることができず、層分割の 7 枚構成と 2 枚構成の二本で行った。

測定そのものの結果は劇的だった。先読みを有効にすると、層分割の生成速度は浅いところで七割強、深いところでは二倍以上に跳ね上がった。数字だけ見れば、午前に測った分担分割の速度すら浅いところでは追い抜いている。

ところがこれには落とし穴がある。この測定に使う合成テキストは繰り返しが多く、先読みがほぼ確実に当たってしまう。実際に採択率は九割七分から十割で張り付いていた。同じ機構で日本語の実務的な文章を生成させると、採択率は六割弱まで落ちる。ツールはこの差を補正する係数を自動で出すようになっており、今回それは約 0.76 だった。補正をかけた実運用相当の値で見直すと、層分割の改善幅は三割から六割程度に縮み、しかも全ての深さで分担分割（先読みなし）に届かない。差は深いところほど開き、最も深いところでは分担分割のほうが七割速い。

もうひとつ副作用がある。先読みを有効にするとプロンプトの読み込み速度が落ちる。7 枚構成では三割以上、2 枚構成でも一割ほど遅くなった。生成が速くなるぶん読み込みが遅くなるという交換になっており、長い文章を読ませてから短く答えさせる用途では割に合わない可能性がある。

前回見つけた「層分割で枚数を増やしても生成は速くならない」という性質は、先読みを有効にしても変わらなかった。7 枚のほうが 2 枚より全ての深さで数%遅い。枚数を増やして買えるのは容量であって速度ではない、という結論は先読み込みでも成り立つ。

運用上の結論としては、この機械・このモデルでは分担分割を先読みなしで使うのが最良で、午前のレポートの推奨は変わらない。先読みが生きるのは、分担分割が使えない場面（たとえば分担分割に未対応のバックエンドや、今回のような併用不具合が直るまでの間）に限られる。なお併用時のハングは上流に報告する価値があるが、投稿文は人間が書く運用に従うため、ここでは素材の提示に留める。

## 添付ファイル

- [実装プラン](attachment/2026-09-14_124457_aws_gpu01_split_mode_mtp/plan.md)
- [計測結果一式](attachment/2026-09-14_124457_aws_gpu01_split_mode_mtp/run/) — `run-info.json`（バイナリ sha256・モード表・KV 型）、モード別の `results-*.json` / `results-*-pp0.json`、`results-real.json`、`argv-*.txt`（正確な server argv）、`server-*.log`、`sampler-*.log`（2 秒間隔の温度・電力・利用率）、`responses-*/`（各段の生成物と送信プロンプト）
- [今回の `bench.local.conf`](attachment/2026-09-14_124457_aws_gpu01_split_mode_mtp/bench.local.conf) — 前回との差分は `SPEC_ARGS` の 1 行のみ
- [比較図の生成スクリプト](attachment/2026-09-14_124457_aws_gpu01_split_mode_mtp/plot_mtp.py)
- 図（MTP on/off 比較、本レポート用に追加作成）: [日本語版](attachment/2026-09-14_124457_aws_gpu01_split_mode_mtp/run/mtp-compare-ja.png) ／ [英語版](attachment/2026-09-14_124457_aws_gpu01_split_mode_mtp/run/mtp-compare-en.png)
- 図（ツール標準出力、今回の 2 腕のみ）: [日本語版](attachment/2026-09-14_124457_aws_gpu01_split_mode_mtp/run/split-bench-ja.png) ／ [英語版](attachment/2026-09-14_124457_aws_gpu01_split_mode_mtp/run/split-bench-en.png)

## 核心発見サマリ

![aws-gpu01 の Tesla P100 7 枚で測った MTP on/off の比較。①decode は MTP 有効で layer 7枚が 11.26→19.59 t/s、layer 2枚が 12.11→21.26 t/s に跳ね上がるが、実運用補正（×0.761）の細い点線で見ると全深度で tensor（MTP 無効、赤破線 18.34→17.61 t/s）に届かない。②伸び率は合成テキストで +74〜+107%、実運用補正後で +32〜+58%。③prefill は MTP で layer 7枚が -31〜-37%、layer 2枚が -10〜-11% 劣化する。④合成テキストの採択率は 97〜100% だが実プロンプトでは平均 61%](attachment/2026-09-14_124457_aws_gpu01_split_mode_mtp/run/mtp-compare-ja.png)

**結論**: **`--spec-type draft-mtp` と `--split-mode tensor` は併用できない**。両方を有効にすると `llama threadpool init` の直後で初期化が停止し、**使用中の全 GPU が 100% 利用率のまま進まない**（7 枚で 12 分、2 枚で 8 分待って打ち切り。単独ではどちらも正常）。したがって前回勝者の tensor 腕は MTP 有効では取得不能で、本計測は `layer`（7 枚）と `layer2`（2 枚）の 2 腕。**MTP 有効化で decode は合成テキスト実測で layer 7枚 +74〜+103%、layer 2枚 +76〜+107%**（深さ 128,793 tok で 6.23→12.68 / 6.57→13.62 t/s）と大幅に伸び、**浅い深度では MTP 有効な layer が MTP 無効の tensor すら上回る**（深さ 11 tok で layer2 21.26 対 tensor 18.34 = +16%）。**ただしこれは合成テキストの採択率が 0.968〜1.000 と楽観側に張り付いた値である**。同一構成・実プロンプト 3 本での採択率は **0.574 / 0.590 / 0.672（平均 61%）**、`tokens_per_cycle` 1.076〜1.173 で、ツールの**実運用補正係数は 0.761**。補正後の decode は layer 7枚 14.91→9.65 t/s、layer 2枚 16.19→10.37 t/s となり、**全深度で tensor（MTP 無効、18.34→17.61 t/s）に届かない**（tensor が +13%〜+70% 優位、深いほど開く）。副作用として **MTP は prefill を劣化させる**（ラダー深部で layer 7枚 -31〜-37%、layer 2枚 -10〜-11%、pp8192 で -26% / -9%）。**「layer 分割は枚数を増やしても decode が速くならない」という前回結論は MTP 有効でも再現**し、7枚は 2枚に対し全深度 -4〜-8%。VRAM は MTP 第 2 コンテキストぶん **+1.83 GiB**（ほぼ全量が最終デバイスに集中）。証跡: バイナリ `ca54f4dd8a4750198b85ebf4bd195c580c77bc98bf1b772388581c1cd8593886`（前回と同一、llama.cpp master `465e49b9c`, build 10830）、`argv-*.txt` の差分は spec 関連 3 フラグのみ。

## 前提・目的

- **背景**: [2026-09-14 の layer vs tensor 実測](./2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor.md)は、比較の純度を保つため **投機デコードを無効（`SPEC_ARGS=""`）** にして行った。同レポートの副次発見 1 と残課題に「取得した GGUF に MTP（NextN）ヘッドがあるので有効化して再測定する」と記録されている。
- **目的**: `SPEC_ARGS` **だけ**を既定（`--spec-type draft-mtp --spec-draft-n-max 2`）に戻し、他のすべて（バイナリ・モデル・ワークロード・KV 型・スレッド数・ctx）を前回と一字一句同じに保って再測定する。これにより前回値との厳密な A/B が成立する。
- **モデル側の MTP 対応の確認**: GGUF メタデータに `qwen35.nextn_predict_layers` が存在し、arch は `qwen35`。前回のサーバログでは `blk.64.nextn.*` が `unused tensor ... -- ignoring` として読み飛ばされていた。
- **llama.cpp 側の実装**: MTP は別のドラフトモデルを読むのではなく、**ターゲットモデルに対して `LLAMA_CONTEXT_TYPE_MTP` の第 2 コンテキストを張る**（`common/speculative.cpp` の `spec_mtp` 分岐）。`hparams.n_layer_nextn == 0` の場合は `llama-context.cpp` が警告を出して nullptr を返す。`--spec-draft-device` はこの経路では `mparams` を使わないため実質無効。

## 環境情報

| 項目 | 値 |
|---|---|
| サーバ | aws-gpu01 (10.8.2.1)、Supermicro SYS-4028GR-TRT2 |
| GPU | Tesla P100-PCIE-16GB × 7（sm_60）、PCIe 接続・**NVLink なし** |
| llama.cpp | master `465e49b9c`、build 10830（**前回と同一バイナリ**） |
| バイナリ sha256 | `ca54f4dd8a4750198b85ebf4bd195c580c77bc98bf1b772388581c1cd8593886` |
| モデル | `Qwen3.8-27B-UD-Q4_K_XL.gguf`（arch `qwen35`、17,559,178,144 B = 16.35 GiB、MTP ヘッド `blk.64` 同梱） |
| KV キャッシュ | `--cache-type-k q8_0 --cache-type-v q8_0` |
| 共通起動引数 | `-ngl all -fa on -c 131072 --parallel 1 -t 16 --jinja --cache-ram 8192 --cache-idle-slots --cache-reuse 256` |
| **投機デコード** | **`--spec-type draft-mtp --spec-draft-n-max 2`（今回の唯一の変更点）** |
| 計測モード | `layer`（CUDA0-6 / layer）、`layer2`（CUDA0,CUDA1 / layer、ベースライン）。**`tensor` は併用不可のため欠測** |
| ワークロード | ctx=131072、ステージ `0,16000,32000,64000,128000`、各段 1000 tok 生成、pp0 サイズ 512/2048/8192 |
| 所要 | layer 23分20秒（11:54:47→12:18:07）／ layer2 26分20秒（→12:44:27）。**合計 49分40秒** |
| 実プロンプト補正 | `REAL_MODE=auto` は tensor 腕を探すが今回は無いため **`layer` 腕で実行**（前回は tensor 腕だった） |

**`argv-*.txt` の差分**（前回 → 今回、両腕とも同一）:

```diff
+--spec-type
+draft-mtp
+--spec-draft-n-max
+2
+--spec-draft-device
+CUDA0,CUDA1,CUDA2,CUDA3,CUDA4,CUDA5,CUDA6   # layer2 腕は CUDA0,CUDA1
```

**VRAM（モデルロード直後、`nvidia-smi` の実測合計）**:

| 構成 | MTP 無効 | MTP 有効 | 増分 | 増分の所在 |
|---|---:|---:|---:|---|
| layer 7枚 | 30,238 MiB | 32,108 MiB | **+1,870 MiB** | CUDA6 が 4,866 → 6,466 MiB（+1,600） |
| layer 2枚 | 23,084 MiB | 24,952 MiB | **+1,868 MiB** | CUDA1 が 12,182 → 13,894 MiB（+1,712） |

**MTP の追加 VRAM は約 1.83 GiB で、そのほぼ全量が最終デバイスに集中する。** 2 枚構成では CUDA1 が 13.9 GiB / 16 GiB まで埋まるため、これ以上 ctx を伸ばす余地は小さい。

## 再現方法

```bash
# 1) ロックは前セッションから継続保持（aws-gpu01 は通電中）
.claude/skills/gpu-server/scripts/lock-status.sh

# 2) MTP が有効になるかの最小確認（決定ゲート）
ssh -n -f aws-gpu01 "cd ~ && setsid nohup ~/llama.cpp/build/bin/llama-server \
  -m ~/models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf \
  --host 127.0.0.1 --port 18099 --device CUDA0,CUDA1 --split-mode layer \
  -ngl all -fa on -c 8192 --parallel 1 -t 16 --jinja \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --spec-type draft-mtp --spec-draft-n-max 2 > /tmp/mtp-probe.log 2>&1 < /dev/null &"
# 合格条件: 'creating MTP draft context' が出て 'nextn ... unused tensor' が出ないこと、
#           /completion の timings に draft_n > 0 / draft_n_accepted > 0 が入ること
# 停止は必ず pkill -x llama-server（pkill -f はリモート側 bash に自己マッチする）

# 3) bench.local.conf の SPEC_ARGS だけを差し替え（他は前回と同一に保つ）
ssh -n aws-gpu01 "cd ~/llama-split-bench && cp bench.local.conf bench.local.conf.nomtp-backup && \
  sed -i 's|^SPEC_ARGS=.*|SPEC_ARGS=\"--spec-type draft-mtp --spec-draft-n-max 2\"|' bench.local.conf"

# 4) 本計測（detached。tensor 腕はハングするため --modes で外す）
ssh -n aws-gpu01 "cd ~/llama-split-bench && \
  setsid nohup bash run-bench.sh gpu01-7way-mtp --modes layer,layer2 \
  > runs/gpu01-7way-mtp.log 2>&1 < /dev/null &"
ssh -n aws-gpu01 'until grep -qE "BENCH-(DONE|ABORT|FIGFAIL)" \
  ~/llama-split-bench/runs/gpu01-7way-mtp.log; do sleep 60; done'

# 5) MTP on/off 比較図（前回 run と突き合わせ。CJK フォントがあるサーバ側 venv で実行）
ssh -n aws-gpu01 "cd ~/llama-split-bench && ~/.venvs/bench-plot/bin/python plot_mtp.py \
  --off runs/gpu01-7way-1 --on runs/gpu01-7way-mtp --lang ja --out runs/gpu01-7way-mtp/mtp-compare-ja.png"
```

## 結果詳細

### 1. `--split-mode tensor` + MTP は初期化がハングする（最重要）

スモークの tensor 腕が `BENCH-ABORT: tensor server not ready` で落ちたため、手動で切り分けた。

| 構成 | MTP 無効 | MTP 有効 |
|---|---|---|
| `--split-mode layer`, 2 枚 | 正常（約 10 秒で `model loaded`） | **正常**（約 10 秒） |
| `--split-mode layer`, 7 枚 | 正常 | **正常** |
| `--split-mode tensor`, 2 枚 | 正常（前回実績） | **ハング**（7分41秒で打ち切り） |
| `--split-mode tensor`, 7 枚 | 正常（前回実績） | **ハング**（12分00秒で打ち切り） |

ハング時の挙動:

- サーバログは `llama threadpool init, n_threads = 16` で止まり、**`creating MTP draft context` にすら到達しない**（layer 腕ではこの直後に出る）
- プロセスは `R` 状態で **CPU 約 100%**、**使用中の GPU が全て利用率 100%**、VRAM は重みぶん（7 枚で各 2.9 GiB、計 20.4 GiB）確保済みのまま増えない
- 枚数に依存しない（2 枚でも 7 枚でも同じ）ので、**7-way 固有ではなく tensor 分割と MTP の組み合わせ固有**
- `ptrace_scope` によりバックトレースは取得できず（aws-gpu01 は sudo をユーザに依頼する運用のため深追いせず）

なお `--split-mode tensor` は MTP の有無にかかわらず起動時に
`common_fit_params: failed to fit params to free device memory: llama_params_fit is not implemented for SPLIT_MODE_TENSOR, abort`
を出すが、これは前回も出ていた無害な警告で、今回のハングとは別物である。

### 2. decode（生成速度、t/s）— 合成テキスト実測

| 実効深さ (tok) | layer 7枚 MTP off | layer 7枚 MTP on | 伸び | layer 2枚 MTP off | layer 2枚 MTP on | 伸び | tensor 7枚 MTP off |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 11 | 11.26 | **19.59** | +74% | 12.11 | **21.26** | +76% | 18.34 |
| 15,825 | 10.38 | **19.45** | +87% | 11.15 | **20.28** | +82% | 18.17 |
| 32,458 | 9.79 | **17.49** | +79% | 10.25 | **18.93** | +85% | 18.09 |
| 64,785 | 8.29 | **15.87** | +92% | 8.71 | **16.69** | +92% | 17.86 |
| 128,793 | 6.23 | **12.68** | +103% | 6.57 | **13.62** | +107% | 17.61 |
| **初段比の維持率** | 55.3% | **64.7%** | — | 54.2% | **64.1%** | — | **96.0%** |

**この表だけを見ると MTP 有効の layer が tensor を浅い深度で上回る**（深さ 11 tok で layer 2枚 21.26 対 tensor 18.34 = +16%、layer 7枚 19.59 = +6.8%）。交差点は 3〜4 万トークン付近で、それより深いと tensor が逆転する（深さ 128,793 tok で tensor は layer 2枚 MTP on の +29%）。

**ただしこの値は採択率が楽観側に張り付いた合成テキストのものである**（次節）。

### 3. 採択率と実運用補正 — 合成 0.97〜1.00 に対し実プロンプト 0.61

| 段（実効深さ） | `draft_n` | `draft_n_accepted` | 採択率 |
|---:|---:|---:|---:|
| 11 | 680 | 658 | 0.968 |
| 15,825 | 667 | 665 | 0.997 |
| 32,458 | 667 | 665 | 0.997 |
| 64,785 | 668 | 664 | 0.994 |
| 128,793 | 666 | 666 | **1.000** |

（layer / layer2 とも同一値。ラダーの合成フィラーは反復が多く、MTP がほぼ全部当てる）

`results-real.json`（日本語実務風プロンプト 3 本、temp 0.7 / top_p 0.9 / n_predict 1200、**layer 7枚**で実行）:

| プロンプト | decode (t/s) | prefill (t/s) | `draft_n` | 採択 | 採択率 | `tokens_per_cycle` |
|---|---:|---:|---:|---:|---:|---:|
| design | 14.78 | 45.7 | 1,115 | 640 | **0.574** | 1.076 |
| review | 14.45 | 46.7 | 1,100 | 649 | **0.590** | 1.091 |
| qa | 15.51 | 48.9 | 1,023 | 687 | **0.672** | 1.173 |
| 平均 | **14.91** | 47.1 | — | — | **0.612** | 1.113 |

**実運用補正係数 = 14.91 / 19.59 = 0.761**。前回（MTP 無効）の同係数は 0.993 で、投機デコードが無い以上ほぼ 1.0 になるのが当然だった。**今回初めてこの係数が意味を持つ。**

`tokens_per_cycle` が 1.08〜1.17 しかないのが本質で、`--spec-draft-n-max 2` に対して実際には 1 サイクルあたり 1.1 トークンしか進んでいない。合成テキストでは同じ指標が 2 に近づく。

### 4. decode（実運用補正後）— tensor（MTP 無効）に全深度で届かない

| 実効深さ (tok) | layer 7枚 MTP on（補正後） | 対 MTP off | layer 2枚 MTP on（補正後） | 対 MTP off | tensor 7枚 MTP off | tensor の優位 |
|---:|---:|---:|---:|---:|---:|---:|
| 11 | 14.91 | +32% | **16.19** | +34% | **18.34** | +13% |
| 15,825 | 14.80 | +43% | **15.44** | +38% | **18.17** | +18% |
| 32,458 | 13.32 | +36% | **14.41** | +41% | **18.09** | +26% |
| 64,785 | 12.08 | +46% | **12.71** | +46% | **17.86** | +41% |
| 128,793 | 9.65 | +55% | **10.37** | +58% | **17.61** | +70% |

（MTP 無効側は投機デコードが無いので補正不要。前回の実プロンプト実測 18.22/18.21/18.20 t/s が tensor 合成値 18.34 とほぼ一致していることで裏づけられている）

**MTP は layer 分割の decode を実運用ベースで +32〜+58% 改善するが、tensor 分割（MTP 無効）には全深度で届かない。** 差は深さとともに広がり、13 万トークンでは tensor が 70% 速い。

### 5. prefill — MTP は読み込みを確実に遅くする

ラダーの増分プロンプト評価（t/s）:

| 実効深さ (tok) | layer 7枚 off | layer 7枚 on | 変化 | layer 2枚 off | layer 2枚 on | 変化 | tensor 7枚 off |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 15,825 | 349.5 | 241.6 | **-31%** | 181.6 | 163.1 | -10% | 427.4 |
| 32,458 | 326.2 | 217.8 | **-33%** | 159.3 | 142.5 | -11% | 379.4 |
| 64,785 | 290.5 | 189.0 | **-35%** | 134.7 | 120.4 | -11% | 324.5 |
| 128,793 | 229.1 | 144.3 | **-37%** | 102.7 | 91.2 | -11% | 251.4 |

depth-0 prefill（新規プロンプト、`cache_prompt=false`）:

| サイズ | layer 7枚 off | layer 7枚 on | 変化 | layer 2枚 off | layer 2枚 on | 変化 | tensor 7枚 off |
|---|---:|---:|---:|---:|---:|---:|---:|
| pp512 | 130.6 | 126.6 | -3% | 134.3 | 130.2 | -3% | **384.4** |
| pp2048 | 224.8 | 217.4 | -3% | 171.4 | 167.1 | -3% | **423.6** |
| pp8192 | 346.2 | 254.5 | **-26%** | 186.2 | 169.2 | -9% | **438.7** |

**劣化幅が 7 枚で大きく 2 枚で小さい**のが特徴で、バッチが大きいほど（pp8192、ラダー深部ほど）効く。MTP 用の第 2 コンテキストにも同じトークン列を通す必要があるためと考えられるが、7 枚と 2 枚で三倍の開きがある理由までは特定していない。

結果として **layer 7枚の腕は MTP 有効のほうが総所要時間が長くなった**（19分01秒 → 23分20秒）。decode が倍近く速くなっても、prefill の劣化がそれを上回る。

### 6. 「layer 分割は枚数を増やしても decode が速くならない」は MTP 有効でも再現

| 実効深さ (tok) | layer 7枚 / layer 2枚（MTP off） | layer 7枚 / layer 2枚（MTP on） |
|---:|---:|---:|
| 11 | -7% | **-7.9%** |
| 15,825 | -7% | **-4.1%** |
| 32,458 | -4% | **-7.6%** |
| 64,785 | -5% | **-4.9%** |
| 128,793 | -5% | **-6.9%** |

**前回と同じく、7 枚は 2 枚より全深度でわずかに遅い。** MTP はパイプライン段数の不利を打ち消さない。prefill だけは 7 枚が 2 枚を上回る（MTP 有効でも +48〜+58%）ので、「layer 分割で枚数を増やして買えるのは VRAM と prefill であって decode ではない」という前回結論はそのまま維持される。

### 7. GPU 利用率・温度・電力（`sampler-*.log`、2 秒間隔）

| モード | 利用率 平均 | 温度 最大 / 平均 | 電力 最大 / 平均 |
|---|---:|---:|---:|
| layer 7枚 MTP off（前回） | 27.5% | 67℃ / 57.5℃ | 212 W / 77 W |
| layer 7枚 MTP on | **22.9%** | 67℃ / 58.6℃ | 214 W / 72 W |
| layer 2枚 MTP off（前回） | 18.2% | 71℃ / 49.4℃ | 216 W / 58 W |
| layer 2枚 MTP on | **17.7%** | 71℃ / 50.6℃ | 223 W / 59 W |
| tensor 7枚 MTP off（前回） | **75.9%** | 67℃ / 60.6℃ | 213 W / 97 W |

**MTP を有効にしても平均 GPU 利用率は上がらない（むしろ微減）**。MTP は投入する仕事量を増やすのではなく「1 回の順伝播でより多くのトークンを確定させる」機構なので当然ではあるが、**layer 分割の 27.5% → tensor の 75.9% という利用率の差は MTP では埋まらない**。これが第 4 節の結論（tensor に届かない）の物理的な裏づけになっている。温度・電力とも前回同様に余裕がある。

## 副次発見

1. **`--spec-draft-device` は MTP 単独モデル構成では効果がない**。`common/speculative.cpp` の `spec_mtp` 分岐は `llama_init_from_model(model_tgt, cparams)` を呼ぶだけで `mparams`（デバイス指定を含む）を使わない。`llama-split-bench` は `SPEC_ARGS` に `draft` が含まれると自動でこのフラグを付けるが、MTP ヘッドの配置先を制御できているわけではない。実際、追加 VRAM は最終デバイスに集中する。
2. **ラダーの合成フィラーは MTP の採択率を 1.0 に張り付かせる**。深さ 128,793 tok の段では 666/666 と完全採択だった。ツール README が「合成テキストはほぼ全部採択される（≈1.0 → 楽観側）」と書いているとおりで、**MTP を測るときに実プロンプト補正を省くと結論が反転しうる**（本レポートがまさにその例）。
3. **MTP の追加 VRAM は約 1.83 GiB で最終デバイスに偏る**。均等配分される tensor 分割と違い、layer 分割では最終デバイスだけが重くなるため、**ギリギリの構成では最終デバイスから OOM する**。2 枚構成では CUDA1 が 13.9 GiB / 16 GiB に達した。
4. **ツールの `REAL_MODE=auto` は tensor 腕を優先し、無ければ先頭の腕にフォールバックする**（`run-bench.sh:88-95`）。今回は tensor 腕が無いため補正が `layer` 腕で取られた。**前回は tensor 腕だったので、実プロンプト値どうしを直接比較する際は腕が違う点に注意が要る**。
5. **`llama_params_fit is not implemented for SPLIT_MODE_TENSOR` 警告は今回のハングとは無関係**。前回の正常な tensor 腕でも同じ警告が出ていた。
6. **aws-gpu01 では `ptrace_scope` によりユーザ権限で gdb アタッチできない**。ハングの詳細解析には sudo が要るが、本機は sudo をユーザに依頼する運用のため今回は見送った。

## 残課題

- **tensor + MTP ハングの上流報告**。再現条件は明快（`--split-mode tensor` かつ `--spec-type draft-mtp`、GPU 枚数非依存、`qwen35` + nextn ヘッド同梱 GGUF、build 10830 / `465e49b9c`）で、**分割モードの推奨と投機デコードの推奨が両立しないという実害がある**。報告するならバックトレースが欲しいので、`ptrace_scope` の緩和（sudo）をユーザに依頼したうえで gdb を取るのが先。投稿文は AI に書かせない運用（[llama.cpp #27773 の事例](./2026-09-06_234319_glm53flash_pr27773_vs_27754_depth.md)）に従い、素材の提示に留める。
- **`--spec-draft-n-max` のスイープ**。今回はツール既定の 2 のみ。`tokens_per_cycle` が実プロンプトで 1.1 しかないため、n_max を上げても伸びない可能性が高いが未確認。逆に 1 に下げれば prefill 劣化が減るかもしれない。
- **prefill 劣化の原因特定**。7 枚で -31〜-37%、2 枚で -10〜-11% と枚数依存が大きい。MTP コンテキストのプロンプト投入がどの経路を通るかを追う必要がある。
- **`start.sh` の `--split-mode layer` 固定の見直し**（前回からの継続課題）。**本計測は前回の推奨（tensor）を覆さない**。MTP は tensor の代替にならない。
- **MoE モデルでの再測定**（前回からの継続課題）。既定モデル DeepSeek-V4-Flash 系は MoE かつ MTP ヘッドを持つため、本レポートの結論がそのまま当てはまるとは限らない。aws-gpu02 の `P1_DIMMA2` 物理抜去で RPC 分散が復旧したら 13 GPU 構成で行う。
- **ツール作者への報告素材**。TP=7 / sm_60 での E2E データに加え、**tensor + MTP の併用不可**という運用上の落とし穴は作者にとっても有用（README の「TP≥3 は未検証」の穴埋めに加えて）。
- **電源とロック**: 当初はレポート後に停止する予定だったが、**ユーザの指示で aws-gpu01 は通電したまま残す**。ロックのみ解放済み（次に使うセッションは `lock.sh aws-gpu01` を取ること）。aws-gpu02 には一切触れていない。

## 参照レポート

- [P100 7 枚では tensor 分割が layer 分割を全面的に上回る](./2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor.md) — 本レポートの直接の前編。MTP 無効での layer / tensor / layer2 比較と、本レポートが比較対象に使う全数値の出所
- [aws-gpu02 が別の DIMM 故障で起動しなくなり実機検証が中断](./2026-09-11_055337_aws_gpu02_dimma2_failure_glm53flash_upstream.md) — aws-gpu01 単体運用に至った背景
- [GLM-5.3-Flash の 2 つの PR を深さで比較](./2026-09-06_234319_glm53flash_pr27773_vs_27754_depth.md) — 深度ラダー方式の先行例と、OSS 投稿文を AI に書かせない運用の根拠
