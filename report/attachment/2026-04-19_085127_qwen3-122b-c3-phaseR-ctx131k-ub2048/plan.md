# Phase R: 本番 ctx=131,072 + `-ub=2048` 起動試験

## Context

直近の Phase Q レポート（`report/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound.md`）で、fa=1 + f16 KV cache の compute buffer モデル `CUDA3 = 0.9824 × min(ctx, -ub)` が ub=128〜8,192 の 64 倍ダイナミックレンジで誤差 0.002%・R²=1.00000000 で確立した。しかしこれは **ctx=16,384 までの実機検証** であり、本番想定の ctx=131,072（128k）での実測は未実施。

本 Phase R はレポート「未検証事項（新規項目）」の最優先項目:

> **本番 ctx=131,072 + `-ub=2048` 起動試験**: 理論上 CUDA3 ≈ 2,012 MiB、合計 ≈ 4,276 MiB で確実起動可能。実機で eval / prompt / 長文応答品質を検証

これを実施し、**skill 側 `start.sh` の既定値を `-ub=2048` にハードコードする判断根拠** を提供する。ctx=131,072 × `-ub=2048` が t120h-p100（4×P100-16GB）上で安定起動し、Phase Q 予測式が 8 倍拡張された ctx でも保持されることを示せば、本番投入可能となる。

## Critical Files

### 資産コピー元（Phase Q、そのまま流用可）

- `report/attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/start_phaseQ.sh` — `FLASH_ATTN`/`CTX_SIZE`/`BATCH_SIZE`/`UB_SIZE` 環境変数化済み、OOM / `-ub` 下限拒否の exit code あり
- `report/attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/measure_phaseI.sh` — 変更なしコピー
- `report/attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/run_all.sh` — 変更なしコピー（`SIZES`/`GATE_SIZES`/`GATE_MIB`）
- `report/attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/aggregate_results.sh` — `out_Q_` → `out_R_` の 1 箇所置換のみ
- `report/attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/prompts/prompt_{1k,8k,32k,64k,120k}.txt`

### 参照（読み取りのみ）

- `REPORT.md` — レポート作成ルール
- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- `.claude/skills/llama-server/scripts/stop.sh`
- `.claude/skills/llama-server/scripts/start.sh:155`（現状 `-b 8192 -ub 8192`、Phase R 完了後の TODO 対象）

### 新規作成

- `report/attachment/${TS}_qwen3-122b-c3-phaseR-ctx131k-ub2048/start_phaseR.sh` — Phase Q からの差分（§2 参照）
- `report/attachment/${TS}_qwen3-122b-c3-phaseR-ctx131k-ub2048/fit_analysis_R.py` — 予測 vs 実測の差分評価
- `report/${TS}_qwen3-122b-c3-phaseR-ctx131k-ub2048.md` — 本レポート

## 条件マトリクス

| 条件 | ctx | -b | -ub | 予測 CUDA3 | 実施条件 |
|---|---:|---:|---:|---:|---|
| **R1（メイン）** | 131,072 | 2,048 | 2,048 | 2,012 MiB | 必須 |
| R2（フォールバック） | 131,072 | 1,024 | 1,024 | 1,006 MiB | R1 OOM 時のみ |
| R3（フォールバック） | 131,072 | 512 | 512 | 503 MiB | R2 失敗時のみ |

R1 成功で完了。R1 失敗時に限り ub を半減させて真の下限を特定。

## Phase Q 係数による予測値（R1: ctx=131072, ub=2048）

| GPU | model (実測) | KV (予測) | compute (予測) | 合計予測 | 空き（/16,269） |
|---|---:|---:|---:|---:|---:|
| 0 | 1,301 | 768 | 1,109 | 3,178 | 13,091 |
| 1 | 9,551 | 768 | 520 | 10,839 | 5,430 |
| 2 | 9,551 | 768 | 520 | 10,839 | 5,430 |
| 3 | 1,693 | 768 | 2,012 | 4,473 | 11,796 |

- compute 合計 ≈ 4,337 MiB（Phase Q P1 実測 4,276 MiB と一致）
- KV cache は ctx 比例（ctx=16k で 96 MiB/GPU → ctx=131k で 768 MiB/GPU）
- 全 GPU で 5 GiB 以上の余裕あり → 起動成功見込み高

## 再現手順

### 0. 事前準備とロック

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
PHASE_R_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseR-ctx131k-ub2048"
mkdir -p "$PHASE_R_DIR/startup_logs"
PHASE_Q_DIR="report/attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound"

