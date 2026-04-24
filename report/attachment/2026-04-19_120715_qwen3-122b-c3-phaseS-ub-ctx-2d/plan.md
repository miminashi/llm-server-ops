# Phase S: CUDA0 二次モデルの ub 依存性 (ub × ctx 2 軸スキャン)

## Context

Phase R-ctx3 (`report/2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints.md`) で、Qwen3.5-122B-A10B (t120h-p100, fa=1, f16 KV, C-D3 base) の compute buffer を ctx=16k/32k/65k/131k の 4 点でフィットし:

- **CUDA1/2/3/Host は完全線形** (R²=1.00000000) — Phase R 2 点モデル係数で十分
- **CUDA0 のみ二次関数**: `1046.29 + 3.269e-3·Δctx + 5.770e-8·Δctx² + 0.077·(ub-2048)` (R²=0.99998)

しかし上記 CUDA0 モデルは **ub=2048 固定での ctx fit** に Phase Q 由来の Δub 線形補正を後付けしただけで、ub 可変時の二次項 c および相互作用項の挙動は未検証。Phase R-ctx3 の「未検証事項（新規項目）」と「検証完了後 TODO（新規項目）」両方で **「Phase R-ctx3-ub 候補」** として最優先で登録されている。

本 Phase S は ub=512/1024/4096/8192 × ctx=32768/65536 の 8 条件を実測し、Phase Q の ctx=16k × ub 5 点 + Phase R-ctx3 の ub=2048 × ctx 3 点と合わせて **16 点で 2 次曲面 (6 パラメータ) を最小二乗フィット**することで、起動前 lint で使う CUDA0 予測モデルを ub × ctx 2 軸で確定させる。これにより、ub を 2048 以外に変更した運用で起動前 VRAM 予測誤差が現状の最大 12〜15% から ≤ 1% へ改善する見込み。

## 実施内容

### 計測条件マトリクス (8 新規条件)

固定: fa=1, b=ub (同値), f16 KV, C-D3 base, `numactl --cpunodebind=1 --membind=1 -- --threads 40 --poll 0 -ngl 999`、`-ot 'blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'`

| ID | ctx | ub (=b) | 主採取対象 |
|----|-----|---------|----|
| S1 | 32768 | 512  | sched_reserve (CUDA0/1/2/3/Host) / KV / graph |
| S2 | 32768 | 1024 | 同上 |
| S3 | 32768 | 4096 | 同上 |
| S4 | 32768 | 8192 | 同上 |
| S5 | 65536 | 512  | 同上 |
| S6 | 65536 | 1024 | 同上 |
| S7 | 65536 | 4096 | 同上 |
| S8 | 65536 | 8192 | 同上 |

各条件 `SIZES="warmup 1k"` のみ (compute buffer 主目的、eval 性能トレンドは Phase Q/R 取得済み)。

### VRAM 事前リスク判定

P100 16,269 MiB/GPU。Phase Q 係数 (CUDA3≈0.9824·ub, CUDA1/2≈0.254·ub) と Phase R-ctx3 ctx 線形成分から S8 (ctx=65k×ub=8192) を試算:
- CUDA3: 常駐 2,110 + 0.9824·8192 ≈ **10,156 MiB** → 余裕 6,113 MiB
- CUDA1/2: 常駐 9,971 + 712 (ctx成分) + 0.254·8192 ≈ **12,564 MiB** → 余裕 3,705 MiB
- CUDA0: 常駐 1,726 + 約 3,000 MiB (二次成分込み) → 余裕大

**8 条件すべて起動可能と予測**。OOM 検出 (start_phaseS.sh exit 2) と GATE_MIB=1500 ガードは保持。

## 重要ファイルのパス

### 編集予定 (新規 attachment ディレクトリ配下にコピーして改変)

