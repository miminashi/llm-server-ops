# aws-gpu01 の SAS HBA スロット特定と GPU Option ROM の無効化

## Context

aws-gpu01 の POST 時間（約 150 秒）を短縮するため GPU スロットの Option ROM を無効化したいが、
2026-08-17 に**全スロットを Disabled にしたらブートディスク（SAS HBA 経由）を見失い
EFI Shell に落ちた**。どの BIOS スロット項目が HBA なのかを特定する必要がある。

本セッション前半で**再起動なしの調査を完了**し、有力な仮説を得た。後半でそれを実機検証する。
DeepSeek-V4 は停止し、**復旧しない**（ユーザ指示）。

---

## 前半の調査で判明したこと（すべて実測）

### 1. HBA の物理的な位置

| 項目 | 実測値 |
|---|---|
| デバイス | `82:00.0` Broadcom/LSI MegaRAID SAS-3 3108 [Invader] |
| 接続先 | **CPU2 のルートポート `80:03.0`**（ACPI `\_SB.PCI1.QR3A` = Port 3A） |
| スロット幅 | ルートポートの `LnkCap` は **x16**、`LnkSta` は x8 |
| PCIe `SltCap` | `Slot #4`、ACPI `_SUN` = 4 |
| CPU2 側の他デバイス | オンボード X540 (`81:00.0`) のみ。**CPU2 の拡張カードは HBA 1 枚だけ** |

GPU 7 枚と Mellanox は**すべて CPU1 側**（`00:02.0`→PLX#1 に P100 3 枚、`00:03.0`→PLX#2 に
NIC + P100 4 枚）。`00:01.0` は未接続（`LnkSta Width x0`）。

### 2. gpu01 は Legacy BIOS ブート（事故原因の確証）

`/sys/firmware/efi` が無く `efibootmgr` も空 → **CSM/Legacy モード**。ブートには MegaRAID の
**Legacy Option ROM (INT 13h) が必須**で、事故の説明として完全に整合する。
**仮説 B（原因は OpROM 以外）は否定**。

### 3. 引き継ぎメモの表は正しかった（初期の指摘は撤回）

BIOS スクショ（`bios_pcie2.png` 等）の 11 項目は **gpu02 のもの**。gpu02 の SMBIOS Type 9 は
11 エントリで Designation もレーン幅もスクショと完全一致した。gpu01 は **12 エントリ**
（`CPU1 SLOT1-5` / `CPU2 SLOT6` / `CPU1 SLOT7-12`）で、レポートの「gpu01 は 12 スロット」とも一致。
**BIOS 項目 = SMBIOS Type 9** と見てよい。

### 4. 最有力仮説 — 「CPU2 SLOT6」が SAS HBA

| Designation | Bus Address | Current Usage | 実際に居るデバイス |
|---|---|---|---|
| CPU1 SLOT1 | 09:00.0 | Available | PLX#2 upstream |
| CPU1 SLOT2 | ff:00.0 | Available | なし |
| CPU1 SLOT3 / 4 / 5 | 08 / 07 / 05:00.0 | In Use | Tesla P100 |
| **CPU2 SLOT6** | **01:00.0** | **In Use** | **実際は空**（`00:01.0` は Width x0） |
| CPU1 SLOT7 | ff:00.0 | Available | なし |
| CPU1 SLOT8 | 0b:00.0 | In Use | Mellanox ConnectX-4 |
| CPU1 SLOT9 / 10 / 11 / 12 | 0d / 0f / 0e / 0c:00.0 | In Use | Tesla P100 |
| （一覧に無い） | **82:00.0** | — | **SAS HBA** |

`CPU2 SLOT6` は 12 項目で**唯一 "CPU2" とラベルされ**、**In Use なのに参照先が空**という矛盾を持つ。
CPU2 側の拡張カードは HBA だけなので、**BIOS は HBA を `CPU2 SLOT6` として持ち、
Bus Address のみ誤報告している**と考えるのが最も自然。
仮説 A（`SLOT2`/`SLOT7` が HBA）は、両者とも `ff:00.0` / Available のため弱い。

---

## 実施手順

再起動は合計 **3 回**（想定）。すべて `ALLOW_FAN_NOISE=1` が必要で、
`bmc-power.sh` が `boot-quiet.sh` を自動併走させるため回転は 2,900rpm 台に収まる見込み。

### Phase 0: 準備

1. `.claude/skills/gpu-server/scripts/lock.sh` で aws-gpu01 / aws-gpu02 のロックを取得
2. DeepSeek-V4 を停止（gpu01 の `llama-server`、gpu02 の `ggml-rpc-server`）。
   **`pkill -f` は使わない**（Bash ツールでは自分にマッチして exit 144 になる）。
   `pgrep` で PID を取り、PID 指定で kill する
3. 停止確認: `curl -sf http://10.8.2.1:8000/health` が失敗すること

### Phase 1: 変更前の POST 時間を測る（再起動 1 回目）

2026-08-17 レポートの「11. POST 時間の短縮効果 — 定量化できていない」を解消するため、
**reset 起点**のベースラインを取る。

```bash
source ~/.config/gpu-server/.env
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 reset
# reset 発行時刻を起点に、ping 応答 / SSH 応答までの秒数を 2 秒間隔でポーリング記録
```

同時にファン回転数も記録し、静音化が維持されていることを確認する。

### Phase 2: BIOS 変更（再起動 2 回目）

```bash
source ~/.config/gpu-server/.env
ipmitool -I lanplus -H "$BMC_AWS_GPU01_HOST" -U "$BMC_AWS_GPU01_USER" -P "$BMC_AWS_GPU01_PASS" \
  chassis bootdev bios
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 reset
```

