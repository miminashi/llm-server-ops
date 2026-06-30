# mi25 card-c48c4 SLOT6 移動 + Vulkan 8h 負荷試験 — fault Unique ID 単位再現確認

## 整合性再確認 (2026-06-30 更新)

ユーザ依頼で初版プランの矛盾点を再確認し、以下を修正:

1. **sudo 一貫性**: Phase 1 の `sudo dmesg` → `journalctl -k` で sudo 回避、Phase 3-3 の `sudo dmidecode` (SMBIOS) は前段で取得済かつ sudo 必須なため本試験ではスキップ、Phase 3-4 の `sudo rocm-smi --setpoweroverdrive` は AskUserQuestion でユーザ依頼 (明示)
2. **キャンペーン内部 sudo の取り扱い**: Phase 4 で `run_campaign_c48c4.sh` に BACO 後 power cap 再設定ブロック (`sudo rocm-smi`) を追加する場合は **Phase 6 のキャンペーン投入をユーザに実行依頼** (内部 sudo を含むため)。代替案として sudo を完全に外して warning ログだけにする選択肢も明示
3. **試験後運用変更必須**: post-swap で c48c4 = GPU[2] となるため、c48c4 除外 3 枚運用 (現行 `HIP_VISIBLE_DEVICES=0,1,2`) を続行するなら `0,1,3` に変更必要。試験設計テーブルと Phase 8 完了処理に追記
4. **過去スクリプトの実装確認結果** (Explore agent 報告): `run-8820-stand-alone.sh` (start.sh バイパス・直接 ssh 投入)、`run_campaign_8820.sh` (SCRATCH ハードコード・restart_llama 絶対パス・recover_from_hang lock 再取得)、`start.sh` (`detect_radv_vk_indices()` で GGML_VK_VISIBLE_DEVICES 強制上書き)、`lock.sh/unlock.sh` (第 2 引数で session_id)、`bmc-*.sh` すべて既存実装と整合。BACO 後 power cap 再設定ブロックのみ既存スクリプトに無いため新規追加が必要 (プランの想定通り)

下記の本文は上記修正反映済み。

## Context

直前レポート [report/2026-06-29_213624_mi25_4card_uniqueid_baseline.md](../../projects/llm-server-ops/report/2026-06-29_213624_mi25_4card_uniqueid_baseline.md) の続編。

- 4 枚 baseline で過去 fault 集中個体 = **`card-c48c4` (Unique ID `0x21501edbcec48c4`)** と確定済み (4 枚運用時 BDF 87:00.0 = 過去 GUID 8820 = この Unique ID)
- 過去 stand_alone_24h ([2026-06-29_041700](../../projects/llm-server-ops/report/2026-06-29_041700_mi25_8820_stand_alone_24h.md)) は c48c4 を **その当時の SLOT8 (BDF 87:00.0)** で 24h 単独可視化負荷 → 147 trial / 2 fault (1.36%) で (b) 個体ロジック起因確定済 (c) multi-GPU 経路は微小寄与の可能性のみ
- **未検証**: fault が `card-c48c4` の ASIC 個体不変な欠陥なのか、SLOT8/BDF 87:00.0 そのもの (基板側 PCIe レーン / 熱 / 電源等) に依存しているのか — 過去試験は常に SLOT8 で行われていた

本試験では **c48c4 を SLOT6 (BDF 84:00.0) に物理移動して同じ負荷を当てる** ことで、fault が個体 (Unique ID) に追従するか否かを直接弁別する。AB swap 設計により対照 (SLOT8 元位置の `card-448c4`) も同時観測可能。

期待される最終出力:
- fault が SLOT6 (= c48c4 新位置) で stand_alone_24h と同シグネチャ再現 → **(b) Unique ID 単位確定** = 物理交換しか道なし
- fault が SLOT8 (= 448c4 新位置) で発火 → **(b) 揺らぎ** = 基板/SLOT8 側起因の可能性、物理交換だけでは救えない可能性
- 0 fault → サンプル不足 (8h で期待 0.4-0.5 件、P(0 fault)≒60-66%)、追加試行の必要性のみ示唆

## 試験設計の確定事項

