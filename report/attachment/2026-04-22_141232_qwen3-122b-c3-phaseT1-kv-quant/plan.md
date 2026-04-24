# Phase T-1: KV cache 量子化スイープ

## Context

**背景**: qwen3-122b の eval t/s 改善は Phase A (10→12, GPU expert layer 14-19 復帰) → Phase D (12→15.03, numactl -N1 -m1 --threads 40) → Phase S (15.39, ctx×ub 細粒度探索) と進行。Phase S-eval (S1-S59) は再現性検証として S1 で reject 決着済み、残りは同一バイナリの反復測定で新しい情報を生まない。

**目的**: パラメータチューニングによる追加改善余地があるかを直接検証するフェーズ (Phase T) に切り替え、その第一弾として **KV cache 量子化型スイープ** を実施する。

**選定理由**: ユーザ提示の有望軸 5 つ (KV 量子化 / split-mode row / threads 中間値 / OT pattern / ビルドフラグ) のうち、KV cache 量子化 (`--cache-type-k/--cache-type-v`) は:
- 現行 `f16` と一部 Phase の `q8_0` のみ既測、`q4_0 / q4_1 / q5_0 / q5_1` 未検証
- KV 量子化は VRAM 圧縮により同 ctx での compute buffer 余裕が拡大 → -ub をより大きく取れる可能性
- eval 経路 (token-by-token attention) で KV 読み出し帯域が支配的となる場面があり、低精度化で memory traffic が下がる可能性
- 再ビルド不要で実行時フラグのみで切替可 → 低コストで検証完了

**判定基準**: eval t/s と prompt t/s の両方で、Phase D (15.03) / Phase S (15.39) ピークを明確に超える KV 型 × ub の組合せが存在するかを判定する。

## 実験条件

### 固定パラメータ (Phase S-eval ベースライン S54 構成を踏襲)

| 項目 | 値 |
|------|---|
| HOST | t120h-p100 (10.1.4.14) |
| MODEL | unsloth/Qwen3.5-122B-A10B-GGUF Q4_K_M |
| ctx-size | 32768 |
| threads | 40 |
| numactl | `--cpunodebind=1 --membind=1` |
| -ngl | 999 |
| -ot | `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU` |
| flash-attn | 1 |
| parallel | 1 |
| poll | 0 |
| sampling | `--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0` |

### スイープ軸 (4 × 2 = 8 条件)

- **KV cache 型**: `f16` (baseline) / `q8_0` / `q4_0` / `q4_1` (各々 `--cache-type-k` と `--cache-type-v` に同値を設定)
- **ubatch サイズ**: `1586` (S54 ピーク) / `1664` (S54 探索上限)

### 測定 run 数

- 各条件: warmup 2 run + eval 5 run = **7 run × 8 条件 = 56 run**
- プロンプト: 1k tokens (既存 `prompts/` ディレクトリ流用)

## 実装方針

### スクリプト構成 (S54 添付を踏襲して改修)

流用元: `report/attachment/2026-04-22_072412_qwen3-122b-c3-phaseSeval54s/`

| ファイル | 変更内容 |
|--------|--------|
| `start_phaseT1.sh` | S54 の `start_phaseSeval54s.sh` をコピーし、`CACHE_TYPE_K` / `CACHE_TYPE_V` 環境変数を受け取れるように改修 (行 30 `--cache-type-k f16 --cache-type-v f16` を変数化)。REMOTE_LOG prefix を `phaseT1` に変更し、ファイル名に KV 型を含める |
| `measure_phaseT1.sh` | S54 の `measure_phaseI.sh` をコピー (ロジック変更なし、出力ディレクトリ命名のみ `out_T1_kv${CACHE_TYPE}_ub${UB}` 形式に対応) |
| `run_all_phaseT1.sh` | S54 の `run_all.sh` をコピー。warmup 2 + eval 5 の構造は同じ |
| `batch_phaseT1.sh` | S54 の `batch_phaseSeval54s.sh` をコピーし、外側ループを **KV 型 (f16/q8_0/q4_0/q4_1) × ub (1586/1664)** の 8 条件に変更。KV 型変更時は必ずサーバ再起動 |
| `analyze_phaseT1.py` | S54 の `analyze_phaseSeval54s.py` をベースに、**pivot 比較表生成** を追加: 行 = KV 型、列 = ub × {eval_tps, prompt_tps} の mean±std。CSV + Markdown テーブル出力 |

**timeseries plot は生成しない** (反復測定ではなく探索のため、ユーザ指示)。

### 起動前チェック

KV 量子化により compute buffer 余裕が変動するため、各条件で起動ログの CUDA0/1/2/3 buffer size を記録し、OOM abort を検知 (S54 の `cudaMalloc failed` grep パターンをそのまま使用)。

### 測定メトリクス

- **eval_tps**: `predicted_per_second` (llama-server JSON timings)
- **prompt_tps**: `prompt_per_second` (同上)
- いずれも 5 run の mean / std / min / max を算出

