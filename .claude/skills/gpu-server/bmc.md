# BMC緊急操作（IPMI 電源制御 / KVM スクリーンショット）

OS がハング・クラッシュして SSH が効かなくなったときに、**OS 非依存（out-of-band）**で
GPU サーバを操作・観測するための手順。BMC（Baseboard Management Controller）に直接アクセスする。

## いつ使うか

- OS がフリーズ／カーネルパニックして `ssh` も `ping` も応答しない
- ファイルシステム破損で read-only 再マウントされ復旧に再起動が要る（例: 2026-06-13 mi25 の ext4 ジャーナル破損）
- BIOS 設定（MMIO High Size など）を確認・変更したい
- POST で停止していないか画面で確認したい

## トランスポートの使い分け（重要）

| 機種 | BMC | 電源制御 | スクリーンショット | スクリプト |
|------|-----|----------|--------------------|-----------|
| **mi25**（Supermicro X10DRG-Q） | ATEN/AMI, FW 3.94 | **IPMI**（`ipmitool`） | HTML5 KVM canvas | `bmc-power.sh` / `bmc-screenshot.sh` |
| **t120h-p100**（HPE） | iLO5 | **Redfish**（`power.sh`） | （未整備） | `power.sh` |

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
```

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
