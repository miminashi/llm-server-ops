# 物理スワップ実験まとめレポート作成 + CLAUDE.md 追記

## Context

2026-06-29 04:18 JST 完了の [8820 stand-alone 24h レポート](../../projects/llm-server-ops/report/2026-06-29_041700_mi25_8820_stand_alone_24h.md) は「(b) 個体ロジック起因確定 = 8820 物理交換相当」と結論した。

その後 06-28 20:00 〜 06-29 14:30 JST の間に **物理的にどのカード個体が故障しているか** を特定する目的で、約 12 回のシャットダウン → 物理スワップ → 起動 → `lspci` / `rocm-smi -i` / `rocm-smi --showuniqueid` 確認を実施。

その過程で **`rocm-smi -i` の GUID 値は固定 ID ではなく KFD ランタイム割当値であること** が判明 (同一 SLOT6 単独装着で 2 枚の別個体カードが両方とも GUID 54068 を返した、ただし Unique ID は別: `0x21501edbcec48c4` / `0x2150040969a48e4`)。

過去の mi25 関連レポート群 (4 枚運用 / 物理層障害 / 負荷試験 / VRAM memtest / stand-alone 24h) は全て「GUID 8820 / 54068 / 33301 / 29525」を**カード個体識別子として扱っていた**ため、その前提が揺らぐ重要な発見。

本計画では:
- この知見を新レポートで体系化
- CLAUDE.md に運用ルールとして明文化
- 過去レポートとメモリにも最低限のクロスリファレンスを追加して整合させる

ただし「(b) 個体ロジック起因」「BDF 87:00.0 で fault 集中」「8820 を物理交換相当扱い」という核心結論自体は揺るがない (BDF は当該セッション中は一貫しており、Unique ID 記録欠落で「どの物理カード」が特定できないだけ)。

## 成果物

### 1. 新レポート

**パス**: `report/2026-06-29_HHMMSS_mi25_gpu_card_id_unique_id.md`
**タイトル**: `mi25 GPU 個体識別: GUID は不変ではない (Unique ID 必須)`
**フォーマット**: [REPORT.md](../../projects/llm-server-ops/REPORT.md) 準拠

#### セクション構成

1. **核心発見サマリ** (**`summary.png` 必須**: メモリ feedback_report_title.md ルール)
   - PNG 内容: 「装着試行マトリックス図」 — 縦軸=物理カード (Unique ID 末尾 4 桁: `c48c4` / `a48e4` / unknown)、横軸=試行 (06-28 20:25 〜 06-29 14:18 の 6 観測点)、セル=「観測 BDF / GUID 値」。同じ SLOT で 2 枚の別カードが両方 GUID 54068 を返す視覚化
   - 本文要点:
     - `rocm-smi -i` の GUID = KFD ランタイム割当値 (構成変更で変動)
     - `rocm-smi --showuniqueid` の Unique ID = ASIC 内部不変 ID
     - 観測決定打: 同じ SLOT6 単独装着で 2 枚の別個体が両方 GUID 54068
       - 付箋「8820」: Unique ID `0x21501edbcec48c4`
       - 付箋「54068」: Unique ID `0x2150040969a48e4`
   - 結論: **過去レポート群の「GUID xxxxx」表記は当時のセッション内ラベルとして読み替える、今後は Unique ID で識別**

2. **背景と実験経緯**
   - 8820 stand-alone 24h 完了後の状況
   - 物理スワップを始めた動機 (どの物理カードを交換すべきかの特定)
   - 約 18.5h で 12 回シャットダウン + 装着 + 確認の経過 (簡潔な時系列表)

3. **観測データ** (装着試行ごとの結果テーブル)
   - 装着内容 / 観測 BDF / 観測 GUID / 観測 Unique ID (取得分のみ)
   - jsonl 解析から抽出した過去観測 (06-28 20:25 GUID 29525, 06-28 22:45 〜 GUID 54068, 06-29 05:13 Unique ID `…c48c4`, 06-29 14:18 Unique ID `…a48e4`)

