# Phase S-eval: ub=1584/1586/1664 eval 再現性検証

## Context

直前レポート [2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload.md](/home/ubuntu/projects/llm-server-ops/report/2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload.md) の未検証事項のうち、★最優先 **かつ** 短時間で実施可能な以下を潰す。

- **ub=1586 eval 15.466 t/s の 5-10 run 再現性** (★最優先, Phase Sbf3 継続)
- **ub=1664 eval 15.451 t/s の 5-10 run 再現性** (Phase Sb-fine 継続)
- **ub=1584 eval 15.293 t/s の 5-10 run 再現性** (Phase Sb-fine2 継続)

これら 3 点はそれぞれ別 Phase で 1-run のみ測定された値で、run 間ゆらぎを含めた「本当の」ピーク構造が未確定。検証完了後 TODO の ★最重要 **Phase S-eval** に対応。候補 L (FA tile 量子化副作用) が Phase Sb-fa0-offload で support 確定した今、fa=1 × ctx=32k における eval の ub 依存性ピーク (1584/1586/1664) の再現性が次の必須検証点。

本 Phase は debug build が必要な Phase Sb-tensor-dump (2-3 時間、★最優先同順位) より優先度・即時性のバランスが良い。所要 45-60 分で 3 条件 × 5-10 run を取得する。

## 実施概要

| 項目 | 値 |
|---|---|
| GPU サーバ | t120h-p100 (10.1.4.14, P100 × 4) |
| llama.cpp build | 既存 `~/llama.cpp/build/bin/llama-server`（Phase Sbfine3 と同一） |
| モデル | Qwen3.5-122B-A10B-Q4_K_M (既存 snapshot) |
| fa | 1 (flash-attn on) |
| ctx | 32768 |
| KV | f16 / f16 |
| OT_REGEX | `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU` (MoE only、X4 ではない) |
| ngl | 999 |
| numactl | `--cpunodebind=1 --membind=1` |
| threads | 40 |
| poll | 0 |
| ub = b | {1584, 1586, 1664} |
| eval 計測 run 数 | 7 run / 条件 (warmup 2 run を除き、5 run 集計 + 2 run 余裕) |
| 総所要時間 | 45-60 分 (start 各 1-2 分 × 3、eval 各 10-15 分 × 3) |

## 再現性検証のプロトコル

各 ub 値について:

1. llama-server を `start.sh` 相当で起動（1.5 分程度）
2. Phase Sbfine3 と同一 prompt (1k token 入力、n_predict=256) で **eval-only**（prompt_tps は計測するが集計は eval_tps 中心）
3. 最初の 2 run を warmup（結果破棄）、続く 5 run を正式計測
4. 各 run の eval_tps / prompt_tps / TTFT を JSON → TSV
5. llama-server を停止
6. 次 ub へ

集計:
- **eval_tps**: 平均・標準偏差・min/max・中央値・Run 1 外れ値判定 (±2σ)
- 15.466 / 15.451 / 15.293 t/s の 1-run 値が **±0.05 t/s** に収まれば `confirmed`、±0.10 に入れば `partial`、それ外れ値なら `reject`
- ub=1586 (+δ=+0.24 MiB/FA tile 境界) と ub=1584/1664 の有意差確認

## 成功条件

- [ ] 3 条件すべて起動成功
- [ ] 各条件 5 run 以上の有効 eval_tps を取得
- [ ] ub=1584/1586/1664 の平均 eval_tps / σ を確定
- [ ] 1-run 参照値との整合性判定 (confirmed / partial / reject)
- [ ] Run 1 外れ値の有無を記録
- [ ] ub=1586 vs 1584 の t-test 相当の有意差判定

## 作業ディレクトリと成果物

作業ディレクトリ: `report/attachment/2026-04-20_<HHMMSS>_qwen3-122b-c3-phaseSeval/`

