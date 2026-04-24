# Phase Sb-fa0-offload: OT_REGEX 拡大で fa=0 × ctx≥32k を実現し δ 項の fa 依存性を確定

## Context

直前 Phase Sb-fa0 (2026-04-19 22:13) で候補 K（FA workspace が cross 項の発生源）は**事実上棄却**され、新解釈「**FA は cross 項を suppress する最適化**」に至った。しかし fa=0 × ctx=32k が CUDA1 compute buffer=6744 MiB（P100 16 GiB 枠で 140 MiB over）で OOM となり、**δ 項 (ctx=32k × ub=1586 で +0.24 MiB) が fa=1 固有（候補 L = FA tile 量子化副作用）か fa=0 でも出るか**という決定的検証点が未達。本 Phase は OT_REGEX を拡大して CUDA1 担当 attention 層の一部を CPU オフロードし、fa=0 × ctx=32k を起動成立させ δ 項の fa 依存性を数値確定する。副次成果として ctx=65k/131k も試行し、OOM でも alloc size から CUDA1 slope(ctx) fa=0 版の外挿点を取得する。

未検証事項での位置付け: **★最優先「Phase Sb-fa0-offload 候補（新規）」** および **「fa=0 × ctx=32k+ の CUDA1 alloc size から CUDA1 slope を派生測定」** の 2 項目を同バッチで同時消化。

## 設計判断

### OT_REGEX 拡張 — CUDA1 attention 層優先、段階的 escalation

t120h-p100 の層配置推定（4 GPU × 12 層均等、model buffer 9550 MiB/GPU より）:
| GPU | 担当層 |
|---|---|
| CUDA0 | 0-11 |
| **CUDA1** | **12-23**（OOM 当事者） |
| CUDA2 | 24-35 |
| CUDA3 | 36-47 |

既存 OT_REGEX は MoE FFN experts のみ CPU オフロード（`blk\.(X|Y|Z)\.ffn_.*_exps\.weight=CPU`）。本 Phase は **CUDA1 担当層 (12-23) の attention 層を CPU オフロード** することで CUDA1 compute buffer を縮小する。attention 計算の workspace が CUDA1 で要求される量を直接的に削る。

**escalation ladder（Stage 1 パイロットで確定）**:
| TAG | 追加パターン（既存 MoE オフロードと OR 結合） | CUDA1 attention 削減量 |
|---|---|---|
| X1 | `blk\.(2[0-3])\.attn_.*\.weight=CPU` | 4 層（20-23） |
| X2 | `blk\.(1[6-9]\|2[0-3])\.attn_.*\.weight=CPU` | 8 層（16-23） |
| X3 | `blk\.(1[2-9]\|2[0-3])\.attn_.*\.weight=CPU` | 12 層（CUDA1 担当全部） |
| X4 | 全 attention CPU オフロード（案 A 相当） | 48 層 |

Stage 1 パイロット: ctx=32k × ub=1584 で X1 → X2 → X3 → X4 の順に試行、最初に起動成立した TAG を `FINAL_OT_TAG` として以降に伝播。

### 実行 Stage 構成（計 40-60 分、GPU ロック保持 ~45 分目標）

| Stage | 条件 | 目的 | 時間見積 |
|---|---|---|---|
| 0 | GPU ロック取得、作業ディレクトリ作成 | - | 1 分 |
| 1 | パイロット: OT 案 X1-X4 × ctx=32k × ub=1584 | OT 案確定 | 5-15 分 |
| 2 | 本走査: 確定 OT × ctx=32k × ub∈{1584,1585,1586} | δ 項 fa 依存性判定（**★最優先**） | 10 分 |
| 3 | 拡張: 確定 OT × ctx∈{65536,131072} × ub∈{1584,1585,1586} | OOM でも alloc size 取得 | 10-20 分 |
| 4 | 比較: 確定 OT × ctx=16k × ub∈{1584,1585,1586} | OT 拡張が slope に与える影響確認 | 5 分 |
| 5 | 分析・レポート・GPU ロック解放 | - | 10 分 |

Stage 3 は Stage 2 成功 & 残時間 15 分以上なら実施、それ以外は skip（起動失敗時も OOM alloc size のみ TSV 記録）。

### 成功条件（最低限）

1. **★最優先**: Stage 2 の 3 条件で startup_log に CUDA0/1/2/3 compute buffer size が記録される
2. δ_fa0(ctx=32k) = Δ(1585→1586) − Δ(1584→1585) を 0.01 MiB 精度で取得
3. 候補 L 判定 verdict を `Sbfa0offload_candidate_L_verdict.txt` に出力:
   - `|δ_fa0| ≤ 0.10 MiB` → candidate_L **support**（δ は FA tile 固有）
   - `|δ_fa0 − 0.24| ≤ 0.05 MiB` → candidate_L **reject**（δ は fa 共通）
   - 中間値 → **partial**
