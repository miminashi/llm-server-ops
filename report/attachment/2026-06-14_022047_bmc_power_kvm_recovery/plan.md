# mi25 BMC 緊急操作（電源リセット + KVM スクリーンショット）の整備

## Context（背景）

`report/2026-06-13_112006_mi25_qwen36_128k.md` の探索終盤で、mi25（Supermicro X10DRG-Q）の
ルート FS が ext4 ジャーナル破損で read-only 再マウントされ、OS がクラッシュした。
こうした「OS がハング/クラッシュして SSH が効かない」事態に備え、**OS に依存しない
out-of-band（BMC 経由）の復旧手段**を整備したい。具体的には:

1. **BMC からの電源リセット**（強制再起動・電源 ON/OFF）
2. **KVM スクリーンショット取得**（POST 画面・パニック画面・BIOS を画像で確認）

別プロジェクト `pvese` の Supermicro BMC 操作スキルを流用する。

### 実機調査で判明した制約（設計の根拠）

実機 BMC（10.1.4.7, claude/Claude123）への読み取り専用プローブで確認:

| 項目 | 結果 |
|------|------|
| ボード/FW | X10DRG-Q / BMC FW 3.94 / ATEN(AMI) / IPMI 2.0 |
| **Redfish** | **DCMS ライセンス未活性で全滅**（`OemLicenseNotPassed: SUM DCMS OOB needed`）。電源・スクショとも不可 |
| **IPMI (lanplus)** | **完全動作**（`chassis status` で `System Power: on` 取得成功） |
| HTML5 KVM ビューア | `man_ikvm_html5_bootstrap` が `#noVNC_canvas`（2D canvas, classic noVNC）を使用 → pvese の `bmc-kvm-interact.py` のセレクタと**完全一致** |
| CapturePreview.cgi | 存在するが CSRF トークン必須（`Token Value is not matched`）で純 curl 化は不安定 → 不採用 |

**結論**:
- **電源制御 = IPMI（`ipmitool -I lanplus`）一択**。pvese / gpu-server の Redfish 系は mi25 では使えない。
- **スクリーンショット = pvese の Playwright canvas 方式をそのまま流用**（X10 の noVNC は 2D canvas なので `toDataURL()` が有効）。

### 確定済みの方針（ユーザ確認済み）

- 配置先: **既存 `gpu-server` スキルに追加**（サーバ台帳・ロック・`.env` 認証情報が集約済み、CLAUDE.md も GPU 操作の入口を gpu-server と定義）。
- 検証: **gpu-server ロック取得の上で実リセットを 1 回**実行可。スクショは 10 回程度反復。

---

## 変更対象ファイル

すべて `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/` 配下。

### 新規スクリプト

1. **`scripts/bmc-power.sh`**（IPMI 電源制御, 新規）
   - pvese の Redfish 版ではなく **ipmitool lanplus** ベースで実装（Redfish は mi25 で不可のため）。
   - サーバ名 → BMC 認証情報を `~/.config/gpu-server/.env` から解決（後述）。
   - コマンド:
     - `status` … `ipmitool ... chassis status`（`System Power` を抽出）
     - `reset` … `ipmitool ... chassis power reset`（暖機なしの即時リセット = 復旧本命）
     - `cycle [wait]` … `chassis power off` → wait → `on`（コールドブート）
     - `on` / `off`（hard off）/ `soft`（ACPI soft-off）
   - 既存 `scripts/power.sh`（iLO5/Redfish, t120h-p100 用）と**役割分担**: Redfish が使える HPE 機は従来通り `power.sh`、Supermicro/IPMI 機は `bmc-power.sh`。`bmc.md` に使い分けを明記。
   - 慣習に合わせ `set -euo pipefail`、日本語ログ、終了コード（2=引数, 3=接続失敗, 10=認証情報未設定）。

