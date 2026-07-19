# mi25 で llama-server ログを ttyd 経由で閲覧できるようにする

## Context

- **要望**: mi25 で llama-server を起動したときも、他 GPU サーバ (t120h-p100 / t120h-m10) と同様に **ttyd 経由でブラウザから llama-server ログを閲覧** できるようにしたい。
- **調査結果**: llama-server スキル側のコード (`ttyd-up.sh`, `start.sh`) は **既に mi25 分岐まで実装済み** で、`start.sh mi25 ...` を叩けば ttyd 起動が自動で呼ばれる設計になっている (2026-06-10 の "ttyd 起動信頼性向上" 対応で集約済み)。
- **未対応だった実体**: mi25 側に `ttyd` バイナリが導入されていなかったため、`ttyd-up.sh` の起動処理が silent fail し続けていた (LISTEN 検証は WARNING を出すが常に `exit 0`)。実機検証も 2026-06-10 レポートの手順 8 で予定されていたが mi25 は対象外として未実施のまま。
- **本計画のスコープ**: バイナリインストール (ユーザ側で対応中) の完了を前提に、**mi25 実機での end-to-end 動作確認** と、**再発防止のためのスキル/レポート整備** に絞る。コード変更は必要最小限。

## 現状 (2026-07-19 時点で読み取れた事実)

| 項目 | 状態 |
|------|------|
| `ttyd-up.sh` の mi25 分岐 (`GPU_CMD="watch -n 1 rocm-smi"`) | 実装済み (`.claude/skills/llama-server/scripts/ttyd-up.sh:39`) |
| `start.sh` からの `ttyd-up.sh` 呼び出し | 実装済み (`start.sh:416`) |
| mi25 側 `ttyd` バイナリ | **ユーザがインストール中** (直前まで未導入) |
| mi25 側 `watch` / `rocm-smi` | 導入済み |
| mi25 の 7681/7682 現在の LISTEN | 空き (8000 のみ llama-server が LISTEN) |
| llama-server ログ出力先 | `/tmp/llama-server.log` (`start.sh:413` の `nohup ... > /tmp/llama-server.log 2>&1`) |
| stop.sh の pkill 自己マッチ問題 | 修正済み (`^ttyd --port 768` アンカー) |

## 変更方針

**コード変更なし**を基本方針とする。既存の `ttyd-up.sh` / `start.sh` は mi25 でそのまま動くはずなので、まずは実機で確認する。ドキュメント側の 1 箇所だけ、ttyd バイナリ導入が暗黙前提だったことを明示化する。

## 実施手順

### 1. ttyd 導入の確認 (前提)

```bash
ssh mi25 "command -v ttyd && ttyd --version 2>&1 | head -1"
```

`/usr/bin/ttyd` などに実行可能な形で存在し、`ttyd version 1.6.x` 等が出ることを確認する。ユーザ側インストールの完了待ち。

### 2. `ttyd-up.sh` 単体での起動確認 (llama-server 稼働状態のまま実施)

**mi25 は現在使用中** (llama-server 稼働中) だが、`ttyd-up.sh` は llama-server プロセス・ポート 8000 に一切触れず、7681/7682 のみを操作するため安全に実行できる。**ロック取得は不要** (`ttyd-up.sh` はロックを取らない設計 = `ttyd-up.sh:16`)。llama-server を停止・再起動する操作は本計画では一切行わない。

```bash
.claude/skills/llama-server/scripts/ttyd-up.sh mi25
ssh mi25 "ss -tlnp 2>/dev/null | grep -E ':(7681|7682) '"
```

期待:
- 標準出力に `[OK] GPU監視  : http://10.1.4.13:7681` と `[OK] ログ閲覧 : http://10.1.4.13:7682` が両方出る
- `ss` で 7681/7682 とも LISTEN 状態

### 3. 7682 (ログ閲覧) の end-to-end 確認

ブラウザで `http://10.1.4.13:7682` を開き、`tail -f /tmp/llama-server.log` の出力がストリームされていることを確認する。llama-server がリクエストを処理していれば新規行が流れる。空でも `tail -f` プロンプトが生きていれば OK (`ttyd-up.sh:75` で `touch` により最低限のファイルは担保済み)。