生成物:
- `plan.md` — 本計画の反映
- `start_phaseSeval.sh` — Phase Sbfine3 の start を流用（UB 環境変数化）
- `batch_phaseSeval.sh` — 3 × 7 run ループ
- `measure_single.sh` — 1 run 実行 (curl + OpenAI API `/v1/chat/completions`、Phase I の `measure_phaseI.sh` を流用)
- `analyze_phaseSeval.py` — 集計・σ 算出・confirmed/partial/reject 判定
- `batch_phaseSeval.log` — 全体ログ
- `summary_phaseSeval.tsv` — run 別 raw データ
- `phaseSeval_stats.csv` — ub × 統計量
- `phaseSeval_verdict.txt` — 3 条件の再現性判定結果
- `startup_logs/` — 3 ファイル (ub=1584/1586/1664)

## 流用する既存ファイル

| 用途 | 参照元 |
|---|---|
| start.sh パターン | `report/attachment/2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok/start_*.sh` |
| batch 制御ロジック | `report/attachment/2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok/batch_*.sh` |
| curl + JSON payload | 過去 Phase で `measure_phaseI.sh` 系を流用 (存在確認必要、なければ自作) |
| GPU ロック | `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh` |
| llama-server 停止 | `.claude/skills/llama-server/scripts/stop.sh` |

## 重要な実装判断

- **run 数は 7**（warmup 2 + 計測 5）。10 run は時間 (+30%) 対効果が低い。標準偏差評価には 5 run で十分
- **prompt サイズは 1k token**（Phase Sbfine3 と同一）で eval_tps が支配的な条件、短 prompt では TTFT が大きく eval の分離が困難
- **GPU ロック保持目標は 60 分上限**。超える場合は ub=1664 を省略
- **Run 1 が外れ値の場合**、warmup と区別するため kernel cache warmup 効果の確認用として記録する（Phase J で 15.54 t/s 外れ値と同種の挙動）
- 既存 `measure_phaseI.sh` が存在するか不明 — 存在しなければ Phase Sbfine3 の batch スクリプト内から eval 部分を抽出して `measure_single.sh` を新規作成

## 検証（End-to-End）

1. GPU ロック取得: `bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100`
2. バッチ実行: `bash batch_phaseSeval.sh > batch_phaseSeval.log 2>&1`
3. 分析: `python3 analyze_phaseSeval.py`
4. 判定: `cat phaseSeval_verdict.txt` で 3 条件の confirmed/partial/reject を確認
5. 停止・解放: `bash .claude/skills/llama-server/scripts/stop.sh t120h-p100 && bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100`

## レポート作成

CLAUDE.md / REPORT.md のルールに従い `report/2026-04-20_<HHMMSS>_qwen3-122b-c3-phaseSeval.md` を作成。

必須セクション:
- 実施日時 / 作業種別 / GPU ロック状況
- 添付ファイル一覧
- 参照 (直前レポート、Phase Sbfine / Sbfine2 / Sbfine3)
- 前提・目的 / 成功条件
- 環境情報 / 再現方法
- 実行結果サマリ (ub × run 別 TSV / 統計量 / verdict)
- 再現性分析（run 間ゆらぎ、Run 1 外れ値、有意差）
- 採用判定
- **未検証事項** — 直前レポートの未検証リストを引き継ぎ、本 Phase で [x] マーク、新規項目を追加
- **検証完了後に実施すべき TODO** — 直前レポートから引き継ぎ、本 Phase で確定した内容を反映
- 補足

## 想定される結果と次 Phase

- 3 条件すべて confirmed: Phase Sb-tensor-dump (★最優先, debug build) または Phase Sb-tensor-names (★高優先, 20 分) へ
- 1-run 値が再現しない条件あり: Phase S-eval-extended（10 run、他 ub も含めた広域スキャン）
- 有意差なし（ub 依存性が消失）: Phase Sb-session-gap（セッション間ゆらぎ検証）

## 非対象

- eval の新 ub 値走査（1584/1586/1664 以外は対象外）
- fa=0 / OT=X4 の eval 計測（graph splits 3-5 倍で不適と確定済み）
- ctx 依存性（ctx=32k 固定）
- KV q8_0（Phase Sb-KV8 で別途）
- compute buffer size の再計測（Phase Sbfine3 までで確定済み）
