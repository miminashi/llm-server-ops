#!/bin/sh

usage() {
  cat <<EOF
Usage: $(basename "$0") [-f|--force] [-h|--help]

Options:
  -f, --force   更新がなくてもビルドを実行
  -h, --help    このヘルプを表示

Environment:
  MI25_BACKEND  ビルドバックエンド: vulkan (既定) | hip
                vulkan : Vulkan (RADV)。pin 不要で master 追従。build-vulkan/ にビルド。
                hip    : ROCm/HIP (gfx900) fallback。FP8 型リグレッション回避のためコミット pin。
                         build/ にビルド。
EOF
  exit 0
}

# バックエンド選択。既定は vulkan (RADV)。過去は hip 既定だったが、2026-07-20 実測で
# Vulkan が pp / tg とも ROCm を上回ることが確認されたため反転
# (report/2026-07-20_013500_mi25_prompt_eval_regression.md)。hip は fallback 用途で残置。
MI25_BACKEND="${MI25_BACKEND:-vulkan}"

# mi25 (ROCm 6.2 / gfx900) 向け llama.cpp コミット pin (hip バックエンドのみ)。
# llama.cpp master は 112c78159 "ggml-cuda: Add NVFP4 dp4a kernel (#20644)" 以降、
# ggml/src/ggml-cuda/vendors/hip.h が __hip_fp8_e4m3 (FP8 e4m3) 型をアーキガードなしで
# 参照するため、gfx900 (Vega) の device compile で "unknown type name '__hip_fp8_e4m3'"
# となりビルド不能。ROCm/gfx900 でビルド可能な直前コミット (version 8533) に固定する。
# 新しい master が gfx900 で再びビルド可能になったら、検証のうえこの値を更新すること。
# (P100/M10 は CUDA バックエンドのため影響なし＝それぞれの update_and_build スクリプトは master 追従)
#
# vulkan バックエンドは hip.h を device コンパイルしない (HIP 無効) ため、この FP8 型
# リグレッションの影響を受けない。よって vulkan では pin 不要で master をそのまま使える。
PINNED_COMMIT="0fac87b15"

build_llama_cpp_hip() {
  rm -rf build &&
  HIPCXX="$(hipconfig -l)/clang" HIP_PATH="$(hipconfig -R)" cmake -S . -B build \
    -DGGML_HIP=ON \
    -DAMDGPU_TARGETS=gfx900 \
    -DCMAKE_BUILD_TYPE=Release \
    -DLLAMA_OPENSSL=ON &&
  cmake --build build --config Release -- -j $(nproc)
}

build_llama_cpp_vulkan() {
  # ROCm の build/ には触れず、別ディレクトリ build-vulkan/ にビルドして共存させる。
  rm -rf build-vulkan &&
  cmake -S . -B build-vulkan \
    -DGGML_VULKAN=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DLLAMA_OPENSSL=ON &&
  cmake --build build-vulkan --config Release -- -j $(nproc)
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

case "$MI25_BACKEND" in
  hip)
    # master を追わず、gfx900 でビルド可能な PINNED_COMMIT に固定する。
    git fetch origin 2>/dev/null || true
    if ! git checkout "$PINNED_COMMIT" 2>&1 | tail -2; then
      echo "ERROR: pinned commit $PINNED_COMMIT への checkout に失敗しました" >&2
      exit 1
    fi
    ;;
  vulkan)
    # Vulkan は pin 不要。master を追従する。
    git fetch origin 2>/dev/null || true
    if ! git checkout master 2>&1 | tail -2; then
      echo "ERROR: master への checkout に失敗しました" >&2
      exit 1
    fi
    git pull --ff-only 2>&1 | tail -2 || true
    ;;
  *)
    echo "ERROR: 不明な MI25_BACKEND: $MI25_BACKEND (hip|vulkan)" >&2
    exit 1
    ;;
esac

AFTER=$(git rev-parse HEAD)

run_build() {
  case "$MI25_BACKEND" in
    hip)    build_llama_cpp_hip ;;
    vulkan) build_llama_cpp_vulkan ;;
  esac
}

# vulkan は build-vulkan/ が未生成なら HEAD 不変でもビルドする (初回バックエンド切替対策)。
NEED_BUILD=0
if [ "$BEFORE" != "$AFTER" ]; then
  NEED_BUILD=1
elif [ "$FORCE" -eq 1 ]; then
  NEED_BUILD=1
elif [ "$MI25_BACKEND" = "vulkan" ] && [ ! -x build-vulkan/bin/llama-server ]; then
  NEED_BUILD=1
elif [ "$MI25_BACKEND" = "hip" ] && [ ! -x build/bin/llama-server ]; then
  NEED_BUILD=1
fi

if [ "$NEED_BUILD" -eq 1 ]; then
  if [ "$MI25_BACKEND" = "vulkan" ]; then
    echo "Vulkan バックエンドで master ($AFTER) をビルドします (build-vulkan/)..."
  else
    echo "pinned commit ($PINNED_COMMIT) で HIP バックエンドをビルドします (build/)..."
  fi
  run_build
else
  echo "更新はありません (backend: $MI25_BACKEND)。"
fi
