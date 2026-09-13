#!/usr/bin/env bash
# 両機の VRAM 使用量と最小空きを 1 行ずつ出す。ローカル (WS) から実行する。
for S in aws-gpu01 aws-gpu02; do
  ssh -n $S "nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits" 2>/dev/null \
  | awk -v s="$S" -F', *' '{u+=$1; if(m==""||$2<m) m=$2} END{printf "%s: used=%d MiB minfree=%d MiB (n=%d)\n", s, u, m, NR}'
done
