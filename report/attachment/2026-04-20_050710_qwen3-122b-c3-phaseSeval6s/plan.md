# Phase S-eval-6session 実施プラン

## Context

直前レポート [2026-04-20_041308_qwen3-122b-c3-phaseSeval5s.md](../../projects/llm-server-ops/report/2026-04-20_041308_qwen3-122b-c3-phaseSeval5s.md)（Phase S-eval-5session）の「未検証事項」セクションの新規 ★最優先 項目のうち、単一 Phase で最大 4 項目を同時検証でき、所要時間 50 分・実施可能性が最も高い **Phase S-eval-6session** を実施する。

直前 Phase（S5）の主要発見と未解決問題:

- **ub=1586 が S5 で初めて session_dominated に転落**: range 0.070 → 0.187 (+167%)、pooled σ 0.030 → 0.068 (+127%)。偶発か継続ドリフトか未判明
- **ub=1664 bimodal/periodic 仮説棄却**: Δ パターン + + − +、「上昇 + 単発ダウンスパイク」型だが S5 で軽い後退（14.714）、長期傾向は未確定
- **ub=1584 崩壊頻度 1/5 = 20%**: Wilson 95% CI [3.6%, 62.5%] で推定幅広、もう 1 session で信頼区間を狭める必要
- **S1-S3 vs S4-S5 モード分離仮説**: ピーク順序（1584 → 1586）、warmup Δ（+0.31 → +0.16）、性能水準の 2 モード化。S6 で intra-day の時間帯依存性（~03:00 JST 境界）か別要因かの判別手がかりを得る

本 Phase の達成目標:

1. **ub=1586 の S6 挙動で転落原因を切り分ける**: S5 上振れが偶発なら S6 で 15.13-15.20 帯に戻る、継続ドリフトなら同等上振れを維持
2. **ub=1664 反転継続 vs 単独ダウンスパイクの判別**: S6 値が 14.593-14.714 帯なら反転継続、15.0 以上なら「S4 のみ単独ダウンスパイク」確定
3. **ub=1584 崩壊頻度 n=6 更新**: 崩壊セッションが 1/6 か 2/6 か、信頼区間更新
4. **S1-S3 / S4-S5 モード分離の S6 検証**: S6 で ub=1586 ピーク継続（モード B）か ub=1584 ピーク復帰（モード A）か
5. **pooled 30-run mean / σ**: 特に ub=1586 σ が n=25→30 でさらに拡大か収束に転じるか
6. **warmup1 ub=1584 absolute 帯のモード判定**: S6 で 14.78-15.37 帯（S4-S5）か 15.51-15.78 帯（S1-S3）か

採用候補の中で他案を採らない理由:

- **Phase S-eval-mode-split (2 時間)**: モード境界の物理機構切り分けは S6 でモード判定が先決
- **Phase S-eval-extended (n=10-20)**: 1 session で 10-20 run は 2-3 時間、ub=1584 崩壊頻度絞り込みに特化し他項目の情報得られず → 後続
- **Phase S-eval-cold-boot**: sudo reboot 必要、CLAUDE.md「Claude は sudo を直接実行しない」制約に該当 → 後続
- **Phase S-eval-ub-isolate**: ub=1584 単独 15-20 run で 40 分、観点が異なる → 別 Phase
- **Phase S-eval-nextday**: inter-day drift 分離のため翌日待ち → 後続

## 実施内容

### 1. 作業ディレクトリと既存資産の流用

直前 Phase S-eval-5session のスクリプトをコピーし `5s` → `6s` 置換と analyze の PRIOR_TSVS 拡張を行う。

**起点ファイル**（`report/attachment/2026-04-20_041308_qwen3-122b-c3-phaseSeval5s/`）:

- `start_phaseSeval5s.sh` → `start_phaseSeval6s.sh`
- `batch_phaseSeval5s.sh` → `batch_phaseSeval6s.sh`
- `run_all.sh`（変更不要）
- `measure_phaseI.sh`（変更不要）
- `analyze_phaseSeval5s.py` → `analyze_phaseSeval6s.py`
- `prompts/prompt_1k.txt`（変更不要）

