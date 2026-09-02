# llama.cpp コントリビューション文書の日本語訳を追加

- **実施日時**: 2026年9月2日 23:10 〜 23:40 JST (原文精読・翻訳方針決定・全訳・品質確認・レポート作成)
- **報告日時**: 2026年9月2日 23:40 JST
- **作成者**: Claude Opus 4.7 (1M context)

## 概要

llama.cpp プロジェクトが定めるコントリビューションルールを、ユーザ (miminashi) が精読するための日本語訳版を用意した。llama.cpp は AGENTS.md と CONTRIBUTING.md の中で、プルリクエスト説明・コミットメッセージ・レビュアーへの返信を AI に書かせることを明示的に禁止しており、違反した場合は PR 即クローズ、または貢献者アカウントの永久 BAN というペナルティを課している。これはユーザが llama.cpp に投稿する際、Claude に代筆を頼むことができない領域があるということであり、ユーザ本人が両ドキュメントの内容を正確に把握しておく必要がある。

英語原文のままでも読めるが、精読の効率と参照時の見返しやすさを考えると、母語の日本語訳が手元にあるほうが実務的である。そこで llama.cpp 上流の AGENTS.md (231 行) と CONTRIBUTING.md (207 行) を全訳し、`docs/llama.cpp/AGENTS.ja.md` および `docs/llama.cpp/CONTRIBUTING.ja.md` として本リポジトリに追加した。

翻訳方針は「忠実な逐語訳」で、見出し・箇条書き・強調・引用ブロック・コードブロック・GitHub Admonition (`> [!IMPORTANT]` など) の構造をすべて原文どおり維持している。原文中の相対リンクは、翻訳版が別リポジトリに置かれる関係で解決できないため、すべて llama.cpp 上流の絶対 URL (`https://github.com/ggml-org/llama.cpp/blob/master/...`) に置き換えた。翻訳版どうしの相互参照 (AGENTS ↔ CONTRIBUTING) のみ同ディレクトリ内の相対パスとし、原文 URL も併記して両側から辿れるようにした。

コードブロック内は英語のコードをそのまま残し、コメント (`// ...`) の中身だけを日本語化した。ただし `// GOOD` `// BAD` `// BEST` のラベルは視覚的な識別子として機能するため原文のまま維持している。コミットメッセージ用のトレイラー (`Assisted-by:` `Co-authored-by:`) は機械的に処理される識別子なので訳していない。

訳語は事前に対応表を決めて統一した (Contributor→コントリビューター、Maintainer→メンテナ、ggml/GGUF/perplexity/KV cache→英語のまま、など)。冒頭にはそれぞれ「これは私的翻訳であり、原文が権威版である」旨と、翻訳スナップショット時点の上流コミット (llama.cpp `master` @ `c812c543`, 2026-07-25) を注釈として明記した。齟齬があった場合に読者がすぐ原文へ飛べるようにしてある。

翻訳完了後は原文と翻訳版で構造メトリクス (見出し数・コードフェンス数・Admonition ブロック数) を比較し、差異が冒頭注釈による +1 のみで説明可能であることを確認した。相対リンクの書き換え漏れも grep で洗い出したところ、翻訳版内相互参照を除いて残存ゼロだった。品質面での問題は検出されていない。

今回作成した翻訳版は本リポジトリ (llm-server-ops) 内にのみ配置しており、llama.cpp 上流への PR は行わない。そもそも AGENTS.md 自体が AI による PR 投稿を禁止している対象文書であり、翻訳を上流に投げるという性質の作業ではない。今後、ユーザが llama.cpp へ投稿する場面が発生した際に、この翻訳版を精読の起点として活用してもらう想定である。

## 添付ファイル

- [実装プラン](attachment/2026-09-02_233100_llamacpp_agents_contributing_ja_translation/plan.md)

## 前提・目的

- **背景**: llama.cpp は AGENTS.md / CONTRIBUTING.md で、AI にプルリクエスト説明・コミットメッセージ・レビュアーへの返信を書かせることを明示的に禁止している。違反時のペナルティは PR 即クローズおよびアカウント永久 BAN。詳細は memory `feedback_llamacpp_no_ai_posts.md` に記録済み
- **目的**: ユーザ本人が両ドキュメントを精読するための日本語訳版を、本リポジトリ内に整備する
- **範囲外**: llama.cpp 上流への翻訳の PR は行わない。llama.cpp コードベースへの変更や実測は本作業に含めない

## 環境情報

