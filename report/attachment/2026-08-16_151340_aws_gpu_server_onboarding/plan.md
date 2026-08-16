# aws-gpu01 / aws-gpu02 を管理対象 GPU サーバへ追加

## Context

現在このリポジトリが管理する GPU サーバは `mi25` / `t120h-p100` / `t120h-m10` の 3 台で、
サーバ名は `lock.sh` などのホワイトリスト、`power-ctl.sh` の `server_type()`、`start.sh` の
case 分岐といった**複数箇所にハードコード**されている。新たに 2 台（`aws-gpu01` /
`aws-gpu02`、いずれも Supermicro）が使えるようになったため、これらを既存の運用基盤
（排他ロック・BMC 電源制御・KVM スクショ・llama-server 起動）に載せる。

本セッションでハードウェア詳細は BMC/OS から実測取得済み（下記）。**両機は起動時にファンが
爆音になるため、ユーザの明確な指示なしにリブート・電源投入を行わない**。この制約はドキュメント
記載だけでなくスクリプト側のガードとして実装する。

## 実測で確定したハードウェア情報

| 項目 | aws-gpu01 | aws-gpu02 |
|---|---|---|
| 製品型番 | **SYS-4028GR-TRT2** | **SYS-4028GR-TRT** |
| M/B | X10DRG-OT+-CPU (BMC Product Name: X10DRG-O+-CPU) | 同左 |
| シャーシ | CSE-418GTS-R4000BP | CSE-418GTS-R3200BP |
| 製品シリアル | S240241X8731725 | S188918X6107112 |
| GPU | Tesla P100-PCIE **16GB × 7 = 112GB** | 16GB × 4 + **12GB × 2** = 88GB |
| GPU BDF | 05,07,08,0C,0D,0E,0F | 05,08,09,84,88,89 |
| CPU | Xeon E5-2687W v4 ×2 (24C/48T, 3.0GHz) | Xeon E5-2640 v4 ×2 (20C/40T, 2.4GHz) |
| RAM | 157 GiB | 94 GiB |
| ディスク空き | 707 GB (/ 1.1T) | 141 GB (/ 457G) |
| OS / driver / CUDA | Ubuntu 24.04.3 / 535.288.01 / nvcc 12.0 | 同左 |
| PCIe リンク | 全 GPU Gen3 x16 | 全 GPU Gen3 x16 |
| BMC | ASPEED, FW 3.86, IPMI 2.0 + **Redfish 可** | 同左 |
| SSH ホスト名 | `chungpu`（`aws-gpu01` とは別名） | `gpu02` |
| SSH ユーザ | **`ubuntu`**（既存 3 台は `llm`） | 同左 |
| sudo | **NOPASSWD で root 取得可** | 同左 |
| llama.cpp | **未導入** | ビルド済（`971facc38`、CUDA backend） |
| ツール | ttyd ✓ / nvtop ✓ / cmake ✓ / ninja ✓ / `~/.local/bin/hf` ✓ / docker ✗ / uv ✗ | ttyd ✓ / nvtop ✓ / cmake ✓ / ninja ✗ / hf ✗ / docker ✗ / uv ✗ |
| 他ユーザ | `/home` に myzk, sizumita（**共用機**） | ubuntu のみ |

**注意すべき個体差**

- aws-gpu01: GPU0 (05:00.0) と GPU5 (0E:00.0) のみ **ECC Disabled**（他 5 枚は Enabled）
- aws-gpu01: SEL に 2026-02-23 の **PSU 故障イベント**履歴（現在 PS1-4 すべて `ok`）
- aws-gpu02: **FAN7 が `No Reading` (ns)**（他 7 個は 4700-5200 RPM で正常）
- aws-gpu02: P100 **12GB 版が 2 枚混在** — `--tensor-split` 前提の均等分割は不可

**ネットワーク（既存 3 台との決定的な差）**

ユーザ確認済みのとおり、両機は **WS（このマシン）と同一拠点**にある。実測でも裏付けられた:

| 経路 | aws-gpu01/02 | 既存 mi25 / t120h-p100 |
|---|---|---|
| WS からの RTT | **0.3 ms** | ping 不通（別拠点） |
| WS ↔ サーバ帯域 | **約 100 MB/s** | 1 MB/s まで落ちることあり |
| サーバ → HuggingFace | **27 MB/s (01) / 37 MB/s (02)** | P100 は Xet 経由が不安定で迂回策が必要 |
| WS → HuggingFace | 18 MB/s（参考） | 同左 |

→ **新 2 台は HF 直接ダウンロードのほうが WS 経由より速い**ため、CLAUDE.md の
「必ず WS 経由」ルールの明示的な例外とする（ユーザ選択済み）。

