# Phase S-eval-10session 実施計画

## Context

直前レポート [2026-04-20_080258_qwen3-122b-c3-phaseSeval9s.md](/home/ubuntu/projects/llm-server-ops/report/2026-04-20_080258_qwen3-122b-c3-phaseSeval9s.md) の未検証事項・検証完了後 TODO のうち、**最優先** かつ最も多くの項目を同時に進められる「**Phase S-eval-10session 候補**」を実施する。

S9 までで n=9 の連続セッション観測が完了しており、S10 を追加することで以下の最優先未検証項目を同時に前進させられる:

- **ub=1586 崩壊モードの周期 or 確率判定** — S6 / S9 の 3 session 間隔再発が S12 で再現するか、S10 は中間観察点
- **ub=1664 3 帯分布 (下 5/9 / 中 2/9 / 上 2/9) の Wilson CI 更新**
- **ub=1664 の 2 値状態性 (1位 or 最下位) の再確認** — 9 session で中位 (2位) 観測 0/9 の継続確認
- **warmup ≒ eval 現象 (S9 で 3 ub 全体拡大) の再現性**
- **warmup1 absolute 第 4 帯** (S7/S8/S9 の 3 連続再現、15.40-15.44 中心) の継続確認
- **pooled σ の n=45→50 挙動** (ub=1586 σ_pool 拡大継続か・ub=1584 縮小継続か)
- **peak order 6 種モデルの更新** (9 session で 4 種観測 + 2 種未出現)
- **ub 別独立変動の 10 session 継続支持**
- **ub=1584 pooled mean 15.218 t/s の史上最高値の安定性**

所要時間 約 40 分（GPU ロック保持含む）、既存インフラ（start_phaseSeval9s.sh / batch / run_all / measure_phaseI / analyze_phaseSeval9s.py）をほぼそのまま S10 として複製するだけで完了する。

## 実施内容

### 条件（S9 と完全同一）

- **GPU サーバ**: t120h-p100 (10.1.4.14)、P100 × 4
- **llama.cpp**: 既存ビルド（前 Phase と同一 binary）
- **モデル**: Qwen3.5-122B-A10B-Q4_K_M
- **起動パラメータ**: fa=1、f16/f16 KV、ctx=32768、`numactl --cpunodebind=1 --membind=1`、threads=40、poll=0、ngl=999
- **OT_REGEX**: `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
- **ub 条件**: {1584, 1586, 1664}
- **warmup**: 2 run（短 prompt "Write a short haiku about autumn."、予測 256 tokens）
- **eval**: 5 run（`prompts/prompt_1k.txt` 流用、prompt_n=1085、max_tokens=256、`[Request ID <uniq>] ` prefix 付与）
- **cooldown**: run 間 60 秒
- **S9 との cool time**: 本 Phase 開始時刻で記録（S9 終了は 2026-04-20 08:43）

### 手順

1. **GPU ロック取得** — `bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100`
2. **attachment ディレクトリ作成** — `report/attachment/<YYYY-MM-DD_HHMMSS>_qwen3-122b-c3-phaseSeval10s/`
3. **S9 スクリプトを S10 として複製**:
   - `start_phaseSeval9s.sh` → `start_phaseSeval10s.sh`（ログ tag `phaseSeval9s` → `phaseSeval10s` のみ置換）
   - `batch_phaseSeval9s.sh` → `batch_phaseSeval10s.sh`（tag `Seval9s` → `Seval10s`、参照スクリプト名も更新）
   - `run_all.sh`、`measure_phaseI.sh` はそのまま流用（tag を引数で受ける設計）
   - `prompts/prompt_1k.txt` はそのまま再利用
4. **analyze_phaseSeval10s.py 作成** — `analyze_phaseSeval9s.py` をコピーし以下を変更:
   - `PRIOR_TSVS` に S9 の TSV を追加（`S9_phaseSeval9s` → `summary_phaseSeval9s.tsv`）
   - `CUR_SESSION_LABEL = "S10_phaseSeval10s"`
   - `TAG_PREFIX = "Seval10s_fa1_ctx"`
   - `MODE_GROUPS` の `prev_S8` / `prev_S9` / `cur_S10` を追記
   - 出力ファイル名 `phaseSeval10s_stats.csv` / `phaseSeval10s_verdict.txt` / `summary_phaseSeval10s.tsv`
5. **バッチ実行** — `bash batch_phaseSeval10s.sh > batch_phaseSeval10s.log 2>&1`（約 37 分）
6. **分析実行** — `python3 analyze_phaseSeval10s.py`
7. **停止・解放** — `bash .claude/skills/llama-server/scripts/stop.sh t120h-p100` → `bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100`
8. **レポート作成** — `report/2026-04-20_<HHMMSS>_qwen3-122b-c3-phaseSeval10s.md`
   - [REPORT.md](/home/ubuntu/projects/llm-server-ops/REPORT.md) のフォーマットに従う
   - 「未検証事項」「検証完了後に実施すべき TODO」セクションを含める（ユーザ指示）
   - S9 レポート構造を踏襲（前提・目的、環境情報、再現方法、実行結果サマリ、統計、考察、比較表、核心発見）
9. **Discord 通知** — レポート完成後、skill `discord-notify` でレポート URL 付き通知を送信

## 重要ファイル

### 既存（再利用・参照のみ）

- `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/lock.sh` — GPU ロック取得
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/unlock.sh` — GPU ロック解放
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/stop.sh` — llama-server 停止
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-20_080258_qwen3-122b-c3-phaseSeval9s/start_phaseSeval9s.sh` — 起動スクリプト雛形
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-20_080258_qwen3-122b-c3-phaseSeval9s/batch_phaseSeval9s.sh` — バッチ雛形
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-20_080258_qwen3-122b-c3-phaseSeval9s/run_all.sh` — 1 条件内ループ
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-20_080258_qwen3-122b-c3-phaseSeval9s/measure_phaseI.sh` — 1 run 計測
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-20_080258_qwen3-122b-c3-phaseSeval9s/analyze_phaseSeval9s.py` — 解析スクリプト雛形
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-20_080258_qwen3-122b-c3-phaseSeval9s/prompts/prompt_1k.txt` — 1k prompt
- `/home/ubuntu/projects/llm-server-ops/REPORT.md` — レポートフォーマット
- S1-S9 TSV（PRIOR_TSVS として analyze が参照）

### 新規作成

- `/home/ubuntu/projects/llm-server-ops/report/attachment/<NEW_DIR>/start_phaseSeval10s.sh`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/<NEW_DIR>/batch_phaseSeval10s.sh`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/<NEW_DIR>/run_all.sh`（S9 からコピー、内容変更不要）
- `/home/ubuntu/projects/llm-server-ops/report/attachment/<NEW_DIR>/measure_phaseI.sh`（S9 からコピー、内容変更不要）
- `/home/ubuntu/projects/llm-server-ops/report/attachment/<NEW_DIR>/analyze_phaseSeval10s.py`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/<NEW_DIR>/prompts/prompt_1k.txt`（S9 からコピー）
- `/home/ubuntu/projects/llm-server-ops/report/2026-04-20_<HHMMSS>_qwen3-122b-c3-phaseSeval10s.md`

