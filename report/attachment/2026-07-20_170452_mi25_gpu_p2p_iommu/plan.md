# mi25 GPU ピア間通信 (P2P) 有効性の調査と検証

## Context

mi25 は MI25 (Vega10, gfx900) 4 枚構成で、実運用では Vulkan (RADV) を default、ROCm/HIP を fallback として使用している。llama.cpp の 4 枚 tensor-split / split-mode-layer で GPU 間テンソル転送が発生するが、**ピア間通信 (P2P) が実効的に効いているか、host bounce にフォールバックしているかは未検証**。

過去に調査済みの内容 (Explore 結果):
- `rocm-smi --showtopo` の観察 (2026-06-25 2 枚時、Link Type=PCIE、XGMI 無し)
- 4 枚時の showtopo は未取得だった → **本計画の Phase 1 で 2026-07-20 現在の 4 枚 topology を取得済み** (下記)
- `rocm-bandwidth-test` / `hipMemcpyPeer` / `canAccessPeer` / IOMMU / ACS の実測は**一度も無い**

Read-only で判明した重要事実 (2026-07-20 開始時):
- 4 枚検出: GPU0=c3164, GPU1=448c4, GPU2=c48c4, GPU3=a48e4 (NUMA: 0,0,1,1)
- Weight: 同一 NUMA 内 40 (hops 2)、異 NUMA 間 61 (hops 3)、全 Link=PCIE
- `/proc/cmdline` に IOMMU 引数なし、`dmesg` に `AMD-Vi/DMAR/IOMMU` メッセージなし → **IOMMU 実効無効** (**カーネル側で off、BIOS 側の状態は未確認**)
- `modinfo amdgpu` → `pcie_p2p:Enable PCIe P2P (requires large-BAR). (N = off, Y = on(default))` → **既定で有効、Large-BAR 前提**
- `use_xgmi_p2p` は default 1 だが MI25 に XGMI 無いので無関係
- 87:00.0 GPU 端点は `ACSCap: all disabled` (Vega10 に ACS なし)
- `rccl 2.20.5.60202-116~22.04` はインストール済み、`rocm-bandwidth-test` は未インストール

結論の見通し: 環境的には P2P が有効化しうる条件 (IOMMU off + `pcie_p2p=Y` + Large-BAR 予定) が揃っている可能性が高い。**実測で確認**し、host bounce かどうか帯域から判定するのがゴール。

**IOMMU と P2P の相互作用 (重要)**:
- IOMMU 完全 OFF: PCIe P2P は root complex 経由で直接動く (現状の見込み)
- IOMMU ON + **isolation モード** (kernel default): IOMMU が DMA アドレスを翻訳するため GPU→GPU P2P は**ブロック**される (悪化)
- IOMMU ON + **passthrough モード** (`iommu=pt`): GPU の DMA は IOMMU をバイパス、P2P 動作 + 他デバイスは IOMMU 保護
- したがって「BIOS IOMMU を有効化するだけ」は P2P を悪化させるリスクがあり、必ず `iommu=pt` とセットで検討する

## 目的

1. mi25 4 枚間の P2P が実効的に効いているか実測で判定
2. BIOS 側の IOMMU (Intel VT-d) 状態を BMC KVM 経由で確認し、Disabled なら有効化して P2P への効果を測定する (ユーザ明示指示)
3. カーネル側 P2P も含めて、可能な有効化パスをすべて試して before/after を比較
4. 有効な構成での帯域と、Vulkan バックエンドでの llama-server 実効性能への寄与をベンチマーク

## 進め方 (Phase 構成)

### Phase 0: 事前準備

- `.claude/skills/gpu-server` の SKILL に従いロック取得 (実負荷を伴うため)
- 現状 pin/branch/HEAD の記録 (llama.cpp)
- 進捗管理は TaskCreate/TaskUpdate で追跡

### Phase 1: 環境静的評価 (read-only、追加確認)

- **Large-BAR 確認**: `lspci -vvv -s <GPU BDF>` で Region 0 が 16GB (`Memory at ... 64-bit, prefetchable [size=16G]`) を確認 (Above 4G Decoding 有効の証跡)
- **上流ブリッジ ACS**: `sudo lspci -vvv` で upstream/downstream bridge (`85:00.0`, `86:00.0` 等) の ACSCap/ACSCtl を確認 (root complex で分岐されるか、bridge が ACS で分離してるかで P2P 経路が変わる)
- **PCIe topology**: `lspci -tnnv` で GPU の PCIe 距離を確認 (既に NUMA0=SLOT2/4、NUMA1=SLOT6/8 と判明済み、weight 40 と 61 の内訳確認)
- **kernel 側 amdgpu 実行時パラメータ**: `cat /sys/module/amdgpu/parameters/pcie_p2p` で実効値確認