## 作業スコープ

**やること**: スキルへの登録、BMC 認証情報登録、ロック機構への追加、電源ガード実装、
ドキュメント更新、read-only の疎通確認、レポート作成。

**やらないこと**: llama.cpp のビルド、llama-server の起動、ベンチマーク、リモートブラウザ整備、
**あらゆる電源操作（リブート・電源投入・電源断）**。

サーバ選択優先順位は既存（t120h-p100 → mi25 → t120h-m10）を維持し、新 2 台は末尾に追加する
（ユーザ選択済み）。

---

## Phase 1: 電源ガードの実装（最優先）

爆音制約を仕組みで担保する。他の変更より先に入れることで、以降の作業中の事故も防ぐ。

### `.claude/skills/gpu-server/scripts/bmc-power.sh`

- ファイル冒頭に `FAN_LOUD_SERVERS="aws-gpu01 aws-gpu02"` を定義
- 引数パース後・ipmitool 実行前に `guard_fan_noise()` を挿入:
  - 対象サーバが `FAN_LOUD_SERVERS` に含まれ、かつアクションが
    `on` / `reset` / `cycle` / `off` / `soft` のいずれかなら、
    環境変数 **`ALLOW_FAN_NOISE=1`** が無い限り **exit 20** で拒否
  - 拒否時のメッセージに「起動時にファンが爆音になるためユーザの明示指示が必要」
    「意図的に実行する場合は `ALLOW_FAN_NOISE=1 ...` を付ける」を出力
  - `status` はガード対象外（読み取りのため）
- `off` / `soft` もガードするのは、一度落とすと**復帰に必ず爆音を伴う電源投入が要る**ため
- 終了コード 20 は既存（0/1/2/3/10）と衝突しない新規採番。ファイル冒頭のコメントに追記

### `.claude/skills/gpu-server/scripts/power-ctl.sh`

- `server_type()` の case に `aws-gpu01) / aws-gpu02) echo "supermicro"` を追加
  （**必須**。デフォルトが `*)→hpe` のため、無いと `power.sh`(Redfish/iLO5) に落ちて破綻する）
- `bmc-power.sh` へ委譲する前に同じ `FAN_LOUD_SERVERS` チェックを二重に入れる
  （`llama-up.sh` は `power-ctl.sh on` を経由するので、ここで自動的に止まる）

---

## Phase 2: gpu-server スキルへの登録

| ファイル | 変更内容 |
|---|---|
| `scripts/lock.sh:23` | `VALID_SERVERS` に `aws-gpu01 aws-gpu02` を追加（usage 文言も更新） |
| `scripts/unlock.sh:23` | 同上 |
| `scripts/lock-status.sh:19` | 同上（引数なし実行時の全台一覧に自動反映される） |
| `scripts/bmc-setup.sh:27-33` | `default_bmc_ip()` に `aws-gpu01) 10.11.12.1` / `aws-gpu02) 10.11.12.2` |
| `scripts/transfer-file.sh:36-45` | src/dst ホワイトリストに 2 台追加（既存機からのモデル移送に使えるため入れる） |

`bmc-power.sh` / `bmc-screenshot.sh` / `bmc-kvm.py` は `BMC_<SERVER>_HOST/USER/PASS` を
`tr '[:lower:]-' '[:upper:]_'` で解決する設計なので**サーバ名のコード変更は不要**
（`aws-gpu01` → `BMC_AWS_GPU01_*`）。

### 認証情報の登録（コマンド実行）

```bash
.claude/skills/gpu-server/scripts/bmc-setup.sh aws-gpu01 10.11.12.1 claude Claude123
.claude/skills/gpu-server/scripts/bmc-setup.sh aws-gpu02 10.11.12.2 claude Claude123
```

`~/.config/gpu-server/.env`（chmod 600・gitignore 済）に保存される。手編集はしない。

---

## Phase 3: llama-server スキルへの登録（コードのみ・起動しない）

今回は起動しないが、登録しないと `start.sh` が exit 1 で弾くため、次セッションで使えるよう
コード側だけ整える。**すべて未実行・未検証である旨をドキュメントに明記する。**

