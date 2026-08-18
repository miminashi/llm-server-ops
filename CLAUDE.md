# CLAUDE.md

このファイルは、Claude Code (claude.ai/code) がこのリポジトリのコードを扱う際のガイダンスを提供します。

**応答言語**: Claudeは日本語で応答してください。

## 必読ドキュメント

- [REPORT.md](REPORT.md) — レポート作成ルール

---

## ソースコード

- llama.cpp の完全なソースツリーが `src/llama.cpp/` にある（コードリーディング用）。`.gitignore` で `src/` は git 追跡対象外。ビルドは GPU サーバ側の `~/llama.cpp/` で行う（`llama-server` スキル参照）ため、`src/` はローカル参照専用。

---

## GPUサーバとLLM

**重要**: GPUサーバを使用する場合は、**必ず Skill `gpu-server` を使用してください**。このスキルはサーバのロック管理を行い、複数のClaudeセッションが同時にサーバを使用することを防ぎます。

- GPUサーバ（mi25、t120h-p100、t120h-m10、aws-gpu01、aws-gpu02）の管理、リモートブラウザの管理に関する情報は `.claude/skills/gpu-server/` にあります。
- llama-serverの起動・管理、モデル選択に関する情報は `.claude/skills/llama-server/` にあります。

### ロックが必要なケース

| ケース | ロック必要 | 理由 |
|--------|-----------|------|
| GPUサーバでllama-serverを使用 | **必要** | 他セッションとの競合を防ぐ |
| GPUサーバでリモートブラウザを使用 | **必要** | 同上 |
| **ローカルでブラウザを実行**（CDPプロキシ経由） | 不要 | GPUサーバのリソースを使用しない |
| **読み取り専用の監視・確認**（ダウンロード進捗、VRAM確認、プロセス確認、ログ確認） | 不要 | リソースを専有しない |

**注**: ローカルでDockerコンテナのブラウザを起動し、LLMサーバのみGPUサーバを使用する場合は、LLM使用のためロックが必要です。

### クイックリファレンス

| サーバ | IPアドレス | OpenAI互換API | BMC |
|--------|-----------|---------------|-----|
| mi25 | 10.1.4.13 | `http://10.1.4.13:8000/v1` | 10.1.4.7（IPMI） |
| t120h-p100 | 10.1.4.14 | `http://10.1.4.14:8000/v1` | 10.1.4.8（iLO5） |
| aws-gpu01 | 10.8.2.1 | `http://10.8.2.1:8000/v1` | 10.11.12.1（IPMI） |
| aws-gpu02 | 10.8.2.2 | `http://10.8.2.2:8000/v1` | 10.11.12.2（IPMI） |

**aws-gpu01 / aws-gpu02（2026-08-16 追加）**: Supermicro SYS-4028GR-TRT2 / TRT。
Tesla P100 を 7 枚（112GB）/ 6 枚（88GB）搭載。**起動時にファンが爆音になるため、
ユーザの明確な指示なしにリブート・電源投入・電源断を行わないこと**（スクリプト側で
`ALLOW_FAN_NOISE=1` を要求するガードあり）。ワークステーションと同一拠点で通信が速く、
モデルは HF から直接ダウンロードするのが原則。詳細は
[gpu-server/aws-gpu.md](.claude/skills/gpu-server/aws-gpu.md)。

**ファン静音化（2026-08-17）**: 両機に温度連動デーモン `smc-fanctl` を常設し、
BMC の fan mode を **Full 固定 + duty 制御**に切り替えた（**アイドル 6,500→2,900rpm**）。
デーモンを止めると自動で BMC の Optimal 制御に戻る。**起動 (POST) 中も `bmc-power.sh` が
`boot-quiet.sh` を自動併走させることで 2,900rpm 台に収まる**（2026-08-18 のコールドブートで実測）。
ただし抑制が効かない状況では従来どおり爆音になるため、**電源操作のガードは維持する**。また **aws-gpu01 は Legacy BIOS (CSM) ブートで、
ブートディスクは SAS HBA 経由**のため、**BIOS の `CPU2 Slot6 PCI-E x16 OPROM` を Disabled にすると起動不能になる**（2026-08-18 に特定。
他の 11 スロット項目は Disabled にしても起動するが、**POST 短縮効果は 146→144 秒とほぼ無い**ので触る価値は薄い）。詳細は
[gpu-server/aws-gpu.md](.claude/skills/gpu-server/aws-gpu.md) の「ファン制御」「BIOS 設定」節と
[2026-08-17 静音化レポート](report/2026-08-17_234403_aws_gpu_fan_noise_reduction.md)、
[2026-08-18 HBA スロット特定レポート](report/2026-08-18_185344_aws_gpu01_sas_hba_slot_id.md)。

