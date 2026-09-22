# aws-v100 を管理対象サーバに追加

- **実施日時**: 2026年9月23日 04:00 〜 05:10 JST (サーバ調査・スクリプト/文書更新・ディスク復旧・実機でのビルドと起動検証)
- **報告日時**: 2026年9月23日 05:10 JST
- **作成者**: Claude Opus 5 (1M context)

## 概要

ユーザから「v100 サーバをリストに追加したい」という依頼を受け、`ssh aws-v100` でアクセスできる V100 機を
gpu-server / llama-server スキルと CLAUDE.md の管理対象に加えた。これまで管理していたのは 5 台（mi25、
t120h-p100、t120h-m10、aws-gpu01、aws-gpu02）で、V100 機はどこにも記載が無く、ロックの対象外だった。

まず読み取り専用でサーバの素性を調べた。結果は既存のどのサーバとも性格が違い、民生用のマザーボードに
V100 を 2 枚載せた小型の機械だった。最も運用に影響するのは BMC が無いことで、電源操作も、ハング時の
コンソール画面や SEL の保全もできない。つまり止まったら現地に行くしかない。この 1 点があるため、
電源まわりの扱いは他の 5 台と同じにはできなかった。

調査中に、想定していなかった問題が 2 つ見つかった。1 つはルートファイルシステムが満杯だったこと
（116 GB 中の空きが 109 MB）で、この状態ではビルドもモデルの取得もできない。もう 1 つがその原因で、
片方の GPU につながる PCIe ポートが軽微な通信エラーを絶え間なく報告し続けており、その記録だけで
ログが 2 日半に 2.8 GB 増えていた。訂正済みのエラーなので実害は無いが、放っておくと定期的にディスクを
埋める。ユーザの許可を得てログを削除し、このメッセージだけを記録しない設定を入れて再発を止めた。

登録作業そのものは、ロック・起動・停止に関わるスクリプトのサーバ名リストを広げ、V100 向けのビルド設定
（sm_70）と起動パラメータを追加し、文書を更新するという内容である。計画からは電源まわりだけ方針を変えた。
当初は「BMC が無いので電源関連はすべて拒否する」つもりだったが、それだと起動スクリプトが電源状態の確認で
止まってしまうため、状態確認は SSH の疎通で代用し、投入と切断だけを拒否する形にした。あわせて停止
スクリプトが最後に電源を落とそうとする手順も、このサーバでは飛ばすようにしている。一度落とすと現地でしか
戻せないためである。

最後に、実際にこのサーバで llama.cpp のビルドから llama-server の起動、応答確認、停止までを一度通した。
この過程で登録作業だけでは足りない点が 2 つ見つかった。1 つは起動スクリプトが `hf` コマンドを探す場所に
このサーバの置き場所が入っていなかったこと、もう 1 つはファイアウォールが標準ポートを塞いでいたことで、
どちらもその場で直している。最終的に、ワークステーションから API を叩いて正しい応答を得るところまで確認できた。

今後の課題として、AER の根本原因である変換基板やライザーの状態は手を付けていない。GPU の片方は
本来より遅い速度でしか接続できておらず、これも同じ原因と見られる。性能が問題になるようなら物理的な
確認が要る。

## 添付ファイル

- [実装プラン](attachment/2026-09-23_043617_aws_v100_server_registration/plan.md)

## 環境情報

| 項目 | 値 |
|---|---|
| ホスト名 / IP | `v100` / `10.22.5.2`（SSH エイリアス `aws-v100`、ユーザ `ubuntu`） |
| マザーボード / CPU / RAM | ASRock X99 Taichi（民生品、**BMC なし**）/ Core i7-6800K（12 スレッド）/ 31 GiB |
| GPU | Tesla V100-SXM2-16GB ×2（sm_70、計 32 GB） |
| GPU 接続 | SXM2→PCIe 変換基板。**NVLink 非活性**（`nvidia-smi topo -m` は PHB）。GPU0 = Gen3 x8、GPU1 = Gen2 x8 |
| OS / ドライバ / CUDA | Ubuntu 24.04.3（kernel 6.8.0-106）/ 580.65.06 / `/usr/local/cuda-12.9`（nvcc は PATH 外） |
| WS からの RTT | 0.3 ms（aws-gpu01/02 と同一拠点） |
| sudo | 作業中にユーザが NOPASSWD を設定（`(ALL : ALL) NOPASSWD: ALL`） |
| hf CLI | `~/.venv/bin/hf`（huggingface_hub 0.34.4）。PATH には無い |
| docker | 導入済みだが `ubuntu` は docker グループ外（リモートブラウザは未整備） |

