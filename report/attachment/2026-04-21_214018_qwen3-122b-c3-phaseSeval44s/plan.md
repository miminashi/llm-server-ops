# Phase S-eval-44session 実施計画

## Context

直前レポート [`2026-04-21_194635_qwen3-122b-c3-phaseSeval43s.md`](../../projects/llm-server-ops/report/2026-04-21_194635_qwen3-122b-c3-phaseSeval43s.md) の「未検証事項」および「検証完了後に実施すべき TODO」の最優先項目が **Phase S-eval-44session 候補** に集約されている。S43 で同時に確立された 15+ の新 regime について、n=44 に拡張して S44 時点の動向を確認する。

### S43 で確立され S44 で検証すべき最優先 regime（★最優先のみ抽出）

| # | 項目 | S44 検証内容 |
|---|------|-------------|
| 1 | mode_E 6 session ぶり復帰 (S37 以来) | S44 連続 (43-session 0 例 initial) or 他 mode shift |
| 2 | ub=1584 大幅崩壊 14.538 (崩壊 14 例目) | S44 崩壊継続 (2 連続 initial) or 15.0+ 帯復帰 |
| 3 | ub=1664 5 連続崩壊 initial | S44 6 連続 or break |
| 4 | Welch (-/+/-) 新 subtype | S44 連続 (0 例 initial) or shift |
| 5 | ub=1584 担当 \|t\|>25 到達 | S44 動向 (\|t\|>30 復帰候補) |
| 6 | σ_pool 1586 1 位 2 連続 | S44 3 連続 or 1664 奪還 |
| 7 | σ_pool 逆転幅 -0.010 縮小 | S44 連続縮小 or 拡大転換 |
| 8 | ub=1664 σ_pool 4 連続縮小 | S44 5 連続 (0 例 initial) 可否 |
| 9 | pool 差 +0.07 帯 initial | S44 +0.07 帯定着 or shift |
| 10 | mode_A 外 14 session 最長更新 | S44 15 連続外 or A 復帰 |
| 11 | ub=1584 \|Δ_max\| 担当 13 session ぶり復帰 | S44 連続 or 他 ub 奪還 |
| 12 | double collapse (1584/1664) 4 例目 | S44 5 例目 (interval 1 最短) or 単発 |

同時に中優先以下の以下も副次検証する: ub=1664 mixed-band 帯パターン、境界帯 18+ 分連続 3、ub=1586 peak 1 位 3 連続、3 ub Δ (-/-/-) 再現、hybrid 4 連続、\|Δ\|>0.5 3 session 内 4 連続、3 ub sig 51.2% 3 連続、prompt_tps 最高 ub 12 session rotation。

## 方針

S43 の計測・集計・プロット構成を 100% 流用し、ファイル名 `43s → 44s` 置換で新 session を追加する。測定条件は 43-session 連続一致しているため一切変更しない。

### 測定条件（S1..S43 完全共通）

- **GPU サーバ**: t120h-p100 (10.1.4.14)、P100-PCIE-16GB × 4
- **モデル**: `Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf`
- **起動パラメータ**: fa=1、f16/f16 KV、ctx=32768、`numactl --cpunodebind=1 --membind=1`、threads=40、poll=0、ngl=999、parallel=1、temp=0.6、top_p=0.95、top_k=20
- **OT_REGEX**: `blk\.([0-9]|1[0-3]|2[0-4]|3[1-9]|4[0-7])\.ffn_.*_exps\.weight=CPU`
- **ub 条件**: {1584, 1586, 1664}（-b = -ub 一致で起動）
- **計測**: 各 ub で warmup 2 run（短 prompt "Write a short haiku about autumn."）+ eval 5 run（`prompts/prompt_1k.txt`、[Request ID <uniq>] prefix、max_tokens=256）、run 間 cooldown 60 秒
- **prompt**: Sbfine3 流用、prompt_n=1086 tokens
- **所要時間**: 各 ub 約 12-13 分 × 3 ub = **37-40 分**

## 実装手順

### Step 1: 添付ディレクトリ作成と S43 スクリプト群の複製 + 文字列置換

```bash
TS="$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)"
TOPIC="qwen3-122b-c3-phaseSeval44s"
DEST="/home/ubuntu/projects/llm-server-ops/report/attachment/${TS}_${TOPIC}"
SRC="/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-21_194635_qwen3-122b-c3-phaseSeval43s"

mkdir -p "$DEST/startup_logs"
cp -r "$SRC/prompts" "$DEST/"

for f in start_phaseSeval43s.sh batch_phaseSeval43s.sh run_all.sh measure_phaseI.sh \
         analyze_phaseSeval43s.py plot_timeseries.py; do
  new="${f//43/44}"
  sed 's/43s/44s/g; s/43session/44session/g; s/phaseSeval43/phaseSeval44/g; s/Seval43s/Seval44s/g; s/S43/S44/g; s/S1..S43/S1..S44/g; s/n=43/n=44/g; s/215-run/220-run/g; s/prior 42-session/prior 43-session/g' \
    "$SRC/$f" > "$DEST/$new"
done
chmod +x "$DEST"/*.sh
```

