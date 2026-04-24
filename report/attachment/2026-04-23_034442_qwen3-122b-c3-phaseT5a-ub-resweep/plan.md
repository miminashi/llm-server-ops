# Phase T-5a-ub: B18 × ub 再スイープ

## Context

直前 Phase T-5a で B18 (CPU offload 18 層) × ctx=32k × ub=512 × threads=40 が **eval 18.006 t/s** を達成し歴代最高 (Phase D 比 +19.80%)。T-5a レポートが「最優先未検証事項」として明示したのが本プラン: **B28 で確定した「ub=512 最適」は B18 でも保たれるか**。

B18 は CUDA0 が 91.8% 使用 (1,330 MiB free / 16,269 MiB) で B28 (13,858 MiB free) と VRAM 構造が大きく異なる。compute_buf は ub にほぼ線形比例するため、ub 増加で OOM リスクが急上昇する一方、ub 減少で eval 改善する可能性も残っている (T-5f で B28 ub=384 が ub=512 と僅差 16.40 vs 16.46 だった先例)。本 Phase の意図は (1) **B18 の最適 ub 確定**、(2) drift bracket で T-5a baseline 18.006 の独立再現、(3) 19+ t/s 突破狙い。

ビルド不要・既存 scripts 流用で 100-130 分、ROI 最高。次々 Phase 候補 (T-5a-thr threads sweep, T-5a-ts tensor-split, T-6 ビルドフラグ) は本 Phase の baseline 確定後に判断する。

## ub スイープ値の設計

| ub | 期待 | VRAM 安全度 | 採否 |
|----|-----|-----------|------|
| 128 | T-5f trend 起点。B18 低 ub 形状把握 | safe | **採用** |
| 256 | T-5f で B28 16.43 (ub=512 と僅差)、B18 で逆転狙い | safe | **採用** |
| 384 | 中間補間 | safe | **採用** |
| 512 | drift 起点・終点。T-5a 18.006 再現 | tight (実証済) | **採用 ×2** |
| 768 | B18 で全く未測定。VRAM 圧迫 (~1,449 MiB compute_buf 推定) | risky → **dry probe で先に確認** | **採用** (probe 通過時) |
| 640 | 768 OOM 時の代替 | tight | predicate (768 OOM のみ) |
| 1024+ | OOM 確実視 (推定 free <0) | 危険 | 除外 |

**メイン構成**: `{128, 256, 384, 512a, 768, 512z}` (6 条件、unique ub=5、512 は drift bracket で 2 回)

T-5f が B28 で {64,128,256,384,512,768,1024,1586} の 8 ub 全測定済なので、本 Phase は B18 用に絞り込み、`ub=64` (T-5f で劇的低下既知) と `ub>=1024` (B18 OOM 必至) は除外して 5 unique ub に集中。

## CONDITIONS 配列 (実行順)

```bash
OT_TAG="B18"
OT_REGEX='blk\.([0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'  # 18 CPU 層: 0-3, 24, 31-39

CONDITIONS=(
  'B18_ub512a#32768#512'   # 1. drift 起点 (T-5a 18.006 再現確認)
  'B18_ub768#32768#768'    # 2. 高 ub 側 (probe 後最初に置きリスク早期暴露)
  'B18_ub384#32768#384'    # 3.
  'B18_ub256#32768#256'    # 4. ub=256 vs 512 の Pareto 候補
  'B18_ub128#32768#128'    # 5.
  'B18_ub512z#32768#512'   # 6. drift 終点
)
```

固定: ctx=32768, KV=q8_0 (k/v), split-mode=layer, threads=40, numactl -N1 -m1, -ngl 999, flash-attn=1, parallel=1, poll=0

## 作業手順

### Step 1. プラン承認後の準備 (5 min)

1. `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` でタイムスタンプ取得 → `<TS>` とする
2. レポート名: `<TS>_qwen3-122b-c3-phaseT5a-ub-resweep`
3. 添付ディレクトリ作成: `mkdir -p report/attachment/<TS>_qwen3-122b-c3-phaseT5a-ub-resweep/{prompts,startup_logs}`
4. プランファイルコピー: `cp /home/ubuntu/.claude/plans/phase-t-5a-b18-delightful-kettle.md report/attachment/<TS>_qwen3-122b-c3-phaseT5a-ub-resweep/plan.md`

### Step 2. GPU server lock 取得 (1 min)

```bash
.claude/skills/gpu-server/scripts/lock-status.sh t120h-p100   # 空き確認
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
```

### Step 3. scripts コピー & 改修 (5-10 min)

T-5a から流用 (改修不要):
```bash
SRC_T5A=report/attachment/2026-04-23_014104_qwen3-122b-c3-phaseT5a-ot-redistribution
DST=report/attachment/<TS>_qwen3-122b-c3-phaseT5a-ub-resweep
cp $SRC_T5A/start_phaseT5.sh $SRC_T5A/run_all.sh $SRC_T5A/measure_phaseT5.sh $DST/
cp $SRC_T5A/prompts/prompt_1k.txt $DST/prompts/
```

