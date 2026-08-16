# llama.cpp fine-tuning の歴史と現状をレポート化する

## Context

本日 (2026-07-25) 既に 2 本のレポートを作成済み:

- `2026-07-25_045111_llama-cpp-cpu-finetune-broken.md` — master (b7542) の `llama-finetune` が modern LLM 全てで abort することの一次確認
- `2026-07-25_054901_llama-cpp-cpu-finetune-pr25428-verify.md` — 上流修正候補 PR #25428 の独立検証

いずれも**「今どう壊れているか」の実測**であり、**「なぜこの領域が構造的に壊れ続けるのか」という経緯**は記録されていない。ユーザから「歴史と現状がわかるようにレポートに残してほしい」との依頼があった。

本セッションで、ローカル `src/llama.cpp` の全 git 履歴 (10,118 コミット) と GitHub 側の PR/Issue を突き合わせて調査済み。その結果、llama.cpp の fine-tuning は **一度完全に削除され、まったく別の設計で作り直されている** こと、そして **「個人が実装 → 作者離脱 → 腐る」というサイクルを 2 周している** ことが判明した。

さらに調査の副産物として、**前セッションで `sched_reserve()` に当てた 1 行 sed パッチと同一の問題を、PR #21924 が `ggml-backend.cpp` 側で汎用的に解決済み** であることが分かった (同一 assert・同一根本原因)。この PR は 2026-04-15 以降 3 ヶ月放置されている。

期待する成果: 今後 llama.cpp の training を業務のクリティカルパスに置くかどうかを判断する際の、一次資料となるレポート。

---

## 調査済み事実（レポートに書く内容の骨子）

すべて確認済み。実装フェーズで再調査は不要。

### Phase 0: 発案 (2023-04〜05)

- 発端は ggml リポジトリ Issue #8 のコメント欄での議論
- **PR #1360** (xaedes, 2023-05-13 マージ, **+6,315 行**) — 「Training a llama directly with ggml would be really nice」
- ggml に backward pass を新規実装: `ADD1` / `ACC` / `SET` / `LOG` / `SUM_ROWS` / `SILU_BACK` / `RMS_NORM_BACK` / `GET_ROWS_BACK` / `DIAG` / `DIAG_MASK_ZERO` / `ROPE_BACK`
- **重要**: PR 本文で `GGML_OP_SET` の導入理由を「**Necessary for propagating gradients through kv cache**」と明記。今日 `SET_ROWS` で詰まっているのと同じ構造の課題が最初期から中核だった
- 成果物 `examples/baby-llama/baby-llama.cpp` (1,687 行) — 小さな llama をサイン波出力に学習させるデモ

### Phase 1: LoRA fine-tune の誕生 (2023-06〜09)

| 日付 | PR | 内容 |
|---|---|---|
| 2023-06-13 | #1652 | `train-text-from-scratch` に発展 |
| 2023-08-28 | #2439 | メモリ改善、`common/train.cpp` (1,496 行) に共通化 |
| 2023-09-28 | **#2632** | `examples/finetune/finetune.cpp` (1,935 行) + `export-lora` 誕生 |

- #2632 の TODO に当時の壁が残存: 「backward pass creates unsupported operations like `mul_mat(F32, Q)`」「Finetuning 32-layer models requires more than 8192 graph nodes, so we may need increase `GGML_MAX_NODES` and `GGML_GRAPH_HASHTABLE_SIZE`」
- → **グラフノード数不足は 2023 年から既知**。#21924 と前セッションの 8x/32x パッチはこの再演

### Phase 2: 作者離脱と削除 (2023-11〜2024-07)

- **xaedes の最終コミットは 2023-11-07** (#3974)。全 11 コミットを残し離脱
- 以降 8 ヶ月、`finetune` に入るのは周辺の小修正のみ (`-ngl` 追加、loraB ゼロ初期化、BLAS 高速化、README typo、double free 修正、`ggml_allocr` lifetime の "tmp workaround")
- 2024-07-24 Issue **#8662** — ユーザ報告「`train-text-from-scratch` が区切り線しか出力しない」
- 2024-07-25 **PR #8669** (ngxson) で `examples/finetune` と `train-text-from-scratch` を削除
  > These examples are no longer working and require too much efforts to maintain. Therefore, they need to be removed.
  > It's always sad to say goodbye, but we need to move on... (let's hope that we can bring it back one day)
