# mi25 CMOS バッテリー交換後の BIOS 再設定 (PCIe + Boot 順) 復旧プラン

## Context

**なぜ実施するか**
- 2026-07-12 05:01 JST に [CMOS バッテリー切れリブートループ](../../../projects/llm-server-ops/report/2026-07-12_045926_mi25_cmos_battery_reboot_loop.md) で mi25 (10.1.4.13, Supermicro X10DRG-Q) を BMC 経由 ACPI soft shutdown で停止済み。
- 本セッションで **CR2032 コイン電池は物理交換済み** (ユーザ作業)。**電池交換の際に GPU 4 枚は一時的に取り外している** (ユーザ確認済み、AskUserQuestion 回答)。
- 交換に伴い **BIOS 設定がデフォルトに戻った** ため、PCIe(GPU 4 枚認識) と Boot 順を再設定する必要がある。
- GPU 一時取り外しにより、**Unique ID ↔ SLOT/BDF の対応が変わっている可能性** がある (再装着位置の入れ替わり) — 復旧後の照合が必須。

**現状 (2026-07-17 開始時点で確認済)**:
- `bmc-power.sh mi25 status` = `System Power: on` (ユーザ交換後に自動投入か手動投入で ON)
- `ping 10.1.4.13` = 100% loss、`ssh mi25` = Connection timed out (OS 到達不可)
- BMC KVM スクショ: **Intel Boot Agent GE v1.5.72 が PXE ブート試行 → `NBP is too big to fit in free base memory` → `Reboot and Select proper Boot device` で停止**。BIOS デフォルト = ネットワークブート優先の典型症状で、これは PCIe 設定リセットではなく **Boot 順リセット** の症状。CMOS 交換自体は成功し、Boot Agent がここまで到達している以上ハードウェアは POST を完走している。

**期待する成果**:
- BIOS を「MMIO High Size 512GB」「MMIOHBase 3T」「Above 4G Enabled」「各 GPU スロット Gen3」「NVMe 1st boot」「Secure Boot Disabled」に再設定
- 起動後に `ssh mi25` 到達 + `rocm-smi --showuniqueid` で 4 枚 GPU の Unique ID (c3164/448c4/a48e4/c48c4) を認識
- **Unique ID ↔ SLOT/BDF 対応表を再作成** (物理再装着で入れ替わっている可能性大)
- BMC 時刻 +9h ずれの現状確認と対処 (原因は Timezone 設定 or BMC RTC ドリフト or CMOS 副作用のいずれか未確定、E ブロック参照)
- 以降 CMOS 電圧異常なし・リブートなしを 30 分観測

**前提条件**:
- ロック `aws-mmns-generic-2796720-20260712_050051` は前セッションから継続保持中の可能性が高い (要 `lock-status.sh mi25` で確認 → 期限切れなら再取得)。BIOS 操作は数十分かかるため、ロック TTL に注意 (過去の反省点、`2026-06-14_131713_mi25_gpu4_pcie_dropout.md` L120)
- KVM 経由のキー入力は `bmc-kvm.py sendkeys --prefer vkbd` で可 (Supermicro iKVM の `UI.rfb.sendMacro` 経路、BIOS/POST での確実な入力実績あり)
- Claude が BIOS 設定変更を BMC KVM 経由で実施することはユーザ既承認 (AskUserQuestion 回答)
- BMC/IPMI 経由の BIOS 項目直接変更は不可 (SUM DCMS ライセンス未活性)、KVM の手動操作が必須
- **BMC 認証情報**: `~/.config/gpu-server/.env` の `BMC_MI25_USER` / `BMC_MI25_PASS` を使用 (chmod 600, gitignore 済み)。`bmc-power.sh` / `bmc-screenshot.sh` は内部で読み込み。`ipmitool` を直接呼ぶ場合と `bmc-kvm.py` を呼ぶ場合は `source ~/.config/gpu-server/.env` で環境変数展開し、`-U "$BMC_MI25_USER" -P "$BMC_MI25_PASS"` / `--bmc-user "$BMC_MI25_USER" --bmc-pass "$BMC_MI25_PASS"` を渡す