T-5f から流用 (改修要):
```bash
SRC_T5F=report/attachment/2026-04-22_232010_qwen3-122b-c3-phaseT5f-ub-fine-sweep
cp $SRC_T5F/batch_phaseT5f.sh   $DST/batch_phaseT5a-ub.sh
cp $SRC_T5F/analyze_phaseT5f.py $DST/analyze_phaseT5a-ub.py
cp $SRC_T5F/plot_phaseT5f.py    $DST/plot_phaseT5a-ub.py
```

#### `batch_phaseT5a-ub.sh` 改修

- ヘッダコメントを「Phase T-5a-ub: B18 × ub 再スイープ + drift bracket / 6 条件」に
- `OT_TAG="B28"` → `OT_TAG="B18"`
- `OT_REGEX='...1[0-3]...'` → `OT_REGEX='blk\.([0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'`
- `CONDITIONS` 配列を上記 6 件に差し替え
- ログ prefix `[batchT5f]` → `[batchT5aub]`
- TAG_PREFIX `T5f_` → `T5aub_` (run_all.sh 呼び出し、startup_logs コピー、ログ名)

#### `analyze_phaseT5a-ub.py` 改修

- docstring 更新
- `CONDITIONS` を 6 件 (LABEL, 32768, UB, 40, run_idx, NOTE) に差し替え
- `OT_TAG = "B18"`, `CPU_LAYERS = 18`
- PEAK 定数追加: `PEAK_PHASE_T5F_BEST = 16.455`, `PEAK_PHASE_T5A_BEST = 18.006`
- `verdict()` の最先頭に `if mean_eval > PEAK_PHASE_T5A_BEST: return "**SURPASS_T5a (歴代新記録)**"` を追加
- 出力ファイル名 `phaseT5f_*` → `phaseT5a-ub_*`
- TAG_COND ディレクトリ prefix `out_T5f_` → `out_T5aub_`
- drift 閾値を二段階化 (健全 < 0.15 / 要注意 < 0.30 / 大 ≥ 0.30)
- 補正後の主比較対象を T-5a baseline 18.006 に
- 歴代 Phase 比較表に T-5f (16.455) と T-5a (18.006) を追加
- pivot に「T-5a baseline 比較」セクションを追加 (B18_ub512a vs T-5a B18_run1 の独立再現性判定)

#### `plot_phaseT5a-ub.py` 改修

- docstring / 出力 PNG ファイル名 → `phaseT5aub_*`
- stats CSV 入力 → `phaseT5a-ub_stats.csv`
- `RUN_ORDER` を 6 件 (B18_ub*) に差し替え
- PEAK 定数追加 (T-5a 18.006、T-5f 16.455)
- trend axhline に T-5a baseline (18.006、最も濃い線) を追加
- trend で除外する drift 終点ラベルを `B18_ub512z` に
- 各タイトルを「B18 × ctx=32k × ub」に
- drift グラフに T-5a 18.006 axhline 追加、x 軸 limit を 6 点に

### Step 4. dry probe (5-15 min)

ub=768 が B18 で起動するか先に確認 (main batch 中の OOM で時間溝を作らないため)。

```bash
cd $DST
bash /home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh t120h-p100
sleep 5

FLASH_ATTN=1 CTX_SIZE=32768 BATCH_SIZE=768 UB_SIZE=768 \
  CACHE_TYPE_K=q8_0 CACHE_TYPE_V=q8_0 SPLIT_MODE=layer THREADS=40 \
  OT_TAG=B18 OT_REGEX='blk\.([0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU' \
  bash start_phaseT5.sh 2>&1 | tee dry_start_ub768.log

# 結果記録
ssh t120h-p100 "grep -E 'CUDA0 (model|KV|compute|buffer)' \
  /tmp/llama-server_phaseT5_B18_t40_smlayer_kq8_0_vq8_0_fa1_ctx32768_b768_ub768.log" \
  | tee dry_start_ub768_vram.log

bash /home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh t120h-p100
sleep 5
```

判定:

| dry probe ub=768 | 次アクション |
|-----------------|------------|
| /health OK (起動成功) | main batch CONDITIONS をそのまま (ub=768 含む) で実行 |
| OOM (CUDA buffer alloc fail) | ub=768 を ub=640 に置換して再 probe → 成立すれば main batch、再 OOM なら 768/640 とも除外して 5 条件で実行 |

### Step 5. main batch 実行 (約 78 min)

```bash
cd $DST
nohup bash batch_phaseT5a-ub.sh > batch_phaseT5a-ub.log 2>&1 &
```

監視: `tail -f batch_phaseT5a-ub.log` で各 condition の `start → /health OK → run_all done` 進行確認。1 条件 ~13 min、6 条件で約 78 min。

### Step 6. 解析 + 可視化 (2 min)

```bash
cd $DST
python3 analyze_phaseT5a-ub.py | tee phaseT5a-ub_pivot.md
python3 plot_phaseT5a-ub.py
ls -la phaseT5aub_*.png  # 3 個 >50KB 確認
```

### Step 7. レポート作成 (30-45 min)

