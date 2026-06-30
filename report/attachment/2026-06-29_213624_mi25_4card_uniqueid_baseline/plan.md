# mi25 4枚装着 baseline 取得 — 過去 fault 個体 Unique ID 確定の新規レポート作成

## Context

本セッションで mi25 の 4 枚 GPU 全ての **Unique ID baseline** を物理スワップサイクル
(SLOT6 単独×4 + 4 枚同時×1) で取得した。前段の [2026-06-29_191721_mi25_gpu_card_id_unique_id.md](../../projects/llm-server-ops/report/2026-06-29_191721_mi25_gpu_card_id_unique_id.md)
で「`rocm-smi -i` の GUID は個体不変ではない・Unique ID が正規」と判明した直後の続編で、
**残課題だった「過去 fault 集中個体 (4 枚運用時 BDF 87:00.0 = GUID 8820) の Unique ID 特定」が決着**:

- **`card-c48c4` (Unique ID `0x21501edbcec48c4`) = 過去 fault 集中個体 = 物理交換相当の対象**
- 全 4 枚の Unique ID baseline 取得完了 (今後の物理スワップで照合可能)
- GUID は BDF 決定論的 (今日 05:25 JST と 21:14 JST の 2 回観測で完全一致) を確定
- 末尾 4 桁では衝突 (`c48c4` と `448c4` が共に `48c4`)、末尾 5 桁で一意化

新規レポートとして記録し、過去レポート群の「GUID 8820 個体 = 物理交換」の指示先を
**物理個体識別子 (Unique ID) で確定**させる。本セッション中の 2 番目の課題 (4 枚装着での実負荷
テストによる Unique ID 単位 fault 再現確認) は次セッションのタスクとしてレポート末尾に明記する。

## 新規レポート概要

### ファイル名と配置

- **本体**: `report/<YYYY-MM-DD_HHMMSS>_mi25_4card_uniqueid_baseline.md`
  - タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得 (推測禁止、[REPORT.md](../../projects/llm-server-ops/REPORT.md) L9)
  - 短い英語スラグ: `mi25_4card_uniqueid_baseline` (filename 30字程度、約 60 字以内)
- **添付ディレクトリ**: `report/attachment/<同名 (.md 抜き)>/`
  - `plan.md` (本プラン、[REPORT.md](../../projects/llm-server-ops/REPORT.md) L18-27 必須)
  - `4card_baseline.txt` (本セッション 21:14 JST 取得の rocm-smi 生出力)
  - `single_slot6_swaps.txt` (本セッション SLOT6 単独 4 回スワップの rocm-smi 生出力 4 件まとめ)
  - `summary.png` (matplotlib による 4 枚 baseline マッピング図)
  - `make_summary.py` (図生成スクリプト、既存 [2026-06-29_191721 の make_summary.py](../../projects/llm-server-ops/report/attachment/2026-06-29_191721_mi25_gpu_card_id_unique_id/make_summary.py) と同方針)

### タイトル (日本語、50字以内)

> `mi25 4枚baseline取得 — 過去fault個体 c48c4 のUnique ID確定`

(約 40 字、CLAUDE.md feedback `feedback_report_title.md` のタイトル簡潔化ルールに従う)

### セクション構成

[REPORT.md](../../projects/llm-server-ops/REPORT.md) と既存 [2026-06-29_191721 レポート](../../projects/llm-server-ops/report/2026-06-29_191721_mi25_gpu_card_id_unique_id.md) のパターンに合わせる:

1. `# タイトル` + `- **実施日時**: ...JST` 行
2. `## 添付ファイル` — plan.md / 4card_baseline.txt / single_slot6_swaps.txt / summary.png / make_summary.py
3. `## 核心発見サマリ` — **冒頭に PNG 埋め込み** (`feedback_report_title.md` 必須)
   - 全 4 枚 Unique ID baseline 完成 / `card-c48c4` = 過去 fault 個体確定 / GUID は BDF 決定論的の決定的証拠 (2 回観測で完全一致)
