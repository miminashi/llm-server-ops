# llama-down.sh unlock 順序修正（Step 3/4 入れ替え）

- **実施日時**: 2026年5月12日 10:59 〜 11:07 JST

## 添付ファイル

- [設計修正フェーズのプラン](attachment/2026-05-12_105909_llama_down_unlock_order_fix/plan.md)
- [V3 再検証 setup ログ (再起動)](attachment/2026-05-12_105909_llama_down_unlock_order_fix/verification/cycle4_v3_after_fix_setup.log)
- [V3 再検証本体ログ (自分ロック停止フロー)](attachment/2026-05-12_105909_llama_down_unlock_order_fix/verification/cycle4_v3_after_fix.log)

## 前提・目的

- **背景**: 前タスク（[実機検証フェーズ](2026-05-12_051827_llama_up_down_scripts.md)）で `llama-down.sh` の V3（自分ロックでの正常停止）が **PASS with caveat** と判定された。具体的には:
  > 自分のロック検出 → stop → power off は成功するが、**最後の `unlock.sh` で SSH 接続失敗** (`llama-down.sh EC=3`)。`power.sh off` の Redfish API がグレースフルシャットダウンを即時受理する一方、OS のシャットダウン処理に数秒〜数十秒かかり、その間に `unlock.sh` の SSH 接続（ConnectTimeout=5）が失敗するため。

- **目的**: `llama-down.sh` の Step 3 (`power.sh off`) と Step 4 (`unlock.sh`) の順序を入れ替えて、unlock を SSH 接続が確実に有効な状態で実行する。V3 を caveat なしの **PASS** に更新する。

- **方針**: 修正対象は `.claude/skills/llama-server/scripts/llama-down.sh` と `.claude/skills/llama-server/SKILL.md` のみ。前タスクで承認された「既存スクリプト未変更」原則（受け入れ基準 5）を継続維持し、`gpu-server` 配下のスクリプトおよび `start.sh` / `stop.sh` / `wait-ready.sh` / `llama-up.sh` は無変更。

## 環境情報

- リポジトリ: `/home/ubuntu/projects/llm-server-ops` (master ブランチ)
- 対象サーバ: `t120h-p100` (10.1.4.14, NVIDIA P100 ×4, 64 GB VRAM)
- 検証モデル: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M` モード `fit` (128k ctx, B14b OT, Phase U-6 プロファイル)
- 実行ホスト: `aws-mmns-generic`
- llama.cpp バージョン: `1ec7ba0c1` (前タスクから据え置き、差分なし)

## 修正内容

### llama-down.sh の Step 順序入れ替え

**変更前**:

| Step | 内容 |
|------|------|
| 2/4 | `stop.sh` |
| 3/4 | `power.sh off` |
| 4/4 | `unlock.sh`（自分保持時のみ） |

**変更後**:

| Step | 内容 |
|------|------|
| 2/4 | `stop.sh` |
| 3/4 | `unlock.sh`（自分保持時のみ） |
| 4/4 | `power.sh off` |

ヘッダーコメントの「ロック検証ルール」は変更不要。WARNING メッセージは「power off を続行します」→「続行します」、「unlock 段階へ進みます」→（削除）に調整。

### SKILL.md の動作説明更新

`.claude/skills/llama-server/SKILL.md` の「### 停止: llama-down.sh」セクション内、動作説明 2-3 行目:

**変更前**:
```
2. `stop.sh` → `power.sh off`
3. 自分保持だったロックのみ `unlock`
```

**変更後**:
```
2. `stop.sh` → 自分保持時のみ `unlock` → `power.sh off`
```

下部の補足文「`stop.sh` または `power.sh off` が失敗しても警告のみで後続ステップを継続します」は変更不要（修正後も同じ意味で成立）。

## 再現方法

```bash
# 1. llama-down.sh の Step 順序を入れ替え（Step 3/4 を交換）
$EDITOR .claude/skills/llama-server/scripts/llama-down.sh

# 2. SKILL.md の動作説明を新順序に更新
$EDITOR .claude/skills/llama-server/SKILL.md

# 3. 構文チェック
bash -n .claude/skills/llama-server/scripts/llama-down.sh

