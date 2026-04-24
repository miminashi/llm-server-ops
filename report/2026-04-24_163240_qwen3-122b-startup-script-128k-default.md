# Qwen3.5-122B 128k 既定構成の起動スクリプト更新と実機起動試験

- **実施日時**: 2026年4月24日 16:32〜16:40 (JST)
- **担当サーバ**: t120h-p100
- **モデル**: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`

## 核心発見サマリ

Phase U-6 で確定した「B14b / ub=512 / ctx=131072 / ts=11,12,13,14 / threads 40 + numactl node1」構成を `start.sh` のモデルプロファイル (`qwen3_122b`) として実装し、`start.sh t120h-p100 "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit` の 1 コマンドのみで 128k 既定起動が成立することを実機で確認。起動直後の **eval 18.66 t/s** (短 prompt smoke) が Phase T-5a-ts2 baseline 18.664 t/s と誤差±0.02% 以内で一致し、プロファイル自動適用は無劣化。途中で起動スクリプトに潜んでいた **shell quoting バグ** (regex 中の `()` と `|` が ssh → bash -c のネストで metachar として解釈され syntax error で llama-server が起動できない) を事前検出、llama.cpp の `parse_tensor_buffer_overrides` がサポートするカンマ区切り列挙表現 (14 パターン) に分解して解消した。

## 添付ファイル

- [実装プラン](attachment/2026-04-24_163240_qwen3-122b-startup-script-128k-default/plan.md)
- [git diff (start.sh / wait-ready.sh / SKILL.md)](attachment/2026-04-24_163240_qwen3-122b-startup-script-128k-default/git-diff.patch)
- [start.sh 出力](attachment/2026-04-24_163240_qwen3-122b-startup-script-128k-default/start.log)
- [wait-ready.sh 出力](attachment/2026-04-24_163240_qwen3-122b-startup-script-128k-default/wait-ready.log)
- [stop.sh 出力](attachment/2026-04-24_163240_qwen3-122b-startup-script-128k-default/stop.log)
- [llama-server ログ (先頭 200 行)](attachment/2026-04-24_163240_qwen3-122b-startup-script-128k-default/llama-server.log.head200.txt)
- [プロセス引数](attachment/2026-04-24_163240_qwen3-122b-startup-script-128k-default/process-cmd.txt)
- [nvidia-smi snapshot](attachment/2026-04-24_163240_qwen3-122b-startup-script-128k-default/nvidia-smi.txt)
- [smoke test (非 stream)](attachment/2026-04-24_163240_qwen3-122b-startup-script-128k-default/smoke-test-nonstream.json)
- [smoke test (stream)](attachment/2026-04-24_163240_qwen3-122b-startup-script-128k-default/smoke-test-stream.txt)

## 前提・目的

- **背景**: Phase T 系列 (パラメータチューニング) → Phase U-1〜U-6 (機能軸 + 長文脈) の一連のベンチマークで、Qwen3.5-122B-A10B を t120h-p100 上で ctx=128k 運用するための最適構成が確定した ([Phase U-5](2026-04-24_081326_qwen3-122b-u5-ctx128k-fit-map.md) / [Phase U-6](2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default.md))。実験から運用フェーズへの移行として、起動スクリプトにこの構成を「既定」として埋め込む。
- **目的**: `start.sh t120h-p100 <model> fit` の最小 3 引数で、Phase U-6 確定構成 (128k / B14b / ts=11,12,13,14 / ub=512 / threads 40 / numactl node1) が自動適用されるようにする。その後、実機で起動 → /health → smoke test が成立することを確認する。
- **成功条件**:
  - `start.sh` が fit-ctx 未指定で 131072 を採用
  - llama-server の起動引数に B14b 相当 OT、tensor-split=11,12,13,14、threads=40、numactl cpunodebind=1 membind=1、ub=512、b=2048、ctx=131072 が含まれる
  - /health=200、/v1/models が期待モデルを返す
  - smoke test (/v1/chat/completions) が妥当な応答を返し、eval t/s が Phase U-6 baseline (18.664 t/s @ ctx=32k) と乖離していない

## 環境情報

