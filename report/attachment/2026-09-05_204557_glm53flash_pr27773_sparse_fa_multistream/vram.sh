#!/usr/bin/env bash
# 両機の VRAM 使用量と最小空きを 1 行にまとめる。
set -u
echo -n "aws-gpu01: "
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits | awk -F', ' '{u+=$1; if(m==""||$2<m)m=$2} END{print "used="u" MiB minfree="m" MiB"}'
