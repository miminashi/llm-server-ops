# Phase K: cache-type f16 条件での flash-attn ON/OFF A/B 比較

## Context

Phase J の最優先未検証事項として残された「flash-attn ON/OFF の A/B 比較」を、Phase J で起動不可となった原因（`--cache-type-{k,v} q8_0` と `--flash-attn 0` の非互換）を迂回した上で実行する。

Phase J で判明した事実:
- C-D3 構成（量子化 KV cache q8_0）では `--flash-attn 0` は Segfault で起動不可
- flash-attn の A/B 比較には **f16 KV cache 条件** への移行が必須
- ただし f16 KV は VRAM を約 2x 消費するため、ctx-size を縮小する必要がある

Phase K では `--cache-type-{k,v} f16` + `--ctx-size 16384` の縮小構成で flash-attn ON/OFF の直接比較を行い、以下を確定させる:

1. P100 (CC 6.0) 環境で flash-attn が eval_tps / prompt_tps にもたらす差分（符号・大きさ）
2. flash-attn=0 が f16 条件では起動可能か（Phase J で確認できなかった事項）
3. f16 + ctx=16k での VRAM フットプリントと dmon 所見

Phase K の結果を踏まえて、C-D3 採用構成での flash-attn=1 の正当性がより確実になる（または別構成の採用動機が生まれる）。

## 成功条件

- K_f16_fa1 と K_f16_fa0 両セッションで warmup / 1k / 8k を 3 runs ずつ完走
- 両条件の eval_tps・prompt_tps の中央値と Phase J_fa1（q8_0）との差分を取得
- flash-attn=0 起動の可否と Segfault 原因（Phase J 仮説）の裏取り

## 計測シナリオ

### 共通構成（C-D3 ベース、f16 KV へ差し替え）

```
numactl --cpunodebind=1 --membind=1 -- \
  llama-server \
  --model ${MODEL_PATH} \
  --threads 40 \
  --poll 0 \
  -b 8192 -ub 8192 \
  --ctx-size 16384 \
  --cache-type-k f16 --cache-type-v f16 \
  -ngl 999 -ot 'ffn_.*_exps\.weight=CPU' \
  --flash-attn ${FLASH_ATTN}   # 1 or 0
```

### A/B 2 条件

| セッション | --flash-attn | TAG_PREFIX |
|---|---|---|
| K_f16_fa1 | 1 | `K_f16_fa1` |
| K_f16_fa0 | 0 | `K_f16_fa0` |

### 計測サイズ

Phase J と同様:
- `warmup` (50 token)
- `1k` (1,071 token)
- `8k` (8,072 token)

各 3 runs、合計 2 セッション × 3 サイズ × 3 runs = 18 runs（約 70 分の見込み）。

## 実装ステップ

### Step 1: GPU サーバロック取得

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### Step 2: レポート用 attachment ディレクトリ作成 & Phase J 資産コピー

```bash
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_SLUG="${TS}_qwen3-122b-c3-phaseK-f16-flashattn-ab"
REPORT_DIR="report/attachment/${REPORT_SLUG}"
mkdir -p "$REPORT_DIR"

# Phase J から必要資産をコピー
PHASEJ_DIR="report/attachment/2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab"
cp "$PHASEJ_DIR"/{run_all.sh,measure_phaseI.sh,aggregate_results.sh} "$REPORT_DIR/"
cp -r "$PHASEJ_DIR/prompts" "$REPORT_DIR/prompts"

# プランファイルもコピー（レポート生成時のトレーサビリティ）
cp /home/ubuntu/.claude/plans/todo-starry-harbor.md "$REPORT_DIR/plan.md"
```

### Step 3: start_phaseK.sh の作成

Phase J の `start_phaseJ.sh` を雛形とし、以下を差し替え:

| 項目 | Phase J | Phase K |
|---|---|---|
| `--cache-type-k` | `q8_0` | **`f16`** |
| `--cache-type-v` | `q8_0` | **`f16`** |
| `--ctx-size` | `131072` | **`16384`** |
| ログ識別子 | `[start_phaseJ]` | `[start_phaseK]` |
| コメント | — | 「f16 KV + ctx=16k 縮小版、flash-attn A/B 比較用」の旨を明記 |

`FLASH_ATTN` 環境変数は Phase J のまま継承（既定 1、0 も許容）。

### Step 4: aggregate_results.sh のタグ修正

`out_J_*` → `out_K_*` に書き換え（参照先グロブのみ変更、集計ロジックは不変）。

### Step 5: フェーズ 1（flash-attn=1 測定）

```bash
FLASH_ATTN=1 bash "$REPORT_DIR/start_phaseK.sh"
PID=$(ssh t120h-p100 "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")

pushd "$REPORT_DIR"
TAG_PREFIX=K_f16_fa1 SIZES="warmup 1k 8k" PID=$PID bash run_all.sh
popd

.claude/skills/llama-server/scripts/stop.sh t120h-p100
```

### Step 6: フェーズ 2（flash-attn=0 測定）

```bash
FLASH_ATTN=0 bash "$REPORT_DIR/start_phaseK.sh"
```

**起動判定**:
- 成功（`/health` が 200 を返す）→ PID を取得して計測続行
- 失敗（Phase J と同様 Segfault または起動タイムアウト）→ `llama-server.log` を `$REPORT_DIR/fa0_startup/` に退避し、計測フェーズはスキップ

