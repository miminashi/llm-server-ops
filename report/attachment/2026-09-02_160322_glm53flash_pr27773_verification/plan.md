# GLM-5.3-Flash 対応 PR の最新版を実機検証する（第 2 回）

## Context

2026-08-29 のレポート [`2026-08-29_220506_glm53flash_upstream_pr_verification.md`](../../projects/llm-server-ops/report/2026-08-29_220506_glm53flash_upstream_pr_verification.md)
で GLM-5.3-Flash 対応 PR 2 本（#27752 / #27754）を aws-gpu01+02 の RPC 分散 13 GPU で実機検証した。
そこから 3 日が経ち、**上流の状況が大きく動いた**ので同じ枠組みで再検証する。

事前調査（本セッションで確認済み、すべて 2026-09-01 21:00 JST 時点）:

| 項目 | 前回 (08-29) | 現在 (09-01) |
|---|---|---|
| 本家 master | `cc83d7b48`、`glm5next` 未対応 | **`9d817213a`（2026-09-01 13:55 CEST）、依然 `glm5next` / `glm5-next` の記述なし** — `git grep -l -i 'glm5next\|glm5-next' origin/master -- src/ gguf-py/ convert_hf_to_gguf.py` が空 |
| #27752 (eauchs) | draft 解除・REVIEW_REQUIRED・MERGEABLE | **CONFLICTING / DIRTY**。head `4bc437ab84`。`n_pool>65535` の reshape 修正 (`5390dd741f`) が入った |
| #27754 (danielhanchen) | **draft** | **draft 解除**。head `949f7efb09`。`00699716c2` "Faster inference" / `d07e71ede7` "Add MTP support" が新規 |
| #27773 (timkhronos) | draft・未検証 | **draft 解除。CISC / ngxson がレビュー中、CISC が ggerganov に `kpool` のレビュー依頼**。head `1eca274ed6`（本日 12:05Z）。arch 名 `glm5-next`、MTP は別 PR #27917 に分離 |

つまり **レビューの主戦場が #27752 から #27773 へ移った**。前回レポートは「本家マージの本命は #27752」と
書いているが、この判断は更新が必要である。#27773 は前回一度も実機に載せていない。

PR スレッドでは前回に無かった新しい不具合が議論されている。**深い文脈で `@@@@…` を吐く depth collapse** が
#27752 と #27754 の両方で再現し（feni6: Metal / UD-Q4_K_XL、byte-identical prompt で 108,710 tok から発生）、
`-ub 128` が全構成で回避策になる一方、matteoscalabrini は **CUDA + `-fa on` + `-ub 4096` では起こらない**と
報告している。**P100 (sm_60) + RPC 分散という組み合わせは誰も報告していない**ので、ここは新規のデータ点になる。

ユーザ選択により、本作業のスコープは以下に確定した:

- 検証対象は **#27773 と #27754 の 2 本**（#27752 は今回見送り）
- **depth collapse の再現を試す**
- 作業後は **master に戻して電源 OFF**（前回と同じ後始末）

### GGUF の互換性（事前確認済み）

3 本の PR は **indexer 系のテンソル名がすべて同一**（`blk.%d.indexer.*` と `blk.%d.indexer_compressor_*`）で、
#27773 だけが arch 名 `glm5-next` と KV 接頭辞を使う。前回調べた `Shard_Rewrite/` の shard 1 との差分は
**arch 名の表記と `index_share_mtp` キー 1 個の追加だけ**だったので、**手元の 146 GiB はそのまま流用でき、
入れ替えるのは 9.4 MB の shard 1 のみ**である。HF 側の
`Shard_Rewrite/GLM-5.3-Flash-UD-IQ4_XS-00001-of-00005.gguf_file` は 9,429,984 B で前回記録と一致（未更新）。

---

## 作業計画

### 前提（ユーザ承認が必要な事項）

**本プランの承認をもって、aws-gpu01 / aws-gpu02 の電源投入（`ALLOW_FAN_NOISE=1`）を実施する。**
両機は現在 `System Power: off`。CLAUDE.md の制約により、明確な指示なしに電源投入はしない運用になっている。

### Phase 0: 準備（〜15 分）

1. `bmc-power.sh aws-gpu01 on` / `aws-gpu02 on`（`ALLOW_FAN_NOISE=1`）→ SSH 疎通待ち
2. `lock.sh aws-gpu01` / `lock.sh aws-gpu02`（**両機必須**）
3. aws-gpu01 の `~/llama.cpp` の未コミット変更（`--ui-mcp-proxy` 404 修正）を
   `git diff > ~/patches/2026-09-01-local.patch` + `git stash push -m pre-glm5next-2` で退避
