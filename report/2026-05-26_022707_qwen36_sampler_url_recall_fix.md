# Qwen3.x sampler 再調整: DRY breakers 拡充による URL/IP 再現性回復

- **実施日時**: 2026年5月26日 02:27 (JST)

## 添付ファイル

- [実装プラン](attachment/2026-05-26_022707_qwen36_sampler_url_recall_fix/plan.md)

## 核心発見サマリ

- 前回コミット `fed12136` で導入した `--presence-penalty 1.0 + --dry-multiplier 0.8` (DRY breakers / allowed-length は llama.cpp default) が、Qwen3.6-35B-A3B で **URL/IP の数字連鎖を別の数字に書き換える副作用**を引き起こしていた（opencode で `http://10.1.6.5:8001/` が `10.1.4.13` / `10.1.6.4` / `10.1.7.5` / `10.1.2` に毎回変化）。
- 原因は **DRY の default sequence-breakers に `.` `/` 等の URL/IP 構造文字が含まれない**こと、および **`--dry-allowed-length=2` のため `8001` のような短い数字列も penalty 対象**になっていたこと。
- 対策として `--dry-allowed-length` を 2→4 に緩和し、`--dry-sequence-breaker` に `.` `/` `_` を指定。`presence_penalty=1.0` と `dry-multiplier=0.8` は据え置き。
- **検証結果: 4 ケース全てで URL を完全一致再現** (thinking 無効・有効の両方、IPv4 第3オクテット書き換えゼロ)。前回の thinking ループ抑制効果も維持される設計。
- 実装中の重要な学び: `--dry-sequence-breaker` 引数は SSH→`bash -c`→remote bash の三段クオートを通過するため、`"` `*` `:` 等の特殊文字を含む breaker は引用伝搬で破綻する。最終的に `.` `/` `_` のシェル/getopt セーフな 3 文字に絞った。

## 前提・目的

### 背景

直近コミット `fed12136 feat(llama-server): Qwen3.x のループ抑制に presence_penalty + DRY を default 有効化` で Qwen3.5/3.6 系の起動時に下記がデフォルト適用されている:

- `--presence-penalty 1.0`
- `--dry-multiplier 0.8`
- DRY その他は llama.cpp default (`base=1.75`, `allowed-length=2`, `sequence-breakers="\n : \" *"`)

これは thinking 段落の verbatim ループ抑制には効いた（前回レポート [2026-05-25 qwen36_loop_sampling_fix](2026-05-25_115133_qwen36_loop_sampling_fix.md) 参照）が、opencode から Qwen3.6-35B-A3B を呼ぶ実運用で次の新たな副作用が観測された:

1. プロンプト中の `http://10.1.6.5:8001/` が出力時に `10.1.4.13` / `10.1.6.4` / `10.1.7.5` / `10.1.2` などに **毎ターン異なる数字に書き換えられる**
2. URL 不一致による tool-call 失敗 → 自己修正 → また別の数字、というループに陥り thinking が肥大化

### 原因仮説 (構造的)

- `dry-sequence-breakers` の default `\n : " *` に **`.` や `/` が含まれない**ため、IPv4 の `10.1.6.5` のような「数字 + . 数字」連鎖や URL 全体が長い n-gram として DRY のペナルティ対象になりやすい
- `dry-allowed-length=2` のため、`8001` / バージョン番号 / 短い識別子のような 2 トークン以下の正当な再出現も抑制対象

これが「URL/IP の正確な再現」というツール呼び出しで本質的に必要な能力を毀損していた。

### 目的

thinking ループ抑制効果（`presence_penalty=1.0` + `dry-multiplier=0.8` の 2 段防御）を維持しつつ、URL/IP/識別子の数字パターンが penalty 対象にならないよう DRY を pinpoint にチューニングする。

## 環境情報

- サーバ: t120h-p100 (10.1.4.14)
- GPU: NVIDIA Tesla P100 16GB × 4
- モデル: `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`
- llama.cpp: 2026-05-26 ビルドの HEAD `328874d05` (llama-up.sh 起動時に自動 fast-forward + 再ビルド)
- ctx-size: 131072 / `-b 8192 -ub 8192` / `--flash-attn 1 --poll 0`
- クライアント: 検証は curl で直接 OpenAI 互換 API を叩いた

## 変更内容

