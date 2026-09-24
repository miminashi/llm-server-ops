# aws-gpu01 の P100 2 枚の ECC を有効化する

## Context

2026-08-16 の登録時に、aws-gpu01 の P100 7 枚のうち GPU0（serial 0320318031972）と GPU5（0320318033253）だけが ECC Disabled だった。反映には再起動が要り、爆音ガードのため保留になっていた。今回ユーザから、電源投入・再起動・aws-gpu01 での sudo（今回限り）の明示許可を得たので実施する。現在の電源は Off。作業後は Off に戻す。

ユーザの許可（2026-09-24）: `ALLOW_FAN_NOISE=1` での on / soft、今回限りの `sudo nvidia-smi -e 1`、作業後の soft 電源断。

## 手順

1. **ロック**: `.claude/skills/gpu-server/scripts/lock.sh aws-gpu01`。aws-gpu02 は DIMM 故障で Off のままにし、触らない（09-14〜09-16 の単体作業と同じ扱い）
2. **電源投入**: `ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 on`。boot-quiet が自動で併走する。SSH が通るまで待つ（約 150 秒）
3. **現状確認**: `nvidia-smi --query-gpu=index,pci.bus_id,serial,ecc.mode.current,ecc.mode.pending --format=csv` と `nvidia-smi --query-compute-apps=pid --format=csv`（GPU を使うプロセスが無いこと）。対象は index ではなく **serial で特定**する（index の並びが変わっていないかを確かめる）
4. **有効化**: 対象 index ごとに `ssh aws-gpu01 "sudo nvidia-smi -i <idx> -e 1"` を実行し、再び query を流して `ecc.mode.pending = Enabled` になったことを確認する
5. **反映のための再起動**: 手荒な `reset` は使わず、`ALLOW_FAN_NOISE=1 bmc-power.sh aws-gpu01 soft` で ACPI シャットダウンし、`status` が off になったのを確認してから `on` を実行する（`on` なら boot-quiet が併走する。OS 内の `reboot` では併走しない）
6. **検証**: SSH 復帰後に手順 3 の query を再度流し、**7 枚すべてで `ecc.mode.current = Enabled`** になっていること、各 GPU の memory.total、ECC エラーカウンタ（`ecc.errors.uncorrected.volatile.total`）を記録する。`nvidia-smi -q -d ECC` の全文も保存する
7. **後片付け**: `ALLOW_FAN_NOISE=1 bmc-power.sh aws-gpu01 soft` → `status` で off を確認 → `.claude/skills/gpu-server/scripts/unlock.sh aws-gpu01`

失敗した場合（`-e 1` がエラーになる、再起動後も Disabled のまま、など）は、出力を保存したうえで再試行はせず、電源断とロック解放まで済ませてから報告する。
OS が起動しない場合は、CLAUDE.md に従って `bmc-screenshot.sh` と `ipmitool sel elist` で証跡を保全し、報告する。

## 文書の更新

- `.claude/skills/gpu-server/aws-gpu.md`: baseline 表の ECC 列と「既知の個体差」の ECC 項目を、結果に合わせて更新する（成功した場合は「2026-09-24 に全 7 枚 Enabled へ統一」と書く）
- レポート `report/<timestamp>_aws_gpu01_ecc_enable.md` を REPORT.md の形式で作成する（概要を必須とする）。コンソール出力は `report/attachment/<同名>/` に置く
- コミットはユーザから指示があった場合に限って行う

## 検証（完了条件）

- 再起動後の `ecc.mode.current` が 7 枚すべて Enabled になっている
- 作業後に `bmc-power.sh aws-gpu01 status` が off を返し、ロックが解放されている