| 項目 | 値 | 根拠 |
|---|---|---|
| 移動先 SLOT | **SLOT6 (BDF `84:00.0`)** | CPU2/NUMA1/SLOT8 と同じ root、apples-to-apples 比較 (ユーザ承認済) |
| 物理 swap | **AB swap** (`card-c48c4` ↔ `card-448c4`) | post-swap も 4 枚装着保持、対照観測あり |
| バックエンド | Vulkan/RADV (master 追従、`build-vulkan/bin/llama-server`) | stand_alone_24h と同等 |
| 可視化 | `GGML_VK_VISIBLE_DEVICES=2` | post-swap で c48c4 = GPU[2] (BDF 84:00.0) |
| モデル / ctx / KV | Qwen3-8B Q6_K / ctx=131072 (実 cap 40960) / `--cache-type-k q8_0 --cache-type-v q8_0` | 同上 |
| ub / batch / FA | `-ub 2048 -b 2048 --flash-attn 1 --poll 0` | 同上 |
| 電力 cap | 160W (`sudo rocm-smi --setpoweroverdrive 160 -d 2`) | 同上、device idx のみ 3→2 |
| TRIAL_SEC | 720s (12 分) | 同上 |
| PHASE_CAP_SEC | **28800s (8h)** | 6-8h の上値、自動再起動付きで安全 |
| MAX_TRIALS / MIN_TRIALS / HANG_SAFETY | **60 / 20 / 5** | 8h で trial 30-40 想定、安全マージン半減 |
| 試験後処理 | 電源 ON 維持・**シャットダウンせず保留** | ユーザ判断 (次セッションで追加試行/復元判断) |

**試験後運用上の注意 (HIP_VISIBLE_DEVICES 変更必須)**: 現行運用 (CLAUDE.md / メモリ project_mi25_gpu4_pcie_dropout) は `HIP_VISIBLE_DEVICES=0,1,2` で c48c4 (= GPU[3]) 除外の 3 枚 48GB 運用。**post-swap で c48c4 は GPU[2] になる**ため、本試験後に運用続行 (c48c4 除外 3 枚運用) するなら `HIP_VISIBLE_DEVICES=0,1,3` に変更必要。試験後にユーザが c48c4 を元 SLOT8 に戻すか SLOT6 のまま運用するかで以下のとおり分岐:

| 試験後の物理配置 | 運用時の HIP_VISIBLE_DEVICES (c48c4 除外 3 枚) |
|---|---|
| c48c4 = SLOT8 (試験前と同じ、元に戻す) | `0,1,2` (現行値、変更不要) |
| **c48c4 = SLOT6 (試験後そのまま放置)** | **`0,1,3`** (変更必要) |

**統計的留意点**: 過去発火率 1.36% → 8h × 30-40 trial で期待 fault 0.4-0.5 件、P(0 fault)≒60-66%。**0 件でも (b) 否定にはならない**ことを最初に明記。

## AB swap 期待値 (post-swap baseline)

GUID は KFD allocation で BDF 決定論的なので物理 swap で値は変わらず、**Unique ID のみが入れ替わる**:

| GPU# | BDF | GUID | Unique ID (期待) | 略称 (期待) | 状態 |
|---|---|---|---|---|---|
| GPU[0] | `04:00.0` | 29525 | `0x2150172bdcc3164` | `card-c3164` | 不動 |
| GPU[1] | `07:00.0` | 33301 | `0x2150040969a48e4` | `card-a48e4` | 不動 |
| **GPU[2]** | **`84:00.0`** | **54068** | **`0x21501edbcec48c4`** | **`card-c48c4`** | **★ 移動 / 試験対象** |
| GPU[3] | `87:00.0` | 8820 | `0x215026e14c448c4` | `card-448c4` | ↔ swap、対照位置 |

**swap 成功判定**: `rocm-smi --showuniqueid` で GPU[2] (BDF 84:00.0) の Unique ID が `0x21501edbcec48c4` (= `card-c48c4`)、GPU[3] (BDF 87:00.0) が `0x215026e14c448c4` (= `card-448c4`) であること。不一致なら STOP しユーザに装着確認を依頼。

## 実施手順

