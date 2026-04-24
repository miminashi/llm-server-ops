# Phase Sb-alloc Step 4: 候補評価マトリクス

## 評価基準

| 略号 | 意味 |
|---|---|
| SM | **Step 機構** を生むか (観測: 1585→1586 で slope が 0.0125 → 0.2853 MiB/tok へ遷移) |
| BL | **境界位置** ub*=1586 と整合するか |
| SL | **線形 slope** 0.2853 MiB/tok を生むか |
| GPU | CUDA0 **固有**に出現する理由を説明できるか |

評価記号: ○ 説明可能 / △ 部分的 / × 否定 / ? 未確定

## 候補マトリクス

| 候補 | 内容 | SM | BL | SL | GPU | 評価 |
|---|---|---|---|---|---|---|
| **D** | allocator pool 量子化 (256B/128B/2MiB) | × | × | × | × | **棄却**（本 Phase alloc_sim.py で数値確証）|
| **E** | GDN CUDA kernel tile 境界 | × | × | × | × | **棄却**（grid/block dim が n_tokens 非依存）|
| **F** | graph_reserve worst-case ubatch | × | × | ○ | × | build_graph の容器。step 機構なし |
| **G** | memory_recurrent (R/S buffer) ub 依存 | × | × | × | × | **棄却**（cell 単位、n_tokens 非依存）|
| **H** | graph splits 数の ub 境界での変化 | **?** | **?** | ? | ○ | **候補残**（要実測: ub sweep × "graph splits" log）|
| **I-a** | FA tile ntiles_x=ceil(n_tokens/4) | × | × | × | × | 4-token 境界、1585→1586 同 tile |
| **I-b** | FA parallel_blocks の efficiency 最適化 | △ | ? | ? | △ | 要実測（nvprof 経路 → GPU ロック Phase）|
| **I-c** | qwen35moe build_graph の ub 依存 discreteness | ? | ? | ○ | ○ | **候補残**（MoE router/attention tensor）|
| **J** | VMM block 9 層分散 × SSM 出力累積 (新規仮説) | ○ | △ | ○ | ○ | **最有力**（詳細下記）|

## 最有力候補 J の詳細

本 Phase のシミュレーション (alloc_sim.py) で判明した重要な構造:

- **2 MiB VMM granularity** で 9 層の SSM 出力テンソルが **各層独立に** pool に配置される場合
- 各層の raw サイズ = `32768 × (ub + 128)` bytes = `(ub + 128) / 64` MiB
- 層境界 (block 再取得) は raw size が 2 MiB の倍数を跨ぐタイミング:
  - `(ub + 128) / 64 = k` (k=整数) を解くと `ub = 64k - 128`
  - k=27: ub=1600 (境界), k=28: ub=1664 (次境界)

現実の観測 1585→1586 境界は **64-token 境界 (1600, 1664)** とは**不一致**。
⇒ 候補 J の「9 層独立 VMM block」仮説も**単純形では棄却**。

ただし、**CUDA0 に同時生存する他テンソル (embedding/attn KV/FFN)** との累積が境界を前倒しする可能性は残る。

## 採点表（数値）

| 候補 | Phase Sb-fine3 観測との誤差 | 決定性 |
|---|---|---|
| D (128B/256B alignment) | +0.281 MiB/tok 線形 (≈0.2812, 観測 0.2853 と 1.4% 差) だが **step 発生せず** | 棄却 |
| D (2 MiB VMM) | 486 MiB 平坦の後 ub=1664 で +18 MiB | 棄却 |
| H (splits 変化) | 数値不明 (実測必要) | 実測候補 |
| I-c (build_graph discreteness) | 数値不明 (実測必要) | 実測候補 |

## 推奨次 Phase

1. **★最優先: Phase Sb-splits 実測** (GPU ロック要、所要 40-60 分)
   - ub=1580/1584/1585/1586/1588/1592/1600/1664 の 8 条件で llama-server 起動
   - startup_log から "graph splits" / "graph nodes" の値を抽出
   - 1586 で splits/nodes が変化するなら候補 H 確定

2. **★高優先: Phase Sb-tensor-dump 実測** (GPU ロック要、所要 1.5 時間)
   - llama.cpp の debug ビルドで `ggml_backend_sched_reserve_size` の結果を node 単位で dump
   - ub sweep で node 単位の tensor byte size の増減を比較
   - 1585→1586 で新規 node or 既存 node size のジャンプを特定

3. **★中優先: Phase Sb-ctx-boundary 実測** (GPU ロック要、所要 1.5 時間)
   - 候補 J (SSM 層累積) が正なら境界は ctx 非依存で 1586 固定
   - ctx=16k/65k/131k × ub=1584/1585/1586 の 9 条件
   - 境界が ctx で動くなら KV cache / FA tensor 由来（候補 I-b）
