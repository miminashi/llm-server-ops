# Qwen3.x sampler 再々調整: 長ハイフン含みパスの再現性回復

## Context

直近 2 回の sampler 調整の経緯:

1. **`fed12136`** — thinking 段落 verbatim ループ抑制のため `--presence-penalty 1.0 --dry-multiplier 0.8` を Qwen3.5/3.6 共通に default 有効化。**副作用**: URL/IP の数字が出力時に書き換わる。
2. **`2026-05-26 02:27`** — `--dry-allowed-length 4` + `--dry-sequence-breaker . / _` を追加。**結果**: URL/IP 再現は 4/4 完全回復、thinking ループ抑制も維持。

新たな観測（今回の出発点）: opencode (別ホスト `aws-mmns-opencode` で動作) の tool-call で **実在する長いハイフン含みパス**を Read tool に正しく渡せない:

```
→ Read ~/projects/ytdlor/.worktree/rail    ← 本来は rails-upgrade-to-8.1.0 (実在)
→ Read ~/projects/ytdlor/.workt            ← 自己訂正でさらに短く
→ Read ~/projects/ytdlor/.work
→ Read ~/projects/ytdlor/report
→ Read ~/projects/ytdlor/.worktree/rai
```

LLM が `rails-upgrade-to-8.1.0` の途中で文字列を打ち切り、tool 失敗 → さらに別の短いパスを試行、というループに陥る。

### 構造的原因（Explore 済み）

現状の Qwen3.x 共通プロファイル:
- `--presence-penalty 1.0`
- `--dry-multiplier 0.8 --dry-allowed-length 4`
- `--dry-sequence-breaker . --dry-sequence-breaker / --dry-sequence-breaker _`

問題点:
1. **`-` が breakers に含まれない** → `rails-upgrade-to-8.1.0` 全体が長 n-gram として DRY のペナルティ対象
2. **`presence-penalty 1.0` の累積効果** (推定寄与 ~70%) — llama.cpp の presence-penalty は「これまでに出現した token 全体」に作用。ユーザープロンプトに登場した長パスの各 constituent token (`rail`, `s`, `-`, `up`, `grade`, ...) が、出力で 2 回目に書こうとすると累積 -1.0 ペナルティ。LLM は「同じパスを書き直すと罰される」と学習し、途中で `"` で文字列を閉じる方向に逃げる。

主目的: **パス再現性回復**。副次: **URL 再現 / thinking ループ抑制を毀損しない**。

## 推奨プラン: presence-penalty 緩和 + `-` breaker 追加

`presence-penalty 1.0 → 0.5` で累積罰を半減し、DRY breakers に `-` を加えてハイフン区切り識別子を n-gram から分離する。`--dry-allowed-length 4` と `--dry-multiplier 0.8` は据え置き（前回戦果の維持）。Qwen3.5/3.6 共通で適用。

### 変更ファイル

#### 1. `.claude/skills/llama-server/scripts/start.sh` 行 196-211

`SAMPLING_OPTS` の Qwen3.x 分岐を以下に変更:

```
SAMPLING_OPTS="--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 \
--presence-penalty 0.5 \
--dry-multiplier 0.8 --dry-allowed-length 4 \
--dry-sequence-breaker . --dry-sequence-breaker / \
--dry-sequence-breaker _ --dry-sequence-breaker=-"
```

コメントブロック (行 197-205) を更新:
- `presence-penalty 1.0 → 0.5` 緩和の根拠（path 構成 token への累積罰の半減、Qwen 公式推奨レンジ 0〜2 の下寄り）
- `--dry-sequence-breaker=-` の `=` 形式採用理由（裸の `-` は getopt が次オプションと誤認するため、long-option の `=value` 結合形式を使う）

#### 2. `.claude/skills/llama-server/SKILL.md`

