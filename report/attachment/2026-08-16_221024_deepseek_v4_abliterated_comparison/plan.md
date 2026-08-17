# DeepSeek-V4-Flash abliterated 版の性能劣化検証（aws-gpu01+02 RPC）

## Context

前回セッション（コミット `c95f457b`）で `unsloth/DeepSeek-V4-Flash-0731-GGUF:UD-Q4_K_XL`（144.4 GiB）を
aws-gpu01 + aws-gpu02 の 13 GPU / 200 GiB に llama.cpp RPC で分散して ctx=131072 で起動し、
pp 89.7 t/s / tg 13.6 t/s を記録した。**このサーバは現在も稼働中**。

今回は同じ土俵に `huihui-ai/Huihui-DeepSeek-V4-Flash-0731-abliterated-GGUF` の **Q4_K**（164.6 GB / 153.3 GiB、
単一ファイル）を載せ、**abliteration による性能劣化がないこと**を速度・品質の両面で確認する。

ユーザ確認済みの方針:
1. 評価軸 = **速度（t/s）と品質の両方**
2. 対照 = **現行の unsloth UD-Q4_K_XL のみ**（追加ダウンロードはしない）
3. **現行サーバを停止する前に、今回と同一手順のベンチを取り直す**（既存レポート値の流用ではなく条件を揃える）

### 比較の既知の限界（レポートに必ず明記する）

対照の unsloth UD-Q4_K_XL は Unsloth Dynamic 量子化、今回の abliterated Q4_K は `antirez/deepseek-v4-gguf` 由来の
`Q4KExperts-F16HC-F16Compressor-F16Indexer-Q8Attn-Q8Shared-Q8Out-chat-v2-imatrix` レシピで、**量子化レシピが異なる**
（サイズも 144.4 GiB vs 153.3 GiB）。したがって観測される差分は「abliteration の影響」と「量子化レシピの差」の
**合算**であり、切り分けはできない。これはユーザ了解済みの前提。

なお huihui 版 README に「all expert modules were not ablated」（expert 層は未改変、attention 等のみ ablate）とある。

---

## 現状（調査済みの事実）

| 項目 | 値 |
|---|---|
| aws-gpu01 | Tesla P100 16GB × 7 = 112 GiB / RAM 157 GiB / **disk 空き 562 GB** / SSH 名 `chungpu` |
| aws-gpu02 | 16GB × 4 + 12GB × 2 = 88 GiB / RAM 94 GiB / disk 空き 140 GB（モデル不要） |
| 現行 llama-server | aws-gpu01 で稼働中。`--rpc 192.168.100.2:50052 -ngl 999 -c 131072 --flash-attn 1 --poll 0 -b 2048 -ub 512` |
| 現行 rpc-server | aws-gpu02 で稼働中（`ggml-rpc-server -H 192.168.100.2 -p 50052`、RoCEv2 RDMA 有効） |
| 現行 VRAM 使用 | 合計 161,834 MiB（157.1 GiB）/ 200 GiB。**最小空きは gpu02 の 12GB カード（index 3,5）で約 960 MiB** |
| ロック | aws-gpu01/02 とも**前セッションの保持のまま残留**（`aws-mmns-generic-280036/280042-20260816_1635xx`） |
| 既存モデル | `~/models/DeepSeek-V4-Flash-0731-GGUF/UD-Q4_K_XL/`（5 split, 155,095,241,120 B）— 削除しない |
| 新モデル | `DeepSeek-V4-Flash-Q4_K-0731.gguf` = **164,633,502,592 B** 単一ファイル |
| 前回 DL 実測 | 155 GB を 22 分（117 MB/s） |

**VRAM の懸念**: モデルが +8.9 GiB 増える一方、余裕は約 43 GiB。全体としては入るが、
gpu02 の 12GB カードの空きが元々 1 GiB を切っており、ctx=131072 のまま起動すると OOM する可能性がある。
フォールバック手順を用意する（後述）。

---

## 作業計画

### Phase 0: 準備

1. `Skill gpu-server` を起動（CLAUDE.md の必須ルール）。
2. ロックの残留を解消して取り直す（前セッションのプロセスは終了済み・同一ユーザの継続作業のため強制解放でよい）:
   ```bash
   .claude/skills/gpu-server/scripts/lock-status.sh
   .claude/skills/gpu-server/scripts/unlock.sh aws-gpu01     # session_id 省略 = 強制解放
   .claude/skills/gpu-server/scripts/unlock.sh aws-gpu02
   SID="$(hostname)-abl-$(TZ=Asia/Tokyo date +%Y%m%d_%H%M%S)"   # 2台で同一 SID にする
   .claude/skills/gpu-server/scripts/lock.sh aws-gpu01 "$SID"
   .claude/skills/gpu-server/scripts/lock.sh aws-gpu02 "$SID"
   ```
   ※ `lock.sh` は session_id 省略時に `$$` を含むため 2 台で別 ID になる。明示指定して揃える。
3. 電源操作は**一切行わない**（爆音ガード。両機とも稼働中なので不要）。

### Phase 1: ベンチ資材の作成（ローカル）

