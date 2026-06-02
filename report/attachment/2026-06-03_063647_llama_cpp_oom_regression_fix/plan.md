# llama.cpp 最新版 CUDA OOM リグレッション 根本対策

## Context（背景・目的）

2026-06-02、`llama-up.sh`（→ `start.sh` → `update_and_build-t120h-p100.sh`）が
llama.cpp を master HEAD `d5ab0834a` へ自動 `git pull`・再ビルドした結果、
t120h-p100（4×P100 / 各16GB）で **Qwen3.6-35B-A3B / ctx 131072 / KV q8_0** の
2回目（大きめ）リクエスト時に **CUDA out of memory**（`cuMemCreate` reserve 失敗）で
クラッシュするようになった。報告者は `af6528e6d`（2026-06-01）へロールバックして安定化させ、
detached HEAD でピン留め中。

ユーザ方針: **最新版 llama.cpp を調査し、それに合わせたパラメータ変更で根本対策する**。
ピン留めは根本解決ができなかった場合のフォールバックに留める（ピン留めは恒久対策ではない）。

## 調査で判明した事実

1. **自動更新の経路**: 起動のたびに `update_and_build-{server}.sh` の `git pull`
   （`t120h-p100` 版は L44-46）が master 最新を引き、差分があれば再ビルドする。
   バージョン固定機構は現状なし。そのため `start.sh` 実行で必ず壊れた HEAD に戻る。

2. **OOM の機序（コードリーディングで特定）**: クラッシュは
   `ggml/src/ggml-cuda/ggml-cuda.cu:508-553` の `ggml_cuda_pool_vmm::alloc`
   （`cuMemCreate(&handle, reserve_size, …)` L528）。これは **forward 計算の
   compute scratch 用 VMM プール**で、KV 本体ではなく **オンデマンドで成長**する。
   2回目の大リクエスト処理時にこのプール成長が VRAM を超えて OOM する。

3. **context checkpoint の device 一時バッファ**: checkpoint の作成・復元
   （`common_prompt_checkpoint` → `llama_state_seq_get_data_ext`）は
   **seq の KV cache サイズ相当の device バッファ**を確保しうる。実体保存自体は host RAM
   （`LLAMA_STATE_SEQ_FLAGS_PARTIAL_ONLY`、ON_DEVICE ではない）だが、131072 ctx では
   この一時確保が大きく、"erased invalidated context checkpoint" → full reprocess の
   compute graph 確保と重なってピーク VRAM が跳ねる。関連フラグ
   `--ctx-checkpoints N`（default **32**）/ `--checkpoint-min-step N`（default **256**）/
   `--cache-ram` / `--kv-unified` / `--swa-full`。

4. **上流に同種の既知バグ**: Issue #23371「Qwen3.6 long-context checkpoint retention raises
   VRAM」— 長コンテキストで checkpoint 保持により VRAM が 370〜760 MiB 漸増し解放されない、
   その縁で OOM。35B@131072/q8_0 は 64GB ギリギリのため、この数百MB増で転ぶと整合する。

5. **`af6528e6d..d5ab0834a` の VRAM 関連コミット**（候補。確定には実機 bisect/検証が必要）:
   - `4f3a4beb8` deprecate `llama_set_warmup` — warmup 挙動が変わると起動時の compute プール
     事前確保が縮み、初回後の大リクエストで VMM プールが遅延成長 → OOM の引き金になりうる（**最有力**）。
   - `8e6fff84d` TP: quantized KV cache support — backend-meta を 278 行改変。measure/reserve
     経路に影響しうる（要差分確認）。
   - `236531595` SWA checkpoints store only non-masked cells — Qwen3.6 は非SWAのため影響薄。
   - `de6f727aa` limit max outputs — `n_outputs_max` を制限し reserve を**縮小**する変更。VRAM 削減
     方向で原因とは考えにくい（解放分はプール成長に使えるため）。除外寄りだが念のため監視。
   いずれも単独での確定はできず、**Phase A の実機検証で原因経路とフラグ効果を確認する**。
   なお候補フラグはローカルソース(`common/arg.cpp`)で実在を確認済み:
   `--ctx-checkpoints`(=`-ctxcp`/`--swa-checkpoints`, default 32, 0で無効) /
   `--checkpoint-min-step`(default 256) / `--cache-ram`(=`-cram`, **MiB単位**, default 8192, 0で無効) /
   `--kv-unified` / `--swa-full`。

6. **既存の検証用注入口**: `start.sh` L303-310 に `EXTRA_LLAMA_OPTS`（SERVER_OPTS より後段=優先）が
   あり、**スクリプトを書き換えずに候補フラグを実機で試せる**。現行 t120h-p100 の `SERVER_OPTS`
   は `start.sh:179` の `--flash-attn 1 --poll 0 -b 8192 -ub 8192`。起動は `--parallel 1
   --cache-type-k/v q8_0 --defrag-thold 0.1`（L309）。

## 方針

最新 HEAD を実機で再現し、パラメータで OOM を解消できるか検証 → 成否で分岐。
**GPU サーバ使用のため `gpu-server` スキルでロック取得が必須**（読み取り専用の確認はロック不要）。

### Phase A: 再現 & パラメータ・スイープ（t120h-p100、要ロック）

