# 重要知見まとめ

レポート群から特に重要な知見を抜粋（各 1〜2 行、出典レポート付き）。

> **検証ステータス（2026-06-13）**: 全項目の出典・主要数値をレポート本文と突合済み。
> その際に旧版の **18番・26番・29番** に誤りが見つかり修正した（詳細は各項目）。
> 数値は該当レポート本文に基づく（INDEX 由来の二次情報からの格上げ済み）。

## 基盤・配置

1. **C-3 構成が最速** — layer 14-19 + 25-30 を GPU 復帰させる配置で 12.19 t/s（中央値、C-1 比 +2.8%）。
    出典: `2026-04-16_053225_qwen3-122b-c3-layer30-swap.md`（本文で 12.19 t/s 確認済み）
2. **VRAM マージン不足は起動不能に直結** — C-2/C-2' は追加層を載せたがマージン不足で不採用。
    出典: `2026-04-16_051249_qwen3-122b-c2-cuda2-expansion.md`

## ボトルネック・環境

3. **律速は GPU ではなく CPU** — GPU SM 使用率 4-5%、Xeon の MoE 演算が律速。
    出典: `2026-04-16_054649_qwen3-122b-c3-eval-bottleneck-profile.md`
4. **NUMA リモートアクセスが致命的** — `numactl -N1 -m1` でリモートアクセス 97% 削減・+4.3%。
    出典: `2026-04-16_062447_qwen3-122b-c3-bottleneck-deepdive.md`
5. **interleave=all が最良の NUMA 配置** — スレッド固定比 +60.7%。
    出典: `2026-04-16_072324_qwen3-122b-c3-numa-phaseC.md`
6. **通常稼働では速度劣化しない** — 60分稼働で劣化ゼロ。劣化は idle 後の古プロセス等の特殊条件限定。
    出典: `2026-04-17_035831_qwen3-122b-c3-phaseG-longevity.md`
7. **`--poll 50` は逆効果** — idle 劣化を防げず、ベース速度を -2.2% 下げるだけ。
    出典: `2026-04-17_082738_qwen3-122b-c3-phaseH-idle-poll.md`

## FlashAttention / KV量子化

8. **P100 では fa=1 が機能要件** — fa=0 は q8_0 KV と非互換で Segfault、f16 KV でも OOM。速度目的でなく必須。
    出典: `2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab.md`（Segfault）、`2026-04-18_025221_qwen3-122b-c3-phaseK-f16-flashattn-ab.md`（f16 OOM）
9. **fa=1 の効果を分離定量化** — VRAM -4.8GB かつ eval +3%。
    出典: `2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan.md`
10. **compute buffer のスケーリング機構** — fa=1 で ctx に対し O(n²)→O(n) に変化。
    出典: `2026-04-19_024430_qwen3-122b-c3-phaseN-ctx8k-boundary.md`
11. **KV量子化は q8_0 が最適** — q4_0 より速度・品質とも優位。
    出典: `2026-04-22_141232_qwen3-122b-c3-phaseT1-kv-quant.md`

## batch / ubatch

12. **真のドライバは `-b` でなく `-ub`** — ub=2048 で VRAM 73%削減 + eval +1.5% のダブルウィン。
    出典: `2026-04-19_051604_qwen3-122b-c3-phaseP-fa1-batch-scan.md`
13. **eval 速度のピークは ub=2048** — ub=128 まで下限探索して確認。
    出典: `2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound.md`
14. **OOM 境界 ub*≈1585** — 1〜4 トークン精度で (1584,1600] を ub*≈1585 付近に確定。llama.cpp scheduler/ggml-alloc の動的計算値に由来。
    出典: `2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok.md`（値の確定、本文で ub*=1585 付近を確認）、`2026-04-19_192631_qwen3-122b-c3-phaseSbsrc-threshold-hunt.md` / `2026-04-19_203607_qwen3-122b-c3-phaseSb-alloc.md`（機構の解明）
15. **slope は ctx 依存（cross 項あり）** — 境界 ub は ctx に応じて変動。
    出典: `2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary.md`

## eval 安定性（Seval）

16. **run 内分散は極小だがセッション間ゆらぎが大きい** — 1-run 参照値は再現しない。
    出典: `2026-04-20_003250_qwen3-122b-c3-phaseSeval.md`、`2026-04-20_013006_qwen3-122b-c3-phaseSevalcross.md`
