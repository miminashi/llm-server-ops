# aws-v100 を GPU サーバとして登録する

## Context

`ssh aws-v100` で入れる V100 機を、gpu-server / llama-server スキルと CLAUDE.md の管理対象に加える。
ロックと `start.sh` 系スクリプトを他の 5 台と同じように使える状態にするのが目的。
ユーザ指示: **範囲はスクリプトまで全部**、**手動起動の既存 llama-server は停止してよい**。

### 調査で分かった事実（2026-09-23、読み取り専用で確認）

| 項目 | 値 |
|---|---|
| ホスト名 / IP | `v100` / `10.22.5.2`（ssh config の `aws-v100`）、別 NIC で 192.168.39.119 |
| WS からの RTT | 0.3 ms → aws-gpu01/02 と**同一拠点**（グループ (b)） |
| マザーボード / CPU / RAM | ASRock **X99 Taichi**（民生品、**BMC なし**）/ i7-6800K 12 スレッド / 31 GiB |
| GPU | **Tesla V100-SXM2-16GB ×2**（sm_70）。SXM2→PCIe 変換で **NVLink は非活性**、topo は PHB |
| GPU のリンク | GPU0 = **Gen3 x8**（00:02.0 配下）、GPU1 = **Gen2 x8**（00:03.0 配下。速度が落ちている） |
| ドライバ / CUDA | 580.65.06 / `/usr/local/cuda-12.9`（PATH 上に nvcc は無い） |
| OS | Ubuntu 24.04.3、kernel 6.8.0-106 |
| sudo | パスワードが要る（Claude は実行しない） |
| docker | 導入済みだが ubuntu は docker グループ外 |
| llama.cpp | `~/llama.cpp` は 56381e4（9/12）、`build/` は既に sm_70 でビルド済み。`update_and_build.sh` は無い |
| 既存 llama-server | PID 11254（`~/qwen-v100.pid`）、`~/qwen-v100-run` で起動、**ポート 8080**、Huihui-Qwen3.8-27B UD-Q4_K_XL + mmproj、ctx 16384 |
| モデル | `~/models/huihui-qwen3.8-27b`（18G）、`~/.cache/huggingface`（5.9G + その他で .cache 全体 13G）、`~/.venv` 8G |

### 見つかった問題（登録作業を妨げる）

1. **ルートが 100% 使用済み（空き 109 MB）**。このままではビルド（`rm -rf build` のあと約 650 MB 必要）もモデル取得もできない。
2. 原因の大半は **`/var/log` の 18 GB**（syslog / kern.log 各約 3 GB ×2 世代、dmesg 1.3 GB、journal 4 GB）。
   中身は **root port `00:03.0`（GPU1 の上流）の PCIe AER Correctable `RxErr`（Physical Layer）の洪水**で、2.5 日で約 2.8 GB 出ている。
   GPU1 が Gen2 に落ちているのと同じ原因（変換基板・ライザーの信号品質）と見られる。

## 実装手順

### Step 0: 前提の復旧（sudo が要るのでユーザに実行を依頼する）

ユーザに次のコマンドを提示して実行してもらう。
```bash
ssh -t aws-v100 'sudo truncate -s 0 /var/log/syslog /var/log/kern.log /var/log/dmesg \
  && sudo rm -f /var/log/syslog.1 /var/log/kern.log.1 \
  && sudo journalctl --vacuum-size=200M'
```
再発防止策として、Correctable AER だけを黙らせる案も併せて提示する（採否はユーザが決める）。
- 案 A: `/etc/default/grub` の `GRUB_CMDLINE_LINUX_DEFAULT` に `pci=noaer` を追加し、`update-grub` のあとリブートする（リブートにはユーザの指示が要る）
- 案 B: rsyslog で `RxErr` / `AER: Correctable` を捨てるフィルタを入れる（リブート不要）

どちらを選ぶかは Step 0 の実行時に聞く。空き容量が 5 GB 以上あることを `df -h /` で確認してから次へ進む。

### Step 1: 既存 llama-server の停止（ユーザ承認済み）

`ssh aws-v100 'kill $(cat ~/qwen-v100.pid)'` → `ss -ltnp` で 8080 が閉じたことと、`nvidia-smi` で VRAM が空いたことを確認する。
`~/qwen-v100-run` と `~/models` は**削除しない**。tmux の `default` セッションにも触らない。

### Step 2: スクリプトのサーバ名リストに `aws-v100` を足す

