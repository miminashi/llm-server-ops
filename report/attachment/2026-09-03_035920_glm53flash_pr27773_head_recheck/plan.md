# GLM-5.3-Flash #27773 現 HEAD (`fe3187de7`) の実機動作確認

## Context

前回レポート `report/2026-09-02_160322_glm53flash_pr27773_verification.md` の残課題の筆頭が
**「`head_count_kv` 修正の実機確認」**である。前回は `7de5a8e39` 時点で unsloth の
`Shard_Rewrite/` shard 1 が読めず（per-layer 配列長が 46 対 45）、末尾 1 要素を落とす 4 バイトの
バイトパッチで回避した。その直後に上流が **46 を受け入れる側に倒した**ことをコード読解で確認したが、
**実機では未確認**のまま両機を電源断した。今回はそこに決着をつける。

上流の現状は調査済みで、前回の読解どおりだった。

- **#27773 の現 HEAD は `fe3187de7a7d132742282f2602cf1f8fc3db1d5d`**（2026-09-02 13:53 UTC）。
  前回レポートが「修正コミット」と特定したものそのもので、**以後 24 時間以上更新なし**。
  つまり「現在の最新コミット」＝前回コード読解だけで判定したコミットである。
- 変換側 `conversion/glm.py:462-466` に `# Pad to block_count` /
  `n_kv_heads += [1] * (self.block_count - len(n_kv_heads))` が入っている。
- ローダ側は **本家 master の #28173「model : load relevant arrays with n_layer_all」が
  2026-09-01 16:58 UTC にマージ済み**で、`src/llama-model.cpp:1290-1299` の 3 つの
  `get_key_or_arr` が `hparams.n_layer()` → `hparams.n_layer_all` になっている。PR HEAD にも反映済み。
- HF 側の `Shard_Rewrite/GLM-5.3-Flash-UD-IQ4_XS-00001-of-00005.gguf_file` は
  **9,429,984 B のまま**（未更新）。

したがって **未パッチの `Shard_Rewrite/` shard 1（46 要素）がそのまま読めるはず**であり、逆に
**前回作った `UD-IQ4_XS-rewrite/` のパッチ済み shard 1（45 要素）は落ちるはず**である。
この 2 方向を実機で確定させるのが主目的。

あわせて `7de5a8e39` → `fe3187de7` の差分には kpool 実装の書き直しが含まれる
（`src/llama-memory-hybrid-idx.cpp` +159/-137、`src/models/glm5-next.cpp` +18/-12、
`src/llama-context.cpp` +15/-8、`src/llama-arch.cpp` +1）。前回測定した pp 49.7 t/s と
出力品質が維持されているかの再測にも意味がある。

**ユーザ確認済みの方針**: 電源投入は許可。範囲は **C1〜C3**（C4/C5 は今回やらない）。
後始末は **master 復帰 + 電源 OFF**（前回と同じ）。

## 検証項目

| # | 項目 | 期待 |
|---|---|---|
| **C1** | **未パッチ `Shard_Rewrite/` shard 1 で起動**（本命） | **読み込み成功**、`blk.45.nextn.*` は `unused tensor ... -- ignoring` |
| **C2** | 対照: 前回のパッチ済み shard 1（45 要素）で起動 | **`expected 46, got 45` で FAIL** |
| **C3** | ctx 32768 / `-ub 4096` / `-fa on` で短答・11k needle・2 slot 同時・pp/tg | 前回 A5（pp 49.7 t/s）と同等、品質維持 |

C4（108k depth collapse の再走）と C5（`-fa off` での交絡切り分け）は**今回スコープ外**。
残課題として次回に持ち越す。

## 環境と前提