作業ディレクトリ: `report/attachment/<timestamp>_deepseek_v4_abliterated_comparison/`
（過去の `2026-06-18_084557_mi25_vulkan_param_sweep/measure.sh` の構成を踏襲。ただし当該スクリプトは
`rocm-smi` 前提なので NVIDIA 向けに `nvidia-smi --query-gpu=index,memory.used` へ置き換えて新規作成する）

作成するもの:

| ファイル | 内容 |
|---|---|
| `prompt_1k.txt` | 約 1,200 token の固定プロンプト（前回の 1,215 tok に合わせる） |
| `prompt_19k.txt` | 約 19,000 token の固定プロンプト（前回の 19,015 tok に合わせる） |
| `mkprompt.py` | 上記 2 本の生成スクリプト（再現性確保。llama.cpp のソース or wikitext から決定論的に切り出す） |
| `quality_prompts.jsonl` | 品質評価用の固定プロンプト 8 問（日本語 3・英語 2・コード 2・長文要約 1） |
| `bench_speed.sh` | 速度計測。`/v1/chat/completions` に `cache_prompt: false` で投げ、`timings` を CSV 化 |
| `bench_quality.sh` | 品質計測。8 問 × {temp 0.0 / temp 1.0} × seed 42、`max_tokens 512`、応答と `reasoning_content` を保存 |
| `run_ppl.sh` | `llama-perplexity` を RPC 構成で実行 |

**測定条件（両モデル共通・厳密に同一）**

| 種別 | 条件 |
|---|---|
| 速度 1k | N=3、`max_tokens=128`、`cache_prompt=false`、間に 15 秒 cooldown |
| 速度 19k | N=2、`max_tokens=128`、`cache_prompt=false`（1 回 約 4 分） |
| 品質 ppl | wikitext-2-raw test、`-c 512 --chunks 40 -fa 1`（約 20k token） |
| 品質 応答 | 8 プロンプト × temp {0.0, 1.0} × `seed 42` × `max_tokens 512` |

`cache_prompt: false` は必須（既定 true のままだと 2 回目以降がキャッシュヒットして pp が無意味になる）。
採取値は `prompt_n`, `prompt_ms`, `prompt_per_second`, `predicted_n`, `predicted_per_second`。

### Phase 2: ダウンロード開始（バックグラウンド、以降と並行）

```bash
source ~/.config/gpu-server/.env
ssh -n aws-gpu01 "setsid nohup ~/.local/bin/hf download \
  huihui-ai/Huihui-DeepSeek-V4-Flash-0731-abliterated-GGUF \
  --include 'DeepSeek-V4-Flash-Q4_K-0731.gguf' \
  --local-dir ~/models/Huihui-DeepSeek-V4-Flash-0731-abliterated-GGUF \
  --token $HF_TOKEN > /tmp/hf-download-abliterated.log 2>&1 < /dev/null &"
```
- **末尾に `disown` を付けない**（前回、非対話 bash で SSH チャネルがハングした実測あり）
- 進捗は `du -sh ~/models/Huihui-.../` で監視（`monitor-download.sh` は `/home/llm/.cache/llama.cpp` 決め打ちで aws-gpu では機能しない）
- 完了判定は `stat -c %s` == **164,633,502,592**
- 単一巨大ファイルのため前回の 117 MB/s（5 ファイル並列）より遅い可能性あり。25 分〜1.5 時間を見込む
- ディスク: 562 GB → 397 GB。既存 unsloth モデルは**消さない**

### Phase 3: ベースライン計測（現行 unsloth サーバ、稼働中のまま）

1. `bench_speed.sh` を `http://10.8.2.1:8000` に対して実行 → `baseline_speed.csv`
2. `bench_quality.sh` を同エンドポイントに実行 → `baseline_responses/`
3. 実行中の VRAM を `nvidia-smi` で記録（両機）

（Phase 2 の DL と並行実行可。mmap 済みモデルへの I/O 競合は軽微だが、速度値に異常が出たら DL 完了後に再測定する）

### Phase 4: ベースライン perplexity

```bash
.claude/skills/llama-server/scripts/stop.sh aws-gpu01      # rpc-server は落とさない
ssh -n aws-gpu01 "cd ~/llama.cpp && ./build/bin/llama-perplexity \
  -m ~/models/DeepSeek-V4-Flash-0731-GGUF/UD-Q4_K_XL/DeepSeek-V4-Flash-0731-UD-Q4_K_XL-00001-of-00005.gguf \
  --rpc 192.168.100.2:50052 -ngl 999 -c 512 --chunks 40 -fa 1 \
  -f ~/data/wikitext-2-raw/wiki.test.raw"
```
- wikitext-2-raw は aws-gpu01 から直接取得（`llama.cpp/scripts/get-wikitext-2.sh` 相当。外部回線が速い）
- **DeepSeek-V4 は MoE + DSA アーキテクチャのため `llama-perplexity` が通らない可能性がある**。
  エラーで落ちた場合は ppl を諦め、品質評価は Phase 3/6 の応答比較のみに縮退する（レポートに明記）

### Phase 5: abliterated 版の起動