## レポート構成（必須セクション）

- 前提・目的
- 判定しきい値
- 成功条件
- 環境情報
- セッション間隔表（S1-S10）
- 再現方法
- 実行結果サマリ（S10 eval 5-run ピボット、warmup、pooled 50-run）
- ub 別 session 間変動統計
- peak order / 帯分布 / 崩壊頻度の n=10 更新
- 核心発見（サマリ）
- S9 との対照表
- **未検証事項** — S9 の未検証項目を引き継ぎつつ、S10 で解消したものに [x]、新規発見を追記
- **検証完了後に実施すべき TODO** — S9 から継承 + 新規候補（Phase S-eval-11session / 個別 ub solo 等）
- 作業終了時点の状態

## 判定しきい値（S9 と同一）

- **fully_independent**: 10-session range (max−min) ≤ 0.02 t/s
- **partial_drift**: range ≤ 0.10 t/s
- **session_dominated**: range > 0.10 t/s
- **崩壊判定**: eval_mean < 15.0 t/s

## 検証方法（エンドツーエンド）

1. **起動確認** — `curl -sf -m 5 http://10.1.4.14:8000/health` が 3 条件すべてで OK を返す
2. **計測完了確認** — 各 ub で `out_Seval10s_fa1_ctx32768_ub<UB>_1k/eval_run{1..5}.json` が生成され、`predicted_n=256` / `eval_tps` が記録される
3. **TSV 生成確認** — `summary_phaseSeval10s.tsv` が 3 ub × (2 warmup + 5 eval) = 21 行生成
4. **統計出力確認** — `phaseSeval10s_stats.csv` に n=10 session の mean / σ_session / range / σ_pool が出力
5. **verdict 出力確認** — `phaseSeval10s_verdict.txt` に fully_independent / partial_drift / session_dominated 判定が出力
6. **後片付け確認** — `ssh t120h-p100 "ps aux | grep llama-server | grep -v grep"` で何も残っていない、GPU ロックディレクトリが空

## 注意事項

- **GPU ロック必須**: CLAUDE.md に従い、`gpu-server` skill 経由で取得・解放
- **sudo 不要**: 本 Phase は一切 sudo を使わない
- **plan mode 完了後の auto mode** で自動実行可能（ユーザは Auto Mode を指定済み）
- **メモリは既知パターン**: ub=1586 CUDA0=980.36 / CUDA1=452.31 / CUDA2=452.31 / CUDA3=1558.12 / Host=235.48 MiB（9 session 完全一致） — S10 で同値になることを自動検証
- **実作業時間**: 37 分前後（batch 実行本体）+ 起動/停止/ロック + 分析 + レポート作成

## 本 Phase で解消しない項目（TODO セクションへ送る）

- ub 別独立変動モデルの**物理機構特定**（thermal / cache / scheduler の実測なし）
- ub=1664 3 帯の**物理的区別** — Markov 構造特定には ub=1664 単独 20-30 run が必要
- ub=1586 崩壊の**確定周期判定** — S10-S15 連続観測が必要
- cold-boot / nextday / cooltime-scan 系 — 別 Phase
- Phase Sb-tensor-dump（debug build + FA kernel workspace dump）
