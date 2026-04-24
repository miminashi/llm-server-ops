# Phase S-boundary: CUDA0 区分境界 ub* の特定

## Context

直前レポート [2026-04-19_120715_qwen3-122b-c3-phaseS-ub-ctx-2d.md](../../projects/llm-server-ops/report/2026-04-19_120715_qwen3-122b-c3-phaseS-ub-ctx-2d.md) の未検証事項「新規項目」最上位かつ TODO 新規項目「Phase S-boundary 候補」:

> **CUDA0 区分境界 ub\* の特定** (本 Phase 最優先候補): 1024 < ub\* ≤ 2048 の範囲で CUDA0 基底値が跳ね上がる閾値を ub=1280/1536/1792 等の中間点で特定

### 問題と目的

Phase S で CUDA0 compute buffer が **ub ≤ 1024 で平坦 (961-973 MiB、ctx 独立)**、**ub ≥ 2048 で急増 (1048→2784 MiB)** という区分的挙動を発見した。境界値 ub\* が特定できれば:

1. **CUDA0 区分モデルの境界を定量化**し、lint 組み込み時の区分条件 `if ub < ub*` を正確に記述できる
2. **llama.cpp scheduler の閾値判定ロジック**の存在を強く示唆する数値的証拠が得られる
3. **Phase S で未達だった CUDA0 二次モデル R² ≥ 0.999** の原因（区分性）を中間点データで確認できる

### 期待される成果

- ctx=32768 × ub=1280/1536/1792 の 3 条件で CUDA0 値を計測
- ub* を `[1280, 1536, 1792, 2048]` のいずれかの区間に確定
- 3 条件すべての prompt_tps / eval_tps データも収集（副次）

## 計測設計

### 条件マトリクス（3 条件）

| # | ctx | -b | -ub | 目的 |
|---|---:|---:|---:|---|
| Sb1 | 32,768 | 1,280 | 1,280 | ub=1024 (平坦) と ub=2048 (急増) の中間、4/5 分位点 |
| Sb2 | 32,768 | 1,536 | 1,536 | 中央値 |
| Sb3 | 32,768 | 1,792 | 1,792 | 7/8 分位点 |

### ctx 固定の理由

- Phase S で **CUDA0 の ctx 独立性は ub ≤ 1024 で確認済み**（ub=512/1024 で ctx=16k/32k/65k すべて同値）。境界特定では ctx=32768 固定で十分
- ctx=32768 は Phase S で S1-S4 条件として計測済みの系列なので比較が容易
- 3 条件に絞ることで **所要 30-40 分**に抑え、1 セッション完結

### 他の compute buffer の確認（副次）

- CUDA1/2 に ub × ctx cross 項が 4 params モデルで確定済み（R²=0.99999965）。この 3 点を加えても fit が破綻しないか確認
- CUDA3 = 0.9824·ub が引き続き maintained か（16 点で max_err 0.000）
- CUDA_Host も同様に 4p モデルで維持されるか

## スクリプト設計

### 流用するファイル（無改変）

- `measure_phaseI.sh` — ctx/ub 非依存
- `run_all.sh` — パラメータ化済
- `prompts/` ディレクトリ全体

### 複製 + 最小改変

- `start_phaseS.sh` → `start_phaseSb.sh` — `phaseS_` / `[start_phaseS]` を `phaseSb_` / `[start_phaseSb]` に置換
- `batch_S3onwards.sh` → `batch_boundary.sh` — 条件マトリクスを 3 行（ctx=32768 × ub=1280/1536/1792）に削減
- `aggregate_results.sh` → `aggregate_boundary.sh` — `out_S_*` → `out_Sb_*` に置換

### 新規（計算のみ、簡易）

- `fit_analysis_S.py` は **流用不要**。境界特定は数値の目視で十分。集計後に 19 点マトリクス (Phase S の 16 点 + 本 Phase の 3 点) を含む summary table を生成するだけ

## 再現手順

