# Qwen3.x sampler 再調整: DRY breakers 拡充による URL/IP 再現性回復

## Context

直近コミット `fed12136 feat(llama-server): Qwen3.x のループ抑制に presence_penalty + DRY を default 有効化` で Qwen3.5/3.6 共通に `--presence-penalty 1.0 --dry-multiplier 0.8`（DRY 他オプションは llama.cpp default: `allowed-length=2`, `sequence-breakers="\n : \" *"`）を組み込んだ。これは thinking 段落の verbatim ループ抑制には効いたが、opencode から Qwen3.6-35B-A3B を呼ぶ実運用で次の副作用が観測された:

- 入力プロンプト中の `http://10.1.6.5:8001/` を、出力時に `10.1.4.13` / `10.1.6.4` / `10.1.7.5` / `10.1.2` などへ毎ターン書き換える
- ツール呼び出し → URL 不一致による失敗 → 自己修正 → また別の数字、というループに陥り thinking が肥大化

構造的な原因:

1. `dry-sequence-breakers` のデフォルト `\n : " *` に **`.` `/` `-` `_` が含まれない**ため、IPv4 の `10.1.6.5` のような「数字 + . 」連鎖や URL 全体が長い n-gram として DRY のペナルティ対象になりやすい
2. `dry-allowed-length=2` のため、`8001` / バージョン番号 / 短い識別子のような 2 トークン以下の正当な再出現も抑制されうる

これが「**URL/IP の正確な再現**」というツール呼び出しで本質的に必要な能力を毀損している。

目的: thinking ループ抑制効果（`presence_penalty=1.0` + `dry-multiplier=0.8` の 2 段防御）を維持しつつ、URL/IP/識別子の繰り返し数字パターンが penalty 対象にならないよう DRY を pinpoint にチューニングする。

## 推奨プラン: DRY breakers 拡充 + allowed-length 緩和（penalty 強度は据え置き）

`presence_penalty=1.0` と `dry-multiplier=0.8` は前回の戦果を活かして据え置き、DRY の「**どこで n-gram を分断するか**」と「**何 token 以上の繰り返しを抑制対象とするか**」だけを変更する最小侵襲案。Qwen3.5/3.6 共通で適用（副作用構造は両系列で共通のため）。

### 変更ファイル

#### 1. `.claude/skills/llama-server/scripts/start.sh` 行 196-207

`SAMPLING_OPTS` の Qwen3.5/3.6 分岐に `--dry-allowed-length 4` と `--dry-sequence-breakers` を追加。breakers には既存の default 文字 (`\n`, `:`, `"`, `*`) に加え、URL/IP/パス/識別子で典型的に登場する `.` `/` `-` `_` を含める。コメントも合わせて更新（「DRY breakers は default のまま使用」→「URL/IP の数字連鎖を保護するため `.` `/` `-` `_` を追加、allowed-length も 2→4 に緩和」）。

llama.cpp の `--dry-sequence-breakers` は **JSON 配列形式の文字列** を期待する（例: `'["\n", ":", "\"", "*", ".", "/", "-", "_"]'`）。実装時に `./build/bin/llama-server --help | grep -A 3 dry-sequence-breakers` で正確な引数形式を確認してから適用すること。

変更後の該当行の論理イメージ（最終的なクオート形式は実装時に確認）:

```
SAMPLING_OPTS="--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 \
  --presence-penalty 1.0 \
  --dry-multiplier 0.8 \
  --dry-allowed-length 4 \
  --dry-sequence-breakers '[\"\\n\",\":\",\"\\\"\",\"*\",\".\",\"/\",\"-\",\"_\"]'"
```

#### 2. `.claude/skills/llama-server/SKILL.md` サンプリング表（行 44, 47, 48, 49）

4 モデル分のサンプリングオプション欄を新値に揃え、表の直後に「DRY breakers / allowed-length の調整理由」を 2〜3 行で追記（URL/IP の数字連鎖を保護するための pinpoint チューニング）。

### 設計判断の根拠