4. `~/models/GLM-5.3-Flash-GGUF/UD-IQ4_XS/`（156,822,111,075 B）の残存確認、ディスク空き確認

### Phase 1: 検証環境の下ごしらえ

**needle 生成スクリプトの拡張**（ローカル）: 前回の
`report/attachment/2026-08-29_220506_.../mkneedle.py` は `n_para` 引数を持つのでそのまま流用し、
**浅い位置と深い位置の 2 か所に合言葉を埋める版**に拡張して `mkneedle2.py` とする
（feni6 の "both planted codes correct" 判定を模す）。生成するのは 3 種:

| 名前 | 概算トークン | 用途 |
|---|---|---|
| `needle_11k` | 約 11k | 前回との連続性のための健全性チェック |
| `needle_108k` | 約 108k（`n_para` ≈ 1660） | depth collapse の再現（feni6 の境界 108,710 tok 相当） |
| `needle_2slot_a/b` | 各 11k | 2 slot 同時実行の混線チェック（seed と合言葉を変えた 2 本） |

**GGUF の shard 1 差し替え準備**（#27773 用、非破壊）:

```
~/models/GLM-5.3-Flash-GGUF/UD-IQ4_XS-rewrite/
  ├── GLM-5.3-Flash-UD-IQ4_XS-00001-of-00005.gguf   ← Shard_Rewrite からダウンロードした実体 (9.4 MB)
  └── ...-0000{2,3,4,5}-of-00005.gguf                ← 元ディレクトリへのシンボリックリンク
```

元の `UD-IQ4_XS/` は一切触らないので、#27754 アームへ戻すときの復元作業が不要になる。

### Phase 2: アーム A = PR #27773（新・本命、初検証）

1. 両機で `git fetch origin pull/27773/head:pr27773 && git checkout pr27773` → **HEAD の SHA 一致を確認**
   （checkout 時点の SHA を必ず記録する。#27773 は本日だけで 6 コミット進んでいる）
2. 両機で `update_and_build.sh --no-pull --force` を並行実行（各 20 分前後）
3. `rpc-up.sh` で aws-gpu02 の RPC ワーカー起動
4. **A-1 起動確認**: `UD-IQ4_XS-rewrite/` を指定、`--parallel` 省略（= `n_parallel=4 + kv_unified=true`）、
   `ctx 32768 / -fa on / -ub 512`。ここで見るのは 3 点:
   - **GGUF が読めるか**（arch 名 `glm5-next` + `index_share_mtp` で unknown key / missing tensor が出ないか）
   - PR 本文が言う「複数シーケンスには `--kv-unified` が必要」の制約が `llama-server` 既定で満たされるか
   - `W model has unused tensor` の系統（#27754 では `blk.45.nextn.*` が unused になっていた。#27773 は
     MTP を #27917 に分離しつつ NextN テンソルは温存すると書いているので、扱いが変わる可能性がある）
5. **A-2 `-ub` スイープ**: 512 → 1024 → 2048（→ 通れば 4096）。前回 #27754 は 1024 が上限、
   #27752 は 512 で `failed to allocate compute pp buffers`。#27773 がどちらの挙動かを確定する。
   **判定は `graph_reserve: failed to allocate compute buffers`（警告・継続可）と
   `failed to allocate compute pp buffers` + `exiting due to model loading error`（致命）を区別する**
   （前回の副次発見）
6. **A-3 品質**: 短答「日本の首都は」＋ `needle_11k` ＋ **2 slot 同時**（`needle_2slot_a/b`）。
   `temperature 0` / `max_tokens 256`。前回 #27752 は 2 slot 同時で思考が発散して回答に到達しなかったので、
   #27773 が同じ弱点を持つかを見る
7. **A-4 速度**: pp / tg を `/v1/chat/completions` の `timings` から取得。VRAM は両機で `nvidia-smi` 集計

### Phase 3: アーム B = PR #27754（前回の推奨構成の追試）

1. 両機で `pull/27754/head` を checkout（head は `949f7efb09` 想定、実 SHA を記録）→ 再ビルド
2. モデルは**元の `UD-IQ4_XS/`**（arch `glm5next`）を指定
3. **B-1**: 前回の推奨構成 `ctx 32768 / -fa on / -ub 512` が最新ヘッドでも成立するか
4. **B-2**: `00699716c2` "Faster inference" の効果測定 — 前回の同一構成 **pp 57.9 t/s (`-ub 512`) /
   67.9 t/s (`-ub 1024`)** と直接比較する
5. **B-3**: `d07e71ede7` "Add MTP support" — 前回は compute buffer 不足で起動できなかった
   `--spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-p-min 0.75` を再試行。
   失敗した場合は**失敗サイズが MTP 有無で一致するか**を前回同様に確認して切り分ける
