# llama.cpp 直近 3 ヶ月 (2026-04-26 〜 07-26) の追加機能レポート

## Context

ユーザから「ここ 3 ヶ月で llama.cpp に追加された機能をレポートにまとめてほしい」との依頼。

本プロジェクトは mi25 (MI25 x4 / Vulkan-RADV 主体・ROCm fallback) と t120h-p100 (P100 / CUDA) で
llama-server を運用しており、llama.cpp 上流の HEAD は運用パラメータ・性能・回帰調査に直結する。
直近では [2026-07-20 pp 退行レポート](../../projects/llm-server-ops/report/2026-07-20_013500_mi25_prompt_eval_regression.md)
で default backend を hip → vulkan に反転したばかりで、「上流で何が入ったか」を体系的に把握できていない。

`src/llama.cpp/` にコードリーディング用の完全クローンがあり、HEAD は `c812c543f` (2026-07-25 21:15 +0200)
で最新。対象期間 2026-04-26 〜 2026-07-26 に **1195 commit**、リリースタグは概ね **b8934 → b10121** の範囲。

**確定した方針 (ユーザ回答済み)**:
- 対象範囲: **機能追加 ＋ 主要な性能改善・破壊的変更**（純粋なバグ修正・リファクタは除外）
- 視点: **上流の変化 ＋ 自環境 (mi25 Vulkan/ROCm・P100 CUDA) への影響を併記**
- 情報源: **ローカル git 履歴 ＋ GitHub の PR/Issue を補足参照**（`gh` CLI 認証済みを確認、`miminashi` アカウント。
  `gh pr view` で PR 本文・差分規模・ラベル、`gh pr list --search` で期間/ラベル絞り込みが可能）

成果物は `report/` 配下のレポート 1 本（[REPORT.md](../../projects/llm-server-ops/REPORT.md) 準拠）。
コード変更・GPU サーバ操作は一切行わない（読み取り専用調査のため `gpu-server` ロック不要）。

---

## 事前調査で判明済みの主要テーマ（レポート骨子）

以下は既に `git log` で抽出済み。レポート本文はこの 10 テーマを軸に構成する。