### Phase 1.5: BIOS 側 IOMMU (Intel VT-d) 状態の**確認のみ** (要 BMC KVM、要ロック)

Supermicro X10DRG-Q は Intel Xeon E5-2600 v3/v4 → IOMMU = **Intel VT-d**。

**重要**: この Phase は「観察のみ」で BIOS 設定は**変更しない**。変更は Phase 4 で行う。

- `.claude/skills/gpu-server/scripts/bmc-power.sh mi25 soft` でグレースフル停止 (ロック取得下)
- `bmc-power.sh mi25 on` で起動、POST で `bmc-kvm.py sendkeys Delete Delete Delete --screenshot` で BIOS 進入
- BIOS メニューを画面遷移しながらスクショ収集し、`Intel Virtualization Technology for Directed I/O (VT-d)` の Enable/Disable 状態を確認
  - 典型的な経路: `Advanced` → `Chipset Configuration` → `North Bridge` → `IIO Configuration` → `Intel VT for Directed I/O (VT-d)`
  - 別経路 (SKU 依存): `Advanced` → `Integrated IO Configuration` → `Intel VT-d`
- **確認後は必ず `Esc` (Discard changes and exit) で終了し、設定は変更しないまま通常起動へ**
- 起動後 SSH 復旧を確認して Phase 2 へ
- 現状 Disabled と推定 (dmesg の証跡から)。予想外の Enabled 判明時は Phase 4-B の分岐に進む
- **なぜ Phase 1.5 で変更しないか**: Phase 2/3 の before 実測を「現状のまま」で取る必要があるため。Phase 4 で変更 → after 実測、という順序で before/after 比較が成立する

### Phase 2: P2P 動作の直接確認 (要ロック)

- **hipDeviceCanAccessPeer マトリクス**: 20 行程度の HIP 単発コード (`~/scratch/hip_peer_check.cpp`) を作成し、4x4 で `canAccessPeer` を照会、`hipDeviceEnablePeerAccess` の成否を確認
  - ビルド: `hipcc -o hip_peer_check hip_peer_check.cpp`
  - 実行: `HIP_VISIBLE_DEVICES=0,1,2,3 ./hip_peer_check`
- **簡易 hipMemcpyPeer 帯域**: 上記コードに 256MB / 1GB のバッファで hipMemcpyPeerAsync + hipEventElapsedTime を追加し、GB/s を出す
  - 判定基準: **PCIe 3.0 x16 の理論 15.75 GB/s の 50-80% (≒8-13 GB/s) 出れば P2P 有効**、5 GB/s 前後で頭打ちなら **host bounce (RAM 経由)** の疑い

### Phase 3: rocm-bandwidth-test の導入と本測

- **入手**: 以下優先順で試す
  1. `apt install rocm-bandwidth-test` (ROCm 6.x apt repo にあるはず)
  2. なければ `git clone https://github.com/ROCm/rocm-bandwidth-test` → `cmake`/`make` (ROCm SDK 前提、依存少)
- **測定**:
  - `rocm-bandwidth-test -e` (全 device 列挙)
  - `rocm-bandwidth-test -a` (全パターン: H2D/D2H/D2D 単方向・双方向)
  - `rocm-bandwidth-test -m 268435456` (256MB) と `-m 1073741824` (1GB) の 2 サイズ
- 出力を attachment に保存

### Phase 4: BIOS IOMMU 有効化と effect 測定 (ユーザ指示による必須手順)

ユーザ指示は「BIOS で IOMMU を確認、Disabled なら Enable して効果を確認」。したがって **Phase 2/3 の P2P 実測結果に関わらず、BIOS IOMMU が Disabled ならば有効化して before/after を比較する**。

#### 4-A. Phase 1.5 で BIOS VT-d が Disabled と確認された場合 (最有力ケース)

1. Phase 2/3 の before 実測を保存 (P2P 帯域、canAccessPeer、llama-bench 参照値)
2. `/etc/default/grub` を scratchpad にバックアップ → `GRUB_CMDLINE_LINUX_DEFAULT` に **`iommu=pt intel_iommu=on`** を追加 → `sudo update-grub`
   - 順序が重要: **BIOS 変更「前」に kernel 引数を仕込む**。VT-d 有効化直後の起動時に既に passthrough で入ることで P2P 悪化を回避
