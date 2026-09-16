# aws-gpu01 split-mode × MTP ベンチの 3 腕フル再測定

## Context

2026-09-14 の一連の作業で、aws-gpu01（Tesla P100 ×7）の split-mode 比較レポートが 3 本作られた。

1. [104905 layer vs tensor](../../projects/llm-server-ops/report/2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor.md) — MTP 無効で 3 腕（layer / tensor / layer2）を測り、**tensor が全面的に優位**と結論。
2. [124457 MTP](../../projects/llm-server-ops/report/2026-09-14_124457_aws_gpu01_split_mode_mtp.md) — MTP を有効にして再測定。**tensor 腕が起動ハングで欠測**し、layer / layer2 の 2 腕だけになった。「MTP と tensor は併用できない」と結論。
3. [142115 NCCL ハング](../../projects/llm-server-ops/report/2026-09-14_142115_aws_gpu01_tensor_split_nccl_hang.md) — 2 の結論が誤りと判明。ハングは **MTP と無関係な `--split-mode tensor` 単独の起動時 NCCL AllReduce 不具合**で、`GGML_CUDA_ALLREDUCE` を切り替えれば消える（NCCL 経路 1/15 に対し非 NCCL 経路 15/15、Fisher p = 9.6e-06）。回避策込みで tensor + MTP の実推論が完走することも確認済み。

本作業は **3 の知見（回避策）を使って 2 のベンチマークを 3 腕そろえて実施し直す**もの。2 のレポート自身が残課題に「MTP 有効での tensor 腕の正式な再測定。これにより『MTP は tensor の代替にならない』という結論を同一条件の 3 腕で検証し直せる」と書いており、それに正面から応える。

**期待される成果**: MTP on/off × split-mode(layer / tensor / layer2) の 2×3 が同一バイナリ・同一ワークロードでそろう。とくに「tensor に MTP を足すと速くなるのか遅くなるのか」は現時点で完全に未知（3 のレポートの実推論は ctx=8192 の単発測定で、深度ラダーではない）。

---

## 事前に確定させた事実（調査済み）

| 項目 | 内容 |
|---|---|
| aws-gpu01 の状態 | **電源 OFF**（BMC `System Power: off`、ping 不通）。ユーザから投入許可を取得済み |
| ロック | `lock-status.sh` で aws-gpu01 は UNREACHABLE。t120h-p100 が別セッションに LOCKED（無関係） |
| ツール | `~/llama-split-bench`（ローカル参照は `src/llama-split-bench/`、HEAD `7af72d4`） |
| **env 注入口** | `bench.conf:7` の **`LAUNCH_PREFIX`** が `ARGS` 先頭に展開される（`run-bench.sh:158-159`）。`run-info.json` の `launch_prefix` と `argv-*.txt` 先頭に記録される。**前回の `bench.local.conf` には `LAUNCH_PREFIX` 行が無い** |
| **`butterfly` は不正値** | `ggml-cuda.cu:1228-1248` を実機と同一コミット `465e49b9c` のローカルツリーで確認。有効値は **`nccl` / `internal` / `none`** のみ。未知値は `unknown GGML_CUDA_ALLREDUCE value:` を警告して `comm_init_none` にフォールバック。**前レポートの `butterfly` は実質 `none` だった**（`evidence/probe-ar-butterfly.log` 冒頭に実際に警告が出ている）。本作業は正規の **`none`** を使う（同一コードパス・警告なし） |
| ready 判定 | `run-bench.sh:184-200`。`/health` の `"status":"ok"` を 120 回 × `sleep 5` = **最大約 10 分**待ち、**リトライなし**で `BENCH-ABORT: <name> server not ready` |
| REAL 腕 | `run-bench.sh:92-97` の `REAL_MODE=auto` は **`tensor` という名前の腕があれば必ずそれを選ぶ**。前回（tensor 欠測）は layer だったので、**今回は自動で tensor に変わる**＝前回と補正の取り方が変わる |
| 補正係数 | `plot_bench.py:148-155` / `plot_mtp.py:45-53`。`実プロンプト 3 本の decode 平均 ÷ 基準腕の深度 0 の合成 decode`。**全腕・全深度に一律適用** |
| `plot_mtp.py` | リポジトリには無く `report/attachment/2026-09-14_124457.../plot_mtp.py` が実体。腕名 `layer`/`tensor`/`layer2` はハードコードで**3 腕を描ける**が、**係数の基準腕が `layer` 固定**。suptitle に「tensor は MTP と併用するとハングするため MTP on の腕が無い」と**ベタ書き**されており書き換え必須 |
| 停止コマンド | **`pkill -x llama-server`**（`pkill -f` はリモート bash に自己マッチ）。SIGTERM で落ちない個体があるので `kill -9` フォールバック |
| 失敗判定 | `abort` / `failed to` を使わない（tensor 分割は正常時も `llama_params_fit is not implemented for SPLIT_MODE_TENSOR, abort` を出す）。成功は `listening on` / `"status":"ok"` |
| sudo | 本作業では不要（デバッグしない） |

