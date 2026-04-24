# Phase T-2: split-mode row vs layer 比較

## Context

Phase T-1 (KV cache 量子化スイープ) で以下が確定した:

- Phase D ピーク **15.03 t/s** / Phase S ピーク **15.39 t/s** を超える KV 型 × ub 組合せは存在せず。
- 最良: **KV=q8_0, ub=1586, eval_mean = 15.016 t/s** (Phase D -0.1%)。
- KV 量子化は eval 改善手段として頭打ち。

一方、Phase T-1 の buffer 観察で **CUDA3 compute buffer = 1558-1634 MiB (他 GPU の 3.4x)** という非対称な偏在が定量化された。これは現行 `--split-mode layer` (default) の layer 割当による可能性があり、`--split-mode row` に切替えれば:

1. **compute buffer 均等化** → 空いた VRAM を ub/ctx 拡大に使える余地
2. **layer 間 kernel launch overhead 削減** (row split は全 GPU で同時計算)
3. Phase S ピーク 15.39 超えへの**最も直接的な経路**

さらに同一 session 内で KV ∈ {f16, q8_0} × split-mode ∈ {layer, row} の 2×2 を組むことで、Phase T-1 の副次発見「**q8_0 KV が f16 より eval +4.1% 高速**」の独立再現検証も兼ねる (Phase T-1 の f16 baseline 14.425 は S54 15.173 に対し -4.9% 下振れで、session 変動との切り分けが未決着)。

Phase T シリーズは「パラメータチューニングで eval/prompt t/s 改善余地を探る」位置付けであり、Phase T-2 は CUDA3 偏在という**既存の構造的非効率を直撃する**最も情報量が大きい候補。再ビルド不要・runtime flag のみで実施でき、失敗してもコスト低。

## 比較ベースライン

| 参照 | 条件 | eval_mean |
|------|------|-----------|
| Phase D | numactl -N1 -m1, threads=40 | **15.03 t/s** |
| Phase S | ctx=65k, ub=512 | **15.39 t/s** |
| Phase T-1 最良 (q8_0 ub=1586) | split-mode=layer (default) | **15.016 t/s** |
| Phase T-1 f16 (ub=1586) | split-mode=layer (default) | 14.425 t/s |

**Phase T-2 判定閾値**:
- Phase T-1 q8_0 超え: eval_mean > 15.016 t/s
- Phase D 超え: eval_mean > 15.03 t/s
- Phase S 超え: eval_mean > 15.39 t/s
- split-mode row が改善: 同一 KV 型で row > layer (+3% 以上)

## スイープ設計

4 条件 (KV × split-mode の 2×2)、ub=1586 / ctx=32768 固定:

| # | KV 型 | split-mode | 備考 |
|---|-------|-----------|------|
| 1 | f16   | layer | Phase T-1 baseline 再取得 |
| 2 | f16   | row   | split-mode 効果 (f16) |
| 3 | q8_0  | layer | Phase T-1 最良 再現 |
| 4 | q8_0  | row   | 本命 (compute buffer 均等化 × KV 帯域削減) |

- 各条件 warmup 2 run + 1k prompt eval 5 run
- 実行順序: row 系を先にして OT 非対応などで失敗した場合の fail-soft を早期検知
- 測定所要: 4 条件 × (起動 3 分 + 7 run × 60 秒) ≈ 40-60 分

## 実施手順

### 1. 添付ディレクトリ作成

報告ディレクトリ: `report/attachment/{YYYY-MM-DD_HHMMSS}_qwen3-122b-c3-phaseT2-splitmode/`

Phase T-1 ディレクトリから以下をコピーし名前を T2 に置換:

- `start_phaseT1.sh` → `start_phaseT2.sh`
- `batch_phaseT1.sh` → `batch_phaseT2.sh`
- `analyze_phaseT1.py` → `analyze_phaseT2.py`
- `run_all.sh`, `measure_phaseT1.sh` → そのまま複製 (または `measure_phaseT2.sh` に rename)
- `prompts/` ディレクトリごと複製 (1k prompt 再利用)

### 2. `start_phaseT2.sh` の修正点 (T-1 からの差分)

- L10-13 付近に `SPLIT_MODE="${SPLIT_MODE:-layer}"` を追加
- L23 (`REMOTE_LOG`) に `_sm${SPLIT_MODE}` を含める
- L25-34 の `LAUNCH_CMD` に `--split-mode ${SPLIT_MODE}` を追加 (`--flash-attn` の前または後)
- echo ログに `SPLIT_MODE=${SPLIT_MODE}` を追加
- OOM/reject 検知 regex に `split-mode|row split|not supported` 追加 (row + OT 非対応時の早期 abort)

### 3. `batch_phaseT2.sh` の修正点

