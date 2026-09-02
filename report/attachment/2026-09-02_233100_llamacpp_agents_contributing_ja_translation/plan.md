# llama.cpp AGENTS.md / CONTRIBUTING.md 日本語訳版の作成

## Context

llama.cpp プロジェクトは AGENTS.md / CONTRIBUTING.md 内で「AI にプルリクエスト説明・コミットメッセージ・レビュアーへの返信を書かせること」を明示的に禁止しており、違反時は PR 即クローズ・アカウント BAN のペナルティを課している (memory `feedback_llamacpp_no_ai_posts.md` に既記録)。

このため、ユーザ (miminashi) が llama.cpp に投稿する際は、Claude に代筆させず本人が全文を書く必要がある。**その前提として、AGENTS.md と CONTRIBUTING.md の内容をユーザ自身が深く理解しておく必要があり、逐語訳の日本語版があると精読・参照時に便利**、というのが本作業の動機。

今回はローカルの llm-server-ops リポジトリ内に翻訳版を置くだけで、llama.cpp 上流にはコミットしない (そもそも AGENTS.md はそれ自体が投稿禁止の対象なので、翻訳を上流に PR しようとする話ではない)。

## 対象ファイル

原文 (`src/llama.cpp/` は llm-server-ops の `.gitignore` で追跡対象外の参照用ツリー):

- `src/llama.cpp/AGENTS.md` (231 行、10.7 KB)
- `src/llama.cpp/CONTRIBUTING.md` (207 行、12.4 KB)

翻訳先 (新規作成):

- `docs/llama.cpp/AGENTS.ja.md`
- `docs/llama.cpp/CONTRIBUTING.ja.md`

`docs/` ディレクトリは既存にはないので新設する。`docs/llama.cpp/` というサブディレクトリを切ることで、将来 llama.cpp 以外の翻訳が増えた場合でも整理しやすい。

## 翻訳方針

### 全体方針

- **忠実な逐語訳**。段落・箇条書き・強調・引用ブロック・コードブロックの構造をすべて原文どおり維持する
- 各ファイルの冒頭に「これは私 (miminashi) が私的に日本語訳したもので、原文の権威版ではない。齟齬がある場合は原文が正 (訳文は commit ハッシュ `d59c18c5` 時点のスナップショット)」旨と原文 URL を明記する
- コードブロック内の**コード自体は英語のまま**残し、**コメント (`// ...`) だけ日本語訳**を併記する (原文コメント → 日本語コメント の順で残すか、日本語のみに置き換えるかは下記参照)
- `// GOOD` `// BAD` `// BEST` ラベルは原文のまま維持 (視覚的識別子として機能するため)
- `Assisted-by:` `Co-authored-by:` などのコミットトレイラーは訳さない (トレイラーは機械的に処理される識別子)

### 訳語対応表 (統一)

| 原文 | 訳語 | 備考 |
|---|---|---|
| Contributor | コントリビューター | カタカナ |
| Collaborator (Triage) | コラボレーター (Triage) | Triage は括弧内でそのまま |
| Maintainer | メンテナ | 「メンテナー」ではなく「メンテナ」で統一 |
| Pull Request / PR | プルリクエスト / PR | 初出は「プルリクエスト (PR)」、以降は PR |
| AI Coding Agent | AI コーディングエージェント | |
| Code Owner / CODEOWNERS | コードオーナー / `CODEOWNERS` ファイル | ファイル名はコード表記 |
| private fork | プライベートフォーク | |
| squash-merge | squash マージ | git 用語は原則英語 |
| rebase | rebase | 同上 |
| ggml / GGUF / KV cache / perplexity / quantization | 英語のまま | 技術用語 |
| ban | BAN | カタカナではなく大文字英語 (memory の慣習に合わせる) |
| disclose (AI 使用の) | 開示する | |
| roadmap | ロードマップ | |
| in-scope | スコープ内 | |

### 書式ルール

- `> [!IMPORTANT]` `> [!NOTE]` などの GitHub Admonition は**原文の書式をそのまま維持**する (GitHub と多くの MD ビューアで解釈される)
- 見出しレベル (`#` `##` `###`) は完全一致
- 水平線 `---` はそのまま
- コードブロック内のコメント翻訳: 原文コメントは削除し**日本語コメントに置換**する (両言語併記だとブロックが冗長化するため)。ただしラベル `// GOOD` `// BAD` `// BEST` は原文維持
- 例:
  ```cpp
  // 元:  // GOOD (code is self-explanatory, no comment needed)
  // 訳: // GOOD (コードが自明なのでコメント不要)
  ```

### リンク変換ルール

`src/llama.cpp/` は追跡対象外で相対リンクが解決できないため、**すべての相対リンクを llama.cpp 上流の絶対 URL に書き換える**:

- `CONTRIBUTING.md` → `https://github.com/ggml-org/llama.cpp/blob/master/CONTRIBUTING.md`
- `AGENTS.md` → `https://github.com/ggml-org/llama.cpp/blob/master/AGENTS.md`
- `docs/build.md` などの docs 配下 → `https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md`
- `.github/pull_request_template.md` → `https://github.com/ggml-org/llama.cpp/blob/master/.github/pull_request_template.md`
- `CODEOWNERS` → `https://github.com/ggml-org/llama.cpp/blob/master/CODEOWNERS`
- `tools/server/README.md` → `https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md`
- `common/jinja/README.md` → `https://github.com/ggml-org/llama.cpp/blob/master/common/jinja/README.md`
- `ci/README.md` → `https://github.com/ggml-org/llama.cpp/blob/master/ci/README.md`
- `skills/` (AGENTS.md 内) → `https://github.com/ggml-org/llama.cpp/tree/master/skills/`
- `media/matmul.png` (画像) → `https://github.com/ggml-org/llama.cpp/raw/master/media/matmul.png`

既に絶対 URL のリンク (例: `https://github.com/ggml-org/llama.cpp/issues`, `https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines`) はそのまま維持する。

翻訳版の**相互リンク**は同じ翻訳ディレクトリ内の相対パスを使う:

- AGENTS.ja.md 内の CONTRIBUTING.md 参照 → 「[CONTRIBUTING.ja.md](CONTRIBUTING.ja.md) (原文: `https://github.com/ggml-org/llama.cpp/blob/master/CONTRIBUTING.md`)」の形で両方示す
- CONTRIBUTING.ja.md 内の AGENTS.md 参照 → 同様に両方示す

これで、翻訳版内を巡回することも原文へ飛ぶこともできる。

## 実装ステップ

1. `docs/llama.cpp/` ディレクトリを作成 (Write ツールで新規ファイルを書くと親ディレクトリは自動作成される想定)
2. `docs/llama.cpp/AGENTS.ja.md` を作成:
   - 冒頭に注釈ブロック (これは私的な日本語訳である旨、原文 URL、翻訳時点 = master @ `d59c18c5` のスナップショット)
   - 231 行の全訳
3. `docs/llama.cpp/CONTRIBUTING.ja.md` を作成:
   - 同様の冒頭注釈
   - 207 行の全訳
4. 品質確認:
   - 翻訳ファイルを Read して見出し数・箇条書き数・コードブロック数が原文と一致することを確認
   - リンク書き換えの漏れがないか grep で確認 (`grep -nE '\]\(([A-Za-z]|\.\.?/)' docs/llama.cpp/*.ja.md` で相対リンクが残っていないか検査)
   - Admonition ブロック (`> [!IMPORTANT]` 等) が保持されているか確認
5. レポート作成 (CLAUDE.md 制約により必須):
   - `report/YYYY-MM-DD_HHMMSS_llamacpp_agents_contributing_ja_translation.md`
   - 動機 (llama.cpp の AI 投稿禁止ポリシーと理解の必要性)、翻訳範囲、判断メモ (訳語選択の理由、リンク方針)、原文コミット (`d59c18c5`) の記録
   - `report/attachment/` は今回不要 (添付ログなし)
   - `report/INDEX.md` に 1 行追加

## 変更ファイル一覧

- `docs/llama.cpp/AGENTS.ja.md` (新規)
- `docs/llama.cpp/CONTRIBUTING.ja.md` (新規)
- `report/YYYY-MM-DD_HHMMSS_llamacpp_agents_contributing_ja_translation.md` (新規)
- `report/INDEX.md` (1 行追加)

`src/llama.cpp/` 配下や既存の翻訳対象外ファイルには手を触れない。既に status に出ている `report/INDEX.md` の M と `report/2026-09-02_160322_*` は別作業の未コミット分なので、今回のコミットには含めない (別途ユーザ判断)。

## 検証

- **原文と翻訳版の構造比較**:
  ```bash
  diff <(grep -cE '^#{1,6} ' src/llama.cpp/AGENTS.md) \
       <(grep -cE '^#{1,6} ' docs/llama.cpp/AGENTS.ja.md)
  # 見出し数が一致することを確認 (差異は冒頭に追加した注釈ブロックの分のみ許容)

  diff <(grep -cE '^```' src/llama.cpp/AGENTS.md) \
       <(grep -cE '^```' docs/llama.cpp/AGENTS.ja.md)
  # コードフェンス数が一致することを確認
  ```
  CONTRIBUTING についても同様に実施。

- **リンク書き換え漏れの検査**:
  ```bash
  grep -nE '\]\(([^h)][^)]*\.md|[^h)][^)]*\.png|CODEOWNERS)\)' docs/llama.cpp/*.ja.md
  # 出力があれば相対リンクが残っている
  ```
  (相互参照リンク `CONTRIBUTING.ja.md` / `AGENTS.ja.md` は除外して確認)

- **ユーザへの提示**: 翻訳完了後、両ファイルを SendUserFile でユーザの他端末にも送れるようにする (ユーザが精読するのが本タスクの目的のため)

- **エージェント視点のレビュー (任意)**: 訳文が (a) 原文の意図から乖離していないか、(b) 訳語が統一されているか、を Explore or 別の Claude セッションで確認してもよい。ただしユーザ自身が精読することが本来の目的なので、必須ではない
