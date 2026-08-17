# aws-gpu01 / aws-gpu02 リファレンス

2026-08-16 に管理対象へ追加した Supermicro 製 GPU サーバ 2 台。ハードウェア情報は
BMC (IPMI / Redfish) と OS から実測取得したもの。

## ⚠️ 電源操作の制約（最重要）

**両機は起動時にファンが爆音になる。ユーザの明確な指示なしにリブート・電源投入・電源断を
行ってはならない。**

この制約はスクリプト側でガードしてある:

- `bmc-power.sh` の `on` / `off` / `soft` / `reset` / `cycle`
- `power-ctl.sh` の `on` / `off`（`llama-up.sh` / `llama-down.sh` もこれを経由する）

いずれも `ALLOW_FAN_NOISE=1` が無ければ **exit 20** で拒否される。`status` と
`bmc-screenshot.sh` は読み取りのみなので常に許可。

```bash
# 拒否される（正常な動作）
.claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 reset

# ユーザから明示的な指示を得た場合のみ
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 reset
```

ガード対象サーバの定義は `bmc-power.sh` と `power-ctl.sh` の `FAN_LOUD_SERVERS`
（両方に同じ値を書く。片方だけ変更しないこと）。

## ⚠️ 他ユーザのホームディレクトリを消さない

aws-gpu01 の `/home` には `myzk` / `sizumita` がある。**この 2 ユーザは現在サーバを使用して
いない**ため、ロック競合や GPU の取り合いを気にする必要はない（ロック機構への登録は
他 Claude セッションとの調停のために引き続き有効）。

ただし **ホームディレクトリのデータは削除しないこと**。ディスクを空ける必要が生じても、
`/home/myzk` / `/home/sizumita` には手を出さず、自分（`ubuntu`）の
`~/models` や `~/.cache/huggingface` を整理すること。aws-gpu01 は `/` に 707GB 空きがあり
（2026-08-16 時点）、通常の運用で他ユーザ領域に手を付ける理由はない。

## ハードウェア

| 項目 | aws-gpu01 | aws-gpu02 |
|---|---|---|
| 製品型番 | **SYS-4028GR-TRT2** | **SYS-4028GR-TRT** |
| M/B | X10DRG-OT+-CPU（BMC の Product Name は X10DRG-O+-CPU） | 同左 |
| シャーシ | CSE-418GTS-R4000BP | CSE-418GTS-R3200BP |
| 製品シリアル | S240241X8731725 | S188918X6107112 |
| ボードシリアル | VM185S038801 | VM158S006353 |
| GPU | Tesla P100-PCIE **16GB × 7 = 112GB** | 16GB × 4 + **12GB × 2 = 88GB** |
| CPU | Xeon E5-2687W v4 × 2（24C/48T, 3.0GHz） | Xeon E5-2640 v4 × 2（20C/40T, 2.4GHz） |
| RAM | 157 GiB | 94 GiB |
| ディスク | / に 1.1T（空き 707GB） | / に 457G（空き 141GB） |
| OS | Ubuntu 24.04.3 LTS | 同左 |
| driver / CUDA | 535.288.01 / nvcc 12.0（`/usr/bin/nvcc`） | 同左 |
| PSU | 4 台（PS1-4 すべて Presence detected） | 同左 |
| SSH ホスト名 | `chungpu`（エイリアス `aws-gpu01` とは別名） | `gpu02` |
| SSH ユーザ | **`ubuntu`**（既存 3 台は `llm`） | 同左 |
| sudo | **NOPASSWD で root 取得可** | 同左 |
| 他ユーザ | `/home` に myzk, sizumita（**現在は未使用**、ただしデータは残す） | ubuntu のみ |

### GPU 個体 baseline（2026-08-16 取得）

mi25 の Unique ID 運用（[CLAUDE.md](../../../CLAUDE.md) 参照）に相当するもの。NVIDIA では
`nvidia-smi --query-gpu=serial` が個体不変の識別子になる。

**aws-gpu01**（BDF / シリアル / ECC）

