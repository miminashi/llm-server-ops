# HF_TOKEN対話入力時の検証エラー修正

- **実施日時**: 2026年4月4日 22:45 (JST)

## 添付ファイル

- [実装プラン](attachment/2026-04-04_224541_fix_hf_token_validation/plan.md)

## 前提・目的

`start.sh`でHuggingFaceトークンを対話入力すると、正しいトークンでもHTTP 401が返り認証に失敗する問題を修正する。

- 背景: ユーザーがHuggingFaceで取得した有効なトークンを入力しても、繰り返し「トークンが無効です（HTTP 401）」と表示される
- 目的: トークン入力時の不可視文字混入を除去し、正しく検証できるようにする

## 原因

`read -rp`で読み取った入力値に対して、ホワイトスペースやCR(`\r`)文字のトリミングが行われていなかった。ターミナルでトークンをペーストした際に末尾にCR文字や空白が混入すると、curlの`Authorization`ヘッダに不正な文字が含まれ、HuggingFace APIが401を返す。

## 修正内容

対象ファイル: `.claude/skills/llama-server/scripts/start.sh`

### 1. トークン入力値のトリミング追加

`read -rp`の直後に以下のトリミング処理を追加:
- 末尾のCR文字(`\r`)を除去
- 先頭・末尾の空白文字を除去

```bash
HF_TOKEN_INPUT="${HF_TOKEN_INPUT%$'\r'}"
HF_TOKEN_INPUT="${HF_TOKEN_INPUT#"${HF_TOKEN_INPUT%%[![:space:]]*}"}"
HF_TOKEN_INPUT="${HF_TOKEN_INPUT%"${HF_TOKEN_INPUT##*[![:space:]]}"}"
```

### 2. エラー時のレスポンスボディ表示

検証失敗時にHuggingFace APIのレスポンスボディも表示するように変更し、原因切り分けを容易にした。

変更前:
```
トークンが無効です（HTTP 401）。再入力してください（空入力でスキップ）。
```

変更後:
```
トークンが無効です（HTTP 401: {"error":"Invalid username or password."}）。再入力してください（空入力でスキップ）。
```

## 検証結果

トリミング処理の動作確認:

| 入力パターン | トリミング後 | 結果 |
|-------------|-------------|------|
| `hf_abc123\r` | `hf_abc123` | OK |
| `  hf_abc123  ` | `hf_abc123` | OK |
| `  hf_abc123  \r` | `hf_abc123` | OK |
| `hf_abc123` | `hf_abc123` | OK（変化なし） |

## 再現方法

1. HF_TOKENが未設定の状態で`start.sh`を実行
2. トークン入力プロンプトで、末尾にCR文字付きのトークンをペースト
3. 修正前: HTTP 401エラー、修正後: 正常に検証通過
