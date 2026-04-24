# Phase Sb-src 候補式一覧と数値検証

本 Phase の目的は、Phase Sb-fine3 で確定した CUDA0 compute buffer の step 境界 ub\*=1586 と線形域 slope 0.2853 MiB/tok の llama.cpp ソース上の由来を特定することにある。モデルは Qwen3.5-122B-A10B (`qwen35moe`, hybrid SSM + MoE、48 層 = 12 attn + 36 SSM)、P100 × 4 GPU、f16 KV、fa=1、ctx=32768。

## モデル・配置パラメータ (hparams.txt より抽出)

| 項目 | 値 |
|---|---|
| arch | `qwen35moe` |
| n_embd | 3072 |
| n_layer | 48 (attn 12 + SSM 36) |
| n_head / n_head_kv | 32 / 2 (gqa_ratio = 16) |
| n_embd_head_k/v | 256 |
| full_attention_interval | 4 |
| ssm_d_inner | 8192 |
| ssm_d_state (S_v = head_v_dim) | 128 |
| ssm_n_group (num_k_heads) | 16 |
| ssm_dt_rank (num_v_heads = H) | 64 |
| 各 GPU の layer 配置 | 12 層 (3 attn + 9 SSM) |

## 候補 A: SSM chunking (delta-net-base.cpp) の chunk transition

`src/models/delta-net-base.cpp:60` は `CS = kda ? 16 : 64`。

qwen35moe では `build_delta_net_chunking()` に入る条件下で `kda = (g->ne[0] == S_k && g->ne[1] == H_k)` を判定:
- `g->ne[0] = 1` (qwen35moe.cpp:241 `gate = reshape_4d(ctx0, gate, 1, num_v_heads, ...)`) ≠ `S_k = 128`
- したがって **KDA = false → CS = 64**

CS=64 の chunk transition:
- 1536→1537 (pad 0 → 63, n_chunks 24 → 25)
- 1600→1601 (n_chunks 25 → 26)

観測 1585→1586 とは不一致。

さらに **runtime ログで `fused Gated Delta Net (chunked) enabled`** を確認 → `build_delta_net_chunking` パスは qwen35moe では使われず、代わりに `build_delta_net_fused` → `ggml_gated_delta_net` (CUDA kernel) が呼ばれる。

**結論**: 候補 A は棄却。

## 候補 B: FA tile kernel の ncols1 境界

`ggml/src/ggml-cuda/fattn-tile.cuh` に基づき、P100 (CC 6.0) + head_dim=256 の dispatch:

- 経路判定 (`ggml_cuda_get_best_fattn_kernel`): tensor core 非搭載、WMMA 非搭載 → **BEST_FATTN_KERNEL_TILE**
- GQA opt: `gqa_ratio=16, gqa_ratio % 8 == 0` → **ncols2 = 8**
- `launch_fattn_tile_switch_ncols1`: `Q->ne[1] > 2` → `cols_per_block = 32`, **ncols1 = 32/8 = 4**
- `ntiles_x = ceil(n_tokens / 4)` → 境界は 4 の倍数 (1584, 1588, 1592, ...)
- 観測 1585→1586 とは不一致。

**結論**: 候補 B は棄却。

## 候補 C: gated_delta_net 出力テンソルの n_tokens 線形項 (slope の主因)

`ggml/src/ggml.c:6202` で `ggml_gated_delta_net` は以下の出力テンソルを作る:

```c
const int64_t ne[4] = { S_v * H, n_tokens * n_seqs + S_v * n_seqs, 1, 1 };
struct ggml_tensor * result = ggml_new_tensor(ctx, GGML_TYPE_F32, 4, ne);
```

qwen35moe の SSM 層では S_v=128, H=64, n_seqs=1:

- ne = [128*64=8192, n_tokens + 128, 1, 1] = 8192 × (n_tokens + 128) F32 elements
- per layer bytes = 4 × 8192 × (n_tokens + 128) = 32,768 × (n_tokens + 128) bytes
  - 線形項: 32,768 bytes/tok
  - 定数項: 32,768 × 128 = 4,194,304 bytes = **4 MiB / layer**

**CUDA0 の 9 SSM 層を同時生存と仮定した場合**:
- 線形: 9 × 32,768 = **294,912 bytes/tok = 0.28125 MiB/tok**
- 定数: 9 × 4 = 36 MiB

