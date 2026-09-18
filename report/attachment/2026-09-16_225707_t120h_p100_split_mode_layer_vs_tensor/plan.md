# t120h-p100 で split-mode layer vs tensor ベンチを実施する

## Context

`report/2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor.md` は、aws-gpu01（Tesla P100 ×7）で
llama-split-bench を使い `--split-mode layer`（既定）と `--split-mode tensor` を深度ラダーで比較し、
**tensor が全深度・全指標で layer を上回る**という結論を出した。同レポートの残課題には
**「他サーバ（t120h-p100 の 4 枚 ほか）や MoE モデルでの再測定なしに `start.sh` の既定値を変えるべきではない」**と明記されている。

本作業はその残課題に直接応えるもので、**同じ方式を t120h-p100（Tesla P100 ×4）で、モデルを
Qwen3.6-35B-A3B（MoE）に替えて実施する**。手本が dense 27B だったのに対し今回は MoE であり、
**本プロジェクトで MoE × tensor 分割を測るのは初めて**になる（手本レポートの残課題「MoE モデルでの layer vs tensor」の初データ）。

成果物は `report/<TS>_t120h_p100_split_mode_layer_vs_tensor.md` と添付一式。

## 前提（調査で確定済み）

| 項目 | 値 |
|---|---|
| サーバ | t120h-p100 (10.1.4.14)、Tesla P100-PCIE-16GB **×4**（sm_60、PCIe、NVLink なし）、Xeon Gold 6138 ×2 |
| 現在の状態 | **電源 OFF**（iLO5 `power.sh` で投入可。爆音ガードは aws 機のみなので t120h-p100 には無い） |
| モデル | `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` → `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf`、**22,360,456,160 B = 20.8 GiB**、MoE 35B/A3B、**非 MTP** |
| ベンチツール | `src/llama-split-bench/`（`~/llama-split-bench` へ rsync。数 MB） |
| 手本の設定 | ctx=131072 / STAGES=0,16000,32000,64000,128000 / N_PREDICT=1000 / PP0=512,2048,8192 / THREADS=16 / SPEC_ARGS="" / KV q8_0 / `-fa on` |

### ユーザ判断（確認済み）

1. **llama.cpp は aws-gpu01 と同じ `465e49b9c`（build 10830）に揃える** — 機械間の直接比較を可能にするため。
2. **tensor 腕の AllReduce は NCCL を先に試し、ダメなら回避策へ**。
3. **モデルがサーバに残っていなければ、転送を始めず報告して指示を仰ぐ**。

### 判断 2 についての訂正（調査で判明）

`ggml/src/ggml-cuda/allreduce.cu` の `ggml_cuda_ar_pipeline_init` は **(a) `n_devices != 2`、(b) `cc < VOLTA(sm_70)`** の
いずれかで nullptr を返し、`none`（meta backend butterfly）へフォールバックする。
**P100（cc 6.0）かつ 4 枚の本機では `internal` は二重に選択不可**なので、実質の選択肢は **`nccl` か `none` の 2 択**になる。
（aws-gpu01 で「internal が 6/6 成功」とされた実績も、実体は `none` だったと説明が付く。）
ユーザの意図（まず既定 NCCL、ダメなら回避策）はそのまま `nccl` → `none` として実行する。

## 方針の要点

- **`-ub` は指定しない**（`EXTRA_ARGS=""`、llama-server 既定 `-b 2048 -ub 512`）。手本と同一条件にするため。
  本番運用の `start.sh` は `-b 4096 -ub 4096` を使うが、これを持ち込むと compute buffer が約 8 倍になり
  **2 枚 layer 腕が 16 GiB に収まらない**（見積 16.3 GiB）。**手本との同一性と OOM 回避が同じ方向を向く**。
  レポートには「本ベンチは `-ub 512` であり本番の `-ub 4096` とは prefill 絶対値が異なる」と明記する。
- **腕は手本と同形**: `layer`（4枚 layer）/ `tensor`（4枚 tensor）/ `layer2`（2枚 layer、`BASELINE`）。
  1 枚（15.6 GiB 空き）には 20.8 GiB の重みが載らないので `single` は取らない（手本と同じ事情）。
- **作図は WS 側で行う**（結果一式は手本実測で 1.4 MB。対してサーバに matplotlib 30 MB + Noto CJK 16 MB を
  遅い回線で落とすのは割に合わない）。WS には matplotlib 3.6.3 が既にある。

## 手順

