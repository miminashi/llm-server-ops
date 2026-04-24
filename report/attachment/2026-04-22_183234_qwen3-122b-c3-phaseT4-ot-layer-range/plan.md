# Phase T-4: OT pattern 層範囲スイープ

## Context

Qwen3.5-122B Q4_K_M の eval t/s 改善を狙う Phase T シリーズの第 4 弾。
これまで:
- Phase D (2026-04-16): 15.03 t/s (threads=40, ub=1586, ctx=32k)
- Phase S (2026-04-19): **15.39 t/s** 歴代最高 (ctx=65k, ub=512)
- Phase T-1 (KV 量子化): 最良 q8_0 で 15.016 (Phase D 未達)
- Phase T-2 (split-mode): row -15〜-22% 劣化、layer 維持 (最良 14.672)
- Phase T-3 (threads 中間値): 最良 threads=32 で 14.860 (+0.53% vs 40)、Phase D 未達。
  **副次発見: threads=36 で非単調 drop (-2.08%)**。CPU offload 層数 36 と一致

T-3 の核心仮説 = 「OT pattern でマッチする CPU offload 層数と threads 数が一致すると OpenMP schedule(static, 1) 的状況で MoE expert routing の非一様性が drop を起こす」

**Phase T-4 で OT pattern の CPU 層数を {32, 36(現行), 40} に変えて threads={32, 40} と組合せ、仮説を direct test し同時に絶対最良 t/s 更新を狙う。再ビルド不要 (T-5 ビルドフラグより低コスト・高情報量)。**

## アプローチ

Phase T-3 の attachment を複製し OT_REGEX を環境変数化、3 OT × 2 threads = 6 条件をスイープ。

### スイープ条件

| ID | OT_REGEX | CPU 層数 | 14-19 | 44-47 | threads | 仮説判定での役割 |
|----|----------|---------|-------|-------|---------|-----------------|
| **A36** | `blk\.([0-9]\|1[0-3]\|2[0-4]\|3[1-9]\|4[0-7])\.ffn_.*_exps\.weight=CPU` | 36 | GPU | CPU | 32, 40 | T-3 baseline 再現 (36 ∉ {32,40} は control) |
| **B32** | `blk\.([0-9]\|1[0-3]\|2[0-4]\|3[1-9]\|4[0-3])\.ffn_.*_exps\.weight=CPU` | 32 | GPU | **GPU 戻し** | 32, 40 | threads=32 で drop → 仮説支持 |
| **C40** | `blk\.([0-9]\|1[0-7]\|2[0-4]\|3[1-9]\|4[0-7])\.ffn_.*_exps\.weight=CPU` | 40 | **14-17 CPU 追加** | CPU | 32, 40 | threads=40 で drop → 仮説支持 (dry-start で当初の 1[0-9] だと 42 層となったため修正) |

**実行順**: A36-t40 → A36-t32 → C40-t40 → C40-t32 → B32-t40 → B32-t32 (B は VRAM リスクあり最後)

### VRAM リスク

- T-3 startup log: CUDA1/CUDA2 free 5832 MiB
- B32 で +1 expert 層/GPU ≈ +1500-1800 MiB → **ボーダーライン、必ず dry-start で OOM 確認**
- C40 は CPU 寄せで VRAM 余裕方向 (安全)

### 固定パラメータ (T-3 と同一)

`numactl -N1 -m1 -- llama-server --split-mode layer --flash-attn 1 --poll 0 -b 1586 -ub 1586 --ctx-size 32768 --cache-type-k q8_0 --cache-type-v q8_0 --parallel 1 -ngl 999 --jinja`

## 修正対象ファイル

複製元: `report/attachment/2026-04-22_181614_qwen3-122b-c3-phaseT3-threads/`
作成先: `report/attachment/{TIMESTAMP}_qwen3-122b-c3-phaseT4-ot-layer-range/`

