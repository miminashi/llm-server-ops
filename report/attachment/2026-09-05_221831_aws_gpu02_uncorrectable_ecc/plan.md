# aws-gpu02 のハング原因特定と復旧

## Context

前回レポート [2026-09-05_204557_glm53flash_pr27773_sparse_fa_multistream.md](../../projects/llm-server-ops/report/2026-09-05_204557_glm53flash_pr27773_sparse_fa_multistream.md)
で aws-gpu02 が本日 3 回（通算 5 回）ハングし、最後は **POST すら抜けられない**状態になって
両機の電源を落として終了した。同レポートは原因を「痕跡なし・ハードウェア障害を強く疑う」と
記録するに留まっている。

本セッションの読み取り専用調査で **原因が特定できた**。ユーザから電源投入・BIOS 設定変更・
BIOS 初期化・**gpu02 上のすべての sudo** の許可を得ているので、リモートで打てる手をすべて
打って復旧を試みる。物理作業（DIMM 抜き差し・CMOS クリア）は「可能だが当面すぐには無理」
との回答なので、**最後の手段として手順だけ用意し、リモートで完結する策を先に尽くす**。

---

## 確定した原因（本セッションの読み取り専用調査）

**BMC の SEL に `Memory | Uncorrectable ECC` が記録されていた。** 前回「MCE / Hardware Error /
Xid / panic の記録は一切ない」と書いたのは **OS 側の journalctl だけを見ていた**ためで、
BMC 側には残っていた。

| SEL | 時刻 | 前回レポートのハング |
|---|---|---|
| `82` `83` | 2026-09-05 **20:29:04** ×2 | 3-1（20:28:42、アイドル中） |
| `84` | 2026-09-05 **20:42:36** | 3-2 前後 |
| `85` `86` | 2026-09-05 **21:00:17** ×2 | 3-3（21:00 頃、**ブート中**） |
| `5e`〜`61` | 2026-09-02 01:15:26 / 01:20:07 / 01:20:08 | 09-02 の 2 回目（01:17:12） |
| `73` `74` | 2026-09-02 13:46:23 ×2 | POST 中の検出（直前に OEM レコード連番あり） |

裏付け:

- **BMC 時計は WS と 1 秒差で同期**（`sel time get` で確認）。時刻の突き合わせは信頼できる
- **09-02 より前に memory イベントは 1 件も無い**（SEL は 2019 年から 138 件残っている）
- **対照の aws-gpu01 は SEL に memory イベント 0 件**（全 29 件、最終追記 08-15）
- `82`〜`86` の前後に POST を示す OEM レコード（`Unknown #0xff` の連番）が**無い**ため、
  これらは POST 検出ではなく **OS 稼働中の実イベント**
- Event Data は 5 件とも `a11a81`（sensor-specific offset 0x1 = Uncorrectable ECC）

Xeon E5 v4 の uncorrectable ECC は fatal MCE として即座に停止するため、**ジャーナルに何も
残らないハードロックアップ**という前回の観測と完全に整合する。「アイドルでも高負荷でも
ブート中でも落ちる」という説明のつかなかった挙動も、これで一貫して説明できる。

### DIMM の特定は未確定（BMC のデコードが壊れている）

SEL の表示は `DIMME1(CPU2)` / `DIMME2(CPU2)` だが、**この位置情報は信用できない**:

- 同じ SEL に `DIMMS-(CPU4)` / `DIMM[-(CPU4)` という**存在しない位置**の記録がある（2 ソケット機）
- `aws-gpu.md` は「P2-DIMME1 は空スロット、BIOS が過去の故障情報を表示し続けているだけ」と
  記録している（2026-08-18 に `dmidecode -t 17` で 3 枚のみ実装と確認済み）
- 一方 **Redfish の Memory コレクションは 5 枚を返す**（`P1_DIMMA1/A2/A3` + `P2_DIMME1/E2`、
  すべて 32GB）。**Health は `P1_DIMMA1` と `P1_DIMMA2` が `Critical`**、他 3 枚は OK