| ファイル | 変更内容 |
|---|---|
| `scripts/start.sh:135-142` | サーバ名 case に `aws-gpu01\|aws-gpu02` を追加 |
| `scripts/start.sh:205-282` | `aws-gpu01)` / `aws-gpu02)` の `SERVER_OPTS` 分岐を追加。P100 なので `t120h-p100` の実績値 `--flash-attn 1 --poll 0 -b 4096 -ub 4096` を踏襲し、`warn_gpu_degraded "$SERVER" "$CNT" 7`（01）/ `6`（02）で枚数チェック |
| `scripts/start.sh:345-378` | **`/home/llm/.local/bin/hf` のハードコードを一般化**。`command -v hf` → `~/.local/bin/hf` → `/home/llm/.local/bin/hf` の順に解決するヘルパへ置き換え（既存 3 台は最後の fallback で従来どおり動く） |
| `scripts/stop.sh:29-36` | case に 2 台追加 |
| `scripts/ttyd-up.sh:29-35` | case に 2 台追加（GPU 監視は NVIDIA なので `*)` の nvtop で自動対応・両機に nvtop 導入済み） |
| `scripts/ttyd-gpu.sh:18-24` | case に 2 台追加 |
| **新規** `server-scripts/update_and_build-aws-gpu01.sh` | `update_and_build-t120h-p100.sh` を雛形に作成（`start.sh:191` がファイル名完全一致を要求）。P100 = sm60 なので `-DCMAKE_CUDA_ARCHITECTURES=60`、nvcc は 12.0（p100 用の 12.9 パス直書きは使わない） |
| **新規** `server-scripts/update_and_build-aws-gpu02.sh` | 同上。**ninja 未導入**のため生成前に `-G Ninja` を使わないか、導入手順をコメントで明記 |
| `scripts/setup-llama-cpp.sh:26-64` | `aws-gpu01) / aws-gpu02)` の `GPU_TYPE=cuda` + `BUILD_SCRIPT` 分岐を追加（次セッションでビルドする際の入口） |

**aws-gpu02 の tensor-split 注意**: 16GB×4 + 12GB×2 の非均等構成なので、既存の
`--tensor-split 11,12,13,14` 系プロファイルはそのまま使えない。SKILL.md にその旨を注記する。

---

## Phase 4: ドキュメント更新

| ファイル | 変更内容 |
|---|---|
| **新規** `.claude/skills/gpu-server/aws-gpu.md` | 本プランの「実測で確定したハードウェア情報」を移植した機種別リファレンス。型番・GPU 構成・シリアル・ECC/FAN7/PSU の個体差・GPU シリアル baseline・ネットワーク実測値・ツール導入状況・共用ユーザ・**爆音制約と `ALLOW_FAN_NOISE` の使い方**を記載 |
| `gpu-server/SKILL.md:3` | frontmatter description のサーバ名列挙に 2 台追加（**Skill 起動判定に使われる**） |
| `gpu-server/SKILL.md:16-20` | サーバ一覧表に 2 行（GPU/枚数/VRAM/プラットフォーム/IP） |
| `gpu-server/SKILL.md:44-48` | エンドポイント表に 2 行（`http://10.8.2.1:8000/v1` / `10.8.2.2`） |
| `gpu-server/SKILL.md:74-86` | サーバ選択方針: 既存順位を維持し、新 2 台を末尾に。**電源 OFF なら選ばない**（爆音のため起動できない）ことを明記 |
| `gpu-server/SKILL.md:144-152` | BMC 一覧表に 2 行（IPMI / `bmc-power.sh`）＋ `aws-gpu.md` へのリンク |
| `gpu-server/SKILL.md:183-186` | lock/unlock 例のサーバ名列挙 |
| `gpu-server/bmc.md:15-18` | 機種別トランスポート表に Supermicro 2 行。**両機は Redfish も応答するが、既存 Supermicro 運用と揃えて IPMI を正とする**旨を注記（mi25 の DCMS ライセンス問題との差分として記録） |
| `gpu-server/bmc.md:31-42` | `bmc-setup.sh aws-gpu01 10.11.12.1 ...` の例を追記 |
| `gpu-server/lock.md:40,65,100-106` | 有効サーバ名の列挙を 5 台に |
| `gpu-server/scripts/install-global.sh:86` | plugin.json description のサーバ名列挙（SKILL.md:3 と同文言） |
| `llama-server/SKILL.md:285-293` | サーバ別最適化パラメータ表に 2 行（**未検証**と明記） |
| `llama-server/SKILL.md:348-364` | プロセス確認・VRAM 確認の ssh 例に 2 台分 |
| `llama-server/server-scripts/README.md:16-21` | ビルドスクリプト一覧表に 2 行 |
| `CLAUDE.md:23` | gpu-server スキル説明のサーバ名列挙 |
| `CLAUDE.md:39-42` | クイックリファレンス表に 2 行（IP / API / BMC 10.11.12.1・.2 IPMI） |
| `CLAUDE.md:83-88`「ネットワーク構成」 | **aws-gpu01/02 は WS と同一拠点で高速**（0.3ms / 100MB/s）である旨を追記し、別拠点の注意は既存 3 台に限る記述へ修正 |
| `CLAUDE.md:90-112`「モデルダウンロード」 | **aws-gpu01/02 は HF 直接ダウンロードを原則**とする例外を明記（実測値付き）。既存 3 台の WS 経由ルールは維持 |
| `CLAUDE.md` 重要な制約表 | 「**aws-gpu01/02 の電源操作**: ユーザの明示指示なしにリブート・電源投入・電源断を行わない。スクリプトは `ALLOW_FAN_NOISE=1` 必須」の行を追加 |

