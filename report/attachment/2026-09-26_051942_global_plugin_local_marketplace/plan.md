# グローバルインストールを正規のローカルマーケットプレース方式に作り直す

## Context

`install-global.sh` が gpu-server / llama-server を、公式マーケットプレース `claude-plugins-official` のプラグインに偽装して登録している。その登録手順は次のとおり。

- cache へ直接コピーする
- `installed_plugins.json` と `enabledPlugins` を直接書き換える

公式の一覧に無いため、`claude plugin list` で `✘ failed to load: Plugin gpu-server not found in marketplace claude-plugins-official` となり、他プロジェクトから両スキルを使えない。

副次的な欠陥が 2 つある。

- `rpc-stack-up.sh` / `rpc-stack-down.sh` の `../gpu-server/scripts` 相対参照を書き換えていない（aws-gpu01 の既定起動が壊れる）。
- `aws-gpu.md` / `bmc.md` の相対パスも未変換。

ユーザは案 2（正規のローカルマーケットプレース）を選択した。personal skill（`~/.claude/skills`）は project skill より優先されるため、この repo の編集が反映されなくなる。案 1 はこの理由で不採用とした。

## 方針

**プラグイン `llm-server-ops` 1 つに `gpu-server` / `llama-server` / `discord-notify` の 3 スキルを兄弟として収め、ローカルマーケットプレース `llm-server-ops-local` から `claude plugin` CLI で正規にインストールする。**

- 3 スキルが兄弟なので、スクリプト内の `$SKILL_DIR/../gpu-server/scripts` などはそのまま解決する。スクリプトの `sed` 書換ハックは全廃し、rpc-stack の不具合も解消する。
- 他プロジェクトでは `llm-server-ops:gpu-server` のように名前空間付きになるため、この repo の project skill と衝突しない。

## 変更内容

### 1. `.claude/skills/install-all-global.sh` を全面改修（唯一のインストーラにする）

install の流れ:

1. `check_deps`（jq, `claude` CLI）と `sync_env`（既存関数をそのまま流用）。
2. **旧偽装登録の掃除**（旧 `--uninstall` のロジックを `cleanup_legacy` 関数に移植）。
   - `cache/claude-plugins-official/{gpu-server,llama-server}` を削除する。
   - `installed_plugins.json` のキー削除、`enabledPlugins` のキー削除。
   - `permissions.allow` から旧 scripts パスを含む項目を除去する。
   - 対象がすでに無ければ何もしない（冪等）。
3. **ステージング生成**: `~/.local/share/claude-marketplaces/llm-server-ops/`
   - `.claude-plugin/marketplace.json` を置く（`name: llm-server-ops-local`、plugin `llm-server-ops`、`source: "./plugins/llm-server-ops"`）。
   - `plugins/llm-server-ops/.claude-plugin/plugin.json` を置く。
   - `plugins/llm-server-ops/skills/{gpu-server,llama-server,discord-notify}/` へ `rm -rf` → `cp -r` でコピーする（`install-global.sh` 自体は除外）。
4. 再インストールに対応させる。既存があれば `claude plugin uninstall llm-server-ops@llm-server-ops-local` と `claude plugin marketplace remove llm-server-ops-local` を実行し、その後 `claude plugin marketplace add <staging>` → `claude plugin install llm-server-ops@llm-server-ops-local` を実行する。
5. **実際の installPath を `claude plugin list --json` から取得する**。cache にコピーされるか元ディレクトリ参照かが未確定なので、実測値を使う。
6. installPath 配下の全 `*.md` について sed で置換する。
   - `.claude/skills/(gpu-server|llama-server|discord-notify)/` → `<installPath>/skills/\1/` に置換する。server-scripts も含む。
   - 「プロジェクトルートからの相対パスで実行」注意書きの差し替えも、旧スクリプトと同じ sed で行う。
7. `permissions.allow` に絶対パスを登録する（旧 2 スクリプトの `PERM_SCRIPTS` を統合し、重複排除の jq も流用）。
   - 旧パスは手順 2 で除去済み。再インストール時は、同じ plugin の旧 installPath を含む項目を先に除去する。
8. `claude plugin list` の該当行を表示して終了する。

`--uninstall`: plugin uninstall → marketplace remove → staging 削除 → permissions 除去 → `cleanup_legacy`。

### 2. 旧スクリプトの削除

- `.claude/skills/gpu-server/scripts/install-global.sh` と `.claude/skills/llama-server/scripts/install-global.sh` を削除する（`git rm`）。
- 個別インストールは廃止し、3 スキル一体の 1 プラグインにする。

### 3. ドキュメント更新

- `README.md` のグローバルインストール節とディレクトリ構成を更新する（個別インストール削除、スキル名が `llm-server-ops:gpu-server` になる旨、仕組み）。
- `.claude/skills/*/SKILL.md` 等で `install-global.sh` に言及する箇所があれば直す（grep で確認）。

## 検証

1. `bash -n .claude/skills/install-all-global.sh` を実行する。続けて本体を実行する。
2. `cd /tmp && claude plugin list` を確認する。
   - `llm-server-ops@llm-server-ops-local` が `✔ enabled` であること。
   - 旧 2 エントリが消えていること。
3. `claude plugin details llm-server-ops@llm-server-ops-local` で 3 スキルが見えることを確認する。
4. installPath 配下の md に `.claude/skills/` の相対参照が残っていないことを grep で確認する。
5. installPath 内のスクリプトで、兄弟参照が解決するかを読み取り専用で確認する。
   - `lock-status.sh aws-gpu01`
   - `llama-up.sh` / `rpc-stack-up.sh` の `GPU_SCRIPTS_DIR` 解決は、`bash -x` 相当ではなく `cd "$SKILL_DIR/../gpu-server/scripts"` の存在確認で行う。
   - 電源・ロック操作は行わない。
6. `/tmp` から `claude -p` で、`llm-server-ops:gpu-server` スキルが一覧に出るかを確認する。
7. `jq '.permissions.allow' ~/.claude/settings.json` で新パスが登録され、旧パスが消えていることを確認する。
8. 再実行（冪等性）と `--uninstall` → 再 install の往復を確認する。

完了後、REPORT.md に従ってレポートを作成し、コミットする。
