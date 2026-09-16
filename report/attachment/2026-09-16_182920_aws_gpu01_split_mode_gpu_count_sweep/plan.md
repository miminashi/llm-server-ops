# aws-gpu01 split-mode ベンチを GPU 2→7 枚でスイープする

## Context

2026-09-14 の [layer vs tensor レポート](../../projects/llm-server-ops/report/2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor.md) は、
aws-gpu01（Tesla P100-PCIE-16GB ×7、sm_60、PCIe、NVLink なし）で 3 腕（7枚 layer / 7枚 tensor / 2枚 layer）を測り、

1. tensor 分割が prefill / decode の全深度・全指標で layer 分割を上回る
2. **layer 分割は枚数を 2→7 に増やしても decode が改善しない（-4〜-7%）＝「速度ではなく VRAM を買う」**

と結論した。2 は本プロジェクトで 3 セッション連続して再現している強い主張だが、**根拠は 2 枚と 7 枚の 2 点だけ**で、
その間（3/4/5/6 枚）がどう振る舞うかは未測定である。同様に tensor 分割が枚数に対してどうスケールするかも 7 枚の 1 点しかない。

本作業は**同一バイナリ・同一モデル・同一ワークロードのまま、GPU 枚数を 2→7 まで 1 枚刻みでスイープ**して、
両分割方式のスケーリング曲線を埋める。既存の 2 枚 / 7 枚の値がスイープ曲線の両端として再現するかどうかが、
そのまま本計測の妥当性チェックになる。

**ユーザが選んだ条件**（AskUserQuestion で確認済み）:

| 項目 | 選択 |
|---|---|
| モード | **layer + tensor の両方**（12 腕） |
| 投機デコード (MTP) | **無効**（`SPEC_ARGS=""` ＝ 2026-09-14 10:49 と同条件） |
| ワークロード | **既存と完全に同一**（ctx=131072 / stages 0,16000,32000,64000,128000 / n-predict 1000 / pp0 512,2048,8192） |

---

## 事前に確定させた事実（調査済み）

