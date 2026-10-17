#!/bin/bash
# start.sh の起動コマンド組み立てを、ssh/scp をスタブに差し替えて検証する（実機には接続しない）。
# 使い方: プロジェクトルートで bash report/attachment/<この dir>/verify-start-sh.sh
set -u
D=$(mktemp -d)
cp "$(dirname "$0")/fake-ssh.sh" "$D/ssh"; printf '#!/bin/bash\nexit 0\n' > "$D/scp"; chmod +x "$D/ssh" "$D/scp"
for s in t120h-p100 mi25; do
  : > "$D/log"
  PATH=$D:$PATH .claude/skills/llama-server/scripts/start.sh "$s" "unsloth/Qwen3.8-27B-GGUF:UD-Q4_K_XL" 131072 >/dev/null 2>&1
  echo "== $s"
  grep -o "nohup bash -c.*" "$D/log" | grep -oE -- "-m '[^']*'|--split-mode [a-z]+|--spec-[a-z-]+ [^ ]+|--temp [^ ]+|-ub [0-9]+|--alias '[^']*'" | paste -sd' '
done
