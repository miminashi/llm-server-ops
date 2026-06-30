# mi25 8820 個体 VRAM スキャン (memtest_vulkan)

## Context

mi25 4枚復旧後、SLOT6 / BDF 87:00.0 / GUID 8820 が累積 88 trial で 3 回フォルト (3/88 = 3.4%、TDR signature `vmid:4 / pasid:32772 / ring:88`)。直近 2026-06-26_210732 の電力スイープ追試で「電力点固有説否定 / 確率的揺らぎ説確定」となり、残る真因仮説は次の 3 つ:

- **(a)** 個体 VRAM bad page / トラップ電荷
- **(b)** コアロジック VM/MMU レジスタ層
- **(c)** multi-GPU 同期経路 (split-mode layer / PCIe tensor transfer)

本プランは **(a) を直接検査** する。bad page 検出 → 物理交換確定。0 件 → (a) 否定して推奨2 (8820 stand-alone 24h) で (b)/(c) へ進む弁別材料となる。本リポジトリで `memtest_vulkan` の利用実績はなく、初回投入。

## Goal

- 8820 (Vulkan idx 3) の VRAM を `memtest_vulkan v0.5.0` で多周回スキャンし、error count / address range を取得
- 健全 3 枚 (SLOT2/SLOT4/SLOT8) 各 1 周を対照として実施し、個体差を観測
- 真因仮説 (a) について「確定」「否定」「保留 (カバレッジ不足)」のいずれかを示す

## Scope

- **対象サーバ**: mi25 (10.1.4.13)、Ubuntu 22.04.5、RADV (Mesa 23.2.1) / Vulkan 1.4.313、4 枚復旧済み
- **対象ツール**: `memtest_vulkan v0.5.0` (pre-built linux x86_64 tarball)
- **対象 GPU**: 4 枚全て (Bus=04/07/84/87:00.0)、ただし主検査対象は Bus=0x87:00 (8820)
- **時間予算**: 約 4.5 時間 (取得 + help 確認 15min + ディスカバリ 5min + 健全 3 枚 計 25min + 8820 多周回 180min = long 120 + short 15×4 + 集計 30min + 予備 ~20min)
- **電力 cap**: 既定 160W のまま (本実験で変更しない)
- **llama-server**: 実験中は down (memtest_vulkan 専用)

## Implementation Plan

### 1. 準備

- `gpu-server` ロック取得 (`/.claude/skills/gpu-server/scripts/lock.sh mi25`)
- 前状態記録: `rocm-smi --showmaxpower` / `lspci | grep "Instinct MI25"` / カーネル dmesg リング初期化
- `llama-down.sh mi25` で llama-server 停止
- scratchpad 作成 + 過去スイープから `telemetry.sh` / `telemetry_pcie.sh` を流用 (パスのみ書き換え)

### 2. memtest_vulkan 取得 + 仕様確認

mi25 に Rust 未導入のため **pre-built バイナリ** を使う (cargo build は 30 分超 + LLVM 依存で非推奨)。

```
URL=https://github.com/GpuZelenograd/memtest_vulkan/releases/download/v0.5.0/memtest_vulkan-v0.5.0_DesktopLinux_X86_64.tar.xz
ssh mi25 'mkdir -p ~/memtest_vulkan && cd ~/memtest_vulkan && curl -sLO $URL && tar -xf *.tar.xz'
```

`VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.x86_64.json` で llvmpipe を排除して RADV 限定にする。

**仕様確認** (取得直後に必ず実施):
- `./memtest_vulkan --help` の出力をログに保存
- `--help` で iteration / batch / device 選択用 CLI フラグの有無を確認。フラグが存在すれば対話入力ではなくフラグ経由に切り替える (本プランは「フラグなし」を前提に設計しているが、あれば優先)
- README/COPYING も `tar -tf` で同梱物として確認

### 3. ディスカバリ (Bus → メニュー番号マップ)

`memtest_vulkan` は対話メニュー (推定 1〜4、10 秒タイムアウトで先頭自動選択)。メニュー順は **PCI Bus 昇順** が有力 (RADV は PCI 順で列挙、過去の Vulkan idx と一致) だが、確認のためディスカバリを行う:

- **第一案**: `printf '\n' | timeout 15 ./memtest_vulkan 2>&1 | head -40` でメニュー表示後に空入力で先頭自動選択 → 即 SIGINT で停止し、stdout のメニュー行から Bus 値を抽出
- **フォールバック (第一案で取れない場合)**: `script` コマンド経由で interactive 出力を tee し、`Ctrl-C` 発火タイミングを工夫して取得
- **更にフォールバック**: メニュー順 = Bus 昇順と仮定 (1=04:00.0, 2=07:00.0, 3=84:00.0, 4=87:00.0) で進め、各 Run の memtest 起動ログ冒頭で実 Bus を照合 (誤対象なら即 SIGINT して次の番号で再試行)

### 4. 並走 telemetry / AER

3 ストリームを bg で起動 (回収時に kill):
- `telemetry.sh` — rocm-smi (per-card power / temp / clock) 10s
- `telemetry_pcie.sh` — per-port LnkSta + AER (CE/UC/FATAL/NFATAL) 10s
- `journalctl -k -f` — kernel ログ 全量

### 5. スキャン実行

`timeout --signal=INT <sec> bash -c 'printf "<N>\n" | ./memtest_vulkan'` 形式。SIGINT で extended endless モードを打ち切り、終了サマリを得る。

| Run | 対象 | 持続 | ねらい |
|---|---|---|---|
| pass01 (×3) | SLOT2/SLOT4/SLOT8 | 各 ~6 min | 健全枠の基準値 |
| long | 8820 (SLOT6) | ~120 min | 同じ allocator 配置で iter 数を稼ぐ |
| p01-p04 | 8820 (SLOT6) | ~15 min × 4 | プロセス再起動で allocator 位置を変え、全 VRAM カバレッジを補強 |

注: memtest_vulkan には iteration 指定 CLI フラグなし → wall-time のみで制御。RADV で 1 アロケーション 3.5GB 制限がある場合、1 本での実カバレッジは 16GB の ~22%。ショート 4 本の再起動で位置揺らぎを稼ぎ、目安 60-80% カバレッジを狙う (初回ログで実カバレッジを確認)。

### 6. 各 Run 間の健全性チェック

- `lspci | grep -c "Instinct MI25"` が 4 維持を毎回確認 → 減少時は撤退判定
- AER FATAL 増分があれば即中止 (project_mi25_gpu4_pcie_dropout 既知挙動)

### 7. 集計

`make_mt_summary.py` を新規作成 (短い)。各 `mt_*.log` を regex でパース → `data.md` + `summary.png`。

PNG 設計はエラー分布に応じて分岐:
- **エラー有 (8820 で >0)**: 棒グラフ X 軸 = GPU/Run、Y 軸 = total errors。健全 3 枚と 8820 の比が一目で読める
- **全 PASS (8820 含む全部 0)**: 棒グラフでは情報量ゼロ → 代わりに「カバレッジ・iteration・実消費 (Tj/power) を含む表のラスタライズ + ヘッダー "ALL PASS - n bad pages detected across N GiB scanned"」を PNG として出力 (matplotlib `table()` で生成)

パース対象:
- `Error found. Mode <INITIAL_READ|NEXT_RE_READ>, total errors 0xNNN out of 0xMMM`
- `Errors address range: 0xAAA..=0xBBB`
- 最後の `N iteration` 行 + 終了サマリ `no any errors, testing PASSed.`

### 8. 後処理

- telemetry プロセスを kill (pids ファイル経由)
- llama-server は復帰させず ロック解放はレポート完成後
- 添付ディレクトリにすべての log / script / data.md / summary.png / plan.md を配置

## Verification

- `summary.png` で 8820 と健全 3 枚の error 比較が一目で読める
- `data.md` 表で各 Run の (Iter, ErrBlocks, TotalErrors, AddrMin/Max, dmesg_AER, TDR) が揃う
- 健全 3 枚が全て 0 errors PASS なら基準値 OK
- 8820 long + p01-p04 の合算で実カバレッジ ≥ 60% を達成
- 全期間で PCIe AER FATAL = 0、gpu_count = 4 維持

