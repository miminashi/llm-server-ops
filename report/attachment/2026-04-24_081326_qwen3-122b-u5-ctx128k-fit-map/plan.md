# Phase U-5: Qwen3.5-122B-A10B 長文脈 VRAM fit マップ

## Context

Qwen3.5-122B-A10B を **ctx=131072 (128k)** で運用できる (OT, tensor-split) 構成を特定する。現 baseline B14b_ts_alt は ctx=32k / -ts 11,12,13,14 / OT 14 CPU 層で、GPU3 残 1260 MiB のタイト構成。KV は q8_0 / 線形式 `96 × (ctx/16384) MiB` (Phase S 実測で 16 点一致) で、ctx=128k では KV が 32k 比 4 倍 (192→768 MiB 全体、1 GPU あたり +150 MiB 級) 膨張するため baseline のままでは OOM 濃厚。

Phase U-4 で fused GGUF は eval -16.7% 回帰のため却下済。spec ckpt (U-1-ext) も本環境で禁忌確定済。したがって「ctx 延伸で使える安定構成を確保すること」自体が次 Phase U-6 (長文脈 eval/prompt ベンチ) の前提となる。

Phase U-5 は dry-probe (起動 → /health → warm probe 10 tok → SIGTERM) で OT × ctx × tensor-split の fit/OOM を 2D 表化する読み取り専用スイープ。実 eval 性能は U-6 で別途測定する。

## 成功条件

- ctx=131072 で fit する (OT, -ts) 構成が **1 つ以上特定できること**
- 128k 全滅の場合、ctx=98304 (96k) の fit 構成を最終候補として提示
- Phase U-6 で使う候補 2-3 個の提示 (推奨順位付き)

## 実装範囲

### 固定パラメータ (baseline 構成踏襲)

- モデル: `/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf`
- llama.cpp: `6217b4958` (`~/llama.cpp/build/bin/llama-server`、U-1 ビルド済)
- 起動: `numactl --cpunodebind=1 --membind=1`
- llama-server: `-ngl 999 -b 256 -ub 256 --flash-attn 1 --poll 0 --parallel 1 --threads 40 --cache-type-k q8_0 --cache-type-v q8_0 --split-mode layer`
- EXTRA_ARGS: 空 (spec ckpt/fused 無し)

### OT Regex (CPU 層オフロード)

| Tag | Regex | CPU 層集合 | 層数 |
|-----|-------|-----------|------|
| B14b | `blk\.([2-3]\|2[0-3]\|3[1-8])\.ffn_.*_exps\.weight=CPU` | {2,3, 20-23, 31-38} | 14 |
| B16 | `blk\.([2-3]\|2[0-4]\|3[0-8])\.ffn_.*_exps\.weight=CPU` | {2,3, 20-24, 30-38} | 16 |
| B18 | `blk\.([0-3]\|2[0-4]\|3[1-9])\.ffn_.*_exps\.weight=CPU` | {0-3, 20-24, 31-39} | 18 |
| B20 | `blk\.([0-3]\|19\|2[0-4]\|3[0-9])\.ffn_.*_exps\.weight=CPU` | {0-3, 19, 20-24, 30-39} | 20 |
| B24 | `blk\.([0-4]\|1[6-9]\|2[0-4]\|3[0-9])\.ffn_.*_exps\.weight=CPU` | {0-4, 16-19, 20-24, 30-39} | 24 |

- B14b / B18 は既存 regex 再利用 (U-1-ext `batch_phaseU1ext_B.sh` L19 準拠)
- B16 / B20 / B24 は本 Phase で新規定義。既存 CPU 層クラスタの隣接追加で層数を段階的に拡張 (mmap 連続性維持)
- 各条件起動前に **Python assert で層数を検算** (regex 取り違え検出)

### Sweep Grid (Tier-1 21 条件、~2.5 時間)