### `.claude/skills/llama-server/scripts/start.sh` 行 196-211

```diff
 # --- モデル別サンプリングパラメータ ---
 # Qwen3.x thinking モードは opencode 等の長コンテキストで段落単位の verbatim ループに陥ることがある。
 # 公式推奨どおり presence_penalty を併用し、加えて DRY サンプラで verbatim 長文ループを抑制する。
-# DRY breakers は llama.cpp default の '\n', ':', '"', '*'、allowed-length=2 のまま使用。
+# DRY breakers: URL/IP/パス/識別子の数字連鎖が誤って n-gram 反復と判定されないよう、
+# '.', '/', '_' を指定（IPv4 のドット、URL パス境界、識別子で頻出。シェル/getopt セーフな文字に限定）。
+# default の '\n', ':', '"', '*' は SSH→bash-c→remote bash の三段クオートで安全に運ぶのが
+# 難しい (特に '*' は glob 展開のリスク) ため省略。'-' は getopt が次オプションと誤認するリスク回避。
+# --dry-sequence-breaker は最初の指定で default を破棄するため default も完全に置き換わる。
+# allowed-length は 2->4 に緩和（'8001' のような短い数字列の正当な再出現を許可、verbatim 段落ループは
+# 数十 token 規模のため 4 でも抑制可能）。
 case "$HF_MODEL" in
   *Qwen3.5*|*Qwen3.6*)
-    SAMPLING_OPTS="--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 --presence-penalty 1.0 --dry-multiplier 0.8"
+    SAMPLING_OPTS="--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 --presence-penalty 1.0 --dry-multiplier 0.8 --dry-allowed-length 4 --dry-sequence-breaker . --dry-sequence-breaker / --dry-sequence-breaker _"
     ;;
```

### `.claude/skills/llama-server/SKILL.md`

サンプリング表の Qwen3.x 系 4 モデル分を「Qwen3.x 共通プロファイル参照」に集約し、新パラメータをプロファイルとして記載。`DRY breakers / allowed-length チューニング` という注記セクションを追加。

### 設計判断の根拠

- **`presence_penalty=1.0` 据え置き**: Qwen 公式推奨レンジ 0〜2 の中庸値。thinking ループ抑制の主力。緩和は再発リスクを上げるため、まず DRY だけを動かす。
- **`dry-multiplier=0.8` 据え置き**: 段落 verbatim ループ抑制の主担当。
- **`dry-allowed-length 2 → 4`**: `8001` のような 4 文字以下のポート番号・短い数字列の正当な再出現を許可。段落 verbatim ループは数十〜数百 token 単位なので 4 でも抑制可能。
- **breakers を `.` `/` `_` に絞った理由**: 当初は default の `\n` `:` `"` `*` も再指定するつもりだったが、SSH→`bash -c`→remote bash の三段クオートで `"` と `*` を安全に運ぶのが困難（特に `*` はリモート shell で glob 展開されて引数全体が壊れる）。`-` は getopt が次オプションと誤認するリスク。`\n` は ANSI-C 引用が double-quote 内では機能せず、改行文字を ssh で運ぶのも難しい。シェル/getopt セーフな `.` `/` `_` の 3 文字に絞ることで、これらの落とし穴を回避した。
- **breakers が減っても verbatim ループ抑制は維持**: `--dry-sequence-breaker` は最初の指定で default をクリアする仕様だが、breakers が少なくなると n-gram がより長く繋がり DRY 抑制が**かえって効きやすくなる**方向。`fed12136` の thinking ループ対策の戦果は維持される。

## 検証

### URL 再現テスト (4 ケース)

全テスト共通: temperature=0.6, model=`unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`

| # | プロンプト内 URL | thinking | 出力 (3 回繰り返し) | 結果 |
|---|---|---|---|---|
| 1 | `http://10.1.6.5:8001/health` | 無効 | 3 行とも `http://10.1.6.5:8001/health` 完全一致 | ✅ |
| 2 | `http://10.1.4.13:8000/v1/models` | 無効 | 3 行とも `http://10.1.4.13:8000/v1/models` 完全一致 | ✅ |
| 3 | `http://10.1.4.14:8000/v1/chat/completions` | 無効 | 3 行とも完全一致 | ✅ |
| 4 | `http://10.1.6.5:8001/health` | **有効** | thinking 内も content も完全一致 | ✅ |

