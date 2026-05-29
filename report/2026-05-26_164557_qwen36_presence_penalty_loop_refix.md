# Qwen3.6 verbatim ループ再発: presence_penalty を 1.0 へ再引き上げ

- **実施日時**: 2026年05月26日 16:45 JST

## 核心発見サマリ

- **`presence_penalty=0.5` 単独では数百〜数千トークン規模の段落 verbatim ループに対して抑制力が不足する**。クライアント (ytdlor-production の別 Claude Code セッション) で Active Storage の Disk service 構造に関する同一段落（"...`key bsrwt2geuu64a0oa9oixe68gcemy` に対して、`storage/bs/rwt2/geuu/...` のようなパスになります..."）が 10 回以上 verbatim で反復する事象が再発した。
- 対応として Qwen3.x 共通サンプリングプロファイルの **`--presence-penalty 0.5` → `1.0`** へ引き上げ。DRY サンプラ (`--dry-multiplier 0`) は前回 #3 と同じく無効化を維持し、URL/長パスの再現副作用を発生させない。
- **検証 3 ケース (URL 再現 / 長パス再現 / Active Storage 長文回答) すべて PASS**。
  - URL 完全一致（greedy）
  - 長パス完全一致（greedy）
  - 5,459 tokens 構造化解説で段落反復なく完結