| # | OT | ctx | -ts | 目的 |
|---|-----|-----|-----|------|
| T1-01 | B14b | 32768 | 11,12,13,14 | baseline 再現 sanity |
| T1-02 | B14b | 65536 | 11,12,13,14 | 中間 |
| T1-03 | B14b | 98304 | 11,12,13,14 | 96k fit 下限 |
| T1-04 | B14b | 131072 | 11,12,13,14 | **本命**: B14 で 128k fit 最優先 |
| T1-05 | B16 | 65536 | 11,12,13,14 | |
| T1-06 | B16 | 98304 | 11,12,13,14 | |
| T1-07 | B16 | 131072 | 11,12,13,14 | |
| T1-08 | B18 | 32768 | 11,14,14,11 | U-1-ext 実測再現 |
| T1-09 | B18 | 65536 | 11,12,13,14 | |
| T1-10 | B18 | 98304 | 11,12,13,14 | |
| T1-11 | B18 | 131072 | 11,12,13,14 | |
| T1-12 | B20 | 65536 | 11,12,13,14 | |
| T1-13 | B20 | 98304 | 11,12,13,14 | |
| T1-14 | B20 | 131072 | 11,12,13,14 | |
| T1-15 | B24 | 98304 | 11,12,13,14 | |
| T1-16 | B24 | 131072 | 11,12,13,14 | 保険 (大幅 offload で確実 fit) |
| T1-17 | B14b | 131072 | 11,14,14,11 | ts 探索: GPU1/2 厚く |
| T1-18 | B18 | 131072 | 11,14,14,11 | ts 探索 |
| T1-19 | B20 | 131072 | 11,14,14,11 | ts 探索 |
| T1-20 | B14b | 131072 | (default/均等) | ts 探索: default |
| T1-21 | B18 | 131072 | 12,14,14,10 | ts 探索: GPU1/2 重く GPU3 軽く |

時間見積: 21 条件 × ~7 分 = **~2.5 時間** (P100 × 122B Q4_K_M ~66 GB のモデルロード 4-5 分が主)。2 条件目以降は OS page cache で短縮期待。

### Dry-probe タイミング仕様

1. `.claude/skills/llama-server/scripts/stop.sh` → sleep 5
2. `start_phaseU5.sh` 起動 (env で OT/ctx/ts 注入、nohup、ssh t120h-p100 経由)
3. /health polling: 5 秒 × 最大 60 回 (**300 秒タイムアウト**)。途中で OOM regex ヒットすれば即 abort
4. /health OK → sleep 10 (KV prealloc / compute buffer reserve 完了待機)
5. **nvidia-smi 1 回目** (`--query-gpu=index,memory.free --format=csv,noheader,nounits` を GPU 0-3 で取得) → `*_free_static_MiB` 列
6. **warm probe**: `curl -s -m 30 http://10.1.4.14:8000/completions` に `{"prompt":"Hello","max_tokens":5}` を 1 回送信
7. **nvidia-smi 2 回目** → `*_free_after_probe_MiB` 列 (compute buffer 実行時膨張検出)
8. `stop.sh` → sleep 5 → 次条件

### エラー分類

| class | 判定条件 |
|-------|---------|
| OK | /health OK AND warm probe HTTP 200 |
| OOM_STARTUP | /health OK 前に OOM regex (`cudaMalloc failed: out of memory\|failed to allocate CUDA[0-9] buffer\|graph_reserve: failed to allocate\|failed to allocate KV\|CUDA error: out of memory`) ヒット |
| TIMEOUT | 300 秒 /health 未達 (OOM regex 無し) |
| OOM_PROBE | warm probe HTTP 失敗 or CUDA error |
| PARAM_REJECT | llama.cpp が ts/ot を拒否 (exit 3) |

fit 判定: `fit=1` if OK、それ以外は `fit=0`

## 実装ファイル

添付ディレクトリ: `report/attachment/<yyyymmdd_hhmmss>_qwen3-122b-u5-ctx128k-fit-map/`

| File | 役割 | 既存流用元 |
|------|------|-----------|
| `start_phaseU5.sh` | llama-server 起動 (OT/ctx/ts env 経由、EXTRA_ARGS 空) | `start_phaseU1ext.sh` (ctx/ts/ot パラメータ化) |
| `batch_phaseU5.sh` | CONDITIONS 21 条件ループ、probe → CSV | `batch_phaseU1ext_B.sh` + `batch_S3onwards.sh` の CONDS 配列パターン |
| `run_all_phaseU5.sh` | ロック取得 → batch 呼び出し → 解放 | U-1 `run_all_phaseU1.sh` |
| `probe_vram.sh` | ssh nvidia-smi + warm probe + CSV 1 行 emit | 新規 (既存 measure_phaseI.sh の snap_extras パターン参考) |
| `analyze_phaseU5.py` | CSV → heatmap PNG 3-4 枚 + summary.md | `plot_phaseT4.py` (NaN マスク + imshow) |
| `phaseU5_results.csv` | 全条件の結果 | — |
| `startup_logs/` | 各条件の startup log + nvidia-smi 2 回分 | — |

### CSV スキーマ (`phaseU5_results.csv`)

```
condition_id, OT_name, CPU_layers, ctx, ts, fit, startup_sec,
GPU0_free_static_MiB, GPU1_free_static_MiB, GPU2_free_static_MiB, GPU3_free_static_MiB, min_GPU_free_static_MiB,
GPU0_free_after_probe_MiB, GPU1_free_after_probe_MiB, GPU2_free_after_probe_MiB, GPU3_free_after_probe_MiB, min_GPU_free_after_probe_MiB,
error_class, error_msg
```

