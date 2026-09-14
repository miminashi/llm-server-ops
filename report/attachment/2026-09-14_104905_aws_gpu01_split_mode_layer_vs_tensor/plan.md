# llama-split-bench を aws-gpu01 単体（P100 ×7）で実行しレポート化する

## Context

`src/llama-split-bench/` は 2026-09-14 09:15 に外部リポジトリ
（`https://github.com/kuraneko1/llama-split-bench`）からクローンされたばかりのツールで、
**このリポジトリでは一度も実行されていない**（`report/` に言及ゼロ、`runs/` も
`bench.local.conf` も未作成）。

このツールは llama.cpp の `--split-mode layer`（既定・パイプライン分割）と
`--split-mode tensor`（TP）のどちらが実際に速いかを、深度ラダー方式で prefill / decode
両面から実測し、単一 GPU ベースラインとの比較図まで自動生成する。
現行の運用既定値は `start.sh:215` が **`--split-mode layer` を固定**しており、
これを実測で再検証する当て先になる。

実行先を aws-gpu01 単体とする理由はユーザ指示だが、背景として **aws-gpu02 が
`P1_DIMMA2` 故障（2026-09-10）で POST を通過せず**、既定の RPC 分散構成が使えない。
aws-gpu01 単体（Tesla P100 16GB ×7 = 112 GiB）は SKILL.md 上「未検証」の構成なので、
今回の実測はその構成自体の初回データにもなる。

さらにツール作者自身が **「TP=3 以上・参照環境以外の構成は未検証」** と明記しているため、
**7-way は本ツールにとっても初の検証ケース**になる。

**現在の状態**: aws-gpu01 / aws-gpu02 とも電源 OFF（BMC で確認済み）。
ユーザから **aws-gpu01 のみ電源投入する許可を取得済み**（2026-09-14）。
モデルは **起動後に `~/models` の実物一覧を提示してユーザが選択**する方針で合意済み。

---

## 実行計画

### Phase 0: ローカル事前チェック（ワークステーション）

```bash
bash src/llama-split-bench/check.sh      # bash -n + py_compile
```

### Phase 1: ロック取得 → 電源投入

```bash
.claude/skills/gpu-server/scripts/lock.sh aws-gpu01
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 on
```

- **aws-gpu02 は投入しない**。ロックも gpu01 のみ取る（gpu02 は起動不能で SSH 不通、
  `lock.sh` が到達できない。CLAUDE.md の「両機ロック」は RPC 分散前提のため今回は非該当）。
- `bmc-power.sh` が `boot-quiet.sh` を自動併走させ、POST 中も 2,900rpm 台に収まる想定
  （2026-08-18 実測）。
- POST は約 146 秒、SSH 到達まで実績 227 秒。5 秒間隔で `ssh -o ConnectTimeout=5` を
  ポーリングし、最大 10 分待つ。

### Phase 2: モデル選択（★ユーザ確認ポイント）

```bash
ssh -n aws-gpu01 "du -sh ~/models/* ; find ~/models -name '*.gguf' -printf '%s\t%p\n' | sort -rn"
ssh -n aws-gpu01 "nvidia-smi --query-gpu=index,name,memory.total --format=csv ; nproc ; free -g"
```

得られた実サイズ一覧を **AskUserQuestion で提示してユーザに選ばせる**。判断軸:

| 軸 | 内容 |
|---|---|
| 単一 GPU（16 GiB）に載るか | 載るなら `single` ベースライン（図のパネル④）が取れる。載らないなら `--modes layer,tensor` に絞り、代わりに `--mode-spec` で 2-way / 4-way / 7-way のスケーリングを見る |
| 7 GPU（112 GiB）に載るか | GLM-5.3-Flash UD-IQ4_XS（146 GiB）・Huihui-DeepSeek-V4-Flash Q4_K（153.3 GiB）・DeepSeek-V4-Flash UD-Q4_K_XL（144.4 GiB）は**単体では載らない**ので対象外 |
| MTP 対応か | 非対応モデルは `SPEC_ARGS=""` が必須（既定の `--spec-type draft-mtp` のままだと起動失敗） |