| idx | BDF | Serial | ECC |
|---|---|---|---|
| 0 | 05:00.0 | 0320318031972 | **Disabled** |
| 1 | 07:00.0 | 0323818055114 | Enabled |
| 2 | 08:00.0 | 0323817102181 | Enabled |
| 3 | 0C:00.0 | 0322818134388 | Enabled |
| 4 | 0D:00.0 | 0320318067792 | Enabled |
| 5 | 0E:00.0 | 0320318033253 | **Disabled** |
| 6 | 0F:00.0 | 0324218044774 | Enabled |

**aws-gpu02**

| idx | BDF | Serial | VRAM | ECC |
|---|---|---|---|---|
| 0 | 05:00.0 | 0322818006546 | 16GB | Enabled |
| 1 | 08:00.0 | 0320319086127 | 16GB | Enabled |
| 2 | 09:00.0 | 0323818055058 | 16GB | Enabled |
| 3 | 84:00.0 | 0322718237913 | **12GB** | Enabled |
| 4 | 88:00.0 | 0322818133689 | 16GB | Enabled |
| 5 | 89:00.0 | 0322718237810 | **12GB** | Enabled |

全 GPU が PCIe Gen3 x16 でリンクしている（登録時点）。

### 既知の個体差・注意事項

- **aws-gpu01: GPU0 と GPU5 のみ ECC Disabled**（他 5 枚は Enabled）。揃えるには
  `nvidia-smi -i 0 -e 1` 相当の操作＋**再起動が必要**なので、爆音制約により保留中。
- **aws-gpu01: SEL に PSU 故障履歴**（2026-02-23 に PS #0xc4-0xc7 が Asserted → 数分で
  Deasserted）。登録時点では 4 台とも `ok`。再発時はこの履歴と突き合わせること。
- **aws-gpu02: FAN7 が `No Reading` (ns)**。他 7 個は 4700-5200 RPM で正常。ファン未実装か
  センサー故障かは未確認。BMC の温度は全系統正常値。ファン fail 検知による全開化は起きていない。
- **aws-gpu02: POST に DIMM 不良の報告**（2026-08-17 に KVM で確認）。
  `Failing DIMM:DIMM location(Uncorrectable memory component found) / P2-DIMME1`。
  ただし BIOS の Total Memory は 98304MB、OS も 94GiB を認識して稼働しており、EDAC は正常に
  初期化、カーネルログにメモリエラーの記録もない。**実害は未観測だが追跡対象**
  （BIOS の Event Logs / `edac-util` / MCE を折を見て確認する）。
- **aws-gpu01 のブートディスクは SAS HBA（拡張カード）経由**。BIOS でスロット OPROM を
  無効化すると起動しなくなる（下記「BIOS 設定」参照）。aws-gpu02 はオンボード SATA ブート。
- **aws-gpu02 の VRAM は不均等**（16/16/16/12/16/12 GB）。t120h-p100 の
  `--tensor-split 11,12,13,14` 系プロファイルはそのまま流用できない。

## ネットワーク（既存 3 台との決定的な差）

両機は **ワークステーション（作業マシン）と同一拠点**にある。mi25 / t120h-p100 が別拠点で
低速なのとは前提が異なる。

| 経路 | aws-gpu01 | aws-gpu02 | 既存 mi25 / t120h-p100 |
|---|---|---|---|
| WS からの RTT | 0.3 ms | 0.3 ms | ping 不通（別拠点） |
| WS ↔ サーバ帯域 | 約 100 MB/s | 約 99 MB/s | 1 MB/s まで落ちることあり |
| サーバ → HuggingFace | **27 MB/s** | **37 MB/s** | P100 は Xet 経由が不安定で迂回策が必要 |
| WS → HuggingFace（参考） | 18 MB/s | 18 MB/s | 同左 |

**モデル取得は HF から直接ダウンロードするのが原則**（WS 経由より速い）。既存 3 台の
「WS へ落としてから転送」ルールはこの 2 台には適用しない。