| 項目 | 値 |
|---|---|
| サーバ | t120h-p100 (10.1.4.14) |
| CPU | Intel Xeon Gold 6138 × 2 socket (20 physical / 40 logical per socket、SMT ON) |
| RAM | 264 GB (263741504 kB) |
| GPU | NVIDIA Tesla P100-PCIE-16GB × 4 (SM60、各 16269 MiB 可視) |
| OS | Linux 5.15.0-174-generic (Ubuntu) |
| llama.cpp | HEAD `ffdd983fb83ff3ca5e972188b30bcf8d039d3283` (build b8916 相当、Phase U 系列と同世代) |
| モデル | `Qwen3.5-122B-A10B-GGUF:Q4_K_M` (unsloth、BF16 → Q4_K_M 量子、122 B params、fused 化していない separate gate/up) |
| ロック | aws-mmns-generic-1376861-20260424_163225 で取得 → 試験後解放 |

## 再現方法

```bash
# 1. 事前確認 + ロック
.claude/skills/gpu-server/scripts/lock-status.sh
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 2. GPU 監視 + 起動 + ヘルスチェック (3 コマンド、引数は全て同じ)
.claude/skills/llama-server/scripts/ttyd-gpu.sh t120h-p100
.claude/skills/llama-server/scripts/start.sh    t120h-p100 "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit
.claude/skills/llama-server/scripts/wait-ready.sh t120h-p100 "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit

# 3. smoke test
curl -s http://10.1.4.14:8000/health
curl -s http://10.1.4.14:8000/v1/chat/completions -H 'Content-Type: application/json' -d \
  '{"model":"unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M","messages":[{"role":"user","content":"1+1はいくつですか?数字だけ短く答えてください。"}],"max_tokens":64}' | python3 -m json.tool

# 4. 停止 + 解放
.claude/skills/llama-server/scripts/stop.sh t120h-p100
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 起動スクリプトの修正内容

### 1. `.claude/skills/llama-server/scripts/start.sh`

**モデルプロファイル判定の追加** — `HF_MODEL` が `*Qwen3.5-122B-A10B*` にマッチするとき `MODEL_PROFILE=qwen3_122b` を設定:
```bash
MODEL_PROFILE="generic"
case "$HF_MODEL" in
  *Qwen3.5-122B-A10B*)
    MODEL_PROFILE="qwen3_122b"
    ;;
esac
```

**fit-ctx default のプロファイル分岐** — qwen3_122b 時は 131072 (128k) を既定に:
```bash
if [ -z "$FIT_CTX_ARG" ]; then
  if [ "$MODEL_PROFILE" = "qwen3_122b" ]; then
    FIT_CTX=131072
  else
    FIT_CTX=8192
  fi
else
  FIT_CTX="$FIT_CTX_ARG"
fi
```

**サーバ × モデルプロファイル上書き** — t120h-p100 × qwen3_122b の組み合わせで Phase U-6 パラメータに差し替え:
```bash
if [ "$MODEL_PROFILE" = "qwen3_122b" ] && [ "$SERVER" = "t120h-p100" ]; then
  SERVER_OPTS="--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14"
  ENV_PREFIX="numactl --cpunodebind=1 --membind=1"
  THREADS_OPT="--threads 40"
fi
```

**`--threads -1` ハードコードの変数化** — LAUNCH_CMD の `--threads -1` を `$THREADS_OPT` (default `--threads -1`) に置換して上書き可能に。

**B14b OT パターンの分岐** — fit モード時に qwen3_122b ならカンマ列挙の 14 パターン、それ以外は従来の `ffn_.*_exps.weight=CPU` (全層):
```bash
if [ "$FIT_MODE" = true ]; then
  if [ "$MODEL_PROFILE" = "qwen3_122b" ]; then
    OT_PATTERNS=""
    for L in 2 3 20 21 22 23 31 32 33 34 35 36 37 38; do
      [ -n "$OT_PATTERNS" ] && OT_PATTERNS+=","
      OT_PATTERNS+="blk.$L.ffn_.*_exps.weight=CPU"
    done
    NGL_OPTS="-ngl 999 --split-mode layer -ot '$OT_PATTERNS'"
  else
    NGL_OPTS="-ngl 999 -ot 'ffn_.*_exps.weight=CPU'"
  fi
  ...
