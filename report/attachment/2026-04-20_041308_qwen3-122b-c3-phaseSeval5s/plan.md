# Phase S-eval-5session 実施プラン

## Context

直前レポート [2026-04-20_032317_qwen3-122b-c3-phaseSeval4s.md](../../../projects/llm-server-ops/report/2026-04-20_032317_qwen3-122b-c3-phaseSeval4s.md)（Phase S-eval-4session）の「未検証事項」セクションで、最優先（★最優先）として残置されている事項のうち、所要時間 50 分・実施可能性が最も高い **Phase S-eval-5session** を実施する。

直前 Phase の主要発見と未解決問題:
- **ub=1584 が S4 で −0.728 t/s 大崩壊**、4-session range 0.839（5.5%）。「崩壊 session」の頻度未定量
- **ub=1664 単調増加仮説が S4 で破綻**（14.646→15.042→15.135→14.593 と S1 以下まで戻る）、bimodal/periodic の可能性
- **ub=1586 のみ 4 session で partial_drift 維持**（range 0.070, σ_session 0.033）。最ロバストの物理メカニズム未確定
- **S4 全 ub が prior pool 対比 significant 下振れ**（thermal / DRAM / 他プロセス候補、切り分け未済）
- **pooled mean 未収束**（ub=1584 が n=15→20 で −0.178 動いた）

本 Phase の達成目標:
1. **n=5 で σ_session の収束性確認**（特に ub=1586 partial_drift がさらに維持されるか）
2. **ub=1584 大崩壊頻度の定量化**（5 session 中で何回崩壊するか）
3. **ub=1664 bimodal/periodic 仮説の検証**（S5 が S4 に近い/遠い、周期性の手がかり）
4. **ピーク順序の S5 安定性**（S4 の ub=1586 ピークが偶発か傾向か）
5. **pooled 25-run mean / σ への更新**（特に ub=1584 / ub=1664）
6. **S4 共通下振れの再現性**（S5 も同様に低速 group か、S5 で正常域に戻るか）

採用候補の中で他案を採らない理由:
- **Phase S-eval-cold-boot**: sudo reboot 必要、CLAUDE.md「Claude は sudo を直接実行しない」制約に該当 → 後続
- **Phase S-eval-trend (5-6 session 連続)**: 所要 5 時間で長すぎる → 本 Phase をその第 1 段階として扱える
- **Phase S-eval-ub-isolate**: ub=1584 単独 15-20 run で 40 分、観点が異なるため別 Phase
- **Phase S-eval-nextday**: 翌日待ち、日跨ぎ時刻で実施 → 後続

## 実施内容

### 1. 作業ディレクトリ作成と既存資産の流用

直前 Phase S-eval-4session のスクリプトをコピーし、`4s` → `5s` の文字列置換と analyze スクリプトでの prior session 拡張を行う。

**起点ファイル**:
- `report/attachment/2026-04-20_032317_qwen3-122b-c3-phaseSeval4s/start_phaseSeval4s.sh`
- `report/attachment/2026-04-20_032317_qwen3-122b-c3-phaseSeval4s/batch_phaseSeval4s.sh`
- `report/attachment/2026-04-20_032317_qwen3-122b-c3-phaseSeval4s/run_all.sh`（変更不要）
- `report/attachment/2026-04-20_032317_qwen3-122b-c3-phaseSeval4s/measure_phaseI.sh`（変更不要）
- `report/attachment/2026-04-20_032317_qwen3-122b-c3-phaseSeval4s/analyze_phaseSeval4s.py`
- `report/attachment/2026-04-20_032317_qwen3-122b-c3-phaseSeval4s/prompts/prompt_1k.txt`

### 2. ファイル別変更点

| ファイル | 変更内容 |
|---|---|
| `start_phaseSeval5s.sh` | 4s→5s リネームのみ（REMOTE_LOG prefix 含む） |
| `batch_phaseSeval5s.sh` | 4s→5s リネームのみ（startup_logs / out_ ディレクトリ prefix 含む） |
| `run_all.sh` | 変更なし（コピーのみ） |
| `measure_phaseI.sh` | 変更なし（コピーのみ） |
| `analyze_phaseSeval5s.py` | (a) `PRIOR_TSVS` に S4 の `summary_phaseSeval4s.tsv` を追加（4 prior + 1 cur = 5 session）、(b) `CUR_SESSION_LABEL = "S5_phaseSeval5s"`、(c) `TAG_PREFIX = "Seval5s_fa1_ctx"`、(d) 出力ファイル名・テーブルラベル `4s`→`5s` 置換、(e) コメント・ヘッダーの 4-session→5-session 表記、(f) Pooled n=20→n=25 の数値表現 |
| `prompts/prompt_1k.txt` | 変更なし（コピーのみ） |

### 3. 実行手順