選択結果から `CTX` / `STAGES` / `SPEC_ARGS` / `SINGLE_DEV` を確定する。
**ctx は既定の 262144 を使わず、モデルの native ctx と VRAM 残量から決める**
（P100 ×7 で 262k ラダーは時間もメモリも過大）。目安は 65536、ステージは
`0,8000,16000,32000,65000`。

### Phase 3: セットアップ（gpu01 側）

```bash
# llama.cpp と split-mode tensor 対応を確認（前回停止時は master 465e49b9c + パッチ、無変更）
ssh -n aws-gpu01 "cd ~/llama.cpp && git rev-parse HEAD && git status --short | head"
ssh -n aws-gpu01 "~/llama.cpp/build/bin/llama-server --help | grep -A3 'split-mode'"

# ツール転送（.git / runs は除外）
rsync -av --exclude .git --exclude runs \
  src/llama-split-bench/ aws-gpu01:~/llama-split-bench/

# 作図用 venv（初回のみ）
ssh -n aws-gpu01 "python3 -m venv ~/.venvs/bench-plot && ~/.venvs/bench-plot/bin/pip install matplotlib"

# デバイス一覧（CUDA0..CUDA6 が出ることを確認）
ssh -n aws-gpu01 "cd ~/llama-split-bench && ./list-devices.sh ~/llama.cpp/build/bin/llama-server"
```

- **ビルドはしない**（`update_and_build.sh` を流さない）。既存バイナリをそのまま使い、
  `run-info.json` に記録される sha256 を証跡にする。`--split-mode tensor` が
  `--help` に無い場合のみビルド要否をユーザに相談する。
- **運用 llama-server（ポート 8000）は起動しない**。`llama-up.sh` を使わないこと
  — ベンチが自前で 18081 にサーバを立てるうえ、外部プロセスガードが対象 GPU 上の
  他プロセスを検出すると即 abort する。
- ttyd（7681/7682）も立てない（不要かつガードの誤爆要因を減らすため）。

`~/llama-split-bench/bench.local.conf`（Phase 2 の選択結果で穴埋め）:

```bash
BIN=$HOME/llama.cpp/build/bin/llama-server
MODEL=$HOME/models/<選択したモデル>.gguf
DEVICES=CUDA0,CUDA1,CUDA2,CUDA3,CUDA4,CUDA5,CUDA6
SINGLE_DEV=CUDA0
CTX=65536
STAGES=0,8000,16000,32000,65000
THREADS=<nproc に応じて>
SPEC_ARGS=""                  # MTP 非対応モデルの場合
VENV_PY=$HOME/.venvs/bench-plot/bin/python
MACHINE="aws-gpu01 — Tesla P100 16GB x7"
```

### Phase 4: スモーク（約 4 分）

```bash
ssh -n aws-gpu01 "cd ~/llama-split-bench && mkdir -p runs && \
  bash run-bench.sh smoke --stages 0,4000 --n-predict 100 --ctx 8192 \
       --pp0-sizes 512,2048 --modes layer,single --no-real 2>&1 | tail -20"
```

`BENCH-DONE` を確認。失敗時は `runs/smoke/server-*.log` と `argv-*.txt` を読んで
起動引数（`SPEC_ARGS`、KV 型、`-fa on`、`--cache-*`）を切り分ける。

### Phase 5: 本計測（detached）

```bash
ssh -n aws-gpu01 "cd ~/llama-split-bench && \
  setsid nohup bash run-bench.sh gpu01-7way-1 > runs/gpu01-7way-1.log 2>&1 < /dev/null &"
```

- モードは `layer` / `tensor` / `single`（モデルが 1 枚に載らない場合は
  `--mode-spec` で `7way|CUDA0..6|tensor` / `7way|...|layer` / `2way` / `4way` に差し替え）。
- **`tail -f` は使わない**。`until grep -qE "BENCH-(DONE|ABORT|FIGFAIL)" ...` でマーカーを
  ポーリングし、途中経過は `status-<mode>.txt` を読む。