---

## 復旧すべき BIOS 設定項目 (デフォルトからの差分)

過去レポート [2026-06-13_112006_mi25_qwen36_128k.md](../../../projects/llm-server-ops/report/2026-06-13_112006_mi25_qwen36_128k.md) と [2026-06-14_131713_mi25_gpu4_pcie_dropout.md](../../../projects/llm-server-ops/report/2026-06-14_131713_mi25_gpu4_pcie_dropout.md) の BIOS スクリーンショット 3 枚から抽出。

### A. Advanced → PCIe/PCI/PnP Configuration

| 項目 | デフォルト (推定) | 設定すべき値 | 必須度 | 根拠 |
|---|---|---|---|---|
| PCI PERR/SERR Support | Disabled | Disabled | — | 変更不要 |
| **Above 4G Decoding** | Disabled | **Enabled** | **必須** | 4 枚目 GPU (16GB Large-BAR) の 64-bit MMIO 配置に必要 |
| SR-IOV Support | Disabled | Disabled | — | 変更不要 (未使用) |
| Maximum Payload | Auto | Auto | — | |
| Maximum Read Request | Auto | Auto | — | |
| ASPM Support | Auto | Auto | — | |
| **MMIOHBase** | 56T (推定) | **3 T** | **必須** | 4×16GB Large-BAR + ブリッジ窓の余裕確保、MMIO High Size と組で機能 |
| **MMIO High Size** | 256 GB | **512 GB** | **必須** | 256GB では 4 枚目 GPU (`80:02.0` Root Port) が BIOS で無効化される。過去に 3 枚しか認識しない状態を経験 |
| MMCFG BASE | Auto | Auto | — | |

### B. Advanced → Chipset → North Bridge → IIO Configuration → IIO1

| 項目 | 設定値 | 備考 |
|---|---|---|
| IOU2 (IIO1 PCIe Port 1) | Auto | |
| CPU1 SLOT10 PCI-E 3.0 X8 (IN X16) Link | Gen 3 (8 GT/s) | |
| IOU0 (IIO1 PCIe Port 2) | Auto | |
| **CPU1 SLOT2 PCI-E 3.0 X16 Link Speed** | **Gen 3 (8 GT/s)** | GPU |
| IOU1 (IIO1 PCIe Port 3) | Auto | |
| **CPU1 SLOT4 PCI-E 3.0 X16 Link Speed** | **Gen 3 (8 GT/s)** | GPU |
| IIO1 IOU0 Non-Posted Prefetch | Disable | |
| IIO1 IOU1 Non-Posted Prefetch | Disable | |
| IIO1 IOU2 Non-Posted Prefetch | Disable | |

### C. Advanced → Chipset → North Bridge → IIO Configuration → IIO2

| 項目 | 設定値 | 備考 |
|---|---|---|
| IOU2 (IIO2 PCIe Port 1) | Auto | |
| CPU2 SLOT11 PCI-E 3.0 X8 Link Speed | Gen 3 (8 GT/s) | |
| IOU0 (IIO2 PCIe Port 2) | Auto | |
| **CPU2 SLOT8 PCI-E 3.0 X16 Link Speed** | **Gen 3 (8 GT/s)** | GPU 用 SLOT |
| IOU1 (IIO2 PCIe Port 3) | Auto | |
| **CPU2 SLOT6 PCI-E 3.0 X16 Link Speed** | **Gen 3 (8 GT/s)** | GPU 用 SLOT |
| IIO2 IOU0/1/2 Non-Posted Prefetch | Disable | |

- IIO1/2 の Link Speed は Auto でも Gen3 に落ち着くが、fault tracking セッションで 4 枚全て明示的に Gen3 固定してあったため、原状復帰として同じ設定にする
- どの GPU 個体 (c3164/448c4/a48e4/c48c4) がどの SLOT に入るかは Phase 7 の再照合結果で決まる — SLOT 側の Link Speed 設定は GPU 個体に依らず固定

