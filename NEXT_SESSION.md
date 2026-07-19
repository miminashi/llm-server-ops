# 次セッションへの引き継ぎ

**作成**: 2026-07-12 04:26 JST

## 最優先: mi25 リブートループ (CMOS バッテリー切れ、ハードウェア修理必須)

### 症状

2026-07-12 02:07 JST 以降、mi25 (10.1.4.13) が **勝手なリブートを繰り返している**。約 2 時間で **20 回近くの再起動**。短命 (0 秒〜1 分) と 5〜10 分もつブートが混在:

```
boot -19  02:07:40 → 02:08:50  (1m10s)
boot -18  02:11:22 → 02:11:22  (0s = 即死)
boot -17  02:15:23 → 02:23:18  (7m55s)
boot -16  02:25:44 → 02:25:45  (1s)
... (中略) ...
boot -2   04:03:58 → 04:07:24  (3m26s)
boot -1   04:09:51 → 04:09:51  (0s)
boot 0    04:17:59 → 現在稼働中  (作成時点で 4m 経過)
```

全ブートで `journalctl -b -N -k` に amdgpu fault / GPU reset / kernel panic は 0 件。**OS レベルの障害ではない**。

### 根本原因 (ほぼ確定)

**BMC センサ**: `VBAT` (マザーボード CMOS/RTC バッテリー) = **1.624V**、閾値以下:

| 閾値 | 値 |
|---|---|
| Lower Non-recoverable | 2.326V |
| Lower Critical | 2.430V |
| Lower Non-Critical | 2.508V |
| Upper Non-Critical (通常運用値) | 3.678V |

現在の VBAT 1.624V は **Lower Non-recoverable を大きく下回っている** = **CR2032 コイン電池が完全に切れている**。BMC SEL 458 件のうち **428 件超が `Voltage VBAT Lower Non-recoverable going low`** (直近 30 件は 2026-07-12 の 12:03-13:16 BMC 時刻 = **03:03-04:16 JST に集中**、リブートループ時刻と完全一致)。

**BMC 時刻オフセット注意**: BMC RTC は現在 `13:26 JST` を表示、実時刻は `04:26 JST` = **BMC 時刻が 9 時間先行**。CMOS/RTC の時刻同期が壊れている副作用。SEL のタイムスタンプは -9h して読む必要がある。

**その他の BMC センサは全て正常**:
- CPU1 Temp 38°C / CPU2 Temp 41°C / System Temp 35°C
- 12V=11.937V / 5VCC=5.156V / 3.3VCC=3.384V (すべて閾値内)
- Chassis: `Power Overload=false / Main Power Fault=false / Cooling/Fan Fault=false`

つまり **電源系・冷却系・CPU 系は健全**、CMOS バッテリー単独の障害。

### 因果連鎖の推定

CMOS/RTC バッテリー切れ → BIOS 設定/RTC が保持できない → 起動途中で不整合を検出 or watchdog reset → リブート → ループ。5〜10 分もつブートは Ubuntu が起動できたが稼働中に不整合検出、0 秒即死のブートは起動プロセス初期で破綻。

### 対処 (ユーザ介入必須)

1. **CR2032 コイン電池を物理交換**する (最優先、これで根本解決)
2. 交換後、BIOS 設定を default → 必要な項目 (BIOS 内 CPU2 SLOT8 / SLOT6 の PCIe 認識設定など) を再設定
3. BMC 時刻同期を再設定 (NTP か手動)
4. 電源復帰後、`ssh mi25 "sudo dmesg | wc -l"` で baseline 再取得

**Claude が (BMC 経由で) できること**:
- 現状の状態確認 (`bmc-power.sh mi25 status`、`bmc-screenshot.sh mi25 <path>`)
- SEL の再取得 (`ipmitool -I lanplus -H 10.1.4.7 -U ADMIN -P ADMIN sel elist`)
- 電源 OFF (`bmc-power.sh mi25 off`) — **物理修理までシャットダウンするのはあり**、リブートループでの消耗を止められる

**Claude が (BMC 経由で) できないこと**: バッテリー物理交換、BIOS 設定変更

### 保全済みの証跡

- `/tmp/claude-1000/.../scratchpad/mi25_hang_2026-07-12_041620.png` — BIOS POST 段階 (`PEI--Intel Reference Code Execution..`) のスクショ
- `/tmp/claude-1000/.../scratchpad/mi25_hang_2026-07-12_041702_followup.png` — GRUB メニュー (Ubuntu 選択、29秒 auto-boot 直前)
- `/tmp/claude-1000/.../scratchpad/mi25_track_{1..5}_*.png` — 45 秒間隔で 5 回、ブートシーケンス追跡
- `/tmp/claude-1000/.../scratchpad/mi25_bmc_sel_20260712.log` — BMC SEL 全 458 件

**注意**: scratchpad は session-specific なので、レポート化するなら `report/attachment/<ts>_mi25_cmos_battery_reboot_loop/` に移動要。

## 完了済み (本セッション以前の対応)

### Fable レビュー D-1 決定実験は完全達成 (次セッションで追加調査不要)

