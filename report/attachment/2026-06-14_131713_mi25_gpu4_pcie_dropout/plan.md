# mi25 4枚目 MI25 GPU 脱落の調査と復旧

## Context

`report/2026-06-14_041305_mi25_vulkan_backend_quality.md` の「環境情報」「既知の課題」で、
mi25(MI25/gfx900 ×4物理)の **4枚目がランタイムから脱落**しており、ROCm/Vulkan とも実コンピュートは3枚、
原因未特定(dmesg は当時 sudo 権限なく未取得)と記録されていた。本タスクはこの原因を特定し、
遠隔で可能な範囲で4枚目を復旧することが目的。

### 調査で判明した事実(2026-06-14 05:01 時点、読み取り専用で確認済み)

- 現在 mi25 は MI25 が **PCIe バス上に3枚しか存在しない**。`lspci` の Vega VGA は `04:00.0 / 07:00.0 / 84:00.0` の3枚のみ
  (+ ASPEED オンボード)。`rocm-smi` も3枚しか列挙しない。
- **この起動(boot 0、02:15 開始)では POST 時点から一貫して3枚**。dmesg の amdgpu 初期化は
  3デバイス分のみ(`added device 1002:6860` ×3 = `04/07/84`)、4枚目の初期化行は無い。
  ランタイム脱落の痕跡も無い(ログは boot 後 251秒で停止、PCI removal イベント無し)。
  → **「ランタイムで4枚目が脱落した」のではなく、起動時からそもそも列挙されていない**。
  ※ レポート(04:13、この起動中に作成)の「rocm-smi は4枚列挙」という記述は、この起動の
  カーネル証拠(amdgpu 3枚のみ)と矛盾しており、**誤観測の可能性が高い**(本プランの判断には影響しない)。
- **2026-06-13 以降の複数回のウォームリブートでも4枚目は一度も復帰していない**
  (`last reboot`: 06-13 05:40 / 09:55 / 18:24 / 23:44、06-14 02:15)。→ **ウォームリブートでは復旧不能**。
- **動作中の3枚は完全に健全**: いずれも `LnkSta: 8GT/s x16 (ok)`、16GB の 64bit prefetch BAR を高位 MMIO
  (`0x37000000000` / `0x37800000000` / `0x3f800000000`)に正常割り当て。**動作中3枚に MMIO 不足は無い**。
  (注: dmesg の初回 `BAR ... failed to assign` 群は再割り当てで解消済みの良性ログで、3枚は正常動作している。)
- **4枚目は所属ルートポートごと消失**: Intel ルートポート割り当ては
  `00:01.0→NVMe`, `00:02.0→GPU(04)`, `00:03.0→GPU(07)`, `80:00.0→NIC`, `80:03.0→GPU(84)`。
  node1(bus 80)は GPU 2枚構成のはずだが、4枚目が居るべき `80:01.0/80:02.0` ルートポートが
  **PCI ツリーに存在しない**。= GPU が「バスから落ちた(fallen off the bus)」状態。
- カーネル cmdline は素(`pci=realloc` 等なし)。稼働カーネル 5.15.0-164、amdgpu 6.8.5。
- ロックは空き、稼働中の llama-server なし。dmesg/lspci -vv の読み取りには既設の NOPASSWD sudo を使用
  (メモリ `project_mi25_qwen36_128k.md` 記載。読み取り専用に限定)。

### 最有力の原因

4枚目 MI25 の **PCIe リンクが POST 時に確立されておらず、ルートポートごと未列挙**になっている。候補:
(a) リンク学習の不安定/カード装着・補助電源・ライザーの接触不良(ルートポートごと消える挙動はこちらをより示唆)、
(b) BIOS の MMIOH(Above-4G Decoding / MMIO High Size)が4枚分の各 16GB BAR を確保しきれず、
   BIOS が当該デバイス/ポートを切り離した。
いずれもウォームリブートでは回復せず(実績あり)、**コールド電源サイクル(全電力ドレイン→再投入)**が
遠隔で可能な本命復旧手段。なお `pci=realloc` はルートポート自体が未列挙の現状では効かない(対象が無い)ため採らない。

## 対応方針(ユーザ選択: 「BIOS確認・調整まで」)

電源サイクルで戻らない場合は KVM 経由で BIOS 設定確認・調整まで進める。BIOS の設定変更は都度ユーザ確認の上で実施。

### 手順

すべて**プロジェクトルートからの相対パス**でスクリプト実行。電源操作(BMC/ipmitool)・KVM はローカル実行で
sudo 不要。リモートの sudo は **読み取り専用(dmesg/lspci -vv)に限り既設 NOPASSWD を使用**し、
**状態を変更する sudo が必要になった場合はコマンドをユーザに提示して依頼**する(CLAUDE.md の sudo 制約に準拠)。

1. **ロック取得**
   ```bash
   .claude/skills/gpu-server/scripts/lock.sh mi25
   ```

