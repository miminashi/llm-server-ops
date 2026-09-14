# aws-gpu01 7-way split-mode ベンチ（MTP 有効版）

## Context

前回セッション（[report/2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor.md](../../projects/llm-server-ops/report/2026-09-14_104905_aws_gpu01_split_mode_layer_vs_tensor.md)）で、aws-gpu01 単体（Tesla P100 ×7）上で llama-split-bench を初実行し、`--split-mode tensor` が `layer` を prefill / decode の全深度で上回ることを実測した。ただしその計測は **投機デコードを無効（`SPEC_ARGS=""`）** にして行っている。

その理由は、比較の純度を保つためだった。一方で、取得した GGUF `Qwen3.8-27B-UD-Q4_K_XL.gguf`（arch `qwen35`）には **MTP（NextN）ヘッドが同梱されており**、前回のサーバログでは `blk.64.nextn.*` が `unused tensor ... -- ignoring` として読み飛ばされていた。GGUF メタデータにも `qwen35.nextn_predict_layers` が存在することを確認済み。前回レポートの「残課題」には **「MTP を有効にした再測定」** が明記されている。

本作業はその残課題を実行する。**前回と同一のバイナリ・モデル・引数・ワークロード**で `SPEC_ARGS` だけを既定（`--spec-type draft-mtp --spec-draft-n-max 2`）に戻し、3 本の腕（`layer` / `tensor` / `layer2`）を再測定する。これにより前回レポートの数値との **MTP on/off の厳密な A/B** が成立し、「layer 分割は速度でなく VRAM を買う」という結論が投機デコード込みでも保たれるかを検証できる。

完了後、レポートを作成してコミット・push し、aws-gpu01 の電源を落としてロックを解放する（ユーザの明示指示）。

## 現状確認済みの事実

- aws-gpu01 は通電中・SSH 可（uptime 1:43）、7 GPU とも VRAM 使用 0 MiB、llama-server は未起動
- ロックは前回セッションの保持のまま（holder `aws-mmns-generic-990003-20260914_092911`）。本セッションから引き継いで使い、最後に解放する
- `~/llama-split-bench/` にツール・`bench.local.conf`・前回 run（tag `gpu01-7way-1`）が残存。モデルも `~/models/Qwen3.8-27B-GGUF/` にあり、再取得は不要
- 作図の前提（`~/.venvs/bench-plot` の matplotlib、`~/.fonts` の Noto Sans CJK JP）は両方とも生存。ディスク空き 245 GB
- ツール側: `run-bench.sh:166` が `SPEC_ARGS` を argv に展開し、`*draft*` を含む場合 `--spec-draft-device` を付ける。`measure_ladder.py:207` が段ごとの `draft_accept_rate`、`measure_real.py:75` が実プロンプトの `accept_rate` を記録する
- llama.cpp 側: MTP は別ドラフトモデルではなく **ターゲットモデルに対して `LLAMA_CONTEXT_TYPE_MTP` の第 2 コンテキストを張る**（`common/speculative.cpp` の `spec_mtp` 分岐）。`hparams.n_layer_nextn == 0` なら `llama-context.cpp` が警告を出して nullptr を返す
- **ワークステーション側には CJK フォントが無い**ため、追加作図は aws-gpu01 上の venv で行う

## 作業手順

### 1. 事前確認（ロック・状態）

```bash
.claude/skills/gpu-server/scripts/lock-status.sh
ssh -n aws-gpu01 "nvidia-smi --query-gpu=index,memory.used --format=csv,noheader; ps aux | grep -c '[l]lama-server'"
```

ロックが前回セッション保持のままであることを確認して引き継ぐ（他ホストが取っていたら中止してユーザに報告）。

### 2. MTP が実際に有効になるかの最小確認（決定ゲート・約 3 分）

フルランに 1 時間かける前に、MTP が本当に作動するかを最短で確かめる。2 枚（重み 16.35 GiB は 1 枚に載らない）・小 ctx で `llama-server` を直接起動し、ログとタイミングを見る。

```bash
ssh -n aws-gpu01 "cd ~ && setsid nohup ~/llama.cpp/build/bin/llama-server \
  -m ~/models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf \
  --host 127.0.0.1 --port 18099 --device CUDA0,CUDA1 --split-mode layer \
  -ngl all -fa on -c 8192 --parallel 1 -t 16 --jinja \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --spec-type draft-mtp --spec-draft-n-max 2 --spec-draft-device CUDA0,CUDA1 \
  > /tmp/mtp-probe.log 2>&1 < /dev/null &"
```

