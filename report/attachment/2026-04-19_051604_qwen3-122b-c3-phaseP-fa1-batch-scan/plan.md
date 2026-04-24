# Phase P 実装プラン: fa=1 `-b` バッチサイズ感度スキャン

## Context

Phase O レポート（`report/2026-04-19_033924_qwen3-122b-c3-phaseO-fa1-ctx16k.md`）の「新規項目」末尾に **Phase P 候補（`-b` 感度スキャン）** が最優先 TODO として明記されている。

Phase O で判明したのは、fa=1 の compute buffer は `n_eff = min(ctx, -b=8192)` で飽和し、CUDA3 は `min(ctx, -b) × 0.9824` で完全予測可能ということ。ただしこれは「`-b=8192` 固定」でのみ実証されており、**真のドライバが `-b` なのか他の要因（例: `-ub`、モデル構造固有の 8192）なのかが未確定**。

Phase P は `-b` を 2048 / 4096 / 8192 に振って、CUDA3 の頭打ち点が `-b` に比例することを実証する。確認できれば：
- 本番 `start.sh` の `-b` を環境変数化して **VRAM 節約レバー**として活用可能
- 長 ctx（131k 本番）でも `-b` を小さくすれば compute buffer を大幅削減できる根拠になる
- Phase N/O の区分モデルが「決定版」として確定する

## Approach

**ctx=16384 固定、`-b` を 4 条件で振る最小スキャン**。起動 → `sched_reserve` 採取 → warmup 3 run → 次条件へ、を繰り返す（約 22〜25 分）。

### 計測条件

| 条件 | -b | -ub | 期待 CUDA3 (MiB) | 期待合計 (MiB) | 目的 |
|---|---:|---:|---:|---:|---|
| P1 | 2048 | 2048 | 2,012 | ≈ 5,200 | 最小 -b での頭打ち |
| P2 | 4096 | 4096 | 4,024 | ≈ 9,000 | 中間 -b |
| P3 | **8192** | **8192** | 8,048 | 15,697 | Phase O 再現（ベースライン） |
| P4 | 8192 | 4096 | 8,048 | ≈ 15,700 | `-ub` 単独効果の分離 |

**`-b=16384` は完全除外**：CUDA3 compute buffer 16,095 MiB + 層 weights 2,193 MiB + KV 96 MiB ≈ 18.4 GB で P100 の 16.27 GB を超過、OOM 確実。仮説検証にも不要（P1〜P3 の線形性で十分）。

### 成功条件（定量判定）

- [ ] CUDA3 実測と `min(16384, -b) × 0.9824` 予測の差 |絶対値| ≤ 5 MiB（全 4 条件）
- [ ] P1〜P3 の (-b, CUDA3) log-log 傾きが 0.95〜1.05
- [ ] CUDA1/2 も -b 比例で単調増加（P1 < P2 < P3）
- [ ] P3 が Phase O 値と ±2 MiB 以内で再現
- [ ] P3 vs P4 の compute buffer 差 ≤ ±10 MiB（`-ub` 非依存の確定）

### 失敗条件
- CUDA3 が `min(ctx, -b)` 予測から ±10% 以上乖離 → 仮説棄却、別モデル再検討
- P1（最小）でも OOM → `-b` 縮小が VRAM レバーにならず、本番反映候補から除外

## 実装ステップ

