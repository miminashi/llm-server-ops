# グローバルプラグインをローカルマーケットプレース方式に作り直す

- **実施日時**: 2026年9月26日 05:03 〜 05:25 JST（原因特定、インストーラ全面改修、インストール・往復検証、文書更新）
- **報告日時**: 2026年9月26日 05:25 JST
- **作成者**: Claude Opus 5.5 (1M context)

## 概要

他プロジェクトの Claude セッションから gpu-server スキルを使おうとしたところ、読み込まれないという報告があった。調べると、グローバルインストール用のスクリプトが、Anthropic 公式のプラグインマーケットプレースに属するプラグインであるかのように見せかけて登録していたことが原因だった。Claude Code は公式マーケットプレースの一覧と照合し、載っていないプラグインを「見つからない」として読み込みを拒否していた。そのため、このリポジトリの外では gpu-server も llama-server も使えない状態だった。

直し方として、個人スキルとしてホーム配下に置く案も検討した。しかし個人スキルは同名のプロジェクトスキルより優先されるため、このリポジトリで編集したスキルが古いコピーに隠されてしまう。そこで、ユーザの判断により、正規のローカルマーケットプレースを作って Claude Code の CLI からインストールする方式を採用した。

新しい方式では、3 つのスキル（gpu-server、llama-server、discord-notify）を 1 つのプラグインにまとめて兄弟として並べる。スクリプト同士が互いを相対パスで参照していても、そのまま動く。旧方式はその参照を一部だけ書き換えていたため、aws-gpu01 の既定の起動手順（RPC 分散）がグローバル環境では動かないという隠れた欠陥もあった。この欠陥も同時に解消した。他プロジェクトからはプラグイン名の接頭辞付きの名前で見えるので、このリポジトリ自身のスキルとは衝突しない。

インストールスクリプトは 1 本に統合し、旧方式が書き込んだ偽の登録を自動で掃除するようにした。再実行すれば最新の内容で入れ直せる。実機で、インストール、再インストール、アンインストールからの再インストールを通した。そのうえで、別ディレクトリで起動した新しい Claude セッションから 3 つのスキルが見えることを確かめた。

注意点として、インストールされるのは実行時点のコピーなので、スキルを変更したらインストールをやり直す必要がある。また、BMC 画面キャプチャ用の Python 仮想環境はコピーしても動かないため除外した。プラグイン側でその機能を使うときは、インストール先で作り直す必要がある。

## 添付ファイル

- [実装プラン](attachment/2026-09-26_051942_global_plugin_local_marketplace/plan.md)

## 核心発見サマリ

**結論**: 旧 `install-global.sh` は `gpu-server@claude-plugins-official` / `llama-server@claude-plugins-official` を cache・`installed_plugins.json`・`enabledPlugins` への直接書き込みで登録していた。Claude Code 2.1.282 は `claude plugin list` で `✘ failed to load — Plugin gpu-server not found in marketplace claude-plugins-official` を返し、読み込んでいなかった。`install-all-global.sh` を作り直し、ローカルマーケットプレース `llm-server-ops-local` からプラグイン `llm-server-ops`（3 スキル同梱）を `claude plugin install` で入れる方式にした。結果は `✔ enabled`、Skills (3)。

| 項目 | 旧 | 新 |
|---|---|---|
| 登録方法 | JSON とキャッシュを直接書き換え（公式に偽装） | `claude plugin marketplace add` + `claude plugin install` |
| プラグイン | `gpu-server` / `llama-server` の 2 つ（discord-notify は llama-server 内に同梱） | `llm-server-ops` 1 つに 3 スキルを兄弟として収める |
| スキル名（他プロジェクト） | （読み込まれず） | `llm-server-ops:gpu-server` / `:llama-server` / `:discord-notify` |
| スクリプトの相互参照 | `llama-up.sh` / `llama-down.sh` の `GPU_SCRIPTS_DIR` だけを sed で書き換え。**`rpc-stack-up.sh` / `rpc-stack-down.sh` は未対応** | 兄弟配置なので書き換え不要 |
| 文書のパス変換 | `SKILL.md` / `lock.md` / `remote-browser.md` のみ（`aws-gpu.md` / `bmc.md` は未変換） | インストール先の全 `*.md` |
| インストール先 | `~/.claude/plugins/cache/claude-plugins-official/<name>/1.0.0/` | `~/.claude/plugins/cache/llm-server-ops-local/llm-server-ops/1.0.0/`（ステージングは `~/.local/share/claude-marketplaces/llm-server-ops/`） |
| サイズ | — | 456 KB（`.venv` 159 MB を除外） |