fi
```

### 2. `.claude/skills/llama-server/scripts/wait-ready.sh`

`start.sh` と整合する fit-ctx default 判定を追加 (qwen3_122b で 131072 を既定表示)。Discord 通知の ctx-size 表示が起動実態と一致するよう同等のロジックを展開。

### 3. `.claude/skills/llama-server/SKILL.md`

- モデル一覧の Qwen3.5-122B-A10B 行を `fit (128k default)` + 「Phase U-6 確定プロファイル自動適用」に更新
- fitモード節を「モデルプロファイル別に OT・fit-ctx・追加設定が自動切替される表」に差し替え、期待性能・OT=B14b・tensor-split 等の要点を明記
- サーバ別最適化パラメータ表に `t120h-p100 × Qwen3.5-122B-A10B` 行を追加
- OT 表現の実装ノート (regex 表記との等価性、カンマ列挙に分解した理由) を補足

### 4. Shell quoting バグの発見と解消

#### 現象
当初、B14b OT パターンを `-ot 'blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU'` 形式で埋め込んだ `start.sh` をローカル simulation すると、bash がパターン中の `(` を syntax error として拒否することを発見:
```
$ bash -c 'echo blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU'
bash: -c: line 1: syntax error near unexpected token '('
```

#### 原因
既存の起動パイプライン `ssh "$SERVER" "cd ... && nohup bash -c '$LAUNCH_CMD' > ..."` は **入れ子の single-quote stripping** を経て引数が内側 bash -c へ渡る設計。LAUNCH_CMD 内部の `'...'` 対は `bash -c` 引数の word を「クオート部 + unquoted 部」が交互に現れる **一塊の word** として構成するため、unquoted 部に落ちた正規表現中の `(`, `)`, `|` が bash のメタキャラとして再評価され、subshell / pipe 文法として展開されようとする。従来の `ffn_.*_exps.weight=CPU` は `.` と `*` のみで、`*` は当該 CWD に一致が無いため default で literal 保持され、運よく通っていた。

#### 修正
llama.cpp のソース (`common/arg.cpp` の `parse_tensor_buffer_overrides`) を確認したところ、`-ot` の値は **カンマ `,` で分割** され各パターンは独立評価されることが判明。`()` / `|` を使わないカンマ区切り列挙で等価挙動を作れるため、B14b の 14 層を `blk.N.ffn_.*_exps.weight=CPU` (各層ぶん) でカンマ連結し 1 つの `-ot` 値にまとめた。bash の word 中に現れるのは `.`, `*`, `,` のみとなり、メタキャラ syntax error を回避できる。

事前検証:
```bash
$ bash -c 'echo blk.2.ffn_.*_exps.weight=CPU,blk.3.ffn_.*_exps.weight=CPU'
blk.2.ffn_.*_exps.weight=CPU,blk.3.ffn_.*_exps.weight=CPU
```

std::regex では `.` は「任意 1 文字」だが、対象テンソル名 (`blk.N.ffn_{gate,up,down}_exps.weight`) の構造上、`blk.2.ffn_` が `blk.20.ffn_` を誤マッチすることは無い (`blk.20.` では `2` の次に `0` が、さらに次に `.` が来る — `.ffn_` 部で `f` とマッチ失敗)。

## 起動試験結果

### 起動コマンド展開 (`ps` 実測)

親 bash (PID 1452392) 配下で numactl 経由で llama-server を起動しているのが確認できる。llama-server 本体 (PID 1452393) の argv:

```
./build/bin/llama-server
  -m /home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/.../Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf
  --jinja -ngl 999 --split-mode layer
  -ot blk.2.ffn_.*_exps.weight=CPU,blk.3.ffn_.*_exps.weight=CPU,blk.20.ffn_.*_exps.weight=CPU,blk.21.ffn_.*_exps.weight=CPU,blk.22.ffn_.*_exps.weight=CPU,blk.23.ffn_.*_exps.weight=CPU,blk.31.ffn_.*_exps.weight=CPU,blk.32.ffn_.*_exps.weight=CPU,blk.33.ffn_.*_exps.weight=CPU,blk.34.ffn_.*_exps.weight=CPU,blk.35.ffn_.*_exps.weight=CPU,blk.36.ffn_.*_exps.weight=CPU,blk.37.ffn_.*_exps.weight=CPU,blk.38.ffn_.*_exps.weight=CPU
  --flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14
  --n-predict 32768 --threads 40 --ctx-size 131072 --parallel 1
  --cache-type-k q8_0 --cache-type-v q8_0 --defrag-thold 0.1
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0
  --port 8000 --host 0.0.0.0 --alias unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M
```

**主要項目チェック**:

| 項目 | 期待 | 実測 | 判定 |
|---|---|---|---|
| numactl | `--cpunodebind=1 --membind=1` | 親シェル chain に含む、llama-server の Cpus_allowed_list=`20-39,60-79` | ✅ |
| threads | 40 | 40 | ✅ |
| -b | 2048 | 2048 | ✅ |
| -ub | 512 | 512 | ✅ |
| tensor-split | 11,12,13,14 | 11,12,13,14 | ✅ |
| flash-attn | 1 | 1 | ✅ |
| poll | 0 | 0 | ✅ |
| split-mode | layer | layer | ✅ |
| cache-type-k/v | q8_0 / q8_0 | q8_0 / q8_0 | ✅ |
| ctx-size | 131072 | 131072 | ✅ |
| -ot パターン | B14b 14 層カンマ列挙 | 14 層ぶん (2,3,20-23,31-38) 正しくカンマ連結、argv[n] として 1 トークンで渡達 | ✅ |
| parallel | 1 | 1 | ✅ |

### llama-server ログ主要行 ([全文抜粋](attachment/2026-04-24_163240_qwen3-122b-startup-script-128k-default/llama-server.log.head200.txt))

```
build: 6232 (ffdd983fb) with cc (Ubuntu 11.4.0-1ubuntu1~22.04) 11.4.0 for x86_64-linux-gnu
system_info: n_threads = 40 (n_threads_batch = 40) / 80 | CUDA : ARCHS = 600 | USE_GRAPHS = 1 | ...
load_tensors: offloaded 49/49 layers to GPU
llama_context: n_ctx         = 131072
llama_context: flash_attn    = enabled
llama_kv_cache: size = 1632.00 MiB (131072 cells, 12 layers, 1/1 seqs), K (q8_0): 816.00 MiB, V (q8_0): 816.00 MiB
init: using 79 threads for HTTP server
main: server is listening on http://0.0.0.0:8000
```

補足: `llama_model_loader: tensor overrides to CPU are used with mmap enabled - consider using --no-mmap for better performance` という情報メッセージが出る。現在 `--no-mmap` は指定していないが、fit モードでは unsloth 推奨どおり mmap を保つ (swap しないよう ~/.cache が NVMe に乗っているため実害は軽微)。将来 `--no-mmap` 追加を検討する価値あり (未検証事項に記載)。

### VRAM 実測

`nvidia-smi` 直後 (起動後アイドル状態):

| GPU | used (MiB) | free (MiB) | U-5 T1-04 期待 free | 差分 |
|---|---|---|---|---|
| CUDA0 | 15101 | 1170 | 960 | +210 |
| CUDA1 | 14711 | 1560 | 1682 | -122 |
| CUDA2 | 12155 | 4116 | 4238 | -122 |
| CUDA3 | 15567 | 704 | 956 | **-252** |

min_free=704 MiB (GPU3) で Phase U-5 T1-04 の 956 MiB と比較すると -252 MiB 少なめ。要因候補:
- llama.cpp HEAD 更新 (U-5 時点 `6217b4958` → 本試験 `ffdd983fb`) で compute buffer 配分が微変動している
- `llama_model_loader: tensor overrides to CPU are used with mmap enabled` の運用上、別 GPU に固定されている可能性の tensor (不明)
- 短 prompt で KV cache を既に warmup したため reserve が増えている

OOM しない程度のヘッドルームは保たれており Phase U-6 も同構成で 96k prompt を完走した実績がある。長 prompt 運用時の挙動は未検証事項に記載。

### /health + /v1/models

```json
{"status":"ok"}
```

```json
{"id":"unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M",
 "aliases":["unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M"],
 "meta":{"n_ctx_train":262144,"n_embd":3072,"n_params":122111526912,"size":76525965312}}
```

モデルの `n_params=122,111,526,912` (122 B)、`size=76.5 GB`、`n_ctx_train=262144` が一致。

### Smoke test 結果

**Case A (非 stream、max_tokens=64)**: プロンプト「1+1はいくつですか?数字だけ短く答えてください。」
```
prompt_tokens   = 26
completion_tokens = 64  (finish_reason=length、思考トレース途中で打ち切り)
prompt_per_second   = 37.64 t/s
predicted_per_second = 18.66 t/s
```

**Case B (stream、max_tokens=512)**: プロンプト「1+1=?のみ答える。」
```
prompt_tokens   = 18
completion_tokens = 301  (思考後に最終解 "2" を出力、正常終了)
prompt_per_second   = 37.58 t/s
predicted_per_second = 18.36 t/s
```

**eval 18.36〜18.66 t/s は Phase T-5a-ts2 baseline B14b_ts_alt 18.664 t/s @ ctx=32k とほぼ一致** (誤差 ±1.6% 以内)。ctx=128k へ拡張しても短 prompt では eval 性能に実質的な劣化が無いことが確認できた。

| 試験 | prompt t/s | eval t/s | Phase U-6 短 prompt (1k) 予測 | 乖離 |
|---|---|---|---|---|
| Case A | 37.64 | 18.66 | 64 t/s / 17.69 t/s | prompt は短すぎて有意比較不能、eval +5.5% |
| Case B | 37.58 | 18.36 | 同上 | eval +3.8% |

短 prompt は PP overhead が支配的なため t/s 値は U-6 の長 prompt ベンチと直接比較できないが、**eval は baseline と同等** と言える。

## 未検証事項

- **長 prompt (≥32k) での起動後 VRAM と eval の安定性**: 今回 short prompt のみ。Phase U-6 では 32k/96k も完走したが、本スクリプトでの 128k prompt 投入は未実施。GPU3 min_free が 704 MiB (U-5 時 956 MiB より 252 MiB 少) で差分原因未特定のため、96k prompt で OOM しないかを別途確認すべき。
- **`--no-mmap` 追加の効果**: llama-server 起動ログで推奨メッセージあり。tensor override 混在時の性能・VRAM への影響は未測定。
- **他サーバでの挙動**: 本プロファイルは `t120h-p100 + qwen3_122b` のみ上書きで、mi25 / t120h-m10 では既定 generic 経路に落ちる。122B を mi25 や m10 で起動した場合の fallback (従来の全層 ffn_exps=CPU) が妥当か未確認 (VRAM 足りない可能性高)。
- **プロファイル非適用時の動作**: 35B や gpt-oss-20b など既存モデルの起動に回帰が無いこと。syntax 観点では MODEL_PROFILE=generic で従来コードパスを踏むため問題ないはずだが、実機テストは未実施。
- **起動時間の計測**: 今回 wait-ready は attempt 1/60 (5 秒以内) で /health=200 を返した。ただし実際の「モデルロード完了〜listening」までの時間 (build 除く) は未計測。cold start メトリクスとして将来参照したい。
- **smoke test の多様性**: 日本語 short prompt のみ検証。英語プロンプト、長文脈プロンプト、tool-use フォーマット等での汎用動作確認は未実施。
- **Mems_allowed_list = 0-1 の意味**: numactl --membind=1 にもかかわらず /proc/PID/status で両ノード許可に見えた (cpuset のフィールド上仕様と考えられるが、実際の allocation が node 1 にバインドされているかは numastat で未確認)。

## 検証完了後に実施すべき TODO

- [ ] 128k prompt × 実運用相当 (`--tokens-test 96k`) で再起動 → /v1/chat/completions を 1 回通す soak test。VRAM 残余が OOM しないことを確認。
- [ ] `--no-mmap` を `qwen3_122b` プロファイルに追加した版と比較ベンチ (eval ±0.2 t/s 以内なら採用)。
- [ ] 35B / gpt-oss-20b の起動回帰テスト (短 prompt smoke 1 回ずつ)。
- [ ] プロファイル判定の unit test: `SERVER × HF_MODEL × FIT_CTX_ARG` の 6 組み合わせで `MODEL_PROFILE` / `FIT_CTX` / `SERVER_OPTS` / `NGL_OPTS` の期待値を assert するテストスクリプトを `.claude/skills/llama-server/scripts/_test_profile.sh` として追加。
- [ ] `mi25 × qwen3_122b` と `t120h-m10 × qwen3_122b` の挙動確認 (OOM で失敗する場合、usage か error message で早期 abort を追加)。
- [ ] 変更 (start.sh / wait-ready.sh / SKILL.md) を git commit。コミットメッセージは REPORT 本文のサマリを流用可。
- [ ] 対話的利用マニュアル (CLAUDE.md の「クイックリファレンス」節) に `fit` 既定が 128k になったことを追記する必要があるか確認。

## 参考レポート

- [Phase U-5: 長文脈 VRAM fit マップ (ctx=128k fit 構成 9 件特定)](2026-04-24_081326_qwen3-122b-u5-ctx128k-fit-map.md)
- [Phase U-6: ctx=128k 起動 default 構成確定 (B14b / ub=512 採用)](2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default.md)
- [Phase T-5a-ts2: B14 × tensor-split で 18.664 t/s baseline 確定](2026-04-23_093629_qwen3-122b-c3-phaseT5a-ts2.md)