cp "$PHASE_Q_DIR"/{measure_phaseI.sh,run_all.sh,aggregate_results.sh} "$PHASE_R_DIR/"
cp -r "$PHASE_Q_DIR/prompts" "$PHASE_R_DIR/"
cp "$PHASE_Q_DIR/start_phaseQ.sh" "$PHASE_R_DIR/start_phaseR.sh"
cp /home/ubuntu/.claude/plans/todo-deep-grove.md "$PHASE_R_DIR/plan.md"
```

### 1. start_phaseR.sh への差分（4 箇所）

1. 先頭コメント置換（Phase Q → Phase R）
2. **起動タイムアウト 120 s → 300 s**（ctx=131k の KV 確保と reserve 時間延長に備える）
3. `REMOTE_LOG` に `phaseR_` プレフィックスを追加（Phase Q ログとの衝突防止）
4. OOM 検知 grep パターンに `llama_kv_cache.*failed|n_ctx.*too large|failed to allocate KV` を追加

他は Phase Q と完全同一（NUMA `--cpunodebind=1 --membind=1`、`--threads 40 --poll 0`、`-ot` regex、`--flash-attn 1`、`--cache-type-{k,v} f16`）。

`aggregate_results.sh` は `out_Q_` → `out_R_` の sed 置換のみ。

### 2. R1 起動と計測

```bash
cd "$PHASE_R_DIR"
UB=2048; B=2048; CTX=131072

FLASH_ATTN=1 CTX_SIZE=$CTX BATCH_SIZE=$B UB_SIZE=$UB bash start_phaseR.sh
PID=$(ssh t120h-p100 "ps -eo pid,comm | awk '\$2==\"llama-server\"{print \$1;exit}'")
ssh t120h-p100 "cat /tmp/llama-server_phaseR_fa1_ctx${CTX}_b${B}_ub${UB}.log" \
  > "startup_logs/fa1_ctx${CTX}_b${B}_ub${UB}.log"

TAG_PREFIX="R_f16_fa1_ctx${CTX}_b${B}_ub${UB}" \
  SIZES="warmup 1k 8k 32k 64k 120k" \
  GATE_SIZES="32k 64k 120k" GATE_MIB=1500 \
  PID=$PID bash run_all.sh