- 外側ループを `SPLIT_MODES=(layer row)`, 内側を `KV_TYPES=(f16 q8_0)` に変更
- `UBS=(1586)` 1 値固定に縮小
- `TAG_COND="kv${KV}_sm${SM}_ctx${CTX}_ub${UB}"` に変更
- start/run 呼び出しに `SPLIT_MODE="$SM"` 環境変数を追加
- remote log 参照パスに `_sm${SM}` 反映
- row split が 1 つでも失敗したら fail-soft で次条件へ (既存 continue ロジック流用)

### 4. `analyze_phaseT2.py` の修正点

- 入力ディレクトリ glob を `out_T2_kv*_sm*_ctx*_ub*_1k` に変更
- key tuple を (kv, split_mode, ub) に拡張
- pivot 表の行を (KV, split_mode)、列を ub に変更 (本 Phase は ub 固定なので 1 列)
- split-mode 比率 (row/layer) 列を追加し改善率表示
- 参照値を **Phase T-1 q8_0=15.016, f16=14.425, Phase D=15.03, Phase S=15.39** に更新

### 5. バッチ実行

```bash
cd report/attachment/{日時}_qwen3-122b-c3-phaseT2-splitmode/
bash batch_phaseT2.sh 2>&1 | tee batch_phaseT2.log
python3 analyze_phaseT2.py
```

### 6. 観察すべき指標

- **eval_tps / prompt_tps の mean ± stdev** (5 run)
- **CUDA0-CUDA3 compute buffer サイズ** (startup log から grep) — row で均等化するか
- **KV buffer サイズ** (row は device 分割の単位が layer から row に変わる)
- **起動時間** (row で長くなる/短くなる)
- 出力品質目視 (1 条件あたり eval_run5.json の reasoning_content 冒頭)

### 7. 失敗フォールバック

- **row + OT 非対応で起動失敗**: batch の fail-soft で row 全条件スキップ、layer 2 条件のみ完了 → 「row は OT と非互換」結論として報告
- **row + q8_0 起動失敗**: layer 3 条件 + row f16 のみで継続
- **全条件失敗**: start_phaseT2.sh の remote log を回収し failure mode を分析、レポート化

## 再利用する既存資産

| 資産 | パス | 用途 |
|------|------|------|
| Phase T-1 スクリプト群 | `report/attachment/2026-04-22_141232_qwen3-122b-c3-phaseT1-kv-quant/` | 複製元 |
| SKILL_STOP | `.claude/skills/llama-server/scripts/stop.sh` | 既存条件間のサーバ停止 |
| 1k prompt | 上記 attachment 内 `prompts/prompt_1k.txt` | eval 入力 |
| measure/run_all | 上記 attachment 内 | API 呼び出しと JSON 保存 |

## レポート要件 (本 Phase 完了後)

- ファイル名: `report/{日時}_qwen3-122b-c3-phaseT2-splitmode.md`
- **タイトル**: `Phase T-2: split-mode row vs layer 比較` (50 字以内厳守)
- **核心発見サマリ**に本文冒頭で以下を明記:
  - Phase D (15.03) / Phase S (15.39) / Phase T-1 q8_0 (15.016) との比較表
  - split-mode row が改善/中立/劣化のいずれか
  - q8_0 vs f16 再現性 (Phase T-1 副次発見 +4.1% の再現可否)
- **未検証事項**セクション: ub=1586 以外での split-mode 効果、ctx=65k での row 挙動、row × KV 量子化の他 2 型 (q4_0/q4_1) など
- **検証完了後に実施すべき TODO**: Phase T-3 (threads 中間値 24/28/32/36) / T-4 (OT pattern 層範囲代替 blk.14-19 など) / T-5 (ビルドフラグ GGML_CUDA_FORCE_MMQ/DMMV)
- フォーマットは [REPORT.md](../REPORT.md) に従う
- PNG グラフが有用 (split-mode × KV の bar chart) — 核心発見サマリ冒頭に埋め込み

## 検証方法 (end-to-end)

1. `bash batch_phaseT2.sh` 完走 (batch_phaseT2.log に全 4 条件の `measure done` が記録される)
2. `python3 analyze_phaseT2.py` が `summary_phaseT2.tsv` / `phaseT2_pivot.md` / `phaseT2_stats.csv` を生成
3. pivot 表で eval_tps の 4 セルが埋まっており stdev < 0.2 t/s
4. 核心発見サマリの比較表 (Phase D/S/T-1 vs T-2 最良) が数値で埋まっている
5. GPU サーバは `bash .claude/skills/llama-server/scripts/stop.sh t120h-p100` で停止済みかつロック解除済み

## 想定所要時間

- 準備 (スクリプト複製と diff 適用、analyze の書き換え): 15-20 分
- バッチ実行: 40-60 分
- 分析・レポート執筆: 20-30 分
- **合計**: 約 75-110 分
