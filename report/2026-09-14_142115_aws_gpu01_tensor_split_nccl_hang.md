# tensor 分割の起動ハングは MTP ではなく NCCL が原因

- **実施日時**: 2026年9月14日 13:20 〜 14:34 JST (前レポートのハング再現・gdb によるバックトレース採取・NCCL_DEBUG での停止点特定・4 条件 30 試行のハング率測定・回避策での実推論確認・レポート作成)
- **報告日時**: 2026年9月14日 14:34 JST
- **作成者**: Claude Opus 5 (1M context)

## 概要

> **【2026-09-16 11:05 JST 追記・訂正】本レポートの結論（ハングは MTP と無関係な tensor 分割単独の現象で、`GGML_CUDA_ALLREDUCE` の切り替えで消える）は覆っていない。**
> ただし 2 点の訂正と 1 点の追加がある。詳細は[3 腕再測定レポート](./2026-09-16_103619_aws_gpu01_split_mode_mtp_3arm.md)。
> 1. **本レポートが推奨した `GGML_CUDA_ALLREDUCE=butterfly` は存在しない値だった。** `ggml/src/ggml-cuda/ggml-cuda.cu:1236-1248` が受け付けるのは `nccl` / `internal` / `none` のみで、
>    未知値は `unknown GGML_CUDA_ALLREDUCE value:` を警告して `comm_init_none` にフォールバックする（本レポートの `evidence/probe-ar-butterfly.log` 冒頭にもその警告が記録されている）。
>    **挙動は `none` と同一なので測定値と結論は有効**だが、**正しい書き方は `none`** である。
> 2. **残課題「回避策のコストは不明」に数字が付いた。** ctx=131072・7 枚・MTP 無効で条件をそろえて比べると、
>    **`none` は NCCL に対し decode -25%（18.34→13.81 t/s）、prefill -78〜-80%（pp512 で 384.4→83.8 t/s）**。
>    GPU 利用率も 75.6% → 48.7% に落ちる。**回避策は tensor 分割の最大の長所を打ち消す**。
> 3. **7 枚構成での NCCL ハング率が 0/13 になった。** 2026-09-16 に同一 argv で 10 回試して全て失敗（本レポートの 0/3 と通算）。
>    停止位置・GPU の徴候とも本レポートの特定と完全に一致した。
>
> **以下の本文は当時の記述をそのまま残す（`butterfly` の表記も含む。実体は `none` と読み替えること）。**

同じ日の昼に書いたレポートで、複数のカードで一つの層を分担して計算する分割方式と、モデルの先読み機構を同時に使うと、サーバの起動が途中で固まって前に進まなくなる、という現象を報告した。そのときは原因を突き止められないまま「この二つは組み合わせられない」と結論し、詳しい解析は次回に送っていた。デバッガを使うには管理者権限が要るのだが、この機械は権限の扱いを利用者に確認する運用にしていたためである。今回ユーザから明示的な許可が出たので、あらためて調べ直した。

結果として、**前回の結論は誤りだった**。固まるのは先読み機構とは何の関係もない。分担分割そのものが、起動のごく初期に確率的に固まるのである。先読みを切った状態でも同じ頻度で固まることを、条件を揃えた反復試行で確認した。前回たまたま先読みを切ったときだけ起動できていたのは、単に運が良かっただけだった。逆に言えば、前回のレポートで「分担分割のほうが速い」と結論づけた測定そのものも、起動に成功した幸運な一回の上に成り立っていたことになる。

固まる場所も正確に特定できた。モデルを読み込み終えたあと、サーバは本番の前に空回しを一回する。その空回しが、カード間で計算結果を足し合わせる処理の最初の一回で止まる。デバッガで覗くと、処理を待っている側のプログラムはずっと同じところを回り続けており、カードのほうは使用率が振り切れているのに、メモリの読み書きはまったく発生していなかった。つまり何も計算せずにひたすら相手の合図を待ち続けるプログラムが、カードの上で回りっぱなしになっている。足し合わせの待ち合わせが成立していない状態である。

この足し合わせには三つのやり方が用意されていて、既定では専用の通信ライブラリが選ばれる。固まるのはこのライブラリを使ったときだけで、残り二つに切り替えると、試した限り一度も固まらなかった。切り替えは環境変数一つで済む。数字で言うと、既定のままでは十五回中一回しか起動できなかったのに対し、切り替えた側は十五回中十五回とも起動できた。偶然でこの差が出る確率は十万分の一以下である。

さらに、切り替えたうえで先読み機構も同時に有効にして、実際に文章を生成させてみた。何の問題もなく動き、先読みもきちんと働いていた。つまり**前回「両立しない」と書いた二つの機能は、実際には両立する**。両立を妨げていたのは、まったく別の場所にあった通信の不具合だった。

副産物として、前回のレポートにあったもう一つの記述の誤りも判明した。この機械では管理者権限がパスワードなしで使える状態になっており、デバッガを使えなかったのは技術的な制約ではなく運用上の取り決めによるものだった。

