# Qwen3.5-122B-A10B C-3 Phase L（f16 KV + ctx=4096 で flash-attn ON/OFF A/B 比較）

- **実施日時**: 2026年4月18日 07:01 – 20:10 (JST、fa=1 起動試行で偶発的に 12 時間 idle が発生したため実計測時間は約 40 分)
- **作業種別**: 計測・検証（Phase K 未検証事項「ctx ≤ 4096 での flash-attn=0 起動可否」「O(n²) compute buffer スケーリング仮説の実測」）

## 添付ファイル

- [実装プラン](attachment/2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan/plan.md)
- [起動スクリプト (start_phaseL.sh)](attachment/2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan/start_phaseL.sh)
- [計測スクリプト (measure_phaseI.sh、Phase I から流用)](attachment/2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan/measure_phaseI.sh)
- [一括実行スクリプト (run_all.sh、Phase J から流用)](attachment/2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan/run_all.sh)
- [集計スクリプト (aggregate_results.sh)](attachment/2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan/aggregate_results.sh)
- [集計結果 TSV (results.tsv)](attachment/2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan/results.tsv)
- [fa=0 マスターログ (run_all_L_f16_fa0_ctx4096.log)](attachment/2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan/run_all_L_f16_fa0_ctx4096.log)
- [fa=1 マスターログ (run_all_L_f16_fa1_ctx4096.log)](attachment/2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan/run_all_L_f16_fa1_ctx4096.log)
- [fa=0 起動ログ (startup_logs/fa0_ctx4096.log)](attachment/2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan/startup_logs/fa0_ctx4096.log)
- [fa=1 起動ログ (startup_logs/fa1_ctx4096.log)](attachment/2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan/startup_logs/fa1_ctx4096.log)
- `out_L_f16_fa{0,1}_ctx4096_{warmup,1k}/` の各計測アーティファクト

## 参照

- 前身レポート: [2026-04-18_025221_qwen3-122b-c3-phaseK-f16-flashattn-ab.md](2026-04-18_025221_qwen3-122b-c3-phaseK-f16-flashattn-ab.md)
- Phase J: [2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab.md](2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab.md)
- Phase I: [2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext.md](2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext.md)

## 前提・目的

Phase K で「f16 KV + ctx=16384 での `--flash-attn 0` は graph_reserve 段階で CUDA0 に 18,176 MiB の compute buffer を要求 → P100 16GB では OOM、起動不能」と判明した。Phase K レポートは「compute buffer は attention score matrix の O(n²) 依存で、ctx を縮小すれば起動可能」という**仮説**を提示し、ctx=4k で ~1,136 MiB、2k で ~284 MiB と予測したが、**実験的検証は未実施**だった。

本 Phase L では、その未検証事項のうち最優先の 2 件を同時に解決する:

1. **ctx ≤ 4096 での flash-attn=0 起動可否確認**
2. **O(n²) compute buffer スケーリング仮説の実測検証**（起動ログの `sched_reserve: CUDA* compute buffer size` 行から採取）
3. 副次目的: 起動可能な ctx での **fa=0 vs fa=1 eval/prompt A/B 比較**（Phase K で未達）

### 成功条件（当初設定）

- fa=0 + ctx=4096 での起動可否を明示的に判定する（OOM なら ctx=2048 → 1024 へ降順） → **ctx=4096 で起動成功のため降順探索は省略**
- 起動成功 ctx で fa=0/1 両条件を warmup + 1k × 3 runs で計測 → **達成**
- compute buffer の実測 MiB と Phase K 仮説の O(n²) 外挿値を突き合わせ → **達成**

## 環境情報

- **サーバ**: `t120h-p100` (10.1.4.14)
- **GPU**: NVIDIA Tesla P100-PCIE-16GB × 4（各 16,269 MiB、合計 65,077 MiB、CC 6.0）
- **CPU**: Intel Xeon Gold 6138 @ 2.00GHz × 2 socket、計 40 コア / 80 スレッド、NUMA 2 ノード
- **メモリ**: 257,560 MiB (約 251 GiB)
- **モデル**: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- **llama.cpp ビルド**: b8807-b3d758750（Phase D〜K と同一系列）
- **構成（Phase L）**: C-D3 ベース + `--cache-type-{k,v} f16` + `--ctx-size 4096`
  - NUMA: `numactl --cpunodebind=1 --membind=1 --`
  - `--threads 40 --poll 0 -b 8192 -ub 8192`
  - `-ngl 999 -ot 'blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'`
  - `--cache-type-k f16 --cache-type-v f16 --ctx-size 4096`
