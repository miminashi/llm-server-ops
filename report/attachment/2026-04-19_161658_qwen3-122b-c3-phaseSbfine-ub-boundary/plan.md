# Phase Sb-fine: CUDA0 区分境界 ub\* の 64-token 精度絞り込み

## Context

直前レポート (`report/2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary.md`) の「未検証事項 / 新規項目」最上位:

> **★最優先: CUDA0 境界 ub\* の 64-token 精度での絞り込み** (Phase S-boundary-fine 候補): ub=1600/1664/1700/1750 で追加計測、ub\* を 64-token 以下の精度で特定

Phase Sb で `ub\* ∈ (1536, 1792]` と 256-token 精度で確定したが、実際の境界点は未特定。本 Phase では同区間を 4 点で細分化し、**64-token 以下の精度**で境界を絞り込む。

### Phase Sb から継承した確定事項（参考値）

ctx=32k 系列 CUDA0 実測値:

| ub | 1024 | 1280 | 1536 | **1600** | **1664** | **1700** | **1750** | 1792 | 2048 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CUDA0 (MiB) | 973.00 | 976.25 | 979.50 | ? | ? | ? | ? | 1039.12 | 1112.13 |
| Δ from prev | — | +3.25 | +3.25 | ? | ? | ? | ? | (+59.62 at jump) | +73.01 |

ub=1536 → 1792 の 256-token 区間で +59.62 MiB の大ジャンプが起きており、jump 発生点を 64-token 精度 (1600/1664/1700/1750 の 4 刻み) で特定する。

### 期待シナリオ

- シナリオ A: ub=1600 で既に jump → `ub\* ∈ (1536, 1600]`
- シナリオ B: ub=1600 平坦、ub=1664 で jump → `ub\* ∈ (1600, 1664]`
- シナリオ C: ub=1664 平坦、ub=1700 で jump → `ub\* ∈ (1664, 1700]`
- シナリオ D: ub=1700 平坦、ub=1750 で jump → `ub\* ∈ (1700, 1750]`
- シナリオ E: ub=1750 平坦、ub=1792 で jump → `ub\* ∈ (1750, 1792]`

## アプローチ

Phase Sb で確立した batch 運用パターン (stdout redirect 版 `batch_boundary.sh` + `start_phaseSb.sh` + `run_all.sh` + `measure_phaseI.sh`) をほぼ無改変で流用。`CONDS` 配列のみ 4 条件に差し替える。

## 実行パラメータ

- **サーバ**: t120h-p100 (10.1.4.14)
- **モデル**: Qwen3.5-122B-A10B Q4_K_M
- **構成**: Phase Sb と完全一致（NUMA node1 bind, threads=40, C-D3 layer split, f16 KV, fa=1, `-b=ub -ub=ub`）
- **条件マトリクス**: ctx=32768 固定 × ub=1600/1664/1700/1750 の **4 条件**
- **計測**: warmup + 1k prompt × 3 run（Phase Sb と同一）
- **所要時間見積**: 1 条件 ~10 分 × 4 = **40-45 分**

## 手順

### 1. ロック取得 + ディレクトリ準備 + スクリプト流用

```bash
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100

TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
PHASE_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseSbfine-ub-boundary"
mkdir -p "$PHASE_DIR/startup_logs"

PHASE_SB="report/attachment/2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary"
cp "$PHASE_SB"/{measure_phaseI.sh,run_all.sh,start_phaseSb.sh,aggregate_boundary.sh,batch_boundary.sh} "$PHASE_DIR/"
cp -r "$PHASE_SB/prompts" "$PHASE_DIR/"

# プレフィックス置換: Sb → Sbf
mv "$PHASE_DIR/start_phaseSb.sh" "$PHASE_DIR/start_phaseSbf.sh"
mv "$PHASE_DIR/batch_boundary.sh" "$PHASE_DIR/batch_boundary_fine.sh"
mv "$PHASE_DIR/aggregate_boundary.sh" "$PHASE_DIR/aggregate_boundary_fine.sh"

sed -i 's/phaseSb_/phaseSbf_/g; s/\[start_phaseSb\]/[start_phaseSbf]/g' "$PHASE_DIR/start_phaseSbf.sh"
sed -i 's/\[batchSb\]/[batchSbf]/g; s/start_phaseSb\.sh/start_phaseSbf.sh/g; s/phaseSb_/phaseSbf_/g; s/TAG_PREFIX="Sb_f16/TAG_PREFIX="Sbf_f16/g; s/run_Sb_ctx/run_Sbf_ctx/g; s/start_stdout_Sb_ctx/start_stdout_Sbf_ctx/g' "$PHASE_DIR/batch_boundary_fine.sh"
sed -i 's/out_Sb_\*/out_Sbf_*/g' "$PHASE_DIR/aggregate_boundary_fine.sh"
```

### 2. `batch_boundary_fine.sh` の CONDS 配列を 4 条件に編集

```bash
CONDS=(
  "32768 1600"
  "32768 1664"
  "32768 1700"
  "32768 1750"
)
```

### 3. バッチ計測

```bash
cd "$PHASE_DIR"
bash batch_boundary_fine.sh > batch_boundary_fine.log 2>&1
```

### 4. 停止・集計・解析・解放

