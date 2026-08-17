# aws-gpu01 / aws-gpu02 のファン騒音低減

## Context

aws-gpu01 / aws-gpu02（Supermicro SYS-4028GR-TRT2 / TRT、M/B X10DRG-OT+）は
**起動時にファンが全力で回って爆音になる**。これが理由で CLAUDE.md / `bmc-power.sh` /
`power-ctl.sh` に「ユーザの明示指示なしに電源操作しない」爆音ガード（`ALLOW_FAN_NOISE=1`）が
入っており、ECC 設定の統一など再起動を伴う作業がすべて保留になっている。

ユーザの要望は **(1) 起動直後の爆音を何とかしたい（最優先）**、**(2) 起動完了後の常時騒音も
できれば下げたい**。温度連動デーモンの常設と、立ち会いでの再起動を伴う BIOS 変更まで許可済み。

### 実測した現状（2026-08-17、読み取りのみ）

| 項目 | aws-gpu01 | aws-gpu02 |
|---|---|---|
| Fan mode (`raw 0x30 0x45 0x00`) | **02 = Optimal** | **02 = Optimal** |
| duty zone0 / zone1 (`raw 0x30 0x70 0x66 0x00 <z>`) | 0x34 (52%) / 0x32 (50%) | 0x32 (50%) / 0x36 (54%) |
| FAN1-8 RPM（アイドル） | 6300–6600 | 6300–6800（FAN7 は No Reading） |
| FAN 閾値 (LNR/LCR/LNC) | 300 / 500 / **700 RPM** | 同左 |
| 温度 | CPU 40–41℃, GPU 42–47℃, System 39℃ | CPU 49–53℃, GPU 42–48℃, System 40℃ |
| in-band IPMI | `/dev/ipmi0` + `ipmi_si` あり、**ipmitool 未導入** | 同左 |
| BIOS | 3.1 (2018-07-13) | 3.2 (2019-12-13) |
| 稼働中 | DeepSeek-V4 llama-server（RPC 親） | ggml-rpc-server（RPC 子） |

**アイドルで温度に余裕があるのに duty 50% / 6500 RPM 固定** ＝ 定常騒音には明確な削減余地がある。

### 技術的前提（調査結果）

- X10 系は **Fan mode = Full (0x01) にしないと手動 duty 指定が BMC に上書きされる**
  （Optimal/Standard のままでは数十秒〜数分で BMC の目標値に戻る）。
  → 静音化は「Full mode ＋ ソフトウェア側の温度連動制御」が定石（smfc / smx10fanctl と同じ構成）。
- Fan mode 値: 0=Standard, 1=Full, 2=Optimal, 4=Heavy IO。
  duty は `raw 0x30 0x70 0x66 0x01 <zone> <duty>`、zone0=CPU/システム、zone1=ペリフェラル。
- **BMC は POST 中も IPMI を受け付ける**ので、電源 ON 直後から外部（WS）から
  Full + 低 duty を投げ続ければ POST 中の爆音も抑えられる可能性がある（要実測。
  BMC が POST 完了までファン制御を手放さない実装なら効かない）。
- BMC の温度センサは **GPU1–GPU10 Temp を持っている**ので、デーモンは in-band IPMI だけで
  GPU 温度も取れる（nvidia-smi 不要 = RPC 子機でも同じ実装が使える）。

## 方針

3 層に分けて、**再起動が不要な層から順に**実施する。

| 層 | 目的 | 再起動 | 手段 |
|---|---|---|---|
| **A** | 起動完了後の定常騒音を下げる | 不要 | サーバ常駐の温度連動デーモン（Full mode + duty 制御） |
| **B** | 起動直後の爆音を短縮／抑制 | 要（立ち会い） | WS から BMC 経由で電源 ON 直後に Full + 低 duty を投入し続ける |
| **C** | POST 自体を短縮して爆音時間を縮める | 要（立ち会い） | BIOS の Fast Boot / 不要 Option ROM 無効化 |

## 実施手順

### Step 0: 準備

- ロックは前セッション（`aws-mmns-generic-abl-20260816_220958`）が保持したまま
  DeepSeek-V4 が稼働中。同一ユーザの作業継続として**そのロックを引き継いで作業**する
  （`unlock.sh` はしない）。稼働中の llama-server は Step 4 の負荷試験にそのまま使える。
