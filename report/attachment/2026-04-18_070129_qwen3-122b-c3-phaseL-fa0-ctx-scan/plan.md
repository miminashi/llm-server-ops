# Phase L — ctx ≤ 4096 での flash-attn=0 起動可否スキャン

## Context（なぜこの作業を行うか）

Phase K（最新レポート）で「f16 KV + ctx=16384 で `--flash-attn 0` は graph_reserve 段階で CUDA0 に 18,176 MiB の compute buffer を要求 → OOM で起動不能」と判明した。Phase K レポートは「compute buffer は attention score matrix の O(n²) 依存で、ctx=4k で ~1.1 GB、ctx=2k で ~0.3 GB、ctx=1k で ~0.07 GB」という**仮説**を提示したが、**実験的検証は未実施**のまま残った。

本 Phase L は、Phase K 未検証事項（新規項目）のうち最優先の 2 件を同時に解決する:

1. **ctx ≤ 4096 での flash-attn=0 起動可否**: ctx を 4096 / 2048 / 1024 と段階的に縮小して起動閾値を確定
2. **O(n²) compute buffer スケーリング仮説の実測検証**: `ggml_backend_cuda_buffer_type_alloc_buffer: allocating ... MiB on device 0` ログから要求バイト数を採取し、Phase K 仮説値と突き合わせ
3. 副次目的: 起動可能な ctx で Phase K 未達の **fa=0 vs fa=1 eval/prompt A/B 比較**を取得

期待される成果: 「P100 16GB での flash-attn=0 起動境界 ctx 値」の確定と、flash-attn 本体の速度寄与の初計測。C-D3 採用継続の最終裏付け。

## 前提・構成

- **サーバ**: `t120h-p100`（10.1.4.14、P100 16GB × 4）。GPU サーバロック必須
- **モデル**: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- **ベース構成**: C-D3（NUMA node1 bind、threads 40、poll 0、b/ub 8192、-ngl 999、`-ot 'blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'`）
- **Phase K からの変更**: cache-type は `f16` 固定、**ctx のみ可変**、FLASH_ATTN は 0→1 両方

## 実装手順

### Step 1: 準備

```
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseL-fa0-ctx-scan"
mkdir -p "$REPORT_DIR"
# Phase K 資産を流用
cp report/attachment/2026-04-18_025221_qwen3-122b-c3-phaseK-f16-flashattn-ab/{run_all.sh,measure_phaseI.sh,aggregate_results.sh} "$REPORT_DIR/"
cp -r report/attachment/2026-04-18_025221_qwen3-122b-c3-phaseK-f16-flashattn-ab/prompts "$REPORT_DIR/"
```

### Step 2: start_phaseL.sh を新規作成（start_phaseK.sh ベース）

変更点:
- `CTX_SIZE` 環境変数を追加（既定 4096、`--ctx-size "${CTX_SIZE}"`）
- `FLASH_ATTN` 既定値を 0 に（Phase L の主目的）
- リモートログを `/tmp/llama-server_fa${FLASH_ATTN}_ctx${CTX_SIZE}.log` に分離
- ヘルスチェック待ちを 120s に短縮（fa=0 OOM は早期に落ちる）
- 終了時、起動失敗なら早期 abort する判定を次 3 パターンで grep:
  - `cudaMalloc failed: out of memory`
  - `ggml_gallocr_reserve_n_impl: failed to allocate CUDA0 buffer`
  - `graph_reserve: failed to allocate compute buffers`

### Step 3: aggregate_results.sh を Phase L 向けに編集

- 集計対象を `out_L_*` に変更

### Step 4: fa=0 降順スキャン（ctx 閾値確定）

```
for CTX in 4096 2048 1024; do
  FLASH_ATTN=0 CTX_SIZE=$CTX bash "$REPORT_DIR/start_phaseL.sh"
  # 起動成功 → break
  # 起動失敗 → remote log を fa0_startup_ctx${CTX}/llama-server.log に退避
done
```

起動成功した最大 ctx で: `FLASH_ATTN=0 CTX_SIZE=<X>`。`measure_phaseI.sh` を `SIZES` に ctx 内プロンプトのみ含めて実行:
- ctx=4096 → `SIZES="warmup 1k"`
- ctx=2048 → `SIZES="warmup 1k"`
- ctx=1024 → `SIZES="warmup"` のみ

