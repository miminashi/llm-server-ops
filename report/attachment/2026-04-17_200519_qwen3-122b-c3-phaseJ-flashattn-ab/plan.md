# Phase J: flash-attn ON/OFF A/B 比較（長〜中コンテキスト）

## Context

Phase I (2026-04-17) で C-D3 採用構成 (`numactl --cpunodebind=1 --membind=1 --threads 40 --poll 0 --flash-attn 1 -b 8192 -ub 8192 --ctx-size 131072 --cache-type-k q8_0 --cache-type-v q8_0`) の長コンテキスト性能プロファイルが確定した。しかし、**`--flash-attn 1` は Phase A〜I の全フェーズで前提として固定され、一度も `--flash-attn 0` との A/B 比較が行われていない**（2026-04-10 の初期 VRAM チューニング計画から既定値のまま）。

t120h-p100 の GPU は P100 (CC 6.0) で Tensor Core を持たず、flash-attention の実装上のメリット（matmul 融合による SM 占有率向上）が A100/H100 と同等に発揮されない可能性がある。P100 では off のほうが速いシナリオも理論的にはあり得るため、**採用構成の土台条件を直接検証する**のが本 Phase J の目的。

合わせて Phase I で観測された「セッション間 warmup ゆらぎ（14.66〜15.00、2.3%）」を相殺するため、Phase J 内で flash-attn=1 の基準値も同日再採取し、セッションペア同士の「warmup 比劣化率」ベースで比較する。

## 目的（成功条件）

1. flash-attn=1 と flash-attn=0 の eval_tps・prompt_tps を、少なくとも **warmup・1k・8k** の 3 サイズで直接比較
2. flash-attn=0 の GPU メモリ影響（CUDA1 free の変動）を実測し、OOM 境界の把握
3. P100 CC 6.0 で flash-attn 採用が正当化されるか、**明示的な判定**をレポートに記録
4. 2 時間ロック枠内で完走（想定 90 分）

## 構成

### 変更箇所（Phase I 資産から最小改変）

| ファイル | Phase I 内容 | Phase J での変更 |
|---|---|---|
| `start_phaseI.sh` | `--flash-attn 1` ハードコード | **`FLASH_ATTN` 環境変数化**（既定 1）。他は維持 |
| `run_all.sh` | TAG 固定 (`I_warmup` 等)、全 6 サイズ | **`TAG_PREFIX` 環境変数化**、`run_gated` 関数追加（CUDA1 free 閾値チェック） |
| `measure_phaseI.sh` | - | **変更なし、そのまま流用** |
| `generate_prompts.py`, `check_tokens.sh`, `prompts/` | - | **流用**（Phase I 生成済みプロンプトをコピー使用） |
| `aggregate_results.sh` | タグ I_* 向け | **TAG_PREFIX 対応に修正** |

### 計測サイズ（2 セッション × 各サイズ）

| タグ | prompt_n | Run 数 | 想定所要 | ゲート |
|---|---:|---:|---:|---|
| `J_fa1_warmup` | 48 | 3 | ~5 min | — |
| `J_fa1_1k` | 1,069 | 3 | ~7 min | — |
| `J_fa1_8k` | 8,070 | 3 | ~7 min | — |
| **[サーバ再起動 flash-attn=0]** | | | ~5 min | — |
| `J_fa0_warmup` | 48 | 3 | ~5 min | CUDA1 free >= 1,500 MiB |
| `J_fa0_1k` | 1,069 | 3 | ~7 min | 同上 |
| `J_fa0_8k` | 8,070 | 3 | ~10 min | 同上 |
| `J_fa0_32k` | 32,101 | 2 | ~15 min | 同上（OOM 時 skip） |

**合計**: 起動・停止・クールダウンを含めて約 **90 分**（2 時間ロック枠内）。

64k / 120k は除外（flash-attn=0 での O(N²) アテンションバッファで OOM 確度が極めて高く、走っても 30 分超かかるため時間予算を圧迫）。32k 以上は gate で保護。

### OOM ゲートの実装方針（`run_all.sh` 追加）

```bash
check_cuda1_free() {
  local threshold_mib="${1:-1500}"
  local free
  free=$(ssh "$HOST" "nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits -i 1" \
    | tr -d '[:space:]')
  if [ "${free:-0}" -lt "$threshold_mib" ]; then
    echo "[gate] CUDA1 free=${free} MiB < ${threshold_mib}, SKIP"
    return 1
  fi
  echo "[gate] CUDA1 free=${free} MiB OK"
  return 0
}
run_gated() {
  local tag="$1" spec="$2" runs="$3" thresh="${4:-1500}"
  if check_cuda1_free "$thresh"; then
    run "$tag" "$spec" "$runs"
  else
    echo "[run_all] SKIPPED $tag (memory gate)" | tee -a "$MASTER_LOG"
  fi
}
```

