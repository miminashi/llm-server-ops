# Phase F: C-E5 (`--numa isolate`) 再現性 + C-D3 ベースライン再取得

## Context

前身レポート [2026-04-16_225920_qwen3-122b-c3-phaseE-smt.md](../../../projects/llm-server-ops/report/2026-04-16_225920_qwen3-122b-c3-phaseE-smt.md) で、現行採用 C-D3 (`numactl --cpunodebind=1 --membind=1 -- + --threads 40`, 15.03 t/s) に対する追加検証を実施した。以下 2 点が最優先の未検証事項として残っている:

1. **C-E5 (`--numa isolate` 併用) の +5.1% 効果が再現するか**: Phase E では初回 15.00 / 再計測 14.75 で揺らぎ 0.25 t/s、統計的に有意と断定できず。3 回以上の再起動 × 計測を推奨。
2. **C-D3 の長時間稼働劣化**: 同一構成 C-D3 が Phase D 直後 15.03 → Phase E (1 時間後) 14.27 と 5% 劣化。再起動で回復するか、定期再起動が必要か不明。Phase E では「優先度上昇」と明示。

本 Phase F は上記 2 つを 1 セッションで同時検証する。C-E5 判定には C-D3 比較が必須であり、「現行のマシン状態での C-D3 ベースライン」を再取得しないと判定基準自体が不安定となるため、両者を交互に 3 サイクル計測する。

## スコープと成功条件

### 採用判定（C-E5 を C-D3 から昇格させる条件）

- **C-F2 (= C-E5) 中央値 ≥ C-F1 (= C-D3) 中央値 × 1.03** → 採用候補（以降の Phase で長期運用検証を経て正式採用）
- **C-F2 中央値 − C-F1 中央値 ≥ 0.2 t/s** かつ符号一貫 → 「再現した」と記録（採用基準未達でも効果あり所見として残す）
- それ以外 → C-D3 維持、C-E5 非採用（+5.1% は Phase E の一回限りの擾乱と結論）

### 副次観察

- C-F1a/F1b/F1c の Run 1 のばらつき（= fresh restart 直後の再現揺らぎ）
- 各 variant 内 Run1→Run3 の短期劣化（< 4 分経過）
- numastat_pre/post での Node 1 占有率（Phase E と同程度 (>99.98%) を維持しているか）
- `/proc/$PID/status` の voluntary_ctxt_switches（fresh restart 直後 vs. 4 分経過時点で差分発生しているか）

## プロトコル

### variants（2 種のみ、Phase E から削減）

| 構成 | プレフィックス | `--threads` | 追加引数 | Phase E 対応 |
|------|--------------|:----------:|---------|:---:|
| **C-F1** | `numactl --cpunodebind=1 --membind=1 --` | 40 | (なし) | = C-E1 / C-D3 |
| **C-F2** | `numactl --cpunodebind=1 --membind=1 --` | 40 | `--numa isolate` | = C-E5 |

共通引数（Phase E と完全同一）: `-ngl 999 -ot 'blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU' --flash-attn 1 --poll 0 -b 8192 -ub 8192 --n-predict 32768 --ctx-size 131072 --parallel 1 --cache-type-k q8_0 --cache-type-v q8_0 --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0`

### 実行順（交互配置で順序効果を相殺）

```
F1a → F2a → F1b → F2b → F1c → F2c
```

各サイクル共通: `stop.sh → start_phaseF.sh <variant> → 正 PID 取得 → measure_phaseF.sh <pid> <tag>`（3 run、60s cooldown）

### 判定プロトコル

1. F1a/F1b/F1c の中央値 m_F1、F2a/F2b/F2c の中央値 m_F2 を算出（各サイクル Run 3 個の中央値）
2. グループ中央値 M_F1 = median(m_F1_a, b, c), M_F2 = median(m_F2_a, b, c)
3. 採用判定: M_F2 ≥ M_F1 × 1.03 かつ m_F2_{a,b,c} 全てが m_F1 最大値を上回る
4. 再現判定: M_F2 − M_F1 ≥ 0.2

## 前工程・後工程

### 前提

- 現在 t120h-p100 で C-D3 構成が稼働中（Phase E 作業末で PID 57017、--port 8000）
- GPU サーバロック: Phase E 終了時に解放済み（要確認）
- llama.cpp ビルド: b8807-b3d758750（変更なし、Phase D/E と同一）

### 前工程

1. `.claude/skills/gpu-server/scripts/lock.sh t120h-p100` でロック取得（失敗時は待機 or ユーザ確認）
2. `ssh t120h-p100 "ps -eo pid,comm,args | awk '\$2==\"llama-server\"'"` で現稼働プロセス確認
3. `.claude/skills/llama-server/scripts/stop.sh t120h-p100` で既存プロセス停止
4. 15 秒待機 → `ps` で停止確認

### 後工程

1. 計測終了後、採用判定に従い以下のいずれかで再起動:
   - **C-D3 維持採用**: 現行通り `numactl --cpunodebind=1 --membind=1 -- + --threads 40`
   - **C-E5 採用候補**: `+ --numa isolate` 追加（ただし長期運用検証が別途必要なため、次 Phase までは C-D3 で戻す）
2. `.claude/skills/gpu-server/scripts/unlock.sh t120h-p100` でロック解放
3. レポート作成、plan.md コピー、添付物整理

## 添付ファイル構成

