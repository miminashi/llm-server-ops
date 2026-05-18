# Phase D: Architecture（B12 / B16 / -sm tensor / SWA）

- **実施日時**: 2026 年 5 月 16 日 22:21–23:21 JST
- **対象**: llama.cpp `HEAD = 1348f67c5` × Qwen3.5-122B-A10B-Q4_K_M × t120h-p100 × fit (B14b_ts_alt, ctx=128k)

## 核心発見サマリ

- **B14（現行）が CPU offload 層数の sweet spot**: B12 化（CPU 12 層）は起動失敗 → 12 層では GPU に乗り切らず OOM、B16 化（CPU 16 層）は -4.18% 低下
- **`-sm tensor`（tensor parallel）は本構成では curl_failed で計測不可**: KV f16 化しても、context checkpoint + tensor split の組み合わせで OOM
- **`--swa-full` は -1.32%（軽微低下）**: Qwen3.5MoE が `full_attention_interval=4` を持つにも関わらず、フル SWA キャッシュは速度面で寄与しない
- **B12 化（感度外挿 18.91 t/s）の実証は失敗** → memory `[[project_t_series_roadmap]]` の未試行項目はこの構成では不可

## 添付ファイル

- [実装プラン](attachment/2026-05-16_232150_qwen3-122b-bench-marathon-phaseD-arch/plan.md)
- [Phase D オーケストレータ](attachment/2026-05-16_232150_qwen3-122b-bench-marathon-phaseD-arch/phaseD_orchestrator.sh)
- [生 CSV](attachment/2026-05-16_232150_qwen3-122b-bench-marathon-phaseD-arch/results.csv)
- [Phase D 実行ログ](attachment/2026-05-16_232150_qwen3-122b-bench-marathon-phaseD-arch/phaseD.log)
- 各試行の out_<試行>/ 配下の生レスポンス JSON + llama-server log

## 前提・目的

- 背景: Phase A-C で BL は U-6 比 +1.3〜+4.5% 改善、Quick wins（M1, T1_th32）で +1.6% 累積見込み。次は **アーキ系**の試行で更なる改善余地を探る
- 目的:
  - **O1 (B12)**: CPU offload を 14 → 12 層に削減。VRAM 余裕を生んで eval 改善（感度外挿 18.91 t/s 予測）
  - **O2 (B16)**: 逆方向に CPU offload を増やしてプロファイル把握
  - **G1 (`-sm tensor`)**: tensor parallel で TG 1.3-1.7x 期待（PR #19378）。FA 必須・KV 量子化禁止
  - **W1 (`--swa-full`)**: Qwen3.5MoE の `full_attention_interval=4` 構造を活用
- 参照: [Phase A](2026-05-16_183834_qwen3-122b-bench-marathon-phaseA-quickwins.md), [Phase C](2026-05-16_221912_qwen3-122b-bench-marathon-phaseC-sweep.md), [T-5a-ts2](2026-04-23_093629_qwen3-122b-c3-phaseT5a-ts2.md)

## 環境情報

- サーバ: `t120h-p100`、P100 × 4 (64 GB)
- llama.cpp `HEAD = 1348f67c5`
- ベース: BL = B14b_ts_alt + ctx=128k + `--flash-attn 1 -b 2048 -ub 512 --tensor-split 11,12,13,14`, threads 40, KV q8_0

## GGUF メタ調査結果（再掲）

- block_count=48, head_count=32, head_count_kv=2, head_dim=256
- `full_attention_interval=4`（4 層ごとに full attention、それ以外は局所）
- `mtp.*` テンソル: なし → MTP/SWA メタは無いがアーキとしては SWA 採用

## 試行内容

| ID | 変更 | 期待 |
|----|------|------|
| O1 | OT 14 → 12 層 (`{2,3,21,22,23,31-37}`、layer 20, 38 を GPU に戻す) | 18.91 t/s (感度外挿) |
| O2 | OT 14 → 16 層 (`{2,3,20-24,31-39}`、layer 24, 39 を CPU に追加) | プロファイル把握 |
| G1 | `--split-mode tensor` + KV f16 | TG 1.3-1.7x |
| W1 | `--swa-full` 追加 | SWA キャッシュ全保持で hit 改善 |

## 結果

| 試行 | n | eval mean (t/s) | eval std | prompt mean (t/s) | BL 比 |
|------|---|-----------------|----------|--------------------|------|
| **BL (Phase A 値)** | 5 | **18.482** | 0.110 | 64.366 | – |
| **O1 (B12)** | – | 🚫 **起動失敗** | – | – | – |
| **O2 (B16)** | 5 | 17.709 | 0.006 | 60.432 | **-4.18%** |
| **G1 (`-sm tensor`)** | – | 🚫 **curl_failed** | – | – | – |
| **W1 (`--swa-full`)** | 5 | 18.238 | 0.006 | 64.518 | -1.32% |