```bash
# ~/.config/gpu-server/.env の HF_TOKEN を使う（匿名 DL は CDN で rate limit される）
ssh aws-gpu01 "~/.local/bin/hf download <repo> --include '*Q4_K_M*.gguf' --token <HF_TOKEN>"
```

### 100GbE 直結リンク（2 台間、RPC 分散推論用）

10.8.2.x の管理系とは別に、**aws-gpu01 ↔ aws-gpu02 が 100GbE で直結**されている。
片方の VRAM に収まらないモデルを 2 台に分散して載せるための経路（[llama-server
SKILL.md](../llama-server/SKILL.md) の「RPC 分散構成」節）。

| 項目 | aws-gpu01 | aws-gpu02 |
|---|---|---|
| IP アドレス | **192.168.100.1** | **192.168.100.2** |
| インタフェース | `enp11s0np0` | `enp4s0np0` |
| NIC | Mellanox ConnectX-4 (MT27700) | 同左 |
| リンク速度 | 100000 Mb/s (Full) | 同左 |
| MTU | 9000 | 9000 |
| RTT | 0.20 ms（相互） | — |
| RDMA | `mlx5_0/1` が **ACTIVE**、`libibverbs.so.1` 導入済 | 同左 |

llama.cpp は cmake 時に `libibverbs` を検出すると **`RDMA transport enabled
(auto-detected)`** を出し、RPC が TCP でなく RoCEv2 で通信する（コマンドラインの
変更は不要）。

**永続化について（2026-08-17）**: この 100GbE は当初 netplan に登録されておらず手動設定
（`ip addr add` + `ip link set up`）だったため、**再起動すると IP とリンクが消えていた**
（gpu02 の再起動で実際に失われ、gpu01 側も `No partner detected` になった）。
`/etc/netplan/60-rpc-100gbe.yaml` を両機に置いて永続化済み（既存の `50-cloud-init.yaml`
＝管理系 10.8.2.x は触っていない）。gpu01 の再起動で自動復帰を検証した。

```bash
# 永続化の確認
ssh aws-gpu01 "sudo cat /etc/netplan/60-rpc-100gbe.yaml; ip -br addr show enp11s0np0"
# 万一消えていた場合の手動復旧
ssh aws-gpu02 "sudo ip link set enp4s0np0 mtu 9000; sudo ip addr add 192.168.100.2/24 dev enp4s0np0; sudo ip link set enp4s0np0 up"
```

## ソフトウェア導入状況（2026-08-16 時点）

| ツール | aws-gpu01 | aws-gpu02 |
|---|---|---|
| llama.cpp | **未導入** | `~/llama.cpp` にビルド済（HEAD `971facc38`、CUDA backend） |
| `hf` CLI | `~/.local/bin/hf` あり | **なし**（要導入） |
| ttyd | ✓ `/usr/bin/ttyd` | ✓ |
| nvtop | ✓ `/usr/bin/nvtop` | ✓ |
| cmake / ninja | ✓ / ✓ | ✓ / ✗ |
| docker | ✗（リモートブラウザは未整備） | ✗ |
| uv | ✗ | ✗ |

`start.sh` の hf CLI パス解決は `command -v hf` → `$HOME/.local/bin/hf` →
`/home/llm/.local/bin/hf` の順にフォールバックする（既存 3 台の `llm` ユーザにも対応）。

## BMC

| 項目 | aws-gpu01 | aws-gpu02 |
|---|---|---|
| BMC IP | 10.11.12.1 | 10.11.12.2 |
| ユーザ | `claude`（ADMINISTRATOR 権限） | 同左 |
| BMC MAC | ac:1f:6b:ae:b9:1a | 0c:c4:7a:b8:16:36 |
| チップ / FW | ASPEED / 3.86 | 同左 |
| IPMI | ✓ lanplus | ✓ |
| Redfish | **✓ 使える**（`/redfish/v1/Systems/1` が応答） | ✓ |
| KVM | HTML5 KVMIP（最大 4 セッション）**スクショ動作確認済** | 同左 |