### Phase 0: 事前準備 [5 min]

```bash
export TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)
export REPORT_NAME="${TS}_mi25_c48c4_slot_move_load"
export ATTACH_DIR="report/attachment/${REPORT_NAME}"

# mi25 ロック取得 (本セッション専有)
.claude/skills/gpu-server/scripts/lock.sh mi25 "c48c4-slot-move-${TS}"

# 添付ディレクトリ + プランファイル copy
mkdir -p "$ATTACH_DIR"
cp /home/ubuntu/.claude/plans/report-2026-06-29-213624-mi25-4card-uniq-virtual-charm.md "$ATTACH_DIR/plan.md"

# 過去スクリプトを copy → リネーム
SRC="report/attachment/2026-06-27_183151_mi25_8820_stand_alone_24h"
cp "$SRC/load_driver.py" "$SRC/telemetry.sh" "$SRC/telemetry_pcie.sh" "$ATTACH_DIR/"
cp "$SRC/run-8820-stand-alone.sh"  "$ATTACH_DIR/run-c48c4-slot6.sh"
cp "$SRC/run_campaign_8820.sh"     "$ATTACH_DIR/run_campaign_c48c4.sh"
cp "$SRC/make_summary_standalone.py" "$ATTACH_DIR/make_summary_slot_move.py"
```

### Phase 1: Pre-swap 状態保全 [5 min]

```bash
# 現在 (2026-06-29 21:14 JST baseline と同じ) 配置の再確認
ssh mi25 'lspci | grep -cE "Vega 10 \[Instinct"; lspci -nn | grep -E "Vega 10 \[Instinct"; rocm-smi -i 2>/dev/null | grep -E "GPU\[|GUID|Subsystem"; rocm-smi --showuniqueid 2>/dev/null; rocm-smi --showbus 2>/dev/null' \
  | tee "$ATTACH_DIR/pre_swap_4card_baseline.txt"

# 期待: GPU[3] (87:00.0) = card-c48c4。不一致なら STOP し物理状態確認。
# kernel log は sudo 回避のため journalctl -k を使用 (一般 user で読める)
ssh mi25 'journalctl -k --no-pager 2>/dev/null | tail -200' > "$ATTACH_DIR/pre_swap_dmesg_tail.txt"
ssh mi25 'uname -a; uptime' > "$ATTACH_DIR/pre_swap_sysinfo.txt"
```

### Phase 2: shutdown → AB swap → boot [20 min、内ユーザ物理作業 ~10 min]

```bash
# 2-1. 電源 OFF (soft = ACPI shutdown)
.claude/skills/gpu-server/scripts/bmc-power.sh mi25 soft
# off 確定待ち
until .claude/skills/gpu-server/scripts/bmc-power.sh mi25 status | grep -qi off; do sleep 5; done
```

**2-2. ユーザに物理 AB swap を依頼** (AskUserQuestion で「完了報告」を取得):
- SLOT8 のカード (= 付箋 `c48c4`) を抜く
- SLOT6 のカード (= 付箋 `448c4`) を抜く
- `c48c4` を SLOT6 へ、`448c4` を SLOT8 へ装着
- 付箋ラベル (末尾 5 桁) で物理同一性を確認

```bash
# 2-3. ユーザ完了報告後、電源 ON
.claude/skills/gpu-server/scripts/bmc-power.sh mi25 on

# 2-4. SSH 復帰待機 (最大 300s)
for i in $(seq 1 60); do
  ssh -o ConnectTimeout=5 -o BatchMode=yes mi25 true 2>/dev/null && break
  sleep 5
done
```

### Phase 3: Post-swap baseline 確認 [10 min]

```bash
# 3-1. Post-swap 4 枚 baseline
ssh mi25 'lspci | grep -cE "Vega 10 \[Instinct"; lspci -nn | grep -E "Vega 10 \[Instinct"; rocm-smi -i 2>/dev/null | grep -E "GPU\[|GUID|Subsystem"; rocm-smi --showuniqueid 2>/dev/null; rocm-smi --showbus 2>/dev/null' \
  | tee "$ATTACH_DIR/post_swap_4card_baseline.txt"

# 3-2. swap 成功判定 (Claude が出力解析): GPU[2]=c48c4 / GPU[3]=448c4 を確認
#      不一致なら Phase 2 にリトライ (ユーザに再装着依頼)

# 3-3. lspci PCIe tree のみ取得 (SMBIOS dmidecode は sudo 必須かつ前段 baseline で取得済み・CLAUDE.md L60-63 にメモあり → 本試験ではスキップ)
ssh mi25 'lspci -tnnv' > "$ATTACH_DIR/post_swap_lspci_tree.txt"
```

