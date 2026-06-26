# mi25 4枚 Vulkan 負荷 — 電力制限スイープ追試 計画

## Context

[2026-06-25_145006_mi25_4card_load_vulkan.md](/home/ubuntu/projects/llm-server-ops/report/2026-06-25_145006_mi25_4card_load_vulkan.md) で「Vulkan 4枚負荷 → 約 2208s で GPU 8820 (SLOT6/87:00.0) が `amdgpu_job_timedout` → `BACO reset` → `VRAM lost` → llama-server クラッシュ」を確定済み。原因は 8820 個体のハード起因と推測されるが、**フォルト発火が電力(熱・電流)に依存するか**を切り分ける必要がある。電力制限を 140W〜190W で 5W 刻みにスイープし、各電力点で同一負荷を投入して time-to-fault と anomaly の有無を観測する。期待結果:

- 高電力ほど早く・確実にフォルト → 電力/熱主因
- 全電力点で安定 → 物理層 (信号/絶縁/メモリセル) 主因、電力では救えない
- 中間に明瞭な閾値 → 電力スイートスポットを 4 枚 64GB 運用に活用できる可能性

## 前提・目的

- **目的**: 11 電力点 (140/145/150/.../185/190 W) × Phase 1 (4 枚 Vulkan) × MAX_TRIALS=4 のスイープを完走し、(電力, fault有無, time-to-fault, eval/prompt スループット) の関係表を得る。
- **前提**:
  - mi25 利用可能・`gpu-server` ロック取得 (これから取得)。
  - 4 枚復旧状態 (GUID 29525/33301/54068/8820、全ポート x16・AER0) を維持。電源サイクル合格は前回確定済 (バックエンド非依存) のため再実施しない。
  - Vulkan (RADV、`build-vulkan/`、master 追従) のみで実施。ROCm 追試はしない。
  - 電力制限の参照: `/etc/rc.local` (`echo "<μW>" > /sys/class/drm/cardX/device/hwmon/hwmonY/power1_cap`)。`power1_cap_max=220000000` (=220 W)・`power1_cap_min=0` を確認済。現在値 160 W。hwmon 番号は再起動で変わるためスクリプトで動的解決。
  - mi25 は NOPASSWD ALL 設定済 (`sudo -l` で `(ALL) NOPASSWD: ALL` を確認、`sudo tee` も問題なく動く)。

## スイープ仕様

| 項目 | 値 |
|------|----|
| 電力点 | 190, 185, 180, 175, 170, 165, 160, 155, 150, 145, 140 (W) — **高→低の順** |
| 構成 | Vulkan, 4 枚 (`GGML_VK_VISIBLE_DEVICES=0,1,2,3`、start.sh が auto 検出) |
| モデル | `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`, ctx=131072 |
| 起動パラメータ | 元レポートと同一 (`--n-gpu-layers 99 --split-mode layer --flash-attn 1 --poll 0 -b 2048 -ub 2048 --cache-type-{k,v} q8_0`) |
| 試行設定 | `MAX_TRIALS=4 MIN_TRIALS=4 PHASE_CAP_SEC=3000 TRIAL_SEC=720` (PHASE_CAP は 4×720=2880 + 余裕 120s) |
| 想定 1 点あたり時間 | 安定 ≈ 2880s, フォルト時 ≈ 2200s + (空回り 3 試行 × ~30s) ≈ 2300s |
| 想定総時間 | **約 9 時間** (11 点 × 平均 2700s + 点間オーバヘッド 2-3 分 × 11) |
| 早期打ち切り | **なし** (全 11 点完走)。ただし `run_campaign` が rc≠0 で抜けたら **スイープループ中断** (rc=7 ハング安全境界 / rc=8 NW outage / rc=9 BMC 復旧失敗 はどれも 8820 フォルト以外の異常事態) |
| 進行順理由 | 既に 160 W で発火確認済 (元レポート ~2208s)。先に 190 W で再現性を確認 → 下げていくと「いつ消えるか」を時系列で観測できる。低→高 だと初期の「フォルトしない」が個体ばらつきかスイープ効果か曖昧 |

## 設計

### 0. スクラッチパッド準備 (`scratchpad/`)