2. **`scripts/bmc-kvm.py`**（KVM スクショ/キー送信, pvese から移植）
   - `pvese/scripts/bmc-kvm-interact.py` を**ほぼそのまま移植**（`screenshot` / `sendkeys` / `type`）。
     セレクタ `#noVNC_canvas`・login.cgi フローは実機で一致確認済み。
   - venv 自動 re-exec 部分を、本スキルの venv パス（`.claude/skills/gpu-server/.venv/bin/python`）に合わせて修正。
   - 認証情報は引数（`--bmc-ip/--bmc-user/--bmc-pass`）。

3. **`scripts/bmc-screenshot.sh`**（薄いラッパ, 新規）
   - venv の存在確認 → 無ければ案内、サーバ名 → BMC 認証情報を `.env` から解決 → `bmc-kvm.py screenshot` を呼ぶ。
   - 例: `bmc-screenshot.sh mi25 out.png`

4. **`scripts/bmc-setup.sh`**（認証情報登録, 新規）
   - 既存 `power.sh` の `setup` を踏襲。`ipmitool ... mc info` で疎通テスト後、
     `~/.config/gpu-server/.env` に `BMC_<SERVER>_HOST/USER/PASS` を保存（chmod 600）。
   - 例: `bmc-setup.sh mi25 10.1.4.7 claude Claude123`

5. **`scripts/setup-bmc-venv.sh`**（venv 構築, 新規）
   - `uv venv .claude/skills/gpu-server/.venv && uv pip install --python ... playwright`。
     chromium は共有キャッシュ `~/.cache/ms-playwright/`（既存）を利用するため再 DL 不要。
   - 既存 `setup-llama-cpp.sh` 等と同じ慣習。

### ドキュメント・設定

6. **`bmc.md`**（新規）… BMC 操作の手引き。サーバ別 BMC 台帳、IPMI/Redfish の使い分け、
   電源コマンド一覧、スクショ手順、トラブルシュート（KVM 未接続時の再試行など）。
   - **命名の使い分けを明記**: `power.sh`=Redfish/iLO5（HPE 機, 例 t120h-p100）、
     `bmc-power.sh`=IPMI lanplus（Supermicro 機, 例 mi25。Redfish ライセンス不要）。
7. **`SKILL.md`**（更新）… 既存の iLO 表（**line 122-124**, 現状 `t120h-p100 | 10.1.4.8` のみ）を
   「BMC 一覧」に拡張し **mi25 = 10.1.4.7（IPMI）** を追記。`bmc.md` への参照リンクと、
   `~/.config/gpu-server/.env` の `BMC_<SERVER>_*` キー説明を追記。
8. **`.gitignore`**（更新, **必須**）… 現状 `*.lock` / `.env` のみ。新規 venv が追跡されないよう
   `.claude/skills/gpu-server/.venv/`（または `.venv/`）を追加。chromium は共有キャッシュ
   `~/.cache/ms-playwright/`（リポジトリ外）なので追加不要。
9. **`CLAUDE.md`**（更新, 任意）… クイックリファレンスに mi25 BMC（10.1.4.7）と
   「OS ハング時は `gpu-server` の bmc-power.sh / bmc-screenshot.sh」を一行追記。

### 既存パターンの再利用

- 認証情報ストア: `power.sh` の `~/.config/gpu-server/.env` 方式（`VAR_PREFIX_HOST/USER/PASS`、chmod 600、`grep -v` で上書き）をそのまま流用。プレフィックスのみ `ILO_` → `BMC_`。
- ロック: `scripts/lock.sh` / `unlock.sh` / `lock-status.sh`（`VALID_SERVERS="mi25 t120h-p100 t120h-m10"`）。
- 移植元: `pvese/scripts/bmc-power.sh`（postcode の IPMI raw だけ流用可）, `pvese/scripts/bmc-kvm-interact.py`（スクショ本体）。

---

## BMC 台帳（スクリプトに埋め込む既定値）

| サーバ | BMC IP | 認証 | トランスポート |
|--------|--------|------|----------------|
| mi25 | 10.1.4.7 | claude/Claude123 | **IPMI**（Redfish 不可） |
| t120h-p100 | 10.1.4.8 | （iLO5） | Redfish（既存 power.sh） |
| t120h-m10 | 未確認 | — | 未確認 |