| 項目 | 値 |
|---|---|
| 対象 | #27773 `timkhronos:GLM5.3-Flash` **`fe3187de7a`** |
| 参考 | #27754 は `949f7efb09` から**変化なし**（再検証不要）。#27752 は `c9ddd6821c` に更新。#27917 は draft のまま |
| 本家 master | `9400c8946e`（2026-09-02） |
| サーバ | aws-gpu01（メイン、P100×7）+ aws-gpu02（RPC ワーカー、P100×6）。**現在いずれも電源 OFF**（ping 不通）、`/tmp/gpu-server-locks/` も存在せず |
| llama.cpp | 両機とも master `b81c99b479` でビルド済み。**aws-gpu01 には `--ui-mcp-proxy` 404 修正のローカル変更が復元済み**（`M tools/server/server-http.cpp`） |
| モデル | `~/models/GLM-5.3-Flash-GGUF/UD-IQ4_XS/`（146 GiB）残置、`UD-IQ4_XS-rewrite/`（パッチ済み shard 1）残置 |

**時間の見積り**（Explore で判明した前提を反映）:
`update_and_build-aws-gpu0N.sh` は **ccache を使わず毎回 `rm -rf build` するため常にフルリビルド**
（`-j$(nproc)` = 48 / 40、`GGML_CUDA_FA_ALL_QUANTS=ON`）。PR ビルド 1 回 + 後始末の master ビルド
1 回で **フルビルド 2 巡**が確定する。モデルの cold ロードは約 15 分。全体で 3 時間前後を見込む。

**再利用する資産**: 前回の添付スクリプトをそのまま使う。
`report/attachment/2026-09-02_160322_glm53flash_pr27773_verification/` の
`mkneedle2.py`（needle 生成）／`check.py`（応答判定）／`ask.sh`（リクエスト投入）／
`sweep_meas.sh`（pp/tg 取得）／`mkfig.py`（図生成）。
`patch_shard1.py` は**今回は当てない**（対照 C2 では前回の生成物をそのまま使う）。

## 手順

### 1. 電源投入（ユーザ許可済み）

```bash
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 on
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu02 on
```

`boot-quiet.sh` が自動併走するので POST 中も 2,900rpm 台に収まる見込み。
コールドブートは gpu01 が約 150 秒、gpu02 が約 85 秒。SSH 疎通を `until` ループで待つ。

**aws-gpu02 は前回 2 回痕跡なしにハングし 3 回目で復旧している**。SSH が上がらない場合は
CLAUDE.md の必須手順どおり **`bmc-screenshot.sh` で KVM スクショを保全してから**
`ALLOW_FAN_NOISE=1 bmc-power.sh aws-gpu02 reset` する。

### 2. ロック取得（両機）

```bash
.claude/skills/gpu-server/scripts/lock-status.sh
.claude/skills/gpu-server/scripts/lock.sh aws-gpu01
.claude/skills/gpu-server/scripts/lock.sh aws-gpu02
```

再起動で `/tmp` が飛ぶため、**電源投入後に取る**（先に取っても消える）。

### 3. aws-gpu01 のローカル修正を退避

```bash
ssh -n aws-gpu01 "cd ~/llama.cpp && mkdir -p ~/patches && git diff > ~/patches/\$(date +%F)-local.patch \
  && git stash push -m pre-glm5next-2 -- tools/server/server-http.cpp && git status --short"
```

### 4. 未パッチ shard 1 を配置（**新ディレクトリ**。既存 `UD-IQ4_XS-rewrite/` は C2 の対照に温存）

aws-gpu01 は WS と同一拠点で HF 直接 DL が速いので、サーバ上で直接取る（9.4 MB）。

```bash
source ~/.config/gpu-server/.env
ssh -n aws-gpu01 "D=~/models/GLM-5.3-Flash-GGUF; mkdir -p \$D/UD-IQ4_XS-nopatch && \
  curl -sL -H 'Authorization: Bearer $HF_TOKEN' \
  -o \$D/UD-IQ4_XS-nopatch/GLM-5.3-Flash-UD-IQ4_XS-00001-of-00005.gguf \
  'https://huggingface.co/unsloth/GLM-5.3-Flash-GGUF/resolve/main/Shard_Rewrite/GLM-5.3-Flash-UD-IQ4_XS-00001-of-00005.gguf_file' && \
  stat -c %s \$D/UD-IQ4_XS-nopatch/GLM-5.3-Flash-UD-IQ4_XS-00001-of-00005.gguf"
```