### Step 1: ディレクトリと資産準備（2 分）

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
PHASE_P_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseP-fa1-batch-scan"
mkdir -p "$PHASE_P_DIR/startup_logs"
PHASE_O_DIR="report/attachment/2026-04-19_033924_qwen3-122b-c3-phaseO-fa1-ctx16k"
cp "$PHASE_O_DIR"/{measure_phaseI.sh,run_all.sh,aggregate_results.sh} "$PHASE_P_DIR/"
cp -r "$PHASE_O_DIR/prompts" "$PHASE_P_DIR/"
cp "$PHASE_O_DIR/start_phaseO.sh" "$PHASE_P_DIR/start_phaseP.sh"
```

### Step 2: スクリプト改変

#### 2.1 `start_phaseP.sh` に `BATCH_SIZE` / `UB_SIZE` 環境変数追加

行 15〜16（`FLASH_ATTN` / `CTX_SIZE` の下）に追加:
```bash
BATCH_SIZE="${BATCH_SIZE:-8192}"
UB_SIZE="${UB_SIZE:-${BATCH_SIZE}}"
```

行 25 の `REMOTE_LOG` を以下に更新:
```bash
REMOTE_LOG="/tmp/llama-server_fa${FLASH_ATTN}_ctx${CTX_SIZE}_b${BATCH_SIZE}_ub${UB_SIZE}.log"
```

行 30 の `-b 8192 -ub 8192` を以下に置換:
```bash
-b ${BATCH_SIZE} -ub ${UB_SIZE}
```

#### 2.2 `aggregate_results.sh` を `out_P_*` 対応に

`out_O_*` の 1 箇所のみ `out_P_*` に置換。

#### 2.3 `fit_analysis.py` を頭打ち検証専用に書き換え

5 点多項式フィットは不要。以下を出力する簡素版（約 50 行）に差し替え:
- 4 条件の sched_reserve 実測 vs `min(ctx, -b) × 0.9824` 予測の誤差表
- CUDA1/2 の Phase N `1.91e-6·n_eff² + 0.2227·n_eff` モデル残差
- P3 vs Phase O の再現性差
- P3 vs P4 の `-ub` 単独効果

### Step 3: 4 条件の計測実行（16〜20 分）

```bash
cd "$PHASE_P_DIR"
# P1, P2, P3 を -b = -ub で実行
for BS in 2048 4096 8192; do
  FLASH_ATTN=1 CTX_SIZE=16384 BATCH_SIZE=$BS UB_SIZE=$BS bash start_phaseP.sh
  PID=$(ssh t120h-p100 "ps -eo pid,comm | awk '\$2==\"llama-server\"{print \$1;exit}'")
  ssh t120h-p100 "cat /tmp/llama-server_fa1_ctx16384_b${BS}_ub${BS}.log" \
    > "startup_logs/fa1_ctx16384_b${BS}_ub${BS}.log"
  TAG_PREFIX="P_f16_fa1_ctx16384_b${BS}_ub${BS}" SIZES="warmup" PID=$PID bash run_all.sh
  cd - && .claude/skills/llama-server/scripts/stop.sh t120h-p100 && cd "$PHASE_P_DIR"
done
# P4: -b=8192 -ub=4096 追加
FLASH_ATTN=1 CTX_SIZE=16384 BATCH_SIZE=8192 UB_SIZE=4096 bash start_phaseP.sh
PID=$(ssh t120h-p100 "ps -eo pid,comm | awk '\$2==\"llama-server\"{print \$1;exit}'")
ssh t120h-p100 "cat /tmp/llama-server_fa1_ctx16384_b8192_ub4096.log" \
  > "startup_logs/fa1_ctx16384_b8192_ub4096.log"
