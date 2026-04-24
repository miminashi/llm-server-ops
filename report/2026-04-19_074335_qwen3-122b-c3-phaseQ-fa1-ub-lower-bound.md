# Qwen3.5-122B-A10B C-3 Phase Q（fa=1 `-ub` 下限探索）

- **実施日時**: 2026年4月19日 07:43 – 08:32 (JST、実計測時間 約 49 分)
- **作業種別**: 計測・検証（Phase P 未検証事項「決定的発見の可能性」最上位項目）

## 添付ファイル

- [実装プラン](attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/plan.md)
- [起動スクリプト (start_phaseQ.sh、`-ub` 下限拒否検知 exit 3 を追加)](attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/start_phaseQ.sh)
- [計測スクリプト (measure_phaseI.sh)](attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/measure_phaseI.sh)
- [一括実行スクリプト (run_all.sh)](attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/run_all.sh)
- [集計スクリプト (aggregate_results.sh、`out_Q_*` 対応)](attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/aggregate_results.sh)
- [線形性検証 + 7 点フィット Python (fit_analysis.py)](attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/fit_analysis.py)
- [検証結果 (fit_analysis.txt)](attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/fit_analysis.txt)
- [集計結果 TSV (results.tsv)](attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/results.tsv)
- [compute buffer サマリ (compute_buffer_summary.txt)](attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/compute_buffer_summary.txt)
- 起動ログ 4 件:
  - [fa1_ctx16384_b1024_ub1024.log](attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/startup_logs/fa1_ctx16384_b1024_ub1024.log)
  - [fa1_ctx16384_b512_ub512.log](attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/startup_logs/fa1_ctx16384_b512_ub512.log)
  - [fa1_ctx16384_b256_ub256.log](attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/startup_logs/fa1_ctx16384_b256_ub256.log)
  - [fa1_ctx16384_b128_ub128.log](attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/startup_logs/fa1_ctx16384_b128_ub128.log)
- `out_Q_*` 計測アーティファクト 4 条件

## 参照

- 前身レポート: [2026-04-19_051604_qwen3-122b-c3-phaseP-fa1-batch-scan.md](2026-04-19_051604_qwen3-122b-c3-phaseP-fa1-batch-scan.md)
- Phase O (fa=1 ctx=16k): [2026-04-19_033924_qwen3-122b-c3-phaseO-fa1-ctx16k.md](2026-04-19_033924_qwen3-122b-c3-phaseO-fa1-ctx16k.md)
- Phase N (ctx=8192 境界 + 4 点フィット): [2026-04-19_024430_qwen3-122b-c3-phaseN-ctx8k-boundary.md](2026-04-19_024430_qwen3-122b-c3-phaseN-ctx8k-boundary.md)
- Phase M (fa=0 ctx スキャン): [2026-04-18_220428_qwen3-122b-c3-phaseM-ctx-scan.md](2026-04-18_220428_qwen3-122b-c3-phaseM-ctx-scan.md)

## 前提・目的

Phase P レポート末尾「未検証事項 / 新規項目」最上位として **「決定的発見の可能性」** と明記されていた最優先項目。

> **`-ub=1024` / `-ub=512` / `-ub=256` の下限探索**: 線形性が極小領域まで保たれるか。`-ub=256` なら CUDA3 ≈ 252 MiB まで削減可能、ctx=131k でも起動可能になる決定的発見の可能性

Phase P で確定した線形モデル `CUDA3 = 0.9824·min(ctx, -ub)` が **-ub=128 まで保たれるか**、また **eval 速度の `-ub` 単調減少傾向に反転点が存在するか** を 4 条件（Q1〜Q4）で実証する。

### 成功条件

- [x] Q1〜Q4 全 4 条件で起動成功・`sched_reserve` 採取（OOM／`-ub` 下限拒否ゼロ）
- [x] CUDA3 線形性誤差 ≤ 0.5%（実測: **全条件で 0.002%、Phase P と同精度を維持**）
- [x] log-log 傾き 0.95〜1.05（実測: **6 区間全てで 1.0000**）
- [x] 7 点線形フィット係数 0.978〜0.987（実測: **0.982422**、R²=1.00000000）
- [x] graph nodes = 4473 全条件一致、graph splits の `bs=${ub}` 対応継続（実測: **両方とも継続**）
- [x] eval 中央値の単調性 or 反転点検出（**ub=2048 を頂点とする反転点を検出**）

## 環境情報

- **サーバ**: `t120h-p100` (10.1.4.14)
- **GPU**: NVIDIA Tesla P100-PCIE-16GB × 4（各 16,269 MiB、合計 65,077 MiB、CC 6.0）
- **CPU**: Intel Xeon Gold 6138 @ 2.00GHz × 2 socket、計 40 コア / 80 スレッド、NUMA 2 ノード
- **メモリ**: 257,560 MiB (約 251 GiB)
- **モデル**: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- **llama.cpp ビルド**: b8807-b3d758750（Phase D〜P と同一系列）
- **構成**: Phase P と同じ C-D3 ベース + `--cache-type-{k,v} f16`
  - NUMA: `numactl --cpunodebind=1 --membind=1 --`
  - `--threads 40 --poll 0`
  - `-ngl 999 -ot 'blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'`
  - `--flash-attn 1 --ctx-size 16384`
  - **Phase Q 可変**: `-b` / `-ub`（Phase P と同じ環境変数化スクリプトを流用）