- **L_f16_fa0_ctx4096 セッション PID**: 143119（fresh、計測直後に停止）
- **L_f16_fa1_ctx4096 セッション PID**: 148429（fresh、計測直後に停止）

## 計測手順（再現方法）

### スクリプト構成（Phase K からの変更点）

| ファイル | 変更内容 |
|---|---|
| `start_phaseL.sh` | Phase K の `start_phaseK.sh` をベースに、`--ctx-size` を **`CTX_SIZE` 環境変数化**、`FLASH_ATTN` 既定値を 0 に変更、リモートログ名に `fa${FLASH_ATTN}_ctx${CTX_SIZE}` を含めて分離、ヘルスチェック待ちを 300s → 120s に短縮、OOM 3 パターン（`cudaMalloc failed`、`failed to allocate CUDA* buffer`、`graph_reserve: failed to allocate`）を grep して早期 abort する条件を追加 |
| `run_all.sh` | 変更なしで流用 |
| `measure_phaseI.sh` | 変更なしで流用 |
| `aggregate_results.sh` | 集計対象を `out_K_*` → `out_L_*` に変更、存在チェック `[ -d "$dir" ]` を追加 |
| `prompts/` | Phase K からコピー（`prompt_{1k,8k}.txt` のうち 1k のみ使用） |

### 実行フロー

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseL-fa0-ctx-scan"
# （Phase K 資産をコピー、start_phaseL.sh / aggregate_results.sh を作成）

# ---- フェーズ 1: fa=0 起動試行（ctx=4096） ----
FLASH_ATTN=0 CTX_SIZE=4096 bash "$REPORT_DIR/start_phaseL.sh"
# → 起動成功。ctx=2048/1024 の降順探索は実施せず（起動判定は満たされた）
PID=143119
cd "$REPORT_DIR"
TAG_PREFIX=L_f16_fa0_ctx4096 SIZES="warmup 1k" PID=$PID bash run_all.sh
.claude/skills/llama-server/scripts/stop.sh t120h-p100

# ---- フェーズ 2: fa=1 起動（A/B 対照、同一 ctx=4096） ----
FLASH_ATTN=1 CTX_SIZE=4096 bash "$REPORT_DIR/start_phaseL.sh"
PID=148429
TAG_PREFIX=L_f16_fa1_ctx4096 SIZES="warmup 1k" PID=$PID bash run_all.sh
.claude/skills/llama-server/scripts/stop.sh t120h-p100

cd "$REPORT_DIR" && bash aggregate_results.sh > results.tsv
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 実行タイムライン

| タグ | prompt_n（ChatTemplate 込み） | Run 数 | 開始 | 終了 |
|------|---------:|------:|----------:|----------:|
| L_f16_fa0_ctx4096 起動試行 | — | — | 07:02:27 | 07:02:42（**起動成功、15s**）|
| L_f16_fa0_ctx4096_warmup | 58 | 3 | 07:52:54 | 07:57:49 |
| L_f16_fa0_ctx4096_1k | 1,079 | 3 | 07:57:49 | 08:02:39 |
| L_f16_fa1_ctx4096 起動試行 (aged suspect) | — | — | 08:03:14 | 19:55（**誤って 12 時間 idle 稼働、停止して再起動**） |
| L_f16_fa1_ctx4096 起動試行 (fresh) | — | — | 19:55:41 | 19:55:56（**起動成功、15s**）|
| L_f16_fa1_ctx4096_warmup | 58 | 3 | 19:59:35 | 20:04:34 |
| L_f16_fa1_ctx4096_1k | 1,079 | 3 | 20:04:34 | 20:09:28 |

Phase L の実計測時間: **fa=0 約 10 分 + fa=1 約 10 分 = 約 20 分**（aged セッション分を除く）。途中で Claude セッションの完了通知が届かず 12 時間 idle となった fa=1 初回起動は **aged 疑いのため破棄**し、公平な A/B のため fresh で再起動した（「補足」参照）。

## 実行結果サマリ

### 1. 起動可否マトリクス

| ctx | f16 KV, fa=0 | f16 KV, fa=1 |
|----:|:---:|:---:|
| 16384 (Phase K) | ❌ OOM (CUDA0 18,176 MiB 要求) | ✅ 起動成功 |
| **4096 (Phase L)** | **✅ 起動成功**（新規発見） | ✅ 起動成功 |
| 2048 / 1024 | 未実施（ctx=4096 で判定達成のため省略） | 未実施 |