4. **解釈** (rocm-smi GUID と Unique ID の仕様差)
   - `rocm-smi -i` GUID = KFD render node ID 由来、起動毎/構成毎に再割当て
   - Subsystem ID (Radeon PRO V320) は両カードで共通 → 単独構成で GUID が同一値に収束する仮説
   - Unique ID は ASIC 内部レジスタの不変値 (16 文字 hex)
   - 過去 4 枚運用時の各カード Unique ID 記録は **存在しない** (`report/attachment/` 全文 grep で 0 件) → カード個体特定は今後の baseline 取得が必要

5. **PCIe トポロジ / SMBIOS スロットマッピングの副次知見**
   - SMBIOS Type 9 の Bus Address は MI25 カード内蔵 upstream bridge の bus 番号
   - 例: SMBIOS SLOT6 (CPU2 SLOT6) = `0000:82:00.0` (upstream bridge) → `83:00.0` (downstream) → `84:00.0` (GPU 本体)
   - したがって SMBIOS Bus Address ≠ GPU 本体 BDF
   - 正しい SLOT↔GPU BDF マッピングは `lspci -tnnv` で PCIe tree を辿って確定

6. **過去レポートへの影響と読み替えガイド**
   - 「fault は BDF 87:00.0 で集中 = (b) ASIC 個体欠陥」という結論は揺らがない (BDF は当該セッション内で一貫)
   - 「物理的にどのカード個体か」は Unique ID 記録欠落により未確定
   - 物理交換を「8820」付箋のカード or「54068」付箋のカードのどちらに対して実施すべきかは、4 枚運用復帰時に Unique ID baseline を取得した後でないと判断できない
   - 当面の運用方針 (3 枚 excl 「BDF 87:00.0 に挿していたカード」/ 48GB) は不変

7. **今後の運用変更**
   - 認識確認時に `rocm-smi --showuniqueid` を必ず取得・記録 (boot_state.log 等に併記)
   - レポート/メモリでカードを呼ぶときは Unique ID 末尾 4 桁等で略記 (例: `card-c48c4` / `card-a48e4`)
   - 既存レポートの「GUID 8820 / 54068 / 33301 / 29525」は変更せず、当時の rocm-smi 出力値として読み替える注釈を本レポートで提供
   - 物理スワップ前後で Unique ID で必ず照合 (GUID では追跡不能)

8. **残課題**
   - **4 枚運用復帰時の Unique ID baseline 取得**: 4 枚同時装着で各 BDF/SLOT/GUID/Unique ID を `boot_state.log` に保存し、固定リファレンスとする
   - **過去 fault 個体の Unique ID 特定**: baseline 取得後、過去の「BDF 87:00.0 = 当時 SLOT6 = fault 集中個体」に対応する Unique ID を確定 → その時点で物理交換対象が一意に決まる
   - **本レポート計画では実施せず**、別タスクとして残置

9. **添付ファイル** (REPORT.md ルール準拠、必須セクション)
   - `[実装プラン](attachment/2026-06-29_HHMMSS_mi25_gpu_card_id_unique_id/plan.md)`
   - `[装着試行タイムライン](attachment/2026-06-29_HHMMSS_mi25_gpu_card_id_unique_id/swap_timeline.md)`
   - `[GUID 観測スナップショット](attachment/2026-06-29_HHMMSS_mi25_gpu_card_id_unique_id/rocm_smi_snapshots/)`
   - `[SMBIOS / PCIe tree 出力](attachment/2026-06-29_HHMMSS_mi25_gpu_card_id_unique_id/)`
   - `[summary.png 生成スクリプト](attachment/2026-06-29_HHMMSS_mi25_gpu_card_id_unique_id/make_summary.py)`

10. **参照**
    - 直前の [stand-alone 24h レポート](../../projects/llm-server-ops/report/2026-06-29_041700_mi25_8820_stand_alone_24h.md)
    - [4枚復旧の負荷検証](../../projects/llm-server-ops/report/2026-06-25_094641_mi25_4card_load_gpuvm_fault.md) 以降の fault 系列
    - [メモリ project_mi25_gpu4_pcie_dropout](../../.claude/projects/-home-ubuntu-projects-llm-server-ops/memory/project_mi25_gpu4_pcie_dropout.md)