### D. Boot Order (現状 PXE ブート試行 → 失敗)

| 項目 | 設定値 |
|---|---|
| **CSM Support / Boot Mode Select** | 現状値のまま (default 復帰後に確認、Legacy or UEFI+CSM が過去実績)。**default が UEFI-only になっていた場合は Legacy+UEFI (Dual) or Legacy に変更** (GRUB Legacy エントリを保持するため) |
| **1st Boot Device** | **NVMe/Hard Disk (Crucial P1, nvme0n1)** — nvme0n1p2 に Ubuntu 22.04.5 LTS ルート |
| 2nd Boot Device | UEFI Boot Manager (もし UEFI エントリがあれば) |
| Network Boot / PXE | **Disabled** (現症状の PXE E79 で数秒無駄になるため。Boot Option Priorities で最下位 or 無効化) |
| **Secure Boot** | **Disabled** (mi25 は amdgpu-dkms を signed 前提で運用していない、default で Enabled に戻ると起動失敗リスク、`Boot → Secure Boot` で確認) |

- 現症状の Intel Boot Agent GE = Legacy PXE OpROM が動いたことから **Legacy CSM 有効モード** の可能性が高い
- UEFI モードでも Ubuntu 22.04 は起動可 (GRUB2 EFI 経由)、default 復帰後の CSM 設定次第で判断
- ネットワーク PXE エントリを **削除するのではなく最下位に降ろす** のが安全 (BIOS 再設定時の副作用回避)

### E. BMC 時刻同期 (BIOS ではなく BMC Web UI or ipmitool)

- 前セッション観測で **BMC 時刻が +9h 先行** ([CMOS レポート L57](../../../projects/llm-server-ops/report/2026-07-12_045926_mi25_cmos_battery_reboot_loop.md))
- 原因は不明。可能性:
  - (i) BMC が UTC 保持で Timezone が Asia/Tokyo に未設定 (JST +9h と重複表示)
  - (ii) BMC 内蔵 RTC のドリフト
  - (iii) CR2032 電圧不足による副次障害 (前セッションが推定した仮説)
- **CMOS 交換で解消するのは (iii) の可能性のみ**。BMC 内蔵 RTC は CR2032 と独立している (Supermicro 一般) ため、Timezone 設定が主因なら復旧後も +9h ずれが継続する可能性が高い
- 復旧後にまず `ipmitool sel time get` で現時刻を確認、ずれの継続有無で原因を判定してから対処:
  - **方法 A (簡易・即時)**: `source ~/.config/gpu-server/.env; ipmitool -I lanplus -H 10.1.4.7 -U "$BMC_MI25_USER" -P "$BMC_MI25_PASS" sel time set "$(date '+%m/%d/%Y %H:%M:%S')"` で JST に一発同期
  - **方法 B (恒久)**: BMC Web UI https://10.1.4.7/ → `Configuration → Date and Time` → Timezone を Asia/Tokyo に設定 → NTP Enable + Server=`ntp.nict.jp` → Save
- OS 側 (Ubuntu): `sudo timedatectl set-timezone Asia/Tokyo` と `sudo systemctl status systemd-timesyncd` を確認 (default で NTP 同期)

---

## 実施手順

### Phase 0: 事前確認 (read-only)

```bash
# .env 読み込み (BMC 認証情報を BMC_MI25_USER / BMC_MI25_PASS に展開)
source ~/.config/gpu-server/.env

# ロック状態確認
.claude/skills/gpu-server/scripts/lock-status.sh mi25

# 電源・KVM 現況
.claude/skills/gpu-server/scripts/bmc-power.sh mi25 status
.claude/skills/gpu-server/scripts/bmc-screenshot.sh mi25 <scratchpad>/mi25_before_bios.png

# BMC 時刻 (+9h ずれの継続有無を判定)
ipmitool -I lanplus -H 10.1.4.7 -U "$BMC_MI25_USER" -P "$BMC_MI25_PASS" sel time get

# センサ健全性 (VBAT が復旧しているかを最重要チェック)
ipmitool -I lanplus -H 10.1.4.7 -U "$BMC_MI25_USER" -P "$BMC_MI25_PASS" sensor \
  | grep -iE "VBAT|CPU.*Temp|System Temp|12V|5VCC|3\.3VCC"
```