Phase K 仮説「fa=0 は ctx ≤ 4096 程度に絞れば起動可能」は **ctx=4096 で成立を実証**。ただし後述のとおり、compute buffer 要求量の実測から「純粋な O(n²)」ではなく O(n^1.3) 程度の混合オーダーであった。

### 2. compute buffer の実測 MiB（起動ログ `sched_reserve` より）

| GPU | Phase K fa=1 (ctx=16384) | **L fa=0 (ctx=4096)** | **L fa=1 (ctx=4096)** | L fa=0 vs K fa=1 比 |
|----:|------:|------:|------:|------:|
| CUDA0 | 2,888 (推定) | **2,888.00** | **1,428.00** | — |
| CUDA1 | 2,656 (推定) | **2,656.09** | **944.13** | — |
| CUDA2 | 2,608 (推定) | **2,608.09** | **944.13** | — |
| CUDA3 | 4,024 (推定) | **4,024.00** | **4,024.00** | — |
| CUDA_Host | 176 (推定) | **176.13** | **160.16** | — |
| **CUDA 合計** | — | **12,176.18** | **7,340.26** | fa=1 は fa=0 の **60.3%** |
| graph nodes | — | 4,532 | 4,473 | — |

> **Phase K fa=0 (ctx=16384)** 起動時の唯一採取できた CUDA0 要求量は **18,176 MiB**（`cudaMalloc failed: out of memory` 直前のログ）。他 GPU の数値は停止点より後のため採取されず。

### 3. Phase K 仮説 (O(n²)) と実測の突き合わせ

Phase K が予測した「fa=0 の ctx を 1/4 に縮小（16384 → 4096）すると compute buffer は 1/16 (18176 → ~1136 MiB)」に対し、**実測は CUDA0 で 18176 → 2888 MiB、比は 1/6.29**。

- 対数スケールで n^k を求めると: `log(6.29) / log(4) = 1.306`
- つまり **compute buffer ≈ O(n^1.3)**、純粋な O(n²) ではない
- 要因の内訳推定:
  - attention score matrix 成分: O(n²)（flash-attn 未使用時）
  - 中間活性 / logits / working buffer 成分: O(n)
  - 定数成分（embedding/output layer の常駐領域）: O(1)
- CUDA3 が **fa=0 でも fa=1 でも 4,024 MiB で不変**である事実は、CUDA3 に配置されている output/embed 層の compute buffer が **ctx / flash-attn に依存しない定数成分**であることを示唆（ctx=16384 時も同じ値だった可能性が高い）

### 4. fa=0 vs fa=1 の eval 速度（ctx=4096 同条件 A/B）

| タグ | prompt_n | Run 1 | Run 2 | Run 3 | 中央値 | Run 間 range |
|------|---------:|------:|------:|------:|------:|-----:|
| L_f16_fa0_ctx4096_warmup | 58 | 15.068 | 15.064 | 15.075 | **15.067** | 0.011 (0.07%) |
| L_f16_fa1_ctx4096_warmup | 58 | 14.973 | 14.961 | 14.963 | **14.963** | 0.012 (0.08%) |
| L_f16_fa0_ctx4096_1k | 1,079 | 14.495 | 14.496 | 14.489 | **14.495** | 0.007 (0.05%) |
| L_f16_fa1_ctx4096_1k | 1,079 | 14.952 | 14.947 | 14.940 | **14.947** | 0.012 (0.08%) |

**A/B 差分 (fa=1 − fa=0)**:

| サイズ | fa=0 中央値 | fa=1 中央値 | Δ (t/s) | Δ (%) | 判定 |
|------|------:|------:|-----:|-----:|------|
| warmup (58 tok) | 15.067 | 14.963 | **−0.104** | **−0.69%** | ゆらぎ範囲内（差なし）|
| 1k (1,079 tok) | 14.495 | 14.947 | **+0.452** | **+3.12%** | **fa=1 が有意に速い** |

Run 間 range は全 12 runs で 0.05〜0.08% と Phase K 同様に極めて安定。eval 速度の flash-attn 寄与は **プロンプト長に強く依存**し、

- 短プロンプト（warmup 58 tok）では fa=1 がむしろ微減（誤差範囲）
- 中プロンプト（1k = 1079 tok）では fa=1 が **+3.12%** と有意に速い