| 項目 | 内容 |
|---|---|
| aws-gpu01 の状態 | **電源 OFF**（BMC `System Power: off`）。**投入にはユーザの明示許可が要る**（本プランの承認をもって許可とする） |
| aws-gpu02 | `P1_DIMMA2` 故障で起動不能。**一切触れない**。ロックも取らない（09-16 の先例に合わせる） |
| ツール | `~/llama-split-bench`（ローカル参照は `src/llama-split-bench/`、HEAD `7af72d4`）。**無改造で足りる** |
| モード数の上限 | **無し**（`MODES` 配列を回すだけ）。名前は一意・カンマ不可・`gpu`/`single` を含めない（`plot_bench.py:48` が凡例ラベルを名前で判定する） |
| **作図の色は 9 系列まで** | `plot_bench.py:32-41`。固定色は `layer`/`tensor`/`single`/`tp2p` の 4 つ、残りは 5 色のフォールバックを `len(COL)%5` で払い出す。**カスタム名だけ 6 腕並べると 1 番目と 6 番目が同色になる** → 7 枚の腕を `layer` / `tensor`（固定色）と名付けて回避する。この命名は 09-14 / 09-16 の腕名とも一致する |
| パネル④ | 6 系列では棒幅 0.08・ラベル 5.2pt で**判読不能**（`plot_bench.py:271,291`）。**`VS_PANEL=off` にして、枚数軸の図は自前で描く** |
| 失敗時の挙動 | `run_measure()` が**非ゼロ終了で run 全体を即 abort**（`run-bench.sh:135-143`）。自動再開は無い。**`--reuse --modes <残り>` が事実上の再開手段**で、ステージごとに JSON が書き出される（`measure_ladder.py:219-220`）ので既測分は失われない |
| 再開の副作用 | `--reuse` すると `run-info.json` と最終作図が**再開分の腕だけ**で上書きされる（`run-bench.sh:224,275`）。全腕の図は `plot_bench.py` を手で叩いて作り直す |
| env 注入口 | `LAUNCH_PREFIX`（`bench.conf:7` → `run-bench.sh:158-159`）。**run 全体でグローバル**で腕別に変えられない。`run-info.json` の `launch_prefix` と `argv-*.txt` 先頭に証跡が残る |
| tensor 腕の必須 env | **`GGML_CUDA_ALLREDUCE=none`**。既定の NCCL 経路は起動時ハングで**7 枚 0/13・2 枚 1/12** と実質起動不能（[NCCL ハングレポート](../../projects/llm-server-ops/report/2026-09-14_142115_aws_gpu01_tensor_split_nccl_hang.md), [3 腕再測定](../../projects/llm-server-ops/report/2026-09-16_103619_aws_gpu01_split_mode_mtp_3arm.md)）。`butterfly` は不正値なので使わない |
| layer 腕での不活性 | `--split-mode layer` では `ggml_backend_cuda_comm_init` 自体が呼ばれず、不正値でも警告すら出ない（09-16 実測）。**全腕に一律で `LAUNCH_PREFIX` を掛けてよい** |
| ラダーの所要時間 | `T ≈ max(STAGES)/prefill_tps + len(STAGES)×N_PREDICT/decode_tps`（prefill はキャッシュ再利用で合計 128k トークンぶんのみ） |
| 実プロンプト補正 | `REAL_MODE=auto` は**名前が厳密に `tensor` の腕**を選び、無ければ `SEL[0]`（`run-bench.sh:92-97`）。1 run につき 1 腕のみ |
| 停止コマンド | **`pkill -x llama-server`**（`pkill -f` はリモート bash に自己マッチして exit 255） |
| 失敗判定の注意 | `abort` / `failed to` を grep しない（tensor 分割は正常時も `llama_params_fit is not implemented for SPLIT_MODE_TENSOR, abort` を出す）。成功は `"status":"ok"` / `listening on` |
| CUDA 破損の罠 | ハングした llama-server を kill すると `nvidia_uvm` の参照が残り `ggml_cuda_init: failed to initialize CUDA: unknown error` になることがある。復旧は `sudo rmmod nvidia_uvm && sudo modprobe nvidia_uvm`（要ユーザ許可）。`nvidia-smi` は正常に見えるので気づきにくい |
| sudo | 本作業では**原則不要**。上記の CUDA 復旧が必要になった場合のみユーザに依頼する |

---

## 計測設計

### 腕（12 本）

`bench.local.conf` の `MODES` に 12 腕すべてを定義し、run ごとに `--modes` で絞る。デバイスは `CUDA0` から順に使う。

| 腕名 | デバイス | split | 備考 |
|---|---|---|---|
| `layer2` | CUDA0,CUDA1 | layer | **ベースライン**。09-14 / 09-16 と同一条件 |
| `layer3` 〜 `layer6` | CUDA0..CUDA(N-1) | layer | 新規 |
| `layer` | CUDA0..CUDA6 | layer | **09-14 の `layer` 腕と同一**（再現性チェック） |
| `tensor2` | CUDA0,CUDA1 | tensor | 新規 |
| `tensor3` 〜 `tensor6` | CUDA0..CUDA(N-1) | tensor | 新規 |
| `tensor` | CUDA0..CUDA6 | tensor | **09-16 の切り分け腕（`none`・MTP 無効）と同一条件**（再現性チェック） |

7 枚の腕を `layer` / `tensor` と名付けるのは、(a) 作図の固定色枠を確保して 6 系列の色衝突を避けるため、(b) 過去 3 レポートの腕名と揃えるため。

### run の分割

**2 タグに分ける**（12 腕を 1 タグにすると、1 腕の失敗で 6 時間ぶんが飛ぶため）。

| タグ | 腕 | 想定所要 |
|---|---|---|
| `gpu01-sweep-layer` | `layer2,layer3,layer4,layer5,layer6,layer` | **約 2 時間 20 分** |
| `gpu01-sweep-tensor` | `tensor2,tensor3,tensor4,tensor5,tensor6,tensor` | **約 2 時間 50 分 〜 3 時間 30 分** |

