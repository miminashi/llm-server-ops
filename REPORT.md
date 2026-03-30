# REPORT.md

## レポート作成ルール

- レポートはプロジェクトルート以下の `report` ディレクトリに作成する
- レポートのタイトルは日本語で記載する
- レポートには日時（分まで）を入れる
- レポートのファイル名は `yyyy-mm-dd_hhmmss_レポート名.md` にする（ファイル名のレポート名は英語）
- タイムスタンプは `date +%Y-%m-%d_%H%M%S` コマンドで取得すること（LLM が時刻を推測してはならない）
- レポート内の日時表記は JST (日本標準時) で記載すること。システムが UTC の場合は +9 時間に変換する
- 実験やタスクの前提条件・目的は専用のセクションを設けて記載する
- 実験の再現方法（手順・コマンド等）を記載する
- 実験に際して参照した過去のレポートがある場合は、そのレポートへのリンクを記載する
- 実験レポートにはサーバ構成・ストレージ構成等の環境情報を記載する
- レポートに添付ファイル（プランファイル、ログ、スクリーンショット等）がある場合は `report/attachment/<レポートファイル名>/` ディレクトリに格納し、レポート本文から相対パスでリンクすること
  - `<レポートファイル名>` は `.md` を除いたファイル名（例: `2026-03-30_120000_llama_server_benchmark`）
  - リンク例: `[実装プラン](attachment/2026-03-30_120000_llama_server_benchmark/plan.md)`
- **プランファイルの添付（必須）**: プランモードで作業を行った場合、レポート作成時に必ず以下の手順でプランファイルを添付すること:
  1. 添付ディレクトリを作成: `mkdir -p report/attachment/<レポートファイル名>/`
  2. プランファイルをコピー: `cp /home/ubuntu/.claude/plans/<plan-name>.md report/attachment/<レポートファイル名>/plan.md`
     - `<plan-name>` はプランモード開始時に指定されたファイル名（例: `groovy-humming-candy`）
  3. レポート本文に `## 添付ファイル` セクションを設け、リンクを記載:
     ```markdown
     ## 添付ファイル

     - [実装プラン](attachment/<レポートファイル名>/plan.md)
     ```

### Discord 通知

レポート作成時は Discord に通知を送信すること。

```bash
.claude/skills/discord-notify/scripts/notify.sh "1行要約" "レポートファイルパス"
```

詳細は `.claude/skills/discord-notify/SKILL.md` を参照。

### 例

```
report/
  2026-03-30_120000_llama_server_benchmark.md
  attachment/
    2026-03-30_120000_llama_server_benchmark/
      plan.md
```

ファイル内の例:
````markdown
# llama-server ベンチマークレポート

- **実施日時**: 2026年3月30日 12:00

## 添付ファイル

- [実装プラン](attachment/2026-03-30_120000_llama_server_benchmark/plan.md)

## 前提・目的

t120h-p100 上で llama-server の推論性能を計測する。

- 背景: モデル選択の判断材料が必要
- 目的: 複数モデルの推論速度・品質を比較する
- 前提条件: t120h-p100 が利用可能であること

## 環境情報

- サーバ: t120h-p100 (10.1.4.14)
- GPU: NVIDIA Tesla P100 16GB
- llama-server バージョン: b1234

## 再現方法

1. llama-server を起動
   ```bash
   .claude/skills/llama-server/scripts/start.sh t120h-p100 model-name
   ```

2. ベンチマークを実行
   ```bash
   curl http://10.1.4.14:8000/v1/completions -d '{"prompt": "Hello", "max_tokens": 100}'
   ```
````