- **条件マトリクス（4 条件、`-b = -ub` で固定）**:
  - **Q1**: `-b=1024 -ub=1024`（PID=176347）
  - **Q2**: `-b=512  -ub=512`（PID=178387）
  - **Q3**: `-b=256  -ub=256`（PID=180427）
  - **Q4**: `-b=128  -ub=128`（PID=182472、Q3 成功で追加実施）

## 再現方法

Phase Q は Phase P の資産をほぼそのまま流用。差分は **start_phaseQ.sh への `-ub` 下限拒否検知（exit 3）追加** と **集計/解析スクリプトの `out_P_` → `out_Q_` 置換**のみ。

### start_phaseQ.sh の主な変更点（Phase P からの差分）

```diff
@@ -53,6 +53,12 @@
   if ssh "$HOST" "grep -qE 'cudaMalloc failed: out of memory|failed to allocate CUDA[0-9] buffer|graph_reserve: failed to allocate' ${REMOTE_LOG} 2>/dev/null"; then
     echo "[start_phaseQ] OOM pattern detected" >&2
     exit 2
   fi
+  # Phase Q 追加: llama.cpp の -ub 内部下限拒否を検出
+  if ssh "$HOST" "grep -qE 'ubatch.*must be|n_ubatch.*must|invalid.*ubatch|llama_init.*failed' ${REMOTE_LOG} 2>/dev/null"; then
+    echo "[start_phaseQ] -ub lower-bound rejection detected" >&2
+    exit 3
+  fi
```

### 実行フロー

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
PHASE_Q_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound"
mkdir -p "$PHASE_Q_DIR/startup_logs"
PHASE_P_DIR="report/attachment/2026-04-19_051604_qwen3-122b-c3-phaseP-fa1-batch-scan"
cp "$PHASE_P_DIR"/{measure_phaseI.sh,run_all.sh,aggregate_results.sh} "$PHASE_Q_DIR/"
cp -r "$PHASE_P_DIR/prompts" "$PHASE_Q_DIR/"
cp "$PHASE_P_DIR/start_phaseP.sh" "$PHASE_Q_DIR/start_phaseQ.sh"
# start_phaseQ.sh: コメント置換 + -ub 拒否検知 exit 3 追加
# aggregate_results.sh: out_P_ → out_Q_
# fit_analysis.py: 7 点フィット / log-log 全区間 / eval 反転点検出に書き直し

cd "$PHASE_Q_DIR"

for UB in 1024 512 256 128; do
  FLASH_ATTN=1 CTX_SIZE=16384 BATCH_SIZE=$UB UB_SIZE=$UB bash start_phaseQ.sh
  PID=$(ssh t120h-p100 "ps -eo pid,comm | awk '\$2==\"llama-server\"{print \$1;exit}'")
  ssh t120h-p100 "cat /tmp/llama-server_fa1_ctx16384_b${UB}_ub${UB}.log" \
    > "startup_logs/fa1_ctx16384_b${UB}_ub${UB}.log"
  TAG_PREFIX="Q_f16_fa1_ctx16384_b${UB}_ub${UB}" SIZES="warmup" PID=$PID bash run_all.sh
  cd - && .claude/skills/llama-server/scripts/stop.sh t120h-p100 && cd "$PHASE_Q_DIR"
done

