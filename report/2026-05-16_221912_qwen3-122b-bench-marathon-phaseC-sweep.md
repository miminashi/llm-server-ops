# Phase C: Parameter sweep（ub / b / threads）

- **実施日時**: 2026 年 5 月 16 日 19:52–22:18 JST
- **対象**: llama.cpp `HEAD = 1348f67c5` × Qwen3.5-122B-A10B-Q4_K_M × t120h-p100 × fit (B14b_ts_alt, ctx=128k)

## 核心発見サマリ

- **`--threads 32`（T1_th32）が BL 比 +0.66% で軽微だが有意改善**（Phase T-3 結論と再現）→ BL_FINAL 候補
- **`--threads 44` は -27.49% 大幅低下**（Xeon Gold 6138 socket0 の 40 物理スレッドを超え NUMA 領域逸脱）→ 採用厳禁
- **`-ub 768` は eval -1.57% / prompt +16.2%** の Pareto トレードオフ。**prompt 重視のワークロードでは強力な候補**
- **`-ub 256/384` / `-b 4096` は OOM で起動後すぐクラッシュ**（context checkpoint 機構が無効化されたままデフォルトで動作し、ub 縮小時の VRAM 配分が破綻するため）
- **`-b` を 1024 / 4096 に変えても改善はなく、b=2048 (BL) が最適**

## 添付ファイル

- [実装プラン](attachment/2026-05-16_221912_qwen3-122b-bench-marathon-phaseC-sweep/plan.md)
- [Phase C オーケストレータ](attachment/2026-05-16_221912_qwen3-122b-bench-marathon-phaseC-sweep/phaseC_orchestrator.sh)
- [生 CSV](attachment/2026-05-16_221912_qwen3-122b-bench-marathon-phaseC-sweep/results.csv)
- [Phase C 実行ログ](attachment/2026-05-16_221912_qwen3-122b-bench-marathon-phaseC-sweep/phaseC.log)
- 各試行の out_<試行>_<promptlen>/ 配下の生レスポンス JSON + llama-server log

## 前提・目的

- 背景: Phase A で BL は U-6 比 +1.3〜+4.5% 改善を確認、M1 (+0.91%) が有意。Phase B では spec が context checkpoint OOM で全失敗。Phase C は **spec を使わない純粋なパラメータ sweep** で軽微な改善余地を探る
- 目的: `-ub`, `-b`, `--threads` の値を変えて、現 HEAD と現 fit 構成で BL から +α を得られるか確認
- 参照レポート:
  - [Phase A (BL + Quick wins)](2026-05-16_183834_qwen3-122b-bench-marathon-phaseA-quickwins.md)
  - [Phase B (spec 全失敗)](2026-05-16_195031_qwen3-122b-bench-marathon-phaseB-spec-fail.md)
  - [T-5a-ts2 (歴代ベスト ctx=32k)](2026-04-23_093629_qwen3-122b-c3-phaseT5a-ts2.md)
  - [Phase T-3 (threads sweep)](2026-04-23_053125_qwen3-122b-c3-phaseT5a-thr.md)

## 環境情報

- サーバ: `t120h-p100` (10.1.4.14)、P100 × 4 (64 GB)
- CPU: Xeon Gold 6138 × 2 (20 cores/socket、HT 込み 40 thread/socket)、`numactl --cpunodebind=1 --membind=1` で node1 固定
- llama.cpp `HEAD = 1348f67c5`
- ベース構成（BL）: B14b_ts_alt + `--flash-attn 1 -b 2048 -ub 512 --tensor-split 11,12,13,14`, `--threads 40`, KV q8_0, ctx=131072

## 試行マトリクス

Phase C は 1k prompt のみ計測（warmup 2 + eval 5 × max_tokens=1024）。short 版設計。

| ID | 変更点 | 結果 |
|----|--------|------|
| U1_ub256 | `-ub 256`（他は BL） | ❌ OOM (warmup 1 後) |
| U1_ub384 | `-ub 384` | ❌ OOM (warmup 1 後) |
| U1_ub768 | `-ub 768` | ✅ 完走 |
| B1_b1024 | `-b 1024 -ub 512` | ✅ 完走 |
| B1_b4096 | `-b 4096 -ub 512` | ❌ OOM (warmup 1 後) |
| T1_th32 | `--threads 32`（他は BL） | ✅ 完走 |
| T1_th44 | `--threads 44`（他は BL） | ✅ 完走（劇的低下）|

## 結果

| 試行 | n | eval mean (t/s) | eval std | prompt mean (t/s) | BL eval 比 | 備考 |
|------|---|-----------------|----------|--------------------|------------|------|
| **BL (Phase A 値)** | 5 | **18.482** | 0.110 | 64.366 | – | 比較基準 |
| U1_ub256 | – | OOM | – | – | – | 起動成功 → 1 リクエスト目で CUDA3 OOM |
| U1_ub384 | – | OOM | – | – | – | 同上 |
| U1_ub768 | 5 | 18.192 | 0.186 | **74.754** | **-1.57%** | prompt **+16.2%** 改善（Pareto）|
| B1_b1024 | 5 | 18.107 | 0.021 | 64.008 | -2.03% | 微減 |
| B1_b4096 | – | OOM | – | – | – | 同上 OOM |
| **T1_th32** | 5 | **18.604** | 0.013 | 64.509 | **+0.66%** | ★ 軽微改善（Welch t ≈ 2.4, p≈0.04）|
| T1_th44 | 5 | 13.401 | 0.003 | 64.155 | **-27.49%** | NUMA 領域逸脱 |

