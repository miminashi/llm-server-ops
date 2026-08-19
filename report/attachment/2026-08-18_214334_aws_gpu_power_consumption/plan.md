# aws-gpu01 / aws-gpu02 の消費電力調査（読み取り専用）

## Context

aws-gpu01 / aws-gpu02（Supermicro SYS-4028GR-TRT2 / TRT、Tesla P100 × 7 / × 6）は
2026-08-16 に運用へ加わり、以降 RPC 分散で 1 つの llama-server を常時動かす構成が既定になった。
一方で **これまで消費電力を一度も測っていない**。ファン静音化（2026-08-17）や既定構成の常時起動を
決めた判断も、電力面の裏付けを持たないまま進んでいる。

本調査の目的は 2 つ:

1. **現状把握（内訳の可視化）** — シャーシ全体の W が、GPU / それ以外（CPU・DIMM・ファン・PSU 損失等）に
   どう割れているかを分解する。特に **RPC 分散はパイプライン並列で GPU が 1 枚ずつしか動かない**ため、
   13 枚 × 250W = 3.25kW のような単純積算とは実態が大きく違うはずで、そこを実測で確定させる。
2. **電気代・運用コスト試算** — アイドル / 推論中それぞれの平均 W から kWh/日・月・年を出し、
   「常時起動し続けてよいのか」を判断できる材料にする。

ユーザ指示により **測定は読み取り専用の範囲に限定**する（GPU サーバのロックは取らない）。
負荷試験の意図的な投入・電源操作・power limit 変更はいっさい行わない。

## 前提と制約

- **ロックは取らない**。現在 aws-gpu01 / aws-gpu02 は別セッション
  (`aws-mmns-generic-428765/428772`, 2026-08-18 19:58 取得) がロック中で、RPC スタックが稼働している。
  CLAUDE.md の規定どおり、読み取り専用の監視（DCMI 読み出し・`nvidia-smi` 参照）はロック不要。
- **他セッションのワークロードに便乗する**。下調べ中に別セッションが推論を流していることを確認済み
  （`prompt processing 75 tok/s`、GPU1 が 180W / util 96%）。意図的に負荷をかけずとも、
  サンプリング期間中にアイドルと推論中の両方が観測できる見込み。
- **CPU の RAPL は読めない**。`/sys/class/powercap/intel-rapl:*/energy_uj` は `-r-------- root` で、
  Claude は sudo を直接実行しない規定。よって CPU 単体の W は分解対象から外し、
  「シャーシ全体 − GPU 合計」＝ **非 GPU 分**（CPU + DIMM + ファン + HDD + NIC + PSU 変換損失）として扱う。
  CPU 分の内訳が欲しい場合のみ、実行フェーズで下記コマンドをユーザに提示して実行を依頼する（任意・省略可）:
  ```bash
  ssh aws-gpu01 "sudo cat /sys/class/powercap/intel-rapl:0/energy_uj /sys/class/powercap/intel-rapl:1/energy_uj; sleep 10; sudo cat /sys/class/powercap/intel-rapl:0/energy_uj /sys/class/powercap/intel-rapl:1/energy_uj"
  ```

## 測定手段（下調べで実証済み）

| 対象 | 手段 | 実測サンプル |
|---|---|---|
| シャーシ全体 | `ipmitool -I lanplus ... dcmi power reading` の Instantaneous | gpu01 485W（常駐アイドル）→ 673-689W（推論中）/ gpu02 472W |
| 長期平均 | 同上の Average / Min / Max（sampling period ≈ 70h の BMC 累積） | gpu01 avg 467W, max 985W / gpu02 avg 434W, max 794W |
| GPU 個別 | `nvidia-smi --query-gpu=index,power.draw,utilization.gpu,clocks.sm --format=csv` | アイドル 35-42W/枚、稼働枚は 180W |
| ファン回転数 | `ipmitool sdr type Fan`（副次情報） | 静音デーモン常設下の実値 |
| PSU 構成 | `ipmitool fru` / `sdr type "Power Supply"` | PS1-4 すべて Presence detected |

BMC 認証情報は `~/.config/gpu-server/.env` の `BMC_AWS_GPU01_*` / `BMC_AWS_GPU02_*`
（`bmc-power.sh` と同じ解決規則）。

## 手順

### 1. サンプラーの作成と起動

`scratchpad/power-sampler.sh` を新規作成する（既存の `report/attachment/.../telemetry.sh` の
「制御ホスト側で ssh 越しに一定間隔サンプリングし、ローカルに追記」という構造を踏襲する）。