3. `bmc-power.sh mi25 soft` でグレースフル停止
4. `bmc-power.sh mi25 on` で起動、POST で BIOS 進入 → Intel VT-d を Enable → `F4` (Save & Exit) → `Y`
5. 起動後 `dmesg | grep -iE 'IOMMU|DMAR|VT-d'` で `Intel-IOMMU: enabled` `IOMMU: passthrough` を確認
6. Phase 2/3 と同じ手順で after 実測 (canAccessPeer、rocm-bandwidth-test)
7. before/after を並記して比較

#### 4-B. Phase 1.5 で BIOS VT-d が既に Enabled と確認された場合

- kernel 側で `intel_iommu=off` されている or 何もされていない状態を確認
- 効果測定として:
  - まず `iommu=pt intel_iommu=on` を GRUB に追加して再起動、P2P 帯域を測定
  - 現状 (VT-d 有効 + kernel 側何もなし = isolation モード) vs passthrough モードの差を before/after として記録
- ユーザ意図の「無効なら有効化」は既に満たされているので、BIOS 側の変更はしない

#### 4-C. Phase 2/3 で P2P 帯域が 5 GB/s 未満と判明した場合 (追加調査)

上記 4-A/4-B の実施後、なお帯域が低い場合:

- `numactl --cpunodebind` で CPU node を GPU NUMA と揃えて再測
- upstream bridge の ACS 状態を再確認、Ubuntu 22.04 kernel が `pcie_acs_override` パッチを含むかを `grep -r 'pcie_acs_override' /proc/config.gz` 等で確認 (通常 vanilla では非対応 → 試さない)
- Above 4G / MMIO 512GB は既運用の VRAM 認識に影響するため触らない (`project_mi25_qwen36_128k.md` の警告に従う)

**共通の安全策**:
1. 変更前に `/etc/default/grub` を scratchpad にバックアップ
2. BIOS 変更前後で `bmc-screenshot.sh` で BIOS 設定画面をキャプチャ (証跡)
3. 各再起動後は SSH 復旧確認 → 不可なら BMC KVM で POST 画面確認 → 最悪 BIOS を再度開いて設定戻し
4. 各段階で `dmesg | grep -iE 'IOMMU|DMAR|VT-d'` を保存し、実効状態を証跡化
5. 失敗時のロールバック手順を最初に確立 (grub 差し戻し + BIOS VT-d Disable)

### Phase 5: llama-server ベンチマーク (Vulkan のみ、ユーザ確定)

**方針**: 常用の Vulkan バックエンドに絞る。P2P (hipMemcpyPeer) は HIP レイヤの概念だが、Vulkan バックエンドも内部で GPU 間コピーを行うため、PCIe P2P の下地が効いていれば `--split-mode row` で恩恵があるはず。効かなければ Vulkan は host bounce のまま、という切り分けが可能。

**モデル選定**: 4 枚使い切る & tensor 転送量が多い構成
- **一次候補**: Qwen3-122b-c3 (実運用構成、~127GB)
- llama-server skill の `MI25_BACKEND=vulkan` (default) で起動

**軸**:
- **--split-mode**: `layer` (default) vs `row`
  - `row` は tensor 転送量が桁違いに増える → 帯域律速 → P2P 有無で顕著な差
  - `layer` はレイヤー境界のみ転送 → 帯域影響小 (control 群)
- **--tensor-split**: 均等 (`25,25,25,25`)。ただし c48c4×SLOT6 のフォルト履歴を踏まえ、ハング検知したら `HIP_VISIBLE_DEVICES=0,1,3` で 3 枚版にフォールバック
- **numa affinity**: `numactl --cpunodebind` で CPU node を GPU NUMA と合わせるかどうかを 2 水準

**指標**:
- prompt eval (pp)、eval (tg) の t/s (llama-bench)
- 起動時 VRAM 割当ログ、tensor 転送関連の警告

**プロトコル**:
- 各構成で 3 回計測、中央値採用
- llama-bench (推奨) で最短化

**タイミング** (重要、Phase 4 との関係):
- **before 測定**: Phase 3 完了時、Phase 4 の変更を実施する「前」に llama-bench を全軸ラン。Phase 4 のロールバックが起きても before 値が残るように attachment に生ログ保存
- **after 測定**: Phase 4 完了後 (BIOS/kernel 変更 → 再起動 → dmesg 確認済み後) に同じ軸を再ラン
- before/after 両方が揃った状態で比較表を作成 (これが本計画のユーザ意図の中核)

### Phase 6: レポート作成

