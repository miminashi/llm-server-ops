# PR #25428 (llama.cpp qwen2 no-cache attention for training) の CPU-only 独立検証

## Context

`llama.cpp` の `llama-finetune` は 2026-07-25 セッション時点で modern LLM (Llama / Qwen 系 dense) すべてに対して backward graph 構築時点で `GGML_ASSERT` により abort する ([2026-07-25 レポート](../../projects/llm-server-ops/report/2026-07-25_045111_llama-cpp-cpu-finetune-broken.md), Issue [#18805](https://github.com/ggml-org/llama.cpp/issues/18805))。upstream に修正候補 PR [#25428](https://github.com/ggml-org/llama.cpp/pull/25428) が Draft で存在するが、2026-07-13 の作者コメント以降 review が着かず停滞している (2026-07-25 現在の WebFetch で確認済)。

PR 作者は Qwen2.5-14B-Instruct + GPU 想定で「複数 epoch 収束確認」と述べているが、**HW 環境不明・単一モデル・具体的な `llama-finetune` コマンド未記載**。本プロジェクトでは:
- **CPU-only (94 vCPU / AVX-512 のみ / BLAS OFF)** の作者と異なる HW で独立再現
- **Qwen2.5-0.5B** の小型モデル (作者の 14B より遥かに軽量、~30〜60 min/epoch で回せる)
- **before/after wiki.test.raw PPL** で「収束した」の定量証拠
- **loss curve PNG** (前セッションと同じ形式) で視覚証拠

を持ち込み、PR コメントとして投稿することで review が着くきっかけを作る。全 3 パターン (収束 / 部分的収束 / crash・発散) いずれでも PR コメントとして意義があるため、結果によらず投稿ドラフトを用意する方針。

**投稿方式** (ユーザ確認済): Claude は英文コメントドラフトをレポート内に用意するのみ、ユーザが GitHub Web / 手元 `gh` CLI で投稿。

## 前提 (2026-07-25 時点 Phase 1 で確認済)

- **mmns-cpu-llm 環境** (10.1.6.3, SSH で入れる):
  - Disk `/` : 16 GB 空き (~5 GB 追加使用見込み → OK)
  - `~/finetune-lab/venv` — Python 3.12 + torch 2.6.0+cpu / transformers / gguf 一式 (1.1 GB)
  - `~/finetune-lab/gguf/qwen2.5-0.5b.f32.gguf` (1.98 GB) — **主検証対象**
  - `~/finetune-lab/gguf/smollm2-135m-instruct.f32.gguf` (540 MB) — Llama 系 negative control (PR が Qwen 限定であることの確認用)
  - `~/finetune-lab/data/wikitext-2-raw/` (wiki.{train,valid,test}.raw)
  - `~/llama.cpp/` — master `af3be131c` (b7542, 前セッションから未 pull)
  - `~/llama-worktrees/finetune-b6290/` — 参考用に残置
- **PR #25428 現状**: Draft, base=`master`, head=`daineball:fix/qwen2-train-no-cache-attn`, 最新 SHA=`fd0b2b4791dae9dd09f583e1891c9834f1a1b06b`, last-update 2026-07-13
- **plot_loss.py** — 前セッションの scratchpad に残存 (`/tmp/claude-1000/.../bf40b091-.../scratchpad/plot_loss.py`, 93 行)。本セッションの scratchpad にコピーして流用
- **gh CLI 認証**: 未認証 (`gh auth login` 要求) → ユーザ判断済み「Claude はドラフト作成のみ」
- **GPU サーバロック**: mmns-cpu-llm はロック管理対象外 (`gpu-server` スキルの mi25 / t120h-* とは別サーバ)、CPU-only ジョブなので不要

## 実施ステップ

推定 1.5〜2 時間。長時間ジョブ (build 15 min, finetune 30〜60 min) は `nohup ... & disown` で背景実行し、Monitor で待機。

### Step 1: PR ブランチ fetch + build (15 分)

```bash
ssh mmns-cpu-llm '
  cd ~/llama.cpp &&
  git fetch origin pull/25428/head:pr-25428 &&
  git worktree add -f ~/llama-worktrees/pr-25428 pr-25428 &&
  cd ~/llama-worktrees/pr-25428 &&
  git log --oneline -1 &&
  cmake -B build -DGGML_OPENMP=ON -DGGML_CUDA=OFF -DGGML_VULKAN=OFF -DGGML_BLAS=OFF -DCMAKE_BUILD_TYPE=Release &&
  cmake --build build --target llama-finetune llama-perplexity llama-completion --config Release -j 32'
```

**確認事項**: HEAD が `fd0b2b4791...` になっていること (PR 最新 SHA と一致)。build 失敗時は log を保存して abort、レポートに「build failed」パターンとして記録。

### Step 2: Qwen2.5-0.5B baseline PPL 取得 (10 分)

前セッションで SmolLM2 の baseline は取得済 (PPL 18.6775) だが、**Qwen2.5-0.5B の baseline は未取得** (NEXT_SESSION.md 明記)。

```bash
ssh mmns-cpu-llm '
  ~/llama-worktrees/pr-25428/build/bin/llama-perplexity \
      -m ~/finetune-lab/gguf/qwen2.5-0.5b.f32.gguf \
      -f ~/finetune-lab/data/wikitext-2-raw/wiki.test.raw \
      -c 512 -b 512 -t 64 --numa distribute \
      2>&1 | tee ~/finetune-lab/logs/pr25428_ppl_qwen_before.log'
```

期待: `Final estimate: PPL = X.XX +/- Y.YY` が最終行に出る。

### Step 3: `llama-finetune` を Qwen2.5-0.5B + wikitext-2 で 1 epoch 実行 (30〜60 分)

**重要**: `-fa off` は必須 (前セッションで確認)。まず 1 epoch で収束傾向を見てから、必要に応じて 2 epoch 目を追加判断。

```bash
ssh mmns-cpu-llm '
  cd ~/finetune-lab &&
  nohup ~/llama-worktrees/pr-25428/build/bin/llama-finetune \
      -m gguf/qwen2.5-0.5b.f32.gguf \
      -f data/wikitext-2-raw/wiki.test.raw \
      -o out/qwen2.5-0.5b-ft-pr25428.f32.gguf \
      -c 512 -b 512 -ub 512 -fa off \
      -t 64 --numa distribute \
      -epochs 1 -lr 1e-5 -opt adamw \
      > logs/pr25428_ft_qwen.log 2>&1 & disown'
```

Monitor で完了待ち。3 分毎に log tail で loss 推移をチェック:
- **crash パターン**: `GGML_ASSERT` で abort → 早期 abort、Step 4 スキップして結果パターン「crash」で報告
- **発散パターン**: loss が単調悪化 → 完了まで待つ (更新無効化と区別)
- **収束パターン**: loss が下降 → 完了まで待って Step 4 へ

### Step 4: 学習後 PPL + 生成の比較評価 (10 分)

```bash
# 学習後 PPL
ssh mmns-cpu-llm '
  ~/llama-worktrees/pr-25428/build/bin/llama-perplexity \
      -m ~/finetune-lab/out/qwen2.5-0.5b-ft-pr25428.f32.gguf \
      -f ~/finetune-lab/data/wikitext-2-raw/wiki.test.raw \
      -c 512 -b 512 -t 64 --numa distribute \
      2>&1 | tee ~/finetune-lab/logs/pr25428_ppl_qwen_after.log'

# 生成比較 (baseline は SmolLM2 のみ取得済、Qwen は今回 baseline + after 両方取る)
ssh mmns-cpu-llm '
  for MODEL in gguf/qwen2.5-0.5b.f32.gguf out/qwen2.5-0.5b-ft-pr25428.f32.gguf; do
    echo "=== $MODEL ===" &&
    ~/llama-worktrees/pr-25428/build/bin/llama-completion \
        -m ~/finetune-lab/$MODEL \
        --temp 0 -n 80 -c 512 -t 64 --seed 42 \
        -p "Barack Obama was born in "
  done 2>&1 | tee ~/finetune-lab/logs/pr25428_gen_compare.log'
```

**判定基準**:
- PPL after < PPL before なら「収束した」positive 結果
- PPL after ≒ before なら「無効化パッチと同じ」中立結果
- PPL after >> before なら「発散」negative 結果

### Step 5: Llama 系 negative control (任意, ~5 分)

PR タイトルが `qwen2 : use no-cache attention path for training graphs` と Qwen 限定を示唆しているため、SmolLM2 (Llama 系) では **依然 crash が期待される**。これを確認できれば「PR は Qwen fix であり Llama は依然 broken」という追加情報を PR コメントに含められる。

```bash
ssh mmns-cpu-llm '
  ~/llama-worktrees/pr-25428/build/bin/llama-finetune \
      -m ~/finetune-lab/gguf/smollm2-135m-instruct.f32.gguf \
      -f ~/finetune-lab/data/wikitext-2-raw/wiki.test.raw \
      -o /tmp/dummy.gguf \
      -c 512 -b 512 -ub 512 -fa off \
      -t 64 --numa distribute \
      -epochs 1 -lr 1e-5 -opt adamw \
      2>&1 | tee ~/finetune-lab/logs/pr25428_ft_smollm_control.log' \
  || echo "(expected: assert if Llama still broken)"
```

早期 abort でも log は保全される。時間かからないので実施推奨。

### Step 6: 添付ファイル取得 + loss curve PNG 生成 (10 分)

```bash
# log を local に取ってくる
mkdir -p report/attachment/2026-07-25_XXXXXX_llama-cpp-cpu-finetune-pr25428-verify/
scp mmns-cpu-llm:~/finetune-lab/logs/pr25428_*.log \
    report/attachment/2026-07-25_XXXXXX_llama-cpp-cpu-finetune-pr25428-verify/

# plot_loss.py を今セッション scratchpad にコピー、Qwen 用に config を差し替えて実行
cp /tmp/claude-1000/-home-ubuntu-projects-llm-server-ops/bf40b091-*/scratchpad/plot_loss.py \
   /tmp/claude-1000/-home-ubuntu-projects-llm-server-ops/9e3908d3-*/scratchpad/plot_loss_pr25428.py
# 編集: ATTACH パスと configs リストを PR 検証用に差し替え、y-axis range を実データに合わせる
python3 /tmp/.../plot_loss_pr25428.py
```

### Step 7: レポート作成 + PR コメント英文ドラフト作成 (15 分)

- **レポート**: `report/2026-07-25_HHMMSS_llama-cpp-cpu-finetune-pr25428-verify.md`
  - REPORT.md のフォーマット (概要必須、核心発見サマリ冒頭に PNG 埋め込み、添付ファイル一覧など) 準拠
  - 前レポート `2026-07-25_045111_llama-cpp-cpu-finetune-broken.md` を参照レポートに列挙
  - 結果 (収束 / 発散 / crash) に応じて核心発見サマリを書き分け
- **PR コメント英文ドラフト**: 同レポートの末尾 or 添付として `pr25428_comment_draft.md`
  - 内容: (a) 環境 (CPU-only, AVX-512, 94 vCPU, no AMX/AVX-VNNI), (b) 使用モデル (Qwen2.5-0.5B), (c) 検証結果 (PPL before/after, loss curve, sample generation), (d) 副次発見 (SmolLM2 control 結果), (e) upstream に対する所感 (review 促進、他 arch への展開要望)
- **INDEX.md** に 1 行追記

## 変更対象 (書き込み)

**Local リポジトリ**:
- `report/2026-07-25_HHMMSS_llama-cpp-cpu-finetune-pr25428-verify.md` (新規)
- `report/attachment/2026-07-25_HHMMSS_llama-cpp-cpu-finetune-pr25428-verify/` (新規ディレクトリ、log × 6 + PNG + plan.md + `pr25428_comment_draft.md`)
- `INDEX.md` (1 行追記)
- **触らない**: `.claude/skills/llama-server/scripts/start.sh` の M / `.gitignore` の M / 既存 M 大量ファイル (前セッションの LFS 遡及産物、NEXT_SESSION.md 初動手順で「触らない」と明記)

**リモート (mmns-cpu-llm)**:
- `~/llama-worktrees/pr-25428/` (新規 worktree, ~5 GB)
- `~/finetune-lab/out/qwen2.5-0.5b-ft-pr25428.f32.gguf` (新規 output, 1.98 GB)
- `~/finetune-lab/logs/pr25428_*.log` (新規 log × 6)

## 流用する既存資産

- **REPORT.md** — レポートフォーマットの正 (`report/2026-07-25_045111_...md` を範例に踏襲)
- **plot_loss.py** (`/tmp/claude-1000/.../bf40b091-.../scratchpad/plot_loss.py`) — regex ベースの `train: ... loss=X.X` 抽出、`Agg` backend で headless 実行、そのまま流用可
- **`~/finetune-lab/` 一式** — 前セッションで既にセットアップ済み、コマンドが即動く状態

## 動作確認 (end-to-end)

1. `git log --oneline -1` (mmns-cpu-llm 上の `~/llama-worktrees/pr-25428/`) が `fd0b2b4791...` を返すこと
2. `~/llama-worktrees/pr-25428/build/bin/llama-finetune --help` が実行できること (build 成功)
3. `logs/pr25428_ppl_qwen_before.log` の最終行に `Final estimate: PPL = X.XX +/- Y.YY` が出ること
4. `logs/pr25428_ft_qwen.log` が **crash せずに epoch 1 完了** することを確認 (これが PR fix の一次検証)
5. `logs/pr25428_ft_qwen.log` の最終 loss が baseline 付近 (3.0 以下) に収まっていることを確認 (収束の一次検証)
6. `pr25428_ppl_qwen_after.log` の PPL が before の値以下 (改善) または同等 (収束) であること
7. `pr25428_gen_compare.log` で after model の生成テキストが崩壊していないこと (before と近い出力形式が維持されている)
8. `loss_divergence.png` (Qwen 用) がレポート添付ディレクトリに生成されていること
9. `report/2026-07-25_HHMMSS_...md` が REPORT.md フォーマットに従い、核心発見サマリ冒頭に PNG が埋め込まれていること
10. `pr25428_comment_draft.md` に英文コメントが用意され、ユーザが gh CLI or GitHub Web で貼り付けられる形式であること

## リスク / 早期打ち切り条件

- **Build 失敗**: PR が master に対して conflict、または依存関係が変わっている → 「build failed」パターンで PR コメントを短く用意 (「fetch した SHA X で build error, log 添付」) して終わる
- **Qwen0.5B で依然 crash**: PR が想定通り動かない → crash log + assert 内容を PR コメントで報告 (negative but useful)
- **finetune が 90 分経っても終わらない**: `-t 64` の CPU 5864% 相当でも Qwen0.5B は SmolLM2 の 4 倍のパラメータ数 → 60 min / epoch 目安を超えて 90 min まで待ち、それでも進捗ないなら abort して部分結果で報告
- **PPL 悪化・loss 発散**: 前セッションの b6290 patch と同じパターン。ただし PR は根本修正なので発散すれば「作者主張と乖離」の重要データ → 収束できるオプティマイザ / lr 組合せを 1〜2 追加試行 (SGD lr=1e-6 など) してから報告