- OS が見ている RAM は 94 GiB = 32GB×3 なので、**物理的には 5 枚載っているが BIOS が CPU2 側
  2 枚を無効化したまま保持している**可能性が高い（POST の `Failing DIMM ... P2-DIMME1` と
  `numactl` の node1 size = 0 MB がこれで説明できる）
- `OperatingSpeedMhz` は 1600（`AllowedSpeedsMHz` 2400）。**1 チャネルに 3 枚（3DPC）**という
  信号品質的に最も厳しい実装で、E5-2640 v4 の POR で 1600 まで落ちている
- PN は `36ASF4G72PZ-2G3A1`（A2/A3）と `36ASF4G72PZ-2G3D1`（E2）で**リビジョン混在**

つまり **「メモリの uncorrectable ECC」までは確定、「どの DIMM か」は未確定**。ここを詰めるのが
本作業の中核になる。

### 時系列で気になる点（仮説）

`smc-fanctl` による静音化（2026-08-17、アイドル 6,500 → **2,900rpm**）の 2 週間後に UCE が
始まっている。そして **`smc-fanctl` のカーブ入力は CPU1/2・GPU1-10・System・Peripheral・PCH の
5 系統だけで、`P1-DIMMA* Temp` と `VmemABVRM Temp` を一切見ていない**
（`.claude/skills/gpu-server/fan-control/smc-fanctl.py`）。DIMM 温度は無監視のまま
風量を 45% に落としたことになる。因果は未証明だが、**確認と緩和のコストが低いので必ず潰す**。

---

## 実施計画

### Phase 1 — 証跡の保全（読み取り専用・先に済ませる）

レポート添付ディレクトリに保存する。復旧作業で SEL が上書き・消去されても残るように。

- `ipmitool ... sel elist` 全 138 件 → `sel_aws-gpu02.txt`
- `sel get 0x5e 0x5f 0x60 0x61 0x73 0x74 0x82..0x86` の raw → `sel_raw_memory.txt`
- Redfish `/redfish/v1/Systems/1/Memory/{1..5}` → `redfish_memory.json`
- 対照として aws-gpu01 の SEL → `sel_aws-gpu01.txt`

認証は `~/.config/gpu-server/.env` の `BMC_AWS_GPU02_HOST/USER/PASS`（`bmc-power.sh` と同じ）。

### Phase 2 — 電源投入と POST 観察

**boot-quiet の抑制窓を延ばしてから投入する**（POST が長引いても爆音に戻らないように）。
`bmc-power.sh` は `BOOT_QUIET_SECS` をそのまま `boot-quiet.sh` に渡す。

```bash
BOOT_QUIET_SECS=2400 ALLOW_FAN_NOISE=1 \
  .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu02 on
```

- 20 秒間隔で `bmc-screenshot.sh aws-gpu02 <out>.png` を撮り、**連続する PNG の md5 が一致
  したら停止**と判定する（前回セッションと同じ判定法）
- 正常時の目安: **85 秒で OS 起動 / 108 秒で smc-fanctl 稼働**（`aws-gpu.md` 実測値）
- 並行して `ssh -o ConnectTimeout=5 -o BatchMode=yes -n aws-gpu02 true` をポーリング
- 上限 10 分。ファン回転数は `boot-quiet.sh` の CSV（`/tmp/boot-quiet-aws-gpu02.csv`）で監視

**分岐 A: OS が起動した → Phase 3 へ。分岐 B: POST で停止 → Phase 2b へ。**

### Phase 2b — POST が通らない場合（リモートでの復旧ラダー）

上から順に試し、通った時点で Phase 3 へ抜ける。各段の前に必ず KVM スクショで証跡を残す。

1. **電源 OFF → 90 秒待機 → cold cycle**（最大 2 回）。長めのドレインで通ることがある
2. **BMC のコールドリセット**: `ipmitool ... mc reset cold` → BMC 復帰を待って再投入。
   BMC 側の電源シーケンス状態が固まっている場合に効く
