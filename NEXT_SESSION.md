# 次セッションへの引き継ぎ

**更新**: 2026-08-18 JST (aws-gpu01 の SAS HBA スロットを特定・完了 → 最優先タスクなし)
**前回更新**: 2026-08-18 JST (aws-gpu01/02 ファン静音化 完了 → gpu01 の HBA スロット特定タスクを追加)

---

## 完了: aws-gpu01 の SAS HBA スロット特定（2026-08-18）

**結論: SAS HBA は BIOS の `CPU2 Slot6 PCI-E x16 OPROM`。ここを Disabled にすると起動不能になる。**

詳細は [HBA スロット特定レポート](report/2026-08-18_185344_aws_gpu01_sas_hba_slot_id.md)。要点のみ:

- **gpu01 は Legacy BIOS (CSM) ブート**（`/sys/firmware/efi` 無し・`efibootmgr` 空）で、
  MegaRAID (`82:00.0`) の **Legacy OpROM が無いとブートできない**。
  **gpu02 は UEFI ブート + オンボード SATA** なので同じ変更で無事だった＝ 2026-08-17 の事故の完全な説明
- **BIOS 項目 = SMBIOS `Designation`** で 1:1 対応（gpu01 は 12 項目、gpu02 は 11 項目）。
  前回レポートに貼られた BIOS スクショは **gpu02 のもの**だった
- `CPU2 Slot6` は SMBIOS で **In Use なのに Bus Address `01:00.0`（実際は空）** という矛盾を
  持っており、これが HBA の誤報告だった
- **検証**: `CPU2 Slot6` だけ Legacy に残し他 11 項目を Disabled → **正常起動**、
  POST 画面に `AVAGO MegaRAID SAS-MFI BIOS` の実行を目視確認

### ただし POST 短縮という目的は達成できなかった

| 条件 | reset → SSH 応答 |
|---|---|
| 変更前（全 12 スロット Legacy） | 146 秒 |
| 変更後（11 スロット Disabled） | **144 秒（−2 秒）** |

**GPU の VGA OpROM は POST 時間の主因ではない。**支配的なのは残さざるを得ない MegaRAID の
`F/W Initializing Devices` と 160GB のメモリトレーニングで、**この経路での改善は行き止まり**。

### 現在の BIOS 設定（ユーザ判断で変更後のまま維持）

- `CPU2 Slot6` = **Legacy**、他の 11 項目 = **Disabled**
- 実害は無く、GPU 7 枚・SAS HBA・100GbE・`smc-fanctl` はすべて正常に復帰済み
- 元に戻す場合は `ipmitool chassis bootdev bios` → reset → 全項目を Legacy → F4

---

## aws-gpu01 / aws-gpu02 の現状（2026-08-18 時点）

- **ファン静音化 完了**: 両機に `smc-fanctl` を systemd 常設。**アイドル 6,500 → 2,900rpm**、
  実負荷でも 16–28%（2,900–4,200rpm）。**起動 (POST) 中も 2,900rpm 台**
  （`bmc-power.sh` が `boot-quiet.sh` を自動併走させる）
- **爆音ガードは維持**（抑制が効かない状況では従来どおり全開になるため）。
  再起動には引き続き `ALLOW_FAN_NOISE=1` とユーザの明示指示が必要
- **DeepSeek-V4-Flash abliterated Q4_K は停止中**（2026-08-18 の BIOS 作業で停止し、
  ユーザ指示により復旧していない）。再開する場合は `rpc-up.sh` → `rpc-llama-up.sh`
  （`EXTRA_LLAMA_OPTS` で `--jinja --temp 1.0 --top-p 1.0 --min-p 0.01`）。cold ロード 13〜15 分
- **ロックは解放済み**。**ロックはサーバの `/tmp` にあるので再起動すると消える**
- **100GbE は netplan で永続化済み**（`/etc/netplan/60-rpc-100gbe.yaml`、再起動 2 回で検証済み）
- **BIOS 変更済み**: 両機とも `Wait For "F1" If Error` = Disabled、`Onboard LAN 1 OPROM` = Disabled。
  スロット OPROM は **gpu02 は全 11 項目 Disabled**、**gpu01 は `CPU2 Slot6` のみ Legacy で他 11 項目 Disabled**
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

### 2026-08-18: aws-gpu01 の SAS HBA スロット特定

- 詳細: [HBA スロット特定レポート](report/2026-08-18_185344_aws_gpu01_sas_hba_slot_id.md)
- SAS HBA = BIOS の `CPU2 Slot6`。他 11 項目は Disabled にしても起動する
- POST 短縮効果は −2 秒で、**この経路での改善は打ち切り**

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

4. **最優先タスクは無い**。「その他の未完タスク」から優先度順に着手する。
   DeepSeek-V4 が必要な作業なら、先に RPC 分散を起動する（cold ロード 13〜15 分）
