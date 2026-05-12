# llama-up.sh / llama-down.sh のグローバルインストール対応 + README 反映

## Context

`llama-up.sh` / `llama-down.sh` は llama-server の電源制御・起動・停止を 1 コマンドに統合した推奨スクリプト（SKILL.md でも「統合スクリプト（推奨）」として既に紹介済み）。しかし以下 2 点が未対応:

1. **`.claude/skills/llama-server/scripts/install-global.sh` の `PERM_SCRIPTS` 配列に含まれていない** → グローバルインストール後も実行時に承認ダイアログが出る。
2. **内部で gpu-server スキルを相対パス参照している** (`$SKILL_DIR/../gpu-server/scripts`) → グローバルインストール後は gpu-server が別プラグインツリーに居るため `cd` が失敗してスクリプトが即異常終了する。

また README.md には:
- クイックスタートに統合スクリプトのフローが無い（個別ステップ版のみ）
- ディレクトリ構成 (L114-118) に `llama-up.sh` / `llama-down.sh` が記載されていない

## 修正対象ファイル

- `.claude/skills/llama-server/scripts/install-global.sh`
- `README.md`

プロジェクト内の `llama-up.sh` / `llama-down.sh` 本体には手を入れない（プロジェクトから直実行する従来の使い方を維持）。

## 修正内容

### 1. `install-global.sh` の修正

#### (a) `PERM_SCRIPTS` に追加（L30-36）

```bash
PERM_SCRIPTS=(
  start.sh
  stop.sh
  wait-ready.sh
  ttyd-gpu.sh
  monitor-download.sh
  llama-up.sh      # 追加
  llama-down.sh    # 追加
)
```

ファイルコピー (`cp -r "${SOURCE_DIR}/." "${SKILL_DIR}/"` L76) と `chmod +x` (L77) はディレクトリ全体・グロブを対象にしているため、配列追加だけで自動的に拾われる。

#### (b) GPU_SCRIPTS_DIR パス書き換えを追加（L104-110 の `if` ブロック内）

既存の SKILL.md パス書換と同じ流儀で `sed` 置換する。`gpu_global_scripts` 変数はすでに L107 で定義済みなので再利用。

```bash
if [[ -d "${gpu_global_scripts}" ]]; then
  sed -i "s|${gpu_relative}|${gpu_global_scripts}/|g" "${SKILL_DIR}/SKILL.md"

  # 追加: llama-up.sh / llama-down.sh の GPU_SCRIPTS_DIR を絶対パスに固定化
  # 元: GPU_SCRIPTS_DIR="$(cd "$SKILL_DIR/../gpu-server/scripts" && pwd)"
  # 後: GPU_SCRIPTS_DIR="<gpu_global_scripts の絶対パス>"
  local f
  for f in llama-up.sh llama-down.sh; do
    if [[ -f "${SCRIPTS_PATH}/${f}" ]]; then
      sed -i "s|^GPU_SCRIPTS_DIR=.*|GPU_SCRIPTS_DIR=\"${gpu_global_scripts}\"|" \
        "${SCRIPTS_PATH}/${f}"
    fi
  done
else
  echo "WARNING: gpu-server プラグインが未インストールのため、llama-up.sh / llama-down.sh の GPU_SCRIPTS_DIR を書換できません。先に gpu-server をインストールするか、install-all-global.sh を使ってください。" >&2
fi
```

行頭アンカー `^GPU_SCRIPTS_DIR=` で限定し、置換は厳密に 1 行のみ。

#### (c) アンインストール処理は変更不要

L186-189 の現行ロジック:

```bash
'.permissions.allow |= map(select(contains($path) | not))' \
  --arg path "${SCRIPTS_PATH}/"
```

は `${SCRIPTS_PATH}/` プレフィックス (`.../skills/llama-server/scripts/`) で contains 判定するため、新規追加した `llama-up.sh` / `llama-down.sh` の permission も自動的に削除される。ファイル自体は `rm -rf "${INSTALL_BASE}"` (L170) で消える。

### 2. `README.md` の修正

#### (a) クイックスタート（L21-50）を統合スクリプト版に置き換え

