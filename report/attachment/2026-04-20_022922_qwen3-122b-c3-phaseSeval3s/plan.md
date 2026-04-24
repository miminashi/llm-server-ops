# Phase S-eval-3session 実施計画

## Context

直前レポート [2026-04-20_013006_qwen3-122b-c3-phaseSevalcross.md](/home/ubuntu/projects/llm-server-ops/report/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross.md) で、ctx=32768 × fa=1 × OT=MoE-only 固定、ub={1584, 1586, 1664} × 5-run の計測を 2 セッションで実施した結果、以下が判明:

- **ub=1586 のみ session_independent**（Δsession=+0.016 t/s、pooled σ=0.010）
- ub=1584（Δ=+0.264）/ ub=1664（Δ=+0.395）は session_dominated
- ピーク ub 順序 (1584 > 1586 > 1664) は両 session で維持
- compute buffer は 1 MiB 単位で一致 → 性能ドリフトは runtime kernel 状態由来

しかし、これらは **2 session のみの観察**。直前レポートの未検証事項★最優先「**3+ session での cross-session 検証**」および次推奨 Phase 筆頭「**Phase S-eval-3session**」として残置された。

本 Phase S-eval-3session は **時間を空けた別セッション（第 3 session）で同条件 5-run を再実行**し、以下を達成する:

1. σ_session（セッション間標準偏差）の確度向上（n=3 で初の安定推定）
2. ub=1586 session_independent 性の第 3 session 検証（2 点→3 点）
3. ub=1584/1664 の bimodal 分布が trimodal 化するか、第 3 点がどこに落ちるか確認
4. pooled 15-run mean / σ の算出（「真の性能値」推定確度の更新）
5. ピーク ub 順序のセッション間安定性を 3 session で再確認

## アプローチ

**前 Phase S-eval-cross-session のスクリプト・設定を完全再利用**し、別タイムスタンプの添付ディレクトリに新セッションとして計測する。差分は以下のみ:

- 添付ディレクトリ: `report/attachment/<new-timestamp>_qwen3-122b-c3-phaseSeval3s/`
- TAG_PREFIX: `Seval3s_fa1_ctx`
- ログ接頭辞: `phaseSeval3s`
- 前 Phase TSV 2 本（phaseSeval + phaseSevalcross）を **合算して prior として読む** 3-session 分析スクリプト `analyze_phaseSeval3s.py` を新規作成

計測条件（前 Phase と完全同一）:
- ctx=32768, fa=1, f16/f16 KV
- OT_REGEX: `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
- numactl --cpunodebind=1 --membind=1, threads=40, poll=0, ngl=999
- prompt: prompt_1k.txt（1084 tokens、Sbfine3 流用）、max_tokens=256、run 間 cooldown 60 秒
- warmup 2 + eval 5、UBS=[1584, 1586, 1664]、所要約 37-41 分

## 手順

1. **GPU ロック取得**: `bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100`
2. **添付ディレクトリ作成**: `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` でタイムスタンプ取得し、`report/attachment/<ts>_qwen3-122b-c3-phaseSeval3s/` を作成
3. **スクリプトコピー**: 前 Phase S-eval-cross-session ディレクトリから以下をコピーし、`Sevalcross` → `Seval3s`、`phaseSevalcross` → `phaseSeval3s`、TAG_PREFIX を書き換え:
   - `start_phaseSevalcross.sh` → `start_phaseSeval3s.sh`
   - `batch_phaseSevalcross.sh` → `batch_phaseSeval3s.sh`
   - `run_all.sh`、`measure_phaseI.sh`（改変不要）
   - `prompts/prompt_1k.txt`（改変不要）
4. **3-session 分析スクリプト作成**: `analyze_phaseSeval3s.py` を新規作成
   - phaseSeval + phaseSevalcross の TSV を読み込み、第 3 session と合算し pooled 15-run 統計
   - ub 別の session 間 σ_session（n=3）、session 毎 mean の時系列、ub 毎 verdict 再判定
   - ピーク順序 3 session 安定性、ub=1586 の session_independent 性の n=3 検証
5. **バッチ実行**: `bash batch_phaseSeval3s.sh > batch_phaseSeval3s.log 2>&1`（所要 37-41 分）
6. **分析**: `python3 analyze_phaseSeval3s.py`
7. **停止・解放**: `stop.sh t120h-p100` → `unlock.sh t120h-p100`
8. **レポート作成**: `report/<ts>_qwen3-122b-c3-phaseSeval3s.md` に以下セクション:
   - 前提・目的 / 環境情報 / 再現方法 / 実行結果サマリ（3-session 統計テーブル中心）
   - 再現性分析と解釈 / 採用判定
   - **未検証事項**（前 Phase から継承 + 本 Phase で判明したもの）
   - **検証完了後に実施すべき TODO**（前 Phase から継承 + 本 Phase 派生）
   - 補足（3-session verdict / 次の推奨 Phase）
9. **プランファイル添付**: `cp /home/ubuntu/.claude/plans/todo-peaceful-goose.md report/attachment/<ts>_qwen3-122b-c3-phaseSeval3s/plan.md`

## 再利用する資産

| ファイル | 出典 |
|---|---|
| `start_phaseSevalcross.sh` | report/attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/ |
| `batch_phaseSevalcross.sh` | 同上 |
| `run_all.sh` / `measure_phaseI.sh` | 同上 |
| `prompts/prompt_1k.txt` | 同上（Sbfine3 由来、1084 tokens） |
| `summary_phaseSeval.tsv` | report/attachment/2026-04-20_003250_qwen3-122b-c3-phaseSeval/ |
| `summary_phaseSevalcross.tsv` | report/attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/ |

## 新規作成するファイル

- `batch_phaseSeval3s.sh`（phaseSevalcross → phaseSeval3s のリテラル書換のみ）
- `start_phaseSeval3s.sh`（ログ ID 差し替えのみ）
- `analyze_phaseSeval3s.py`（3-session 用に新規設計、pooled 15-run + n=3 σ_session）
- レポート本体

## 検証方法（end-to-end）

1. バッチ実行ログ `batch_phaseSeval3s.log` を確認し、3 条件すべて `measure done` で正常終了していること
2. `summary_phaseSeval3s.tsv` に 3 条件 × 5 run の eval_tps が記録されていること
3. `phaseSeval3s_verdict.txt` で:
   - ub=1586 の 3-session Δ_max が 0.02 t/s 以内を維持していること（session_independent 継続）
   - ub=1584/1664 の 3-session σ_session が算出され、bimodal/trimodal 構造が読み取れること
   - ピーク ub 順序 1584 > 1586 > 1664 が 3 session すべてで維持されていること
4. `start.sh` の compute buffer ログが前 Phase と 1 MiB 単位で一致していること（物理構成の再現性確認）
5. GPU ロックが `unlock.sh` で正常に解放されていること（`ls /tmp/gpu-server-locks/` に該当ロックなし）

## リスク・留意点

- **セッション間隔**: 前 Phase Svalcross 終了 (02:11 JST) から現在 (約 04:00 JST) で 2 時間弱空いている。「intra-day drift」として弱めだが、第 3 session として十分有効
- **失敗時の切り分け**: llama-server 起動失敗・OOM は前 Phase で未発生だが、発生時は前 Phase 同様 GPU ロックを解放してから再起動
- **プロンプト cache hit**: `[Request ID <uniq>]` prefix で既回避、warmup 2 runでさらに安定化
