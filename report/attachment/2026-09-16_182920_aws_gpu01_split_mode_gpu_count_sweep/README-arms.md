# 腕の対応表（GPU 枚数スイープ）

すべて同一バイナリ（`ca54f4dd…8593886`、llama.cpp master `465e49b9c` / build 10830）、
同一モデル（`Qwen3.8-27B-UD-Q4_K_XL.gguf`）、同一ワークロード
（ctx=131072 / stages `0,16000,32000,64000,128000` / n-predict 1000 / pp0 512,2048,8192 /
KV q8_0 / `-fa on` / `-t 16` / `--parallel 1`）。**MTP は無効**（`SPEC_ARGS=""`）。

`LAUNCH_PREFIX="env GGML_CUDA_ALLREDUCE=none"` を全腕に一律で掛けている。
`--split-mode layer` では `ggml_backend_cuda_comm_init` 自体が呼ばれないため**完全に不活性**
（2026-09-16 レポート副次発見 2 で実測確認済み）。`--split-mode tensor` では有効に効く。

| ディレクトリ | 腕名 | GPU 枚数 | デバイス | split | 備考 |
|---|---|---:|---|---|---|
| `run-layer/` | `layer2` | 2 | CUDA0,CUDA1 | layer | 2026-09-14 / 09-16 の `layer2` と同条件（再現性チェック） |
| `run-layer/` | `layer3` | 3 | CUDA0-2 | layer | 新規 |
| `run-layer/` | `layer4` | 4 | CUDA0-3 | layer | 新規 |
| `run-layer/` | `layer5` | 5 | CUDA0-4 | layer | 新規 |
| `run-layer/` | `layer6` | 6 | CUDA0-5 | layer | 新規 |
| `run-layer/` | `layer` | 7 | CUDA0-6 | layer | 2026-09-14 の `layer` と同条件（再現性チェック） |
| `run-tensor/` | `tensor2` | 2 | CUDA0,CUDA1 | tensor | 新規 |
| `run-tensor/` | `tensor3` | 3 | CUDA0-2 | tensor | 新規 |
| `run-tensor/` | `tensor4` | 4 | CUDA0-3 | tensor | 新規 |
| `run-tensor/` | `tensor5` | 5 | CUDA0-4 | tensor | 新規 |
| `run-tensor/` | `tensor6` | 6 | CUDA0-5 | tensor | 新規 |
| `run-tensor/` | `tensor` | 7 | CUDA0-6 | tensor | 2026-09-16 の切り分け腕（`none`・MTP 無効）と同条件（再現性チェック） |

7 枚の腕だけ数字を付けずに `layer` / `tensor` としているのは、`plot_bench.py:32` の固定色枠
（`layer` = 青 / `tensor` = 赤）を確保して 6 系列の色衝突を避けるため。カスタム名だけを 6 個並べると
フォールバック色が 5 色しかなく 1 番目と 6 番目が同色になる。過去 3 レポートの腕名とも一致する。

## 実プロンプト補正

`REAL_MODE=auto` は「名前が厳密に `tensor` の腕」を選ぶ（`run-bench.sh:95`）。
したがって `run-layer/results-real.json` は **`layer2`**（`SEL[0]`）、
`run-tensor/results-real.json` は **`tensor`（7 枚）** で取られている。

## スモーク

`run-smoke/` は本計測前に 12 腕すべての起動を確認したもの
（ctx=8192 / stages `0,4000` / n-predict 100 / pp0 512 / `--no-real`、13 分 20 秒で完走）。