- **`presence_penalty=1.0` 据え置き**: Qwen 公式推奨レンジ 0〜2 の中庸値。thinking ループ抑制の主力。緩和は再発リスクを上げるため、まず DRY だけを動かす。
- **`dry-multiplier=0.8` 据え置き**: 段落 verbatim ループ抑制の主担当。値を落とすと再発リスク。
- **`dry-allowed-length 2 → 4`**: `8001` のような 4 文字以下のポート番号・短い数字列の正当な再出現を許可。段落 verbatim ループは数十〜数百 token 単位なので 4 でも余裕で抑制可能。
- **breakers 拡充**: `.` `/` `-` `_` は IP/URL/パス/識別子の構造境界で頻出し、これらで n-gram を切ることで「数字.数字.数字」型の連鎖を DRY から除外できる。コードトークンに対しては既存の `\n : " *` が引き続き機能。
- **Qwen3.5/3.6 共通変更**: 副作用構造は共通で、3.5 でも同じ問題が顕在化していないだけの可能性が高い。case 分岐を増やさない方が保守性が高い。

### 代替案（採用せず）

- **DRY 完全無効化**: `fed12136` の戦果を捨てる過剰反応。
- **複合（presence_penalty も 0.5 に緩和）**: thinking ループ再発リスクと引き換えになる。今回はまず pinpoint で効果を見て、ループが残るようなら次段で検討。
- **opencode 側でリクエスト時に `presence_penalty=0` を送る運用**: クライアントごとに分散する運用負荷が高い。サーバ default を直すのが先。

## 検証手順

1. 変更後、`.claude/skills/llama-server/scripts/llama-server --help` 相当（または `./build/bin/llama-server --help`）で `--dry-sequence-breakers` の引数形式を確認し、上記コマンドのクオート方法を最終調整する
2. GPU サーバ排他制御:
   ```
   .claude/skills/gpu-server/scripts/lock.sh t120h-p100
   .claude/skills/llama-server/scripts/llama-down.sh t120h-p100
   .claude/skills/llama-server/scripts/llama-up.sh t120h-p100
   ```
3. 起動引数反映確認:
   ```
   ssh t120h-p100 "ps aux | grep llama-server | grep -v grep | grep -oE 'dry-allowed-length [^ ]+|dry-sequence-breakers [^ ]+|presence-penalty [^ ]+|dry-multiplier [^ ]+'"
   ```
   期待: `presence-penalty 1.0` / `dry-multiplier 0.8` / `dry-allowed-length 4` / `dry-sequence-breakers '[...]'` の 4 行
4. **URL 再現テスト（直接 API）**:
   ```
   curl -s http://t120h-p100:8000/v1/chat/completions -H 'Content-Type: application/json' \
     -d '{"model":"unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL","messages":[{"role":"user","content":"次のURLを正確にそのまま3回繰り返してください: http://10.1.6.5:8001/health"}],"temperature":0.6}'
   ```
   評価: 3 回とも `10.1.6.5:8001` が完全一致（オクテット書き換えゼロ）。プロンプトを `http://10.1.4.13:8000/` `http://10.1.4.14:8000/` の 2 つに変えて同様確認。
5. **ループ再発テスト**: 前回レポート `report/2026-05-25_115133_qwen36_loop_sampling_fix.md` の元シナリオ（ActiveStorage signature 404 デバッグ相当の長 thinking + tool-use）を opencode から投げ、thinking 内で同一段落の verbatim 連続出力が発生しないことを確認。
6. **opencode 実運用**: 今回問題が出た「URL を取得してください」系のプロンプトを再投入し、`10.1.6.5:8001` が書き換わらず、自己修正ループが起きないことを確認。

## ロールバック条件

- 検証 5 で thinking ループが 1 セッション中 2 回以上再発 → `dry-multiplier` を 0.8 → 1.0、`dry-allowed-length` を 4 → 3 に強化して再評価
- 検証 4 で URL 再現が依然失敗 → 複合案（`presence-penalty` を 1.0 → 0.5）に進む
- どちらも改善せず → `fed12136` 直前（DRY/penalty なし）に戻して別経路を検討

## レポート作成

実装完了後、`report/YYYY-MM-DD_HHMMSS_qwen36_sampler_url_recall_fix.md` に下記を記載:
- 問題の再現サンプル（opencode 出力ログ）
- 原因仮説（DRY breakers / allowed-length）
- 採用パラメータと変更差分
- 検証結果（URL 再現テスト 3 ケース、ループ再発テスト、opencode 実運用）
- 前回レポート（`2026-05-25_115133_qwen36_loop_sampling_fix.md`）への参照