---

## 計測設計

**前回（`gpu01-7way-mtp`）から変えるのは 2 点だけ**にして厳密な A/B を保つ。

| 項目 | 前回 | 今回 |
|---|---|---|
| バイナリ | `465e49b9c` / build 10830 / sha256 `ca54f4dd…8593886` | **同一**（再ビルドしない。sha256 で照合） |
| モデル・KV・ctx・stages・n_predict・pp0・threads | 同上 | **同一** |
| `SPEC_ARGS` | `--spec-type draft-mtp --spec-draft-n-max 2` | **同一** |
| 腕 | layer / layer2（tensor 欠測） | **layer / tensor / layer2 の 3 腕** ←変更点1 |
| env | なし | **`GGML_CUDA_ALLREDUCE=none`** ←変更点2 |

- タグ: `gpu01-7way-mtp2`
- 腕順は前回・前々回と同じ **layer → tensor → layer2**（GPU の熱履歴の順序も揃える。実測で最大 71℃ と余裕があるので影響は小さいが、揃えられるものは揃える）
- 実プロンプト補正は `REAL_MODE=auto` のまま＝**tensor 腕**で取得。前回は layer 腕だったので、**layer / layer2 の補正係数は本計測後に個別取得する**（下記 Phase 6）。これをやらないと前回レポートの 0.761 と今回の値が比較できず、かつ「MTP 込み tensor が MTP 無し tensor を超えるか」という本丸の問いに実運用ベースで答えられない

### `GGML_CUDA_ALLREDUCE` をどの腕に効かせるか

layer 分割では AllReduce 自体が走らないはずなので全腕に一律で渡して問題ないと予想されるが、**A/B の純度を守るため Phase 3 で実測して決める**。

- Phase 3 で layer 腕を `GGML_CUDA_ALLREDUCE=zzz-probe` で起動し、`server-*.log` に `unknown GGML_CUDA_ALLREDUCE value` が出るかを見る
- **出ない**（= layer では comm_init すら呼ばれない＝env は完全に不活性）→ `bench.local.conf` に `LAUNCH_PREFIX="env GGML_CUDA_ALLREDUCE=none"` を 1 行足すだけ。**ツール無改造**
- **出る** → `run-bench.sh:158` の直後に 1 行入れて tensor 腕だけに効かせる:
  ```bash
  if [ "$split" = tensor ] && [ -n "${SERVER_ENV_TENSOR:-}" ]; then
    PREFIX=(env $SERVER_ENV_TENSOR "${PREFIX[@]}")
  fi
  ```
  （`set -u` なので `${…:-}` は必須。`$SERVER_ENV_TENSOR` は複数変数を渡せるよう意図的に非クォート）。呼び出しは `SERVER_ENV_TENSOR='GGML_CUDA_ALLREDUCE=none' bash run-bench.sh …`。差分は `git diff` を証跡に残す

---

## 手順

### Phase 0 — 起動と占有（約 15 分）

```bash
cd /home/ubuntu/projects/llm-server-ops
.claude/skills/gpu-server/scripts/lock-status.sh aws-gpu01
.claude/skills/gpu-server/scripts/lock.sh aws-gpu01
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 on
# POST 約 146 秒 + OS 起動。boot-quiet.sh が併走して約 2,900rpm に収まる
until ssh -n -o ConnectTimeout=5 aws-gpu01 true 2>/dev/null; do sleep 20; done
.claude/skills/gpu-server/scripts/lock.sh aws-gpu01   # /tmp が消えるので再取得
```

- **aws-gpu02 には一切触れない**（`P1_DIMMA2` 故障で起動しない）
- 起動後にファン回転数を確認し、爆音が続くようなら `smc-fanctl` の状態を見る

