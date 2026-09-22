#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SKILL_DIR")")")"

# .envからHF_TOKENを読み込み（プロジェクトルート → ~/.config/gpu-server/.env の順）
ENV_FILE=""
if [ -f "$PROJECT_ROOT/.env" ]; then
  ENV_FILE="$PROJECT_ROOT/.env"
elif [ -f "${LLM_SERVER_ENV:-${HOME}/.config/gpu-server/.env}" ]; then
  ENV_FILE="${LLM_SERVER_ENV:-${HOME}/.config/gpu-server/.env}"
fi
if [ -n "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

# HF_TOKENが未設定の場合、対話的にセットアップ
if [ -z "${HF_TOKEN:-}" ]; then
  if [ -t 0 ]; then
    echo "==> HF_TOKEN が設定されていません。HuggingFace トークンを入力してください。"
    echo "    トークンは https://huggingface.co/settings/tokens で取得できます。"
    while true; do
      read -rp "HF_TOKEN: " HF_TOKEN_INPUT
      # CR・前後空白を除去（ペースト時の不可視文字対策）
      HF_TOKEN_INPUT="${HF_TOKEN_INPUT%$'\r'}"
      HF_TOKEN_INPUT="${HF_TOKEN_INPUT#"${HF_TOKEN_INPUT%%[![:space:]]*}"}"
      HF_TOKEN_INPUT="${HF_TOKEN_INPUT%"${HF_TOKEN_INPUT##*[![:space:]]}"}"
      if [ -z "$HF_TOKEN_INPUT" ]; then
        echo "    スキップします（認証なしでダウンロードを試みます）"
        break
      fi
      # トークンの有効性を検証
      RESPONSE=$(curl -sS -w '\n%{http_code}' \
        -H "Authorization: Bearer $HF_TOKEN_INPUT" \
        https://huggingface.co/api/whoami-v2)
      HTTP_CODE=$(echo "$RESPONSE" | tail -1)
      if [ "$HTTP_CODE" = "200" ]; then
        echo "    トークンは有効です。保存します..."
        HF_TOKEN="$HF_TOKEN_INPUT"
        # 永続化先を決定
        SAVE_TARGET=""
        if [ -n "$ENV_FILE" ]; then
          SAVE_TARGET="$ENV_FILE"
        elif [ -f "$PROJECT_ROOT/.env" ]; then
          SAVE_TARGET="$PROJECT_ROOT/.env"
        else
          SAVE_TARGET="${HOME}/.config/gpu-server/.env"
          mkdir -p "${HOME}/.config/gpu-server"
        fi
        echo "HF_TOKEN=$HF_TOKEN" >> "$SAVE_TARGET"
        chmod 600 "$SAVE_TARGET"
        echo "    保存完了: $SAVE_TARGET"
        break
      else
        BODY=$(echo "$RESPONSE" | sed '$d')
        echo "    トークンが無効です（HTTP $HTTP_CODE: $BODY）。再入力してください（空入力でスキップ）。"
      fi
    done
  else
    echo "WARNING: HF_TOKEN が未設定です。認証が必要なモデルのダウンロードは失敗する可能性があります。" >&2
  fi
fi

usage() {
  cat <<'EOF'
Usage: start.sh <server> <hf-model> [ctx-size|fit] [fit-ctx]

Arguments:
  server     GPUサーバ名 (mi25, t120h-p100, t120h-m10, aws-gpu01, aws-gpu02, aws-v100)
  hf-model   HuggingFaceモデル (例: unsloth/gpt-oss-20b-GGUF:Q8_0)
  ctx-size   コンテキストサイズ or "fit" (省略時: 65536)
  fit-ctx    fitモード時のctx-size ("fit"指定時のみ有効)
             - Qwen3.5-122B-A10B: 省略時 131072 (Phase U-6 確定 128k default)
             - その他 MoE       : 省略時 8192

Examples:
  start.sh t120h-p100 "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M" 131072
  start.sh mi25 "unsloth/gpt-oss-20b-GGUF:Q8_0"
  start.sh t120h-p100 "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit         # 128k default
  start.sh t120h-p100 "unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M" fit 32768   # 短 ctx 指定
EOF
  exit 1
}

# --- 引数チェック ---
if [ $# -lt 1 ]; then
  usage
fi

SERVER="$1"
HF_MODEL="${2:-}"
CTX_SIZE_ARG="${3:-65536}"
FIT_CTX_ARG="${4:-}"

# fitモード判定
if [ "$CTX_SIZE_ARG" = "fit" ]; then
  FIT_MODE=true
  CTX_SIZE="fit"
else
  FIT_MODE=false
  CTX_SIZE="$CTX_SIZE_ARG"
fi

if [ -z "$HF_MODEL" ]; then
  echo "ERROR: モデルが指定されていません。" >&2
  echo "Claude側で AskUserQuestion を使ってモデルを選択してください。" >&2
  exit 1
fi

# --- モデルプロファイル判定 ---
# Phase U-6 (2026-04-24) で確定した Qwen3.5-122B-A10B 向け ctx=128k 専用 default 構成を
# モデル名で自動適用する。他モデルは従来挙動。
MODEL_PROFILE="generic"
case "$HF_MODEL" in
  *Qwen3.5-122B-A10B*)
    MODEL_PROFILE="qwen3_122b"
    ;;
esac

# fit 時の ctx-size default はプロファイル依存 (qwen3_122b: 131072、その他: 8192)
if [ -z "$FIT_CTX_ARG" ]; then
  if [ "$MODEL_PROFILE" = "qwen3_122b" ]; then
    FIT_CTX=131072
  else
    FIT_CTX=8192
  fi
else
  FIT_CTX="$FIT_CTX_ARG"
fi

# --- サーバ名バリデーション ---
case "$SERVER" in
  mi25|t120h-p100|t120h-m10|aws-gpu01|aws-gpu02|aws-v100) ;;
  *)
    echo "ERROR: 不明なサーバ: $SERVER" >&2
    echo "有効なサーバ: mi25, t120h-p100, t120h-m10, aws-gpu01, aws-gpu02, aws-v100" >&2
    exit 1
    ;;
esac

# --- GPU 枚数検出ヘルパ ---
# RADV 物理 GPU の Vulkan index をカンマ連結で返す（llvmpipe/lavapipe=CPU を除外）。
# vulkaninfo --summary の各 GPUn ブロックを走査し、deviceType=PHYSICAL_DEVICE_TYPE_CPU
# （= llvmpipe/lavapipe）を除いた index のみを列挙する（例 実効3枚→ "0,1,2" / 4枚→ "0,1,2,3"）。
# この index は vulkaninfo の GPUn 列挙順 = ggml-vulkan の Vulkann 列挙順と一致する（実機確認済み）。
# ただし ICD のデバイス列挙順の安定性に依存するため、ドライバ/Mesa 更新時は要再確認。
# vulkaninfo 不在/失敗時は空文字を返す（呼び出し側でフォールバックする）。
detect_radv_vk_indices() {
  local srv="$1"
  ssh "$srv" 'vulkaninfo --summary 2>/dev/null' 2>/dev/null | awk '
    /^GPU[0-9]+:/ { match($0, /[0-9]+/); idx = substr($0, RSTART, RLENGTH); have = 1; is_cpu = 0; next }
    have && /deviceType/  { if ($0 ~ /PHYSICAL_DEVICE_TYPE_CPU/) is_cpu = 1 }
    have && /deviceName/  {
      if (is_cpu || $0 ~ /llvmpipe|lavapipe/) { } else { out = out (out == "" ? "" : ",") idx }
      have = 0
    }
    END { print out }'
}

# 実効 GPU 枚数が期待を下回る場合に stderr へ警告を出す（起動は中断しない）。
# actual が空/0/非数値（検出不能）なら誤警告を避けるため何もしない。
# 注: 数値ガードを -lt 比較の前に置くこと（空/非数値での算術エラー→ set -e 中断を防ぐ）。
warn_gpu_degraded() {
  local srv="$1" actual="$2" expected="$3"
  case "$actual" in
    ''|*[!0-9]*) return 0 ;;
  esac
  if [ "$actual" -lt "$expected" ]; then
    echo "WARNING: $srv の実効 GPU 枚数が ${actual} 枚です（期待 ${expected} 枚）。GPU 脱落の可能性があります。" >&2
    echo "         実効枚数で VRAM が不足する場合はモデルロード時に llama-server 自体が失敗します。起動は継続します。" >&2
  fi
  return 0
}