```bash
# 1. ロック取得 + ディレクトリ準備
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
PHASE_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseSb-ub-boundary"
mkdir -p "$PHASE_DIR/startup_logs"

# 2. スクリプト流用（Phase S の attachment から）
PHASE_S="report/attachment/2026-04-19_120715_qwen3-122b-c3-phaseS-ub-ctx-2d"
cp "$PHASE_S"/{measure_phaseI.sh,run_all.sh,start_phaseS.sh,aggregate_results.sh,batch_S3onwards.sh} "$PHASE_DIR/"
cp -r "$PHASE_S/prompts" "$PHASE_DIR/"
mv "$PHASE_DIR/start_phaseS.sh" "$PHASE_DIR/start_phaseSb.sh"
mv "$PHASE_DIR/batch_S3onwards.sh" "$PHASE_DIR/batch_boundary.sh"
mv "$PHASE_DIR/aggregate_results.sh" "$PHASE_DIR/aggregate_boundary.sh"

# prefix 置換
sed -i 's/phaseS_/phaseSb_/g; s/\[start_phaseS\]/[start_phaseSb]/g' "$PHASE_DIR/start_phaseSb.sh"
sed -i 's/out_S_/out_Sb_/g' "$PHASE_DIR/aggregate_boundary.sh"
# batch_boundary.sh は条件配列を手動で編集（3 条件のみ: 32768 1280/1536/1792）

cd "$PHASE_DIR"

# 3. 一括バッチ計測
bash batch_boundary.sh > batch_boundary.log 2>&1

# 4. 停止・集計・解析・解放
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash aggregate_boundary.sh > results.tsv
grep -E "sched_reserve:|KV buffer|graph nodes|graph splits|cudaMalloc|failed to allocate|reserve took|llama_kv_cache: size|llama_memory_recurrent: size" \
  startup_logs/*.log > compute_buffer_summary.txt
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 所要時間見積もり

- セットアップ: 5 分
- 3 条件計測（batch、各 10-11 分）: 30-33 分
- 集計・解析・ロック解放: 3 分
- **合計: 約 40 分**

## 成功条件

- [ ] 3 条件すべて起動成功（/health OK、OOM ゼロ、-ub 下限拒否ゼロ）
- [ ] CUDA3 3 点で `0.9824·ub ± 0 MiB`（ctx 独立性維持）
- [ ] CUDA0 3 点で境界 ub\* を `[1280, 1536, 1792, 2048]` のいずれかの区間に確定
- [ ] CUDA1/2 / CUDA_Host 3 点が Phase S 確定 4 params モデルの予測値と max_err < 5 MiB で一致
- [ ] graph nodes=4473 / splits_bs1=77 の 3 条件不変
- [ ] KV buffer 3 点で `96·(ctx/16384)` 式と誤差 0 MiB

## 判定ロジック（CUDA0 境界 ub\*）

計測結果の CUDA0 値を以下の閾値で判定:

- CUDA0 < 1000 MiB（≈ 平坦域 973 MiB 近傍）→ ub ≤ ub\*、平坦域
- CUDA0 ≥ 1000 MiB（急増域）→ ub ≥ ub\*、急増域

ub=1280/1536/1792 の 3 点で値を観察し、どの点で jump が発生したかで ub\* を `(1280,1536]`、`(1536,1792]`、`(1792,2048]` の区間に絞り込む。

## 主要ファイル

### 参照（読み取り専用）

- `/home/ubuntu/projects/llm-server-ops/report/2026-04-19_120715_qwen3-122b-c3-phaseS-ub-ctx-2d.md` — 直前レポート、16 点マトリクス・区分モデル仕様
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-19_120715_qwen3-122b-c3-phaseS-ub-ctx-2d/` — Phase S スクリプト一式
- `.claude/skills/gpu-server/scripts/lock.sh`, `unlock.sh` — ロック管理
- `.claude/skills/llama-server/scripts/stop.sh` — サーバ停止

### 新規作成

- `report/attachment/<ts>_qwen3-122b-c3-phaseSb-ub-boundary/start_phaseSb.sh`
- `report/attachment/<ts>_qwen3-122b-c3-phaseSb-ub-boundary/batch_boundary.sh`
- `report/attachment/<ts>_qwen3-122b-c3-phaseSb-ub-boundary/aggregate_boundary.sh`
- `report/attachment/<ts>_qwen3-122b-c3-phaseSb-ub-boundary/results.tsv`
- `report/attachment/<ts>_qwen3-122b-c3-phaseSb-ub-boundary/compute_buffer_summary.txt`
- `report/attachment/<ts>_qwen3-122b-c3-phaseSb-ub-boundary/plan.md` (本プランのコピー)
- `report/<ts>_qwen3-122b-c3-phaseSb-ub-boundary.md` (最終レポート、「未検証事項」「検証完了後に実施すべき TODO」セクション含む)

## 検証方法

### 実行時検証（各条件起動後）

- `curl -m 5 http://10.1.4.14:8000/health` で /health OK を確認
- 起動ログから `llm_load_tensors: CUDA0/1/2/3 compute buffer size` を grep し、目視で CUDA0 値が 1000 MiB 境界のどちら側かを確認

### 事後検証（全 3 条件完了後）

- `results.tsv` に 9 行 (3 条件 × warmup/1k × 3 run) + ヘッダが生成されている
- `compute_buffer_summary.txt` から各条件の CUDA0/1/2/3/Host を抽出し、Phase S の 16 点テーブルに追加して 19 点で整合性確認
- Phase S 4 params cross 項モデル `CUDA1/2 = 520.26 + 3.903e-3·Δctx + 0.2538·Δub + 1.910e-6·Δctx·Δub` の予測値と計測値を比較（max_err < 5 MiB が望ましい）

## 未検証事項（レポート末尾記載予定）

- Phase S-boundary で残る未検証項目（詳細はレポート執筆時に直前の Phase S レポートから継承・更新）
- 本 Phase で新規判明する項目（例: さらに細かい ub\* 特定 (1280 未満の境界)、fa=0 での同様挙動、q8_0 KV での同様挙動）

## 検証完了後に実施すべき TODO（レポート末尾記載予定）

- 最優先 TODO: Phase S で既登録の lint 組み込み（Phase S レポートの記載を継承）
- 本 Phase で得られた区分境界 ub\* を反映した CUDA0 区分モデルの条件式更新
- skill ドキュメント / CLAUDE.md 更新の追記
