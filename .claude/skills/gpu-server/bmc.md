# BMC緊急操作（IPMI 電源制御 / KVM スクリーンショット）

OS がハング・クラッシュして SSH が効かなくなったときに、**OS 非依存（out-of-band）**で
GPU サーバを操作・観測するための手順。BMC（Baseboard Management Controller）に直接アクセスする。

## いつ使うか

- OS がフリーズ／カーネルパニックして `ssh` も `ping` も応答しない
- ファイルシステム破損で read-only 再マウントされ復旧に再起動が要る（例: 2026-06-13 mi25 の ext4 ジャーナル破損）。
  **SSH が突然 `Connection reset by peer` になるのは、fail2ban ではなくこの FS 障害のことがある**
  （2026-06-13 は当初 fail2ban と誤認した）。KVM スクショでコンソールの FS エラーを確認する
- BIOS 設定（MMIO High Size など）を確認・変更したい
- POST で停止していないか画面で確認したい

## ハング調査では最初に SEL を読む（必須）

**OS がハングしたら、KVM スクショと同じくらい重要なのが BMC の SEL（System Event Log）である。**
`journalctl` に何も残らない停止でも、SEL には残っていることがある。**電源が OFF でも読める。**

> 2026-09-05 の aws-gpu02 は、5 回のハングを「MCE / Hardware Error / Xid / panic の記録が
> 一切ない痕跡なしのハードロックアップ」と結論していたが、これは `journalctl` しか見て
> いなかったためだった。SEL には `Memory | Uncorrectable ECC` が 11 件あり、ハング時刻と
> 秒単位で一致していた。詳細は
> [2026-09-05 のレポート](../../../report/2026-09-05_221831_aws_gpu02_uncorrectable_ecc.md)。

```bash
source ~/.config/gpu-server/.env
S=AWS_GPU02   # MI25 / AWS_GPU01 / AWS_GPU02 など（bmc-power.sh と同じ命名）
IPMI="ipmitool -I lanplus -H $(eval echo \$BMC_${S}_HOST) -U $(eval echo \$BMC_${S}_USER) -P $(eval echo \$BMC_${S}_PASS)"

$IPMI sel info                       # 件数と最終追記時刻
$IPMI sel time get                   # BMC 時計のずれを必ず確認（時刻突き合わせの前提）
$IPMI sel elist                      # 全件
$IPMI sel elist | grep -iE 'memory|ecc|processor|power supply|temperature|critical'
$IPMI sel get 0x82                   # 個別エントリの raw（Event Data / Sensor Type）
```

読み方の注意:

- **`Unknown #0xff` の連番は POST を示す OEM レコード**。これに挟まれていないイベントは
  OS 稼働中に起きたものと判断できる
- **DIMM やスロットの位置デコードは信用しすぎない**。aws-gpu02 では `DIMMS-(CPU4)` のような
  存在しない位置が混ざった。位置は **BIOS Setup の `Event Logs` → `View Smbios Event Log`**
  と **POST 画面**のほうを正とする（ただし**BIOS 側の表示は UTC**、SEL は JST）
- Redfish が使える機体（aws-gpu01/02）では `/redfish/v1/Systems/1/Memory/N` で
  BMC 側のメモリ一覧も取れる。**BIOS の見え方と食い違うことがあり、その食い違いが手がかりになる**

### ハング判定: 経路障害と区別する

`/health`・`ping`・`ssh` の三点が全部通らなくても、**ホストが死んだのか、途中のネットワーク経路が
切れたのかは区別できない**。電源リセットの前に次の 2 つで弁別する:

1. **BMC に届くか**（`bmc-power.sh <server> status`）
2. **対象と同じ拠点にある別の参照先に届くか**。mi25 なら **`10.1.5.1` / `10.1.1.1`**。
   **制御ホスト（WS）と同じ拠点の参照先（例 `10.1.6.4`）は使わない**（対象拠点側の経路障害を検出できない）

「BMC に届き、かつ対象拠点の参照先にも届く」ときだけ**ホストのみが死んだ＝真のハング**と判定する。
2026-06-24 の負荷再現キャンペーンで、BMC ごと不達だった経路喪失を真ハングと誤判定した教訓による。

また mi25 のハングは **負荷で決定論的に再現する事象ではなかった**（ROCm 30 + Vulkan 23 試行・約 11.5 時間で
ハング 0）。確率的なハードウェア事象として扱い、**負荷をかけて再現させようとしない**。
詳細は [負荷再現キャンペーンのレポート](../../../report/2026-06-24_161909_mi25_hang_repro_load_campaign.md)。

## トランスポートの使い分け（重要）