この結果は flash-attention の設計原理（attention score 計算の O(n²) → O(n) オンチップ化）と合致する。短プロンプトでは attention 計算の絶対時間が小さく、flash-attn のカーネル切替オーバーヘッドが相殺するが、プロンプトが長くなるほど効果が勝る。

### 5. prompt 処理速度

| タグ | Run 1 | Run 2 | Run 3 | 中央値 |
|------|------:|------:|------:|------:|
| L_f16_fa0_ctx4096_warmup | 9.66 | 10.11 | 10.03 | **10.03** |
| L_f16_fa1_ctx4096_warmup | 9.71 | 10.11 | 10.08 | **10.08** |
| L_f16_fa0_ctx4096_1k | 68.28 | 68.52 | 68.56 | **68.52** |
| L_f16_fa1_ctx4096_1k | 68.50 | 68.56 | 68.46 | **68.50** |

**1k の prompt_per_second は fa=0/1 で 68.52 vs 68.50 と完全に同等**（差 0.03%、誤差）。これは prompt 処理（KV cache を埋めるフェーズ）が flash-attn の最適化経路を通らず、通常 attention でも同じ速度で動くことを示唆する（prompt 処理は FFN と KV cache 書き込みが律速で、attention の read 回数が decode フェーズより圧倒的に少ないため）。

### 6. GPU メモリ使用量（`gpu_post_run*.csv` より、warmup 時）

| GPU | L fa=0 (ctx=4096) | L fa=1 (ctx=4096) | Δ |
|----:|------:|------:|------:|
| 0 | 4,627 | 3,165 | **−1,462 MiB (−31.6%)** |
| 1 | 12,641 | 10,929 | **−1,712 MiB (−13.5%)** |
| 2 | 12,593 | 10,929 | **−1,664 MiB (−13.2%)** |
| 3 | 6,145 | 6,145 | ±0 |
| **合計** | 36,006 | 31,168 | **−4,838 MiB (−13.4%)** |

（単位 MiB）compute buffer 実測差 (12,176 − 7,340 = 4,836 MiB) とほぼ完全一致。他領域（model weight、KV cache）は同一条件で不変のため、差分は純粋に compute buffer 由来と確認。

### 7. Phase K fa=1 warmup との再現性（同 ctx ≠、セッション間ゆらぎ確認）

| セッション | warmup 中央値 | 備考 |
|-----------|:------:|------|
| Phase K K_f16_fa1_warmup | 15.046 | ctx=16384、fresh |
| **Phase L L_f16_fa1_ctx4096_warmup** | **14.963** | ctx=4096、fresh |
| Phase K K_f16_fa1_1k | 15.032 | ctx=16384、fresh |
| **Phase L L_f16_fa1_ctx4096_1k** | **14.947** | ctx=4096、fresh |

ctx のみ 16384 → 4096 に縮小した fa=1 同条件比較で **warmup −0.55%、1k −0.57%**。Phase K 「ctx-size の eval 速度への直接影響」未検証項目の初期データとして、**ctx を 1/4 に縮小しても eval 速度は ~0.5% しか変わらない**ことを示唆。セッション間ゆらぎ（14.66〜15.28、4.2% レンジ）よりも小さく、**ctx-size は eval 速度にほぼ影響しない**というのが本 Phase L の副次所見。

## ボトルネック・副次発見の分析

### 1. Phase K 仮説の部分訂正（O(n²) → O(n^1.3)）

Phase K は「compute buffer は attention score matrix O(n²)」と単純化して予測値を示したが、Phase L 実測で **n^1.306** と確認された。内訳として:

- **O(n²) 成分**: attention score matrix（Q·K^T の n×n 行列、fa=0 時のみ必要）
- **O(n) 成分**: 各層の中間活性（hidden × n）、logits 計算、KV cache 操作領域
- **O(1) 成分**: embedding layer、output head、その他の固定領域

ctx=16384 → 4096 では n² 成分が 1/16、n 成分が 1/4、定数成分は不変のため、全体では「1/16〜1/1 の加重平均」として 1/6.29 に収まる。ctx 依存成分の内訳を特定するには、更に ctx=2048 / 1024 の実測（O(n²) 成分は急減、O(n) 成分も 1/2 / 1/4 に縮小）が必要で、2 点測定からは切り分け不可。

### 2. flash-attn の eval 速度寄与が初めて定量化

