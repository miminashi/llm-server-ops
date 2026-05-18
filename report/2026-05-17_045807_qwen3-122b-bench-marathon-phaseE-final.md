# Phase E: BL_FINAL 最終確認（M1 + T1_th32 組合せ）

- **実施日時**: 2026 年 5 月 16 日 23:23 〜 5 月 17 日 04:58 JST
- **対象**: llama.cpp `HEAD = 1348f67c5` × Qwen3.5-122B-A10B-Q4_K_M × t120h-p100 × fit (B14b_ts_alt, ctx=128k)

## 核心発見サマリ

- **BL_FINAL = BL + `--main-gpu 1` + `--threads 32`** 構成を 2 セット計測（再現性確認）
- Set1: 1k=18.350 (-0.71%), 32k=14.748 (**+1.38%**), 96k=**10.303 (+0.77%)**
- Set2: 1k=17.973 (**-2.75%**), 32k=14.563 (+0.11%)
- **Set1 と Set2 で大きな drift**: 1k で 0.38 t/s 低下、32k で 0.19 t/s 低下 → セッション運用時間と thermal で性能が劣化
- **Phase A の単体測定 (M1 単独 +0.91%, T1_th32 単独 +0.66%) は組合せでは打ち消し合う傾向**: 期待累積 +1.6% に対し実測は drift 込みで -1.7% 〜 +0.7%
- **結論**: 個別フラグの組合せでは BL を有意に超えない。**HEAD 自体の U-6 比 +1.3〜+4.5% が主たる改善源**

## 添付ファイル

- [実装プラン](attachment/2026-05-17_045807_qwen3-122b-bench-marathon-phaseE-final/plan.md)
- [Phase E オーケストレータ](attachment/2026-05-17_045807_qwen3-122b-bench-marathon-phaseE-final/phaseE_orchestrator.sh)
- [生 CSV](attachment/2026-05-17_045807_qwen3-122b-bench-marathon-phaseE-final/results.csv)
- [Phase E 実行ログ](attachment/2026-05-17_045807_qwen3-122b-bench-marathon-phaseE-final/phaseE.log)
- BL_FINAL Set1/Set2 の out_<試行>/ + llama-server log

## 前提・目的

- 背景: Phase A で M1 (`--main-gpu 1`) が単体 +0.91% (有意)、Phase C で T1_th32 (`--threads 32`) が単体 +0.66%。期待累積 ~+1.6%
- 目的: 両者を組み合わせた BL_FINAL を 2 セット計測し、累積効果と再現性を確認
- 参照: [Phase A](2026-05-16_183834_qwen3-122b-bench-marathon-phaseA-quickwins.md), [Phase C](2026-05-16_221912_qwen3-122b-bench-marathon-phaseC-sweep.md)

## 環境情報

- サーバ: `t120h-p100`、P100 × 4 (64 GB)
- llama.cpp `HEAD = 1348f67c5`
- BL_FINAL 構成: `--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14 --main-gpu 1 --threads 32`、`numactl -N1 -m1`、OT=B14b_ts_alt、ctx=131072、KV q8_0

## 結果

### Set1（連続計測 1k → 32k → 96k）

| prompt | n | eval mean | eval std | prompt mean | BL 比 (eval) |
|--------|---|-----------|----------|-------------|--------------|
| 1k     | 5 | 18.350 | 0.010 | 64.140 | **-0.71%** |
| 32k    | 5 | 14.748 | 0.066 | 61.285 | **+1.38%** |
| 96k    | 5 | **10.303** | 0.067 | 53.088 | **+0.77%** |

### Set2（Set1 終了後 30 秒で再起動、1k → 32k）

| prompt | n | eval mean | eval std | prompt mean | BL 比 (eval) |
|--------|---|-----------|----------|-------------|--------------|
| 1k     | 5 | **17.973** | 0.009 | 64.161 | **-2.75%** |
| 32k    | 5 | 14.563 | 0.120 | 61.030 | **+0.11%** |