**KVM スクリーンショットは検証済み**（2026-08-16）。mi25 と同じ classic noVNC の 2D canvas で、
`bmc-screenshot.sh` がそのまま 1024x768 で取得できる（黒画にならない）。

**mi25 との違い**: mi25 は Redfish が DCMS ライセンス未活性で使えず IPMI 一択だが、
この 2 台は Redfish も応答する。ただし**運用は既存 Supermicro 機と揃えて IPMI
（`bmc-power.sh`）を正とする**。`power-ctl.sh` の `server_type()` も `supermicro` を返す。

```bash
# 電源状態（読み取り・ガード対象外）
.claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 status

# KVM スクリーンショット（OS ハング時の証跡保全。電源に影響しない）
.claude/skills/gpu-server/scripts/bmc-screenshot.sh aws-gpu01 /tmp/aws-gpu01.png

# 認証情報の再登録が必要になった場合（既定 IP は bmc-setup.sh に登録済み）
.claude/skills/gpu-server/scripts/bmc-setup.sh aws-gpu01 10.11.12.1 claude <pass>
```

## ファン制御（静音化）

2026-08-17 に静音化を実施した。**アイドル 6500rpm → 2900rpm**（duty 50% → 16%）。
恒久化のため両機に温度連動デーモン `smc-fanctl` を常設している。

### BMC のファン制御と 4 つの zone

| 項目 | 値 |
|---|---|
| fan mode 取得 / 設定 | `raw 0x30 0x45 0x00` / `raw 0x30 0x45 0x01 <mode>` |
| mode 値 | `00`=Standard `01`=Full `02`=Optimal `04`=HeavyIO |
| duty 取得 / 設定 | `raw 0x30 0x70 0x66 0x00 <zone>` / `raw 0x30 0x70 0x66 0x01 <zone> <duty>` |
| cooling zone | **0,1,2,3 の 4 つ**（zone4 以降は `01` を返し無効）。全 zone に同じ値を入れる運用 |
| FAN ↔ zone | zone0=FAN1,2 / zone1=FAN3,4 / zone2,3=FAN5,6,7,8（1 zone あたり 2 個） |
| FAN 下限閾値 | LNR 300 / LCR 500 / **LNC 700 rpm**（これを割ると BMC が override する） |

**duty ↔ RPM の実測**（両機ほぼ共通）:

| duty | 8% | 12% | 16% | 24% | 32% | 50%（BMC 既定） | 100% |
|---|---|---|---|---|---|---|---|
| RPM | 2100 | 2500 | **2900** | 3800 | 4600 | 6300–6800 | 11900 |

### 最重要: duty 指定には Full mode が必要

X10 系 BMC は **fan mode が Full(0x01) のときだけ手動 duty を保持する**。Optimal/Standard
では BMC が数十秒〜数分で自分の目標値に書き戻す。一方 **Full mode 中は BMC の自動制御が
止まる**ので、温度が上がってもファンは上がらない。そのため:

- **Full mode に固定するなら、温度を見て duty を決めるソフトウェアが必須**
- 制御プロセスを止めるときは必ず **Optimal(0x02) に戻す**（BMC に制御を返す）

また **Full へ切り替えた直後、BMC は非同期に全 zone を 100% へ書き戻す**。切替の直後に
duty を書くと上書きされるので **5 秒ほど待ってから書き、以後も duty を照合して修復する**
必要がある（`smc-fanctl` はこれを実装している）。

**BMC の Optimal 制御は負荷時に duty 68–70%（8000–9000rpm）まで上げる。**
これが「起動後もうるさい」の主因だった。

### smc-fanctl（温度連動デーモン）

実装は [fan-control/smc-fanctl.py](./fan-control/smc-fanctl.py)、unit は
[fan-control/smc-fanctl.service](./fan-control/smc-fanctl.service)。導入・削除:

```bash
# 導入（ipmitool 導入 → /opt/smc-fanctl 配置 → systemd enable --now）
.claude/skills/gpu-server/scripts/install-fan-control.sh all

# 削除（サービス停止時に fan mode は Optimal に戻る）
.claude/skills/gpu-server/scripts/install-fan-control.sh aws-gpu01 --uninstall

# 状態確認
ssh aws-gpu01 "systemctl status smc-fanctl --no-pager; sudo journalctl -u smc-fanctl -n 20 --no-pager"
```

- in-band IPMI（`/dev/ipmi0`）を使うのでネットワーク不要。10 秒周期
- `CPU1/2 Temp` / `GPU1-10 Temp` / `System`・`Peripheral` / `PCH` をそれぞれのカーブに通し、
  **最も高い duty を採用**。下げるときは 3℃ のヒステリシスを取る
- 下限は **16%**（8% はアイドルでも CPU が 61℃ まで上がり続けたため採用しない）
- 毎周期 duty を読み戻し、BMC に書き戻されていたら**自己修復**する
- フェイルセーフ: 停止時・IPMI 連続失敗時・critical 温度（CPU/GPU 85℃）で **Optimal に復帰**

### 緊急時: BMC の自動制御に戻す

デーモンが暴走した、あるいは冷却が不安なときは、これで BMC に制御を返せる（即時・OS 不要）:

```bash
# WS から（lanplus）
source ~/.config/gpu-server/.env
ipmitool -I lanplus -H "$BMC_AWS_GPU01_HOST" -U "$BMC_AWS_GPU01_USER" -P "$BMC_AWS_GPU01_PASS" \
  raw 0x30 0x45 0x01 0x02

# サーバ上から（in-band）
ssh aws-gpu01 "sudo systemctl stop smc-fanctl; sudo ipmitool -I open raw 0x30 0x45 0x01 0x02"
```

### 起動（POST）中の爆音 — 完全には消せない

電源投入から OS 起動までは BMC が全ファンを 100%（11900rpm）で回す。BMC は POST 中も IPMI を
受け付けるが、**ファン制御を手放さず duty を 100% に書き戻し続けるため、外部からの投入は
競り負ける**（2026-08-17 実測）。抑制と記録を行うのが
[scripts/boot-quiet.sh](./scripts/boot-quiet.sh)。

| 条件 | POST 中 FAN1-8 平均の中央値 |
|---|---|
| 2 秒間隔投入・BIOS 変更前 | 5,386 rpm |
| 0.5 秒間隔投入・BIOS 変更前 | 5,243 rpm |
| **0.5 秒間隔投入・BIOS 変更後** | **3,700 rpm** |

```bash
# 抑制しながら RPM を記録（電源操作の直前にバックグラウンドで開始する）
BOOT_QUIET_WRITE_INTERVAL=0.5 .claude/skills/gpu-server/scripts/boot-quiet.sh aws-gpu02 0x10 420 &
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu02 reset

# 抑制せず記録のみ（比較用）
.claude/skills/gpu-server/scripts/boot-quiet.sh aws-gpu02 --observe 420
```

**起動後は速い**: `smc-fanctl` は OS 起動から **10〜26 秒でサービス開始、14〜44 秒で duty 適用**
（`After=sysinit.target` の早期起動）。爆音区間は「電源投入〜OS 起動＋十数秒」に限られる。

**爆音が消えたわけではないので、`bmc-power.sh` / `power-ctl.sh` の `ALLOW_FAN_NOISE` ガードは
維持する。**

### BIOS 設定（2026-08-17 に変更した項目）

POST を短くして爆音区間を縮めるための変更。**BIOS に fan 関連の設定項目は存在しない**
（Advanced 配下と IPMI タブを全確認。X10 のファン制御は BMC 専管で、`Fast Boot` 相当も無い）。

| 項目 | 変更 | aws-gpu01 | aws-gpu02 |
|---|---|---|---|
| `Advanced → Boot Feature → Wait For "F1" If Error` | Enabled → **Disabled** | ✓ | ✓ |
| `Advanced → PCIe/PCI/PnP → Onboard LAN 1 OPROM` | PXE → **Disabled** | ✓ | ✓ |
| 同 → `CPU* Slot* PCI-E OPROM` | Legacy → Disabled | **✗ 起動不能。Legacy のまま** | ✓（11 スロット） |

