# GLM-5.3-Flash #27773 現 HEAD (`8134115f88`) の実機検証

## Context

前回レポート `report/2026-09-03_035920_glm53flash_pr27773_head_recheck.md` は、#27773 の `2b533e0950` で GGUF 受理条件の反転（未パッチ shard 1 が読めるようになり、前回のパッチ済みが逆に落ちる）を実機確認して終わっている。その後 2 日で PR は **`8134115f88`（2026-09-04 21:25 UTC）** まで進み、**検証対象そのものが変わった**。ユーザ依頼は「その続きで最新版を実機検証する」こと。

### 前回 (`2b533e0950`) 以降に入った PR 固有の変更（本家 master マージ 2 回を除く）

| コミット | 内容 | 検証上の意味 |
|---|---|---|
| `ff6be954ff` | **Add multi stream support** — `llama-model.cpp` から `"GLM5-Next requires a unified KV cache for multiple sequences"` の例外を削除。`llama_kv_cache_context::get_k_storage()` を新設し、kpool select と DSA gather を全ストリーム対応に書き換え | **`--no-kv-unified` が初めて使える**。前回まで kv_unified 固定だった |
| `1b564d2dd8` | Finish Rebase（本家の `n_ff_exp` 変更への追随） | ビルド可否のみ |
| `99fdaab443` | **Sparse FA for DSA prefill** — `build_attn_mha(..., v_mla, 0, ...)` → `..., inp_kpool->n_sel, ...`。`ggml_flash_attn_ext_set_n_kv_max()` に渡る。**FA パス限定の最適化** | **prefill (pp) 速度が変わる可能性**。前回 11k で pp 48.7 t/s |
| `8134115f88` | rebase エラー修正（`llama-model.cpp` +1/-0） | ビルド可否のみ |

さらに master マージ 2 回で CUDA FA 側が大きく動いている（`fattn-mma-f16.cuh` +149/-74、`fattn.cu` +133/-0、`ggml-cuda.cu` +182/-3）。**P100 (sm_60) での速度・安定性が動く可能性がある**。

### コード読解で確定済み（実機では回帰確認のみ）

- `conversion/glm.py:464-465` の `# Pad to block_count` は現 HEAD にも存置
- `llama-model.cpp:1298-1307` の `n_layer_all` も存置
- → **GGUF 受理条件は 46 要素のまま**。未パッチ `Shard_Rewrite` shard 1 がそのまま使えるはず
- 本家 master (`4d9176092d`, 2026-09-05) に `glm5` 系 arch は依然なし。#27773 は OPEN・MERGEABLE
- unsloth の HF リポジトリは `lastModified 2026-08-29` で**前回から未更新**（手元の GGUF がそのまま使える）

### PR スレッドから得た検証の焦点

- timkhronos: 「`--kv-unified` と `--no-kv-unified` の両方が正しく動くようになった」（`ff6be954ff` 報告時）
- timkhronos の自己計測: pool caching 無効 vs 有効で **TG が 32k で 15%、64k で 24%、128k で 38%** 変わる（CPU オフロード環境）
- nicholasshirley (1×4090 + CPU offload): **#27773 は深さが増えても tg が落ちない**（~20 で 25.3 / 7.5k で 24.0 / 28.8k で 23.7 t/s。#27754 は 24.8 → 21.1 → 14.6 と落ちる）。prefill は両者 ~123 t/s で深さに対して平坦
- nicholasshirley: **vision は `5c4bd50` で動く**。ただし **unsloth の mmproj は `swiglu_clamp` リネーム前で "Failed to load CLIP model" になる**。`avar6/GLM-5.3-Flash-BF16-gguf` の `GLM-5.3-Flash-mmproj-bf16.gguf`（1,164,010,144 B）を使う必要がある
- ggerganov は kpool のキャッシュ機構をレビュー中。「コード解析だけでは正しさを検証しづらい。今は動くことを祈る」と述べており、**実機での深文脈確認に意味がある**

## 検証範囲（ユーザ選択済み）

コア（ロード回帰・11k needle の pp/tg・短答・2 slot 品質）に加え、**4 項目すべてを実施**する。後始末は **master 復帰 + 再ビルド、電源は ON のまま**。