運用上の結論としては、この機械で分担分割を使うときは足し合わせのやり方を環境変数で明示的に切り替えるべきである。切り替えによる速度の損失は、少なくとも今回の短い測定では見当たらなかった。ただし三つのうち一つは、このカード世代では待ちが発生した瞬間に異常終了する作りになっていることがコードから読み取れるため、実際に選ぶなら残りの一つが安全である。

なお、この不具合は上流に報告する価値がある。よく似た報告が既に一件あるが、そちらは長時間動かしたあとにまれに起きるという性質のもので、今回のように起動のたびに高い確率で起きるものとは様子が異なる。報告に使う文章は人間が書く取り決めなので、ここでは材料の提示に留める。

## 添付ファイル

- [実装プラン](attachment/2026-09-14_142115_aws_gpu01_tensor_split_nccl_hang/plan.md)
- [図の生成スクリプト](attachment/2026-09-14_142115_aws_gpu01_tensor_split_nccl_hang/plot_hang.py)
- [証跡一式](attachment/2026-09-14_142115_aws_gpu01_tensor_split_nccl_hang/evidence/) — 以下を含む
  - `dbg-tensor-mtp.log` — `-lv 4` での再現ログ（`warming up the model with an empty run` の直後で停止していることが見える唯一のログ）
  - `allbt.txt` — ハング中プロセスの全 65 スレッドのバックトレース（`sudo gdb -p <pid> -batch -ex "thread apply all bt"`）
  - `probe-nccldbg.log` / `probe-nccldbg-off.log` — `NCCL_DEBUG=INFO NCCL_DEBUG_SUBSYS=INIT,COLL` 付きの再現ログ（MTP 有効／無効）
  - `rate.txt` / `rate7.txt` — ハング率測定の生結果（2 枚 24 試行 / 7 枚 6 試行）
  - `probe2.sh` / `infer.sh` — 測定に使ったスクリプト
  - `probe-nowarmup.log` — `--no-warmup` でウォームアップを飛ばし、MTP 第 2 コンテキスト生成で止まったログ
  - `probe-nmax0.log` — `--spec-draft-n-max 0`（`n_rs_seq = 0`）でもハングすることの証跡
  - `probe-ar-butterfly.log` / `probe-ar-internal.log` / `probe-base-nomtp.log` — 正常起動時のログ
  - `infer-bf2.log` / `infer-bf7.log` / `infer-int2.log` — 回避策での実推論（`draft acceptance` の行を含む）
  - `mtp-tensor.log` / `mtp-tensor2.log` / `smoke-mtp/` — **前レポート実施時のハングログ**（実機 `/tmp` にしか無く再起動で失われるため回収した）
- 図: [日本語版](attachment/2026-09-14_142115_aws_gpu01_tensor_split_nccl_hang/hang-compare-ja.png) ／ [英語版](attachment/2026-09-14_142115_aws_gpu01_tensor_split_nccl_hang/hang-compare-en.png)

## 核心発見サマリ

![aws-gpu01 の Tesla P100 7 枚で測った --split-mode tensor の起動ハング切り分け。①2 枚構成の起動成功率は既定の NCCL が 1/12（8%）に対し butterfly 6/6・internal 6/6。②7 枚構成でも NCCL 0/3 に対し butterfly 3/3。③NCCL 経路での MTP 無効 0/6 と MTP 有効 1/6 に差はなく、ハングは MTP と無関係。④回避策での decode は internal 2枚 25.89 t/s、butterfly 2枚 26.95 t/s、butterfly 7枚 19.47 t/s](attachment/2026-09-14_142115_aws_gpu01_tensor_split_nccl_hang/hang-compare-ja.png)

**結論: [前レポート](./2026-09-14_124457_aws_gpu01_split_mode_mtp.md)の「`--split-mode tensor` と `--spec-type draft-mtp` は併用できない」は誤りで、真因は MTP と無関係な `--split-mode tensor` 単独の起動時ハングである。**