`TAG_PREFIX=L_f16_fa0_ctx${CTX} RUNS=3 bash run_all.sh`、stop.sh で終了。

### Step 5: 同一 ctx で fa=1 計測（A/B 対照）

`FLASH_ATTN=1 CTX_SIZE=<X>` で再起動、同 `SIZES` で `TAG_PREFIX=L_f16_fa1_ctx${CTX}` 計測、stop.sh。

### Step 6: 集計・解放

```
cd "$REPORT_DIR"
bash aggregate_results.sh > results.tsv
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## 所要時間見積

- ロック・準備: 5 分
- fa=0 起動試行（最大 3 回）: 5〜10 分
- fa=0 計測（ctx 成功時、warmup+1k × 3 runs）: ~12 分
- fa=1 A/B 計測: ~12 分
- 集計・レポート作成: 30 分
- **合計 60〜70 分**

## 報告書骨子（`report/<TS>_qwen3-122b-c3-phaseL-fa0-ctx-scan.md`）

- 添付一覧、参照（Phase K, J）、前提・目的
- 環境情報
- 計測手順（ctx 降順スキャン + A/B）
- 実行結果:
  - **起動可否マトリクス**: ctx × fa
  - **compute buffer 実測 MiB と Phase K の O(n²) 仮説の比較表**
  - 起動成功 ctx での fa=0/1 eval_tps・prompt_tps 中央値と Δ
- 分析: P100 (CC 6.0) における flash-attn の速度寄与符号と大きさ、Phase K 仮説の確証/反証
- 採用判定: C-D3 継続妥当性の最終確認
- **未検証事項**（Phase K 継続 + Phase L 新規）
- **検証完了後に実施すべき TODO**（Phase K 継続 + Phase L 新規）

### Phase L 新規の未検証候補（初期案）

- ctx=4k fa=0 OOM 時、CPU offload を更に拡張して回避可能か（`-ot` 対象層の増加）
- fa=0 × ctx=4k で 8k プロンプトは不可能だが、複数プロンプト連結での prompt cache 挙動
- q8_0 KV で ctx を小さくした場合の graph_reserve 挙動（Phase K の 179 行停止が再現するか）
- Phase K fa=1 warmup と Phase L fa=1 warmup の再現性（同 ctx なら差分 <0.5% 以内か）

## 変更対象ファイル

### 新規作成
- `report/attachment/<TS>_qwen3-122b-c3-phaseL-fa0-ctx-scan/plan.md`
- `report/attachment/<TS>_qwen3-122b-c3-phaseL-fa0-ctx-scan/start_phaseL.sh`
- `report/attachment/<TS>_qwen3-122b-c3-phaseL-fa0-ctx-scan/aggregate_results.sh`（`out_L_*` 対応）
- 計測出力 `out_L_fa{0,1}_ctx{N}_{warmup,1k}/`、`fa0_startup_ctx{N}/`
- `report/<TS>_qwen3-122b-c3-phaseL-fa0-ctx-scan.md`

### 参照流用（コピーのみ、改変なし）
- `run_all.sh`、`measure_phaseI.sh`、`prompts/prompt_{1k,8k}.txt`（Phase K 資産）

### 既存編集
- `REPORT.md`（新レポートエントリ追記）

## Verification（検証方法）

1. start_phaseL.sh 実行中、`ssh t120h-p100 'tail -f /tmp/llama-server_fa0_ctx${N}.log'` で graph_reserve 行の `allocating ... MiB` を確認
2. 起動成功ケース: `ssh t120h-p100 "curl -s http://127.0.0.1:8000/health"` が 200 OK を返す
3. 計測後 `results.tsv` に `L_f16_fa{0,1}_ctx${N}_{warmup,1k}` 行が揃っていることを確認、中央値が妥当（Phase K L_f16_fa1 warmup 15.05 t/s ±0.5 程度）
4. compute buffer 実測 MiB を Phase K 仮説（4k→1136 MiB、2k→284 MiB、1k→71 MiB）と比較し、O(n²) の 1/4 倍（=1/16）トレンドに沿うかをレポートに記載
5. unlock 後 `ssh t120h-p100 "ps aux | grep llama-server | grep -v grep"` で残プロセスなしを確認
