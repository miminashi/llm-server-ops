# Phase S-eval-45session 実施計画

## Context

直前レポート [`2026-04-21_214018_qwen3-122b-c3-phaseSeval44s.md`](../../projects/llm-server-ops/report/2026-04-21_214018_qwen3-122b-c3-phaseSeval44s.md) の「未検証事項」「検証完了後に実施すべき TODO」で **★最優先・★高優先** のほぼ全項目が **Phase S-eval-45session 候補** に集約されている。S44 で initial/延長/break された 20+ の regime を n=45 に拡張して一括同時検証する。ユーザ指示「優先度が高いものを実施」に該当。

### S44 で確立・継続し S45 で検証すべき最優先 regime（★最優先のみ抽出）

| # | 項目 | S45 検証内容 |
|---|------|-------------|
| 1 | ub=1664 6 連続崩壊 initial 44-session 初 (S39-S44 全 COLLAPSE) | S45 7 連続 or break |
| 2 | ub=1664 下帯 2 連続 (14.714/14.497) | S45 3 連続 or 離脱 |
| 3 | ub=1584 大幅回復 15.304 (Δ=+0.766) 崩壊 1 session 限定 fix | S45 定着 or 再崩壊 |
| 4 | Welch (+/+/-) 新 subtype、15-subtype 15-session 連続 | S45 連続 or shift |
| 5 | \|t\|=-21.71 ub=1664 担当（1 session interval 復帰） | S45 \|t\|>25 候補 |
| 6 | σ_pool 1664 1 位奪還 initial 1 session interval | S45 2 連続 or 1586 奪還 |
| 7 | σ_pool 逆転幅 +0.024 微拡大（縮小→拡大転換） | S45 連続拡大 or 縮小 |
| 8 | pool 差 +0.077 で +0.07 帯定着 2 連続 initial | S45 3 連続 or shift、+0.08 帯候補 |
| 9 | mode_A 外 15 session 最長新記録 (S29 以来) | S45 16 連続外 or A 復帰 |
| 10 | ub=1584 \|Δ_max\| 担当 2 連続 initial (S43 -0.607 + S44 +0.766) | S45 3 連続 or 他 ub 奪還 |
| 11 | ub=1586 peak 1 位 50.0% 到達 initial (22/44) | S45 51% 超 or 後退 |
| 12 | \|Δ\|>0.5 4 連続 initial (S41-S44) | S45 5 連続 or 減速 |
| 13 | mode_B 1 session interval 復帰 (14/44=31.8% 1 位維持) | S45 連続 or shift |
| 14 | 3 ub sig 52.3% 3 連続過半 initial | S45 4 連続 or 減少 |
| 15 | 境界帯 18+ 分連続 3 initial (18'57"/19'19"/18'49") | S45 4 連続 or 離脱 |
| 16 | warmup hybrid 4 連続 + out_of_prior_bands_upper 新帯 | S45 pure 復帰 or hybrid 5 連続 |
| 17 | 1 session 内 Welch diff sign-flip 4 連続 | S45 5 連続 pattern |
| 18 | prompt_tps 最高 ub 12 session rotation 新記録 | S45 13 連続 rotation or 固定化 |
| 19 | 3 ub pool range 維持 3 連続 (1.516/1.692/1.321) | S45 4 連続 or 更新 |
| 20 | ub=1586 pool max 15.532 維持 2 連続 / ub=1664 pool max 15.534 維持 6 連続 | S45 維持 or 更新 |

## 方針

S44 の計測・集計・プロット構成を 100% 流用し、ファイル名・スクリプト内識別子 `44s → 45s` / `S44 → S45` 等を置換。測定条件は S1-S44 完全一致のため一切変更しない。

### 測定条件（S1..S44 完全共通）