---

## Phase 5: 疎通確認（read-only + ロックのみ）

電源に触れない範囲で、登録が実際に機能することを確認する。

```bash
# 1. ロック機構（5 台表示 → 取得 → 解放）
.claude/skills/gpu-server/scripts/lock-status.sh
.claude/skills/gpu-server/scripts/lock.sh aws-gpu01
.claude/skills/gpu-server/scripts/lock-status.sh aws-gpu01
.claude/skills/gpu-server/scripts/unlock.sh aws-gpu01
# aws-gpu02 も同様

# 2. BMC 電源状態の読み取り（ガード対象外なので通るはず → On）
.claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 status
.claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu02 status
.claude/skills/gpu-server/scripts/power-ctl.sh aws-gpu01 status   # → "On"

# 3. 電源ガードが効くことの確認（★重要: 実際にはリセットされないことを確認する）
.claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 reset ; echo "exit=$?"   # → exit 20 で拒否
.claude/skills/gpu-server/scripts/power-ctl.sh aws-gpu01 on     ; echo "exit=$?"   # → exit 20 で拒否
# 拒否後に status が On のままであることを再確認して副作用ゼロを裏取り

# 4. KVM スクリーンショット（BMC ログインのみ・電源に影響しない）
.claude/skills/gpu-server/scripts/bmc-screenshot.sh aws-gpu01 /tmp/aws-gpu01.png
.claude/skills/gpu-server/scripts/bmc-screenshot.sh aws-gpu02 /tmp/aws-gpu02.png
# X10 世代なので bmc-kvm.py の 2D noVNC canvas 経路がそのまま通る見込み。
# 黒画になる場合は bmc.md:122-125 のトラブルシュートに従い、結果を aws-gpu.md に記録

# 5. 変更したスクリプトの構文チェック（起動はしない）
bash -n .claude/skills/llama-server/scripts/start.sh
bash -n .claude/skills/gpu-server/scripts/bmc-power.sh
bash -n .claude/skills/gpu-server/scripts/power-ctl.sh
```

`start.sh` / `llama-up.sh` は**実行しない**（llama-server が起動してしまうため）。
サーバ名バリデーションを通ることは case 文の目視と `bash -n` で担保する。

---

## Phase 6: レポート作成

REPORT.md に従い `report/yyyy-mm-dd_hhmmss_aws_gpu_server_onboarding.md` を作成する。

- ファイル名の時刻は `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得
- タイトルは 50 字以内（例: `aws-gpu01/02 を管理対象に追加 — P100 7枚/6枚の Supermicro 2 台`）
- `## 概要` を必須で先頭に（通読できる平易な日本語、5〜8 段落）
- `## 環境情報` に本プランのハードウェア表を転記
- `## 核心発見サマリ` に「同一拠点で HF 直取得が WS 経由より速い」「Redfish が使える
  （mi25 と異なる）」「aws-gpu01 の ECC 不揃い・aws-gpu02 の FAN7 無反応」を数値付きで
  （実測ログのみで PNG は生成しない＝時系列データがないため）
- `## 添付ファイル` に本プランを `attachment/<レポート名>/plan.md` としてコピーしてリンク、
  KVM スクショ PNG も添付
- `report/INDEX.md` に 1 行追記
- コミットは行うが push はユーザ指示があるまで行わない

---

## リスクと留意点

- **爆音制約**: 本作業では一切の電源操作を行わない。ガードの動作確認 (Phase 5-3) は
  「拒否されること」の確認であり、電源に触れない。
- **aws-gpu01 は共用機**（`/home` に他ユーザ 2 名）。ロック機構への登録が特に重要。
- **llama-server 関連は未検証コード**として入る。次セッションでビルド・起動する際に
  `-ub 4096` の妥当性、aws-gpu02 の非均等 VRAM に対する tensor-split を実測で詰める必要がある。
- `~/.ssh/config` の aws-gpu 定義には既存 3 台にある `ServerAliveInterval 3` が無い。
  長時間 SSH セッションが切れやすい可能性があるが、**ユーザ環境のファイルなので今回は変更せず**、
  レポートの残課題に記載する。