認証情報はスクリプトにハードコードせず `.env` に保存（`.gitignore` に `.env` 済み）。
セットアップ時に既定 IP を提示するため、サーバ名→既定 BMC IP の対応表のみスクリプト内に持つ。

---

## 検証（実機, 10 回程度 + 実リセット 1 回）

CLAUDE.md 準拠でプロジェクトルートからの相対パスで実行。**gpu-server ロックを取得してから**実施。

```bash
cd /home/ubuntu/projects/llm-server-ops
# 0. venv 構築 + 認証情報登録
.claude/skills/gpu-server/scripts/setup-bmc-venv.sh
.claude/skills/gpu-server/scripts/bmc-setup.sh mi25 10.1.4.7 claude Claude123
# 1. ロック取得（第2引数は session_id。省略時は hostname-pid-timestamp が自動付与）
.claude/skills/gpu-server/scripts/lock.sh mi25
```

> 注: `status` / スクショは BMC への読み取り的アクセスで GPU リソースを専有しないが、
> 実リセットを伴う検証セッション全体を安全側に倒してロック下で実施する。

### A. 電源 status（読み取り、複数回）
```bash
.claude/skills/gpu-server/scripts/bmc-power.sh mi25 status   # → "System Power: on" を期待
```

### B. KVM スクリーンショット（10 回反復、安定性確認）
```bash
for i in 01..10:  bmc-screenshot.sh mi25 /tmp/bmc_shot_$i.png
```
- 各 PNG が有効画像か（`file` で PNG 判定、サイズ > 数 KB、全黒でないか）を確認。
- **想定される問題と対処**（発見次第修正）:
  - noVNC が自動接続せず canvas が小さい（20px）まま → `#noVNC_connect_button` をクリックして接続を待つ処理を追加。
  - `toDataURL()` が黒画 → `locator("#noVNC_canvas").screenshot()` 方式へ切替（pvese の知見）。
  - SID セッション枯渇/タイムアウト → リトライ・タイムアウト調整。

### C. 実電源リセット（1 回のみ）
1. mi25 が他セッションで未使用 & なるべくアイドル（llama-server 停止 or 退避済み）であることを確認。
2. リセット前に状態を記録: `bmc-power.sh mi25 status` + `bmc-screenshot.sh mi25 /tmp/pre_reset.png`。
3. `bmc-power.sh mi25 reset` を実行。
4. 復旧過程を観察: 数十秒間隔で `bmc-screenshot.sh` を撮り、POST → ブート → ログイン画面の遷移を画像で確認。
5. `ping` / `ssh mi25` 復帰を待ち、`uptime` で再起動を確認。
6. 撮影した一連の PNG をレポートに添付。

### D. 後始末
```bash
.claude/skills/gpu-server/scripts/unlock.sh mi25
```

### レポート作成（REPORT.md 準拠）
- 本タスクは plan mode で計画したため、対のレポートを `report/` に作成（CLAUDE.md 必須ルール）。
- タイトル 50 字以内、核心発見サマリにスクショ PNG を画像埋め込み（memory: feedback_report_title 準拠）。
- 内容: Redfish 不可 → IPMI 採用の判断、スクショ方式、10 回反復で見つかった問題と修正、実リセットの遷移画像。

---

## 完了条件

- `gpu-server` スキルに `bmc-power.sh` / `bmc-kvm.py` / `bmc-screenshot.sh` / `bmc-setup.sh` / `setup-bmc-venv.sh` と `bmc.md` が追加され、SKILL.md に BMC 情報が反映されている。
- mi25 で `status` 取得・スクショ 10 回・実リセット 1 回が成功し、発見された問題が修正済み。
- 認証情報は `.env`（gitignore 済み）にのみ保存され、コミット対象に含まれない。
- 対のレポートが `report/` に作成されている。
