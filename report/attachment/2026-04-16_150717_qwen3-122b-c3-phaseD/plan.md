# Qwen3.5-122B C-3 NUMA 最適化 Phase D（C-C2 改善 & C-C1 乖離検証）

## Context

前身レポート [2026-04-16_072324_qwen3-122b-c3-numa-phaseC.md](../../projects/llm-server-ops/report/2026-04-16_072324_qwen3-122b-c3-numa-phaseC.md) で `numactl --interleave=all`（C-C2）が **eval 11.91 t/s（C-C1 比 +60.7%）** で採用された。しかし以下 3 件の未検証事項が残っている。

- **F-1: コールドスタート時の interleave 均等分散**: 本計測は前セッションのページキャッシュ残存により N0=3.9% / N1=96.1% に偏在。drop_caches 後にコールドスタートすれば N0/N1 ≈ 50:50 となり NUMA リモートアクセスが半減する可能性
- **F-2: `interleave=all` + `--numa distribute` 併用**: C-C2 のメモリ分散と C-C3 の llama.cpp NUMA-aware スレッド配置は相補的である可能性
- **F-3: `--threads 40` + `numactl -N1 -m1` での C-C1 再計測**: 本計測 7.41 t/s と前身 Phase B 11.50 t/s の +55% 乖離。`--threads -1`→80 スレッドが 40 CPU にオーバーサブスクリプションした仮説の直接検証

これらは現行採用 C-C2 構成の追加改善余地（F-1, F-2）と過去計測との整合性確認（F-3）で、いずれも実装コスト低・観測可能性高。本作業ではこの 3 件を Phase D として 4 構成で計測し、C-C2 を上回る構成があれば採用候補とする。

## 目的・成功条件

- **目的**: F-1 / F-2 / F-3 を最小コストで検証し、C-C2 を超える構成があれば採用判定
- **成功条件**:
  - F-1, F-2: いずれかが C-C2 中央値 11.91 × **1.03** 以上（+3%）→ 採用候補
  - F-3: C-C1 が `--threads 40` 明示で前身 11.50 t/s 近傍（±10%）に戻れば仮説検証
- **スコープ外**: 大コンテキスト（>1k tokens）、長時間安定性、量子化変更、`--flash-attn 0`、C-4 層数変更

## 計測構成

| 構成 | プレフィックス | --threads | 追加引数 | drop_caches | 検証目的 |
|------|--------------|----------|---------|:-----------:|---------|
| **C-D1** | `numactl --interleave=all --` | -1 (=80) | (なし) | **あり** | F-1: コールドスタート均等分散 |
| **C-D2** | `numactl --interleave=all --` | -1 (=80) | `--numa distribute` | **あり** | F-1+F-2: 併用＋コールド |
| **C-D3** | `numactl --cpunodebind=1 --membind=1 --` | **40** 明示 | (なし) | あり | F-3: C-C1 オーバーサブスクリプション仮説 |
| **C-D4** (参考) | `numactl --interleave=all --` | **80** 明示 | (なし) | あり | `-1` と `80` の差異確認 |

**比較基準**: 前身の C-C1=7.41 / C-C2=11.91 / C-C3=10.26 t/s（ページキャッシュ warm 状態）。本計測の C-D1 と前身 C-C2 の差が「コールドスタート効果」、C-D2 と C-D1 の差が「`--numa distribute` 上乗せ効果」、C-D3 と C-C1 の差が「`--threads 40` 効果」。

## 実装プラン

### 1. スクリプト準備（ローカル）

新規ディレクトリ: `report/attachment/2026-04-16_<HHMMSS>_qwen3-122b-c3-phaseD/`

**a) `start_phaseD.sh`** — `start_phaseC.sh` をベースに拡張
- variant: D1 / D2 / D3 / D4 に対応
- `--threads` を可変化（既定 -1、D3=40、D4=80）
- `--defrag-thold 0.1` を削除（b8807 で deprecated、前身採用構成準拠）
- 起動前オプション `DROP_CACHES=1`（環境変数）で `ssh $HOST "sudo sync && sudo sysctl -w vm.drop_caches=3"` 実行
  - **drop_caches は llm ユーザーの sudo 権限が必要**（要確認）。権限なければ `sysctl` を root で打つか、`fadvise64 POSIX_FADV_DONTNEED` 相当の代替を検討
- **重要**: 起動前に既存プロセスが完全に落ちていることを確認してから drop_caches 実行（プロセスがマップ中だと効果が薄い）

**b) `measure_phaseD.sh`** — `measure_phaseC.sh` を流用
- 変更点: perf stat ブロック削除（C-C1 専用だった）
- numastat スナップショット追加（Run 1 直前に `ssh $HOST "numastat -p $PID"`）

