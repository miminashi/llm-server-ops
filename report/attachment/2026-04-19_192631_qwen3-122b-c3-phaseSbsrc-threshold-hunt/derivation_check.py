#!/usr/bin/env python3
"""
Phase Sb-src: Qwen3.5-122B-A10B (qwen35moe) で観測された CUDA0 compute buffer の
境界 ub*=1586 と線形域 slope 0.2853 MiB/tok の由来を、llama.cpp ソースから特定した
式で数値検証する。

観測値 (Phase Sb-fine3 より):
  - ub ≤ 1585: 平坦 (slope 0.0125 MiB/tok)
  - ub ≥ 1586: 線形 (slope 0.2853 MiB/tok, 8 点 max_err 0.008 MiB)
  - CUDA0 のみ step 化、他 GPU は純線形または不変

モデル hparams (起動ログより抽出):
  arch                 = qwen35moe
  n_embd               = 3072
  n_layer              = 48
  n_head               = 32
  n_head_kv            = 2
  n_embd_head_k/v      = 256
  n_embd_k_gqa/v_gqa   = 512
  full_attention_interval = 4  (=> 12 attn + 36 SSM layers)
  ssm_d_inner          = 8192
  ssm_d_state          = 128
  ssm_n_group          = 16      (num_k_heads in SSM path)
  ssm_dt_rank          = 64      (num_v_heads in SSM path)
  head_k_dim           = 128     (= ssm_d_state)
  head_v_dim           = 128     (= ssm_d_inner / num_v_heads = 8192/64)
  S_v (CUDA kernel)    = head_v_dim = 128
  H   (CUDA kernel)    = num_v_heads = 64
"""

import math

# ----------- モデル hparams -----------
N_EMBD = 3072
N_LAYER = 48
N_HEAD = 32
N_HEAD_KV = 2
N_EMBD_HEAD = 256
N_EMBD_K_GQA = 512  # n_head_kv * n_embd_head
N_EMBD_V_GQA = 512
FULL_ATTN_INTERVAL = 4

SSM_D_INNER = 8192
SSM_D_STATE = 128
SSM_N_GROUP = 16       # num_k_heads
SSM_DT_RANK = 64       # num_v_heads
SSM_D_CONV = 4

# CUDA kernel tensor dims (from qwen35moe.cpp:205-210)
HEAD_K_DIM = SSM_D_STATE           # 128
HEAD_V_DIM = SSM_D_INNER // SSM_DT_RANK  # 8192/64 = 128
NUM_K_HEADS = SSM_N_GROUP          # 16
NUM_V_HEADS = SSM_DT_RANK          # 64
S_V = HEAD_V_DIM                   # 128 (CUDA kernel S_v)
H   = NUM_V_HEADS                  # 64  (CUDA kernel H)

N_CTX = 32768

# ----------- レイヤ分散 -----------
N_ATTN_LAYERS = N_LAYER // FULL_ATTN_INTERVAL  # 48/4 = 12
N_SSM_LAYERS  = N_LAYER - N_ATTN_LAYERS        # 36
LAYERS_PER_GPU = N_LAYER // 4                  # 12 layers/GPU (4 GPUs)
ATTN_PER_GPU = N_ATTN_LAYERS // 4              # 3 attn/GPU
SSM_PER_GPU  = N_SSM_LAYERS // 4               # 9 SSM/GPU

print(f"=== レイヤ分散 ===")
print(f"  attn layers: {N_ATTN_LAYERS} total, {ATTN_PER_GPU}/GPU")
print(f"  SSM layers : {N_SSM_LAYERS} total, {SSM_PER_GPU}/GPU")

MIB = 1024 * 1024


# =============================================
# 仮説 1: ggml_gated_delta_net 出力テンソルのサイズ
# (ggml/src/ggml.c:6202)
# ne = {S_v * H, n_tokens*n_seqs + S_v*n_seqs, 1, 1}, F32 (4 bytes/elem)
# 1 SSM layer 1 GPU あたり:
#   elements = S_v * H * (n_tokens + S_v)  [n_seqs=1]
#   bytes    = 4 * S_v * H * (n_tokens + S_v)
# CUDA0 の 9 SSM layers 合計（allocator 再利用なしの場合）:
# =============================================
def gdn_output_bytes_per_gpu(n_tokens, n_ssm_layers):
    """SSM output tensor size from ggml_gated_delta_net for a given GPU."""
    per_layer = 4 * S_V * H * (n_tokens + S_V)  # F32
    return per_layer * n_ssm_layers


# =============================================
# 仮説 2: FA tile kernel の dst_tmp
# (ggml/src/ggml-cuda/fattn-common.cuh:1121-1123)
# P100 (CC 6.0) + head_dim=256 → TILE kernel
# ncols2=8 (gqa_ratio=16), ncols1=4 (cols_per_block=32 / 8)
# nbatch_fa=64 (from fattn-tile.cuh)
# dst_tmp = parallel_blocks * ggml_nelements(KQV) = parallel_blocks * head_dim * n_head * n_tokens * n_seqs
# =============================================
NBATCH_FA = 64
P100_NSM = 56
NCOLS1 = 4
NCOLS2 = 8

