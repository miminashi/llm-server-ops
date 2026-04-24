# Phase T-5f: B28 × ctx=32k × ub 微細スイープ + drift 定量化

## Context

### 前回 (Phase T-5e) の結果と問題意識

2026-04-22 夜に完了した Phase T-5e で **B28 × ctx=32k × ub=512** が **eval 16.380 t/s (歴代新記録、Phase D +8.98%)** を達成した。しかし同時に以下 2 つの重要な懸念が露出:

1. **session 内 drift -0.425 t/s (-2.67%)**: 同一条件 B28_32k_1586 を起点 (15.887) と終点 (15.463) に配置したところ、T-5 (0.02%) の **130 倍大**の drift を観測。絶対値比較が drift 補正依存になった。
2. **ub=512 が eval 支配因子だが prompt は 2× 遅い (77 → 38 t/s)**: ub=512 未満の挙動は未探索で、更なる eval 改善余地と prompt との trade-off フロンティアが不明。

### 優先度選定の判断

ユーザが提示した候補と T-5e レポート未検証事項の対応:

| ユーザ候補 | T-5e 未検証項目 | 当 Phase でカバー |
|-----------|----------------|------------------|
| (a) ub 更小化 (256/128/64) | Phase T-5e3 | **✓ ub sweep で統合** |
| (b) B28 × ub=512 再現性 + drift 切り分け | Phase T-5-drift | **✓ drift bracket で統合** |
| (c) eval/prompt Pareto | Phase T-5e-prompt | **✓ ub sweep の副産物** |
| (d) OT 再配分 | Phase T-5a | 後回し (VRAM リスク高) |
| (e) ビルドフラグ | Phase T-6 | 後回し (3-4h、T-5f 結果 baseline で実施が効率的) |

**結論: 単一 session で (a)+(b)+(c) の 3 候補を同時検証する "Phase T-5f: ub 微細 sweep + drift bracket" を実施。**理由:
- T-5e baseline (B28/ctx=32k/q8_0/t40) が既に確立、ub 以外は固定で済み変動要因最小化
- 起点・終点に B28_32k_ub512 を配置し drift を定量化、drift 補正後の ub trend 真値を得る
- 1 session で ub 8 点 + drift bracket = 8~10 条件、予想 80-95 分で収まる
- ub ≤ 512 では VRAM 更に余裕 (compute buffer < 0.9824×ub MiB)、OOM リスクほぼゼロ

### 期待成果

1. **歴代新記録 16.5+ t/s の可能性**: ub=256/128 で eval が更に伸びれば達成
2. **drift 原因切り分けの基礎データ**: B28_32k_ub512 の再現値が 2 run 得られ、drift の線形性仮定の検証
3. **eval/prompt Pareto 曲線**: ub = 64 ~ 1586 の 8 点で trade-off 境界を可視化、実用ub 推奨値を特定
4. **Phase T-6 (ビルドフラグ) の baseline 最適化**: T-5f 最良 ub を T-6 baseline に採用すれば、T-6 の効果判定精度が向上

## 環境・固定パラメータ

- サーバ: **t120h-p100** (10.1.4.14)、P100 × 4 / Xeon E5-2698 v4 ×2 socket (Node1 のみ使用)
- llama.cpp ビルド: `6990e2f1f` (T-1 〜 T-5e と同一、**再ビルド不要**)
- モデル: unsloth/Qwen3.5-122B-A10B-GGUF Q4_K_M
- 固定: **OT=B28** (`blk\.([0-9]|1[0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU`), **ctx=32768**, **KV q8_0/q8_0**, **split-mode=layer**, **threads=40**, **numactl -N1 -m1**, **-ngl 999**, **flash-attn=1**, **parallel=1**, **poll=0**
- 変動: **ub** のみ (batch_size = ub)

## 条件設計 (9 条件)

| # | label | ub | 役割 |
|---|-------|----|------|
| 1 | **B28_32k_ub512a** | 512 | **drift 起点** (T-5e 最良 16.380 の再現) |
| 2 | B28_32k_ub1586 | 1586 | T-5 baseline 参照 (drift 補正基準点) |
| 3 | B28_32k_ub1024 | 1024 | eval 中間点 (Pareto 探索) |
| 4 | B28_32k_ub768 | 768 | eval 中間点 (Pareto knee 候補) |
| 5 | B28_32k_ub384 | 384 | ub<512 trend 確認 |
| 6 | B28_32k_ub256 | 256 | ub<512 trend 確認 (新記録候補) |
| 7 | B28_32k_ub128 | 128 | eval 上限特定 (trend 延長) |
| 8 | B28_32k_ub64 | 64 | eval 下限値 (OOM/動作限界確認) |
| 9 | **B28_32k_ub512z** | 512 | **drift 終点** (起点との差で drift 確定) |