layer を先に回す。既存レポートの `layer` / `layer2` を早い段階で再現できるので、
セッション跨ぎの比較可能性を tensor に 3 時間かける前に検証できる。

### `bench.local.conf`（サーバ側を全文で置き換える）

```bash
# aws-gpu01 — Tesla P100-PCIE-16GB x7, sm_60 / GPU 枚数スイープ (2026-09-16)
BIN=$HOME/llama.cpp/build/bin/llama-server
MODEL=$HOME/models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf
DEVICES=CUDA0,CUDA1,CUDA2,CUDA3,CUDA4,CUDA5,CUDA6

MODES=( "layer2|CUDA0,CUDA1|layer" \
        "layer3|CUDA0,CUDA1,CUDA2|layer" \
        "layer4|CUDA0,CUDA1,CUDA2,CUDA3|layer" \
        "layer5|CUDA0,CUDA1,CUDA2,CUDA3,CUDA4|layer" \
        "layer6|CUDA0,CUDA1,CUDA2,CUDA3,CUDA4,CUDA5|layer" \
        "layer|CUDA0,CUDA1,CUDA2,CUDA3,CUDA4,CUDA5,CUDA6|layer" \
        "tensor2|CUDA0,CUDA1|tensor" \
        "tensor3|CUDA0,CUDA1,CUDA2|tensor" \
        "tensor4|CUDA0,CUDA1,CUDA2,CUDA3|tensor" \
        "tensor5|CUDA0,CUDA1,CUDA2,CUDA3,CUDA4|tensor" \
        "tensor6|CUDA0,CUDA1,CUDA2,CUDA3,CUDA4,CUDA5|tensor" \
        "tensor|CUDA0,CUDA1,CUDA2,CUDA3,CUDA4,CUDA5,CUDA6|tensor" )
BASELINE=layer2
VS_PANEL=off          # 6 系列ではパネル④が判読不能。枚数軸の図は plot_sweep.py で描く

CTX=131072
STAGES=0,16000,32000,64000,128000
N_PREDICT=1000
PP0_SIZES=512,2048,8192

THREADS=16
SPEC_ARGS=""          # MTP 無効（2026-09-14 10:49 と同条件）

VENV_PY=$HOME/.venvs/bench-plot/bin/python
MACHINE="aws-gpu01 - Tesla P100-PCIE-16GB x7 (sm_60, PCIe, no NVLink)"

# --split-mode tensor の起動時 NCCL ハング回避。layer 腕では完全に不活性（09-16 実測）。
LAUNCH_PREFIX="env GGML_CUDA_ALLREDUCE=none"
```

**09-14 からの変更点は「腕の構成」と「`LAUNCH_PREFIX` の追加」の 2 点だけ**。バイナリ・モデル・KV 型・ctx・
ステージ・生成トークン数・pp0 サイズ・スレッド数・`SPEC_ARGS` はすべて同一に保つ。

---

## 手順

### Phase 0: 準備（約 15 分）

1. `.claude/skills/gpu-server/scripts/lock.sh aws-gpu01` でロック取得
2. **電源投入**: `ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 on`
   （aws-gpu02 には触れない。POST 中もファンは `boot-quiet.sh` 併走で 2,900rpm 台）
3. SSH 疎通を待ってから**ロックを取り直す**（`/tmp` が消えるため）
4. 環境の同一性を確認 — バイナリ sha256 が `ca54f4dd…8593886`、モデルのサイズが `17,559,178,144`、
   `~/.venvs/bench-plot` と `~/.fonts/NotoSansCJKjp-Regular.otf` が残っていること。
   欠けていれば [09-14 レポートの再現方法](../../projects/llm-server-ops/report/2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor.md) の手順で作り直す
5. `rsync -a --exclude .git --exclude runs src/llama-split-bench/ aws-gpu01:~/llama-split-bench/` でツールを同期し、
   上記 `bench.local.conf` を書き込む