添付ディレクトリ: `report/attachment/<レポートファイル名>/`（レポートファイル名は実施時に `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で動的取得）

- `plan.md` - 本プラン（`cp /home/ubuntu/.claude/plans/iridescent-swinging-pelican.md`）
- `start_phaseF.sh` - 起動スクリプト（下記参照）
- `measure_phaseF.sh` - 計測スクリプト（`measure_phaseE.sh` からロゴのみ差し替え）
- `out_F1a_cpunodebind_threads40/`, `out_F2a_numa_isolate/`, `out_F1b_…/`, `out_F2b_…/`, `out_F1c_…/`, `out_F2c_…/` (計 6 ディレクトリ)

各 out ディレクトリ: `eval_run{1,2,3}.json`, `dmon_run{1,2,3}.log`, `status_run3.txt`, `numastat_pre.txt`, `numastat_post.txt`, `cmdline.txt`, `timeline.log`

### `start_phaseF.sh` の改変点（`start_phaseE.sh` からの差分）

- variant を `F1` と `F2` の 2 種のみに削減（= Phase E の E1 / E5）
- **PID 取得行を変更**: `pgrep -f 'build/bin/llama-server' | head -1` → `ps -eo pid,comm,args | awk '\$2=="llama-server" {print \$1; exit}'`（Phase E で親 bash 誤検知が確認されたため、`comm` 完全一致方式に切り替え）
- ヘルスチェック・起動コマンド本体は変更なし

### `measure_phaseF.sh`

- `measure_phaseE.sh` と実質同一。ログ行の「phaseE」→「phaseF」文言差し替えのみ

## 実施手順（実行時の参照用）

```bash
# 0. 準備（ローカル）
REPORT_NAME=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)_qwen3-122b-c3-phaseF-reproducibility
ATTACH_DIR="report/attachment/${REPORT_NAME}"
mkdir -p "$ATTACH_DIR"
cp /home/ubuntu/.claude/plans/iridescent-swinging-pelican.md "$ATTACH_DIR/plan.md"
# start_phaseF.sh, measure_phaseF.sh を $ATTACH_DIR に配置（Phase E のコピー + 修正）

# 1. ロック取得・旧プロセス停止
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
.claude/skills/llama-server/scripts/stop.sh t120h-p100
sleep 15

# 2. 6 サイクル実行（F1a → F2a → F1b → F2b → F1c → F2c）
cd "$ATTACH_DIR"
for tag in F1a:F1 F2a:F2 F1b:F1 F2b:F2 F1c:F1 F2c:F2; do
  TAG="${tag%%:*}"; VAR="${tag##*:}"
  .claude/skills/llama-server/scripts/stop.sh t120h-p100
  sleep 15
  bash start_phaseF.sh "$VAR"
  PID=$(ssh t120h-p100 "ps -eo pid,comm,args | awk '\$2==\"llama-server\" {print \$1; exit}'")
  bash measure_phaseF.sh "$PID" "${TAG}_$( [ "$VAR" = F1 ] && echo cpunodebind_threads40 || echo numa_isolate )"
done

# 3. 集計（中央値算出）
for d in out_F*/; do
  tag="${d%/}"
  vals=$(jq -r '.timings.predicted_per_second' "${d}eval_run"*.json | sort -n | awk 'NR==2')
  echo "$tag median=$vals"
done

# 4. 後処理
.claude/skills/llama-server/scripts/stop.sh t120h-p100
sleep 15
# C-D3 で再稼働（採用構成維持）
numactl -N1 -m1 -- llama-server ... --threads 40  # 詳細は Phase E レポートの「採用構成の再起動コマンド」セクション参照
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100

# 5. レポート作成
# report/${REPORT_NAME}.md に作成、Phase E レポートと同様の構成
# 必須セクション: 前提・目的 / 環境情報 / 再現方法 / 結果 / 判定 / 未検証事項 / 検証完了後に実施すべき TODO
```

## 想定所要時間

| 工程 | 時間 |
|------|------|
| 準備（スクリプト配置、ロック取得、旧プロセス停止） | ~5 分 |
| 1 サイクル（stop 30s + start 60~90s + 計測 4.5 分 ≒ 約 7 分） × 6 | ~42 分 |
| 集計・レポート執筆 | ~30 分 |
| バッファ | ~15 分 |
| **合計** | **~90 分** |

## 検証（Phase F の成否確認）

- 6 out ディレクトリがすべて生成され、各 `eval_run{1,2,3}.json` に `.timings.predicted_per_second` が存在
- 各 `status_run3.txt` で Cpus_allowed_list が期待通り（F1: `20-39,60-79` / F2: `0-79`）
- numastat_post.txt で Node 1 比率 >99.9%
- `predicted_per_second` に極端な外れ値（< 10 t/s 等）が含まれない
- 判定結論がレポート本文で明示される

## 未検証事項（Phase F で扱わない = 次 Phase 以降に持ち越し）

Phase E から継続のうち本 Phase で扱わないもの:

- **1 時間超の連続稼働試験**: 本 Phase は短サイクル（各 restart 間隔 7 分）で長期劣化を直接検証しない。別 Phase（idle 30 分おきに計測）で実施
- 大コンテキストでの eval 速度 / flash-attn off / 量子化ダウン / pcm-memory / perf stat / drop_caches コールドスタート / `--threads` 中間値 / `--numa numactl` モード / OpenMP 環境変数
- C-4 実験（CPU 層数削減）
- 他モデル検証

## 代替案と不採用理由

**案 B: C-E5 のみ 4 回再起動で計測（Phase D の 15.03 を C-D3 基準として使用）**
不採用。Phase E で C-E1 (= C-D3 追試) = 14.27 が出ており、Phase D 値 15.03 は現在のマシン状態を代表しない可能性がある。基準値が腐った状態では再現性判定ができない。所要時間は半減するが、結論が出ない計測になるリスクが大きい。
