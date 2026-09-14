# tensor 分割 × MTP ハングの原因特定と回避策の実証（aws-gpu01）

## Context

`report/2026-09-14_124457_aws_gpu01_split_mode_mtp.md` で、`--split-mode tensor` と
`--spec-type draft-mtp` を併用すると llama-server の初期化が停止する現象を観測したが、
当時は「aws-gpu01 の sudo はユーザ依頼運用」という制約でバックトレースが取れず、
**原因未特定のまま残課題**になっていた（副次発見 6・残課題 1）。

これは実害のある不具合である。本環境の最良構成は tensor 分割（前編レポートの結論）だが、
投機デコードの推奨（MTP 有効）と両立しない。今回ユーザから **gpu01 での sudo / ptrace / gdb
の使用許可（本セッション限り）** が出たので、原因を確定させ、併用可能にする回避策を実証する。

## 事前調査で既に確定した事実（コード変更・実機実行なしで判明）

1. **停止位置はターゲットコンテキストの「ウォームアップ `llama_decode`」に絞り込める。**
   実機 `465e49b9c` では `llama threadpool init` は `common/common.cpp:1790`
   （`common_threadpools::init()`）が出しており、その呼び出し元は
   `common/common.cpp:1408` = **`common_init_result` コンストラクタの最終行**。
   つまりこのログが出た時点で `llama_init_from_model`（sched 生成・graph reserve）は
   **完走済み**。ここから次のログ `creating MTP draft context`
   （`common/speculative.cpp:2307`）までの間で GPU を使う処理は
   **`common/common.cpp:1510-1546` のウォームアップ decode だけ**。
   → 正常時（layer 腕）はこの区間が 189〜295 ms。レポートの「MTP 第 2 コンテキスト生成が
   怪しい」という当時の見立ては**外れ**で、第 2 コンテキストには到達していない。

2. **MTP を有効にすると「ターゲット側」の cparams が変わる。**
   `common/common.cpp:1724` の `cparams.n_rs_seq = params.speculative.need_n_rs_seq()` は
   draft-mtp / eagle3 / dflash / dspark のとき `draft.n_max` を返す（`common/common.h:394-400`）。
   今回は `--spec-draft-n-max 2` なので **`n_rs_seq = 0 → 2`**。
   これは hybrid（SSM）モデルの recurrent state を `mem_size * (1 + n_rs_seq)` に拡張し
   （`src/llama-memory-recurrent.cpp:99`）、**MTP 無効時は no-op だった
   `s_copy_extra` 経路のノードを実グラフに出現させる**（`src/llama-graph.cpp:3129-3153`）。
   rollback 対応アーキは `QWEN35 / QWEN35MOE` のみ（`src/llama-arch.cpp:969-977`）。

3. **`--split-mode tensor` は meta デバイス（TP）実装で、AllReduce はタイムアウトなしのスピン。**
   旧 row-split (`ggml_backend_cuda_split_buffer_type`) は削除済みで、現行は
   `ggml/src/ggml-backend-meta.cpp` + `ggml-cuda` の comm フック。
   AllReduce 経路は `nccl → internal → butterfly` の順に選ばれ
   （`ggml/src/ggml-cuda/ggml-cuda.cu:1155-1240`、**env `GGML_CUDA_ALLREDUCE` で強制可**）、
   internal は **2 GPU 専用**でカーネル内 `while (signal != token) __nanosleep(100);`
   （`ggml/src/ggml-cuda/allreduce.cu:158-169`）。
   **「全 GPU 100% + メインスレッドのみ R で CPU 100% + 進まない」はこのスピンと完全に一致する。**

4. **meta バックエンドには、まさにこの組み合わせを壊しそうな FIXME がある。**
   `ggml/src/ggml-backend-meta.cpp:1827-1834` は、ホストバッファの view ノード
   （= `s_copy_main` / `s_copy_extra`）を **rank 分割せず全 rank に同一ノードを入れる**とし、
   コメントで *「regular usage では no-op だから問題ない」* と明言している。
   `n_rs_seq > 0`（= MTP 有効）は**その前提を崩す唯一の設定**。
   サブグラフ境界の判定でも同じノードが `continue` でスキップされる（`:1940-1946`）ため、
   AllReduce に渡る `nodes[j]`（各 rank の最終ノード、`:2201-2213`）が rank 間でズレると
   3 のスピンが永久に解けない。