### Phase 1: スモーク + プリフライト（約 25 分）

1. **12 腕すべてのスモーク**（約 20 分）。6 時間の本計測に入る前に、全腕が起動して計測経路を通ることを確かめる:
   ```bash
   bash run-bench.sh smoke-sweep --modes layer2,layer3,layer4,layer5,layer6,layer,tensor2,tensor3,tensor4,tensor5,tensor6,tensor \
     --stages 0,4000 --n-predict 100 --ctx 8192 --pp0-sizes 512 --no-real
   ```
2. **`tensor2` の ctx=131072 プリフライト**（約 3 分）。2 枚 tensor は VRAM がいちばん厳しい未検証構成なので、
   実際に ctx=131072 で起動して `/health` と各カードの VRAM を確認し、`pkill -x llama-server` で落とす
3. `server-*.log` に `unknown GGML_CUDA_ALLREDUCE value` の警告が **0 件**であることを確認

### Phase 2: layer スイープ本計測（約 2 時間 20 分）

```bash
ssh -n aws-gpu01 "cd ~/llama-split-bench && setsid nohup bash run-bench.sh gpu01-sweep-layer \
  --modes layer2,layer3,layer4,layer5,layer6,layer > runs/gpu01-sweep-layer.log 2>&1 < /dev/null &"
```

- 監視は `runs/<tag>.log` の `BENCH-(DONE|ABORT|FIGFAIL)` マーカーと `status-<mode>.txt` をポーリング（`tail -f` は使わない）
- **完了後のチェックポイント**: `layer` 腕と `layer2` 腕が 09-14 の値（`layer` 初段 11.26 / 最深 6.23、`layer2` 初段 12.11 / 最深 6.57 t/s）を
  **±5% 以内で再現**しているか。外れていたら原因を調べてから Phase 3 に進む（サーマル、バイナリ差、他プロセスの混入）

### Phase 3: tensor スイープ本計測（約 2 時間 50 分〜3 時間 30 分）

```bash
ssh -n aws-gpu01 "cd ~/llama-split-bench && setsid nohup bash run-bench.sh gpu01-sweep-tensor \
  --modes tensor2,tensor3,tensor4,tensor5,tensor6,tensor > runs/gpu01-sweep-tensor.log 2>&1 < /dev/null &"
```

- **チェックポイント**: `tensor` 腕が 09-16 の切り分け腕（`none`・MTP 無効、初段 13.81 / 最深 13.50 t/s、pp512 83.8 t/s）を再現しているか
- 途中で 1 腕が abort したら、`--reuse --modes <残り>` で続きを回す（既測腕の JSON は残る）

### Phase 4: 集計・作図（約 30 分）

1. `rsync` で両タグの `runs/` をワークステーションへ回収
2. **枚数軸の図 `plot_sweep.py` を新規作成**（前回の `plot_mtp2.py` / `plot_tensor.py` と同じ流儀。
   CJK フォントはサーバ側にしかないので、スクリプトを送って `VENV_PY` で実行する）。6 パネル構成:

   | パネル | 内容 |
   |---|---|
   | ① | **decode t/s vs 枚数** — layer 実線 / tensor 破線、最浅（11 tok）と最深（128,793 tok）の 2 深度 |
   | ② | **増分 prefill t/s vs 枚数** — 同上（深さ 15,825 と 128,793） |
   | ③ | **depth-0 prefill vs 枚数** — pp512 / pp2048 / pp8192 を layer / tensor で |
   | ④ | **2 枚基準のスケーリング効率** — decode・prefill の対 2 枚比に理想線 `y = N/2` を重畳 |
   | ⑤ | **GPU 利用率平均 vs 枚数**（`sampler-*.log` 集計。使用中のカードのみ） |
   | ⑥ | **VRAM 合計 / 1 枚あたり vs 枚数**（`runs/<tag>.log` の `nvidia-smi` 行から） |

   日本語版・英語版の 2 枚を出す
