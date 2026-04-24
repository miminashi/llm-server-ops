# Phase U-2: `--cache-ram` (PR #16391) 独立検証プラン

## Context

Phase U-1-ext (report/2026-04-23_171459_qwen3-122b-u1ext-specckpt-relaxed.md) で spec
decoding (ngram-mod + ctx checkpoint) は本構成 (Qwen3.5-122B-A10B Q4_K_M / P100×4 +
CUDA2 hetero, B14b_ts_alt) では OFF 比 **-21〜-33%** と確定し、spec 軸を終了。

次は T 系列後ロードマップ (memory: project_t_series_roadmap) の **Cycle 85 次アイテム**
である `--cache-ram` (PR #16391 *host memory prompt caching*) の独立検証。PR 記述では
TTFT **-93%** と報告されており、**P100 hetero 構成でこれが再現するか**および**最適
`cache-ram` サイズ**を特定する。

本 Phase の技術要請:
- baseline eval_tps (B14b_ts_alt, 18.664 t/s) を壊さない範囲で
- cache hit 時の TTFT 短縮効果を定量化
- 過去の Phase T-5a-ts2 / Phase U-1 / U-1-ext と横断比較可能な形式で結果を残す

llama.cpp は U-1 でビルド済 `6217b4958`。PR #16391 マージ `d00cbea63` (2025-10-09) は
この祖先に含まれるため **再ビルド不要**（実装時の最初のステップで念のため
`git merge-base --is-ancestor` で二重確認）。

---

## 確定した前提事実 (探索から)

### F1. B14b_ts_alt の起動コマンド (既存 baseline 構成)

```bash
numactl --cpunodebind=1 --membind=1 -- ./build/bin/llama-server \
  -m <model> --jinja \
  -ngl 999 -ot 'blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU' \
  --tensor-split 11,12,13,14 --split-mode layer \
  --flash-attn 1 --poll 0 -b 256 -ub 256 \
  --n-predict 32768 --threads 40 \
  --ctx-size 32768 --parallel 1 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0
```

### F2. `--cache-ram` 仕様
- 短 `-cram`、単位 **MiB**、default **8192**、`0` 無効、`-1` 無制限、env `LLAMA_ARG_CACHE_RAM`
- LCP (Longest Common Prefix) 判定、`f_keep >= 0.25` で候補採用、`f_keep < 0.5` で cache 置換
- グローバル (全 slot 共有)
- 観測: response JSON `.timings.cache_n`、`GET /slots[].n_prompt_tokens_cache`、server log `"found better prompt ..."`

### F3. baseline 18.664 t/s は **default 8192 MiB + marker 付き (cache miss 強制)** で測定済み
→ 既存 eval_tps は cache-miss 側の値として regression 比較可能。`[Request ID <marker>]`
prefix を除くことで初めて cache hit が発生する。

### F4. TTFT は `.timings.prompt_ms` で代理する
既存 measure は `stream=false`。純 TTFT は `stream=true` + SSE 初 chunk 時刻で実測可能
だが、同一 LAN かつ server 側 `prompt_ms` が prompt 処理+前段 forward を含むため、
**最初の dry run で両方取って乖離が < 5ms なら以降 `prompt_ms` に統一** (コスト削減)。

---

## 検証設計

### 軸
`CACHE_RAM ∈ {0, 128, 256, 512, 1024, 2048} MiB` の **6 条件**。
- `0` = 完全無効 (純 baseline、既存 marker 無し prompt でも毎回 prefill)
- `8192` (default、unset) は既存 T-5a-ts2 baseline で既取得のため本 batch には含めない
  (ただし pivot で既存 B14b_ts_alt cache_ram=default 値を横並び表記)
- PR 記述の「現実的運用値」としての 128〜2048 MiB を網羅

### 各条件で実施する 3 種の測定

| Kind | 目的 | 実装要点 |
|---|---|---|
| **A. TTFT miss→hit 連投** | 同一 prompt を N=4 連投して cache hit 時 TTFT を miss と比較 | marker 除去、`/slots` pre/post snap、`timings.cache_n`/`prompt_ms`/`predicted_per_second` 記録 |
| **B. Shared-prefix (agent パターン)** | 固定 system + 可変 user suffix で部分 hit 率を評価 | system=512 tok 固定、user suffix 5 パターン、`f_keep >= 0.25` 閾値クリア率を観測 |
| **C. eval_tps regression** | cache-ram 有効化で baseline 18.664 から drift するか | 既存 `measure_phaseT5.sh` (marker 付き) を warmup2+eval5 そのまま流用、差分を median で 0.5% 以内確認 |

Total runs/条件 ≈ 5 (A) + 5 (B) + 7 (C) = 17 runs。

---

## 新規作成ファイル (attachment ディレクトリ配下)

レポートファイル名は実装時に `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で確定。仮に
`<RID> = 2026-04-XX_YYYYYY_qwen3-122b-c3-phaseU2-cache-ram` とする。

attachment dir: `report/attachment/<RID>/`

| ファイル | 役割 | 既存 copy 元 |
|---|---|---|
| `start_phaseU2.sh` | `CACHE_RAM` env を受けて `--cache-ram` 付与する起動ラッパー | `report/attachment/2026-04-23_093629_qwen3-122b-c3-phaseT5a-ts2/start_phaseT5.sh` |
| `measure_phaseU2_ttft.sh` | marker 無し連投 + `/slots` polling + `cache_n` 抽出 | `.../phaseT5a-ts2/measure_phaseT5.sh` から marker 行を削除し cache 観測追加 |
| `measure_phaseU2_prefix.sh` | 固定 system + 可変 user 5 suffix を投げる | 新規 (jq で messages array 構築) |
| `batch_U2.sh` | 6 条件 × (A/B/C) の逐次実行、GPU ロック管理 | `.../phaseT5a-ts2/batch_T5ats2.sh` を土台 |
| `analyze_phaseU2.py` | TTFT / cache_hit_rate / eval_tps drift の集計と PNG 3 枚 | `.../phaseT5a-ts2/analyze_phaseT5a-ts2.py` + `plot_phaseT5a-ts2.py` |
| `prompts/system_fixed.txt` | 512-tok 程度の system prompt (英文固定) | 既存 `.../phaseT5a-ts2/prompts/prompt_1k.txt` の先頭 512 tok を `llama-tokenize` で切出し |
| `prompts/user_suffixes.tsv` | 5 パターンの user suffix (各 100-200 tok) | 新規、手書き |

参照のみ (読み取り):
- `report/attachment/2026-04-23_093629_qwen3-122b-c3-phaseT5a-ts2/run_all.sh`, `prompts/prompt_1k.txt`
- llama.cpp: `tools/server/server-context.cpp` (f_keep), `tools/server/server-task.cpp` (cache load, timings JSON)

---

## `start_phaseU2.sh` 差分ポイント

`start_phaseT5.sh` に対し以下の最小差分:
1. env 受付: `CACHE_RAM="${CACHE_RAM:-}"` 追加
2. REMOTE_LOG tag に `_cram${CACHE_RAM:-def}` を混ぜる
3. LAUNCH_CMD 末尾に `${CACHE_RAM:+--cache-ram ${CACHE_RAM}}` 追加
4. B14b_ts_alt と一致する defaults: `OT_TAG=B14b`, `OT_REGEX='blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU'`, `TS=11,12,13,14`, `FLASH_ATTN=1`, `CTX_SIZE=32768`, `BATCH_SIZE=256`, `UB_SIZE=256`, `KV=q8_0`, `SPLIT_MODE=layer`, `THREADS=40`

それ以外 (health wait、OOM 検知 regex、PID 取得) は一切変更しない。

---

## `measure_phaseU2_ttft.sh` ロジック

入力: `<pid> <tag> <prompt_file> <n_hits>`

1. 開始時に `curl -sS ${URL}/slots > slots_pre.json`
2. **Run 0 (miss baseline)**: payload を jq で構築 — **marker を付けない** (これが既存 measure_phaseT5.sh との唯一の差分)。`POST /v1/chat/completions` (stream=false, max_tokens=256, temp=0.6, top_p=0.95, top_k=20, min_p=0)。response から `timings.prompt_ms`, `timings.predicted_per_second`, `timings.prompt_n`, `timings.predicted_n`, `timings.cache_n` を抽出。
3. `sleep ${COOLDOWN:-10}` (eval regression 側 C と違い cache 効かせ目的で短め)
4. **Run 1..N_HITS** (N=4): 同一 prompt 連投。各 run 前後で `/slots` を snap。
5. 出力:
   - `run_ttft_${i}.json` (response JSON そのまま)
   - `slots_pre_${i}.json` / `slots_post_${i}.json`
   - `ttft_summary.tsv`: `run_id cache_ram prompt_n cache_n prompt_ms eval_tps`

### TTFT 測定方式の検証 (最初の dry run 時)
`STREAM_TTFT=1` env で SSE 実測版を実行し、`prompt_ms` 近似との差分を同時記録。差分が
平均 5 ms 以内なら以降 `prompt_ms` に統一。超える場合は stream 実測を正 (cost 増を許容)。

---

## `measure_phaseU2_prefix.sh` ロジック

入力: `<pid> <tag> <system_prompt_file> <suffix_tsv>`

1. `system` を `@<file>` で読込、`messages=[{role:system,content:$sys},{role:user,content:$suf}]` を jq で組立 (既存 measure は単一 user message のみ)
2. 5 suffix 順次 POST、各 response から timings を抽出
3. 期待: 初回 miss、2 回目以降 `cache_n ≈ system_tokens_n`、`prompt_ms` 大幅短縮
4. `prefix_summary.tsv`: `suffix_id cache_ram system_n suffix_n cache_n prompt_ms eval_tps f_keep_expect`

### f_keep 閾値対策
`f_keep = LCP_tokens / cached_prompt_tokens`。LCP ≥ system 分なので、
`f_keep ≥ system_n / (system_n + suffix_n_prev) ≥ 0.25` を成立させるため
**system=512 tok / user suffix ≤ 300 tok** で設計 (safety margin 付き)。

---

## `batch_U2.sh` フロー

```
lock.sh t120h-p100 (外部で事前取得推奨、以降は無保持でも barrier なし)
for CACHE_RAM in 0 128 256 512 1024 2048:
  stop.sh
  CACHE_RAM=$v bash start_phaseU2.sh  → PID 取得
  /health polling (max 180s)
  A) measure_phaseU2_ttft.sh  <pid>  U2_cram${v}  prompts/prompt_1k.txt  4
  B) measure_phaseU2_prefix.sh <pid>  U2_cram${v}  prompts/system_fixed.txt prompts/user_suffixes.tsv
  C) measure_phaseT5.sh (既存、marker 付き)  warmup 2 + eval 5
  stop.sh