**3-4. 電力 cap 160W 設定** (sudo は CLAUDE.md ルール上ユーザ依頼必須 → AskUserQuestion で下記コマンドの実行を依頼):

```bash
# ユーザに実行を依頼するコマンド (Claude 直接実行禁止):
ssh mi25 'sudo rocm-smi --setpoweroverdrive 160 -d 2'

# 設定確認 (sudo 不要、Claude が実行可能)
ssh mi25 'rocm-smi --showmaxpower' | tee -a "$ATTACH_DIR/post_swap_4card_baseline.txt"
```

### Phase 4: スクリプト修正 [5 min]

**`$ATTACH_DIR/run-c48c4-slot6.sh`** (元 `run-8820-stand-alone.sh` から修正):
- `GGML_VK_IDX="3"` → **`GGML_VK_IDX="2"`** のみ

**`$ATTACH_DIR/run_campaign_c48c4.sh`** (元 `run_campaign_8820.sh` から修正):
- `SCRATCH=...8820_stand_alone_24h` → `SCRATCH="$ATTACH_DIR"` (絶対パス)
- `record_boot_state` の reset_type ラベル → `phase-start-vulkan-c48c4-slot6`
- `PHASE_CAP_SEC` default `86400` → **`28800` (8h)**
- `MAX_TRIALS` `200` → **`60`**、`MIN_TRIALS` `80` → **`20`**、`HANG_SAFETY` `10` → **`5`**
- `restart_llama` 内の `run-8820-stand-alone.sh` 参照を **`run-c48c4-slot6.sh`** に置換
- **BACO 後の power cap 160W 自動再設定ブロック追加** (stand_alone_24h 副次発見への対処): `restart_llama` 成功後に `ssh mi25 'sudo rocm-smi --setpoweroverdrive 160 -d 2'` を実行
  - **重要**: 内部 sudo を含むため、Phase 6 のキャンペーン投入は **Claude が直接実行せず、ユーザに実行依頼** (CLAUDE.md「sudo は ssh 先含めユーザ依頼」ルール準拠)
  - 代替案 (sudo を完全に外す): `rocm-smi --showmaxpower` で cap drop を検出し warning ログを残すだけ・自動再設定なし。この場合は BACO 復帰後 cap が 220W に戻り、stand_alone_24h と同等の挙動。実装簡素化を優先するならこちらでも可
- `recover_from_hang` の lock session_id を `c48c4-slot-move-${TS}` に

**`$ATTACH_DIR/make_summary_slot_move.py`** (集計図):
- GPU[3]→GPU[2] 解析切替
- 比較対象を 2 種類化: 4 枚運用 (88 trial / 3 fault) と stand_alone_24h SLOT8 (147 trial / 2 fault) **両方**との Fisher exact
- summary.png タイトル: `c48c4 SLOT6 移動 / Vulkan stand-alone 8h — N trials, K faults`

`load_driver.py` / `telemetry.sh` / `telemetry_pcie.sh` はそのまま流用。

### Phase 5: smoke test [5 min]

```bash
# 初回起動 (ラッパ内で /health 待機)
CTX_SIZE=131072 bash "$ATTACH_DIR/run-c48c4-slot6.sh"

# health + chat smoke
curl -sf -m 5 http://10.1.4.13:8000/health | tee "$ATTACH_DIR/smoke_health.json"
curl -sf -m 30 http://10.1.4.13:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"unsloth/Qwen3-8B-GGUF:Q6_K","messages":[{"role":"user","content":"Say OK."}],"max_tokens":8,"temperature":0}' \
  | tee "$ATTACH_DIR/smoke_chat.json"

# GPU[2] のみ VRAM 使用されているか (他 GPU は idle)
ssh mi25 'rocm-smi --showmemuse --showpower' | tee "$ATTACH_DIR/smoke_rocmsmi.txt"
```