- ベースライン記録（fan mode / duty / 全 FAN RPM / 全温度）を 10 分間 15 秒間隔で採取し、
  scratchpad に CSV 保存。以降の before/after 比較の基準にする。
- **sudo が必要なので以下はユーザに実行を依頼**（CLAUDE.md の sudo ルール）:
  ```bash
  ssh aws-gpu01 "sudo apt-get install -y ipmitool"
  ssh aws-gpu02 "sudo apt-get install -y ipmitool"
  ```
  in-band 制御にするのは、WS 常駐にすると WS 停止時にファンが低速固定で残るため。

### Step 1: zone マッピングと最小 duty の実測（gpu02 → gpu01）

WS から lanplus 経由で、**必ず温度監視を並走させながら**段階的に下げる:

1. `raw 0x30 0x45 0x01 0x01`（Full）に切替
2. zone0 の duty を 0x30 → 0x28 → 0x20 → 0x18 → 0x10 と下げ、各段で 60 秒待って
   全 FAN RPM を記録 → **どの FAN が zone0 か判別**（RPM が動いたファン）
3. zone1 も同様に走査
4. 各段で「RPM が LNC 700 を割らないか」「BMC が duty を戻さないか（override 検知）」を確認
5. **アボート条件**: CPU ≥ 75℃ / GPU ≥ 75℃ / いずれかの FAN が `ns` になる →
   即 `raw 0x30 0x45 0x01 0x02`（Optimal）に戻す
6. アイドル時の実用最小 duty を決定（暫定目標 20–30% = 2500–3500 RPM 前後）

gpu01 は llama-server の親なので、gpu02（RPC 子、負荷は軽い）から先に試す。

### Step 2: 温度連動デーモン（層 A）

リポジトリに新規追加（既存 `setup-*.sh` / `install-global.sh` と同じ配布パターン）:

- `.claude/skills/gpu-server/fan-control/smc-fanctl.py` — 制御本体（python3.12、依存なし）
- `.claude/skills/gpu-server/fan-control/smc-fanctl.service` — systemd unit
- `.claude/skills/gpu-server/scripts/install-fan-control.sh` — 両機への配布＋有効化
  （sudo が要る部分はコマンドを表示してユーザに依頼する形にする）

制御ロジック:

- 10 秒周期で in-band `ipmitool sdr` から CPU1/2・System・Peripheral・GPU1–10 Temp を読む
- zone ごとに多段テーブルで duty 決定（例: GPU/CPU の最大値が ≤50℃→25%、60℃→40%、
  70℃→60%、75℃→80%、≥80℃→100%）＋ ヒステリシス（下げは 3℃ 余裕を見てから）
- 変化があったときだけ duty を書き、journald に記録

フェイルセーフ（Full mode は BMC の自動制御を止めるため必須）:

| 事象 | 挙動 |
|---|---|
| サービス停止（`ExecStop`） | fan mode を **Optimal (0x02) に戻す** |
| 異常終了 / IPMI 連続失敗 | Optimal に戻して exit、systemd `Restart=on-failure` |
| 温度 ≥ critical（CPU 80℃ / GPU 80℃） | duty 100%、さらに超えるなら Optimal に戻して BMC に委譲 |
| fan mode の drift | 60 秒ごとに mode を読み、Full でなければ再設定 |

起動順は `After=sysinit.target` / `Before=multi-user.target`（in-band なのでネットワーク待ち不要）
＝ カーネル起動後の最速タイミングで duty を下げる。これが層 B が効かなかった場合の
「爆音を早く終わらせる」保険にもなる。

### Step 3: 起動時爆音の実測と抑制（層 B、**再起動はユーザに確認**）

1. **爆音プロファイル取得**: WS から 1 秒間隔で全 FAN RPM をポーリングしながら、
   ユーザ立ち会いで `ALLOW_FAN_NOISE=1 bmc-power.sh aws-gpu02 reset` → 電源 ON から
   何秒間 100% で回るかを CSV 化（POST → OS 起動 → デーモン適用の各段が見える）
2. **抑制試験**: 同じ再起動を、`boot-quiet.sh`（1 秒間隔で Full + 低 duty を投げ続ける
   ループ）を並走させて実施し、RPM が抑えられるか比較
3. 効くなら `bmc-power.sh` の `on` / `reset` / `cycle` に組み込み（電源投入と同時に自動起動）。
   効かないなら層 B は諦めて層 C の POST 短縮に寄せる（結論はレポートに残す）

