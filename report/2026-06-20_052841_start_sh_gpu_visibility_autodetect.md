# start.sh の GPU 可視性を実 GPU 枚数に追従させる自動検出化

- **実施日時**: 2026年6月20日 05:28 (JST)

## 添付ファイル

- [実装プラン](attachment/2026-06-20_052841_start_sh_gpu_visibility_autodetect/plan.md)

## 核心発見サマリ

`start.sh` の mi25 Vulkan 分岐がハードコードしていた `GGML_VK_VISIBLE_DEVICES=0,1,2,3`
（**物理4枚前提**）を撤廃し、**起動前に `vulkaninfo --summary` で RADV 物理 GPU の index のみを
動的検出**して設定する方式に変更した。あわせて期待枚数（mi25=4 / p100=4）を下回ると **stderr 警告
（起動は中断しない）** を出す枚数チェックを mi25・t120h-p100 双方に追加した。

実機検証の決定的な所見:

1. **脱落は間欠的で、枚数ハードコードは原理的に追従不能**。今回は OFF 状態からのコールド電源 ON で
   起動した結果、mi25 は **4枚すべて列挙**された（脱落は間欠的。前回検証時は実効3枚だった）。
   `vulkaninfo --summary` は GPU0-3=RADV VEGA10、
   GPU4=llvmpipe(CPU) を列挙。3枚構成（GPU0-2=RADV、GPU3=llvmpipe）と index 配置が変わるため、
   固定 `0,1,2,3` は「4枚時は偶然正しい／3枚時は index 3 の llvmpipe を拾い破綻」という不整合だった。
   自動検出は 4枚→`0,1,2,3`、3枚→`0,1,2` を正しく出し分ける。
2. **index 対応が確定**: `vulkaninfo` の `GPUn` 順 = `ggml-vulkan` の `Vulkann` 順（`--list-devices`
   と本番ログで一致確認）。検出した index をそのまま `GGML_VK_VISIBLE_DEVICES` に使える。
3. **フォールバック（未設定）が現行 master で安全**と判明: `GGML_VK_VISIBLE_DEVICES` 未設定時、
   現行 master の `build-vulkan` は llvmpipe を**自動除外**して RADV のみを列挙する
   （`--list-devices` で Vulkan0-3=RADV のみ・llvmpipe 非掲載を確認）。よって vulkaninfo 不在等で
   検出に失敗しても、空代入を避け「環境変数ごと渡さない＋強い警告」で実害なく続行できる。
4. **`GGML_VK_VISIBLE_DEVICES` の SET/UNSET 意味論は非対称**（破綻の根本メカニズム）:
   - **SET**（例 `0,1,2,3`）時は **raw な物理デバイス列挙（llvmpipe を含む全 Vulkan デバイス）への
     index 参照**。よって3枚構成では index 3 が llvmpipe(CPU) を指し OOM 破綻する（この3枚時の破綻は
     [06-18 param sweep](2026-06-18_084557_mi25_vulkan_param_sweep.md) で実証。本検証は4枚のため未再現）。
   - **UNSET** 時は ggml が **`deviceType=CPU` を自動フィルタ**して RADV のみを列挙する（上記 3）。
   - つまり「固定 `0,1,2,3` は3枚時に破綻するが未設定は安全」の理由はこの非対称性にある。本対応は
     SET 経路を使いつつ、**SET する index を vulkaninfo の RADV ブロックだけに絞る**ことで raw 列挙の
     罠を回避している（UNSET の自動フィルタに依存せず、明示的・将来のバージョン挙動変化にも頑健）。

検証結果: mi25 Vulkan で `GGML_VK_VISIBLE_DEVICES=0,1,2,3`（4枚）が設定され `/health` 200・
llvmpipe 不掴み。mi25 ROCm・t120h-p100 CUDA とも可視性を触らず回帰なし・`/health` 200。

## 前提・目的

