# llama-up.sh / llama-down.sh の mi25(IPMI)対応

## Context

`llama-up.sh` / `llama-down.sh` は電源制御に HPE iLO5/Redfish 専用の `power.sh` を**無条件**で呼ぶ。mi25 は Supermicro/IPMI 機で Redfish 不可のため、実行すると最初の電源確認ステップで `power.sh` が **exit 10(iLO認証情報未設定)** で失敗する(実機で確認済み)。mi25 の電源制御は IPMI 用の別スクリプト `bmc-power.sh` で行う必要がある。

本変更で `llama-up.sh` / `llama-down.sh` を mi25(IPMI)と t120h-p100(iLO5)の両対応にし、mi25 でも統合スクリプトで起動・停止できるようにする。

### 2つの電源スクリプトの差異(設計の核心)

| | `power.sh`(iLO5/Redfish) | `bmc-power.sh`(IPMI) |
|---|---|---|
| status 出力 | `t120h-p100: 電源状態 = On`(**On/Off**) | `mi25: System Power: on`(**on/off** 小文字) |
| グレースフル停止 | `off`(Redfish GracefulShutdown) | **`soft`**(ACPI)。`off` は**ハード即時断=FS破損リスク** |
| exit 10 | 認証情報未設定 | 認証情報未設定 / exit 3=IPMI接続失敗 |

→ 抽象「off」は **{iLO5: `power.sh off`, IPMI: `bmc-power.sh soft`}** にマップする(ハード断を避ける)。status は大小文字を吸収して正規化する。

## 採用アプローチ: 電源抽象化ラッパー `power-ctl.sh` を新規作成

サーバ種別判定(IPMI機 vs Redfish機)を1箇所に集約するディスパッチャを `gpu-server/scripts/` に追加し、`llama-up.sh`/`llama-down.sh` は `power.sh` 呼び出しをこれに差し替えるだけにする。種別→トランスポートの知識は gpu-server 層に閉じ、llama-server 層に漏らさない。各スクリプトに分岐を重複させる案(B)より、off のグレースフル変換・status 正規化を単一実装にできる点で優れる。

## 変更内容

### 1. 新規: `.claude/skills/gpu-server/scripts/power-ctl.sh`

`power-ctl.sh <server> <status|on|off>` の薄いディスパッチャ。

- **サーバ種別 case(真実源)**: `t120h-p100`→`hpe` / `mi25`→`supermicro` / `t120h-m10`→`hpe`(BMC方式未確認、認証未設定なら exit 10 で安全に失敗するため既定 hpe) / `*`→`hpe`。
- **status**: 下位の status を呼び、人間向け生出力は **stderr** に流し、**stdout には `On`/`Off`/`Unknown` の1語だけ**を正規化出力(`grep -oiE` で大小吸収)。
- **on**: 下位の `on` をそのまま。
- **off**: hpe→`power.sh off` / supermicro→`bmc-power.sh soft`(グレースフル統一)。
- **終了コード伝播**: 下位の exit(10=認証未設定 / 3=IPMI接続失敗 / 1 等)をそのまま返す。下位が出す setup 案内(stderr)に委譲し、power-ctl 独自の案内は持たない。
- **実装注意(pipefail バグの回避 — 最重要)**:
  - `set -euo pipefail` 下で grep のパイプはマッチ0件だと exit 1 になり、**pipefail でパイプ全体が非ゼロ → 代入失敗 → set -e で power-ctl.sh 自体が落ちる**。`|| true` は必ず**パイプライン全体の末尾(`tail` の後)**に置く:
    ```bash
    STATE="$(printf '%s\n' "$OUT" | grep -oiE 'on|off' | tail -n1 || true)"
    ```
    (`grep ... || true | tail` は `||` の優先順位的に無効。誤配置に注意。)
  - **下位 exit の伝播は意図的に活かす**: `OUT="$("$SCRIPT_DIR/bmc-power.sh" "$SERVER" status)"` で下位が exit 10/3 を返すと、この代入は単純コマンド置換(`local` を使わない)なので set -e が作動し、その終了コードのまま power-ctl.sh が停止する。**`OUT` 取得は必ずトップレベル(関数内 `local VAR=$()` にしない)**。`local` を付けると終了コードが local の成功で握りつぶされ伝播しなくなる罠がある。
  - status 正常時(電源 On/Off いずれも下位は exit 0)は OUT 取得成功 → 正規化 → stdout に1語、が通る。

### 2. 変更: `.claude/skills/llama-server/scripts/llama-up.sh`(38-49行)

```diff
-POWER_OUT=$("$GPU_SCRIPTS_DIR/power.sh" "$SERVER" status)
-echo "$POWER_OUT"
-POWER_STATE=$(echo "$POWER_OUT" | grep -oE 'On|Off' | tail -1)
-if [ -z "$POWER_STATE" ]; then
+POWER_STATE=$("$GPU_SCRIPTS_DIR/power-ctl.sh" "$SERVER" status)
+if [ "$POWER_STATE" != "On" ] && [ "$POWER_STATE" != "Off" ]; then
   echo "ERROR: 電源状態を判定できませんでした" >&2
   exit 1
 fi
```
```diff
-  "$GPU_SCRIPTS_DIR/power.sh" "$SERVER" on
+  "$GPU_SCRIPTS_DIR/power-ctl.sh" "$SERVER" on
```
(生出力は power-ctl が stderr に出すので 39行の `echo "$POWER_OUT"` は削除。`Unknown` は `!=On && !=Off` でエラー扱いになる。)

