# 収集データ（生ログ要約） — mi25 2/3/4枚 段階増設

収集日: 2026-06-25 (JST)。すべて読み取り専用（lspci / rocm-smi / dmesg / dmidecode / journalctl / sysfs AER）。

## 環境（全構成共通）

```
機種:    Supermicro SYS-7048GR-TR / M/B X10DRG-Q
BIOS:    American Megatrends Inc. Ver 3.2 (2019-11-22)
CPU:     Intel Xeon E5-2620 v3 ×2 (各6コア/12スレッド, デュアルソケット=2 NUMAノード)
OS:      Ubuntu 22.04.5 LTS / kernel 5.15.0-181-generic
ROCm:    6.2.2-116 (/opt/rocm-6.2.2)
GPU共通: gfx900 / 64CU / VRAM 16368M / MEM ECC active
```

## スロット↔ルートポート↔GUID 対応

ルートポートのデバイス番号は物理固定（`dmidecode -t slot` の Bus Address と `lspci -tv` の照合で確定）。

| 物理スロット(DMI) | ルートポート | 2枚 | 3枚 | 4枚 |
|---|---|---|---|---|
| CPU1 SLOT2 | `00:02.0` | 29525 | 29525 | 29525 |
| CPU1 SLOT4 | `00:03.0` | 33301 | 33301 | 33301 |
| CPU2 SLOT6 | `80:03.0` | — | 54068 | 8820 |
| CPU2 SLOT8 | `80:02.0` | — | — | 54068 |

注: 4枚時に SLOT6/SLOT8 のカード配置が3枚時から入れ替わっている（54068 が SLOT6→SLOT8、新規 8820 が SLOT6）。
ユーザ報告どおり「認識まで数回の抜き差し」を要した作業の反映。

## 各構成のリンク幅・エラー（核心）

### 2枚（uptime観測 04:51 / `lspci -c "Instinct MI25"` = 2）
```
04:00.0(SLOT2,29525): LnkSta: Speed 8GT/s (ok), Width x16 (ok)
07:00.0(SLOT4,33301): LnkSta: Speed 8GT/s (ok), Width x16 (ok)
RootPort 00:02.0/00:03.0: x16 (ok), SltSta PresDet+
AER TOTAL_ERR_COR: 04:00.0=0 / 07:00.0=0
VRAM: 各 17163091968 B (16GB) / ECC active
VRAM BAR Region0: 04=0x30000000000 / 07=0x30800000000 (3TB台, size=16G)
dmesg: amdgpu reset/hang/x0/x8 なし。BAR6 bogus alignment は expansion ROM(良性)
NVMe 00:01.0: LnkSta x4(native) / CESta CorrErr-（前回の長時間後 CorrErr+ は良性と再確認）
```

### 3枚（uptime観測 05:54 / count = 3、追加=GUID 54068 @ SLOT6）
```
04:00.0(SLOT2,29525): x16 (ok)
07:00.0(SLOT4,33301): x16 (ok)
84:00.0(SLOT6,54068): x16 (ok)
RootPort 00:02/00:03/80:03: x16 (ok), PresDet+
AER TOTAL_ERR_COR: 全3枚=0
VRAM: 各16GB / ECC active / junction 31〜38℃ / 3〜6W idle
VRAM BAR Region0: 04=0x380000000000 / 07=0x380800000000 / 84=0x384400000000 (56TB台, size=16G)
dmesg: reset/hang/x0/x8 なし
```

### 4枚（uptime観測 06:10 / count = 4、追加=GUID 8820 @ SLOT6, 54068 は SLOT8 へ）
```
04:00.0(SLOT2,29525): x16 (ok)
07:00.0(SLOT4,33301): x16 (ok)
84:00.0(SLOT8,54068): x16 (ok)
87:00.0(SLOT6,8820):  x16 (ok)
RootPort 00:02/00:03/80:02/80:03: 全て x16 (ok), PresDet+
AER TOTAL_ERR_COR: 全4枚=0
VRAM: 各16GB / ECC active / junction 30〜38℃ / 3〜6W idle
VRAM BAR Region0: 04=0x380000000000 / 07=0x380800000000 / 84=0x384400000000 / 87=0x384800000000 (size=16G)
dmesg: amdgpu reset/hang/timeout/fence/link down/x0/x8 すべてゼロ（grep 空）
```