閾値 **1,500 MiB** = Phase I ピーク 1,053 MiB + 約 50% マージン。1k で既に閾値未満なら「flash-attn off 運用は不可」と結論し 8k/32k は即 skip。

### 比較メトリクス

- **必須**: `eval_tps` (predicted_per_second), `prompt_tps` (prompt_per_second), CUDA0-3 `memory.used`, CUDA1 `memory.free`
- **重点分析**: `dmon_run*.log` の **sm%** と **power**（flash-attn の本質は SM 占有率向上と仮説。off で sm% 低下が見えるか）
- **副次**: `numastat_m_{pre,post}.txt` は差分のみ。per-run は取らない

### セッションゆらぎの処理

- Phase H で観測された warmup ゆらぎ 14.66〜15.00 (2.3%) は有意
- **Phase J 内で flash-attn=1 の warmup を再採取**し、「その日の基準値」として使う
- A/B 判定は `(J_fa0_Xk / J_fa0_warmup) vs (J_fa1_Xk / J_fa1_warmup)` の劣化率比較で、セッションゆらぎを相殺

## 実行手順

### 事前準備（ロック外）

```bash
# ロック取得
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 作業ディレクトリ作成（実行時に TS を確定）
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseJ-flashattn-ab"
mkdir -p "$REPORT_DIR"

# Phase I 資産をコピー
SRC="report/attachment/2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext"
cp "$SRC/measure_phaseI.sh" "$REPORT_DIR/"
cp "$SRC/check_tokens.sh" "$REPORT_DIR/"
cp "$SRC/generate_prompts.py" "$REPORT_DIR/"
cp "$SRC/aggregate_results.sh" "$REPORT_DIR/aggregate_results.sh"
cp -r "$SRC/prompts" "$REPORT_DIR/"

# start_phaseI.sh を編集して Phase J 用に保存
cp "$SRC/start_phaseI.sh" "$REPORT_DIR/start_phaseJ.sh"
#   L21 `--flash-attn 1` → `--flash-attn ${FLASH_ATTN}` に変更
#   ファイル先頭に `FLASH_ATTN="${FLASH_ATTN:-1}"` を追加

# run_all.sh を編集して TAG_PREFIX / run_gated を追加
cp "$SRC/run_all.sh" "$REPORT_DIR/run_all.sh"
#   - `TAG_PREFIX="${TAG_PREFIX:-J_fa1}"` を追加
#   - 全タグを `${TAG_PREFIX}_warmup`, `${TAG_PREFIX}_1k` 等に変更
#   - 計測サイズを warmup/1k/8k/32k に絞る（64k/120k は削除）
#   - 32k は run_gated に変更（閾値 1500）
#   - I_post 相当は省略可（本 Phase は A/B が主目的）
```

### フェーズ 1: flash-attn=1 基準再採取（約 25 分）

```bash
FLASH_ATTN=1 bash "$REPORT_DIR/start_phaseJ.sh"
PID=$(ssh t120h-p100 "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
cd "$REPORT_DIR"
TAG_PREFIX=J_fa1 PID=$PID bash run_all.sh
cd -
.claude/skills/llama-server/scripts/stop.sh t120h-p100
```

（run_all.sh は 32k を含まず warmup/1k/8k のみ実行するよう `SIZES="warmup 1k 8k"` で絞る実装）

### フェーズ 2: flash-attn=0 計測（約 50 分）

```bash
FLASH_ATTN=0 bash "$REPORT_DIR/start_phaseJ.sh"
PID=$(ssh t120h-p100 "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
cd "$REPORT_DIR"
TAG_PREFIX=J_fa0 SIZES="warmup 1k 8k 32k" PID=$PID bash run_all.sh
cd -
.claude/skills/llama-server/scripts/stop.sh t120h-p100
```

### 集計・終了

