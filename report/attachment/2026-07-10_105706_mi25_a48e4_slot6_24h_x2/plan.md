# 健全カード a48e4×SLOT6 単独 24h 負荷試験プラン

対象レビュー: [report/2026-07-05_181639_mi25_fault_tracking_fable_review.md](/home/ubuntu/projects/llm-server-ops/report/2026-07-05_181639_mi25_fault_tracking_fable_review.md)

## Context

Fable レビュー (2026-07-05) が最重要見落としとして指摘したのは、6/29 の「(b) 個体ロジック起因確定 = 物理交換相当」宣言が **カード×スロットの交絡** を分離せずに下されていたこと。過去 fault 5 件はすべて c48c4×SLOT6 で発生、SLOT8 では 0/258 だが、この事実は「(b) c48c4 個体起因」でも「(d) SLOT6 環境起因 / c48c4×SLOT6 相互作用」でも整合する。「物理交換必須」は CLAUDE.md・メモリまで伝播しており、過大な断定になっている。

レビュー **推奨 D-1** (最優先) が示す決定実験: **健全カードを SLOT6 に挿し、単独 24h 負荷を SA と同一条件で実施**。SLOT6 起因なら健全カードでも fault が出るはず。出なければ (b) c48c4 単独起因 (または c48c4×SLOT6 相互作用) に絞れる。

**現状の物理配置 (2026-07-05 時点、9 観測点で凍結)**:

| SLOT | BDF | Unique ID 末尾5桁 | 用途 |
|---|---|---|---|
| SLOT2 | 04:00.0 | c3164 | 健全 |
| SLOT4 | 07:00.0 | 448c4 | 健全 (SLOT6 では micro-fit で不認識) |
| **SLOT6** | **87:00.0** | **a48e4** | **★試験対象 (既に SLOT6 装着済)** |
| SLOT8 | 84:00.0 | c48c4 | fault 疑い個体 (2026-06-30 に SLOT6→SLOT8 移動済) |

決定的簡略化: **a48e4 は 2026-06-30 の SLOT4↔SLOT6 swap で既に SLOT6 に移動済**。物理作業ゼロで実験に入れる。Vulkan idx 3 (BDF 87:00.0) = SA 試験 (c48c4×SLOT6) で使った `GGML_VK_IDX=3` と偶然一致するため、SA harness をほぼそのまま流用可能。

## 実験設計

### 目的と成功/失敗判定

- **仮説 H_SLOT6**: SLOT6 (BDF 87:00.0) 側に fault を誘発する環境要因 (信号品質・電源系統・接点状態、または個体×スロット相互作用) が存在する
- **成功条件 (H_SLOT6 支持)**: a48e4×SLOT6 単独 24h で fault ≥1 件、シグネチャが過去 5 件と一致
- **失敗条件 (H_SLOT6 棄却)**: 0 fault で終了。147 trial 到達で P(≥1|p=0.0136)≒87%、200 trial 到達なら ≒93%、240 trial 到達なら ≒96% の検出力
- **弁別対象**: (b) c48c4 個体起因 vs (d) SLOT6 環境/相互作用起因

### 試験パラメータ (SA-SLOT6 と厳密同等 + BACO パッチ)

