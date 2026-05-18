# Phase B: Speculative decoding 探索（全試行 OOM 失敗）

- **実施日時**: 2026 年 5 月 16 日 18:40–19:50 JST
- **対象**: llama.cpp `HEAD = 1348f67c5` × Qwen3.5-122B-A10B-Q4_K_M × t120h-p100 × fit (B14b_ts_alt)

## 核心発見サマリ

- **`--spec-type` 系（ngram-simple / ngram-mod / ngram-cache）は ctx=128k / ctx=96k の両方で OOM クラッシュし、本構成では実用不可**
- 原因: spec が **`context checkpoint`** 機構を必須とし、各リクエストで 149 MiB × 2-3 個 = 300-450 MiB を CUDA per-GPU に追加確保するため、Phase U-6 デフォルト構成（min_gpu_free=460–590 MiB）の VRAM 余裕を超える
- **これは Phase U-1 (spec ckpt) で確定済みの「VRAM 競合」と同じ問題**。ngram-* 系も同じ checkpoint 機構を使うため同様に失敗
- spec を活用するには **VRAM 確保構成**（B12 化 / KV q4_0 / より小さい OT / ctx<64k 等）が前提

## 添付ファイル

- [実装プラン](attachment/2026-05-16_195031_qwen3-122b-bench-marathon-phaseB-spec-fail/plan.md)
- [Phase B (ctx=128k) スクリプト](attachment/2026-05-16_195031_qwen3-122b-bench-marathon-phaseB-spec-fail/phaseB_orchestrator.sh)
- [Phase B' (ctx=96k) スクリプト](attachment/2026-05-16_195031_qwen3-122b-bench-marathon-phaseB-spec-fail/phaseB_ctx96k_orchestrator.sh)
- [生 CSV (全 spec 試行)](attachment/2026-05-16_195031_qwen3-122b-bench-marathon-phaseB-spec-fail/results.csv)
- [Phase B 実行ログ](attachment/2026-05-16_195031_qwen3-122b-bench-marathon-phaseB-spec-fail/phaseB.log)
- [Phase B' 実行ログ](attachment/2026-05-16_195031_qwen3-122b-bench-marathon-phaseB-spec-fail/phaseB_ctx96k.log)
- 各試行の cmdline・out_<S*>/・llama-server ログ

## 前提・目的

- 背景: Phase A で BL が U-6 比 +1.3〜+4.5% 改善を確認。次は **新規 spec 機構**（`--spec-type ngram-simple/mod/cache/map-k/map-k4v/chain`）が generate 速度を更に押し上げるか検証する予定だった
- 目的: PR #22838 等で追加された 7 種類の spec 方式（draft model 不要の ngram 系 + MTP）を順次試行し、本構成での効果を計測
- 前提: 既存メモリ `[[project_t_series_roadmap]]` に「spec ckpt PR #19493 は逆効果と確定（Phase U-1）」と記載。今回の ngram-* 系は **同じ checkpoint 機構を使う実装**であることが本フェーズで判明
- 参照レポート:
  - [U-1 spec ckpt baseline (-21〜-33% 回帰)](2026-04-23_132933_qwen3-122b-u1-specckpt-baseline.md)
  - [U-1ext spec ckpt relaxed](2026-04-23_171459_qwen3-122b-u1ext-specckpt-relaxed.md)
  - [Phase A 結果](2026-05-16_183834_qwen3-122b-bench-marathon-phaseA-quickwins.md)

## 環境情報

- サーバ: `t120h-p100` (10.1.4.14)、GPU: P100 × 4 (64 GB, sm_60)
- llama.cpp `HEAD = 1348f67c5`
- ベース構成（BL）: B14b_ts_alt + `--flash-attn 1 -b 2048 -ub 512 --tensor-split 11,12,13,14`、`--threads 40`、`numactl -N1 -m1`、`--cache-type-k/v q8_0 --parallel 1`
- 試行ごとに `--spec-type <variant>` を `SERVER_OPTS` に追加して計測

## GGUF メタ事前調査結果

- `mtp.*` テンソル: **なし** → `--spec-type draft-mtp` はスキップ確定
- `sliding_window` / `swa.*` メタ: **なし** だが `qwen35moe.full_attention_interval=4` 確認（SWA は Phase D で別途検証）
- block_count=48, head_count=32, head_count_kv=2, head_dim=256

## 試行マトリクスと結果

### Phase B（ctx=128k = 131072）

| ID | spec_args | 起動 | 1k 計測 | 32k 計測 | 結果 |
|----|-----------|------|---------|----------|------|
| S1 | `--spec-type ngram-simple` | ✅ | warmup 2 OK / eval 1-5 全 fail | 全 fail | OOM (CUDA error: out of memory on CUDA3) |
| S2 | `--spec-type ngram-mod` | ✅ | warmup 1 OK / 以降 fail | 全 fail | OOM |
| S3 | `--spec-type ngram-cache` | ✅ | warmup 1 OK / 以降 fail | 全 fail | OOM |
| S4 | `--spec-type ngram-map-k` | （Phase B' に切替えのため未実行）| – | – | – |
| S5 | `--spec-type ngram-map-k4v` | – | – | – | – |
| S6 | チェイン `--spec-type ngram-mod,ngram-cache` | – | – | – | – |
| S7 | `--spec-type draft-mtp` | （GGUF に MTP テンソルなし）| – | – | スキップ |

### Phase B'（ctx=96k = 98304）

ctx を 96k に下げて再試行（プランの ctx フォールバック規則）。

| ID | spec_args | 結果 |
|----|-----------|------|
| S1@96k | ngram-simple | warmup 2 + **eval 1-2 のみ成功** (eval mean ≈ 18.40 t/s = BL 比 -0.4%) / eval 3-5 fail / 32k 全 fail |
| S2@96k | ngram-mod | warmup 1 OK / 以降全 fail | 
| S3@96k | ngram-cache | warmup 1 OK / 以降全 fail |
| S4@96k〜S6@96k | （途中で打ち切り） | – |

### OOM の決定的根拠（サーバログ抜粋）

```
0.19.494.972 W srv load_model: speculative decoding will use checkpoints
0.19.494.993 I common_speculative_init: adding speculative implementation 'ngram-simple'
0.44.810.198 I slot create_check: id 0 | task 0 | created context checkpoint 1 of 32
                                 (pos_min = 555, pos_max = 555, n_tokens = 556, size = 149.063 MiB)
0.51.857.673 I slot create_check: id 0 | task 0 | created context checkpoint 2 of 32
                                 (pos_min = 1067, pos_max = 1067, n_tokens = 1068, size = 149.063 MiB)
...
/home/llm/llama.cpp/ggml/src/ggml-cuda/ggml-cuda.cu:102: CUDA error
0.52.003.528 E CUDA error: out of memory
0.52.003.533 E   current device: 3, in function alloc at ggml-cuda.cu:527
```

- 1 リクエストにつき **2 個の context checkpoint × 149 MiB = 298 MiB** が CUDA に追加確保される
- 連続リクエストで checkpoint が累積（最大 32 個まで → 4.7 GB）
- BL の min_gpu_free=590 MiB / ctx=96k で min_gpu_free=782 MiB しか余裕がなく、即 OOM
- ngram-simple は理論上 checkpoint 不要にも見えるが、現実装は **全 spec バリアントが checkpoint 機構を共有**（`speculative decoding will use checkpoints` ログ）

## 仮説と解釈

1. **ngram-* 系は内部で context checkpoint を使う実装**: ngram cache 自体は軽量だが、spec の rollback サポートに checkpoint が必要。S1（ngram-simple）でも `created context checkpoint` ログが出る
2. **per-request の checkpoint 累積が OOM を生む**: 1 件で 300 MiB、5 件連続で 1.5 GB / GPU 追加。本構成の VRAM 余裕 590 MiB ではすぐに超過
3. **ctx=96k → 128k → 192k のメモリ削減効果は spec にとって小さい**: KV (q8_0) は 32k 縮小 ≈ 100 MiB / GPU しか浮かないが、checkpoint 1 個は 149 MiB と単発で大きい
4. **K1 (KV q4_0) で +192 MiB の余裕を得れば spec が動くか** — 未検証。Phase D の余裕枠があれば実施を検討
5. **spec ckpt との連続性**: Phase U-1 で確定した「spec ckpt PR #19493 は -21〜-33% で逆効果」と同じ問題が、改名された ngram-* 系でも継続している

## Phase B 全試行を打ち切った判断

- S1 (ngram-simple) ctx=128k → OOM、ctx=96k でも改善なし
- S2/S3 も同様の挙動を確認、S4-S6 でも結果は変わらないと判断（チェックポイント機構は全 spec 共通のため）
- 残り 24 時間予算と Phase C/D/E の必要時間を考慮し、19:50 時点で打ち切り
- 「**spec は本構成では使えない**」を確定的に記録し、Phase C へ移行

## 効きそうな PR の観測結果（updated）

| PR | 期待 | 観測 |
|----|------|------|
| #22838 (spec parallel drafting) | generate +20-100% | **本構成では VRAM 不足で不可**、speedup 検証不能 |
| #22506 (spec last-token discard) | spec 受理率改善 | 同上 |
| #22679 (state seq flags on device) | spec D2H 削減 | 同上 |
| #22673 (draft-mtp) | decode 1.85-2.2x | GGUF に `mtp.*` テンソルなし → スキップ |

## 次フェーズ (C) への反映点

- **Phase C は spec なしで進める**（ub / b / threads sweep）
- spec 検証は **将来的に B12 化や KV q4_0 で VRAM 余裕を作った後** に Phase D で部分的に再試行する可能性あり
- BL は ctx=128k のままで Phase C のベースに採用
- N1 + B 全失敗で予算 +2 時間消費 → Phase C / D は短縮版で進める

## 再現方法

```bash
# Phase B (ctx=128k) で OOM を再現する場合
bash <添付>/phaseB_orchestrator.sh

# Phase B' (ctx=96k) で同様に OOM 再現
bash <添付>/phaseB_ctx96k_orchestrator.sh

# サーバログで `speculative decoding will use checkpoints` と `created context checkpoint` を確認
ssh t120h-p100 'grep -E "checkpoint|out of memory" /tmp/llama-server.log'
```

## 未試行 / 後フェーズに送る項目

- spec + KV q4_0 構成（K1 ベース、+192 MiB 余裕）→ Phase D 余裕枠で検討
- spec + B12 化（OT 12 層に縮小）→ Phase D O1 で B12 が成功すれば spec 再試行
- spec + ctx=32k → BL 自体が U-6 比較対象外になるため優先度低
- S4 (ngram-map-k) / S5 (ngram-map-k4v) / S6 (chain) の動作確認 → 上記改善構成で実現できれば