成功時:
```bash
PID=$(ssh t120h-p100 "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
pushd "$REPORT_DIR"
TAG_PREFIX=K_f16_fa0 SIZES="warmup 1k 8k" PID=$PID bash run_all.sh
popd
.claude/skills/llama-server/scripts/stop.sh t120h-p100
```

### Step 7: 集計・ロック解放

```bash
pushd "$REPORT_DIR"
bash aggregate_results.sh > results.tsv
popd
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### Step 8: レポート作成

REPORT.md ルールに従い以下を作成:

- ファイル: `report/${TS}_qwen3-122b-c3-phaseK-f16-flashattn-ab.md`
- 必須セクション:
  - 添付ファイル一覧
  - 参照（Phase J、Phase I）
  - 前提・目的
  - 環境情報
  - 計測手順（再現方法）
  - 実行結果サマリ（K_f16_fa1 の eval / prompt / VRAM、K_f16_fa0 の同項目 or 起動失敗記録）
  - ボトルネック・副次発見の分析（Phase J_fa1 / Phase I との比較、flash-attn 差分の数値化、VRAM 差分、dmon 所見）
  - 採用判定（C-D3 における flash-attn=1 の正当性再評価）
  - **未検証事項**（Phase J から継続 + Phase K で新規発生）
  - **検証完了後に実施すべき TODO**（Phase J から継続 + Phase K で新規発生）
  - 補足
- プランファイルへのリンク: `[実装プラン](attachment/${REPORT_SLUG}/plan.md)`

## リスク・想定される分岐

| 事象 | 分岐 |
|---|---|
| flash-attn=1 起動時 VRAM 逼迫で OOM | `--ctx-size` を 8192 に下げて再試行 |
| flash-attn=0 が f16 でも Segfault | ログを保全し「f16 でも非互換」として報告。Phase K の部分的決着とし、Phase K-2 で `--cache-type f16 --flash-attn 0 --ctx-size 4096` など極小構成を試行する TODO を立てる |
| K_f16_fa1 の eval_tps が Phase J_fa1 (q8_0) と大きく乖離 | 両条件の差分は「量子化 KV の memory bandwidth 節約効果」を示唆。分析セクションで言及 |
| ロック取得失敗 | 他セッションが使用中。ロック解放まで待機し、再実行 |

## 改変対象ファイル

**新規作成のみ**（既存リポジトリファイルの変更なし）:

- `report/attachment/<slug>/start_phaseK.sh`（新規、Phase J start_phaseJ.sh のコピー改変）
- `report/attachment/<slug>/run_all.sh`（Phase J からコピー、無修正）
- `report/attachment/<slug>/measure_phaseI.sh`（Phase J からコピー、無修正）
- `report/attachment/<slug>/aggregate_results.sh`（Phase J からコピー、`out_J_*` → `out_K_*`）
- `report/attachment/<slug>/prompts/`（Phase J からコピー）
- `report/attachment/<slug>/plan.md`（本計画のコピー）
- `report/attachment/<slug>/out_K_f16_{fa1,fa0}_{warmup,1k,8k}/`（計測結果、実行時生成）
- `report/attachment/<slug>/results.tsv`（集計結果）
- `report/<TS>_qwen3-122b-c3-phaseK-f16-flashattn-ab.md`（新規レポート）

## 参照ファイル

既存の再利用対象:
- `report/attachment/2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab/start_phaseJ.sh` — start スクリプト雛形
- `report/attachment/2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab/run_all.sh` — 計測オーケストレータ（無修正流用）
- `report/attachment/2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab/measure_phaseI.sh` — 個別サイズ計測（無修正流用）
- `report/attachment/2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab/prompts/prompt_{warmup,1k,8k}.txt` — プロンプト
- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh` — 排他制御
- `.claude/skills/llama-server/scripts/stop.sh` — 停止

## 検証（Verification）

計測が妥当に完了したことを確認するチェックリスト:

1. `results.tsv` に K_f16_fa1_{warmup,1k,8k} の 3 runs 分 × 3 サイズの eval_tps / prompt_tps が記録されている
2. K_f16_fa0 について、起動成功なら同様の記録、失敗なら `fa0_startup/llama-server.log` に落ちたログがある
3. 各 `out_K_*/gpu_post_run*.csv` で CUDA1 free が正値（OOM していない）
4. Phase J_fa1 (q8_0, ctx=131072) の warmup 中央値 15.28 t/s と、K_f16_fa1 (f16, ctx=16384) の warmup 中央値を比較し、差分を数値化
5. K_f16_fa0 が起動成功なら flash-attn 差分 (Δeval_tps、Δprompt_tps) を中央値同士で算出
6. レポートに「未検証事項」「検証完了後に実施すべき TODO」セクションが Phase J から継承 + Phase K 新規項目を含む形で記載されている
7. llama-server プロセスが残存していないこと、GPU ロックが解放されていることを最終確認

## 所要時間見積もり

- ロック取得・準備: 5 分
- K_f16_fa1 フェーズ: 約 18 分（Phase J_fa1 実績同等）
- K_f16_fa0 フェーズ: 起動成功時 18 分、失敗時 < 5 分
- 集計・レポート作成: 20 分
- **合計**: 最大約 70 分（起動失敗時は約 50 分）
