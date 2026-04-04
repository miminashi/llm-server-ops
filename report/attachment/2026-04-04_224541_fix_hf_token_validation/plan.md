# HF_TOKEN検証の401エラー修正

## Context
`start.sh`でHuggingFaceトークンを対話入力すると、正しいトークンでもHTTP 401が返る問題。
原因: `read -rp`で読み取った入力値に対してホワイトスペース・CR文字のトリミングが行われていない。
ペースト時に末尾の`\r`や空白が混入し、curlのAuthorizationヘッダに不正な文字が含まれる。

## 修正対象
- `.claude/skills/llama-server/scripts/start.sh` (32行目付近)

## 修正内容

### 1. トークン入力値のトリミング追加
`read -rp`の直後、空チェックの前に以下を追加:
```bash
# CR・前後空白を除去
HF_TOKEN_INPUT="${HF_TOKEN_INPUT%$'\r'}"
HF_TOKEN_INPUT="$(echo "$HF_TOKEN_INPUT" | xargs)"
```

### 2. デバッグ用レスポンスボディ表示
401エラー時にレスポンスボディも表示し、原因切り分けを容易にする:
```bash
RESPONSE=$(curl -sS -w '\n%{http_code}' \
  -H "Authorization: Bearer $HF_TOKEN_INPUT" \
  https://huggingface.co/api/whoami)
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')
```
エラー時に`$BODY`を表示。

## 検証方法
- トークンに`\r`を付加した文字列でトリミングが正しく動作することを確認
- 無効トークンでエラーメッセージにレスポンスボディが表示されることを確認

## レポート作成
修正完了後、`report/` にレポートを作成する。
- ファイル名: `<timestamp>_fix_hf_token_validation.md`
- 内容: 問題の原因、修正内容、検証結果
- プランファイルを`attachment/`にコピー
- Discord通知を送信
