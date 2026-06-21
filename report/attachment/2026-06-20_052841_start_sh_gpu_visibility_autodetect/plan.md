# start.sh の GPU 可視性デバイス指定を実 GPU 枚数に追従させる

## Context（なぜこの変更が必要か）

`.claude/skills/llama-server/scripts/start.sh` の mi25 / Vulkan 分岐（200-203 行）は
`ENV_PREFIX="GGML_VK_VISIBLE_DEVICES=0,1,2,3"` と**物理4枚前提**でハードコードしている。
しかし mi25 は SLOT4 の PCIe 物理層障害で**実効3枚**のことがあり
（`report/2026-06-14_131713_mi25_gpu4_pcie_dropout.md`）、その状態では Vulkan のデバイス列挙が
「RADV VEGA10 × 3（index 0,1,2）+ llvmpipe(CPU/lavapipe)（index 3）」になる。
`0,1,2,3` を渡すと index 3 で llvmpipe を拾い `ErrorOutOfDeviceMemory` で起動破綻する
（`report/2026-06-18_084557_mi25_vulkan_param_sweep.md` 核心発見 #7 で実機確認、正は `0,1,2`）。

→ **起動前に実 GPU 枚数を検出し、RADV 物理 GPU の index のみを動的に設定する**ことで、
3枚/4枚いずれの構成でも、また将来の復旧・さらなる脱落でも破綻しないようにする。
あわせて期待枚数（P100=4 / MI25=4）を下回る場合は警告を出す（ただし起動は中断しない）。

確定事実: ggml-vulkan の `GGML_VK_VISIBLE_DEVICES` の index は vulkaninfo の `GPUn` 列挙順と
一致する（06-18 レポートで `0,1,2` = RADV 3枚と実機確認済み。ただし ICD 列挙順の安定性に依存する点はコメントで明記する）。

## 方針（確定事項）

- **Vulkan のみ可視性を動的制御**。ROCm(hip) / CUDA(P100) は auto で実効枚数のみ使うため**可視性は触らない**（脱落枚数でも問題なく動作する既知挙動）。枚数チェックの**警告のみ**行う。
- **フォールバック = 未設定 + 強い警告**（ユーザ確定）。検出が空なら `GGML_VK_VISIBLE_DEVICES` を
  **環境変数ごと渡さない**（`ENV_PREFIX=""`。`GGML_VK_VISIBLE_DEVICES=` の空代入は ggml が
  「デバイス0個」と解釈し全滅しうるため厳禁）。ハードコード値（`0,1,2` 等）には戻さない。
  - **注意（フォールバックの位置づけ）**: これは「保証された安全網」ではなく **best-effort の大声警告**。
    未設定時に ggml が llvmpipe を除外するかは実装前調査（後述 V1）で確認する。除外しないと判明した場合でも
    フォールバックは「未設定で起動し、ログで実 GPU 数を確認せよと強く警告」する方針（ユーザ選択）を維持する
    ＝ vulkaninfo 自体が使えない異常時は起動成功を保証しないが、検出経路が正常な通常運用では発生しない。
- **t120h-m10 は一切変更しない**（GPU15 使用不可という別制約に基づく `CUDA_VISIBLE_DEVICES=0..14` を維持）。
- **警告のみで続行**：実効枚数で VRAM 不足ならロード時に llama-server 自体が失敗する。それはそのまま任せる。

## 変更対象ファイル

### 1. `.claude/skills/llama-server/scripts/start.sh`（主たる実装）

**(a) ヘルパ関数を 2 つ追加**（サーバ名バリデーション 142 行の後、case 文 178 行の前あたり）:

- `detect_radv_vk_indices "$SERVER"` — `ssh "$srv" 'vulkaninfo --summary 2>/dev/null'` の出力を
  awk で**ブロック単位**に解析。`^GPU[0-9]+:` でブロック開始＝index 確定、同ブロック内の
  `deviceType` が `..._CPU`（llvmpipe/lavapipe）の GPU を**除外**し、残った（GPU 種別）index のみを
  カンマ連結で返す（例 `0,1,2`、非連番 `0,2` も正しく返せる）。
  - 判定は **`deviceType = ...CPU` で除外**（`deviceName` の `llvmpipe|lavapipe` 文字列一致より頑健。
    mesa の改称・将来の他 GPU 混在に強い）。保険として deviceName の `llvmpipe|lavapipe` も併用可。
  - 成否は**終了ステータスではなく stdout のパース結果**（RADV index が 1 つ以上取れたか）で判定。