### 2. ファイル別変更点

| ファイル | 変更内容 |
|---|---|
| `start_phaseSeval6s.sh` | `5s`→`6s` リネーム（REMOTE_LOG prefix `phaseSeval5s`→`phaseSeval6s` 含む） |
| `batch_phaseSeval6s.sh` | `5s`→`6s` リネーム（startup_logs / out_Seval5s_*→out_Seval6s_* prefix 含む） |
| `run_all.sh` | 変更なし（コピーのみ） |
| `measure_phaseI.sh` | 変更なし（コピーのみ） |
| `analyze_phaseSeval6s.py` | (a) `PRIOR_TSVS` に S5 の `summary_phaseSeval5s.tsv` を追加（5 prior + 1 cur = 6 session）、(b) `CUR_SESSION_LABEL = "S6_phaseSeval6s"`、(c) `TAG_PREFIX = "Seval6s_fa1_ctx"`、(d) 出力ファイル名 `5s`→`6s` 置換、(e) コメント・ヘッダー 5-session→6-session 表記、(f) Pooled n=25→n=30 の数値表現、(g) **新規出力**: モード分類（S1-S3 / S4-S5 / S6 別 mean 比較）、ub=1584 崩壊頻度 n=6 更新（Wilson CI 再計算）、ub=1664 時系列 Δ パターン更新、ピーク順序 6-session 集計 |
| `prompts/prompt_1k.txt` | 変更なし（コピーのみ） |

### 3. 実行手順