**mi25 デフォルトバックエンド**: Vulkan (RADV, 4 枚 x16GB)。
`MI25_BACKEND=hip` を明示すると ROCm fallback。詳細は
[llama-server SKILL.md](.claude/skills/llama-server/SKILL.md) の「mi25 のバックエンド切替」節、
および [2026-07-20 pp 退行レポート](report/2026-07-20_013500_mi25_prompt_eval_regression.md)。

**OSハング/クラッシュ（SSH・ping 不通）を検知したら、電源リセットの前に必ず**
`bmc-screenshot.sh`（KVM スクショ）でコンソール画面を保全すること。カーネルパニックの
スタックトレース・FS 破損・OOM などの原因究明に決定的な情報が表示されている可能性が高く、
リセットすると失われるため。保全後に `bmc-power.sh`（電源リセット）で復旧する。いずれも
`gpu-server` スキルのスクリプトで、SSH 不通でも操作可。詳細は
`.claude/skills/gpu-server/bmc.md`。

```bash
# llama-server確認
ssh t120h-p100 "ps aux | grep llama-server | grep -v grep"

# リモートブラウザ確認
ssh t120h-p100 "docker ps | grep chrome-novnc-cdp"
```

### mi25 GPU 個体識別 (Unique ID 必須)

mi25 (MI25 4枚) では `rocm-smi -i` が表示する **GUID は KFD ランタイム割当値で個体不変ではない**。過去のレポート群で「GUID 8820 / 54068 / 33301 / 29525」と呼んでいたものは、その当時の 4 枚同時運用セッション内でのみ有効。物理交換・スロット入れ替え・単独可視化で値が変わる (実例: 別個体カードを単独装着すると両方とも GUID 54068 を返した)。

カード個体不変の識別子は `rocm-smi --showuniqueid` の **Unique ID** (例: `0x21501edbcec48c4`)。ASIC 内部に焼き込まれた値で、構成変更でも変わらない。

**運用ルール**:
- 認識確認では必ず `rocm-smi --showuniqueid` を併記して記録 (`boot_state.log` 等)
- レポート/メモリで「カード」を指すときは Unique ID **末尾 5 桁** で略記 (例: `card-c48c4`)。2026-06-29 の 4 枚 baseline で末尾 4 桁では `48c4` が `card-c48c4` / `card-448c4` で衝突することが判明したため。衝突した場合は 6 桁以上に拡張
- 過去レポートの「GUID xxxxx」は当時のセッション値として読み替える (新たに使わない)。本日の 4 枚 baseline で過去 fault 集中個体 (4 枚運用時 BDF 87:00.0 = GUID 8820) = **`card-c48c4` (Unique ID `0x21501edbcec48c4`)** と確定
- 物理スワップ前後で Unique ID で必ず照合 (BDF / GUID では追跡不能)

**SMBIOS スロット ↔ GPU BDF**:
- `sudo dmidecode -t 9` の `Bus Address` は MI25 内蔵 upstream bridge の bus 番号 (GPU 本体 BDF ではない)
- 正しい SLOT↔GPU BDF マッピングは `lspci -tnnv` で PCIe tree を辿る
- 例: SMBIOS CPU2 SLOT6 = `85:00.0` (upstream) → `86:00.0` (downstream) → `87:00.0` (GPU 本体) / CPU2 SLOT8 = `82:00.0` → `83:00.0` → `84:00.0`

詳細経緯は [report/2026-06-29_191721_mi25_gpu_card_id_unique_id.md](report/2026-06-29_191721_mi25_gpu_card_id_unique_id.md) と続編 [report/2026-06-29_213624_mi25_4card_uniqueid_baseline.md](report/2026-06-29_213624_mi25_4card_uniqueid_baseline.md) (4 枚 baseline 取得 + 過去 fault 個体 = `card-c48c4` 確定) を参照。

### ネットワーク構成 (重要)

**サーバによって前提がまったく異なる**ので、どちらのグループかを必ず確認すること。

**(a) t120h-p100 / mi25 / t120h-m10 — 別拠点（遅い）**

ワークステーション（現在の作業マシン）とは**同一 IP セグメントだが物理的には別拠点**に設置されている。そのため:

- **WS ↔ GPU マシン間の通信は遅い**（1 MB/s 程度まで落ちることもある）。大きなファイルの `scp` / `rsync` は時間がかかる前提で計画すること。
- **GPU マシンから HuggingFace への直接アクセスはさらに遅い**。GPU マシン上で直接 `hf download` / `curl` するのは避ける。

**(b) aws-gpu01 / aws-gpu02 — 同一拠点（速い）**

ワークステーションと**同じ拠点**にあり、上記の制約は当てはまらない（2026-08-16 実測）:

