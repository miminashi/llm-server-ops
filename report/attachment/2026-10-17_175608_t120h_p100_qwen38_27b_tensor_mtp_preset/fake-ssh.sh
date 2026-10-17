#!/bin/bash
echo "SSH $*" >> "$(dirname "$0")/log"
case "$*" in *"find ~/models/Qwen3.8-27B-GGUF/"*) echo /home/llm/models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf;; *"-G "*) echo "hostname 10.1.4.14";; esac
exit 0