- **モデル**: `unsloth/Qwen3-8B-GGUF:Q6_K` (`/home/ubuntu/models/Qwen3-8B-Q6_K.gguf` に配置済み)
- **バックエンド**: Vulkan (RADV) — `~/llama.cpp/build-vulkan/bin/llama-server` を使用
- **単独可視化**: `GGML_VK_VISIBLE_DEVICES=3` (a48e4 = BDF 87:00.0 = Vulkan idx 3)
- **HIP index** (rocm-smi 経由): `GPU[3]` = a48e4
- **llama-server 引数** (SA/SLOT8 共通の Qwen3-8B mi25 最適): `--flash-attn 1 --poll 0 -b 2048 -ub 2048 --n-predict 32768 --n-gpu-layers 99 --split-mode layer --ctx-size 131072 --parallel 1 --cache-type-k q8_0 --cache-type-v q8_0 --defrag-thold 0.1 --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 --presence-penalty 1.0 --dry-multiplier 0`
- **キャンペーンパラメータ**: `MAX_TRIALS=200 MIN_TRIALS=80 HANG_SAFETY=10 PHASE_CAP_SEC=86400 TRIAL_SEC=720` (SA と同一)
- **電力キャップ**: 全期間 160W 固定。SLOT8 R2 で導入した「BACO reset 検出 → `sudo rocm-smi --setpoweroverdrive 160 -d 3` で強制再設定」ロジックを継承し、SA で発生した「BACO 後に 220W に戻ったまま 89 trial 実施」問題を防ぐ
- **試験回数**: **Round 1 (24h) のみ確定実施**。0 fault なら 2nd round 24h を追加するか判断 (SLOT8_x2 と対称にすればトータル ~240 trial で検出力 ~96%)。fault ≥1 なら即結論 (SLOT6 起因を積極支持) して R2 不要
- **PCIe root port の物理経路差**: SLOT6 = `80:03.0`, SLOT8 = `80:02.0` (下流 upstream bridge 経由でそれぞれ 87:00.0 / 84:00.0)。SLOT6 root port は fault 5 件全数の物理経路であり、a48e4×SLOT6 が同経路に該当する = 交絡分離の中核

### レビュー副次発見への対応

- **pp_tps 半減の追跡** (A-3): 試験開始 5 分の smoke test で pp_tps を計測し、SA (508.9 t/s) と SLOT8 (206-230 t/s) のどちら側に着地するかを記録。もし SLOT8 側なら pp 曝露が SA より弱い可能性を最初から明示 (結論の限定条件になる)。SA 側なら「同等曝露で 0 fault」の主張が強くなる
- **Tj 相関のデフォルト分析** (A-4): 試験後の summary スクリプトに fault 発生時の Tj / power の実測値記録を組み込む (0 fault で終わってもテンプレとして残す)
- **fault アドレスの体系的記録** (A-5): fault 検出時に `dmesg -w` ストリームから fault 行 (`amdgpu: no-retry page fault` の address / VM_L2_PROTECTION_FAULT_STATUS / UTCL2 client) を抽出して trials jsonl に付記。過去 Vulkan fault の address は `0x33000` (低位、SA fault 2 件と一致)、ROCm 経路 fault は `0x100000000` (4GiB 境界)、VM_L2_PROTECTION_FAULT_STATUS 先頭 = `0x004012B1`、UTCL2 client burst = `SQC (inst) 0x9` → `CB 0x0` を 8-9 件
- **多重比較の意識**: 本試験の統計は「a48e4×SLOT6 (今回) vs c48c4×SLOT6 SA」の 1 比較で終える。SLOT8 と混ぜて 3 群比較にしない (混合効果 = Fable A-2 で指摘済)

### 非目的 (今回はやらないこと)

- **VBIOS/RAS カウンタ 4 枚比較** (レビュー D-4): 副次発見として 5 分で採取するが、決定実験の判断とは分離
- **sclk/DPM スイープ** (レビュー A-6): 本試験の結果次第で次段
- **448c4×SLOT6 micro-fit 検証**: 起動段階の障害で試験自体が成立しないため今回は不関与
- **c48c4×SLOT8×4枚同時 24h** (レビュー D-2): 本試験で SLOT6 起因が濃厚となれば実施の意義が変わる (SLOT8 運用継続の可否)、SLOT6 起因が棄却されれば c48c4 個体確定として最後の駄目押し実験の位置になる。順序としてまず本試験
- **CLAUDE.md / メモリ修正** (レビュー D-5): 本試験の結果を待って一括更新
- **残存テレメトリデーモン停止** (レビュー B-1): 本試験と衝突するため Phase 0 で必須実施。**未 push コミット・未整理ファイル (B-3/B-4) は本試験と独立**、本試験終了後にユーザ判断で対応