```bash
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash aggregate_boundary_fine.sh > results.tsv
grep -E "sched_reserve:|KV buffer|graph nodes|graph splits|cudaMalloc|failed to allocate|reserve took|llama_kv_cache: size|llama_memory_recurrent: size" \
  startup_logs/*.log > compute_buffer_summary.txt
python3 analyze_boundary_fine.py | tee analyze_boundary_fine.txt
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 5. 解析スクリプト `analyze_boundary_fine.py` の新規作成

Phase Sb の `analyze_boundary.py` をベースに、4 点の実測値を差し込んで:

- 各 ub における C0 実測値と Phase Sb 平坦域モデル `966.5 + 0.0064·ub` の残差を表示
- 直前の ub との C0 差分 ΔC0 を算出し、**+3.25〜+3.5 MiB の線形挙動を維持している点**と **ジャンプ発生点 (Δ > +30 MiB)** を識別
- 平坦域モデルから +5 MiB 以内なら「平坦域」、+30 MiB 以上なら「遷移後」と判定
- 境界 ub\* の最終区間を出力

CUDA1/2/Host/CUDA3 については Phase Sb の 4p / 純比例モデルを流用し、4 点での max_err も併せて出力する（23 点検証）。

## 成功条件

- [ ] 4 条件すべて起動成功（/health OK、OOM ゼロ、-ub 下限拒否ゼロ）
- [ ] CUDA3 4 点で `0.9824·ub ± 0.1 MiB`
- [ ] CUDA0 4 点で境界 ub\* を (1536, 1600] / (1600, 1664] / (1664, 1700] / (1700, 1750] / (1750, 1792] のいずれか 1 区間に確定
- [ ] CUDA1/2 / CUDA_Host 4 点が Phase Sb 確定 4p モデルと max_err < 5 MiB
- [ ] graph nodes=4473 / splits_bs1=77 の 4 条件不変
- [ ] KV buffer 4 点で `192 MiB/GPU` ± 0

## 修正ファイル一覧

すべて新規作成のみ（既存ファイルは変更しない）:

- `report/attachment/{TS}_qwen3-122b-c3-phaseSbfine-ub-boundary/` 配下（スクリプト・計測出力・ログ）
- `report/{TS}_qwen3-122b-c3-phaseSbfine-ub-boundary.md`（レポート本体、直前レポートと同構造、「未検証事項」「検証完了後に実施すべき TODO」セクションを必須で含む）
- `REPORT.md` のインデックス追記

## 既存資産の流用（再利用）

- `start_phaseSb.sh` — 起動スクリプト、プレフィックスのみ差し替え
- `batch_boundary.sh` — バッチ運用、CONDS 4 行へ差し替え（stdout redirect 版は Phase S で確立済み）
- `measure_phaseI.sh` / `run_all.sh` / `prompts/` — 無改変流用
- `aggregate_boundary.sh` — 出力プレフィックス置換のみ
- `analyze_boundary.py` — 4 点版 `analyze_boundary_fine.py` として書き換え
- `.claude/skills/gpu-server/scripts/{lock,unlock}.sh` — GPUサーバ排他制御
- `.claude/skills/llama-server/scripts/stop.sh` — サーバ停止

## リスクと想定外動作

- **-ub 下限拒否**: ub=1600〜1792 は Phase Q/Sb の実測範囲内、llama.cpp 下限 (Phase Q で ~300 と確定済み) を大きく上回るため拒否は想定外
- **OOM**: Phase Sb の ub=1792 時点で CUDA0 実測 1039 MiB、余裕 15 GiB 以上。問題なし
- **所要 45 分超過**: 1 条件 10 分 × 4 で 40 分見込みだが、stdout redirect 方式でハングは発生しない（Phase Sb で実証済み）

## 検証 (end-to-end)

1. `batch_boundary_fine.log` に 4 条件すべて `[batchSbf] measure done` が出現
2. `results.tsv` に 4 条件 × (warmup + 1k) × 3 run = 24 データ行 + ヘッダ
3. `compute_buffer_summary.txt` に 4 条件 × 5 GPU = 20 以上の `sched_reserve:` 行、4 条件 × 4 GPU = 16 の `KV buffer` 行
4. `analyze_boundary_fine.py` 出力で境界 ub\* が 1 区間に確定
5. レポート末尾の「未検証事項」「検証完了後に実施すべき TODO」セクションが Phase Sb 同様に網羅的に記載される

## 追記: レポート記載必須事項

直前レポート (`2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary.md`) と同じ以下のセクションを含める:

- 前提・目的（Phase Sb 未検証事項からの引用）
- 成功条件（チェックボックス）
- 環境情報
- 再現方法（スクリプト差分・実行フロー・タイムライン）
- 実行結果サマリ（compute buffer 実測値、境界 ub\* の確定、モデル残差、graph/KV、reserve 時間、eval/prompt 性能）
- ボトルネック・副次発見の分析
- 採用判定（チェックリスト）
- 確定モデル（23 点検証版への更新）
- **未検証事項**（既知項目 / 新規項目、本 Phase で潰した項目は `[x]`）
- **検証完了後に実施すべき TODO**（既知項目 / 新規項目）
- 補足（核心発見、23 点データベース、eval/prompt データベース、作業終了時点の状態）
