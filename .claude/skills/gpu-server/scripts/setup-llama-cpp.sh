#!/bin/bash
#
# setup-llama-cpp.sh - GPUサーバにllama.cppをセットアップ
#
# Usage: ./setup-llama-cpp.sh <server>
#   server: mi25, t120h-p100, t120h-m10
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

usage() {
    echo "Usage: $0 <server>"
    echo "  server: mi25, t120h-p100, t120h-m10"
    exit 1
}

if [ $# -ne 1 ]; then
    usage
fi

SERVER="$1"

# サーバ設定
case "$SERVER" in
    mi25)
        GPU_TYPE="rocm"
        BUILD_SCRIPT='build_llama_cpp() {
  rm -rf build &&
  HIPCXX="$(hipconfig -l)/clang" HIP_PATH="$(hipconfig -R)" cmake -S . -B build -DGGML_HIP=ON -DAMDGPU_TARGETS=gfx900 -DCMAKE_BUILD_TYPE=Release -DLLAMA_OPENSSL=ON &&
  cmake --build build --config Release -- -j $(nproc)
}'
        ;;
    t120h-p100)
        GPU_TYPE="cuda"
        BUILD_SCRIPT='build_llama_cpp() {
  rm -rf build &&
    cmake -B build \
          -DLLAMA_OPENSSL=ON \
          -DGGML_NATIVE=ON \
          -DGGML_CUDA=ON \
          -DGGML_CUDA_FA_ALL_QUANTS=ON \
          -DCMAKE_CUDA_COMPILER="/usr/local/cuda-12.9/bin/nvcc" \
          -DCMAKE_CUDA_ARCHITECTURES="60" &&
    cmake --build build --config Release -- -j $(nproc)
}'
        ;;
    t120h-m10)
        GPU_TYPE="cuda"
        # M10: compute capability 5.2 (Maxwell)
        BUILD_SCRIPT='build_llama_cpp() {
  rm -rf build &&
    cmake -B build \
          -DLLAMA_OPENSSL=ON \
          -DGGML_NATIVE=ON \
          -DGGML_CUDA=ON \
          -DGGML_CUDA_FA_ALL_QUANTS=ON \
          -DCMAKE_CUDA_ARCHITECTURES="52" &&
    cmake --build build --config Release -- -j $(nproc)
}'
        ;;
    *)
        echo "Error: Unknown server '$SERVER'"
        usage
        ;;
esac

echo "=== $SERVER に llama.cpp をセットアップ ==="
echo "GPU Type: $GPU_TYPE"

# 1. llama.cppディレクトリの確認
echo ""
echo "--- Step 1: llama.cpp ディレクトリ確認 ---"
HAS_LLAMA=$(ssh "$SERVER" "test -d ~/llama.cpp && echo 'yes' || echo 'no'")

if [ "$HAS_LLAMA" = "no" ]; then
    echo "llama.cpp が存在しません。クローンします..."
    ssh "$SERVER" "git clone https://github.com/ggml-org/llama.cpp.git ~/llama.cpp"
    echo "クローン完了"
else
    echo "llama.cpp は既に存在します"
    # 最新版かチェック
    echo "最新版をチェック..."
    ssh "$SERVER" "cd ~/llama.cpp && git fetch origin"
    LOCAL=$(ssh "$SERVER" "cd ~/llama.cpp && git rev-parse HEAD")
    REMOTE=$(ssh "$SERVER" "cd ~/llama.cpp && git rev-parse origin/master 2>/dev/null || git rev-parse origin/main")
    if [ "$LOCAL" != "$REMOTE" ]; then
        echo "更新があります (local: ${LOCAL:0:8}, remote: ${REMOTE:0:8})"
    else
        echo "最新版です"
    fi
fi

# 2. update_and_build.sh の作成
echo ""
echo "--- Step 2: update_and_build.sh を配置 ---"

UPDATE_SCRIPT='#!/bin/sh

usage() {
  cat <<EOF
Usage: $(basename "$0") [-f|--force] [-h|--help]

Options:
  -f, --force   更新がなくてもビルドを実行
  -h, --help    このヘルプを表示
EOF
  exit 0
}

'"$BUILD_SCRIPT"'

FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    -f|--force)
      FORCE=1
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      ;;
  esac
done

BEFORE=$(git rev-parse HEAD)
git pull
AFTER=$(git rev-parse HEAD)

if [ "$BEFORE" != "$AFTER" ]; then
  echo "更新を検出しました。ビルドを開始します..."
  build_llama_cpp
elif [ "$FORCE" -eq 1 ]; then
  echo "強制ビルドを実行します..."
  build_llama_cpp
else
  echo "更新はありません。"
fi'

