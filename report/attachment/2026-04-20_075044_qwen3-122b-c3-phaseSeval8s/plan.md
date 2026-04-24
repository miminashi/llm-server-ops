# Plan: Phase S-eval-8session（第 8 セッション追加、ub 別独立変動モデル再確認）

## Context

直前 Phase S-eval-7session (n=7) で以下が確定した:

- S7 で **3 ub の最近接モードがすべて異なる**（1584→C / 1586→A / 1664→B）ことから、**ub 別独立変動モデル** が決定的に支持された
- ub=1586 の **bouncing 機構**（S5 +0.187 → S6 -0.594 → S7 +0.407）が確認された
- ub=1664 の S6 過去最高ジャンプ +0.579 は S7 -0.556 で完全打ち消し、**「散発的 outlier 型」** と確定
- 崩壊頻度は ub=1584 1/7=14.3% / ub=1586 1/7=14.3% / ub=1664 **4/7=57.1%**（Wilson 95% CI 依然広い）

S7 レポートの「未検証事項」と「検証完了後に実施すべき TODO」で **Phase S-eval-8session 候補** が ★最重要 と明記されており、所要 40 分で以下の複数項目を同時に検証できる:

1. ub 別独立変動モデルの再確認（S8 での 3 ub の最近接モード分布）
2. ub=1664 spike 頻度の n=8 絞り込み（4/7 → 次 session で 4/8 or 5/8）
3. ub=1586 bouncing の周期性 vs ランダム反転の判別（S8 で再下落 or 継続）
4. ub=1584 崩壊頻度の n=8 絞り込み
5. warmup1 ub=1584 absolute 第 4 帯（15.418）の再現性
6. pooled 40-run σ_pool 安定性（bouncing 効果の継続確認）
7. Prior 7-session pool vs S8 の Welch t

以上より、本プランは **Phase S-eval-8session の実行** を目標とする。

## アプローチ

Phase S-eval-7session の構成を完全踏襲し、phaseSeval7s → phaseSeval8s にリネームのうえ、PRIOR_TSVS に S7 TSV を追加する。スクリプト構成変更なし。

### ディレクトリ構成

作業ディレクトリ: `report/attachment/2026-04-20_<HHMMSS>_qwen3-122b-c3-phaseSeval8s/`

- `start_phaseSeval8s.sh` — 7s をコピーし REMOTE_LOG prefix を `phaseSeval8s` に変更
- `batch_phaseSeval8s.sh` — 7s をコピーし TAG_PREFIX を `Seval8s_fa1_ctx...` に変更、startup log パス・run log パスの 7s → 8s 置換
- `run_all.sh` — 7s から無変更コピー
- `measure_phaseI.sh` — 7s から無変更コピー
- `prompts/prompt_1k.txt` — 7s から無変更コピー（計 1084 tokens、1k eval 統一）
- `analyze_phaseSeval8s.py` — 7s をコピー後、以下を修正:
  - `PRIOR_TSVS` に `("S7_phaseSeval7s", SCRIPT_DIR.parent / "2026-04-20_061007_qwen3-122b-c3-phaseSeval7s" / "summary_phaseSeval7s.tsv")` 追記
  - `CUR_SESSION_LABEL = "S8_phaseSeval8s"`
  - `TAG_PREFIX = "Seval8s_fa1_ctx"`
  - 出力ファイル名を `summary_phaseSeval8s.tsv` / `phaseSeval8s_stats.csv` / `phaseSeval8s_verdict.txt`
  - MODE_GROUPS に `"cur_S8": ["S8_phaseSeval8s"]` 追加、S7 を mode 分類セットに追加するかは 2 通り検討し、**S7 は「後見モード用」として独立セクション維持** にする（本レポートで解釈の軸を増やさない）
  - 7-session 用テーブル列を 8-session に拡張
- `startup_logs/` ディレクトリ作成

### 実行手順

```bash
# 1. GPU ロック取得（skill 経由）
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 2. 作業ディレクトリ準備（8s 版スクリプト配置）
cd report/attachment/2026-04-20_<HHMMSS>_qwen3-122b-c3-phaseSeval8s/

# 3. バッチ実行（3 条件 × (warmup 2 + eval 5)、約 37 分）
bash batch_phaseSeval8s.sh > batch_phaseSeval8s.log 2>&1

# 4. 集計（S1-S7 TSV + S8 合算）
python3 analyze_phaseSeval8s.py

# 5. llama-server 停止 + GPU ロック解放
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 測定条件（S1-S7 と完全同一）

- GPU サーバ: t120h-p100（10.1.4.14）
- llama.cpp binary: `~/llama.cpp/build/bin/llama-server`（前 session と同一）
- モデル: `Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf`
- 起動: fa=1、f16/f16 KV、ctx=32768、numactl cpunodebind=1 membind=1、threads=40、poll=0、ngl=999
- OT_REGEX: `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
- prompt: `prompts/prompt_1k.txt`（prompt_n=1084）+ `[Request ID <uniq>] ` prefix で cache 回避
- max_tokens=256、cooldown 60s、warmup 短 prompt 2 run
- 条件 3 件（ub=1584/1586/1664）× (warmup 2 + eval 5)