---

## 実行計画

cold ロードが 1 回あたり約 11 分と律速なので、**サーバ起動 3 回に測定をまとめる**。総所要は約 2 時間 45 分の見込み。

### Phase 0: 準備（約 25 分）

1. **電源投入**（`bmc-power.sh` は `ALLOW_FAN_NOISE=1` が無いと exit 20。**本プランの承認をもってユーザの明示的指示とみなす**）
   ```bash
   ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 on
   ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu02 on
   until timeout 8 ssh -o ConnectTimeout=5 -o BatchMode=yes -n aws-gpu01 true 2>/dev/null; do sleep 15; done
   ```
   POST 中は `boot-quiet.sh` が自動併走してファンは 2,900rpm 台に収まる（前回実測）。
2. **両機をロック**（`lock.sh` の実体は GPU サーバ側 `/tmp` の symlink。**再起動で消えるので必ず電源投入の後**）
3. aws-gpu01 のローカル修正（`--ui-mcp-proxy` 404 修正）を `~/patches/$(date +%F)-local.patch` に保存して `git stash push -- tools/server/server-http.cpp`
4. **両機で `pull/27773/head:pr27773` を fetch/checkout し、`git rev-parse HEAD` を記録して一致を確認**
   - 前回・前々回とも作業中に HEAD が進んだ。**checkout 時点の実 HEAD を正**とし、`8134115f88` と違えば差分を確認してから続行する
5. 両機で `update_and_build.sh --no-pull --force`（`rm -rf build` のフルビルド、`-j48` / `-j40` で 4〜8 分。**1 台につき 1 本だけ**）
6. **ビルド中に並行して** avar6 の mmproj を aws-gpu01 へ**直接ダウンロード**（同一拠点なので HF 直が原則。1.16 GB / 約 1 分）
   ```bash
   source ~/.config/gpu-server/.env
   ssh -n aws-gpu01 "curl -sL -H 'Authorization: Bearer $HF_TOKEN' -o ~/models/GLM-5.3-Flash-GGUF/mmproj-avar6-bf16.gguf \
     'https://huggingface.co/avar6/GLM-5.3-Flash-BF16-gguf/resolve/main/GLM-5.3-Flash-mmproj-bf16.gguf' && stat -c %s ..."  # → 1164010144
   ```
7. ビルド完了後、`gguf-py` で**前提を数値で確定**（起動を試す前に）
   - `UD-IQ4_XS-nopatch/` shard 1: `head_count_kv` = 46 / `block_count` = 46（前回作成済み・残置されている）
   - avar6 mmproj と unsloth mmproj の **`swiglu_clamp` 系キーの有無を比較**（読めない mmproj で起動すると llama-server が即死するため、**起動前に必ず検査**）

### Phase 1: Run 1 — コア + tg vs 深さ（約 35 分）

`run_cfg.sh C1 <nopatch shard1> 32768 4096`（`--parallel` 省略 = kv_unified 既定）。

- **C1 ロード回帰**: `head_count_kv` エラーが出ないこと、`unused tensor ... -- ignoring` が 29 件、`n_slots` / `kv_unified` の値、cold ロード所要
- **C2 速度**: `needle_11k.json` で pp / tg。**前回 pp 48.7 / tg 8.3 t/s と比較して Sparse FA の効果を見る**
- **C3 品質**: `short.json` / `needle_11k.json` / `needle_2slot_a.json` / `needle_2slot_b.json` を**前回と同一のペイロードのまま**投入
  - 前回の応答 `r_C1_*.json` が添付に残っているので、**前回残課題「短答の出力差はペイロードが残っておらず判定不能」に決着がつく**
- **C4 tg vs 深さ**: `mkneedle2.py` で深さ 3 点を生成し tg を測る（合言葉は毎回変えて記憶汚染を避ける）
  | 深さ | 生成 | 備考 |
  |---|---|---|
  | ~20 tok | `short.json` を流用 | C3 と共用 |
  | ~7.5k tok | `mkneedle2.py <seed> <A> <B> needle_7k.json 26` | 1.36 文字/token 換算 |
  | ~28.8k tok | `mkneedle2.py <seed> <A> <B> needle_29k.json 100` | ctx 32768 に収まる上限付近 |
