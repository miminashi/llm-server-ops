# Phase Q: fa=1 `-ub` 下限探索（ub=1024 / 512 / 256）

## Context（実施動機）

Phase P レポート（`report/2026-04-19_051604_qwen3-122b-c3-phaseP-fa1-batch-scan.md`）の「未検証事項 / 新規項目」最上位として「**決定的発見の可能性**」と明記された項目を実施する。

Phase P で確定した事実:
- fa=1 の compute buffer 真のドライバは `-ub`（`-b` ではない）
- CUDA3 = `min(ctx, -ub) × 0.9824` MiB が誤差 ≤ 0.2 MiB（0.002%）で完全一致
- ub=2048 で compute buffer 73% 削減 + eval +1.5%（ダブルウィン）

Phase Q の目的:
1. 線形性 `0.9824·n_eff` が `-ub=1024 / 512 / 256` の極小領域まで保たれるか実証
2. eval 速度の `-ub` 単調減少傾向が下方向で継続するか／反転点があるか検出
3. graph splits の `bs=${ub}` 対応が極小領域でも成立するか
4. llama.cpp 内部の `-ub` 最小許容値（ある場合）を検出

達成すれば本番 ctx=131k で `-ub=1024` または `-ub=512` 採用が現実的になり、CUDA3 ≈ 1006/503 MiB まで圧縮可能。Phase R（fa=0）/ Phase S（prompt 軸）への土台にもなる。

## 条件マトリクス

`-b = -ub` 同値（Phase P で `-b > -ub` の compute buffer 効果ゼロ確定済）。

| 条件 | -b | -ub | 予測 CUDA3 (MiB) | 起動可否予測 |
|---|---:|---:|---:|---|
| Q1 | 1024 | 1024 | 1006.0 | ✅ ほぼ確実 |
| Q2 | 512 | 512 | 503.0 | ✅ 確実 |
| Q3 | 256 | 256 | 251.5 | ⚠️ llama.cpp 下限警告の可能性 |
| Q4（任意） | 128 | 128 | 125.7 | Q3 成功時のみ追加 |

ctx=16384 / fa=1 / f16 KV / C-D3 base 固定（Phase P と完全同一）。

## 成功条件

- [ ] Q1〜Q3 全て起動成功・`sched_reserve` 採取（Q3 失敗時は exit 3 で検知してデータ保全）
- [ ] CUDA3 線形性誤差 ≤ 0.5%（Phase P は 0.002%、下限崩壊検出のため許容を 250 倍に緩和）
- [ ] log-log 傾き 0.95〜1.05（区間 ub=128→256, 256→512, 512→1024, 1024→2048 の 4 区間）
- [ ] 7 点フィット（Phase P 4 点 + Phase Q 3 点）の線形係数が 0.978〜0.987
- [ ] graph nodes = 4473 全条件一致、graph splits の `bs=${ub}` 対応継続
- [ ] eval 中央値の単調性 or 反転点の検出（反転点があれば本番既定値の根拠になる）

## Critical Files

### 流用する Phase P 資産（読取・コピー元）

- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-19_051604_qwen3-122b-c3-phaseP-fa1-batch-scan/start_phaseP.sh`（既に `BATCH_SIZE`/`UB_SIZE` 環境変数化済み）
- 同上 `measure_phaseI.sh` / `run_all.sh` / `aggregate_results.sh` / `prompts/`
- 同上 `fit_analysis.py`（Phase Q 用に書き直し）

### 新規作成（Phase Q 専用ディレクトリ）

タイムスタンプ取得後:

- `report/attachment/${TS}_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound/start_phaseQ.sh`（コメントのみ Phase P→Q 置換、+ `-ub` 拒否検知パターン追加）
- 同上 `aggregate_results.sh`（`out_P_` → `out_Q_` 1 箇所置換）
- 同上 `fit_analysis.py`（書き直し: 7 点フィット・極小区間 log-log 傾き・graph splits 追跡・eval 反転点検出）
- 同上 `startup_logs/fa1_ctx16384_b{1024,512,256}_ub{1024,512,256}.log`
- 同上 `out_Q_*` 計測アーティファクト
- 同上 `results.tsv` / `fit_analysis.txt` / `compute_buffer_summary.txt`

### 利用する skill スクリプト

- `.claude/skills/gpu-server/scripts/lock.sh t120h-p100`
- `.claude/skills/gpu-server/scripts/unlock.sh t120h-p100`
- `.claude/skills/llama-server/scripts/stop.sh t120h-p100`

## 実行手順

```bash
# 0. ロック取得とディレクトリ準備
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
PHASE_Q_DIR="report/attachment/${TS}_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound"
mkdir -p "$PHASE_Q_DIR/startup_logs"
PHASE_P_DIR="report/attachment/2026-04-19_051604_qwen3-122b-c3-phaseP-fa1-batch-scan"
cp "$PHASE_P_DIR"/{measure_phaseI.sh,run_all.sh,aggregate_results.sh} "$PHASE_Q_DIR/"
cp -r "$PHASE_P_DIR/prompts" "$PHASE_Q_DIR/"
cp "$PHASE_P_DIR/start_phaseP.sh" "$PHASE_Q_DIR/start_phaseQ.sh"
# start_phaseQ.sh: コメント置換 + -ub 拒否検知 grep パターン追加
# aggregate_results.sh: out_P_ → out_Q_ 置換
# fit_analysis.py: 全面書き直し（要件は本プラン §解析スクリプト要件）

cd "$PHASE_Q_DIR"

# 1. Q1 / Q2 / Q3 順次実行（失敗時は break、ログは保全）
for UB in 1024 512 256; do
  if FLASH_ATTN=1 CTX_SIZE=16384 BATCH_SIZE=$UB UB_SIZE=$UB bash start_phaseQ.sh; then
    PID=$(ssh t120h-p100 "ps -eo pid,comm | awk '\$2==\"llama-server\"{print \$1;exit}'")
    ssh t120h-p100 "cat /tmp/llama-server_fa1_ctx16384_b${UB}_ub${UB}.log" \
      > "startup_logs/fa1_ctx16384_b${UB}_ub${UB}.log"
    TAG_PREFIX="Q_f16_fa1_ctx16384_b${UB}_ub${UB}" SIZES="warmup" PID=$PID bash run_all.sh
    cd - && .claude/skills/llama-server/scripts/stop.sh t120h-p100 && cd "$PHASE_Q_DIR"
  else
    ssh t120h-p100 "cat /tmp/llama-server_fa1_ctx16384_b${UB}_ub${UB}.log 2>/dev/null" \
      > "startup_logs/fa1_ctx16384_b${UB}_ub${UB}_FAILED.log" || true
    cd - && .claude/skills/llama-server/scripts/stop.sh t120h-p100 || true
    cd "$PHASE_Q_DIR"
    break
  fi
done

# 2. Q4 (ub=128): Q3 成功時のみ条件付き実施
if grep -q "CUDA3 compute buffer" "startup_logs/fa1_ctx16384_b256_ub256.log" 2>/dev/null; then
  if FLASH_ATTN=1 CTX_SIZE=16384 BATCH_SIZE=128 UB_SIZE=128 bash start_phaseQ.sh; then
    PID=$(ssh t120h-p100 "ps -eo pid,comm | awk '\$2==\"llama-server\"{print \$1;exit}'")
    ssh t120h-p100 "cat /tmp/llama-server_fa1_ctx16384_b128_ub128.log" \
      > "startup_logs/fa1_ctx16384_b128_ub128.log"
    TAG_PREFIX="Q_f16_fa1_ctx16384_b128_ub128" SIZES="warmup" PID=$PID bash run_all.sh
    cd - && .claude/skills/llama-server/scripts/stop.sh t120h-p100 && cd "$PHASE_Q_DIR"
  fi
fi

