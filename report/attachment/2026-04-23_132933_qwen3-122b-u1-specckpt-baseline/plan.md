# Phase U-1: llama.cpp 再ビルド + speculative checkpointing (PR #19493) baseline 検証

## Context

Phase T 系列（パラメータチューニング軸）は **Phase T-5a-ts2 (B14b_ts_alt, eval 18.664 t/s, +24.18% vs Phase D)** で区切った。ここから **llama.cpp 機能軸** にピボットする。

現 t120h-p100 上のビルドは `6990e2f1f` (2026-04-17) で、以下の新機能・修正が未搭載:

- PR #19493 **speculative checkpointing** (merged 2026-04-19, commit `455d8e4be`) — recurrent/hybrid 層対応の新しい投機的デコーディング機構。Qwen3 は PR 内で直接評価対象、code/repetitive タスクで最大 ~2× 加速が実測されている。
- 関連 fix: #22114 (server checkpoint logic 再設計) / #22168 (ngram-mod 最適化) / #22223 (`--spec-default` 追加) / #22227 (speculative-simple への ckpt 対応)

本 Phase は **機能 enablement + A/B 比較** がゴールであり、spec ckpt 周りのパラメータ fine tuning は次 Phase (U-2 以降) に委ねる。ロードマップは現 auto-memory に沿い、U-1 完了後 → **cache-ram** → **gate/up fused GGUF** の順で進める。

## Goals / Non-Goals

**Goals**
- `~/llama.cpp` を `origin/master` HEAD まで pull & rebuild（関連 fix 4 件を全て取り込む）
- B14b_ts_alt 最良構成（Phase T-5a-ts2 現最高）上で spec ckpt **OFF vs ON** を A/B 測定
- 最低 3 種の prompt（汎用 1k / code / repetitive）で測定し **task 依存性** を明示
- Phase T-5a-ts2 baseline (18.664 t/s) との比較表 + spec stats（acceptance rate 等、取得可能な全 `.timings` フィールド）

**Non-Goals**
- `--ctx-checkpoints` / `--spec-ngram-size-n` / `--draft-min|max` の sweep（次 Phase）
- B14 以外の構成（B16/B18/A36 等）での spec ckpt 評価
- ngram cache 永続化、長コンテキスト (>32k) での動作

## Critical files / paths

**t120h-p100 上:**
- `~/llama.cpp/` — ソース（git pull 対象）
- `~/llama.cpp/build/bin/llama-server` — 再ビルド後バイナリ
- `~/llama-server.bak.6990e2f1f` — Phase T-5a-ts2 時点バックアップ（**新規作成、ホームディレクトリ直下に保管**: `build/` は rebuild で `rm -rf` される）
- モデル: `/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf`

**ローカル（参照のみ・改変しない）:**
- `.claude/skills/gpu-server/scripts/{lock,unlock,lock-status}.sh`
- `.claude/skills/llama-server/scripts/stop.sh`
- `.claude/skills/llama-server/server-scripts/update_and_build-t120h-p100.sh`
  - 挙動: `git pull` → HEAD 変化検出なら `rm -rf build && cmake -B build ...` → `cmake --build`。`-f` で強制 rebuild。**既存 build/ を丸ごと消すため、バックアップは事前に自前で取る必要あり。**

**再利用元 (Phase T-5a-ts2 attachment、`/tmp/phaseU1/` にコピーして改変):**
- `report/attachment/2026-04-23_093629_qwen3-122b-c3-phaseT5a-ts2/start_phaseT5.sh` — env var I/F（FLASH_ATTN/CTX_SIZE/UB_SIZE/OT_REGEX/TS/THREADS 等）が整備済み
- `.../batch_T5ats2.sh` — 複数条件ループ + start → health check → measure → stop
- `.../measure_phaseT5.sh` — `.timings.predicted_per_second` 等を jq 抽出
- `.../run_all.sh` — WARMUP 2 + EVAL 5 の実行フレーム
- `.../prompts/prompt_1k.txt` — 1k 汎用 prompt（baseline 再現に使用）

## Plan

### Step 0: 事前準備
1. ロック取得: `bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100`（失敗時は `lock-status.sh` 確認して待機）
2. 現 llama-server 停止: `bash .claude/skills/llama-server/scripts/stop.sh t120h-p100`
3. 作業ディレクトリ: `mkdir -p /tmp/phaseU1/{prompts,startup_logs}`
4. 既存スクリプトコピー: `cp report/attachment/2026-04-23_093629_qwen3-122b-c3-phaseT5a-ts2/{start_phaseT5.sh,measure_phaseT5.sh,run_all.sh,prompts/prompt_1k.txt} /tmp/phaseU1/` （新 batch は新規作成）

### Step 1: 現バイナリバックアップ
```
ssh t120h-p100 "cp ~/llama.cpp/build/bin/llama-server ~/llama-server.bak.6990e2f1f && \
                ssh_sha=\$(sha256sum ~/llama-server.bak.6990e2f1f) && echo \$ssh_sha"
ssh t120h-p100 "cd ~/llama.cpp && git rev-parse HEAD" # 6990e2f1f であること確認
```

