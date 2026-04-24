# Qwen3.5-122B-A10B 128k コンテキスト化と VRAM 最適化 — 実行プラン

## Context

2026-04-10 のレポート [`report/2026-04-10_161331_qwen3-122b-128k-vram-tuning.md`](../../projects/llm-server-ops/report/2026-04-10_161331_qwen3-122b-128k-vram-tuning.md) で設計した段階検証プラン（A → B → D → C-1）を実行フェーズに移す。目的は `t120h-p100` で `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M` を **ctx 131072（128k）** で安定稼働させつつ、空いた VRAM に expert 重みを戻して eval 速度を向上させること。

調査レポートの提案はすべて「実測前の推定」である点に留意する。各プラン実行後に必ず nvidia-smi／起動ログで実測値を確認し、仮説 H1（compute buffer は ctx 非依存）／H2（弱く比例）／H3（GPU 間不均衡）のどれが成立したかを判定してから次プランに進む。

**現状**: t120h-p100 の電源は OFF（`power.sh status` で確認済み）。iLO5 経由で起動する必要がある。

**ユーザ判断済みの方針**:
- 電源 ON にして実行する
- プラン A → B → D → C-1 を自動で段階検証（OOM 時は自動で退避プランへ）
- B/C/D は `start.sh` を拡張せず、**ssh 経由で llama-server コマンドを直接起動** する（`start.sh` のビルドと環境変数処理はプラン A で済ませ、B 以降は起動コマンドのみ差し替え）

## 実行手順

### Phase 0: 準備（電源 ON・ロック取得）

1. iLO5 で t120h-p100 を電源 ON
   ```bash
   .claude/skills/gpu-server/scripts/power.sh t120h-p100 on
   ```
2. SSH 到達まで待機（ポーリング、最大 5 分）
   ```bash
   until ssh -o ConnectTimeout=5 t120h-p100 "echo ready" 2>/dev/null; do sleep 10; done
   ```
3. ロック取得
   ```bash
   .claude/skills/gpu-server/scripts/lock.sh t120h-p100
   ```
4. 既存 llama-server プロセス確認（通常は起動直後なので無し）
   ```bash
   ssh t120h-p100 "pgrep -a -f './build/bin/llama-server'"
   ```

### Phase 1: プラン A — ctx 131072 ベースライン（仮説 H1 vs H2 実測）

**狙い**: 最小差分で 128k が収まるか、compute buffer が ctx 倍化でどれだけ増えるかを実測。

1. 起動（既存 `start.sh` の fit モードを利用）
   ```bash
   .claude/skills/llama-server/scripts/start.sh t120h-p100 \
     "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit 131072
   .claude/skills/llama-server/scripts/wait-ready.sh t120h-p100 \
     "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit 131072
   ```
2. 計測
   ```bash
   ssh t120h-p100 "nvidia-smi --query-gpu=index,memory.used,memory.free,memory.total --format=csv"
   ssh t120h-p100 "grep -E 'load_tensors|KV buffer|RS buffer|compute buffer|CPU_Mapped|llama_new_context' /tmp/llama-server.log"
   ```
3. eval 速度ベンチ（16k トークン入力・512 出力）
   ```bash
   curl -s http://10.1.4.14:8000/v1/chat/completions \
     -H 'Content-Type: application/json' \
     -d '{"model":"unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M","messages":[{"role":"user","content":"<16k 程度のダミープロンプト>"}],"max_tokens":512,"stream":false}' | jq '.usage'
   ssh t120h-p100 "grep -E 'prompt eval|eval time|tokens per second' /tmp/llama-server.log | tail -20"
   ```
4. 判定:
   - CUDA3 空き ≥ 3 GiB & OOM なし → **プラン B に進む**
   - OOM → `-b 4096 -ub 4096` に縮めてプラン A′ でリトライ。それでも OOM なら Phase 4 へ飛ばす

計測結果は Markdown 表で記録（後のレポート材料）。

### Phase 2: プラン B — down_proj のみ GPU 復帰

**狙い**: expert 重み 72.3 GiB のうち down_proj 分（約 24 GiB）を GPU に戻す。

1. 既存 llama-server 停止
   ```bash
   .claude/skills/llama-server/scripts/stop.sh t120h-p100
   ```
2. ssh 経由で直接起動（`-ot` を `ffn_(gate|up)_exps\.weight=CPU` に差し替え）
   ```bash
   # モデルパスは Phase 1 ログから確認済みのものを使用
   MODEL_PATH=$(ssh t120h-p100 "find ~/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/ -name '*Q4_K_M*.gguf' -not -name '*.incomplete' 2>/dev/null | sort | head -1")

   LAUNCH_CMD="./build/bin/llama-server \
     -m '$MODEL_PATH' --jinja \
     -ngl 999 -ot 'ffn_(gate|up)_exps\\.weight=CPU' \
     --flash-attn 1 --poll 0 -b 8192 -ub 8192 \
     --n-predict 32768 --threads -1 \
     --ctx-size 131072 --parallel 1 \
     --cache-type-k q8_0 --cache-type-v q8_0 \
     --defrag-thold 0.1 \
     --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 \
     --port 8000 --host 0.0.0.0 \
     --alias 'unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M'"

   ssh -f t120h-p100 "cd ~/llama.cpp && nohup bash -c \"$LAUNCH_CMD\" > /tmp/llama-server.log 2>&1 < /dev/null &"
   .claude/skills/llama-server/scripts/wait-ready.sh t120h-p100 \
     "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" 131072
   ```