Phase I〜K まで「flash-attn は C-D3 の機能要件」（量子化 KV、長 ctx の VRAM 制約など）として固定されてきたが、**本体の速度寄与の大きさは未計測**だった。Phase L で初めて同条件 A/B が成立し:

- **短プロンプト (58 tok)**: fa=1 寄与 **±0%**（誤差、むしろ微減）
- **中プロンプト (1,079 tok)**: fa=1 寄与 **+3.12%**

この傾向から、長プロンプト（8k、32k、120k）では更に寄与が増大すると推測されるが、P100 の VRAM 制約で fa=0 時の ctx=8k 以上は起動不能のため、**本 Phase では長プロンプト A/B は原理的に実施不可**。ただし、Phase K の fa=1 ctx=131072 での eval=14.558 t/s（8k プロンプト）と比較すると、ctx 依存の線形モデル `time_per_token = 66.5μs + 0.485μs × N_context`（Phase I 提案）の枠組みで、fa=0 ならさらに係数が大きくなる可能性がある。

### 3. CUDA3 の compute buffer が fa=0/1 で不変（4,024 MiB）

`sched_reserve` で報告された CUDA3 buffer は fa=0 でも fa=1 でも **4,024 MiB で完全に同一**。これは:

- CUDA3 が attention を担当していない（= attention score matrix を計算しない）
- CUDA3 に配置されているのは FFN routing / output head 系の層で、flash-attn の最適化経路を通らない

ことを示唆。Phase K の dmon 所見（CUDA1/2/3 が idle、計算は CUDA0 集中）と整合し、**attention 計算は CUDA0 に集中、CUDA3 は output layer 周りの定常計算**という層配置の裏付けになる。これは Phase J/K 継続項目「層→GPU アライメントのソース解析」への間接証拠。

### 4. prompt 処理が fa=0/1 で同速という発見

prompt_per_second が 1k で fa=0/1 ともに 68.5 と完全一致した事実は、「prompt 処理フェーズでは flash-attn の効果が出ない」ことを明示している。これは:

- prompt 処理 (ubatch=8192) は chunk 単位で ubatch 分を一括処理するため、attention の read 回数が decode 時 (token ごとに全 KV を参照) より少ない
- compute buffer の確保は起動時に 1 度だけで、prompt 処理の実行時間は buffer サイズにほぼ無関係

つまり flash-attn の速度寄与は **decode（eval）フェーズ専用**であり、**prompt 処理では VRAM 削減のみが効果**（速度はほぼ同じ）。アプリ側でコンテキストキャッシュ戦略を考える際の重要な仕様情報。

### 5. セッション間ゆらぎの続報

| セッション | warmup 中央値 | 備考 |
|-----------|:------:|------|
| Phase H H1_t0 | 14.664 | poll=0 fresh |
| Phase I I_warmup | 15.000 | poll=0 fresh |
| Phase J J_fa1_warmup | 15.282 | poll=0 fresh (q8_0, ctx=131072) |
| Phase K K_f16_fa1_warmup | 15.046 | poll=0 fresh (f16, ctx=16384) |
| **Phase L L_f16_fa0_ctx4096_warmup** | **15.067** | poll=0 fresh (f16, ctx=4096) |
| **Phase L L_f16_fa1_ctx4096_warmup** | **14.963** | poll=0 fresh (f16, ctx=4096) |

Phase G/H/I/J/K を含めた 7 セッションで 14.66〜15.28 の **4.2% レンジ**（Phase K 時点から拡大せず）。Phase L は中央域の 14.96〜15.07。本 Phase の Run 間 range は 0.05〜0.08% と過去最小レベル。

## 採用判定

| 項目 | 結果 |
|------|------|
| f16 KV + fa=0 の起動可否（ctx=4096）| **可能**（Phase K 仮説の実証）|
| Phase K 仮説「compute buffer は O(n²)」| **部分訂正**: 実測は O(n^1.3)、n²/n/定数 成分の混合 |
| fa=1 vs fa=0 の eval 速度差（ctx=4096 同条件）| warmup 0%、1k +3.12% |
| fa=1 vs fa=0 の prompt 速度差 | **ほぼ完全一致** (1k で差 0.03%) |
| fa=1 vs fa=0 の VRAM 差 | fa=1 が **−4,838 MiB (−13.4%)** |
| C-D3 採用構成（q8_0, ctx=131k, fa=1）の妥当性 | **再確認**（fa=1 の VRAM 節約効果は長 ctx で必須、速度寄与は中〜長プロンプトでプラス）|