**中断判断**: VBAT が 3V 前後に復旧していない場合は電池交換失敗、BIOS 作業に進まずユーザ相談。

### Phase 1: BIOS 進入 (write, 電源リセット)

**方針**: `ipmitool chassis bootdev bios` で **次回起動時のみ BIOS Setup へ強制入場** させる (Delete 連打より確実、探索エージェント指摘)。

```bash
source ~/.config/gpu-server/.env    # BMC 認証情報の環境変数展開

# ロック取得 (前セッションから継続保持なら不要、要 lock-status.sh mi25 で確認)
.claude/skills/gpu-server/scripts/lock.sh mi25

# 次回起動時 BIOS 強制入場を予約
ipmitool -I lanplus -H 10.1.4.7 -U "$BMC_MI25_USER" -P "$BMC_MI25_PASS" chassis bootdev bios

# ハードリセットで再 POST
.claude/skills/gpu-server/scripts/bmc-power.sh mi25 reset

# POST 完走 + Setup 起動を待つ (30-60 秒)、KVM スクショで到達確認
sleep 45
.claude/skills/gpu-server/scripts/bmc-screenshot.sh mi25 <scratchpad>/mi25_bios_entry.png

# Aptio Setup Utility (American Megatrends) の Main タブに到達していれば成功
# 万一到達しない場合の fallback:
#   - Delete 連打を上乗せ:
#     .claude/skills/gpu-server/.venv/bin/python \
#       .claude/skills/gpu-server/scripts/bmc-kvm.py \
#       --bmc-ip 10.1.4.7 --bmc-user "$BMC_MI25_USER" --bmc-pass "$BMC_MI25_PASS" \
#       sendkeys Delete Delete Delete Delete Delete \
#         --wait 4000 --prefer vkbd --screenshot <scratchpad>/mi25_bios_entry2.png
```

- 各キー入力・遷移で `--screenshot <path>` を付けて画面遷移を保全 (後のレポートに使う)

### Phase 2: PCIe/PCI/PnP 設定 (A ブロック)

矢印キー / Enter / +/- / F10 を `bmc-kvm.py sendkeys` で組み合わせて実施。各設定後にスクショで結果確認。

1. Right/Left で **Advanced タブ** へ移動
2. Down で `PCIe/PCI/PnP Configuration` にカーソル → Enter
3. `Above 4G Decoding` → Enter → `Enabled` 選択 → Enter
4. `MMIOHBase` → Enter → `3 T` 選択 → Enter
5. `MMIO High Size` → Enter → `512 G` 選択 → Enter
6. Esc で 1 レベル上に戻る

**キー送信例** (実際は各ステップ後にスクショで状態確認しつつ進める):
```bash
source ~/.config/gpu-server/.env
.claude/skills/gpu-server/.venv/bin/python .claude/skills/gpu-server/scripts/bmc-kvm.py \
  --bmc-ip 10.1.4.7 --bmc-user "$BMC_MI25_USER" --bmc-pass "$BMC_MI25_PASS" \
  sendkeys Right --prefer vkbd --screenshot <scratchpad>/mi25_bios_advanced.png
```

### Phase 3: IIO1/IIO2 Link Speed 設定 (B, C ブロック)

1. Advanced → Chipset → North Bridge → IIO Configuration へ移動
2. IIO1 Configuration → 各 SLOT の Link Speed を **Gen 3 (8 GT/s)** に設定
   - CPU1 SLOT10, CPU1 SLOT2, CPU1 SLOT4