# 3. 集計と解析
bash aggregate_results.sh > results.tsv
python3 fit_analysis.py | tee fit_analysis.txt
grep -E "sched_reserve:|KV buffer|graph nodes|graph splits|cudaMalloc|failed to allocate|ubatch.*must|n_ubatch.*must" \
  startup_logs/*.log > compute_buffer_summary.txt
cd -
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

## start_phaseQ.sh の差分（Phase P からの変更）

1. 先頭コメントの "Phase P" → "Phase Q" 置換
2. OOM 検知ブロック直後に `-ub` 下限拒否検知を追加:

```bash
# Phase Q 追加: llama.cpp の -ub 内部下限拒否を検出
if ssh "$HOST" "grep -qE 'ubatch.*must be|n_ubatch.*must|invalid.*ubatch|llama_init.*failed' ${REMOTE_LOG} 2>/dev/null"; then
  echo "[start_phaseQ] -ub lower-bound rejection detected" >&2
  ssh "$HOST" "tail -30 ${REMOTE_LOG}" >&2 || true
  exit 3
fi
```

## fit_analysis.py の書き換え要件

1. Phase P 既存 4 点を定数として埋め込み + Phase Q ログ自動パース
2. 各 Q 条件で `0.9824·n_eff` 予測との誤差 / 百分率（許容 ≤ 0.5%）
3. log-log 傾きの全 6 区間（128→256, 256→512, 512→1024, 1024→2048, 2048→4096, 4096→8192）追跡 + 崩壊点フラグ
4. 7 点フィット: 線形 `a·ub+b` と log-log `α·log(ub)+β`、α=1 の検定（numpy.polyfit）
5. graph splits 表（条件別 `bs=${ub}` 対応確認）
6. eval / prompt 中央値の ub 関数表 + 反転点（極大）検出

## 想定実行時間

| 項目 | 想定 |
|---|---|
| 準備（lock 取得・コピー・編集） | 5 分 |
| Q1〜Q3 計測（3 条件 × 11.5 分） | 35 分 |
| Q4（任意、ub=128） | +12 分 |
| 集計・解析 | 5 分 |
| **合計（実行のみ）** | **45〜57 分** |
| レポート執筆 | 別途 45〜60 分 |

## レポート構成（CLAUDE.md 必須事項）

ファイル: `report/${TS}_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound.md`

- 添付ファイル（実装プラン含む、本プランファイルを `attachment/.../plan.md` にコピー）
- 参照（Phase P / O / N / M）
- 前提・目的 / 環境情報 / 再現方法 / 実行タイムライン
- 実行結果サマリ（条件別 sched_reserve、線形性検証、log-log 傾き、7 点フィット、graph splits、eval/prompt 速度、Phase P+Q 統合表）
- ボトルネック・副次発見の分析
- 採用判定
- **「未検証事項」セクション**（既知 = Phase P から継承して [x] 付与、新規 = Phase Q で発生したもの）
- **「検証完了後に実施すべき TODO」セクション**（既知 + 新規、★最優先項目を明示）
- 補足（核心発見、計算モデル更新版、VRAM 予測表、作業終了時点の状態）

## 検証方法（end-to-end）

1. プラン通りに実行し、`results.tsv` に Q1〜Q3 各 3 run（warmup）が記録されること
2. `fit_analysis.txt` で:
   - 各条件の `0.9824·n_eff` 誤差 ≤ 0.5%
   - log-log 傾き 全区間で 0.95〜1.05、または崩壊点が明示
   - 7 点線形フィット係数 0.978〜0.987
3. `compute_buffer_summary.txt` に全条件の sched_reserve / graph splits / graph nodes が含まれる
4. `startup_logs/` に成功 3〜4 件 + （あれば）FAILED ログが保全される
5. 作業終了時に llama-server 停止確認 + GPU lock 解放
6. レポートに必須セクション「未検証事項」「検証完了後に実施すべき TODO」が存在

## リスクと注意点

- **GPU lock**: 必ず `lock.sh t120h-p100` で取得し、終了時に `unlock.sh` で解放
- **OOM はほぼ起こらない**（compute buffer は単調減少のみ）。起こったら異常事態
- **llama.cpp の `-ub` 内部下限拒否**は exit 3 で検知。Q3/Q4 で発生したらそれ自体が貴重な発見
- **eval 速度反転点**が検出された場合は核心発見に格上げ、本番既定値を反転点 ub に変更する強い動機
- **`-ub=1` (greedy) ベンチマーク**と **`-ub > -b` 検証**は Phase Q では実施しない（Phase P 別項目として登録済）
- **plan モード**で計画を立てたため、レポート作成は CLAUDE.md 規定により**必須**
