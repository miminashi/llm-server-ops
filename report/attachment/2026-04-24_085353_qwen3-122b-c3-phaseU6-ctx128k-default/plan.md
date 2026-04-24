# Phase U-6: ctx=128k 起動 default 構成確定ベンチ

## Context

直前 Phase U-5 で ctx=131072 (128k) に fit する 9 構成を特定し、推奨 3 構成を順位付けた。Phase U-6 は、この 3 構成の中から **起動スクリプトの default として採用すべき構成** (OT / ts / ub / ctx) を eval_tps (TG) と prompt_tps (PP) の実測で確定することを目的とする。

- 歴代 baseline: `B14b_ts_alt @ ctx=32k` で **eval_tps = 18.664 t/s**
- 推奨 3 構成 (全て ts=11,12,13,14, ctx=131072):
  - **T1-04 / B14b**: CPU層=14, GPU3 残 956 MiB (本命、VRAM 最狭)
  - **T1-11 / B18**: CPU層=18, GPU3 残 1682 MiB (フォールバック)
  - **T1-14 / B20**: CPU層=20, GPU3 残 2348 MiB (保守枠)
- 過去 Phase T-5f で ctx=32k の ub 最適 = 512 (eval 16.455 t/s)。ctx=128k での再最適化が未検証
- 長文脈 prompt (32k/96k) 処理時の compute buffer 再膨張による OOM が懸念 (B14b)

本 Phase の成果物: ctx=128k 運用下での default 構成決定、baseline 比 eval 回帰率、prompt ingestion 時間の実測値、未検証 TODO。

---

## 測定行列 (傾斜採択)

本命 B14b を徹底し、B18/B20 は代表点のみ。総 105 run、見積 2.2-2.4 時間。

| 構成 | ub 点 | prompt 点 | セル数 | run 数 |
|------|------|----------|-------|-------|
| **B14b** (本命) | {256, 512, 1024} | {1k, 32k, 96k} | 9 | 63 (9×7) |
| **B18** | {256, 512} | {1k, 32k} | 4 | 28 (4×7) |
| **B20** | {512} | {1k, 32k} | 2 | 14 (2×7) |
| **合計** | | | 15 | **105** |

- 各セル: warmup 2 + eval 5 = 7 run
- prompt_96k は B14b のみ (OOM リスク検知 + PP 長尺軸を本命で完結)
- ub=1024 は B14b のみ (長文脈で最適点が動く仮説の最短検証)

**固定パラメータ**: unsloth GGUF `Qwen3-122B-A10B-128K-Instruct-UD-Q4_K_XL` / llama.cpp commit `6217b4958` / threads 40 / KV cache q8_0 / flash-attn 1 / parallel 1 / poll 0 / split-mode layer / temp 0.6 / top-p 0.95 / top-k 20

**prompt 仕様**:
- prompt_1k: 約 1070 tokens, n_predict=1024 (TG 評価主体)
- prompt_32k: 約 32100 tokens, n_predict=512 (中段 PP 評価)
- prompt_96k: 約 96000 tokens, n_predict=256 (長尺 PP 評価)
- ctx=131072 − n_predict(256) − chat_template(~40) に対し 5k margin を確保

---

## OOM リスク対処フロー

B14b は GPU3 残 956 MiB と狭く、長 prompt の compute buffer 膨張で OOM の可能性がある。

1. **各構成の初回は prompt_96k を先行実行**（構成不適合の早期検知）
2. stdout から OOM regex (`cudaMalloc failed|failed to allocate CUDA[0-9] buffer|graph_reserve`) を監視
3. 96k warmup で OOM → 当該構成の 96k セルのみ SKIP、`error_class=OOM_96K` を CSV に記録
4. 32k warmup で OOM → 当該構成全体を SKIP、次構成へ
5. `nvidia-smi --query-gpu=memory.free` を 1Hz で記録し、`min_GPU_free_MiB < 100` なら次 run 前に cooldown を 60s→120s に延長
6. OOM 検出時も batch は停止せず次条件へ進む (CSV に記録し後で確認)

---

## 実装ファイル構成

配置先: `report/attachment/2026-04-24_<HHMMSS>_qwen3-122b-c3-phaseU6-ctx128k-default/`