3. Esc → IIO2 Configuration → 同様に
   - CPU2 SLOT11, CPU2 SLOT8, CPU2 SLOT6

- 各値変更後にスクショで確認
- Non-Posted Prefetch は BIOS デフォルトが Disable なら変更不要 (要確認)

### Phase 4: Boot 順設定 (D ブロック)

1. Right で **Boot タブ** へ移動 (スクショで現状把握)
2. `Boot Mode Select` / `CSM Configuration` の現状値を確認
   - **default が Legacy or Legacy+UEFI (Dual) だった場合**: 現状値を維持
   - **default が UEFI-only になっていた場合**: `Legacy+UEFI (Dual)` に変更 (GRUB2 の Legacy MBR エントリを維持しつつ UEFI 経路も許容、過去実績に近い形)
3. `Boot → Secure Boot` が `Enabled` になっていたら **Disabled** に (amdgpu-dkms 非署名運用のため)
4. `Boot Option Priorities` → `1st Boot Device` を **NVMe デバイス (Crucial P1, `nvme0n1` 相当のエントリ)** に設定
   - Legacy モードでは `Hard Disk: Crucial CT500P1SSD8` などのエントリ、UEFI モードでは `UEFI: Crucial CT...` エントリを選ぶ
   - パーティション (nvme0n1p2) はブートデバイス選択肢に出ない (BIOS はデバイス単位で選択)
5. `Boot Option Priorities` のネットワーク PXE エントリ (Intel I350) を最下位に降ろす or 無効化
6. `Save & Exit` は Phase 5 で実施

### Phase 5: Save & Exit

1. F4 (Save & Exit) → Enter で確認
2. 再起動待ち (POST 30-60 秒)
3. Ubuntu GRUB → login: プロンプト到達を KVM スクショで確認

### Phase 6: BMC 時刻同期

```bash
source ~/.config/gpu-server/.env

# 現時刻取得 (+9h ずれ継続の有無を判定)
ipmitool -I lanplus -H 10.1.4.7 -U "$BMC_MI25_USER" -P "$BMC_MI25_PASS" sel time get

# ずれが継続していれば JST に手動同期
TARGET=$(date +"%m/%d/%Y %H:%M:%S")
ipmitool -I lanplus -H 10.1.4.7 -U "$BMC_MI25_USER" -P "$BMC_MI25_PASS" sel time set "$TARGET"

# 再確認
ipmitool -I lanplus -H 10.1.4.7 -U "$BMC_MI25_USER" -P "$BMC_MI25_PASS" sel time get

# 恒久解決を望む場合は BMC Web UI で Timezone=Asia/Tokyo + NTP Enable を設定 (E ブロック参照)
```

### Phase 7: 復旧検証

**注**: GPU は電池交換で一時取り外し済み。**Unique ID ↔ SLOT/BDF 対応の再照合が必須** (物理再装着で入れ替わっている前提で検証、07-12 停止直前の対応は「参考値」扱い)。