### Phase 0 — ローカル事前チェック（5 分）

```bash
cd /home/ubuntu/projects/llm-server-ops
bash src/llama-split-bench/check.sh
python3 -c "import matplotlib; print(matplotlib.__version__)"     # 3.6.3
fc-list | grep -ci "noto sans cjk" || true                        # 0 なら Phase 9 で導入
```

### Phase 1 — 電源投入 → SSH 到達 → ロック取得（8〜15 分）

`lock.sh` は SSH 経由なので**電源投入が先**（手本の「ロック→電源」順は aws 機固有）。

```bash
.claude/skills/gpu-server/scripts/power.sh t120h-p100 on
until ssh -n -o ConnectTimeout=5 -o BatchMode=yes t120h-p100 uptime 2>/dev/null; do sleep 15; done
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

- 15 分で SSH が来ない → `bmc-screenshot.sh` で KVM 保全してから報告（電源リセットの前にスクショが本プロジェクトの鉄則）。
- ロックが他セッション保持 → **即中止して報告**（電源も落とさない）。

### Phase 2 — 環境確認（5 分）★中止判断ポイント

```bash
ssh -n t120h-p100 'nvidia-smi --query-gpu=index,name,memory.total,memory.used,compute_cap --format=csv; nproc; free -g|head -2; df -h ~|tail -1'
ssh -n t120h-p100 'pgrep -x llama-server; ss -ltn | grep -E ":8000|:18081"; echo ---'
ssh -n t120h-p100 'find ~/.cache/huggingface ~/models -name "Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf" -printf "%s\t%p\n" 2>/dev/null'
ssh -n t120h-p100 'cd ~/llama.cpp && git rev-parse HEAD && git status --short | head'
```

- **GGUF が無ければ、転送を始めずユーザに報告して指示を待つ**（ユーザ判断 3）。
  報告時には mi25 に実体がある可能性（過去に P100→mi25 でコピーした実績あり）も併せて伝える。
- 他の `llama-server` が動いていたら停止を検討する（ツールの外部プロセスガードが ladder を abort するため）。
- ディスク空きが `build` 2 つ分に足りなければ、退避方法を `cp bin/` 単位に切り替える。

### Phase 3 — llama.cpp を `465e49b9c` にしてビルド（30〜60 分）★リスクあり

**既存バイナリを必ず退避してから**行う。`update_and_build.sh` は `git pull` で master HEAD に進めてしまうので使わず、
その `build_llama_cpp()` と同じ cmake 引数を手で実行する。

```bash
# 0) 退避（失敗時はこれを戻す）
ssh -n t120h-p100 'cd ~/llama.cpp && git rev-parse --short HEAD && mv build build.bak-$(git rev-parse --short HEAD)'

# 1) 465e49b9c を取得。まず通常の fetch を試す
ssh -n t120h-p100 'cd ~/llama.cpp && timeout 900 git fetch origin 465e49b9cea78a68b9c244ffb48d0ee24a82873d'
#    失敗したら WS の src/llama.cpp（既に 465e49b9c）から差分バンドルを作って転送する:
#      cd src/llama.cpp && git bundle create /tmp/lcpp.bundle <p100のHEAD>..465e49b9c
#      scp /tmp/lcpp.bundle t120h-p100:/tmp/ && ssh -n t120h-p100 'cd ~/llama.cpp && git fetch /tmp/lcpp.bundle'

ssh -n t120h-p100 'cd ~/llama.cpp && git checkout 465e49b9cea78a68b9c244ffb48d0ee24a82873d && git rev-parse --short HEAD'

# 2) ビルド（update_and_build-t120h-p100.sh:15-25 と同一の引数）
ssh -n t120h-p100 "cd ~/llama.cpp && setsid nohup sh -c 'cmake -B build -DLLAMA_OPENSSL=ON -DGGML_NATIVE=ON \
  -DGGML_CUDA=ON -DGGML_CUDA_FA_ALL_QUANTS=ON -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.9/bin/nvcc \
  -DCMAKE_CUDA_ARCHITECTURES=60 && cmake --build build --config Release -- -j \$(nproc)' > /tmp/build.log 2>&1 < /dev/null &"
ssh -n t120h-p100 'until grep -qE "llama-server|Error|error:" /tmp/build.log && [ ! -x ~/llama.cpp/build/bin/llama-server ] || [ -x ~/llama.cpp/build/bin/llama-server ]; do sleep 60; done'