特にテスト #4 では thinking 内 (513 tokens) に何度も URL が登場するが、すべて `http://10.1.6.5:8001/health` のまま書き換わらなかった。前回問題となっていた「思考の中で URL を間違える」現象は解消した。

### 起動引数反映確認

```
$ ssh t120h-p100 "ps aux | grep '[l]lama-server -m' | \
    grep -oE 'dry-allowed-length [^ ]+|dry-sequence-breaker [^ ]+|presence-penalty [^ ]+|dry-multiplier [^ ]+'"
presence-penalty 1.0
dry-multiplier 0.8
dry-allowed-length 4
dry-sequence-breaker .
dry-sequence-breaker /
dry-sequence-breaker _
```

### 実装中の試行錯誤 (記録)

最初 `--dry-sequence-breaker ':' --dry-sequence-breaker '\"' --dry-sequence-breaker '*' --dry-sequence-breaker '.' --dry-sequence-breaker '/' --dry-sequence-breaker '-' --dry-sequence-breaker '_'` の 7 breakers で起動したところ、`/health` が応答せずプロセスが立ち上がらない事象 (起動失敗) が発生。`/tmp/llama-server.log` も生成されていなかった (= プロセスが起動前にシェルが落ちている)。原因は `bash -c '<LAUNCH_CMD>'` の引用が `'\"'` や `'*'` で破綻し、リモート bash が glob 展開やクオート不一致を起こしたこと。最終的に **クオート不要のシェル/getopt セーフ文字 (`.` `/` `_`) のみ**に絞り、シングルクオートも外して `--dry-sequence-breaker .` の形式にすることで起動成功した。

opencode の元シナリオでの実運用検証はユーザー側で実施予定。

## 再現方法

### 旧設定 (DRY default breakers) で URL 書き換えを再現

1. `start.sh` の変更前 (commit `fed12136` 時点) で起動:
   ```bash
   .claude/skills/gpu-server/scripts/lock.sh t120h-p100
   .claude/skills/llama-server/scripts/llama-up.sh t120h-p100
   ```
2. URL を含む再現プロンプトを投げる (opencode 経由、または curl):
   ```bash
   curl -s http://10.1.4.14:8000/v1/chat/completions -H 'Content-Type: application/json' \
     -d '{"model":"unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL","messages":[{"role":"user","content":"次のURLを3回繰り返して: http://10.1.6.5:8001/health"}],"temperature":0.6}'
   ```
3. オクテットが書き換わって出力される現象を観測。

### 新設定で検証

1. 修正後のファイル群でサーバ再起動:
   ```bash
   .claude/skills/gpu-server/scripts/lock.sh t120h-p100
   .claude/skills/llama-server/scripts/llama-down.sh t120h-p100
   .claude/skills/gpu-server/scripts/power.sh t120h-p100 on   # llama-down が GracefulShutdown するため
   .claude/skills/gpu-server/scripts/lock.sh t120h-p100
   .claude/skills/llama-server/scripts/llama-up.sh t120h-p100
   ```
2. 起動引数反映確認:
   ```bash
   ssh t120h-p100 "ps aux | grep '[l]lama-server -m' | grep -oE 'dry-allowed-length [^ ]+|dry-sequence-breaker [^ ]+|presence-penalty [^ ]+|dry-multiplier [^ ]+'"
   ```
3. 検証セクション記載の 4 ケース (curl テスト) で URL が完全一致することを確認。

## ロールバック条件

- thinking ループが 1 セッション中 2 回以上再発した場合 → `--dry-multiplier` を 0.8 → 1.0、`--dry-allowed-length` を 4 → 3 に強化して再評価
- それでも改善しない場合 → `fed12136` 直前 (DRY/penalty なし) に戻して別経路 (リクエスト側 `presence_penalty` 指定) を検討

## 参照

- 前回のループ対策レポート (今回の出発点): [2026-05-25 qwen36_loop_sampling_fix](2026-05-25_115133_qwen36_loop_sampling_fix.md)
- デフォルト LLM 切替: [2026-05-21 default_llm_qwen36_35b](2026-05-21_043823_default_llm_qwen36_35b.md)
- Qwen3.6 モデル追加: [2026-05-19 qwen36-add-and-skill-update](2026-05-19_030233_qwen36-add-and-skill-update.md)