- `warn_gpu_degraded "$SERVER" "$actual" "$expected"` — `actual` が数値かつ `expected` 未満なら
  stderr に「実効 N 枚（期待 M 枚）。GPU 脱落の可能性。VRAM 不足ならロードは llama-server 側で失敗。
  継続します」と警告。`actual` が空/0/非数値（検出不能）なら**警告を出さない**（誤警告＝狼少年化を回避）。
  - **実装地雷（set -e）**: 数値ガードを `-lt` 比較の**前**に置く。`[ "$actual" -lt 4 ]` は
    `actual` が空/非数値だと bash 算術エラー（非0）→ `set -e` でスクリプトが落ちる。
    先に `case "$actual" in ''|*[!0-9]*) return 0 ;; esac` で弾く（return 0 で警告抑制＝中断しない）。

**(b) `set -euo pipefail`（2 行目）対策**：検出を呼ぶ箇所はすべて `VAR=$(... || true)` でガードし、
ssh/awk のパイプが非 0 を返してもスクリプトが落ちないようにする（「中断しない」要件を守る最重要点）。
`local VAR=$(...)` の形は終了ステータスを握りつぶす移植性のない挙動なので、宣言と代入を分離する。

**(c) mi25 分岐（179-204 行）の書き換え**:
```
mi25)
    SERVER_OPTS="--flash-attn 1 --poll 0 -b 2048 -ub 2048"
    if [ "${MI25_BACKEND:-hip}" = "vulkan" ]; then
      LLAMA_BIN="./build-vulkan/bin/llama-server"
      MI25_VK_IDX=$(detect_radv_vk_indices "$SERVER" || true)
      if [ -n "$MI25_VK_IDX" ]; then
        ENV_PREFIX="GGML_VK_VISIBLE_DEVICES=$MI25_VK_IDX"
        # 枚数 = カンマ要素数。vulkaninfo を二度呼ばない（pipefail 対策で || true）
        MI25_GPU_COUNT=$(printf '%s' "$MI25_VK_IDX" | awk -F, '{print NF}' || true)
      else
        ENV_PREFIX=""   # 未設定で続行（空代入ではない）
        echo "WARNING: mi25 で RADV GPU を検出できませんでした。GGML_VK_VISIBLE_DEVICES を未設定で起動します。" >&2
        echo "         ggml の自動選択が llvmpipe(CPU) を巻き込む可能性があります。/tmp/llama-server.log で実 GPU 数を確認してください。" >&2
        MI25_GPU_COUNT=""
      fi
    else
      # ROCm(hip): 可視性は触らない。枚数は rocminfo の gfx900 エージェント数で best-effort 検出
      # ('Name:' 行に限定して過剰カウントを防ぐ。実機の実数は実装前調査で確認・パターン確定)
      MI25_GPU_COUNT=$(ssh "$SERVER" "rocminfo 2>/dev/null | grep -cE '^[[:space:]]*Name:[[:space:]]*gfx900'" || true)
    fi
    warn_gpu_degraded "$SERVER" "$MI25_GPU_COUNT" 4
    ;;
```
- 既存コメント（191-199 行: 「`GGML_VK_VISIBLE_DEVICES=0,1,2,3` で物理4GPUに限定」等）を、
  「**vulkaninfo で RADV 物理 GPU の index のみ動的検出（llvmpipe 除外）。index は ICD 列挙順依存・
  ドライバ更新時は要再確認**」に更新。
- ROCm 枚数は `rocminfo | grep -c gfx900`（カーネル/コンピュートが実際に見る数）を採用。
  `rocm-smi` は脱落時に 4 枚を誤列挙した実績（06-14 レポート行109）があるため使わない。
  rocminfo 不在なら空→警告抑制。

**(d) t120h-p100 分岐（205-215 行）**: CUDA は可視性を触らず、枚数検出＋警告のみ追加:
```
    P100_GPU_COUNT=$(ssh "$SERVER" "nvidia-smi --query-gpu=index --format=csv,noheader 2>/dev/null | wc -l" || true)
    warn_gpu_degraded "$SERVER" "$P100_GPU_COUNT" 4
```

**(e) t120h-m10 分岐**: 変更なし。

### 2. `.claude/skills/llama-server/SKILL.md`（注記更新）

- 「サーバ別最適化パラメータ」表（288 行）の mi25 Vulkan 行: `GGML_VK_VISIBLE_DEVICES` は
  「起動時に vulkaninfo で RADV 物理 GPU を自動検出（llvmpipe 除外）」と更新。
- 「mi25 のバックエンド切替」節の**注意書き（306 行）**: 現状「`0,1,2,3` ハードコード／本対応のスコープ外、
  別途修正要」という陳腐化する記述を撤回し、「**start.sh が起動前に vulkaninfo で RADV 物理 GPU の
  index を動的検出し `GGML_VK_VISIBLE_DEVICES` に設定する（実効3枚なら `0,1,2`）。llvmpipe は除外。
  検出失敗時は未設定で警告継続**」に書き換える。