元レポート添付 `report/attachment/2026-06-25_145006_mi25_4card_load_vulkan/` から以下を **新スクラッチパッド** にコピー:

- `run_campaign.sh` — **`SCRATCH=...` 行を新パスへ sed で書き換え必須** (元は前セッションのハードコード `/tmp/claude-1000/.../b494831f-.../scratchpad/mi25-vulkan-load`)
- `load_driver.py` — `run_campaign.sh` が `$SCRATCH/load_driver.py` で呼ぶため必須
- `telemetry.sh` — `run_campaign.sh` が `start_telemetry()` で自動起動 (rocm-smi 10s + dmesg ストリーム + llama-server ログ tail)
- `telemetry_pcie.sh` — 4 ルートポート LnkSta + AER 10s 毎、`sweep_one_point.sh` が手動起動
- `make_summary.py` — スイープ集計用に**カラム拡張** (電力スイープ表 + PNG)

新規スクリプト:

- `set_power_cap.sh` — mi25 上で実行する power1_cap 設定ヘルパ (hwmon パス動的解決)
- `sweep_one_point.sh` — 1 電力点のルーチン (再起動 / 電力切替 / run_campaign / 退避)
- `sweep_loop.sh` — 11 点ループ + ロック / 後始末

### 1. 電力制御ヘルパ (`set_power_cap.sh`)

```bash
#!/bin/bash
set -euo pipefail
W=${1:?usage: $0 <watts>}
UW=$((W * 1000000))
for c in 1 2 3 4; do
  H=$(ls -d /sys/class/drm/card$c/device/hwmon/hwmon* 2>/dev/null | head -1)
  [ -z "$H" ] && { echo "ERR: no hwmon for card$c" >&2; exit 1; }
  echo "$UW" | sudo tee "$H/power1_cap" > /dev/null
  CUR=$(cat "$H/power1_cap")
  echo "card$c $H/power1_cap = ${CUR} (=$((CUR/1000000))W)"
done
```

実行: `ssh mi25 'bash -s' < scratchpad/set_power_cap.sh 175`。設定後 `ssh mi25 'rocm-smi --showmaxpower'` でも反映確認。**llama-server 停止中に切り替える** (生プロセスへの不要な擾乱を避ける)。

### 2. 1 電力点ルーチン (`sweep_one_point.sh`)

```bash
# pseudo
SCR=<scratchpad>
WATTS=$1
TAG="p${WATTS}W"

# (a) llama-server 停止 (生きてれば)
ssh mi25 'pkill -f bin/llama-server || true; sleep 3'

# (b) 電力制限切替 + 反映確認
ssh mi25 'bash -s' < $SCR/set_power_cap.sh "$WATTS"
ssh mi25 'rocm-smi --showmaxpower' > $SCR/maxpower_${TAG}.txt

# (c) 期前 cursor 取得 (点別差分を取るため)
ssh mi25 "sudo journalctl --since=now --cursor-file=/tmp/jcur_${TAG} -n0"
ssh mi25 "date -Iseconds" > $SCR/anchor_${TAG}.txt

# (d) llama-server 起動 (Vulkan 4枚 auto)
MI25_BACKEND=vulkan .claude/skills/llama-server/scripts/llama-up.sh mi25 \
  "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072

# (e) per-card PCIe+AER サンプラを手動起動 (run_campaign が起動する telemetry.sh とは別物)
bash $SCR/telemetry_pcie.sh "$SCR" mi25
# → $SCR/telemetry_pcie.log と $SCR/telemetry_pcie.pid を作る

# (f) run_campaign.sh vulkan 実行 (telemetry.sh は中で start_telemetry が自動起動)
MAX_TRIALS=4 MIN_TRIALS=4 PHASE_CAP_SEC=3000 TRIAL_SEC=720 \
  bash $SCR/run_campaign.sh vulkan
RC=$?

# (g) per-card PCIe サンプラ停止
[ -f $SCR/telemetry_pcie.pid ] && kill $(cat $SCR/telemetry_pcie.pid) 2>/dev/null
rm -f $SCR/telemetry_pcie.pid

# (h) telemetry.sh が起動した子プロセスも停止
[ -f $SCR/telemetry.pids ] && xargs -r kill 2>/dev/null < $SCR/telemetry.pids
rm -f $SCR/telemetry.pids

# (i) 固定名出力を点別に退避 (run_campaign / telemetry の固定名は次点で上書きされるため必須)
mv $SCR/trials_vulkan.jsonl        $SCR/trials_${TAG}.jsonl
mv $SCR/campaign_vulkan.log        $SCR/campaign_${TAG}.log
mv $SCR/telemetry_pcie.log         $SCR/telemetry_pcie_${TAG}.log
mv $SCR/telemetry_rocmsmi.log      $SCR/telemetry_rocmsmi_${TAG}.log
mv $SCR/telemetry_gpucount.log     $SCR/telemetry_gpucount_${TAG}.log
mv $SCR/kern_dmesg.log             $SCR/kern_dmesg_${TAG}.log
mv $SCR/llama_server.log           $SCR/llama_server_${TAG}.log
# boot_state.log は run_campaign が点をまたいで追記する共通台帳 → そのまま残す

# (j) llama-server.log のサーバ側 tail + 期間差分 journal を採取
ssh mi25 "tail -300 /tmp/llama-server.log" > $SCR/llama_server_${TAG}_tail.log
ssh mi25 "sudo journalctl --cursor-file=/tmp/jcur_${TAG} --no-pager" > $SCR/journal_${TAG}.txt

# (k) llama-server 停止 + 点間 PCIe 健全性の最終スナップ
ssh mi25 'pkill -f bin/llama-server || true'
ssh mi25 'rocm-smi --showbus --showpower --showtemp --showmeminfo vram' > $SCR/rocm_${TAG}_post.txt

# (l) run_campaign の rc を返す
exit $RC
```