`REPORT.md` に従い `report/YYYY-MM-DD_HHMMSS_mi25_gpu_p2p.md` を作成:
- 概要 (必須、50 字以内タイトル、核心発見サマリに PNG 埋め込み)
- 環境 (BIOS/kernel/ROCm バージョン、Large-BAR、IOMMU 状態、amdgpu パラメータ)
- Phase 1-5 の実施結果、attachment に生ログ
- 4 枚実運用への示唆 (Vulkan バックエンドでの split-mode 選定指針、P2P 有効化による効果の有無、通常運用に反映すべきか)

## 主要ファイル

### 参照 (read)
- `CLAUDE.md` — mi25 セクション、Vulkan default、gfx900 pin
- `REPORT.md` — レポートフォーマット
- `.claude/skills/gpu-server/SKILL.md` (ロック管理), `bmc.md` (緊急復旧手段の把握)
- `.claude/skills/llama-server/SKILL.md`, `scripts/start.sh` (バックエンド切替、パラメータ)
- `report/2026-06-25_063238_mi25_4card_recovery.md` (`--showtopo` 2枚時の観察)
- `report/2026-06-29_213624_mi25_4card_uniqueid_baseline.md` (現在の Unique ID ↔ SLOT ↔ GUID 対応)
- `report/2026-07-20_013500_mi25_prompt_eval_regression.md` (直近の pp 退行、バックエンド反転)
- `~/.claude/projects/-home-ubuntu-projects-llm-server-ops/memory/project_mi25_gpu4_pcie_dropout.md`

### 新規作成 (write, Phase 実施時)
- `hip_peer_check.cpp` (Phase 2、mi25 サーバ側 `~/` 配下に置く。ローカルにミラー不要、ソースは attachment に添付)
- `report/YYYY-MM-DD_HHMMSS_mi25_gpu_p2p.md` (Phase 6)
- `report/attachment/YYYY-MM-DD_HHMMSS_mi25_gpu_p2p/` (生ログ・PNG・hip_peer_check.cpp・BIOS スクショ)

### 変更する (Phase 4 内で明示的に、ユーザ許可済み)
- `/etc/default/grub` (`GRUB_CMDLINE_LINUX_DEFAULT` に `iommu=pt intel_iommu=on` を追加)
- BIOS 設定 (BMC KVM 経由で Intel VT-d の Enable/Disable を変更)

### 一切変更しない
- BIOS の `Above 4G Decoding` / `MMIO High Size` (VRAM 認識に影響、現運用が MMIO 512GB 依存のため触らない)
- llama-server skill の `scripts/start.sh` などのビルド済み構成 (ベンチのために MI25_BACKEND=vulkan 以外に切り替えたりしない)

## 検証 (End-to-end)

1. `ssh mi25 "cat /sys/module/amdgpu/parameters/pcie_p2p"` が `Y`
2. Phase 2 の `hip_peer_check` が全 4x4 で `canAccessPeer=1` を返し、hipMemcpyPeerAsync が例外なく成功
3. Phase 3 の `rocm-bandwidth-test -a` が全 device で完走、D2D peer 帯域が測定される (絶対値の目標なし。値そのものが本調査の成果物)
4. Phase 4 前後で `dmesg | grep -iE 'IOMMU|VT-d'` の内容が変化していることを証跡化 (Enabled/Disabled/passthrough)
5. Phase 5 の llama-bench で pp/tg の再現性 (3 回中央値のばらつき ±3% 以内)、Phase 4 前後で同一構成を比較して差分が算出できている
6. レポート最終形が REPORT.md の必須セクション (概要、環境、方法、結果、考察、次アクション) を満たす

## リスクとブレーキ

- **c48c4×SLOT6 の既知フォルト**: 短時間の P2P 帯域測定 (<5 分/構成) では発火しない見込みだが、`hip_peer_check` は SIGINT で速やかに落とせるように設計
- **BIOS 変更 (VT-d) は BMC KVM 経由で遠隔可能** (Above 4G/MMIO 512GB は触らない、変更すると VRAM 認識に影響)
- **VT-d 有効化と `iommu=pt` の順序**: BIOS で VT-d 有効化する時は、事前に GRUB に `iommu=pt intel_iommu=on` を入れて `update-grub` してから再起動する。逆順にすると isolation モードで P2P が悪化
- **rocm-bandwidth-test ビルド失敗**: 代替として `hip_peer_check` の帯域測定機能を拡張して代用
- **ロック競合**: gpu-server スキルの排他制御を必ず経由
- **BIOS 進入失敗時の復旧**: `bmc-power.sh mi25 reset` でハードリセット → POST から再度 Delete 連打。連続失敗時はいったん通常起動に戻し、ユーザに現状報告
- **BIOS 設定が保存されない**: X10DRG-Q の BIOS 設定変更は `F4` (Save & Exit) → `Y` で確定。sendkeys で確実に反映されるかは要確認