```bash
# (a) GPU ロック取得（skill 必須）
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100

# (b) 作業ディレクトリ作成
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_BASENAME="${TS}_qwen3-122b-c3-phaseSeval5s"
ATT_DIR="report/attachment/${REPORT_BASENAME}"
mkdir -p "${ATT_DIR}/startup_logs" "${ATT_DIR}/prompts"

# (c) 既存資産コピー＋4s→5s 置換
cp report/attachment/2026-04-20_032317_qwen3-122b-c3-phaseSeval4s/{start_phaseSeval4s.sh,batch_phaseSeval4s.sh,run_all.sh,measure_phaseI.sh,analyze_phaseSeval4s.py} "${ATT_DIR}/"
cp report/attachment/2026-04-20_032317_qwen3-122b-c3-phaseSeval4s/prompts/prompt_1k.txt "${ATT_DIR}/prompts/"
# Edit ツールで 4s→5s に置換し、analyze の PRIOR_TSVS に S4 を追加

# (d) plan ファイルを attachment にコピー
cp /home/ubuntu/.claude/plans/todo-parallel-frost.md "${ATT_DIR}/plan.md"

# (e) バッチ実行（warmup 2 + eval 5、3 条件、所要約 37 分）
cd "${ATT_DIR}"
bash batch_phaseSeval5s.sh > batch_phaseSeval5s.log 2>&1

# (f) 分析（5-session 統計を生成）
python3 analyze_phaseSeval5s.py

# (g) 停止・解放
bash ../../../.claude/skills/llama-server/scripts/stop.sh t120h-p100
bash ../../../.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 4. 環境情報（前 Phase と完全同一を維持）

- **GPU サーバ**: t120h-p100 (10.1.4.14)、NVIDIA Tesla P100-PCIE-16GB × 4 (CC 6.0)
- **モデル**: `Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf`
- **起動パラメータ**: fa=1、f16/f16 KV、ctx=32768、`numactl --cpunodebind=1 --membind=1`、threads=40、poll=0、ngl=999
- **OT_REGEX**: `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
- **prompt**: Phase Sbfine3 `prompts/prompt_1k.txt` 流用（prompt_n=1084 tokens）
- **予測長**: max_tokens=256
- **cooldown**: run 間 60 秒
- **warmup**: 短 prompt 2 run、続いて eval 5 run（1 条件あたり 7 run）

### 5. 判定しきい値（前 Phase と同一）

- **fully_independent**: 5-session range (max−min) ≤ 0.02 t/s
- **partial_drift**: range ≤ 0.10 t/s
- **session_dominated**: range > 0.10 t/s

### 6. 成功条件

- [ ] 3 条件すべて起動成功
- [ ] 各条件 eval 5 run の eval_tps 取得
- [ ] 5-session range / σ_session の算出（n=5）
- [ ] Welch t (prior 4-session pool vs S5) で有意差判定
- [ ] ピーク ub 順序の 5 session 安定性確認
- [ ] pooled 25-run 統計の算出
- [ ] **ub=1584 崩壊頻度カウント**: S1-S5 で eval_mean < 15.0 となった session 数を verdict に記載
- [ ] **ub=1664 周期性検定**: S1-S5 を時系列順に並べたとき bimodal / periodic の手がかりが verdict に出ているか
- [ ] GPU ロック取得・解放の正常動作

## 参照する既存資産（流用元）

| 資産 | パス | 役割 |
|---|---|---|
| start.sh | `attachment/2026-04-20_032317_qwen3-122b-c3-phaseSeval4s/start_phaseSeval4s.sh` | llama-server 起動（fa=1, ctx=32k, ub=可変） |
| batch.sh | 同上 `batch_phaseSeval4s.sh` | 3 条件のループ駆動 |
| run_all.sh | 同上 | warmup 2 + eval 5 を 1 条件分実行 |
| measure_phaseI.sh | 同上 | 1 run の eval 計測（completions API → JSON 保存） |
| analyze.py | 同上 `analyze_phaseSeval4s.py` | 5-session 統計の起点（PRIOR_TSVS 追加で N-session 拡張可能） |
| prompt_1k.txt | 同上 `prompts/prompt_1k.txt` | 4 session 通じて固定（再現性のため不変） |
| lock/unlock | `.claude/skills/gpu-server/scripts/{lock,unlock}.sh` | GPU 排他制御（必須） |
| stop | `.claude/skills/llama-server/scripts/stop.sh` | 各条件間でのサーバ停止 |

## レポート作成

実施完了後、以下を記載したレポートを `report/${TS}_qwen3-122b-c3-phaseSeval5s.md` として作成する:

- 直前レポート (Phase S-eval-4session) へのリンク
- S1-S5 の系列を含む 5-session mean 時系列、range、σ_session
- pooled 25-run 統計（ub 別）
- ピーク順序 5 session 比較
- ub=1584 崩壊頻度カウント、ub=1664 時系列パターン分析
- Welch t (prior S1-S4 pool vs S5)
- 「**未検証事項**」セクション（前 Phase の未検証事項を引き継ぎつつ本 Phase で潰した項目を [x] でマーク）
- 「**検証完了後に実施すべき TODO**」セクション
- 添付ファイル: plan.md、各種スクリプト、ログ、TSV、CSV、verdict.txt、startup_logs/

## 検証方法（end-to-end）

1. `batch_phaseSeval5s.log` の末尾に `[batchSeval5s] end at ...` が記録されている
2. `summary_phaseSeval5s.tsv` に 3 ub × (warmup 2 + eval 5) = 21 行のデータが揃う
3. `phaseSeval5s_verdict.txt` の各 verdict セクションに 5 session 分のラベルが現れる
4. `phaseSeval5s_stats.csv` で eval phase の各 ub stdev が ≤ 0.02 t/s（プロトコル健全性確認）
5. compute buffer が startup_logs 3 ファイルすべてで MiB 単位 4-session と一致（物理構成の連続性確認）

## リスクと注意点

- 直前の S4 (04:02 終了) から本 Phase 開始まで時間を空ける必要あり（cool time の影響）。S3-S4 間隔 14 分 / S2-S3 間隔 18 分などの過去差を考慮、本 Phase は計画開始時点で 16 時間以上空いており intra-day 連続性は弱まる点に留意（レポートに明記）
- 失敗時は GPU ロック解放を必ず実施（trap や明示 unlock）
- llama-server 起動失敗（OOM 等）時は `start_phaseSeval5s.sh` のエラー検出ロジックで即時 exit する仕組みを流用