- 全条件で **warmup 2 + eval 5 = 7 run**、prompt tokens 1024、max output tokens 300
- 順序: drift 起点 → 高 ub → 低 ub → drift 終点 (高 ub から低 ub への単調減で熱/state 変化のモノトニックな傾向を作り、drift 線形性仮定を強化)

## VRAM 事前予測 (Phase S 2 軸モデル、T-5e で検証済み)

`CUDA3 compute = 0.9824 × ub (MiB)`, `CUDA3 KV = 102 MiB @ ctx=32k`, `CUDA3 model = 12,829 MiB`:

| ub | CUDA3 compute | CUDA3 total 予測 (MiB) | 16 GB 制限までの余裕 |
|----|---------------|----------------------|--------------------|
| 1586 | 1558 | 14,489 | 1,911 MiB |
| 1024 | 1006 | 13,937 | 2,463 MiB |
| 768 | 755 | 13,686 | 2,714 MiB |
| 512 | 503 | 13,434 | 2,966 MiB |
| 384 | 377 | 13,308 | 3,092 MiB |
| 256 | 252 | 13,183 | 3,217 MiB |
| 128 | 126 | 13,057 | 3,343 MiB |
| 64 | 63 | 12,994 | 3,406 MiB |

**OOM リスクは全 ub でほぼゼロ。** dry-start は不要 (T-5e で ctx=65k ub=1586 まで fit 確認済み、本 Phase はそれより常に軽い)。

## 判定基準

| 判定 | 閾値 |
|------|------|
| **Phase T-5e (16.380) 超え** | 任意の condition で eval_mean > 16.380 t/s |
| **ub trend 単調減** | ub=1586 → 64 で eval_mean が単調増 (反転あれば peak 特定) |
| **drift 再現** | B28_32k_ub512a と B28_32k_ub512z の差の絶対値 (補正前) |
| **drift 健全 (仮閾値)** | \|ub512a − ub512z\| < 0.3 t/s (T-5e の 0.425 より改善) |
| **OOM 動作限界** | ub=64/128 で log に OOM が出るか (予測は fit) |

### drift 補正方式

- 線形補正: `per_run_drift = (ub512z_mean − ub512a_mean) / (run_count − 1)` で各 condition に -drift × run_index を加算
- 補正後の ub trend で「真の eval 最良 ub」を判定

## 実装計画 (既存資産の最大再利用)

### 1. attachment ディレクトリ作成 (T-5e ベースをコピー)

```bash
# レポートファイル名のタイムスタンプは実行時に取得: TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S
NEW_DIR=report/attachment/<timestamp>_qwen3-122b-c3-phaseT5f-ub-fine-sweep
mkdir -p "$NEW_DIR"
cp report/attachment/2026-04-22_214556_qwen3-122b-c3-phaseT5e-ctx-ub-apply/{start_phaseT5.sh,batch_phaseT5e.sh,analyze_phaseT5e.py,plot_phaseT5e.py} "$NEW_DIR/"
cd "$NEW_DIR"
```

### 2. 改修する箇所 (最小差分)

#### `batch_phaseT5e.sh` → `batch_phaseT5f.sh` (condition 配列のみ変更)

- CONDITIONS 配列を下記 9 条件に置換:
  ```
  B28_32k_ub512a#32768#512
  B28_32k_ub1586#32768#1586
  B28_32k_ub1024#32768#1024
  B28_32k_ub768#32768#768
  B28_32k_ub384#32768#384
  B28_32k_ub256#32768#256
  B28_32k_ub128#32768#128
  B28_32k_ub64#32768#64
  B28_32k_ub512z#32768#512
  ```
- log ファイル名 (バッチ側) を `batch_phaseT5f.log` に変更
- OT_TAG / THREADS / CACHE_TYPE_K/V / FLASH_ATTN / SPLIT_MODE は T-5e と同一

#### `analyze_phaseT5e.py` → `analyze_phaseT5f.py`

- condition list 更新 (同上 9 件)
- 2x2 factorial (ctx × ub) 分析セクションを **ub 1D trend 表** + **drift bracket 分析** に置換
- drift 補正テーブル (per-run -drift 線形補正) 出力を追加
- Pareto 用に eval_mean, prompt_mean を 1 表で ub 順にソート出力
- PEAK 比較は Phase D/S/T-4/T-5/T-5e の 16.380 も加える

#### `plot_phaseT5e.py` → `plot_phaseT5f.py`

- **Figure 1**: ub (log scale x 軸) vs eval_mean + prompt_mean の dual y-axis line plot
- **Figure 2**: Pareto scatter (x=prompt_mean, y=eval_mean)、点ラベルは ub 値
- **Figure 3**: drift bracket (run_index=1..9 vs eval_mean、起点・終点強調)

### 3. 実行手順