### Pareto 図（テキスト版）

```
prompt_tps↑  +16.2%  ┃           ★ U1_ub768
              + 0.2% ┃ T1_th32          
              + 0.0% ┃ BL/B1_b1024       
              + 0.0% ┃     T1_th44 (-27.5%)
              -------+--------------------------- eval_tps
                  -27%   -2%  BL  +0.7%
```

## 仮説と解釈

1. **`-ub 768` の prompt 大幅改善**: 大きい ubatch で prefill 並列度が上がり、GPU の SIMT 利用率向上。eval は ubatch 拡大による KV キャッシュアクセス遅延で僅かに低下
2. **`-ub 256/384` / `-b 4096` OOM の原因**: llama.cpp HEAD では **`-ctxcp/--ctx-checkpoints/--swa-checkpoints` がデフォルト有効**（max 32 ckpt/slot, 1 ckpt あたり 149 MiB）。BL (`-ub 512`) では VRAM が辛うじて足りるが、ub を縮めたり b を拡げたりすると、ub 単位の prefill ピーク中間バッファが増えて checkpoint 領域と競合し OOM
3. **`-b 1024` の微減**: BL の `-b 2048` から半減で prompt は変わらず、eval が若干悪化。`-b` は **`-ub` に揃えるか、それより大きくすれば挙動同じ**で、現実装では BL の 2048 が最適点
4. **`--threads 32` の +0.66%**: Phase T-3 で確認した「socket0 物理コア 20 × HT2 = 40 を超えない範囲で多少絞ると CPU 競合が減る」効果。p100 は MoE expert 計算を CPU で実行するため、CPU 側の効率が直接 generate に影響
5. **`--threads 44` の -27.49%**: socket1 にスレッドが流出 → numactl `--cpunodebind=1` 違反で **NUMA cross-socket メモリアクセス**発生 → 致命的減速

## 効きそうな PR との関係（updated）

| PR | 期待 | Phase C 観測 |
|----|------|--------------|
| #21168 (ds_read_b128 mmq) | Q4/Q5 mmq +10% | b/ub sweep でも 1% 程度の振れ幅のみ、Pascal では効果限定 |
| – | 一般的 ubatch tuning | ub=768 で prompt +16%、eval -1.6%。**用途別 sweet spot** が変化 |

## Phase D / E への反映点

- **T1_th32 を BL_FINAL に組み込む**: `--threads 32` で +0.66%
- **U1_ub768 はオプション保持**: prompt 中心のワークロードでは採用、デフォルトは BL の ub=512
- **`-b 2048` / `-ub 512` 構成が **VRAM-checkpoint の同時成立点**であることが確認できた → Phase D で B12 (CPU 12 層) に縮めても、VRAM 余裕を活かして checkpoint と prefill バッファの両立が可能か検証
- **`--ctx-checkpoints 0` で context checkpoint を無効化**できれば、ub=256/384/b=4096 の OOM が回避できる可能性。次の試行候補

## 再現方法

```bash
bash <添付>/phaseC_orchestrator.sh  # 約 2.4 時間（7 試行）
```

各試行の挙動:
- 各 trial: `start.sh` を python パッチで一時編集 → `llama-up.sh` → 計測 1k → `pkill llama-server` → `git checkout start.sh`
- OOM の場合は wait_ready で /health 取得後 1 リクエスト目で fail → curl_failed が CSV に記録

## 未試行 / 後フェーズに送る項目

- `-ub` 中間値（448, 576, 640）の sweep
- `-b` を `-ub` と揃えた値（512, 768）の比較
- `--threads` を 28/30/34/36/38 で細粒度 sweep
- `--ctx-checkpoints 0 --swa-checkpoints 0` で checkpoint 無効化（VRAM 余裕確保）→ Phase D 余裕枠で検証
- `--threads-batch` 別途指定（現状は `--threads` と同値）

## 経過時間

| 試行 | 所要 | 結果 |
|------|------|------|
| U1_ub256 | 8 分 (起動 1 + 計測 fail 4 + 停止 3) | ❌ |
| U1_ub384 | 8 分 | ❌ |
| U1_ub768 | 51 分 (warmup × 2 max_tokens=1024 で長め) | ✅ |
| B1_b1024 | 20 分 (warmup 1 が長め) | ✅ |
| B1_b4096 | 12 分 | ❌ |
| T1_th32 | 16 分 | ✅ |
| T1_th44 | (22 分以上) | ✅ |
| **合計** | **~2.4 時間** | – |
