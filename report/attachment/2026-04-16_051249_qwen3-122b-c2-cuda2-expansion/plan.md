# C-1 拡張: CUDA2 に中間層 expert を追加復帰して eval 速度を向上

## Context

前身レポート [`report/2026-04-16_043659_qwen3-122b-128k-execution.md`](../../projects/llm-server-ops/report/2026-04-16_043659_qwen3-122b-128k-execution.md) で採用した **C-1 構成**（layer 14-19 の expert を GPU1 に復帰、eval 12.06 t/s = ベースライン比 +18%）の未検証 TODO のうち、**「C-1 の拡張余地」** を進める。

前身レポート C-1 実測で以下の VRAM 状態が確認されている：

| GPU | model | free (MiB) |
|-----|-------|-----------|
| CUDA0 | 1301 | 6568 |
| CUDA1 | **9551** | **2098** ← C-1 で expert 追加済み |
| CUDA2 | 1199 | **10962** ← 空き豊富、未活用 |
| CUDA3 | 1693 | 5786 |

**狙い**: CUDA2 が担当する中間層 (layer 24-29 相当、推定) の expert 重み約 9 GiB を GPU に戻すことで、eval 速度をさらに +15〜20% 程度押し上げる。CUDA1 同等の配置を CUDA2 にも適用する発想。

**現状**:
- t120h-p100 で C-1 構成 `blk\.([0-9]|1[0-3]|2[0-9]|3[0-9]|4[0-7])\.ffn_.*_exps\.weight=CPU` が稼働中（health OK 確認済み）
- llama-server プロセス PID 13395 が ctx 131072 で動作中
- ロックは解放済み

## 採用アプローチ

**C-2（仮称）**: C-1 の `-ot` パターンに layer 24-29 を追加で GPU 復帰。
- CPU: layer 0-13, 20-23, 30-47（34 層）
- GPU: layer 14-19, 24-29（12 層 = 6+6）
- 新 `-ot`: `blk\.([0-9]|1[0-3]|2[0-3]|3[0-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`

想定される VRAM 変化：
- CUDA2 の model buffer: 1199 → **約 10000 MiB** (+8800)、空き 10962 → **約 2000 MiB**（CUDA1 と同水準のマージン）
- CUDA0/1/3 は変化なし（層マッピングが CUDA1 と対称な中間層想定）