```bash
source ~/.config/gpu-server/.env

# 1. OS 到達
ping -c 5 10.1.4.13
ssh mi25 "uptime; hostname; date"

# 2. 4 枚 GPU 認識 (最重要)
ssh mi25 "lspci | grep -c 'Instinct MI25'"    # 4 が期待値。3 以下なら MMIO 設定を疑う
ssh mi25 "lspci -tnnv | grep -A1 'Instinct MI25' | head -20"   # BDF ツリー

# 3. Unique ID ↔ SLOT/BDF 対応表を再作成 (物理入れ替わりの検証が主目的)
ssh mi25 "rocm-smi --showuniqueid --showbus"   # 4 個の Unique ID と BDF
ssh mi25 "sudo dmidecode -t 9 | grep -E 'Bus Address|Designation' | head -20"   # SMBIOS SLOT 名

# 参考値 (07-12 停止直前の配置、変更されている可能性大):
#   BDF 04:00.0 = card-c3164
#   BDF 07:00.0 = card-448c4
#   BDF 87:00.0 = card-a48e4 (SMBIOS CPU2 SLOT6)
#   BDF 84:00.0 = card-c48c4 (SMBIOS CPU2 SLOT8, Unique ID 0x21501edbcec48c4)
# 4 個の Unique ID (c3164/448c4/a48e4/c48c4) が全て揃うことを確認。
# BDF/SLOT 対応が変わっていれば [[project_mi25_gpu4_pcie_dropout]] memory を更新。
# ※ SMBIOS SLOT 番号は upstream bridge の bus 番号なので、GPU 本体 BDF は
#   lspci -tnnv で PCIe tree を辿って照合 (CLAUDE.md の SMBIOS スロット節参照)

# 4. amdgpu 初期化正常性
ssh mi25 "sudo dmesg | grep -E 'amdgpu|VBIOS' | head -30"
ssh mi25 "sudo dmesg | grep -iE 'error|fail|GPU reset' | head -20"

# 5. リブート発生ゼロ (30 分観測)
ssh mi25 "sudo journalctl --list-boots --no-pager | tail -5"
# → 30 分後に再確認、boot 0 のまま uptime が伸びていること

# 6. BMC センサ健全 (VBAT 3V 前後 = 電池交換の効果確認)
ipmitool -I lanplus -H 10.1.4.7 -U "$BMC_MI25_USER" -P "$BMC_MI25_PASS" sensor \
  | grep -iE "VBAT|CPU.*Temp|12V|5VCC|3\.3VCC|Chassis"

# 7. BMC SEL に新規 VBAT アラートが出ていないこと
ipmitool -I lanplus -H 10.1.4.7 -U "$BMC_MI25_USER" -P "$BMC_MI25_PASS" sel elist | tail -20
```

**Unique ID ↔ SLOT/BDF の対応変更が検出された場合の対応**:
- `project_mi25_gpu4_pcie_dropout` memory の `HIP_VISIBLE_DEVICES` マッピングを更新 (SLOT8=c48c4 なら `0,1,3`、SLOT6=c48c4 なら `0,1,2` 等)
- fault tracking の SLOT 帰属分析 (Fable D-1〜D-5 系列) にも影響するので、memory 更新と Fable 側の追記を対で行う

### Phase 8: ロック解放と証跡整理

- scratchpad の BIOS 進入前/各 Phase 完了時/最終 login プロンプトのスクショを report attachment に移動
- `.claude/skills/gpu-server/scripts/unlock.sh mi25`
- 本作業のレポートを `report/2026-07-17_*_mi25_bios_restore_after_cmos.md` として作成

---

## 想定される問題と対処

| 問題 | 対処 |
|---|---|
| `chassis bootdev bios` で BIOS 進入できない | Delete 連打を fallback で試行 (`bmc-kvm.py sendkeys --prefer vkbd Delete Delete ...`)。または `bmc-power.sh mi25 cycle 20` の cold boot 後に再試行 |
| KVM canvas が黒画になる | `bmc-screenshot.sh` のトラブルシュート節参照。noVNC_connect_button クリック相当を bmc-kvm.py で送る |
| BIOS が UEFI-only モードにデフォルト復帰していた | Boot → CSM Support を Enabled にし、Legacy PXE を無効化しつつ Legacy/UEFI (Dual) にする。または UEFI Boot Order で `UEFI: Crucial ...` を第一位に上げる |
| Secure Boot が Enabled に復帰していた | Boot → Secure Boot → Disabled に設定 (amdgpu-dkms が非署名のため) |
| 4 枚 GPU 認識せず 3 枚のまま | MMIO High Size が反映されていない。BIOS 再進入で確認。cold boot (`bmc-power.sh cycle 20`) も検討 |
| VBAT が交換後も低い (< 2.5V) | 電池不良の可能性。ユーザに追加交換を依頼、BIOS 作業は中断 |
| BMC 時刻がリブート後にまた +9h ずれる | E ブロックの原因判定 (Timezone 未設定 / RTC ドリフト / CMOS 副作用) を先に切り分け。Timezone 未設定なら BMC Web UI で Asia/Tokyo 設定で恒久解決。RTC ドリフト・CMOS 副作用の場合は Supermicro FW 更新か個体交換の相談 |
| GPU の Unique ID ↔ BDF/SLOT が過去記録と違う | 物理再装着で入れ替わり済。**BDF↔Unique ID 対応表を再作成し、`project_mi25_gpu4_pcie_dropout` memory を更新**。fault tracking の SLOT 帰属分析にも影響するので Fable レビュー D-1〜D-5 側にも反映 |
| GRUB が起動しない (BIOS 再設定後) | Boot Mode/CSM/UEFI エントリの選択ミスの可能性。BIOS Setup で NVMe デバイスの認識と `Boot Option Priorities` の先頭項目を確認。必要なら Ubuntu USB Live で `grub-install` |