### PNG ヒートマップ (ts 別 3-4 枚)

- 1 枚 = 1 ts 値 (`11,12,13,14` / `11,14,14,11` / `default` / `12,14,14,10` など、条件があるもののみ生成)
- x 軸: ctx (32768, 65536, 98304, 131072)
- y 軸: OT (B14b, B16, B18, B20, B24、CPU 層数昇順)
- セル色: fit 時 `min_GPU_free_after_probe_MiB` (colormap `YlGn`、vmin=0 vmax=6000)、OOM 時灰色
- アノテーション: fit は `"{min_free} MiB"`、OOM は `"OOM-{class}"`
- 出力例: `phaseU5_heatmap_ts11-12-13-14.png` / `phaseU5_heatmap_ts11-14-14-11.png` / `phaseU5_heatmap_ts_default.png`
- レポート「核心発見サマリ」冒頭に PNG 埋め込み必須

### 推奨度評価基準 (Phase U-6 候補選定)

`score = (OT_name=="B14b" ? 1000 : 0) + min_GPU_free_after_probe_MiB − (ts 非標準なら 100)`

- (a) B14b boost: U-2 で eval 18.750 t/s (baseline 最良) 実績ありのため Phase U-6 での実測期待値最高
- (b) min_free 大 = KV/compute buffer のヘッドルーム、spec ckpt/cache-ram 再試行余地
- (c) ts=default or "11,12,13,14" 優先 (非対称 ts は Phase T 知見で eval 不利側)
- ctx=128k fit 複数 → score 降順上位 2-3 個を U-6 候補として抽出
- ctx=128k 全滅 → 同基準で ctx=98k に fallback、レポートに明記

## Critical Files (参照/流用)

- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-23_171459_qwen3-122b-u1ext-specckpt-relaxed/start_phaseU1ext.sh`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-23_171459_qwen3-122b-u1ext-specckpt-relaxed/batch_phaseU1ext_B.sh`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-23_171459_qwen3-122b-u1ext-specckpt-relaxed/batch_phaseU1ext_A_smoke.sh`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-19_120715_qwen3-122b-c3-phaseS-ub-ctx-2d/batch_S3onwards.sh` (CONDS 配列パターン)
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/lock.sh`, `unlock.sh`
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/start.sh`, `stop.sh`
- `/home/ubuntu/projects/llm-server-ops/REPORT.md` (タイトル 50 字以内、核心発見サマリ冒頭に PNG 埋め込み、「未検証事項」「検証完了後に実施すべき TODO」必須)

## 検証方法 (end-to-end)

1. ロック取得: `.claude/skills/gpu-server/scripts/lock.sh t120h-p100 phaseU5`
2. 事前検算 (Python): 各 OT regex の CPU 層数が Tag 宣言と一致することを assert
3. `run_all_phaseU5.sh` 実行 → `phaseU5_results.csv` に 21 行 append
4. 進行中 Discord 通知 (中間経過、完了時): `.claude/skills/discord-notify/` 経由
5. 完了後 `analyze_phaseU5.py` 実行 → 3-4 枚 PNG + summary.md 生成
6. レポート `report/<yyyy-mm-dd_hhmmss>_phase-u-5-ctx128k-fit-map.md` 作成 (REPORT.md 規則準拠)
7. ロック解放

## 未検証事項 (本 Phase では扱わない)

- fit 構成の実 eval 性能 (eval_tps, prompt_tps) — **Phase U-6 で測定**
- ctx=128k で実プロンプト (10k-100k 入力) 処理時の compute buffer 再膨張挙動 (warm probe は 1 トーク級のため不十分)
- KV=f16 (q8_0 より大容量) での fit 境界 (今回は q8_0 固定)
- 5 OT tag 以外 (B12 軽 offload、B22/B28 中間点) の fit 特性

## 検証完了後 TODO

- Phase U-6: 推奨 2-3 候補で eval (code/math/ja 3 タスク × 5 run)、prompt 処理 (1k/8k/32k/128k)、cross-session 安定性 (U-2 同基準)
- B20/B24 の層数検算スクリプトを `.claude/skills/llama-server/scripts/` 配下に恒久化 (他 Phase 再利用のため)
- KV=f16 fit 探索 (ctx=128k / B14b で fit しないケースのフォールバック)
- プロセス並列 (`--parallel 2-4`) 時の VRAM 追加余地確認 (dry-probe 結果を利用して Phase U-7 以降で検討)
- 長文脈 prompt (32k/64k/128k 入力) 実走 compute buffer プロファイル (Phase I longcontext の dmon stream 利用)