### 3. 変更: `.claude/skills/llama-server/scripts/llama-down.sh`(95-96行)

```diff
-echo "==> [4/4] $SERVER の電源を OFF にします..."
-if ! "$GPU_SCRIPTS_DIR/power.sh" "$SERVER" off; then
-  echo "WARNING: power.sh off に失敗しました（API エラー等）。" >&2
+echo "==> [4/4] $SERVER の電源を OFF にします（グレースフル）..."
+if ! "$GPU_SCRIPTS_DIR/power-ctl.sh" "$SERVER" off; then
+  echo "WARNING: 電源 OFF に失敗しました。" >&2
```
(mi25 では自動的に `bmc-power.sh soft` にマップ。Step3 の「power off 前に unlock」順序ロジックは soft でも成立し変更不要。)

### 4. 変更: `.claude/skills/gpu-server/scripts/install-global.sh`(28-36行)

`PERM_SCRIPTS` 配列に `power-ctl.sh` を追加(グローバルインストール時の allowlist 登録。`cp -r`/`chmod +x *.sh` で配布自体は自動)。`bmc-power.sh` は追加不要 — llama-up/down が直接呼ぶのは `power-ctl.sh` だけで、`bmc-power.sh`/`power.sh` はその子プロセス(Claude が直接起動しない)ため承認対象外。`bmc-power.sh` の直接実行(BMC 緊急操作)を allowlist 化するかは本変更のスコープ外。

### 5. ドキュメント更新

- **`llama-server/SKILL.md`**: 160-161行(`power.sh status`/`power.sh on`)・182,186行(`power.sh off`)を `power-ctl.sh` 表記に更新。llama-up/down が **mi25/p100 両対応**で電源トランスポートを自動判別する旨を追記。
- **`gpu-server/SKILL.md`**: 電源制御節とトランスポート表(146-149行付近)に、統一IF `power-ctl.sh <server> <status|on|off>`(llama-up/down 経由、低レベル操作は power.sh / bmc-power.sh)を追記。
- **`gpu-server/bmc.md`**: `power-ctl.sh` の off が Supermicro で `soft`(グレースフル)にマップされる旨を1文追記。

## 検証

**前提・制約**:
- **t120h-p100 は他セッションで使用中。電源・llama-server に一切触れない**(電源 OFF/ON、`llama-up.sh`/`llama-down.sh` の実行は禁止)。p100 に対しては**読み取り専用の `power-ctl.sh t120h-p100 status`(Redfish の状態取得のみ・状態変更なし)だけ**許可。
- **mi25 は実機テスト可**。現在 mi25 は本セッションで Qwen3.6-35B-A3B 稼働中・ロック取得中。検証の一環として停止→再起動してよい。

手順(mi25 はロック保持のまま実施):

1. **status 正規化(読み取りのみ)**: `power-ctl.sh mi25 status` と `power-ctl.sh t120h-p100 status` がいずれも stdout に `On`/`Off` の1語だけを返す(`| cat -A` で確認)。生メッセージは stderr に出る。p100 は状態取得のみで電源は変わらない。
2. **mi25 グレースフル停止**: `llama-down.sh mi25` が Step4 で `bmc-power.sh soft`(ハード `off` でない)を呼ぶことをログ確認 → 一定時間後 `bmc-power.sh mi25 status` が `off`。**注意: llama-down.sh は Step3 で自分保持ロックを解放する**ため、続く手順の前に **`lock.sh mi25` でロックを取り直す**(llama-up.sh はロックを取得しない仕様)。
3. **mi25 起動(本命)**: ロック再取得後、`llama-up.sh mi25 "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072` が Step1`Off`判定 → `bmc-power.sh on` → SSH 疎通待ち → start/wait-ready まで通る(=当初の exit 10 が解消)。
4. **p100 回帰(コードパス)**: p100 は落とせないため、hpe 分岐の回帰はステップ1の `status` 読み取りで確認。`on`/`off` 委譲は `power.sh` をそのまま呼ぶだけ(ロジック不変)で、status 経路が正常なら回帰リスクは低いことを根拠に、電源を伴う実起動テストは**実施しない**と明記。
5. **異常系(mi25)**: `GPU_SERVER_ENV` を空ファイルに向けて `power-ctl.sh mi25 status` が exit 10 + setup 案内(stderr)を出し、`llama-up.sh mi25 ...` がそこで停止することを確認。

## レポート(必須)

CLAUDE.md の制約により、plan mode で計画した本作業は実装後に対のレポートを作成する([REPORT.md](REPORT.md) フォーマット)。