## 結果詳細

### 変更したファイル

| ファイル | 変更内容 |
|---|---|
| `lock.sh` / `unlock.sh` / `lock-status.sh` | `VALID_SERVERS` に `aws-v100` を追加 |
| `transfer-file.sh` / `stop.sh` / `ttyd-gpu.sh` / `ttyd-up.sh` / `wait-ready.sh` / `install-global.sh` | サーバ名の許可リスト・usage を更新 |
| `start.sh` | 許可リスト、`aws-v100` の分岐（`--flash-attn 1 --poll 0 -b 4096 -ub 4096` + 2 枚の枚数チェック）、`hf` 探索先に `$HOME/.venv/bin` を追加 |
| `setup-llama-cpp.sh` | `aws-v100` の分岐（CUDA、`/usr/local/cuda-12.9/bin/nvcc`、`CMAKE_CUDA_ARCHITECTURES=70`） |
| `power-ctl.sh` | サーバ種別に **`none`（BMC なし）** を新設。`status` は SSH 疎通で `On`/`Unknown` を返し、`on`/`off` は exit 2 |
| `llama-down.sh` | `aws-v100` では Step 4 の電源 OFF をスキップ |
| `update_and_build-aws-v100.sh`（新規） | sm_70 / cuda-12.9 のビルドスクリプト。RPC ワーカーではないので `-DGGML_RPC` と `--no-pull` は持たない |
| `CLAUDE.md` / `gpu-server/SKILL.md` / `llama-server/SKILL.md` / `server-scripts/README.md` | サーバ一覧・エンドポイント・注意事項・BMC 一覧・パラメータ表を更新 |

### 実機検証

| 項目 | 結果 |
|---|---|
| 構文チェック（`bash -n` / `sh -n`） | 変更した全スクリプトで通過 |
| ロック | `lock.sh` → `lock-status.sh`（LOCKED 表示）→ `unlock.sh` が正常動作。不正なサーバ名は従来どおり exit 2 |
| `power-ctl.sh aws-v100 status` | `On`（SSH 疎通で判定）。`on` は exit 2 で拒否 |
| ビルド | `start.sh` 経由で llama.cpp master `709fe75` を sm_70 でフルビルド成功（約 40 分、12 スレッド）。`llama-server` の sha256 先頭 `4348b86f7ad84949` |
| 起動 | Huihui-Qwen3.8-27B-abliterated UD-Q4_K_XL（18 GB）を ctx=16384 でロード。**VRAM 使用は GPU0 9,673 MiB / GPU1 10,919 MiB**（各 16,384 MiB）。`-b 4096 -ub 4096` で余裕あり |
| API | WS から `http://10.22.5.2:8000/v1/models` が応答。chat completions で「日本の首都は東京です。」を取得 |
| 速度 | prompt eval **113.7 t/s**（63 tok）、eval **33.8 t/s**（60 tok） |
| 停止 | `llama-down.sh aws-v100` で llama-server と ttyd を停止、VRAM 0 MiB、ロック解放、**電源 OFF は設計どおりスキップ** |

### 検証中に判明して直した点

1. **`start.sh` の `hf` 探索先にこのサーバの置き場所が無かった。** 既存 3 台は `/home/llm/.local/bin/hf`、
   aws-gpu01/02 は `~/.local/bin/hf` だが、aws-v100 は **`~/.venv/bin/hf`**（venv 内、PATH 外）にある。
   探索順に `$HOME/.venv/bin/hf` を追加した。
2. **ufw が標準ポート 8000 を塞いでいた。** 許可は 22 と 8080（停止した手動サーバのポート）だけで、
   サーバ内からは 200 が返るのに WS からはタイムアウトしていた。ユーザの選択により
   **`10.0.0.0/8` からの 8000 / 7681 / 7682（ttyd）を許可**した（Anywhere ではなく社内セグメント限定）。
3. **ローカル GGUF の指定は絶対パスが必須。** `start.sh` の判定は `/*.gguf` なので `~/...` は
   HF リポジトリ名と解釈されて失敗する（スクリプトの仕様どおり。今回は呼び出し側の誤り）。

## 残課題