- **GPU サーバ**: t120h-p100 (10.1.4.14)、P100-PCIE-16GB × 4
- **モデル**: `Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf`
- **起動パラメータ**: fa=1、f16/f16 KV、ctx=32768、`numactl --cpunodebind=1 --membind=1`、threads=40、poll=0、ngl=999、parallel=1、temp=0.6、top_p=0.95、top_k=20
- **OT_REGEX**: `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
- **ub 条件**: {1584, 1586, 1664}（-b = -ub 一致で起動）
- **計測**: 各 ub で warmup 2 run（"Write a short haiku about autumn."）+ eval 5 run（`prompts/prompt_1k.txt`、`[Request ID <uniq>]` prefix、max_tokens=256）、run 間 cooldown 60 秒
- **prompt**: Sbfine3 流用、prompt_n=1086 tokens、6200 bytes
- **所要時間**: 各 ub 約 12-13 分 × 3 ub = **37-40 分**

## 実装手順

### Step 1: 添付ディレクトリ作成と S44 スクリプト群の複製 + 文字列置換

```bash
TS="$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)"
TOPIC="qwen3-122b-c3-phaseSeval45s"
DEST="/home/ubuntu/projects/llm-server-ops/report/attachment/${TS}_${TOPIC}"
SRC="/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-21_214018_qwen3-122b-c3-phaseSeval44s"

mkdir -p "$DEST/startup_logs"
cp -r "$SRC/prompts" "$DEST/"

for f in start_phaseSeval44s.sh batch_phaseSeval44s.sh run_all.sh measure_phaseI.sh \
         analyze_phaseSeval44s.py plot_timeseries.py; do
  new="${f//44/45}"
  sed 's/44s/45s/g; s/44session/45session/g; s/phaseSeval44/phaseSeval45/g; s/Seval44s/Seval45s/g; s/S1..S44/S1..S45/g; s/n=44/n=45/g; s/220-run/225-run/g; s/prior 43-session/prior 44-session/g; s/PRIOR_N = 215/PRIOR_N = 220/g' \
    "$SRC/$f" > "$DEST/$new"