## 既存資産の再利用

- ssh 実行パターンは start.sh 内既存（147 行 `pgrep`、290 行 `find` 等）に合わせる。
- case 文到達時点でビルド用 ssh（164-169 行）が成功済み = サーバ到達性は担保済み。
- `warn_gpu_degraded` は P100 / mi25 双方で共用（expected はサーバごとに引数で渡す）。

## 実装前の実機調査（コードを書く前に実施 — mi25 を power on して1回）

> mi25・t120h-p100 とも現在電源 OFF（P100 のロックは解放済み）。両サーバとも実機テスト可能。
> 操作前に対象サーバのロックを取得する。

awk の確定とフォールバック方針の妥当性は実機の出力に依存するため、**実装の前に**確認する。

- **ロック取得 → 電源 ON**: `.claude/skills/gpu-server/scripts/lock.sh mi25` →
  `bmc-power.sh mi25 on`（または `llama-up.sh` の power 部）→ SSH 疎通待ち。
- **V2**: `ssh mi25 'command -v vulkaninfo'`（vulkaninfo の存在。ROCm-only 構成での有無）。
- **V3**: `ssh mi25 'vulkaninfo --summary'` の実フォーマットで `GPUn:` / `deviceType` / `deviceName`
  行の正確な体裁を確認し、`detect_radv_vk_indices` の awk を確定する。
- **V1**: `GGML_VK_VISIBLE_DEVICES` **未設定**時に現行 master の build-vulkan が llvmpipe を
  除外するかを確認（フォールバックが「大声警告のみ」で許容できるかの根拠固め。
  除外しない場合でも方針は維持するが、警告文をより強くする判断材料にする）。
- **V4（ROCm 枚数）**: `ssh mi25 'rocminfo'` の実出力で gfx900 エージェントの数え方を確認し、
  `grep` パターン（`^[[:space:]]*Name:[[:space:]]*gfx900`）が実効枚数（現状 3）と一致するか検証。
  ずれる場合はパターンを調整する。

これらの結果を踏まえて start.sh / SKILL.md を編集する。

## 実装後の検証（mi25・t120h-p100 両方をライブ検証 — ユーザ確定）

各サーバとも操作前に `lock.sh <server>` でロック取得 → 電源 ON → テスト → `unlock.sh`。

### mi25（Vulkan が主目的・ROCm 回帰も確認）

1. **Vulkan ライブ起動**:
   `MI25_BACKEND=vulkan .claude/skills/llama-server/scripts/start.sh mi25 "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072`
   - `ssh mi25 "ps aux | grep llama-server | grep -o 'GGML_VK_VISIBLE_DEVICES=[^ ]*'"` で
     実効 RADV 枚数（現状おそらく `0,1,2`）になっていること、`3` が含まれないことを確認。
   - `/tmp/llama-server.log` で `Vulkan0/1/2 = RADV`、llvmpipe を掴んでいないこと。
   - `wait-ready.sh` で `/health` 200 を確認。
2. **デグレ警告の確認**: 実効 3 枚（< 期待 4）のとき stderr に warn が出るが起動継続することを確認
   （現状は物理修復まで毎回この警告が出るのが正常＝要件 2 の意図どおり）。
3. **ROCm 回帰確認**: `stop.sh mi25` 後、`start.sh mi25 "<同モデル>" 131072`（既定=hip）で
   可視性を触らず正常起動・`/health` 200。rocminfo 由来の枚数警告挙動も確認。

### t120h-p100（CUDA・回帰確認と枚数チェック）

4. **CUDA ライブ起動**: `start.sh t120h-p100 "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072`
   - CUDA の可視性を触っていない（`ENV_PREFIX` に `CUDA_VISIBLE_DEVICES` 等が無い）こと、
     正常起動・`/health` 200 を確認（回帰なし）。
   - 4 枚健全なら `warn_gpu_degraded` の警告が**出ない**ことを確認（`nvidia-smi` 枚数=4）。
   - もし実機が < 4 枚なら警告が出て起動継続することを確認。

### 後始末

5. 各サーバ `stop.sh` →（自分保持なら）`unlock.sh <server>` → 必要なら電源 OFF。

## レポート作成（必須）

plan mode で計画したため、対になるレポートを `report/` に作成する（REPORT.md 準拠、
タイムスタンプ `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`）。プランファイルを
`report/attachment/<レポート名>/plan.md` に添付し、本文からリンクする。