**補正が必要な箇所**:
- `analyze_phaseSeval44s.py` に S43 の TSV pointer を追加（1 エントリのみ）
- `analyze_phaseSeval44s.py` 内の `PRIOR_TSVS` は S1-S43 を prior とするため、`summary_phaseSeval43s.tsv` を append
- `PRIOR_TSVS` リスト末尾と `WELCH PRIOR_N = 215` 等の定数調整（pooled は 220 = 44×5）
- 複製後の差分を目視確認（comment 内の session 数、range 記述など）

### Step 2: GPU ロック取得と実行

```bash
cd /home/ubuntu/projects/llm-server-ops
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100

cd "$DEST"
HOST=t120h-p100 bash batch_phaseSeval44s.sh > batch_phaseSeval44s.log 2>&1
python3 analyze_phaseSeval44s.py
python3 plot_timeseries.py

cd /home/ubuntu/projects/llm-server-ops
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

バッチは t120h-p100 で `llama-server` を ub ごとに起動 → /health 確認 → 5 run 計測 → stop、を 3 ub 繰り返す自己完結型。

### Step 3: レポート作成

`report/2026-04-DD_HHMMSS_qwen3-122b-c3-phaseSeval44session.md`（実施完了時刻を TS に採用）を [REPORT.md](../../projects/llm-server-ops/REPORT.md) のフォーマットで作成。ユーザ指示により以下 2 セクションを必ず含める:

- **未検証事項**: Phase M/Q/S/Sb/Sbfine/Sb-fa0-offload/S-eval 系の継続 TODO + 本 Phase S44 新規 TODO
- **検証完了後に実施すべき TODO**: CLAUDE.md / skill 訂正、Phase S-eval-45session、Phase S-eval-ub1664-X-collapse（X 連続）、Phase Sb-ctx-fine 等の将来候補

## 重要ファイル

- **複製元**: `report/attachment/2026-04-21_194635_qwen3-122b-c3-phaseSeval43s/` の以下 6 ファイル
  - `start_phaseSeval43s.sh` (起動、llama-server + OT_REGEX)
  - `batch_phaseSeval43s.sh` (3 ub ループ)
  - `run_all.sh` (1 条件内 warmup 2 + eval 5)
  - `measure_phaseI.sh` (1 run 計測、prompt 流入・TTFT・eval_tps 抽出)
  - `analyze_phaseSeval43s.py` (43-session 集計、Welch t、pooled、mode 分類)
  - `plot_timeseries.py` (matplotlib PNG)
- **GPU ロック**: `.claude/skills/gpu-server/scripts/{lock,unlock,lock-status}.sh t120h-p100`
- **llama-server stop**: `.claude/skills/llama-server/scripts/stop.sh`
- **前回 S43 レポート**: `report/2026-04-21_194635_qwen3-122b-c3-phaseSeval43s.md`
- **REPORT フォーマット**: `REPORT.md`

## 検証方法（end-to-end）

1. `bash .claude/skills/gpu-server/scripts/lock-status.sh t120h-p100` で `available` を確認してから lock
2. `batch_phaseSeval44s.log` の末尾に `[batchSeval44s] end at ...` が出力され、途中エラーがないこと
3. 3 ub 分の `out_Seval44s_fa1_ctx32768_ub{1584,1586,1664}_1k/*.json` が各 5 個生成
4. `phaseSeval44s_stats.csv` に 3 行（ub × n=5 mean/stdev）が出力
5. `phaseSeval44s_verdict.txt` に 44-session σ_session と判定（`fully_independent`/`partial_drift`/`session_dominated`）が出力
6. `timeseries_eval_tps.png` が S1..S44 + S0 Sbfine 参照点で更新
7. ロック解放確認後、レポート本文に S44 Δ vs S43、mode 分類、Welch t、pooled 220-run 統計、peak 1 位頻度を反映
8. cool time（S43 終了 2026-04-21 20:34:32 JST から S44 開始までの実測時刻差）を記載

## リスク・注意点

- **cool time が極めて短いと measurement clustering の懸念**: S38→S43 で 13 分未満ゾーン 0 例維持。最短でも ~13 分以上空けるのが自然
- **OT_REGEX エスケープ**: shell 経由のため `start_phaseSeval44s.sh` の `OT_REGEX='blk\.([0-9]|...)` シングルクォート保持必須
- **PRIOR_TSVS 末尾追加を忘れない**: analyze_phaseSeval44s.py で S43 エントリ追加しないと prior=42 のまま Welch が計算される
- **時系列プロット**: `plot_timeseries.py` 内の session 一覧にも S43 → S44 追加が必要
- **GPU ロック解放**: バッチ失敗時も必ず `unlock.sh` を実行（失敗時は ssh でプロセス残留チェック）
