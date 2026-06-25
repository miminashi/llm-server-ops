# mi25 4枚 Vulkan 負荷追試 — ROCm 版 GPUVM フォルトの Vulkan 再現性検証

## Context(なぜ実施するか)

[2026-06-25_094641 mi25 4枚負荷検証レポート](../../projects/llm-server-ops/report/2026-06-25_094641_mi25_4card_load_gpuvm_fault.md) で、ROCm/HIP バックエンドの 4枚 offload 推論が **GPU 8820(SLOT6/87:00.0 / KFD node-5)で再現性ある GPUVM page fault** (`Memory access fault by GPU node-5` / `[gfxhub0] no-retry page fault` / UTCL2 / addr 0x100000000) を起こすことが確定した(4枚 2/2 / 3枚含8820 1/1 / 3枚除外8820 3/3完走)。物理層(PCIe x16・AER0)・熱(≤65℃)・電力(≤164W)は健全で、**compute/VRAM 層の突然死**と結論。

本タスクの目的は、**同じ負荷を Vulkan(RADV) バックエンドで投入して 8820 GPUVM フォルトが再現するかを確認**し、フォルトの「バックエンド非依存(=ハード/カード個体側)」か「ROCm/HIP メモリアロケータ経路特有」かを切り分けること。**スコープはユーザ確定で ROCm 版と完全対称(4枚 + 8820除外3枚 + 8820含む3枚 の3構成)** とし、ROCm 結果表に Vulkan 列をそのまま並べられる形にする。期待される分岐:

- **Vulkan でも 8820 フォルト**: フォルトはバックエンド非依存=カード個体/SLOT6 装着が根本(ROCm 結論の追認、4枚64GB 回復には物理対応が必須で確定)。
- **Vulkan は 4枚で安定**: フォルトは ROCm の HSA/HIP メモリ管理 or P2P/UTCL2 経路特有=**Vulkan が 4枚64GB 運用の実用的ワークアラウンドになる**(eval -40% を許容できれば本番に投入可)。

電源サイクルテストは前回 7/7 合格(再起動耐性は獲得済み・バックエンド非依存)のため **再実施しない**。本タスクは負荷テストのみに絞る。

## 現状ベースライン(調査済)

- mi25 電源 ON / 4枚認識継続(GUID 29525・33301・54068・8820 / 全ポート x16・AER0、原レポート data.md と同一構成)。
- llama-server 未起動 / ロック空き(本タスク内で取得)。
- Vulkan ビルド資産: `~/llama.cpp/build-vulkan/`(master 追従、`update_and_build-mi25.sh` の `MI25_BACKEND=vulkan` 分岐済み)。
- `start.sh` の `detect_radv_vk_indices()` が `vulkaninfo --summary` の RADV 物理 GPU を index 抽出して `GGML_VK_VISIBLE_DEVICES` に渡す(4枚なら `0,1,2,3`)。**ただし BDF 取得 helper は未実装** → 8820 (87:00.0) に対応する Vulkan index を本タスク内で確定する必要あり。

## 再利用する既存資産(新規作成を最小化)

| 資産 | パス | 用途 |
|---|---|---|
| 負荷ドライバ | `report/attachment/2026-06-24_161909_mi25_hang_repro_load_campaign/load_driver.py` | 合成連続推論負荷 + 三点ハング検出(`--backend vulkan` 受け入れ済) |
| キャンペーン制御 | 同上 `run_campaign.sh` | 試行ループ + MI25_BACKEND=vulkan の llama-up.sh 透過済(L74) |
| テレメトリ | 同上 `telemetry.sh` | rocm-smi(amdgpu カーネル層)/GPU枚数/dmesg/llama-server ログ |
| per-card PCIe サンプラ | `report/attachment/2026-06-25_094641_mi25_4card_load_gpuvm_fault/` 系列のサンプラ手順 | 4ルートポート LnkSta/PresDet/AER の 10秒毎採取 |
| 推論起動 | `MI25_BACKEND=vulkan .claude/skills/llama-server/scripts/llama-up.sh mi25 "<model>" 131072` | Vulkan で llama-server を起動(Phase 1 の 4 枚 auto 起動用) |

## 確定構成

- モデル: `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`、ctx=131072
- Vulkan: `--flash-attn 1 --poll 0 -b 2048 -ub 2048`、KV `q8_0`、split-mode layer(skill 既定 = ROCm と同一パラメータ。fa+q8_0 必須、f16 KV はホストが不安定化するため厳禁)
- 期待スループット: prompt ~3.3× ROCm / eval ~0.6× ROCm(eval ≈ 16.9 t/s @ 32k、原レポートの ROCm eval 22.9 と比較)
- 同一テストプロンプト・同一 trial-seconds で ROCm 結果と比較する

## 実施計画

### Phase 0: 準備(read-only + ロック取得 + Vulkan BDF mapping 確定)