```bash
# (a) GPU ロック取得（skill 必須）
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100

# (b) 作業ディレクトリ作成
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
REPORT_BASENAME="${TS}_qwen3-122b-c3-phaseSeval6s"
ATT_DIR="report/attachment/${REPORT_BASENAME}"
mkdir -p "${ATT_DIR}/startup_logs" "${ATT_DIR}/prompts"

# (c) 既存資産コピー＋5s→6s 置換
SRC=report/attachment/2026-04-20_041308_qwen3-122b-c3-phaseSeval5s
cp "${SRC}"/{start_phaseSeval5s.sh,batch_phaseSeval5s.sh,run_all.sh,measure_phaseI.sh,analyze_phaseSeval5s.py} "${ATT_DIR}/"
cp "${SRC}/prompts/prompt_1k.txt" "${ATT_DIR}/prompts/"
# Edit で 5s→6s 置換、PRIOR_TSVS に S5 追加

# (d) plan ファイルを attachment にコピー
cp /home/ubuntu/.claude/plans/todo-pure-swan.md "${ATT_DIR}/plan.md"

# (e) バッチ実行（warmup 2 + eval 5、3 条件、所要約 38 分）
cd "${ATT_DIR}"
bash batch_phaseSeval6s.sh > batch_phaseSeval6s.log 2>&1

# (f) 分析（6-session 統計を生成）
python3 analyze_phaseSeval6s.py

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

- **fully_independent**: 6-session range (max−min) ≤ 0.02 t/s
- **partial_drift**: range ≤ 0.10 t/s
- **session_dominated**: range > 0.10 t/s
- **ub=1584 崩壊判定**: eval_mean < 15.0 t/s

### 6. 新規検証（本 Phase 固有）

- **モード分類**: S1-S3（mode A）/ S4-S5（mode B）/ S6 の 3 群で ub 別 mean、warmup1 absolute を算出、S6 がどちらに近いか判定
- **Welch t (prior 5-session pool vs S6)**: ub 別に significant/not_sig
- **ピーク順序 6-session 集計**: 1 位頻度比（ub=1584 / 1586 / 1664）
- **ub=1584 崩壊頻度 Wilson CI 更新**: k/6 の 95% 区間
- **ub=1664 時系列 Δ パターン**: 単調収束 / 単独ダウンスパイク / 新規 bimodal の判定

### 7. 成功条件

- [ ] 3 条件すべて起動成功
- [ ] 各条件 eval 5 run の eval_tps 取得
- [ ] 6-session range / σ_session の算出（n=6）
- [ ] Welch t (prior 5-session pool vs S6) で有意差判定
- [ ] ピーク ub 順序の 6-session 安定性確認
- [ ] pooled 30-run 統計の算出
- [ ] ub=1584 崩壊頻度 n=6 更新（Wilson 95% CI）
- [ ] ub=1664 時系列 Δ パターン更新（単調収束 / 単独ダウンスパイク / 新規 bimodal 判定）
- [ ] モード分類（S1-S3 / S4-S5 / S6）の ub 別 mean 比較
- [ ] GPU ロック取得・解放の正常動作

## 参照する既存資産（流用元）

| 資産 | パス | 役割 |
|---|---|---|
| start.sh | `attachment/2026-04-20_041308_qwen3-122b-c3-phaseSeval5s/start_phaseSeval5s.sh` | llama-server 起動（fa=1, ctx=32k, ub=可変） |
| batch.sh | 同上 `batch_phaseSeval5s.sh` | 3 条件のループ駆動 |
| run_all.sh | 同上 | warmup 2 + eval 5 を 1 条件分実行 |
| measure_phaseI.sh | 同上 | 1 run の eval 計測（completions API → JSON 保存） |
| analyze.py | 同上 `analyze_phaseSeval5s.py` | 5-session 統計の起点（PRIOR_TSVS 拡張で 6-session 化） |
| prompt_1k.txt | 同上 `prompts/prompt_1k.txt` | 6 session 通じて固定（再現性のため不変） |
| lock/unlock | `.claude/skills/gpu-server/scripts/{lock,unlock}.sh` | GPU 排他制御（必須） |
| stop | `.claude/skills/llama-server/scripts/stop.sh` | 各条件間でのサーバ停止 |

## レポート作成

実施完了後、`report/${TS}_qwen3-122b-c3-phaseSeval6s.md` として作成:

- 直前レポート (Phase S-eval-5session) へのリンク
- S1-S6 の系列を含む 6-session mean 時系列、range、σ_session
- pooled 30-run 統計（ub 別）
- ピーク順序 6-session 比較（1 位頻度比の確定度向上）
- ub=1584 崩壊頻度カウント n=6、Wilson 95% CI 更新
- ub=1664 時系列 Δ パターン（単調収束 / 単独ダウンスパイク 判定）
- モード分類（S1-S3 / S4-S5 / S6）の ub 別 mean 比較
- Welch t (prior S1-S5 pool vs S6)
- warmup1 ub=1584 absolute 帯のモード判定
- 「**未検証事項**」セクション（前 Phase 引継ぎ、本 Phase で潰した項目を [x] でマーク、新規発生項目を追加）
- 「**検証完了後に実施すべき TODO**」セクション
- 添付ファイル: plan.md、各種スクリプト、ログ、TSV、CSV、verdict.txt、startup_logs/

## 検証方法（end-to-end）

1. `batch_phaseSeval6s.log` の末尾に `[batchSeval6s] end at ...` が記録されている
2. `summary_phaseSeval6s.tsv` に 3 ub × (warmup 2 + eval 5) = 21 行のデータが揃う
3. `phaseSeval6s_verdict.txt` の各 verdict セクションに 6 session 分のラベルが現れる
4. `phaseSeval6s_stats.csv` で eval phase の各 ub stdev が ≤ 0.02 t/s（プロトコル健全性確認）
5. compute buffer が startup_logs 3 ファイルすべてで MiB 単位 5-session と一致（物理構成の連続性確認）
6. analyze 出力にモード分類表、ub=1584 崩壊頻度 Wilson CI、ub=1664 Δ パターン文字列が記載される

## リスクと注意点

- 直前 S5 (04:55 終了) から本 Phase 開始までの cool time が次の比較軸。過去最短 S4-S5 間隔 11 分では崩壊回避、長間隔（S5-S6 で数時間以上）での挙動は新知見になり得る（レポートに実際の cool time を明記）
- 失敗時は GPU ロック解放を必ず実施
- llama-server 起動失敗（OOM 等）時は `start_phaseSeval6s.sh` のエラー検出ロジックで即時 exit
- Discord 通知は本 Phase のスコープ外（skill 必要ならユーザ明示時のみ）
- sudo 操作は本 Phase で一切発生しない（reboot なし・drop_caches なし）