3. 計測（Phase 1 と同じ項目）
4. 判定:
   - 起動成功 & eval 速度向上 → **完了**（Phase 5 のレポート作成へ）
   - OOM（特に CUDA3） → **プラン D へ**

### Phase 3: プラン D — `-b/-ub 4096` で compute buffer を削りプラン B を成立させる

**狙い**: `-b 4096 -ub 4096` により CUDA3 の compute buffer を 8 GiB → 約 4 GiB に削減し、B の 6 GiB 追加を収めるマージンを作る。

1. 既存 llama-server 停止
2. ssh 経由直接起動（Phase 2 のコマンドから `-b 8192 -ub 8192` → `-b 4096 -ub 4096` に変更）
3. 計測・判定:
   - 起動成功 → **完了**（prompt processing は遅くなるが eval 速度は B と同等）
   - OOM → **プラン C-1 へ**

### Phase 4: プラン C-1 — layer 14〜19 のみ expert を GPU に復帰

**狙い**: GPU1 が担当すると推定される中間層（6 層、+9 GiB）だけ expert を GPU 側に残す最低限の攻め手。

1. 既存 llama-server 停止
2. ssh 経由直接起動（`-ot` を層パターンに差し替え）
   ```
   -ot 'blk\.([0-9]|1[0-3]|2[0-9]|3[0-9]|4[0-7])\.ffn_.*_exps\.weight=CPU'
   ```
   ctx は 131072 のまま。`-b 8192 -ub 8192`。
3. 計測・判定:
   - 起動成功 → 完了
   - OOM → 層範囲をさらに絞る（例: layer 15〜17 のみ GPU）

### Phase 5: レポート作成・ロック解放

1. タイムスタンプ取得
   ```bash
   date +%Y-%m-%d_%H%M%S
   ```
2. 添付ディレクトリ作成・プランコピー
   ```bash
   mkdir -p report/attachment/<timestamp>_qwen3-122b-128k-execution/
   cp /home/ubuntu/.claude/plans/sleepy-discovering-balloon.md \
      report/attachment/<timestamp>_qwen3-122b-128k-execution/plan.md
   ```
3. レポート本文 `report/<timestamp>_qwen3-122b-128k-execution.md` を作成（REPORT.md ルール準拠、前身レポートへのリンクあり）
   - 前提・目的（前身レポートからの継続）
   - 環境情報
   - 実行結果（各プランの実測値テーブル、採用プラン、eval 速度）
   - 仮説判定（H1/H2/H3 のどれが成立したか）
   - 再現手順（最終採用構成の ssh コマンドを完全な形で）
   - 未検証事項・今後の TODO
4. 最終的に停止するかは採用プランに依存（成功した構成を残す運用）。本プランでは **成功プランで稼働したまま** ロックを解放するか否かをユーザに確認する余地を残す
5. ロック解放
   ```bash
   .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
   ```
6. Discord 通知（`.claude/skills/discord-notify/scripts/notify.sh` でレポート完了を通知）

## 成功条件

- ctx 131072 で 10 分以上（= 健康チェック + 1 回の eval ベンチ）安定稼働（OOM なし）
- 全 GPU で 3 GiB 以上の空き VRAM（セーフティマージン）
- プラン B/C/D のいずれかで eval 速度が現状（~10 t/s）を上回る（目標 13〜17 t/s）
- レポート書き上げ + プランファイル添付

## 触るファイル

- **新規作成**: `report/<timestamp>_qwen3-122b-128k-execution.md`
- **新規作成**: `report/attachment/<timestamp>_qwen3-122b-128k-execution/plan.md`（本プランのコピー）
- **触らない**: `.claude/skills/llama-server/scripts/start.sh`（今回は手動起動で対応。`LLAMA_OT_OVERRIDE` 拡張は別タスクで検討）
- **触らない**: その他プロジェクトコード・設定

## リスクと緩和策

| リスク | 緩和策 |
|--------|--------|
| プラン A で ctx 131072 が収まらない（H2 が顕著） | `-b 4096 -ub 4096` で Phase 3 相当のリトライ。それでも NG なら H1 前提を破棄し、Phase 4 へ |
| プラン B で CUDA3 OOM | Phase 3（D）に自動遷移 |
| プラン D でも OOM | Phase 4（C-1）に自動遷移。層範囲を絞る |
| サーバ電源 ON 後に SSH が上がらない | iLO5 コンソールで状態確認。5 分タイムアウトで中断してユーザに報告 |
| 層→GPU マッピング推定が外れる | Phase 1 の `load_tensors` ログで実測マッピングを確認してから Phase 4 へ入る |
| フラッシュアテンションが CC 6.0 P100 で不安定 | `--flash-attn 0` を退避候補として用意（compute buffer は増えるが安定性優先） |

## 検証（レポート完了前の最終確認）

- [ ] llama-server が稼働中である（`curl http://10.1.4.14:8000/health` が 200）
- [ ] `/v1/models` で alias が `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M` であること
- [ ] `nvidia-smi` で全 GPU 空き ≥ 3 GiB
- [ ] 16k トークン入力の eval で 512 トークン生成が成功し、`tokens per second` が記録されている
- [ ] レポートに前身レポートへのリンク・添付プランへのリンク・全プランの実測テーブル・採用プランの完全な起動コマンドが含まれている