2. **事前状態の保全**(復旧前後比較・レポート添付用)
   ```bash
   ssh mi25 'lspci | grep -c "VGA compatible"; rocm-smi --showid; sudo -n dmesg > /tmp/mi25-dmesg-before.txt'
   .claude/skills/gpu-server/scripts/bmc-screenshot.sh mi25 /tmp/mi25-before.png   # 念のため現コンソール
   ```

3. **コールド電源サイクル**(本命)。`reset`(暖機リセット)では電力が抜けないため必ず `cycle` を使う。
   ```bash
   .claude/skills/gpu-server/scripts/bmc-power.sh mi25 status
   .claude/skills/gpu-server/scripts/bmc-power.sh mi25 cycle 30   # OFF→30秒待機→ON
   ```
   POST 進行を KVM スクショで監視(必要に応じ複数回)。OS 起動後 SSH 復帰を待つ。

4. **復旧確認**
   ```bash
   ssh mi25 'lspci | grep "VGA compatible"; lspci | grep -c "VGA compatible"; rocm-smi --showid'
   ```
   - **VGA が5(MI25 4枚 + ASPEED)、rocm-smi 4枚なら復旧成功** → 手順6へ(検証)。
   - **まだ3枚なら** → 手順5(BIOS)へ。

5. **(復旧しない場合)BIOS 確認・調整** — KVM の sendkeys で BIOS 進入。
   ```bash
   .claude/skills/gpu-server/.venv/bin/python .claude/skills/gpu-server/scripts/bmc-kvm.py \
     --bmc-ip 10.1.4.7 --bmc-user claude --bmc-pass Claude123 \
     sendkeys Delete Delete Delete --screenshot /tmp/mi25-bios.png
   ```
   - 確認項目(Supermicro X10DRG-Q): **Advanced → PCIe/PCI/PnP → Above 4G Decoding = Enabled**、
     **MMIOH Base / MMIO High Size**(4枚×16GB を収容できる十分大きい値、例 256G〜512G)。
     既知メモリ「BIOS MMIO 512GB依存」と整合するか確認。
   - スロット別の Link Speed/有効化、当該スロットが Disabled になっていないかも確認。
   - **設定変更が必要な場合は、変更内容(現値→新値)をユーザに提示し承認を得てから** sendkeys で変更・保存。
     変更後再起動して手順4で再確認。

6. **(復旧成功時)検証** — 4枚を実際にコンピュートで掴めるか軽く確認。
   ```bash
   ssh mi25 'rocm-smi --showproductname; rocm-smi --showmeminfo vram'   # 4枚分の VRAM 列挙
   # 任意: 4枚を使う構成で llama-server を短時間起動し -ngl で全GPU割当を確認(llama-server スキル参照)
   ```

7. **後始末・記録**
   ```bash
   ssh mi25 'sudo -n dmesg > /tmp/mi25-dmesg-after.txt'
   .claude/skills/gpu-server/scripts/unlock.sh mi25
   ```
   - 結果に応じてメモリ `project_mi25_qwen36_128k.md`(mi25固有の落とし穴)を更新。
   - 4枚目が**戻らなかった/BIOS 設定は正常だった場合**は、ハードウェア要因(カード再装着・補助電源・
     ライザー・スロット交換)として**物理アクセスが必要**な旨をレポートに明記しユーザへエスカレーション。

## 影響ファイル / 成果物

- **コード変更なし**(運用タスク)。
- BIOS 設定変更の可能性あり(手順5、都度ユーザ承認)。
- 既存ツールを利用: `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh` / `lock-status.sh` /
  `bmc-power.sh`(`cycle`) / `bmc-screenshot.sh` / `bmc-kvm.py`(`sendkeys`)。手順は `.claude/skills/gpu-server/bmc.md` 準拠。
- メモリ更新: `project_mi25_qwen36_128k.md`(復旧手順・BIOS MMIO 設定の確定値を追記)。

## 検証(end-to-end)

1. 電源サイクル後 `lspci | grep -c "VGA compatible"` が **5**(MI25 4 + ASPEED 1)になること。
2. `rocm-smi --showid` が **GPU[0]〜GPU[3]** の4枚を列挙すること。
3. 4枚目ルートポート(`80:01.0` または `80:02.0`)が `lspci` に出現し、配下の MI25 が `8GT/s x16 (ok)` で
   リンクし 16GB BAR が割り当たること(`sudo -n lspci -vvs <bus> | grep LnkSta`)。
4. (任意)4枚を使う llama-server 起動で全 GPU に VRAM が割り当たること。

## レポート

plan mode で計画したため、完了後に対になるレポートを `REPORT.md` 準拠で作成する
(タイトル50字以内、核心発見サマリに before/after の lspci・rocm-smi・BMC スクショを添付)。
本件は既存レポート `2026-06-14_041305_mi25_vulkan_backend_quality.md` の「既知の課題」の follow-up として相互リンクする。