## 判定ロジック

pivot 表生成後、以下の閾値で各条件を分類:

| 判定 | eval_tps 閾値 | prompt_tps 閾値 |
|------|-------------|---------------|
| **Phase S ピーク超え** | mean > 15.39 | (情報として記録) |
| **Phase D ピーク超え** | mean > 15.03 | |
| **ベースライン (f16) 同等** | f16 mean ± 3% | |
| **劣化** | f16 mean より 3% 以上低下 | |

q4_0/q4_1 で出力品質劣化が懸念されるため、warmup run の生成テキスト末尾を目視サンプル保存 (S54 既存の `out_*` ディレクトリに残る JSON を流用)。

## 実行手順

```bash
# スクリプト準備
TS=$(ssh t120h-p100 'TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S')
REPORT_NAME="${TS}_qwen3-122b-c3-phaseT1-kv-quant"
ATTACH_DIR="report/attachment/${REPORT_NAME}"
mkdir -p "${ATTACH_DIR}"

# S54 スクリプトをコピー & 改修
cp report/attachment/2026-04-22_072412_qwen3-122b-c3-phaseSeval54s/{measure_phaseI.sh,run_all.sh,prompts} "${ATTACH_DIR}/"
# start_phaseT1.sh / batch_phaseT1.sh / analyze_phaseT1.py を上記方針で作成

# ロック取得 (gpu-server skill)
# バッチ実行
bash "${ATTACH_DIR}/batch_phaseT1.sh" 2>&1 | tee "${ATTACH_DIR}/batch_phaseT1.log"

# 分析
python3 "${ATTACH_DIR}/analyze_phaseT1.py" "${ATTACH_DIR}/"
```

## レポート作成

**ファイル**: `report/${TS}_qwen3-122b-c3-phaseT1-kv-quant.md`

**タイトル** (50 字以内): `Phase T-1: KV cache 量子化スイープ (f16/q8_0/q4_0/q4_1)`

**必須セクション構成**:
1. 添付ファイル (plan.md リンク)
2. 前提・目的 (Phase A/D/S ピーク値と Phase T 切替の背景)
3. 環境情報
4. 核心発見サマリ (判定結果・ピーク超え条件の有無)
5. 再現方法
6. **pivot 比較表** (KV 型 × ub × {eval_tps, prompt_tps})
7. 条件別詳細 (compute buffer size、出力品質サンプル)
8. **未検証事項** セクション (必須)
9. **検証完了後に実施すべき TODO** セクション (必須)
10. 参照レポート (Phase D/S/S54 レポートへのリンク)

**未検証事項候補** (レポート内で列挙予定):
- split-mode row vs layer (Phase T-2 候補)
- threads 中間値 24/28/32/36 (Phase T-3 候補)
- OT pattern expert 層範囲の他組合せ (Phase T-4 候補)
- llama.cpp ビルドフラグ GGML_CUDA_FORCE_MMQ / FORCE_DMMV (Phase T-5 候補)
- q5_0 / q5_1 KV 型 (本 Phase で未含、容量と精度の中間点)
- KV 非対称 (k=q8_0, v=f16 等) の組合せ
- ctx=65536 での KV 量子化挙動 (本 Phase は ctx=32768 のみ)

**TODO 候補**:
- 勝者構成があれば安定性検証 (10 セッション反復)
- KV 量子化による出力品質の定量評価 (perplexity など)
- Phase T-2 (split-mode row) のスクリプト雛形準備

## 検証方法

1. **バッチ完了確認**: 8 条件 × 7 run = 56 measurement が全て完了、abort/error 無し
2. **CSV 一貫性**: `summary_phaseT1.tsv` が 40 行 (8 条件 × 5 eval run) を持つ
3. **pivot 表整合**: Markdown 表が 4 行 × 4 列 ({f16,q8_0,q4_0,q4_1} × {ub1586_eval, ub1586_prompt, ub1664_eval, ub1664_prompt}) で欠損なし
4. **判定値の再現確認**: f16 baseline (ub=1586) の eval_tps が S54 の 15.173 ± 5% 内に収まるか (収まらなければ環境変動ありと判定して注釈)

## 参照

- [Phase S-eval-54session レポート](../projects/llm-server-ops/report/attachment/2026-04-22_072412_qwen3-122b-c3-phaseSeval54s/) — 流用元スクリプト
- Phase D レポート (15.03 t/s 達成) — `report/2026-04-15_*_qwen3-122b-c3-phaseD.md` 付近
- Phase S レポート (15.39 t/s 達成) — `report/2026-04-19_120715_qwen3-122b-c3-phaseS-ub-ctx-2d.md` 付近

## 重要な遵守事項

- **GPU サーバロック必須**: Skill `gpu-server` でロック取得
- **sudo 直接実行禁止**: 必要時はコマンド提示してユーザに依頼
- **プランファイル添付必須**: レポート作成時に本ファイルを `attachment/<レポート名>/plan.md` にコピー
- **REPORT.md ルール遵守**: タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得