done
unlock.sh (外部)
```

OOM 検知: `start_phaseU2.sh` 継承。NUMA host memory 断片化対策として各条件 pre/post で
`ssh t120h-p100 free -w` を記録 (`free_log_${v}.txt`)。

---

## `analyze_phaseU2.py` 出力

### CSV / MD
- `u2_stats.csv`: columns = `cache_ram, run_kind, run_id, prompt_n, cache_n, cache_hit_ratio, prompt_ms, eval_tps`
- `u2_pivot.md`: 条件 × run_kind の median / stdev ピボット、**比較行として Phase T-5a-ts2 B14b_ts_alt (18.664 t/s, cache_ram=default=8192), Phase U-1 Config A, Phase U-1-ext の数値を併記**

### PNG (3 枚、核心発見サマリ直下に埋込)
1. `ttft_vs_cache_ram.png`: X=cache_ram(MiB)、Y=prompt_ms、系列=miss/hit_2nd/hit_4th
2. `cache_hit_rate_vs_size.png`: X=cache_ram、Y=cache_n/prompt_n (A と B 両方)
3. `eval_tps_drift.png`: X=cache_ram、Y=median eval_tps、水平線=18.664 ±0.5%

---

## 想定時間・ディスク

- 1 条件あたり ~13 分 (起動 2-3 min + A 2.3 min + B 2.2 min + C 7 min + 停止 10s)
- 6 条件: **~80 分** + buffer 20 min = **~1h 40min**
- 準備 (scripts + prompts) 30 min、解析 20 min
- 総計 **約 2.5 時間**、ディスク < 50 MB

---

## 想定落とし穴

1. **default 8192 の見えない影響**: 既存 T-5a-ts2 baseline は cache_ram=8192 で取得、しかし marker で cache 無効化されていたため eval_tps は cache-miss と同等。regression 比較可。
2. **`--cache-type-k/-v q8_0` との相互作用**: `--cache-ram` はトークン履歴のメタデータのみを保持し、KV 実体は別途。quantized KV でも動作するはず → 最初の dry で `/slots.n_prompt_tokens_cache > 0` が返るか確認。
3. **`f_keep < 0.5` で cache 更新**: B パターンで suffix ≥ system/4 だと頻繁に cache 書換。system=512, suffix ≤ 128 に抑える。
4. **GPU thermal drift**: A の cooldown は 10s と短い (TTFT 主目的で GPU 負荷小のため可)。C は既存の 60s を踏襲。
5. **OOM 懸念**: B14b_ts_alt 既存構成は GPU3 に余裕あり。cache-ram は host memory のため GPU OOM しないが、host mem を `free -w` で pre/post 確認。
6. **連投回数 N_HITS=4**: LRU 更新で hit が落ちる可能性は 1 prompt なので無し。ただし B パターンで 5 suffix 回すと system prefix が常に先頭にある設計なので常時 hit 見込み。

---

## 未検証事項 (本 Phase の範囲外)

- cache_ram > 2048 MiB (4096, 8192 default) での TTFT 減衰率
- ctx = 32768 以外 (8k/64k/131k) での cache_ram 効果
- `--parallel > 1` (複数 slot) 時の global cache 共有挙動
- `f_keep` 閾値 0.25 を patch で変えた場合の効果
- multi-turn 会話 (assistant → user → assistant) 実運用シナリオでの累積 TTFT 短縮効果

## 検証完了後 TODO (別 Phase で扱う)

- U-2 結果が良好 (例: `prompt_ms` 80% 以上短縮 & eval_tps 劣化 ≤ 0.5%) の場合、長 context (32k/64k) で絶対値を取る **Phase U-2b**
- eval_tps に有意 regression (>0.5%) を観測した場合、運用 default を `--cache-ram 0` もしくは小さい値に落とす運用 note を CLAUDE.md 級ドキュメントへ反映
- T 系列ロードマップ (memory: project_t_series_roadmap) 次項: `gate/up fused GGUF` 切替 **Phase U-3**
- Discord 通知: 主要結果 3 行 (discord-notify skill)
- プランファイル添付 (REPORT.md 必須手順) とレポート本文執筆

---

## 再現手順 (検証コマンド)

### 事前確認
```bash
# PR #16391 含有確認
ssh t120h-p100 "cd ~/llama.cpp && git merge-base --is-ancestor d00cbea63 6217b4958 && echo INCLUDED"
ssh t120h-p100 "cd ~/llama.cpp && ./build/bin/llama-server --help 2>&1 | grep -i cache-ram"

# GPU ロック取得
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### 実行
```bash
RID=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)_qwen3-122b-c3-phaseU2-cache-ram
ATT=report/attachment/${RID}
mkdir -p ${ATT}/prompts
# (scripts + prompts を配置)
bash ${ATT}/batch_U2.sh 2>&1 | tee ${ATT}/batch_U2.log
python3 ${ATT}/analyze_phaseU2.py ${ATT}
```

### レポート作成
- ファイル名: `report/${RID}.md`
- タイトル (50 字以内): **「Phase U-2: --cache-ram TTFT 効果と最適値特定」**
- 核心発見サマリ冒頭に 3 PNG を `![](attachment/${RID}/xxx.png)` で埋込
- 比較表に Phase T-5a-ts2 B14b (18.664) / U-1 / U-1-ext 数値を併記
- 「未検証事項」「検証完了後 TODO」を別見出しで記載
- `cp /home/ubuntu/.claude/plans/report-2026-04-23-171459-qwen3-122b-u1e-polymorphic-wind.md ${ATT}/plan.md`
- `## 添付ファイル` セクションにプランファイルリンク

### 後始末
```bash
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```