- **PCIe AER の物理的な原因は未対処**。GPU1 の上流ポートでの `RxErr` / `BadTLP` は SXM2→PCIe 変換基板や
  ライザーの信号品質が疑わしい。**GPU1 が Gen2 x8 に留まっている**のも同根と見られ、帯域が効く用途では
  物理的な確認（挿し直し・ケーブル交換）が要る。今回はログ出力を止めただけで、エラー自体は続いている
- **ディスクの空きは 17 GB しかない**。`~/.venv`（8 GB）や `~/.cache`（13 GB）に整理の余地があるが、
  他の用途のものか判断できないため今回は触っていない
- **`-b 4096 -ub 4096` は P100 系からの流用値**で、V100 向けの最適化はしていない。VRAM には
  各 5〜6 GB の余裕があるので引き上げる余地がある
- **ベンチマークは未取得**。今回測ったのは短いプロンプト 1 本（prompt eval 113.7 t/s / eval 33.8 t/s）だけで、
  長コンテキストでの挙動は未確認

## 副次発見

### ルート FS 満杯と PCIe AER のログ洪水

調査時点でルート FS は 100% 使用（116 GB 中 空き 109 MB）だった。内訳は `/var/log` が 18 GB
（syslog / kern.log が各約 3 GB × 2 世代、dmesg 1.3 GB、journal 4 GB）で、中身はほぼすべてが
以下の 4 行 1 組の繰り返しだった。

```
pcieport 0000:00:03.0: AER: Correctable error message received from 0000:00:03.0
pcieport 0000:00:03.0: PCIe Bus Error: severity=Correctable, type=Physical Layer, (Receiver ID)
pcieport 0000:00:03.0:   device [8086:6f08] error status/mask=00000001/00002000
pcieport 0000:00:03.0:    [ 0] RxErr                  (First)
```

`00:03.0` は **GPU1 の上流ルートポート**で、`RxErr`（物理層の受信エラー）が毎秒数回の頻度で発生している。
訂正済みのエラーなので計算結果には影響しないが、**2.5 日で約 2.8 GB** のペースでログが増える。
**GPU1 が Gen2 x8 でしかリンクしていない**のも同じ原因（SXM2→PCIe 変換基板の信号品質）と見られる。

対処として、ログを削除して 17 GB を回復したうえで、ユーザの選択により rsyslog のフィルタを導入した。

- `/etc/rsyslog.d/10-drop-pcie-aer.conf` — 上記 4 行に該当するメッセージを syslog / kern.log に書かずに捨てる
- `/etc/systemd/journald.conf.d/10-max-use.conf` — journal 側は残るため `SystemMaxUse=1G` で上限を固定

導入後 60 秒の観測で kern.log は 0 バイトのまま（従来は約 1.1 MB/分の増加ペース）、journal 側は
引き続き毎分 250 件前後を受けているが上限で頭打ちになる。

なお **GPU に負荷をかけると別表現のメッセージ**（`AER: Multiple Correctable error message received` と
`BadTLP`）が出ることが検証中に分かったため、これらと `pcieport` 由来の `error status/mask=` 行も
フィルタに追加した（約 35 分で 41 KB の増加を確認したあと追加し、再観測では 60 秒で 0 バイト）。
**`severity=Uncorrected` の行は意図的に残している**ので、訂正不能な重大エラーが起きれば気付ける。

## 結論・対応

**aws-v100 を 6 台目の管理対象サーバとして登録し、ロックから起動・停止まで実機で通ることを確認した。**
運用上の要点は次の 3 つ。

1. **BMC が無い。** 電源操作もハング時の証跡保全（KVM スクショ・SEL）もできず、止まったら現地対応になる。
   `power-ctl.sh` は `status` のみ（SSH 疎通で代用）、`llama-down.sh` は電源 OFF をしない。
2. **ディスクが小さく（116 GB）、PCIe AER でログが膨らむ性質がある。** 今回フィルタを入れて止めたが、
   作業前には `df -h /` を見る習慣にしたい。現在の空きは 17 GB で、モデルを 1 本足すと厳しい。
3. **単体運用で、VRAM は 32 GB。** 27B の Q4 級がちょうど載る規模（実測で約 20 GB 使用）。

残課題は「副次発見」に挙げた AER の物理的な原因（変換基板・ライザー）で、GPU1 が Gen2 x8 に
留まっていることと合わせ、性能を詰める段階で物理確認が要る。
