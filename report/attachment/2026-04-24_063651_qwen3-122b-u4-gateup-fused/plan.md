# Phase U-4: gate/up fused GGUF (PR #19139) の変換・量子化・ベンチ

## Context

**背景**: Phase T 系列後ロードマップの Cycle 89 = Phase U-4。直前の Phase U-2 (cache-ram) で TTFT -98% を確定し cache-ram 軸は完結、本 Phase では llama.cpp PR #19139 (`--fuse-gate-up-exps`) による MoE gate/up 重み融合が Qwen3.5-122B-A10B + P100×4 hetero (B14b_ts_alt) 構成で PP (prompt t/s) を +5〜12% 押し上げるかを検証する。Qwen3-Next 実測で +12% が報告済。

**現状**:
- 既存 GGUF (`unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`) は融合なし、T-5a-ts2 で eval 18.664 t/s baseline を持つ
- **HF 本家 (`Qwen/Qwen3.5-122B-A10B`, BF16 safetensors) から取得し、local で convert → quantize → remote 転送** する必要がある
- 現ビルド `6217b4958` に PR #19139 (`b68d75165`) + fix PR #20416 (`4a748b8f1`) 両方マージ済 (確認済)
- `--fuse-gate-up-exps` は `convert_hf_to_gguf.py` の CLI フラグ (`llama-quantize` ではない点に注意)
- Local (aws-mmns-generic): 2.0 TB total, **1.6 TB free**、llama.cpp/HF CLI 未インストール、31 GB RAM、32 CPU
- Remote (t120h-p100): 548 GB total, **121 GB free** (既存 unsloth GGUF 72 GB 含む)
- 既存 unsloth GGUF は **U-4 で新 GGUF を B14b 構成で確認後に削除判断** (ベンチ期間中は温存)
- 融合後のテンソル名は `ffn_gate_up_exps.weight` (`ffn_gate_exps` と `ffn_up_exps` を dim=1 concat)

**目的**:
1. `Qwen/Qwen3.5-122B-A10B` を HF から DL → `--fuse-gate-up-exps` 付きで GGUF 変換 → Q4_K_M 量子化
2. 旧 unsloth GGUF vs 新 fused GGUF の **eval_tps / prompt_tps** 比較 (B14b_ts_alt 構成固定)
3. PP +5〜12% の再現確認、TG (eval) は誤差範囲 (±1%) 想定
4. 3 prompt (prompt_1k / prompt_code / prompt_repetitive) × (warmup 2 + eval 5) で測定

## ロードマップ整合性

本 Phase は memory `project_t_series_roadmap` の **Cycle 89 = Phase U-4** に相当。U-1 (spec ckpt baseline)、U-1-ext (spec ckpt relaxed で負方向確定、U-3 skip)、U-2 (cache-ram で TTFT -98%) に続く系列最終 Phase。

## 重要な技術前提

### `-ot` 正規表現と融合テンソルの互換性

現構成 `-ot 'blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU'` は `ffn_.*_exps\.weight` 部分がグリーディマッチのため **融合後の `ffn_gate_up_exps.weight` も自動的にマッチ**する (`.*` = `gate_up`)。また `ffn_down_exps.weight` は従来通りマッチ。**正規表現の変更は不要**。

### 融合の挙動 (`convert_hf_to_gguf.py` l.548 以降)

```python
if bid in self._gate_exp_buffer and self._up_exp_buffer:
    fused_data = torch.cat([gate_data, up_data], dim=1)  # (n_expert, n_ff*2, n_embd)
    fused_name = format_tensor_name(gguf.MODEL_TENSOR.FFN_GATE_UP_EXP, bid)
```

量子化段階では融合テンソルをそのまま `llama-quantize` に渡せば Q4_K_M が適用される。

### ディスク収支 (local)

| 段階 | 累積ピーク使用量 | 備考 |
|------|-----------------:|------|
| 1. DL 完了 (safetensors) | ~244 GB | |
| 2. 変換完了 (BF16 GGUF 追加) | ~488 GB | safetensors + BF16 両方存在 |
| 3. 量子化完了 (Q4_K_M 追加) | ~563 GB | 244 + 244 + 75 |
| 4. 転送完了 + BF16/safetensors 削除 | ~75 GB (Q4_K_M のみ保持) | 必要なら Q4_K_M も削除可 |

1.6 TB 余裕内だが、step 3 終了時点で safetensors を削除しておけば一時的に **319 GB ピーク** に抑えられる。

### ディスク収支 (remote)

| 段階 | 使用量 | 残 | 備考 |
|------|-------:|---:|------|
| 現状 (unsloth 温存) | 400 GB | 121 GB | |
| 新 Q4_K_M 転送 (~75 GB) | 475 GB | 46 GB | ベンチ期間中 |
| ベンチ完了後、旧 unsloth 削除 | 403 GB | 118 GB | U-4 完了後判断 |

**46 GB 残はギリギリだが稼働には問題なし** (llama-server 側で追加ディスク書込は無い)。

## 実装計画

### 1. Local 環境準備