- **ハング地点**: `common_init_from_params` の**ウォームアップ `llama_decode`**（`common/common.cpp:1510-1546`）。`-lv 4` で `warming up the model with an empty run` を出した直後に停止することを実測。`--no-warmup` を付けるとここは通過し、次の GPU 実行（MTP 第 2 コンテキスト生成）で止まる。つまり止まるのは「**meta バックエンド上の最初の GPU 実行**」であって、特定の機能ではない。
- **バックトレース**（`sudo gdb`、Release ビルドのため関数名レベル）: メインスレッドは `llama_decode` → `llama_context::decode` → `ggml_backend_sched_graph_compute_async` → **`ggml_backend_meta_graph_compute`** → `ggml_backend_cuda_graph_compute` → `ggml_cuda_op_rope_impl<true>` → `ggml_cuda_kernel_can_use_pdl` → **`cudaFuncGetAttributes`** の中。全 65 スレッド中これ 1 本だけが `R` で、残りは futex / poll 待ち。20 秒間隔 3 回のサンプルでフレーム構成がわずかに変動するので、**デッドロックではなく libcuda 内部のスピン**。
- **GPU の状態**: 使用中の GPU が `utilization.gpu = 100%` かつ **`utilization.memory = 0%`**、SM クロックはブースト（1328 MHz）。**メモリ帯域を一切使わないカーネルが回り続けている**＝相手待ちのスピンカーネル。ホスト側の `cudaFuncGetAttributes`（lazy module load）はそのデバイスの処理完了を待たされているだけで、**真犯人はその前に投入された AllReduce**。
- **NCCL の停止点**: `NCCL_DEBUG=INFO NCCL_DEBUG_SUBSYS=INIT,COLL` で、`ncclCommInitAll` は両 rank とも `Init COMPLETE`（0.33 s）。その後 `AllReduce: opCount 0 ... count 10240 datatype 7`（= f32、ウォームアップ 2 トークン × n_embd 5120）が**ちょうど 12 回**発行されて停止する。**MTP 有効／無効で発行回数・サイズ・データ型は完全に同一**。
- **ハング率**（2 枚 / ctx=8192、同一条件反復。`rate.txt` / `rate7.txt`）:

| 経路 | 構成 | MTP | 起動成功 |
|---|---|---|---:|
| NCCL（既定） | 2 枚 | 無効 | **0 / 6** |
| NCCL（既定） | 2 枚 | 有効 | **1 / 6** |
| NCCL（既定） | 7 枚 | 有効 | **0 / 3** |
| `GGML_CUDA_ALLREDUCE=butterfly` | 2 枚 | 有効 | **6 / 6** |
| `GGML_CUDA_ALLREDUCE=internal` | 2 枚 | 有効 | **6 / 6** |
| `GGML_CUDA_ALLREDUCE=butterfly` | 7 枚 | 有効 | **3 / 3** |

  **NCCL 経路 1/15（6.7%）に対し非 NCCL 経路 15/15（100%）**。Fisher 正確検定（両側）**p = 9.6 × 10⁻⁶**。一方 **NCCL 経路内での MTP 無効 0/6 対 MTP 有効 1/6 には差がない**（p = 1.0）。
- **回避策は実用になる**: `GGML_CUDA_ALLREDUCE=butterfly` で `--split-mode tensor` と `--spec-type draft-mtp` を**同時に有効**にしたまま `/completion` が完走した。decode **26.95 t/s**（2 枚）/ **19.47 t/s**（7 枚）、`draft_n_accepted / draft_n` = 174/249（0.70）・128/340（0.38）で**投機デコードも機能している**。`internal` も 2 枚で 25.89 t/s（採択 168/261 = 0.64）で動作した。
- 証跡: バイナリは前レポートと同一（llama.cpp master `465e49b9c` / build 10830、`CMAKE_BUILD_TYPE=Release`、`GGML_CUDA_NCCL=ON`、`CMAKE_CUDA_ARCHITECTURES=60`）。NCCL は `libnccl.so.2.29.2` で、`cuobjdump --list-elf` により **sm_60 の cubin を同梱している**ことを確認済み（デバイスコード欠落ではない）。

## 前提・目的

- **背景**: [2026-09-14 の MTP レポート](./2026-09-14_124457_aws_gpu01_split_mode_mtp.md)は、`--split-mode tensor` + `--spec-type draft-mtp` でサーバが `llama threadpool init` の直後から進まなくなる現象を報告し、「**MTP × tensor 分割の組み合わせ固有の不具合**」と結論した。当時は「**hybrid モデル × MTP コンテキスト × tensor 分割**の三重条件」「`mtp_on_hybrid_qwen35` という特殊分岐が怪しい」という当たりを付けていた。
- **当時の制約**: 同レポートの副次発見 6 に「`ptrace_scope` によりユーザ権限で gdb アタッチできない。sudo はユーザに依頼する運用のため見送った」とあり、バックトレースが無いまま残課題に送られていた。
- **目的**: ユーザから aws-gpu01 での sudo / ptrace / gdb 使用の許可（本セッション限り）を得たので、**ハングの原因を確定させ、併用可能にする回避策を実証する**。
- **実害**: 本環境の最良構成は tensor 分割（前々レポートの結論）であり、その起動が確率的に失敗するのは運用上の問題である。

## 環境情報