4. レポートに「未検証事項」「検証完了後に実施すべき TODO」セクション完備

## 生成物

作業ディレクトリ: `report/attachment/<TS>_qwen3-122b-c3-phaseSbfa0offload/`（TS は実行時の JST タイムスタンプ）

| ファイル | 役割 | 差分元 |
|---|---|---|
| `plan.md` | 本プランの写し | 本ファイルを cp |
| `start_phaseSbfa0offload.sh` | 単一条件 start、OT_REGEX 環境変数化 | Phase Sb-fa0 `start_phaseSbfa0.sh` |
| `batch_Sbfa0offload.sh` | Stage 1-4 escalation バッチ | Phase Sb-fa0 `batch_Sbfa0.sh` |
| `analyze_Sbfa0offload.py` | 候補 L 判定・OT_TAG 別 pivot | Phase Sb-fa0 `analyze_Sbfa0.py` |
| `startup_logs/fa0offload_<TAG>_ctx<C>_ub<U>.log` | 起動ログ（条件毎） | - |
| `batch_Sbfa0offload_oom.tsv` | OOM alloc size（ctx=65k/131k 派生データ用） | 新規 |
| `summary_Sbfa0offload.tsv` / `Sbfa0offload_pivot_<TAG>.csv` / `Sbfa0offload_slopes.csv` | 分析成果物 | - |
| `Sbfa0offload_candidate_L_verdict.txt` | 候補 L 判定 | 新規 |
| `report/<TS>_qwen3-122b-c3-phaseSbfa0offload.md` | レポート（REPORT.md 準拠） | - |

## 実装手順

### Step 0: GPU ロック & 作業準備
```bash
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
WORKDIR="report/attachment/${TS}_qwen3-122b-c3-phaseSbfa0offload"
mkdir -p "$WORKDIR/startup_logs"
cp /home/ubuntu/.claude/plans/todo-quirky-pinwheel.md "$WORKDIR/plan.md"
```

### Step 1: `start_phaseSbfa0offload.sh`
Phase Sb-fa0 の start_phaseSbfa0.sh を基に以下のみ変更:
- `OT_REGEX` を環境変数化（デフォルトは MoE FFN のみ、案 X の regex は batch 側が渡す）
- `OT_TAG` 環境変数を受け、`REMOTE_LOG` ファイル名に含める (`phaseSbfa0offload_<TAG>_fa0_ctx*_ub*.log`)
- llama.cpp の `-ot` 引数は**複数パターンをカンマ区切り**で指定可能（実装時に一度手動確認、もし splitter 非対応なら `-ot A -ot B` 形式に変更）

### Step 2: `batch_Sbfa0offload.sh`
Phase Sb-fa0 の batch_Sbfa0.sh を基に:
- Stage 1 escalation ループ追加（X1 → X2 → X3 → X4、成立で break）
- `FINAL_OT_TAG` / `FINAL_OT_REGEX` 確定後、Stage 2/3/4 の本走査
- OOM 時は `ssh HOST "grep -E 'allocating [0-9.]+ MiB on device [0-9]' LOG"` で alloc size 抽出 → `batch_Sbfa0offload_oom.tsv`
- 各 Stage 間で必ず `bash .claude/skills/llama-server/scripts/stop.sh t120h-p100 && sleep 5` を挟む（プロセス残留防止）
- Stage 3 は残時間チェック: GPU ロック取得時刻 + 40 分を閾値、超過なら skip

### Step 3: `analyze_Sbfa0offload.py`
Phase Sb-fa0 の analyze_Sbfa0.py を基に:
- ファイル名 pattern を `fa0offload_(?P<tag>\w+)_ctx(\d+)_ub(\d+)\.log` に
- summary に `ot_tag` 列
- OT_TAG 毎の pivot 出力
- **新 verdict**: `Sbfa0offload_candidate_L_verdict.txt`:
  - fa=1 既知値 δ_fa1 = +0.24 MiB をハードコード参照
  - δ_fa0(ctx=32k) = Δ(1585→1586) − Δ(1584→1585) 計算
  - support / reject / partial のラベル付与
- OOM alloc size から CUDA1 slope(ctx=65k), slope(ctx=131k) 派生抽出（ctx=65k alloc size / ctx=131k alloc size それぞれ 3 ub 分）

### Step 4: バッチ実行
```bash
cd "$WORKDIR"
bash batch_Sbfa0offload.sh > batch_Sbfa0offload.log 2>&1
python3 analyze_Sbfa0offload.py
bash ../../../.claude/skills/llama-server/scripts/stop.sh t120h-p100
```