- [レポート: 2026-07-10_105706_mi25_a48e4_slot6_24h_x2.md](report/2026-07-10_105706_mi25_a48e4_slot6_24h_x2.md)
- **累積 221 trial / 0 fault**、Fisher exact vs c48c4×SLOT6 累積 5/235 で **p=0.0356 (5% 有意)**
- **(d) SLOT6 単独環境起因説を統計的に棄却**、fault は **c48c4 個体または c48c4×SLOT6 相互作用**
- 2×2 マトリクス完成:
  - c48c4×SLOT6 = 5/235 (2.13%) ★fault 集中
  - c48c4×SLOT8 = 0/221 (0%)
  - **a48e4×SLOT6 = 0/221 (0%)** ★本実験
- Fable レビュー B-1 (テレメトリデーモン残存) の恒久修正確認済 (`trap 'stop_telemetry' EXIT INT TERM` in `run_campaign_a48e4.sh`)

### mi25 リブート事象の履歴 (今回とは独立の可能性)

本試験期間 (07-05 23:44 〜 07-08 08:04) 中は 0 回だが、それ以降:

- 07-09 07:15 (1 回目、当初は Unattended Upgrades 起因と推定)
- 07-09 13:43 (2 回目)
- 07-10 09:01 (3 回目)

現時点で振り返ると、**これらも VBAT 低下の初期症状だった可能性が高い**。当時のレポート ([a48e4_slot6_24h_x2 副次観測 4](report/2026-07-10_105706_mi25_a48e4_slot6_24h_x2.md)) では「Unattended Upgrades 起因と推定」と記録したが、**次セッションで訂正候補**: SEL の VBAT アラート開始日時を遡って調査すれば、リブート事象の起点と VBAT 降下の起点が一致するか確認できる。

## 未完タスク (優先度順、mi25 復旧後)

### 決定実験系

1. **c48c4×SLOT8×4-card 同時 24h** (Fable レビュー D-2) — SLOT8 化した c48c4 が他 3 枚も稼働時に fault しないか。本試験で SLOT6 起因は棄却済のため、この試験の意義は「SLOT8 運用の運用継続前提条件を確定」に絞られる
2. **VBIOS/RAS/ECC カウンタ 4 枚詳細比較** (D-4 の残り) — VBIOS は 4 枚同一 (`113-D0513700-001`) を確認済、RAS uncorrectable カウント等の個体差を採取
3. **fault シグネチャ台帳の再監査** (Fable A-5) — stand_alone_24h の 3 件目 (uptime 43173) の由来ラベル vs 算術の緊張関係、fault アドレス (0x33000 vs 0x100000000) の体系的解析

### CLAUDE.md / メモリ更新 (Fable D-5)

以下 2 ファイルの「(b) 個体ロジック起因確定・物理交換相当/必須」表現を更新:

- [CLAUDE.md](CLAUDE.md)
- [~/.claude/projects/-home-ubuntu-projects-llm-server-ops/memory/project_mi25_gpu4_pcie_dropout.md](/home/ubuntu/.claude/projects/-home-ubuntu-projects-llm-server-ops/memory/project_mi25_gpu4_pcie_dropout.md)

新しい表現:

> **「fault は c48c4×SLOT6 の組み合わせでのみ観測 (5/235)、c48c4×SLOT8 (0/221) と a48e4×SLOT6 (0/221) はいずれも 0。SLOT6 単独環境起因は棄却済、c48c4 個体または c48c4×SLOT6 相互作用が真の原因。SLOT8 での c48c4 運用は現時点で有効な回避策」**

### 運用是正 (Fable B-3/B-4)

- 未追跡ファイル `MNL-1677.pdf` / `mb_slots_zoom.png` の由来確認と attachment 格納 (SLOT 番号再訂正の裏付け証跡か要確認)
- 未 push commit の push 可否判断 (ローカルに主要結論が滞留、ディスク故障で喪失リスク)

## 初動手順 (次セッション開始時)

1. mi25 の状態確認: `ping -c 3 10.1.4.13` と `ssh mi25 uptime`
   - 稼働中: → 4 でリブート履歴分析
   - 停止中/リブートループ中: → 2
2. BMC 経由の状態確認:
   ```bash
   .claude/skills/gpu-server/scripts/bmc-power.sh mi25 status
   ipmitool -I lanplus -H 10.1.4.7 -U ADMIN -P ADMIN sensor | grep -iE "VBAT|CPU.*Temp|12V|5VCC|3\.3VCC"
   ipmitool -I lanplus -H 10.1.4.7 -U ADMIN -P ADMIN sel elist | tail -30
   ```
3. VBAT が改善していない (< 2.5V) 場合、**バッテリー交換が完了しているかユーザに確認**。未対応なら:
   - リブートループ継続なら `.claude/skills/gpu-server/scripts/bmc-power.sh mi25 off` で電源を止める判断もあり (要ユーザ承認)
4. mi25 復旧後: `ssh mi25 "sudo journalctl --list-boots --no-pager 2>/dev/null | tail -30"` でリブート履歴確認
5. VBAT アラート開始日時を SEL から遡って調査 (今回の 428 件超のうち最古のアラート時刻を確認)、07-09 の 3 回リブートとの相関を検証