| ファイル | 操作 | 主要 diff |
|---------|------|----------|
| `start_phaseT4.sh` | 新規 (T-3 base) | L19: `OT_REGEX` をハードコード→`${OT_REGEX:?required}`。L15 に `OT_TAG=${OT_TAG:-A36}`、L24 REMOTE_LOG ファイル名に `${OT_TAG}` 追加 |
| `batch_phaseT4.sh` | 新規 (T-3 base) | `THREADS_LIST` → `CONDITIONS=("OT_TAG\|THREADS\|OT_REGEX" × 6)` に置換。`IFS='\|' read` で分解、`OT_TAG` `OT_REGEX` を export して `start_phaseT4.sh` に渡す。`TAG_COND` に OT_TAG 含める。startup log 取得パスも `${OT_TAG}` 含める形式に |
| `measure_phaseT4.sh` | T-3 から cp | コメント `phaseT3` → `phaseT4` のみ (本体無変更で動く) |
| `run_all.sh` | T-3 から cp | L33: `measure_phaseT3.sh` → `measure_phaseT4.sh` |
| `analyze_phaseT4.py` | 新規 (T-3 base) | `THREADS_LIST` → `CONDITIONS=[(OT,THR)]` の 6 タプル。`OT_TAGS=["B32","A36","C40"]` (層数昇順)、`OT_LAYER_COUNT={...}`。`collect(thr)` → `collect(ot, thr)`、tag_cond に `${ot}_` prefix。pivot を OT × threads マトリクス化、「層数=threads drop 仮説」判定セクションを追加。`PEAK_PHASE_T3_BEST=14.860`, `PEAK_PHASE_T3_T40=14.781` を追加 |
| `plot_phaseT4.py` | 新規 (T-3 base) | x 軸を CPU 層数 (32/36/40) に、threads={32,40} を 2 本の折れ線で重ね描き。axhline で Phase D/S/T-1/T-2/T-3 best 5 本。heatmap 追加 |
| `prompts/prompt_1k.txt` | T-3 から cp | 無変更 |
| `plan.md` | この計画ファイルを cp | レポート添付用 |

## 既存ユーティリティの再利用

- `.claude/skills/gpu-server/scripts/lock.sh t120h-p100` / `unlock.sh t120h-p100`
- `.claude/skills/llama-server/scripts/stop.sh t120h-p100`
- T-3 の `measure_phaseT3.sh` の jq payload 構築 / curl invocation / nvidia-smi dmon バックグラウンドロジックは無変更で再利用 (tag を渡すだけで動作)
- T-3 の `run_all.sh` の warmup/eval 二段階構成も流用 (WARMUP_RUNS=2, EVAL_RUNS=5)
- analyze_phaseT3.py の `stats()` / `verdict()` / `fmt_cell()` 関数は流用

## 実行フロー

```
1. mkdir 添付ディレクトリ + cp 共通ファイル
2. 新規 4 ファイル (start/batch/analyze/plot) 作成
3. lock.sh t120h-p100
4. dry-start (B32-t40) で VRAM 確認:
   - load_tensors の CUDA buffer 値、cudaMalloc failed の有無
   - 1 リクエスト curl で inference 動作確認
   - OOM なら CONDITIONS から B32 削除 (4 条件で続行)
5. stop.sh t120h-p100
6. nohup bash batch_phaseT4.sh > batch_phaseT4.log 2>&1 & (約 100-130 分)
7. 完了後 unlock.sh t120h-p100
8. python3 analyze_phaseT4.py / plot_phaseT4.py
9. レポート作成 (REPORT.md ルール準拠、タイトル「Phase T-4: OT pattern 層範囲スイープ」)
10. discord-notify でレポート URL 通知
```

## 仮説判定基準 (4 段階)