## 前回(2026-06-14 dropout)との対比

| カード | 前回4枚時 | 今回4枚時 | スロット変化 |
|---|---|---|---|
| GUID 33301 | SLOT4 で 13ブート中12回 x0/PresDet-（リンク死） | x16 健全 | 同一 SLOT4 で改善 |
| GUID 8820 | SLOT8 で x8/欠落・不安定 | x16 健全 | SLOT8→SLOT6 へ移して改善 |
| GUID 54068 | 安定スロットの健全カード（当時スロットは前回レポート未特定） | x16 健全 | →SLOT8 |

## 追加観測（カード素性・トポロジ・ブート履歴）

### カード素性（2枚時に GPU0/1 で取得、全カード同一と推定）
```
VBIOS version : 113-D0513700-001 (全カード)
Card SKU      : D0513700
Subsystem ID  : Radeon PRO V320
Serial Number : N/A (get_serial_number, Not supported) → 個体識別は GUID のみ
GFX Version   : gfx900 / 64CU / xnack-
```

### メモリ詳細（showmeminfo all, 2枚時例）
```
VRAM     Total: 17163091968 B (16GB)
VIS_VRAM Total: 17163091968 B (16GB) = VRAM全域CPU可視（Large-BAR）
GTT      Total: 8317042688 B (≈7.7GB)
MEM ECC is active / SRAM ECC is not presented
```

### DevSta（全GPU共通・良性）
```
DevSta: CorrErr+ NonFatalErr- FatalErr- UnsupReq+   ← 表示は立つが…
CESta : RxErr- BadTLP- BadDLLP- Rollover- Timeout- AdvNonFatalErr+ (mask済)
AER aer_dev_correctable TOTAL_ERR_COR = 0           ← 実エラーは0（良性確定）
```

### GPU間トポロジ（showtopo, 2枚時のみ取得）
```
Weight GPU0-GPU1 = 40 / Hops = 2 / Link Type = PCIE（XGMIなし=P2PはPCIe経由）
Numa Node: GPU0(SLOT2)=0, GPU1(SLOT4)=0  ← 2枚はともにCPU1側でnode0
※4枚時はSLOT6/8がCPU2側のためnode1になる（前回dropoutレポートの対応表:SLOT2/4=node0,SLOT6/8=node1）。3/4枚のshowtopoは未取得
```

### idleクロック・電力（showclocks/showpower, 2枚時例）
```
sclk 852MHz / mclk 167MHz / socclk 600MHz / pcie 8.0GT/s x16
PwrCap 160.0W / Fan 9.41% / Power 3〜6W (idle)
```

### ブート履歴（数回の抜き差しを裏付け）
```
# journalctl --list-boots / last reboot
03:30〜04:32 に短時間ブート多数（数分で落として再起動を反復＝抜き差し作業の痕跡）
※参考: 6/23 08:17〜6/24 10:57 に約26.7時間連続稼働（ただし4枚復旧より前の構成の記録）
ドライバ: amdgpu out-of-tree (amdkcl, kernel taint) / cmdline = ro のみ
```

## 主な収集コマンド

```bash
ssh mi25 'lspci | grep -c "Instinct MI25"'
ssh mi25 'rocm-smi --showid; rocm-smi --showmeminfo vram --showtemp --showpower --showclocks'
ssh mi25 'sudo lspci -vv -s <bdf> | grep -Ei "LnkSta:|SltSta|Region 0:|DevSta"'
ssh mi25 'cat /sys/bus/pci/devices/0000:<bdf>/aer_dev_correctable'
ssh mi25 'sudo dmesg | grep -iE "amdgpu" | grep -iE "fail|reset|hang|x0|x8|VRAM|ECC"'
ssh mi25 'sudo dmidecode -t slot; sudo dmidecode -t bios -t system -t baseboard'
ssh mi25 'lspci -tv | grep -iE "MI25|Vega"'
```