約 2 分後に BIOS Setup が開く。`bmc-kvm.py`（`screenshot` / `sendkeys` / `type`）で操作し、
`Advanced → PCIe/PCI/PnP Configuration → PCI Devices Option Rom Setting` へ移動する。

**変更内容: `CPU2 SLOT6` だけを Legacy のまま残し、他の 11 項目を Disabled にする**

| 項目 | 変更後 | 理由 |
|---|---|---|
| CPU1 SLOT1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12 | **Disabled** | GPU 7 枚・NIC・PLX・空きスロット。ブートに不要 |
| **CPU2 SLOT6** | **Legacy（据え置き）** | SAS HBA の可能性が最も高い |
| `Onboard Video OPROM` / `VGA Priority` / `Above 4G Decoding` / `MMIO High Size` / `CSM Support` | 触らない | 前回同様 |

実務上の注意（2026-08-17 に踏んだ罠、レポート記載）:
- **1 項目ごとにスクショで現在位置を確認する**。一括でキーを送るとスクロールでずれて
  意図しない項目（実績: `VGA Priority`）のポップアップが開く
- スロット OPROM の選択肢は `Disabled / Legacy / EFI` で、Legacy から **ArrowUp 1 回**
- 変更後は `F4` → `Enter` で保存して再起動

### Phase 3: 起動確認と分岐

- **起動した場合** → **`CPU2 SLOT6` = SAS HBA と確定**。GPU/NIC の OpROM も全部止まり、
  POST 短縮の効果は最大。Phase 4 へ
- **EFI Shell に落ちた場合** → 仮説 E は棄却。以下で復旧してから案 2 を試す
  ```bash
  ipmitool ... chassis bootdev bios
  ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 reset
  # BIOS で全 12 項目を Legacy に戻して F4
  ```
  **案 2（保守的）**: GPU が載る `CPU1 SLOT3,4,5,9,10,11,12` の 7 項目のみ Disabled にし、
  `SLOT1`(PLX) / `SLOT2` / `CPU2 SLOT6` / `SLOT7` / `SLOT8`(NIC) は Legacy 維持。
  これなら HBA を切る危険は最小で、POST 短縮の目的だけは達成できる。
  起動したら `SLOT2` と `SLOT7` を追加 Disabled して候補をさらに絞る

### Phase 4: 変更後の POST 時間を測る（再起動 3 回目）

BIOS 保存経由の起動は BIOS 終了処理を含み比較にならないため、改めて reset 起点で測定する。
手順は Phase 1 と同一。**Phase 1 との差が Option ROM 無効化の効果**になる。

あわせて起動後の健全性を確認する:

```bash
ssh aws-gpu01 "nvidia-smi -L | wc -l"                    # 7 枚
ssh aws-gpu01 "lspci -s 82:00.0"                         # HBA 認識
ssh aws-gpu01 "systemctl is-active smc-fanctl"           # active
ssh aws-gpu01 "ip -br link show | grep -i 192.168.100 -A0"  # 100GbE（netplan 永続化の再確認）
```

### Phase 5: 記録

- **レポート作成**（`REPORT.md` の規約に従う）
  - タイトル（50 字以内）: `aws-gpu01 SAS HBA のスロット特定と OPROM 無効化`
  - **概要**必須。核心発見（HBA = どのスロットか / POST 短縮の実測値）を冒頭に
  - 添付 `report/attachment/<timestamp>_<slug>/` に生出力を置く（通常 git 管理、LFS は使わない）:
    `gpu01_dmidecode_t9.txt` / `gpu01_lspci_vv.txt` / `gpu02_dmidecode_t9.txt` /
    POST 時間の CSV / BIOS 画面のスクショ
  - `report/INDEX.md` に追記
- **`NEXT_SESSION.md` の更新**: 最優先タスクを完了扱いにし、結果と残課題を反映
- **`CLAUDE.md` の更新**: 「aws-gpu01 は BIOS のスロット OPROM を無効化するとブートディスクを
  見失い起動不能になる」の記述を、**特定できたスロット名を含む正確な記述**に差し替える
- **`.claude/skills/gpu-server/aws-gpu.md`** の「BIOS 設定」節も同様に更新
- **2026-08-17 レポート**には訂正を**追記**する（既存記述は書き換えない）:
  Legacy ブートである事実、`CPU2 SLOT6` の SMBIOS 矛盾、新レポートへのリンク

### Phase 6: 後片付け

- ロックを解放（`unlock.sh`）。**DeepSeek-V4 は復旧しない**
- ファン回転数が 2,900rpm 台に戻っていることを確認

---

## リスクと復旧

- **起動不能になっても復旧手順は確立済み**（2026-08-17 に実績）:
  `ipmitool chassis bootdev bios` → reset → 全スロットを Legacy に戻して F4
- 最悪でも BIOS 設定を元に戻せば現状復帰する。ディスク・データには触れない
- ファンは `boot-quiet.sh` の自動併走で 2,900rpm 台に収まる見込み（2026-08-18 実測）。
  もし爆音になった場合は起動完了を待って `smc-fanctl` の復帰を確認する

## 検証方法

- **仮説の検証**: Phase 3 で起動すれば `CPU2 SLOT6` = HBA。起動しなければ棄却し案 2 へ
- **目的（POST 短縮）の検証**: Phase 1 と Phase 4 の reset 起点の秒数を比較。
  参考値は gpu01 150 秒 / gpu02 85 秒（2026-08-18 コールドブート実測、条件が違うので参考）
- **副作用が無いことの確認**: GPU 7 枚・HBA・100GbE・`smc-fanctl` がすべて復帰していること