**期待サイズ 9,429,984 B**（HF API で確認済み。前回のパッチ済みは 9,429,980 B）。一致を確認する。
shard 2〜5 は `UD-IQ4_XS/` の実体へシンボリックリンク（実体は shard 1 の 9.4 MB のみ）。

### 5. 両機を `fe3187de7a` でビルド

```bash
ssh -n aws-gpu01 "cd ~/llama.cpp && git fetch origin pull/27773/head:pr27773 -f && git checkout pr27773 && git rev-parse HEAD"
ssh -n aws-gpu02 "cd ~/llama.cpp && git fetch origin pull/27773/head:pr27773 -f && git checkout pr27773 && git rev-parse HEAD"
```

両機とも `fe3187de7a7d132742282f2602cf1f8fc3db1d5d` であることを確認してから
（**コミット一致は RPC 分散の必須条件**）、ビルドスクリプトを転送して流す。

```bash
scp .claude/skills/llama-server/server-scripts/update_and_build-aws-gpu01.sh aws-gpu01:~/llama.cpp/update_and_build.sh
scp .claude/skills/llama-server/server-scripts/update_and_build-aws-gpu02.sh aws-gpu02:~/llama.cpp/update_and_build.sh
```

`./update_and_build.sh --no-pull --force` を **1 台 1 本ずつ**（同じ `build/` に 2 本走らせない）、
`setsid nohup` でバックグラウンド起動して `pgrep -f '[u]pdate_and_build'` で完了を待つ。
`--no-pull` は PR ブランチが `git pull` で壊されるのを防ぐため必須。

### 6. C1 — 未パッチ shard 1 で起動（本命）

```bash
.claude/skills/llama-server/scripts/rpc-up.sh aws-gpu02      # 192.168.100.2:50052
```

llama-server は前回レポートの再現手順と同一構成で手打ち起動する
（`rpc-llama-up.sh` の既定は `-b 2048 -ub 512` で前回と違うため、比較可能性を優先して手打ちを使う）。

```
--model ~/models/GLM-5.3-Flash-GGUF/UD-IQ4_XS-nopatch/GLM-5.3-Flash-UD-IQ4_XS-00001-of-00005.gguf
--alias 'GLM-5.3-Flash-UD-IQ4_XS' --rpc 192.168.100.2:50052
--n-gpu-layers 999 --ctx-size 32768 -fa on --poll 0 -b 512 -ub 4096
--jinja --temp 1.0 --top-p 0.95 --host 0.0.0.0 --port 8000
```

判定は `/tmp/llama-server.log` に `listening on` が出るか、`head_count_kv` エラーで落ちるか。
**成功したら `unused tensor blk.45.nextn.*` の行と、`n_head_kv` 関連のログを保存する。**

万一 C1 が失敗した場合は、`build/bin/llama-gguf` 等で shard 1 の実際の配列長と `block_count` を
読み出し、コード読解のどこが外れていたかを切り分けてからレポートに書く。

### 7. C3 — 動作・速度測定（C1 のサーバをそのまま使う）

- 短答「日本の首都は」（`temperature 0`）→ 前回と同じ応答・thinking 296 字か
- 11k needle（`mkneedle2.py` を `n_para=39`、合言葉 2 か所）→ 両方正答するか
- 2 slot 同時（前回と同じ 2 組: `紫陽花7823`/`金木犀2290`、`向日葵4519`/`石楠花8846`）
- pp / tg を `sweep_meas.sh` の要領で取得し、**前回 A5 の pp 49.7 t/s と比較**
- `nvidia-smi` で両機の VRAM 使用量・最小空きも記録（前回 1,714 MiB / 578 MiB）

### 8. C2 — 対照（パッチ済み shard 1 で落ちること）

C3 完了後、llama-server を止めて `--model` を `UD-IQ4_XS-rewrite/`（前回のパッチ済み shard 1）に
差し替えて起動。**`expected 46, got 45` で落ちること**を確認しログを保存する。落ちるのは
ロード前なので数分。

確認後、`UD-IQ4_XS-rewrite/` の shard 1 を**未パッチのものに差し戻す**（前回レポートが
「現 HEAD では有害」と書いた残置物を無害化する）。

### 9. 後始末（master 復帰 + 電源 OFF）