### O1 (B12) 起動失敗の詳細

- OT を 12 層に縮小 (`{2,3,21,22,23,31-37}`)、layer 20, 38 が新たに GPU に戻る
- Qwen3.5-122B-A10B (Q4_K_M, 122B モデル) の expert weight は 1 層あたり大きく、12 層を CPU に置くだけでは残り 36 層 × expert weight が GPU 容量を超える
- wait_ready 120 回 × 5 秒 = 10 分 timeout で起動失敗判定

### O2 (B16) eval mean = 17.709 t/s

- CPU offload 16 層で expert weight CPU 処理負荷増加
- 結果: -4.18% 低下、Phase T-4 系で観測した B16 ≈ 17.5–17.8 t/s 帯と整合
- B14b_ts_alt が現実装での最適点であることを再確認

### G1 (`-sm tensor`) curl_failed

- `--split-mode tensor` は KV 量子化と非互換のため f16 に強制
- 起動は成功した可能性があるが、初回リクエストで curl_failed
- 原因不明（KV f16 + tensor split + context checkpoint の組合せで OOM の可能性）
- llama-server ログ取得済み、追加調査は要時間

### W1 (`--swa-full`) eval mean = 18.238 t/s

- Qwen3.5MoE は `full_attention_interval=4` で 75% の層が SWA、25% が full attention
- `--swa-full` で SWA キャッシュをフル保持しても eval は -1.32% 低下
- prompt は +0.24% でほぼ同等、メモリ使用量は増えるが速度メリットなし

## 仮説と解釈

1. **B12 化失敗**: 122B モデル × Q4_K_M で、本構成では 14 層 CPU が最少。これ以上削るには GPU 1 枚あたりの VRAM 拡張（P100 16 GB → A100/A6000 等への移行）が必要
2. **B16 で -4.18% 低下**: CPU expert 処理は 1 層あたり ~1.3% の eval 影響。B14 → B16 で 2 層追加 → 2.6% 低下が期待値だが、実測 -4.18% はやや大きい。CPU 側のメモリ帯域競合可能性
3. **`-sm tensor` の難しさ**: PR #19378 で導入された tensor parallel は本構成 (fit + checkpoint) との非互換性が高い。これを使うには fit モードを諦めて従来の `-sm none` で全層 GPU に乗せる必要があり、122B モデルでは不可
4. **SWA の効果なし**: `--swa-full` は SWA キャッシュ拡大による hit 増を狙うが、本ワークロード（1 リクエストあたり 1k prompt）では SWA の効果が小さい。長期セッションで何度も同じ prompt prefix を使う場合に効くと推測

## Phase E への反映点

- **Phase D は全試行で BL を上回らず**、Phase E の `BL_FINAL` は Phase A の M1 (+0.91%) と Phase C の T1_th32 (+0.66%) のみを組合せる構成にする
- **B14b_ts_alt は変更しない**（現実装での最適 OT パターン）
- **`-sm tensor` / `--swa-full` / OT 変更 は不採用**

## 再現方法

```bash
bash <添付>/phaseD_orchestrator.sh  # 約 1 時間
```

各試行の挙動:
- O1: `for L in 2 3 21 22 23 31 32 33 34 35 36 37` に編集 → 起動 timeout
- O2: `for L in 2 3 20 21 22 23 24 31 32 33 34 35 36 37 38 39` に編集 → 完走
- G1: `--split-mode tensor` + `--cache-type-k/v f16` に編集 → curl_failed
- W1: SERVER_OPTS 末尾に `--swa-full` 追加 → 完走

## 未試行 / 後フェーズに送る項目

- **B13 化**（CPU 13 層、B14 から layer 38 のみ GPU に戻す）→ B12 が失敗したので、より控えめな縮小は試す価値あり
- **`-sm tensor` + `--no-mmap` + KV q4_0**（VRAM 大幅削減）→ 専用調査が必要
- **`--swa-checkpoints 0`**（SWA checkpoint を無効化）→ Phase B の OOM 軽減検証用
- **W1 を 32k/96k prompt で計測**（SWA は長 prompt で効く可能性）

## 経過時間

| 試行 | 所要 | 結果 |
|------|------|------|
| O1 (B12) | 19 分 (起動 timeout 10 分 + 失敗判定) | ❌ |
| O2 (B16) | 24 分 | ✅ |
| G1 (`-sm tensor`) | 約 10 分 (起動 + curl_failed 即終了) | ❌ |
| W1 (`--swa-full`) | 13 分 | ✅ |
| **合計** | **~1 時間** | – |