- **背景**: mi25 は SLOT4 等の PCIe 物理層障害で**実効枚数が間欠的に変動**する
  （[4枚目脱落＝PCIe物理層障害](2026-06-14_131713_mi25_gpu4_pcie_dropout.md)）。
  Vulkan(RADV) バックエンドのデバイス列挙は「RADV × 実効枚数 + 末尾に llvmpipe(CPU)」となるため、
  `start.sh` のハードコード `GGML_VK_VISIBLE_DEVICES=0,1,2,3` は3枚構成時に index 3 の llvmpipe を
  拾い `ErrorOutOfDeviceMemory` で起動破綻していた
  （[Vulkan param sweep](2026-06-18_084557_mi25_vulkan_param_sweep.md) 核心発見 #7、正は `0,1,2`）。
- **目的**: 起動前に実 GPU 枚数を検出し、RADV 物理 GPU の index のみを動的に設定する。あわせて
  期待枚数を下回る場合に警告を出す（ただしモデルロードに支障がなければ起動は中断しない）。
- **前提条件**: mi25・t120h-p100 とも利用可（要電源 ON＋ロック取得）。sudo 不要の読み取り診断のみ。

## 環境情報

- **mi25**（10.1.4.13）: AMD Radeon Instinct MI25（gfx900/VEGA10、16GiB）物理4枚、Supermicro
  X10DRG-Q、Ubuntu 22.04、amdgpu/RADV（Mesa 23.2.1）、Vulkan 1.3.255。BMC=10.1.4.7（IPMI）。
  本検証時は4枚すべて RADV 列挙（GPU0-3）+ llvmpipe（GPU4）。vulkaninfo の deviceUUID 中間バイト
  （`0400/0700/8400/8700`）から、今回列挙された4枚は PCIe バス **04/07/84/87** に対応
  （[脱落レポート](2026-06-14_131713_mi25_gpu4_pcie_dropout.md)が追跡したバス番号と整合）。
- **t120h-p100**（10.1.4.14）: NVIDIA Tesla P100 16GB ×4、HPE iLO5（10.1.4.8、Redfish）。
- **llama.cpp**: Vulkan=master `fabde3bf`（build-vulkan/、pin 不要）。ROCm=gfx900 ビルド可能コミットに
  pin（build/）。

## 実装内容

変更ファイル: `.claude/skills/llama-server/scripts/start.sh`（+65/−3 行）、
`.claude/skills/llama-server/SKILL.md`（注記更新、+24/−5 行）。

### 1. ヘルパ関数 2 つを追加（サーバ名バリデーション直後）

- **`detect_radv_vk_indices "$srv"`**: `ssh "$srv" 'vulkaninfo --summary'` を awk で**ブロック単位**に
  解析。`^GPU[0-9]+:` で index を確定し、同ブロックの `deviceType=PHYSICAL_DEVICE_TYPE_CPU`
  （= llvmpipe/lavapipe）を除いた index のみをカンマ連結で返す（保険として deviceName の
  `llvmpipe|lavapipe` 文字列一致も併用）。非連番（例 `0,2`）も正しく返せる。vulkaninfo 不在/失敗時は
  空文字を返す。
- **`warn_gpu_degraded "$srv" "$actual" "$expected"`**: `actual` が `expected` 未満なら stderr 警告、
  ただし**起動は中断しない**。`actual` が空/0/非数値なら誤警告回避のため無音。
  **数値ガード（`case`）を `-lt` 比較の前**に置き、空/非数値での算術エラーによる `set -e` 中断を防ぐ。

### 2. mi25 分岐

- **Vulkan 時**: `detect_radv_vk_indices` の結果を `GGML_VK_VISIBLE_DEVICES` に設定（`|| true` で
  pipefail ガード）。枚数はカンマ要素数から算出し `warn_gpu_degraded ... 4`。検出空なら
  `ENV_PREFIX=""`（環境変数ごと渡さない。空代入 `GGML_VK_VISIBLE_DEVICES=` は「デバイス0個」
  解釈で全滅しうるため厳禁）＋強い警告で続行。