#### attachment ディレクトリ詳細

`report/attachment/2026-06-29_HHMMSS_mi25_gpu_card_id_unique_id/`:

- `plan.md` — 本プランファイルのコピー (REPORT.md 必須ルール: プランモード時)
- `swap_timeline.md` — jsonl 解析から起こした 12 回のスワップ詳細時系列 (装着 / 観測 / 判定)
- `rocm_smi_snapshots/` — 観測 4 件 (`6-28_2025_guid29525.txt`, `6-28_2245_guid54068.txt`, `6-29_0513_uniqueid_c48c4.txt`, `6-29_1418_uniqueid_a48e4.txt`)
- `smbios_slot_map.txt` — `sudo dmidecode -t 9` 出力スナップショット
- `lspci_tnnv.txt` — `lspci -tnnv` 出力スナップショット (PCIe tree)
- `make_summary.py` — Python (matplotlib) で `summary.png` を生成するスクリプト
- `summary.png` — 装着試行マトリックス図 (核心発見サマリ用)

### 2. CLAUDE.md 追記

**ファイル**: `CLAUDE.md`
**追記位置**: `## GPUサーバとLLM` セクション末尾 (`---` 直前)、新サブセクションとして `### mi25 GPU 個体識別 (Unique ID 必須)` を追加

**追記内容** (案):

```markdown
### mi25 GPU 個体識別 (Unique ID 必須)

mi25 (MI25 4枚) では `rocm-smi -i` が表示する **GUID は KFD ランタイム割当値で不変ではない**。
過去のレポート群で「GUID 8820 / 54068 / 33301 / 29525」と呼んでいたものは、その当時の
4 枚同時運用セッション内でのみ有効。物理交換・スロット入れ替え・単独可視化で値が変わる
(実例: 別個体カードを単独装着すると両方とも GUID 54068 を返した)。

カード個体不変の識別子は `rocm-smi --showuniqueid` の **Unique ID** (例: `0x21501edbcec48c4`)。
ASIC 内部に焼き込まれた値で、構成変更でも変わらない。

**運用ルール**:
- 認識確認では必ず `rocm-smi --showuniqueid` を併記して記録 (boot_state.log 等)
- レポート/メモリで「カード」を指すときは Unique ID 末尾 4 桁等で略記 (例: `card-c48c4`)
- 過去レポートの「GUID xxxxx」は当時のセッション値として読み替える (新たに使わない)
- 物理スワップ前後で Unique ID で必ず照合 (BDF / GUID では追跡不能)

**SMBIOS スロット ↔ GPU BDF**:
- `sudo dmidecode -t 9` の Bus Address は MI25 内蔵 upstream bridge の bus 番号 (GPU 本体ではない)
- 正しい SLOT↔GPU BDF マッピングは `lspci -tnnv` で PCIe tree を辿る
- 例: SMBIOS SLOT6 = `82:00.0` (upstream) → `83:00.0` (downstream) → `84:00.0` (GPU 本体)

詳細経緯は新レポート [report/2026-06-29_HHMMSS_mi25_gpu_card_id_unique_id.md] を参照。
```

### 3. 過去レポート末尾の補足注追加

**ファイル**: `report/2026-06-29_041700_mi25_8820_stand_alone_24h.md`
**追記位置**: 末尾の `## 参照レポート` 直前
**追記内容** (案):

```markdown
## 補足 (2026-06-29 追記)

本レポート中の「GUID 8820」「8820 個体」等の表記は `rocm-smi -i` の出力値であり、本実験当時の
4 枚同時運用セッションにおけるラベルである。後続の物理スワップ実験で **`rocm-smi -i` の GUID
は KFD ランタイム割当値で個体不変ではない** ことが判明した (実例: 単独装着で別個体 2 枚が両方
GUID 54068 を返した)。

**本レポートの結論** (「fault は BDF 87:00.0 で集中 = (b) ASIC 個体ロジック起因 = 物理交換相当」)
**は揺らがない** — BDF は本実験中一貫して同一個体に固定されていた。ただし「物理的にどのカード
個体か」は当時 Unique ID を記録しておらず特定不能。次の 4 枚運用復帰時に Unique ID baseline を
取得して特定する。

詳細は [後続レポート 2026-06-29_HHMMSS_mi25_gpu_card_id_unique_id.md] を参照。
```