DL 完了・サイズ検証後、**前回と完全に同一のパラメータ**で起動する:

```bash
ssh -n aws-gpu01 'cd ~/llama.cpp && setsid nohup ./build/bin/llama-server \
  --model ~/models/Huihui-DeepSeek-V4-Flash-0731-abliterated-GGUF/DeepSeek-V4-Flash-Q4_K-0731.gguf \
  --alias DeepSeek-V4-Flash-0731-abliterated-Q4_K \
  --rpc 192.168.100.2:50052 \
  --n-gpu-layers 999 --ctx-size 131072 \
  --flash-attn 1 --poll 0 -b 2048 -ub 512 \
  --jinja --temp 1.0 --top-p 1.0 --min-p 0.01 \
  --host 0.0.0.0 --port 8000 \
  > /tmp/llama-server-abliterated.log 2>&1 < /dev/null &'
```

**完了検出は `listening on`（成功）と `error|out of memory|terminate`（失敗）に限定する。**
`W common_fit_params: ... abort` は正常時にも出る警告なので、これを失敗と誤判定しないこと
（前回この誤判定で llama-server を二重起動しかけた）。

**OOM 時のフォールバック（この順で試す）**
1. `--ctx-size 65536` → だめなら `32768`
   （前回 ctx 32k↔128k で速度差がないことを確認済みなので、速度比較への影響は最小）
2. `--tensor-split` で gpu02 の 12GB カード（RPC デバイス index 3,5）の割当を下げる
3. `--cache-type-k q8_0 --cache-type-v q8_0`（KV 圧縮。ベースラインと条件が変わるため最後の手段）

ctx を下げた場合、**ベースライン側の ppl / 応答比較の条件は影響を受けない**が、速度計測は
ctx 非依存であることを前回結果とともにレポートで説明する。

### Phase 6: abliterated 版の計測

Phase 3 とまったく同じ `bench_speed.sh` / `bench_quality.sh` を実行し、
`abliterated_speed.csv` / `abliterated_responses/` を得る。
perplexity は llama-server 起動前（Phase 5 の直前）に Phase 4 と同一条件で実施する。

### Phase 7: 比較・レポート

判定基準（目安）:
- **速度**: pp / tg とも**ベースライン比 −5% 以内**なら「劣化なし」。それを超える場合は VRAM 配分・ctx 差など要因を切り分ける
- **品質(ppl)**: 両者の PPL を併記。量子化レシピが違うため単純な優劣判定はせず、**同オーダーであることの確認**に留める
- **品質(応答)**: 8 問 × 2 温度の出力を目視比較し、指示追従・言語一貫性・繰り返し崩壊・thinking の有無をチェック。
  temp 0.0 の出力は決定論的なので diff を添付する

成果物:
- `report/<TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S>_deepseek_v4_abliterated_comparison.md`
  - REPORT.md 準拠。H1 は 50 字以内の平易な日本語、メタ情報 3 行（作成者 = `Claude Opus 5`）、
    `## 概要`（5〜8 段落・平易な日本語）を最上位に置く
  - `## 核心発見サマリ` 冒頭に比較 PNG を画像埋め込み（pp/tg 棒グラフ + ppl）
  - `## 環境情報` / `## 再現方法` / `## 結果詳細` / `## 残課題`
  - **比較の限界（量子化レシピ差）を明示**
- `report/attachment/<同名>/` に plan.md・全ログ・CSV・スクリプト・PNG・`mkfig.py`
- `report/INDEX.md` に 1 行追加
- 添付は **Git LFS を使わず通常の git 管理**。100 MB 超になるログは `gzip`

### Phase 8: 後始末

- abliterated 版の llama-server は**起動したまま残す**（前回セッションと同様の運用。ユーザが不要と言えば `stop.sh` → `rpc-down.sh` の順で停止）
- ロックは保持したまま引き継ぐか、停止する場合のみ `unlock.sh aws-gpu01 "$SID"` / `aws-gpu02 "$SID"`
- 電源は触らない

---

## 触れてはいけないもの

- `/home/myzk` `/home/sizumita`（他ユーザ領域、現在未使用だが削除しない）
- 既存の `~/models/DeepSeek-V4-Flash-0731-GGUF/UD-Q4_K_XL/`（対照モデル。検証完了まで残す）
- aws-gpu01/02 の電源（`ALLOW_FAN_NOISE=1` を要するものは一切実行しない）
- llama.cpp の再ビルド（両機とも `10bf611e5` / build 10451 で一致済み。RPC はバージョン一致必須なので触らない）

## 検証（このタスク自体の完了確認）

1. `stat -c %s` が 164,633,502,592 と一致すること
2. `curl http://10.8.2.1:8000/v1/models` が `DeepSeek-V4-Flash-0731-abliterated-Q4_K` を返すこと
3. `baseline_speed.csv` と `abliterated_speed.csv` が同一条件（プロンプト長・N・max_tokens）で揃っていること
4. 両モデルの応答が 8 問すべてで欠損なく取得できていること
5. レポートが REPORT.md のセクション要件（`## 概要` を先頭に置く等）を満たし、INDEX.md に登録されていること