- 対象リポジトリ: `llm-server-ops` (本リポジトリ)
- 原文の出所: `src/llama.cpp/AGENTS.md` および `src/llama.cpp/CONTRIBUTING.md`
- 原文スナップショット: llama.cpp `master` @ [`c812c543`](https://github.com/ggml-org/llama.cpp/commit/c812c543f8ab480661bd10b9546515b608b4747f) (2026-07-25、`common : skip empty implicit default preset (#25643)`)
- 原文サイズ: AGENTS.md = 231 行 / 10.7 KB、CONTRIBUTING.md = 207 行 / 12.4 KB
- 翻訳先: `docs/llama.cpp/{AGENTS,CONTRIBUTING}.ja.md` (`docs/` ディレクトリは今回新設)

## 参照レポート

- 過去に類似のレポート (ドキュメント翻訳・コントリビューションガイド精読) は存在しない
- 関連 memory: `feedback_llamacpp_no_ai_posts.md` (llama.cpp が AI 生成投稿を禁止していること、spam マークされた実例、アカウント BAN リスク、Claude は素材出しに留める運用ルール)

## 結果詳細

### 生成物

| ファイル | 行数 | サイズ | 内容 |
|---|---|---|---|
| `docs/llama.cpp/AGENTS.ja.md` | 241 | 16,174 B | AGENTS.md 全訳 + 冒頭注釈 |
| `docs/llama.cpp/CONTRIBUTING.ja.md` | 216 | 16,868 B | CONTRIBUTING.md 全訳 + 冒頭注釈 |

翻訳版の行数が原文より 10 行程度多いのは、冒頭に追加した `> [!NOTE]` 注釈ブロック (原文出所・翻訳スナップショット・リンク方針) の分。

### 構造メトリクスの一致確認

原文と翻訳版で見出し・コードフェンス・Admonition の数を比較した結果:

| 項目 | AGENTS 原文 → 翻訳版 | CONTRIBUTING 原文 → 翻訳版 | 差の説明 |
|---|---|---|---|
| 見出し (`^#{1,6} `) | 11 → 12 (+1) | 13 → 14 (+1) | 冒頭タイトル `# ... (日本語版)` を H1 に追加した分 |
| コードフェンス (`^\`\`\``) | 14 → 14 | 0 → 0 | 完全一致 (CONTRIBUTING はコードブロックが箇条書き内でインデント配置されており、行頭 grep で 0 になるのは原文と同じ挙動) |
| Admonition (`^> \[!`) | 2 → 3 (+1) | 1 → 2 (+1) | 冒頭に `> [!NOTE]` を追加した分 |

差異はすべて冒頭注釈による説明可能な +1 のみで、原文の構造は完全に保持されている。

### 相対リンク書き換え漏れ検査

以下のコマンドで翻訳版内に相対リンク (相互参照 `AGENTS.ja.md` / `CONTRIBUTING.ja.md` を除く) が残っていないか確認:

```bash
grep -nE '\]\(([^h)][^)]*\.md|[^h)][^)]*\.png|CODEOWNERS)\)' docs/llama.cpp/*.ja.md \
  | grep -vE '\((AGENTS|CONTRIBUTING)\.ja\.md\)'
```

結果: **出力なし**。原文中の `CONTRIBUTING.md` / `AGENTS.md` / `docs/build.md` / `.github/pull_request_template.md` / `CODEOWNERS` / `tools/server/README.md` / `common/jinja/README.md` / `ci/README.md` / `skills/` / `media/matmul.png` はすべて `https://github.com/ggml-org/llama.cpp/...` の絶対 URL に置換済み。既に絶対 URL だった `https://github.com/ggml-org/llama.cpp/issues` や `https://isocpp.github.io/...` はそのまま維持。

### 訳語対応 (統一)

| 原文 | 訳語 | 補足 |
|---|---|---|
| Contributor | コントリビューター | カタカナ長音あり |
| Collaborator (Triage) | コラボレーター (Triage) | Triage は括弧内で英語のまま |
| Maintainer | メンテナ | 「メンテナー」ではなく「メンテナ」 |
| Pull Request / PR | プルリクエスト / PR | 初出は「プルリクエスト (PR)」で以降 PR |
| Code Owner / CODEOWNERS | コードオーナー / `CODEOWNERS` ファイル | ファイル名は英語コード表記 |
| ban | BAN | 大文字英語 (既存 memory の慣習に合わせる) |
| ggml / GGUF / KV cache / perplexity / quantization | 英語のまま | 定訳のない技術用語 |
| squash-merge / rebase | squash マージ / rebase | git 用語は原則英語 |
| private fork | プライベートフォーク | |

### 判断メモ

- **冒頭注釈の位置**: `# タイトル` の直後に `> [!NOTE]` ブロックとして配置。読み始めた瞬間に「これは私的翻訳で、原文が権威版」であると認識できるようにした
- **コード内コメントの扱い**: 原文英語コメントと日本語訳を両方残すと視覚的に冗長になるため、日本語訳のみに置換した。ラベル `// GOOD` `// BAD` `// BEST` は視覚的識別子として機能するため原文維持
- **相互参照の扱い**: `AGENTS.md ↔ CONTRIBUTING.md` の相互参照は、翻訳版内の相対リンク (`AGENTS.ja.md` / `CONTRIBUTING.ja.md`) と原文 URL の両方を併記した。日本語で読み進めるときは相対リンク、原文にあたりたいときは URL、どちらでも辿れる
- **リンク先の branch/commit**: 上流の絶対 URL は `blob/master/...` としてブランチ名を使用 (コミットハッシュ固定にはしなかった)。翻訳版が古くなっても原文の最新版に飛べる利便性を優先。翻訳スナップショット時点のハッシュは冒頭注釈に別途明記してある
- **`docs/` ディレクトリ新設**: 本リポジトリには既存の `docs/` はなかった。ルート直下 (`/AGENTS.ja.md`) に置くと本リポジトリ自身の規約と誤読される懸念があるため、`docs/llama.cpp/` サブディレクトリを切って上流ドキュメントの翻訳であることを構造で明示

## 再現方法

翻訳版が古くなった場合、または llama.cpp 上流に大きな更新があった場合の再翻訳手順:

```bash
# 1. 上流を最新化 (src/ は .gitignore なので git 追跡外)
cd src/llama.cpp && git pull && cd -

# 2. 原文の HEAD ハッシュを取得 (冒頭注釈用)
git -C src/llama.cpp log -1 --format='%H %ci %s'

# 3. 原文と現行翻訳版で diff を取り、変更箇所を把握
diff src/llama.cpp/AGENTS.md docs/llama.cpp/AGENTS.ja.md
diff src/llama.cpp/CONTRIBUTING.md docs/llama.cpp/CONTRIBUTING.ja.md

# 4. 翻訳版を更新したら構造メトリクスで確認
for f in AGENTS CONTRIBUTING; do
  echo "=== $f ==="
  echo "見出し: orig $(grep -cE '^#{1,6} ' src/llama.cpp/$f.md) / ja $(grep -cE '^#{1,6} ' docs/llama.cpp/$f.ja.md)"
  echo "フェンス: orig $(grep -cE '^```' src/llama.cpp/$f.md) / ja $(grep -cE '^```' docs/llama.cpp/$f.ja.md)"
  echo "Admonition: orig $(grep -cE '^> \[!' src/llama.cpp/$f.md) / ja $(grep -cE '^> \[!' docs/llama.cpp/$f.ja.md)"
done

# 5. 相対リンク残存チェック
grep -nE '\]\(([^h)][^)]*\.md|[^h)][^)]*\.png|CODEOWNERS)\)' docs/llama.cpp/*.ja.md \
  | grep -vE '\((AGENTS|CONTRIBUTING)\.ja\.md\)'
```

差分の翻訳自体は、原文の該当箇所を Read してから対応する翻訳版セクションを Edit する。

## 副次発見

- **`src/llama.cpp/CLAUDE.md`** が存在し、内容は 1 行 (「AGENTS.md を熟読すること」) のみ。Read したときシステムリマインダーとして注入されるが、これは llama.cpp 上流のリポジトリルート CLAUDE.md であって本リポジトリ (`llm-server-ops`) の CLAUDE.md ではない。llama.cpp コードベース内で作業するとき (今後 fine-tune 検証などで touch する可能性あり) は、この CLAUDE.md が本リポジトリの CLAUDE.md に加えて追加ガイダンスとなる
- **CONTRIBUTING.md のコードブロックが行頭 grep で 0 になる件**: `grep -cE '^\`\`\`'` で 0 になるのは、CONTRIBUTING.md 内のコードブロックがすべて箇条書き (`-`) の中でインデント (4 スペース) 配置されているため。原文の書式上そうなっており、翻訳版もそれを踏襲しているだけで異常ではない。実際にはコードブロックは複数存在する (`enum llama_vocab_type`、`llama_model_init()`、`typedef struct llama_context * llama_context_t;` など)

## 残課題

- **本翻訳の実運用への投入**: 今回はドキュメントの整備のみ。ユーザが llama.cpp に投稿する場面が発生したら、翻訳版を起点として精読し、投稿文はユーザ本人が英語で書く運用となる (Claude は素材出しに留める)
- **翻訳版のメンテナンス**: llama.cpp 上流の AGENTS.md / CONTRIBUTING.md は変更頻度が低くはないと想像される。定期的に上流 diff を取って翻訳版を追従させる必要がある。ただし今回時点で運用ルーチンには組み込んでいない (定期実行するほど頻繁に llama.cpp へ投稿するわけでもない前提)
- **他ドキュメントの翻訳**: llama.cpp には他にも `docs/build.md` `docs/development/HOWTO-add-model.md` などの重要文書がある。今回のスコープ外だが、必要が生じたら同じ方針で `docs/llama.cpp/` 配下に追加できる