## 実施手順

### Phase 0 — 事前整理 (試験開始前、~5 分)

**必須項目のみ**: レビュー B-1 (残存テレメトリデーモン) が本試験の計測環境と衝突するため、これだけは本試験前に処理する。B-2 (attachment ディレクトリ名不一致)、B-3 (未追跡ファイル)、B-4 (未 push commit) は mi25 に触らない git 側のみの作業なので本試験終了後に一括対応。

1. **既存テレメトリデーモン 2 系統を停止** (pid ファイル経由 → パターン kill → リモート kill の 3 段):
   ```bash
   # (a) 各 SCRATCH の pid ファイル経由
   for D in report/attachment/2026-07-01_040254_mi25_c48c4_slot8_24h \
            report/attachment/2026-07-02_102205_mi25_c48c4_slot8_24h_round2; do
     [ -f "$D/telemetry.pids" ] && xargs -r kill 2>/dev/null < "$D/telemetry.pids"
     [ -f "$D/telemetry_pcie.pid" ] && xargs -r kill 2>/dev/null < "$D/telemetry_pcie.pid"
   done
   # (b) パターン kill (fallback)
   pkill -f "telemetry.sh.*2026-07" 2>/dev/null
   pkill -f "telemetry_pcie.sh.*2026-07" 2>/dev/null
   # (c) mi25 側の残存 ssh セッション
   ssh mi25 "pkill -f 'dmesg -w' 2>/dev/null; pkill -f 'tail -F /tmp/llama-server.log' 2>/dev/null"
   # (d) 確認: 出力 0 行が期待
   ps -ef | grep -E "telemetry.sh|telemetry_pcie.sh" | grep -v grep
   ssh mi25 "ps -ef | grep -E 'dmesg -w|tail -F /tmp/llama-server' | grep -v grep"
   ```
2. **7 月試験の commit 済み添付ログ 6 ファイルを試験終了時刻断面 (07-03 10:31 JST) に restore** (追記分を破棄):
   ```bash
   git checkout HEAD -- report/attachment/2026-07-01_040254_*/telemetry_*.log \
                        report/attachment/2026-07-02_102205_*/telemetry_*.log
   ```
3. `git status` で M が 0 になることを確認

### Phase 1 — ロック取得 & 事前 baseline (~5 分)

1. `.claude/skills/gpu-server/scripts/lock.sh mi25 "a48e4-slot6-24h-r1-<ts>"`
2. GPU 4 枚認識と Unique ID 一致を確認: `rocm-smi --showuniqueid` (期待: c3164/448c4/c48c4/a48e4 = 4 枚、9 観測点で凍結済み)
3. `rocm-smi --showmaxpower` で全 4 枚 160W cap を確認 (`/etc/rc.local` が boot 時に 160W 永続化済み。HW default は 220W)
4. `rocm-smi --showvbios` を実行し 4 枚の VBIOS 版数を記録 (D-4 の副次採取)
5. **dmesg baseline 行数を必ず記録**: `BASELINE=$(ssh mi25 "sudo dmesg | wc -l")`。SA R1 では kernel ring buffer 全流入で過去 fault が新規として偽計上された既知バグあり。集計時は `tail -n +$((BASELINE+1))` で差分だけを対象にする

### Phase 2 — smoke test (5〜10 分)