### Phase 1 — 環境の同一性確認（約 5 分）

- `sha256sum ~/llama.cpp/build/bin/llama-server` = `ca54f4dd8a4750198b85ebf4bd195c580c77bc98bf1b772388581c1cd8593886`
- `~/llama.cpp/build/bin/llama-server --version` が `build 10830, commit 465e49b9c`
- `ls -l ~/models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf` が `17559178144` バイト
- `nvidia-smi` で 7 枚すべて見えること、VRAM が空いていること、`pgrep -x llama-server` が空
- `df -h ~` の空き、`ls ~/llama-split-bench/runs/`（既存タグ確認）
- **`bench.local.conf` の現在の内容**（`SPEC_ARGS` が MTP 版のままか、`nomtp-backup` があるか）
- `~/.venvs/bench-plot/bin/python -c "import matplotlib"` と `fc-list | grep -i "noto sans cjk"`

**一つでも食い違ったら本計測に入らず、原因を潰してから進む**（食い違ったままでは前回値との A/B が成立しない）。

### Phase 2 — 設定の投入（約 5 分）

`bench.local.conf` を前回の MTP 版（`report/attachment/2026-09-14_124457_aws_gpu01_split_mode_mtp/bench.local.conf`）と一致させる。差分は Phase 3 の結果次第で足す `LAUNCH_PREFIX` の 1 行だけ。作業前に現物を `bench.local.conf.bak-$(date +%s)` へ退避し、投入後に `diff` を取って証跡化する。

### Phase 3 — env 不活性テスト + tensor+MTP スモーク（約 15 分）

3-a. **env 不活性テスト**（2 分）: layer 2 枚・ctx=8192 で `GGML_CUDA_ALLREDUCE=zzz-probe` を付けて起動し、`unknown GGML_CUDA_ALLREDUCE value` の有無を確認 → 上記の分岐を決定。

3-b. **スモーク**（約 6 分）: 前回・前々回と同じ形。**tensor+MTP が起動することがここでの最大の確認事項**。
```bash
ssh -n aws-gpu01 "cd ~/llama-split-bench && <env> bash run-bench.sh smoke-mtp2 \
  --modes layer,tensor,layer2 --stages 0,4000 --n-predict 100 --ctx 8192 \
  --pp0-sizes 512,2048 --no-real"
```
合格条件: `BENCH-DONE` / 3 腕すべて `results-*.json` が出る / `draft_accept_rate` が non-null / tensor 腕の `server-tensor.log` に `unknown GGML_CUDA_ALLREDUCE` 警告が**出ない**（`none` が正規値であることの確認）。

3-c. **ctx=131072 の VRAM プリフライト**（約 7 分）: **tensor + MTP × ctx=131072 は完全に未検証**（3 のレポートの実測は ctx=8192 のみ）。MTP は第 2 コンテキストで約 1.83 GiB 追加する。tensor 分割でその追加分がどこに載るかは不明で、7 枚が均等に埋まっているとこれが OOM 要因になりうる。tensor 腕を ctx=131072 で単独起動し、`listening on` と `nvidia-smi` の 7 枚の memory.used を記録する。
- **載らなければ**: ctx を下げて 3 腕そろえるのではなく、**tensor+MTP が ctx=131072 に載らないこと自体を結果として記録**し、前回同様 2 腕＋別枠の縮小 ctx 測定に切り替えるかをユーザに確認する（ctx を変えると前回値との A/B が壊れるため、勝手に変えない）

### Phase 4 — 本計測（約 70〜85 分、detached）

```bash
ssh -n aws-gpu01 "cd ~/llama-split-bench && \
  setsid nohup env <ENV> bash run-bench.sh gpu01-7way-mtp2 \
  > runs/gpu01-7way-mtp2.log 2>&1 < /dev/null &"
ssh -n aws-gpu01 'until grep -qE "BENCH-(DONE|ABORT|FIGFAIL)" \
  ~/llama-split-bench/runs/gpu01-7way-mtp2.log; do sleep 60; done'
```