- 「`fed12136` で `presence_penalty=1.0` 時に観測されていた URL/IP 数字書換」は **DRY=0.8 が真犯人**であり (前回 #2 / #3 で greedy decoding 再現済み)、`presence_penalty` 単独 1.0 では本検証では未観測。
- 本対策で再発した場合の次の手は、SKILL.md L68 既存記述どおり、クライアント側で `dry_multiplier=0.4` 程度をリクエスト JSON で送る運用に切り替える（サーバ default は変えない）。

## 添付ファイル

- [実装プラン](attachment/2026-05-26_164557_qwen36_presence_penalty_loop_refix/plan.md)
- [Test 1: URL 再現 (greedy) レスポンス](attachment/2026-05-26_164557_qwen36_presence_penalty_loop_refix/test1_url_recall.json)
- [Test 2: 長パス再現 (greedy) レスポンス](attachment/2026-05-26_164557_qwen36_presence_penalty_loop_refix/test2_path_recall.json)
- [Test 3: ループ抑制 (Active Storage 長文) レスポンス](attachment/2026-05-26_164557_qwen36_presence_penalty_loop_refix/test3_loop_suppression.json)

## 参照レポート

- 直近 #3 (DRY 完全無効化に切替): [2026-05-26 qwen36_sampler_path_recall_fix](2026-05-26_143817_qwen36_sampler_path_recall_fix.md)
- 前々回 #1 (DRY breakers 調整で URL 改善): [2026-05-26 qwen36_sampler_url_recall_fix](2026-05-26_022707_qwen36_sampler_url_recall_fix.md)
- 起点 (presence_penalty + DRY を初めて default 有効化): [2026-05-25 qwen36_loop_sampling_fix](2026-05-25_115133_qwen36_loop_sampling_fix.md)

## 前提・目的

### 背景

直近 #3 (2026-05-26 14:38, [path recall fix](2026-05-26_143817_qwen36_sampler_path_recall_fix.md)) で DRY サンプラを完全無効化 (`--dry-multiplier 0`)、thinking ループ抑制は `presence_penalty=0.5` 単独に委ねる運用に切り替えていた。本日、ytdlor-production プロジェクトの別 Claude Code セッションで thinking 段落 verbatim ループの再発を観測したため、サーバ default を再調整する。

### 観測されたループの抜粋

```
Active StorageのDisk serviceは、blob keyに基づいてファイルを保存する際に、キーの最初の2文字をディレクトリ名として使用します。例えば、key bsrwt2geuu64a0oa9oixe68gcemy に対して、storage/bs/rwt2/geuu/... のようなパスになります。
しかし、ボリューム内のファイルは 00, 03, 05 などのディレクトリに格納されています。これは、Active Storageの古いバージョン（Rails 6以前）のディレクトリ構造かもしれません。
あるいは、ボリューム内のファイルがリストア前の古い形式で保存されている可能性があります。
（以下、ほぼ同一段落が 10 回以上繰り返される）
```

- 段落単位で 5〜7 文ほどがほぼ完全一致で 10 回以上反復
- 数百〜数千トークン規模の長距離 verbatim ループに該当
- `presence_penalty=0.5` 単独ではトークン頻度ベースの抑制が弱く、段落丸ごとの再出現を防げない

### 目的

- 段落 verbatim ループの再発を抑制する
- 前回 #2 / #3 で対応した URL/長パス再現性のリグレッションを起こさない

## 環境情報

- **サーバ**: t120h-p100 (10.1.4.14)
- **GPU**: NVIDIA Tesla P100 16GB × 4
- **モデル**: `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`
- **llama.cpp**: HEAD `dbe9c0c8c` (2026-05-26 ビルド、b9341 タグ取り込み済)
- **ctx-size**: 131072 / `-b 8192 -ub 8192` / `--flash-attn 1 --poll 0`
- **本リポジトリ HEAD**: `8f7195eb` 直前 (本コミットを対象に変更を適用)
- **クライアント**: 検証は curl で OpenAI 互換 API を直接叩いた

## 変更内容

### `.claude/skills/llama-server/scripts/start.sh` 行 196-215

```diff
 # --- モデル別サンプリングパラメータ ---
 # Qwen3.x thinking モードは opencode 等の長コンテキストで段落単位の verbatim ループに陥ることがある。
-# Qwen 公式推奨の presence_penalty (0〜2 のうち下寄りの 0.5) のみで対処する。
-#
-# 履歴 (2026-05-26 #3): DRY サンプラは long path / 識別子の末尾を切り落とす副作用が greedy decoding でも
-# 観測されたため、サーバ default では完全無効化 (--dry-multiplier 0、llama.cpp default 値と同じ)。
+# Qwen 公式推奨レンジ (0〜2) の presence_penalty を 1.0 で常用し、DRY サンプラはサーバ default では
+# 完全無効化 (--dry-multiplier 0、llama.cpp default 値と同じ) する。DRY は long path / 識別子の末尾を
+# 切り落とす副作用が greedy decoding でも観測されたため、必要なクライアントだけがリクエスト側で
+# dry_multiplier を送る運用にしている。
 # 経緯:
 #   fed12136          : presence_penalty=1.0 + DRY=0.8 default 有効化 → URL/IP 数字書換の副作用
 #   2026-05-26 #1     : DRY allowed-length=4 + breakers `. / _` (実は最後の '_' だけ有効) で URL 改善
 #   2026-05-26 #2     : `-` 追加 + presence_penalty=0.5 緩和 → path の数字/文字書換は止まったが、
 #                       greedy + dry_multiplier=0 でないと末尾 (.1.0/config/... 等) が切れる
-#   2026-05-26 #3     : DRY サーバ default を 0 (無効) に。thinking ループ抑制は presence_penalty
+#   2026-05-26 #3     : DRY サーバ default を 0 (無効) に。thinking ループ抑制は presence_penalty 0.5
 #                       単独で対応。クライアントが必要なら dry_multiplier をリクエスト側で送れる。
-# verbatim ループが再発した場合は、まず presence_penalty を 1.0 まで戻し、それでも抑制不足なら
-# クライアント側で dry_multiplier=0.4 程度を送る運用に切り替える。
+#   2026-05-26 #4     : ytdlor セッションで Active Storage 文脈の段落 verbatim ループ再発 (同一段落
+#                       10 回以上反復) を観測。presence_penalty=0.5 単独では長距離段落反復に抑制不足と
+#                       判断し、presence_penalty を 1.0 へ引き上げ。fed12136 時の URL 副作用は DRY=0.8
+#                       が原因 (greedy decoding で再現済) であり、presence_penalty 単独 1.0 では
+#                       URL/path リグレッションは観測されない。
+# それでも verbatim ループが再発した場合は、クライアント側で dry_multiplier=0.4 程度を送る運用に
+# 切り替える (SKILL.md 参照)。
 case "$HF_MODEL" in
   *Qwen3.5*|*Qwen3.6*)
-    SAMPLING_OPTS="--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 --presence-penalty 0.5 --dry-multiplier 0"
+    SAMPLING_OPTS="--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 --presence-penalty 1.0 --dry-multiplier 0"
     ;;
```

### `.claude/skills/llama-server/SKILL.md`

- Qwen3.x 共通サンプリングプロファイル表記: `--presence-penalty 0.5` → `--presence-penalty 1.0`
- 反復対策パラメータ説明: 「Qwen 公式推奨レンジ (0〜2) の `presence_penalty` を **1.0** でデフォルト有効化」に書き換え
- チューニング履歴に **2026-05-26 #4** を追加（本レポートと同内容の要約）

## 検証結果

### 起動引数反映確認

```
$ ssh t120h-p100 "ps aux | grep '[l]lama-server -m' | grep -oE 'presence-penalty [^ ]+|dry-multiplier [^ ]+'"
presence-penalty 1.0
dry-multiplier 0
```

### Test 1: URL 再現性（リグレッションチェック）

**プロンプト**: `次のURLを3回繰り返して（一文字も変更しないで）: http://10.1.6.5:8001/health`

**サンプラ**: `temperature=0, top_k=1` (greedy)、サーバ default の `presence_penalty=1.0` 適用

**結果**:
```
http://10.1.6.5:8001/health http://10.1.6.5:8001/health http://10.1.6.5:8001/health
```

- 3 個の URL すべて完全一致、IPv4 オクテット書換ゼロ ✅
- ([Test 1 レスポンス全体](attachment/2026-05-26_164557_qwen36_presence_penalty_loop_refix/test1_url_recall.json))

### Test 2: 長パス再現性（リグレッションチェック）

**プロンプト**: `次のパスを3回繰り返して（一文字も変更しないで）: /home/ubuntu/projects/ytdlor/.worktree/rails-upgrade-to-8.1.0/config/environments/production.rb`

**サンプラ**: `temperature=0, top_k=1` (greedy)

**結果**:
```
/home/ubuntu/projects/ytdlor/.worktree/rails-upgrade-to-8.1.0/config/environments/production.rb
/home/ubuntu/projects/ytdlor/.worktree/rails-upgrade-to-8.1.0/config/environments/production.rb
/home/ubuntu/projects/ytdlor/.worktree/rails-upgrade-to-8.1.0/config/environments/production.rb
```

- 3 行とも完全一致、末尾切断・ハイフン書換なし ✅
- ([Test 2 レスポンス全体](attachment/2026-05-26_164557_qwen36_presence_penalty_loop_refix/test2_path_recall.json))

### Test 3: ループ抑制（主目的）

**プロンプト**: Rails Active Storage の Disk service について blob key `bsrwt2geuu64a0oa9oixe68gcemy` のパス構造を Rails 6 / 7 のバージョン差含めて詳しく説明させる長文回答誘導。

**サンプラ**: 実運用デフォルト `temperature=0.6, top_p=0.95, top_k=20`、サーバ default の `presence_penalty=1.0`

**結果**:
- 出力 `completion_tokens` = **5,459 tokens**
- 構造化された解説（記号付き見出し `🔑`, `🤔`, `💡`, `📚` でセクション化、コードブロック・箇条書きを多用）で完結
- **同一段落の verbatim 反復は観測されず**、各セクションごとに異なる論点を展開
- 末尾は「ご提示のキーが Rails 6 環境由来の場合でも...」のまとめ文で正常終了
- ([Test 3 レスポンス全体](attachment/2026-05-26_164557_qwen36_presence_penalty_loop_refix/test3_loop_suppression.json))

### 総評

| Test | 内容 | 期待 | 実測 | 判定 |
|------|------|------|------|------|
| 1 | URL 再現 (greedy) | IPv4 書換ゼロ | 3 個とも完全一致 | ✅ |
| 2 | 長パス再現 (greedy) | 末尾切断なし | 3 行とも完全一致 | ✅ |
| 3 | Active Storage 長文回答 | 段落反復なく完結 | 5459 tokens 構造化解説で正常終了 | ✅ |

## 再現方法

### 1. サーバ再起動

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
.claude/skills/llama-server/scripts/stop.sh t120h-p100
.claude/skills/llama-server/scripts/start.sh t120h-p100 \
  "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
.claude/skills/llama-server/scripts/wait-ready.sh t120h-p100 \
  "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
```

### 2. 起動引数反映確認

```bash
ssh t120h-p100 "ps aux | grep '[l]lama-server -m' | \
  grep -oE 'presence-penalty [^ ]+|dry-multiplier [^ ]+'"
# 期待: presence-penalty 1.0 / dry-multiplier 0
```

### 3. 検証 3 ケース

添付ディレクトリの `test1_url_recall.json` / `test2_path_recall.json` / `test3_loop_suppression.json` の `request` は本レポート Test 1〜3 で使用した curl プロンプト（本文の通り）。同一 curl を打って `.choices[0].message.content` が同様の出力パターン (3 行完全一致 / 構造化長文) になるか確認する。

## ロールバック条件

- thinking 段落 verbatim ループが 1 セッション中 2 回以上再発した場合
  - **次手**: `dry_multiplier=0.4` を**クライアント側**でリクエスト JSON に追加（サーバ default は変えない）。SKILL.md L68 に明文化済み
  - **その次手**: `dry_multiplier` を 0.8 まで強化＋`dry_allowed_length=8` 程度に緩和（URL/path 副作用の再観測リスクあり、過去 #1〜#2 の知見適用）
- URL/長パスの再現性が回帰した場合
  - 本変更 (`presence_penalty 0.5 → 1.0`) を直接ロールバック (#3 状態へ戻す)。ただし本検証では未観測

## 今後の課題

- 本変更による副作用（頻出語抑制が強まることでの語彙多様化／不自然な言い回し）の有無は curl 単発検証では捕捉できないため、ytdlor-production および opencode 経由の実運用フィードバックを待つ
- 長距離 verbatim ループ抑制の決定打は本来 DRY の `dry_penalty_last_n` を活用するルートだが、過去レポートで観測された末尾切断副作用との両立はまだ未解決。クライアント側 `dry_multiplier` 運用が定着した時点で、サーバ default への再有効化と allowed-length チューニングを再検討する余地あり