- **ROCm(hip) 時**: 可視性は**触らない**（auto で実効枚数のみ使用）。枚数は
  `rocminfo | grep -cE '^[[:space:]]*Name:[[:space:]]*gfx900'`（gfx900 Agent 数）で検出し警告のみ。
  `rocm-smi` は脱落時に4枚を誤列挙した実績があり不採用。

### 3. t120h-p100 分岐

- CUDA は可視性を**触らない**。`nvidia-smi --query-gpu=index | wc -l`（数字以外を `tr` で除去）で
  枚数検出し `warn_gpu_degraded ... 4`。

### 4. t120h-m10 分岐

- 変更なし（GPU15 使用不可という別制約の `CUDA_VISIBLE_DEVICES=0..14` を維持）。

## 検証結果

### 実装前の実機調査（mi25、power on 後）

| 項目 | 結果 |
|------|------|
| V2: vulkaninfo 存在 | `/usr/bin/vulkaninfo`（あり） |
| V3: `vulkaninfo --summary` 形式 | GPU0-3=`PHYSICAL_DEVICE_TYPE_DISCRETE_GPU` RADV VEGA10、GPU4=`PHYSICAL_DEVICE_TYPE_CPU` llvmpipe。awk が `0,1,2,3` を返すことを確認 |
| V1: 未設定時の ggml 列挙 | `build-vulkan --list-devices` で Vulkan0-3=RADV のみ（**llvmpipe 自動除外**）→ フォールバック安全・index 対応一致 |
| V4: rocminfo gfx900 数 | `Name: gfx900` 行 = **4**（今回4枚復帰）。`amdgcn-...gfx900` 行は誤マッチせず |

### 単体・合成テスト

- `bash -n` 構文チェック: エラーなし。
- awk 3枚合成入力（GPU0-2=RADV、GPU3=llvmpipe）→ `0,1,2`（期待どおり）。
- `warn_gpu_degraded` 単体（`set -euo pipefail` 下）: actual=3→警告/4→無音/空→無音/非数値→無音、
  全ケースで rc=0・中断なし。

### 実機ライブ検証

| 検証 | 結果 |
|------|------|
| mi25 Vulkan 起動 | `Vulkan: RADV 物理 GPU を検出 → GGML_VK_VISIBLE_DEVICES=0,1,2,3 (4枚)`、プロセス env も同値、ログ Vulkan0-3=RADV のみ（llvmpipe 不掴み）、`/health` 200、推論でトークン生成確認 |
| mi25 4枚時の警告 | 4≧4 のため**警告なし**（正しい） |
| mi25 ROCm 回帰 | `build/bin/llama-server` 使用、`GGML_VK_VISIBLE_DEVICES` 不在（可視性不介入）、枚数警告なし、`/health` 200 |
| t120h-p100 CUDA 回帰 | `build/bin/llama-server` 使用、`CUDA_VISIBLE_DEVICES`/`GGML_VK` 不在（可視性不介入）、nvidia-smi=4 で警告なし、`/health` 200 |

> **注**: 実効3枚（< 期待4）時の警告＋`GGML_VK_VISIBLE_DEVICES=0,1,2` の本番起動は、今回ブートが
> 4枚復帰していたためライブでは再現できなかった。awk の3枚合成テスト（→`0,1,2`）と
> `warn_gpu_degraded` 単体テスト（actual=3→警告）で当該パスを担保した。

## 再現方法