1. `gpu-server` lock-status 確認 → `lock.sh mi25` でロック取得。
2. ベースライン採取(idle): 4枚認識・4ルートポート LnkSta/PresDet/AER・GUID(原レポート data.md と同条件)。
3. **Vulkan index ↔ BDF マッピングを ssh で確定**:
   - `ssh mi25 'vulkaninfo 2>/dev/null | awk "/^GPU[0-9]+/{idx=\$0} /pciDomain|pciBus|pciDevice|pciFunction|deviceName/{print idx,\$0}"'` 相当で各 GPU の `pciDomain:pciBus:pciDevice.pciFunction` を抽出。
   - 8820 = BDF `87:00.0` に対応する Vulkan index を確定し、4枚分の `idx → BDF → GUID` テーブルを `data.md` 風に記録。
4. テスト資産を scratchpad へコピー(`load_driver.py`/`run_campaign.sh`/`telemetry.sh` を `mi25-vulkan-load/` 配下に)。`run_campaign.sh` は backend 引数 `vulkan` で渡せばそのまま動く。エンドポイントは ROCm と同じ `http://10.1.4.13:8000`。
5. per-card PCIe+AER サンプラ(原レポート踏襲、`/sys/bus/pci/devices/0000:<RP>/aer_dev_correctable` を 10秒毎)を起動準備。

### Phase 1: Vulkan 4枚負荷テスト(主目的)

1. `MI25_BACKEND=vulkan llama-up.sh mi25 "<model>" 131072` → `/health` 200 待ち → 起動ログで **4枚 offload** を確認(Vulkan0〜Vulkan3 にモデルバッファ配置、llvmpipe が紛れ込んでいないこと)。
2. **走行強度(ユーザ確定: 完走時の倍伸ばしを最初から込みで開始)**:
   - `MAX_TRIALS=12 MIN_TRIALS=4 PHASE_CAP_SEC=14400 TRIAL_SEC=720 bash run_campaign.sh vulkan`(最初から約4時間/12試行上限で開始)。
   - フォルト発生時は load_driver/llama-server がクラッシュし `run_campaign.sh` のリトライループ内で停止判定(原 ROCm 実施と同じく、サーバ即死は rc≠42/43 の server_error_transient に分類されハング扱いされない=BMC 電源リセットは走らない)。**最初の trial でフォルトしたら手動で run_campaign.sh を停止**し dmesg 保全 → Phase 2 へ。
   - 完走パスでは ROCm 6 試行(~2h)を超えた **12 試行・約 4 時間** まで持って初めて「Vulkan は 4 枚で持続的に安定」と判定(原 ROCm 4枚 run の time-to-fault ~700s に対し約 20 倍長い窓を持って反証可能性を抑える)。
3. **フォルト検出基準(Vulkan 一般化)**:
   - **kernel 層(バックエンド共通)**: `dmesg | grep -iE "amdgpu 0000:[0-9a-f]+:00.0.*page fault|no-retry page fault|gfxhub0"` → 出るかどうか、出る場合の BDF(=どの GPU か)・address・ring・vmid・PERMISSION/MAPPING/WALKER。原 ROCm は `amdgpu 0000:87:00.0 ... [gfxhub0] no-retry page fault ... address 0x100000000`。**この行は ROCm/Vulkan 共通で出る**(amdgpu カーネルドライバ由来)。
   - **ユーザランド層(バックエンド依存)**: `Memory access fault by GPU node-N` は **HSA/ROCm ランタイム由来のメッセージで Vulkan では出ない**。Vulkan ではフォルト時に llama-server が `VK_ERROR_DEVICE_LOST` 等の Vulkan エラーで終了する想定。**Vulkan の `llama-server.log` 末尾と amdgpu kernel 行を組み合わせて判定**する。
   - **物理層**: 4 ルートポート x16 / AER0 / gpu_count=4 が全期間維持されるか(物理層は健全のはず)
   - **熱・電力**: junction 温度 / power cap 近傍ピーク(原 ROCm: ≤65℃ / ≤164W)
   - **タイミング規則性**: ROCm では `restored context checkpoint → 短いプロンプト → フォルト` で発火。Vulkan でも同パターンが出るか、ターン履歴量を load_driver JSONL から ROCm と対照。
4. **判定**:
   - フォルト発現(kernel page fault で BDF=87:00.0=8820) → time-to-fault と BDF を記録、手動停止 → dmesg/journalctl/llama-server.log を保全 → Phase 2 へ。
   - 別 BDF でフォルト → ROCm との差異(=Vulkan 特有のメモリ経路で別カードを踏む)として記録 → Phase 2 へ。
   - 12 試行(約4時間)完走 → 「Vulkan は 4 枚で安定」と暫定結論 → Phase 2 で control 補強。

### Phase 2: 切り分け(control: ROCm 版と完全対称の 2 構成)

Phase 1 の結果に関わらず、**ROCm 版の切り分け表(2026-06-25_094641 の §③)に Vulkan 列を完全に並べる**ため、以下 2 構成を必ず実施(ユーザ確定):