```bash
.claude/skills/llama-server/scripts/stop.sh aws-gpu01      # llama-server → RPC の順。逆は不可
.claude/skills/llama-server/scripts/rpc-down.sh aws-gpu02
ssh -n aws-gpu01 "cd ~/llama.cpp && git checkout master && git pull --ff-only && git rev-parse HEAD"
ssh -n aws-gpu02 "cd ~/llama.cpp && git checkout master && git pull --ff-only && git rev-parse HEAD"
```

両機で `./update_and_build.sh --no-pull --force` を流し直したのち、

```bash
ssh -n aws-gpu01 "cd ~/llama.cpp && git stash pop && git status --short"   # 404 修正パッチを復元
.claude/skills/gpu-server/scripts/unlock.sh aws-gpu01
.claude/skills/gpu-server/scripts/unlock.sh aws-gpu02
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 soft
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu02 soft
```

`git stash pop` は**再ビルド後**に行う（パッチ込みでビルドしても構わないが、前回と同じ
「master 素のビルド + 作業ツリーにパッチ」の状態に戻すため）。

### 10. レポート作成（REPORT.md 準拠）

- ファイル名: `report/2026-09-03_HHMMSS_glm53flash_pr27773_head_recheck.md`
  （タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得。**推測しない**）
- `## 概要` を H1・メタ情報の直下に必須。作成者は `Claude Opus 5`
- `## 核心発見サマリ` の冒頭に PNG を画像埋め込み（`mkfig.py` を流用し、
  C1/C2 の可否マトリクスと pp の前回比較を 1 枚に）
- `## 添付ファイル` に `attachment/<同名>/plan.md`（このプラン）とログ一式
- `## 残課題` に C4/C5（108k 再走、`-fa off` 交絡切り分け）と #27917 を引き継ぐ
- 前回レポートの残課題「`head_count_kv` 修正の実機確認」に決着した旨を明記し、
  前回レポート側にも一行追記して相互リンクする
- INDEX への追加も行う

## 検証（この作業自体の成否判定）

| 結果 | 意味 |
|---|---|
| C1 成功 かつ C2 が `expected 46, got 45` で失敗 | 前回レポートのコード読解が実機で裏づけられた。残課題クローズ |
| C1 失敗 | 読解が外れていた。GGUF の実配列長を読み出して原因を切り分け、前回レポートの追記を訂正する |
| C3 の pp が前回から大きく変動 | kpool 書き直しの影響。数値を記録し #27754（58.8 t/s）との差も再掲する |

## 付随して見つかった事項（作業対象外・報告のみ）

前回 spam マークされた #27773 へのコメントは **GitHub API 上まだ残っており**
（`miminashi` / `2026-09-02T14:05:38Z`）、本文中の `<GIST_URL>` が**プレースホルダのまま**である。
かつ内容は既に上流で修正済みの不具合を指しており、記載のワークアラウンドは現 HEAD では有害になる。
**編集・削除するかはユーザの判断**とし、Claude からは投稿本文を書かない
（前回レポートで合意した運用方針どおり）。今回の実機結果が出れば、その判断材料にはなる。

---

## 実行時の変更点（2026-09-03 03:14 JST 追記）

プラン承認後、**checkout 時点で PR HEAD が `fe3187de7a` から `2b533e0950b6b57decf0da01a79521db3612c22d`
「Kpool pooled caching clarify」（2026-09-02 17:53 UTC = 09-03 02:53 JST）へ進んでいた**。
これは前回レポートの副次発見「活発な PR を検証すると、その間に上流が動く」がそのまま再現した形である。

差分は `src/llama-memory-hybrid-idx.cpp` +16/-9、`src/llama-memory-hybrid-idx.h` +4/-4、
`src/models/glm5-next.cpp` +1/-0 の kpool キャッシュ処理のみで、**`head_count_kv` 関連は不変**
（`src/llama-model.cpp:1290,1299` は `n_layer_all`、`conversion/glm.py:464-465` の
`# Pad to block_count` も存置）。検証仮説は変わらないため、**ユーザ依頼の「現在の最新コミット」に
忠実に `2b533e0950` を対象とする**。