**rc=42 (load_driver の HOST_HANG) は run_campaign 内で BMC リセット & 復旧** され、復旧成功なら次の trial に進む。8820 フォルトは「サーバ機械は生きてる / llama-server だけ死ぬ」ため load_driver では `server_error_transient` (rc=0) に分類され BMC リセットは走らない (これは元レポートで確定済の挙動)。

### 3. スイープループ (`sweep_loop.sh`)

```bash
SCR=<scratchpad>
LOCK=.claude/skills/gpu-server/scripts/lock.sh
UNLOCK=.claude/skills/gpu-server/scripts/unlock.sh

$LOCK mi25
trap "$UNLOCK mi25" EXIT INT TERM

for W in 190 185 180 175 170 165 160 155 150 145 140; do
  echo "=========== POWER POINT ${W}W START $(date -Iseconds) ==========="
  if ! bash $SCR/sweep_one_point.sh "$W"; then
    rc=$?
    echo "!!! sweep_one_point ${W}W failed rc=$rc → スイープ中断 !!!"
    break
  fi
  echo "=========== POWER POINT ${W}W DONE $(date -Iseconds) ==========="
done 2>&1 | tee -a $SCR/sweep_master.log

# 後始末: 元の 160 W に戻して終了
ssh mi25 'pkill -f bin/llama-server || true'
ssh mi25 'bash -s' < $SCR/set_power_cap.sh 160
```

実行は `nohup bash $SCR/sweep_loop.sh > $SCR/nohup.out 2>&1 &` で投入。約 9 時間の長時間ジョブで ssh 切断耐性を確保。進捗は `tail -f $SCR/sweep_master.log` か web ttyd (7682) で監視。

### 4. データ集計 (`make_summary.py` 拡張)

11 点ぶんの `trials_*.jsonl` + `kern_dmesg_*.log` + `telemetry_pcie_*.log` + `telemetry_rocmsmi_*.log` をパースし、以下の表 + PNG を生成:

| 表カラム | 抽出元 | 説明 |
|---|---|---|
| watts | TAG | 設定電力 |
| trials_completed | trials_*.jsonl | trial 中 `trial_done` イベントの数 |
| time_to_fault_s | kern_dmesg_*.log | 期前 anchor から最初の `GPU reset begin!` または `amdgpu_job_timedout` までの経過秒 (なし=null) |
| fault_card_bdf | kern_dmesg_*.log | dmesg から抽出 (期待: 87:00.0=8820) |
| fault_signature | kern_dmesg_*.log | `BACO reset` / `Memory access fault` 等の分類 |
| eval_tps_mean | trials_*.jsonl の `eval_tps` 平均 | trial 中の eval 平均 t/s |
| prompt_tps_mean | trials_*.jsonl の `pp_tps` 平均 | trial 中の prompt 平均 t/s |
| power_w_p95 | telemetry_rocmsmi_*.log | `Current Socket Graphics Package Power` の 95 パーセンタイル (設定値が効いたか) |
| junction_temp_max | telemetry_rocmsmi_*.log | 最大ジャンクション温度 |