サーバ名の列挙を 1 か所ずつ `aws-v100` まで広げる（`VALID_SERVERS=`、`case` の許可パターン、usage 文字列）。
- `.claude/skills/gpu-server/scripts/lock.sh`, `unlock.sh`, `lock-status.sh`（`VALID_SERVERS`）
- `.claude/skills/gpu-server/scripts/transfer-file.sh`（L16-18 usage、L38 case）
- `.claude/skills/gpu-server/scripts/install-global.sh`（L86 description）
- `.claude/skills/llama-server/scripts/stop.sh`, `start.sh`（L136-139 の許可リスト、L72 の usage）, `ttyd-gpu.sh`, `ttyd-up.sh`, `wait-ready.sh`（usage）
- `llama-up.sh` / `llama-down.sh` は RPC の分岐以外は素通りのはずなので、読んで確認だけする

### Step 3: サーバ別の分岐を追加

- **`start.sh`**: `aws-gpu02)` の後ろに `aws-v100)` の分岐を追加する。
  `SERVER_OPTS="--flash-attn 1 --poll 0 -b 4096 -ub 4096"` とし、`nvidia-smi` で数えた枚数を `warn_gpu_degraded "$SERVER" ... 2` に渡す（aws-gpu01 分岐と同じ書き方）。
  コメントには V100 SXM2 ×2 / sm_70 / NVLink 非活性 / GPU1 が Gen2 x8 / ub は初回起動で VRAM を見て調整する、を書く。
- **`setup-llama-cpp.sh`**: `aws-v100)` の分岐を足す。`GPU_TYPE=cuda`、`-DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.9/bin/nvcc -DCMAKE_CUDA_ARCHITECTURES=70`。
- **新規 `.claude/skills/llama-server/server-scripts/update_and_build-aws-v100.sh`**: `update_and_build-t120h-p100.sh`（cuda-12.9 を使っている）を下敷きにして arch を 70 にする。RPC ワーカーではないので `-DGGML_RPC` と `--no-pull` は入れない。`server-scripts/README.md` の表にも 1 行足す。
- **`power-ctl.sh`**: `server_type` に `aws-v100) echo "none"` を足し、`none` のときは「BMC なし（民生マザーボード）のため電源制御できない」と表示して exit 2 する。今のままだと既定の `hpe` に落ちて、紛らわしいエラーになるため。

### Step 4: ドキュメントに追記

- **`.claude/skills/gpu-server/SKILL.md`**: description、「利用可能なGPUサーバ」表、`aws-v100` の注意事項（BMC なし＝ハングしたら現地で対応、sudo は要パスワード、AER の洪水と Gen2 への速度低下、NVLink 非活性、単体運用）、エンドポイント表（`http://10.22.5.2:8000/v1`、リモートブラウザは未整備）、`ssh -G`、ロック例、BMC 一覧（「なし」）
- **`.claude/skills/llama-server/SKILL.md`**: サーバ別最適化パラメータの表、起動前確認・VRAM 確認のコマンド例
- **`CLAUDE.md`**: GPU サーバの列挙、クイックリファレンス表、ネットワーク構成のグループ (b)（RTT のみ実測。HF 帯域は未測定と書く）、モデルダウンロード節（HF から直接取る扱い。`hf` CLI の有無は確認して書く）、BMC なしなので電源リセットでは復旧できないことを一言

### Step 5: レポート

REPORT.md の書式で `report/<日時>_aws_v100_server_registration.md` を作る（概要、ハード構成、ディスク満杯と AER の発見、変更内容、検証結果）。`report/INDEX.md` にも 1 行足す。

## 検証

1. `bash -n` で、変更したシェルスクリプトをすべて構文チェックする
2. `lock.sh aws-v100` → `lock-status.sh aws-v100` → `unlock.sh aws-v100` が通ること。不正なサーバ名が今までどおり exit 2 になること
3. `power-ctl.sh aws-v100 status` が「BMC なし」で止まること
4. ロックを取り、`start.sh aws-v100 ~/models/huihui-qwen3.8-27b/Huihui-Qwen3.8-27B-abliterated-UD-Q4_K_XL.gguf`（既存 GGUF をローカルパスで指定）で起動する。
   `update_and_build-aws-v100.sh` の転送とビルド（sm_70）が通り、`wait-ready.sh` が成功し、`curl http://10.22.5.2:8000/v1/models` と短い chat completion が返ることを確かめる。ロード時の VRAM を `nvidia-smi` で記録する
5. `stop.sh aws-v100` で停止し、`unlock.sh aws-v100` でロックを外す
6. 最後にコミットする（`.githooks` の pre-commit を通す）