5. 環境の実測値: **ptrace_scope = 1**（root なら gdb アタッチ可）、**sudo は NOPASSWD で通る**、
   gdb 15.0.50 あり（`eu-stack` / `pstack` は無し）、バイナリは `not stripped` だが
   **`CMAKE_BUILD_TYPE=Release` で DWARF なし**（`.debug_*` セクション 0 件）＝
   **関数名は出るが行番号・変数は出ない**。`GGML_CUDA_NCCL=ON` / `GGML_CUDA_GRAPHS=ON` /
   `CMAKE_CUDA_ARCHITECTURES=60`。aws-gpu01 は現在**ロック空き・GPU 全枚アイドル・llama-server 停止中**。

6. **ハング時のログが実機に残っているが `/tmp` 配下で、再起動すると消える**
   （`/tmp/mtp-tensor.log`、`/tmp/mtp-tensor2.log`、`~/llama-split-bench/runs/smoke-mtp/`）。

## 主仮説

> MTP を有効にすると `n_rs_seq = 2` となり、hybrid Qwen3.5 の recurrent rollback ノード
> （`s_copy_extra` 系）がターゲットのグラフに出現する。meta バックエンドはこのホスト側
> view ノードを rank 分割もサブグラフ境界判定もせずスキップするため、rank ごとの最終ノードが
> 食い違い、サブグラフ境界の AllReduce が成立しない。AllReduce はタイムアウトなしの
> GPU カーネル内スピン（2 枚）／ NCCL collective 待ち（7 枚）なので、
> **最初の GPU 実行であるウォームアップ decode で永久に止まる。**

この仮説は「枚数非依存」「layer では起きない」「MTP 単独では起きない」「GPU 100% で張り付く」
「hybrid × MTP × TP という稀な三重条件」をすべて説明する。

## 手順

### Phase 0: 準備（5 分）

1. ロック取得: `.claude/skills/gpu-server/scripts/lock.sh aws-gpu01`
   （aws-gpu02 は電源 Off・RPC スタックを立てないので gpu01 のみでよい）
2. **証跡の退避**: 実機 `/tmp/mtp-tensor*.log` と `~/llama-split-bench/runs/smoke-mtp/` を
   ワークステーションへ回収（再起動で失われるため最初にやる）
3. ローカル参照ツリーを実機に合わせる（ユーザ許可済み）:
   `git -C src/llama.cpp fetch origin && git -C src/llama.cpp checkout 465e49b9c`
   （現 HEAD は `c812c543f` = b10128 で実機より 700 コミット古く、読み違いの元）

### Phase 1: 最小再現（10 分）

- **2 枚 / ctx=8192 / `-lv 4`** で tensor + MTP を起動（ログ量を増やして reserve 完走を機械的に確認）。
  7 枚より速く、internal AllReduce（2 GPU 専用経路）を確実に踏むので切り分けに適する。
- 起動作法は llama-server スキルに従う: `ssh -n -f ... setsid nohup ... &`、
  停止は `pkill -x llama-server`（`pkill -f` は自己マッチする）、
  成功判定は `listening on`、失敗判定に `abort` を使わない（正常時も出る）。

### Phase 2: バックトレース採取（15 分）

1. `sudo gdb -p <pid> -batch -ex "thread apply all bt"` を **時間を空けて 2 回**取得
   （同じ場所でスピンしているのか、ゆっくり進んでいるのかを弁別する）
2. 併せて `sudo cat /proc/<pid>/task/*/stack`、`nvidia-smi --query-compute-apps`、
   `perf top -p <pid>`（ホスト側スピンならここに出る）
3. CUDA 側: `cuda-gdb` があれば `info cuda kernels` で**居座っているカーネル名**を取る。
   `allreduce.cu` 由来のカーネル名が出れば仮説はほぼ確定。

判定:
- ホスト bt が `cudaStreamSynchronize` / `ggml_backend_meta_graph_compute` 系で止まる
  → **GPU カーネル内スピン**（仮説どおり）
- ホスト bt が `llama-kv-cache` / `llama-memory-*` の `find_slot` / `split_equal` で止まる
  → CPU 無限ループ（この場合 GPU 100% の説明が要るので再検討）

