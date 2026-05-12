# llama-up.sh / llama-down.sh のグローバルインストール対応

- **実施日時**: 2026年5月13日 16:18 JST

## 核心発見サマリ

- `install-global.sh` の `PERM_SCRIPTS` 配列に `llama-up.sh` / `llama-down.sh` を追加するだけでは不十分。これらは内部で gpu-server スキルを **相対パス参照** (`$SKILL_DIR/../gpu-server/scripts`) しており、グローバルインストール後は gpu-server が別プラグインツリーに居るため `cd` 失敗で即異常終了する。
- 解決策: `install-global.sh` 内の SKILL.md パス書換ロジック（L104-110）と同じ流儀で `sed` 置換を追加し、コピー先ファイル内の `GPU_SCRIPTS_DIR=...` 行を gpu-server プラグインの絶対パスに固定化。プロジェクト内ソースは無変更で従来の使い方を維持できる。
- 検証では実機 t120h-p100 で `llama-up.sh` の Step 1-2（電源 ON）と `llama-down.sh` の全 4 Step（ロック判定→stop→power off）がすべて成功し、`GPU_SCRIPTS_DIR` 書換が機能していることを確認。

## 添付ファイル

- [実装プラン](attachment/2026-05-13_071824_llama_up_down_global_install/plan.md)

## 前提・目的

- **背景**: `llama-up.sh` / `llama-down.sh` は電源制御を含む統合スクリプトとして llama-server SKILL.md で「統合スクリプト（推奨）」と既に位置づけられているが、グローバルインストール (`install-global.sh`) の対象から漏れていた。permission 登録漏れに加え、gpu-server スキルへの相対パス参照のためグローバル環境ではそもそも動作しない問題があった。
- **目的**: グローバルプラグインとして両スクリプトを正しくインストールし、グローバル環境からも実行可能にする。
- **前提条件**: `gpu-server` プラグインが先にインストール済みであること（`install-all-global.sh` 経由なら自動的に gpu-server → llama-server の順で入る）。

## 環境情報

- 検証サーバ: t120h-p100 (10.1.4.14、NVIDIA Tesla P100 × 4)
- インストール先: `~/.claude/plugins/cache/claude-plugins-official/{gpu-server,llama-server}/1.0.0/`
- jq: 必須（既存の前提条件）

## 修正内容

### 1. `.claude/skills/llama-server/scripts/install-global.sh`

#### (a) `PERM_SCRIPTS` 配列への追加 (L30-38)

```bash
PERM_SCRIPTS=(
  start.sh
  stop.sh
  wait-ready.sh
  ttyd-gpu.sh
  monitor-download.sh
  llama-up.sh     # 追加
  llama-down.sh   # 追加
)
```

ファイルコピー (`cp -r "${SOURCE_DIR}/." "${SKILL_DIR}/"`) と `chmod +x "${SCRIPTS_PATH}"/*.sh` はディレクトリ全体・グロブ対象なので、配列追加のみで実行ビット・コピーは自動的に拾われる。

#### (b) `GPU_SCRIPTS_DIR` の絶対パス書換 (L108-125)

既存の SKILL.md パス書換 `if [[ -d "${gpu_global_scripts}" ]]; then` ブロック内に追加:

```bash
# llama-up.sh / llama-down.sh は gpu-server スキルを相対パス参照しているため、
# グローバルインストール後に隣接スキルとして解決できなくなる。
# 行頭の GPU_SCRIPTS_DIR=... を gpu-server プラグインの絶対パスに固定化する。
local f
for f in llama-up.sh llama-down.sh; do
  if [[ -f "${SCRIPTS_PATH}/${f}" ]]; then
    sed -i "s|^GPU_SCRIPTS_DIR=.*|GPU_SCRIPTS_DIR=\"${gpu_global_scripts}\"|" \
      "${SCRIPTS_PATH}/${f}"
  fi
done
```

`else` 節で gpu-server 未インストール時の警告メッセージも追加。書換対象は **コピー先ファイルのみ**（プロジェクト内ソースは無傷）。

#### (c) アンインストールロジックは変更不要