- **llama.cpp clone + build** (`~/llama.cpp`)
  - `git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp && cd ~/llama.cpp && git checkout 6217b4958`
  - `cmake -B build -DGGML_CUDA=OFF && cmake --build build --target llama-quantize -j 32` (量子化に CUDA 不要、CPU のみビルド)
- **python 依存**: `pip install -r ~/llama.cpp/requirements/requirements-convert_hf_to_gguf.txt` (torch CPU 版、transformers、sentencepiece、etc.)
- **HF CLI**: `pip install "huggingface_hub[cli]"` (resume 可能 DL 用)
- **HF_TOKEN**: `Qwen/Qwen3.5-122B-A10B` は通常 non-gated だが、念のため既存 `~/.huggingface/token` or `HF_TOKEN` env を確認。未設定なら `huggingface-cli login` を **ユーザに実行依頼** (対話入力必要)
- **cmake 未導入**: `sudo apt install cmake` → **ユーザに実行依頼** (sudo)

### 2. DL (`Qwen/Qwen3.5-122B-A10B`)

- 保存先: `~/models/Qwen3.5-122B-A10B-hf/`
- `huggingface-cli download Qwen/Qwen3.5-122B-A10B --local-dir ~/models/Qwen3.5-122B-A10B-hf --resume-download` を **tmux session で Monitor 起動**
- 注意事項 (memory 由来):
  - 回線が細いため **数時間〜半日単位** の DL を想定、進捗が遅く見えても誤判断しない
  - 中断時は同コマンドで resume 可能
  - DL 中は他 Phase 並行実施せず、local IO を優先
- 完了判定: `~/models/Qwen3.5-122B-A10B-hf/config.json` と全 `*.safetensors` が揃うこと、および `du -sh` で ~244 GB 到達

### 3. GGUF 変換 (`--fuse-gate-up-exps`, BF16)

```bash
cd ~/llama.cpp
python3 convert_hf_to_gguf.py \
  --outtype bf16 \
  --fuse-gate-up-exps \
  --outfile ~/models/Qwen3.5-122B-A10B-BF16-fused.gguf \
  ~/models/Qwen3.5-122B-A10B-hf
```

- ログに `Fused gate_exps and up_exps for layer N` が 62 層 (Qwen3.5-122B の layer 数) 分表示されること
- BF16 GGUF サイズ ~244 GB、lazy loading + single-thread で **1〜2 時間想定** (RAM 31 GB で安全)

### 4. 量子化 (Q4_K_M)

```bash
~/llama.cpp/build/bin/llama-quantize \
  ~/models/Qwen3.5-122B-A10B-BF16-fused.gguf \
  ~/models/Qwen3.5-122B-A10B-Q4_K_M-fused.gguf \
  Q4_K_M 32
```

- 32 threads 指定、~30〜60 分想定
- 出力 ~75 GB
- **imatrix は使用しない** (unsloth 版との比較のため条件を揃える; unsloth Q4_K_M が imatrix 使用か不明だが、本 Phase は stock Q4_K_M で比較、差は PP 側で明瞭に出る想定)

### 5. Remote 転送

```bash
rsync -avP --inplace ~/models/Qwen3.5-122B-A10B-Q4_K_M-fused.gguf \
  t120h-p100:/home/llm/.cache/huggingface/hub/Qwen3.5-122B-A10B-Q4_K_M-fused.gguf
```

- 保存先は HF cache 外の一時パスで OK (既存 unsloth と混同しない)
- ~75 GB 転送、同 LAN Gigabit で **15〜30 分**想定
- 転送後、local の BF16 GGUF と safetensors を削除してディスク回復 (`rm ~/models/Qwen3.5-122B-A10B-BF16-fused.gguf` および `rm -rf ~/models/Qwen3.5-122B-A10B-hf`)

### 6. 新 GGUF で llama-server 起動確認

- skill `gpu-server` で t120h-p100 ロック取得
- B14b_ts_alt 構成で llama-server 起動 (固定オプション: `-ngl 999 -ot '...' -ts 11,12,13,14 --split-mode layer --flash-attn 1 --poll 0 -b 256 -ub 256 --ctx-size 32768 --parallel 1 --cache-type-k q8_0 --cache-type-v q8_0 --threads 40`)
- モデルパスのみ新 Q4_K_M-fused に差し替え、それ以外は Phase T-5a-ts2 / U-2 と完全同一
- startup log で融合テンソル `ffn_gate_up_exps.weight` が認識されることを確認 (テンソル一覧に `blk.X.ffn_gate_up_exps.weight` が出ること)

### 7. ベンチマーク (旧 unsloth vs 新 fused、3 prompt × 5 run)

- 既存 measure script (`measure_phaseT5.sh` or similar) を流用、marker 付き eval (cache miss 強制)
- 3 prompt: `prompt_1k.txt` / `prompt_code.txt` / `prompt_repetitive.txt` (U-1 / U-2 で使用したものと同一)
- 各モデル: warmup 2 + eval 5 runs
- 記録項目: `prompt_ms`, `predicted_per_second`, `prompt_n`, `timings.prompt_per_second`
- 測定順序は **ABAB** (unsloth → fused → unsloth → fused)、環境 drift を相殺
- **eval_tps** と **prompt_tps** の median, mean, stdev を抽出