done
chmod +x "$DEST"/*.sh
```

**補正が必要な箇所** (手動 Edit):
- `analyze_phaseSeval45s.py`: `PRIOR_TSVS` 末尾に `S44_phaseSeval44s` エントリ追加（パスは `SCRIPT_DIR.parent / "2026-04-21_214018_qwen3-122b-c3-phaseSeval44s" / "summary_phaseSeval44s.tsv"`）
- `plot_timeseries.py`: `SESSIONS`（または同等の session 一覧定数）に S44 を append
- sed で置換しきれなかった残存「44」を grep で検索し手動修正

### Step 2: GPU ロック取得と実行

```bash
cd /home/ubuntu/projects/llm-server-ops
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100

cd "$DEST"
HOST=t120h-p100 bash batch_phaseSeval45s.sh > batch_phaseSeval45s.log 2>&1
python3 analyze_phaseSeval45s.py
python3 plot_timeseries.py

cd /home/ubuntu/projects/llm-server-ops
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

バッチは t120h-p100 で `llama-server` を ub ごとに起動 → `/health` 確認 → 5 run 計測 → stop、を 3 ub 繰り返す自己完結型。

### Step 3: レポート作成

`report/2026-04-DD_HHMMSS_qwen3-122b-c3-phaseSeval45session.md`（バッチ完了時刻を TS に採用）を [REPORT.md](../../projects/llm-server-ops/REPORT.md) のフォーマットで作成。ユーザ指示により以下 2 セクションを必ず含める:

- **未検証事項**: Phase M/Q/S/Sb/Sbfine/Sb-fa0-offload/S-eval 系の継続 TODO + 本 Phase S45 新規 TODO
- **検証完了後に実施すべき TODO**: CLAUDE.md / skill 訂正、Phase S-eval-46session、Phase S-eval-ub1664-7collapse (or break)、Phase Sb-ctx-fine 等の将来候補

各 S45 測定値 (ub=1584/1586/1664 の 5-run mean) を S44 との Δ、pooled 225-run 統計、Welch t（prior 44-session pool vs S45）、peak 1 位頻度、mode 分類、崩壊頻度 CI、cool time sub-zone、σ_pool 順序、warmup1 hybrid 判定で論じる。時系列プロット PNG を S1..S45 + Sbfine ref に更新し添付。

## 重要ファイル

- **複製元**: `report/attachment/2026-04-21_214018_qwen3-122b-c3-phaseSeval44s/` の以下 6 ファイル
  - `start_phaseSeval44s.sh` (llama-server 起動 + OT_REGEX)
  - `batch_phaseSeval44s.sh` (3 ub ループ)
  - `run_all.sh` (1 条件内 warmup 2 + eval 5)
  - `measure_phaseI.sh` (1 run 計測、prompt 流入・TTFT・eval_tps 抽出)
  - `analyze_phaseSeval44s.py` (44-session 集計、Welch t、pooled、mode 分類)
  - `plot_timeseries.py` (matplotlib PNG)
- **GPU ロック**: `.claude/skills/gpu-server/scripts/{lock,unlock,lock-status}.sh t120h-p100`
- **llama-server stop**: `.claude/skills/llama-server/scripts/stop.sh`
- **前回 S44 レポート**: `report/2026-04-21_214018_qwen3-122b-c3-phaseSeval44s.md`
- **REPORT フォーマット**: `REPORT.md`

## 検証方法（end-to-end）

1. `bash .claude/skills/gpu-server/scripts/lock-status.sh t120h-p100` で `available` を確認（確認済: 2026-04-21 時点 available）してから lock
2. `batch_phaseSeval45s.log` の末尾に `[batchSeval45s] end at ...` が出力され、途中エラーがないこと
3. 3 ub 分の `out_Seval45s_fa1_ctx32768_ub{1584,1586,1664}_{warmup,1k}/*.json` が各 warmup 2 + eval 5 個生成
4. `phaseSeval45s_stats.csv` に 3 行（ub × n=5 mean/stdev）が出力
5. `phaseSeval45s_verdict.txt` に 45-session σ_session と判定（`fully_independent`/`partial_drift`/`session_dominated`）が出力
6. `timeseries_eval_tps.png` が S1..S45 + S0 Sbfine 参照点で更新
7. ロック解放確認後、レポート本文に S45 Δ vs S44、mode 分類、Welch t（prior 44-session = 220 run pool vs S45 = 5 run）、pooled 225-run 統計、peak 1 位頻度、崩壊頻度、cool time sub-zone を反映
8. cool time（S44 終了 2026-04-21 21:37:54 JST から S45 開始までの実測時刻差）を記載

## リスク・注意点

- **cool time が極めて短いと measurement clustering の懸念**: S38-S44 で 13 分未満ゾーン 0 例維持。最短でも ~13 分以上空けるのが自然。境界帯 18+ 分連続 3 を破るか延ばすかは事後観察
- **OT_REGEX エスケープ**: shell 経由のため `start_phaseSeval45s.sh` の `OT_REGEX='blk\.([0-9]|...)` シングルクォート保持必須
- **PRIOR_TSVS 末尾追加を忘れない**: `analyze_phaseSeval45s.py` で S44 エントリ追加しないと prior=43 のまま Welch が計算される
- **PRIOR_N 定数**: sed で `215 → 220` 置換が通らない場合（異なる文脈で 215 が出現する可能性）は手動 Edit
- **時系列プロット**: `plot_timeseries.py` 内の session 一覧配列にも S44 追加が必要（grep で確認）
- **GPU ロック解放**: バッチ失敗時も必ず `unlock.sh` を実行（失敗時は `ssh t120h-p100 "ps aux | grep llama-server"` でプロセス残留チェック、`stop.sh` で明示停止）
- **ディスク**: 6 out ディレクトリ + ログで数 MB 程度、影響なし