3. **次回起動を BIOS Setup に固定して入る**（`aws-gpu.md` の「BIOS に確実に入る方法」）:
   ```bash
   ipmitool -I lanplus -H "$BMC_AWS_GPU02_HOST" -U "$BMC_AWS_GPU02_USER" \
     -P "$BMC_AWS_GPU02_PASS" chassis bootdev bios
   BOOT_QUIET_SECS=2400 ALLOW_FAN_NOISE=1 \
     .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu02 reset
   ```
   画面操作は `scripts/bmc-kvm.py ... sendkeys --prefer vkbd`（BIOS ナビは vkbd 推奨）
4. Setup に入れたら **F3 = Restore Optimized Defaults → F4 保存**（ユーザ許可済み）。
   これで **BIOS が保持している DIMM 無効化マップと過去の故障記録がクリアされ、5 枚すべてが
   再テストされる**ことを狙う

   **初期化後に必ず入れ直す設定**（`aws-gpu.md` の「触ってはいけない項目」。既定値に戻ると
   6 GPU + Mellanox の MMIO が足りず起動不能になりうる）:

   | 項目 | 戻す値 |
   |---|---|
   | `Above 4G Decoding` | Enabled |
   | `MMIO High Size` | 512G |
   | `VGA Priority` | Onboard |
   | `Onboard Video OPROM` | Legacy |
   | ブート順 | UEFI の `ubuntu`（オンボード SATA `/dev/sda`） |

   ※ `Wait For "F1" If Error` = Disabled と各スロットの OPROM 無効化（POST 短縮のための
   任意設定）は**復元しなくてよい**。gpu02 はオンボード SATA ブートなので gpu01 のような
   起動不能リスクは無い。
5. Setup にも入れない場合は **ここで一旦停止し、物理作業をユーザに依頼**（下の「物理作業の
   手順」）。無為に電源を入れ直し続けない。

### Phase 3 — OS 起動後の証拠固め（sudo 許可済み）

まず `lock.sh aws-gpu02` を取る（再起動で `/tmp` が飛ぶので必ず起動後に取る）。
aws-gpu01 は OFF のまま触らないのでロック不要。

```bash
ssh -n aws-gpu02 "sudo dmidecode -t 17"          # DIMM 実装・PN・Serial・速度
ssh -n aws-gpu02 "sudo dmidecode -t 16"          # 物理メモリアレイ（最大容量・エラー訂正方式）
ssh -n aws-gpu02 "free -g; numactl --hardware"   # node1 size が 0 のままか
ssh -n aws-gpu02 "sudo journalctl -k -b -1 | tail -50; sudo journalctl -k -b -2 | tail -50"
ssh -n aws-gpu02 "grep -r . /sys/devices/system/edac/mc/mc*/ce_count /sys/devices/system/edac/mc/mc*/ue_count /sys/devices/system/edac/mc/mc*/*/[cu]e_count 2>/dev/null"
ssh -n aws-gpu02 "nvidia-smi -L; nvidia-smi --query-gpu=index,serial,memory.total --format=csv"
```

**確認したい分岐点**:

- `dmidecode -t 17` の実装枚数が **3 枚のままか / 5 枚に増えたか**（BIOS 初期化をした場合）
- POST 画面に `Failing DIMM ... P2-DIMME1` がまだ出ているか（KVM スクショで確認）
- EDAC の CE/UE カウンタ（08-18 時点は全 0）

さらに **`rasdaemon` を導入**して以後の CE/UE を per-DIMM ラベル付きで記録できるようにする
（`sudo apt install rasdaemon && sudo systemctl enable --now rasdaemon`、
`sudo ras-mc-ctl --error-count` / `--summary`）。次に落ちたときの情報量が段違いになる。

### Phase 4 — DIMM の特定

**本命: memtest86+**（Ubuntu 24.04 のパッケージが GRUB エントリを自動生成する。物理メディア
不要で、失敗アドレスから DIMM スロットを推定表示できる）。

```bash
ssh -n aws-gpu02 "sudo apt-get install -y memtest86+ && sudo update-grub"
ssh -n aws-gpu02 "sudo awk -F\\\" '/menuentry /{print \$2}' /boot/grub/grub.cfg"   # エントリ名を確認
ssh -n aws-gpu02 "sudo grub-reboot '<Memtest86+ のエントリ名>'"                     # 次回起動のみ
BOOT_QUIET_SECS=2400 ALLOW_FAN_NOISE=1 \
  .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu02 reset
```