def fa_dst_tmp_bytes_per_gpu(n_tokens, parallel_blocks, n_attn_layers):
    """FA dst_tmp size per GPU."""
    if parallel_blocks <= 1:
        return 0
    kqv_elems = N_EMBD_HEAD * N_HEAD * n_tokens * 1  # n_seqs=1
    per_layer = 4 * parallel_blocks * kqv_elems  # F32
    return per_layer * n_attn_layers


# =============================================
# 仮説 3: FA launch における ntiles_dst の境界
# ntiles_x = ceil(n_tokens / ncols1) = ceil(n_tokens / 4)
# 境界 = 4 の倍数
# =============================================


# =============================================
# 検証 1: slope 0.2853 MiB/tok が 9 SSM layers × 32,768 bytes/tok に一致するか
# =============================================
print("\n=== 検証 1: ub ≥ 1586 線形域 slope 0.2853 MiB/tok の由来 ===")

observed_slope_per_tok = 0.2853 * MIB  # bytes/tok
print(f"  観測 slope: {observed_slope_per_tok:,.0f} bytes/tok  ({observed_slope_per_tok/MIB:.4f} MiB/tok)")

# Gated Delta Net 出力の per-token 線形項: S_v * H * f32 per layer
ssm_linear_per_layer_per_tok = 4 * S_V * H  # bytes/tok
print(f"  SSM 1 layer の n_tokens 線形項: {S_V}*{H}*4 = {ssm_linear_per_layer_per_tok:,.0f} bytes/tok  ({ssm_linear_per_layer_per_tok/MIB:.4f} MiB/tok)")

# CUDA0 の 9 SSM layers
ssm_cuda0_slope = ssm_linear_per_layer_per_tok * SSM_PER_GPU
print(f"  CUDA0 (9 SSM layers): {ssm_cuda0_slope:,.0f} bytes/tok  ({ssm_cuda0_slope/MIB:.4f} MiB/tok)")

diff_abs = observed_slope_per_tok - ssm_cuda0_slope
diff_pct = 100.0 * diff_abs / observed_slope_per_tok
print(f"  差分: {diff_abs:+,.0f} bytes/tok ({diff_pct:+.2f}%)  [page/align 等の補正余地]")
print(f"  → 判定: {'一致（SSM 出力テンソルが主因）' if abs(diff_pct) < 2.0 else '不一致'}")

# FA dst_tmp (parallel_blocks=3 を仮定) の比較
print("\n  比較: FA dst_tmp (P100 tile kernel) の寄与仮説")
for pb in [1, 2, 3, 4]:
    fa_contrib = fa_dst_tmp_bytes_per_gpu(10000, pb, ATTN_PER_GPU) / 10000  # per-token
    print(f"    parallel_blocks={pb}: {fa_contrib:,.0f} bytes/tok ({fa_contrib/MIB:.4f} MiB/tok)")

# =============================================
# 検証 2: 境界 ub*=1586 が何由来かの候補
# =============================================
print("\n=== 検証 2: 境界 ub*=1586 の候補式 ===")

# 候補 A: CS=64 chunking (KDA=false だが fused_gdn_ch enabled で実際には使われない)
# chunk transition at ceil(ub/64) の変化点: 1536→1537, 1600→1601
print("  候補 A: delta-net-base.cpp CS=64 chunking (KDA=false)")
for ub in [1584, 1585, 1586, 1587, 1588, 1592, 1600, 1601]:
    pad = (64 - ub % 64) % 64
    n_chunks = (ub + pad) // 64
    print(f"    ub={ub}: pad={pad:2d}, n_chunks={n_chunks}")
print("  → KDA=false で CS=64 の場合、境界は 1536→1537 と 1600→1601。1585→1586 ではない。")
print("  → かつ runtime log で fused_gdn_ch=enabled → chunking path は使われない。")

# 候補 B: CS=16 chunking (KDA=true の場合)
# 1584→1585 transitions
print("\n  候補 B: delta-net-base.cpp CS=16 chunking (KDA=true の場合)")
for ub in [1583, 1584, 1585, 1586, 1588, 1600]:
    pad = (16 - ub % 16) % 16
    n_chunks = (ub + pad) // 16
    print(f"    ub={ub}: pad={pad:2d}, n_chunks={n_chunks}")
print("  → CS=16 で境界は 1584→1585。観測 1585→1586 と 1-tok オフ。")
print("  → さらに qwen35moe は KDA=false (g->ne[0]=1) なので CS=16 パスには入らない。")

