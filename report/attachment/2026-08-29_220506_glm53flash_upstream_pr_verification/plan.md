# GLM-5.3-Flash 対応 PR の最新版を実機検証する

## Context

[report/2026-08-27_235754_glm53flash_aws_gpu_rpc_startup.md](../../projects/llm-server-ops/report/2026-08-27_235754_glm53flash_aws_gpu_rpc_startup.md)
で GLM-5.3-Flash を aws-gpu01/02 の RPC 分散で起動したとき、本家 llama.cpp が arch `glm5next` に
未対応だったため PR #27754（`cadbe97b7`）でのビルドが必須で、さらに 3 つの制約
（`--parallel 1` 明示 / `-fa off` / `-ub 64`）を回避しないと起動できなかった。

2026-08-29 時点で本家 master（`cc83d7b48`）は依然 `glm5next` 未対応で 3 本の PR も未マージだが、
PR 側は 2 日で大きく動いている。特に:

- **#27754 から拒否メッセージ自体が消えた**。レポートの失敗 #1 で出た
  `the pooled indexer needs one sequence per stream, so a unified KV cache is only supported with a single sequence`
  が最新 diff に存在せず、`n_stream = cparams.kv_unified ? 1 : ubatch.n_seqs_unq` の
  per-sequence pooling（`204fa7003c`「pool the indexer per sequence so a unified KV cache works」）に
  置き換わった。**`--parallel 1` が不要になった可能性が高い**。
- **#27752 は同じ pooled 実装を入れつつ、PR 本文で「unified cache + 複数シーケンスは起動するが
  選択品質が劣化する」と明記**している。両 PR で挙動が違う可能性がある。
- #27752 が draft 解除され ggerganov / CISC / JohannesGaessler にレビュー要求中で、
  **本家マージの本命**になった。

本作業の目的は、この 5 点をコード読解ではなく**実機で確定させ**、レポートに残すこと。

## 検証する 5 項目

| # | 主張 | 検証方法 |
|---|---|---|
| 1 | `--parallel 1` 制約は解消された | `--parallel` を省略して起動できるか。できたら複数 slot 同時で品質劣化がないか |
| 2 | `-fa off` / `NVIDIA_TF32_OVERRIDE=0` は依然必須 | `-fa on` で起動・出力比較。TF32 は P100 (sm_60) 非該当をコードで確認 |
| 3 | `-ub` はまだ上げられない（indexer workspace が `O(ubatch × n_ctx)`） | `-fa` × `-ub` のスイープで起動可否と prefill 速度を実測 |
| 4 | CUDA は `n_pool > 65535`（実深度 ≈262,140 tok）で落ちる | ctx を伸ばして到達できるか。到達したら実機再現 |
| 5 | 手元の GGUF は再変換が必要か | GGUF の KV / テンソルを dump し、`index_share_for_mtp_iteration` と `blk.45.nextn.*` を確認 |

## 前提条件（確認済み）

- aws-gpu01 / aws-gpu02 とも **`System Power: off`**。ユーザ承認済みなので `ALLOW_FAN_NOISE=1` で投入する
- コールドブート実測: gpu01 は SSH まで約 150 秒、gpu02 は約 85 秒（`gpu-server/aws-gpu.md:306-309`）
- `rpc-llama-up.sh` は `--flash-attn 1 --poll 0 -b 2048 -ub 512` 固定・`--parallel` を渡さないため
  **今回は使えない**。前回同様 `ssh` で直接 `llama-server` を起動する
- `update_and_build-aws-gpu0*.sh` は先頭で `rm -rf build` するフルビルド（`-j $(nproc)`、48T/40T）。
  **1 台につき 1 本だけ**（同じ `build/` に 2 本流すと壊れる）。2 台は並行してよい
- 前回退避したローカルパッチは aws-gpu01 の `~/patches/server-http-404-mcpproxy.patch` と
  `git stash@{0}` にある。片付けで復元する
- ロックは GPU サーバ側 `/tmp/gpu-server-locks/<server>.lock`。**電源断で消える**ので投入後に取り直す

## 手順

### Step 0: 起動と準備（約 15 分）