TAG_PREFIX="P_f16_fa1_ctx16384_b8192_ub4096" SIZES="warmup" PID=$PID bash run_all.sh
cd - && .claude/skills/llama-server/scripts/stop.sh t120h-p100
```

**SIZES は warmup のみ**で十分（頭打ち判定は sched_reserve だけで可能、eval は副次成果）。

### Step 4: 集計・解析（2 分）

```bash
cd "$PHASE_P_DIR"
bash aggregate_results.sh > results.tsv
python3 fit_analysis.py | tee fit_analysis.txt
grep -E "sched_reserve:|KV buffer|graph nodes|graph splits" \
  startup_logs/*.log > compute_buffer_summary.txt
cd -
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### Step 5: レポート作成

`report/${TS}_qwen3-122b-c3-phaseP-fa1-batch-scan.md` を Phase O と同形式で作成。**必須セクション**:

1. 添付ファイル / 参照 / 前提・目的 / 環境情報 / 再現方法 / 実行タイムライン
2. 実行結果サマリ（6〜7 項目）:
   - 4 条件の sched_reserve 表
   - CUDA3 頭打ち予測 vs 実測の精密対比表
   - CUDA1/2/CUDA_Host の n_eff モデル残差
   - P3 ↔ Phase O の再現性
   - P3 ↔ P4 の `-ub` 単独効果
   - eval / prompt 速度の `-b` 依存性
   - GPU 使用量合計
3. ボトルネック・副次発見の分析
4. 採用判定（n_eff モデル確定 / start.sh `-b` 環境変数化の提言）
5. **「未検証事項」セクション**（Phase O の継続項目 + Phase P 新規）
6. **「検証完了後に実施すべき TODO」セクション**（継続 + 新規）
7. 補足（決定版 n_eff モデル、`-b` 縮小による VRAM 節約予測表）

## Critical Files

**流用（無修正）**:
- `report/attachment/2026-04-19_033924_qwen3-122b-c3-phaseO-fa1-ctx16k/measure_phaseI.sh`
- `report/attachment/2026-04-19_033924_qwen3-122b-c3-phaseO-fa1-ctx16k/run_all.sh`
- `report/attachment/2026-04-19_033924_qwen3-122b-c3-phaseO-fa1-ctx16k/prompts/`

**Phase P で新規/改変**:
- `start_phaseP.sh`（Phase O コピー + BATCH_SIZE/UB_SIZE 環境変数化、3 箇所修正）
- `aggregate_results.sh`（`out_O_` → `out_P_` 1 箇所置換）
- `fit_analysis.py`（頭打ち検証専用に書き直し、約 50 行）

**Skill 既存資産（参照のみ）**:
- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- `.claude/skills/llama-server/scripts/stop.sh`

## 所要時間見積もり

| 工程 | 時間/回 | 回数 | 合計 |
|---|---:|---:|---:|
| 資産準備・スクリプト改変 | — | — | 3 min |
| 起動（fa=1） | 30s | 4 | 2 min |
| sched_reserve 取得 | 5s | 4 | 20s |
| warmup 3 run（cooldown 60s × 2 含む） | 4 min | 4 | 16 min |
| stop + 次起動間 | 30s | 4 | 2 min |
| 集計・解析 | — | — | 2 min |
| レポート作成 | — | — | 10 min |
| **総計** | | | **約 35〜40 min** |

## OOM 対応

- `start_phaseO.sh` 由来の OOM 早期検知（`cudaMalloc failed` / `failed to allocate` 等）を流用、exit 2 で次条件へ
- 万一 P2（`-b=4096`）が予想外に OOM した場合 → CUDA3 以外のボトルネック発見の重要シグナル、レポートに別記
- ロック解放を忘れないよう `trap` で最終的に `unlock.sh` を呼ぶか、最後の `cd -` 後に必ず実行

## 検証方法

1. **起動成功確認**: 各条件で `startup_logs/fa1_ctx16384_b${BS}_ub${BS}.log` に `sched_reserve:` が 4 GPU + CUDA_Host の 5 行揃うこと
2. **頭打ち確認**: `fit_analysis.txt` で CUDA3 全 4 条件の誤差が ≤ 5 MiB
3. **再現性確認**: P3 の `sched_reserve` が Phase O の `out_O_f16_fa1_ctx16384_warmup` と一致（±2 MiB）
4. **`-ub` 効果確認**: P3 vs P4 の compute buffer 合計差 ≤ 10 MiB
5. **eval 速度再現性**: P3 の eval 中央値が Phase O の 15.011 t/s と ±0.05 t/s 以内

## 留意点

- `start.sh` のハードコード `-b 8192 -ub 8192` 自体は変更しない（Phase P は計測専用、本番反映は「検証完了後 TODO」へ）
- 各条件の起動前に必ず `stop.sh` 実行（ポート 8000 の残存プロセス衝突防止）
- `-ub > -b` は llama.cpp の制約で不可、P4 は `-ub < -b` のみ
- PID 使い回し厳禁、各起動ごとに `ps | awk` で再取得
- **レポートには「未検証事項」と「検証完了後に実施すべき TODO」の両セクションを必ず含める**（ユーザ指示）