6. **B-4**: 2 slot 同時 needle（前回は両方正解。退行がないかの確認）

### Phase 4: depth collapse の再現（両アームで実施）

PR スレッドの主題なので、**両アームで同一の byte-identical プロンプト**を使う。

| # | 構成 | 見るもの |
|---|---|---|
| C-1 | `ctx 131072 / -fa on / -ub` は各アームの実用上限 | ctx 131072 がそもそも VRAM に収まるか（前回は ctx 32768 と 262144 のみ実測） |
| C-2 | `needle_108k` を投入、`-ub` 実用上限 | `@@@@…` 化するか、2 か所の合言葉を両方当てられるか |
| C-3 | C-2 が崩れた場合のみ `-ub 128` | feni6 の回避策が P100 でも効くか。崩れなければ matteoscalabrini の「CUDA + `-fa on` では起きない」を補強する陰性データ点になる |

**時間見積**: `needle_108k` の prefill は pp 68 t/s なら約 27 分、`-ub 128` に落とすと 1 時間超。
**C-3 は C-2 が崩れたときだけ**実施する。

**長時間リクエストの注意**（前回の副次発見）: ワークステーションから `curl` を長時間張ると切断されるので、
**GPU サーバ上で `setsid nohup curl` を走らせて結果をファイルに書き、それをポーリングする**。
また待機ジョブを立てたら通知が来るまで別コマンドを打たない。

### Phase 5: 後始末（ユーザ選択: master 復帰 + 電源 OFF）

1. `stop.sh aws-gpu01` → `rpc-down.sh`（**この順序。逆にするとメインホストの推論が壊れる**）
2. 両機 `git checkout master && git pull`、aws-gpu01 は `git stash pop` で 404 修正パッチを復元
3. 両機で `update_and_build.sh --force` 再ビルド（次回 `llama-up.sh aws-gpu01` が既定の
   DeepSeek-V4-Flash 構成でそのまま動くようにする）
4. `unlock.sh` 両機 → `bmc-power.sh <server> soft`（ACPI グレースフル）で電源 OFF
5. `UD-IQ4_XS-rewrite/` のシンボリックリンクディレクトリは**残す**（次回の #27773 追試を安くするため。
   実体は 9.4 MB のみ）

### Phase 6: レポート作成

`REPORT.md` に従い `report/yyyy-mm-dd_hhmmss_glm53flash_pr27773_verification.md` を作成する
（タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得）。

- H1 は 50 字以内、`## 概要` を最上位に置く（5〜8 段落、平易な日本語、数値・SHA は本文へ）
- `## 核心発見サマリ` の冒頭に **PNG を画像埋め込み**（前回の `mkfig.py` を流用し、
  **PR × `-ub` の起動可否と pp 速度のマトリクス**＋**depth collapse の可否**を図示）
- 添付 `report/attachment/<レポート名>/` に plan.md、`mkfig.py`、`mkneedle2.py`、全 llama-server ログ
- **前回レポートの「本家マージの本命は #27752」という記述が古くなった点を明記**し、
  相互リンクを張る（前回レポート側は書き換えない）
- 作成者は `Claude Opus 5`

---

## 検証（どうやって「できた」と判断するか）

| 判定対象 | 合格条件 |
|---|---|
| master の未対応 | `git grep -i 'glm5next\|glm5-next' origin/master -- src/ gguf-py/ convert_hf_to_gguf.py` が空（確認済み、レポート時点で再確認） |
| #27773 の GGUF 互換 | shard 1 差し替えのみで `llama_model_load` が通り、`missing tensor` / `unknown model architecture` が出ない |
| 各アームの起動 | `/tmp/llama-server.log` に `listening on` が出て `curl http://10.8.2.1:8000/health` が `{"status":"ok"}` |
| 品質 | `temperature 0` で `needle_11k` の合言葉を完全一致で回答。2 slot 同時でも両方正解 |
| 速度 | `/v1/chat/completions` レスポンスの `timings.prompt_per_second` / `predicted_per_second` を記録し、前回の 57.9 / 67.9 t/s と比較 |
| depth collapse | `needle_108k` の応答が `@@@@` 等の反復に陥らず、埋めた 2 か所の合言葉を両方当てる |
| 後始末 | 両機 `git rev-parse HEAD` が master 一致、`build/bin/llama-server` が更新済み、`System Power: off`、ロック解放 |

## 中断ポイント（時間が不足した場合の優先順位）

1. **Phase 2（#27773 の起動可否と GGUF 互換）** — 最優先。ここだけでもレポートの価値は成立する
2. **Phase 3（#27754 の追試と "Faster inference" の効果）**
3. **Phase 4（depth collapse）** — 最も時間を食うので最後。C-2 まで到達できなければ「未実施」と明記する