判定:
- **8820 で error > 0 かつ address に偏在**: (a) 確定 → 物理交換の根拠
- **8820 で error = 0 (健全 3 枚と同等)**: (a) 否定 → 推奨2 へ進む
- **カバレッジ < 50% で error = 0**: 保留 → 後日 long 増やしての再スキャン or 推奨2 を並行検討

## Risks & Withdraw Lines

| 事象 | 検出 | 対応 |
|---|---|---|
| memtest_vulkan 起動即 crash | exit code != 0 / `DEVICE_LOST` | v0.4.4 旧版で再試行 → ダメなら中止 |
| iteration が進まない (allocation 失敗) | iter=0 終了 | env var (`MEMTEST_VULKAN_HEAP_BUDGET_MB` 等) 試行 → ダメなら縮小モード受容 |
| 8820 の TDR (memtest 実行中) | dmesg `page fault → amdgpu_job_timedout` | 既知発火再現として記録、BACO reset 後に次 pass。3 連続で memtest 部分中止 |
| PCIe AER FATAL | telemetry_pcie.log の `FAT=` 増分 | 即中止 |
| host hang (SSH 不通) | ssh タイムアウト連続 | **電源リセット前に必ず `bmc-screenshot.sh mi25` で KVM 取得**、その後 `bmc-power.sh mi25 reset` |
| 4 枚認識ロスト | `gpu_count` < 4 | 既知 (gpu4_pcie_dropout)、電源再投入で復旧確認後、再開判断 |
| 時間オーバ (4.5h → 6h+) | wall-time 監視 | ショート 4→2 本、ロング 120→90 分 |
| memtest_vulkan に `--help` での CLI フラグが見つかる | 取得直後の help 確認 | 対話入力ではなくフラグ経由 (iteration 数指定など) で安定化 |
| ディスカバリで Bus 取得不可 | head -40 にメニュー表示なし | Bus 昇順仮定で進め、各 Run 起動ログで Bus 照合・誤対象なら再試行 |

## Report

ファイル名: `report/yyyy-mm-dd_hhmmss_mi25_8820_vram_memtest.md` (時刻は `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`)。

章立て:

1. **核心発見サマリ** — 1 行結論 + `summary.png` 埋め込み (PNG 必須)
2. **前提・目的** — 真因仮説 (a)/(b)/(c) と本実験の (a) 検証スコープ
3. **環境情報** — mi25 / RADV / memtest_vulkan v0.5.0
4. **再現方法** — 手順 + 添付スクリプト参照
5. **結果** — data.md 表 + ログ抜粋
6. **解釈** — (a) 確定 / 否定 / 保留
7. **過去レポートとの突合** — 過去フォルトと address range
8. **次に着手することの候補** (必須・本プランの要件):
   - **推奨2 (優先)**: 8820 単独 stand-alone 24h 負荷 (`HIP_VISIBLE_DEVICES=3` で llama-server 単独運用、12-14GB モデル)。multi-GPU 経路 (c) と個体ロジック (b) の弁別
   - **推奨3**: sclk スイープ (`rocm-smi --setsclk` で P-state を直接固定、各レベル 1 時間)。電力 cap で律速できなかった計算密度依存を直接検証
9. **参照レポート** — 直近電力スイープ 2 本へのリンク

INDEX.md には該当ジャンルへ時系列順で 1 行追加。添付ディレクトリは `report/attachment/<basename without .md>/`。

## Critical Files

流用 (read-only でコピー、SCRATCH パスのみ書き換え):
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-06-26_210732_mi25_4card_load_vulkan_pwr_sweep_v2/telemetry.sh`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-06-26_210732_mi25_4card_load_vulkan_pwr_sweep_v2/telemetry_pcie.sh`

新規作成:
- `make_mt_summary.py` — log パース + data.md + summary.png 生成 (新規だが短い)
- 主実行スクリプト `run_memtest_campaign.sh` (順序は本ドキュメント Implementation Plan 通り)

参照 (実行スキル):
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/lock.sh`
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/bmc-screenshot.sh`
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/bmc-power.sh`
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/llama-down.sh`

レポート規約:
- `/home/ubuntu/projects/llm-server-ops/REPORT.md`
- `/home/ubuntu/projects/llm-server-ops/CLAUDE.md`