```bash
cd "$REPORT_DIR"
bash aggregate_results.sh  # TAG_PREFIX 対応済みのもの
cd -

.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 例外時の振る舞い

| 事象 | 対応 |
|---|---|
| flash-attn=0 起動時に llama-server が OOM で即死 | `stop.sh` → 8k/32k をスキップし warmup/1k のみのレポートにまとめて明示。A/B の結論は「flash-attn off は起動すら困難」と記録 |
| 1k 完了時点で CUDA1 free < 1500 | gate で 8k/32k 自動スキップ。warmup/1k の eval_tps 差分だけでも本 Phase の採用判定目的は達成 |
| 32k が OOM でタイムアウト (>1 時間) | `CURL_MAX_TIME=3600` 到達で cur l が失敗、eval_run2.json が `{}` になる。タイムアウト起因として記録し 32k は 1 run で打ち切り |

## 分析方針（レポート作成時）

1. **相対劣化率テーブル**: `(Xk の eval_tps) / (warmup の eval_tps)` を fa1/fa0 それぞれで出し、差分を比較
2. **絶対値テーブル**: Phase I 結果を参考値として併記（同日再採取の J_fa1 を正系）
3. **prompt_tps の 8k ピーク**: flash-attn off でも 8k ピークが見えるか、変化量はどの程度か
4. **dmon sm%・power の時系列**: 1 Run の dmon ログを fa1/fa0 で比較図示
5. **GPU メモリプロファイル**: 8k / 32k (fa0 到達可能時) での CUDA1 free 変動
6. **採用判定**:
   - flash-attn=0 の eval_tps が warmup 比で fa1 以上なら → `--flash-attn 0` 再検討
   - 長コンテキストで fa0 が fa1 を下回るか OOM で不可 → `--flash-attn 1` 維持確定
   - 短コンテキストで fa0 優位、長で fa1 優位なら → 運用コンテキストに応じた切替示唆（採用変更は即時せず別 Phase で再検討）

## Critical Files

**参照（読み取りのみ）**:
- `/home/ubuntu/projects/llm-server-ops/report/2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext.md` — Phase I レポート
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext/start_phaseI.sh` — 起動テンプレ
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext/measure_phaseI.sh` — 計測本体（流用）
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext/run_all.sh` — 一括実行
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/start.sh` — skill 側起動テンプレ (L155 参照)
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh`
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- `/home/ubuntu/projects/llm-server-ops/REPORT.md` — レポート作成ルール

**新規作成（`report/attachment/<TS>_qwen3-122b-c3-phaseJ-flashattn-ab/` 配下）**:
- `start_phaseJ.sh` — `FLASH_ATTN` 環境変数対応版
- `run_all.sh` — `TAG_PREFIX` / `SIZES` / `run_gated` 対応版
- `measure_phaseI.sh` — コピー（リネームしない、Phase I と同一のため）
- `aggregate_results.sh` — `TAG_PREFIX` 対応版
- `check_tokens.sh`, `generate_prompts.py` — コピー
- `prompts/` — プロンプトディレクトリコピー
- 各 `out_J_fa{0,1}_*` ディレクトリ — 計測アーティファクト

**レポート**:
- `/home/ubuntu/projects/llm-server-ops/report/<TS>_qwen3-122b-c3-phaseJ-flashattn-ab.md`

## レポート構成（[REPORT.md](../projects/llm-server-ops/REPORT.md) 準拠）

以下のセクションを必ず含める:

1. タイトル・実施日時・作業種別
2. 添付ファイル一覧
3. 参照（Phase I, Phase H, Phase D）
4. 前提・目的
5. 環境情報
6. 計測手順（再現方法）
7. 実行タイムライン
8. 実行結果サマリ（eval_tps / prompt_tps / GPU mem）
9. ボトルネック・副次発見の分析
10. 採用判定
11. **未検証事項**（Phase I から継続 + 本 Phase 新規）
12. **検証完了後に実施すべき TODO**（Phase I から継続 + 本 Phase 新規）
13. 補足

### 未検証事項への引き継ぎ方針

- Phase I の既知項目一覧を**そのまま引き継ぎ**、本 Phase で flash-attn off 項目に決着が付いた分だけチェックを入れる
- 新規に「flash-attn off での 64k/120k 挙動」「flash-attn のカーネル経路（P100 CC 6.0 での分岐）のソース解析」を追加

## Verification

### 完走判定

- [ ] `J_fa1_warmup`, `J_fa1_1k`, `J_fa1_8k` の 3 runs ずつが `eval_run{1,2,3}.json` に有効な timings を含む
- [ ] `J_fa0_warmup` が成功（起動自体は成功）
- [ ] `J_fa0_1k`, `J_fa0_8k` が OOM で skip / 成功いずれにせよ記録
- [ ] `aggregate_results.sh` が TSV を生成し、全タグの中央値・Run間 range が算出されている

### 結論が得られる条件

以下いずれかが成立すれば採用判定を下せる:

- A. fa0 で warmup〜8k のすべての eval_tps が fa1 を下回る → **flash-attn 1 維持確定**
- B. fa0 で warmup〜8k のいずれかの eval_tps が fa1 を上回る → **追加検証が必要**（Phase K に引き継ぎ）
- C. fa0 で 8k に到達できない（OOM / skip） → **flash-attn 1 維持確定**（P100 では off は物理的に困難）

### ロールバック手順

本 Phase J はサーバ起動オプションの一時変更のみで、採用構成の `start.sh` (skill 側) は改変しない。計測終了後、通常通り `stop.sh` / `unlock.sh` で復帰。計測中に問題があれば即座に `stop.sh` して `unlock.sh` で解放。