| 機種 | BMC | 電源制御 | スクリーンショット | スクリプト |
|------|-----|----------|--------------------|-----------|
| **mi25**（Supermicro X10DRG-Q） | ATEN/AMI, FW 3.94 | **IPMI**（`ipmitool`） | HTML5 KVM canvas | `bmc-power.sh` / `bmc-screenshot.sh` |
| **t120h-p100**（HPE） | iLO5 | **Redfish**（`power.sh`） | （未整備） | `power.sh` |
| **t120h-m10**（NEC Express5800/T120h） | iLO5, FW 2.90（`10.1.4.17`） | **Redfish**（`power.sh`）。IPMI over LAN は不可 | （未整備） | `power.sh` |
| **aws-gpu01**（Supermicro X10DRG-OT+） | ASPEED, FW 3.86 | **IPMI**（`ipmitool`）※爆音ガード | HTML5 KVM canvas | `bmc-power.sh` / `bmc-screenshot.sh` |
| **aws-gpu02**（Supermicro X10DRG-OT+） | ASPEED, FW 3.86 | **IPMI**（`ipmitool`）※爆音ガード | HTML5 KVM canvas | `bmc-power.sh` / `bmc-screenshot.sh` |

> **aws-gpu01/02 は Redfish も応答する**（mi25 と違い `/redfish/v1/Systems/1` が正常に返る）が、
> 運用は既存 Supermicro 機と揃えて **IPMI を正**とする。`power-ctl.sh` の `server_type()` も
> `supermicro` を返す。

> **⚠️ aws-gpu01/02 の爆音ガード**: 両機は起動時にファンが爆音になるため、**ユーザの明確な
> 指示なしにリブート・電源投入・電源断を行わない**。`bmc-power.sh` の
> `on`/`off`/`soft`/`reset`/`cycle` と `power-ctl.sh` の `on`/`off` は、`ALLOW_FAN_NOISE=1`
> が無ければ **exit 20** で拒否する（`status` とスクショは常に可）。
> ガード対象は両スクリプトの `FAN_LOUD_SERVERS` で定義。詳細は [aws-gpu.md](./aws-gpu.md)。

> **なぜ mi25 で Redfish を使わないか**: mi25 の BMC は Redfish API が
> **DCMS（SUM DCMS OOB）ライセンス未活性**で `OemLicenseNotPassed` を返し、電源もスクショも
> 取得できない。一方 IPMI（lanplus）はライセンス不要で完全に動作する。
> このため Supermicro 機の out-of-band 操作は IPMI ベースの `bmc-power.sh` を使う。
> （`power.sh` は HPE iLO5 の Redfish 専用なので mi25 では使えない。）

> **上位スクリプト向けの統一IF**: `llama-up.sh` / `llama-down.sh` などはサーバ種別を意識しないよう
> `power-ctl.sh <server> <status|on|off>` を経由する。これが HPE→`power.sh`、Supermicro→`bmc-power.sh`
> へ振り分け、`off` は Supermicro では **`bmc-power.sh soft`（ACPI グレースフル）** にマップする
> （ハード即時断 `bmc-power.sh off` は使わない）。

## 初回セットアップ

```bash
cd /home/ubuntu/projects/llm-server-ops

# 1. KVM スクショ用 venv（Playwright + Chromium）を構築。
#    Chromium は ~/.cache/ms-playwright/ の共有キャッシュを使う。
.claude/skills/gpu-server/scripts/setup-bmc-venv.sh

# 2. BMC 認証情報を登録（ipmitool で疎通テスト後、~/.config/gpu-server/.env に保存）
.claude/skills/gpu-server/scripts/bmc-setup.sh mi25 10.1.4.7 claude Claude123
.claude/skills/gpu-server/scripts/bmc-setup.sh aws-gpu01 10.11.12.1 claude Claude123
.claude/skills/gpu-server/scripts/bmc-setup.sh aws-gpu02 10.11.12.2 claude Claude123
```

`bmc-setup.sh` にはサーバ別の既定 BMC IP が登録済みなので、IP を省略して
`bmc-setup.sh aws-gpu01 "" claude Claude123` のようには書けない（引数は位置指定）。
IP を明示するのが確実。

認証情報は `~/.config/gpu-server/.env` に `BMC_<SERVER>_HOST/USER/PASS`（chmod 600）として保存され、
`.gitignore` 済みでコミットされない。

## 電源制御

```bash
# 電源状態（System Power: on/off）
.claude/skills/gpu-server/scripts/bmc-power.sh mi25 status

# ハードリセット（暖機なし即時リセット。OS ハングからの復旧本命）
.claude/skills/gpu-server/scripts/bmc-power.sh mi25 reset

# コールドブート（OFF → 15秒待機 → ON。待機秒は引数で変更可）
.claude/skills/gpu-server/scripts/bmc-power.sh mi25 cycle 20

# 個別操作
.claude/skills/gpu-server/scripts/bmc-power.sh mi25 on
.claude/skills/gpu-server/scripts/bmc-power.sh mi25 off    # ハード電源OFF（即時）
.claude/skills/gpu-server/scripts/bmc-power.sh mi25 soft   # ACPI ソフトシャットダウン
```