```bash
# 0. mi25 をロック取得・電源ON（IPMI）
.claude/skills/gpu-server/scripts/bmc-power.sh mi25 on
#    SSH 疎通後
.claude/skills/gpu-server/scripts/lock.sh mi25

# 1. デバイス列挙・検出ロジックの確認（読み取り専用）
ssh mi25 'vulkaninfo --summary | sed -n "/^Devices:/,\$p"'
ssh mi25 'cd ~/llama.cpp && ./build-vulkan/bin/llama-server --list-devices'   # Vulkan0-3=RADV のみ
ssh mi25 "rocminfo | grep -cE '^[[:space:]]*Name:[[:space:]]*gfx900'"          # gfx900 Agent 数

# 2. Vulkan 起動（自動検出が GGML_VK_VISIBLE_DEVICES を設定）
MI25_BACKEND=vulkan .claude/skills/llama-server/scripts/start.sh mi25 \
  "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
ssh mi25 "ps aux | grep llama-server | grep -o 'GGML_VK_VISIBLE_DEVICES=[^ ]*'"   # 実効枚数に追従
curl -s -o /dev/null -w '%{http_code}\n' http://10.1.4.13:8000/health             # 200

# 3. ROCm 回帰（既定 = hip、可視性は触らない）
.claude/skills/llama-server/scripts/stop.sh mi25
.claude/skills/llama-server/scripts/start.sh mi25 "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072

# 4. t120h-p100 CUDA 回帰（可視性は触らない・枚数警告のみ）
.claude/skills/gpu-server/scripts/power-ctl.sh t120h-p100 on
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
.claude/skills/llama-server/scripts/start.sh t120h-p100 "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072

# 5. 後始末
.claude/skills/llama-server/scripts/stop.sh <server>
.claude/skills/gpu-server/scripts/unlock.sh <server>
.claude/skills/gpu-server/scripts/power-ctl.sh t120h-p100 off   # mi25 は bmc-power.sh mi25 soft
```

## 結論・対応

- **完了**: `start.sh` は起動前に vulkaninfo で RADV 物理 GPU を検出し `GGML_VK_VISIBLE_DEVICES` を
  実効枚数に追従させる。3枚→`0,1,2` / 4枚→`0,1,2,3` を出し分け、llvmpipe を巻き込まない。
  期待枚数（mi25=4/p100=4）を下回る場合は警告のみ出し、起動は中断しない。ROCm/CUDA は可視性
  不介入。
- **SKILL.md** の「サーバ別最適化パラメータ」表と「mi25 のバックエンド切替」節の注記を自動検出方式に
  更新（旧「`0,1,2,3` ハードコード・本対応のスコープ外」記述を撤回）。

## 既知の課題・今後

- **物理修復は未実施**: mi25 の SLOT4/SLOT8 の PCIe 物理層障害自体は遠隔修復不可で、4枚が安定して
  揃う保証はない（本検証時はたまたま4枚復帰）。本変更は**どの実効枚数でも破綻しない**ようにする対応で、
  物理障害そのものの解決ではない。物理対応の詳細は
  [4枚目脱落レポート](2026-06-14_131713_mi25_gpu4_pcie_dropout.md) を参照。
- **index 対応は ICD 列挙順に依存**: vulkaninfo と ggml-vulkan の列挙順一致は ICD ローダの決定性に
  依存する。Mesa/ドライバ更新時は `--list-devices` で再確認すること（コメントに明記済み）。
- **3枚構成での本番ライブ未確認**: 実効3枚時の警告＋`0,1,2` 起動は合成/単体テストで担保済みだが、
  実3枚ブートに当たった際にライブ確認できると万全。
- **（本タスク対象外の観測）mi25 の ttyd 監視UI 起動不安定**: 本検証で mi25 起動時に ttyd
  7681（GPU監視）/7682（ログ閲覧）が**両方とも LISTEN 失敗**した（`WARNING: ttyd ... LISTEN
  しません`）。一方 t120h-p100 では両ポート正常 LISTEN。本体（llama-server）には影響なく `/health`
  200 だが、mi25 固有の ttyd 起動不安定（`watch -n 1 rocm-smi` ラップや起動タイミング等）が疑われる。
  GPU 可視性とは無関係のため本対応では触らず、別件の調査余地として記録する。

## 参照レポート

- [mi25 4枚目MI25脱落＝PCIe物理層障害](2026-06-14_131713_mi25_gpu4_pcie_dropout.md)（実効枚数変動の原因）
- [mi25 Vulkan param sweep（start.sh のデバイス指定バグ発見）](2026-06-18_084557_mi25_vulkan_param_sweep.md)
- [mi25 Vulkan 品質検証（未設定時 RADV 自動選択の旧挙動）](2026-06-14_041305_mi25_vulkan_backend_quality.md)