**OOM 時フォールバック**: 層範囲を 24-28（5 層）→ 24-27（4 層）と段階的に縮める。対応する `-ot` パターン:
- 24-28: `blk\.([0-9]|1[0-3]|2[0-4]|(29)|3[0-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
  - CPU: 0-13, 20-24, 29, 30-47 / GPU: 14-19, 25-28 ... 複雑になるので実行時に再構築
- シンプル版（24-28 = GPU）:
  `blk\.([0-9]|1[0-3]|2[0-3]|29|3[0-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
  - CPU: 0-13, 20-23, 29, 30-47 / GPU: 14-19, 24-28

## 実行手順

### Phase 0: 準備

1. 既存稼働状態確認（現在 C-1 稼働・health OK）
2. ロック取得
   ```bash
   .claude/skills/gpu-server/scripts/lock.sh t120h-p100
   ```
3. 前身 C-1 の eval ベンチを 1 回再測定（比較基準の再現性確認、オプション）
   ```bash
   curl -s http://10.1.4.14:8000/v1/chat/completions \
     -H 'Content-Type: application/json' \
     -d '{"model":"unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M","messages":[{"role":"user","content":"Write a 256-token explanation of the concept of recursion."}],"max_tokens":256}'
   ssh t120h-p100 "grep -E 'prompt eval|eval time' /tmp/llama-server.log | tail -4"
   ```

### Phase 1: C-2 構成で起動

1. 既存 llama-server 停止
   ```bash
   .claude/skills/llama-server/scripts/stop.sh t120h-p100
   ```
2. ssh 経由で新 `-ot` パターンで起動
   ```bash
   MODEL_PATH="/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf"

   LAUNCH_CMD="./build/bin/llama-server \
     -m '$MODEL_PATH' --jinja \
     -ngl 999 -ot 'blk\\.([0-9]|1[0-3]|2[0-3]|3[0-9]|4[0-7])\\.ffn_.*_exps\\.weight=CPU' \
     --flash-attn 1 --poll 0 -b 8192 -ub 8192 \
     --n-predict 32768 --threads -1 \
     --ctx-size 131072 --parallel 1 \
     --cache-type-k q8_0 --cache-type-v q8_0 \
     --defrag-thold 0.1 \
     --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 \
     --port 8000 --host 0.0.0.0 \
     --alias 'unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M'"

   ssh -f t120h-p100 "cd ~/llama.cpp && nohup bash -c \"\$LAUNCH_CMD\" > /tmp/llama-server.log 2>&1 < /dev/null &"
   ```
3. ヘルスチェック（最大 3 分）
   ```bash
   until curl -sf http://10.1.4.14:8000/health > /dev/null; do sleep 5; done
   ```

### Phase 2: VRAM 実測・eval ベンチ

1. nvidia-smi と llama-server ログで VRAM 配分を確認
   ```bash
   ssh t120h-p100 "nvidia-smi --query-gpu=index,memory.used,memory.free,memory.total --format=csv"
   ssh t120h-p100 "grep -E 'load_tensors|KV buffer|compute buffer|CPU_Mapped|llama_new_context' /tmp/llama-server.log"
   ```
2. eval ベンチ（前身 C-1 と同条件）
   ```bash
   curl -s http://10.1.4.14:8000/v1/chat/completions \
     -H 'Content-Type: application/json' \
     -d '{"model":"unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M","messages":[{"role":"user","content":"Write a 256-token explanation of the concept of recursion."}],"max_tokens":256}'
   ssh t120h-p100 "grep -E 'prompt eval|eval time' /tmp/llama-server.log | tail -4"
   ```
3. 判定基準：
   - **成功**: OOM なし & 全 GPU 空き ≥ 2 GiB & eval ≥ 12 t/s → Phase 4 へ
   - **OOM or 空き < 1 GiB**: Phase 3（フォールバック）へ
   - **速度劣化**（< 12 t/s）: 層マッピング推定が外れている可能性。load_tensors ログで実 GPU 配置を確認し、別の層範囲（例: 30-35）で再試行を検討

### Phase 3: フォールバック（OOM 時のみ）

層範囲を 24-28（5 層）に縮めて再起動：
```
-ot 'blk\.([0-9]|1[0-3]|2[0-3]|29|3[0-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'
```
- CPU: 0-13, 20-23, 29, 30-47 / GPU: 14-19, 24-28
- それでも OOM なら 24-27（4 層）にさらに縮小

### Phase 4: レポート作成・ロック解放

1. タイムスタンプ取得
   ```bash
   TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S
   ```
2. 添付ディレクトリ作成・プランコピー
   ```bash
   mkdir -p report/attachment/<ts>_qwen3-122b-c2-cuda2-expansion/
   cp /home/ubuntu/.claude/plans/vivid-toasting-donut.md \
      report/attachment/<ts>_qwen3-122b-c2-cuda2-expansion/plan.md
   ```
3. レポート作成 `report/<ts>_qwen3-122b-c2-cuda2-expansion.md`（REPORT.md 準拠）
   - 前提・目的（前身レポートの C-1 拡張 TODO に対応）
   - 環境情報
   - 実行結果テーブル（C-1 vs C-2 の VRAM・eval 比較）
   - 採用構成の完全な起動コマンド
   - **未検証事項**セクション: 本レポート時点で未検証の事項を列挙（既知のものも含む）
     - 既知: 長時間安定性（1時間超）、大コンテキストでの eval 速度（16k〜128k）、flash-attn off との比較
     - 新規: C-2 での長時間安定性、C-2 配下での CUDA2 ピーク VRAM 使用量、層→GPU マッピング推定の妥当性（load_tensors 実測との突合）
   - **検証完了後に実施すべき TODO**セクション: 次にやるべき作業を列挙（既知のものも含む）
     - 既知: start.sh の `LLAMA_OT_OVERRIDE` 相当拡張、CUDA1 セーフティマージンの OOM フォールバック実装（層範囲 15-18 退避）、flash-attn off ベンチマーク、大コンテキスト実プロンプトでの eval 計測（16k/32k/64k/128k）、1 時間超の連続稼働試験
     - 新規: C-2 採用時の start.sh プリセット化、さらなる拡張（CUDA0/3 の compute buffer を減らして expert 追加余地を作れるか検討）
4. ロック解放
   ```bash
   .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
   ```

## 成功条件

- C-2 構成で ctx 131072 が OOM なく起動
- 全 GPU 空き ≥ 2 GiB（前身 C-1 の CUDA1 マージンと同水準）
- eval 速度が C-1（12.06 t/s）と同等以上、理想は 14 t/s 以上
- レポート書き上げ + プランファイル添付

## 触るファイル

- **新規作成**: `report/<ts>_qwen3-122b-c2-cuda2-expansion.md`
- **新規作成**: `report/attachment/<ts>_qwen3-122b-c2-cuda2-expansion/plan.md`（本プランのコピー）
- **触らない**: `.claude/skills/llama-server/scripts/start.sh`（今回も ssh 経由手動起動で対応）
- **触らない**: その他プロジェクトコード・設定

## リスクと緩和策

| リスク | 緩和策 |
|--------|--------|
| 層→GPU マッピング推定が外れ、CUDA2 ではなく CUDA0/3 に乗る | load_tensors ログで実配置を確認。別層範囲（30-35 等）で再試行 |
| CUDA2 に 9 GiB 追加で OOM | Phase 3 で 5 層 → 4 層と段階縮小 |
| eval 速度がむしろ低下 | C-1 構成にロールバック（`-ot` を元パターンに戻して再起動） |
| llama-server の停止→再起動中の一時的 API 断（約 1-2 分） | 事前にユーザーに通知は不要（ロック取得済み）。起動失敗時は C-1 に戻す |

## 検証（レポート完了前の最終確認）

- [ ] llama-server が稼働中（`curl http://10.1.4.14:8000/health` が 200）
- [ ] `nvidia-smi` で全 GPU 空き ≥ 2 GiB
- [ ] eval ベンチで tokens/s が記録されている
- [ ] レポートに C-1 との比較テーブル・完全な起動コマンド・前身レポートへのリンクが含まれている
- [ ] プランファイルが添付ディレクトリにコピーされている
