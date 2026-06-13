# mi25 Vulkan で Qwen3.6-35B-A3B 128k パラメータ探索

## Context（背景・目的）

既存レポート `report/2026-06-13_112006_mi25_qwen36_128k.md` は、mi25 (MI25/gfx900 ×4 = 64GB) で
Qwen3.6-35B-A3B (UD-Q4_K_XL, 22.36GB) を **ROCm/HIP バックエンド**で 128k (131072) コンテキスト実行する
最適パラメータ (ub=2048 / FA有効) を確定した。

ただし ROCm では llama.cpp master が `__hip_fp8_e4m3` 型を gfx900 でアーキガードなしに参照するため
ビルド不能で、コミット `0fac87b15` に **pin** している（`update_and_build-mi25.sh`）。

本タスクでは **Vulkan (RADV) バックエンド**で同じパラメータ探索を行う。Vulkan ビルドは HIP の
device コンパイルを伴わないため当該 FP8 リグレッションの影響を受けず、**バージョン pin が不要**で
llama.cpp 最新 master をそのまま使える。これを検証し、ビルドスクリプトを Vulkan 対応に拡張したうえで、
ROCm 構成と性能・VRAM を比較するレポートを作成する。

### 事前調査で確定済みの事実（読み取り専用 ssh で確認）

- mi25 に Vulkan ツールチェーン完備: `vulkaninfo` (Instance 1.4.313)、`glslc` (shaderc v2023.8)、
  `/usr/include/vulkan/vulkan.h`、`libvulkan.so`、RADV ICD (`radeon_icd.x86_64.json`)。
- 4 枚すべて `Radeon Instinct MI25 (RADV VEGA10)` として Vulkan から列挙 (GPU id 0-3、DISCRETE_GPU)。
  **注意**: `llvmpipe` (CPU, GPU id 4) も列挙されるため、計算に巻き込まないよう除外が必要
  (`GGML_VK_VISIBLE_DEVICES=0,1,2,3`)。
- 現在 `~/llama.cpp` は pin コミット `0fac87b15`、ROCm の `build/` がビルド済み（本番稼働構成）。

## ユーザ決定事項

1. **ビルド配置**: ROCm 本番 (`build/`) を壊さず、Vulkan は **別ディレクトリ `build-vulkan/` に共存**。
   `update_and_build-mi25.sh` に `MI25_BACKEND` env (hip=既定 / vulkan) を追加し、start.sh から配線。
2. **探索軸**: 元レポートと同じ **ub {4096, 3072, 2048} 掃引** に加え、**`--flash-attn` 有無の両方**を比較。

---

## 実装変更

### 1. `.claude/skills/llama-server/server-scripts/update_and_build-mi25.sh`

`MI25_BACKEND` env でバックエンドを分岐（既定 `hip` = 現状維持）。

- **hip** (既定): 現状どおり `PINNED_COMMIT` へ checkout → `build/` に `-DGGML_HIP=ON -DAMDGPU_TARGETS=gfx900`。
- **vulkan**: pin せず **master を追従** (`git checkout master && git pull --ff-only`)、
  `build-vulkan/` に以下でビルド:
  ```sh
  cmake -S . -B build-vulkan -DGGML_VULKAN=ON -DCMAKE_BUILD_TYPE=Release -DLLAMA_OPENSSL=ON
  cmake --build build-vulkan --config Release -- -j $(nproc)
  ```
  - HIP のような pin は不要（理由をコメントで明記: Vulkan は hip.h を device コンパイルしないため
    FP8 型リグレッション非該当）。
  - 更新判定は `build_llama_cpp()` を backend 引数化し、checkout 前後の HEAD 差分 or `--force` で発火。
  - `build-vulkan/` を `rm -rf` してから再構成（hip の `build/` には触れない）。

### 2. `.claude/skills/llama-server/scripts/start.sh`（mi25 ケース + 起動部）

- ビルド転送・実行行 (167行付近) を `MI25_BACKEND` を透過するよう変更:
  ```sh
  ssh "$SERVER" "cd ~/llama.cpp && MI25_BACKEND='${MI25_BACKEND:-}' ./update_and_build.sh"
  ```
- LAUNCH_CMD (323行) の `./build/bin/llama-server` をハードコードから変数 `LLAMA_BIN` に置換。
  既定 `./build/bin/llama-server`、mi25 かつ `MI25_BACKEND=vulkan` のとき `./build-vulkan/bin/llama-server`。
- mi25 case で `MI25_BACKEND=vulkan` のとき、`ENV_PREFIX` に `GGML_VK_VISIBLE_DEVICES=0,1,2,3` を付与
  （llvmpipe 除外）。SERVER_OPTS は探索のため当面 ROCm 同等の baseline (`--flash-attn 1 -b 2048 -ub 2048`)
  を起点とし、各試行は `EXTRA_LLAMA_OPTS` で ub / FA を上書き（元レポートと同じ非破壊手法）。
- ub/FA 最適値が判明したら、mi25 vulkan 用の SERVER_OPTS をコメント付きで確定値に更新。

> 既存 ROCm 経路（`MI25_BACKEND` 未設定）は完全に現状維持。回帰なし。