PNG (`summary.png`): X 軸 = 電力 (140〜190W)、左 Y 軸 = `time_to_fault` 秒 (フォルト無しは上限線で表現)、右 Y 軸 = `eval_tps_mean`。各点を「緑 = anomaly 0 完走」「赤 = フォルト」で色分け。

### 5. 終了処理

- 電力制限を **160 W に復元** (`/etc/rc.local` 現状値と一致、再起動後の挙動を変えない)。
- llama-server **停止**、ttyd は維持 (ログ参照用)。
- `gpu-server` ロック **解放** (trap で確実に)。
- 電源は **ON のまま idle**。元レポート末尾と同じ最終状態。
- レポート: `report/2026-06-25_HHMMSS_mi25_4card_load_vulkan_pwr_sweep.md` を REPORT.md ルールに従って作成。プランファイルを `attachment/<basename>/plan.md` にコピー、生成物 (set_power_cap.sh, sweep_loop.sh, sweep_one_point.sh, run_campaign.sh, load_driver.py, telemetry*.sh, make_summary.py, 11 点ぶんの trials/campaign/dmesg/journal/rocm/telemetry, summary.png, data.md) も同 attachment に同梱。

## 検証

1. **電力制限が実際に効いているか**: 各電力点で `maxpower_${TAG}.txt` と `cat power1_cap` の両方を採取・突合。`telemetry_rocmsmi_${TAG}.log` の `Current Socket Graphics Package Power` p95 が設定値の ±5W に収まるか確認。
2. **フォルト署名の一貫性**: dmesg に `87:00.0` (=8820) で `amdgpu_job_timedout` → `BACO reset` → `VRAM is lost` の系列が出ているか。違うカードが出た場合は別現象として注記。
3. **llama-server の生存判定**: 各点完了後の `/health` 応答コードを `tail` で確認 (200 → 完走、000 → クラッシュ)。
4. **物理層健全性**: `telemetry_pcie_${TAG}.log` 全 11 点で `link_speed=8 GT/s`, `link_width=16`, AER counter 増分 0 を継続確認 (PCIe 物理層障害混入の弁別)。
5. **次レポートの「対の表」**: 既存レポートの「枚数依存性表」を「電力依存性表」へ並べ替えて出す。表に空欄が残らないことが完走の指標。

## リスク

- **8820 が早期に永久死する可能性** (高電力連発で個体劣化)。各点完了後の `rocm_${TAG}_post.txt` で 4 枚認識継続を確認。劣化兆候があれば即報告し以降のテストを中止 (rc≠0 → sweep_loop が break する設計で自動的に守られる)。
- **電力切替が即時反映されない可能性**。`telemetry_rocmsmi_*.log` の `Current ... Power` で常時検証し、反映されていない点はレポートで明示。
- **mi25 SLOT4 の確率的 PCIe ドロップ再発** (memory: project_mi25_gpu4_pcie_dropout)。Phase 0 で枚数が 4 でなかった場合は電源再投入してから開始。スイープ中に発生したら `boot_state.log` の `gpu_count` 減少として観測されるので、各点開始の boot 記録を必ず確認。
- **総 9 時間中の長時間 ssh セッション切断**。`nohup` + `tee` でログ永続化、別 ssh での `tail -f` 監視で対処。run_campaign 自身も `ssh -o ConnectTimeout=...` で短い ssh 多用で耐性あり。
- **過去メモの「mi25 ハング再現負荷は確率的・11.5h でも 0」** (memory: project_mi25_hang_load_campaign) は今タスク非該当。本タスクは「既知の確定フォルト (Vulkan 8820 TDR @4 枚) の電力依存性測定」であってハング再現ではない。
