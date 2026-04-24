# Phase Sb-fine2: CUDA0 境界 ub\* の 16-token 精度絞り込み

## Context

直前レポート [2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary.md](../../projects/llm-server-ops/report/2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary.md) 末尾「未検証事項 / 新規項目」最上位に登録された **★最優先: CUDA0 境界 ub\* の 16-token 精度絞り込み** を実施する。

- Phase Sb-fine で境界区間は **ub\* ∈ (1536, 1600]**（64-token 精度）まで絞り込まれた。
- ub=1536 → 1600 で CUDA0 が +4.85 MiB、ub=1600 → 1664 で +18.26 MiB（平坦域 +3.25 の 22 倍）の非連続的増加が発生。
- ub=1600 は既に ub ≥ 1600 線形モデル `1002.61 + 0.2853·(ub − 1664)` 上（平坦域より大幅に上）にある一方、ub=1536 は平坦域（+0.0127 MiB/token）にある。
- したがって境界 ub\* は (1536, 1600] の 64-token 区間内のどこかに存在し、本 Phase で **16-token 精度**（4 倍改善）で特定する。

**成功条件**:
1. 4 条件 (ub=1552/1568/1584/1600) すべて起動成功・OOM ゼロ・/health OK
2. CUDA0 4 点から境界 ub\* を 16-token 精度で特定
3. Phase Sb-fine の ub=1600 実測値 (CUDA0=984.35) が再現される（セッション間再現性確認）
4. CUDA1/2, CUDA3, CUDA_Host は Phase Sb 4p モデル / 純 ub 比例で max_err < 1 MiB

## アプローチ

Phase Sb-fine の scripts（`start_phaseSbf.sh`, `batch_boundary_fine.sh`, `aggregate_boundary_fine.sh`, `analyze_boundary_fine.py`, `measure_phaseI.sh`, `run_all.sh`, `prompts/`）をほぼそのまま流用し、CONDS 配列と解析スクリプト内の実測値プレースホルダのみ差し替える。

- **名称**: Phase Sb-fine2、プレフィックス `Sbf2_` / `phaseSbf2_`
- **タイムスタンプ**: 計測開始時の時刻（例 `2026-04-19_HHMMSS`）
- **所要時間見積**: Phase Sb-fine と同規模（約 44 分計測 + 5-10 分後処理）

## 実施手順

### 1. 準備（1-2 分、read-only + ディレクトリ作成）

```bash
# GPU サーバロック取得
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100

# Phase Sb-fine2 ディレクトリ作成
TS=$(date +%Y-%m-%d_%H%M%S)
PHASE_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseSbfine2-ub16tok"
mkdir -p "$PHASE_DIR/startup_logs"

# Phase Sb-fine のスクリプト一式をコピー
PHASE_SBF="report/attachment/2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary"
cp "$PHASE_SBF"/{measure_phaseI.sh,run_all.sh,start_phaseSbf.sh,aggregate_boundary_fine.sh,batch_boundary_fine.sh,analyze_boundary_fine.py} "$PHASE_DIR/"
cp -r "$PHASE_SBF/prompts" "$PHASE_DIR/"

# プレフィックス置換: Sbf -> Sbf2, phaseSbf -> phaseSbf2
mv "$PHASE_DIR/start_phaseSbf.sh" "$PHASE_DIR/start_phaseSbf2.sh"
mv "$PHASE_DIR/batch_boundary_fine.sh" "$PHASE_DIR/batch_boundary_fine2.sh"
mv "$PHASE_DIR/aggregate_boundary_fine.sh" "$PHASE_DIR/aggregate_boundary_fine2.sh"
mv "$PHASE_DIR/analyze_boundary_fine.py" "$PHASE_DIR/analyze_boundary_fine2.py"

sed -i 's/phaseSbf_/phaseSbf2_/g; s/\[start_phaseSbf\]/[start_phaseSbf2]/g' "$PHASE_DIR/start_phaseSbf2.sh"
sed -i 's/\[batchSbf\]/[batchSbf2]/g; s/start_phaseSbf\.sh/start_phaseSbf2.sh/g; s/phaseSbf_/phaseSbf2_/g; s/TAG_PREFIX="Sbf_/TAG_PREFIX="Sbf2_/g; s/run_Sbf_ctx/run_Sbf2_ctx/g; s/start_stdout_Sbf_ctx/start_stdout_Sbf2_ctx/g' "$PHASE_DIR/batch_boundary_fine2.sh"
sed -i 's/out_Sbf_\*/out_Sbf2_*/g' "$PHASE_DIR/aggregate_boundary_fine2.sh"
```

### 2. スクリプト編集（read-only エリア外、Edit ツールで実施）

- **`batch_boundary_fine2.sh` の CONDS 配列（行 14-19）** を以下に書き換え:
  ```bash
  CONDS=(
    "32768 1552"
    "32768 1568"
    "32768 1584"
    "32768 1600"
  )
  ```

- **`analyze_boundary_fine2.py` の MEAS_SBF 配列**: 計測後に実測値で書き換え（手順 4 で）。現時点では Phase Sb-fine の 4 点のまま、Phase Sb-fine2 の新 4 点へは計測後に置き換える。変数名は `MEAS_SBF2` に変更し、比較対象として Phase Sb-fine の ub=1600 実測値を参照対象に加える。

