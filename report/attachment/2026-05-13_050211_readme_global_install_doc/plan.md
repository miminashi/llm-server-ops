# README.md にグローバルインストール手順を追記

## Context

このリポジトリには既に `install-all-global.sh` という、Skill をグローバル Claude Code プラグイン（`~/.claude/plugins/cache/`）として登録する一括インストールスクリプトが存在する。しかし `README.md` には Skill 一覧・クイックスタート・ディレクトリ構成しか書かれておらず、グローバルインストール機能の存在自体がドキュメント化されていない。

ユーザは「過去レポートを調査のうえ README に使い方を記載」と依頼。過去レポート（`report/*.md`）を grep したが `install-global` / `claude-plugins-official` 等を含むレポートは存在しなかったため、**根拠はスクリプト本体の Usage コメントと実装** に置く。

意図する成果: 初見の読者が、`README.md` だけで「通常はプロジェクトローカル相対パスで実行・グローバルインストールすると他プロジェクトの Claude セッションからも `/gpu-server` 等で呼べる」という選択肢を理解し、コマンド 1 つで導入・撤去できる状態にする。

## 既存スクリプトの根拠

- `/.claude/skills/install-all-global.sh:1-157` — 一括インストール／アンインストール／ヘルプの 3 モード
  - 引数: なし (= インストール), `--uninstall`, `-h|--help`
  - 前提: `jq` と `~/.claude` ディレクトリ
  - `.env` を `~/.config/gpu-server/.env` に冪等マージ
  - 内部で個別スクリプト `gpu-server/scripts/install-global.sh` と `llama-server/scripts/install-global.sh` を順に実行
  - 完了後「Claude Code を再起動してください（/exit して再度起動）」を表示
- 個別スクリプトも存在し、単独で `--uninstall` / `-h` を受け付ける

## 追記内容

### 追記位置

`README.md` の **「クイックスタート」セクションの直後・「ディレクトリ構成」の直前** に新セクション「グローバルインストール（オプション）」を追加する。

Skills 一覧テーブルの下にも、リード文として 1 行 `グローバルインストール手順は [後述](#グローバルインストールオプション) を参照。` を加えると見通しが良い（任意・要相談）。

### セクション本文（README.md にそのまま貼る想定の Markdown）

```markdown
## グローバルインストール（オプション）

通常はプロジェクトルートから `.claude/skills/...` の相対パスでスクリプトを実行しますが、
複数プロジェクトや他の Claude Code セッションからも同じ Skill を呼び出したい場合は、
グローバル Claude Code プラグインとして `~/.claude/plugins/` に登録できます。

### 前提条件

- `jq` がインストール済み（未インストールの場合: `sudo apt install jq`）
- Claude Code が `~/.claude` にインストール済み

### インストール

\```bash
# プロジェクトルートから実行（gpu-server と llama-server をまとめて登録）
.claude/skills/install-all-global.sh
\```

実行すると以下が行われます:

- `gpu-server` / `llama-server` スキルを `~/.claude/plugins/cache/` 配下にコピー
- SKILL.md 内の相対パス参照を絶対パスに書き換え
- `~/.claude/settings.json` に各スクリプトの実行パーミッションを登録
- プロジェクトの `.env` を `~/.config/gpu-server/.env` に冪等マージ（HF_TOKEN 等）

インストール完了後、**Claude Code を再起動してください**（`/exit` で終了し再度起動）。

### アンインストール

\```bash
.claude/skills/install-all-global.sh --uninstall
\```

### 個別インストール / ヘルプ

\```bash
# ヘルプ表示
.claude/skills/install-all-global.sh --help

# Skill 単位でインストール（一括ではなく個別に入れたい場合）
.claude/skills/gpu-server/scripts/install-global.sh
.claude/skills/llama-server/scripts/install-global.sh
\```
```

### 「ディレクトリ構成」セクションへの追記

`.claude/skills/install-all-global.sh` の存在もツリーに加える:

```
└── .claude/skills/
    ├── install-all-global.sh         ← 追記
    ├── gpu-server/
    │   ├── scripts/
    │   │   ├── install-global.sh     ← 追記
    │   │   └── ...
    ...
    └── llama-server/
        ├── scripts/
        │   ├── install-global.sh     ← 追記
        │   └── ...
```

## 修正対象ファイル

- `/home/ubuntu/projects/llm-server-ops/README.md` のみ

スクリプト本体・他の Skill ファイルは変更しない（**ドキュメント追加のみ**）。

## 検証

- `README.md` を Markdown ビューア（GitHub やローカル）で開き、目次・コードブロック・テーブルが崩れていないか目視確認
- 追記したコマンドをそのままコピペし、`.claude/skills/install-all-global.sh --help` だけは実際に実行して Usage が表示されること（インストール自体は副作用が大きいので実行しない）

## レポート

CLAUDE.md の制約に従い、Plan mode で計画 → 実装した場合は対になるレポートを `report/` に作成する。ファイル名形式は他レポートに倣う（`YYYY-MM-DD_HHMMSS_<topic>.md`）。
