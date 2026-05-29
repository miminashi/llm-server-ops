# Qwen3.x sampler 再々調整: DRY 完全無効化による長パス再現性回復

- **実施日時**: 2026年5月26日 14:38 (JST)

## 添付ファイル

- [実装プラン](attachment/2026-05-26_143817_qwen36_sampler_path_recall_fix/plan.md)

## 核心発見サマリ

- 直前 (2026-05-26 #1, #2) のサンプラ調整で URL/IP 数字書換は解消したが、opencode の tool-call で **`/home/ubuntu/projects/ytdlor/.worktree/rails-upgrade-to-8.1.0/...` のような長パスが途中で切れる/書き換わる**問題が残った。原因は **DRY サンプラが長 token 列の末尾を切り落とす**こと。greedy decoding (`temperature=0, top_k=1`) でも症状が再現したため、サンプラの確率的乱れではなく DRY 固有の挙動と確定。
- リクエスト側で `dry_multiplier=0` を送ると **3 行とも完全一致再現**できた → DRY 完全無効化が確実な対策。
- 重大な副次発見: llama.cpp の最新版で **`--dry-sequence-breaker` を複数回指定すると最後の値のみが有効** (deprecation 警告)。前回 2026-05-26 #1 修正での `. / _` 3 回指定は実質 `_` だけが効いていた。複数 breaker はカンマ区切り 1 引数 (`--dry-sequence-breaker .,/,_,-`) で渡す必要がある。
- 採用方針: **DRY サンプラをサーバ default で完全無効化** (`--dry-multiplier 0`)、thinking 段落 verbatim ループ抑制は `presence_penalty 0.5` 単独で対応。verbatim ループが実運用で再発したらクライアント側で `dry_multiplier` を送る運用に切替。

## 前提・目的

### 背景

直前のチューニング履歴:

1. **`fed12136`** (2026-05-25): thinking 段落 verbatim ループ抑制のため `--presence-penalty 1.0 --dry-multiplier 0.8` を Qwen3.5/3.6 共通に default 有効化 → URL/IP の数字書換副作用。
2. **2026-05-26 #1** ([前回レポート](2026-05-26_022707_qwen36_sampler_url_recall_fix.md)): `--dry-allowed-length 4` + `--dry-sequence-breaker . / _` 追加 → URL/IP 再現性回復確認 (4/4 完全一致)。
3. **今回 (#3、本レポート)**: 新たに「長ハイフン含みパスが tool-call で途中切断される」問題に対応。

### 観測された問題

opencode 経由で Qwen3.6-35B-A3B に `~/projects/ytdlor/.worktree/rails-upgrade-to-8.1.0` 等のパスを含む依頼を投げると、Read tool に渡す引数が途中で切れていた:

```
Read ~/projects/ytdlor/.worktree/rail    ← 実在パスは ...rails-upgrade-to-8.1.0
File not found → 自己訂正でさらに短く
Read ~/projects/ytdlor/.workt
Read ~/projects/ytdlor/.work
```

### 当初仮説と検証経過

**仮説 (Plan 段階)**: `-` が DRY breaker に含まれず長ハイフン識別子が長い n-gram として DRY 対象、加えて `presence-penalty 1.0` の累積効果で「同じパスを 2 回目以降書くと罰される」と LLM が学習。

**対策 #2 (実装)**: `presence-penalty 1.0 → 0.5` 緩和 + 4 breakers をカンマ区切り `.,/,_,-` で集約。

**検証で発覚した深刻な追加問題**:

`temperature=0.6, presence_penalty=0.5, DRY (0.8/4/.,/,_,-)` でテストすると依然パスが乱れた:
```
/home/ubuntu/projects/ytdlor/.worktree/rrails-upgrade-to-8.1.0/confg/environments/production.rb
/home/ubuntu/projects/ytdlor/.worktrree/rails-upgrade-to-8.0/config/environments/production.rb
/home/ubuntu/projects/ytdlor/.wotree/rails-upgrade-to-81.0/config/enviroments/production.rb
```

リクエスト側 `presence_penalty=0, frequency_penalty=0` 上書き、さらに `temperature=0, top_k=1` (greedy) でも末尾が切れる症状が継続:
```
/home/ubuntu/projects/ytdlor/.worktree/rails-upgrade-to-8.1
.0/config/environments/production.rb     ← 改行が変な位置
/home/ubuntu/projects/ytdlor/.work
tree/rails-upgrade-to-                    ← 末尾切れ
8.1.0/config/environments
```

**決定的検証**: リクエスト側で `dry_multiplier=0` を送ると 3 行とも完全一致:
```
/home/ubuntu/projects/ytdlor/.worktree/rails-upgrade-to-8.1.0/config/environments/production.rb
/home/ubuntu/projects/ytdlor/.worktree/rails-upgrade-to-8.1.0/config/environments/production.rb
/home/ubuntu/projects/ytdlor/.worktree/rails-upgrade-to-8.1.0/config/environments/production.rb
```

→ **DRY が長パスの末尾を切り落とす真犯人**と確定。

### 副次発見: `--dry-sequence-breaker` の複数回指定が deprecated

サーバ起動ログで以下の警告が出た:
```
DEPRECATED: argument '--dry-sequence-breaker' specified multiple times, use comma-separated values instead (only last value will be used)
```

つまり、前回 #1 修正の `--dry-sequence-breaker . --dry-sequence-breaker / --dry-sequence-breaker _` は **`_` だけが効いていた**。それでも URL 再現が改善したのは `_` 単独の効果か、`--dry-allowed-length 4` の効果と推測される。今回 `--dry-sequence-breaker .,/,_,-` のカンマ区切り 1 引数形式に書き換えた（が、最終案では DRY 自体を無効化したので不要に）。

また、`--dry-sequence-breaker=-` の `=` 結合形式は **invalid argument エラーで起動失敗**することも判明。

## 環境情報

- サーバ: t120h-p100 (10.1.4.14)
- GPU: NVIDIA Tesla P100 16GB × 4
- モデル: `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`
- llama.cpp: 2026-05-26 ビルドの HEAD `328874d05`
- ctx-size: 131072 / `-b 8192 -ub 8192` / `--flash-attn 1 --poll 0`
- クライアント: 検証は curl で直接 OpenAI 互換 API を叩いた

## 変更内容

### `.claude/skills/llama-server/scripts/start.sh` 行 196-213

```diff
 # --- モデル別サンプリングパラメータ ---
 # Qwen3.x thinking モードは opencode 等の長コンテキストで段落単位の verbatim ループに陥ることがある。
-# 公式推奨どおり presence_penalty を併用し、加えて DRY サンプラで verbatim 長文ループを抑制する。
-# DRY breakers は llama.cpp default の '\n', ':', '"', '*'、allowed-length=2 のまま使用。
+# Qwen 公式推奨の presence_penalty (0〜2 のうち下寄りの 0.5) のみで対処する。
+# 履歴 (2026-05-26 #3): DRY サンプラは long path / 識別子の末尾を切り落とす副作用が greedy decoding でも
+# 観測されたため、サーバ default では完全無効化 (--dry-multiplier 0、llama.cpp default 値と同じ)。
+# (経緯コメント省略、ファイル参照)
 case "$HF_MODEL" in
   *Qwen3.5*|*Qwen3.6*)
-    SAMPLING_OPTS="--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 --presence-penalty 1.0 --dry-multiplier 0.8"
+    SAMPLING_OPTS="--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 --presence-penalty 0.5 --dry-multiplier 0"
     ;;
```

### `.claude/skills/llama-server/SKILL.md`

- Qwen3.x 共通サンプリングプロファイル更新 (`--dry-multiplier 0`、DRY 関連他オプション削除)
- 「チューニング履歴」セクションに `fed12136` → 2026-05-26 #1 → #2 → #3 の経緯を集約。`--dry-sequence-breaker` の複数回指定が deprecated である事実を明記。

## 検証結果

### 起動引数反映確認

```
$ ssh t120h-p100 "ps aux | grep '[l]lama-server -m' | \
    grep -oE 'presence-penalty [^ ]+|dry-multiplier [^ ]+'"
presence-penalty 0.5
dry-multiplier 0
```

起動ログでも `--dry-sequence-breaker` の deprecation 警告は消失（`--defrag-thold` の deprecation だけが残るが既存）。

### パス再現テスト (主目的)

`temperature=0.6, default sampler (presence-penalty 0.5, dry-multiplier 0)`、thinking 無効モード:

```
入力: /home/ubuntu/projects/ytdlor/.worktree/rails-upgrade-to-8.1.0/config/environments/production.rb
出力 3 行:
/home/ubuntu/projects/ytdlor/.worktree/rails-upgrade-to-8.1.0/config/environments/production.rb
/home/ubuntu/projects/ytdlor/.worktree/rails-upgrade-to-8.1.0/config/environments/production.rb
/home/ubuntu/projects/ytdlor/.worktree/rails-upgrade-to-8.1.0/config/environments/production.rb
```
✅ 全完全一致

### URL リグレッション (前回戦果の維持確認)

`http://10.1.6.5:8001/health` × 3、thinking 無効:
```
http://10.1.6.5:8001/health
http://10.1.6.5:8001/health
http://10.1.6.5:8001/health
```
✅ 全完全一致、IPv4 オクテット書き換えゼロ

### thinking 有効モードでのパス再現

`temperature=0.6, max_tokens=8192, thinking 有効`:
- reasoning_content (1643 chars) 内でも対象パスが正確に書かれている
- content 3 行とも完全一致
- completion_tokens=532（前回 thinking テスト 513 と同程度、肥大化なし）

## 再現方法

### サーバ起動確認

```bash
.claude/skills/gpu-server/scripts/lock.sh t120h-p100
.claude/skills/llama-server/scripts/llama-up.sh t120h-p100
ssh t120h-p100 "ps aux | grep '[l]lama-server -m' | grep -oE 'presence-penalty [^ ]+|dry-multiplier [^ ]+'"
# 期待: presence-penalty 0.5 / dry-multiplier 0
```

### パス再現テスト

```bash
curl -s http://10.1.4.14:8000/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL",
  "messages": [{"role":"user","content":"次のパスを3行で正確に繰り返してください: /home/ubuntu/projects/ytdlor/.worktree/rails-upgrade-to-8.1.0/config/environments/production.rb"}],
  "temperature": 0.6, "max_tokens": 1024,
  "chat_template_kwargs": {"enable_thinking": false}
}'
```

### thinking ループ再発確認 (要ユーザー検証)

opencode から長文 thinking + tool-use を伴う実シナリオ (前々回レポート `2026-05-25_115133_qwen36_loop_sampling_fix.md` の ActiveStorage 404 デバッグ等) を投入。thinking 段落の verbatim 反復が出ないこと、または出ても許容範囲（1 セッションあたり 1 回以下）であることを確認。

## ロールバック条件

| 状況 | アクション |
|---|---|
| thinking ループが 1 セッション中 2 回以上再発 | `presence-penalty 0.5 → 1.0` に戻す（中庸値）。それでも不足なら、クライアント (opencode) 側で `dry_multiplier: 0.4` をデフォルトで送る設定にする |
| パスは再現できるが thinking ループが頻発 | クライアント側ハイブリッド方針へ移行: tool-call 要求文 (`Read`, `Bash` 等を投げる時) は `dry_multiplier=0`、通常会話は `dry_multiplier=0.8` を送り分ける |
| 何らかの理由で `presence-penalty` まで悪さする場合 | `--presence-penalty 0` まで下げる（`fed12136` 完全に元に戻す経路） |

## 補足: クライアント側オーバーライド

llama.cpp の OpenAI 互換 API は `dry_multiplier`、`dry_base`、`dry_allowed_length`、`dry_sequence_breakers` をリクエスト側で受け取り、起動時設定を上書きできる（OpenAI 互換 API 拡張）。`presence_penalty` と `frequency_penalty` は標準仕様の範囲。これにより、サーバ default はニュートラルにしつつ、クライアント側で用途別にチューニング可能。

## 参照

- 前々回 (元凶): [2026-05-25 qwen36_loop_sampling_fix](2026-05-25_115133_qwen36_loop_sampling_fix.md) — fed12136 で `presence_penalty=1.0 + DRY=0.8` を default 有効化したレポート
- 前回 (URL 修正): [2026-05-26 qwen36_sampler_url_recall_fix](2026-05-26_022707_qwen36_sampler_url_recall_fix.md) — `--dry-allowed-length 4 + breakers` を追加、URL/IP 再現性を回復したレポート（ただし複数回指定 deprecated に気付かず）
- デフォルト LLM 切替: [2026-05-21 default_llm_qwen36_35b](2026-05-21_043823_default_llm_qwen36_35b.md)
