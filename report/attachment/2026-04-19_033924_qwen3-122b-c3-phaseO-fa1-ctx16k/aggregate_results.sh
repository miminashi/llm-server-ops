#!/usr/bin/env bash
# 各 out_O_* ディレクトリから eval_run*.json と gpu_post_run*.csv を抽出して TSV 形式で出力
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

printf "tag\trun\teval_tps\tprompt_tps\tprompt_n\tpredicted_n\tgpu0_used\tgpu1_used\tgpu2_used\tgpu3_used\n"

for dir in out_O_*; do
  [ -d "$dir" ] || continue
  tag="${dir#out_}"
  for json in "$dir"/eval_run*.json; do
    [ -f "$json" ] || continue
    run=$(basename "$json" .json | sed 's/eval_run//')
    eval_tps=$(jq -r '.timings.predicted_per_second // "n/a"' "$json")
    prompt_tps=$(jq -r '.timings.prompt_per_second // "n/a"' "$json")
    prompt_n=$(jq -r '.timings.prompt_n // "n/a"' "$json")
    predicted_n=$(jq -r '.timings.predicted_n // "n/a"' "$json")

    gpu_csv="$dir/gpu_post_run${run}.csv"
    if [ -f "$gpu_csv" ]; then
      gpu0=$(awk -F',' 'NR==1 {gsub(/ /,""); print $2}' "$gpu_csv" || echo n/a)
      gpu1=$(awk -F',' 'NR==2 {gsub(/ /,""); print $2}' "$gpu_csv" || echo n/a)
      gpu2=$(awk -F',' 'NR==3 {gsub(/ /,""); print $2}' "$gpu_csv" || echo n/a)
      gpu3=$(awk -F',' 'NR==4 {gsub(/ /,""); print $2}' "$gpu_csv" || echo n/a)
    else
      gpu0=n/a; gpu1=n/a; gpu2=n/a; gpu3=n/a
    fi

    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
      "$tag" "$run" "$eval_tps" "$prompt_tps" "$prompt_n" "$predicted_n" \
      "$gpu0" "$gpu1" "$gpu2" "$gpu3"
  done
done