- 進捗は KVM スクショを 5 分間隔で撮って追う。96 GB で 1 pass 数時間かかる前提
- **最低 1 pass、エラーが出なければ 2 pass**。エラーが出たら失敗アドレスと DIMM 表示を保全
- memtest 中も SEL を WS から監視し、UCE が積まれるかを見る
- 終わったら通常起動へ戻す（`grub-reboot` は一度きりなので放置で戻る）

**併用: OS 上での負荷試験**（memtest でシロだった場合、実運用に近い条件で誘発する）。
`stressapptest` か `memtester` を全メモリの 9 割に対して回し、**WS 側から SEL をポーリング**
する。ハングしても SEL には残る（今回それが証明された）。

### Phase 5 — リモートで打てる緩和策

Phase 3/4 の結果を見て採否を決める。**いずれも BIOS 設定または既存デーモンの変更で完結する。**

| # | 施策 | 狙い | 副作用 |
|---|---|---|---|
| 1 | **BIOS 初期化**（Phase 2b-4 と同じ操作。POST が通っていても実施する価値がある） | BIOS が保持する DIMM 無効化マップをクリアし、5 枚全部を再テストさせる。E1/E2 が生き返れば RAM が 160GB になり、A1/A2 を疑う余地も広がる | 上表の必須設定の再投入が要る |
| 2 | **Memory RAS = Rank Sparing** | UCE になる**前**に閾値超えのランクを退避させる。3DPC の 32GB 2Rx4 なら 1 ランクぶんの容量減で済む | 容量が減る。Independent 以外は BIOS 側の対応可否を実機で確認する |
| 3 | **メモリ周波数を 1600 → 1333 に固定** | 3DPC で信号品質が厳しいので、マージンを稼ぐ古典的な手 | 帯域が落ちる。gpu02 は RPC ワーカーでホスト RAM 帯域は律速でないので実害は小さい |
| 4 | **`smc-fanctl` のカーブに DIMM 温度を追加** | `P1-DIMMA1/A2/A3 Temp` と `VmemABVRM Temp` を入力に加える。**現在これらは完全に無監視** | 状況により duty が上がって少し騒がしくなる |
| 5 | **duty 下限を 16% → 24% に暫定引き上げ** | 4 の実装前の即効の保険 | 2,900 → 約 4,000rpm。ユーザ確認のうえで |

施策 4 は `.claude/skills/gpu-server/fan-control/smc-fanctl.py` にセンサ名を足して
`install-fan-control.sh aws-gpu02` で再配布する（既存の導入手順をそのまま使える）。
**DIMM 温度の実測値を先に取ってから**カーブを決める（無負荷と memtest 中で比較）。

### Phase 6 — 物理作業の手順（ユーザ向け。リモートで詰まった場合のみ）

すぐには実施できないとのことなので、**手順書として残し、必要になった時点で依頼する**。

1. **DIMM 抜き差し**: `P1_DIMMA1/A2/A3` を抜いて端子を確認し、しっかり挿し直す
2. **最小構成での切り分け**: `P1_DIMMA1` **1 枚だけ**にして起動 → memtest。以後 1 枚ずつ追加。
   **gpu02 は RPC ワーカーなのでホスト RAM は 32GB でも実用上まったく困らない**
3. **CMOS クリア**: マザーボード上の **JBT1** を短絡（AC ケーブルを抜いた状態で）。
   リモートの Restore Defaults で消えない領域まで初期化できる
4. Redfish が `P2_DIMME1/E2` に 32GB を報告している件を目視で確認（本当に載っているか）

### Phase 7 — 復旧後の後始末

前回セッションの積み残しを解消する。