1. `run-a48e4-slot6.sh` (下記 Phase 3 で作成) を単発起動 → `/health` 確認
2. `python3 load_driver.py --trial-seconds 300 --trial-no smoke --endpoint http://10.1.4.13:8000 --model unsloth/Qwen3-8B-GGUF:Q6_K --server mi25 --backend vulkan --jsonl /tmp/smoke.jsonl` を 1 trial 走らせ、pp_tps / eval_tps を記録
3. pp_tps が SA 水準 (500+ t/s) か SLOT8 水準 (~200 t/s) かをレポート結論の限定条件に反映
4. **llama-server を明示停止** (Phase 3 の重複起動チェック回避、`recover_from_hang` 誤発火防止):
   ```bash
   ssh mi25 "pkill -f 'llama-server' 2>/dev/null; sleep 3; pgrep -f 'llama-server' && echo 'STILL RUNNING' || echo 'stopped'"
   ```

### Phase 3 — 24h キャンペーン Round 1

新しい attachment ディレクトリ `report/attachment/<ts>_mi25_a48e4_slot6_24h_round1/` を作成し、以下 5 スクリプトを SLOT8 R2 (`2026-07-02_102205_mi25_c48c4_slot8_24h_round2/`) からコピーして最小差分で改造:

1. **`run-a48e4-slot6.sh`** (fork of `run-c48c4-slot8.sh`):
   - `GGML_VK_IDX="3"` (元 "2")
   - コメント差し替え (`# a48e4 = SLOT6 (BDF 87:00.0) = GPU[3] = Vulkan idx 3`)
   - モデル・パラメータは同一 (Qwen3-8B Q6_K、`-b 2048 -ub 2048 --flash-attn 1` 他)
2. **`run_campaign_a48e4.sh`** (fork of `run_campaign_c48c4.sh`):
   - `ROCM_DEVICE_IDX=3` (元 2)
   - SCRATCH パスを新ディレクトリに
   - ロック識別子を `a48e4-slot6-24h-r1-<ts>` に
   - `MAX_TRIALS`/`MIN_TRIALS`/`HANG_SAFETY` を SA と同じ 200/80/10 に (SLOT8 R2 の 120/20/5 ではなく)
3. **`telemetry.sh`, `telemetry_pcie.sh`, `load_driver.py`**: SLOT8 R2 版をそのままコピー (改造不要)
4. **H-1 是正**: `run_campaign_a48e4.sh` の while ループ入口付近に `trap 'stop_telemetry; ssh mi25 "pkill -f \"dmesg -w\"; pkill -f \"tail -F /tmp/llama-server.log\"" 2>/dev/null' EXIT` を追加 (SA/SLOT8 でテレメトリデーモンが試験終了後も残存し commit 済みログが書き換わった問題の恒久対策)

キャンペーン起動:
```bash
nohup bash report/attachment/<ts>_mi25_a48e4_slot6_24h_round1/run_campaign_a48e4.sh \
  > report/attachment/<ts>_mi25_a48e4_slot6_24h_round1/nohup.out 2>&1 &
```

### Phase 4 — 中間監視 (2h / 8h / 20h の 3 チェックポイント)

- 各 CP で: trial 数、pp_tps 分布、Tj/power 分布、dmesg 追加行数、`/health` 応答、GPU 枚数
- fault 検出時: KVM スクショ (自動)、dmesg リングバッファ抽出、address / FAULT_STATUS の記録 → 中断はせず継続 (SA と同じく複数観測狙い、`HANG_SAFETY=10` まで許容)
- 12h 超で fault 0 の場合: SLOT8_R2 と同じく Round 2 (追加 24h) を予約

### Phase 5 — 終了処理 (レビュー B-1 の再発防止を含む)

- キャンペーン完走後、`stop_telemetry` 相当の呼び出しを明示 (SA/SLOT8 での H-1 未修正への対策)
- 全 log を commit 前に一度読み込み確定 → 以降テレメトリ書き込みが乗らないことを確認
- `make_summary_24h.py` を fork 実行し、fault 有無 / pp/eval 分布 / power/Tj 分布 / dmesg 追加行 / 全 trial 集計を 1 枚 PNG 化

## 統計・比較設計