### 8. 分析・レポート

- CSV 集計 + matplotlib bar chart 2 枚 (prompt_tps / eval_tps × 3 prompt × 2 model)
- 判定基準:
  - **PP (prompt_tps)**: fused vs unsloth で **+5% 以上** なら PR #19139 効果再現と判定
  - **TG (eval_tps)**: **±1.5%** 以内なら誤差範囲
- レポート: `report/<timestamp>_qwen3-122b-u4-gateup-fused.md`
  - **タイトル 50 字以内**: `Phase U-4: gate/up fused GGUF で PP +X%` 的簡潔形
  - **核心発見サマリ** セクション冒頭に PNG 画像埋め込み (`![prompt_tps_compare](...)` の形)
  - **未検証事項** (`## ` 独立見出し)
  - **検証完了後に実施すべき TODO** (`## ` 独立見出し)
  - プラン添付: `report/attachment/<name>/plan.md`
  - DL 失敗・中断があればその経緯も記録

### 9. 事後処理

- 旧 unsloth GGUF 削除判断: 新 fused で eval ±1.5% 以内 + PP +5% 以上確認できたら remote から削除可 (ユーザに確認後)
- memory `project_t_series_roadmap` を更新: U-4 完了、T 系列後ロードマップ全体終了、次の feature 軸 (未定) へ
- Discord 通知 (skill `discord-notify`) でレポート URL 投稿

## 主要ファイル・スクリプト (新規作成/利用)

- **既存 (再利用)**:
  - `convert_hf_to_gguf.py` (`--fuse-gate-up-exps` 実装: l.120, l.139, l.548-568, l.13407-13413)
  - `llama-quantize` (build/bin/)
  - Phase T/U 系列の `measure_phaseT5.sh` (measure script テンプレ、3-prompt eval)
  - skill `gpu-server/scripts/lock.sh`, `unlock.sh`
  - skill `llama-server/scripts/start.sh` (要らないなら直接 llama-server 起動コマンドを使う)
- **新規作成**:
  - `report/attachment/<name>/start_phaseU4.sh` — llama-server 起動 (モデルパス可変)
  - `report/attachment/<name>/measure_phaseU4.sh` — 3-prompt × 5-run eval、ABAB 順
  - `report/attachment/<name>/batch_U4.sh` — モデル切替 + 起動 + 測定 + 停止の一連フロー
  - `report/attachment/<name>/analyze_phaseU4.py` — CSV 集計 + PNG 生成

## 検証方法 (エンドツーエンド)

1. **DL 完了検証**: `ls -lh ~/models/Qwen3.5-122B-A10B-hf/` で safetensors 全数揃い、`du -sh` で ~244 GB
2. **変換検証**: `~/llama.cpp/build/bin/llama-gguf-split --metadata <BF16-fused> | grep gate_up` でテンソル存在確認 (または `gguf_dump.py` が使えるなら使用)
3. **量子化検証**: `file ~/models/Qwen3.5-122B-A10B-Q4_K_M-fused.gguf` で GGUF と認識、サイズ ~75 GB
4. **起動検証**: llama-server 起動後 `curl -s http://10.1.4.14:8000/props | jq '.chat_template'` で chat template 取得成功 + `/metrics` で `kv_cache_tokens_used` 取れること
5. **機能検証**: 簡易 curl で `/v1/chat/completions` に `"Hello"` 投げて応答生成、`usage.completion_tokens > 0` 確認
6. **ベンチ検証**: 各 prompt で 5 run stdev < 0.05 t/s (B14b_ts_alt の安定性基準)、marker 付き payload で cache miss 強制、`cache_n=0` 確認
7. **PP 効果判定**: fused の prompt_tps median が unsloth に対し **+5% 以上** → PR #19139 効果確認

## リスク・注意

- **HF token gate**: 万一 `Qwen/Qwen3.5-122B-A10B` が gated (Llama-3 系と同じ運用) なら `huggingface-cli login` 必要。事前確認。
- **DL 中断**: resume 対応済だが、念のため tmux session で維持し ssh 切断で死なせない
- **RAM 31 GB**: convert の lazy loading で OK だが、torch が eager モード選ぶ layer があれば OOM 可能性。`--use-temp-file` が lazy と排他なので使わない
- **cmake 未導入**: ユーザに `sudo apt install cmake` を依頼
- **imatrix 不使用の妥当性**: 本 Phase は融合効果の測定が主目的、imatrix 差は別軸 (将来 Phase で分離比較)
- **Local IO 占有**: 250+ GB の書込で他作業の応答遅延、DL/変換中は他 Phase 並行実施しない
- **時間見積り**: DL 数時間〜半日 + 変換 1〜2h + 量子化 0.5〜1h + 転送 0.5h + ベンチ 1h = **合計 1 日仕事**の可能性