**合格条件**（全部満たすこと）:

- `/tmp/mtp-probe.log` に `nextn` の `unused tensor ... -- ignoring` が **出ない**
- `context type MTP requested but model doesn't contain MTP layers` が **出ない**
- `/completion` を 1 発叩いた `timings` に `draft_n > 0` かつ `draft_n_accepted > 0` が入る

停止は **`pkill -x llama-server`**（`pkill -f` はリモート側 bash に自己マッチして exit 255 になる。前回レポート副次発見 6・メモリ `feedback_pkill_self_match` 参照）。

**不合格だった場合**: ここで打ち切り、「このビルド／この GGUF では MTP が有効化できない」という否定的結果をログ付きでレポートにまとめる（フルランは実施しない）。その場合も commit / push / 電源断は実施する。

### 3. `bench.local.conf` の更新

`SPEC_ARGS` の行だけを差し替える。他の項目（`MODES` / `BASELINE` / `CTX` / `STAGES` / `N_PREDICT` / `PP0_SIZES` / `THREADS` / `MACHINE`）は**前回と一字一句同じに保つ**（A/B の成立条件）。

```bash
# before: SPEC_ARGS=""          # Qwen3.8-27B (non-MTP) — draft-mtp を外す
# after:
SPEC_ARGS="--spec-type draft-mtp --spec-draft-n-max 2"   # MTP 有効（本計測の唯一の変更点）
```

変更前に `cp bench.local.conf bench.local.conf.nomtp-backup` を取り、差分（`diff`）を証跡としてレポート添付に含める。

### 4. スモーク（約 4〜5 分）

```bash
ssh -n aws-gpu01 "cd ~/llama-split-bench && bash run-bench.sh smoke-mtp --modes layer,tensor \
  --stages 0,4000 --n-predict 100 --ctx 8192 --pp0-sizes 512,2048 --no-real"
```

確認項目:

- `results-layer.json` / `results-tensor.json` の各段に `draft_accept_rate` が **non-null** で入る
- **tensor 分割 + MTP の組み合わせが起動する**（ここが最大の未知数。`--split-mode tensor` は `llama_params_fit` 未対応の警告を出すが前回同様無害のはず）
- `BENCH-DONE` で終わる

tensor+MTP だけが失敗した場合は、その事実を記録したうえで動く腕のみで本計測に進む。

### 5. ctx=131072 の VRAM プリフライト（約 3 分）

MTP は第 2 コンテキスト（KV キャッシュ）を張るため、前回より VRAM を食う。**最も余裕の無い `layer2`（2 枚）で ctx=131072 が載るか**を先に確かめる。前回の `layer2` は GPU0 10.9 GiB + GPU1 12.2 GiB（各 16 GiB 中）だった。

手順 2 と同じ直接起動を `-c 131072` で行い、`model loaded` 到達後に `nvidia-smi --query-gpu=index,memory.used` を記録して停止する。載らなければ `layer2` 腕を外して 2 本で本計測を回し、その旨をレポートに明記する。

### 6. 本計測（detached、約 60〜75 分）

```bash
ssh -n aws-gpu01 "cd ~/llama-split-bench && \
  setsid nohup bash run-bench.sh gpu01-7way-mtp > runs/gpu01-7way-mtp.log 2>&1 < /dev/null &"
```

待機は `tail -f` ではなく **完了マーカーのポーリング**で行う（前回踏襲）:

```bash
ssh -n aws-gpu01 'until grep -qE "BENCH-(DONE|ABORT|FIGFAIL)" ~/llama-split-bench/runs/gpu01-7way-mtp.log; do sleep 60; done'
```

腕の順は `layer` → `tensor` → `layer2`。`tensor` の後に実プロンプト補正（`results-real.json`）が自動で走る。**MTP 有効時はこの補正係数が初めて意味を持つ**（合成テキストは採択率がほぼ 1.0 に張り付き楽観側に出るため、README が 0.7〜0.9 を想定）。

### 7. 結果回収と追加作図