---

## 参考ファイル

**必読レポート**:
- [報告書: CMOS バッテリー切れ](../../../projects/llm-server-ops/report/2026-07-12_045926_mi25_cmos_battery_reboot_loop.md) — 本作業の起点
- [報告書: 4 枚復旧 (BIOS MMIO 512GB 設定の初回導入)](../../../projects/llm-server-ops/report/2026-06-13_112006_mi25_qwen36_128k.md)
- [報告書: PCIe dropout (BIOS 詳細確認、IIO Link Speed 設定)](../../../projects/llm-server-ops/report/2026-06-14_131713_mi25_gpu4_pcie_dropout.md)

**BIOS スクリーンショット (原状復帰の参照画像、リポジトリルート `/home/ubuntu/projects/llm-server-ops/` からの相対パス)**:
- `report/attachment/2026-06-14_131713_mi25_gpu4_pcie_dropout/bios-pcie-above4g-mmio.png` — Above 4G / MMIO High Size 512GB / MMIOHBase 3T
- `report/attachment/2026-06-14_131713_mi25_gpu4_pcie_dropout/bios-iio1-linkspeed.png` — IIO1 SLOT2/4/10
- `report/attachment/2026-06-14_131713_mi25_gpu4_pcie_dropout/bios-iio2-linkspeed.png` — IIO2 SLOT6/8/11

**BMC 操作スクリプト** (プロジェクトルート相対、CLAUDE.md ルール準拠):
- `.claude/skills/gpu-server/scripts/bmc-power.sh` — 電源制御 (`.env` 経由で認証)
- `.claude/skills/gpu-server/scripts/bmc-kvm.py` — キー送信 + スクショ (認証は CLI 引数、`.env` から展開)
- `.claude/skills/gpu-server/scripts/bmc-screenshot.sh` — 単発スクショ (`.env` 経由で認証)
- `.claude/skills/gpu-server/bmc.md` — BMC 操作マニュアル
- `~/.config/gpu-server/.env` — BMC 認証情報 (`BMC_MI25_USER` / `BMC_MI25_PASS`、chmod 600)

**メモリ**:
- `project_mi25_qwen36_128k` — MMIO 512GB 依存の記録
- `project_mi25_bmc_recovery` — BMC 経由の操作手順
- `project_mi25_gpu4_pcie_dropout` — 4 枚 GPU の物理配置と Unique ID

---

## レポート化 (作業完了後)

REPORT.md ルールに従い、以下を `report/YYYY-MM-DD_HHMMSS_mi25_bios_restore_after_cmos.md` として作成:
- 核心発見サマリ: BIOS 再設定完了、4 枚 GPU 認識復旧、リブートループ再発なし
- 添付: 交換後の初回 KVM スクショ、BIOS 設定 3 種のスクショ (Above 4G / IIO1 / IIO2)、login プロンプト、rocm-smi --showuniqueid 結果、`ipmitool sensor` VBAT 復旧確認
- 副次発見: (もしあれば) BMC 時刻同期の残課題、電池交換で消えた設定の網羅性、GPU 物理配置の変化有無
