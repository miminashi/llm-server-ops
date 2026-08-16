# llama.cpp CPU-only Fine-tuning 実行計画 (mmns-cpu-llm)

## Context

- llama.cpp の fine-tuning 機能 (`llama-finetune` バイナリ) が実際に CPU-only 環境で動作するかを確認したい。
- 実行環境は mmns-cpu-llm (QEMU vCPU 94 コア / 62 GiB RAM / ディスク空き 23 GB / GPU なし / Ubuntu 24.04)。
- CLAUDE.md 指定の「ローカルでは重いプロセスを動かさない」制約に従い、全 heavy work は mmns-cpu-llm 側で実施。
- 得られる成果: (a) llama.cpp fine-tune パイプラインの疎通、(b) 学習前後で perplexity と生成テキストが変化することの実証、(c) CPU-only fine-tune の所要時間と RAM 実測値。
- レポート作成が必須 (CLAUDE.md ルール) なので、完了後 `report/` 配下にレポートを 1 本書く。

## llama.cpp fine-tune の重要制約 (調査済み)

- `~/llama.cpp/build/bin/llama-finetune` は full-parameter fine-tune (LoRA adapter 学習は未サポート)。
- **F32 GGUF 必須**: `llama_set_param` (`src/llama-context.cpp:3246`) が F32 テンソルしか学習対象に登録しないため、F16/BF16/量子化モデルでは norm 層等しか更新されず実質学習にならない。
- 現状 `token_embd.weight` と `rope_freqs.weight` は学習対象からスキップされる (FIXME)。
- 入力は plain text (BOS 付き next-token 予測)。JSONL / instruction 形式は未対応。
- 出力はフル GGUF (LoRA adapter ではない)。保存対応 arch: LLaMA / Qwen2 / Qwen3 / Mistral / Phi / Gemma(v1,2) / Starcoder 等 dense 主要 arch。非対応 arch は `llama-model-saver.cpp:15-36` を要確認。
- KV cache は F32 に強制 (F16 OUT_PROD 未実装のため)。
- 制約: `hparams.n_ctx_train % n_batch == 0`, `n_batch % n_ubatch == 0`。
- デフォルト: `-c` context, `-b 2048`, `-ub 512`, `-lr 1e-5`, `-epochs 2`, `--val-split 0.05`, `-opt adamw`。README proof-of-concept は `-c 512 -b 512 -ub 512`。

## Stage 構成 (Stage A + Stage B Qwen まで — ユーザ選択)

| Stage | ベースモデル | 目的 | F32 GGUF | 推定 RAM ピーク | 見積り時間 |
|---|---|---|---|---|---|
| A | HuggingFaceTB/SmolLM2-135M-Instruct | パイプライン疎通 | ~540 MB | ~3 GB | fine-tune 5–15 min |
| B | Qwen/Qwen2.5-0.5B | PPL 改善観察 | ~2.0 GB | ~9–10 GB | fine-tune 20–40 min |

いずれも Apache-2.0 / 非 gated で **HF_TOKEN 不要**。両モデルとも Llama/Qwen2 arch で saver 対応済。

## データセット

- `~/llama.cpp/scripts/get-wikitext-2.sh` で wikitext-2-raw を取得。
  - `wiki.test.raw` (~1.3 MB, ~280k tokens) を fine-tune 入力、`--val-split 0.05` (55 サンプル程度) を自動 val にする。
  - 効果可視化は同じ `wiki.test.raw` で PPL を before/after 比較 (README と同じ雑さで許容)。
  - fine-tune 効果は SmolLM2-Instruct/Qwen2.5 の chat 系分布と wikipedia 百科体のドメインギャップから出やすい。

## 作業ディレクトリ (mmns-cpu-llm)

```
~/finetune-lab/
  ├─ venv/          (Python 3.12 venv)
  ├─ hf/            (HF snapshot)
  ├─ gguf/          (F32 GGUF base)
  ├─ data/          (wikitext-2-raw)
  ├─ out/           (fine-tuned GGUF)
  └─ logs/          (progress / PPL / gen)
```

## 手順

### Step 0. 前提パッケージ (ユーザ済)

`python3-venv / python3-pip / unzip` はユーザが `sudo apt install` 実行済み。追加の sudo は原則発生しない見込み。

### Step 1. venv 構築 & Python 依存

```bash
ssh mmns-cpu-llm '
  mkdir -p ~/finetune-lab/{hf,gguf,data,out,logs} &&
  cd ~/finetune-lab &&
  python3 -m venv venv &&
  . venv/bin/activate &&
  pip install --upgrade pip &&
  pip install -r ~/llama.cpp/requirements/requirements-convert_hf_to_gguf.txt &&
  pip install "huggingface_hub[cli]"
'
```