| 経路 | aws-gpu01 | aws-gpu02 |
|---|---|---|
| WS からの RTT | 0.3 ms | 0.3 ms |
| WS ↔ サーバ帯域 | 約 100 MB/s | 約 99 MB/s |
| サーバ → HuggingFace | 27 MB/s | 37 MB/s |
| WS → HuggingFace（参考） | 18 MB/s | 18 MB/s |

**サーバから HF を直接叩くほうが WS 経由より速い**ため、モデル取得は直接ダウンロードが原則（下記参照）。

### モデルダウンロード (HuggingFace)

- **aws-gpu01 / aws-gpu02 は例外: サーバから直接ダウンロードする**（2026-08-16 実測で HF 直が 27〜37 MB/s、WS 経由 18 MB/s より速いため）。下記の 2 段階ルールは適用しない。
  ```bash
  source ~/.config/gpu-server/.env
  ssh aws-gpu01 "~/.local/bin/hf download <repo> --include '*Q4_K_M*.gguf' --token $HF_TOKEN"
  ```
  aws-gpu02 には `hf` CLI が未導入なので、初回は `pip install --user huggingface_hub` 等で導入が要る。
- **原則（t120h-p100 / mi25 / t120h-m10）: 2 段階で取得する**
  1. **まずワークステーション（現在のマシン）にダウンロード**する（HF への回線が最も速いのは WS）。
  2. その後 **GPU マシンへ転送**する（`scp` / `rsync`）。
  - GPU マシンから HF へ直接ダウンロードしない。WS→GPU 転送も遅い（上記「ネットワーク構成」参照）ので、レジューム可能な手段（`rsync --partial --progress` や `scp` の再実行）を使い、転送に長時間かかることを織り込んでおくこと。
  - WS のディスク空き容量を事前に確認する（大きな GGUF は数十 GB になる）。転送・検証完了後は WS 側の一時ファイルを削除してよい。
  - 転送後は `stat -c %s` で WS 側と GPU マシン側のサイズ一致を確認する（期待サイズは HF API `https://huggingface.co/api/models/<repo>/tree/main` からも取得可）。
- **HF トークン**: `~/.config/gpu-server/.env` の `HF_TOKEN` を利用。匿名ダウンロードは CDN 側で厳しく rate limit されるため、モデル取得時は**必ずトークン付き**で実行する。`llama-server/scripts/start.sh` も同じ `.env` を参照している。
- **参考: P100 (t120h-p100) の Xet ストレージ問題** (2026-07-19 判明) — 上記の原則どおり WS 経由で取得すれば回避できる。GPU マシンから直接落とさざるを得ない場合の記録として残す。P100 から HuggingFace の Xet バックエンド (`cas-bridge.xethub.hf.co`) への直接ダウンロードは不安定。
  - `hf CLI` (+ `hf_transfer`) は adaptive concurrency が bandwidth を誤判定 (64 KB/s) で張り付き実質停止
  - `huggingface.co/<repo>/resolve/main/<file>` の GET が途中で固まる (HEAD は 200 で通る、TCP:443 も通る)
  - **迂回策**: ワークステーション側で signed URL (Xet CDN の presigned URL) を pre-resolve → P100 で `curl -C -` によるレジューム型ダウンロード。実測 5-9 MB/s。ただし 15-30 分程度で突然切断されることが多いので、**切断時に signed URL を取り直して再開する resilience loop が必須**
    ```bash
    source ~/.config/gpu-server/.env
    URL=$(curl -sI -H "Authorization: Bearer $HF_TOKEN" -o /dev/null -w '%{redirect_url}' \
      --max-time 15 https://huggingface.co/<repo>/resolve/main/<file>)
    echo "$URL" > /tmp/url.txt && scp /tmp/url.txt t120h-p100:/tmp/url.txt
    ssh t120h-p100 "curl -C - --max-time 3300 -o ~/models/<file>.part \"\$(cat /tmp/url.txt)\""
    # 上記を while ループで囲み、期限 1h の URL を都度再取得
    ```
  - 転送完了後は `.part` を `.gguf` にリネームし、`stat -c %s` で HF API の期待サイズ (`https://huggingface.co/api/models/<repo>/tree/main` から取得) と一致することを確認する

---

## リポジトリ運用

### 添付ファイルは Git LFS を使わない

`report/attachment/` 配下のログは **LFS に載せず通常の git 管理**とする。2026-07-19 に一度 LFS を導入したが、2026-08-16 に廃止した。

理由は **LFS が中身を無圧縮のまま保存する**こと。添付は反復の多いテキストログで zlib が非常によく効くため、通常の git のほうが圧倒的に小さい。