1. 新レポート名を決める: `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得し `<ts>_aws_gpu01_split_mode_mtp.md`
2. `report/attachment/<レポート名>/run/` を作り、`rsync -a aws-gpu01:~/llama-split-bench/runs/gpu01-7way-mtp/ ...` で回収
3. `plan.md`（本ファイル）と `bench.local.conf` の差分も同ディレクトリへ
4. **MTP on/off 比較図を追加生成**する。ツールの `split-bench-ja.png` は単一ランの 3 腕しか描かないので、前回 run の `results-*.json` と今回の `results-*.json` を突き合わせた比較図（深度 × decode、MTP on/off × layer/tensor）を matplotlib で作る。**WS に CJK フォントが無いため aws-gpu01 の `~/.venvs/bench-plot/bin/python` で実行**し、生成 PNG を回収する。スクリプトも添付する
5. 添付合計サイズを確認（100 MiB 超は push 拒否。前回 run は 1.4 MB なので問題ないはず）

### 8. レポート作成

`REPORT.md` に従う。ファイル名は英語、タイトルは平易な日本語 50 字以内。

必須・推奨セクション:

- `## 概要`（H1 とメタ情報の直下、5〜8 段落、平易な日本語、数値・識別子は省いてよい）
- `## 添付ファイル`（`[実装プラン](attachment/<名>/plan.md)` 必須）
- `## 核心発見サマリ`（冒頭に **PNG 画像埋め込み**。MTP on/off 比較図を主役に据え、続けて `**結論**:` 段落）
- `## 前提・目的` / `## 環境情報` / `## 再現方法` / `## 結果詳細` / `## 副次発見` / `## 残課題` / `## 参照レポート`

結果詳細に入れる表:

| 表 | 内容 |
|---|---|
| decode MTP on/off | 深度 × {layer, tensor, layer2} × {MTP off（前回値）, MTP on, 伸び率} |
| 採択率 | 段ごとの `draft_accept_rate`（合成）と `results-real.json` の実プロンプト採択率、補正係数 |
| prefill / pp0 | MTP はドラフト検証で prefill 経路を使うため、劣化が無いかを確認 |
| VRAM / 利用率 / 温度・電力 | `sampler-*.log` 集計。MTP 第 2 コンテキストぶんの VRAM 増を明記 |

前回レポートの「残課題」も更新対象として見直す（MTP 再測定が済んだ旨を新レポートの参照で示す。前回レポート本体の書き換えはしない）。

### 9. コミット・push

```bash
git add report/<新レポート>.md report/attachment/<新レポート>/
git commit   # docs(report): ... （日本語・命令形の既存慣習に合わせる）
git push
```

`.githooks/pre-commit`（巨大ファイル検出）が有効か `git config core.hooksPath` で確認する。添付は Git LFS を使わない（CLAUDE.md）。

### 10. 電源断とロック解放

ユーザの明示指示があるため `ALLOW_FAN_NOISE=1` を付けて実行する。

```bash
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 soft   # ACPI シャットダウン
# 数十秒待って確認
.claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 status                   # System Power: off を確認
.claude/skills/gpu-server/scripts/unlock.sh aws-gpu01
```

`soft` が効かず OS が落ちない場合のみ、ユーザに確認のうえ `off`（ハード断）に切り替える。aws-gpu02 には一切触れない。

## 検証

- **MTP が効いた証跡**: `server-*.log` に `nextn` の unused 警告が出ないこと、`results-*.json` の `draft_accept_rate` が non-null かつ 0 でないこと、`argv-*.txt` に `--spec-type draft-mtp` が記録されていること
- **A/B の同一性**: 今回の `run-info.json` の `bin_sha256` が前回の `ca54f4dd8a47...8593886` と一致すること、`argv-*.txt` の差分が spec 関連フラグのみであること（`diff` を取って添付する）
- **完走**: `BENCH-DONE` マーカーと、3 腕ぶんの `results-*.json` / `results-*-pp0.json` / `results-real.json` / 2 枚の PNG が揃うこと
- **レポート**: `## 概要` が H1 直下にあり、`## 核心発見サマリ` の冒頭が `![...](...)` の画像埋め込みであること
- **後始末**: `bmc-power.sh aws-gpu01 status` が `off`、`lock-status.sh` で aws-gpu01 のロックが消えていること

## リスクと対処

| リスク | 対処 |
|---|---|
| MTP が有効化できない（ビルド／GGUF 側の制約） | 手順 2 の決定ゲートで早期に判定。否定的結果としてレポート化し、フルランは回さない |
| `--split-mode tensor` + MTP が起動しない | スモークで判明する。動く腕のみで本計測し、失敗を副次発見に記録 |
| ctx=131072 で `layer2` が VRAM 不足 | 手順 5 のプリフライトで事前検出。該当腕を外し 2 本で実施、図のパネル④は出ない旨を明記 |
| 本計測中のハング・クラッシュ | SSH / ping 不通なら **電源リセット前に** `bmc-screenshot.sh` と `ipmitool sel elist`（CLAUDE.md の必須手順） |
| `pkill -f` の自己マッチ | プロセス停止は必ず `pkill -x llama-server` |