| 項目 | 値 |
|---|---|
| サーバ | aws-gpu01 (10.8.2.1)、Supermicro SYS-4028GR-TRT2 |
| GPU | Tesla P100-PCIE-16GB × 7（sm_60）、PCIe 接続・**NVLink なし**。GPU0-2 は PIX（同一 PCIe スイッチ配下）、GPU3-6 も PIX、両群間は PHB。P2P は全ペア `OK` |
| llama.cpp | master `465e49b9c`、build 10830（**前レポートと同一バイナリを再ビルドせず使用**） |
| ビルド設定 | `CMAKE_BUILD_TYPE=Release`（**DWARF なし**＝関数名のみ、`.debug_*` セクション 0 件）、`GGML_CUDA=ON` / `GGML_CUDA_NCCL=ON` / `GGML_CUDA_GRAPHS=ON` / `CMAKE_CUDA_ARCHITECTURES=60` |
| NCCL | `libnccl.so.2.29.2`（システム提供）。`cuobjdump --list-elf` で `sm_60 sm_61 sm_70 sm_80 sm_90` を確認 |
| モデル | `Qwen3.8-27B-UD-Q4_K_XL.gguf`（arch `qwen35`、hybrid = SSM + attention 混成、MTP ヘッド `blk.64` 同梱） |
| 切り分け時の共通引数 | `-ngl all -fa on -c 8192 --parallel 1 -t 16 --jinja --cache-type-k q8_0 --cache-type-v q8_0`（**ctx は 8192 に縮小**。起動可否だけを見るため） |
| デバッガ | gdb 15.0.50（`eu-stack` / `pstack` は未導入）。`ptrace_scope = 1` だが **sudo は NOPASSWD で通る** |
| ロック | `aws-gpu01` のみ取得（aws-gpu02 は `P1_DIMMA2` 故障で電源 Off、RPC スタックは立てないため） |

## 再現方法

```bash
# 0) ロック取得（プロジェクトルートからの相対パス）
.claude/skills/gpu-server/scripts/lock.sh aws-gpu01

# 1) 最小再現（2 枚 / ctx=8192 / -lv 4）。-lv 4 にしないと停止位置が分からない
#    （"warming up ..." は COM_TRC なので既定の verbosity 3 では出ない）
ssh -n -f aws-gpu01 "cd ~ && setsid nohup ~/llama.cpp/build/bin/llama-server \
  -m ~/models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf \
  --host 127.0.0.1 --port 18099 --device CUDA0,CUDA1 --split-mode tensor \
  -ngl all -fa on -c 8192 --parallel 1 -t 16 --jinja \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  -lv 4 > /tmp/dbg.log 2>&1 < /dev/null &"
# 高確率（本レポートの反復測定では 15 回中 14 回）で
# "warming up the model with an empty run" の直後で停止する
# （MTP フラグの有無は関係ない）

# 2) ハング中のバックトレース（要 sudo。ptrace_scope=1 のため一般ユーザでは不可）
ssh -n aws-gpu01 'sudo gdb -p $(pgrep -x llama-server) -batch -ex "bt"'
ssh -n aws-gpu01 'sudo gdb -p $(pgrep -x llama-server) -batch -ex "thread apply all bt"'

# 3) GPU 側の判別（100% なのに memory 0% ならスピンカーネル）
ssh -n aws-gpu01 'nvidia-smi --query-gpu=index,utilization.gpu,utilization.memory,clocks.sm --format=csv,noheader'

# 4) NCCL のどこで止まったか
#    NCCL_DEBUG=INFO NCCL_DEBUG_SUBSYS=INIT,COLL を付けて起動し、最後の AllReduce 行を見る

# 5) 回避策（これを付けると起動が安定する）
#    GGML_CUDA_ALLREDUCE=butterfly を環境変数で渡すだけ

# 停止は必ず pkill -x llama-server（pkill -f はリモート側 bash に自己マッチする）
```

ハング率の測定には `evidence/probe2.sh`、回避策での実推論には `evidence/infer.sh` を使った。
**`probe2.sh` は起動前に「GPU 利用率が全枚 5% 未満かつ compute app が 0 件」になるまで待つ**。
ハングしたプロセスを落とした直後は GPU にスピンカーネルが残ることがあり、これを待たないと
次の試行の判定が汚染される。

## 結果詳細

### 1. ハング地点は「ウォームアップ `llama_decode`」

実機 `465e49b9c` では `llama threadpool init` を出すのは `common/common.cpp:1790`
（`common_threadpools::init()`）で、呼び出し元は `common/common.cpp:1408` =
**`common_init_result` コンストラクタの最終行**である。つまりこのログが出た時点で
`llama_init_from_model`（`ggml_backend_sched` 生成・graph reserve）は完走済みで、
**reserve でのハングは除外される**。実際 `-lv 4` のログには停止前に

```
sched_reserve: reserve took 77.87 ms, sched copies = 1
cmn          init: llama threadpool init, n_threads = 16
cmn  common_init_: warming up the model with an empty run - please wait ... (--no-warmup to disable)
```

と出ており、**ウォームアップに入った直後で止まっている**。

`--no-warmup` を付けるとここは通過し、`creating MTP draft context` を出したあと
（= MTP 第 2 コンテキストの生成中）で止まる。**どちらも「meta バックエンド上の最初の GPU 実行」**であり、
止まるのは特定の機能ではなく「最初の一回」である。

### 2. バックトレース — メインスレッド 1 本だけが libcuda 内でスピン