- VRAM を両機で記録（`nvidia-smi` の最小空き）

### Phase 2: Run 2 — `--no-kv-unified` + vision（約 30 分）

`run_cfg.sh C5 <nopatch shard1> 32768 4096 --no-kv-unified --parallel 2 --mmproj <avar6 mmproj> --no-mmproj-offload`。

- `--parallel 2` にするのは、**non-unified では `n_ctx_slot = ctx / n_parallel`** になり、既定の 4 だと 8192 で 11k needle が入らないため。2 なら 16384 で入る。かつ `n_seq_max > 1` なので**旧 HEAD なら例外で落ちた条件**をちょうど踏める
- **B1**: `kv_unified = 'false'` で起動できること（`ff6be954ff` で例外が消えたことの実証）
- **B2**: `needle_2slot_a/b.json` を同時投入し、合言葉 4 つを正答すること（ストリーム分割の正しさ）
- **B3**: `needle_11k.json` の pp / tg を Run 1 と比較（non-unified のコスト）
- **E1 vision**: ラベル入り PNG 2 枚（小さいロゴ相当 / 大きい図表相当）を base64 で `/v1/chat/completions` に投げ、ラベルを読めるか
- **VRAM 注意**: non-unified は KV がストリーム数ぶん増える。起動ログの KV buffer size を見て、OOM 気配があれば **ctx を 16384 に落とす**（`--parallel 2` は維持）。それでも駄目なら `-ub 512`

### Phase 3: Run 3 — 108k depth collapse 再走（約 55 分）

`run_cfg.sh C6 <nopatch shard1> 131072 4096`（kv-unified 既定）。

- 前回 09-02 の 108k プロンプトは**添付に残っていない**（残っているのは 11k 系のみ）ので、`mkneedle2.py <seed> <A> <B> needle_108k.json 386` で再生成する。**前回とバイト同一ではない旨をレポートに明記**する
- 判定は前回同様「12% 地点と 88% 地点の合言葉を両方正答するか」＋ `check.py` の崩壊検出（同一文字 5 連以上 / 同一 4-gram 反復）
- `graph_reserve: failed to allocate` は前回同様出るが致命ではない見込み（`run_cfg.sh` も警告扱い）
- **kpool は 2 度書き直された上に multi stream 化された**ので、今回いちばん回帰の危険がある箇所

### Phase 4: 後始末（約 20 分）

```bash
.claude/skills/llama-server/scripts/stop.sh aws-gpu01     # llama-server → RPC の順。逆は不可
.claude/skills/llama-server/scripts/rpc-down.sh aws-gpu02
ssh -n aws-gpu01 "cd ~/llama.cpp && git checkout master && git pull --ff-only"
ssh -n aws-gpu02 "cd ~/llama.cpp && git checkout master && git pull --ff-only"
# 両機で update_and_build.sh --no-pull --force を流し直す
ssh -n aws-gpu01 "cd ~/llama.cpp && git stash pop"        # 404 修正パッチを復元
.claude/skills/gpu-server/scripts/unlock.sh aws-gpu01
.claude/skills/gpu-server/scripts/unlock.sh aws-gpu02
```

**電源は落とさない**（ユーザ選択）。ロックは解放し、次の作業者が使える状態で引き渡す。

### Phase 5: レポート作成

- `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で採番し
  `report/2026-09-05_<HHMMSS>_glm53flash_pr27773_sparse_fa_multistream.md` を作成
- [REPORT.md](../../projects/llm-server-ops/REPORT.md) 準拠: H1 は**平易な日本語 50 字以内**、メタ 3 行（作成者は `Claude Opus 5 (1M context)`）、**`## 概要` を最初に**、`## 添付ファイル` に**プランファイルを必ず添付**
- **`## 核心発見サマリ` の冒頭に PNG を画像埋め込み**。図は `mkfig2.py` を改造して 2 枚組にする
  - 左: pp / tg の 3 コミット推移（`7de5a8e39` → `2b533e0950` → 今回）で Sparse FA の効果を示す
  - 右: tg vs 深さ（本セッションの 3 点。nicholasshirley の 4090 実測を参考線として併記）
- `report/INDEX.md` を更新