### 4. メモリ更新

**ファイル**: `/home/ubuntu/.claude/projects/-home-ubuntu-projects-llm-server-ops/memory/project_mi25_gpu4_pcie_dropout.md`
**追記位置**: 末尾の「当面の運用」直前

**追記内容** (案、概略):

```markdown
- **2026-06-29 GPU 個体識別子の再点検 ([カード個体識別レポート](report/2026-06-29_HHMMSS_mi25_gpu_card_id_unique_id.md))**:
  物理スワップ追跡で **`rocm-smi -i` の GUID 値は KFD ランタイム割当値で不変ではない** ことが判明。
  単独 SLOT6 装着で 2 枚の別個体カードが両方とも GUID 54068 を返した (Unique ID は別:
  `0x21501edbcec48c4` / `0x2150040969a48e4`)。本メモリ内の「GUID 8820 / 54068 / 33301 / 29525」
  は当時のセッション値、**今後は Unique ID で識別** (末尾 4 桁略記: `card-c48c4` / `card-a48e4` 等)。
  4 枚運用復帰時に Unique ID baseline を取得して、過去 fault 集中個体 (BDF 87:00.0 当時の SLOT) を
  Unique ID で確定する。SMBIOS Type 9 の Bus Address は MI25 内蔵 upstream bridge bus 番号で
  GPU 本体 BDF と異なる (例: SMBIOS SLOT6=82:00.0 → upstream → 83:00.0 → GPU 84:00.0)、
  正しい SLOT↔BDF は `lspci -tnnv` で確定すること。
```

そして MEMORY.md のワンライナーは `mi25 4枚復旧の経緯と現状` を一文だけ更新して **Unique ID 必須** に触れる (内容は変えず末尾に「Unique ID 識別必須、`rocm-smi -i` GUID 不変ではない (06-29 確認)」を追記)。

### 5. INDEX 追記

**ファイル**: `report/INDEX.md`
**追記位置**: `## 11. mi25 への横展開（2台目 GPU サーバ）` セクション末尾、直前エントリ (`2026-06-29_041700_mi25_8820_stand_alone_24h.md`) の **下**
**形式**: 既存と同一のフラットリスト (`- [x] [filename](filename) — ワンライン説明`)、テーブルではない

**追記内容** (案):

```markdown
- [x] [2026-06-29_HHMMSS_mi25_gpu_card_id_unique_id.md](2026-06-29_HHMMSS_mi25_gpu_card_id_unique_id.md) — 8820 stand-alone 完了後の物理スワップ追跡 (約 12 回シャットダウン+装着+確認) で、**`rocm-smi -i` の GUID 値は KFD ランタイム割当値で個体不変ではない** ことが判明 (同 SLOT6 単独で 2 枚の別個体カードが両方 GUID 54068 を返したが Unique ID は別: `0x21501edbcec48c4` / `0x2150040969a48e4`)。過去レポート群の「GUID 8820/54068/33301/29525」は当時のセッション値、**今後は `rocm-smi --showuniqueid` の Unique ID で識別**。SMBIOS Type 9 の Bus Address は MI25 内蔵 upstream bridge bus 番号で GPU 本体 BDF と異なる副次知見も併記。stand-alone 24h の結論 (BDF 87:00.0 集中 = (b) 個体ロジック起因) は不変、ただし物理カード個体特定は 4 枚運用復帰時の Unique ID baseline 取得まで保留
```

## 実装手順

### Step 0: タイムスタンプ取得とディレクトリ作成

```bash
TS=$(TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S)   # REPORT.md ルール: LLM 推測禁止、コマンド取得
REPORT_NAME="${TS}_mi25_gpu_card_id_unique_id"
mkdir -p "report/attachment/${REPORT_NAME}/rocm_smi_snapshots"
```