実行時に `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得した TS で:

- `report/attachment/${TS}_qwen3-122b-c3-phaseS-ub-ctx-2d/start_phaseS.sh` — Phase R-ctx3 の `start_phaseR.sh` を複製、`REMOTE_LOG` プレフィックス `phaseRctx3_` → `phaseS_` のみ変更
- `report/attachment/${TS}_qwen3-122b-c3-phaseS-ub-ctx-2d/aggregate_results.sh` — `out_Rctx3_*` → `out_S_*` glob 変更のみ
- `report/attachment/${TS}_qwen3-122b-c3-phaseS-ub-ctx-2d/run_all.sh` / `measure_phaseI.sh` / `prompts/` — **無改変流用**
- `report/attachment/${TS}_qwen3-122b-c3-phaseS-ub-ctx-2d/fit_analysis_S.py` — Phase R-ctx3 の `fit_analysis_Rctx3.py` (L223-273 の Gaussian elimination 二次フィット) を 2 変量 6 パラメータに拡張
- `report/attachment/${TS}_qwen3-122b-c3-phaseS-ub-ctx-2d/plan.md` — 本プランをコピー
- `report/${TS}_qwen3-122b-c3-phaseS-ub-ctx-2d.md` — 最終レポート (Phase R-ctx3 と同フォーマット、「未検証事項」「検証完了後に実施すべき TODO」セクション必須)

### 参照予定 (流用 or データソース)

- `report/attachment/2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints/{start_phaseR.sh, measure_phaseI.sh, run_all.sh, aggregate_results.sh, fit_analysis_Rctx3.py, prompts/}` — スクリプト雛形
- `report/attachment/2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/compute_buffer_summary.txt` — ctx=16k × ub=128/256/512/1024/2048 の 5 ub 点（フィット用既存データ）
- `report/attachment/2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints/compute_buffer_summary.txt` — ub=2048 × ctx=32k/65k 既存データ
- `.claude/skills/gpu-server/scripts/{lock,unlock}.sh` — t120h-p100 排他制御
- `.claude/skills/llama-server/scripts/stop.sh` — llama-server 停止

## 2 軸フィット数式と実装

モデル: `CUDA0 = a + b·Δctx + c·Δctx² + d·Δub + e·Δctx·Δub + f·Δub²`
- Δctx = ctx − 16384、Δub = ub − 2048
- 6 パラメータ、計 16 点 (Phase Q 5 点 + Phase R-ctx3 3 点 + Phase S 8 点)、自由度 10

実装: `fit_analysis_Rctx3.py` の Gaussian elimination 関数を 6×6 へ拡張。設計行列 X (16×6) と応答 y (16) で正規方程式 `XᵀX·β = Xᵀy` を解く。R² と各点予測誤差 (MiB / %) を出力。Phase R-ctx3 単変量モデルとの差分も並列出力。

CUDA1/2/Host も同様に 2 軸 (Δctx, Δub) 線形フィットを実施し、相互作用項なしの単純加法モデル `intercept + slope_ctx·Δctx + slope_ub·Δub` の R² を確認。

## 実行フロー

```bash
# 1. ロック取得 + ディレクトリ準備
SKILL_DIR=/home/ubuntu/projects/llm-server-ops
bash $SKILL_DIR/.claude/skills/gpu-server/scripts/lock.sh t120h-p100
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
PHASE_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseS-ub-ctx-2d"
mkdir -p "$PHASE_DIR/startup_logs"
PHASE_R3="report/attachment/2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints"
cp "$PHASE_R3"/{measure_phaseI.sh,run_all.sh,aggregate_results.sh,start_phaseR.sh} "$PHASE_DIR/"
cp -r "$PHASE_R3/prompts" "$PHASE_DIR/"
mv "$PHASE_DIR/start_phaseR.sh" "$PHASE_DIR/start_phaseS.sh"
# プレフィックス置換 (sed/Edit) phaseRctx3_ → phaseS_, out_Rctx3_ → out_S_

# 2. プラン添付
cp /home/ubuntu/.claude/plans/todo-humble-flame.md "$PHASE_DIR/plan.md"

cd "$PHASE_DIR"

# 3. fit_analysis_S.py 作成 (fit_analysis_Rctx3.py から)
# ※ Edit/Write で 2 軸 6 パラメータ拡張

