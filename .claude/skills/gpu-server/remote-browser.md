# リモートブラウザ管理

リモートブラウザはGPUサーバ上でDockerコンテナとして起動します。**llama-serverと同じGPUサーバで起動してください**。

## 排他制御（必須）

**リモートブラウザを操作する前に、必ずロックを取得してください。**

```bash
# ロック取得
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

# ... リモートブラウザの操作 ...

# ロック解放（作業完了後）
.claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

詳細は [排他制御のドキュメント](./lock.md) を参照してください。

---

## 基本コマンド

```bash
# 既存プロセスの確認
ssh mi25 "docker ps | grep chrome-novnc-cdp"
ssh t120h-p100 "docker ps | grep chrome-novnc-cdp"

# 起動
ssh -t mi25 "cd ~/chrome-novnc-cdp && docker compose up"
ssh -t t120h-p100 "cd ~/chrome-novnc-cdp && docker compose up"

# 再起動（必要な場合）
ssh mi25 "cd ~/chrome-novnc-cdp && docker compose restart chrome-novnc"
ssh t120h-p100 "cd ~/chrome-novnc-cdp && docker compose restart chrome-novnc"
```

---

## 重要な注意事項

### 起動/再起動後の待機

**重要: 起動/再起動後は30秒以上待機してから操作を開始してください**。ブラウザの初期化が完了する前にCDP接続を行うとタイムアウトエラーが発生することがあります。

```bash
# 再起動後の待機を含む推奨手順
ssh mi25 "cd ~/chrome-novnc-cdp && docker compose restart chrome-novnc" && sleep 30
```

### 勝手に終了しない

llama-serverと同様、既存のリモートブラウザが起動している場合は**勝手に終了しないでください**。人間や他のエージェントが使用中の可能性があります。

---

## ランごとの再起動は不要

リモートブラウザにはブラウザプロセスを再起動するAPI（ポート9221）が備わっています。`try-browser-use` はこのAPIを自動的に呼び出すため、**ランごとに docker compose を再起動する必要はありません**。

docker compose の再起動が必要なのは以下の場合のみです：
- コンテナが停止・クラッシュした場合
- 設定を変更した場合

---

## エンドポイント

| サーバ | CDP（ブラウザ） | ブラウザ再起動API |
|--------|----------------|------------------|
| mi25 | `http://10.1.4.13:9222` | `http://10.1.4.13:9221` |
| t120h-p100 | `http://10.1.4.14:9222` | `http://10.1.4.14:9221` |

---

## トラブルシューティング

### コンテナが起動しない場合

```bash
# ログを確認
ssh mi25 "cd ~/chrome-novnc-cdp && docker compose logs"

# コンテナを完全に再作成
ssh mi25 "cd ~/chrome-novnc-cdp && docker compose down && docker compose up -d"
```

### CDP接続がタイムアウトする場合

1. コンテナが起動しているか確認
2. 起動後30秒以上待機したか確認
3. ファイアウォール設定を確認（ポート9222）
