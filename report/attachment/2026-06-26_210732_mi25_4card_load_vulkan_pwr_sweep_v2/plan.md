# mi25 4枚 Vulkan 電力スイープ追試 (確率再現性検証) 計画

## Context

[2026-06-26_081718 原 電力スイープレポート](/home/ubuntu/projects/llm-server-ops/report/2026-06-26_081718_mi25_4card_load_vulkan_pwr_sweep.md) で 140-190W (5W刻み 11点) スイープを実施した結果、**11点中 3点 (175W / 155W / 150W) で 8820 (SLOT6 / 87:00.0) が `[gfxhub0] page fault → amdgpu_job_timedout → BACO reset → VRAM lost` フォルトを起こした**が、電力に対して **非単調** (180W PASS → 175W FAULT → 170-160W 3連続 PASS → 155W FAULT → 150W FAULT → 145-140W PASS) で、結論は「電力では救えない」「per-card 実消費 36-39W に対し cap=140W でも cap が効いていない」だった。

このフォルト分布が **(A) 電力点固有の現象** (同じ 175/155/150W で再発火する) なのか、**(B) 確率的な発火を電力スイープで時系列観測しているだけ** なのかが、原実験 1 回だけでは弁別できていない。本タスクは原実験を **完全同条件で再実施** し、フォルト点・時系列・シグネチャを直接比較することで (A) と (B) を弁別し、加えて per-card power の再現性 / 8820 の再発火率 / time_to_fault 分布の追加観測を行う。

期待される新発見:
- **同じ 175/155/150W で再発火**: 個体・電力点固有モード強化 (原因究明の手掛かり)
- **別の点で発火**: 確率的揺らぎ説強化、原実験の「非単調」も単なる順序内ランダム発火
- **発火 0 件**: 8820 故障の進行性質 (劣化/回復可能性)
- **発火 6 件以上**: 個体劣化進行のシグナル → 8820 物理対応の緊急度上昇

## 前提・目的

- **目的**: 原実験 (sweep_loop.sh / sweep_one_point.sh / set_power_cap.sh / run_campaign.sh / load_driver.py / telemetry*.sh / make_summary.py) と **完全に同じ仕様** で 11 電力点 × Phase 1 (4枚 Vulkan) × MAX_TRIALS=4 を回し、原レポートと直接比較する。
- **進行順**: **190 → 140W (高→低 5W 刻み 11点)** — 原と同じ (確率的揺らぎ vs 電力点固有の弁別を最もクリーンにするため、変数は「実行回」だけに絞る)
- **試行設定**: `MAX_TRIALS=4 MIN_TRIALS=4 PHASE_CAP_SEC=3000 TRIAL_SEC=720` — 原と同じ
- **モデル/起動**: `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` ctx=131072、Vulkan 4枚 `MI25_BACKEND=vulkan`、起動は `.claude/skills/llama-server/scripts/llama-up.sh` (元レポートと同パラメータ自動)
- **前提条件**:
  - mi25 利用可 (確認済: ロック available)。`gpu-server` ロック取得後に開始
  - 4枚復旧維持 (確認済: `lspci | grep -c "Instinct MI25"` = 4、power_cap 160W で起動中)
  - Vulkan (RADV、`build-vulkan/` master 追従) のみで実施。ROCm 比較は対象外
  - `power1_cap` 制御は `set_power_cap.sh`、hwmon パス動的解決、NOPASSWD sudo (検証済)
  - 想定総時間: 約 **9時間** (原実績 9h 5min)

## スイープ仕様 (原と完全同一)

| 項目 | 値 |
|------|----|
| 電力点 | 190, 185, 180, 175, 170, 165, 160, 155, 150, 145, 140 (W) — 高→低 |
| 構成 | Vulkan, 4枚 (`GGML_VK_VISIBLE_DEVICES=0,1,2,3` auto) |
| 起動パラメータ | `--n-gpu-layers 99 --split-mode layer --flash-attn 1 --poll 0 -b 2048 -ub 2048 --cache-type-{k,v} q8_0` |
| 試行設定 | `MAX_TRIALS=4 MIN_TRIALS=4 PHASE_CAP_SEC=3000 TRIAL_SEC=720` |
| 早期打ち切り | なし (全 11 点完走)。`run_campaign` rc≠0 のみ中断 |
| 1点あたり想定時間 | 安定 ≈ 2880s、フォルト時 ≈ 8-1500s + 残 trial 空回り |