**主要比較 (単群同士、多重補正なしで正当)**:

| 群 | trial | fault | 率 | 由来 |
|---|---|---|---|---|
| c48c4×SLOT6 SA | 147 | 2 | 1.36% | 2026-06-29 SA |
| **a48e4×SLOT6 (本試験 R1 のみ)** | **~120〜150** | ? | ? | Round 1 (24h) 確定分 |
| **a48e4×SLOT6 (R1+R2 拡張時)** | **~240** | ? | ? | R1 が 0 fault の場合の追加 24h |

- Fisher exact test で片側検定 (H1: 本試験の fault 率 > 0)
- **R1 のみで 0/150**: 95% 信頼上限 ≈ 3/150 ≈ 2.0% で SA 実測率 1.36% と統計的区別不能 → 「SA と両立する」で報告 (検出力 87%、Fable A-2 の断定回避)。R2 追加判断はここで
- **R1+R2 で 0/240**: 95% 信頼上限 ≈ 3/240 ≈ 1.25% で SA 実測率 1.36% を「上から抑える」水準 → 「SA と両立するが SLOT6 起因説を大幅減弱」まで踏み込める (検出力 96%)
- fault ≥1 かつシグネチャ一致 → SLOT6 起因を積極支持 → c48c4 個体単独起因の可能性大幅減
- **2×2 マトリクス整理表** をレポートに再掲: c48c4×SLOT6 / c48c4×SLOT8 / a48e4×SLOT6 (本試験) / a48e4×SLOT8 (未実施、必要なら次段)

## 検証 (試験完了時のチェックリスト)

- [ ] Round 1 完走 (24h または MAX_TRIALS 到達) — `campaign_vulkan.log` に「MAX_TRIALS 到達で終了」or「PHASE_CAP 到達で終了」の 1 行
- [ ] 全 trial で GPU[3] = a48e4 の Unique ID が変わっていないこと (`pre_r1_baseline.txt` と `post_r1_baseline.txt` を照合)
- [ ] 電力キャップが試験期間中 160W 維持 (BACO reset の再設定履歴を campaign log から grep)
- [ ] `trials_vulkan.jsonl` の trial 数、fault 数、pp_tps / eval_tps の中央値と p95
- [ ] fault 発生時は dmesg 該当バーストと SA/4card fault 5 件のアドレス・FAULT_STATUS・UTCL2 client を並置比較 (A-5 の宿題込み)
- [ ] レポート ([REPORT.md](/home/ubuntu/projects/llm-server-ops/REPORT.md) ルール準拠): `<ts>_mi25_a48e4_slot6_24h.md`、attachment に plan.md 添付、`report/INDEX.md` の「mi25 への横展開」節に追記
- [ ] 試験終了と同時にテレメトリデーモン停止を確認 (`ps -ef | grep telemetry` で残存 0)
- [ ] git status で M ファイル 0 (レビュー B-1 の再発防止)

## 対象外 / 保留事項

- **CLAUDE.md / メモリの修正** (D-5): 本試験結果を反映して一括更新 (試験前は現状のまま)
- **c48c4×SLOT8×4枚同時 24h** (D-2): 本試験の結果次第で位置づけが変わるため後回し
- **c3164 / 448c4 の SLOT6 補足試験**: 本試験が (d) SLOT6 起因を支持した場合の追加検証候補として温存
- **B-2 attachment ディレクトリ名不一致の是正**: 本試験終了後に対応
- **B-3 未追跡ファイル整理** (`MNL-1677.pdf`, `mb_slots_zoom.png`): 由来を確認して attachment に格納、本試験と独立
- **B-4 未 push 9 コミットの push**: 本試験と独立、実施可否はユーザ判断
- **VBIOS/RAS カウンタ 4 枚比較** (D-4): Phase 1 の baseline 採取で `rocm-smi --showvbios` は含めるが、詳細比較解析は別途