### Set1 vs Set2 の差（drift 観測）

| prompt | Set1 eval | Set2 eval | 差 | drift |
|--------|-----------|-----------|----|-------|
| 1k     | 18.350    | 17.973    | -0.377 t/s | **-2.05%** |
| 32k    | 14.748    | 14.563    | -0.185 t/s | **-1.25%** |

ベンチセッション 12 時間連続運用後の thermal / メモリ断片化が drift の主因と推定。

## 仮説と解釈

1. **M1 + T1_th32 の組合せは打ち消し合い**: M1 は CUDA0→CUDA1 切替で tensor split の起点を変える効果（+0.91%）、T1_th32 は CPU の MoE expert 処理効率改善（+0.66%）。両方を適用すると、main-gpu 切替により CPU 側の MoE 計算スケジューリングが変わり、threads=32 の最適性が崩れた可能性
2. **drift の主因**: 12 時間連続運用 (P100 thermal stable のはずだが、CPU NUMA メモリ断片化や CUDA driver 内部状態の蓄積が考えられる)
3. **32k/96k での改善は本物**: 32k は両 Set で +0.11〜+1.38%、96k は Set1 で +0.77%。`--main-gpu 1` が長 prompt 処理（多くの KV キャッシュアクセス）でメリットを生む構造的効果
4. **1k での減少は drift 主因**: Set1 -0.71% / Set2 -2.75%。drift を除けば BL とほぼ同等

## デフォルト構成更新の判断

**BL_FINAL を default として採用しない**：

- 1k で -0.71〜-2.75% は無視できない（generate 重視のワークロードを損なう）
- 32k/96k での +0.1〜1.4% は drift と区別がつきにくい
- 単純な BL（M1/T1_th32 なし）が、calibration を取り直した直後の測定で最も安定

**ただし以下は更新を検討**:
- `--main-gpu 1` 単独: 32k で +1.41%、1k で +0.91% (Phase A)。drift の影響を排除できれば採用候補

## Phase E の経過時間

| ステップ | 開始 | 終了 | 所要 |
|---------|------|------|------|
| start.sh patch + Set1 起動 | 23:23:43 | 23:24:54 | 1.2 分 |
| Set1 1k | 23:24:54 | 23:35:56 | 11 分 |
| Set1 32k | 23:36:00 | 00:34:14 | 58 分 |
| Set1 96k | 00:34:15 | 03:40:03 | 3 h 6 分 |
| Set1 停止 + Set2 起動 | 03:40:03 | 03:46:46 | 6.7 分 |
| Set2 1k | 03:46:46 | 03:57:24 | 10.6 分 |
| Set2 32k | 03:57:26 | 04:55:00 | 58 分 |
| **合計** | 23:23 | **04:58** | **5 h 35 分** |

96k が大半を占める。Phase E のような最終確認では 96k を 1 セットのみで良いと判断（Set1 96k 単独）。

## 再現方法

```bash
bash <添付>/phaseE_orchestrator.sh  # 約 5.5 時間
# Set1 1k+32k+96k、Set2 1k+32k を計測
# 終了時に start.sh は revert される
```

## Phase E 結論

- BL_FINAL = BL + `--main-gpu 1` + `--threads 32` は 32k/96k で軽微改善、1k で drift 主因の低下
- **HEAD (1348f67c5) のデフォルト構成 (BL) を維持するのが最も安定**
- 個別フラグの追加改善は drift 帯（~±1%）に埋もれる
- HEAD 自体の U-6 比 +1.3〜+4.5% こそが、3 週間で得られた実質改善

## 未試行 / 後フェーズに送る項目

- BL_FINAL を **同 1 セッション内で複数回計測** し drift を排除する設計（Set1/Set2 を起動分離せず、連続計測）
- T1_th32 単独 32k 計測（Phase C では 1k のみ）
- 真の dirty BL（thermal warm 状態）と clean BL（cold 状態）の差を別途計測