3. ツール標準の `split-bench-{ja,en}.png` は各タグぶんそのまま添付（6 系列・パネル④無し）
4. サンプラ集計は前回の [`sampler.py`](../../projects/llm-server-ops/report/attachment/2026-09-16_103619_aws_gpu01_split_mode_mtp_3arm/sampler.py)、
   表生成は [`tables.py`](../../projects/llm-server-ops/report/attachment/2026-09-16_103619_aws_gpu01_split_mode_mtp_3arm/tables.py) を流用・拡張する

### Phase 5: レポート作成（約 40 分）

- ファイル名: `report/$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)_aws_gpu01_split_mode_gpu_count_sweep.md`
- [REPORT.md](../../projects/llm-server-ops/REPORT.md) に従う。**`## 概要` を H1 とメタ情報の直下に置き、5〜8 段落の通読可能な日本語で書く**。
  タイトルは 50 字以内・数値を詰め込まない。`## 核心発見サマリ` の冒頭に枚数軸 PNG を画像埋め込みし、直後に `**結論**:` 段落
- **必ず明記する caveat**: 本スイープの tensor 腕は **`GGML_CUDA_ALLREDUCE=none` 経路**であり、
  09-14 レポートの tensor 値（NCCL 経路、prefill 3〜5 倍速い）とは**直接比較できない**。
  同一 N での layer vs tensor の比較もこの前提つきで読む必要がある
- 添付: `attachment/<レポート名>/` に `plan.md`（本プランのコピー）、両タグの `runs/`、`bench.local.conf`、
  `plot_sweep.py`、集計スクリプト、図
- 既存 3 レポートへの相互リンクを `## 参照レポート` に張る。あわせて
  [09-14 レポート](../../projects/llm-server-ops/report/2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor.md) の概要冒頭に、
  先例（09-16 の追記）と同じ体裁で**スイープ結果への追記を 1 ブロック足す**

### Phase 6: 後片付け

- `git add` + コミット（`docs(report): ...` 形式。`.githooks` の巨大ファイル検出が有効か確認し、
  100 MB 超があれば `gzip`。今回は数 MB 見込みなので問題にならない）
- **電源とロック**: 落とすかどうかは**ユーザに確認してから**。落とす場合は
  `ALLOW_FAN_NOISE=1 bmc-power.sh aws-gpu01 soft` → `status` で off 確認 → `unlock.sh aws-gpu01`

---

## 所要時間の見積もり（重要）

質問時に「約 5 時間」と示したが、ツールのコードと過去 3 レポートの実測から積み直すと**より長い**。

| フェーズ | 見積 |
|---|---|
| Phase 0 準備・電源投入 | 15 分 |
| Phase 1 スモーク + プリフライト | 25 分 |
| Phase 2 layer スイープ 6 腕 | **2 時間 20 分** |
| Phase 3 tensor スイープ 6 腕 | **2 時間 50 分 〜 3 時間 30 分** |
| Phase 4 集計・作図 | 30 分 |
| Phase 5 レポート作成 | 40 分 |
| **合計** | **約 6 時間 40 分 〜 7 時間 20 分** |

根拠: `T_arm ≈ 128000/prefill_tps + 5000/decode_tps + ロード等 3 分`。
layer は 09-14 実測の prefill 140（2枚）〜290（7枚）t/s を線形補間して 6 腕 138 分。
tensor は `none` 経路の 7 枚実測（prefill 83 t/s・35 分／腕）と、2 枚のほうが速いという
[NCCL ハングレポート](../../projects/llm-server-ops/report/2026-09-14_142115_aws_gpu01_tensor_split_nccl_hang.md)の傍証から 20〜35 分／腕。

大半は無人待ちだが、**もし時間を削るなら tensor スイープを 2,4,7 枚の 3 点に間引く**のが最も効く（約 1 時間 40 分の短縮）。
その場合でも layer 側は 6 点すべて取る（こちらが本作業の主目的のため）。

---

## リスクと対処

