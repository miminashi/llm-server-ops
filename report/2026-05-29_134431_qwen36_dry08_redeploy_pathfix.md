# Qwen3.x: 未コミットの DRY=0 修正を稼働サーバへ反映しパス破損を解消

- **実施日時**: 2026年05月29日 13:44 JST

## 核心発見サマリ

- opencode `merge-upstream-24` の `fork-regression-test` Phase A が連続タイムアウトした原因は、**稼働中の llama-server が既知バグ設定 `--dry-multiplier 0.8` のまま動いていたこと**だった（[起点レポート](http://10.1.6.4:5032/opencode/report/2026-05-29_102800_merge-upstream-24-llm-sampler-corruption.md)）。DRY=0.8 はファイルパスを文字レベルで破損させ（`.opencode`→`.oencode` 等）、opencode が破損パスへの書き込みで「外部ディレクトリアクセス許可」ダイアログを出し plan_exit がタイムアウトしていた。
- DRY=0.8 が long path / URL 破損の真犯人であることは **2026-05-26 のデバッグ (#1〜#4) で greedy decoding により再現確定済み**で、`--dry-multiplier 0` への修正も完了していた。しかし**その修正がコミットも push もされず本マシンの作業ツリーに 3 日間放置**され、別 checkout（origin/master = dry=0.8）から起動された共有サーバが旧設定のまま稼働していたために再発した。
- 本対応で **(1) dry=0 修正をコミット (`673472b6`)、(2) 共有サーバ t120h-p100 を作業ツリーの修正版 start.sh で再起動、(3) パス再現を検証** した。
- **検証 4 ケースすべて PASS**。稼働フラグは `presence-penalty 1.0 / dry-multiplier 0`。

| 検証 | 内容 | サンプラ | 結果 | 判定 |
|------|------|---------|------|------|
| A-1 | URL を 3 回反復 | greedy (temp=0,top_k=1) | 3 行とも `http://10.1.6.5:8001/health` 完全一致 | ✅ |
| A-2 | 長パスを 3 回反復 | greedy | 3 行とも完全一致、末尾切断・ハイフン書換なし | ✅ |
| B | plan ファイルパスを 3 箇所で出力 | temp 0.6 実運用デフォルト | `.opencode`/`ytdlor`/タイムスタンプとも 3 箇所完全一致 | ✅ |
| C | 起点レポート診断1 (fox×3) の追試 | temp 0.6 | 3 行とも `The quick brown fox jumps over the lazy dog.` 完全一致（dry=0.8 では `lazy狗`/`laze dog`/`the`脱落 に破損していた） | ✅ |

## 添付ファイル

- [実装プラン](attachment/2026-05-29_134431_qwen36_dry08_redeploy_pathfix/plan.md)
- [検証A-1: URL greedy 全レスポンス](attachment/2026-05-29_134431_qwen36_dry08_redeploy_pathfix/verifyA_url_greedy.json)
- [検証A-2: 長パス greedy 全レスポンス](attachment/2026-05-29_134431_qwen36_dry08_redeploy_pathfix/verifyA_path_greedy.json)
- [検証B: plan パス temp0.6 全レスポンス](attachment/2026-05-29_134431_qwen36_dry08_redeploy_pathfix/verifyB_planpath_temp06.json)
- [検証C: fox×3 temp0.6 全レスポンス](attachment/2026-05-29_134431_qwen36_dry08_redeploy_pathfix/verifyC_fox_temp06.json)
- [稼働フラグ (ps aux)](attachment/2026-05-29_134431_qwen36_dry08_redeploy_pathfix/running_flags.txt)

## 前提・目的

### 背景

opencode の `merge-upstream-24` 動作確認担当 Claude が、サンプラー設定の修正を本担当に依頼する
[中断レポート](http://10.1.6.4:5032/opencode/report/2026-05-29_102800_merge-upstream-24-llm-sampler-corruption.md)
を残した。同レポートは「DRY サンプラ + presence_penalty がパス文字列を破損させている」と切り分けつつ、
**実際の稼働フラグは未確認**（ログ読み取りが拒否されたため SKILL.md 記載からの推定）と申し送っていた。

### 目的

- 稼働サーバの実フラグを確認し、パス破損の真因を確定する
- 2026-05-26 #4 で検証済みの設定（`presence_penalty=1.0` + `dry_multiplier=0`）を稼働サーバへ反映する
- パス再現の正常化を実証し、fork-regression-test を再実行できる状態へ戻す

### 前提条件

- 起点レポートにより GPU ロックは解放済み・llama-server は ON のまま残されていた

## 環境情報

- **サーバ**: t120h-p100 (10.1.4.14)、GPU: NVIDIA Tesla P100 16GB × 4
- **モデル**: `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`、ctx-size 131072
- **llama.cpp**: `19e92c33e`（2026-05-28、既ビルド。再起動時 "Already up to date" で差分なし）
- **本リポジトリ**: `aws-mmns-generic` 上の checkout、修正コミット `673472b6`（push なし）
- **クライアント**: curl で OpenAI 互換 API を直接叩いた

## 根本原因（フォレンジック）

稼働サーバ（09:46 起動）の実フラグは `--presence-penalty 1.0 --dry-multiplier 0.8`。本マシンで
`dry-multiplier 0.8` を生成できるソースを調査した結果:

| ソース | dry 値 | 備考 |
|--------|--------|------|
| 作業ツリー `start.sh` L218 / SKILL.md | **0**（修正済） | 未コミット、mtime 2026-05-26 16:38 |
| HEAD = origin/master (`8f7195eb`) | **0.8** | コミット済みの旧設定 (fed12136 系) |
| plugin cache v1.0.0 (`~/.claude/plugins/...`) | dry 行なし | 2026-05-13 の旧版、本件と無関係 |

- 起点レポートは「SKILL.md に dry=0.8 と記載」と引用しており、これは **HEAD の内容**。本作業ツリー
  （dry=0）とは異なる。本マシンに llm-server-ops の checkout は 1 つだけ。
- → **起点レポート作成者は origin/master(`8f7195eb`=dry=0.8) のクリーンな別 checkout（別マシン）から
  共有 GPU サーバを起動した**と確定。5/26 の dry=0 修正は本マシンの作業ツリーにのみ存在し push されて
  いなかったため、相手マシンには一切届いていなかった。これが「修正済みのはずのバグが再発した」真因。
- #24 は llama.cpp を新規リビルドしたが、DRY を 0 にすればビルド差異は無関係になる（検証 C で実証）。

## 変更内容

### コミット `673472b6`（push なし）

- `start.sh` L218 `--dry-multiplier 0.8` → `0`（Qwen3.5/3.6 共通プロファイル）
- `SKILL.md` 対応記述・チューニング履歴
- 経緯レポート 3 件 (#1〜#4 系) + attachment を同梱

## 検証結果

### 起動フラグ反映確認

```
$ ssh t120h-p100 "ps aux | grep '[l]lama-server -m' | grep -oE 'presence-penalty [^ ]+|dry-multiplier [^ ]+'"
presence-penalty 1.0
dry-multiplier 0
```

### 検証 A — greedy 完全一致（リグレッションチェック）

```
# URL
http://10.1.6.5:8001/health
http://10.1.6.5:8001/health
http://10.1.6.5:8001/health
# 長パス
/home/ubuntu/projects/ytdlor/.worktree/rails-upgrade-to-8.1.0/config/environments/production.rb
（3 行とも完全一致）
```

### 検証 B — plan モード相当（temp 0.6、起点レポートの破損シナリオ再現）

```
/home/ubuntu/projects/ytdlor/.opencode/plans/2026-05-29_140000_add-download-retry.md
プランファイル /home/ubuntu/projects/ytdlor/.opencode/plans/2026-05-29_140000_add-download-retry.md に計画を書き込みます
/home/ubuntu/projects/ytdlor/.opencode/plans/2026-05-29_140000_add-download-retry.md
```

- `.opencode`・`ytdlor`・タイムスタンプとも 3 箇所すべて完全一致。破損なし。

### 検証 C — 起点レポート診断1 の追試（fox×3、temp 0.6）

```
The quick brown fox jumps over the lazy dog.
The quick brown fox jumps over the lazy dog.
The quick brown fox jumps over the lazy dog.
```

- dry=0.8 では `lazy狗` / `laze dog` / `the` 脱落 に破損していたが、dry=0 で完全に解消。

## 再現方法

```bash
# 1. ロック取得 → 再起動（作業ツリーの相対パス start.sh = dry=0 を使用）
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
.claude/skills/llama-server/scripts/stop.sh t120h-p100
.claude/skills/llama-server/scripts/start.sh t120h-p100 "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
.claude/skills/llama-server/scripts/wait-ready.sh t120h-p100 "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072

# 2. 起動フラグ確認
ssh t120h-p100 "ps aux | grep '[l]lama-server -m' | grep -oE 'presence-penalty [^ ]+|dry-multiplier [^ ]+'"
# → presence-penalty 1.0 / dry-multiplier 0

# 3. 検証 A/B/C は添付の各 *.json を -d で POST（本文の通り）
curl -s http://10.1.4.14:8000/v1/chat/completions -H "Content-Type: application/json" -d @verifyA_url_greedy入力.json
```

## #24 マージ担当への引き継ぎ（重要）

- 共有サーバ t120h-p100 は **`presence-penalty 1.0 / dry-multiplier 0` で ON のまま**にし、GPU ロックは解放した。
  起点レポートの再開手順 §3（`fork-regression-test` label=merge-upstream-24, num_plan_a=5）をそのまま実行できる。
- **重要**: 本修正は本マシンでコミットしたが **push していない**。あなたの別 checkout は依然 dry=0.8 のまま。
  - **llama-server を自分の checkout から再起動しないこと**。再起動すると dry=0.8 が再注入され破損が再発する。
  - 既に dry=0 で稼働中の本サーバに対して fork-regression-test を実行すること。
- 恒久的なクロスマシン整合（origin への push → 各 checkout の pull、plugin v1.0.0 の再発行）は今回ユーザ判断で見送り。別途要検討。

## 参照レポート

- 起点（中断）: [merge-upstream-24 LLM サンプラー破損](http://10.1.6.4:5032/opencode/report/2026-05-29_102800_merge-upstream-24-llm-sampler-corruption.md)
- 直近 #4: [presence_penalty を 1.0 へ再引き上げ](2026-05-26_164557_qwen36_presence_penalty_loop_refix.md)
- #3: [DRY 完全無効化に切替](2026-05-26_143817_qwen36_sampler_path_recall_fix.md)
- #1: [DRY breakers 調整で URL 改善](2026-05-26_022707_qwen36_sampler_url_recall_fix.md)