| 観測 | 判定 |
|------|------|
| B32-t32 と C40-t40 両方で「層数=threads」が他方より -1% 以上 drop | **STRONG SUPPORT** |
| 片方のみ drop | **PARTIAL SUPPORT** (構造要因が他にもある) |
| 両方 drop < 1% | **REJECT** (T-3 の 36 drop は別要因) |
| match が other より +1% 以上 高い | **INVERSE** (むしろ層数=threads が最適) |

絶対値判定: > 15.39 = Phase S 越え (歴代更新) / > 15.03 = Phase D 越え / > 14.860 = T-3 最良越え / ≤ 14.781 = 改善なし

## Verification (実行後検証)

```bash
# (a) 6 条件 × (warmup 2 + eval 5) = 42 個の eval_runN.json 存在確認
find out_T4_*_warmup out_T4_*_1k -name 'eval_run*.json' | wc -l   # = 42 期待

# (b) 全 JSON が timings.predicted_per_second 持つか
for f in out_T4_*/eval_run*.json; do
  jq -e '.timings.predicted_per_second' "$f" > /dev/null || echo "BAD: $f"
done

# (c) cmdline.txt の OT regex が条件 tag と一致 (cross-check)
for d in out_T4_*_warmup; do
  grep -o 'blk[^ ]*ffn_[^ ]*' "$d/cmdline.txt" | head -1
done

# (d) startup_logs から GPU 配置 (load_tensors: CUDA[0-3] model buffer) を抽出し、
#     A36 ≈ T-3 と一致 / C40 で CUDA1/2 が約 1800 MiB 減 / B32 で約 1800 MiB 増 を確認

# (e) eval_tps stdev が T-3 と同水準 (≤ 0.05 t/s) か
python3 analyze_phaseT4.py | grep -A 1 "stdev"

# (f) Phase D/S/T-1/T-2/T-3 全比較表が pivot.md に出力されているか
```

## 失敗時フォールバック

| 失敗モード | 対応 |
|-----------|------|
| dry-start で B32 OOM | CONDITIONS から B32 削除、4 条件で続行。レポートに B 不可と明記、TODO に「ub=512 / split=tensor で再試行」追加 |
| 本番中 health timeout (OOM) | batch ループの continue で自動 skip、analyze で no_data 表示 |
| eval curl エラー (timeout) | 該当 run のみ no_data、他 run で stats 算出 |
| batch 全体中断 | `CONDITIONS` を残条件のみに絞った resume 版で再実行 (既消化分の出力は tag unique で保持) |
| A36-t40 が T-3 14.781 と乖離 (±1% 超) | 絶対値判定は session drift 注意で記載。T-4 内 vs 比は依然有効 |

## レポート章構成

タイトル: `Phase T-4: OT pattern 層範囲スイープ` (29 字)
パス: `report/{TIMESTAMP}_qwen3-122b-c3-phaseT4-ot-layer-range.md`

1. 添付ファイル
2. **核心発見サマリ** (PNG `phaseT4_eval_tps.png` + `phaseT4_heatmap.png` 埋め込み + 観点別表)
3. 前提・目的 (背景 / 目的 / 選定理由 / 判定基準)
4. 環境情報
5. 再現方法
6. **VRAM 事前確認結果** (dry-start log 抽出 + B32 採否)
7. pivot 比較表 (OT × threads マトリクス + **Phase D/S/T-1/T-2/T-3 全比較表**)
8. 条件別詳細 (GPU 配置 / 仮説判定詳細 / run 間安定性 / 出力品質)
9. **未検証事項**
10. **検証完了後に実施すべき TODO** (短期 = T-5 ビルドフラグ準備 / 中期 = Phase S 条件で再現 / 長期 = SMT ON 等)
11. 参照レポート (Phase D / S / T-1 / T-2 / T-3 へリンク)

## 推定所要時間

- 添付準備 + スクリプト作成: 15 分
- lock + dry-start: 10 分
- 本番 batch (6 条件 × 約 18 分): 100-130 分
- analyze + plot: 5 分
- レポート作成: 30 分
- **合計: 約 160-190 分**