```
#12 cudaFuncGetAttributes () from libcudart.so.12
#13 ggml_cuda_kernel_can_use_pdl(void const*) () from libggml-cuda.so.0
#14 void ggml_cuda_op_rope_impl<true>(ggml_backend_cuda_context&, ggml_tensor*, ggml_tensor const*) ()
#15 ggml_backend_cuda_graph_compute(ggml_backend*, ggml_cgraph*) ()
#16 ggml_backend_meta_graph_compute(ggml_backend*, ggml_cgraph*) () from libggml-base.so.0
#17 ggml_backend_sched_graph_compute_async () from libggml-base.so.0
#18 llama_context::graph_compute(ggml_cgraph*, bool) ()
#19 llama_context::process_ubatch(...) ()
#20 llama_context::decode(llama_batch const&) ()
#21 llama_decode () from libllama.so.0
#22 common_init_from_params(common_params&, bool) () from libllama-common.so.0
#23 server_context_impl::load_model(common_params&) ()
```

全 65 スレッドのうち、動いているのは**このメインスレッド 1 本だけ**。他は
`__futex_abstimed_wait_common64` 46 本、`__GI___poll` 12 本などで待機している
（NCCL のプロキシスレッド `ncclProxyService` / `ncclProxyServiceUDS` も poll 待ちでアイドル）。
**複数スレッドが互いを待つ古典的デッドロックではない。**

20 秒間隔で 3 回サンプルすると libcuda 内部のフレーム構成がわずかに変動するので、
`cudaFuncGetAttributes` は**固まっているのではなく内部でスピンしている**。
`cudaFuncGetAttributes` は CUDA 12 の lazy module loading を誘発するため、
**先に投入済みのカーネルが GPU を占有していると待たされる**。つまり
このフレームは被害者であって犯人ではない。

### 3. GPU の状態 — 帯域を使わないスピンカーネル

```
index, utilization.gpu, utilization.memory, clocks.sm
0, 100 %, 0 %, 1328 MHz
1, 100 %, 0 %, 1328 MHz
2, 0 %, 0 %, 1189 MHz     ← 未使用の 5 枚は 0%
```

**利用率 100% なのにメモリ利用率が 0%**、SM クロックはブースト状態。
計算もメモリアクセスもせずに回り続けるカーネル＝**相手の到着を待つスピン**である。
7 枚構成では使用中の 7 枚すべてが 100% になる。

### 4. NCCL は初期化に成功し、AllReduce を 12 回発行したところで止まる

`NCCL_DEBUG=INFO NCCL_DEBUG_SUBSYS=INIT,COLL`:

```
ncclCommInitAll comm ... rank 0 nranks 2 cudaDev 0 busId 5000 - Init COMPLETE
ncclCommInitAll comm ... rank 1 nranks 2 cudaDev 1 busId 7000 - Init COMPLETE
Init timings - ncclCommInitAll: total 0.33 (kernels 0.24, alloc 0.06, bootstrap 0.00, ...)
AllReduce: opCount 0 sendbuff 0x... count 10240 datatype 7 op 0 root 0 comm 0x...871d0 [nranks=2]
AllReduce: opCount 0 sendbuff 0x... count 10240 datatype 7 op 0 root 0 comm 0x...a16a0 [nranks=2]
Symmetric VA size=16GB
Channel 00/0 : 1[1] -> 0[0] via P2P/direct pointer
Connected all rings, use ring PXN 0 GDR 1
... (AllReduce がさらに 5 ペア) ...
                                   ← ここで停止
```

- **`ncclCommInitAll` は成功している**（0.33 秒）。初期化ハングではない。
- `count 10240` = ウォームアップの 2 トークン × n_embd 5120、`datatype 7` = f32。
  小テンソル経路（`ne < 32768`）なので bf16 圧縮経路には入っていない。
- **AllReduce はちょうど 12 回（6 ペア）発行されて止まる**。最初の AllReduce の最中に
  `Symmetric VA` と `Channel ... via P2P/direct pointer` が出ており、
  **遅延接続（lazy connect）が最初の collective の中で走っている**。
- **ログ上 `opCount` は 12 回すべて 0 のまま**で、collective が完了扱いにならないことと整合する。
- **MTP 有効時と無効時で、発行回数・count・datatype はすべて同一**だった
  （`probe-nccldbg.log` と `probe-nccldbg-off.log`）。これが「MTP は無関係」の直接証拠である。

### 5. 切り分けマトリクス

| # | 条件（2 枚 / ctx=8192） | 結果 |
|---|---|---|
| 1 | tensor、MTP 無効 | **ハングする**（前レポートの前提が崩れる） |
| 2 | tensor、MTP 有効 `--spec-draft-n-max 2` | ハングする |
| 3 | tensor、MTP 有効 `--spec-draft-n-max 0`（`n_rs_seq = 0`） | **ハングする** → recurrent rollback 説は棄却 |
| 4 | tensor、MTP 有効、`--no-warmup` | ウォームアップは通過し、MTP 第 2 コンテキスト生成で停止 |
| 5 | tensor、MTP 有効、`GGML_CUDA_ALLREDUCE=butterfly` | **正常**（11 秒で `listening on`） |
| 6 | tensor、MTP 有効、`GGML_CUDA_ALLREDUCE=internal` | **正常**（11 秒） |
| 7 | layer、MTP 有効 | 正常（前レポート実績） |