# --- 既存プロセス確認 ---
# build/bin (HIP/CUDA) と build-vulkan/bin (Vulkan) の双方を検出するため bin/llama-server で照合。
echo "==> $SERVER の既存 llama-server プロセスを確認中..."
EXISTING=$(ssh "$SERVER" "pgrep -a -f 'bin/llama-server'" || true)
if [ -n "$EXISTING" ]; then
  echo "WARNING: $SERVER で llama-server が既に起動中です:" >&2
  echo "$EXISTING" >&2
  echo "" >&2
  echo "既存プロセスを終了してから再実行してください。" >&2
  exit 1
fi

# --- ビルドスクリプト転送・実行 ---
BUILD_SCRIPT="$SKILL_DIR/server-scripts/update_and_build-${SERVER}.sh"
if [ ! -f "$BUILD_SCRIPT" ]; then
  echo "ERROR: ビルドスクリプトが見つかりません: $BUILD_SCRIPT" >&2
  exit 1
fi

echo "==> ビルドスクリプトを $SERVER に転送中..."
scp -q "$BUILD_SCRIPT" "${SERVER}:~/llama.cpp/update_and_build.sh"
ssh "$SERVER" "chmod +x ~/llama.cpp/update_and_build.sh"

echo "==> llama.cpp を更新・ビルド中..."
# MI25_BACKEND (hip|vulkan) をリモートビルドへ透過。mi25 の update_and_build がバックエンドを分岐する。
ssh "$SERVER" "cd ~/llama.cpp && MI25_BACKEND='${MI25_BACKEND:-}' ./update_and_build.sh"