- 2024-11-03 `baby-llama` も #10144 (CPU backend 分離) のついでに削除
- → **fine-tuning 機能が完全消滅した 10 ヶ月間**

### Phase 3: ゼロからの再構築 (2024-11〜2025-05)

- 復活させたのは **Johannes Gäßler** (CUDA バックエンド主要メンテナ)。xaedes のコードは継承せず `ggml_opt` を土台に作り直し
- 2024-11-16 `ggml/988` 「new optimization interface」
- 2024-11-22 ggml Issue **#1025** で構想公開。当初は GPT-2 example で先行実装する計画
- 2024-11-27 PR **#10544** 起票 → **2025-05-12 マージ (約 5.5 ヶ月)**
- 方針転換の理由 (#10544 本文):
  > I decided to implement the training directly in llama.cpp after all because the GPT-2 GGML example is already pretty complex, would require a significant amount of effort to refactor, and **I'm not familiar with the codebase at all**.
- 設計: `n_ctx` = 学習時最大系列長 / `n_batch` = optimizer step あたりトークン数 / `n_ubatch` = 並列度。`llama_opt_init()` / `llama_opt_epoch()` を `llama.h` に追加、`llama-model-saver.cpp` でモデル保存
- **マージ時点で制約が明示済み**:
  > CPU training seems to work, other backends are missing support for some GGML ops.
  > ~20 hours and ~100 GB RAM with LLaMA 3 8b (1 epoch over Wikitext-2)
- 新 `examples/training/finetune.cpp` は **96 行** (xaedes 版 1,935 行に対し機能を大幅に絞った)

### Phase 4: 再放置と再破壊 (2025-08〜現在)

`examples/training/` の全変更履歴 (8 コミット):

| 日付 | 内容 | 種別 |
|---|---|---|
| 2025-05-12 | #10544 初期実装 | 機能 |
| 2025-05-26 | #13803 README typo | 些末 |
| **2025-08-14** | **#13873 SGD optimizer + CLI 引数** (Jonathan Graehl) | **機能 (最後)** |
| 2025-12-14 | #17937 common_sampler リファクタ | 巻き添え |
| 2026-03-04 | #17331 GGUF ロケール修正 | 巻き添え |
| 2026-03-31 | #21176 `common_init()` 移動 | 巻き添え |
| 2026-04-17 | #21936 libcommon リネーム | 巻き添え |
| 2026-07-23 | #20834 mlock/mmap リファクタ | 巻き添え |

`ggml/src/ggml-opt.cpp` は全期間で **7 コミットのみ** (2024-11 × 3, 2025-05 × 2, 2025-08 × 1, 2026-04 × 1 — 最新はメモリリーク修正 #21592)。

その間の master 側の破壊イベント:

| 日付 | 変更 | training への影響 |
|---|---|---|
| 2025-06-27 | #14274 `ggml_set_rows` 追加 | — |
| **2025-07-03** | **#14285 KV cache が `ggml_set_rows` へ移行** | backward 未実装 → **学習パス崩壊** |
| 2025-08-28 | #15505 `LLAMA_SET_ROWS` フォールバック撤去 | 旧経路消滅、退避不能に |

→ **最後の機能追加 (2025-08-14) の直前に KV cache が SET_ROWS へ移行**。Issue #18805 はこの非同期が約 1 年放置された結果。

### 現在オープンな 3 つの修正 PR

| PR | 作者 | 状態 | 規模 | アプローチ |
|---|---|---|---|---|
| **#21924** | System64fumo | OPEN / 非 Draft / 最終更新 2026-04-15 | +40 / -4、3 ファイル | `SET_ROWS` backward を実装 + sched hash_set を動的拡張 |
| **#22705** | srossitto79 → DFveloper | OPEN / **Draft** / 最終更新 2026-07-25 | +7,067 / -196、66 ファイル | MoE 向け QLoRA を全バックエンドに新規実装 |
| **#25428** | daineball | **Draft** / 最終更新 2026-07-13 | (前レポートで検証済) | qwen2 のみ training 時に KV cache を回避 |

**#21924 の詳細** (本レポートの中核発見):

- `ggml/src/ggml.c`: `ggml_compute_backward()` に `GGML_OP_SET_ROWS` ケース追加 (`ggml_get_rows_back(grad, src1, src0)`)、`ignore_src[1]` に SET_ROWS 追加、inplace op の assert 緩和 (`SET_ROWS` / `SCALE` / `SET` / `ROPE` 許可)、`ggml_graph_dup()` で `force_grads` 時に `3 * n_nodes` を確保
- `ggml/src/ggml-backend.cpp`: **`ggml_backend_sched_grow_hash_set()` を新規追加し、`GGML_ASSERT((int)sched->hash_set.size >= graph->n_nodes + graph->n_leafs)` を撤去**
- `examples/training/finetune.cpp`: `flash_attn_type` を強制 `DISABLED`
- 停滞理由: JohannesGaessler が「なぜ backend scheduler を触るのか」と質問 → 作者がバックトレースを提示して回答 (2026-04-15) → **以降レスポンスなし、レビュー 0 件**
- 作者の明示的限界: 「This doesn't fully fix/improve/change the behavior of the finetune tool, It **only fixes the crashes**」

**#22705 の詳細**:

- ggml-gh-bot が投稿直後に **規約違反 4 件** を指摘 (新規コントリビュータの複数 PR / 複数バックエンド同時変更 / AI 生成コンテンツ / PR が巨大)
- `test_zorvian.bat` / `zorvian_training_data.jsonl` / `vulkan_implementation_plan.md` 等の個人作業ファイルが混入
- 2026-06-04 MrDrMcCoy が Qwen3.6-35B-A3B で実行しクラッシュ報告 (`CLAMP` の inplace op が backward graph でスキップされ続けた末に `GGML_ASSERT(!src1_needs_grads || ggml_are_same_shape(...))` で abort)
- **メンテナからの反応は bot 以外ゼロ**

### 前セッション結果との突き合わせ（新発見）

前セッション (`pr25428-verify` レポート) で遭遇した
`GGML_ASSERT((int)sched->hash_set.size >= graph->n_nodes + graph->n_leafs) failed` (`ggml-backend.cpp:1866`)
に対し、`src/llama-context.cpp` の `sched_reserve()` で `max_nodes` を `8 *` にする 1 行 sed パッチを当てて回避した。

**PR #21924 は同じ assert を `ggml-backend.cpp` 側で汎用的に解決している** — `ggml_backend_sched_grow_hash_set()` でハッシュセットを必要に応じ再確保し、assert 自体を撤去する。llama-context 側の係数いじりではなく scheduler 自身が伸びるため、モデルサイズ・batch サイズに依存しない。**前セッションのローカルパッチの upstream 版が既に 3 ヶ月前から存在していた**ことになる。

---

## 実施内容

### 1. タイムライン PNG の生成

`matplotlib 3.6.3` はローカルで利用可能 (確認済)。ローカル実行のみ、GPU サーバ不要 = `gpu-server` スキルのロック不要。

**図の仕様**:

- 上段: `training` 関連パス (`examples/baby-llama` / `examples/train-text-from-scratch` / `examples/finetune` / `examples/training` / `common/train.cpp` / `ggml/src/ggml-opt.cpp` / `src/llama-model-saver.cpp`) の**月別コミット数**を棒グラフに
- 2025-05 以降の棒は「機能変更」と「巻き添えリファクタ」を色分け (上記 Phase 4 の表の種別に従う)
- 背景に時代区分をシェーディング: `xaedes 期` / `漂流期` / `**機能不在期 (2024-07〜2025-05)**` / `Gäßler 期` / `再漂流期`
- 縦線マーカーでイベント注記: #1360 / #2632 / xaedes 離脱 / **#8669 削除** / #10544 再実装 / **#14285 SET_ROWS 移行** / #13873 最終機能追加 / #18805 起票
- 「機能不在期」と「再漂流期」は視覚的に強調 (ハッチング等)
- 日本語ラベルのフォント不足が起きうるため、軸・注記は英数字主体にし、凡例のみ日本語 or 全て英語で作図する (実行時にフォント警告を確認して判断)

データ取得コマンド (調査済、再利用可):

```bash
cd src/llama.cpp
git log --format='%ad' --date=format:'%Y-%m' -- \
  'examples/baby-llama' 'examples/train-text-from-scratch' 'examples/finetune' \
  'examples/training' 'common/train.cpp' 'ggml/src/ggml-opt.cpp' 'src/llama-model-saver.cpp' \
  | sort | uniq -c
```

生成スクリプトはスクラッチパッドに置き、成果物 PNG と一緒に attachment へコピーする。

### 2. レポート本文の作成

- **ファイル名**: `report/2026-07-25_200322_llama-cpp-finetune-history.md`
  (タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得済み)
- **タイトル (H1)**: `# llama.cpp の fine-tune は 2 度作られ 2 度放置された — 3 年史と現状`
- **メタ情報**: 実施日時 / 報告日時 / 作成者 `Claude Opus 5 (1M context)`

**セクション構成** (REPORT.md カノニカル名):

| セクション | 内容 |
|---|---|
| `## 概要` | 5〜8 段落、通読できる平易な日本語。数値・SHA・PR 番号は極力省き、「なぜ調べたか」「2 度作られ 2 度放置された経緯」「今 3 本の PR がどう位置づくか」「業務判断への示唆」を物語として書く |
| `## 添付ファイル` | plan.md、タイムライン PNG、作図スクリプト、git 集計の生ログ |
| `## 核心発見サマリ` | 冒頭にタイムライン PNG を画像埋め込み。直後に `**結論**:` 段落で 2 サイクル構造・破壊の因果 (#14285 → #18805)・#21924 が前セッションのパッチの upstream 版であること・3 PR の評価を凝縮 |
| `## 前提・目的` | 背景 (本日の 2 レポートは「今どう壊れているか」のみ)、目的 (経緯の一次資料化) |
| `## 参照レポート` | broken レポート / pr25428-verify レポートへの相対リンク |
| `## 結果詳細` | Phase 0〜4 の年表 (上記「調査済み事実」を整形)、3 PR の比較表、#21924 の diff 詳細、破壊イベントの因果表 |
| `## 副次発見` | 2023 年 #2632 の TODO に既にグラフノード不足が記録されていた件、`GGML_OP_SET` が最初から KV cache 勾配伝播のためだった件、#22705 に個人作業ファイルが混入している件、#10544 が「codebase に不慣れ」を理由に方針転換した件 |
| `## 残課題` | (a) PR #21924 の `ggml_backend_sched_grow_hash_set` を前セッション環境で検証し、`sched_reserve` sed パッチを置き換えられるか確認 (b) その結果を PR #25428 コメントドラフトに追記 / #21924 にも投稿 (c) #21924 のレビュー停滞を JohannesGaessler 宛に再喚起するか判断 (d) 定期スモークテストの検討 |
| `## 結論・対応` | HF Trainer + LoRA 方針の継続が歴史的にも正当であること、llama.cpp training をクリティカルパスに置かない判断根拠 |

**執筆上の注意**:

- 既存 2 レポートと**内容を重複させない**。実測 (loss / PPL / assert 行番号) はそちらに委ね、本レポートは経緯・構造・PR 地図に徹する
- 前セッションで「upstream fix を待つ」と書いた対象が、実は #21924 / #25428 の 2 系統に分岐していることを明示する

### 3. 添付ディレクトリの整備

```
report/attachment/2026-07-25_200322_llama-cpp-finetune-history/
├── plan.md                    # 本プランファイルをコピー
├── finetune_timeline.png      # タイムライン図
├── plot_timeline.py           # 作図スクリプト
└── git_timeline_raw.log       # git log 集計の生出力 (月別コミット数 + 主要コミット一覧)
```

### 4. INDEX.md への追記

`report/INDEX.md` の **「## 12. llama.cpp CPU fine-tune 検証（mmns-cpu-llm）」** セクション末尾に 1 行追加。
既存 2 エントリと同じ `- [x] [ファイル名](ファイル名) — 説明` 形式、説明は同セクションの粒度 (数百字) に合わせる。

なお本レポートは mmns-cpu-llm での検証ではなく git 履歴調査なので、セクション見出しを
「## 12. llama.cpp fine-tune 検証と経緯調査」等へ改める案も検討する (既存 2 行の説明文は変更しない)。

### 5. メモリ更新

`/home/ubuntu/.claude/projects/-home-ubuntu-projects-llm-server-ops/memory/project_llama_cpp_finetune_broken.md` を更新:

- 既存の「Issue #18805 で b7405-b7717 全滅」等の記述は保持
- 追記する非自明な知見:
  - llama.cpp の training は「個人実装 → 作者離脱 → 腐敗 → 削除/放置」を 2 周した構造的に無主の領域であり、**推論側リファクタが定期的に破壊する位置にある**
  - オープンな修正 PR は 3 本 (#21924 汎用 / #25428 qwen2 限定 / #22705 MoE QLoRA・Draft 巨大)、いずれもメンテナのレビューが付いていない
  - #21924 の `ggml_backend_sched_grow_hash_set` は前セッションの `sched_reserve` 1 行パッチの upstream 汎用版
  - **Why / How to apply** 行を付与し、新レポートへ `[[...]]` リンクを張る
- `MEMORY.md` の該当行 (`llama.cpp llama-finetune は 2026-07-25 時点で壊れている`) のフックを、歴史的知見を含む形に更新

---

## 変更するファイル

| パス | 操作 |
|---|---|
| `report/2026-07-25_200322_llama-cpp-finetune-history.md` | 新規作成 |
| `report/attachment/2026-07-25_200322_llama-cpp-finetune-history/` | 新規作成 (PNG / スクリプト / 生ログ / plan.md) |
| `report/INDEX.md` | セクション 12 に 1 行追記 (＋見出し名の見直し) |
| `.claude/projects/.../memory/project_llama_cpp_finetune_broken.md` | 更新 |
| `.claude/projects/.../memory/MEMORY.md` | 該当行のフック更新 |

**変更しないもの**: `src/llama.cpp/` (読み取り専用の参照ツリー)、既存レポート 2 本、`pr25428_comment_draft.md` (残課題として提案するに留める)、GitHub 上への投稿は一切行わない。

---

## 検証方法

1. **PNG**: 生成後に `Read` ツールで画像として開き、時代区分・イベント注記・凡例が読める状態か、日本語フォントが豆腐化していないかを目視確認する
2. **リンク切れ**: レポート内の相対パスを `ls` で実在確認
   ```bash
   cd report && grep -o '(attachment/[^)]*)' 2026-07-25_200322_llama-cpp-finetune-history.md \
     | tr -d '()' | xargs -I{} ls -la {}
   ```
   参照レポートへの `./yyyy-...md` リンクも同様に確認
3. **事実の照合**: レポート中の PR 番号・コミット SHA・日付を、本セッションで取得済みの `gh` / `git log` 出力と突き合わせる。特に以下は再実行して一致を確認:
   ```bash
   cd src/llama.cpp && git log --format='%h %ad %an | %s' --date=short -- 'examples/training/'
   gh pr view 21924 --repo ggml-org/llama.cpp --json state,updatedAt,additions,deletions
   ```
4. **REPORT.md 準拠**: `## 概要` が H1 とメタ情報の直下・他セクションより先にあること、`## 核心発見サマリ` 冒頭が画像埋め込み `![...](...)` であること (リンクのみは不可)、attachment へのリンクに `./` プレフィックスが無いこと、作成者が `Claude Opus 5 (1M context)` であることを確認
5. **INDEX.md**: セクション 12 に 3 エントリが時系列順に並んでいることを確認
6. **メモリ**: 更新後の `project_llama_cpp_finetune_broken.md` を読み返し、frontmatter (`name` / `description` / `metadata.type: project`) が保持され、`MEMORY.md` の行と齟齬がないことを確認