### Step 2: 再ビルド
```
bash .claude/skills/llama-server/server-scripts/update_and_build-t120h-p100.sh
```
- 完了後: `ssh t120h-p100 "cd ~/llama.cpp && git rev-parse HEAD && git log --oneline -10"` を記録
- PR #19493 取り込み確認: `ssh t120h-p100 "cd ~/llama.cpp && git log --oneline 455d8e4be -1"`（ヒットすれば OK）
- 関連 4 PR (22114/22168/22223/22227) も `git log --oneline --all | grep -E '#(22114|22168|22223|22227)'` で確認
- **ビルド失敗時**: ログ原因分析 → ユーザに判断を仰ぎ、バックアップ rollback (`cp ~/llama-server.bak.6990e2f1f ~/llama.cpp/build/bin/llama-server`) + `git reset --hard 6990e2f1f` を **ユーザ確認の上** 実施（Plan mode 外で sudo も git reset --hard も慎重に）

### Step 3: 新バイナリの dry probe（フラグ名確定）
```
ssh t120h-p100 "~/llama.cpp/build/bin/llama-server --version"
ssh t120h-p100 "~/llama.cpp/build/bin/llama-server --help 2>&1 | grep -iE 'spec|draft|ckpt|checkpoint|ngram'" | tee /tmp/phaseU1/help_spec.txt
```
確認したい項目（出力をもって正式名・default を確定）:
- `--spec-use-checkpoints` の正式名・形式（on/off か、boolean か、存在するか）
- `--ctx-checkpoints` の default（調査では 32 と報告。ユーザ推奨は 4）
- `--spec-type` の候補（`ngram-mod`, `ngram-map-k`, ほか）
- `--spec-default` (#22223) / `--spec-ngram-size-{n,m}` / `--draft-{min,max}` の有無と default
- llama-server のレスポンス JSON `.timings` に含まれる spec 系フィールド名（`draft_n` / `draft_accepted_n` 等）
  - → eval サンプル 1 回流してレスポンスを `jq .timings` で全 key ダンプし、acceptance rate 計算式を確定

**フラグ名が推奨と異なる場合は Step 5 の batch スクリプトを修正する（推測で叩かない）。**

### Step 4: prompt 準備（/tmp/phaseU1/prompts/ 配下）
- `prompt_1k.txt` — 既存再利用（Phase T-5a-ts2 cross-session baseline 再現用、汎用タスク）
- `prompt_code.txt` — 新規作成。例: "Implement quicksort in Python with type hints, docstring, and pytest unit tests covering: empty list, single element, duplicates, negatives, already-sorted input. Then implement mergesort with the same interface and write a benchmark comparing both on 10k random integers." (PR で spec ckpt 効果が高いとされるコード生成タスク)
- `prompt_repetitive.txt` — 新規作成。例: "Generate valid Python literal of a list containing 50 employee dicts with fields: id (int, sequential), name (str, realistic), department (one of engineering/sales/marketing/hr/finance), salary (float 50000-150000), hire_date (ISO8601 string). Output only the list, no markdown fencing, no commentary." (反復パターン強、spec ckpt が最も効くとされるタイプ)

各 prompt の行数・バイト数をメタ情報として記録する。

### Step 5: A/B batch スクリプト作成 (/tmp/phaseU1/batch_phaseU1.sh)
batch_T5ats2.sh をベースに以下を変更:
- **構成は B14b_ts_alt 1 種のみ**: `OT='blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU'`, `-ts 11,12,13,14`, `-ub 256`, `-b 256`, `--ctx-size 32768`, `--threads 40`, `--cache-type-k/v q8_0`, `--split-mode layer`, `--flash-attn 1`, `--poll 0`, `numactl --cpunodebind=1 --membind=1`
- **mode × prompt マトリクス**: 2 mode × 3 prompt = 6 条件 × (warmup 2 + eval 5) = 42 run
  - `OFF`: 追加フラグなし
  - `ON`:  `--spec-use-checkpoints on --ctx-checkpoints 4 --spec-type ngram-mod --spec-ngram-size-n 24 --draft-min 48 --draft-max 64`（Step 3 で確定した正式名に置換）
- `start_phaseT5.sh` を拡張せず、新規 `start_phaseU1.sh` として作成し末尾に `${EXTRA_ARGS}` を注入する形にする（既存 attachment を破壊しない）
- `run_all.sh` は prompt 切替版 `run_all_phaseU1.sh` を別途作成し、3 prompt を順次回す
- `measure_phaseT5.sh` の JSON 抽出ロジックを拡張: `jq -c '.timings'` で全フィールドを timeline.log に記録、spec stats は別 TSV に集計
- 各条件間で llama-server を再起動（prompt cache / ngram cache の汚染回避）

測定順序:
1. OFF + prompt_1k（Phase T-5a-ts2 cross-session 再現確認 = 健全性テスト）
2. ON  + prompt_1k
3. OFF + prompt_code
4. ON  + prompt_code
5. OFF + prompt_repetitive
6. ON  + prompt_repetitive

### Step 6: 測定実行
```
cd /tmp/phaseU1 && bash batch_phaseU1.sh 2>&1 | tee batch_phaseU1.log
```
- 進行中は `ssh t120h-p100 "nvidia-smi --query-gpu=...  --format=csv"` を別途 monitor
- Step 6-1 (OFF + prompt_1k) の eval_mean が **18.0 ± 0.5 t/s** 範囲でなければ ON 測定に入らず、まず新ビルドの regression を疑って原因調査（Phase T-5a-ts2 は 18.664 t/s）

### Step 7: 結果集計・可視化
- TSV/CSV: eval_mean / prompt_mean / stdev / `draft_accepted_n` / `draft_n` / acceptance rate / speedup 倍率を条件別に
- PNG（matplotlib）:
  1. `spec_onoff_eval.png` — 3 prompt × 2 mode の eval t/s bar chart
  2. `spec_onoff_speedup.png` — ON/OFF 倍率を prompt 別に
  3. `spec_acceptance.png` — acceptance rate を prompt 別に（取得可能な場合）
- Phase T-5a-ts2 (18.664) を基準線として全グラフに明示
- 歴代 Phase D → T-5a-ts2 → U-1 の比較表も 1 枚作成（Phase T-5a-ts2 report から継承）

### Step 8: ロック解放
```
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### Step 9: レポート作成
- タイムスタンプ: `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`
- ファイル名（英語、50 字以内の日本語タイトル別）: `report/<ts>_qwen3-122b-u1-specckpt-baseline.md`
- タイトル候補: 「Phase U-1: spec-ckpt A/B 検証 (B14 構成, 3 prompt)」（48 字以内）
- **必須セクション順**（REPORT.md 準拠）:
  1. 実施日時 (JST)
  2. 添付ファイル（プラン、batch ログ、PNG、CSV）
  3. **核心発見サマリ**（冒頭に PNG 3 枚を画像埋め込み必須）
  4. 前提・目的
  5. 環境情報（サーバ、GPU、モデル、llama.cpp 新 commit hash）
  6. 再現方法（Step 0-8 のコマンド）
  7. 結果詳細（比較表 + spec stats）
  8. 参照レポート（Phase T-5a-ts2, PR #19493 他）
  9. **未検証事項 / 検証完了後 TODO**:
     - `--ctx-checkpoints` の sweep (4 vs 8 vs 16 vs 32)
     - `--spec-ngram-size-{n,m}` の sweep
     - `--draft-{min,max}` の tuning
     - 長コンテキスト (prompt_8k, 16k) 下での動作
     - B18_default など他構成での spec ckpt 評価
     - Phase U-2 (cache-ram) との相互作用
- プラン添付必須: `mkdir -p report/attachment/<basename>/ && cp /home/ubuntu/.claude/plans/phase-t-unified-bird.md report/attachment/<basename>/plan.md`
- batch ログ / start スクリプト / prompt 一式 / 生成 PNG / CSV を attachment に格納

## Verification（受け入れ基準）

1. `ssh t120h-p100 "cd ~/llama.cpp && git rev-parse HEAD"` が `origin/master` HEAD と一致
2. `ssh t120h-p100 "cd ~/llama.cpp && git log --oneline 455d8e4be -1"` が非空（PR #19493 取り込み確認）
3. 新バイナリ `--help` に spec ckpt 系フラグ（`--spec-use-checkpoints` もしくは同等）が存在
4. OFF + prompt_1k の eval_mean が 18.0 ± 0.5 t/s（Phase T-5a-ts2 cross-session 再現）
5. 全 6 条件で `.timings.predicted_per_second` / `.timings.prompt_per_second` が取得されている
6. ON モードで spec stats（`draft_n`/`draft_accepted_n` 等）が最低 1 prompt で非 null
7. レポートに比較表・PNG 3 枚・未検証 TODO・プラン添付が揃っている
8. ロックが正しく解放されている

## Risks / Rollback

- **R1: ビルド失敗（CUDA ABI 変更等）** — `~/llama-server.bak.6990e2f1f` からバイナリ rollback + `git reset --hard 6990e2f1f`（ユーザ確認必須: destructive）
- **R2: spec ckpt フラグ名の不一致（PR 後のリネーム）** — Step 3 の `--help` で正式名を確定してから batch を回す。推測で叩かない
- **R3: OFF baseline 再現失敗（新ビルドで regression）** — Step 6-1 で 18.0 ± 0.5 t/s 範囲外なら ON 測定に進まず原因調査
- **R4: ON で prompt processing 劣化** — PR 本文で A3B の expert saturation 下で微減報告あり。prompt_per_second も全条件で記録し、eval と分けて評価
- **R5: 1 prompt のみで早計判断** — 3 prompt 必須。task 依存性を本文で明記、単一数値で良し悪しを断定しない
- **R6: ロック競合** — `lock-status.sh` で確認、他セッション使用中なら別時間帯に延期
- **R7: spec ckpt で server crash / OOM** — `start_phaseU1.sh` の OOM/param-reject 検出ロジック（既存の grep パターン）を流用。発生時はその条件のみスキップして継続、レポートに明記