# 4. 8 条件ループ
for cond in "32768 512" "32768 1024" "32768 4096" "32768 8192" \
            "65536 512" "65536 1024" "65536 4096" "65536 8192"; do
  read CTX UB <<< "$cond"
  bash $SKILL_DIR/.claude/skills/llama-server/scripts/stop.sh t120h-p100 || true
  FLASH_ATTN=1 CTX_SIZE=$CTX BATCH_SIZE=$UB UB_SIZE=$UB bash start_phaseS.sh
  PID=$(ssh t120h-p100 "ps -eo pid,comm | awk '\$2==\"llama-server\"{print \$1;exit}'")
  ssh t120h-p100 "cat /tmp/llama-server_phaseS_fa1_ctx${CTX}_b${UB}_ub${UB}.log" \
    > "startup_logs/fa1_ctx${CTX}_b${UB}_ub${UB}.log"
  TAG_PREFIX="S_f16_fa1_ctx${CTX}_b${UB}_ub${UB}" SIZES="warmup 1k" \
    GATE_SIZES="1k" GATE_MIB=1500 PID=$PID bash run_all.sh
done

# 5. 停止 + 集計 + 解析 + 解放
bash $SKILL_DIR/.claude/skills/llama-server/scripts/stop.sh t120h-p100
bash aggregate_results.sh > results.tsv
grep -E "sched_reserve:|KV buffer|graph nodes|graph splits|cudaMalloc|failed to allocate|reserve took|llama_kv_cache: size|llama_memory_recurrent: size" \
  startup_logs/*.log > compute_buffer_summary.txt
python3 fit_analysis_S.py | tee fit_analysis_S.txt
bash $SKILL_DIR/.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 想定所要時間

- 1 条件: 起動 60s + warmup 3run ≈ 120s + 1k 3run ≈ 180s + stop 30s ≈ **6.5 分**
- 8 条件 × 6.5 分 = **約 52 分** + ロック/集計/解析 約 10 分 = **計 60〜70 分**

## 成功条件

- [ ] 8 条件すべて起動成功 (/health OK、OOM ゼロ、-ub 下限拒否ゼロ)
- [ ] CUDA3 16 点で `0.9824·ub ± 2 MiB`（ctx 完全不依存の再確認）
- [ ] CUDA1/2/Host の 2 軸線形性 R² ≥ 0.999
- [ ] **CUDA0 二変量二次フィット R² ≥ 0.999**
- [ ] 相互作用項 e の評価: `|e · max(Δctx) · max(Δub)|` が CUDA0 中央値の 1% 未満なら "独立可分"、超えるなら "相互作用あり" と結論
- [ ] graph nodes=4473 / splits=136(bs=ub)+77 が 16 条件で一致
- [ ] Phase R-ctx3 単変量モデルの全 16 点予測誤差を一覧化、誤差 > 5% の条件を可視化

## 検証方法

1. **fit R² 評価**: fit_analysis_S.txt の CUDA0 R² ≥ 0.999 を確認
2. **Phase R-ctx3 単変量モデル比較**: 16 点で予測誤差 % を一覧、現行モデルが ub 可変時にどこまで誤差を持つか定量化
3. **graph 構造 16 点不変性確認**: compute_buffer_summary.txt から `graph nodes` / `graph splits` を grep
4. **KV buffer 比例性**: 96·(ctx/16384) との誤差を全 16 点で 0 MiB 確認

## レポート要件

- ファイル名: `report/${TS}_qwen3-122b-c3-phaseS-ub-ctx-2d.md`
- フォーマット: REPORT.md 準拠 + Phase R-ctx3 と同構成
- **必須セクション**: 添付ファイル / 参照 / 前提・目的 / 環境情報 / 再現方法 / 実行タイムライン / 実行結果サマリ / ボトルネック・副次発見 / 採用判定 / **未検証事項** / **検証完了後に実施すべき TODO** / 補足
- 添付ファイル: plan.md, start_phaseS.sh, run_all.sh, measure_phaseI.sh, aggregate_results.sh, fit_analysis_S.py, fit_analysis_S.txt, results.tsv, compute_buffer_summary.txt, startup_logs/*.log
- Phase R-ctx3 の「未検証事項」リストから本 Phase で潰せた項目に [x]、新規発生事項を「新規項目」として追記
- 「検証完了後に実施すべき TODO」も Phase R-ctx3 ベースに更新 (本 Phase 結果を起動前 lint へ組み込む TODO 等)