### 4. 7681 (GPU 監視) の TERM 罠回帰チェック

これは 2026-06-10 レポートの手順 8 で mi25 対象外として skip された確認事項。ブラウザで `http://10.1.4.13:7681` を開き:

- `watch -n 1 rocm-smi` が描画され、1 秒ごとに更新される
- `Error opening terminal: unknown.` が出ない (ttyd-up.sh の TERM ラップが効いている証拠)

サーバ側でも:
```bash
ssh mi25 "pgrep -a watch; pgrep -a rocm-smi"
```
で `watch -n 1 rocm-smi` プロセスが生存していること。

### 5. `start.sh` からの統合起動確認 — **今回は実施しない**

現在 mi25 の llama-server は使用中のため、**`start.sh` 経由の統合確認は今回スコープ外**。`start.sh:416` から `ttyd-up.sh` が呼ばれるフローはコードで確認済みで、手順 2〜4 で `ttyd-up.sh` 単体が動くことを検証すれば、`start.sh` 経由も同じコードパスを通るため実質担保される。次回自然に llama-server を再起動する機会に、副作用ゼロで検証できる。

### 6. ドキュメント補足 (必要最小限)

**修正対象ファイル**: `.claude/skills/llama-server/SKILL.md` (もしくは `.claude/skills/llama-server/scripts/ttyd-up.sh` 冒頭コメント)

現状の SKILL.md (line 190〜232) は「ttyd は自動起動される」と書いてあるが、**サーバ側 `ttyd` バイナリが導入済みであることが暗黙の前提** になっている。今回 mi25 で未導入だったことが判明したため、**「前提: サーバ側に `ttyd` が入っていること (Ubuntu なら `sudo apt install ttyd`)」** を 1 行追記する。導入自動化までは踏み込まない (今回の mi25 対応は手動で完結する規模)。

追記候補位置: SKILL.md line 211 の「### ttyd-up.sh の動作」直下に注記を 1 行入れる形が最小侵襲。

### 7. レポート作成 (CLAUDE.md ルール)

plan mode でまとまった作業を行うため、完了時に `report/YYYY-MM-DD_HHMMSS_mi25_ttyd_llama_log.md` を [REPORT.md](../projects/llm-server-ops/REPORT.md) のフォーマットに従い作成。必須セクション (概要含む) を守る。手順 2〜5 の実測結果と、mi25 での 2×2 (7681/7682 × 描画/LISTEN) が全 OK になったことを核心発見サマリに書く。

## 想定リスク

- **万一 `ttyd-up.sh mi25` で 7681 の watch が Error opening terminal で即死する場合**: TERM ラップは既に入っている (`ttyd-up.sh:82`) ので、`watch` (procps) のバージョン依存で terminfo 参照が壊れているケースを疑う。`ncurses-term` 未導入なら `sudo apt install ncurses-term` で解消することが多い。ただし今日の mi25 でこの症状が出るかは未知数で、出てから調査で十分。
- **7682 の `tail -f` が即終了する場合**: `ttyd-up.sh:75` の `touch /tmp/llama-server.log` で対策済み。すでに llama-server 稼働中なので実際にはログが流れており、まず問題ない。
- **ポート衝突**: 現状 mi25 で 7681/7682 は空き。9221/9222 (chrome-novnc-cdp) とも別空間で衝突なし。

## 検証

- **成功条件**: 手順 2〜4 が全て期待通り (両ポート LISTEN、ブラウザで rocm-smi 描画、ブラウザで稼働中 llama-server のログストリーム)。
- **完了後の状態**: 次回 mi25 で `start.sh` を叩けば毎回 ttyd も自動で立ち上がり、他 2 サーバと運用が揃う。ドキュメントに前提 (ttyd バイナリ必須) が明示され、次回同種のトラブルを予防できる。
- **本計画のスコープ外**: mi25 使用中のため、llama-server の停止・再起動を伴う `start.sh` 経由の統合確認は実施しない (次回自然に再起動する機会に確認)。