### 3. バッチ計測（約 44 分）

```bash
cd "$PHASE_DIR"
bash batch_boundary_fine2.sh > batch_boundary_fine2.log 2>&1
bash ../../../.claude/skills/llama-server/scripts/stop.sh t120h-p100
```

各条件 (ub=1552/1568/1584/1600) × warmup + 1k prompt × 3 run、合計 24 run。Phase Sb-fine と同じ pattern なので stdout redirect 方式のハングリスクは低い。

### 4. 集計・解析（5-10 分）

```bash
bash aggregate_boundary_fine2.sh > results.tsv
grep -E "sched_reserve:|KV buffer|graph nodes|graph splits|cudaMalloc|failed to allocate|reserve took|llama_kv_cache: size|llama_memory_recurrent: size" \
  startup_logs/*.log > compute_buffer_summary.txt
# compute_buffer_summary.txt から CUDA0/1/2/3/Host の 4 点実測値を analyze_boundary_fine2.py の MEAS_SBF2 に転記
python3 analyze_boundary_fine2.py | tee analyze_boundary_fine2.txt
```

解析内容:
- **境界判定**: ub=1552/1568/1584/1600 の CUDA0 4 点で「平坦域 (+0.0127 MiB/token) から線形 (+0.2853 MiB/token) への遷移」がどの ub で発生したか特定
- **3 パターン仮説**:
  - (a) ub\* ≤ 1552: 全 4 点が線形モデル上（既に遷移済み）
  - (b) 1552 < ub\* ≤ 1584: 4 点内のどこかで遷移（中間に +10 〜 +20 MiB のジャンプ）
  - (c) 1584 < ub\* ≤ 1600: ub=1552/1568/1584 の 3 点は平坦域傾き、ub=1600 のみ線形モデル上
- **ub=1600 セッション間再現性**: Phase Sb-fine での CUDA0=984.35 MiB との乖離幅 (< 1 MiB 目標)
- **ub ≥ 1600 線形モデル再検証**: Phase Sb-fine の線形モデルに新 4 点を追加した時の max_err

### 5. レポート作成

`report/2026-04-19_HHMMSS_qwen3-122b-c3-phaseSbfine2-ub16tok.md` を [REPORT.md](../../projects/llm-server-ops/REPORT.md) 形式に従って作成。直前レポートと同様に「未検証事項」「検証完了後に実施すべき TODO」セクションを含める。

### 6. 解放

```bash
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 変更対象ファイル

- **新規作成**: `report/attachment/${TS}_qwen3-122b-c3-phaseSbfine2-ub16tok/` 配下一式
  - `start_phaseSbf2.sh`（Phase Sb-fine からプレフィックス置換）
  - `batch_boundary_fine2.sh`（CONDS 4 行置換 + プレフィックス置換）
  - `aggregate_boundary_fine2.sh`（パターン置換）
  - `analyze_boundary_fine2.py`（MEAS_SBF2 への差し替え）
  - `measure_phaseI.sh`, `run_all.sh`, `prompts/`（無改変流用）
  - 計測アーティファクト（`out_Sbf2_*/`, `startup_logs/*.log`, `results.tsv`, `compute_buffer_summary.txt`, `analyze_boundary_fine2.txt`, `batch_boundary_fine2.log`）
- **新規作成**: `report/2026-04-19_HHMMSS_qwen3-122b-c3-phaseSbfine2-ub16tok.md`
- **編集なし**: `.claude/skills/` 配下、`CLAUDE.md`、既存 `report/*` ファイル

## 検証方法

- **成功条件 1 (起動)**: `batch_boundary_fine2.log` で 4 条件すべて `/health OK` 確認、`OOM` / `-ub rejected` ゼロ
- **成功条件 2 (境界判定)**: `analyze_boundary_fine2.txt` で境界 ub\* の 16-token 区間（4 パターンのいずれか）を特定
- **成功条件 3 (再現性)**: ub=1600 新計測値と Phase Sb-fine の 984.35 MiB の差分 < 1 MiB（物理的に同じ条件なので、ページキャッシュ差のみ）
- **成功条件 4 (既存モデル維持)**: CUDA1/2, CUDA3, CUDA_Host の 4 点で Phase Sb 4p / 純比例モデル max_err < 1 MiB
- **成功条件 5 (graph 構造不変)**: graph nodes=4473 / splits_bs1=77 の 4 条件不変
- **成功条件 6 (KV buffer)**: 4 点で 192 MiB 誤差 0

## リスク・注意点

- **SSH/tty ハング**: Phase Sb-fine で 11 条件連続成功済みの stdout redirect パターンを流用するため低リスク
- **スクリプト置換漏れ**: `sed -i` で置換した後、各スクリプト冒頭を目視確認（特に `batch_boundary_fine2.sh` の CONDS / TAG_PREFIX）
- **lock 取り忘れ**: 手順 1 で必ず lock 取得後に起動、解放は手順 6 で実施
- **ub=1552 で既に境界を越えている可能性**: その場合「境界は (1536, 1552] にある」という結果になり、Phase Sb-fine3（ub=1537/1540/1544/1548 等）が必要になる。これは次 Phase の TODO として追記