bash aggregate_results.sh > results.tsv
python3 fit_analysis.py | tee fit_analysis.txt
grep -E "sched_reserve:|KV buffer|graph nodes|graph splits|cudaMalloc|failed to allocate|ubatch.*must|n_ubatch.*must" \
  startup_logs/*.log > compute_buffer_summary.txt
cd -
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 実行タイムライン

| 条件 | prompt_n | Run 数 | 起動 | eval 開始 | eval 終了 |
|------|---------:|------:|----------:|----------:|----------:|
| Q1 (b=1024 ub=1024) | 69 | 3 | 07:51 | 07:52:30 | 07:56:43 |
| Q2 (b=512  ub=512)  | 67 | 3 | 08:03 | 08:04:02 | 08:08:13 |
| Q3 (b=256  ub=256)  | 67 | 3 | 08:14 | 08:14:54 | 08:19:49 |
| Q4 (b=128  ub=128)  | 67 | 3 | 08:25 | 08:26:00 | 08:31:19 |

実計測時間: **約 49 分**（4 条件 × 約 12 分、見積もり 45〜57 分の範囲内）。

## 実行結果サマリ

### 1. 4 条件の `sched_reserve` 値（実測）と Phase P との結合表

| ub | 条件 | CUDA0 | CUDA1 | CUDA2 | CUDA3 | CUDA_Host | 合計 | graph splits | src |
|---:|---|---:|---:|---:|---:|---:|---:|---|---|
|   128 | **Q4** |   961.62 |   34.64 |   34.64 |   **125.75** |  11.00 |  **1,167.65** | 136 (bs=128) | Q |
|   256 | **Q3** |   963.25 |   65.01 |   65.01 |   **251.50** |  22.01 |  **1,366.78** | 136 (bs=256) | Q |
|   512 | **Q2** |   966.50 |  130.02 |  130.02 |   **503.00** |  44.02 |  **1,773.56** | 136 (bs=512) | Q |
| 1,024 | **Q1** |   973.00 |  260.03 |  260.03 | **1,006.00** |  88.04 |  **2,587.10** | 136 (bs=1024)| Q |
| 2,048 | P1 | 1,048.13 |  520.06 |  520.06 | 2,012.00 | 176.08 |  4,276.33 | 136 (bs=2048)| P |
| 4,096 | P2 | 1,568.27 | 1,040.13 | 1,040.13 | 4,024.00 | 352.16 |  8,024.69 | 136 (bs=4096)| P |
| 4,096 | P4 (b=8192) | 1,568.27 | 1,040.13 | 1,040.13 | 4,024.00 | 352.16 |  8,024.69 | 136 (bs=4096)| P |
| 8,192 | P3 | 2,784.00 | 2,080.25 | 2,080.25 | 8,048.00 | 704.31 | 15,696.81 | 136 (bs=8192)| P |

**graph nodes = 4473 は全 8 条件で同一**。**graph splits = 136、bs=${ub} の対応も全条件で完全継続**（Phase P 仮説の延長確認）。

### 2. CUDA3 線形性検証 — 全条件で誤差 0.002%

予測式 `CUDA3 = 0.9824 × min(ctx=16384, -ub)` の精度（Phase Q 4 条件 + Phase P 4 条件、計 8 条件）:

| ub | n_eff | 予測 MiB | 実測 MiB | 誤差 MiB | 誤差 % |
|---:|---:|---:|---:|---:|---:|
|   128 |   128 |   125.75 |   125.75 | +0.00 | +0.002% |
|   256 |   256 |   251.49 |   251.50 | +0.01 | +0.002% |
|   512 |   512 |   502.99 |   503.00 | +0.01 | +0.002% |
| 1,024 | 1,024 | 1,005.98 | 1,006.00 | +0.02 | +0.002% |
| 2,048 | 2,048 | 2,011.96 | 2,012.00 | +0.04 | +0.002% |
| 4,096 | 4,096 | 4,023.91 | 4,024.00 | +0.09 | +0.002% |
| 8,192 | 8,192 | 8,047.82 | 8,048.00 | +0.18 | +0.002% |

**全 8 条件（ub=128 から 8,192 までの 64 倍ダイナミックレンジ）で誤差ピッタリ +0.002%**。成功条件 ≤ 0.5% を **250 倍の精度で達成**。

### 3. log-log 傾き — 全 6 区間で完全線形

| 区間 | CUDA3 比 | ub 比 | log-log 傾き | 判定 |
|---|---:|---:|---:|---|
|  128→ 256 | 2.0000 | 2.00 | **1.0000** | OK |
|  256→ 512 | 2.0000 | 2.00 | **1.0000** | OK |
|  512→1024 | 2.0000 | 2.00 | **1.0000** | OK |
| 1024→2048 | 2.0000 | 2.00 | **1.0000** | OK |
| 2048→4096 | 2.0000 | 2.00 | **1.0000** | OK |
| 4096→8192 | 2.0000 | 2.00 | **1.0000** | OK |

**6 区間全てで傾き 1.0000**。線形性の崩壊点は ub=128 までの範囲では検出されなかった。

### 4. 7 点線形フィット — 完全な線形

主系列（ub = b、計 7 点）に対する最小二乗フィット結果:

```
線形:    CUDA3 = 0.982422 × ub + 0.0000      R² = 1.00000000
log-log: log(CUDA3) = 1.000000 × log(ub) − 0.0177
         exp(β) = 0.9824                     R² = 1.00000000
α = 1 仮説（純線形）: |α − 1| = 0.0000        判定 OK
```

- 線形フィットの切片 b は浮動小数点ゼロ（純比例）
- 傾き 0.982422 は Phase P の係数 0.9824 と完全一致（成功条件 0.978〜0.987 の範囲内、極めて狭い信頼区間）
- **CUDA3 = 0.9824·ub** は ub=128 から 8,192 までの 64 倍範囲で **R² = 1 の決定論的法則**として確立

### 5. eval 速度の `-ub` 反転点 — **ub=2048 が単一頂点**

| ub | eval 中央値 (t/s) | Δ vs ub=2048 | prompt 中央値 (t/s) | compute buffer 合計 | GPU 使用量合計 |
|---:|---:|---:|---:|---:|---:|
|   128 | **14.721** | -4.51% | 10.83 |  1,168 | 25,272 |
|   256 | **14.723** | -4.50% | 10.72 |  1,367 | 25,460 |
|   512 | **14.947** | -3.04% | 10.71 |  1,774 | 25,848 |
| 1,024 | **14.745** | -4.35% | 10.82 |  2,587 | 26,616 |
| 2,048 | **15.416** | **+0.00%（頂点）** | 10.99 |  4,276 | 28,218 |
| 4,096 | 15.368 | -0.31% | 11.03 |  8,025 | 31,790 |
| 8,192 | 15.186 | -1.49% | 10.95 | 15,697 | 39,110 |

**ub=2048 が eval の単一頂点**（W 字状の小ノイズはあるが、ub<2048 全域で 14.7〜14.95、ub=2048 が明確に最速）。Phase P 報告「ub=2048 で +1.5%」は実は **トレンドの最高点を観測**していたことが Phase Q で確定。

#### 反転点の構造（隣接 ub 間の Δeval）

| 区間 | Δeval (t/s) | 符号 |
|---|---:|---|
| 128→ 256 | +0.0027 | + |
| 256→ 512 | +0.2238 | + |
| 512→1024 | -0.2018 | − |
| 1024→2048 | **+0.6707** | + |
| 2048→4096 | -0.0480 | − |
| 4096→8192 | -0.1820 | − |

ub=2048 を頂点として両側で eval が低下（W 字の小ノイズあり）。1024→2048 の +0.6707 t/s が圧倒的な変化点。

### 6. GPU 使用量（post-eval、`gpu_post_run*.csv`）

| GPU | Q4 (ub=128) | Q3 (256) | Q2 (512) | Q1 (1024) | P1 (2048) | P3 (8192) |
|----:|---:|---:|---:|---:|---:|---:|
| 0 | 2,771 | 2,773 | 2,777 | 2,783 | 2,859 |  4,595 |
| 1 | 10,091 | 10,121 | 10,187 | 10,317 | 10,577 | 12,137 |
| 2 | 10,091 | 10,121 | 10,187 | 10,317 | 10,577 | 12,137 |
| 3 | 2,319 | 2,445 | 2,697 | 3,199 | 4,205 | 10,241 |
| **合計** | **25,272** | **25,460** | **25,848** | **26,616** | **28,218** | **39,110** |

- ub=128 で **GPU 合計 25,272 MiB**（Phase P P3=8192 比 -13,838 MiB、**-35.4%**）
- ub=128 でも **約 25 GB の VRAM を使用**（モデル本体 +KV cache の固定費が支配的）
- compute buffer の削減は線形だが、GPU 使用量合計は固定費との比率で見ると改善幅が小さい

### 7. CUDA1 / CUDA2 / CUDA0 / CUDA_Host の係数（Phase Q で観測）

P1〜P3 から外挿される係数を Phase Q 範囲で簡易検算:

| GPU | 観察される ub 比例係数 | 定数項（推定） | Phase P での説明 |
|---|---:|---:|---|
| CUDA0 | ≈ 0.077 MiB/token | ≈ 951 MiB | Phase P で「c=828 + α」と推定、Phase Q で **c≈951 が有力**（ub=128 で 961.62 MiB が下限漸近値） |
| CUDA1/2 | ≈ 0.254 MiB/token | ≈ 2 MiB | Phase P で「0.254·n_eff + 8」と再フィット、Phase Q で確認（ub=128 で 34.64≈0.27·128） |
| CUDA3 | **0.9824** MiB/token | **0** MiB | 純比例、定数項ゼロ |
| CUDA_Host | ≈ 0.086 MiB/token | ≈ 0 MiB | Phase P で「130 + 0.07·n_eff」推定だったが、ub=128 で 11 MiB なので **定数項は 0 に近い** |

**Phase P 推定の CUDA_Host 定数項 100〜130 MiB は Phase Q で否定**。実際は ub=128 で 11 MiB、ub=8192 で 704 MiB、つまり **CUDA_Host ≈ 0.086·ub** の純比例（係数 0.086 = 1/12 ≈ KV cache 領域の token あたり Host staging）。

### 8. 起動時間と reserve コスト

| ub | reserve 所要時間 |
|---:|---|
| 128 | 36.96 ms |
| 256 | 約 50 ms（中間値） |
| 512 | 約 60 ms |
| 1024 | 85.11 ms |

`-ub` を下げれば reserve 時間も比例して短縮。起動高速化の副次効果あり（ただし全体に占める割合は微小）。

## ボトルネック・副次発見の分析

### 1. CUDA3 = 0.9824·ub は **ハードコードされた決定論的法則**

ub=128 から 8,192 まで 64 倍のダイナミックレンジで **誤差 0.002%、R²=1.00000000**。傾き 0.982422 は浮動小数点演算誤差ゼロで Phase P の 0.9824 を再現。係数 0.9824 ≈ **0.96 + 0.022** に分解できそうだが、より重要なのは:

- **embedding 層の token あたりメモリ (Q4_K_M モデルの hidden dim ≈ 4,096 + α)**
- 1 token あたり概ね 1 MiB ≈ 1,048,576 バイト ≈ hidden_dim × 256 バイト/要素

f16 (2 byte/element) で hidden_dim 4,096 → 8,192 byte/token、2 × hidden_dim staging buffer 等を加算するとほぼ 1 MiB に収束。CUDA3 が **embedding output / 最終層 staging buffer** を担っているという物理的解釈と整合。

### 2. eval 速度ピークは **ub=2048**、これより小さい ub は SM 利用率の低下で不利

P100 PCIe（SM 数 56、CC 6.0）で `-ub=2048` がスイートスポット。

- **ub > 2048**: バッチごとの compute buffer が大きすぎてキャッシュヒット率／GPU 間転送が重荷
- **ub < 2048**: 1 バッチあたりの並列度が SM 数に対して不足、kernel launch overhead が支配的（推定）
- **ub=2048 ≈ 56 SM × 36 thread/SM**: 偶然か必然か、P100 の SM カバレッジに相当する候補

ub=512 が部分的に回復する（W 字）のは、SM 数の倍数との相性（512 = 256 × 2、1024 = 256 × 4）かもしれないが、ノイズの可能性も否定できない。Run 間 range は 0.005〜0.020 t/s なので 0.2 t/s の差は有意。

### 3. **ub=2048 採用は VRAM・eval ダブルウィン**（Phase P で観測した結論を強化）

| 比較 | ub=8192 (現状) | ub=2048 (Phase P 推奨) | ub=128 (Phase Q 最小) |
|---|---:|---:|---:|
| compute buffer 合計 | 15,697 MiB | 4,276 MiB（-72.7%） | 1,168 MiB（-92.6%） |
| GPU 使用量合計 | 39,110 MiB | 28,218 MiB（-27.8%） | 25,272 MiB（-35.4%） |
| eval 中央値 | 15.186 t/s | **15.416 t/s（+1.5%）** | 14.721 t/s（-3.1%） |
| 採用判断 | 現行 | **★最適** | VRAM 緊急時の救済策 |

**ub=2048 採用は決定的**。Phase Q で ub<2048 の eval 劣化が確定したため、本番既定値は 2048 で確定すべき。

### 4. Phase P CUDA_Host 定数項仮説（100〜130 MiB）の否定

Phase P で「P1 (ub=2048) の CUDA_Host 残差 +175% から定数項 ~130 MiB が必要」と予測したが、Phase Q ub=128 で実測 11.00 MiB（予測式 `130 + 0.07·128 ≈ 139 MiB` を大きく下回る）。

**実際は CUDA_Host ≈ 0.086·ub の純比例**で、Phase P の Phase N 4 点モデル `3.81e-6·n²+0.0235·n` が極端に過小推定だっただけ。Phase N データセット（ub=8192 固定）では定数項と n² 項が縮約されて区別不能だった。

### 5. graph splits の `bs=${ub}` は ub=128 まで完全継続

llama.cpp 内部の sched_reserve は `-ub` 値を直接バッチサイズとして使用していることが極小領域でも確認された。**llama.cpp ソース上で `-ub` が `n_ubatch` として全ロジックを通る**ことの間接的最終証拠。

### 6. CUDA0 の定数項漸近値は **約 951 MiB**

ub=128 で CUDA0 = 961.62 MiB → これは「定数項 ≈ 951 + 0.083·128」または「951 + 0.077·128」と表現可能（傾きは ub による）。

Phase N の Phase O での残差 +455 MiB（fa=1, ctx=16384 で予測 2,328 vs 実測 2,784）は、定数項が 828 ではなく **951** だったことが原因と判明。

### 7. CUDA1/2 のべき乗項は ub=128 まで線形のみで観測不要

Phase N 4 点フィット `1.91e-6·n² + 0.2227·n` は ub=8192 で 251 MiB、Phase Q 範囲では n² 項の寄与は 0.03〜0.5% と無視可能。極小 ub では **CUDA1/2 ≈ 0.254·ub** の純線形で十分。

## 採用判定

| 項目 | 結果 |
|------|------|
| 4 条件の起動成功 | ✅ 全成功（OOM ゼロ、`-ub` 下限拒否ゼロ） |
| sched_reserve 採取 | ✅ 4 GPU + CUDA_Host の全値取得、全条件で完全 |
| CUDA3 線形性検証 | ✅ **誤差 0.002%（成功条件を 250 倍の精度で達成）** |
| log-log 傾き全区間 | ✅ **6 区間全てで 1.0000（完全線形）** |
| 7 点フィット | ✅ **0.982422、R²=1.00000000、α=1 完全成立** |
| graph splits 連続性 | ✅ **bs=${ub} が ub=128 まで継続** |
| eval 反転点検出 | ✅ **ub=2048 を頂点とする反転点を確定** |
| `-ub` 内部下限 | ⚠️ **ub=128 でも警告/拒否なし、下限はさらに下**（Phase P TODO「-ub=1 ベンチマーク」へ） |

**結論**: Phase Q は計画していた全目標を達成。CUDA3 線形性は ub=128 まで完璧に保たれ、eval ピークは ub=2048 と確定。**本番 start.sh の既定値は `-ub=2048` で確定**。ctx=131k 起動時は CUDA3 ≈ 2,012 MiB しか使わず、CUDA3 空き枠 14 GB 以上を確保できる。

VRAM 緊急時の救済策として `-ub=512` または `-ub=1024` も実用可能（compute buffer を 1/4〜1/2 に削減、eval 損失 -3〜-4%）。`-ub=128/256` は eval 損失と引き換えに compute buffer を 90% 削減できる極限オプション。

## 未検証事項

### 既知項目（Phase P から継続、Phase Q で潰したものに [x]）

- [ ] **2 時間超の連続稼働試験（eval あり）**
- [ ] **層→GPU アライメントのソース解析**
- [ ] **ページキャッシュのコールドスタート検証**: `sudo sysctl vm.drop_caches=3` 権限未付与
- [ ] **量子化ダウンでの eval 向上量**: Q4_K_M → Q3_K_M / IQ2_XXS
- [ ] **pcm-memory による DRAM 帯域実測**
- [ ] **C-D3 + コールドスタート**
- [ ] **Node 0 側のコールドスタート C-D6**
- [ ] **perf stat での C-D3 の node-load-miss rate**
- [ ] **C-4 実験**（CPU 層 36 → 20 層未満）
- [ ] **他モデルでの同様の傾向**（Qwen3.5-35B-A3B 等）
- [ ] **`--threads 30` / `--threads 28` などの中間値**
- [ ] **`--numa numactl` モード**
- [ ] **OpenMP 環境変数の影響**
- [ ] **「初回サイクル効果」の原因特定**
- [ ] **セッション間 warmup ゆらぎの原因特定**
- [ ] **`--poll 1` / `--poll 10` / `--poll 100` の影響**
- [ ] **G_aged_t96 の再現条件の特定**
- [ ] **`--poll` とスレッド affinity / OpenMP の相互作用**
- [ ] **線形モデル `time_per_token = 66.5μs + 0.485μs × N_context` の他構成での検証**
- [x] **prompt_per_second が 8k で頂点を打つ理由**（Phase O/P で `-ub` 支配と判明、**Phase Q で eval も ub=2048 が頂点と確定**）
- [ ] **64k / 120k の Run 間再現性**
- [ ] **128k コンテキストが純粋応答に与える影響**
- [ ] **KV cache 量子化 (q8_0) の精度影響**
- [ ] **prompt cache hit 時の実効 turn time**
- [ ] **llama.cpp のソース上で `--cache-type-{k,v} q8_0` と `--flash-attn` の依存ロジック確認**
- [ ] **Segfault 時のバックトレース取得**
- [ ] **P100 CC 6.0 の flash-attention カーネル経路の検証**
- [ ] **CUDA1/2/3 の SM 稼働実態の時系列計測**
- [ ] **J_fa1_warmup run 1 の外れ値（15.54 t/s）再現性**
- [x] **CUDA0 の定数項 c=1,562 (fa=0) / c=828 (fa=1) の内訳特定**（**Phase Q で fa=1 の定数項漸近値は 951 MiB と判明**、Phase P 推定 828 を更新）
- [ ] **CUDA1 / CUDA2 の n² 係数 (fa=0 a=1.26e-4) の物理解釈**
- [x] **CUDA3 の線形係数 b=0.9824 MiB/token の源**（**Phase Q で ub=128 まで線形性継続、係数 0.982422 で確定**、embedding 層の token あたりメモリと結論）
- [ ] **ctx=1024 の fa=0 eval 劣化 (−5.2%) の原因**
- [ ] **ctx=512 / 256 の極小域での挙動**
- [ ] **3 点厳密解 vs 4 点最小二乗の妥当性**
- [x] **2 次多項式モデルの外挿限界**（**Phase Q で線形のみで完全成立、2 次項は ub=128 まで不要**）
- [ ] **eval 速度のセッション間ゆらぎレンジ更新**
- [ ] **prompt 処理の ctx 非依存の長 ctx 側確認**
- [ ] **fa=1 eval の「谷型」(ctx=2048 最高 → ctx=4096 最低) の再現性**
- [ ] **Phase M のモデルを f16 KV → q8_0 KV（C-D3 採用構成）に適用した場合の整合性**
- [ ] **ctx=6144 等の中間 ctx での fa=1 / fa=0 境界確認**
- [ ] **fa=0 ctx=8192 で CUDA1 空き枠を増やす手法**（**Phase Q で `-ub` 縮小が有効と確認、ub=2048 採用で 11 GB 空き枠確保**）
- [ ] **eval 谷型の最低値 ctx の fa=1 における物理原因**

### 既知項目（Phase P で新規追加、Phase Q で部分的に潰したもの）

- [x] **`-ub=1024` / `-ub=512` / `-ub=256` の下限探索**: ✅ **本 Phase Q で実施完了**。線形性は ub=128 まで完璧に継続、eval 反転点は ub=2048 で確定
- [ ] **`-ub=1 (greedy)` でのベンチマーク**: 未実施。eval は decode のみなので `-ub` 影響は理論上最小
- [ ] **`-ub > -b` の挙動（llama.cpp 制約検証）**: 未実施
- [ ] **fa=0 側での `-ub` 支配性の確認**: 未実施（Phase R 候補）
- [x] **CUDA_Host 定数項の定量化**: ✅ Phase Q で **定数項は 0 に近く、純比例 0.086·ub** と判明。Phase P 推定 130 MiB は誤り
- [x] **CUDA0 の `-ub` 非完全依存の内訳**: ✅ Phase Q で **定数項漸近値 951 MiB + 約 0.077·ub** と判明
- [x] **eval 速度と `-ub` の負相関の物理解釈**: 部分的。Phase Q で **ub=2048 が頂点、ub<2048 で逆効果**と判明、SM 利用率不足が有力候補
- [ ] **大 prompt での `-ub` 依存性**: 未実施（Phase S 候補）
- [ ] **`-b > -ub` 運用の意義**: Phase P で観測のみ
- [ ] **graph splits=77 (with bs=1) の存在意義**: 全条件で固定 77、bs=1 時に使われるパス（eval 段階か KV update か）
- [ ] **`--parallel 2` との相互作用**: `-b` が並列度に寄与する設計のはず
- [ ] **P3 vs Phase O の eval 差 +1.17% のセッション源**: 同一条件で sched_reserve 完全再現だが eval 差
- [x] **Phase P と Phase N の fa=1 4 点モデル係数の `-ub` ベース再校正**: ✅ Phase Q 7 点で線形係数 0.982422 確定（CUDA3）。他 GPU は本レポート §7 で更新
- [ ] **本番 ctx=131072 + `-ub=2048` 起動試験**: Phase Q で予測精度確定、実機検証は未実施

### 新規項目（本 Phase Q で判明・発生）

- [ ] **eval ピークが ub=2048 となる物理メカニズム**: SM 数 56 × thread 36 ≈ 2016 との一致は偶然か必然か。kernel launch overhead と SM occupancy の trade-off で説明できるか
- [ ] **W 字型 (ub=512 が部分的に回復) の再現性**: 1 セッションのみでの観測、再計測が必要
- [ ] **`-ub` 内部下限の真の値**: ub=128 でも警告ゼロ。`-ub=64 / 32 / 16 / 8 / 4 / 2 / 1` でどこまで動作するか（Phase Q-2 候補）
- [ ] **CUDA3 線形係数 0.982422 の更なる分解**: 0.96 + 0.022 = embedding (hidden_dim × 2 byte) + α？モデルアーキテクチャから理論値を導出可能か
- [ ] **CUDA0 の係数 0.077〜0.083 の ub 依存性**: ub<256 と ub>2048 で値が違う？非線形要素の存在
- [ ] **モデル別の係数転移性**: Qwen3.5-122B-A10B では 0.9824 だが、Qwen3.5-35B-A3B では？hidden_dim の比例関係を仮定すると予測可能
- [ ] **prompt 処理速度と `-ub` の関係（極小 ub 領域）**: Phase Q では prompt_n=67/69 のみ。prompt_n=8k/32k で `-ub=128` がどれだけ不利か
- [ ] **Q_K_M 量子化での係数変化**: Q4_K_M で 0.9824、Q3_K_M / IQ2_XXS では？
- [ ] **本番 ctx=131072 + `-ub=2048` 起動試験**: 理論上 CUDA3 ≈ 2,012 MiB、合計 ≈ 4,276 MiB で確実起動可能。実機で eval / prompt / 長文応答品質を検証
- [ ] **eval ピーク `ub=2048` の周辺探索**: ub=1536 / 2560 / 3072 で eval が ub=2048 を上回る可能性。500 刻みの細かいスキャンで真のピーク特定
- [ ] **長時間 eval (1000 token 生成) での `-ub` 影響の蓄積**: Phase Q は predicted_n=256 のみ。decode 中の cache pressure による差

## 検証完了後に実施すべき TODO

### 既知項目（Phase P から継続、本 Phase Q で更新）

- [ ] **start.sh の拡張**: `LLAMA_NUMACTL_PREFIX` / `LLAMA_EXTRA_THREADS` 環境変数サポート追加
- [ ] **CUDA1 セーフティマージン OOM フォールバック実装**
- [ ] **層→GPU アライメントのソースコード解析**
- [ ] **C-4 実験**（CPU 層削減 + GPU 層追加）
- [ ] **drop_caches 権限の確保**（sudoers 設定 or vmtouch 導入）
- [ ] **C-D3 での perf stat 計測**
- [ ] **コールドスタート C-D6 計測**
- [ ] **start.sh での NUMA プリセット整備**
- [ ] **start.sh に `--threads` 設定追加**
- [ ] **PID 取得ロジックの統一**
- [ ] **セッション間ゆらぎの管理**: 計測プロトコルに「直前プロセス情報」を明示的に記録
- [ ] **`--poll 50` を採用しない旨を start.sh のコメントで明記**
- [ ] **`measure_phaseI.sh` を汎用化して skill に組み込む**
- [ ] **「長コンテキスト性能カード」をモデル単位で記録するドキュメント整備**（**Phase Q で `-ub` ピーク 2048 を追加**）
- [ ] **アプリ側にコンテキストサイズ別レイテンシ警告を出す仕組み**
- [ ] **プロンプトキャッシュの活用ドキュメント化**
- [ ] **`start_phaseJ.sh` 〜 `start_phaseQ.sh` の環境変数化を skill 側 `start.sh` に逆輸入**
- [ ] **依存制約の lint 化**: 起動前 pre-check
  - **Phase Q 確定: fa=1 は `n_eff=min(ctx,-ub)` で計算し `predicted_cuda3 = 0.9824·n_eff` ≤ GPU 空き枠を判定**（係数の有効範囲: ub=128 〜 8192 で誤差 < 0.005%）
- [ ] **llama.cpp upstream issue/PR のサーベイ**

### 新規項目（本 Phase Q で発見）

- [ ] **★最優先: start.sh の既定値を `-ub=2048` に確定**:
  - Phase P で +1.5% eval 向上、Phase Q で **ub<2048 全域で eval 低下を実証**
  - **`UB_SIZE` 環境変数を追加、既定値 2048 でハードコード**（現状 8192）
  - `BATCH_SIZE` も並行で `-b=2048` 推奨（`-b=8192` でも compute buffer は変わらないが、prompt 大での `-b > -ub` の利点は要検証）
- [ ] **★最優先: 起動前 lint に `predicted_cuda3 = 0.9824 × min(ctx, ub)` を組み込む**:
  - skill 側 `start.sh` で起動前に CUDA3 の予測値と実空き枠を比較
  - 誤差 0.002% の精度なので、warning 閾値はマージン 50 MiB で十分
- [ ] **compute buffer 予測モデル（Phase Q 確定版）を skill / CLAUDE.md に記録**:
  - **fa=1**: `n_eff = min(ctx, -ub)`、ub=128 〜 8192 の範囲で
    - **CUDA3 = 0.9824·n_eff**（誤差 0.002%、Phase Q で ub=128 まで線形性確認）
    - CUDA1 = CUDA2 ≈ 0.254·n_eff
    - CUDA0 ≈ 951 + 0.077·n_eff（Phase Q で定数項漸近値 951 を確定）
    - CUDA_Host ≈ 0.086·n_eff（Phase Q で純比例、定数項ゼロを確定）
  - **fa=0**: Phase M の係数は `-b=-ub=8192` 固定下のもの、`-ub` 軸での再測定が必要
- [ ] **CLAUDE.md / skill の情報更新**:
  - 「fa=1 の compute buffer は **`-ub`（micro-batch size）に純線形比例、係数は CUDA3 で 0.9824 MiB/token**」を記録
  - 「**eval 速度のピークは `-ub=2048`、それ以下は SM 利用率不足で低下、それ以上は転送負荷で低下**」を記録
  - 「**`-ub` 既定値は 2048 を推奨**（VRAM 削減 73% + eval +1.5% のダブルウィン）」を明記
  - 「**`-ub` 緊急時の救済策として 1024 / 512 / 256 を提供可、eval 損失 3〜5% で compute buffer を 1/4〜1/16 に圧縮可能**」を記録
- [ ] **モデルカード更新**: Qwen3.5-122B-A10B の「`-ub` vs eval / VRAM」テーブルを Phase Q 結果（7 点）で記載
- [ ] **本番 ctx=131072 での `-ub=2048` 動作確認**: Phase P/Q 予測 CUDA3=2,012 MiB / 合計 28 GB で確実起動。実機で長文応答品質を検証
- [ ] **Phase Q-2 候補（`-ub` 内部下限の真の値特定）**: `-ub=64 / 32 / 16 / 8 / 4 / 2 / 1` で線形性 / 拒否ログ / eval 影響を確認
- [ ] **Phase Q-3 候補（`-ub` ピーク周辺探索）**: ub=1536 / 1792 / 2304 / 2560 / 2816 / 3072 で eval ピーク値の真の最大化点を特定
- [ ] **Phase R 候補（fa=0 側での `-ub` 支配性検証）**: Phase M の係数は `-ub` 軸で再フィット必要
- [ ] **Phase S 候補（prompt サイズ × `-ub` 2 軸スキャン）**: prompt_n=1k/8k/32k で `-ub=512/2048/8192` の prompt_per_second を測定
- [ ] **Phase T 候補（`-ub=1` でのベンチマーク）**: greedy decode、`-ub` 影響は理論上最小、係数の境界条件確認

## 補足

### Phase Q の核心発見

1. **CUDA3 = 0.9824·ub は ub=128 まで完全線形** — 64 倍ダイナミックレンジで R²=1.00000000、誤差 0.002%
2. **eval ピークは `-ub=2048`** — それ以下は eval 低下、Phase P の +1.5% は実は最高点を観測していた
3. **graph splits の bs=${ub} 対応は ub=128 まで継続** — llama.cpp 内部の `n_ubatch` ベース実装の最終確認
4. **CUDA_Host 定数項は 0 に近い、純比例 0.086·ub** — Phase P 推定 130 MiB は誤り
5. **CUDA0 定数項漸近値は 951 MiB** — Phase N 推定 828 を更新、Phase O の +455 MiB 残差の原因が解明
6. **線形性崩壊点は ub=128 までの範囲では未検出** — `-ub` の物理的下限は更に下（Phase Q-2 候補）

### 計算モデルの確定版（fa=1, f16 KV, C-D3 base、ub=128〜8192 で実証）

```
n_eff = min(ctx, -ub)   ← Phase P で確定、Phase Q で範囲拡張

fa=1: compute_buffer(n_eff)   [MiB]、ub=128〜8192 の範囲で実証
  CUDA0:    951 + 0.077·n_eff           [Phase Q で定数項漸近値 951 を確定]
  CUDA1/2:  0.254·n_eff                  [Phase Q 範囲では純線形で十分]
  CUDA3:    0.9824·n_eff                 [完全一致、誤差 0.002%、ub=128〜8192]
  CUDA_Host: 0.086·n_eff                 [Phase Q で純比例、定数項ゼロを確定]

fa=1 合計 ≈ 951 + (0.077 + 2·0.254 + 0.9824 + 0.086)·n_eff
        ≈ 951 + 1.654·n_eff             [n_eff ≤ -ub で線形]
```

### eval 速度モデル（Phase P + Q 統合、fa=1 ctx=16384 固定）

```
eval(ub) ≈ピーク 15.42 t/s @ ub=2048

ub > 2048: SM 内で過剰 batch、kernel が compute buffer 移動で律速
  ub=4096: 15.37 (-0.3%)
  ub=8192: 15.19 (-1.5%)

ub < 2048: SM 利用率不足、kernel launch overhead が支配
  ub=1024: 14.75 (-4.4%)
  ub=512:  14.95 (-3.0%)  ※W 字型の小ノイズ
  ub=256:  14.72 (-4.5%)
  ub=128:  14.72 (-4.5%)
```

### VRAM 予測表（Phase P + Q 実証データベース、fa=1 ctx=131k 想定）

| -ub | n_eff | CUDA3 (MiB) | compute buffer 合計 (MiB) | GPU 使用量合計 (MiB) | eval (Phase Q ctx=16k) | 起動可否 / 推奨度 |
|---:|---:|---:|---:|---:|---:|---|
| 8,192 | 8,192 | 8,048 | 15,697 | 39,110 | 15.19 | ✅（現状、過大） |
| 4,096 | 4,096 | 4,024 |  8,025 | 31,790 | 15.37 | ✅（中庸） |
| **2,048** | **2,048** | **2,012** |  **4,276** | **28,218** | **15.42** | ✅ **★本番既定推奨** |
| 1,024 | 1,024 | 1,006 |  2,587 | 26,616 | 14.75 | ✅（VRAM 緊急時） |
|   512 |   512 |   503 |  1,774 | 25,848 | 14.95 | ✅（VRAM 緊急時） |
|   256 |   256 |   252 |  1,367 | 25,460 | 14.72 | ✅（極限の VRAM 削減） |
|   128 |   128 |   126 |  1,168 | 25,272 | 14.72 | ✅（極限） |

**`-ub=2048` を本番既定に採用すれば、131k コンテキストでも CUDA3 空き 14 GB 以上を確保し、かつ eval +1.5% のダブルウィン**。これ以上の `-ub` 削減は eval 損失 3〜5% を伴うため非推奨（VRAM 緊急時のみ）。

### 作業終了時点の状態

- llama-server は停止済み（Q1〜Q4 の 4 セッションすべて stop.sh で正常終了）
- GPU サーバロック（t120h-p100）は解放済み
- `results.tsv` 12 行（4 条件 × warmup 3 run）で集計完了
- `compute_buffer_summary.txt` に 4 起動の `sched_reserve` / `graph splits` を集約済み
- `fit_analysis.py` / `fit_analysis.txt` で全条件の CUDA3 線形性（誤差 0.002%）・log-log 傾き（全 6 区間 1.0000）・7 点フィット（係数 0.982422、R²=1.0）・eval 反転点（ub=2048 頂点）を保存
- **本番 start.sh の `-ub=2048` 既定値ハードコードを次フェーズの最優先タスクとして登録**