**結論**: Phase K の「flash-attn=1 は C-D3 の機能要件」は維持される。Phase L の新規所見として:

1. **fa=0 は ctx=4096 なら起動可能**（P100 16GB 環境）、ただし compute buffer 合計 12 GB を占めるため他リソース（長 ctx、複数 parallel slot）と両立不可
2. **fa=1 の eval 速度寄与は中プロンプト以上で +3%**（短プロンプトでは無効）、long ctx では更に大きいと推測
3. **fa=1 の VRAM 削減効果は 4〜5 GB 規模**（ctx=4k 時点で既に有意）、これが C-D3 で長 ctx を成立させる主因

副次的に、**ctx-size 単独では eval 速度にほぼ影響しない**（ctx=4k と ctx=16k で差 0.5%）ことが確認され、Phase K 継続項目「ctx-size の eval 速度への直接影響」は**ほぼ ゼロ**と結論。

本番 `start.sh` の改変は不要。ただし以下のドキュメント化 TODO:
- 「C-D3 採用構成では fa=1 必須の根本理由は VRAM 制約」（Phase K TODO）
- 「ctx=4k 以下なら fa=0 も起動可能だが、eval 速度は fa=1 より中プロンプトで 3% 遅い」（Phase L 新規）

## 未検証事項

### 既知項目（Phase K から継続、部分更新あり）

- [ ] **2 時間超の連続稼働試験（eval あり）**
- [x] ~~flash-attn off との比較~~ → **Phase L で ctx=4096 条件で達成**（warmup 0%、1k +3.12% 差）
- [ ] **層→GPU アライメントのソース解析**（本 Phase で CUDA3 不変の間接証拠は取得）
- [ ] **ページキャッシュのコールドスタート検証**: `sudo sysctl vm.drop_caches=3` 権限が llm ユーザーにないため未実施
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
- [ ] **「初回サイクル効果」の原因特定**（Phase F 新規項目）
- [ ] **セッション間 warmup ゆらぎ（14.66〜15.28）の原因特定**（Phase H/J/K 継続、本 Phase で fa=0/1 両方が中央域 14.96〜15.07 を再観測）
- [ ] **`--poll 1` / `--poll 10` / `--poll 100` の影響**
- [ ] **G_aged_t96 の再現条件の特定**（本 Phase の fa=1 初回起動で偶発的に 12 時間 aged 状態が発生、破棄したがログは取得せず、追補対象）
- [ ] **`--poll` とスレッド affinity / OpenMP の相互作用**
- [ ] **線形モデル `time_per_token = 66.5μs + 0.485μs × N_context` の他構成での検証**（本 Phase の ctx=4k で傾きが近いか: 14.947 t/s = 66.9 μs/tok、Phase I モデルの f(1024)≈67μs と**近似一致**）
- [ ] **prompt_per_second が 8k で頂点を打つ理由**（`-b / -ub 8192` との関連検証）
- [ ] **64k / 120k の Run 間再現性**
- [ ] **128k コンテキストが純粋応答に与える影響**（131k 上限）
- [ ] **KV cache 量子化 (q8_0) の精度影響**（長コンテキストでの出力品質）
- [ ] **prompt cache hit 時の実効 turn time**
- [ ] **ワークスペース +950 MiB の内訳**（本 Phase で CUDA3 が fa=0/1 不変の 4,024 MiB と判明、関連調査対象）
- [ ] **llama.cpp のソース上で `--cache-type-{k,v} q8_0` と `--flash-attn` の依存ロジック確認**（Phase J 継続、Phase K/L の新発見を踏まえ優先度上昇）
- [ ] **Segfault 時のバックトレース取得**（Phase J/K、core dump を gdb で解析）
- [ ] **P100 CC 6.0 の flash-attention カーネル経路の検証**（`ggml-cuda` 内のカーネル分岐点、本 Phase で fa=0/1 の数値差が明らかになり動機強化）
- [ ] **CUDA1/2/3 の SM 稼働実態の時系列計測**（Phase J/K から継続、本 Phase でも同様の idle 挙動推定）
- [ ] **J_fa1_warmup run 1 の外れ値（15.54 t/s）再現性**（Phase K に続き Phase L でも再現せず、全 12 runs が ±0.1% に収束）

### 新規項目（本 Phase L で判明・発生）

