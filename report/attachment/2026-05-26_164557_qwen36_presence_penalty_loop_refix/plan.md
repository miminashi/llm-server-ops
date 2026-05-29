# Qwen3.6 verbatim ループ再発: presence_penalty 引き上げ対策

## Context

ytdlor-production プロジェクトの別 Claude Code セッションで、Qwen3.6-35B-A3B 由来とみられる thinking ループが再発した。提示ログでは Active Storage の Disk service に関する同一段落（"...key bsrwt2geuu64a0oa9oixe68gcemy に対して、storage/bs/rwt2/geuu/... のようなパスになります。しかし、ボリューム内のファイルは 00, 03, 05 などのディレクトリに格納されています。これは、Active Storageの古いバージョン（Rails 6以前）のディレクトリ構造かもしれません..."）が 10 回以上ほぼ verbatim で繰り返されており、**段落単位の長距離 verbatim ループ** に該当する。

直前の対策（2026-05-26 #3, レポート [14:38](../../projects/llm-server-ops/report/2026-05-26_143817_qwen36_sampler_path_recall_fix.md)）で DRY サンプラを完全無効化 (`--dry-multiplier 0`) し、ループ抑制は `presence_penalty=0.5` 単独に委ねていた。今回の再発は、**`presence_penalty=0.5` 単独では数百〜数千トークン規模の段落 verbatim 反復に対して抑制力が足りない** ことを示している。

SKILL.md L68 で「verbatim ループが再発した場合は、まず `presence_penalty` を 1.0 まで戻し...」と既に運用が明文化されており、本対策はその一段目（1.0 への引き上げ）を default 適用するものである。DRY 再有効化は過去レポートで副作用（URL 数字書換／長パス末尾切断）が greedy decoding でも観測されているため、本対策では行わない。

## 変更内容

### 1. `.claude/skills/llama-server/scripts/start.sh` (L211-214)

Qwen3.x プロファイルの `SAMPLING_OPTS` を以下に変更:

```diff
   *Qwen3.5*|*Qwen3.6*)
-    SAMPLING_OPTS="--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 --presence-penalty 0.5 --dry-multiplier 0"
+    SAMPLING_OPTS="--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 --presence-penalty 1.0 --dry-multiplier 0"
     ;;
```

合わせて L196-210 のコメントブロックに 2026-05-26 #4 の経緯エントリ（presence_penalty 0.5 では長距離段落 verbatim ループ抑制不足 → 1.0 へ引き上げ）を追記し、L209-210 の「再発時運用」記述を「次の段は client 側で `dry_multiplier=0.4` 送信」に更新する。

### 2. `.claude/skills/llama-server/SKILL.md`

- L51-57 の Qwen3.x 共通サンプリングプロファイル表記を `--presence-penalty 0.5` → `--presence-penalty 1.0` に更新
- L61 の説明文（Qwen 公式推奨値）を「下寄りの 0.5 → 中央値寄りの 1.0」に書き換え、過去 #1 で 1.0 採用時の URL 副作用が DRY 由来であり presence_penalty 単独 1.0 では副作用観測がない旨を補足
- L63-68 のチューニング履歴に **2026-05-26 #4** エントリを追加（今回の再発観測と対応）

## 採用しない案

- **DRY 再有効化 (multiplier=0.3〜0.8)**: 過去 2 レポートで URL 数字書換／長パス末尾切断が greedy decoding でも観測済み。再有効化はサーバ default では避け、必要なクライアントがリクエスト JSON で `dry_multiplier` を送る運用を維持する
- **クライアント側のみ対応**: 影響を受けるクライアント（ytdlor 等）が複数あり、サーバ default で先に手当する方が運用負荷が低い。L68 既存記述の方針とも一致

## 検証手順

llama-server を再起動し、過去レポート 2 件のテストケース（URL／長パス再現）と新規ループ実例を curl で軽くチェックする。

### 1. llama-server 再起動

```bash
# gpu-server skill で対象サーバのロックを取得して再起動
# (現状の default 稼働サーバは t120h-p100 / Qwen3.6-35B-A3B-MTP)
.claude/skills/llama-server/scripts/start.sh t120h-p100 \
  "unsloth/Qwen3.6-35B-A3B-Instruct-MTP-GGUF:Q4_K_M"
```

### 2. URL/長パス回帰チェック（過去レポート流用、greedy 設定）

```bash
# URL 4 ケース（過去レポート 02:27 の流用） — IPv4 オクテット書換ゼロを確認
# 長パス（過去レポート 14:38 の流用、rails-upgrade-to-8.1.0 等）— 末尾切断なしを確認
# 各テストは temperature=0, top_k=1 (greedy) で 3 回実行し全行完全一致を確認
```

具体的なテストプロンプトは `report/attachment/2026-05-26_022707_qwen36_sampler_url_recall_fix/` 配下の curl スクリプトをそのまま再利用する。

### 3. ループ再現チェック

提示された Active Storage 文脈に近い長文（Rails Active Storage のパス構造を尋ねるプロンプト）を投げ、同一段落の verbatim 反復が出ないこと（5 段落以上の連続反復が観測されない）を確認する。実プロンプトの完全再現は元セッションのコンテキスト依存のため不可だが、近傍プロンプトで挙動傾向は確認できる。

### 4. 結果判定

- ✅ URL/長パス回帰なし + ループ抑制が改善 → 採用確定、レポート作成
- ❌ ループ再発 → 次手として SKILL.md に「client 側で `dry_multiplier=0.4` 送信」運用へエスカレーション（本 plan 範囲外）

## レポート作成

CLAUDE.md ルールに従い対応レポートを作成する:

- ファイル名: `report/2026-05-26_<JST hhmmss>_qwen36_presence_penalty_loop_refix.md`
  - タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得
- 添付ディレクトリ: `report/attachment/2026-05-26_<JST hhmmss>_qwen36_presence_penalty_loop_refix/`
- 添付物: 本 plan ファイル (`plan.md`)、curl テストの request/response ログ、観測ループ実例の抜粋
- 内容: 経緯（前 2 レポートへのリンク）、今回の観測ログ抜粋、変更差分、検証結果、次の手（必要時の client 側 dry_multiplier 運用）
- 核心発見サマリ: 「`presence_penalty=0.5` 単独では長距離段落 verbatim ループに抑制不足、1.0 で抑制」を冒頭に置く