1. `gpu-server` でロック取得。**まず detached を解除**: リモートで `git checkout master`
   （現状 `af6528e6d` で detached のため、このまま `git pull` すると追跡ブランチ無しで失敗する）。
   その後 `update_and_build-t120h-p100.sh -f` で **master 最新 HEAD** へ更新・再ビルド。ビルド版を記録。
   - 注: 以降のスイープ中も start.sh が毎回 `update_and_build`(git pull) を走らせるが、master 上で
     新規コミットが無ければ再ビルドされない（BEFORE==AFTER）。短時間のスイープ中に HEAD が動いたら
     検出し、テスト対象コミットへ固定して継続する。
2. **ベースライン再現**: 現行パラメータ（ctx 131072）で起動し、6834 prompt + 600 completion を
   連続 3 回。OOM 再現を確認（再現しなければ上流が既に修正済 → そのまま採用し終了）。
3. **候補フラグを `EXTRA_LLAMA_OPTS` で優先順に投入**（start.sh は起動中プロセスがあると exit する
   ため、毎回 `stop.sh` → `start.sh` し log を確認）:
   1. `--ctx-checkpoints 0`（checkpoint 機構を無効化＝ログ警告の発生源を直接断つ。第一候補）
   2. `--checkpoint-min-step` 増大 + `--ctx-checkpoints` 少数（保持数を抑える）
   3. `--cache-ram 0`（host prompt cache 無効、#23371 構成で言及）
   4. `--kv-unified`（KV 確保の見直し）
   - 末手段: `-ub` 縮小（例 2048/512）。ベンチ環境（8192）が変わるため極力回避し、採用時は明記。
4. **131072 ctx を維持したまま** 6834×3 が OOM なし・/health 200・~40 t/s を満たす
   **最小フラグ集合**を確定。

### Phase B-1: パラメータ修正が成功した場合（本命）

- `start.sh` に確定フラグを反映:
  - t120h-p100 の `SERVER_OPTS`（`start.sh:179`）に追記、もしくは Qwen3.6 限定の条件分岐を新設。
  - 経緯コメント（OOM リグレッション・#23371・採用フラグの根拠）を併記。
- `SKILL.md` のサーバ別最適化パラメータ表（L280 付近）と既知問題に追記。
- `update_and_build-*.sh` は **`git pull` のまま据え置き**（最新追従を維持）。リモートは Phase A
  step 1 で既に master 追従・最新 HEAD ビルド済みのため追加のピン解除は不要。
- REPORT 作成。

### Phase B-2: どの組合せでも解消しない場合（フォールバック）

- `update_and_build-{t120h-p100,mi25,t120h-m10}.sh` に **`PIN_REF` 機構**を導入:
  - スクリプト冒頭に `PIN_REF="af6528e6d"`（空なら従来通り最新追従のエスケープハッチ）。
  - `git pull` を `git fetch origin` ＋ **if/else** に置換（`A && B || C` 慣用句は checkout 失敗時に
    C へ落ちるため使わない）:
    ```sh
    git fetch origin
    if [ -n "$PIN_REF" ]; then
      git checkout -q "$PIN_REF"
    else
      git checkout -q master && git pull --ff-only
    fi
    ```
    BEFORE/AFTER 比較はそのまま使え（既に PIN_REF なら no-op で再ビルドなし）、detached でも安全。
  - 検証済みの t120h-p100 のみ `PIN_REF` を設定、他サーバは空のままにするか同値を設定するかを実測後に判断。
- `SKILL.md` にピン運用と解除条件（上流修正のウォッチ）を明記。可能なら上流 issue に再現情報を報告。
- REPORT 作成（パラメータで解消不能だった経緯を記録）。

## 変更対象ファイル

- `.claude/skills/llama-server/scripts/start.sh`（SERVER_OPTS / Qwen3.6 条件分岐）— B-1 本命
- `.claude/skills/llama-server/SKILL.md`（パラメータ表・既知問題）
- フォールバック時のみ: `.claude/skills/llama-server/server-scripts/update_and_build-{t120h-p100,mi25,t120h-m10}.sh`（PIN_REF 機構）
- `report/yyyy-mm-dd_hhmmss_llama_cpp_oom_regression_fix.md`（REPORT.md 準拠、プランファイル添付必須）

## 検証（エンドツーエンド）

1. 確定構成で起動: `.claude/skills/llama-server/scripts/start.sh t120h-p100 unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`
2. `/health` 200 を確認。
3. 6834 prompt + 600 completion トークンを **連続 3 回**投入し、OOM 再発なし・/health 200 維持・
   eval ~40 t/s を確認（報告者の正常版と同条件）。
4. ctx-size は **131072 を維持**（ベンチ環境を変えない）。
5. 終了時にロック解放（`llama-down.sh` / `gpu-server`）。

## 留意点

- sudo は使わない。必要時はコマンドをユーザに提示。
- スクリプトはプロジェクトルートからの相対パスで実行。
- Phase A で「ベースライン再現せず」（上流修正済）なら、パラメータ変更不要でそのまま最新追従を採用し、
  SKILL.md に経緯のみ記録して完了。
- **安全策**: Phase A は報告者が固定した安全版 `af6528e6d` を一旦離れて最新を試す。検証を中断・失敗
  したまま終える場合は、ロック解放前に必ず `git checkout af6528e6d` + 再ビルドで安定版へ戻し、
  稼働サーバを壊れた最新版のまま放置しない。