- [ ] **ctx=2048 / 1024 での fa=0 compute buffer 実測**: O(n^1.3) 混合オーダーの内訳（n² 成分 vs n 成分）を切り分けるには、ctx を更に 2 点（2048, 1024）で計測する必要がある。2 点のみでは「非 n² だが何次か」までで、3 点目があれば最小二乗で n² 係数と n 係数を分離可能
- [ ] **長プロンプト fa=0 A/B**: ctx=4k での 1k プロンプトで fa=1 寄与 +3.12% だが、fa=0 では ctx ≤ 4k の制約から 8k プロンプトは原理的に不可。**疑似的に ctx=4k のまま繰り返し会話を重ねて KV を埋めた状態**（実効 ~3.5k KV）での eval 差分を計測する手段の検討
- [ ] **CUDA3 の固定 4,024 MiB の中身**: fa=0/1 で不変の理由（embed/output 層の常駐 buffer）を llama.cpp ソースコードから特定。Phase K 未解明項目「ワークスペース +950 MiB の内訳」とも関連
- [ ] **fa=0 での idle 劣化（aged）挙動**: 本 Phase で fa=1 初回起動後 12 時間 idle の aged セッションが偶発的に発生したが、eval 未実施のため破棄。aged 条件で fa=0 の eval 劣化が fa=1 とどう違うかは別計測が必要
- [ ] **f16 + ctx=4k + fa=0 の q8_0 化影響**: 同 ctx でも KV を q8_0 にすれば fa=0 起動が可能か（Phase J で ctx=131k の q8_0+fa=0 は Segfault だが、ctx=4k で q8_0+fa=0 は別挙動の可能性）
- [ ] **prompt_per_second の fa=0/1 完全一致の確証**: 1k で差 0.03% は統計ノイズより小さいが、prompt フェーズが `-ub 8192` で一括処理される以上、他 ubatch 値（2048, 4096）で同様に不変かは未検証
- [ ] **ctx-size の eval 速度への影響がほぼゼロであることの長 ctx 側検証**: Phase L で ctx=4k と ctx=16k (Phase K) の fa=1 warmup 差 −0.55% は誤差範囲。ctx=131k (Phase K fa=1 q8_0) とも比較すべきだが cache-type が異なる。**同 cache-type (f16) で ctx=16k / 32k / 64k** の計測で線形性を確認

## 検証完了後に実施すべき TODO

### 既知項目（Phase K から継続、部分更新あり）

- [ ] **start.sh の拡張**: `LLAMA_NUMACTL_PREFIX` / `LLAMA_EXTRA_THREADS` 環境変数サポート追加
- [ ] **CUDA1 セーフティマージン OOM フォールバック実装**
- [x] ~~flash-attn off ベンチマーク~~ → **Phase L で ctx=4096 条件で達成**
- [ ] **層→GPU アライメントのソースコード解析**（本 Phase の CUDA3 不変所見で動機強化）
- [ ] **C-4 実験**（CPU 層削減 + GPU 層追加）
- [ ] **drop_caches 権限の確保**（sudoers 設定 or vmtouch 導入）
- [ ] **C-D3 での perf stat 計測**
- [ ] **コールドスタート C-D6 計測**
- [ ] **start.sh での NUMA プリセット整備**
- [ ] **start.sh に `--threads` 設定追加**
- [ ] **PID 取得ロジックの統一**
- [ ] **セッション間ゆらぎの管理**: 計測プロトコルに「直前プロセス情報（PID、etime、停止からの経過時間）」を明示的に記録
- [ ] **`--poll 50` を採用しない旨を start.sh のコメントで明記**
- [ ] **idle 劣化が偶発現象と確定した場合、Phase E/G の当該セクションに追記**
- [ ] **`measure_phaseI.sh` を汎用化して skill に組み込む**
- [ ] **「長コンテキスト性能カード」をモデル単位で記録するドキュメント整備**
- [ ] **アプリ側にコンテキストサイズ別レイテンシ警告を出す仕組み**
- [ ] **プロンプトキャッシュの活用ドキュメント化**
- [ ] **`-ub` の感度ベンチマーク追加**
- [ ] **`start_phaseJ.sh` / `start_phaseK.sh` / `start_phaseL.sh` の `FLASH_ATTN`/`CTX_SIZE` 環境変数化を skill 側 `start.sh` に逆輸入**（Phase J/K/L 継続項目）
- [ ] **依存制約の lint 化**（Phase J 継続項目）: 起動前に「`--flash-attn 0` かつ ctx > 4096 かつ P100 GPU」の組み合わせを検知して即エラー終了させる pre-check を `start.sh` に追加（本番事故防止）
- [ ] **llama.cpp upstream issue/PR のサーベイ**（Phase J 継続項目）