# 3) ★NCCL がリンクされたかを確定（tensor 腕の経路がこれで決まる）
ssh -n t120h-p100 'grep -i nccl /tmp/build.log | head; ldd ~/llama.cpp/build/bin/libggml-cuda.so 2>/dev/null | grep -i nccl; echo ---'
ssh -n t120h-p100 '~/llama.cpp/build/bin/llama-server --version 2>&1 | head -3; sha256sum ~/llama.cpp/build/bin/llama-server'
```

- `GGML_CUDA_NCCL` は既定 ON だが `find_package(NCCL)` 依存。**NCCL が無ければ既定でも butterfly 経路になり、
  ハングしない代わりに手本の tensor 値（NCCL 経路）と直接比較できない**。どちらだったかを必ずレポートに書く。
- ビルドが通らなければ **1 回だけリトライ**し、それでもダメなら `build.bak-*` を戻して
  「既存 build（`0843245cb`, build 9690）で実施するか、中止するか」をユーザに確認する。
  なお build 9690 でも `--split-mode tensor` と `GGML_CUDA_ALLREDUCE` は実装済み（TP は 2026-04-09 の `d6f303004`、
  allreduce.cu は 2026-05-10 の `f3c3e0e9a` で導入）なので、**計測自体は既存ビルドでも成立する**。

### Phase 4 — ツール転送と設定（3 分）

```bash
rsync -a --exclude .git --exclude runs --exclude __pycache__ src/llama-split-bench/ t120h-p100:~/llama-split-bench/
ssh -n t120h-p100 'cd ~/llama-split-bench && mkdir -p runs && ./list-devices.sh ~/llama.cpp/build/bin/llama-server'
```

`~/llama-split-bench/bench.local.conf`（WS で書いて scp する）:

```bash
BIN=$HOME/llama.cpp/build/bin/llama-server
MODEL=<Phase 2 で確定した GGUF の絶対パス>
DEVICES=CUDA0,CUDA1,CUDA2,CUDA3
MODES=( "layer|CUDA0,CUDA1,CUDA2,CUDA3|layer" \
        "tensor|CUDA0,CUDA1,CUDA2,CUDA3|tensor" \
        "layer2|CUDA0,CUDA1|layer" )
BASELINE=layer2
CTX=131072
STAGES=0,16000,32000,64000,128000
N_PREDICT=1000
PP0_SIZES=512,2048,8192
THREADS=16
SPEC_ARGS=""            # Qwen3.6-35B-A3B は非 MTP。既定の draft-mtp を外す
EXTRA_ARGS=""           # -b/-ub は指定しない（手本と同一条件）
LAUNCH_PREFIX=""        # Phase 5 の結果次第で "env GGML_CUDA_ALLREDUCE=none"
VENV_PY=/usr/bin/python3   # 作図は WS 側で行うのでここに matplotlib は不要
MACHINE="t120h-p100 - Tesla P100-PCIE-16GB x4 (sm_60, PCIe, no NVLink)"
```

### Phase 5 — tensor 起動プローブ（10〜20 分）★分岐ポイント

`run-bench.sh` の外で手動で起動し、ハング時に自分の管理下で kill するため単独実施する。ctx=8192 で起動可否だけを見る。

```bash
ssh -n -f t120h-p100 "cd ~ && setsid nohup ~/llama.cpp/build/bin/llama-server -m <MODEL> \
  --host 127.0.0.1 --port 18099 --device CUDA0,CUDA1,CUDA2,CUDA3 --split-mode tensor \
  -ngl all -fa on -c 8192 --parallel 1 -t 16 --jinja --cache-type-k q8_0 --cache-type-v q8_0 \
  > /tmp/tp-probe.log 2>&1 < /dev/null &"