### 2. 計測手順（GPU サーバ：t120h-p100）

各 variant 共通プロトコル:

1. **lock 取得**: `.claude/skills/gpu-server/scripts/lock.sh t120h-p100`
2. **既存プロセス停止**: `.claude/skills/llama-server/scripts/stop.sh t120h-p100` → 30 秒待機
3. **drop_caches**: `ssh t120h-p100 "sudo sync && sudo sysctl -w vm.drop_caches=3"`
4. **起動**: `DROP_CACHES=1 ./start_phaseD.sh <variant>` → `/health` 200 確認
5. **numastat 確認**: 起動直後の N0/N1 配分を記録
6. **3 run 計測**: 各 run 前 60 秒 cooldown、`max_tokens=256`、`stream=false`
7. **status snapshot**: Run 3 終了時に `/proc/$PID/status` (Threads, Cpus_allowed_list, voluntary/nonvoluntary_ctxt_switches)

実施順序:
- C-D1 → C-D2 → C-D3 → C-D4（各 5–7 分、合計 25–30 分）
- 各 variant 間で stop → drop_caches → 起動を必ず実行（先行 variant のページキャッシュ残存を排除）

### 3. 採用判定 → 構成切替

- **C-D1 か C-D2 が C-C2 比 +3% 以上**: 当該 variant を新採用構成とし、`stop.sh` → 新構成で起動 → 動作確認
- **どちらも +3% 未満**: C-C2 維持。F-1/F-2 は効果が限定的だったと結論
- **C-D3 が前身 11.50 近傍**: F-3 仮説（オーバーサブスクリプション）が支持される。レポートに記載し start.sh の `--threads` 既定値の議論材料に
- **C-D3 が前身と乖離**: 別の変動要因（llama.cpp ビルド差、メモリ断片化、温度等）の可能性をレポートに記載

### 4. レポート作成

`report/2026-04-16_<HHMMSS>_qwen3-122b-c3-phaseD.md` を [REPORT.md](../../projects/llm-server-ops/REPORT.md) フォーマットで作成。

含めるセクション:
- 添付ファイル / 参照（前身 phaseC レポート、C-3, C-2, C-1）
- 前提・目的（F-1/F-2/F-3 の概要）
- 環境情報
- 計測手順（C-D1..D4 の起動差分表）
- 実行結果サマリ（eval / prompt 速度、numastat 配置、status）
- ボトルネック分析
- 採用判定
- 採用構成の起動コマンド
- **未検証事項**（前身から継続項目 + 本計測で残ったもの）
- **検証完了後に実施すべき TODO**（前身から継続項目 + 本計測の発見項目）

## 重要ファイル

- 流用元起動スクリプト: `report/attachment/2026-04-16_072324_qwen3-122b-c3-numa-phaseC/start_phaseC.sh`
- 流用元計測スクリプト: `report/attachment/2026-04-16_072324_qwen3-122b-c3-numa-phaseC/measure_phaseC.sh`
- GPU サーバ操作: `.claude/skills/gpu-server/scripts/{lock,unlock}.sh`
- llama-server 操作: `.claude/skills/llama-server/scripts/stop.sh`
- レポートフォーマット: `REPORT.md`
- 前身レポート: `report/2026-04-16_072324_qwen3-122b-c3-numa-phaseC.md`

## リスク・想定外事項

- **drop_caches 権限**: t120h-p100 の llm ユーザーが `sudo sysctl` できない場合、あらかじめ `sudo` を別経路で実行するか権限なしのフォールバック（`posix_fadvise` 経由のツール）を検討
- **計測時間**: 4 variant × 約 6 分 = 24 分。GPU サーバロックを長時間占有するため、他セッションへの影響に留意
- **観測ノイズ**: 前身でも判明したように perf/mpstat 等の並列観測はオーバーサブスクリプション時に大きく影響する。本計測も最小観測（dmon + status のみ）を継続
- **ページキャッシュ汚染**: 各 variant 間の drop_caches 忘れで効果が出ない。スクリプトで強制
- **C-D2 (`--numa distribute` 併用) の挙動**: `--numa distribute` は llama.cpp が `mbind` を呼ぶ可能性があり、numactl のメモリポリシーと衝突する可能性。ログで確認

## 検証手順（end-to-end）

1. ロック取得 → 既存プロセス停止確認
2. C-D1 計測（drop_caches → 起動 → numastat → 3 run）
3. C-D2 計測（同上）
4. C-D3 計測（同上）
5. C-D4 計測（同上）
6. 各 variant の predicted_per_second 中央値を C-C2 (11.91) と比較
7. 最良構成で再起動 → `/v1/chat/completions` で 1 リクエスト動作確認
8. ロック解放
9. レポート作成・保存