### Step 5: レポート作成
`report/<TS>_qwen3-122b-c3-phaseSbfa0offload.md` を REPORT.md 準拠で作成。以下を必須含める:
- 実施日時（JST, 作業時間, GPU ロック時間）
- 添付ファイル（plan.md, 全成果物）
- 前 Phase 参照リンク
- 実行結果サマリ（Stage 1 escalation 履歴、Stage 2 ピボット、δ_fa0 値、候補 L 判定）
- fa=1 vs fa=0 slope 対比表（前 Phase 拡張）
- 確定モデル更新（候補 L 確定/棄却に応じて）
- **「未検証事項」セクション** — Phase Sb-fa0 からの継続項目 + 本 Phase 新規項目、優先度マーク付き
- **「検証完了後に実施すべき TODO」セクション** — skill 更新、lint ルール、start.sh 拡張等

### Step 6: GPU ロック解放
```bash
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
bash .claude/skills/gpu-server/scripts/lock-status.sh t120h-p100   # 解放確認
```

## 検証方法

結果確認（全て `report/attachment/<TS>_qwen3-122b-c3-phaseSbfa0offload/` 配下）:

| 確認事項 | 参照 |
|---|---|
| Stage 1 escalation 履歴・採用 TAG | `batch_Sbfa0offload.log` の `[escalation]` 行、`FINAL_OT_TAG=...` |
| 条件毎起動結果 | `batch_Sbfa0offload_failures.tsv`（失敗のみ） |
| compute buffer 実測 | `startup_logs/fa0offload_*.log` の `CUDA\d compute buffer size` 行 |
| δ_fa0 値 | `Sbfa0offload_candidate_L_verdict.txt` |
| ctx=65k/131k OOM alloc | `batch_Sbfa0offload_oom.tsv` |
| 候補 L 判定 | 同 verdict ファイル末尾 `candidate_L: support/reject/partial` |

## リスクと回避策

| リスク | 回避策 |
|---|---|
| Stage 1 で X1-X4 全てが ctx=32k OOM | Stage 2 を ctx=16k × X4 の 3 条件に縮退し「ctx=32k fa=0 は P100 では X4 でも不可能」を記録、候補 L 判定は**未達**として次 Phase (KV8 or IQ2_XXS) へ引き継ぎ |
| llama.cpp `-ot` のカンマ区切り非対応 | `-ot pat1 -ot pat2` と複数指定に変更。start_phaseSbfa0offload.sh で `OT_REGEX` を改行区切りにし、`while read` で `-ot` を複数生成 |
| GPU ロック 60 分超過 | Stage 3 を timebox (残時間 <15 分なら skip)、Stage 4 も同様 |
| llama-server 停止失敗 | stop.sh の後に `ssh t120h-p100 "pkill -9 -f llama-server"` 保険、最終 unlock 前に lock-status.sh で確認 |
| attention CPU オフロードが eval 不可経路に触れる | 本 Phase は eval 未実施（compute buffer 測定のみ）、レポートに「eval 性能は未検証」と明記 |
| OT 拡張が fa=1 既存 slope に影響（比較基準変動） | Stage 4 で ctx=16k × 確定 OT の slope を測定、前 Phase 値 2.12 MiB/ub との差を記録。乖離が 0.1 MiB/ub 超なら「OT 影響補正が必要」と記録 |

## Critical Files to Create

- `/home/ubuntu/projects/llm-server-ops/report/attachment/<TS>_qwen3-122b-c3-phaseSbfa0offload/start_phaseSbfa0offload.sh`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/<TS>_qwen3-122b-c3-phaseSbfa0offload/batch_Sbfa0offload.sh`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/<TS>_qwen3-122b-c3-phaseSbfa0offload/analyze_Sbfa0offload.py`
- `/home/ubuntu/projects/llm-server-ops/report/<TS>_qwen3-122b-c3-phaseSbfa0offload.md`

ベースとする既存ファイル（全て読み取り・複製のみ）:
- `report/attachment/2026-04-19_221314_qwen3-122b-c3-phaseSbfa0/start_phaseSbfa0.sh`
- `report/attachment/2026-04-19_221314_qwen3-122b-c3-phaseSbfa0/batch_Sbfa0.sh`
- `report/attachment/2026-04-19_221314_qwen3-122b-c3-phaseSbfa0/analyze_Sbfa0.py`

## 実行後の追跡 TODO（レポート「検証完了後に実施すべき TODO」へ転載）

- skill / CLAUDE.md 更新: 「OT_REGEX 案 X<最終採用> で fa=0 × ctx=32k は実現可能。eval 性能は未検証」
- skill 側 `start.sh` の `--flash-attn` デフォルトは `1` 維持推奨（本 Phase 結果で更新）
- 起動前 lint の fa=0 ctx 閾値更新: `fa=0 & ctx≥32k & OT_REGEX が X1 以上を含まない → WARN`
- Phase Sb-tensor-dump の設計書き出し（debug build での FA kernel workspace dump、候補 L 最終確定手段）
- Phase Sb-KV8 候補（`--cache-type-{k,v} q8_0` で同走査、cross 項が KV 依存か）
- モデルカード更新（fa × ctx 実用域マトリクス）