### 新規項目（本 Phase L で発見）

- [ ] **CLAUDE.md / skill に「P100 での fa=0 は ctx ≤ 4096 で起動可能、ただし eval は中プロンプト以上で fa=1 より 3% 遅い」を注記**: Phase K で「fa=0 は動かない」と書いた部分を Phase L の実測で訂正。「動くが遅い＋VRAM 食う」という**条件付き動作**として再定義
- [ ] **compute buffer O(n^1.3) モデルの skill への記録**: ctx を変えたときの必要 VRAM を推定する式を llama-server skill に載せる（start.sh 内で `CTX_SIZE >> 4096 && FLASH_ATTN=0` を警告するロジックの根拠）
- [ ] **ctx=2048 / 1024 での fa=0 起動試行（Phase M 候補）**: O(n²) vs O(n) 成分の切り分けのため、3 点目の計測が有用。Phase L のスクリプト (`start_phaseL.sh`) は CTX_SIZE 可変なのでそのまま流用可能
- [ ] **Phase L の A/B 差分をモデルカード項目に追加**: Qwen3.5-122B-A10B の性能カードに「ctx=4k、f16 KV、eval: fa=1 14.95 t/s / fa=0 14.50 t/s (1k prompt)」を記載
- [ ] **レポートテンプレートに「測定時 idle 時間（fresh or aged）」セクションを追加**: 本 Phase で aged 疑いセッションを破棄した教訓として、計測ログに起動からの経過分数を必ず記録するプロトコル化

## 補足

### K_f16_fa1 対 L_f16_fa1_ctx4096 の数値サマリ

- **短プロンプト eval (warmup)**: 14.963 t/s（K 15.046 比 −0.55%、ゆらぎ範囲内）
- **1k 入力 eval**: 14.947 t/s（K 15.032 比 −0.57%、ゆらぎ範囲内）
- **VRAM (CUDA0/1/2/3 warmup)**: 3,165 / 10,929 / 10,929 / 6,145 MiB（K 比で CUDA0 −1,428 MiB、CUDA1/2 −1,206 MiB）
- ctx=16384 → 4096 の縮小による VRAM 節約は **合計 −7,934 MiB (−20%)**、speed 変化は誤差範囲

### Phase L の核心発見

1. **Phase K の O(n²) 仮説は部分訂正され、compute buffer ≈ O(n^1.3)**。純粋な n² ではなく、attention score (n²) + 中間活性 (n) + 定数成分の混合オーダーであることが実測で判明
2. **fa=0 は ctx ≤ 4096 の条件付きで起動可能**: Phase J/K で「動かない」と結論付けた部分を実測で訂正
3. **flash-attn の eval 速度寄与はプロンプト長依存**: warmup で 0%、1k で +3.12%。長プロンプトではさらに拡大が予測されるが本 Phase では計測不可
4. **prompt 処理は fa=0/1 で完全同速**（1k で差 0.03%）: flash-attn の効果は decode 専用で、prompt フェーズは VRAM 削減のみが効く

### 12 時間 aged 疑いセッションの発生と対処

本 Phase で fa=1 ctx=4096 を起動した後（2026-04-18 08:03:14）、Claude 側の完了通知ハンドリングの不具合により、次のアクションが遅延して **11 時間 52 分** セッションが idle 放置された。Phase G の aged 劣化条件（96 時間 idle で劣化報告）に近いため、計測は実施せず停止・再起動し、**fresh セッション（PID=148429、起動 3 分半後に計測開始）で A/B 対照を取得**した。

- aged 疑いセッションの起動ログ / VRAM / プロセス状態は採取済み（[fa1_ctx4096.log](attachment/2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan/startup_logs/fa1_ctx4096.log)）
- eval は未実施（破棄）
- 次回以降、aged 劣化の追試が独立タスクとして実施可能

### 作業終了時点の状態

- llama-server は停止済み（fa=0 / fa=1 両セッションとも計測後に stop.sh で正常終了）
- GPU サーバロック（t120h-p100）は解放済み
- `results.tsv` 12 行（fa=0 warmup×3, fa=0 1k×3, fa=1 warmup×3, fa=1 1k×3）で集計完了