smoke 失敗時は STOP し原因切り分け (装着 / Vulkan idx / モデルパス)。

### Phase 6: 8h キャンペーン投入 [1 min]

**重要**: `run_campaign_c48c4.sh` 内部に `sudo rocm-smi --setpoweroverdrive` (BACO 後 power cap 自動再設定) を含む場合は **ユーザに実行を依頼** (CLAUDE.md sudo ルール準拠)。sudo 完全排除版を採用した場合のみ Claude 直接投入可。

```bash
# 既存 llama-server を停止 (smoke test 終了後の重複起動回避)
ssh mi25 'pkill -f bin/llama-server' || true; sleep 5

# 以下のコマンドをユーザに実行依頼 (内部 sudo を含むため):
cd /home/ubuntu/projects/llm-server-ops && \
  MAX_TRIALS=60 MIN_TRIALS=20 HANG_SAFETY=5 PHASE_CAP_SEC=28800 TRIAL_SEC=720 CTX_SIZE=131072 \
  nohup bash "<ATTACH_DIR>/run_campaign_c48c4.sh" \
  > "<ATTACH_DIR>/nohup.out" 2>&1 < /dev/null &
echo "campaign pid=$!"

# 投入確認 (Claude が実行可能 = sudo 不要):
ssh mi25 'ps -ef | grep -E "run_campaign|bin/llama-server" | grep -v grep'
tail -20 "$ATTACH_DIR/nohup.out"
```

### Phase 7: 監視 [6-8h、~1h 間隔]

- `tail -50 $ATTACH_DIR/campaign_vulkan.log` で trial 進捗 / hang 件数
- `tail -100 $ATTACH_DIR/kern_dmesg.log | grep -E "amdgpu|page fault|GPU reset|BACO"` で fault 早期検出
- `tail -50 $ATTACH_DIR/llama_server.log` で crash 兆候
- `ping -c 1 10.1.4.7` (BMC) + `ping -c 1 10.1.4.13` (host) で OS ハング検出
- **OS ハング検知時は電源リセット前に必ず `bmc-screenshot.sh mi25 $ATTACH_DIR/hang_bmc.png`** (CLAUDE.md 必須)

### Phase 8: 完了処理 [30 min]

```bash
# campaign 終了確認
tail -30 "$ATTACH_DIR/campaign_vulkan.log"

# 後片付け
ssh mi25 'pkill -f bin/llama-server' || true
[ -f "$ATTACH_DIR/telemetry.pids" ] && xargs -r kill < "$ATTACH_DIR/telemetry.pids"
[ -f "$ATTACH_DIR/telemetry_pcie.pid" ] && xargs -r kill < "$ATTACH_DIR/telemetry_pcie.pid"
pkill -f "dmesg -w" || true
pkill -f "tail -F /tmp/llama-server.log" || true

# 集計図生成
python3 "$ATTACH_DIR/make_summary_slot_move.py"

# 試験後 baseline (物理同一性 / Unique ID 不変性最終確認)
ssh mi25 'rocm-smi --showuniqueid; rocm-smi --showbus' | tee "$ATTACH_DIR/post_test_4card_baseline.txt"

# 電源 ON 維持 (シャットダウンせず、c48c4 は SLOT6 のまま、次セッションに引き継ぎ)
# 注: c48c4 が SLOT6 = GPU[2] のままなので、c48c4 除外 3 枚運用に戻すなら
#     start.sh の HIP_VISIBLE_DEVICES を 0,1,2 → 0,1,3 に変更必要 (本セッションでは変更しない、
#     ユーザが次セッションで判断)

# mi25 ロック解放
.claude/skills/gpu-server/scripts/unlock.sh mi25 "c48c4-slot-move-${TS}"
```

## 判定フロー