- **`tail -f` は使わない**（セッションを塞ぐ）。マーカーをポーリングする
- 進捗は `runs/gpu01-7way-mtp2.log` の `=== mode <name> ===` 行を随時 grep して確認
- **tensor 腕が `BENCH-ABORT: tensor server not ready` で落ちた場合**（`none` でも確率的に踏む可能性は残る）: 既存結果は `TAGDIR` に残るので `--reuse` で取り直す。
  ```bash
  bash run-bench.sh gpu01-7way-mtp2 --modes tensor,layer2 --reuse
  ```
  3 回続けて失敗するなら、回避策が ctx=131072 では効かないという発見として扱い、ユーザに報告して判断を仰ぐ
- 異常時（SSH・ping 不通のハング）は **電源リセットの前に必ず** `bmc-screenshot.sh` と `ipmitool sel elist` を取る

### Phase 5 — 腕別の実プロンプト補正（約 20 分）

`run-bench.sh` は 1 腕しか実プロンプトを測らない。今回それは tensor 腕になるので、**layer / layer2 の係数を別途取る**。本計測完了後、`argv-layer.txt` / `argv-layer2.txt` の argv をそのまま使ってサーバを起動し、ツール同梱の `measure_real.py` を直接叩く。

```bash
# 例: layer 腕
ssh -n aws-gpu01 "cd ~/llama-split-bench && \
  setsid nohup env <ENV> \$(tr '\n' ' ' < runs/gpu01-7way-mtp2/argv-layer.txt) \
  > /tmp/real-layer.log 2>&1 < /dev/null &"
# listening on を待ってから
ssh -n aws-gpu01 "cd ~/llama-split-bench && python3 measure_real.py \
  --url http://127.0.0.1:18081 --out runs/gpu01-7way-mtp2/results-real-layer.json"
ssh -n aws-gpu01 "pkill -x llama-server"
```

- ポートは `argv-*.txt` 内の `--port`（18081）をそのまま使う
- **`results-real.json` は上書きしない**（plot スクリプトが読む本体なので、tensor 腕のものを保つ）
- 時間が押したら **layer だけ**でもよい（前回レポートの 0.761 との接続にはこれが要る）。layer2 は省略可

### Phase 6 — 回収と作図（約 25 分）

```bash
rsync -a aws-gpu01:~/llama-split-bench/runs/gpu01-7way-mtp2/ \
  report/attachment/<レポート名>/run/
```

- **作図はサーバ側で実行**（CJK フォントは aws-gpu01 の `~/.fonts` にしかない）。`~/.venvs/bench-plot/bin/python`
- `plot_bench.py` はツールが自動で 3 腕版 `split-bench-{ja,en}.png` を出す
- **`plot_mtp.py` を改訂**して `plot_mtp2.py` として使う。変更点:
  1. suptitle の「tensor は MTP と併用するとハングするため MTP on の腕が無い」を削除し、`GGML_CUDA_ALLREDUCE=none` を使った旨に差し替え
  2. **補正係数を腕別にする**（Phase 5 のファイルがある腕はその値、無ければ従来どおり一律）。基準腕 `layer` 固定のロジックを、各腕の `results-real-<arm>.json` ÷ 当該腕の深度 0 に変更
  3. off run は `runs/gpu01-7way-1`（MTP 無効 3 腕）、on run は `runs/gpu01-7way-mtp2`（MTP 有効 3 腕）。**これで初めて 2×3 が全部埋まる**
- `plot_mtp2.py` は添付に含める
- 添付の合計サイズを確認（`report/attachment/` は LFS 不使用。100 MB 超のファイルを作らない。`responses-*/` が大きければ `.gz` のまま置く）

### Phase 7 — レポート作成（約 40 分）

`REPORT.md` に従う。ファイル名は `report/$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)_aws_gpu01_split_mode_mtp_3arm.md`（タイムスタンプは必ず実コマンドで取得）。

- `## 概要` を最上位に置き、平易な日本語で 5〜8 段落
- `## 核心発見サマリ` の直後に **PNG を画像埋め込み**（alt に各パネルの数値を書く）
- `## 添付ファイル` に **`plan.md`（本ファイル）を必ずコピーしてリンク**
- 作成者は `Claude Opus 5 (1M context)`
- 結果詳細に載せる表: ①decode（MTP on/off × 3 腕）②採択率と腕別補正係数 ③decode（補正後）④prefill とラダー ⑤pp0 ⑥GPU 利用率・温度・電力 ⑦VRAM
- **前 3 レポートへの追記**:
  - 124457 の「tensor 腕は欠測」に、本レポートで埋めた旨を追記
  - 142115 の残課題「MTP 有効での tensor 腕の正式な再測定」が解消した旨を追記
  - **142115 の `GGML_CUDA_ALLREDUCE=butterfly` は不正値で実質 `none` だった**ことを訂正として追記（本文の結論は変わらない）