### 3. プロセス検出パターンのバックエンド非依存化（整合性修正・必須）

`start.sh` の既存プロセス検出 (146行) と `stop.sh` (40/59/82/88行) は
`pgrep -f './build/bin/llama-server'` を使っており、Vulkan バイナリ
`./build-vulkan/bin/llama-server` にマッチしない。このままだと掃引中の
「起動済み検出」と「停止」が機能せず、二重起動や停止失敗を招く。

両ファイルの pgrep パターンを **`bin/llama-server`**（`build/bin/...` と
`build-vulkan/bin/...` の双方にマッチ）へ統一する。ロックにより1ホスト1サーバ運用
のため誤検出リスクはない（`llama-bench` 等は `bin/llama-server` に非該当）。

---

## 探索手順（元レポートの方法論を踏襲）

ロックは Skill `gpu-server` で取得（`lock.sh mi25`）。全試行 ctx=131072 / KV q8_0 / split-mode layer。

**Phase 0 — Vulkan ビルド**
- `MI25_BACKEND=vulkan` で `update_and_build-mi25.sh` 実行 → master を取得し `build-vulkan/` をビルド。
- ビルド成功と llama.cpp HEAD（master のコミット）を記録。pin 不要を実証。

**Phase 1 — 起動・KV q8_0 可否確認**
- `MI25_BACKEND=vulkan EXTRA_LLAMA_OPTS="--flash-attn 1 -ub 2048"` で start.sh 起動。
- `/health` 確認。**RADV が KV q8_0 + FA をサポートするか**を最優先で確認（未対応ならログにエラー）。
  - q8_0 不可なら f16 KV にフォールバックし、64GB で 128k が収まるか報告。FA 非対応なら FA=0 を基準化。

**Phase 2 — ub 掃引 × FA 有無**
- 各組合せ `{ub: 4096, 3072, 2048} × {FA: 1, 0}` を `EXTRA_LLAMA_OPTS` で順に注入し起動。
- 各試行で計測:
  - VRAM: `ssh mi25 'rocm-smi --showmeminfo vram'`（amdgpu 経由、Vulkan でも有効）。GPU[0-3] ロード時ピーク。
  - 速度: `curl http://10.1.4.13:8000/v1/chat/completions`（32k プロンプト）の `timings` から
    `prompt_tokens_per_second` / `eval_tokens_per_second`。
  - 安定性: OOM/クラッシュ有無。
- 各試行後に停止 (`stop.sh` 相当) → VRAM 解放確認 → 次試行。

**Phase 3 — 128k 安定性 + ROCm 比較**
- 最良構成で 90k+ トークンの長文リクエストを処理し 131k 近傍の安定性を確認。
- ROCm 既存値 (prompt 122.8 / eval 24.5 t/s @ ub=2048) と Vulkan 最良値を比較表化。

---

## レポート作成（REPORT.md 準拠）

- ファイル: `report/2026-06-13_<HHMMSS>_mi25_vulkan_qwen36_128k.md`（実行時刻で採番）。
- 添付: `report/attachment/2026-06-13_<HHMMSS>_mi25_vulkan_qwen36_128k/`
  - `plan.md`（本計画のコピー）
  - `ub_fa_sweep.png`（左: GPU[0] ロード時 VRAM、右: prompt/eval t/s。FA有無で系列分け。元 `ub_sweep.png` と同様式）
- 構成: タイトル(≤50字) → 核心発見サマリ（**PNG をセクション冒頭に画像埋め込み** + Vulkan ならではの
  発見を箇条書き） → 前提・目的 → 環境（Vulkan/RADV/llama.cpp master コミット, pin 不要の根拠） →
  Phase 0-3 → **ROCm vs Vulkan 比較表**（速度/VRAM/ビルド保守性/pin要否） → 確定構成（start.sh 反映） →
  再現方法 → 既知の課題 → 参照レポート（`2026-06-13_112006_mi25_qwen36_128k.md` 等）。
- `report/INDEX.md` に追記。
- グラフは matplotlib（ローカル）で生成。

---

## 検証

1. `MI25_BACKEND` 未設定での start.sh が従来どおり ROCm `build/bin/llama-server` を使うこと（回帰なし）を
   コードレビューで確認（本番 ROCm を再ビルドしない）。
2. Vulkan ビルドが master で成功し（pin なし）、4 枚の RADV デバイスで llama-server が `/health` 200 を返すこと。
3. ub 掃引各点で VRAM・t/s が取得でき、グラフ・比較表に反映されること。
4. 128k で OOM せず長文応答が返ること（または収まらない場合はその旨を定量的に報告）。

## リスク・未確定事項

- **RADV の KV q8_0 / FA サポート**が不明（Phase 1 で最優先確認）。未対応なら f16 KV で 128k 可否を報告。
- Vulkan のマルチGPU VRAM 分散・速度が ROCm と大きく異なる可能性（探索で定量化）。
- master 追従のため、将来の master 変更で Vulkan ビルドが壊れる可能性（pin しない方針の代償。レポートに明記）。
- `llvmpipe` 混入による誤デバイス選択 → `GGML_VK_VISIBLE_DEVICES=0,1,2,3` で回避。