| ケース | 観測 | 判定 | 次アクション |
|---|---|---|---|
| **(A) 期待ケース** | BDF `84:00.0` で stand_alone_24h 完全同一シグネチャ (SQC+CB バースト / ring 88 / pasid 32772 / BACO / vk::DeviceLost) | **(b) Unique ID 単位確定** | `card-c48c4` 物理交換確定、新品 MI25 調達 |
| **(B) 非典型シグネチャ** | BDF 84:00.0 で fault も SQC+CB バースト並びが異なる / ring 他 | (b) 確証ではなく要追検 | 別 fault モード分析、次セッション課題化 |
| **(C) 揺らぎ** | BDF `87:00.0` (= 移動後 `card-448c4`) で同シグネチャ | **(b) 揺らぎ** = slot/基板/熱起因の可能性 | SLOT8 そのものを疑う方向に転換 (SLOT8 単独試験提案) |
| **(D) 0 fault** | 8h 期間 fault なし | **(b) 否定にはならない** (期待 0.4-0.5 件、P(0)≒60-66%) | 追加 8-16h or 24h 拡張提案 |
| **(E) OS ハング** | SSH/ping 不通 | 経路喪失 / kernel panic | **BMC スクショ保全 → bmc-power.sh reset** (CLAUDE.md 必須) |

## 過去スクリプト再利用方針

| スクリプト | 修正内容 |
|---|---|
| `run-8820-stand-alone.sh` | `GGML_VK_IDX=2` のみ変更 → `run-c48c4-slot6.sh` |
| `run_campaign_8820.sh` | SCRATCH / PHASE_CAP / MAX/MIN/HANG_SAFETY / restart_llama 参照 / boot label / BACO 後 power cap 再設定追加 → `run_campaign_c48c4.sh` |
| `load_driver.py` | 変更なし (流用) |
| `telemetry.sh` / `telemetry_pcie.sh` | 変更なし (per-GPU 全部記録、解析側で GPU[2] 抽出) |
| `make_summary_standalone.py` | GPU[3]→GPU[2]、Fisher 比較 2 種類化 → `make_summary_slot_move.py` |
| `bmc-power.sh` / `bmc-screenshot.sh` / `lock.sh` / `unlock.sh` | そのまま使用 |

## 添付・レポート構成 (REPORT.md L18-27 準拠)

`report/${TS}_mi25_c48c4_slot_move_load.md` 本体構成:

1. タイトル (50 字以内)
2. `## 添付ファイル` (plan.md / pre/post swap baseline / lspci / SMBIOS / smoke / 各スクリプト / campaign log / kern_dmesg / llama_server log / telemetry / trials.jsonl / hang_*.png / post_test_baseline / data.md / summary.png)
3. `## 核心発見サマリ` (summary.png 埋め込み + 主要結論 5 件、メモリ feedback ルール準拠)
4. `## 前提・目的` (本プランの目的)
5. `## 環境情報` (SLOT 配置 + post-swap 期待値 + 実測値表)
6. `## 再現方法` (Phase 1-8 サマリ)
7. `## 観測データ` (trial 数 / fault 件数 / シグネチャ照合 / 時間バケット推移)
8. `## スロット位置の移動記録` (pre/post swap の Unique ID + BDF + GUID + 略称表を時系列で 3 点 (pre / post-swap / post-test))
9. `## 判定` (判定フロー (A)-(E) のどれに該当 + Fisher exact + 結論)
10. `## 過去 fault シグネチャとの完全照合表` (stand_alone_24h R1/R2 + 本試験 fault の各項目比較)
11. `## 残課題 / 次セッションのタスク`
12. `## 参照レポート` (uniqueid_baseline / stand_alone_24h / vram_memtest / 4card_load 各種)

## 時間配分概算

| Phase | 内容 | 時間 |
|---|---|---|
| 0-1 | 準備 + Pre-swap 保全 | 10 min |
| 2 | shutdown + AB swap + boot | 20 min |
| 3-4 | post-swap 確認 + スクリプト修正 | 15 min |
| 5 | smoke test | 5 min |
| 6 | キャンペーン投入 | 1 min |
| 7 | **8h 監視** (定期チェック並走) | **6-8 h** |
| 8 | 完了処理 + 集計 + post-test baseline | 30 min |
| 9 | レポート執筆 | 30-60 min |
| **合計** | | **約 8-10 h** (ハンズオン 1.5h + 監視 6-8h) |