調査用のサブエージェントは「ディレクトリ型マーケットプレースはキャッシュへコピーせず、元ディレクトリを参照する」と報告していた。実測では **cache にコピーされた**。そのため installPath は決め打ちにせず、`claude plugin list --json` から取得している。

## 前提・目的

- **背景**: 他プロジェクトの Claude セッションから、gpu-server スキルが使えないという指摘があった。
- **目的**: グローバルインストールを、Claude Code が正規に読み込む形に作り直す。
- **採用しなかった案**: `~/.claude/skills/` に personal skill として置く案。公式ドキュメント（skills.md「Resolve skills that share a name」）では優先順位が Enterprise > Personal > Project なので、この repo の project skill が古いコピーに隠される。

## 環境情報

- Claude Code 2.1.282
- ワークステーション（`~/.claude` のユーザ設定）
- 変更前の `settings.json` / `installed_plugins.json` / `known_marketplaces.json` は、作業前にセッションのスクラッチパッドへ退避した。

## 結果詳細

### 変更ファイル

- `.claude/skills/install-all-global.sh` — 全面改修し、唯一のインストーラにした。
  - 関数構成は `cleanup_legacy`（旧偽装登録の掃除）、`unregister`、`build_staging`、`rewrite_docs`、`add_perms`。
  - `sync_env` と、`json_update` の重複排除ロジックは流用した。
- `.claude/skills/gpu-server/scripts/install-global.sh`、`.claude/skills/llama-server/scripts/install-global.sh` — 削除した（個別インストールは廃止）。
- `README.md` — グローバルインストール節とディレクトリ構成を更新した。
- `.claude/skills/llama-server/SKILL.md` — 「グローバル plugin 版は古い」注記を、新方式の説明（スナップショットなので再実行で更新する）に差し替えた。

### 検証

| 確認項目 | 結果 |
|---|---|
| `claude plugin list`（/tmp から） | `llm-server-ops@llm-server-ops-local ✔ enabled`。旧 2 エントリは消えた |
| `claude plugin details` | Skills (3): discord-notify, gpu-server, llama-server |
| 別ディレクトリで起動した `claude -p` | `llm-server-ops:gpu-server` / `:llama-server` / `:discord-notify` を認識 |
| インストール先 md に残る `.claude/skills/` 相対参照 | 0 件 |
| 兄弟参照（`llama-server/../gpu-server/scripts`、`../discord-notify/scripts`） | 解決する |
| インストール先の `lock-status.sh aws-v100` | `aws-v100: available`（読み取り専用。t120h-p100 は電源 OFF で UNREACHABLE） |
| `permissions.allow` | 新パス 16 件を登録。`claude-plugins-official` を含む旧パスは 0 件 |
| `enabledPlugins` / `installed_plugins.json` | 旧 2 キーを削除し、新キーを追加 |
| 再実行（冪等性） | 既存を uninstall してから入れ直す。permissions は重複しない |
| `--uninstall` → install の往復 | uninstall 後はプラグイン、マーケットプレース、permissions がすべて 0 件になり、再 install で復帰した |

電源操作・ロック取得・llama-server 起動は行っていない。

## 残課題

- 他プロジェクトで `llm-server-ops:gpu-server` の BMC スクショ（`bmc-screenshot.sh`）を使う場合は、インストール先で `setup-bmc-venv.sh` を実行して `.venv` を作る必要がある。
- インストールはスナップショットなので、スキルを変更したら `install-all-global.sh` を再実行する。この運用を忘れると旧版と同じく古いまま残る。
- 既存の Claude セッションは再起動するまで新プラグインを読み込まない。

## 参照レポート

- [README にグローバルインストール手順を追記](./2026-05-13_050211_readme_global_install_doc.md)
- [llama-up/down のグローバルインストール対応](./2026-05-13_071824_llama_up_down_global_install.md)
- [メモリの注意点をスキル文書へ移す（plugin 版が古い件）](./2026-09-19_183529_memory_to_skill_docs.md)