**事前にコードから立てた仮説は外れた。** `n_rs_seq` は `--spec-type draft-mtp` を付けると
`--spec-draft-n-max` の値になり（`common/common.h:394-400`）、hybrid の recurrent state を拡張して
`s_copy_extra` 経路のノードをグラフに出現させる（`src/llama-graph.cpp:3129-3153`）。
`ggml/src/ggml-backend-meta.cpp:1827-1834` にはこのホスト側 view ノードを rank 分割せずスキップする
FIXME があり「regular usage では no-op だから問題ない」と明言されているため、
**MTP がその前提を崩している**と見立てていた。しかし #3 で `n_rs_seq = 0` にしてもハングし、
#1 で MTP 無効でもハングしたので、この筋は成立しない。

### 6. ハング率 — NCCL 1/15 に対し非 NCCL 15/15

`probe2.sh` による同一条件反復（起動から 45〜60 秒以内に `listening on` が出れば成功）:

| 経路 | 構成 | MTP | 成功 / 試行 | 成功時の起動所要 |
|---|---|---|---:|---|
| NCCL（既定） | 2 枚 | 無効 | 0 / 6 | — |
| NCCL（既定） | 2 枚 | 有効 | 1 / 6 | 13 秒 |
| NCCL（既定） | 7 枚 | 有効 | 0 / 3 | — |
| butterfly | 2 枚 | 有効 | **6 / 6** | 10〜13 秒 |
| internal | 2 枚 | 有効 | **6 / 6** | 10〜13 秒 |
| butterfly | 7 枚 | 有効 | **3 / 3** | 20 秒 |

- **NCCL 経路 1/15（6.7%）／非 NCCL 経路 15/15（100%）、Fisher 正確検定（両側）p = 9.6 × 10⁻⁶。**
- **NCCL 経路の中では MTP 無効 0/6 と MTP 有効 1/6 に有意差はない**（p = 1.0）。
- ハング時は必ず「使用中の GPU が全枚 100% / memory 0%」になり、成功時は起動後 0% に落ちる。
- **枚数には依存しない**（2 枚でも 7 枚でも起きる）。
- なお本測定より前に行った N=3 の予備試行では NCCL 経路で 3/6 成功しており、**ハング率自体は
  一定ではない**（試行間隔や page cache の状態でタイミングが変わるためと思われる）。
  「確率的に起きる」という性質は変わらないが、**率の絶対値は条件依存**と理解すべきである。

### 7. 回避策は実用になる — tensor 分割と MTP は両立する

`infer.sh`（起動 → `/completion` で 300 トークン生成、`cache_prompt=false`）:

| 条件 | 起動 | decode | prefill | `draft_n_accepted / draft_n` |
|---|---|---:|---:|---:|
| `internal`、2 枚、MTP 有効 | OK | **25.89 t/s** | 16.65 t/s | 168 / 261 = 0.64 |
| `butterfly`、2 枚、MTP 有効 | OK | **26.95 t/s** | 17.01 t/s | 174 / 249 = 0.70 |
| `butterfly`、7 枚、MTP 有効 | OK | **19.47 t/s** | 17.75 t/s | 128 / 340 = 0.38 |

**`--split-mode tensor` と `--spec-type draft-mtp` を同時に有効にしたまま推論が完走し、
投機デコードも実際に効いている**（採択率 0.38〜0.70）。前レポートの「併用不可」は撤回される。

7 枚が 2 枚より遅いのは前々レポートの layer 分割で観測された傾向と同じ方向だが、
本測定は ctx=8192・単発リクエストの簡易測定であり、**深度ラダーでの正式な比較ではない**。
モデルは同じだが ctx とワークロードが違うので、前レポートの数値と直接比較してはならない。

## 副次発見

1. **前レポートの記述 2 点が誤りだった**。
   - 「`--spec-type draft-mtp` と `--split-mode tensor` は併用できない」（第 1 節・結論）→ **併用できる**。
     ハングは MTP と無関係で、`GGML_CUDA_ALLREDUCE` を切り替えれば両立する。
   - 「aws-gpu01 では `ptrace_scope` によりユーザ権限で gdb アタッチできない」（副次発見 6）→
     `ptrace_scope = 1` は事実だが、**この機械は NOPASSWD で sudo が通る**（`gpu-server/aws-gpu.md` にも
     「NOPASSWD で root 取得可」と記載がある）。障壁は技術的なものではなく、
     CLAUDE.md の sudo 運用ポリシー（aws-gpu01 は例外リストに未収載）だけだった。