### Step 1: jsonl から物理スワップ実験の全観測を抽出

`/home/ubuntu/.claude/projects/-home-ubuntu-projects-llm-server-ops/ccdb0def-b5f5-454d-b309-1fd1bd9d62de.jsonl` から:
- ユーザ装着メッセージ (06-28 20:00 以降の全 USER メッセージ)
- 各起動後の `lspci` / `rocm-smi -i` / `rocm-smi --showuniqueid` 出力
- SMBIOS / lspci -tnnv 出力

を Python スクリプトで抽出し、`swap_timeline.md` および `rocm_smi_snapshots/*.txt` として保存。

### Step 1b: summary.png 生成

`make_summary.py` を作成 (Python + matplotlib)。装着試行マトリックス図を `summary.png` に出力:

- 縦軸: 物理カード (Unique ID 末尾 4 桁: `c48c4` / `a48e4` / `unknown`)
- 横軸: 装着試行 (タイムスタンプ順)
- 各セルに観測 BDF + GUID 値を表示
- 「同じ SLOT で 2 枚の別カードが両方 GUID 54068」が一目で分かる配色

### Step 2: 新レポート本文を執筆

[REPORT.md](../../projects/llm-server-ops/REPORT.md) フォーマット準拠で `report/${REPORT_NAME}.md` を作成。

ファイル名の `HHMMSS` は Step 0 で取得したタイムスタンプを使用。本文には:
- 核心発見サマリ冒頭に `![summary](attachment/${REPORT_NAME}/summary.png)` を埋め込み
- `## 添付ファイル` セクションを設けてプランファイル他をリンク

### Step 2b: プランファイルをコピー (REPORT.md 必須ルール)

```bash
cp /home/ubuntu/.claude/plans/report-2026-06-27-071959-mi25-8820-vram-nifty-finch.md \
   "report/attachment/${REPORT_NAME}/plan.md"
```

### Step 3: CLAUDE.md に新サブセクション追加

`## GPUサーバとLLM` セクション末尾、`---` 直前 (現状 L58 直前) に `### mi25 GPU 個体識別 (Unique ID 必須)` を追加。CLAUDE.md は現状の構造:

- L19: `## GPUサーバとLLM`
- L26: `### ロックが必要なケース`
- L37: `### クイックリファレンス`
- L57: ssh コマンド例終了
- L58: `---`
- L60: `## 重要な制約`

→ L57 と L58 の間に新サブセクション挿入。

### Step 4: 過去レポート末尾に補足注追加

`report/2026-06-29_041700_mi25_8820_stand_alone_24h.md` の `## 参照レポート` 直前に `## 補足 (2026-06-29 追記)` セクションを追加。

### Step 5: メモリ更新

`/home/ubuntu/.claude/projects/-home-ubuntu-projects-llm-server-ops/memory/project_mi25_gpu4_pcie_dropout.md` 末尾の「当面の運用」直前にエントリを追加。MEMORY.md ワンライナーも更新。

### Step 6: INDEX 追記

`report/INDEX.md` の **`## 11. mi25 への横展開（2台目 GPU サーバ）`** セクション末尾 (`2026-06-29_041700_mi25_8820_stand_alone_24h.md` エントリの下) に、フラットリスト形式 (`- [x] [filename](filename) — ワンライン説明`) で 1 行追加。

### Step 7: 動作確認

- `report/${REPORT_NAME}.md` の Markdown を vim/cat で目視確認
- 相対リンクが解決可能か `grep -oE "\(.*\.(md|png|txt)\)" report/${REPORT_NAME}.md` で抽出して全て `ls -la` で存在確認
- `summary.png` を image viewer で確認 (図の意味が伝わるか)
- CLAUDE.md の構造が崩れていないか `head -80 CLAUDE.md` で確認

## 新規/改変ファイル一覧

