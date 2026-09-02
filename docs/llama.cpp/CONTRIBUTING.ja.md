# llama.cpp コントリビューションガイド (日本語版)

> [!NOTE]
> このファイルは llama.cpp 上流の [CONTRIBUTING.md](https://github.com/ggml-org/llama.cpp/blob/master/CONTRIBUTING.md) を miminashi が私的に日本語訳したものです。**原文の権威版ではありません**。齟齬がある場合は原文が正となります。翻訳時点のスナップショットは llama.cpp `master` @ [`c812c543`](https://github.com/ggml-org/llama.cpp/commit/c812c543f8ab480661bd10b9546515b608b4747f) (2026-07-25) です。
>
> 原文中の相対リンクはすべて上流の絶対 URL に置き換えています。翻訳版どうしの相互参照 (`AGENTS.ja.md`) は同一ディレクトリ内の相対パスにしてあります。

---

# コントリビューター

このプロジェクトはコントリビューターを 3 段階に区別します:

- **Contributors (コントリビューター)**: 過去に貢献したことのある人 (特別な権限なし)
- **Collaborators (Triage) (コラボレーター)**: 大きな貢献を行ってきた人。コードの一部を担当する場合があり、担当コードについての貢献の保守とレビューを期待される
- **Maintainers (メンテナ)**: PR のレビューとマージを担当する。コードオーナーの承認を得たうえで行う

# AI 利用ポリシー

> [!IMPORTANT]
>
> AI が生成したコードは許可されています。どのように生成されたかにかかわらず、すべての行に対してあなたが 100% の責任を負います。
>
> AI 利用の未開示は、あなたのアカウントがこのプロジェクトへの貢献から永久に BAN される結果となる可能性があります。
>
> AI の許容される利用方法・制限される利用方法に関する詳細は、[AGENTS.ja.md](AGENTS.ja.md) (原文: [AGENTS.md](https://github.com/ggml-org/llama.cpp/blob/master/AGENTS.md)) ファイルにあります。

コードの一部でも AI で生成する場合、コントリビューターは以下の要件を守らなければなりません:

1. AI をどのように使ったかを明示的に開示すること。
2. 同じ変更を扱う既存の PR がないかチェックし、あれば重複した新規 PR を作る代わりに、そちらの著者と協働するためにコメントすること。
3. プルリクエストを提出する前に、包括的な手動レビューを行うこと。
4. メンテナから質問されたときに、提出したすべての行のコードを説明できる準備をしておくこと。
5. あなたの投稿文 (バグレポート、機能要望、プルリクエスト説明、Github discussions、人間への返信など) を書かせるために AI を使うことは厳格に禁止されている。

より詳しくは [AGENTS.ja.md](AGENTS.ja.md) (原文: [AGENTS.md](https://github.com/ggml-org/llama.cpp/blob/master/AGENTS.md)) を参照してください。

# プルリクエスト (コントリビューター & コラボレーター向け)

### 始める前に

- まず既存の議論と PR を検索すること - 重複はおそらく問答無用でクローズされます。
- 機能は PR ではなく issue から始めなければなりません - コードを書き始める前に関心が集まるのを待ってください。ニッチな機能はサンプル/ツールとして、あるいはプライベートフォークにしか着地しないかもしれません。
- バグ修正 PR には、再現可能な issue と、あなたの変更前には失敗し変更後に通るリグレッションテストを含めなければなりません。テストのない修正はレビューなしにクローズされる場合があります。
- 新しい CLI や公開 API の追加は、内部変更よりも**高いハードル**を持ちます - なぜ既存のメカニズムでは不十分なのかを正当化してください。
- 上記すべてを満たしても、マージが保証されるわけではありません - [プルリクエスト (メンテナ向け)](#プルリクエスト-メンテナ向け) を参照してください。
- 新しいコントリビューターの場合
    - 同時にオープンする PR は 1 件に制限すること
    - 些細な修正 (typo、フォーマット変更など) を提出しないこと

### PR の準備

- llama.cpp はモデル評価に ggml テンソルライブラリを使います。ggml に不慣れな場合は、[ggml リポジトリのサンプル](https://github.com/ggml-org/ggml/tree/master/examples/) を見てみることを検討してください。[simple](https://github.com/ggml-org/ggml/tree/master/examples/simple) は ggml 利用の最小構成を示しています。[gpt-2](https://github.com/ggml-org/ggml/tree/master/examples/gpt-2) は GPT-2 を使った言語モデル推論の最小実装を持っています。[mnist](https://github.com/ggml-org/ggml/tree/master/examples/mnist) は単純な画像分類器を訓練・評価する方法を示しています
- 変更をテストすること:
  - 公開前に [自分のマシンで CI 一式を実行](https://github.com/ggml-org/llama.cpp/blob/master/ci/README.md) すること
  - あなたの変更で perplexity と性能が負の方向に影響を受けていないことを確認すること (`llama-perplexity` と `llama-bench` を使う)
  - `ggml` ソースを変更した場合、`test-backend-ops` ツールを実行して、`ggml` 演算子の異なるバックエンド実装が一貫した結果を生成するか確認すること (少なくとも 2 つの異なる `ggml` バックエンドへのアクセスが必要)
  - `ggml` 演算子を変更または新規追加した場合、対応するテストケースを `test-backend-ops` に追加すること
- 機能または修正ごとに個別の PR を作ること:
  - 無関係な変更を単一の PR に混ぜないこと
  - 新しいモデルや機能のサポートを追加する場合、良い理由がない限り、最初の PR は **CPU サポートのみ** に集中すること。CUDA など他のバックエンドのサポートはフォローアップの PR で追加する
  - 特に、新しいデータ型の追加 (`ggml_type` enum の拡張) は不均衡に大きな保守負担を伴います。新しい量子化型を追加するには、次の**追加要件**を*最低限*満たす必要があります:
    - 新しい型を使って小さなモデルを GGUF に変換し、HuggingFace にアップロードする
    - FP16/BF16 (ネイティブ精度のほう) および同程度サイズの他の型と比較した [perplexity](https://github.com/ggml-org/llama.cpp/tree/master/tools/perplexity) 比較を提供する
    - 新しい型と同程度サイズの他の型の両方について、FP16/BF16 (ネイティブ精度のほう) との KL divergence データを計算して提供する
    - 純粋な CPU 上での、新しい型と同程度サイズの他の型との [性能データ](https://github.com/ggml-org/llama.cpp/tree/master/tools/llama-bench) を提供する
- 高速レビューのために、あなたのブランチへの write アクセスを許可することを検討してください。レビュアーが直接コミットを push できるようになります

### PR 送信後

- llama.cpp の品質と長期保守性の基準を満たすため、修正の要求が来ることを覚悟しておくこと
- メンテナは PR を承認・マージするかの最終判断を、あなたの洞察と承認に依存します
- PR が停滞したら、最新の `master` の上に rebase してメンテナの注意を引くこと
- 関連する issue の修正や関連する PR のレビューへの対応可能性を示すため、[CODEOWNERS](https://github.com/ggml-org/llama.cpp/blob/master/CODEOWNERS) に自分を追加することを検討してください

# プルリクエスト (メンテナ向け)

- PR は squash マージすること
- squash されたコミットのタイトルには次のフォーマットを使うこと: `<module> : <commit title> (#<issue_number>)`。例: `utils : fix typo in utils.py (#1234)`
- `<module>` はここから任意に選んでよい: https://github.com/ggml-org/llama.cpp/wiki/Modules
- 他のメンテナには自分の PR をマージさせること
- PR をマージするときは、変更内容をよく理解していることを確認すること
- PR が新しいリリースを正当化しない場合、squash されたコミットに `[no release]` を追加して CI リソースを節約すること
- 保守を意識すること: 機能に関する作業のほとんどは PR がマージされた後に発生します。PR の著者が長期的な貢献にコミットしない場合、誰か他の人 (=あなた) が責任を取る必要があります

メンテナは、特に以下の条件のいずれかに該当する場合、いかなる理由でも、質問なしにレビューを拒否したりプルリクエストをクローズしたりする権利を留保します:
- 提案された変更が既にロードマップまたは既存の issue に言及されており、誰かに割り当てられている場合。
- プルリクエストが既存のものと重複している場合。
- コントリビューターがこのコントリビューションガイドまたは AI ポリシーを守らない場合。
- 変更が既存のアーキテクチャに合わない、または複雑すぎて利益を正当化できない場合。

# コーディングガイドライン

- サードパーティ依存、追加ファイル、追加ヘッダなどの追加を避けること
- 他 OS・他アーキテクチャとのクロス互換性を常に考えること
- 見栄えのする現代的な STL 構文を避け、基本的な `for` ループを使い、テンプレートを避け、シンプルに保つこと
- 縦の整列は読みやすさと一括編集のしやすさを向上させる
- 行末の空白を掃除し、インデントは 4 スペース、ブレースは同じ行、`void * ptr`、`int & a` とする
- 公開 API では `int32_t` のようなサイズ指定整数型を使うこと。`size_t` はアロケーションサイズやバイトオフセットにも適切な場合がある
- 構造体は `typedef struct foo {} foo` ではなく `struct foo {}` で宣言すること
    - C++ コードでは、必要ないときは省略可能な `struct` および `enum` キーワードを省略する
    ```cpp
    // OK
    llama_context * ctx;
    const llama_rope_type rope_type;

    // not OK
    struct llama_context * ctx;
    const enum llama_rope_type rope_type;
    ```

    _(注: このガイドラインは `llama.cpp` コードベースにはまだ適用されていません。新規コードはこのガイドラインに従うこと。)_

- コード中の既存パターン (インデント、スペースなど) にできる限り従うこと。迷ったら `clang-format` (clang-tools v15+) を使って追加したコードをフォーマットする
- 現行ガイドラインでカバーされていないものについては、[C++ Core Guidelines](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines) を参照する
- テンソルはデータを row-major 順で格納する。次元 0 を列、1 を行、2 を行列と呼ぶ
- 行列積は慣例と異なる: [`C = ggml_mul_mat(ctx, A, B)`](https://github.com/ggml-org/llama.cpp/blob/880e352277fc017df4d5794f0c21c44e1eae2b84/ggml.h#L1058-L1064) は $C^T = A B^T \Leftrightarrow C = B A^T$ を意味する。

![matmul](https://github.com/ggml-org/llama.cpp/raw/master/media/matmul.png)

# ネーミングガイドライン

- 関数名、変数名、型名には `snake_case` を使うこと
- ネーミングは通常、最長共通接頭辞を最適化する (https://github.com/ggml-org/ggml/pull/302#discussion_r1243240963 参照)

    ```cpp
    // not OK
    int small_number;
    int big_number;

    // OK
    int number_small;
    int number_big;
    ```

- Enum 値は常に大文字で、enum 名を接頭辞にする

    ```cpp
    enum llama_vocab_type {
        LLAMA_VOCAB_TYPE_NONE = 0,
        LLAMA_VOCAB_TYPE_SPM  = 1,
        LLAMA_VOCAB_TYPE_BPE  = 2,
        LLAMA_VOCAB_TYPE_WPM  = 3,
        LLAMA_VOCAB_TYPE_UGM  = 4,
        LLAMA_VOCAB_TYPE_RWKV = 5,
    };
    ```

- 一般的なネーミングパターンは `<class>_<method>` で、`<method>` は `<action>_<noun>` である

    ```cpp
    llama_model_init();           // class: "llama_model",         method: "init"
    llama_sampler_chain_remove(); // class: "llama_sampler_chain", method: "remove"
    llama_sampler_get_seed();     // class: "llama_sampler",       method: "get_seed"
    llama_set_embeddings();       // class: "llama_context",       method: "set_embeddings"
    llama_n_threads();            // class: "llama_context",       method: "n_threads"
    llama_adapter_lora_free();    // class: "llama_adapter_lora",  method: "free"
    ```

    - `get` の `<action>` は省略可
    - 必要なければ `<noun>` は省略可
    - `<class>` の `_context` サフィックスは任意。シンボルを曖昧さなく区別する必要があるときに使う
    - コンストラクタ/デストラクタの `<action>` には `init`/`free` を使う

- 型がユーザに対して不透明であるべき場合は `_t` サフィックスを使う - それが struct であるか他の何かであるかは、ユーザにとって関係ないため

    ```cpp
    typedef struct llama_context * llama_context_t;

    enum llama_pooling_type llama_pooling_type(const llama_context_t ctx);
    ```

    _(注: このガイドラインは `llama.cpp` コードベースにはまだ適用されていません。新規コードはこのガイドラインに従うこと)_

- C/C++ ファイル名はすべて小文字でダッシュ区切り。ヘッダは `.h` 拡張子、ソースファイルは `.c` または `.cpp` 拡張子を使う
- Python ファイル名はすべて小文字でアンダースコア区切り

- _(TODO: 略語の使用)_

# プリプロセッサディレクティブ

- _(TODO: 例付きでガイドラインを追加し、コードベースに適用する)_

    ```cpp
    #ifdef FOO
    #endif // FOO
    ```

# コード保守

- 既存のコードは、次のことに責任を持つ指定のコラボレーターおよび/またはメンテナが [CODEOWNERS](https://github.com/ggml-org/llama.cpp/blob/master/CODEOWNERS) ファイルに指定されているべきです:
  - 関連する PR のレビューとマージ
  - 関連するバグの修正
  - 開発者へのガイダンス/サポートの提供

- コードの大きな部分を追加または変更するとき:
  - あなたがコラボレーターであれば、関連 PR のレビュー可能性を示すため [CODEOWNERS](https://github.com/ggml-org/llama.cpp/blob/master/CODEOWNERS) に自分を追加すること
  - あなたがコントリビューターであれば、あなたのコードを長期的にレビュー・保守する意思のある既存のコラボレーターを見つけること
  - 変更をテストするための必要な CI ワークフロー (およびハードウェア) を提供すること ([ci/README.md](https://github.com/ggml-org/llama.cpp/tree/master/ci) 参照)

- 新規コードは、本ドキュメントで概説されるガイドライン (コーディング、ネーミングなど) に従うべきです。`ggml` インターフェースと直接やり取りしない、隔離された・バックエンド固有のコード部分では例外が認められます。
  _(注: 過去の経緯により、既存コードはこのガイドラインに従うことを要求されません)_

- server の変更については、[server 開発ドキュメント](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README-dev.md) を必ず参照してください

# ドキュメント

- ドキュメントはコミュニティの取り組みです
- API の使い方を調べるためにソースコードを見なければならないとき、将来の参照のために短いサマリをヘッダファイルに追加することを検討してください
- 誤ったまたは古いドキュメントに気付いたら、更新してください

# リソース

Github の issues、PRs、discussions には、コードベースに慣れるうえで有用な情報が多く含まれています。便宜上、より重要な情報の一部が Github プロジェクトから参照されています:

https://github.com/ggml-org/llama.cpp/projects
