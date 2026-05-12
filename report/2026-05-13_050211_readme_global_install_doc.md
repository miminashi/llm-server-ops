# README にグローバルインストール手順を追記

- **実施日時**: 2026年5月13日 05:02 (JST)

## 添付ファイル

- [実装プラン](attachment/2026-05-13_050211_readme_global_install_doc/plan.md)

## 前提・目的

- 背景: リポジトリには `.claude/skills/install-all-global.sh` という一括グローバルインストールスクリプトが既に存在するが、`README.md` にはこの機能への言及がなく、新規ユーザがその存在に気付けない状態だった。
- 目的: `README.md` だけで「グローバルインストールという選択肢が存在し、コマンド 1 つで導入・撤去できる」ことが分かるようにする。
- 前提条件: スクリプト本体・実装には手を入れない（ドキュメント追加のみ）。

## 過去レポート調査

依頼に従い `report/*.md` を調査したが、`install-global` / `install-all-global` / `claude-plugins-official` / 「グローバルインストール」 などのキーワードを含むレポートは見つからなかった。そのため、本レポートの記述根拠は **スクリプト本体（`.claude/skills/install-all-global.sh`）の Usage コメントと実装** に置いた。

参考にした関連レポート（インストールスクリプトとは直接無関係だが、隣接する Skill スクリプト群の改善履歴）:

- [2026-05-12_051827_llama_up_down_scripts.md](2026-05-12_051827_llama_up_down_scripts.md)
- [2026-05-12_105909_llama_down_unlock_order_fix.md](2026-05-12_105909_llama_down_unlock_order_fix.md)
- [2026-05-13_030350_wrapper_hang_fix.md](2026-05-13_030350_wrapper_hang_fix.md)

## 環境情報

- リポジトリ: `/home/ubuntu/projects/llm-server-ops`
- ブランチ: `master`
- 編集対象: `README.md` のみ
- 実装根拠: `.claude/skills/install-all-global.sh:1-157`

## 変更内容

### 1. 新セクション「グローバルインストール（オプション）」を追加

`README.md` のクイックスタート直後・ディレクトリ構成直前に、以下の見出し構成で追記:

- リード文（相対パス実行が通常、グローバル登録は複数プロジェクト/他セッションから呼びたい場合）
- 前提条件（`jq`、`~/.claude`）
- インストール（`.claude/skills/install-all-global.sh`）+ 何が起こるかの 4 項目
  - スキルを `~/.claude/plugins/cache/` 配下にコピー
  - SKILL.md 内の相対パスを絶対パスに書き換え
  - `~/.claude/settings.json` に実行パーミッションを登録
  - プロジェクトの `.env` を `~/.config/gpu-server/.env` に冪等マージ
- インストール後に Claude Code 再起動が必要な旨を明記
- アンインストール（`--uninstall`）
- 個別インストール / ヘルプ（`--help`、`gpu-server/scripts/install-global.sh`、`llama-server/scripts/install-global.sh`）

### 2. ディレクトリ構成ツリーを更新

ツリーに以下を追加:

- `.claude/skills/install-all-global.sh`（一括登録）
- `.claude/skills/gpu-server/scripts/install-global.sh`（gpu-server 単体）
- `.claude/skills/llama-server/scripts/install-global.sh`（llama-server 単体）

## 再現方法

```bash
# 1. README.md のクイックスタート直後に「グローバルインストール（オプション）」セクションを追記
# 2. ディレクトリ構成ツリーに install スクリプト 3 本を追加
# 3. 検証: --help がドキュメントどおりに動作することを確認
.claude/skills/install-all-global.sh --help
```

`--help` 実行結果（README に記載した動作と一致）:

```
Usage: install-all-global.sh [OPTIONS]

gpu-server / llama-server スキルをグローバル Claude Code プラグインとして
一括インストールします。

Options:
  --uninstall    全プラグインをアンインストール
  -h, --help     このヘルプを表示

インストール対象:
  gpu-server     排他制御（ロック）、リモートブラウザ、電源制御、セットアップ
  llama-server   LLM推論サーバの起動・管理、llama.cppのビルド
```

インストール／アンインストール自体は副作用が大きいため、本作業では実行していない。

## 核心発見サマリ

- `README.md` だけを変更し、スクリプト本体には触れずにグローバルインストール機能をドキュメント化できた。
- 既存スクリプトには既に `--help` / `--uninstall` / 冪等マージ / 個別実行 すべてが揃っており、ドキュメント側を仕様に合わせるだけで十分だった。
- 過去レポートには本スクリプトの導入経緯を記録したものが存在しなかったため、今後のために本レポートでスクリプト仕様を簡潔に押さえた。