- Qwen3.x 共通サンプリングプロファイル（行 51-59 付近）を新値に更新
- 既存の「DRY breakers / allowed-length チューニング (2026-05-26 更新)」注記の直後に **新セクション「path 再現性チューニング (2026-05-26 #2)」** を 3-5 行で追記。`presence-penalty` 緩和と `-` breaker 追加の経緯、`=` 形式採用理由を明記。

### 設計判断の根拠

- **`presence-penalty 1.0 → 0.5`**: 主因（累積罰）への直接対策。1.0 は Qwen 推奨レンジ 0〜2 の中庸、0.5 は下寄り。0 まで下げると thinking ループ抑制が dry 単独に依存して再発リスクが上がるため、中庸を残す。
- **`-` breaker 追加**: ハイフン区切り識別子を DRY n-gram から分離。`=` 結合形式を採用する理由は、前回 `'\"'` `'*'` でクオート破綻した経緯と同じく、裸の `-` は getopt 衝突のリスクがあるため。`--dry-sequence-breaker=-` は long-option の標準形式で SSH 三段クオートを安全に通過する想定。
- **`--dry-allowed-length 4` 据え置き**: 前回の URL 戦果の最低条件。
- **`--dry-multiplier 0.8` 据え置き**: thinking 段落 verbatim 抑制の主担当を温存。
- **Qwen3.5/3.6 共通変更**: 副作用構造は両系列で共通。

### 起動可否確認（実装最初に必須）

`--dry-sequence-breaker=-` 形式で実機 llama-server が起動するか、ロック取得後に短時間テストする:

```
ssh t120h-p100 "ps aux | grep '[l]lama-server.*--dry-sequence-breaker=-'"
```
で値が反映されていることを確認。万一起動失敗なら以下のフォールバック順序:

1. `--dry-sequence-breaker=-` (= 結合形式、第一候補)
2. `-` を完全に諦め、`presence-penalty` 緩和のみで様子見（A-1 単体）

## 検証手順

ロック取得 → llama-down → llama-up 後:

1. **起動引数反映確認**:
   ```
   ssh t120h-p100 "ps aux | grep '[l]lama-server -m' | grep -oE 'presence-penalty [^ ]+|dry-allowed-length [^ ]+|dry-sequence-breaker[ =][^ ]+|dry-multiplier [^ ]+'"
   ```
   期待: `presence-penalty 0.5` / `dry-multiplier 0.8` / `dry-allowed-length 4` / 4 つの breaker (`. / _ =-`)。

2. **パス再現テスト (主目的)** — curl で `/v1/chat/completions` に対し thinking 無効モード:
   ```
   {"role":"user","content":"次のパスを3行に分けてそのまま3回繰り返してください: /home/ubuntu/projects/ytdlor/.worktree/rails-upgrade-to-8.1.0/config/environments/production.rb"}
   ```
   期待: 全文字列が改変なしで 3 行とも完全一致。

3. **長 hyphen 識別子テスト**:
   ```
   {"role":"user","content":"次のパスを3行で正確に繰り返して: ~/projects/llm-server-ops/.claude/skills/llama-server/scripts/start.sh"}
   ```

4. **URL 再現リグレッション** (前回 4 ケース再実行):
   - `http://10.1.6.5:8001/health` × 3、thinking 有効/無効両方
   - 期待: 前回同様、IPv4 オクテット書き換えゼロ。

5. **thinking モード下のパス再現** (opencode 実シナリオに近い):
   - thinking 有効でパス再現を依頼し、reasoning_content 内でもパスが切れていないこと。

6. **opencode 実運用 (ユーザー側)**: 元の「ytdlor サムネイル調査依頼」を opencode から再投入し、Read tool に渡すパスが正しく完成すること。

## ロールバック条件

| 検証結果 | アクション |
|---|---|
| パス改善せず + URL/thinking 維持 | `--dry-allowed-length 4 → 6` に緩和（A-5 への昇格）→ 再検証 |
| `--dry-sequence-breaker=-` で起動失敗 | `-` breaker を諦め、`presence-penalty 0.5` のみで様子見 (A-1 単体) |
| パス改善 + thinking ループ再発 (1 セッション 2 回以上) | `presence-penalty 0.5 → 0.7` に戻し、`--dry-multiplier 0.8 → 1.0` に強化 |
| パス改善 + URL リグレッション | `--dry-allowed-length 4 → 3` に戻す（`-` breaker は維持） |
| 全項目改善せず | `fed12136` 直前に戻し、クライアント側 (opencode) で per-request の `presence_penalty=0` 指定経路へ移行 |

## レポート作成

実装完了後、`report/YYYY-MM-DD_HHMMSS_qwen36_sampler_path_recall_fix.md` に下記を記載:
- 問題の再現サンプル（opencode 出力ログ、aws-mmns-opencode ホストでの実在パスを LLM が打ち切る挙動）
- 原因仮説（presence-penalty 累積罰が主因、DRY breakers の `-` 不含が副因）
- 採用パラメータと変更差分
- 検証結果（パス再現テスト、URL 再現リグレッション、thinking ループリグレッション）
- 前回レポート `2026-05-26_022707_qwen36_sampler_url_recall_fix.md` への参照
- `attachment/<basename>/plan.md` にこのプランファイルを同梱
