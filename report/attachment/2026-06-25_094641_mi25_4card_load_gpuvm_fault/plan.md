# mi25 4枚復旧後の安定性検証(電源サイクルテスト + 負荷テスト)

## Context(なぜ実施するか)

2026-06-25 朝の復旧レポート [`report/2026-06-25_063238_mi25_4card_recovery.md`](../../projects/llm-server-ops/report/2026-06-25_063238_mi25_4card_recovery.md) で、MI25 4枚が物理再装着により全数 Gen3 x16・AERエラー0 で認識され 64GB VRAM が復旧した。ただし以下のとおり **「恒久解決ではなく暫定復旧・要監視」** と位置づけられている:

- 3枚・4枚を認識させるのに **認識まで数回の抜き差しを要した** = 接触マージンが低く再発しうる
- 観測は **idle のみ**。長時間稼働・再起動後の再列挙・高負荷時の脱落は未検証

レポートの「推奨フォローアップ」のうち、本タスクで以下2件を実施する:
1. **電源サイクルテスト**(推奨①): コールド/ウォーム再起動をまたいで 4枚が安定列挙されるか
2. **負荷テスト**(推奨②): 4枚 offload 推論の高負荷下で脱落・リンク劣化・ハングが出ないか

**現状ベースライン(本計画時に読み取り確認済み)**: 電源ON / 4枚認識維持(GUID 29525・33301・54068・8820) / uptime 約1:47 / llama-server 未起動 / ロック空き。

## 実施順序・強度(ユーザ確定)

- **順序: 電源サイクルテスト → 負荷テスト**(ユーザ選択)。
- **強度: 標準** — 負荷=ROCm 約2時間(約10試行)、電源サイクル=コールド5回 + ウォーム2回。

## 重要な前提・リスク

- **電源サイクルテストは「復旧した4枚目を再び落とす」リスクがある**。前回 dropout レポートで SLOT4(00:03/GUID 33301) は遠隔(電源サイクル)では **不可逆に x0** だった。今回は物理再装着で健全化したが接触マージンが低いため、コールドサイクルで再脱落すると **遠隔復旧不可 → ユーザの物理再装着が必要**。
- **サイクル先行の含意**: 電源サイクルテストで 4→3枚 に脱落した場合、後続の負荷テストは **残存枚数(3枚)でしか実施できない**。その時点で一旦停止し、ユーザに「3枚で負荷テスト続行」か「物理再装着して4枚に戻す」かを確認する。
- 電源サイクル中に 4→3枚 への脱落を検知したら、**それ以上サイクルを回さず即停止**(更にリスクを重ねない・遠隔では戻せない)。状態を保全しユーザへ報告。
- 負荷テストは LLM を使うため **`gpu-server` ロック必須**。電源サイクルも機体を占有するため取得する。ただし **ロックは GPU サーバの `/tmp/gpu-server-locks/mi25.lock`(SSH経由の symlink)に置かれ、再起動で `/tmp` がクリアされる + OFF中は SSH不可** のため、**サイクルをまたいで保持できない**。→ `run_campaign.sh` が reset 後に unlock→lock し直すのと同様、**各サイクルの SSH 復帰後にロックを取り直す**(単独運用のため OFF 窓中の競合リスクは許容)。
- ハング/SSH不通検知時は **電源リセット前に必ず `bmc-screenshot.sh` でKVMスクショ保全**(CLAUDE.md / [[project_mi25_bmc_recovery]])。
- sudo が要る操作はユーザに依頼(mi25 は NOPASSWD sudo 設定済みのため SSH 経由 sudo は自動実行可、[[project_mi25_qwen36_128k]])。

## 再利用する既存資産(新規作成を最小化)

| 資産 | パス | 用途 |
|---|---|---|
| 負荷ドライバ | `report/attachment/2026-06-24_161909_mi25_hang_repro_load_campaign/load_driver.py` | 合成連続推論負荷 + 三点ハング検出(BMC+拠点参照弁別) |
| キャンペーン制御 | 同上 `run_campaign.sh` | 試行ループ・ハング時KVMスクショ→復旧→再開の自動化 |
| テレメトリ | 同上 `telemetry.sh` | 10秒毎 rocm-smi/GPU枚数/dmesg/llama-server ログ採取 |
| 解析・作図 | 同上 `analyze.py` | スループット分布・GPU枚数推移の図・集計JSON |
| 電源サイクル雛形 | `report/attachment/2026-06-19_015028_mi25_coldcycle_3card_recovery/cycle5.sh` | N回コールドサイクル + 各サイクルで PCIe/dmidecode/GUID 採取 |
| 電源/ロック | `.claude/skills/gpu-server/scripts/{bmc-power,bmc-screenshot,lock,unlock,lock-status}.sh` | IPMI電源・KVM・排他制御 |
| 推論起動 | `.claude/skills/llama-server/scripts/{start,wait-ready,stop}.sh`(または `llama-up.sh`) | mi25 ROCm 4枚 offload 起動 |

## 確定構成(メモリ・スキルより)