# スクリプトをサーバに転送
echo "$UPDATE_SCRIPT" | ssh "$SERVER" "cat > ~/llama.cpp/update_and_build.sh && chmod +x ~/llama.cpp/update_and_build.sh"
echo "update_and_build.sh を配置しました"

# 3. ビルド環境の確認
echo ""
echo "--- Step 3: ビルド環境確認 ---"

if [ "$GPU_TYPE" = "cuda" ]; then
    # nvccを探す（PATHにあるか、/usr/local/cuda-*/bin/ にあるか）
    NVCC_PATH=$(ssh "$SERVER" "which nvcc 2>/dev/null || ls /usr/local/cuda-*/bin/nvcc 2>/dev/null | sort -V | tail -1 || echo 'not_found'")
    if [ "$NVCC_PATH" = "not_found" ] || [ -z "$NVCC_PATH" ]; then
        echo "WARNING: nvcc が見つかりません"
        echo ""
        echo "以下の場所を確認してください:"
        echo "  - PATH に nvcc があるか"
        echo "  - /usr/local/cuda-*/bin/nvcc が存在するか"
        echo ""
        echo "CUDA Toolkit がインストールされていない場合:"
        echo "  1. https://developer.nvidia.com/cuda-downloads からダウンロード"
        echo "  2. または: sudo apt install nvidia-cuda-toolkit"
        exit 1
    else
        echo "nvcc: $NVCC_PATH"
        # nvccのパスをビルドスクリプトに反映（M10など、PATHにない場合）
        if [ "$SERVER" = "t120h-m10" ]; then
            BUILD_SCRIPT='build_llama_cpp() {
  rm -rf build &&
    cmake -B build \
          -DLLAMA_OPENSSL=ON \
          -DGGML_NATIVE=ON \
          -DGGML_CUDA=ON \
          -DGGML_CUDA_FA_ALL_QUANTS=ON \
          -DCMAKE_CUDA_COMPILER="'"$NVCC_PATH"'" \
          -DCMAKE_CUDA_ARCHITECTURES="52" &&
    cmake --build build --config Release -- -j $(nproc)
}'
            # update_and_build.sh を再生成
            echo "nvccパスを含めて update_and_build.sh を再配置します..."
            UPDATE_SCRIPT='#!/bin/sh

usage() {
  cat <<EOF
Usage: $(basename "$0") [-f|--force] [-h|--help]

Options:
  -f, --force   更新がなくてもビルドを実行
  -h, --help    このヘルプを表示
EOF
  exit 0
}

'"$BUILD_SCRIPT"'

FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    -f|--force)
      FORCE=1
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      ;;
  esac
done

BEFORE=$(git rev-parse HEAD)
git pull
AFTER=$(git rev-parse HEAD)

if [ "$BEFORE" != "$AFTER" ]; then
  echo "更新を検出しました。ビルドを開始します..."
  build_llama_cpp
elif [ "$FORCE" -eq 1 ]; then
  echo "強制ビルドを実行します..."
  build_llama_cpp
else
  echo "更新はありません。"
fi'
            echo "$UPDATE_SCRIPT" | ssh "$SERVER" "cat > ~/llama.cpp/update_and_build.sh && chmod +x ~/llama.cpp/update_and_build.sh"
            echo "update_and_build.sh を再配置しました（nvcc: $NVCC_PATH）"
        fi
    fi
elif [ "$GPU_TYPE" = "rocm" ]; then
    HAS_HIPCC=$(ssh "$SERVER" "which hipcc 2>/dev/null || echo 'not_found'")
    if [ "$HAS_HIPCC" = "not_found" ]; then
        echo "WARNING: hipcc が見つかりません"
        echo "ROCm のインストールが必要です"
        exit 1
    else
        echo "hipcc: $HAS_HIPCC"
    fi
fi

# 4. buildディレクトリの確認
echo ""
echo "--- Step 4: ビルド状態確認 ---"
HAS_BUILD=$(ssh "$SERVER" "test -d ~/llama.cpp/build && echo 'yes' || echo 'no'")
HAS_SERVER=$(ssh "$SERVER" "test -f ~/llama.cpp/build/bin/llama-server && echo 'yes' || echo 'no'")

if [ "$HAS_BUILD" = "no" ] || [ "$HAS_SERVER" = "no" ]; then
    echo "ビルドが必要です"
    echo ""
    echo "ビルドを実行しますか? (y/N)"
    read -r REPLY
    if [ "$REPLY" = "y" ] || [ "$REPLY" = "Y" ]; then
        echo "ビルドを開始します..."
        ssh -t "$SERVER" "cd ~/llama.cpp && ./update_and_build.sh -f"
    else
        echo "後で手動でビルドしてください:"
        echo "  ssh $SERVER 'cd ~/llama.cpp && ./update_and_build.sh -f'"
    fi
else
    echo "llama-server は既にビルド済みです"
fi

echo ""
echo "=== セットアップ完了 ==="