| ファイル | 種別 | 内容 |
|---|---|---|
| `report/2026-06-29_HHMMSS_mi25_gpu_card_id_unique_id.md` | **新規** | 本計画の核心成果物、`## 添付ファイル` セクション必須 |
| `report/attachment/.../plan.md` | **新規** | 本プランファイルのコピー (REPORT.md 必須) |
| `report/attachment/.../swap_timeline.md` | **新規** | jsonl 抽出時系列 |
| `report/attachment/.../rocm_smi_snapshots/*.txt` | **新規** (4 件) | 観測スナップショット |
| `report/attachment/.../smbios_slot_map.txt` | **新規** | dmidecode -t 9 出力 |
| `report/attachment/.../lspci_tnnv.txt` | **新規** | lspci -tnnv 出力 |
| `report/attachment/.../make_summary.py` | **新規** | summary.png 生成 (Python + matplotlib) |
| `report/attachment/.../summary.png` | **新規** | 装着試行マトリックス図 (核心発見サマリ用、必須) |
| `CLAUDE.md` | **改変** | `### mi25 GPU 個体識別 (Unique ID 必須)` サブセクション追加 |
| `report/2026-06-29_041700_mi25_8820_stand_alone_24h.md` | **改変** | 末尾に `## 補足 (2026-06-29 追記)` 1 段落追加 |
| `/home/ubuntu/.claude/projects/-home-ubuntu-projects-llm-server-ops/memory/project_mi25_gpu4_pcie_dropout.md` | **改変** | 2026-06-29 個体識別子の再点検エントリ追加 |
| `/home/ubuntu/.claude/projects/-home-ubuntu-projects-llm-server-ops/memory/MEMORY.md` | **改変** | mi25 4枚復旧ワンライナーに Unique ID 必須を追記 |
| `report/INDEX.md` | **改変** | 新レポートエントリ 1 行追加 |

## 検証手順 (verification)

| 検証項目 | 期待値 |
|---|---|
| 新レポートが REPORT.md フォーマットに準拠 | タイトル 50 字以内、`## 添付ファイル` セクションあり、プランファイルリンクあり、ファイル名は `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得 (LLM 推測禁止) |
| 核心発見サマリに `summary.png` が埋め込まれている | メモリ feedback_report_title.md ルール準拠 |
| Unique ID 2 件が正しく転記されている | `0x21501edbcec48c4` / `0x2150040969a48e4` ともに本文に出現 |
| CLAUDE.md の新サブセクションが既存セクションと整合 | `## GPUサーバとLLM` の `### ロックが必要なケース` / `### クイックリファレンス` と同じ見出しレベル、`---` 直前に位置 |
| 過去レポート補足注が `## 参照レポート` の直前にある | 既存内容を変更せず追加のみ |
| メモリ追記が時系列順に並んでいる | 末尾の「当面の運用」直前に挿入 |
| INDEX 新エントリが `## 11. mi25 への横展開` セクション末尾の正しい位置 | フラットリスト形式 `- [x] [filename](filename) — ...`、直前は `2026-06-29_041700_mi25_8820_stand_alone_24h.md` |
| 関連ファイルへの相対パスリンクが全て解決可能 | `[..](...)` の各 URL が実在 (Step 7 で grep + ls 検証) |

## リスク

| リスク | 緩和 |
|---|---|
| 過去レポート改変による履歴の不可逆性 | 末尾追加のみで既存内容は変えない。compare-friendly |
| Unique ID 末尾 4 桁略記 (`c48c4` / `a48e4`) の衝突可能性 | 衝突したら 6 桁に拡張する旨を CLAUDE.md に明記 |
| 4 枚運用復帰の Unique ID baseline 取得は別タスク | 本計画で「残課題」として明示的に切り出し、INDEX 等で次計画化 |
| jsonl 抽出時の見落とし (装着試行は最多 12 回) | swap_timeline.md でユーザ装着メッセージを 1 件残らず転記、観測 GUID 不明箇所も「未取得」と明記 |

## 完了後の状態

- 新レポート 1 件と attachment 一式が作成済
- CLAUDE.md・過去レポート・メモリ・INDEX が更新済
- 「真の故障個体の Unique ID 特定」は残課題として明示、4 枚運用復帰のタイミングで再着手
- 当面の運用方針 (3 枚 / 48GB / ROCm) は不変