再起動は 1 回にまとめず、Step 3-1 / 3-2 / Step 4 で計 3 回程度必要。**毎回ユーザに確認**する。

### Step 4: BIOS で POST 短縮（層 C、立ち会い再起動）

`bmc-kvm.py sendkeys Delete` で BIOS に入り、**変更前に全ページのスクショを保全**した上で:

- Advanced → Boot Feature: **Fast Boot** / Quiet Boot / POST Error Pause
- Advanced → PCIe/PCI/PnP: ブートデバイス以外の **Option ROM を Disabled**
  （GPU 7 枚の VGA OpROM 実行は POST 時間の大きな部分。CUDA 動作には無関係）
- Memory 設定に DIMM トレーニングをスキップする項目があれば有効化（157GiB / 94GiB あるため効果大）
- **fan 関連の項目が存在するか確認**（X10DRG では無い見込みだが未確認なので目視する）

1 項目群ずつ変えて POST 時間を計測。`Above 4G Decoding` などGPU 動作に必要な設定は触らない。
ブート不良になったら KVM から BIOS デフォルトに戻して復旧できることを前提に進める。

### Step 5: 永続性の確認

- `mc reset cold` 後に fan mode が保持されるか（duty は揮発する想定）
- OS 再起動でデーモンが自動起動し duty が下がるか（Step 3 の再起動で同時に確認）
- AC 断は行わない

### Step 6: ドキュメントとレポート

- `.claude/skills/gpu-server/aws-gpu.md` に「ファン制御」節を追記
  （fan mode / duty の実測値、デーモンの仕様、緊急時に Optimal へ戻すコマンド）
- 爆音が実際に軽減できた場合は **CLAUDE.md と `bmc-power.sh` / `power-ctl.sh` の
  爆音ガードの扱いを見直す**（`FAN_LOUD_SERVERS` は両ファイルに同じ値を書く規約に注意）。
  効果が不十分ならガードは現状維持
- `report/` に REPORT.md 準拠のレポート（**概要**必須、タイトル 50 字以内、核心発見サマリ冒頭に
  PNG 埋め込み）。before/after の RPM・duty・温度表と、起動時 RPM プロファイルのグラフを添付
  （グラフは dataviz スキル準拠、ログは `report/attachment/` に通常 git で追加）

## 検証

| 観点 | 方法 | 合格基準 |
|---|---|---|
| 定常騒音 | アイドル 10 分の RPM 平均を before/after 比較＋**ユーザの体感確認**（実機前） | RPM が明確に低下し、温度が平衡で CPU < 65℃ / GPU < 60℃ |
| 実負荷の安全性 | 稼働中の DeepSeek-V4 llama-server に 15–20 分連続推論を投げ、温度平衡点を記録。`nvidia-smi --query-gpu=temperature.gpu,clocks_throttle_reasons.sw_thermal_slowdown` も併記 | GPU < 75℃、thermal slowdown が立たない、推論速度が既存レポート値から劣化しない |
| 起動時騒音 | 1 秒間隔 RPM ポーリングの before/after ＋ユーザの体感 | 爆音区間が短縮 or 消える。効かない場合はその結論を記録 |
| フェイルセーフ | `systemctl stop` / プロセス kill / IPMI 到達不能を人為的に起こす | いずれも fan mode が Optimal に戻る |
| 永続性 | `mc reset cold` と OS 再起動後に設定値を確認 | 再起動後も自動で静音状態に復帰 |

## 主なリスク

- **Full mode 中はデーモンが唯一の冷却制御**になる → 上記フェイルセーフ必須。
  実装前に「停止時に Optimal へ戻る」ことを単体で確認してから常設する
- P100 は passive 冷却でシャーシ風量に完全依存 → 下限 duty はアイドル値ではなく
  **実負荷試験の結果から決める**（アイドルで静かでも負荷時に足りなければ意味がない）
- duty を下げすぎて RPM が LNC 700 を割ると BMC が override（実害はなく効かないだけ）
- BIOS の Option ROM 無効化はブート不良のリスク → 変更前スクショ、1 項目ずつ、
  ブートデバイスの OpROM は残す
- 再起動は毎回ユーザの明示指示を得てから `ALLOW_FAN_NOISE=1` を付けて実行する
