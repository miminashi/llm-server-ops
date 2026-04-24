# Qwen3.5-122B C-3 eval ボトルネック プロファイリング

## Context

直前レポート `report/2026-04-16_053225_qwen3-122b-c3-layer30-swap.md` の未検証事項（新規項目）の **最優先項目**「eval 頭打ちのボトルネック特定」を実施する。

- C-3 構成では GPU 層を 6 → 12 層に倍増したが eval は 11.86 → 12.19 t/s（+2.8%）にしか伸びず、GPU 層追加の効果が頭打ちしている
- ボトルネックの候補は (a) 残り 36 層の **CPU expert 計算**、(b) **CPU↔GPU PCIe 転送**、(c) **GPU 同期待ち**、の 3 通り。どれが支配的か不明
- この判定結果は次の最適化（`-ub 4096` で CUDA0/3 compute buffer 削減 → layer 10-13 や 36-39 の追加 GPU 復帰）の成否を左右するため、先に観測で切り分ける
- **llama-server は再起動しない。C-3 稼働状態を維持したまま OS レベル観測のみ実施**

## アプローチ

稼働中の C-3 に eval リクエストを 3 回投げながら、ホスト側（作業マシン）から ssh 経由で `nvidia-smi dmon` と `top -b` を並列起動し、GPU SM 利用率・VRAM 帯域・消費電力と CPU user/sys 利用率を時系列で採取する。加えて idle 基準（eval を打たない窓）を 1 回取り、観測ノイズの基準線を確定させる。

採取後、eval 開始・終了のミリ秒タイムスタンプで窓アラインし、GPU/CPU 指標の平均・p95 をクロス集計。判定マトリクスに当てはめてボトルネック要因を同定する。派生実験（`-ub 4096`、`--threads` 変更、flash-attn off）は本レポートのスコープ外とし、次レポート送りにする。

## 実施手順

### 1. 事前準備

1. ロック取得: `.claude/skills/gpu-server/scripts/lock.sh t120h-p100`
2. タイムスタンプ確定: `TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)`
3. 添付ディレクトリ作成: `report/attachment/${TS}_qwen3-122b-c3-eval-bottleneck-profile/`
4. 稼働確認:
   - `curl -sf http://10.1.4.14:8000/health`
   - `ssh t120h-p100 pgrep -af llama-server` で PID 記録
   - `ssh t120h-p100 'tail -50 /tmp/llama-server.log'` で C-3 `-ot` パターンの記録確認

### 2. プロファイル計測

`report/attachment/.../profile.sh` に以下の構造で実装:

```bash
run_profile() {
  local RUN=$1 ATTACH=$2
  # dmon: 1秒×40サンプル = 40秒窓
  ssh t120h-p100 "nvidia-smi dmon -s pucvmet -c 40 -o DT" \
    > $ATTACH/dmon_run${RUN}.log 2>&1 &
  local DMON_PID=$!
  # top 全体 (40 回)
  ssh t120h-p100 "top -b -d 1 -n 40 -w 512" \
    > $ATTACH/top_system_run${RUN}.log 2>&1 &
  # top PID 限定
  ssh t120h-p100 "top -b -d 1 -n 40 -p $LLAMA_PID -w 512" \
    > $ATTACH/top_pid_run${RUN}.log 2>&1 &
  sleep 3  # dmon ウォームアップ
  local EVAL_START=$(TZ=Asia/Tokyo date +%H%M%S.%N)
  curl -s http://10.1.4.14:8000/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -d '{"model":"unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M",
         "messages":[{"role":"user","content":"Write a short haiku about autumn."}],
         "max_tokens":256,"temperature":0.6,"top_p":0.95}' \
    > $ATTACH/eval_run${RUN}.json
  local EVAL_END=$(TZ=Asia/Tokyo date +%H%M%S.%N)
  wait
  echo "run=$RUN eval_start=$EVAL_START eval_end=$EVAL_END" \
    >> $ATTACH/timeline.log
}
```

- **Run 0 (idle)**: eval を打たず dmon/top のみ 20 秒 → 観測ノイズ基準
- **Run 1, 2, 3**: 上記 `run_profile` を順次実行。各 run 間 60 秒インターバル
- 所要時間: idle 30s + (40s × 3 + 60s × 2) = 約 4 分

### 3. ログ集計・解析

- `dmon_run*.log` を GPU 別（CUDA0-3）に分割し、Python/awk で集計:
  - `sm%`: avg, p50, p95, peak
  - `mem%`: avg（VRAM 帯域）
  - `pwr`: avg（P100 TDP 250W 比）
  - `mclk/pclk`: 熱スロットル検出
- `top_system_run*.log` から `%Cpu(s)` 行を抽出し `us/sy/wa/id` 平均計算
- `top_pid_run*.log` から llama-server の `%CPU`（N コア × 100% 最大）と `THR`（スレッド数）を抽出
- `eval_run*.json` の `timings.predicted_per_second` を 3 run 抽出、中央値 / 平均 / 標準偏差
- 結果を `summary_gpu.tsv`, `summary_cpu.tsv` に保存