17. **ub 構成ごとに独立変動** — 崩壊・復帰パターンが ub ごとに異なる（Markov 的挙動も観測）。
    出典: `2026-04-20_085556_qwen3-122b-c3-phaseSeval10s.md`（Markov 連鎖）ほか Seval シリーズ全般
18. **「単一の最高速 ub」は存在しない（旧記述を修正）** — 3構成(ub=1584/1586/1664)はセッション毎に首位が入れ替わる。59回通算の首位最多は **ub=1586（42.4%・最安定）**、ub=1664 は pool max 15.534 t/s だが崩壊頻度 54.2% で最も不安定。
    出典: `2026-04-22_140055_qwen3-122b-c3-phaseSeval59s.md`（最終回。首位率 1586=42.4%/1584=33.9%/1664=23.7%、ub=1664 pool max 15.534 を確認）
    ※旧版の「ub=1664 が最終的に最高速・自己ベスト15.621」は誤り。15.621 は本文に存在せず、ub=1664 の実際の pool max は 15.534。

## 最終構成（Phase T/U）

19. **split-mode は layer が優位** — P100 構成では row より layer。
    出典: `2026-04-22_165843_qwen3-122b-c3-phaseT2-splitmode.md`
20. **スレッド数は 24 が最適** — 16/20/24/28 比較。
    出典: `2026-04-22_181614_qwen3-122b-c3-phaseT3-threads.md`
21. **gate/up 融合 GGUF で MoE 効率改善** — 演算効率の向上を確認。
    出典: `2026-04-24_063651_qwen3-122b-u4-gateup-fused.md`
22. **ctx=128k を本番既定化** — VRAM フィットを確認し起動スクリプトに反映。
    出典: `2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default.md`、`2026-04-24_163240_qwen3-122b-startup-script-128k-default.md`

## 運用・モデル移行

23. **Marathon ベンチで HEAD 再ビルド +1.3〜4.5%** — 18時間29試行。ngram-spec/B12/sm tensor は全失敗、ub=768 で prompt +16.2%。
    出典: `2026-05-17_045809_qwen3-122b-bench-marathon-summary.md`（phaseA〜E の個別レポートあり）
24. **Qwen3.6-35B-A3B をデフォルト LLM 化** — 軽量モデルへ移行。
    出典: `2026-05-21_043823_default_llm_qwen36_35b.md`
25. **DRY サンプラは「有効化→副作用判明→無効化」の弧（旧記述を修正）** — (a) `fed12136`/loop_sampling_fix で thinking ループ抑制のため DRY を**有効化(0.8)** → (b) DRY=0.8 が URL/IP・長パスを文字破損させる副作用が判明 → (c) **path_recall_fix(#3) で DRY 完全無効化(`--dry-multiplier 0`)** → (d) dry08_redeploy で dry=0 をコミット(`673472b6`)・稼働反映・検証。
    出典（無効化の一次）: `2026-05-26_143817_qwen36_sampler_path_recall_fix.md`。有効化の発端: `2026-05-25_115133_qwen36_loop_sampling_fix.md`。コミット・反映: `2026-05-29_134431_qwen36_dry08_redeploy_pathfix.md`
    ※旧版は loop_sampling_fix を「無効化」の出典としていたが、これは逆に「有効化」の回で誤り。
26. **presence_penalty もループ要因** — サンプラ起因のループを段階的に修正（DRY=0 維持下で presence-penalty 0.5→1.0）。
    出典: `2026-05-26_164557_qwen36_presence_penalty_loop_refix.md`
27. **llama.cpp の OOM 回帰を修正** — 新ビルドで再発した OOM への対処。
    出典: `2026-06-03_063647_llama_cpp_oom_regression_fix.md`
28. **t120h-p100 は `-ub 4096` で CUDA OOM 回避（旧記述を修正）** — ctx=131072 / KV q8_0 を `-ub 8192` で起動すると OOM。default を `-ub 8192`→`-ub 4096`（`-b 4096`）に変更して回避。
    出典: `2026-06-03_063647_llama_cpp_oom_regression_fix.md`（タイトル「llama.cpp 最新版 CUDA OOM の根本対策 (t120h-p100 を -ub 4096 へ)」）、コミット d4c5a5a3
    ※旧版の「対応する単独レポートは無し」は誤り。上記が専用レポート。