| File | 役割 | 流用元 |
|------|------|-------|
| `plan.md` | 本プラン | 新規 (この .md をコピー) |
| `start_phaseU6.sh` | llama-server 起動 (OT/ts/ub/ctx=131072) | U-5 `start_phaseU5.sh` を基に ub runtime 化 |
| `measure_phaseU6.sh` | 1 セル分 warmup 2 + eval 5、TTFT/VRAM peak 抽出 | Phase I `measure_phaseI.sh` |
| `batch_phaseU6.sh` | 構成 × ub × prompt ループ、warmup 96k 先行、OOM handler | U-5 batch + I run_all を統合 |
| `run_all_phaseU6.sh` | lock 取得 → batch 実行 → unlock → Discord 通知 | U-5 `run_all` |
| `prompts/generate_prompts.py` | 1k/32k/96k 生成 (既存 Phase I 版に 96k エントリ追加) | Phase I |
| `prompts/check_tokens.sh` | `/tokenize` API で実 token 数検証 | Phase I |
| `analyze_phaseU6.py` | CSV → pivot (構成×ub×prompt)、baseline 18.664 比較列、median/p90 | 新規 |
| `plot_phaseU6.py` | PNG1: eval_tps × ub × 構成、PNG2: prompt_tps × prompt_len × 構成 | T-5f `plot_phaseT5f.py` を流用 |
| `phaseU6_results.csv` | 列: cond_id, OT, ts, ub, prompt_tag, prompt_n, run_idx, role, eval_tps, prompt_tps, TTFT_ms, load_sec, min_gpu_free_MiB, error_class | 新規 |

### 主要スクリプト要点

- `start_phaseU6.sh`: `--flash-attn 1 --poll 0 --parallel 1 --cache-type-k q8_0 --cache-type-v q8_0 --split-mode layer --threads 40 --ctx-size 131072 --jinja --metrics --ubatch-size $UB -ot "$OT_REGEX" --tensor-split $TS --n-gpu-layers 999`
- `batch_phaseU6.sh`: 構成切替時に `stop.sh` → 次構成 `start_phaseU6.sh` → `/health` polling (max 300s) → measure 起動。cooldown 60s default、min_free<100 検知で 120s へ延長。
- `measure_phaseU6.sh`: `run_marker` unique 付与で prompt cache を無効化、`timings.prompt_ms`/`timings.predicted_ms` を JSON 抽出、dmon で peak VRAM 取得
- OT regex (既存):
  - B14b: `blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU`
  - B18:  `blk\.([0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU`
  - B20:  `blk\.([0-3]|19|2[0-4]|3[0-9])\.ffn_.*_exps\.weight=CPU`

---

## time budget 超過時の skip 順位

90 分経過時点で残り行列を再評価し、以下の順で削減:

1. cooldown 60s→30s (最軽)
2. **B20 全セル SKIP** (保守枠、B14b/B18 差分確保優先)
3. **ub=1024 × 96k SKIP** (B14b 本命の ub=512 × 96k が確定していれば撤退可)
4. **ub=256 全セル SKIP** (baseline 互換は T-5f で既知)
5. **B18 全セル SKIP**
6. 最低死守: **B14b × ub=512 × {1k, 32k, 96k} の 21 run** — default 確定の合格ライン

Discord 通知で 30/60/90 分地点の進捗を emit、skip 発動を人間可読で明記。

---

## 推奨 default 構成決定の判定基準

複合スコアで default を選定 (高い方を採用):

```
score = 0.50 * R_eval + 0.25 * R_prompt_32k + 0.15 * R_headroom + 0.10 * R_stability

R_eval       = eval_tps(1k) / 18.664         (baseline 回帰率)
R_prompt_32k = prompt_tps(32k) / max_obs     (構成間相対)
R_headroom   = min_GPU_free_MiB / 2500       (cap 1.0)
R_stability  = 1 - stdev(eval) / median(eval)
```

**採用優先順**:
1. R_eval ≥ 0.85 (baseline 15.86 t/s 以上) かつ全 run 完走 → default 候補
2. 候補中 score 1 位を default 推奨
3. B14b が R_eval ≥ 0.85 を満たさない場合のみ B18 を採用。B18 が 0.80 未満なら B20。全滅なら「ctx=98k に後退」を U-7 TODO に格上げ
4. ub は構成確定後に同スコアで最高値。T-5f 挙動から ub=512 が選ばれる見込み。ub=1024 が ≥2% 上回ればそちらへ

---

## レポート構成

