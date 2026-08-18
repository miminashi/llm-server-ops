# 次セッションへの引き継ぎ

**更新**: 2026-08-18 JST (aws-gpu01/02 ファン静音化 完了 → gpu01 の HBA スロット特定タスクを追加)
**前回更新**: 2026-07-25 JST (llama-finetune 検証 → PR #25428 動作確認タスクを追加、以降 `~/projects/llama.cpp-fine-tuning` へ移管)

---

## 最優先: aws-gpu01 の SAS HBA スロット特定と Option ROM 無効化

### 目的

aws-gpu01 の **POST 時間を短縮**して、起動時にファンが唸る区間をさらに縮める。
そのために **GPU が載るスロットの Option ROM を無効化したいが、ブートディスクを繋いでいる
SAS HBA の OpROM まで切ると起動しなくなる**ため、どのスロットが HBA なのかを見極める必要がある。

### 背景（2026-08-17 に起きたこと）

BIOS の `PCI Devices Option Rom Setting` にある **12 スロット全部を Disabled にしたところ、
aws-gpu01 が EFI Shell に落ちて起動しなくなった**（`map: Cannot find required map name`）。
`ipmitool chassis bootdev bios` で BIOS に入り、全スロットを Legacy に戻して復旧済み。
同じ変更をした aws-gpu02 は**オンボード SATA ブートなので問題なく起動**した。

詳細: [2026-08-17 ファン静音化レポート](report/2026-08-17_234403_aws_gpu_fan_noise_reduction.md)
の「10. aws-gpu01 が起動しなくなった事故と復旧」。

### 判明済みの資料（2026-08-18 に採取、再取得不要）

**ブートディスクの経路**: `sda` → `0000:80:03.0` → **`0000:82:00.0` = Broadcom/LSI MegaRAID SAS-3 3108 [Invader]**

**SMBIOS のスロット一覧**（`sudo dmidecode -t 9`）と `lspci` の突合:

| BIOS のスロット項目 | Bus Address | 実デバイス |
|---|---|---|
| CPU1 SLOT1 | 09:00.0 | PLX PCIe スイッチ |
| **CPU1 SLOT2** | **ff:00.0（SMBIOS 上は "Available"）** | **不明** |
| CPU1 SLOT3 | 08:00.0 | Tesla P100 |
| CPU1 SLOT4 | 07:00.0 | Tesla P100 |
| CPU1 SLOT5 | 05:00.0 | Tesla P100 |
| CPU2 SLOT6 | 01:00.0 | `lspci` は空を返した（ブリッジのみ？） |
| **CPU1 SLOT7** | **ff:00.0（SMBIOS 上は "Available"）** | **不明** |
| CPU1 SLOT8 | 0b:00.0 | Mellanox ConnectX-4（100GbE） |
| CPU1 SLOT9 | 0d:00.0 | Tesla P100 |
| CPU1 SLOT10 | 0f:00.0 | Tesla P100 |
| CPU1 SLOT11 | 0e:00.0 | Tesla P100 |
| CPU1 SLOT12 | 0c:00.0 | Tesla P100 |
| — | **82:00.0** | **SAS HBA（一覧に現れない）** |

**ACPI のスロット番号**（`/sys/bus/pci/slots/*/address`）— **SMBIOS の SLOT 名とは一致しない**ので注意:

```
0    0000:81:00      0-1  0000:10:00     1    0000:01:00
2    0000:02:00      3    0000:09:00     4    0000:82:00   ← SAS HBA
```

### 未解明の点（ここが次セッションの本題）

**SAS HBA (82:00.0) は SMBIOS のスロット一覧に現れないのに、BIOS の 12 スロットを全部
Disabled にすると起動しなくなった。** 仮説は 2 つ:

- **仮説 A**: `CPU1 SLOT2` か `CPU1 SLOT7`（SMBIOS では Bus Address `ff:00.0` ＝「空き」と
  報告されている 2 つ）が、実は内部 AOC スロットで SAS HBA が載っている
- **仮説 B**: 起動不能の原因は OpROM ではなく別のもの（Boot Order の再構成など）。
  この場合 GPU スロットだけ切っても再発しうる

### 実施手順（低リスク・低コストな順。所要 1〜2 時間、再起動 2〜3 回）

再起動には `ALLOW_FAN_NOISE=1` が要る（**ユーザに都度確認**）。
`bmc-power.sh` が `boot-quiet.sh` を自動併走させるので、**起動中の回転は 2,900rpm 台に収まる**
（2026-08-18 実測。以前のような爆音にはならない）。

**Step 1: POST 画面から HBA のスロット番号を読む（設定変更なし・再起動 1 回）**

MegaRAID の OpROM は POST 中に `LSI MegaRAID SAS-MFI BIOS ... ` のバナーを出し、
製品によっては **スロット番号を併記**する。これが読めれば一発で確定する。

```bash
# KVM のスクショを連続取得しながら再起動（POST の 30〜120 秒あたりを狙う）
SCR=/tmp/kvm-post && mkdir -p $SCR
source ~/.config/gpu-server/.env
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 reset
for i in $(seq 1 20); do
  .claude/skills/gpu-server/.venv/bin/python .claude/skills/gpu-server/scripts/bmc-kvm.py \
    --bmc-ip "$BMC_AWS_GPU01_HOST" --bmc-user "$BMC_AWS_GPU01_USER" --bmc-pass "$BMC_AWS_GPU01_PASS" \
    screenshot "$SCR/post_$(printf %02d $i).png"
done
```

- **`Advanced → Boot Feature → AddOn ROM Display Mode` は `Force BIOS`**（両機とも未変更。
  2026-08-17 の [BIOS スクショ](report/attachment/2026-08-17_234403_aws_gpu_fan_noise_reduction/bios_bootfeature.png)
  で確認済み）なので、OpROM の画面は表示される設定になっている
- **注意: これは「連写」にならない**。`bmc-kvm.py` は 1 回の呼び出しごとに KVM へ接続し直すため
  1 枚あたり 15〜20 秒かかり、POST 全体（gpu01 は約 150 秒）でも 5〜7 枚しか撮れない。
  **バナーを捉えられるかは運任せ**なので、外したら深追いせず Step 2 へ進むこと

**Step 2: GPU の 7 スロットだけ Disabled にして起動確認（本命・再起動 1 回）**

HBA を特定できなくても**目的（POST 短縮）はこれで達成できる**。

- 対象: **CPU1 SLOT3, 4, 5, 9, 10, 11, 12**（＝ Tesla P100 が載る 7 枚）を Legacy → Disabled
- **触らない**: SLOT1（PLX）、SLOT2、CPU2 SLOT6、SLOT7、SLOT8（NIC）、`Onboard Video OPROM`、
  `VGA Priority`、`Above 4G Decoding`、`MMIO High Size`
- 起動すれば仮説 A が裏付けられ（HBA は残した 5 つのどれか）、POST 時間も測れる
- **起動しなければ仮説 B**（原因は OpROM ではない）＝ すぐ全スロットを Legacy に戻す

**Step 3: 範囲を狭めて HBA を特定（任意・再起動 1〜2 回）**

Step 2 が成功したら、残した 5 つのうち **SLOT2 と SLOT7 を追加で Disabled** にして起動確認。
起動しなくなればそのどちらかが HBA と確定（さらに 1 つずつに分ければ一意に決まる）。

### BIOS 操作の実務メモ（2026-08-17 に踏んだ罠）

- **BIOS に入るのは `ipmitool chassis bootdev bios` が確実**。Delete 連打は POST のタイミング次第で
  外れる（実際に何度も失敗した）。EFI Shell からの `exit` 入力も KVM 経由では効かない
- **カーソル位置は画面スクロールでずれる**。一括でキーを送ると意図しない項目
  （実際に `VGA Priority`）のポップアップが開く。**1 段階ごとにスクショで現在位置を確認する**
- 選択肢の並びは項目ごとに違う（スロット OPROM は `Disabled/Legacy/EFI`、
  Onboard LAN 1 OPROM は `PXE/iSCSI/FCoE/Disabled`）
- 変更後は `F4` → `Enter` で保存して再起動

### 復旧手段（起動しなくなった場合）

```bash
source ~/.config/gpu-server/.env
ipmitool -I lanplus -H "$BMC_AWS_GPU01_HOST" -U "$BMC_AWS_GPU01_USER" -P "$BMC_AWS_GPU01_PASS" \
  chassis bootdev bios
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 reset
# 約 2 分後に BIOS Setup が開くので、スロット OPROM を Legacy に戻して F4
```

### 事前にユーザへ確認すること

- **再起動の可否**（毎回）。DeepSeek-V4 が稼働していれば停止する必要がある
- 稼働中モデルを**復旧するか**（cold ロードに 13〜15 分）

### 参考値（比較用、2026-08-18 のコールドブート実測）

| 機体 | OS 起動まで | smc-fanctl 稼働まで | スロット OPROM |
|---|---|---|---|
| aws-gpu01 | 150 秒 | 160 秒 | Legacy（GPU 7 枚の VGA OpROM を実行） |
| aws-gpu02 | 85 秒 | 108 秒 | Disabled |

差の 65 秒には GPU 枚数（7 vs 6）と RAM 量（160GB vs 96GB）の違いも混ざるので、
**OPROM 単独の寄与は Step 2 の前後比較で初めて分かる**。

---

## aws-gpu01 / aws-gpu02 の現状（2026-08-18 時点）

- **ファン静音化 完了**: 両機に `smc-fanctl` を systemd 常設。**アイドル 6,500 → 2,900rpm**、
  実負荷でも 16–28%（2,900–4,200rpm）。**起動 (POST) 中も 2,900rpm 台**
  （`bmc-power.sh` が `boot-quiet.sh` を自動併走させる）
- **爆音ガードは維持**（抑制が効かない状況では従来どおり全開になるため）。
  再起動には引き続き `ALLOW_FAN_NOISE=1` とユーザの明示指示が必要
- **DeepSeek-V4-Flash abliterated Q4_K が RPC 分散で稼働中**
  （aws-gpu01 が親 / aws-gpu02 が `ggml-rpc-server`、ctx=131072、`http://10.8.2.1:8000/v1`）
- **ロック取得済み**: `aws-deepseek-v4-rpc-20260818_023922`（稼働中モデルの保護用）。
  **ロックはサーバの `/tmp` にあるので再起動すると消える** → 再起動後は取り直すこと
- **100GbE は netplan で永続化済み**（`/etc/netplan/60-rpc-100gbe.yaml`、再起動 2 回で検証済み）
- **BIOS 変更済み**: 両機とも `Wait For "F1" If Error` = Disabled、`Onboard LAN 1 OPROM` = Disabled。
  スロット OPROM は **gpu02 のみ Disabled**（gpu01 は上記の事故により Legacy のまま）
- **既知の個体差**: gpu02 は POST に `Failing DIMM: P2-DIMME1` を出すが**該当スロットは空**で
  実害なし。ただし **gpu02 は CPU2 側にメモリが 1 枚も無い**（`numactl` の node1 = 0 MB）ので、
  NUMA 的に不利。増設は未検討

### 緊急時: ファン制御を BMC に戻す

```bash
ssh aws-gpu01 "sudo systemctl stop smc-fanctl; sudo ipmitool -I open raw 0x30 0x45 0x01 0x02"
```

---

## その他の未完タスク（優先度順）

### 中優先

1. **aws-gpu02 の BIOS 設定値の再確認**: 2026-08-17 に変更したが、保存後に BIOS 画面へ戻って
   値が保持されているかを見ていない（正常起動は確認済み）。次に gpu02 の BIOS へ入る機会に確認
2. **mi25 の BMC 時刻同期**（BMC Web UI 経由）: BMC は 2015-01-02 開始のまま、
   `ipmitool sel time set` は "Specified time could not be parsed" で失敗する
   - 対処: BMC Web UI (https://10.1.4.7/) → Configuration → Date and Time →
     Timezone=Asia/Tokyo + NTP Enable (Server=ntp.nict.jp) → Save
3. **mi25 の Vulkan パフォーマンス改善**:
   - Vulkan 32k / 100k の -9% / -12% 誤差要因の bisect
     （`f3e182816` → `ded1561b4` の間で軽微退行 PR が挟まった可能性）
   - `git log --oneline f3e182816..ded1561b4 -- 'ggml/src/ggml-vulkan/**'` で候補列挙 → 代表点を
     checkout + 32k pp 実測で範囲を縮小

### 低優先

4. **aws-gpu 系の重い負荷での冷却再検証**: 今回の負荷は MoE の実運用推論（GPU 使用率 7–9%）。
   dense モデルや gpu-burn 相当で GPU 全数を長時間 100% にしたときの平衡温度は未確認
5. **`mc reset cold` 後に fan mode が保持されるかの確認**: BMC リセット自体が一時的に
   ファンを全開にする可能性があり、実機前のユーザに追加の爆音を負わせないため見送った。
   デーモンが 60 秒ごとに mode を確認するので、消えていても実害はない見込み
6. **mi25 Fable D-2 R2 追試**（追加 N ≥ 100 で累計 N ≥ 200、任意）
7. **mi25 Fable D-3 fault シグネチャ台帳の一次データ再監査**（サーバ時間ゼロ）
8. **mi25 Fable D-4 VBIOS / RAS カウンタ 4 枚比較**（サーバ数分）
9. **mi25 VBAT 監視の運用整備**: VBAT 2.794V は `ok` 域だが新品 3.0V より 6.87% 低い。
   `ipmitool sensor | grep VBAT` を cron 日次記録 → 2.5V 割れで discord-notify 通知

### 打ち切り（今後行わない）

- **ROCm long-ctx 退行の原因調査**: Vulkan 既定化に伴い着手しない。
  ROCm が必要なら `MI25_BACKEND=hip` で fallback するのみ
- **Git LFS の再導入**: 2026-08-16 に廃止済み（テキストログは通常 git のほうが圧倒的に小さい）。
  `.gitattributes` はパス一致しか書けず「この日以降のみ」を表現できないため再検討しない

---

## 完了済み（参考）

### 2026-08-17〜18: aws-gpu01/02 のファン静音化

- 詳細: [2026-08-17 ファン静音化レポート](report/2026-08-17_234403_aws_gpu_fan_noise_reduction.md)
- X10 の BMC は **fan mode = Full のときだけ手動 duty を保持する**。cooling zone は 0–3 の 4 つ
- **Full に切り替えるたびに BMC が全 zone を 100% にリセットする**ため、
  mode を繰り返し書いてはいけない（この見落としで起動中の爆音を自ら誘発していた）
- 新規: `fan-control/smc-fanctl.py` + `.service`、`scripts/install-fan-control.sh`、
  `scripts/boot-quiet.sh`。`bmc-power.sh` に boot-quiet の自動併走を追加

### 2026-07-20: mi25 のデフォルトバックエンドを Vulkan に変更（実施済み）

`start.sh` は `${MI25_BACKEND:-vulkan}` になっており、**prefix なしで Vulkan 起動**する。
ROCm を使う場合のみ `MI25_BACKEND=hip` を明示する。

### 2026-07-25: llama.cpp fine-tune 関連（別プロジェクトへ移管）

`~/projects/llama.cpp-fine-tuning` へ移管済み。本リポジトリでは扱わない。

---

## 初動手順（次セッション開始時）

1. **git 状態の確認**
   ```bash
   git status        # クリーンなはず
   git log --oneline -5
   # 直近は 2026-08-17〜18 のファン静音化関連コミット（未 push）
   ```

2. **aws-gpu の状態確認**（ロックは取得済みだが、再起動を挟んでいたら消えている）
   ```bash
   .claude/skills/gpu-server/scripts/lock-status.sh
   for s in aws-gpu01 aws-gpu02; do ssh $s "systemctl is-active smc-fanctl"; done
   curl -sf http://10.8.2.1:8000/health && echo    # DeepSeek-V4 が稼働中か
   ```

3. **ファンの状態確認**（静音化が効いているか）
   ```bash
   source ~/.config/gpu-server/.env
   ipmitool -I lanplus -H "$BMC_AWS_GPU01_HOST" -U "$BMC_AWS_GPU01_USER" -P "$BMC_AWS_GPU01_PASS" \
     sdr type fan          # 2,900rpm 前後なら正常
   ```

4. **上記「最優先」タスク（gpu01 の HBA スロット特定）に着手**。
   再起動が要るので、着手前にユーザへ可否とモデル復旧の要否を確認する