# --- サーバ別パラメータ設定 ---
SERVER_OPTS=""
ENV_PREFIX=""
THREADS_OPT="--threads -1"
# llama-server バイナリパス (バックエンドで切替)。既定は build/ (HIP/CUDA)。
LLAMA_BIN="./build/bin/llama-server"

case "$SERVER" in
  mi25)
    # MI25 (gfx900/ROCm) x4 = 64GB。llama.cpp は -fa auto がデフォルトで Flash-Attention を
    # 有効化するが、split-mode layer で層が GPU0 に偏り、FA tile カーネルの compute buffer
    # (ubatch 比例) で GPU0 が 16GiB を超え OOM する。Qwen3.6-35B-A3B / ctx=131072 / KV q8_0 で:
    #   ub=4096: ロード時 GPU0 16.8/16 GiB、32k プロンプトで OOM クラッシュ。
    #   ub=2048: GPU0 12.3 GiB に収まり 131k 安定。prompt 122.8 t/s / eval 24.5 t/s (32k 計測)。
    #   ub=3072: GPU0 15.0 GiB かつ prompt 99.3 t/s (ub=2048 より遅い) で不利。
    # → gfx900 では ub=2048 が速度・VRAM 両面の最適点。--flash-attn 1 を明示し auto 挙動に依存しない。
    # なお mi25 の llama.cpp は update_and_build-mi25.sh で gfx900 ビルド可能コミットに pin 済み
    # (master は __hip_fp8_e4m3 型を gfx900 で参照しビルド不能)。詳細は
    # report/2026-06-13_*_mi25_qwen36_128k.md。
    SERVER_OPTS="--flash-attn 1 --poll 0 -b 2048 -ub 2048"
    # Vulkan (RADV) バックエンド: build-vulkan/ のバイナリを使い、llvmpipe (CPU) を除外する。
    # 【可視性の動的検出】MI25 は SLOT4 等の PCIe 物理層障害で実効枚数が変動する (4枚⇄3枚、間欠的。
    # report/2026-06-14_131713_mi25_gpu4_pcie_dropout.md)。vulkaninfo の列挙は「RADV VEGA10 × 実効枚数
    # ＋ 末尾に llvmpipe(CPU)」となるため、起動前に vulkaninfo で RADV 物理 GPU の index のみを検出して
    # GGML_VK_VISIBLE_DEVICES に設定する (実効3枚→0,1,2 / 4枚→0,1,2,3)。旧来の固定値 0,1,2,3 は
    # 3枚構成時に index 3 の llvmpipe を拾い ErrorOutOfDeviceMemory で破綻していた
    # (report/2026-06-18_084557_mi25_vulkan_param_sweep.md)。index は vulkaninfo GPUn 順 =
    # ggml-vulkan Vulkann 順と一致 (--list-devices で実機確認済み・ICD 列挙順に依存)。
    # Vulkan は HIP の FP8 型問題に無関係なため pin 不要 (build-vulkan は master 追従)。
    # 探索結果 (report/2026-06-14_001107_mi25_vulkan_qwen36_128k.md): ub は VRAM/速度に
    # ほぼ無影響 (GPU0 8.72GB 一定・prompt ~405 t/s 一定で ub=4096 でも OOM せず) なので
    # ROCm と同じ ub=2048 を踏襲。prompt は ROCm の約3.3倍、eval は約0.6倍。FA=0+q8_0 は不可
    # (V cache quantization requires flash_attn)。KV を f16 にすると高負荷でホストが不安定
    # になる事象を観測したため本番は q8_0 のままにすること。EXTRA_LLAMA_OPTS で上書き可。
    if [ "${MI25_BACKEND:-vulkan}" = "vulkan" ]; then
      LLAMA_BIN="./build-vulkan/bin/llama-server"
      # set -o pipefail 下でも落ちないよう || true でガード。
      MI25_VK_IDX=$(detect_radv_vk_indices "$SERVER" || true)
      if [ -n "$MI25_VK_IDX" ]; then
        ENV_PREFIX="GGML_VK_VISIBLE_DEVICES=$MI25_VK_IDX"
        MI25_GPU_COUNT=$(printf '%s' "$MI25_VK_IDX" | awk -F, '{print NF}' || true)
        echo "    Vulkan: RADV 物理 GPU を検出 → GGML_VK_VISIBLE_DEVICES=$MI25_VK_IDX (${MI25_GPU_COUNT}枚)"
      else
        # 検出失敗 (vulkaninfo 不在/失敗): 環境変数ごと渡さず ggml の自動選択に委ねる。
        # 空代入 (GGML_VK_VISIBLE_DEVICES=) は「デバイス0個」と解釈され全滅しうるため厳禁。
        ENV_PREFIX=""
        echo "WARNING: mi25 で RADV GPU を検出できませんでした (vulkaninfo 不在/失敗)。" >&2
        echo "         GGML_VK_VISIBLE_DEVICES を未設定で起動します (ggml 自動選択。現行 master は llvmpipe を除外する)。" >&2
        echo "         /tmp/llama-server.log で実 GPU 数 (Vulkan0..) を確認してください。" >&2
        MI25_GPU_COUNT=""
      fi
    else
      # ROCm(hip): 可視性は触らない (auto で実効枚数のみ使用)。枚数は rocminfo の gfx900 Agent 数で
      # best-effort 検出 ('Name:' 行に限定。rocm-smi は脱落時に誤って4枚列挙した実績があり使わない)。
      MI25_GPU_COUNT=$(ssh "$SERVER" "rocminfo 2>/dev/null | grep -cE '^[[:space:]]*Name:[[:space:]]*gfx900'" 2>/dev/null || true)
    fi
    warn_gpu_degraded "$SERVER" "${MI25_GPU_COUNT:-}" 4
    ;;
  t120h-p100)
    # -ub は 4096。8192 は CUDA OOM (2026-06-02 の llama.cpp master リグレッション)。
    # 経緯: 2026-06-02 頃の master で 1 ubatch あたりの compute buffer 確保が約2倍に増加し、
    # Qwen3.6-35B-A3B / ctx=131072 / KV q8_0 では ub=8192 だとロード時点で VRAM 15.3/16 GiB
    # (空き ~0.6 GiB)。2回目以降の大リクエストで VMM プール (ggml_cuda_pool_vmm::alloc /
    # cuMemCreate) が成長しきれず device 0 で out of memory・クラッシュした。
    # ub=4096 でロード時 VRAM が 10.6 GiB (空き ~5.4 GiB) に下がり OOM 解消。eval ~39 t/s 維持、
    # context checkpoint も有効のまま (同一プレフィクスの再リクエストは ~3倍高速)。
    # 詳細は report/2026-06-03_*_llama_cpp_oom_regression_fix.md。
    SERVER_OPTS="--flash-attn 1 --poll 0 -b 4096 -ub 4096"
    # CUDA は可視性を触らない (auto で実効枚数のみ使用)。期待 4 枚に対する枚数チェックのみ行う。
    # nvidia-smi の index 行数で枚数を取得し、tr で数字以外を除去して堅牢化。
    P100_GPU_COUNT=$(ssh "$SERVER" "nvidia-smi --query-gpu=index --format=csv,noheader 2>/dev/null | wc -l" 2>/dev/null | tr -dc '0-9' || true)
    warn_gpu_degraded "$SERVER" "${P100_GPU_COUNT:-}" 4
    ;;
  t120h-m10)
    ENV_PREFIX="CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14"
    SERVER_OPTS="-b 4096 -ub 4096"
    ;;
  aws-gpu01)
    # Supermicro SYS-4028GR-TRT2。Tesla P100-PCIE 16GB x7 = 112GB (全 Gen3 x16)。
    # t120h-p100 と同じ P100 (sm60) なので、実績のある -b 4096 -ub 4096 を踏襲する
    # (ub=8192 は 2026-06-02 の llama.cpp master リグレッションで CUDA OOM。
    #  詳細は t120h-p100 の分岐コメントと report/2026-06-03_*_llama_cpp_oom_regression_fix.md)。
    # 未検証: 本サーバでの llama-server 起動は 2026-08-16 時点で未実施。初回起動時に
    #         VRAM 実測を取り、必要なら ub を調整すること。
    SERVER_OPTS="--flash-attn 1 --poll 0 -b 4096 -ub 4096"
    AWS_GPU01_COUNT=$(ssh "$SERVER" "nvidia-smi --query-gpu=index --format=csv,noheader 2>/dev/null | wc -l" 2>/dev/null | tr -dc '0-9' || true)
    warn_gpu_degraded "$SERVER" "${AWS_GPU01_COUNT:-}" 7
    ;;
  aws-gpu02)
    # Supermicro SYS-4028GR-TRT。Tesla P100-PCIE 16GB x4 + 12GB x2 = 88GB (全 Gen3 x16)。
    # 注意: VRAM 容量が不均等 (16/16/16/12/16/12 GB) なので、t120h-p100 の
    #       --tensor-split 11,12,13,14 系プロファイルはそのまま流用できない。
    #       大きなモデルを載せる場合は 12GB 枚 (index 3, 5) に合わせた split が必要。
    # 未検証: 本サーバでの llama-server 起動は 2026-08-16 時点で未実施。
    SERVER_OPTS="--flash-attn 1 --poll 0 -b 4096 -ub 4096"
    AWS_GPU02_COUNT=$(ssh "$SERVER" "nvidia-smi --query-gpu=index --format=csv,noheader 2>/dev/null | wc -l" 2>/dev/null | tr -dc '0-9' || true)
    warn_gpu_degraded "$SERVER" "${AWS_GPU02_COUNT:-}" 6
    ;;
  aws-v100)
    # ASRock X99 Taichi + Tesla V100-SXM2 16GB x2 = 32GB (sm_70)。SXM2→PCIe 変換基板のため
    # NVLink は非活性 (topo PHB)。リンクは GPU0 Gen3 x8 / GPU1 Gen2 x8 (00:03.0 配下で
    # Correctable AER RxErr が多発し Gen2 に落ちている、2026-09-23 確認)。
    # -b/-ub は P100 系と同じ 4096 を初期値にした。初回起動時に VRAM 実測を取り、必要なら調整すること。
    SERVER_OPTS="--flash-attn 1 --poll 0 -b 4096 -ub 4096"
    AWS_V100_COUNT=$(ssh "$SERVER" "nvidia-smi --query-gpu=index --format=csv,noheader 2>/dev/null | wc -l" 2>/dev/null | tr -dc '0-9' || true)
    warn_gpu_degraded "$SERVER" "${AWS_V100_COUNT:-}" 2
    ;;