- `## 残課題` に、`CLAUDE.md` / `llama-server` スキルへ `GGML_CUDA_ALLREDUCE=none` を反映するかのユーザ判断（142115 から持ち越し）を再掲

### Phase 8 — commit と後片付け

```bash
git config core.hooksPath .githooks   # 未設定なら
git add report/... && git commit   # docs(report): …（Co-Authored-By 行を付ける）
.claude/skills/discord-notify/scripts/notify.sh "<1行要約>" "report/<file>.md"

# 電源断（ユーザの明示指示あり）
ssh -n aws-gpu01 "pgrep -x llama-server"          # 残存プロセスが無いことを確認
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 soft
until .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 status | grep -q "off"; do sleep 20; done
.claude/skills/gpu-server/scripts/unlock.sh aws-gpu01
```

- **完了後に電源を落とす**（ユーザの明示指示）。順序は「計測結果の回収完了を確認 → レポート作成・commit → `soft`（OS 正常シャットダウン） → `status` で `off` を確認 → `unlock`」。**回収前に落とすと `/tmp` とサーバ上の run が失われる**ので、`rsync` の完了とレポート本文の完成を先に済ませる
- `soft` が効かない場合のみ `off`（強制断）にフォールバックする。いずれも `ALLOW_FAN_NOISE=1` が要る
- aws-gpu02 は元から電源 OFF なので触れない
- push はユーザの指示があるときだけ

---

## リスクと対処

| リスク | 兆候 | 対処 |
|---|---|---|
| tensor+MTP が ctx=131072 で OOM | Phase 3-c で `out of memory` / 起動失敗 | ctx は下げない（A/B が壊れる）。事実として記録し、ユーザに判断を仰ぐ |
| `none` でも起動ハング | 10 分待って `BENCH-ABORT: tensor server not ready`、GPU が 100% / memory 0% | `--reuse` で再試行（最大 3 回）。3 回とも駄目なら発見として報告 |
| 孤児 llama-server が VRAM を掴む | `pgrep -x llama-server` が残る、`nvidia-smi` に compute app | `kill -9`。次フェーズ前に必ず「全 GPU 5% 未満 & compute app 0 件」を確認 |
| OS ハング（SSH・ping 不通） | — | **電源リセット前に `bmc-screenshot.sh` と `ipmitool sel elist`** を必ず取る |
| `pkill -f` の自己マッチ | exit 144 / 255 | `pkill -x llama-server` のみ使う |
| 日本語 PNG が豆腐 | `findfont: ... not found` | 作図はサーバ側 venv で実行。駄目なら `fc-cache -f ~/.fonts && rm -rf ~/.cache/matplotlib` |
| 同一タグ拒否 | `ERROR: ... is not empty` | 新タグを使う。意図的な追記のときだけ `--reuse` |

## 所要時間の見積り

Phase 0-3 で約 40 分、Phase 4 の本計測が 70〜85 分、Phase 5-8 で約 90 分（電源断の待ちを含む） → **合計およそ 3 時間 25 分**。

## 検証（この作業が成功したと言える条件）

1. `runs/gpu01-7way-mtp2/run-info.json` の `modes` に **layer / tensor / layer2 の 3 腕**が並び、`bin_sha256` が `ca54f4dd…8593886`、`launch_prefix` に `GGML_CUDA_ALLREDUCE=none` が記録されている
2. `results-tensor.json` の 5 段すべてに `predicted_per_second` と **non-null の `draft_accept_rate`** が入っている（＝ tensor 分割で投機デコードが実際に効いた証拠）
3. `server-tensor.log` に `unknown GGML_CUDA_ALLREDUCE value` の警告が**出ていない**
4. `split-bench-ja.png` に 3 系列、`mtp-compare-ja.png`（改訂版）に **MTP off / on の 3 腕 × 2 = 6 系列**が描かれている
5. レポートが `REPORT.md` 準拠（`## 概要` 最上位・核心発見サマリ直後に PNG 埋め込み・`plan.md` 添付）で作成され、前 3 レポートへの追記が入っている