| リスク | 兆候 | 対処 |
|---|---|---|
| `tensor2` が ctx=131072 で VRAM 不足 | 起動中に OOM / `server not ready` | Phase 1 のプリフライトで**本計測の前に**検出する。落ちたら tensor スイープは 3 枚以上に切り替え、その旨をレポートに書く |
| `none` 経路でも起動ハングする枚数がある | `BENCH-ABORT: <name> server not ready`（最大 10 分待ち） | その腕を飛ばして `--reuse --modes <残り>` で継続。**ハングした腕の枚数は新発見として記録する**（`none` の起動率は 2 枚 15/15・7 枚 3/3 しか実績がない） |
| ハング kill 後に CUDA が壊れる | `ggml_cuda_init: failed to initialize CUDA: unknown error` / `--list-devices` が `(none)` | `sudo rmmod nvidia_uvm && sudo modprobe nvidia_uvm` を**ユーザに依頼**。次の腕に進む前に `--list-devices` で CUDA が生きていることを確認する |
| 外部プロセスが計測 GPU に載る | `measure_ladder.py` のガードが即 ABORT | 他セッションがロックを無視していないか確認。`lock-status.sh` を随時見る |
| 再開時に図と `run-info.json` が壊れる | `--reuse` の副作用 | 全腕そろってから `plot_bench.py --dir runs/<tag> --series <全腕>` を手で叩き直す |
| 6〜7 時間のあいだにセッションが切れる | — | 本計測は `setsid nohup` で detach 済み。復帰後は `runs/<tag>.log` のマーカーと `status-*.txt` から状態を復元できる |

---

## 完了条件

1. `gpu01-sweep-layer` / `gpu01-sweep-tensor` の 12 腕（または欠測の理由が明記された腕）の
   `results-*.json` / `results-*-pp0.json` / `sampler-*.log` / `argv-*.txt` / `server-*.log` が揃っている
2. `layer` / `layer2` が 09-14 の値を ±5% で再現し、`tensor` が 09-16 の `none` 腕を再現していることを確認済み
3. 枚数軸の図（日本語・英語）が生成され、レポートの「核心発見サマリ」冒頭に埋め込まれている
4. レポートが [REPORT.md](../../projects/llm-server-ops/REPORT.md) の必須セクションを満たし、`plan.md` が添付されている
5. tensor 腕が `none` 経路であるという caveat がレポート本文に明記されている
6. コミット済み。電源・ロックの扱いをユーザに確認済み

---

## 実施後の追記（2026-09-16 19:05 JST）

プランからの逸脱・追加は 3 点。

1. **機構プローブを追加**（計画外、約 10 分）。layer の prefill に「2 枚 = 3 枚」という段差が出たため、本計測後に `-lv 4` で
   2〜7 枚を立ち上げ `n_batch` / `n_ubatch` / `pipeline parallelism` / `graph splits` を直接読んだ。3 つとも枚数に応じて
   期待どおり変化しており段差を説明しない（未解明として報告）。**計測中は GPU ガードが ABORT するので本計測後に実施する必要がある**。
2. **同一 PCIe スイッチ 4 枚の追試を追加**（計画外、18 分）。tensor の枚数依存を PCIe トポロジで説明する記述をレポートに
   書く以上、検証せずに残課題へ送るのは弱いと判断した。`--mode-spec` で `tensor4b|CUDA3,CUDA4,CUDA5,CUDA6|tensor` を 1 腕だけ実行。
   **decode +20%（浅部）で、本調査の最速構成になった**。
3. **監視方法の変更**。長時間の `ssh ... sleep` をバックグラウンドに積み上げたところ、ワークステーションのメモリ不足で
   監視プロセスが kill された（ベンチ本体はサーバ側 `setsid nohup` なので無傷）。以降はフォアグラウンドの 9 分待機に切り替えた。

所要は見積 6時間40分〜7時間20分に対し **実績 約 6 時間**（13:00〜19:05）。tensor スイープが見積より速かった（枚数が増えると
性能が落ちるぶん所要が伸びると予想したが、2〜5 枚が速かったため相殺された）。
