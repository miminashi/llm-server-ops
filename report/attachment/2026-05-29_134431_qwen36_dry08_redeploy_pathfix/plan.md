# Qwen3.x サンプラー: 未コミットの DRY=0 修正を稼働サーバへ反映しパス破損を解消

## Context（なぜこの変更が必要か）

opencode `merge-upstream-24` の `fork-regression-test` Phase A が連続タイムアウトした
（[レポート](http://10.1.6.4:5032/opencode/report/2026-05-29_102800_merge-upstream-24-llm-sampler-corruption.md)）。
原因は opencode 側ではなく llama-server のサンプリング層によるパス文字列破損
（`.opencode`→`.oencode`、`ytdlor`→`ytclor` 等）で、破損パスへの書き込みが
「外部ディレクトリアクセス許可」ダイアログを誘発し plan_exit が出ずタイムアウトしていた。

### 根本原因（フォレンジックで確定）

稼働中サーバ（t120h-p100, 2026-05-29 09:46 起動）の実フラグは
`--presence-penalty 1.0 --dry-multiplier 0.8`。これは 2026-05-26 のデバッグ（レポート #1〜#4）で
**「DRY=0.8 が long path / URL の末尾切断・文字書換の真犯人」と greedy decoding で再現確定済みの
既知バグ設定**そのもの。#4 で `--dry-multiplier 0` へ修正し検証（URL/長パス greedy 完全一致、
5459 token 長文ループ抑制）まで済ませていたが、**コミットも push もされず本マシンの作業ツリーに
3 日間放置**されていた。

本マシン (`aws-mmns-generic`) 上で `dry-multiplier 0.8` を生成できるのは HEAD(`fed12136`) の内容のみ:

| ソース | dry 値 | 備考 |
|--------|--------|------|
| 作業ツリー `start.sh` L218 / SKILL.md | **0**（修正済） | 未コミット、mtime 2026-05-26 16:38 |
| HEAD = origin/master (`8f7195eb`) の `start.sh` L202 / SKILL.md | **0.8** | コミット済みの旧設定 |
| plugin cache v1.0.0 (`~/.claude/plugins/.../start.sh`) | dry 行なし | 2026-05-13 の旧版、本件と無関係 |

レポート作成者は「SKILL.md に dry=0.8 と記載」と引用しており、これは **HEAD の内容**。本作業ツリー
（dry=0）ではない。本マシンには llm-server-ops の checkout は 1 つだけ（他クローン無し）。
→ **レポート作成者は origin/master(`8f7195eb`=dry=0.8) のクリーンな別 checkout（別マシン）から
共有 GPU サーバ t120h-p100 を起動した**と確定。5/26 の dry=0 修正は本マシンの作業ツリーにのみ存在し、
push されていないため相手マシンには一切届いていない。これが「修正済みのはずのバグが再発した」真因。
加えて #24 は llama.cpp を新規リビルド（19e92c33e, 5/28）したが、DRY を 0 にすればビルド差異は無関係。

**意図する結果**: 2026-05-26 #4 で検証済みの設定（`presence_penalty=1.0` + `dry_multiplier=0`）を
共有サーバへ反映し、本マシンの修正をコミットして再喪失を防ぐ。パス再現の正常化を実証し、
fork-regression-test を #24 担当が再実行できる状態に戻す。

## 採用方針

レポートの依頼 4 案のうち **案1（DRY 無効化）を採用** — 実体は作業ツリーに既存の dry=0 修正の
「コミット + 稼働サーバへの再デプロイ」。`presence_penalty=1.0` は #4 で検証済みのため維持。
案2（presence 引き下げ）/案3（llama.cpp 差し戻し）は検証で dry=0 でもなお破損する場合のみの
エスカレーション手段として温存する。

ユーザ決定: **コミットする / push はしない**、対応範囲は **サンプラー修正+検証まで**
（fork-regression-test 再実行は #24 マージ担当へ引き継ぐ）。

## 実施手順

### 1. 修正のコミット（再喪失防止・push なし）

作業ツリーの既存変更と untracked レポート群をコミット（push しない）。

- `.claude/skills/llama-server/SKILL.md`, `.claude/skills/llama-server/scripts/start.sh`
- レポート 3 件 + 各 attachment:
  `report/2026-05-26_022707_qwen36_sampler_url_recall_fix.md` /
  `report/2026-05-26_143817_qwen36_sampler_path_recall_fix.md` /
  `report/2026-05-26_164557_qwen36_presence_penalty_loop_refix.md`
- 変更の実体は `start.sh` L218 `--dry-multiplier 0.8`→`0`（SKILL.md は対応記述・履歴）。
- コミットメッセージ末尾に `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。

### 2. 共有サーバを修正版 start.sh で再起動（GPU ロック取得）

レポートはロックを解放し llama-server を ON のまま残している（サンプラー修正担当が操作できるように）。
`gpu-server` skill でロック取得後、**本作業ツリーの相対パス**（= dry=0、plugin 版ではない）で再起動する。

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
.claude/skills/llama-server/scripts/stop.sh t120h-p100
.claude/skills/llama-server/scripts/start.sh t120h-p100 \
  "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
.claude/skills/llama-server/scripts/wait-ready.sh t120h-p100 \
  "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
```

- llama.cpp は 19e92c33e でビルド済みのため再ビルドは差分なしなら即完了。
- `start.sh` はビルドが長引くことがあるため `timeout: 300000` または `run_in_background` で実行。

### 3. 起動フラグの反映確認

```bash
ssh t120h-p100 "ps aux | grep '[l]lama-server -m' | \
  grep -oE 'presence-penalty [^ ]+|dry-multiplier [^ ]+'"
# 期待: presence-penalty 1.0 / dry-multiplier 0
```

### 4. パス再現の検証（破損が止まったことの実証）

curl で OpenAI 互換 API を直接叩く（ロック保持中）。

- **検証 A — greedy 完全一致**（#4 Test 1/2 同等、リグレッションチェック）:
  `temperature=0, top_k=1` で URL `http://10.1.6.5:8001/health` と長パス
  `/home/ubuntu/projects/ytdlor/.worktree/rails-upgrade-to-8.1.0/config/environments/production.rb`
  を「3 回そのまま繰り返す」よう指示 → 3 行とも一字一句一致。
- **検証 B — plan モード相当（temp 0.6）**: レポートで破損した実パス
  `~/projects/ytdlor/.opencode/plans/...` 系を `temp 0.6, top_p 0.95, top_k 20` で複数回言及・
  書き出しさせ、`.opencode`/`ytdlor`/タイムスタンプが破損しないこと。
- **検証 C — レポート診断 1 追試**:「`The quick brown fox jumps over the lazy dog.` を 3 回」を実行し
  dry=0 で破損が解消するか確認。**B/C でなお破損する場合**は presence=1.0 が新ビルドで悪化した
  疑い → エスカレーション（下記）。

### 5. ロック解放・引き継ぎ（push しない前提の重要事項）

- 検証 PASS なら **llama-server は dry=0 で ON のまま**にし、GPU ロックは解放（レポート再開手順
  §3 をそのまま実行できる状態へ）。
- **引き継ぎを明示する**: push しないため #24 担当の別 checkout は dry=0.8 のまま。よって
  「**llama-server を自分の checkout から再起動しないこと。私が dry=0 で起動済みの稼働サーバに対して
  fork-regression-test を再実行すること**」を申し送る（再起動すると dry=0.8 が再注入され破損が再発）。
  恒久対応として「origin に push → 相手が pull」が必要だが今回はユーザ判断で見送り、と明記。
- レポート作成（[REPORT.md](REPORT.md) 準拠、タイトル 50 字以内、核心発見サマリ冒頭に検証 PNG/抜粋）:
  経緯・検証結果・「修正が未コミット/未 push で別 checkout に未達だったことが再発根本原因」を記録。
- discord-notify でレポート URL 通知（任意）。

## エスカレーション（dry=0 でもなお破損する場合のみ）

1. `presence_penalty 1.0 → 0.5`（または 0.3）へ引き下げ再検証（案2）。トレードオフ: 段落 verbatim
   ループ抑制が弱まる（#4 で 0.5 単独は不足と判明）。ループ抑制は client 側 `dry_multiplier=0.4`
   送信運用で補完（SKILL.md L69 既出）。
2. llama.cpp を #23 で正常だった既知良好コミットへ差し戻して新ビルド回帰を切り分け（案3）。

## 検証基準値（#4 で実証済み）

- URL/長パスの greedy 完全一致（IPv4 オクテット・パス末尾の書換ゼロ）
- Active Storage 長文 5459 tokens が段落反復なく完結
- 起動フラグ `presence-penalty 1.0 / dry-multiplier 0`

## 触るファイル

- `.claude/skills/llama-server/scripts/start.sh`（修正済み、コミットのみ）
- `.claude/skills/llama-server/SKILL.md`（修正済み、コミットのみ）
- 新規レポート `report/2026-05-29_*_qwen36_dry08_redeploy_pathfix.md`(+attachment)
- ※サーバ再起動・検証はスクリプト経由（コード変更なし）

## 既知の残課題（push 見送りに伴う）

- plugin cache v1.0.0 は 2026-05-13 の旧版で本対策を一切含まない。スキルを plugin 経由で起動する
  経路では古い挙動になる潜在的不整合。今回は対象外。
- 恒久的なクロスマシン整合（origin への push と各 checkout の pull、plugin 再発行）は別途要検討。