## 設計

### 0. スクラッチパッド準備

原実験の全スクリプトを **新スクラッチパッド** にコピーし、`SCRATCH=` のセッション固有パスのみ書き換える。コピー元: `report/attachment/2026-06-26_081718_mi25_4card_load_vulkan_pwr_sweep/`

| ファイル | 流用 / 改変 |
|---|---|
| `run_campaign.sh` | 流用、`SCRATCH=` を新パスへ書き換え (sed/Edit) |
| `load_driver.py` | 流用 (改変なし) |
| `telemetry.sh` | 流用 (改変なし) |
| `telemetry_pcie.sh` | 流用 (改変なし) |
| `make_summary.py` | 流用 (改変なし。原実験と同列の data.md + summary.png を生成) |
| `set_power_cap.sh` | 流用 (改変なし) |
| `sweep_one_point.sh` | 流用、`SCRATCH=` を新パスへ書き換え |
| `sweep_loop.sh` | 流用、`SCR=` を新パスへ書き換え |

新規スクリプトは作成しない (原と仕様一致を保証するため)。

### 1. 実行手順

```bash
SCR=<新スクラッチパッド絶対パス>
SRC=report/attachment/2026-06-26_081718_mi25_4card_load_vulkan_pwr_sweep

# 0. ロック取得
.claude/skills/gpu-server/scripts/lock.sh mi25

# 1. スクリプト一式コピー
cp $SRC/{run_campaign.sh,load_driver.py,telemetry.sh,telemetry_pcie.sh,make_summary.py,\
set_power_cap.sh,sweep_one_point.sh,sweep_loop.sh} $SCR/

# 2. SCRATCH/SCR を新セッションパスへ書き換え (Edit で3ファイル)
#    - run_campaign.sh    L16  SCRATCH=...
#    - sweep_one_point.sh L7   SCR=...
#    - sweep_loop.sh      L5   SCR=...

# 3. 開始前の現状記録
ssh mi25 'rocm-smi --showmaxpower' > $SCR/maxpower_pre.txt
ssh mi25 'lspci | grep "Instinct MI25"' > $SCR/lspci_pre.txt

# 4. スイープ投入 (nohup でセッション切断耐性)
nohup bash $SCR/sweep_loop.sh > $SCR/nohup.out 2>&1 &

# 5. 進捗監視 (別ターミナル / 必要なら)
tail -f $SCR/sweep_master.log

# 6. 完走後の集計
cd $SCR && python3 make_summary.py  # data.md + summary.png 生成
```

実行中の中断条件: `sweep_one_point.sh` から rc≠0 が返れば `sweep_loop.sh` が break。電源リセット系のフォルトは `run_campaign` 内 BMC リセットで自動復旧 (rc=42 経路)。8820 のフォルトは `server_error_transient` (rc=0) で run_campaign は完走するので、スイープは中断しない。

### 2. 後始末 (sweep_loop.sh 末尾で自動)

- 電力 cap を **160W に復元** (rc.local 既定値、原と同じ)
- llama-server 停止
- 電源 ON のまま idle、4枚認識継続を確認
- `gpu-server` ロック解放 (レポート作成完了後に手動)

### 3. 比較分析 (新発見を狙う主軸)

集計後、**原実験との直接比較表** をレポートに含める。比較すべき項目:

| 比較項目 | 原実験 (1回目) | 再実験 (2回目) | 何が言えるか |
|---|---|---|---|
| FAULT 点 (W) | 175 / 155 / 150 | (実測) | **同一点で再発火 → 電力点固有 / 別点 → 確率的** |
| FAULT 件数 / 11 点 | 3 件 | (実測) | 8820 個体の発火率推定 (n=2 で粗いが) |
| 発火カード BDF | 全 3 件 87:00.0 (8820) | (実測) | 8820 起因の再現性 |
| time_to_fault [s] | 175W=183 / 155W=941 / 150W=1515 | (実測) | t2f が同電力点で同様の分布になるか |
| dmesg シグネチャ | page fault → TDR 連結、vmid:4/pasid:32772/ring:88 | (実測) | パターン再現性 |
| per-card power p95 PASS 点 | 36-39 W | (実測) | cap=140W でも cap 非到達の再現 |
| eval_tps_mean | 16.0-16.3 t/s (全点) | (実測) | スループット安定性 |
| Tj_max PASS 点 | 48-58 °C | (実測) | 熱挙動の再現 |
| PCIe AER | 全点 0 / 全点 width=16 / speed=8GT/s | (実測) | 物理層健全性継続 |

### 4. レポート作成

- ファイル名: `report/<TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S>_mi25_4card_load_vulkan_pwr_sweep_v2.md` (タイムスタンプは実施完了時に取得)
- タイトルは 50 字以内で簡潔に (例: 「mi25 4枚 Vulkan 電力スイープ追試 — 8820 フォルト分布の確率再現性検証」)
- 核心発見サマリに `summary.png` を先頭埋め込み
- 比較表 (上記 §3) を独立セクションで掲載し、(A)/(B) の弁別結論を明示
- 添付:
  - プランファイルを `report/attachment/<basename>/plan.md` にコピー
  - 11 点ぶんの trials/campaign/dmesg/journal/rocm/telemetry/summary.png/data.md/全スクリプト
- 参照: 原電力スイープレポート / 原 Vulkan 4枚負荷 / 原 ROCm 4枚負荷 / 物理復旧

## 検証

1. **電力 cap が実際に反映されているか**: 各点で `maxpower_${TAG}.txt` と `telemetry_rocmsmi_${TAG}.log` の `Current Socket Graphics Package Power` を採取・突合 (原と同じ手法)
2. **フォルト署名の一貫性**: dmesg に `87:00.0` で page fault → TDR の連結シグネチャが出ているか
3. **物理層健全性**: 全 11 点で `telemetry_pcie_*.log` の AER カウンタ 0 / width=16 / speed=8GT/s 維持
4. **4枚認識継続**: `boot_state.log` の `gpu_count=4` 維持 (原電力スイープ 2026-06-26 04:52 完了時から本日プラン実行時まで idle 継続中)
5. **データ表完走**: `data.md` の 11 行 (140-190W) 全てに値が入る
6. **原との比較表**: §3 の表が完成し、(A)/(B) の弁別結論まで書ける

## リスク

- **8820 が累積劣化して全電力点で発火**: 原電力スイープ (本日 04:52 完了) からの再開なので個体熱履歴は近接。一連の負荷試験 (原 ROCm 4枚 + 原 Vulkan 4枚 + 原電力スイープ 11点 + 本再実験 11点) の累積で劣化が進めば 6 件以上のフォルトが出る可能性。即「8820 物理対応必須」の緊急度上昇として報告
- **mi25 SLOT4 確率的 PCIe ドロップ再発** (memory: project_mi25_gpu4_pcie_dropout): `boot_state.log` の `gpu_count` 減少で観測。発生時は電源再投入で復旧 (原と同じ手順)
- **9 時間長時間ジョブの ssh 切断**: `nohup` + `tee` でログ永続化、別 ssh の `tail -f` で監視。原実験で実証済
- **電力 cap 設定の sudo 失敗**: NOPASSWD 検証済だが、`sudo tee` で書き込めない場合は即中断 (set_power_cap.sh が exit 1)。再起動後 hwmon 番号が変わっていれば自動解決済
- **時間予算**: 約 9 時間。途中中断したい場合は `kill <pid>` で sweep_loop.sh を止め、その時点までのデータで集計可
