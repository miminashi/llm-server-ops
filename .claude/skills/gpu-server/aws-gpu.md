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
| 他ユーザ | `/home` に myzk, sizumita（**共用機**） | ubuntu のみ |

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
  センサー故障かは未確認。BMC の温度は全系統正常値。
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

## 未検証事項

- **llama-server の起動実績なし**。`start.sh` のサーバ別パラメータ
  (`--flash-attn 1 --poll 0 -b 4096 -ub 4096`) は t120h-p100（同じ P100）の実績値を
  踏襲した推定値であり、実測での検証が必要。
- **ビルド未実施**。`update_and_build-aws-gpu01.sh` / `-aws-gpu02.sh` は作成済みだが
  未実行。nvcc 12.0 と Ubuntu 24.04 の gcc の組み合わせで問題が出る可能性がある。
- `~/.ssh/config` の定義に既存 3 台にある `ServerAliveInterval 3` が無い。

## 検証済み（2026-08-16 登録時）

- ロック取得・解放（`lock.sh` / `unlock.sh` / `lock-status.sh` の全台一覧）
- BMC 電源状態の読み取り（`bmc-power.sh status` / `power-ctl.sh status` → `On`）
- **爆音ガードが実際に電源操作を止めること**（`reset` / `off` / `on` がすべて exit 20 で拒否され、
  拒否後も `System Power: on` かつ uptime 継続＝副作用ゼロを確認）
- KVM スクリーンショット（両機とも 1024x768 でログインプロンプトを取得）
