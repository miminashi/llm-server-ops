# Phase S-eval-cross-session: セッション間 eval 性能ゆらぎの定量化

## Context

直前 Phase S-eval（2026-04-20 00:32-01:13 JST、`report/2026-04-20_003250_qwen3-122b-c3-phaseSeval.md`）で
ub ∈ {1584, 1586, 1664} × (warmup 2 + eval 5 run) を実施した結果、

- σ（run 間）= 0.005–0.008 t/s と極小
- しかし 1-run 参照値との乖離は −0.087〜−0.805 t/s と σ の 18–160 倍
- "セッション間ゆらぎ" が支配的ノイズ源として浮上（★最優先 未検証事項）

直前レポートの★最優先 TODO「Phase S-eval-cross-session 候補」を実施する。
**同一スクリプトを別セッションで再実行**し、5-run mean のセッション間変動を定量化する。

### 目的

1. 前 Phase 5-run mean が「真の性能」か「本セッション限定の mean」かを判定
2. σ_session（セッション間標準偏差）の実測
3. ピーク ub 順序（ub=1584 > 1586 > 1664）のセッション間安定性
4. 過去 1-run 参照値（ub=1586: 15.466, ub=1664: 15.451）が別セッションで再現するか検証

### 判定しきい値

| セッション間 Δmean | 判定 |
|---|---|
| ≤ 0.02 t/s | **session_independent**（セッション独立、run 間 σ が支配） |
| 0.02–0.10 t/s | **partial_session_drift**（軽度セッションゆらぎ） |
| > 0.10 t/s | **session_dominated**（セッション間ゆらぎが支配、単一セッション mean は不十分） |

## 実装手順

1. **GPU ロック取得**
   ```
   bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
   ```

2. **新規出力ディレクトリ作成とスクリプトコピー**
   新レポート名: `<yyyy-mm-dd_hhmmss>_qwen3-122b-c3-phaseSevalcross.md`
   （`date +%Y-%m-%d_%H%M%S` で実タイムスタンプ取得）
   - `report/attachment/<新名>/` を作成
   - 前 Phase の `start_phaseSeval.sh` / `batch_phaseSeval.sh` / `run_all.sh` / `measure_phaseI.sh` / `analyze_phaseSeval.py` / `prompts/prompt_1k.txt` をコピー
   - `batch_phaseSeval.sh` の出力ディレクトリ prefix を `out_Seval_` → `out_Sevalcross_` に変更（衝突回避）
   - 分析スクリプトを拡張（前 Phase TSV 読み込み + session 間 diff/Welch t）

3. **バッチ実行（所要 37-40 分）**
   ```
   cd report/attachment/<新名>/
   bash batch_phaseSeval.sh > batch_phaseSevalcross.log 2>&1
   ```

4. **分析**
   ```
   python3 analyze_phaseSevalcross.py
   ```
   前 Phase TSV (`../2026-04-20_003250_qwen3-122b-c3-phaseSeval/summary_phaseSeval.tsv`) と
   本 Phase TSV を突合し、ub ごとに mean 差・Welch t・verdict を生成。

5. **サーバ停止・ロック解放**
   ```
   bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
   bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
   ```

6. **レポート作成**（必須、REPORT.md 準拠）

## 参照ファイル

### 再利用するスクリプト（前 Phase から流用）
- `report/attachment/2026-04-20_003250_qwen3-122b-c3-phaseSeval/start_phaseSeval.sh`
- `report/attachment/2026-04-20_003250_qwen3-122b-c3-phaseSeval/batch_phaseSeval.sh`
- `report/attachment/2026-04-20_003250_qwen3-122b-c3-phaseSeval/run_all.sh`
- `report/attachment/2026-04-20_003250_qwen3-122b-c3-phaseSeval/measure_phaseI.sh`
- `report/attachment/2026-04-20_003250_qwen3-122b-c3-phaseSeval/analyze_phaseSeval.py`（拡張ベース）
- `report/attachment/2026-04-20_003250_qwen3-122b-c3-phaseSeval/prompts/prompt_1k.txt`（1083 tokens, 6200 bytes）

### 前 Phase 基準値（比較対象）
| ub | 前 Phase 5-run mean | σ | 1-run 参照値 |
|---|---|---|---|
| 1584 | 15.206 | 0.005 | 15.293 (Sbfine2) |
| 1586 | 15.188 | 0.008 | 15.466 (Sbfine3) |
| 1664 | 14.646 | 0.005 | 15.451 (Sb-fine) |

### 環境（前 Phase と完全同一）
- GPU: t120h-p100 (10.1.4.14), Tesla P100-PCIE-16GB × 4
- llama.cpp: `~/llama.cpp/build/bin/llama-server`
- Model: `Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf`
- fa=1, f16/f16 KV, ctx=32768, numactl NUMA1, threads=40, poll=0, ngl=999
- OT_REGEX: `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
- cooldown: 60s, max_tokens=256

## Verification

- [ ] 3 条件すべて起動成功
- [ ] 各 ub で eval 5 run の `eval_tps` を取得、σ が前 Phase 同等 (0.005-0.01) であることを確認
- [ ] 前 Phase mean との Δmean を ub 別に算出
- [ ] Welch t-test で session 間有意差判定（|t|>2 で significant）
- [ ] session verdict 判定（independent / partial_drift / session_dominated）
- [ ] ピーク ub 順序のセッション間安定性確認
- [ ] 1-run 参照値の再現性再確認（前 Phase と同様 reject 継続か）
- [ ] GPU ロック取得・解放の正常動作

## レポート（必須）

レポートパス: `report/<yyyy-mm-dd_hhmmss>_qwen3-122b-c3-phaseSevalcross.md`

必須セクション:
- 実施日時 / 作業種別 / GPU ロック
- 添付ファイル / 参照
- 前提・目的（直前 Phase S-eval の要約と cross-session 動機）
- 環境情報
- 再現方法
- 実行結果サマリ（5-run ピボット、session 間 diff、Welch t、verdict、1-run ref 再現性）
- 再現性分析と解釈
- 採用判定
- **未検証事項**（直前レポートから継承、本 Phase で潰したものは [x]、新規発生は追記）
- **検証完了後に実施すべき TODO**（直前レポートから継承 + 更新）
- 補足

## 所要時間見積もり

- 準備（ロック、スクリプトコピー、微修正）: 5-8 分
- バッチ実行: 37-40 分
- 分析とレポート作成: 15-20 分
- **合計: 60-70 分**

## リスクと緩和

- **GPU ロック競合**: 現時点で t120h-p100 は available、取得失敗時は待機か t120h-m10 検討 → 本 Phase は p100 専用（前 Phase との直接比較のため）
- **起動失敗（ub=1584 等での OOM）**: 前 Phase で同条件起動済み実績あり、確率低
- **所要時間超過**: cooldown 60s 固定で予測可能、37-40 分のバッチ実行中は他作業可