esac

# --- モデルプロファイル上書き (サーバ別 default を上書き) ---
# Phase U-6 (2026-04-24) 確定構成: Qwen3.5-122B-A10B × t120h-p100 × ctx=128k
# -b 2048 / -ub 512 / tensor-split 11,12,13,14 / threads 40 / numactl node1
if [ "$MODEL_PROFILE" = "qwen3_122b" ] && [ "$SERVER" = "t120h-p100" ]; then
  SERVER_OPTS="--flash-attn 1 --poll 0 -b 2048 -ub 512 --tensor-split 11,12,13,14"
  ENV_PREFIX="numactl --cpunodebind=1 --membind=1"
  THREADS_OPT="--threads 40"
fi

# --- モデル別サンプリングパラメータ ---
# Qwen3.x thinking モードは opencode 等の長コンテキストで段落単位の verbatim ループに陥ることがある。
# Qwen 公式推奨レンジ (0〜2) の presence_penalty を 1.0 で常用し、DRY サンプラはサーバ default では
# 完全無効化 (--dry-multiplier 0、llama.cpp default 値と同じ) する。DRY は long path / 識別子の末尾を
# 切り落とす副作用が greedy decoding でも観測されたため、必要なクライアントだけがリクエスト側で
# dry_multiplier を送る運用にしている。
# 経緯:
#   fed12136          : presence_penalty=1.0 + DRY=0.8 default 有効化 → URL/IP 数字書換の副作用
#   2026-05-26 #1     : DRY allowed-length=4 + breakers `. / _` (実は最後の '_' だけ有効) で URL 改善
#   2026-05-26 #2     : `-` 追加 + presence_penalty=0.5 緩和 → path の数字/文字書換は止まったが、
#                       greedy + dry_multiplier=0 でないと末尾 (.1.0/config/... 等) が切れる
#   2026-05-26 #3     : DRY サーバ default を 0 (無効) に。thinking ループ抑制は presence_penalty 0.5
#                       単独で対応。クライアントが必要なら dry_multiplier をリクエスト側で送れる。
#   2026-05-26 #4     : ytdlor セッションで Active Storage 文脈の段落 verbatim ループ再発 (同一段落
#                       10 回以上反復) を観測。presence_penalty=0.5 単独では長距離段落反復に抑制不足と
#                       判断し、presence_penalty を 1.0 へ引き上げ。fed12136 時の URL 副作用は DRY=0.8
#                       が原因 (greedy decoding で再現済) であり、presence_penalty 単独 1.0 では
#                       URL/path リグレッションは観測されない。
# それでも verbatim ループが再発した場合は、クライアント側で dry_multiplier=0.4 程度を送る運用に
# 切り替える (SKILL.md 参照)。
case "$HF_MODEL" in
  *Qwen3.5*|*Qwen3.6*)
    SAMPLING_OPTS="--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 --presence-penalty 1.0 --dry-multiplier 0"
    ;;
  *)
    SAMPLING_OPTS="--temp 1.0 --top-p 1.0 --top-k 0"
    ;;