ssh -n t120h-p100 'for i in $(seq 1 36); do curl -s -m 2 http://127.0.0.1:18099/health && break; sleep 5; done; echo'
ssh -n t120h-p100 'nvidia-smi --query-gpu=index,utilization.gpu,utilization.memory --format=csv,noheader; tail -5 /tmp/tp-probe.log'
ssh -n t120h-p100 'pkill -x llama-server; sleep 5; ~/llama.cpp/build/bin/llama-server --list-devices 2>&1 | head -8'
```

判定（各 3 回まで。**毎回 `--list-devices` で CUDA の健全性を確認**してから次へ）:

| 結果 | 対応 |
|---|---|
| NCCL 既定で 2/3 以上成功 | `LAUNCH_PREFIX=""` のまま本計測（手本と同じ NCCL 経路） |
| NCCL が 0〜1/3 | `LAUNCH_PREFIX="env GGML_CUDA_ALLREDUCE=none"` で再プローブ。layer 腕では不活性なので全腕一律で安全 |
| `none` でも起動しない | **中止して報告**（tensor 腕なしでは目的不成立） |
| `LLAMA_SPLIT_MODE_TENSOR not implemented for architecture` | **即中止**（arch ブラックリスト。回避策なし。MoE 初挑戦なのでありうる） |
| `failed to initialize CUDA: unknown error` | iLO の電源サイクルで復旧を 1 回試す（`rmmod nvidia_uvm` は sudo が要るので実行しない）。直らなければ報告 |

利用率 100% / メモリ利用率 0% ならスピンカーネル＝AllReduce 待ちで、既知の NCCL ハングと同定できる。

### Phase 6 — VRAM プリフライト（15〜25 分）★ベースライン腕の確定

危険な腕を最後に置く（途中で ABORT すると後続が走らないため）。`run-bench.sh` が各腕の起動直後に
`nvidia-smi` の `memory.used` を出すので、これをそのまま計測器に使う。

```bash
ssh -n t120h-p100 "cd ~/llama-split-bench && bash run-bench.sh preflight-1 --ctx 131072 \
  --stages 0,8000 --n-predict 32 --pp0-sizes 8192 --no-real \
  --mode-spec 'layer4|CUDA0,CUDA1,CUDA2,CUDA3|layer' \
  --mode-spec 'tensor4|CUDA0,CUDA1,CUDA2,CUDA3|tensor' \
  --mode-spec 'layer2|CUDA0,CUDA1|layer' 2>&1 | tail -40"
```

見積（`-ub 512`、重み 20.8 GiB、KV 合計 1.2〜1.7 GiB ※このモデルは hybrid で KV が小さく、
**VRAM の律速は KV ではなく ub 比例の compute buffer**）:

| 構成 | 合計/枚（保守） | 16 GiB に対する判定 |
|---|---:|---|
| 4 枚 layer | 6.5〜7.1 GiB | ◎ |
| 4 枚 tensor | 7.0〜8.0 GiB | ◎ |
| **2 枚 layer** | **12.1〜13.2 GiB** | ○ 収まる見込み（要実測） |
| 3 枚 layer（fallback） | 8.3〜8.9 GiB | ◎ |

判定基準（2 枚 layer のロード後ピーク）: **≤13,300 MiB なら `layer2` 採用** / 13,300〜14,800 MiB なら
深部プロンプトを 1 本通して再確認 / **>14,800 MiB か失敗なら `layer3`（3枚）に切替**。
`layer2` を第一候補にするのは、手本の最大の発見であるパネル④「layer 分割は速度ではなく VRAM を買う」を
再現するには枚数比が大きいほど良い（2→4 枚 = 2.0 倍、3→4 枚 = 1.33 倍では誤差に埋もれる）ため。
4 枚 layer すら載らない場合のみ全腕 ctx=65536 に落とし、手本との非同一性をレポートに明記する。

### Phase 7 — スモーク（5〜8 分）

```bash
ssh -n t120h-p100 "cd ~/llama-split-bench && bash run-bench.sh smoke --modes layer,tensor \
  --stages 0,4000 --n-predict 100 --ctx 8192 --pp0-sizes 512,2048 --no-real 2>&1 | tail -25"
```

`BENCH-DONE` または `BENCH-FIGFAIL`（作図だけ失敗＝WS 作図方針では想定内）なら合格。

### Phase 8 — 本計測（70〜110 分、detached）

```bash
ssh -n t120h-p100 "cd ~/llama-split-bench && setsid nohup bash run-bench.sh p100-4way-1 \
  > runs/p100-4way-1.log 2>&1 < /dev/null &"
ssh -n t120h-p100 'until grep -qE "BENCH-(DONE|ABORT|FIGFAIL)" ~/llama-split-bench/runs/p100-4way-1.log; do sleep 60; done; \
  tail -20 ~/llama-split-bench/runs/p100-4way-1.log'
```

腕単位のやり直しは `--modes <腕> --reuse` で可能（中断再開の機構は無い）。tensor 腕が途中でハングしたら
`pkill -x llama-server` → `--list-devices` で健全性確認 → `LAUNCH_PREFIX` を `none` に変えて当該腕のみ再実行。

### Phase 9 — 回収と作図（WS 側、10 分）

```bash
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
DIR=report/attachment/${TS}_t120h_p100_split_mode_layer_vs_tensor
mkdir -p $DIR
rsync -a t120h-p100:~/llama-split-bench/runs/p100-4way-1/ $DIR/run/

