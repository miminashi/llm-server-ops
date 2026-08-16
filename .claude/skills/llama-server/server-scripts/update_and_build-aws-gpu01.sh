#!/bin/sh
#
# aws-gpu01 (Supermicro SYS-4028GR-TRT2) 用ビルドスクリプト
#   GPU  : Tesla P100-PCIE 16GB x7 (sm_60 / Pascal)
#   CUDA : /usr/bin/nvcc (Ubuntu パッケージ版 12.0)。t120h-p100 のような
#          /usr/local/cuda-12.9 は存在しないため PATH 上の nvcc を明示指定する。
#   OS   : Ubuntu 24.04.3 / driver 535.288.01
#
# 未検証: 2026-08-16 のサーバ登録時点では本スクリプトによるビルドは未実施。
#         初回ビルド時に nvcc 12.0 と Ubuntu 24.04 の gcc の組み合わせで
#         エラーが出る場合は -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++-12 等を検討する。

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
          -DCMAKE_CUDA_COMPILER="/usr/bin/nvcc" \
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