REPORT.md ルールに従い `report/<TS>_qwen3-122b-c3-phaseT5a-ub-resweep.md` を作成。タイトル簡潔 (50 字以内)、必須セクション:

- 添付ファイル (plan.md / pivot / TSV / CSV / batch ログ / start / batch / analyze / plot 各 script、dry_start ログ)
- 核心発見サマリ (3 PNG 埋め込みを冒頭に、結果ハイライト 1 段落、結果テーブル)
- 前提・目的 (背景、軸選定、判定基準)
- 環境情報
- 再現方法 (Step 2-6 の絞り込み版)
- 結果詳細 (条件別 / drift bracket / 補正後 / OT 別再現性 / 歴代比較 / 安定性 / VRAM 実測)
- 仮説解釈
- **未検証事項** (必須): 残った Phase 候補
- **検証完了後 TODO** (必須): 短期/中期/長期で優先度付け
- **歴代 Phase 全比較表** (必須、T-5a baseline 18.006 を 1 行入れて全 Phase 並べる)
- 参照レポート

### Step 8. discord 通知 + lock 解放 (1 min)

```bash
.claude/skills/discord-notify/scripts/notify.sh \
  "Phase T-5a-ub 完了: B18 × ub 再スイープ (eval ベスト ... t/s)" \
  "report/<TS>_qwen3-122b-c3-phaseT5a-ub-resweep.md"

.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 検証 (success criteria)

| 判定 | 閾値 | 用途 |
|------|------|------|
| eval JSON 揃い | 各 condition 5 個 | sweep 完了確認 |
| drift 健全 | \|`B18_ub512a` - `B18_ub512z`\| < 0.30 t/s | T-5a が 0.536 だったため緩和、≥ 0.30 は要注意 |
| **B18 baseline 再現** | drift 補正後 `B18_ub512a` ≈ 18.006 ± 0.5 t/s | T-5a 独立再現性確認 |
| **ub=512 最適性** | drift 補正後で ub=512 が他 ub より高い | 確認 → ub=512 を確定 |
| **新記録更新** | いずれかの ub で eval_mean > 18.006 t/s | 達成 → 即新記録 |
| OOM 件数 | main batch で 0 件 | dry probe で除外済の前提 |

## リスク

| リスク | 対策 |
|--------|------|
| ub=768 OOM | dry probe で先に確認、OOM なら ub=640 にスイッチ、それも OOM なら 5 条件で実行 |
| drift 大 (T-5a で +3.34% の前科) | 線形補正適用、`B18_ub512a` を主比較軸とし drift 値も併記 |
| condition 個別失敗 | batch script は `healthy=0` で `continue`、analyze は欠損を `no_data` 処理 (T-5a で実証済) |
| 他セッションとの衝突 | 開始前 `lock-status.sh` で確認、`lock.sh` で取得、終了時 `unlock.sh` |
| サーバ間 drift | dry probe 自体が GPU warmup を兼ねる、main batch 1 条件目で T-5a 18.006 と比較 |

## 推定所要時間

| ステップ | 時間 |
|---------|------|
| 準備 (ディレクトリ作成、scripts cp、改修) | 10-15 min |
| GPU lock 取得 + dry probe ub=768 | 7 min |
| (dry probe ub=640 — 768 OOM 時) | +7 min |
| main batch (6 条件 × ~13 min) | 78 min |
| analyze + plot | 2 min |
| レポート作成 | 30-45 min |
| discord 通知 + lock 解放 | 1 min |
| **合計 (768 通過)** | **約 130-150 min** |
| **合計 (768 OOM, 640 採用)** | **約 140-160 min** |

## 重要ファイル (絶対パス)

実装で参照・コピー:
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-23_014104_qwen3-122b-c3-phaseT5a-ot-redistribution/start_phaseT5.sh`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-23_014104_qwen3-122b-c3-phaseT5a-ot-redistribution/run_all.sh`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-23_014104_qwen3-122b-c3-phaseT5a-ot-redistribution/measure_phaseT5.sh`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-23_014104_qwen3-122b-c3-phaseT5a-ot-redistribution/prompts/prompt_1k.txt`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-22_232010_qwen3-122b-c3-phaseT5f-ub-fine-sweep/batch_phaseT5f.sh`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-22_232010_qwen3-122b-c3-phaseT5f-ub-fine-sweep/analyze_phaseT5f.py`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-22_232010_qwen3-122b-c3-phaseT5f-ub-fine-sweep/plot_phaseT5f.py`

参照 (規約・前 Phase):
- `/home/ubuntu/projects/llm-server-ops/REPORT.md`
- `/home/ubuntu/projects/llm-server-ops/report/2026-04-23_014104_qwen3-122b-c3-phaseT5a-ot-redistribution.md`
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/lock.sh`
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/unlock.sh`
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh`
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/discord-notify/scripts/notify.sh`

新規生成 (実行時):
- `/home/ubuntu/projects/llm-server-ops/report/<TS>_qwen3-122b-c3-phaseT5a-ub-resweep.md`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/<TS>_qwen3-122b-c3-phaseT5a-ub-resweep/` 配下一式