2. **`internal` AllReduce は P100 では原理的に危険**。`ggml/src/ggml-cuda/allreduce.cu:158-169` の
   ランデブー待ちは `while (signal != token) { __nanosleep(100); }` だが、`__nanosleep` は
   `__CUDA_ARCH__ >= GGML_CUDA_CC_VOLTA`（sm_70）でのみ有効で、それ未満では `NO_DEVICE_CODE` に落ちる。
   これは `common.cuh:404-416` の定義により **device 側では `printf` + `__trap()`**、つまり
   **待ちが一度でも発生した瞬間にプロセスが落ちる**。今回 6/6 で正常動作したのは、
   待ちに入る前に相手の signal が既に届いていた（ループを 1 回も回らなかった）ためと解釈できる。
   **sm_60 での回避策には `butterfly` を選ぶべき**で、`internal` は運に依存する。
3. **`cuda-gdb` はこのハングにアタッチできなかった**。`sudo cuda-gdb -p <pid> -batch -ex "info cuda kernels"`
   は 4 分半経っても応答せず、`timeout` の SIGTERM でも死なず `SIGKILL` が必要だった。
   GPU がスピンカーネルで専有されているとデバッガのアタッチ自体が成立しない。
   **スピンカーネルの identity は `nvidia-smi` の `utilization.memory = 0%` から間接的に推定するしかなかった。**
4. **判定スクリプトで「正常時にも出る文字列」を失敗条件にしてはいけない**。
   `--split-mode tensor` は正常時も必ず
   `common_fit_params: failed to fit params to free device memory: llama_params_fit is not implemented for
   SPLIT_MODE_TENSOR, abort` を出す。最初に書いた判定スクリプトはこれを `failed to` / `abort` で拾って
   全試行を ERROR にしてしまった（llama-server スキルに同趣旨の注意書きがあり、それを実際に踏んだ形）。
   成功判定は `listening on`、失敗判定は `terminate called` / `out of memory` / `has no device code` に限定した。
5. **ハングしたプロセスを落とした直後は GPU にスピンカーネルが残ることがある**。
   反復測定では「全 GPU の利用率が 5% 未満かつ compute app が 0 件」になるまで待ってから
   次を起動しないと、前の試行の残骸が判定を汚染する。
6. **`pkill -x llama-server`（SIGTERM）で終了しない個体が残ることがある**。7 枚構成で正常に推論を終えた
   サーバが、ログに `cleaning up before exit...` を出したまま 20 分間 `Ssl` 状態で残り、
   **7 枚ぶんの GPU メモリ（各 2.85 GiB）を掴み続けた**。`kill -9` で即座に解放された。
   反復測定では `pgrep -x llama-server` で残存を確認し、一定時間で `kill -9` にフォールバックすること。
   なお本レポートのハング率測定（`rate.txt` / `rate7.txt`）は `probe2.sh` が毎回
   「GPU 利用率 5% 未満かつ compute app 0 件」を 2〜4 秒で確認して起動しており、**この汚染は受けていない**。