- モデル: `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`、ctx=131072
- ROCm(既定): `--flash-attn 1 --poll 0 -b 2048 -ub 2048`、KV `q8_0`、`--split-mode layer` で4枚自動分散([[project_mi25_qwen36_128k]])。master は FP8 でビルド不能のため pin 済み。
- 4枚になったため ROCm の auto 構成は実効4枚を選択(従来の3枚前提から枚数のみ変化)。
- ヘルス: `http://mi25:8000/health`(200=Ready)、ttyd 7681/7682。

## 実施計画

### Phase 0: 準備(読み取り + ロック取得)
1. `bmc-power.sh mi25 status` / `lock-status.sh mi25`(済: ON・空き)。
2. 4枚認識・**各ルートポートの LnkSta/PresDet・AER COR カウンタ**のベースライン採取(00:02.0/00:03.0/80:02.0/80:03.0)。
3. `lock.sh mi25` でロック取得。
4. テスト資産を scratchpad へコピー: 先行する Phase 1 用に `cycle5.sh`(→4枚チェック版へ調整)、後行の Phase 2 用に `load_driver.py`/`run_campaign.sh`/`telemetry.sh`/`analyze.py`(エンドポイント/モデルを現構成に合わせる)。

### Phase 1: 電源サイクルテスト(破壊リスクあり・先行)
1. `cycle5.sh` を雛形に、**4枚列挙チェック版**へ調整(各サイクルで 認識枚数・GUID・4ルートポートの LnkSta/PresDet・AER・dmesg の x0/x8/reset/hang を採取)。
2. **コールドサイクル5回**(`bmc-power.sh mi25 soft` → 電力ドレイン30秒 → `on` → SSH復帰待ち → **ロック取り直し** → 採取)+ **ウォーム再起動2回**(`ssh mi25 sudo reboot`、戻らなければ `bmc-power.sh reset` → SSH復帰待ち → ロック取り直し → 採取)。
3. **早期停止条件**: あるサイクルで 4→3枚 へ脱落したら、即サイクル停止 → 脱落スロットの状態を保全 → ユーザへ確認(「3枚で負荷テスト続行」か「物理再装着して4枚に戻す」)。遠隔では戻せない。
4. SSH復帰しない(ハング)時は **KVMスクショ保全 → 電源リセット**。
5. 成功判定: 全サイクルで **4/4 が x16・AERエラー0 で再列挙**。

### Phase 2: 負荷テスト(後行) ※ ROCm
1. 電源サイクルテスト完了時点の認識枚数を確認(4枚維持が前提。脱落していれば Phase 1 手順3 のユーザ確認に従う)。ロックは Phase 1 の最終サイクルで取り直したものを継続使用。
2. `start.sh mi25 <model> 131072`(ROCm) → `wait-ready.sh` で /health 200 確認。起動ログで **4枚 offload** を確認。
3. **テレメトリ強化**: `telemetry.sh`(rocm-smi/gpu_count/dmesg)に加え、**per-card LnkSta + AER COR を10秒毎にサンプリングする小スクリプトを追加**(4枚維持・x16維持・AER増加なしを構造化ログで証拠化)。← 本検証の主目的に直結。
4. `run_campaign.sh hip` を **ROCm 約2時間(約10試行)上限**で実行。本テストの目的はハング再現ではなく **4枚の高負荷安定性確認**なので、試行数/時間は前回(24試行/5h)より縮小。
5. 成功判定: 試行中ずっと **gpu_count=4 維持 / 全カード x16 維持 / AER COR デルタ0 / ハング0 / 温度・電力に異常スパイクなし**。
6. `stop.sh` で llama-server 停止。

### Phase 3: 解析・レポート
1. `analyze.py` 等でスループット分布・gpu_count 推移・PCIeリンク推移を集計、核心サマリ PNG を生成([[feedback_report_title]]: タイトル50字以内・核心発見サマリ冒頭にPNG埋め込み)。
2. [REPORT.md](../../projects/llm-server-ops/REPORT.md) 準拠でレポート作成(`report/` + `report/attachment/<ts>_*/` にスクリプト・生ログ要約・PNG)。`report/INDEX.md` 更新。
3. 結果(4枚が再起動/負荷で安定か、暫定復旧の格上げ可否)をメモリ [[project_mi25_gpu4_pcie_dropout]] に反映。必要なら Discord 通知。

## 最終状態の扱い
- テスト後: llama-server 停止 → ロック解放。電源は **ON のまま idle で残す**(4枚状態を継続観測可能にする)既定。ユーザが OFF 希望なら `bmc-power.sh mi25 off`。

## 検証(どう確かめるか)
- 負荷テスト: campaign ログ rc=0(完走)、`telemetry_gpucount.log` が全行 `gpu_count=4`、追加 PCIe ログが全サンプル `x16`・AER COR デルタ0、`kern_dmesg.log` に reset/hang/AER fatal なし。
- 電源サイクル: サイクルトレンドログが全サイクル 4枚・x16・PresDet+・AER0。
- 1件でも脱落/劣化があれば「要監視継続(恒久対策=接点清掃/ライザー点検が必要)」と結論、なければ「4枚復旧は再起動・高負荷に耐え暫定→実用レベルへ格上げ」と結論。