---

## 再利用する既存資産

前回添付の 5 本のスクリプトは**そのまま再利用できる**（`report/attachment/2026-09-03_035920_glm53flash_pr27773_head_recheck/`）。サーバ側 `/tmp` に scp して使う運用。

| 資産 | 使い方 |
|---|---|
| `run_cfg.sh <tag> <model.gguf> <ctx> <ub> [extra...]` | llama-server の停止 → 再起動 → 起動判定。ログは `/tmp/log_<tag>.log`。**extra args で `--no-kv-unified` / `--mmproj` を渡せる** |
| `ask.sh <payload.json> <out.json>` | GPU サーバ上で `setsid nohup curl` 投入（WS から長時間 curl を張ると切れる対策）。`<out.json>.done` に終了コード |
| `check.py <response.json> <code1> [code2...]` | 合言葉の OK/MISS、thinking 長、崩壊検出、pp / tg / n_prompt / n_pred |
| `mkneedle2.py <seed> <A> <B> <out.json> [n_para] [max_tokens]` | needle ペイロード生成。**11k は `n_para=39`**、7.5k は 26、28.8k は 100、108k は 386 |
| `mkfig2.py` | 数値ハードコードなので**今回の値に書き換えて流用** |
| 前回のペイロード 4 本 | `short.json` / `needle_11k.json`（山茶花6104・木蓮3357）/ `needle_2slot_a.json`（紫陽花7823・金木犀2290）/ `needle_2slot_b.json`（向日葵4519・石楠花8846）。**前回の応答 `r_C1_*.json` と厳密比較する** |
| 未パッチ shard 1 | aws-gpu01 `~/models/GLM-5.3-Flash-GGUF/UD-IQ4_XS-nopatch/`（shard 2〜5 はシンボリックリンク）。**前回作成済みで残置** |
| ビルド | `.claude/skills/llama-server/server-scripts/update_and_build-aws-gpu0N.sh` を `~/llama.cpp/update_and_build.sh` に scp |

## リスクと対処

| リスク | 対処 |
|---|---|
| **作業中に PR HEAD が進む**（前回・前々回とも発生。前回は 35 分で 1 コミット進んだ） | checkout 直後に `git rev-parse HEAD` を記録。プラン記載と違えば差分を確認してから続行し、**レポートには実測した HEAD を書く** |
| master マージで CUDA FA が大きく動いた → **sm_60 でビルド失敗 or 実行時エラー** | 失敗そのものを結果として記録し、master マージ前の `1b564d2dd8` と切り分ける（ビルドが 4〜8 分なので A/B は安い） |
| **`--no-kv-unified` で VRAM 不足** | 起動ログの KV buffer size を確認 → ctx 16384 → `-ub 512` の順にフォールバック |
| **mmproj が読めず llama-server が即死** | ダウンロード直後に `gguf-py` でキーを検査してから起動。読めないと判明したら vision はスキップして事実を記録 |
| aws-gpu02 の痕跡なきハング（前々回 2 回） | SSH 不通を検知したら**電源リセットの前に必ず `bmc-screenshot.sh`** で KVM スクショを保全（CLAUDE.md の必須手順） |
| バックグラウンドジョブの結果が信用できない（前々回 `Monitor` が実在しない結果を報告） | **数値はすべて前景コマンドで再取得**する |
| `pkill -f 'build/bin/llama-serv'` の自己マッチ | `[b]uild/...` と書くか `stop.sh` を使う |

## 検証（このプラン自体の成否判定）

- Run 1 で `head_count_kv` エラーが出ず 11k needle が正答 → **受理条件の回帰なし**が確定
- Run 1 の pp が 48.7 t/s から有意に動く → **Sparse FA が sm_60 でも効く**。動かなければ陰性データ点として記録
- Run 1 の tg が深さ 20 / 7.5k / 28.8k で平坦 → **pooled cache の利点を GPU only 環境で追試**したことになる
- Run 2 が `kv_unified = 'false'` で起動し 2 slot 同時が正答 → **multi stream 対応が P100 + RPC 分散でも機能する**実証
- Run 3 で合言葉 2 か所を正答 → **kpool の 3 度の書き直しを経ても深文脈が壊れていない**確認