### 4. ボトルネック判定マトリクス

| 観測パターン | 判定 | 次アクション候補 |
|-------------|------|-----------------|
| GPU sm% 平均 < 40% かつ CPU us > 70% | CPU expert 計算律速 | `--threads` 増、CPU BLAS 置換 |
| GPU sm% 平均 > 70% かつ CPU us < 40% | GPU 律速（compute or PCIe） | GPU 層追加、`-ub` 調整 |
| GPU sm% / CPU us とも 40-70% | PCIe 転送 or 同期律速（`mem%` 参照） | `-ub 4096`、バッチ削減 |
| GPU sm% < 20% かつ CPU us < 20% | 同期待ち・排他律速 | llama.cpp プロファイル |
| CUDA 間 sm% 格差 > 30pt | 層配置非均等 | 層再配置 (C-4 候補) |

### 5. レポート本文

ファイル: `report/${TS}_qwen3-122b-c3-eval-bottleneck-profile.md`

セクション構成（直前レポートと同じ構造を踏襲）:

1. 見出し、実施日時、作業種別
2. 添付ファイル一覧（plan.md, dmon/top/eval ログ, summary TSV）
3. 参照（前身レポート、C-3 原典、`2026-04-16_043659` 等）
4. 前提・目的
5. 環境情報（C-3 構成、llama.cpp build、dmon/top バージョン）
6. 計測手順（本計画の要約）
7. 実行結果サマリ（GPU 指標表、CPU 指標表、eval t/s）
8. ボトルネック判定（マトリクスのどれに該当したか、根拠データ）
9. 結論と次アクション
10. **未検証事項**（既知項目＋新規項目）
11. **検証完了後に実施すべき TODO**（既知項目＋新規項目）
12. 補足

### 6. 作業終了

1. 添付保存（plan.md をコピー、ログ類一式）
2. ロック解放: `.claude/skills/gpu-server/scripts/unlock.sh t120h-p100`
3. C-3 は稼働継続

## 重要ファイル

**新規作成**:
- `report/${TS}_qwen3-122b-c3-eval-bottleneck-profile.md`
- `report/attachment/${TS}_qwen3-122b-c3-eval-bottleneck-profile/plan.md`
- `report/attachment/.../profile.sh`, `dmon_run{0,1,2,3}.log`, `top_system_run{1,2,3}.log`, `top_pid_run{1,2,3}.log`, `eval_run{1,2,3}.json`, `timeline.log`, `summary_gpu.tsv`, `summary_cpu.tsv`

**参照（既存）**:
- `report/2026-04-16_053225_qwen3-122b-c3-layer30-swap.md` — 前身レポート（未検証事項の出典）
- `REPORT.md` — レポート作成ルール
- `.claude/skills/gpu-server/scripts/lock.sh`, `unlock.sh` — ロック管理
- `CLAUDE.md` — プロジェクト制約

## 稼働前提を壊さないための注意点

- **llama-server 再起動禁止**。C-3 構成稼働中。計測は純粋に観測のみ
- dmon/top はホスト側（作業マシン）から ssh 経由で起動、ssh 先は一般ユーザ権限
- `nvidia-smi --gpu-reset` など GPU に触れる破壊的操作は絶対に実行しない
- 観測オーバーヘッド確認: Run 0 (idle) vs Run 1-3 で CPU us の差分が 2pt 以内であること
- `/tmp/llama-server.log` の tail はログ書込み I/O が混ざるため、計測中は避ける

## フォールバック

| 想定故障 | 対処 |
|---------|------|
| `dmon -s pucvmet` がフィールド非対応 | `-s u` (utilization のみ) に縮退。pwr は `--query-gpu=power.draw --format=csv -l 1` 別プロセス補完 |
| eval が 30 秒超過し観測窓オーバーラン | `-c 60 / -n 60` に拡張 |
| 3 run の eval t/s ばらつき ±10% 超 | run4/5 追加、中央値採用、原因を未検証事項に記載 |
| ssh 切断 | `ssh -o ServerAliveInterval=10` 付与 |
| PID が変わっている（再起動疑い） | 計測中止、稼働状態を再確認してから C-3 再起動するか判断 |

## 検証方法（レポート確定前のセルフチェック）

1. eval t/s 3 run 中央値が前身レポート 12.19 t/s と ±1 t/s 以内で一致（定常状態の証拠）
2. Run 0 (idle) の GPU sm% 平均 < 5%（観測基準線確立）
3. Run 1-3 の GPU sm% / CPU us から判定マトリクスの 1 カテゴリに明確に分類できる
4. `summary_*.tsv` が attachment に保存され、本文の数値と一致する
5. 本文末尾に「未検証事項」「検証完了後に実施すべき TODO」が直前レポートと同じ体裁で存在
