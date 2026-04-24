# C-3 実験: layer 24 を避けた C-1 拡張案の検証

## Context

前身レポート [`report/2026-04-16_051249_qwen3-122b-c2-cuda2-expansion.md`](../../projects/llm-server-ops/report/2026-04-16_051249_qwen3-122b-c2-cuda2-expansion.md) にて、C-1 構成（layer 14-19 の expert を GPU 復帰、eval 12.06 t/s）の拡張として C-2（14-19 + **24-29**）を試行したが、**layer 24 が CUDA1 に配置される**ことで CUDA1 空きが 2098 → 706 MiB へ縮小し、eval 速度向上も +3.6% に留まりトレードオフが悪かったため C-1 にロールバックした。

同レポートの「検証完了後に実施すべき TODO（新規項目）」の最優先項目が本プラン。

**仮説**: `--split-mode layer` の既定配置では layer 24 が CUDA1/CUDA2 境界の CUDA1 側、layer 30 が CUDA2/CUDA3 境界の CUDA2 側にアライメントされている。C-2 で判明した layer 24 を CPU 側に残し、代わりに layer 30 を GPU に復帰させれば、**CUDA1 の負荷を増やさずに CUDA2 に 6 層追加** できる可能性がある。

**期待結果**:
- CUDA1 空き ≥ 2 GiB（C-1 と同水準を維持）
- CUDA2 空き ≥ 2 GiB（C-2 では 3490 MiB だったので十分）
- eval +5〜10%（12 層 GPU 分の効果を享受できれば C-2 の +3.6% を上回る）

**失敗時のフォールバック**: OOM または CUDA1 空きが 1.5 GiB 未満に落ちた場合は C-1 にロールバック。eval 向上が +3% 未満の場合も C-1 継続（C-2/C-2' と同等以下なら採用価値なし）。

## 実験構成（C-3）

- **`-ot` パターン**: `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
  - CPU 層: 0-13, 20-24, 31-47（計 36 層）
  - GPU 層: **14-19, 25-30**（計 12 層、C-1 の倍）
- 他パラメータは C-1 と完全一致（`-ctx-size 131072`, `-b 8192 -ub 8192`, `--flash-attn 1`, `cache-type q8_0` 等）

## 実施手順

### 1. 事前準備

```bash
# ロック取得（既に t120h-p100 は自セッションで保持している可能性あり、要確認）
.claude/skills/gpu-server/scripts/lock-status.sh
.claude/skills/gpu-server/scripts/lock.sh t120h-p100  # 未ロック時のみ
```

### 2. 現状 C-1 の再確認（省略可）

前レポートで測定済みのため、ログ確認のみ。ssh で `ps aux | grep llama-server` と `nvidia-smi` を取得し、C-1 稼働中であることを確認。

### 3. C-3 起動

```bash
# 既存プロセス停止
.claude/skills/llama-server/scripts/stop.sh t120h-p100

# C-3 構成で起動
MODEL_PATH="/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/snapshots/51eab4d59d53f573fb9206cb3ce613f1d0aa392b/Q4_K_M/Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf"

LAUNCH_CMD="./build/bin/llama-server \
  -m '$MODEL_PATH' --jinja \
  -ngl 999 -ot 'blk\\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\\.ffn_.*_exps\\.weight=CPU' \
  --flash-attn 1 --poll 0 -b 8192 -ub 8192 \
  --n-predict 32768 --threads -1 \
  --ctx-size 131072 --parallel 1 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --defrag-thold 0.1 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 \
  --port 8000 --host 0.0.0.0 \
  --alias 'unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M'"

ssh -f t120h-p100 "cd ~/llama.cpp && nohup bash -c \"$LAUNCH_CMD\" > /tmp/llama-server.log 2>&1 < /dev/null &"

# ヘルスチェック
until curl -sf http://10.1.4.14:8000/health > /dev/null; do sleep 5; done
```

### 4. VRAM 測定

```bash
ssh t120h-p100 "nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv,noheader"
ssh t120h-p100 "grep -E '(load_tensors|compute buffer size|KV self size)' /tmp/llama-server.log"
```

**チェックポイント**:
- CUDA1 空き ≥ 1500 MiB（最低ライン、目標 ≥ 2000 MiB）
- 他全 GPU 空き ≥ 2000 MiB
- OOM ログなし

### 5. eval ベンチ

前レポート C-2/C-2' と同じプロンプトで `max_tokens=256` を測定。3 回実行して中央値を採用（試行ばらつき排除）。

```bash
for i in 1 2 3; do
  curl -s http://10.1.4.14:8000/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -d '{"model":"unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M","messages":[{"role":"user","content":"Write a short haiku about autumn."}],"max_tokens":256}' \
    | tee /tmp/c3-run-$i.json