| 構成 | デバイス指定 | 含むGUID | 走行 | 期待 |
|---|---|---|---|---|
| 3枚 excl 8820 | `GGML_VK_VISIBLE_DEVICES=<8820以外の3枚>` | 29525,33301,54068 | `MAX_TRIALS=3 MIN_TRIALS=3 TRIAL_SEC=720` (~36分) | クリア(ROCm でクリア・control) |
| 3枚 incl 8820 | `GGML_VK_VISIBLE_DEVICES=<33301以外の3枚>` | 29525,54068,8820 | `MAX_TRIALS=3 MIN_TRIALS=3 TRIAL_SEC=720` (~36分以内、フォルト時は早期終了) | ROCm では ~1613s でフォルト。Vulkan で再現するか |

各構成は **llama-server を一旦 stop して `GGML_VK_VISIBLE_DEVICES` を明示指定して再起動**(skill 既定の auto では 4 枚を掴むため、原 ROCm 切り分けと同じく手動 export での起動)。具体的には `ssh mi25 "cd ~/llama.cpp && GGML_VK_VISIBLE_DEVICES=<idx_list> nohup ./build-vulkan/bin/llama-server -m <gguf> --jinja --n-gpu-layers 99 --split-mode layer --flash-attn 1 --poll 0 -b 2048 -ub 2048 --ctx-size 131072 --cache-type-k q8_0 --cache-type-v q8_0 --port 8000 --host 0.0.0.0 --alias '<model>' > /tmp/llama-server.log 2>&1 &"`(原レポート再現方法と同形)。

切り分け表が完成すれば、Vulkan 列 vs ROCm 列の対比で「バックエンド非依存(=8820 個体/SLOT6 確定)」「Vulkan 特異(=4枚運用ワークアラウンド)」「混合(=条件依存)」のいずれに落ちるかが一目で判断できる。

### Phase 3: 解析・レポート

1. campaign ログ・テレメトリ・per-card PCIe+AER・dmesg/journalctl を集計し、原 ROCm レポートと **同じ構造の比較表**(構成 × 連続負荷時間 × 結果)を作る。
2. 核心サマリ PNG([[feedback_report_title]] 準拠で「核心発見サマリ」セクション冒頭に PNG 埋め込み、タイトル50字以内):
   - 「Vulkan 4 枚負荷で 8820 が(フォルト/安定) — ROCm 比較」を示す図
3. レポートを [REPORT.md](../../projects/llm-server-ops/REPORT.md) 準拠で作成(`report/yyyy-mm-dd_hhmmss_mi25_4card_load_vulkan.md` + `report/attachment/<同名>/` にスクリプト・data.md・PNG・crash dmesg)。`report/INDEX.md` 更新。
4. 結論をメモリ [[project_mi25_gpu4_pcie_dropout]] / [[project_mi25_vulkan]] へ反映(Vulkan が 4 枚運用のワークアラウンドになる/ならないかが新事実)。
5. 必要なら Discord 通知。

## 最終状態の扱い

- llama-server 停止 → ロック解放。電源は **ON のまま idle で残す**(原 ROCm と同じ扱い)。

## リスクと留意点

- **Vulkan で f16 KV にしない**: 過去にホスト不安定→電源再投入を要した事象あり([[project_mi25_vulkan]])。本タスクは q8_0 のみ。
- **GGML_VK_VISIBLE_DEVICES 指定ミスで llvmpipe を巻き込むと OOM 破綻**([[project_mi25_vulkan_param_sweep]] の start.sh バグ事例)。Phase 0 で BDF mapping を必ず実機確認した上で除外/包含リストを作る。
- **フォルトの dmesg signature が ROCm と異なる可能性**: amdgpu kernel 層は共通だが Vulkan のメモリアロケータ経路で別 ring/vmid/アドレスになりうる。signature を機械的に grep する前に生 dmesg を抜粋して比較する。
- ハング時は **電源リセット前に必ず `bmc-screenshot.sh` で KVM スクショ保全**(CLAUDE.md / [[project_mi25_bmc_recovery]])。run_campaign.sh が既に組み込み済み。

## 検証(どう確かめるか)

- 4 枚 Vulkan run で run_campaign.sh の rc=0 完走 or rc=42(ハング)/サーバ即死 を確認。
- `telemetry_gpucount.log` 全行 `gpu_count=4`、per-card PCIe ログ全サンプル `x16`・AER COR デルタ 0(物理層健全)。
- フォルト時: `dmesg | grep -iE "amdgpu 0000:[0-9a-f]+:00.0|no-retry page fault|gfxhub0"` で signature と BDF を確認(amdgpu カーネル層・Vulkan/ROCm 共通)。ユーザランド層は ROCm のみ `Memory access fault by GPU node-N` が出るので Vulkan では llama-server.log の Vulkan エラー(VK_ERROR_DEVICE_LOST 等)で代用。
- ROCm 結果との対比表(構成 × 平均 time-to-fault / 完走可否 / フォルト signature)を作成。
- 1 件もフォルトせず Vulkan で完走できれば **Vulkan は 4 枚 64GB 運用のワークアラウンドになる**、フォルトすれば **8820 個体/SLOT6 がバックエンド非依存に破綻 = 物理対応必須を確証**、いずれにせよ実運用判断材料が増える。