cd - && .claude/skills/llama-server/scripts/stop.sh t120h-p100 && cd "$PHASE_R_DIR"
```

計測は warmup (3 run, haiku) → 1k (3 run) → 8k (3 run) → 32k (2 run, gated) → 64k (1 run, gated) → 120k (1 run, gated)。COOLDOWN=60 s、CURL_MAX_TIME=7200 s (2 h)。

### 3. フォールバック（R1 失敗時のみ）

```bash
# R2
FLASH_ATTN=1 CTX_SIZE=131072 BATCH_SIZE=1024 UB_SIZE=1024 bash start_phaseR.sh
# R3（R2 も失敗時のみ）
FLASH_ATTN=1 CTX_SIZE=131072 BATCH_SIZE=512 UB_SIZE=512 bash start_phaseR.sh
```

フォールバック時は warmup + 1k + 8k のみ計測し、起動可否と compute buffer 実測を重点確認。

### 4. 集計・解析・解放

```bash
bash aggregate_results.sh > results.tsv
python3 fit_analysis_R.py | tee fit_analysis_R.txt
grep -E "sched_reserve:|KV buffer|graph nodes|graph splits|cudaMalloc|failed to allocate|ubatch.*must|n_ubatch.*must|model buffer" \
  startup_logs/*.log > compute_buffer_summary.txt
cd -
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## fit_analysis_R.py の要件

Phase Q の多点フィット用スクリプトを簡略化し、以下 5 パートで構成:

1. `parse_sched_reserve` で startup_logs から CUDA0/1/2/3/Host の MiB 値を抽出
2. Phase Q 予測式（`CUDA0 = 951 + 0.077·ub`, `CUDA1/2 = 0.254·ub`, `CUDA3 = 0.9824·ub`, `CUDA_Host = 0.086·ub`）と実測の差分を表示、全項目 誤差 ≤ 0.5%（CUDA3）/ ≤ 5%（他）を判定
3. KV buffer の ctx=16k → 131k で 8 倍比例（96 → 768 MiB/GPU）を検証
4. graph nodes=4473、graph splits=136（bs=2048）+ 77（bs=1）が Phase Q と同一か判定
5. results.tsv を読み込んでプロンプトサイズ別 eval / prompt 中央値を出力

## 成功条件チェックリスト

### 起動フェーズ
- [ ] R1 (ctx=131072, ub=2048) で 300 s 以内に `/health 200`
- [ ] OOM ゼロ、`-ub` 下限拒否ゼロ
- [ ] sched_reserve 全 GPU + CUDA_Host 採取

### compute buffer 実測精度
- [ ] CUDA3 実測 vs 予測 2,012 MiB、誤差 ≤ 0.5%（目標 0.002%）
- [ ] CUDA1 = CUDA2 実測 vs 予測 520 MiB、誤差 ≤ 1%
- [ ] CUDA0 実測 vs 予測 1,109 MiB、誤差 ≤ 5%
- [ ] CUDA_Host 実測 vs 予測 176 MiB、誤差 ≤ 3%
- [ ] KV buffer 4 GPU 合計 ≈ 3,072 MiB ± 10%
- [ ] graph nodes=4473、graph splits=136+77

### 推論性能
- [ ] warmup / 1k で eval 中央値 ≥ 14.5 t/s（Phase Q ctx=16k ub=2048 で 15.42 t/s、ctx 拡張による ≤ 10% 低下許容）
- [ ] 1k / 8k で prompt_per_second ≥ Phase Q の 80%
- [ ] 32k / 64k / 120k で 2 h 以内完走
- [ ] 120k eval 中央値 ≥ 8 t/s（long-ctx decode 劣化許容）

### 運用面
- [ ] PID / cmdline / numastat pre-post / nvidia-smi post_run 取得
- [ ] stop + unlock 完了

## 想定失敗モードと対処

| 症状 | 対処 |
|---|---|
| R1 起動失敗（CUDA1/2 KV OOM） | ctx=65,536 に落として R1' を試行。R2/R3 のフォールバックも並行 |
| warmup hang（curl タイムアウト） | CURL_MAX_TIME=7200 以内で完走しない場合、EVAL_MAX_TOKENS=64 に短縮 |
| prompt_120k OOM | prompt_64k までで打ち切り、レポートに prompt サイズ上限を記録 |
| CUDA1 free ≤ 1,500 MiB で gate skip | GATE_MIB を動的に下げて再実行、偏り原因を調査 |
| eval 大幅低下（< 12 t/s） | 数値を記録、新規 TODO として「ctx 増大による eval 劣化の物理原因特定」を追加 |
| graph splits が bs=2048 以外 | ログで `n_ubatch` を grep、llama.cpp 内部調整ロジックを記録 |

## 所要時間見積もり

R1 のみ成功: 約 90〜100 分
- 起動 2〜5 分 + warmup 4 + 1k 5 + 8k 8 + 32k 17 + 64k 16 + 120k 30 + 集計 5 + 余裕

R1/R2/R3 全失敗ケース（ログ保全のみ）: 約 60 分

## レポート構成

`report/${TS}_qwen3-122b-c3-phaseR-ctx131k-ub2048.md` に Phase Q と同じ章立てで記述:

1. 添付ファイル（plan.md、start_phaseR.sh、fit_analysis_R.py、fit_analysis_R.txt、compute_buffer_summary.txt、startup_logs、out_R_* 一覧）
2. 参照（Phase Q / Phase P へのリンク）
3. 前提・目的
4. 環境情報
5. 再現方法
6. 実行結果サマリ（sched_reserve 実測 vs Phase Q 予測、KV ctx 比例性、graph splits、プロンプトサイズ別性能、GPU 使用量）
7. ボトルネック・副次発見の分析（Phase Q 係数の ctx 外挿精度、KV 層割当実態、long prompt での -ub 挙動、eval 劣化モデル検証）
8. 採用判定
9. **未検証事項**（既知項目 Phase Q 継続 + 新規項目 Phase R 発生）
10. **検証完了後に実施すべき TODO**
    - ★最優先: skill 側 `start.sh:155` の `-b 8192 -ub 8192` を `-b 2048 -ub 2048` に変更
    - skill 側 `start.sh` のデフォルト ctx-size を本番想定値に更新
    - CLAUDE.md / モデルカード更新
    - Phase R-KV8（q8_0 KV での同様確認）、Phase Q-2（ub 下限）、Phase Q-3（ub 周辺探索）
11. 補足（核心発見、計算モデル確定版、作業終了状態）

## 意図的に変更しない点（Phase R の単独変数を ctx のみに絞る）

NUMA、threads、poll、-ot regex、flash-attn、KV 型、parallel、sampling、ngl — **すべて Phase Q と同一**。これにより Phase R の差分を純粋に ctx 8 倍の影響として解釈可能。

## 検証方法（計画の正しさを確認する観点）

- Phase Q の資産ファイルが全て現存し、指定パスで読める（`ls` で事前確認）
- start_phaseR.sh の差分適用後、`bash -n start_phaseR.sh` 構文チェック通過
- Phase Q 予測係数を fit_analysis_R.py にハードコードせず定数宣言で上部に集約
- R1 起動ログを startup_logs に保存できる（Phase Q と同じパス構造）
- レポートは未検証事項・TODO セクションを Phase Q 同様の粒度で記述