| ファイル | 実サイズ | 通常 git | LFS |
|---|---|---|---|
| `telemetry_rocmsmi.log` (24h) | 66.6 MB | **0.8 MB** (1.3%) | 66.6 MB |
| `journal_p140W.txt` | 30.0 MB | **2.1 MB** (7.0%) | 30.0 MB |

LFS に載せると GitHub の無料枠 1 GB を生バイトで食い潰すだけで、容量的に不利になる。添付は合計 828 MB あるが `.git/objects` は全履歴込みで 414 MB に収まっている。

**PNG や `.gz` など既に圧縮済みのファイルも LFS には載せない**（最大 9.7 MB で問題にならないため）。

> `.gitattributes` は**パス一致でしか書けず「この日以降に追加した分だけ」という時間条件は表現できない**。そのため過去にコミット済みのファイルまで LFS 化しようとして 5090 件が常時 "変更あり" になる事故が起きた。同じ理由で「将来分のみ LFS」は実現不可能なので、再導入を検討しないこと。

### 巨大ファイル検出 hook

GitHub は **100 MiB を超えるファイルの push を拒否**し、50 MiB で警告を出す。これを commit 時点で止めるため `.githooks/pre-commit` を置いている。

**clone 直後に有効化が必要**（`core.hooksPath` はリポジトリに保存されないため）:

```bash
git config core.hooksPath .githooks
```

24h のテレメトリログが約 67 MB なので、**48h 相当を素で置くと 100 MB 上限を超える**。長時間ログは `gzip` してから添付すること。意図的に通す場合のみ `git commit --no-verify`。

---

## 重要な制約

| 制約 | 説明 |
|------|------|
| GPUサーバ使用 | **必ず Skill `gpu-server` を使用**（ロック管理のため） |
| スクリプト実行 | **プロジェクトルートからの相対パス**（`.claude/skills/...`）で実行すること。フルパス（`/home/ubuntu/projects/...`）は使用しない |
| レポート作成 | plan mode で計画を立ててまとまった作業を行った場合は、完了時に**必ず**対になるレポートを作成すること（ユーザから明示的に不要と指示された場合を除く）。フォーマット・必須セクション（**概要**必須ほか）は [REPORT.md](REPORT.md) に従う |
| sudo実行 | **原則 Claudeはsudoを直接実行しない**。sudo権限が必要な操作が発生した場合は、コマンドをユーザに提示して実行を依頼すること（sshリモート先のsudoも同様）。**例外**: mi25 では `sudo dmidecode`（GPU SMBIOS スロット番号確認等の読み出し用途）は Claude が直接実行してよい（NOPASSWD 設定済み・副作用なし） |
| OSクラッシュ時の証跡保全 | OSハング/クラッシュ（SSH・ping不通）検知時は、**電源リセットの前に必ず** `bmc-screenshot.sh` で KVM スクショを取得すること（コンソールに原因究明の情報が残るため）。詳細は「GPUサーバとLLM」節 |
| aws-gpu01 の他ユーザデータ | `/home/myzk` `/home/sizumita` は**現在未使用だがデータを削除しない**。ディスクを空ける場合も自分（`ubuntu`）の `~/models` / `~/.cache/huggingface` に留めること |
| aws-gpu01/02 の電源操作 | **ユーザの明確な指示なしにリブート・電源投入・電源断を行わない**（起動時にファンが爆音になるため）。`bmc-power.sh` の `on`/`off`/`soft`/`reset`/`cycle` と `power-ctl.sh` の `on`/`off` は `ALLOW_FAN_NOISE=1` が無いと exit 20 で拒否される。`status` とスクショは常に可。詳細は [gpu-server/aws-gpu.md](.claude/skills/gpu-server/aws-gpu.md) |
| 添付ファイルと LFS | `report/attachment/` 配下は **Git LFS を使わず通常の git 管理**とする（テキストログは zlib で 1〜7% に縮むが LFS は無圧縮保存のため無料枠に不利）。**LFS の再導入は検討しない**。clone 直後に `git config core.hooksPath .githooks` で巨大ファイル検出 hook を有効化すること。100 MB 超は GitHub が push を拒否するため長時間ログは `gzip` する。詳細は「リポジトリ運用」節 |
| モデルダウンロード | **必ずワークステーション（現在のマシン）に先にダウンロードし、その後 GPU マシンへ転送する**。GPU マシンから HF への直接ダウンロードはしない。HF トークンは `~/.config/gpu-server/.env` の `HF_TOKEN` を使う。詳細は「モデルダウンロード」節 |
| 拠点間通信の遅さ | WS と GPU マシン（p100 / mi25）は同一 IP セグメントだが**物理的に別拠点**で、通信が遅い（1 MB/s 程度まで落ちることもある）。GPU マシンから HF への直接アクセスはさらに遅い。大容量転送は長時間かかる前提で計画すること。詳細は「ネットワーク構成」節 |