`requirements-convert_hf_to_gguf.txt` は torch CPU wheel を `--extra-index-url` 経由で入れる。venv サイズは ~2 GB。

### Step 2. モデル取得と F32 GGUF 変換

**Stage A (SmolLM2-135M-Instruct):**

```bash
ssh mmns-cpu-llm '
  cd ~/finetune-lab && . venv/bin/activate &&
  hf download HuggingFaceTB/SmolLM2-135M-Instruct --local-dir hf/SmolLM2-135M-Instruct &&
  python3 ~/llama.cpp/convert_hf_to_gguf.py hf/SmolLM2-135M-Instruct \
      --outtype f32 --outfile gguf/smollm2-135m-instruct.f32.gguf
'
```

**Stage B (Qwen2.5-0.5B):**

```bash
ssh mmns-cpu-llm '
  cd ~/finetune-lab && . venv/bin/activate &&
  hf download Qwen/Qwen2.5-0.5B --local-dir hf/Qwen2.5-0.5B &&
  python3 ~/llama.cpp/convert_hf_to_gguf.py hf/Qwen2.5-0.5B \
      --outtype f32 --outfile gguf/qwen2.5-0.5b.f32.gguf
'
```

変換後、`gguf-py/scripts/gguf_dump.py` で全 tensor が F32 になっていることを念のため確認。

### Step 3. データ取得

```bash
ssh mmns-cpu-llm '
  cd ~/finetune-lab/data &&
  bash ~/llama.cpp/scripts/get-wikitext-2.sh
'
```

### Step 4. Baseline PPL 測定

```bash
ssh mmns-cpu-llm '
  ~/llama.cpp/build/bin/llama-perplexity \
      -m ~/finetune-lab/gguf/smollm2-135m-instruct.f32.gguf \
      -f ~/finetune-lab/data/wikitext-2-raw/wiki.test.raw \
      -c 512 -b 512 -t 64 --numa distribute \
      2>&1 | tee ~/finetune-lab/logs/ppl_smollm_before.log
'
```

Stage B (Qwen) も同様。**`-t 64` は暫定値**。Stage A の baseline PPL 中に `-t 32/64/94` を比較して最速値を Stage B fine-tune に採用。

### Step 5. Fine-tune 実行 (screen で detach)

**Stage A:**

```bash
ssh mmns-cpu-llm '
  cd ~/finetune-lab &&
  screen -dmS ft-smollm bash -c "
    ~/llama.cpp/build/bin/llama-finetune \
        -m gguf/smollm2-135m-instruct.f32.gguf \
        -f data/wikitext-2-raw/wiki.test.raw \
        -o out/smollm2-135m-ft.f32.gguf \
        -c 512 -b 512 -ub 512 \
        -t 64 --numa distribute \
        -epochs 2 -lr 1e-5 -opt adamw \
        2>&1 | tee logs/ft_smollm.log
  "
'
```

`tail -f ~/finetune-lab/logs/ft_smollm.log` で監視。完了後、同一構成で Stage B (Qwen) を流す。

### Step 6. Fine-tune 後の評価

- **PPL 再測定**: fine-tuned GGUF に対し `llama-perplexity` を同 `-c/-b` で走らせ、before/after を比較。
- **生成テキスト比較**: 同一 prompt/seed で `llama-cli` を before/after に走らせ、目視で百科体シフトを確認。
  ```bash
  ~/llama.cpp/build/bin/llama-cli -m <before or after gguf> \
      -p "Barack Obama was born in " -n 80 -c 512 -t 64 --seed 42 --no-conversation
  ```
- **loss curve**: `logs/ft_*.log` の epoch ごと train/val loss を抜き出し、単調減を確認。

## ディスク見積り (合計 ~7 GB, 23 GB 空きに対し余裕)

| 項目 | サイズ |
|---|---|
| venv (torch CPU + transformers + gguf) | ~2.0 GB |
| SmolLM2-135M HF snapshot | ~270 MB |
| SmolLM2-135M F32 GGUF (base + fine-tuned) | ~1.1 GB |
| Qwen2.5-0.5B HF snapshot | ~1.0 GB |
| Qwen2.5-0.5B F32 GGUF (base + fine-tuned) | ~4.0 GB |
| wikitext-2-raw | ~13 MB |
| ログ | <100 MB |
| **小計** | **~8.5 GB** |

gpt-oss-120b (60 GB) は触らず残す。

## 成功基準

**最小 (fine-tune が動作した):**
1. `logs/ft_*.log` に AdamW progress bar + train/val loss が epoch ごとに出力される。
2. `out/*.f32.gguf` が base とほぼ同サイズで生成される。
3. `llama-cli -m out/*.f32.gguf -p "..." -n 20` がクラッシュせず、意味のあるトークンを吐く。