L186-189 の `'.permissions.allow |= map(select(contains($path) | not))'` が `${SCRIPTS_PATH}/` プレフィックスで contains 判定するため、追加した permission も自動削除される。

### 2. `README.md`

#### (a) クイックスタートを統合スクリプト版に置換

7 ステップ（lock-status / lock / start / wait-ready / curl / stop / unlock）を 5 ステップ（lock-status / lock / llama-up / curl / llama-down）に簡素化。個別ステップは SKILL.md 参照に降格。

#### (b) ディレクトリ構成に `llama-up.sh / llama-down.sh` を追加（推奨マーカー付き）

## 再現方法

### インストール

```bash
.claude/skills/install-all-global.sh
```

### 検証 1: permissions 追加確認

```bash
jq '.permissions.allow | map(select(test("llama-up.sh") or test("llama-down.sh")))' \
  ~/.claude/settings.json
```

期待: `Bash(.../llama-up.sh:*)` と `Bash(.../llama-down.sh:*)` の 2 エントリ。

### 検証 2: `GPU_SCRIPTS_DIR` 書換確認

```bash
grep -n '^GPU_SCRIPTS_DIR=' \
  ~/.claude/plugins/cache/claude-plugins-official/llama-server/1.0.0/skills/llama-server/scripts/llama-{up,down}.sh
```

期待: 両ファイルとも `GPU_SCRIPTS_DIR="/home/.../gpu-server/1.0.0/skills/gpu-server/scripts"` の絶対パス。

### 検証 3: 書換後スクリプトの構文チェック

```bash
bash -n ~/.claude/plugins/cache/claude-plugins-official/llama-server/1.0.0/skills/llama-server/scripts/llama-{up,down}.sh
```

### 検証 4: 実機動作確認

```bash
# プロジェクトルート外（/tmp）から実行
cd /tmp && \
  ~/.claude/plugins/cache/claude-plugins-official/llama-server/1.0.0/skills/llama-server/scripts/llama-down.sh t120h-p100
```

期待出力:
```
==> [1/4] t120h-p100 のロック状態を確認中...
t120h-p100: available
    ロックなしで停止します（注意: 排他制御なし）
==> [2/4] llama-server を停止中...
==> t120h-p100 の llama-server プロセスを確認中...
llama-server は t120h-p100 で起動していません。
==> [3/4] ロック解放スキップ（未保持または --force のため）
==> [4/4] t120h-p100 の電源を OFF にします...
t120h-p100: off コマンドを送信しました (ResetType: GracefulShutdown)
==> 停止完了
```

すべての gpu-server スクリプト呼び出し（`lock-status.sh` / `power.sh off`）が成功すれば、`GPU_SCRIPTS_DIR` 書換が機能していることが確認できる。

### 検証 5: アンインストール

```bash
.claude/skills/install-all-global.sh --uninstall
jq '.permissions.allow | map(select(test("llama-server/scripts")))' ~/.claude/settings.json
```

期待: 空配列 `[]`（既存ロジックで全 permission が削除される）。

## 検証結果

| # | 検証項目 | 結果 |
|---|---------|------|
| 1 | permissions に llama-up.sh / llama-down.sh が追加 | OK（2 エントリ確認） |
| 2 | GPU_SCRIPTS_DIR が gpu-server プラグインの絶対パスに書換 | OK（両ファイル L28 / L30） |
| 3 | 書換後スクリプトの bash 構文チェック | OK |
| 4 | グローバルパスから llama-down.sh 実行（プロジェクト外 /tmp から） | OK（4 Step 全て成功、電源 OFF 完了） |
| 5 | アンインストール後の permissions 全削除 | OK（空配列） |
| 6 | 再インストールで再構築 | OK（permissions 復活、書換も再適用） |

## 関連レポート

- [2026-05-12_051827 llama-up.sh / llama-down.sh 導入](2026-05-12_051827_llama_up_down_scripts.md)
- [2026-05-12_105909 llama-down.sh ロック解放順の修正](2026-05-12_105909_llama_down_unlock_order_fix.md)
- [2026-05-13_050211 README へのグローバルインストール手順追加](2026-05-13_050211_readme_global_install_doc.md)