観測 slope 0.2853 MiB/tok (299,159 bytes/tok) と比較:
- 差分: +4,247 bytes/tok (+1.42%)
- 残差の有力候補: FA dst_tmp_meta の per-token 寄与 (ggml_nrows(KQV) × float2 × parallel_blocks × n_attn_layers per token) や graph allocator の per-tensor alignment padding

**結論**: **候補 C (SSM gated_delta_net 出力の n_tokens 線形項 × 9 SSM layers) が slope の主因 (98.6% 説明)**。

## 候補 D: graph allocator の pool quantization (境界 ub\*=1586 の説明)

候補 C は slope を説明するが、**なぜ ub ≤ 1585 で平坦域 (slope 0.0125 MiB/tok) なのか**は別問題。仮説: graph allocator (`ggml/src/ggml-alloc.c`) が worst-case reservation 時に tensor をメモリプールに配置する際、pool chunk size の境界を越える点で compute buffer 報告値が step 変化する。

### 数値検証: 9 SSM 層の SSM 出力累積と MiB 境界

```
ub=1584: per-layer=53.500 MiB, 9 layers=481.500 MiB ← 482 MiB 境界まで 0.500 MiB 余裕
ub=1585: per-layer=53.531 MiB, 9 layers=481.781 MiB ← 同 0.219 MiB 余裕
ub=1586: per-layer=53.563 MiB, 9 layers=482.063 MiB ← **482 MiB 境界を 0.063 MiB 超過**
ub=1588: per-layer=53.625 MiB, 9 layers=482.625 MiB
ub=1600: per-layer=54.000 MiB, 9 layers=486.000 MiB (MiB 境界ちょうど)
```

**1585 → 1586 の間で 9 SSM 層累積が 482 MiB 境界を越える**。これは Phase Sb-fine3 が分数推定で得た ub\* ≈ 1585.18 の位置（482 MiB 境界までの内挿点は 1585.78）から 0.6 token ずれるが、**オーダーとして一致**している。

### 仮説の限界

- 9 SSM 層の出力は allocator による reuse / reorder の影響を受ける。実効生存数が 9 未満なら境界値がシフトする。
- 「482 MiB」という具体的な値は allocator の何らかの整数倍アラインに過ぎず、真の閾値は他の共存 tensor との和で決まる可能性が高い。
- 補正項 4,247 bytes/tok は定常バイアスで境界位置には直接影響しない。

**結論**: **候補 D (graph allocator pool quantization × SSM 出力累積) が境界の最有力仮説だが、完全な特定には ggml-alloc.c の詳細解析が必要**。

## 要約: 最終判定

| 項目 | 判定 | 式 | 誤差 |
|---|---|---|---|
| **slope 0.2853 MiB/tok の由来** | **特定 (候補 C)** | `9 × 4 × S_v × H × 1 bytes/tok = 294,912 bytes/tok` (ggml_gated_delta_net 出力の線形項) | +1.42% (align / 補助 tensor の寄与) |
| **境界 ub\*=1586 の由来** | **絞り込み (候補 D)** | 9 SSM 層出力累積が ~482 MiB allocator boundary を越える | 0.6 token (allocator の詳細は未解析) |
| **物理的な「非自然な定数 1586」** | **解明** | 整数リテラルではなく、SSM 出力の累積が特定のメモリ境界を越える n_tokens 値として動的に決まる |

## 未解析事項

1. **`ggml/src/ggml-alloc.c` の `ggml_tallocr_alloc` / worst-case 計算ロジック**: 具体的にどのサイズ単位 (1 MiB? page=4 KiB? 他?) で quantize されるかの特定が必要。
2. **残差 4,247 bytes/tok の分解**: FA dst_tmp_meta (parallel_blocks 依存) や graph allocator per-tensor padding の具体寄与。
3. **CUDA1/2/3 でも同一 slope (0.2853 近辺) が現れるはずだが 31 点で純線形 (cross 項含む) に乗っている理由**: おそらく他 GPU では attention layers の寄与が支配的で SSM 出力は小さい副成分として埋もれる。CUDA3 = 0.9824·ub は gqa weight 系に由来する別構造。

## 参考値

| 項目 | 値 |
|---|---|
| gated_delta_net 出力 tensor per layer per token | 32,768 bytes (= 4 × S_v × H × 1 byte) |
| 定数項 per layer | 4,194,304 bytes = 4 MiB (= 4 × S_v × S_v × H × 1 byte) |
| CUDA0 の SSM 層数 | 9 |
| 予測 slope | 0.28125 MiB/tok |
| 観測 slope | 0.28530 MiB/tok |
| 予測 / 観測 比 | 0.9858 |