```bash
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 on
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu02 on
until timeout 8 ssh -o ConnectTimeout=5 -o BatchMode=yes aws-gpu01 true 2>/dev/null; do sleep 15; done
until timeout 8 ssh -o ConnectTimeout=5 -o BatchMode=yes aws-gpu02 true 2>/dev/null; do sleep 15; done
.claude/skills/gpu-server/scripts/lock.sh aws-gpu01
.claude/skills/gpu-server/scripts/lock.sh aws-gpu02
```

続けて、ビルドを待たずに済む確認を先に済ませる:

- モデルの存在とサイズ（`156822111075` と一致するか）
- **項目 5**: `gguf_dump.py --no-tensors` で KV 一覧、`gguf_dump.py` でテンソル一覧を取り、
  `index_share_for_mtp_iteration` の有無、`blk.45.nextn.*` の型、indexer 関連キーを記録。
  HF 側 `unsloth/GLM-5.3-Flash-GGUF/Shard_Rewrite/` のファイル一覧と比較して再変換の要否を判定
- 前回のパッチ退避（`~/patches/`, `git stash list`）が残っていることの確認

### Step 1: #27754 を最新化して両機ビルド（約 20 分）

```bash
ssh -n aws-gpu01 "cd ~/llama.cpp && git fetch origin pull/27754/head:pr27754 -f && git checkout pr27754"
ssh -n aws-gpu02 "cd ~/llama.cpp && git fetch origin pull/27754/head:pr27754 -f && git checkout pr27754"
# 両機 HEAD が f30bed88717059d8a4728864c88f8abad8d329a0 で一致することを確認
scp .claude/skills/llama-server/server-scripts/update_and_build-aws-gpu01.sh aws-gpu01:~/llama.cpp/update_and_build.sh
scp .claude/skills/llama-server/server-scripts/update_and_build-aws-gpu02.sh aws-gpu02:~/llama.cpp/update_and_build.sh
timeout 40 ssh -n aws-gpu01 "cd ~/llama.cpp && setsid nohup ./update_and_build.sh --no-pull --force > /tmp/build.log 2>&1 < /dev/null &" || true
timeout 40 ssh -n aws-gpu02 "cd ~/llama.cpp && setsid nohup ./update_and_build.sh --no-pull --force > /tmp/build.log 2>&1 < /dev/null &" || true
```

ビルド待ちの間に、RPC ワーカー起動用のコマンドと needle テストの入力を用意しておく。

### Step 2: Phase A — #27754 のスイープ（目安 60 分）

RPC ワーカーを立て（`.claude/skills/llama-server/scripts/rpc-up.sh`）、以下を上から順に。
共通部分は前回の確定構成（`NVIDIA_TF32_OVERRIDE=0`, `--rpc 192.168.100.2:50052`,
`-ngl 999 --poll 0 --jinja --temp 1.0 --top-p 0.95`）。

| # | 目的 | 変更点 | 判定 |
|---|---|---|---|
| A1 | **項目 1 の核心** | ctx=32768 / `-b 512 -ub 64` / `-fa off` / **`--parallel` 省略** | `listening on` が出れば制約解消。`server.cpp:153` が `n_parallel=4 + kv_unified=true` を強制した状態で通るかを見る |
| A2 | 項目 1 の品質 | A1 成功時。異なる合言葉を埋めた長文 2 本を **2 slot に同時投入** | 両方正解なら劣化なし。混線・誤答なら劣化あり |
| A3 | **項目 2 / 3** | `-fa on` / `-ub 512` | 起動可否・prefill 速度・temp 0 での出力を A1 と比較 |
| A4 | 項目 3 | A3 成功なら `-ub 1024` → `2048` | どこで `failed to allocate` が出るか。バッファ要求量をログから採取 |
| A5 | **項目 4** | 最良構成で ctx を 65536 → 131072 → 262144 | ctx 上限の確定。262144 に到達したら `n_pool = 65536` で CUDA エラーが出るかを実機確認 |

- A1 が失敗した場合は `--parallel 1` を戻して A3 以降を継続し、項目 1 は「未解消」で確定させる
- 各試行はログの `listening on` / `failed to allocate` / `CUDA error` / `exiting due to model loading error`
  で判定する。**`failed to initialize the context` と `common_fit_params` のエラー行は正常起動でも
  出るので判定に使わない**（前回の副次発見）
