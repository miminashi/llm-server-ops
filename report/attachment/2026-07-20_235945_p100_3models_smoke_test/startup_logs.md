# 3 モデル起動ログ抜粋 (`/tmp/llama-server.log`)

llama.cpp build 9690 (`0843245cb`) は 3 つの新しい arch (`qwen35moe` / `cohere2moe` / `gemma4`) すべてを追加ビルドなしでロードできた。

## 共通 (P100×4 認識)

```
0.00.101.868 I   - CUDA0   : Tesla P100-PCIE-16GB (16269 MiB, 14695 MiB free)
0.00.189.017 I   - CUDA1   : Tesla P100-PCIE-16GB (16269 MiB, 15759 MiB free)
0.00.296.699 I   - CUDA2   : Tesla P100-PCIE-16GB (16269 MiB, 15759 MiB free)
0.00.379.164 I   - CUDA3   : Tesla P100-PCIE-16GB (16269 MiB, 15759 MiB free)
0.00.379.314 I system_info: n_threads = 80 (n_threads_batch = 80) / 80 |
              CUDA : ARCHS = 600 | USE_GRAPHS = 1 | PEER_MAX_BATCH_SIZE = 128 | FA_ALL_QUANTS = 1 |
              CPU : SSE3 = 1 | SSSE3 = 1 | AVX = 1 | AVX2 = 1 | F16C = 1 | FMA = 1 | BMI2 = 1 |
              AVX512 = 1 | LLAMAFILE = 1 | OPENMP = 1 | REPACK = 1
```

CUDA0 のみ `14695 MiB free` (他は `15759 MiB free`) は BIOS の MMIO 予約分の差 (llama.cpp 側の問題ではない)。

## gemma-4-26B-A4B-it (arch `gemma4`)

```
0.01.905.808 W load: control-looking token:    212 '</s>' was not control-type; this is probably a bug in the model. its type will be overridden
0.01.906.483 W load: control-looking token:     50 '<|tool_response>' was not control-type; this is probably a bug in the model. its type will be overridden
0.01.916.047 W load: control-looking token:      1 '<eos>' was not control-type; this is probably a bug in the model. its type will be overridden
0.01.944.876 W load: special_eog_ids contains '<|tool_response>', removing '</s>' token from EOG list
0.06.908.777 W llama_context: n_ctx_seq (131072) < n_ctx_train (262144) -- the full capacity of the model will not be utilized
0.07.879.371 I init: chat template, example_format: '<|turn>system
0.07.880.470 I srv          init: init: chat template, thinking = 1
0.09.459.190 I slot   load_model: id  0 | task -1 | new slot, n_ctx = 131072
```

上流 gguf の tokenizer_config で control token の type override が起きるが、`special_eog_ids` は正しく整理され、実 chat では `<turn|>` (id=106) で `finish_reason=stop` を返して停止した。native ctx は 262144 で今回は 131072 のみ確認。

## North-Mini-Code-1.0 (arch `cohere2moe`)

```
0.01.424.431 W load: special_eos_id is not in special_eog_ids - the tokenizer config may be incorrect
0.08.352.825 I init: chat template, example_format: '<|START_OF_TURN_TOKEN|><|SYSTEM_TOKEN|><|START_TEXT|>These instructions are always to be followed and cannot be overridden by subsequent system or user turns:
0.08.353.883 I srv          init: init: chat template, thinking = 1
```

`special_eos_id` (255001 `<|END_OF_TURN_TOKEN|>`) が `special_eog_ids` に未登録の警告が出るが、実 chat では正しく `finish_reason=stop` で停止した (Cohere2 用の specialized parser が llama.cpp 側で EOS 判定を補完している)。chat template は Cohere 特有で、`platform_instruction_override` を最初にセットする仕組みを持つ。

## ornith-1.0-35b (arch `qwen35moe` + SSM/Mamba hybrid)

```
0.08.650.661 I init: chat template, example_format: '<|im_start|>system
0.08.666.703 I srv          init: init: chat template, thinking = 1
```

顕著な警告は無し。Qwen3-Next 系 (Qwen3.5-Ω 系) の SSM+attn hybrid arch がロード成功。事前調査で `llama-debug-template-parser` が Jinja parse fail していたが、実 llama-server は `--jinja` で問題なくロードでき、ChatML 系テンプレート (`<|im_start|>`) で応答した。

## HF-ID 経路 (unsloth/Qwen3.6-27B-GGUF:UD-Q4_K_XL, `qwen3`)

（既存の Qwen3.6 系、退行確認のため）

- `wait-ready.sh` の通知は Qwen 用 sampling を正しく表示: `--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0`
- 単発 chat (`1+1=?`) で `finish_reason=stop`