**触ってはいけない項目**: `Above 4G Decoding` (Enabled)、`MMIO High Size` (512G)、
`Onboard Video OPROM` (Legacy)、`VGA Priority` (Onboard)。

#### ⚠️ aws-gpu01 でスロット OPROM を無効化してはいけない

**aws-gpu01 のブートディスクは SAS HBA（拡張カード）経由**なので、スロット OPROM を Disabled に
すると BIOS がブートデバイスを見失い **EFI Shell に落ちて起動しない**（2026-08-17 に実際に発生）。
aws-gpu02 はオンボード SATA (`/dev/sda2`) ブートなので同じ変更でも問題ない。

将来 gpu01 でも POST を短縮したい場合は、**SAS HBA が挿さっているスロットだけ Legacy に残し、
他を Disabled にする**こと（スロット特定は OS 上で `lspci -tv` から辿る）。

#### BIOS に確実に入る方法

**Delete 連打は POST のタイミング次第で外れる**（両機で何度も失敗した）。KVM 経由の
EFI Shell からの `exit` も効かない。次回起動を BIOS Setup に固定するのが確実:

```bash
source ~/.config/gpu-server/.env
ipmitool -I lanplus -H "$BMC_AWS_GPU01_HOST" -U "$BMC_AWS_GPU01_USER" -P "$BMC_AWS_GPU01_PASS" \
  chassis bootdev bios
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 reset
# 約 2 分後に bmc-screenshot.sh / bmc-kvm.py で Setup 画面が見える
```

## 未検証事項

- `start.sh` のサーバ別パラメータ (`--flash-attn 1 --poll 0 -b 4096 -ub 4096`) は
  t120h-p100 の実績値を踏襲した推定値のまま。**単体運用（RPC なし）での検証は未実施**。
  RPC 分散構成では `-b 2048 -ub 512` で起動実績あり（下記「検証済み」）。
- `~/.ssh/config` の定義に既存 3 台にある `ServerAliveInterval 3` が無い。

## 検証済み（2026-08-16 RPC 分散実験）

詳細は [2026-08-16 DeepSeek-V4 RPC 分散レポート](../../../report/2026-08-16_175749_deepseek_v4_rpc_dual_gpu_server.md)。

- **ビルド**: 両機とも `update_and_build-aws-gpu0*.sh` でビルド成功
  （llama.cpp `10bf611e5` / build 10451）。**nvcc 12.0 + gcc 13.3 で問題なし**、
  `-DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++-12` は不要だった。
- **llama-server 起動実績あり**: `DeepSeek-V4-Flash-0731 UD-Q4_K_XL`（144.4 GiB）を
  2 台 13 GPU に RPC 分散し **ctx=131072 で起動**（VRAM 157.1 GiB、pp 89.7 t/s、tg 13.6 t/s）。
- **100GbE + RDMA (RoCEv2)** が llama.cpp 本体の機能として自動で有効化されることを実測。
- **aws-gpu01 の HF ダウンロードは実測 117 MB/s**（155GB を 22分12秒）。
  登録時に測った 27 MB/s より大幅に速い。
- **aws-gpu02 の VRAM 不均等は `--tensor-split` 不要**。llama.cpp の自動配分が
  12GB カード（index 3, 5）にも余裕を残す形で収める。

## 検証済み（2026-08-16 登録時）

- ロック取得・解放（`lock.sh` / `unlock.sh` / `lock-status.sh` の全台一覧）
- BMC 電源状態の読み取り（`bmc-power.sh status` / `power-ctl.sh status` → `On`）
- **爆音ガードが実際に電源操作を止めること**（`reset` / `off` / `on` がすべて exit 20 で拒否され、
  拒否後も `System Power: on` かつ uptime 継続＝副作用ゼロを確認）
- KVM スクリーンショット（両機とも 1024x768 でログインプロンプトを取得）