done
```

ログから `eval time / tokens per second` 抽出:
```bash
ssh t120h-p100 "tail -200 /tmp/llama-server.log | grep 'eval time'"
```

### 6. 判定

| 判定 | CUDA1 空き | eval (t/s) | アクション |
|------|-----------|-----------|----------|
| **採用** | ≥ 1500 MiB | ≥ 12.5 | C-3 を新ベースに昇格 |
| **継続検討** | ≥ 1500 MiB | 12.0〜12.5 | C-3 継続稼働だが C-1 も選択肢 |
| **ロールバック** | < 1500 MiB または OOM | 任意 | C-1 に戻す |
| **ロールバック** | 任意 | < 12.0 | C-1 に戻す（C-2/C-2' より劣ると追加実験価値なし） |

### 7. ロールバック（必要時）

```bash
.claude/skills/llama-server/scripts/stop.sh t120h-p100
# C-1 の起動コマンドを前身レポート 113-149 行から転記して起動
```

### 8. レポート作成

- ファイル名: `report/$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)_qwen3-122b-c3-layer30-swap.md`
- 添付ディレクトリに本プランファイルをコピー
- フォーマット: [REPORT.md](../../projects/llm-server-ops/REPORT.md) に準拠
- **必須セクション**:
  - タイトル、日時（JST）、作業種別（実行・実測）
  - 添付ファイル（プランファイルへのリンク）
  - 参照（前身レポート 2 本へのリンク）
  - 前提・目的（layer 30 swap の仮説）
  - 環境情報（前身と同じ）
  - 実行結果サマリ（C-1 / C-2 / C-2' / **C-3** の比較表）
  - 各プランの詳細（C-3 の VRAM 配分、eval、層→GPU アライメントの判明事項）
  - 結論と判断（採用 or ロールバック）
  - **未検証事項** セクション（前身レポートから継続項目 + 本実験で残った項目）
  - **検証完了後に実施すべき TODO** セクション（同上）
  - 採用構成の起動コマンド（C-3 採用時のみ）
  - 補足（作業終了時点の稼働構成、ロック状態）

### 9. 後片付け

```bash
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100  # ロック解放
```

## 批判的ファイル

- `/home/ubuntu/projects/llm-server-ops/report/2026-04-16_043659_qwen3-122b-128k-execution.md`:113-149 — C-1 起動コマンドの原典
- `/home/ubuntu/projects/llm-server-ops/report/2026-04-16_051249_qwen3-122b-c2-cuda2-expansion.md`:54-87 — C-2/C-2' の VRAM 配分と失敗要因
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh` — llama-server 停止
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/{lock,unlock}.sh` — ロック管理
- `/home/ubuntu/projects/llm-server-ops/REPORT.md` — レポートフォーマット規定

## 検証方法（end-to-end）

1. C-3 起動後 `curl http://10.1.4.14:8000/health` が 200 OK
2. `nvidia-smi` で CUDA1 空き ≥ 1500 MiB
3. eval ベンチが 3 回とも正常応答（256 tokens 生成）し、中央値 ≥ 12.0 t/s
4. llama-server.log に `cudaMalloc failed` や `out of memory` が出ていない
5. レポートに C-1/C-2/C-2'/C-3 の 4 構成比較表と未検証事項/TODO セクションを含む

## 想定所要時間

- 起動・停止・再起動含む実験: 約 15〜25 分（モデルロードは OS page cache で短縮される想定）
- レポート作成: 約 10 分
- 合計: 約 30〜40 分

## 非スコープ

- 長時間安定性試験（1 時間超）: 別 TODO
- 大コンテキスト eval（16k〜128k）: 別 TODO
- flash-attn off 比較: 別 TODO
- start.sh 拡張: 別 TODO
- 層→GPU アライメントのソースコード解析: 別 TODO（本実験で実挙動のヒントが得られれば記録する）