```markdown
## クイックスタート

GPUサーバでllama-serverを使用する基本的なワークフローです。`llama-up.sh` / `llama-down.sh` は電源制御から起動・停止までを 1 コマンドに統合した推奨スクリプトです。

```bash
# 1. ロックを取得
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 2. llama-serverを起動（電源OFFなら自動でON→SSH疎通待ち→start→wait-ready）
.claude/skills/llama-server/scripts/llama-up.sh t120h-p100 \
  "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M" 131072

# 3. OpenAI互換APIとして使用
curl http://10.1.4.14:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M", "messages": [{"role": "user", "content": "Hello"}]}'

# 4. llama-serverを停止（stop → 自分保持ロックの自動解放 → 電源OFF）
.claude/skills/llama-server/scripts/llama-down.sh t120h-p100
```

個別ステップ（`start.sh` / `wait-ready.sh` / `stop.sh`）で細かく制御したい場合は [llama-server SKILL.md](.claude/skills/llama-server/SKILL.md) を参照してください。
```

#### (b) ディレクトリ構成（L114-118）に統合スクリプトを追加

```
│   ├── llama-server/
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   │   ├── install-global.sh       # llama-server を単独でグローバル登録
│   │   │   ├── llama-up.sh / llama-down.sh   # 統合スクリプト（電源+起動/停止、推奨）
│   │   │   ├── start.sh / stop.sh / wait-ready.sh
│   │   │   ├── ttyd-gpu.sh
│   │   │   └── monitor-download.sh
│   │   └── server-scripts/
│   │       └── update_and_build-{server}.sh
```

## 検証手順

1. **構文チェック**:
   ```bash
   bash -n .claude/skills/llama-server/scripts/install-global.sh
   ```

2. **一括インストール実行**（gpu-server を先に入れさせるため `install-all-global.sh` を使う）:
   ```bash
   .claude/skills/install-all-global.sh
   ```

3. **permissions.allow 確認**:
   ```bash
   jq '.permissions.allow | map(select(contains("llama-up.sh") or contains("llama-down.sh")))' \
     ~/.claude/settings.json
   ```
   2 エントリが返ること。

4. **GPU_SCRIPTS_DIR 書換確認**:
   ```bash
   grep -n '^GPU_SCRIPTS_DIR=' \
     ~/.claude/plugins/cache/claude-plugins-official/llama-server/1.0.0/skills/llama-server/scripts/llama-up.sh \
     ~/.claude/plugins/cache/claude-plugins-official/llama-server/1.0.0/skills/llama-server/scripts/llama-down.sh
   ```
   絶対パス（`~/.claude/plugins/cache/claude-plugins-official/gpu-server/1.0.0/skills/gpu-server/scripts`）になっていること。

5. **書換後スクリプトの構文確認**:
   ```bash
   bash -n ~/.claude/plugins/cache/claude-plugins-official/llama-server/1.0.0/skills/llama-server/scripts/llama-up.sh
   bash -n ~/.claude/plugins/cache/claude-plugins-official/llama-server/1.0.0/skills/llama-server/scripts/llama-down.sh
   ```

6. **動作確認（軽い形）**: プロジェクトルート外の別シェルから、グローバルインストール先の `llama-up.sh` を実行。電源が既に ON なら Step 3 のヘルスチェック分岐で `exit 0` するため副作用なし。
   ```bash
   ~/.claude/plugins/cache/claude-plugins-official/llama-server/1.0.0/skills/llama-server/scripts/llama-up.sh t120h-p100
   ```

7. **Claude Code から実行**: `/exit` 後に再起動し、`llama-up.sh` 呼出で permission ダイアログが出ないことを確認。

8. **アンインストール検証**:
   ```bash
   .claude/skills/install-all-global.sh --uninstall
   jq '.permissions.allow | map(select(contains("llama-server/scripts")))' \
     ~/.claude/settings.json
   ```
   空配列 (`[]`) が返ること。

## レポート作成

CLAUDE.md の規約に従い、本計画完了後に対になるレポートを `report/2026-05-13_<HHMMSS>_<title>.md` 形式で作成する（[REPORT.md](REPORT.md) の書式に従う）。