# WS に日本語フォントを入れる（sudo 不要。matplotlib のキャッシュ削除まで必須）
mkdir -p ~/.fonts && curl -sL -o ~/.fonts/NotoSansCJKjp-Regular.otf \
  'https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf'
fc-cache -f ~/.fonts && rm -rf ~/.cache/matplotlib

for L in ja en; do
  python3 src/llama-split-bench/plot_bench.py --dir $DIR/run --series layer,tensor,layer2 \
    --baseline layer2 --vs on --lang $L --out split-bench
done
```

### Phase 10 — レポート作成（30 分）

`REPORT.md` の規約に従い `report/${TS}_t120h_p100_split_mode_layer_vs_tensor.md` を作成する。

- H1 は 50 字以内の平易な日本語、`## 概要` を最上部に 5〜8 段落
- `## 核心発見サマリ` の冒頭に日本語 PNG を `![...]()` で画像埋め込み → 直後に `**結論**:`
- `## 添付ファイル` に `[実装プラン](attachment/.../plan.md)`（本ファイルをコピー）と `run/` 一式
- 必ず記載する条件: **ビルド（`465e49b9c` か既存 9690 か）とバイナリ sha256 / NCCL の有無と実際に使った
  AllReduce 経路 / `-ub 512`（本番の `-ub 4096` と異なる）/ ベースライン腕（layer2 か layer3 か）**
- 手本レポート（aws-gpu01 P100×7 / dense 27B）との比較を 1 節設け、**MoE での初データである**ことを明示
- 参照レポートに手本 3 本（`2026-09-14_104905` / `2026-09-14_142115` / `2026-09-16_103619`）と
  先行する `2026-04-22_165843`（同機の `row` vs `layer`）を挙げる
- 終了後、**電源断とロック解放はユーザの指示を得てから**行う（通電・ロック保持のまま報告する）

## 中止条件

| # | 事象 | 対応 |
|---|---|---|
| 1 | SSH が 15 分来ない | KVM スクショ保全 → 報告 |
| 2 | ロックを他セッションが保持 | 即報告（電源も落とさない） |
| 3 | GGUF がサーバに無い | **報告して指示待ち**（ユーザ判断 3） |
| 4 | tensor が arch 非対応 | 即報告（回避策なし） |
| 5 | tensor が NCCL / none の両方で起動しない | 各 3 回試して報告 |
| 6 | CUDA 破損が電源サイクルで直らない | 報告（`rmmod` は sudo が要るので実行しない） |
| 7 | ビルドが 2 回失敗 | `build.bak-*` を戻し、既存ビルドで続行するかを確認 |
| 8 | 2 枚 layer が載らない | `layer3` に切替（中止しない） |
| 9 | 総経過が 6 時間超 | 取れた範囲で打ち切りレポート |

## 実行時の注意（既知の地雷）

- `pkill -f` は使わない（リモート側 bash に自己マッチして exit 255）。必ず `pkill -x llama-server`。
- `ssh ... & disown` は使わない。`ssh -n -f ... setsid nohup ... < /dev/null &` の形にする。
- `tail -f` で待たない。完了マーカーを 60 秒間隔でポーリングする。
- 本番 llama-server（8000 番）を同時に立てない（外部プロセスガードが ladder を abort する）。
- 同一タグの再実行は拒否される。やり直しは `--reuse` か新タグ。
- スクリプトは**プロジェクトルートからの相対パス**で実行する。

## 検証

1. `runs/p100-4way-1/run-info.json` に 3 腕・バイナリ sha256・`launch_prefix` が記録されていること。
2. `results-{layer,tensor,layer2}.json` と `-pp0.json`、`results-real.json` が揃い、
   各段の `predicted_per_second` / `prompt_per_second` が欠測なく並ぶこと。
3. `split-bench-ja.png` / `-en.png` が 4 パネルとも描画され、日本語が豆腐になっていないこと。
4. `sampler-*.log` から腕ごとの GPU 利用率・温度・電力の平均が出せること（手本は利用率が
   layer 27.5% 対 tensor 75.9% で、decode 差の説明になっていた）。
5. レポートが `REPORT.md` の必須セクション（`## 概要` 最上部、核心発見サマリの PNG 埋め込み、
   実装プラン添付）を満たすこと。