## 制約遵守チェック

- [x] GPU サーバ使用 = `gpu-server` スキル経由のロック取得 (Phase 0 で `lock.sh mi25`)
- [x] スクリプト実行はプロジェクトルートからの相対パス (`.claude/skills/...`)
- [x] **sudo はすべてユーザ依頼** (ssh 先含む):
  - Phase 1 の kernel log 取得は `journalctl -k` で sudo 回避済
  - Phase 3-3 の SMBIOS dmidecode はスキップ (前段で取得済かつ sudo 必須)
  - Phase 3-4 の `sudo rocm-smi --setpoweroverdrive 160 -d 2` は AskUserQuestion で依頼
  - Phase 6 のキャンペーン投入は (内部 sudo を含む場合) ユーザ依頼
  - bmc-power.sh / bmc-screenshot.sh は ipmitool 経由 (Claude 側で sudo 不要)
- [x] OS ハング検知時は電源リセット前に必ず `bmc-screenshot.sh` (Phase 7 / 判定 (E))
- [x] plan mode → 対応レポート作成必須 (Phase 9、添付に plan.md 含める)
- [x] タイムスタンプは `TZ=Asia/Tokyo date` (Phase 0、推測禁止)
- [x] 末尾 5 桁略称ルール (`card-c48c4` / `card-448c4` 等)
- [x] Unique ID で個体識別、GUID は個体追跡に使わない
- [x] 試験後運用注記 (`HIP_VISIBLE_DEVICES` 0,1,2 → 0,1,3 への変更必要性) を明示

## Critical Files (修正・新規作成対象)

- `/home/ubuntu/projects/llm-server-ops/report/attachment/${TS}_mi25_c48c4_slot_move_load/plan.md` (新規 = 本プラン copy)
- `/home/ubuntu/projects/llm-server-ops/report/attachment/${TS}_mi25_c48c4_slot_move_load/run-c48c4-slot6.sh` (新規 = 元 `run-8820-stand-alone.sh` から `GGML_VK_IDX=2` 変更)
- `/home/ubuntu/projects/llm-server-ops/report/attachment/${TS}_mi25_c48c4_slot_move_load/run_campaign_c48c4.sh` (新規 = 元 `run_campaign_8820.sh` から SCRATCH/PHASE_CAP/MAX/MIN/HANG_SAFETY/restart_llama 参照/BACO 後 power cap 再設定)
- `/home/ubuntu/projects/llm-server-ops/report/attachment/${TS}_mi25_c48c4_slot_move_load/make_summary_slot_move.py` (新規 = 元 `make_summary_standalone.py` から GPU[3]→GPU[2] / Fisher 比較 2 種類化)
- `/home/ubuntu/projects/llm-server-ops/report/${TS}_mi25_c48c4_slot_move_load.md` (新規 = レポート本体)

## 参照

- [前段 baseline (本試験の直接前提)](/home/ubuntu/projects/llm-server-ops/report/2026-06-29_213624_mi25_4card_uniqueid_baseline.md)
- [stand_alone_24h (再現対象シグネチャ)](/home/ubuntu/projects/llm-server-ops/report/2026-06-29_041700_mi25_8820_stand_alone_24h.md)
- [Unique ID 識別 (運用ルール根拠)](/home/ubuntu/projects/llm-server-ops/report/2026-06-29_191721_mi25_gpu_card_id_unique_id.md)
- [memtest_vulkan (a) 否定](/home/ubuntu/projects/llm-server-ops/report/2026-06-27_071959_mi25_8820_vram_memtest.md)
- [4card_load_vulkan](/home/ubuntu/projects/llm-server-ops/report/2026-06-25_145006_mi25_4card_load_vulkan.md) / [vulkan_pwr_sweep_v2](/home/ubuntu/projects/llm-server-ops/report/2026-06-26_210732_mi25_4card_load_vulkan_pwr_sweep_v2.md) (過去 fault データ源)
- CLAUDE.md (GPU サーバ運用ルール、Unique ID 識別ルール、bmc-screenshot 必須ルール)
- REPORT.md (レポート作成ルール、添付ディレクトリ規約)