### Phase 3: 切り分けマトリクス（30 分）

各 1 回、2 枚 / ctx=8192 で起動して `listening on` に到達するかだけを見る（1 回 2〜3 分）。

| # | 変更点 | 通れば言えること |
|---|---|---|
| 1 | `--no-warmup` | ハングがウォームアップ decode である確定（通過後どこで止まるかも見る） |
| 2 | `--spec-draft-n-max 0` | `n_rs_seq = 0` になる → **rollback ノード（`s_copy_extra`）が原因**と確定 |
| 3 | `--spec-draft-n-max 1` | n_max 依存性の有無 |
| 4 | `GGML_CUDA_ALLREDUCE=butterfly` | 原因が CUDA 側 AR（internal/NCCL）か meta 側の分割かを弁別 |
| 5 | `GGML_CUDA_ALLREDUCE=internal` / `nccl` | 経路ごとの再現性 |
| 6 | `GGML_CUDA_GRAPHS=0`（`GGML_CUDA_DISABLE_GRAPHS=1`） | CUDA graphs の関与を除外 |
| 7 | 7 枚で 2・4 を再確認 | 枚数非依存性と、NCCL 経路でも同一原因であることの確認 |

### Phase 4: 行番号付きバックトレース（必要時のみ、+40〜60 分）

Phase 2 の関数名バックトレースで箇所が特定できない場合のみ、
**別ツリー `~/llama.cpp/build-dbg/`** に `-DCMAKE_BUILD_TYPE=RelWithDebInfo` で再ビルドし、
行番号・引数つきの bt を取り直す。**既存 `build/` は再現環境なので絶対に上書きしない。**

### Phase 5: 回避策の実証（20 分）

Phase 3 で通った設定について、**起動できるだけでなく実際に推論が通るか**まで確認する
（`/completion` を 1 発、深さ浅めで decode t/s と `draft_n` / `draft_n_accepted` を取る）。
「起動は通るが投機が効かない」「起動は通るが推論でハングする」では回避策にならないため。

期待する成果物: **tensor 分割 + MTP を同時に使える設定が実在するか否かの white/black な結論**。

### Phase 6: 片付けとレポート（30 分）

1. llama-server 停止（`pkill -x llama-server`）、GPU アイドル確認、**電源は落とさない**
   （ファン爆音の制約。前セッションの方針どおり通電のまま）
2. ロック解放
3. `REPORT.md` 準拠のレポートを `report/` に作成
   （タイトル 50 字以内、`## 概要` を最上位、証跡は `report/attachment/<同名>/` へ）
4. 元レポート `2026-09-14_124457_aws_gpu01_split_mode_mtp.md` の**訂正**:
   - 副次発見 6「ptrace_scope で gdb アタッチできない」→ 実際は sudo が NOPASSWD で通る
   - 第 1 節の「MTP 第 2 コンテキストが怪しい」→ 実際はウォームアップ decode
   （追記の形で残し、当時の判断は消さない）

## 検証方法

- **原因の確定**: バックトレース（同一箇所でのスピンを 2 回以上観測）＋
  Phase 3 #2（`--spec-draft-n-max 0`）で通ることの再現性 3 回。
- **回避策の確定**: Phase 5 で `/completion` が完走し、`draft_n_accepted > 0` が返ること。
- **副作用がないこと**: 回避策を入れた状態で layer 腕も従来どおり動くこと（1 回）。

## 想定所要

Phase 4 なしで **約 1 時間 50 分**、Phase 4 ありで **約 3 時間**。

## 留意点

- **sudo は本セッション限りの許可**。CLAUDE.md の sudo ポリシー（aws-gpu01 は未収載）は変更しない。
  レポートには「今回はユーザの明示許可で実行した」と明記する。
- **電源操作は一切しない**（`ALLOW_FAN_NOISE` を使わない）。aws-gpu02 には触れない。
- llama.cpp への**投稿文は書かない**。原因が特定できても、上流報告の素材（再現手順・
  バックトレース・該当コード行）を提示するところまでに留める（`AGENTS.md` および
  `report/2026-09-06_234319_glm53flash_pr27773_vs_27754_depth.md` の運用）。
- `~/llama.cpp` の作業ツリーは clean。**実機のソースもビルドも書き換えない**
  （Phase 4 の別ツリー追加を除く）。