### 1. `llama` 統合実行ファイルの導入（最大の UX 変更）
- `app : introduce the llama unified executable` (#23296, 05-20)
- サブコマンド追加: `batched-bench` / `fit-params` / `quantize` / `perplexity` (#23459)、`llama download` (#24982)
- `llama update` セルフアップデータ (#23865)、`--version` / `--licenses` / `--help` (#25054, #23426, #23805)
- `cli : move to HTTP-based implementation` (#24948, 07-08) — llama-cli が server 経由に
- `cli: add --output option` (#25484)

### 2. 投機的デコード (speculative decoding) の大幅拡張
- **EAGLE3 対応** (#18039, 06-12) — 以降 qwen3.5/3.6 (#24593)、Minimax2、backend sampling (#24655)
- **DFlash 対応** (#22105, 06-28) — `spec-draft-p-min` (#25246)、K/V cache rotation (#25823)
- **MTP**: Step3.5/3.7 flash mtp3 (#24340)、Hy3 (hy_v3) (#25395)、NVFP4 MTP scale tensors (#23563)
- parallel drafting (#22838)、spec メトリクス（平均 acceptance length / 位置別 acceptance rate, #24536）
- CLI 引数の整理 (#22964, #22397) → **破壊的変更**
- `server-bench : speed-bench for speculative decoding` (#23869)

### 3. llama-server の router / エージェント化
- router モード: model management API (#23976)、`/models/sse` によるロード進捗 (#24828)、
  モデルダウンロードを専用プロセス化 (#24834)、`-hf` preset repo 刷新 (#24739)
- **組み込みツール / エージェント**: `--agent` arg (#24801)、`get_datetime` (#22649/#26117)、
  `exec_shell_command` のストリーミング (#25526)、`read_file`/`edit_file` 系 (#25498)
- `/responses` API の timings・progress (#25348)、tool call への id 付与 (#24882)
- SSE Replay Buffer (#23226)、SSE ping/keepalive (#24013, #25241)、`X-Accel-Buffering` (#24774)
- prompt cache: RAM 上限強制 (#25070)、checkpoint 管理見直し (#25472, #24176)
- Vertex AI 互換 API (#22545)、vLLM 互換 `continue_final_message` (#23012)、`--cors-*` (#25655)
- ETag 対応 (#23701)、`--api-key-file` コメント行 (#23168)、reasoning 割込み制御 (#23971)

### 4. WebUI (tools/ui) の刷新 — 期間中の新規追加ファイル最多 (232)
- リポジトリ再構成 `tools/ui` + `llama-ui` 命名 (#23064) → **破壊的変更**
- MCP サーバ対応（opt-in #25239、設定 UI #25535、名前衝突修正 #26011）
- Thinking mode トグル + reasoning effort (#23434, #25846, #25539)
- context usage ゲージ (#25340)、会話一括操作 (#25815)、新ロゴ/ナビ刷新 (#24897)
- JS サンドボックスに記号数学 (nerdamer) (#25948)、`--ui-config-file` 同期 (#25132)

### 5. 新規モデルアーキテクチャ対応
- **DeepSeek V4** (#24162, 06-29) — 併せて fused hyper-connection ops (#25585)
- DeepSeek V3.2 / DSA (DeepSeek Sparse Attention) 汎用実装 (#23346)、GLM-DSA indexer (#24770)
- **GLM 5.2 Indexer** (#25407)、Hy3 (#25395)、EXAONE 4.5 (#21733)、Mellum (#23966)、
  sarvam_moe (#20275)、Mimo v2.5 (#22493)、Laguna XS.2/M.1 (#25165)、talkie-1930-13b (#22596)
- マルチモーダル: Granite4 Vision (#23545)、Granite Speech Plus (#24818)、
  Nemotron Nano 3 Omni (#22481)、sarashina2.2-vision (#22103)、qwen-vl frame merge (#21858)
- 埋め込み: LFM2.5-ColBERT/Embedding-350M (#24913)、granite multilingual R2 (#22716)

### 6. 新 ggml op と量子化フォーマット
- **`GGML_OP_LIGHTNING_INDEXER`** (#24231) — DeepSeek V3.2/V4 用。CUDA 実装 (#25545)
- **NVFP4** の全面展開: LM head (#23046)、CPU AVX2 dot + UE4M3 LUT (#23961)、
  WebGPU (#25143)、Vulkan native e2m1/e4m3 (#25338)、CUDA MMVQ post-scale fusion (#24481)
- **Q2_0** 新型: Metal (#25419)、Vulkan (#25430)。OpenCL の q1_0 (#25160)
- f16→f16 `SET_ROWS` (CPU #25344 / CUDA #25367 / Metal #25434 / Vulkan #25432)
- `col2im_1d` (Metal #25176 / CUDA #24417 / Vulkan #24425)、CONV_2D_DW (Metal #21565 / WebGPU #25847)
- f16 `out_prod` (#23997)

### 7. バックエンドの新規追加・強化
- **ET backend 新規追加** (#24179, 07-10) — RISC-V manycore アクセラレータ ET-SOC 向け。`docs/backend/ET.md` 新設
- **OpenVINO**: OV 2026.2 / 2026.2.1、context-shift、Q5_1、自己完結リリースパッケージ (#24503, #24974)、
  `GGML_BACKEND_DL` 対応 (#25795)、Windows リリース追加 (#25022)
- **Hexagon (Qualcomm)**: 期間中 34 commit。HMX flash attention (#22347)、
  MUL_MAT 32x32 tiled repack + cached graphs (#24954)、L2 dirty-bit lazy flush (#25762)、
  op-trace (#24592)、VISION RoPE (#25216)
- **WebGPU**: 26 commit。NVFP4、CONV_2D_DW、F16 on Vulkan/NVIDIA トグル
- **SYCL**: oneDNN XMX による Flash Attention (#25222)、fused top-k MoE (#25217)
- **OpenCL**: Adreno 向け int8 dp4 + MoE prefill 最適化 (#25537)、事前コンパイル済みバイナリカーネル (#23042)
- **KleidiAI**: SME2 f32 kernel (#24414)、SME/SME2 ディスパッチ分離 (#25478)

### 8. Tensor Parallel (`--split-mode tensor`) の実用化
- 期間中に `docs/multi-gpu.md` が**新規追加**され、`tensor` が EXPERIMENTAL として正式文書化
  （`row` は Deprecated に降格）
- quantized KV cache 対応 (#23792)、granularity 128 丸め (#24180)、
  3 GPU + Qwen3.5/3.6 の granularity 修正 (#23843)、Phi3/Bert/Plamo2,3/ChatGLM 対応 (#25536)
- 制約: `-fa` 必須、`--fit` 非対応（`--ctx-size` 手動指定が必要）

### 9. Vulkan バックエンドの性能改善（mi25 直結）
- FA 系: BFloat16 KV cache (#23420)、非対称 FA を coopmat2 / scalar / mmq / coopmat1 全パスで対応
  (#21753, #22589)、softmax 前 bias 適用で overflow 回避 (#24909)、**GCN で mask_opt 無効化 (#24362)**
- **`v_dot2_f32_f16` を matmul / FA で利用 (#24123)** — GCN 世代の扱いは要確認
- **小型 AMD GPU 向け submission 閾値を CU 数ベースに (#25240)**、flops ベース submission ヒューリスティック (#25005)
- **mi50 向け `mul_mat_vecq` 最適化 (#22933)** — gfx906、MI25 (gfx900) との近縁性を確認する価値あり
- Q3_K/Q6_K の 32bit block load (#23056)、Q4_K/Q5_K scale load coalesce (#21751)
- デバイスミューテックス保持時間短縮 (#23641)、host memory lock contention 削減 (#23376)、
  per-instance mutex 化 (#23570)

### 10. CUDA / その他（P100 直結）+ 破壊的変更まとめ
- CUDA: topk-moe fusion 288 experts (#25267)、GET_ROWS quants (#25962)、
  `cudaMemcpy2DAsync` fast path (#25057)、quantized concat の contiguity 緩和 (#25678)
- **破壊的変更候補**（要検証・レポートに専用小節）:
  - `common : fix env names to all have LLAMA_ARG_ prefix` (#23778, 05-27)
    — 期間内で唯一 `breaking change` ラベルが付いた PR。環境変数名の一斉改名
  - `args: refactor mlock/mmap/directio into load-mode` (#20834, 07-23) — `--mlock`/`--no-mmap` の扱い
  - spec CLI 引数の整理 (#22964, #22397)
  - `tools/ui` 再構成と `webui` → `ui` 命名変更 (#23064, #24817)
  - `llama_set_warmup` の deprecate (#24009)
  - `sched : reintroduce less synchronizations during split compute` (#20793) が
    revert (#25138) → 再導入 (#20793) と往復している点（回帰要注意）
- 開発体制: リポジトリに agent skill (`add-new-model` / `code-review`) が追加 (#26042)、
  Python が PEP 621 + uv へ移行 (#21907)

---

## 実施手順

### Step 1 — 追加調査（ローカル git、読み取りのみ）
1. 上記 10 テーマの根拠コミットについて `git show --stat` / `git log -p` で実体を確認。
   特に「機能追加」と主張するものは、CLI フラグ・API フィールド・新ファイルの有無で裏を取る。
2. 破壊的変更の確定: `common/arg.cpp` の期間差分 (`git diff <base>..HEAD -- common/arg.cpp`) を読み、
   **削除・改名された CLI フラグ一覧**を作る。これが運用スクリプト
   (`.claude/skills/llama-server/scripts/start.sh`) への影響判定の根拠になる。
3. カテゴリ別・月別のコミット数を集計し、CSV を作業ディレクトリへ出力（PNG 用データ）。

### Step 2 — GitHub 補足参照（`gh` CLI 主体、WebFetch は fallback）

`gh` は認証済み・`ggml-org/llama.cpp` へアクセス可能なことを確認済み。以下 3 段構えで使う。

**(a) ラベル横断のスクリーニング**（一覧取得、安価）
```bash
gh pr list --repo ggml-org/llama.cpp --state merged \
  --search 'merged:2026-04-26..2026-07-26 label:"breaking change"' \
  --limit 100 --json number,title,mergedAt \
  -q '.[] | "\(.mergedAt[0:10]) #\(.number) \(.title)"'
```
同じ形で `label:performance` / `label:model` / `label:Vulkan` / `label:"Nvidia GPU"` /
`label:"AMD GPU"` / `label:enhancement` を回し、git 履歴のテーマ分類とクロスチェックする。
- **既に判明**: `breaking change` ラベルは期間内 **1 件のみ** (#23778 `common : fix env names to all
  have LLAMA_ARG_ prefix`, 05-27) — ラベル運用が疎なので**破壊的変更の一次情報は `common/arg.cpp`
  の実差分**とし、ラベルは補助に留める。なお #23778 は環境変数名の変更であり、
  `.claude/skills/llama-server/scripts/start.sh` が環境変数を使っていれば直接影響する（要確認）。

**(b) 主要 PR の本文精読**（`gh pr view --json body` で本文・差分規模・著者・ラベルを一括取得）
```bash
gh pr view <番号> --repo ggml-org/llama.cpp \
  --json number,title,author,mergedAt,labels,additions,deletions,body
```
対象（「読まないと内容が判断できない」もの、10〜15 件を上限）:
#23296 (llama unified executable)、#18039 (EAGLE3)、#22105 (DFlash)、#24162 (DeepSeek V4)、
#24179 (ET backend)、#20834 (load-mode)、#23778 (env 名 breaking)、#24801 (server --agent)、
#23792 (TP quantized KV cache)、#24231 (LIGHTNING_INDEXER)、#24362 (Vulkan GCN mask_opt)、
#22933 (mi50 mul_mat_vecq)、#25240 (小型 AMD GPU submission 閾値)、#23064 (tools/ui 再構成)

**(c) 未解決 Issue / 関連議論の確認**（該当機能の既知の落とし穴を拾う）
```bash
gh issue list --repo ggml-org/llama.cpp --state open \
  --search 'EAGLE3 in:title' --limit 10 --json number,title,createdAt
```
EAGLE3 / DFlash / `--split-mode tensor` / Vulkan AMD GCN の 4 テーマについて open issue を確認し、
「今すぐ本番投入してよいか」の判断材料をレポートに書く。

**注意**: PR 本文は AI 生成の誇大表現を含むことがある。本文の主張は必ずローカル差分で裏を取り、
裏が取れない主張は「PR 記載」と明示して区別する。

### Step 3 — 自環境影響の評価（実測はしない、静的判定のみ）
現行の運用構成と突き合わせて「効く/効かない/要検証」を三段階で表にする。
- 現行構成の確認元: `.claude/skills/llama-server/SKILL.md`、`scripts/start.sh`、
  mi25 側 `~/llama.cpp` の pin コミット（既知: Vulkan は `ded1561b4` / v9812、ROCm は `0fac87b15` / v8533）
- 判定軸: (a) mi25 Vulkan (gfx900) で有効か、(b) mi25 ROCm pin 版に含まれるか、
  (c) P100 CUDA (sm_60) で有効か、(d) 運用スクリプト変更が必要か
- **注意**: mi25 の ROCm ビルドは gfx900 のため pin 固定されており、期間中の改善の多くは未反映。
  この「pin による取り残し」自体がレポートの重要な指摘になる。

### Step 4 — 図の作成
`## 核心発見サマリ` 冒頭に埋め込む PNG を matplotlib で 1 枚生成する。
内容は **カテゴリ別コミット数の月次積み上げ**（server / ui / vulkan / hexagon / model / spec / cuda / その他）。
`dataviz` skill を読んでから作図する。出力先は
`report/attachment/<レポート名>/commit_categories.png`。

### Step 5 — レポート執筆
`report/yyyy-mm-dd_hhmmss_llama_cpp_3month_feature_survey.md`
（タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得）

構成（[REPORT.md](../../projects/llm-server-ops/REPORT.md) カノニカル名準拠）:
```
# llama.cpp 直近 3 ヶ月の新機能 — 統合 CLI・投機デコード拡充・server のエージェント化
- 実施日時 / 報告日時 / 作成者 (Claude Opus 5 (1M context))
## 概要                 … 平易な日本語 5〜8 段落。数値・PR 番号は入れない
## 添付ファイル         … plan.md、コミット分類 CSV、PNG
## 核心発見サマリ       … PNG 埋め込み → **結論**: 段落 → 10 テーマの要点表
## 前提・目的           … 調査範囲・期間・情報源・除外したもの
## 環境情報             … 対象クローン、HEAD SHA、タグ範囲、コミット数
## 結果詳細             … 上記テーマ 1〜10 を節立て（各節に PR 番号付き一覧）
##   └ 破壊的変更・非互換                （専用小節）
##   └ 自環境への影響マトリクス          （mi25 Vulkan / mi25 ROCm / P100 CUDA の 3 列）
## 副次発見             … pin 取り残し、sched revert 往復、開発体制の変化 等
## 残課題               … 次に実測すべき候補（下記）
## 参照レポート         … 2026-07-20 pp 退行、Marathon ベンチ、OOM 回帰 等
```

`## 残課題` に入れる実測候補（本レポートでは実施しない）:
- mi25 4 枚での `--split-mode tensor` 試行（TP の quantized KV cache + granularity 修正後）
- Vulkan HEAD 追従による mi25 の pp/tg 再測定（#24362 GCN mask_opt、#25240 CU ベース submission）
- EAGLE3 / DFlash draft モデルによる mi25・P100 の tg 改善検証
- `llama` 統合バイナリへの移行可否（`start.sh` の書き換え規模見積り）

### Step 6 — 後処理
1. `mkdir -p report/attachment/<レポート名>/` → `cp` でこのプランファイルを `plan.md` として添付
2. `report/INDEX.md` に 1 行追記（既存の章立てに合わせ、llama.cpp 関連の章 or 新章）
3. Discord 通知はユーザ指示がある場合のみ（今回は既定で行わない）

---

## 検証方法

- レポート内の全 PR 番号について、`git log --oneline --grep='#<番号>)'` でローカル履歴に存在することを確認する
  （存在しない番号を書かない = 幻覚防止の主要ガード）。ローカルに無い番号を引用する場合は
  `gh pr view <番号> --repo ggml-org/llama.cpp --json state,mergedAt` で状態を確認し、
  未マージなら「PR (未マージ)」と明記する
- 「破壊的変更」と書いた項目は、`common/arg.cpp` の実差分でフラグの削除・改名を実証する
- 「自環境への影響」列で「効く」と書いた項目は、コミット日が mi25/P100 の pin より後か、
  および対象アーキ (gfx900 / sm_60) を除外していないかをソースで確認する
- REPORT.md 準拠チェック: `## 概要` が H1 直後にあること、PNG が `## 核心発見サマリ` 冒頭に
  `![...](...)` で埋め込まれていること、添付リンクに `./` を付けていないこと

## やらないこと

- GPU サーバへの接続・ビルド・ベンチ実行（本レポートは静的調査に限定、ロック不要）
- `src/llama.cpp` の更新 (`git pull`) — HEAD が既に 2026-07-25 で対象期間を満たすため
- 1195 commit の全件列挙（バグ修正・CI・リファクタは除外し、テーマ別要約に留める）