**実質 (fine-tune の効果が観察された):**
1. PPL 改善: SmolLM2-135M で概ね 20–40% 減、Qwen2.5-0.5B で 10–25% 減 (期待レンジ、当てが外れても方向が下向きなら OK)。
2. loss curve: train/val loss が epoch を跨いで単調減。
3. 生成テキストが百科調に寄る変化が目視で確認できる。

## 想定される失敗モードと対応

| 失敗 | 対応 |
|---|---|
| convert 時に arch 不明 | HF snapshot の `config.json` を確認、`convert_hf_to_gguf.py` の対応 arch と照合 |
| Model saver で abort | 保存対応 arch (`llama-model-saver.cpp:15-36` 除外リスト) と照合、非対応なら別モデル |
| RAM OOM | `-c 256 -b 256 -ub 256` にダウンサイズ |
| 学習が進まない (loss 一定) | `gguf_dump.py` で base GGUF の tensor 型を確認 (F32 でない疑い) |
| CPU カーネル遅すぎ | `-t` を 32/48/64 と比較、`OMP_PROC_BIND=close OMP_PLACES=cores` を試す |
| ディスク full | logs のローテ / HF snapshot を fine-tune 完了後に削除 |

## リスク・落とし穴

- **`token_embd` 未学習**: embedding は更新されないため語彙シフトは学習不可。wikitext は語彙が pretrain と近いので実害小。
- **AVX-512 のみ, AMX/VNNI/BF16 なし, BLAS OFF**: 純 ggml F32 カーネルで CUDA/BLAS 版比 10–30× 遅い前提。所要見積りに織り込み済み。
- **QEMU vCPU の実態不明**: `-t 94` フルが最速とは限らず、Stage A の baseline 測定で `-t` チューニング。
- **fine-tuned GGUF の loadable 性**: LLaMA/Qwen2 は saver 除外リスト非該当なので `llama-cli` で読める見込み。読めなければ base F32 とヘッダを diff で比較。
- **1 sample の入力全展開**: `-f` は全ファイル内容をメモリに載せて 1 プロンプト扱いする。wiki.test.raw 1.3 MB は問題ないが将来大コーパスで注意。

## 想定所要時間

| フェーズ | 見積り |
|---|---|
| Step 1 (venv + pip) | 10–20 min |
| Step 2 (Stage A 変換) | 5–10 min |
| Step 2 (Stage B 変換) | 10–15 min |
| Step 3 (wikitext DL) | <1 min |
| Step 4 (Stage A baseline PPL + `-t` チューニング) | 5–15 min |
| Step 5 (Stage A fine-tune, 2 epochs) | 5–15 min |
| Step 6 (Stage A 評価) | 5–10 min |
| Step 4 (Stage B baseline PPL) | 10–20 min |
| Step 5 (Stage B fine-tune, 2 epochs) | 20–40 min |
| Step 6 (Stage B 評価) | 10–20 min |
| **合計** | **80–170 min (1.5–3 時間)** |

長時間ジョブは全て `screen -dmS <name>` でバックグラウンド化し、監視は `tail -f`。ローカルでは重いプロセスは動かさない。

## 完了後

`report/YYYY-MM-DD_HHMMSS_llama-cpp-cpu-finetune-smollm-qwen.md` にレポートを 1 本書く。CLAUDE.md / REPORT.md のフォーマットに従い、**核心発見サマリ**を先頭、PPL before/after の数値表、loss curve (可能なら PNG)、生成テキストの before/after 比較、CPU 実測時間・RAM ピーク、遭遇した落とし穴などを収める。

## Critical Files

- `/home/ubuntu/projects/llm-server-ops/src/llama.cpp/examples/training/finetune.cpp` — llama-finetune 本体
- `/home/ubuntu/projects/llm-server-ops/src/llama.cpp/examples/training/README.md` — 唯一の一次ドキュメント
- `/home/ubuntu/projects/llm-server-ops/src/llama.cpp/src/llama-context.cpp` — 学習可能パラメータ判定 (L3246)
- `/home/ubuntu/projects/llm-server-ops/src/llama.cpp/src/llama-model-saver.cpp` — 保存対応 arch 判定 (L15-36)
- `/home/ubuntu/projects/llm-server-ops/src/llama.cpp/convert_hf_to_gguf.py` — HF → F32 GGUF 変換
- `/home/ubuntu/projects/llm-server-ops/src/llama.cpp/scripts/get-wikitext-2.sh` — データ取得
- `/home/ubuntu/projects/llm-server-ops/src/llama.cpp/common/arg.cpp` — finetune CLI 引数 (L4251-4289)
- `/home/ubuntu/projects/llm-server-ops/src/llama.cpp/requirements/requirements-convert_hf_to_gguf.txt` — venv install 対象