```bash
# 1. gpu-server lock 取得
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 2. attachment へ移動し batch 実行
cd report/attachment/<timestamp>_qwen3-122b-c3-phaseT5f-ub-fine-sweep/
nohup bash batch_phaseT5f.sh > batch_phaseT5f.log 2>&1 &

# 3. 進捗監視 (cache 節約のため Monitor/sleep 併用)
tail -f batch_phaseT5f.log  # または ScheduleWakeup で 20-30 min 間隔で確認

# 4. 完了後の解析
python3 analyze_phaseT5f.py
python3 plot_phaseT5f.py

# 5. lock 解放
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### 4. レポート作成 (plan mode で作業したため必須)

- タイムスタンプは **`TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`** で取得 (CLAUDE.md 指示に従う)
- ファイル名: `report/<ts>_qwen3-122b-c3-phaseT5f-ub-fine-sweep.md`
- 添付: plan ファイル (`mkdir -p report/attachment/<ts>_..._phaseT5f-ub-fine-sweep/` → `cp /home/ubuntu/.claude/plans/phase-t-5e-b28-idempotent-cocoa.md report/attachment/.../plan.md`)
- **タイトル 50 字以内**、**核心発見サマリに PNG 埋め込み**、「未検証事項」「検証完了後に実施すべき TODO」セクションを含める、Phase D/S/T-1〜T-5e 全比較表を記載

## 所要時間予測

| ステップ | 時間 | 備考 |
|---------|------|------|
| スクリプト改修 | 10 min | condition 配列 + analyze/plot 差し替え |
| batch 実行 | 75-90 min | 9 条件 × (startup 4 min + warmup 2 + eval 5 runs ≈ 4-5 min) |
| 解析・プロット | 10 min | 既存コードの流用 |
| レポート作成 | 20-30 min | Phase 全体比較 + Pareto 考察 |
| **合計** | **~115-140 min** | T-5e (63 min) より長いが 9 条件で妥当 |

## リスクと mitigation

| リスク | 影響 | mitigation |
|--------|------|------------|
| drift が T-5e より大 | 絶対値比較不能化 | 補正後ランキングで主張、drift 自体を別節で定量化して今後 Phase への教訓に |
| ub=64/128 で OOM (予測外) | 該当条件失敗 | SKIP_LABELS で該当条件スキップして batch 継続、報告で記録 |
| prompt 遅延が顕著 (ub=64 で prompt <10 t/s) | Pareto 評価に有用 | むしろ Pareto 境界明示、実用 ub 下限の定量化に寄与 |
| 他セッション/ユーザ競合 | lock 取得失敗 | lock.sh 実行時点で holder 確認、必要ならユーザに連絡 |
| session 途中で batch 中断 | 再開困難 | batch は nohup & 化済、途中ログ (batch_phaseT5f.log) で状態確認可能 |
| 全 condition で T-5e を下回る | 新記録なし | drift bracket + Pareto 分析は成立、情報量は維持 |

## 検証方法 (完了判定)

1. `batch_phaseT5f.log` 末尾に全 9 条件の eval 完了行が出ている
2. `analyze_phaseT5f.py` の出力で 9 条件分の eval_mean/stdev が CSV に揃う
3. `plot_phaseT5f.py` が 3 枚の PNG を生成 (ub vs tps、Pareto、drift bracket)
4. 最良 eval_mean > 16.380 なら新記録、そうでなければ T-5e 上限確認 + Pareto 成果として成立
5. drift bracket の |a − z| を記録、T-5e (0.425) との比較を報告する

## 重要ファイルパス

- 基準スクリプト: `report/attachment/2026-04-22_214556_qwen3-122b-c3-phaseT5e-ctx-ub-apply/` 配下
- llama-server skill: `.claude/skills/llama-server/scripts/{start,stop}.sh`
- gpu-server skill: `.claude/skills/gpu-server/scripts/{lock,unlock}.sh`
- T-5e レポート: `report/2026-04-22_230941_qwen3-122b-c3-phaseT5e-ctx-ub-apply.md`
- CLAUDE.md / REPORT.md (作業規約)

## 未検証事項 (T-5f スコープ外、後続 Phase の候補)

以下は T-5f では扱わない。T-5f 完了後にレポートの "検証完了後 TODO" で再掲する予定:

- **Phase T-5g: threads 精密 sweep** (T-5f 最良 ub × threads∈{36,38,40,42})
- **Phase T-6: ビルドフラグ × T-5f 最良 ub** (`GGML_CUDA_FORCE_MMQ` ON/OFF × `GGML_CUDA_FORCE_DMMV` ON/OFF)
- **Phase T-5-drift-deep: 20 run 連続 + nvidia-smi dmon** (T-5f drift 原因究明の主力)
- **Phase T-5a: CUDA0 OT 拡張 (B24 領域)** (VRAM 余裕活用)
- **Phase T-5f-ctx: T-5f 最良 ub × ctx∈{24k, 48k, 96k}** (ctx 感度の再探索)