### 判定しきい値（前 Phase 踏襲）

- fully_independent: 8-session range ≤ 0.02 t/s
- partial_drift: range ≤ 0.10 t/s
- session_dominated: range > 0.10 t/s
- 崩壊判定: eval_mean < 15.0 t/s

## 重要ファイル一覧

### 編集対象（plan 外、Phase 本体で作成）

- `report/attachment/2026-04-20_<HHMMSS>_qwen3-122b-c3-phaseSeval8s/start_phaseSeval8s.sh`
- `report/attachment/2026-04-20_<HHMMSS>_qwen3-122b-c3-phaseSeval8s/batch_phaseSeval8s.sh`
- `report/attachment/2026-04-20_<HHMMSS>_qwen3-122b-c3-phaseSeval8s/analyze_phaseSeval8s.py`
- `report/attachment/2026-04-20_<HHMMSS>_qwen3-122b-c3-phaseSeval8s/run_all.sh`（7s からコピー）
- `report/attachment/2026-04-20_<HHMMSS>_qwen3-122b-c3-phaseSeval8s/measure_phaseI.sh`（7s からコピー）
- `report/attachment/2026-04-20_<HHMMSS>_qwen3-122b-c3-phaseSeval8s/prompts/prompt_1k.txt`（7s からコピー）
- `report/2026-04-20_<HHMMSS>_qwen3-122b-c3-phaseSeval8s.md`（本体レポート）
- `REPORT.md` 最新エントリ更新

### 再利用する既存スクリプト

- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh`
- `.claude/skills/llama-server/scripts/stop.sh`

### 参照元（PRIOR_TSVS）

- `report/attachment/2026-04-20_003250_qwen3-122b-c3-phaseSeval/summary_phaseSeval.tsv`（S1）
- `report/attachment/2026-04-20_013006_qwen3-122b-c3-phaseSevalcross/summary_phaseSevalcross.tsv`（S2）
- `report/attachment/2026-04-20_022922_qwen3-122b-c3-phaseSeval3s/summary_phaseSeval3s.tsv`（S3）
- `report/attachment/2026-04-20_032317_qwen3-122b-c3-phaseSeval4s/summary_phaseSeval4s.tsv`（S4）
- `report/attachment/2026-04-20_041308_qwen3-122b-c3-phaseSeval5s/summary_phaseSeval5s.tsv`（S5）
- `report/attachment/2026-04-20_050710_qwen3-122b-c3-phaseSeval6s/summary_phaseSeval6s.tsv`（S6）
- `report/attachment/2026-04-20_061007_qwen3-122b-c3-phaseSeval7s/summary_phaseSeval7s.tsv`（S7）

## 検証方法（end-to-end）

1. `bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100` で排他ロック取得が成功すること
2. `batch_phaseSeval8s.sh` 実行中に、3 条件すべてで `/health` 応答と PID 取得が成功すること
3. `run_all.sh` が warmup 2 + eval 5 の計 7 run 分 `eval_run{1..7}.json` を生成すること（全 JSON に `timings.predicted_per_second` が存在、`predicted_n == 256`）
4. `analyze_phaseSeval8s.py` が:
   - `summary_phaseSeval8s.tsv`（ub 別 raw、ヘッダ `ub / phase / run / eval_tps / prompt_tps / prompt_n / predicted_n`）
   - `phaseSeval8s_stats.csv`（ub 別 stat + 1-run ref verdict）
   - `phaseSeval8s_verdict.txt`（8 section 構造、section 2 で 8-session range / verdict、section 6 で pooled 40-run、section 10 で崩壊頻度 Wilson CI、section 11/11b/11c で ub 別 Δ パターン、section 13 で mode A/B/C/S7/S8 比較）
   を正常生成し、S1-S7 の TSV を全て読み込めていること
5. `phaseSeval8s_verdict.txt` の `peak order` 行が 8 行出力されていること（session_labels に S1-S8 が含まれる）
6. `bash .claude/skills/llama-server/scripts/stop.sh t120h-p100` で停止成功
7. `bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100` で解放成功
8. 本体レポートに「未検証事項」「検証完了後に実施すべき TODO」セクションを含めて `report/` に公開する

## 成果物（レポート）

- `report/2026-04-20_<HHMMSS>_qwen3-122b-c3-phaseSeval8s.md`
  - 冒頭に添付ファイル一覧（plan / start / batch / run_all / measure / analyze / log / TSV / CSV / verdict / startup_logs / out_Seval8s_* / prompts）
  - 前提・目的・再現方法・8-session 集計結果・採用判定・**未検証事項**・**検証完了後に実施すべき TODO**・補足
  - 前 Phase との対照表
- `REPORT.md` の直近フェーズ一覧に 1 行追加

## スコープ外（明示）

- プロンプト長（8k/32k）の変更は行わない（Phase S-eval-prompt の候補として別枠）
- ub 候補の拡張（1536/1792 等）は行わない（Phase S-eval-ub-wide 別枠）
- run 数 10 拡張は行わない（Phase S-eval-extended 別枠）
- 物理機構（thermal / DRAM / kernel cache）の計測は行わない（Phase S-eval-cold-boot 別枠）
