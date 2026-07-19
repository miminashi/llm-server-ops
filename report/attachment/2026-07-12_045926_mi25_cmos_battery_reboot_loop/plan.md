# mi25 CMOS バッテリー切れ リブートループ対応 & 副次課題消化

## Context

2026-07-12 02:07 JST 以降、mi25 (10.1.4.13) が `勝手なリブートを 20 回近く繰り返す` 事象に陥り、
[NEXT_SESSION.md](../../projects/llm-server-ops/NEXT_SESSION.md) にて根本原因は **BMC センサ VBAT = 1.624V (Lower Non-recoverable 2.326V を大幅下回る)** = **CMOS/RTC コイン電池切れ** とほぼ確定している。BMC SEL 458 件のうち 428 件超が `Voltage VBAT Lower Non-recoverable going low` で、直近 30 件のタイムスタンプがリブートループ時刻と完全一致 (BMC 時刻 9 時間先行の補正込)。他センサ (CPU 温度・電源電圧・冷却) はすべて正常のため電源系・冷却系・CPU 系は健全、CMOS バッテリー単独障害。

物理修理 (CR2032 交換 + BIOS 再設定) はユーザ介入必須。本セッションでは Claude ができる範囲で:
1. 現況確認と、リブートループが続いていれば消耗を止める暫定措置 (BMC 経由の電源停止, ユーザ最終承認要)
2. VBAT アラート開始日時の遡及調査で「07-09 の 3 回リブート = Unattended Upgrades 起因推定」の妥当性を検証
3. 完了レポート作成と、scratchpad 8 点の証跡を `report/attachment/` へ移動
4. 併せて Fable レビュー D-5 の memory 更新 (a48e4×SLOT6=0/221 反映、「(b) 個体ロジック起因確定」表現を「c48c4×SLOT6 相互作用または c48c4 個体」に修正)

を実施し、mi25 復旧待ちの間の準備を完了させる。

## Plan

### Phase A — 現況確認 (BMC 経由 read-only, ロック不要)

1. `ping -c 3 10.1.4.13` と `ssh -o ConnectTimeout=5 mi25 uptime` で mi25 の生存確認
2. `.claude/skills/gpu-server/scripts/bmc-power.sh mi25 status` で BMC 経由の Power 状態
3. `ipmitool -I lanplus -H 10.1.4.7 -U ADMIN -P ADMIN sensor` で **VBAT / CPU Temp / 12V/5VCC/3.3VCC / Chassis** を採取 (VBAT が閾値内に戻っていないか確認)
4. `ipmitool -I lanplus -H 10.1.4.7 -U ADMIN -P ADMIN sel elist` を全件 stdout に取得 (scratchpad に保全)、末尾 30 件で VBAT アラートの継続性確認

**判別ロジック**:
- 稼働中 (ssh 応答 + Power=on) → Phase B-1
- リブートループ継続 (ssh 断続 or Power flapping + VBAT < 2.5V) → Phase B-2
- 既に自然電源断 (Power=off) → Phase B-3

### Phase B-1 — 稼働中の場合

- `ssh mi25 "sudo journalctl --list-boots --no-pager 2>/dev/null | tail -30"` で 07-12 02:07 以降のブートが安定 (連続稼働 > 10 分) しているか確認
- `.claude/skills/gpu-server/scripts/bmc-screenshot.sh mi25 <scratchpad>/mi25_state_<ts>.png` で現在の画面を保全
- リブート再発の可能性が残るため、状態のみ確認して介入はしない

### Phase B-2 — リブートループ継続の場合 (電源停止許可済)

1. `.claude/skills/gpu-server/scripts/bmc-screenshot.sh mi25 <scratchpad>/mi25_before_off_<ts>.png` で現在の POST/GRUB 画面を保全
2. `.claude/skills/gpu-server/scripts/lock.sh mi25` でロック取得 (bmc.md の推奨)
3. **ユーザに最終承認**「VBAT=<値>, リブートループ継続中。`bmc-power.sh mi25 off` を実行してよいか」を明示提示
4. 承認後 `bmc-power.sh mi25 off` 実行、`bmc-power.sh mi25 status` で Power=off 確認
5. ロックは物理修理完了までユーザ判断で保持 or 解放 (要ユーザ確認)

### Phase B-3 — 既に電源断の場合

- 状態のみ記録、介入なし。VBAT の現在値だけ SEL から追加確認

### Phase C — VBAT 履歴分析 (07-09 リブート事象の相関検証)

- Phase A で取得した SEL 全件 (458 件 → 現時点で追加あり得る) から `Voltage VBAT` のイベントだけ抽出
- 最古の `Lower Non-recoverable going low` の BMC タイムスタンプを特定 → -9h 補正で JST 変換
- 07-09 07:15 / 07-09 13:43 / 07-10 09:01 の 3 回リブート時刻と比較
- 判定:
  - VBAT アラート開始が 07-09 07:15 以前 → **Unattended Upgrades 起因推定は誤り、VBAT 起因に訂正**
  - 開始が後 → Unattended Upgrades 起因推定は妥当、今回とは独立事象
- 結果を Phase E のレポートに記述

### Phase D — 証跡整理 (scratchpad → report/attachment/)

