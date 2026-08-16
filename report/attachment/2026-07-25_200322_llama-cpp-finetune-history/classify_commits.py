#!/usr/bin/env python3
"""training 関連コミットを「機能変更」と「巻き添え」に分類して一覧表示する（目視検証用）"""
import re
import subprocess

SRC = "/home/ubuntu/projects/llm-server-ops/src/llama.cpp"
PATHS = [
    "examples/baby-llama",
    "examples/train-text-from-scratch",
    "examples/finetune",
    "examples/training",
    "common/train.cpp",
    "common/train.h",
    "ggml/src/ggml-opt.cpp",
    "ggml/include/ggml-opt.h",
    "src/llama-model-saver.cpp",
]

# 「training 機能そのものへの変更」と判定するキーワード（subject に対して）
FUNC_RE = re.compile(
    r"\b(train|training|finetune|fine-tune|baby-llama|ggml-opt|ggml_opt|lora|"
    r"backward|optimizer|adamw|sgd|opt-step|model-saver|model_saver)\b",
    re.IGNORECASE,
)
# 上記に当たっても機械的変更なら巻き添え扱いに落とすキーワード
COLLATERAL_RE = re.compile(
    r"\b(typo|readme|rename|comment|whitespace|warning|warnings|include|includes|"
    r"cmake|flake|docker|nix|gitignore|format|formatting|no ci)\b",
    re.IGNORECASE,
)

out = subprocess.run(
    ["git", "log", "--reverse", "--format=%h\t%ad\t%s", "--date=short", "--"] + PATHS,
    cwd=SRC, capture_output=True, text=True, check=True,
).stdout.strip().split("\n")

func, coll = [], []
for line in out:
    sha, date, subject = line.split("\t", 2)
    is_func = bool(FUNC_RE.search(subject)) and not COLLATERAL_RE.search(subject)
    (func if is_func else coll).append((sha, date, subject))

print(f"=== 機能変更と判定: {len(func)} 件 ===")
for sha, date, subj in func:
    print(f"  {date} {sha} {subj}")
print(f"\n=== 巻き添えと判定: {len(coll)} 件 ===")
for sha, date, subj in coll:
    print(f"  {date} {sha} {subj}")