配置先: `report/2026-04-24_<HHMMSS>_qwen3-122b-c3-phaseU6-ctx128k-default.md`
タイトル案: `Qwen3-122B Phase U-6: ctx=128k 起動 default 構成確定` (50 字以内)

### 必須セクション

1. 添付ファイル (plan.md, *.sh, *.py, *.csv, *.png, *.log)
2. **核心発見サマリ** — PNG 2 枚を冒頭埋め込み (eval_tps × ub × 構成、prompt_tps × prompt_len × 構成) + 推奨 default 構成の 1 行結論 + baseline 比較の数値
3. 前提・目的 (U-5 推奨 3 構成、baseline、目的観点)
4. 環境情報 (GPU/モデル/llama.cpp commit/固定パラメータ)
5. 再現方法 (lock→run_all→unlock)
6. 結果 (CSV 抜粋、構成別/ub 別/prompt 別 pivot、baseline 比較 %)
7. **ctx=128k 運用時の現実的な期待性能範囲** (eval_tps 中央値、PP 時間 @ 1k/32k/96k、起動時間、VRAM headroom)
8. **未検証事項** (次 Phase へ送る論点、下記)
9. **検証完了後に実施すべき TODO** (下記)

### 未検証事項 (U-7 以降へ送る)

- cross-session 安定性 (U-2 相当のセッション間 drift): 本 Phase は session 内のみ
- prompt cache hit 効果 (本 Phase は run_marker で無効化)
- multi-parallel (`--parallel 2+`) の VRAM 挙動と TG/PP 影響
- KV=f16 / f16+q8_0 mixed の fit 境界
- タスク種別 (code/math/ja) による eval_tps 差
- ub=128/768/2048 の中間点探索
- prompt 128k full (ctx 満杯) 運用時の挙動
- ctx=98k への fallback ベンチ (本 Phase で default が baseline 比 -30% 超劣化した場合)

### 検証完了後に実施すべき TODO

- 起動スクリプト (`.claude/skills/llama-server/scripts/start.sh` 配下) の default パラメータを決定した `OT / ts / ub / ctx` に更新する PR
- `user memory` の `project_t_series_roadmap.md` を U-6 完了で更新 (Cycle 87 として追記)
- ctx=98k 中間点の fit 構成を U-5 map から転用できる確認
- 本 Phase の結論を踏まえた Phase U-7 (session 跨ぎ安定性 or long-ctx real prompt) の計画

---

## Critical Files to Reference / Modify

### 参照元 (流用)

- `report/attachment/2026-04-24_081326_qwen3-122b-u5-ctx128k-fit-map/start_phaseU5.sh`
- `report/attachment/2026-04-24_081326_qwen3-122b-u5-ctx128k-fit-map/batch_phaseU5.sh`
- `report/attachment/2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext/measure_phaseI.sh`
- `report/attachment/2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext/generate_prompts.py`
- `report/attachment/2026-04-22_232010_qwen3-122b-c3-phaseT5f-ub-fine-sweep/plot_phaseT5f.py`
- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- `.claude/skills/llama-server/scripts/start.sh` (default 更新 PR の対象、本 Phase では参照のみ)

### 新規作成

- `report/attachment/<stamp>_qwen3-122b-c3-phaseU6-ctx128k-default/` 配下のスクリプト/解析/prompt/CSV/PNG 一式
- `report/<stamp>_qwen3-122b-c3-phaseU6-ctx128k-default.md`

---

## Verification

1. lock 取得: `.claude/skills/gpu-server/scripts/lock.sh t120h-p100 phaseU6`
2. prompt 生成と token 数検証: `generate_prompts.py && check_tokens.sh` → 1k/32k/96k の実 token 数が想定範囲
3. batch 実行: `run_all_phaseU6.sh` (backgroud 可、Discord 通知で進捗確認)
4. 途中確認: `tail -f` で log、OOM 発生時の SKIP フロー動作を確認
5. 完了後: `analyze_phaseU6.py` で CSV → pivot、`plot_phaseU6.py` で PNG 2 枚生成
6. レポート作成: 核心発見サマリへ PNG 埋め込み、ctx=32k baseline 18.664 との差分を数値で明記
7. unlock: `.claude/skills/gpu-server/scripts/unlock.sh t120h-p100`

所要見込: 2.2-2.4 時間 (完走)、90 分時点で進捗判断し skip 順位に従って削減。