# 候補 C: FA tile kernel ntiles_x = ceil(n_tokens / 4)
# Transition at multiples of 4: 1584, 1588, 1592, ...
print("\n  候補 C: FA tile kernel ntiles_x = ceil(n_tokens / ncols1=4)")
for ub in [1584, 1585, 1586, 1587, 1588, 1592]:
    ntiles_x = (ub + NCOLS1 - 1) // NCOLS1
    ntiles_dst = ntiles_x * 2 * 2 * 1  # ntiles_z_gqa=ceil(16/8)=2, K->ne[2]=2, Q->ne[3]=1
    print(f"    ub={ub}: ntiles_x={ntiles_x}, ntiles_dst={ntiles_dst}")
print("  → FA の境界は 4 の倍数 (1584, 1588, 1592)。1585→1586 とは一致しない。")

# 候補 D: ggml graph allocator による pool quantization
# 確認: SSM output tensor size を pool 境界で評価
print("\n  候補 D: SSM 出力テンソルの累積が allocator pool 境界を超える点")
for ub in [1580, 1584, 1585, 1586, 1587, 1590, 1600]:
    ssm_out_bytes = gdn_output_bytes_per_gpu(ub, SSM_PER_GPU)
    print(f"    ub={ub}: CUDA0 SSM output 累積 = {ssm_out_bytes:,} bytes = {ssm_out_bytes/MIB:.3f} MiB")
print("  → pool chunk size が特定値 (例 1 MiB) の場合、累積が境界を越える ub で step.")

# =============================================
# 検証 3: ub=1586 への 9 SSM layers 累積が 1 MiB 境界を越えるか
# SSM output per layer at n_tokens=N: 4 * 128 * 64 * (N + 128) = 32768 * (N + 128) bytes
# At N=1585: per layer = 32768 * 1713 = 56,131,584 bytes ≈ 53.532 MiB
# At N=1586: per layer = 32768 * 1714 = 56,164,352 bytes ≈ 53.563 MiB
# 9 layers (if independent):
#   N=1585: 9 * 53.532 = 481.786 MiB
#   N=1586: 9 * 53.563 = 482.066 MiB
# =============================================
print("\n=== 検証 3: 9 SSM 層の SSM 出力累積値と pool 量子化境界 ===")
for ub in [1584, 1585, 1586, 1588, 1592, 1600]:
    per_layer = 4 * S_V * H * (ub + S_V)
    total = per_layer * SSM_PER_GPU
    # MiB 境界単位での quantization
    q1mib = math.ceil(total / MIB) * MIB
    pad_bytes = q1mib - total
    print(f"  ub={ub}: per-layer={per_layer/MIB:.4f} MiB, 9 layers={total/MIB:.4f} MiB, "
          f"1 MiB 境界={q1mib/MIB:.0f} MiB, pad={pad_bytes:,}")

# =============================================
# 検証 4: TG 用 graph_reserve との max の境界
# TG 用は n_tokens=1 で固定、PP 用は n_tokens=ub
# =============================================
print("\n=== 検証 4: TG/PP 比較（TG は n_tokens=1 固定） ===")

# TG は n_tokens=1 → 定数項のみ
tg_ssm_bytes = 4 * S_V * H * (1 + S_V) * SSM_PER_GPU
print(f"  TG (n_tokens=1) CUDA0 SSM output: {tg_ssm_bytes/MIB:.4f} MiB")

# PP は n_tokens=ub → 線形
# 実測 slope 0.2853 MiB/tok, offset = 1002.61 - 0.2853 * 1664 = 527.95 MiB (ub=0 外挿)
offset = 1002.61 - 0.2853 * 1664
print(f"  PP 線形モデル: {offset:.2f} + 0.2853 × ub")
print(f"    ub=1:    {offset + 0.2853:.2f} MiB")
print(f"    ub=1585: {offset + 0.2853 * 1585:.2f} MiB (観測 980.12)")
print(f"    ub=1586: {offset + 0.2853 * 1586:.2f} MiB (観測 980.36)")

print("\n=== まとめ ===")
print(f"  (1) slope 0.2853 MiB/tok は 9 SSM layers × gated_delta_net 出力の n_tokens 線形項 = 0.28125 MiB/tok")
print(f"      で説明可能（誤差 {diff_pct:+.2f}%、残差 {diff_abs:+,.0f} bytes/tok は align/padding 由来）")
print(f"  (2) 境界 ub*=1586 は CS=16/64 chunking / FA ncols1=4 のいずれの整数閾値とも一致しない")
print(f"      → ソース単独の整数定数 / chunk_size 閾値では説明できない")
print(f"  (3) 最有力仮説: ggml graph allocator の pool quantization と SSM 出力累積の相互作用")
print(f"      - ub ≤ 1585: 既存 reserve pool 内で SSM 累積が収まる → 平坦域")
print(f"      - ub ≥ 1586: pool 境界超過 → 線形確保が発動")
print(f"  (4) 次 Phase で必要:")
print(f"      - ctx 依存性の検証 (ctx=16k/65k/131k で ub* が同じか)")
print(f"      - KV quant (q8_0) / fa=0 での境界位置")
print(f"      - ggml-alloc.c の tensor_fit / worst_alloc ロジックの詳細解析")