- **10 秒間隔**で 1 行 1 サンプルの CSV を吐く。列は
  `epoch, server, chassis_w, gpu_total_w, gpu_busy_count, gpu0_w..gpu6_w, util0..util6`
- 両サーバを並行サンプリング（gpu01 / gpu02 で別プロセス・別 CSV）
- `ipmitool` は応答に 1-2 秒かかるので、間隔は 10 秒を下回らせない（BMC への過負荷を避ける）
- ssh はタイムアウト付き（`-o ConnectTimeout=8`）。失敗行は欠測として記録し、スクリプトは止めない
- PID を pidfile に書き、停止は pidfile 経由の kill（`pkill -f` は自分にマッチするため使わない）

**サンプリング期間は 30 分を基本**とし、収集後に推論中サンプルが乏しければ 60 分まで延長する。

### 2. 静的情報の採取（サンプリングと並行）

- 両機の `dcmi power reading` 累積統計（Average / Min / Max / Sampling period）
- `ipmitool fru` から PSU の型番・定格（ブレーカ余裕の議論に使う）
- `ipmitool sdr type Fan` の回転数、`sdr type Temperature` の温度
- `nvidia-smi --query-gpu=power.limit` で 250W 制限を確認

### 3. 集計

`scratchpad/aggregate-power.py` を新規作成（`report/attachment/2026-06-27_.../aggregate_power.py` の
「CSV を状態でビン分けして平均・分位を出す」構造を踏襲）。

- **状態区分**: 各サンプルを GPU util 合計で `idle`（全 GPU util = 0）/ `busy`（いずれかの util > 0）に分類
- 区分ごとに シャーシ W / GPU 合計 W / 非 GPU 分 W の **平均・p50・p95・max** を算出
- **内訳表**: 非 GPU 分 = シャーシ全体 − GPU 合計。ここには PSU 変換損失（80 PLUS で概ね 8-12%）が
  含まれることを明記し、「サーバ内部の消費」と「壁からの消費」を混同しない書き方にする
- **2 台合計**の値も出す（RPC 分散は 2 台セットで 1 台分の推論をするため、合計こそが実効コスト）

### 4. 電気代試算

- アイドル / 推論中それぞれの 2 台合計平均 W から `kWh/日`・`kWh/月(30日)`・`kWh/年`
- 単価は **20 / 30 / 40 円/kWh の 3 水準**で表を作る（実単価が判明すれば差し替えられる形にする）
- **BMC 累積統計の 70 時間平均**（gpu01 467W + gpu02 434W = 901W）を「実運用の実効平均」として、
  短時間サンプリングの結果と突き合わせる。両者が乖離する場合はその理由を考察する
- 参考として「常時起動 vs 使うときだけ起動」の差額も出す。ただし aws-gpu01/02 は起動時の爆音制約と
  cold ロード 15 分があるため、**運用判断そのものは提言に留め、電源操作は一切行わない**

### 5. レポート作成

`report/yyyy-mm-dd_hhmmss_aws_gpu_power_consumption.md`（タイムスタンプは
`TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得）。REPORT.md 準拠で以下を含める:

- `## 概要`（必須・平易な日本語 5-8 段落）
- `## 核心発見サマリ`（アイドル/推論中の W、内訳、kWh/月、円/月）
- `## 環境情報` / `## 再現方法` / `## 結果詳細` / `## 副次発見` / `## 残課題` / `## 添付ファイル`
- 添付は `report/attachment/<同名ディレクトリ>/` に CSV・サンプラー・集計スクリプト・plan.md。
  CSV は 30-60 分 × 10 秒間隔で数百行程度なので gzip 不要（100MB hook に抵触しない）

CLAUDE.md の該当節（aws-gpu01/02 の構成）に、実測した消費電力の要約 1-2 行を追記するかは
レポート完成後にユーザへ確認する。

## 検証方法

- サンプリング中に `nvidia-smi` を別途叩き、CSV の値と目視で一致することを確認する
- DCMI の Instantaneous 値が GPU 合計 W の増減に追従していること（推論開始で +150W 程度動くこと）を確認し、
  DCMI が実際にシャーシ電力を反映していることを裏付ける
- 集計スクリプトの `idle` / `busy` 区分が llama-server ログの推論タイムスタンプと整合するかを照合する
- 欠測率（ssh / ipmitool 失敗行）を集計に明記し、5% を超える場合は原因を調べたうえで再取得する

## やらないこと

- ロック取得、意図的な推論投入、ベンチ実行
- 電源操作（`on` / `off` / `reset` / `cycle`）、BIOS 変更、ファン設定変更
- `nvidia-smi -pl` による power limit 変更、ECC 設定変更
- 他セッションが動かしている llama-server / rpc-server への干渉