4. `## 前提・目的` — 前段レポートの残課題 (過去 fault 個体の Unique ID 特定 + 4 枚 baseline 取得) が動機
5. `## 環境情報` — mi25 / Supermicro X10DRG-Q / ROCm / 4 枚装着 (CPU1 SLOT2/4 + CPU2 SLOT6/8)
6. `## 再現方法` — 物理スワップサイクル (`bmc-power.sh mi25 soft`/`on` + SSH 復帰待機 + `rocm-smi --showuniqueid`/`-i`/`--showbus` + `lspci -nn`)
7. `## 観測データ`
   - **テーブル A**: SLOT6 単独 4 回スワップ結果 (BDF 全て `84:00.0` / GUID 全て `54068` / Unique ID は別)
   - **テーブル B**: 4 枚装着 baseline (GPU[0]-[3] の BDF/GUID/Unique ID/カード略称)
   - **テーブル C**: 4 枚装着 GUID/BDF 配置の 2 回観測比較 (今日 05:25 JST vs 21:14 JST、完全一致を示す)
8. `## 解釈`
   - 8.1 過去 fault 集中個体 = `card-c48c4` 特定根拠 (BDF 87:00.0 = GUID 8820 = `0x21501edbcec48c4`)
   - 8.2 GUID は BDF 決定論的 (再確認データ + 推定メカニズム = KFD allocation by enumeration order)
   - 8.3 末尾 4 桁 vs 5 桁の衝突分析 (4 桁: `48c4` 2 重複 / 5 桁: 全 4 枚一意)
9. `## 過去レポートへの影響と読み替えガイド` — 既存レポートの「8820 個体」「BDF 87:00.0」が **物理的に `card-c48c4`** を指すことが確定
10. `## 今後の運用変更`
    - カード略称は **末尾 5 桁基本** (4 桁では衝突)、衝突時 6 桁拡張
    - `boot_state.log` 等の認識ログに Unique ID 必須記録 (既出ルール再確認)
    - 物理交換対象 (`card-c48c4`) の確定
11. `## 残課題 / 次セッションのタスク`
    - **次セッション課題 (概要のみ記載)**: 4 枚装着での実負荷テスト (ROCm / Vulkan) で `card-c48c4` (BDF 87:00.0) に過去 fault と同シグネチャ (`gfxhub0 page fault @ BDF 87:00.0` 等) が再現するかを **Unique ID 単位** で確認 (= baseline の動作検証 + 過去 fault が物理 `card-c48c4` 起因という結論の最終裏取り)。詳細手順 (ROCm vs Vulkan の選択基準・負荷時間・観測項目・判定基準) は次セッション開始時に設計
    - **本セッション終了時の状態**: 4 枚装着 + 電源 ON 維持 (シャットダウンしない、次セッション即時実負荷可、ユーザ判断)
    - 当面の運用方針 (`HIP_VISIBLE_DEVICES=0,1,2` で 3 枚 48GB 運用継続) は不変
12. `## 参照レポート`
    - 直前: [2026-06-29_191721_mi25_gpu_card_id_unique_id.md](../../projects/llm-server-ops/report/2026-06-29_191721_mi25_gpu_card_id_unique_id.md) (本レポートの直接前提)
    - 過去 fault 関連: stand_alone_24h / 4card_load_gpuvm_fault / 4card_load_vulkan / vulkan_pwr_sweep / vulkan_pwr_sweep_v2 / 8820_vram_memtest

### `summary.png` の内容方針 (テーブル + 2 回観測比較バーチャート)

> **注記 (実装後の方針変更)**: 下段は当初「バーチャート」を予定していたが、レポート完成後のレビューで「GUID は名義尺度 (カテゴリ値) のため棒グラフの縦軸として不適切」との指摘を受け、**カテゴリ別色分けマトリックス** (各セルを GUID 値の固有色で塗り、列内の色一致で BDF 決定論性を可視化) に変更した。下記の「バーチャート」記述は当初プラン保存用、実装は同ディレクトリの `make_summary.py` の下段ロジックを参照。