- 同一タグの再実行は仕様として拒否されるので、再走時はタグを変える。
- 想定所要は 1〜2 時間（モードごとにモデルロードが入るので大きいモデルほど伸びる）。
  ユーザ待ちにならないよう、ポーリング中は進捗を随時報告する。

### Phase 6: 回収・確認

```bash
rsync -av aws-gpu01:~/llama-split-bench/runs/gpu01-7way-1/ \
  report/attachment/<レポート名>/runs/
```

- `split-bench-ja.png` / `split-bench-en.png` を確認。
- `server-*.log` / `responses-*/` / `real-response-*.txt` は**コミット前に中身を確認**する
  （プロンプト・生成本文・バックエンド情報が入る）。サイズが大きいものは `gzip`
  （`.githooks/pre-commit` が 100 MB 超を弾く。添付は LFS を使わない）。

### Phase 7: レポート作成 → 電源断

- `report/yyyy-mm-dd_hhmmss_aws_gpu01_split_mode_layer_vs_tensor.md`
  （タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得）。
- REPORT.md 準拠: H1（50 字以内）→ メタ 3 行 → **`## 概要`（必須、平易日本語 5〜8 段落）**
  → `## 添付ファイル`（**plan.md のコピー必須**）→ `## 核心発見サマリ`（**冒頭に PNG を
  画像埋め込み**。split-bench 生成の `split-bench-ja.png` をそのまま使う）→ 環境情報 →
  再現方法 → 結果詳細 → 残課題。
- 結論に含めるべき論点:
  - P100 ×7 で layer と tensor のどちらが速いか（prefill / decode 別、深度別）
  - `start.sh` の `--split-mode layer` 固定を見直すべきか
  - 単一 GPU 比のスケーリング（7 枚が本当に効いているか）
  - **ツール側の未検証領域（TP≥3）で問題が出たかどうか** — 出た場合は上流に報告しうる素材
    として記録（OSS への投稿文は AI に書かせない運用に従い、素材出しに留める）
- 完了後、ユーザに確認のうえ電源断とロック解放:
  ```bash
  ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 soft
  .claude/skills/gpu-server/scripts/unlock.sh aws-gpu01
  ```

---

## 主要な落とし穴（事前に押さえる）

1. **外部プロセスガード** — 対象 GPU に他プロセスの計算があるとラダー開始時に即 abort。
   運用 llama-server を立てない、ロックを取る。
2. **`SPEC_ARGS` 既定が `--spec-type draft-mtp`** — MTP 非対応モデルでは空にしないと起動失敗。
3. **同一タグ再実行は拒否** — 新タグを使う（`--reuse` は意図的な追記専用）。
4. **`--split-mode tensor` は `-fa on` 必須**（`bench.conf` の既定 `FA=on` のままでよい）。
5. **KV 既定は q8_0** — P100 での実績設定と揃っているが、`run-info.json` に記録される値を
   レポートに明記する。
6. **`bench.conf` / `bench.local.conf` は bash で source される** — 外部から受け取った
   設定は使わない（今回は自前作成のみ）。
7. **電源操作のガード** — `ALLOW_FAN_NOISE=1` は今回ユーザの明示的許可がある範囲
   （aws-gpu01 の on / soft）でのみ使う。gpu02 には一切触らない。

## 検証方法

- `check.sh` が通ること（静的チェック）。
- スモークが `BENCH-DONE` で終わること（パイプライン疎通）。
- 本計測後、`runs/<tag>/run-info.json` にバイナリ sha256・モード表・KV 型が記録され、
  `results-layer.json` / `results-tensor.json` / `results-single.json` の各段に
  `prompt_per_second` と `predicted_per_second` が入っていること。
- `split-bench-ja.png` が生成され、パネル①〜④が描かれること
  （`single` を測らなかった場合は④が自動非表示になるのが正常）。
- `sampler-*.log` に 2 秒間隔で温度・電力が記録されていること（熱による律速の確認材料）。