esac

# --- MTP (Multi-Token Prediction) 自動検出 ---
# llama.cpp 2026-05-16 マージの speculative decoding 機能。
# リポジトリ名に "MTP" を含むモデル（unsloth の Qwen3.6-*-MTP-GGUF 等）で自動有効化。
# MTP draft context は追加 compute buffer を要するため、t120h-p100 では
# サーバデフォルトの -b 8192 -ub 8192 だと P100 単体 (16 GiB) で OOM。
# batch を縮小して fit させる。
SPEC_OPTS=""
case "$HF_MODEL" in
  *MTP*)
    SPEC_OPTS="--spec-type draft-mtp --spec-draft-n-max 6"
    if [ "$SERVER" = "t120h-p100" ]; then
      SERVER_OPTS="--flash-attn 1 --poll 0 -b 2048 -ub 512"
    fi
    ;;
esac

# --- チャットテンプレートオプション ---
CHAT_TEMPLATE_OPTS="--jinja"

# --- モデルパス解決 & エイリアス ---
# HF_MODEL が絶対パス (先頭 '/' かつ拡張子 .gguf) の場合はローカルパス直接指定として扱い、
# HF ダウンロードをスキップする。それ以外は "org/repo:quantization" 形式として HF キャッシュを
# 参照し、無ければ hf CLI でダウンロードする。
if [[ "$HF_MODEL" == /*.gguf ]]; then
  MODEL_PATH="$HF_MODEL"
  ALIAS="$(basename "${HF_MODEL%.gguf}")"
  echo "==> ローカルパス指定を検出: $MODEL_PATH"
  if ! ssh "$SERVER" "test -f '$MODEL_PATH'"; then
    echo "ERROR: $SERVER にファイルが見つかりません: $MODEL_PATH" >&2
    exit 1
  fi
else
  ALIAS="$HF_MODEL"
  # HF_MODEL形式: "org/repo:quantization" (例: "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M")
  HF_REPO="${HF_MODEL%%:*}"    # org/repo部分
  HF_QUANT="${HF_MODEL##*:}"   # quantization部分

  echo "==> $SERVER でモデルのローカルキャッシュを確認中..."
  # huggingface-cliのキャッシュからGGUFファイルを検索
  MODEL_PATH=$(ssh "$SERVER" "find ~/.cache/huggingface/hub/models--${HF_REPO//\//--}/ -name '*${HF_QUANT}*.gguf' -not -name '*.incomplete' 2>/dev/null | sort | head -1" || true)

  if [ -n "$MODEL_PATH" ]; then
    echo "    ローカルキャッシュを使用: $MODEL_PATH"
  else
    echo "    ローカルキャッシュなし、huggingface-cli でダウンロードします"
    HF_TOKEN_OPT="${HF_TOKEN:+--token $HF_TOKEN}"
    # hf CLI のパスはサーバのログインユーザによって異なる (既存3台は llm ユーザで
    # /home/llm/.local/bin/hf、aws-gpu01/02 は ubuntu ユーザで ~/.local/bin/hf、
    # aws-v100 は venv 内の ~/.venv/bin/hf)。
    # PATH 上 → $HOME/.local/bin → $HOME/.venv/bin → /home/llm/.local/bin の順に解決する。
    HF_BIN=$(ssh "$SERVER" 'for c in "$(command -v hf 2>/dev/null)" "$HOME/.local/bin/hf" "$HOME/.venv/bin/hf" /home/llm/.local/bin/hf; do if [ -n "$c" ] && [ -x "$c" ]; then echo "$c"; break; fi; done' 2>/dev/null || true)
    if [ -z "$HF_BIN" ]; then
      echo "ERROR: $SERVER に hf CLI が見つかりません（PATH / ~/.local/bin / ~/.venv/bin / /home/llm/.local/bin を確認）" >&2
      echo "       pip install --user huggingface_hub 等で導入してください。" >&2
      exit 1
    fi
    ssh "$SERVER" "$HF_BIN download '$HF_REPO' --include '*${HF_QUANT}*.gguf' $HF_TOKEN_OPT"
    # ダウンロード後にキャッシュからパスを再取得
    MODEL_PATH=$(ssh "$SERVER" "find ~/.cache/huggingface/hub/models--${HF_REPO//\//--}/ -name '*${HF_QUANT}*.gguf' -not -name '*.incomplete' 2>/dev/null | sort | head -1")
    if [ -z "$MODEL_PATH" ]; then
      echo "ERROR: ダウンロード後もGGUFファイルが見つかりません" >&2
      exit 1
    fi
    echo "    ダウンロード完了: $MODEL_PATH"
  fi
fi
MODEL_OPT="-m '$MODEL_PATH'"

# --- fitモード分岐 ---
if [ "$FIT_MODE" = true ]; then
  if [ "$MODEL_PROFILE" = "qwen3_122b" ]; then
    # Phase U-6 確定 OT=B14b: CPU offload = layer {2,3,20-23,31-38}、他は GPU
    # llama.cpp の -ot はカンマ区切りで複数パターンを OR 合成できる (parse_tensor_buffer_overrides)。
    # 単一 regex の `(|)` は bash のメタキャラで outer ssh パイプラインを通らないため使えない。
    OT_PATTERNS=""
    for L in 2 3 20 21 22 23 31 32 33 34 35 36 37 38; do
      [ -n "$OT_PATTERNS" ] && OT_PATTERNS+=","
      OT_PATTERNS+="blk.$L.ffn_.*_exps.weight=CPU"
    done
    NGL_OPTS="-ngl 999 --split-mode layer -ot '$OT_PATTERNS'"
  else
    NGL_OPTS="-ngl 999 -ot 'ffn_.*_exps.weight=CPU'"
  fi
  CTX_OPTS="--ctx-size $FIT_CTX"
else
  NGL_OPTS="--n-gpu-layers 99 --split-mode layer"
  CTX_OPTS="--ctx-size $CTX_SIZE"
fi

# --- llama-server 起動 ---
echo "==> llama-server を $SERVER で起動中..."
echo "    モデル: $HF_MODEL"
if [ "$FIT_MODE" = true ]; then
  echo "    モード: fit (MoE CPUオフロード, ctx-size: $FIT_CTX)"
else
  echo "    ctx-size: $CTX_SIZE"
fi

# EXTRA_LLAMA_OPTS: 検証用の追加フラグ注入口 (YaRN/rope-scaling, -b/-ub 上書き等)。
# SERVER_OPTS より後段に置くため、同名フラグは EXTRA 側が優先される (llama.cpp は最後の指定を採用)。
LAUNCH_CMD="${ENV_PREFIX:+$ENV_PREFIX }$LLAMA_BIN \
  $MODEL_OPT \
  $CHAT_TEMPLATE_OPTS $NGL_OPTS \
  $SERVER_OPTS --n-predict 32768 $THREADS_OPT \
  $CTX_OPTS --parallel 1 --cache-type-k q8_0 --cache-type-v q8_0 \
  --defrag-thold 0.1 $SAMPLING_OPTS $SPEC_OPTS ${EXTRA_LLAMA_OPTS:-} \
  --port 8000 --host 0.0.0.0 \
  --alias '$ALIAS'"

# llama-serverをバックグラウンド起動（ssh -fでSSHを即座に返す）
# ローカル側 fd を /dev/null に向け、tee 等のパイプライン下でハングしないようにする
ssh -f "$SERVER" "cd ~/llama.cpp && nohup bash -c '$LAUNCH_CMD' > /tmp/llama-server.log 2>&1 < /dev/null &" </dev/null >/dev/null 2>&1

# ttyd (7681 GPU監視 / 7682 ログ閲覧) を起動・LISTEN検証（単一の真実源に集約）
"$SCRIPT_DIR/ttyd-up.sh" "$SERVER"

echo "==> llama-server をバックグラウンドで起動しました"
echo "    ログ: ssh $SERVER 'tail -f /tmp/llama-server.log'"
echo "    ブラウザ: http://$SERVER:7682"
echo "    GPU監視: http://$SERVER:7681"
