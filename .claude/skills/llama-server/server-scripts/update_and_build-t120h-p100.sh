#!/bin/sh

usage() {
  cat <<EOF
Usage: $(basename "$0") [-f|--force] [-h|--help]

Options:
  -f, --force   更新がなくてもビルドを実行
  -h, --help    このヘルプを表示
EOF
  exit 0
}

build_llama_cpp() {
  rm -rf build &&
    cmake -B build \
          -DLLAMA_OPENSSL=ON \
          -DGGML_NATIVE=ON \
          -DGGML_CUDA=ON \
          -DGGML_CUDA_FA_ALL_QUANTS=ON \
          -DCMAKE_CUDA_COMPILER="/usr/local/cuda-12.9/bin/nvcc" \
          -DCMAKE_CUDA_ARCHITECTURES="60" &&
    cmake --build build --config Release -- -j $(nproc)
}

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
fi