対象:
- `mi25_hang_2026-07-12_041620.png` — BIOS POST 画面
- `mi25_hang_2026-07-12_041702_followup.png` — GRUB メニュー
- `mi25_track_{1..5}_*.png` — ブートシーケンス追跡 5 枚
- `mi25_bmc_sel_20260712.log` — SEL 458 件
- Phase A/B で新規取得する PNG / SEL

格納先: `report/attachment/2026-07-12_<hhmmss>_mi25_cmos_battery_reboot_loop/`

`cp` で report/attachment/ に配置 (scratchpad は session-specific なので原本を残す必要なし → mv でも良いが、今セッション中は参照残しで cp)。

### Phase E — レポート作成

- パス: `report/2026-07-12_<hhmmss>_mi25_cmos_battery_reboot_loop.md`
- 参照レポート雛形は [REPORT.md](../../projects/llm-server-ops/REPORT.md) に従う
- 節構成:
  1. **核心発見サマリ** — VBAT=1.624V (閾値 2.326V), CMOS バッテリー切れによるリブートループ 20 回近く。SEL 428 件と時刻完全一致。他センサ全て正常。物理交換必須。POST 画面 PNG 埋め込み
  2. 症状の時系列 — journalctl `list-boots` の抜粋 (稼働中に取れた場合)
  3. BMC センサ値の全体像 — 表形式で VBAT / 温度 / 電圧 / Chassis
  4. VBAT 履歴分析結果 (Phase C) — 07-09 の 3 回リブートとの相関判定
  5. 因果連鎖の推定 — CMOS/RTC → BIOS 設定/RTC 保持破綻 → 起動途中で不整合検出 → リブート
  6. 対処 — 物理修理手順、Claude 側の暫定措置 (電源停止した場合はその記録)
  7. 副次発見 — 07-09 リブートの再解釈、`2026-07-10_105706_mi25_a48e4_slot6_24h_x2.md` の副次観測 4 の訂正候補
- INDEX.md の「11. mi25 への横展開」節末尾に追記

### Phase F — Fable D-5: memory / CLAUDE.md 更新

対象ファイル:
- `/home/ubuntu/.claude/projects/-home-ubuntu-projects-llm-server-ops/memory/project_mi25_gpu4_pcie_dropout.md`
- `/home/ubuntu/projects/llm-server-ops/CLAUDE.md` (該当箇所があれば)

修正内容 (NEXT_SESSION.md L111-113 の新表現):
> `fault は c48c4×SLOT6 の組み合わせでのみ観測 (5/235)、c48c4×SLOT8 (0/221) と a48e4×SLOT6 (0/221) はいずれも 0。SLOT6 単独環境起因は棄却済、c48c4 個体または c48c4×SLOT6 相互作用が真の原因。SLOT8 での c48c4 運用は現時点で有効な回避策`

memory の該当行 (2×2 マトリクス、a48e4×SLOT6 の反映漏れ) を編集。CLAUDE.md 側は grep で確認して必要なら同期。

## 対象ファイル (代表)

- 新規: `report/2026-07-12_<hhmmss>_mi25_cmos_battery_reboot_loop.md`
- 新規: `report/attachment/2026-07-12_<hhmmss>_mi25_cmos_battery_reboot_loop/` (PNG + SEL log)
- 修正: `report/INDEX.md` (mi25 節への追記 1 行)
- 修正: `/home/ubuntu/.claude/projects/-home-ubuntu-projects-llm-server-ops/memory/project_mi25_gpu4_pcie_dropout.md`
- 修正候補: `CLAUDE.md` (該当あれば)

## 使用する既存資産

- `.claude/skills/gpu-server/scripts/bmc-power.sh` (status / off)
- `.claude/skills/gpu-server/scripts/bmc-screenshot.sh` (KVM PNG)
- `.claude/skills/gpu-server/scripts/lock.sh` (電源操作時のロック)
- `bmc-setup.sh` で登録済みの `~/.config/gpu-server/.env` (BMC 認証)
- [REPORT.md](../../projects/llm-server-ops/REPORT.md) のレポートフォーマット

## Verification

- **Phase A**: ping / ssh 応答, `bmc-power.sh status` 終了コード 0, `ipmitool sensor` に VBAT 行が含まれる
- **Phase B-2**: `bmc-power.sh mi25 status` が `off` を返す
- **Phase C**: SEL 全件のうち VBAT イベント数と最古タイムスタンプが明示できる
- **Phase D**: `ls -la report/attachment/2026-07-12_*_mi25_cmos_battery_reboot_loop/` に全 PNG + SEL log が存在
- **Phase E**: レポートを [REPORT.md](../../projects/llm-server-ops/REPORT.md) と照合、`report/INDEX.md` にリンク追加、既存 mi25 リブート系レポート (`a48e4_slot6_24h_x2` の副次観測 4) との相互参照
- **Phase F**: `grep -n "b) 個体ロジック起因確定" memory/*.md CLAUDE.md` が 0 hit、新表現の a48e4×SLOT6=0/221 が反映

## 実施しないこと

- CMOS バッテリー物理交換 (ユーザ介入)
- BIOS 設定再構成 (ユーザ介入)
- BMC 時刻同期の再設定 (ユーザ介入)
- 電源リセット (`reset`) — バッテリー切れ状態でリセットしても症状は続くだけなので無意味
- Fable D-2 (c48c4×SLOT8×4-card 24h) や D-3/D-4 の残り — mi25 復旧後に別セッションで実施
- 未 push commit の push (B-4) — 内容確認は本セッション対象外