# 4. 既存スクリプト未変更の確認
git diff --stat \
  .claude/skills/llama-server/scripts/{start,stop,wait-ready,llama-up}.sh \
  .claude/skills/gpu-server/scripts/*.sh
# → 空

# 5. 実機再検証 V3:
.claude/skills/llama-server/scripts/llama-up.sh         # 再起動
.claude/skills/gpu-server/scripts/lock.sh t120h-p100    # 自分ロック
.claude/skills/llama-server/scripts/llama-down.sh       # 修正版実行
# 期待: Step 2 stop → Step 3 unlock (Lock released) → Step 4 power off → exit 0
```

## 実施結果

### 静的検証

- `bash -n` 構文チェック: **PASS**
- 既存スクリプト `git diff --stat`: **空**（受け入れ基準 5 維持）
- SKILL.md 表記: 「2. stop → unlock → off」の 1 行形式に更新

### 実機検証（V3 再実施）

**Cycle 4** (10:59 〜 11:07 JST、約 8 分): t120h-p100 を OFF 状態から再起動 → 自分ロック取得 → 修正版 `llama-down.sh` を実行。

**Cycle 4 setup（再起動）**:
- llama.cpp ビルド差分なし（`1ec7ba0c1` のまま）
- モデルキャッシュ済み
- 起動完了まで `wait-ready` 34/60 attempts (170 秒)
- llama-up.sh 本体は `==> 起動完了` で正常終了（wrapper は `ssh -f` fd 継承で TaskStop 必要、前タスク既知）
- `curl http://10.1.4.14:8000/health` → `{"status":"ok"}` 確認

**Cycle 4 V3 本体**:

```
=== C-2: 自分のロック取得 ===
Lock acquired: t120h-p100 (session: aws-mmns-generic-2728214-20260512_110615)

=== C-3: 修正版 llama-down.sh ===
==> [1/4] t120h-p100 のロック状態を確認中...
t120h-p100: LOCKED
  Holder: aws-mmns-generic-2728214-20260512_110615
    自分のロック (holder=aws-mmns-generic-2728214-20260512_110615) → 停止後に解放します
==> [2/4] llama-server を停止中...
==> llama-server を停止中... (PID: 2833 2834)
llama-server を停止しました。
==> ttyd を停止中...
WARNING: stop.sh が失敗しましたが、続行します
==> [3/4] ロックを解放します...
Lock released: t120h-p100 (was held by: aws-mmns-generic-2728214-20260512_110615)
==> [4/4] t120h-p100 の電源を OFF にします...
t120h-p100: off コマンドを送信しました (ResetType: GracefulShutdown)
==> 停止完了

llama-down.sh EC=0 ELAPSED=52s
```

**判定**: **PASS**（caveat なし）

- `Lock released:` メッセージが Step 3 で正常出力（SSH 接続が生きてる間に実行）
- 後続 Step 4 の `power.sh off` は通常通り成功（HTTP 2xx 応答）
- 最終終了コード **EC=0**
- 所要時間 52 秒（前回 PASS with caveat 時 37 秒 → +15 秒、内訳: Step 順序入れ替えに伴う追加処理ではなく、shut down コマンド前の unlock 処理時間が増加分の主因）

### V3 改善前後の比較

| 項目 | 修正前（前タスク Cycle 2） | 修正後（本タスク Cycle 4） |
|------|---------------------------|---------------------------|
| Step 順序 | stop → off → unlock | stop → **unlock → off** |
| unlock 結果 | `Error: SSH connection to t120h-p100 failed` | `Lock released: t120h-p100 (was held by: ...)` |
| llama-down.sh EC | 3 | **0** |
| 所要時間 | 37 秒 | 52 秒 |
| 残留ロック | GPU サーバ /tmp に symlink 残存 | 解放済み |

## 既知の制約・今後の改修

### 解消した制約

- ✅ **`power.sh off` 後の `unlock.sh` 失敗** (前タスクで発覚): Step 順序入れ替えで解消。`unlock.sh` を `power.sh off` の前に実行することで SSH 接続が生きてる間に確実に解放できる。

### 引き続き残る制約（本タスク範囲外）

- **`start.sh` の `ssh -f` 起動による wrapper ハング**: `llama-up.sh` をパイプライン (`tee` など) 経由で呼ぶと、`ttyd` プロセス (port 7681/7682) の file descriptor を SSH クライアントが継承しているため、呼び出し側の `tee` が EOF を受け取れずハングする。本タスクの再起動でも観測（TaskStop で回避）。これは `llama-server` スキル既存の `start.sh` の `ssh -f` 起動パターンに由来し、本タスク範囲外。
  - 回避案: `ssh -f` を `ssh -n + nohup ... &` に置き換える、または `ssh ... </dev/null >/dev/null 2>&1 &` で fd を明示的に切る。
- **電源 ON 後の OS 起動失敗**: SSH 待機 5 分タイムアウトで exit 1（前タスクから据え置き）。
- **`/health` 200 だが API 異常**: 設計上「200 なら既起動」とみなし `start.sh` をスキップ（前タスクから据え置き）。

## 参考

- 前タスクレポート: [llama-server 統合スクリプト追加（実機検証フェーズ）](2026-05-12_051827_llama_up_down_scripts.md)
- 設計修正フェーズのプラン: [attachment/2026-05-12_105909_llama_down_unlock_order_fix/plan.md](attachment/2026-05-12_105909_llama_down_unlock_order_fix/plan.md)