| アクション | ipmitool | 用途 |
|-----------|----------|------|
| `status` | `chassis status` | 電源状態確認 |
| `reset` | `chassis power reset` | 即時ハードリセット（復旧本命） |
| `cycle [wait]` | `power off` → wait → `on` | コールドブート |
| `on` / `off` | `power on` / `power off` | 電源 ON / ハード OFF |
| `soft` | `power soft` | ACPI ソフトシャットダウン |

> **ロックについて**: 実際に電源を落とす/リセットする操作は他セッションのジョブを壊すため、
> 事前に `lock.sh <server>` でロックを取得すること。`status`・スクショは読み取り的だが、
> 復旧作業全体をロック下で行うのが安全。

### mi25 (X10DRG-Q) で `soft` を優先する理由 (実測ノウハウ)

mi25 (Supermicro X10DRG-Q) では、OS から `sudo shutdown -h +1` を発行しても **OS halt 状態で
止まり、Power=on のまま固定される既知のクセ**がある (BMC `status` で確認可能)。物理スワップ等で
完全電源 OFF が必要な場面では、OS 経由ではなく直接以下を使うのが確実:

```bash
.claude/skills/gpu-server/scripts/bmc-power.sh mi25 soft
# ~20 秒以内に System Power: off に到達 (12 回連続スワップで実測、2026-06-29 物理交換作業)
```

- `soft` は IPMI 経由で ACPI shutdown を OS に依頼 → systemd が正常停止 → 電源 OFF まで進む
- 物理スワップを伴う作業 (シャットダウン → 装着変更 → 電源 ON のサイクルを何度も繰り返す) に最適
- ハード `off` は OS の状態次第で FS 整合性リスクがあるため、SSH 不通でない限り常に `soft` を選ぶ
- 詳細: [report/2026-06-29_191721_mi25_gpu_card_id_unique_id.md](../../../report/2026-06-29_191721_mi25_gpu_card_id_unique_id.md) の物理スワップ 12 サイクルで実証

## KVM スクリーンショット

```bash
.claude/skills/gpu-server/scripts/bmc-screenshot.sh mi25 /tmp/mi25.png
```

内部では Playwright で BMC の HTML5 KVM ビューア
（`url_redirect.cgi?url_name=man_ikvm_html5_bootstrap`）を開き、`#noVNC_canvas`（2D canvas）を
`toDataURL()` でキャプチャする。X10DRG-Q は classic noVNC（2D）なので黒画にならない。

直接 Python を呼ぶ場合（キー送信もできる）:

```bash
.venv/bin/python の代わりに skills/gpu-server/.venv/bin/python を使う
.claude/skills/gpu-server/.venv/bin/python \
  .claude/skills/gpu-server/scripts/bmc-kvm.py \
  --bmc-ip 10.1.4.7 --bmc-user claude --bmc-pass Claude123 \
  screenshot /tmp/mi25.png

# BIOS 進入（Delete 連打）など
.claude/skills/gpu-server/.venv/bin/python \
  .claude/skills/gpu-server/scripts/bmc-kvm.py \
  --bmc-ip 10.1.4.7 --bmc-user claude --bmc-pass Claude123 \
  sendkeys Delete Delete Delete --screenshot /tmp/bios.png
```

## トラブルシュート

- **canvas が小さい/黒い（KVM 未接続）**: ビューアが自動接続しない場合がある。
  `bmc-kvm.py` は canvas サイズが安定するまで待つが、ダメなら `#noVNC_connect_button` の
  クリック処理の追加を検討（実装は `setup_kvm_page`）。
- **`toDataURL()` が黒画**: WebGL canvas の機種では `locator("#noVNC_canvas").screenshot()` に切替。
  X10DRG-Q は 2D なので通常は不要。
- **ログイン失敗（SID 取得不可）**: BMC の同時セッション数上限に達している可能性。少し待つ、
  または BMC Web UI から不要セッションを切断。
- **`exit 10`（認証情報未設定）**: `bmc-setup.sh` を実行。
- **`exit 3`（IPMI 接続失敗）**: BMC IP/到達性、ユーザ/パスワードを確認。
- **原因不明の連続リブート → まず `VBAT`（CMOS 電池）を見る**:
  `$IPMI sensor | grep VBAT`（`$IPMI` は上記「ハング調査では最初に SEL を読む」節の定義）。
  mi25 は 2026-07-11〜12 に CMOS 電池切れで 1 日 30 回超のリブートループになった（VBAT 1.624V、
  閾値は Lower Critical 2.430V / Non-recoverable 2.326V）。**Lower Critical の初警告から約 10 ヶ月の猶予があったが
  監視していなかった**ので、ついでの際に確認するとよい。電池切れの副作用として **BMC 時刻が +9h ずれ**
  （SEL の時刻は補正して読む）、**BIOS 設定も初期値に戻る**（mi25 では MMIO High Size が 256GB に戻り 4 枚認識できなくなる）。
  詳細は [CMOS 電池切れ](../../../report/2026-07-12_045926_mi25_cmos_battery_reboot_loop.md) /
  [BIOS 復旧](../../../report/2026-07-17_135433_mi25_bios_restore_after_cmos.md)。