- **llama.cpp の再ビルド**: git は master `6a1a922d2` だが**ビルドは PR の `build 10855` のまま**。
  RPC はバージョン一致が必須なので必ず流す。**並列度を `-j40` から `-j20` に下げる**
  （ハングの 1 回は `-j40` の nvcc 中に起きている。メモリ圧を下げる意味でも）
  ```bash
  scp .claude/skills/llama-server/server-scripts/update_and_build-aws-gpu02.sh \
      aws-gpu02:~/llama.cpp/update_and_build.sh
  ssh -n aws-gpu02 "cd ~/llama.cpp && setsid nohup ./update_and_build.sh --no-pull --force \
      > /tmp/build.log 2>&1 < /dev/null &"
  ```
- ビルド後に `llama-server --version` で両機のコミット一致を確認（gpu01 は必要時のみ投入）
- ロック解放・電源はユーザの指示に従う（既定は OFF に戻す）

### Phase 8 — ドキュメント更新とレポート

**運用ルールの更新（今回の最大の教訓）**:

- `.claude/skills/gpu-server/bmc.md` に **「OS ハング調査では KVM スクショだけでなく必ず
  `ipmitool sel elist` を見る」** を追加。今回、前回レポートが「痕跡なし」と結論した原因は
  これを見ていなかったことにある
- `CLAUDE.md` の「OSクラッシュ時の証跡保全」に SEL 取得を追記
- `.claude/skills/gpu-server/aws-gpu.md` の
  **「P2-DIMME1 は空スロットで実害なし」の記述を訂正**（Redfish は実装ありと報告しており、
  実際に UCE が発生している）
- gpu02 の sudo 許可を CLAUDE.md の sudo 例外表に追記

**レポート作成**（[REPORT.md](../../projects/llm-server-ops/REPORT.md) に従う）:
`report/2026-09-05_HHMMSS_aws_gpu02_uncorrectable_ecc.md`。
Phase 1 の SEL ダンプ・Redfish JSON・KVM スクショ・memtest 結果を attachment に格納。
前回レポートの「痕跡なし」記述への追記リンクも入れる。

---

## 検証（完了判定）

| 段階 | 合格条件 |
|---|---|
| 原因の確定 | SEL の UCE とハング時刻の一致を、ダンプ付きでレポートに記録できている |
| POST | `bmc-screenshot.sh` の連続 PNG が変化し続け、108 秒前後で OS 起動 |
| OS | `ssh aws-gpu02 true` が通る / GPU 6 枚を `nvidia-smi -L` が認識 / 100GbE `192.168.100.2` が UP |
| メモリ | memtest86+ が **1 pass 以上をエラー 0 で完走**、かつ完走中に SEL へ UCE が積まれない |
| 監視 | `rasdaemon` が動いており `ras-mc-ctl --summary` が読める |
| ビルド | `~/llama.cpp/build/bin/llama-server --version` が master `6a1a922d2` を返す |
| RPC | `rpc-up.sh aws-gpu02` が起動し、gpu01 から `192.168.100.2:50052` に到達できる（gpu01 の投入可否はユーザ判断） |

**打ち切り条件**: Phase 2b を尽くしても POST が通らない場合は、そこで手を止めて物理作業の
依頼に切り替える。電源投入の繰り返しは（爆音とハード負荷の両面で）害しかない。

## リスクと扱い

| リスク | 対処 |
|---|---|
| POST が長引いてファンが爆音に戻る | `BOOT_QUIET_SECS=2400` で抑制窓を延ばす。それでも超えたら手動で `boot-quiet.sh` を再起動 |
| BIOS 初期化で MMIO/Above4G が既定に戻り起動不能 | 初期化直後に必ず上表の 4 項目を入れ直してから保存。gpu01 の OPROM 事故と同じ轍を踏まない |
| 初期化で UEFI ブート順が変わる | Setup の Boot タブで `ubuntu` を先頭に戻す。入れなければ EFI Shell から `fs0:\EFI\ubuntu\shimx64.efi` |
| memtest 中に UCE でハングする | それ自体が陽性の結果。SEL に残るので情報は失われない |
| 冷却制御を触って熱暴走 | `smc-fanctl` は duty を**上げる**方向にしか変更しない。異常時は `sudo systemctl stop smc-fanctl` で BMC の Optimal に自動復帰する |