matplotlib で **上段テーブル + 下段比較チャート** の 2 段構成 1 枚画像:

- **上段 (テーブル)**: 4 枚 baseline マッピング
  - 行: GPU[0..3]
  - 列: BDF / GUID (KFD ランタイム値) / Unique ID 末尾 5 桁 / カード略称 / 過去 fault マーク
  - BDF 87:00.0 の行 (= `card-c48c4`) を **赤背景** でハイライト
- **下段 (バーチャート / カテゴリ比較)**: 05:25 JST vs 21:14 JST の 4 BDF × 2 回観測の GUID 配置一致
  - 横軸: BDF (04:00.0 / 07:00.0 / 84:00.0 / 87:00.0)
  - 縦軸 (もしくはバー上ラベル): GUID 値 (29525 / 33301 / 54068 / 8820)
  - 各 BDF につき 2 バー (05:25 / 21:14) を並べ、両時刻で全 BDF の GUID が完全一致することを視覚化
- 図の下に注記: 「GUID は BDF 決定論的 (本日 2 回観測で完全一致)、Unique ID のみがカード個体不変」
- 既存 [make_summary.py](../../projects/llm-server-ops/report/attachment/2026-06-29_191721_mi25_gpu_card_id_unique_id/make_summary.py) のスタイル (matplotlib table) を踏襲しつつ、`gridspec` で上下分割

## 副次更新 (本プラン承認後に実施)

### 1. CLAUDE.md の運用ルール更新

[CLAUDE.md](../../projects/llm-server-ops/CLAUDE.md) の「mi25 GPU 個体識別」節 (運用ルール部分) で:

- 現在: 「Unique ID 末尾 4 桁等で略記 (例: `card-c48c4`)。衝突した場合は 6 桁に拡張」
- 新版: 「Unique ID **末尾 5 桁** で略記 (例: `card-c48c4`)。本日の 4 枚 baseline で末尾 4 桁では `48c4` が `card-c48c4`/`card-448c4` で衝突することが判明したため。衝突した場合は 6 桁に拡張」

### 2. INDEX.md への追記

[report/INDEX.md](../../projects/llm-server-ops/report/INDEX.md) のセクション 11「mi25 への横展開」末尾 (現在の最終エントリ 2026-06-29_191721 の直後) に 1 行追加:

```markdown
- [x] [<新ファイル名>.md](<新ファイル名>.md) — 上記 Unique ID 続編の 4 枚 baseline 取得 (4 枚装着 + SLOT6 単独 4 回スワップで全 Unique ID 確定)。**過去 fault 集中個体 = `card-c48c4` (`0x21501edbcec48c4`) 確定** (4 枚運用時 BDF 87:00.0 = GUID 8820 = この Unique ID、本日 2 回観測の GUID/BDF 完全一致から KFD allocation の BDF 決定論性も確証)。カード略称は末尾 4 桁では衝突 (`48c4` 2 重) するため **末尾 5 桁基本** に運用変更。物理交換対象が一意に確定 → 4 枚 64GB 復帰には `card-c48c4` の**物理交換**が必要 (stand_alone 24h で (b) 個体ロジック起因確定済のため SLOT 移動では救えない)。次セッション課題 = 4 枚装着実負荷で `card-c48c4` (BDF 87:00.0) の fault シグネチャ再現確認
```

### 3. メモリ更新 `project_mi25_gpu4_pcie_dropout.md`

対象ファイル (絶対パス): `/home/ubuntu/.claude/projects/-home-ubuntu-projects-llm-server-ops/memory/project_mi25_gpu4_pcie_dropout.md` に 2026-06-29 (本セッション 21:14 JST baseline) の追記:

- 過去 fault 集中個体 = `card-c48c4` (Unique ID `0x21501edbcec48c4`) 確定
- 全 4 枚 Unique ID 取得完了 → baseline 化済み (`card-c48c4` / `card-a48e4` / `card-448c4` / `card-c3164`)
- 略称は **末尾 5 桁** 基本 (末尾 4 桁では `48c4` 衝突発生のため変更)
- 4 枚 64GB 復帰には `card-c48c4` の**物理交換**が必要 (stand_alone 24h で (b) 個体ロジック起因確定済のため SLOT 移動では救えない、確定)
- 当面は `HIP_VISIBLE_DEVICES=0,1,2` (`card-c48c4` 除外 3 枚 48GB) で運用継続 — 不変
- リファレンスとして新レポートのファイル名を追加
- 既存メモリ本文内で旧称 `8820` を使用している箇所は併記 (例: `8820 (= card-c48c4)`)、互換性のため旧称を消さない

## 実施手順 (プラン承認後)

1. JST タイムスタンプ取得: `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` → 以降 `<ts>` で参照
2. ファイル名確定: `report/<ts>_mi25_4card_uniqueid_baseline.md`
3. 添付ディレクトリ作成: `mkdir -p report/attachment/<ts>_mi25_4card_uniqueid_baseline/`
4. `plan.md` 配置: `cp ~/.claude/plans/1-2-idempotent-wind.md report/attachment/<ts>_mi25_4card_uniqueid_baseline/plan.md`
5. `4card_baseline.txt` 作成: 21:14 JST 取得済みの rocm-smi 出力 (本セッション会話履歴から) をそのまま保存
6. `single_slot6_swaps.txt` 作成: SLOT6 単独 4 回 (20:17/20:30/20:55/21:03 JST) の rocm-smi 出力をまとめて保存
7. `make_summary.py` 作成 → `python3 make_summary.py` で `summary.png` 生成
8. `<ts>_mi25_4card_uniqueid_baseline.md` 本体作成 (上記セクション構成)
9. `report/INDEX.md` セクション 11 末尾に 1 行追記
10. `CLAUDE.md` の「mi25 GPU 個体識別」節を末尾 4→5 桁ルールへ更新
11. メモリ `project_mi25_gpu4_pcie_dropout.md` を 2026-06-29 baseline 取得結果で更新
12. mi25 ロック解放 (`.claude/skills/gpu-server/scripts/unlock.sh mi25`) — 作業終了の整理として (次セッションは新規にロック取得する)
13. **mi25 シャットダウンしない、4 枚装着 + 電源 ON 維持**で次セッションへ引き継ぎ (次セッション課題 = 実負荷テストを即時開始可能にするため、ユーザ確認済み)

## 検証方法

- 新規レポート (.md) と添付物が `report/` 配下に正しく配置されていることを `ls -la report/<ts>_mi25_4card_uniqueid_baseline.md report/attachment/<ts>_mi25_4card_uniqueid_baseline/` で確認
- `summary.png` のサイズ非ゼロ確認 + `file summary.png` で PNG 形式マジック確認 (CLI 環境のため画像表示は不可、生成成功の客観確認のみ)
- 本文中の相対リンク (添付 / 参照レポート) が全て解決すること: `grep -oE '\]\([^)]+\.(md\|png\|txt\|py)\)' <md>` で抽出し、各リンク先のファイル存在を `ls` で目視確認
- INDEX.md の更新後、当該エントリの相対リンクが効いていること
- CLAUDE.md の末尾 4→5 桁ルール更新箇所の文意整合
- メモリ更新後、MEMORY.md インデックスに既存項目があるので新規追加は不要、既存ファイル更新のみ

## 変更しないもの (本プラン範囲外)

- 4 枚装着での実負荷テスト → **次セッション課題として本レポートに明記**
- 当面の運用方針 (`HIP_VISIBLE_DEVICES=0,1,2` の 3 枚 48GB) → 不変
- 既存レポート (2026-06-29_191721 等) の本文 → 変更しない (新レポート側で「読み替えガイド」として補足)
- 過去レポート群の「GUID 8820」「BDF 87:00.0」表記 → 当時のセッション値として温存