- 起動できた構成では必ず `nvidia-smi` で 13 GPU の VRAM と最小空きを採取する

### Step 3: #27752 をビルド（約 20 分）

Step 1 と同じ手順で `pull/27752/head:pr27752`（`8a8d0bcc4d5fdf024c457526245bec4bc3a12adc`）に切り替えて両機ビルド。

### Step 4: Phase B — #27752 のスイープ（目安 60 分）

| # | 目的 | 構成 | 判定 |
|---|---|---|---|
| B1 | 項目 1 | A1 と同一 | 起動可否 |
| B2 | **項目 1 の品質差** | A2 と同一の 2 slot 同時テスト | PR 本文の「pools mix cells across sequences and selection degrades」を実測で裏取り |
| B3 | 項目 2 / 3 | A で最良だった構成を再現 | PR 間の差を比較 |
| B4 | 追加 | `--spec-type draft-mtp`（Step 0 で `blk.45.nextn.*` が使える型だった場合のみ） | #27752 の目玉。受理率が出れば記録 |

**打ち切り基準**: Phase A / B ともに 60 分。超えたら残りを「未検証」としてレポートに明記する。
優先順位は 項目 1 > 項目 3 > 項目 2 > 項目 4 > 項目 5（項目 5 は Step 0 で完了しているはず）。

### Step 5: 片付け（約 30 分）

```bash
.claude/skills/llama-server/scripts/stop.sh aws-gpu01
.claude/skills/llama-server/scripts/rpc-down.sh
ssh -n aws-gpu01 "cd ~/llama.cpp && git checkout master && git stash pop"   # 退避パッチを復元
ssh -n aws-gpu02 "cd ~/llama.cpp && git checkout master"
```

**master で両機を再ビルドしてから電源を落とす**。次回セッションが既定構成
（DeepSeek-V4-Flash / `llama-up.sh aws-gpu01`）をそのまま使えるようにするため。
その後、電源断（`ALLOW_FAN_NOISE=1` 付き）とロック解放（`unlock.sh` 両機）。

### Step 6: レポート作成

[REPORT.md](../../projects/llm-server-ops/REPORT.md) の規約に従う。

- ファイル名は `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得し
  `report/yyyy-mm-dd_hhmmss_glm53flash_upstream_pr_verification.md`
- H1 は日本語 50 字以内。`## 概要` を必ず最初に置き、5〜8 段落・数値や SHA を含めない平易な文章にする
- `## 核心発見サマリ` の冒頭に **PNG を画像埋め込み**する。図は
  **(PR × `-fa` × `-ub` × ctx) の起動可否マトリクス**を主軸にし、成功構成の prefill 速度と
  最小空き VRAM を併記する
- `## 添付ファイル` に、各試行の llama-server ログ、GGUF の dump、図の生成スクリプト、
  そして**このプランファイル**（`cp /home/ubuntu/.claude/plans/eager-strolling-flamingo.md
  report/attachment/<name>/plan.md`）をリンクする
- `## 参照レポート` から前回レポートへリンクし、前回レポートの「残課題」節にも
  本レポートへの追記を 1 行入れて追跡できるようにする
- `report/INDEX.md` に 1 行追記する（明文規約ではないが全件収録されている運用慣行）
- 5 項目それぞれについて「主張 → 実測 → 結論」を表で示し、未検証に終わった項目はそう明記する

## 検証（このタスク自体の完了条件）

1. 5 項目それぞれに実測または明示的な「未検証」の結論がついている
2. 少なくとも 1 つの構成で `curl http://10.8.2.1:8000/health` が `{"status":"ok"}` を返し、
   needle テストに正解している（＝スイープが空振りに終わっていない）
3. 両機の llama.cpp が master に戻り再ビルドされ、aws-gpu01 の退避パッチが復元されている
4. 両機が `System Power: off`、ロックが両機とも `available`
5. レポートが REPORT.md の必須セクションを満たし、PNG が埋め込まれ、INDEX.md に載っている