7. **上流に似た報告があるが別物**。[llama.cpp #27110](https://github.com/ggml-org/llama.cpp/issues/27110)
   は `--split-mode tensor` で 40 秒以上のアイドル後の最初のリクエストが約 1/1000 の頻度でデッドロックする
   というもので、**internal / NCCL の両方で再現する**と報告されている。今回のものは
   **起動時（最初の GPU 実行）に高確率で起き、internal / butterfly では再現しない**ため、様子が異なる。
   別件として報告する価値がある。
8. **前レポートの「hybrid × MTP × tensor の三重条件」「`mtp_on_hybrid_qwen35` 分岐が怪しい」という
   当たりは全部外れていた**。コードリーディングだけで筋の良い仮説を立てても、
   実測（`--spec-draft-n-max 0` と MTP 無効での再現）1 回で棄却されることがある。

## 残課題

- **根本原因の特定**。「NCCL 経路でだけ、起動直後の最初の AllReduce がランデブーを取り損ねる」ところまでは
  確定したが、**なぜ取り損ねるかは未特定**。次の手は (a) `build-dbg/` に `RelWithDebInfo` で再ビルドして
  行番号付きバックトレースを取る、(b) `NCCL_P2P_DISABLE=1` / `NCCL_CUMEM_ENABLE=0` /
  `NCCL_LAUNCH_MODE` などのノブで再現条件を絞る、(c) 最初の collective 中に走る遅延接続
  （ログ上 `Symmetric VA` / `Channel ... via P2P/direct pointer` が AllReduce の内側で出る）を疑う、あたり。
  なお `libnccl` は sm_60 の cubin を同梱しており、**デバイスコード欠落説は否定済み**。
- ~~**NCCL 経路での性能比較は未取得**~~ → **2026-09-16 に別経路で解決**。NCCL 腕の再取得は 10 回試して全て失敗したが、
  代わりに `tensor × none × MTP 無効` の腕を測り、2026-09-14 の NCCL 腕と比較することでコストを確定させた（decode -25% / prefill -78〜-80%）。詳細は[3 腕再測定レポート](./2026-09-16_103619_aws_gpu01_split_mode_mtp_3arm.md)。以下は当時の記述。
- **NCCL 経路での性能比較は未取得**。回避策（butterfly）のコストを数字で言うには NCCL 経路の decode 値が要るが、
  **リトライを計 6 回行って一度も起動しなかった**ため測れていない（うち 5 回は後述の孤児プロセスが
  GPU を掴んだ状態での試行、1 回はクリーンな状態）。回避策のコストは現時点では**不明**であり、
  「butterfly のほうが速い／遅い」といった主張は本レポートでは行わない。
- **上流報告**。再現条件は明快（`--split-mode tensor` + CUDA + NCCL、sm_60 × 7、GPU 枚数非依存、
  MTP 非依存、`GGML_CUDA_ALLREDUCE` の切り替えで消える）。**#27110 とは別件として整理する**。
  投稿文は AI に書かせない運用（[llama.cpp `AGENTS.md`](https://github.com/ggml-org/llama.cpp/blob/master/AGENTS.md) および
  [#27773 の事例](./2026-09-06_234319_glm53flash_pr27773_vs_27754_depth.md)）に従い、ここでは素材の提示に留める。
- **過去 2 本のレポートの数値の扱い**。[前々レポート](./2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor.md)の
  tensor 腕（64 分の本計測）と[前レポート](./2026-09-14_124457_aws_gpu01_split_mode_mtp.md)の比較対象値は、
  **起動に成功した幸運な 1 回**の上に成り立っている。**測定値そのものが無効になるわけではない**
  （起動さえ抜ければ以後は安定して動き、実際 20 分以上完走している）が、
  「tensor 分割を既定にする」という運用判断をする際は、**起動が確率的に失敗する**という本レポートの事実を
  併せて考慮する必要がある。`start.sh` を tensor に切り替えるなら `GGML_CUDA_ALLREDUCE=butterfly` を
  セットで入れること。
- ~~**MTP 有効での tensor 腕の正式な再測定**~~ → **2026-09-16 に完了**。3 腕そろえて深度ラダーを取り直した（[3 腕再測定レポート](./2026-09-16_103619_aws_gpu01_split_mode_mtp_3arm.md)）。
  「MTP は tensor の代替にならない」は 3 腕でも維持された。以下は当時の記述。
- **MTP 有効での tensor 腕の正式な再測定**。回避策で併用可能になったので、前レポートで欠測だった
  tensor + MTP の腕を深度ラダーで取り直せる。これにより前レポートの「MTP は tensor の代替にならない」
  という結論を、**同一条件の 3 腕**で検証し直せる。
- **`CLAUDE.md` への反映の要否**。本レポートの回避策（`GGML_CUDA_ALLREDUCE=butterfly`）は、
  次に aws-gpu01 で tensor 分割を使うセッションが確実に踏む罠の対策である。
  `CLAUDE.md` の「GPUサーバとLLM」節か `llama-server` スキルに 1 行入れるかは**ユーザの判断を仰ぐ**
  （本セッションでは変更していない）。
- **sudo ポリシー**。今回の sudo 使用はユーザの明示許可（本セッション限り）による。
  CLAUDE.md の例外リスト（現在は mi25 の `dmidecode` と aws-gpu02 のみ）は変更していない。
  aws-gpu01 でのデバッグを今後も行うなら、恒久的に追加するかを別途決める必要がある。
- **電源とロック**: aws-gpu01 は**通電したまま**（前セッションからの方針を維持）。ロックは解放済み。
  aws-gpu02 には一切触れていない。

## 参照レポート

- [tensor 分割と MTP は両立するが回避策が prefill を 7 割奪う](./2026-09-16_103619_aws_gpu01_split_mode_mtp_3arm.md) — 本レポートの回避策を使った 3 腕再測定。`butterfly` の綴りを訂正し、残課題だった回避策のコストに数字を与えた
- [MTP は layer 分割を大きく速くするが tensor 分割とは併用できない](./2026-09-14_124457_aws_gpu01_split_mode_mtp.md) — 本レポートが訂正する直接の対象。ハングを「MTP × tensor 固有」と結論していた
- [P100 7 枚では tensor 分割が layer 分割を全面的に上回る](./2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor.md) — tensor 分割を推奨した元のレポート。その tensor 腕も起動に成功した 1 回の測定である
- [aws-gpu02 が別の DIMM 故障で起動しなくなり実機検証が中断](./2026-09-11_055337_aws_gpu02_dimma2_failure_glm53flash_upstream.md) — aws-gpu01 単体運用に至った背景
- [GLM-5.3-Flash の 2 つの PR を深さで比較](./2026-09-06_234319_glm53flash_pr27773_vs_27754_depth.md) — OSS 投稿文を AI に書かせない運用の根拠
