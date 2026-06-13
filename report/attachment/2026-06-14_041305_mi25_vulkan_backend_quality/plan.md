# mi25 Vulkan(RADV) バックエンド品質劣化・出力破損検証

## Context

[mi25 Vulkan レポート](../../projects/llm-server-ops/report/2026-06-14_001107_mi25_vulkan_qwen36_128k.md)
で、Vulkan(RADV) バックエンドが ROCm に対し prompt 処理 ~3.3倍という大幅な性能向上を示した。
しかし Vulkan は master 追従(pin なし)・RADV シェーダ経路という ROCm とは別実装であり、**実装の数値精度差やシェーダのバグで出力品質が劣化・破損していないか**が未検証。実際、同レポートでは f16 KV + FA トライアル中にホストダウンが起き、RADV シェーダ経路の安定性に懸念が残っている。

本タスクの目的は **モデルの「賢さ」の絶対評価ではなく、既知良好な ROCm 構成を基準に Vulkan 構成が出力を壊していないかの等価性検証**。同一 GGUF・同一量子化(q8_0)・同一サンプリングで動かす。日本語・英語の両言語で計測する。

> **比較の性質と限界(重要)**: ROCm は pin v8533、Vulkan は master v9620 で **1000+ コミット差**があり、両者のバージョンを揃えることはできない(ROCm は gfx900 で v9620 をビルド不能)。したがって観測される差は「バックエンド実装差(数値精度・シェーダ経路)」**と**「llama.cpp バージョン差(v8533→v9620)」の**両方**を含み、両者を完全には分離できない。ただし本タスクで知りたいのは **実運用される 2 構成(ROCm本番=v8533 vs Vulkan本番=v9620)が同等の出力品質を保つか**であり、この「構成まるごとの等価性」比較こそが実運用上の正しい問いに答える(純粋なバックエンド単体差の分離は目的ではない)。差が出た場合に実装差かバージョン差かを切り分ける必要が生じたら、その時点で追加調査する。

期待される結果: KLD/PPL が量子化ノイズ以下に収まり、greedy 生成に破綻がなく、実タスク正答率も誤差内 → 「Vulkan は本番投入可能」と結論づけられる。万一どこかで破損が出れば、その言語・経路を特定する。

## 計測対象(固定条件)

| 項目 | 値 |
|------|-----|
| モデル | `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`(22.36GB、両バックエンド共通の同一 GGUF) |
| KV 量子化 | q8_0(f16 はホストダウンリスクのため回避) |
| バックエンド A(基準) | ROCm/HIP — `build/bin/`(pin `0fac87b15` v8533) |
| バックエンド B(検証) | Vulkan/RADV — `build-vulkan/bin/`(master, `GGML_VK_VISIBLE_DEVICES=0,1,2,3`) |
| 共通起動オプション | `--flash-attn 1 --poll 0 -b 2048 -ub 2048` |
| サンプリング(生成系) | temp=0(greedy)・seed 固定。両バックエンド完全同条件 |

サーバ/エンドポイント・ロック・バックエンド切替手順は既存スキルを使用:
- ロック: `.claude/skills/gpu-server/scripts/lock.sh mi25` / `unlock.sh mi25`
- 起動: `.claude/skills/llama-server/scripts/llama-up.sh`（Vulkan は `MI25_BACKEND=vulkan` を前置）
- API: `http://10.1.4.13:8000/v1`(OpenAI 互換)

## 設計: 3層の計測

### Phase 1(主軸): KL-divergence + Perplexity — バイナリ直接

llama.cpp が量子化・バックエンドの品質劣化検証に公式採用する標準手法。`llama-perplexity` を使い、**ROCm が出した基準 logits に対し Vulkan の同一テキスト評価の KLD を測る**。実装破損(NaN・シェーダ誤り・分布崩れ)はここで決定的に露見する。

- 既存ラッパー: `src/llama.cpp/examples/model-conversion/scripts/utils/perplexity-gen.sh`(基準 `.kld` 生成)/ `perplexity-run.sh`(KLD 計算)を参考に、`build_dir` 引数で ROCm/Vulkan のバイナリを切替。
- データ:
  - **英語** = wikitext-2(`wiki.test.raw`、スクリプトが HF から自動 DL)
  - **日本語** = 日本語 Wikipedia の raw text 抜粋(数百 KB、`ppl/ja-wiki.raw` として用意)
- **実行条件は本番構成と一致させる**(本番で使う q8_0 シェーダ経路を検証するため): 両バイナリとも `--flash-attn 1 --cache-type-k q8_0 --cache-type-v q8_0` を付与。デフォルト(FA=0/KV f16)で測ると本番と別経路になり等価性検証の意味が薄れる。Vulkan は FA=1 が q8_0 KV の前提でもある。
- 手順(英語・日本語それぞれ):
  1. `build/bin/llama-perplexity -m <model> -f <data> --flash-attn 1 --cache-type-k q8_0 --cache-type-v q8_0 --kl-divergence-base ppl/rocm-<lang>.kld`(ROCm 基準 logits 生成)
  2. `build-vulkan/bin/llama-perplexity -m <model> -f <data> --flash-attn 1 --cache-type-k q8_0 --cache-type-v q8_0 --kl-divergence --kl-divergence-base ppl/rocm-<lang>.kld`(Vulkan で KLD 計算)
  3. 各実行の PPL も記録。実装破損検出が目的なので `--chunks` を絞り短時間化(例 50 チャンク)。
- 抽出指標: **Mean KLD / KLD p99・max / Same-top-token 一致率(%) / PPL(ROCm) / PPL(Vulkan) / PPL 比**
- 合否目安(量子化レベルのノイズ内か): Same-top-token > 99% / Mean KLD < 0.01 nats / PPL 比 ±1% 以内。

> `llama-perplexity` バイナリは llama-server と別ターゲット。mi25 上で `build/` と `build-vulkan/` それぞれ `cmake --build <dir> --target llama-perplexity` で追加ビルドが必要(サーバと同一ツリーなので追加コンパイルは小さい)。

> **【重要リスク】KLD logits のバージョン互換性**: ROCm は pin `0fac87b15`(v8533)、Vulkan は master `57fe1f07c`(v9620)で **1000+ コミット差**があり、両バージョンを揃えることはできない(ROCm は v9620 をビルド不能)。`--kl-divergence-base` の logits バイナリフォーマットが両バージョン間で非互換だと、ROCm 生成 `.kld` を Vulkan が読めず KLD 計算が破綻する。**最初に小さなチャンクで互換性を確認する**:
> - **互換の場合** → 設計どおり KLD(Mean/分位点/Same-top-token)を主指標に使う。
> - **非互換の場合** → KLD を諦め、(a) **同一コーパスの PPL 値の直接比較**(ROCm PPL vs Vulkan PPL。teacher-forced の安定指標で、2 構成の出力品質が同等かを反映する)と、(b) **Phase 2 の greedy トークン列一致率**(logits ファイルに依存せず同一の問いに答えられる)を主指標に格上げする。この二段構えにより、KLD が使えなくても「2 構成が出力を壊していないか」は確実に判定できる。

### Phase 2: greedy 生成の破綻チェック — API 経由

日英の代表プロンプト各 8〜10 件(知識 QA・要約・コード生成・長文継続・定型生成・指示追従)を temp=0/seed 固定で両バックエンドに送り、**実装破損が質的に現れる現象**を検出:

- 自動チェック: n-gram 反復ループ、不正 Unicode(文字化け)、`finish_reason` 異常な途中停止、空応答、極端な長さ。
- 両バックエンド出力の差分: 最初の分岐トークン位置・編集距離を記録。**「片方だけ破綻」が実装差の証拠**(両方に同じ反復が出るならモデル特性でありバックエンド差ではない)。
- 目視確認も併用(特に日本語の流暢さ・崩れ)。
- 軽量な独自スクリプト(`gen_diff.py`)を attachment 配下に作成。`/v1/chat/completions` に投げるだけ。

### Phase 3(傍証): 実タスク正答率 — API 経由

実タスクでも崩れていないことの裏付け。両バックエンドで正答率を比較し、差が統計誤差内かを見る。

- **英語 = GSM8K**: 既存 `src/llama.cpp/examples/llama-eval/llama-eval.py` を使用(`--dataset gsm8k --grader-type regex`、HF 自動 DL)。例 150 問。
- **日本語 = JMMLU**: llama-eval.py は未対応のため、**GPQA の選択肢(A/B/C/D)抽出ロジックを流用した軽量スクリプト `jmmlu_eval.py` を新規作成**(attachment 配下)。HF の JMMLU データセットを DL し、数科目サブセットを `/v1/chat/completions` に投げ regex 採点。例 数百問。
- **サンプリングは greedy(temp=0)で統一**。temp>0 にすると数値差で両バックエンドのサンプリング軌道が分岐し、正答率差が「実装差」か「サンプリング分散」か切り分け不能になるため避ける。thinking 反復は `max_tokens` 打ち切り + regex 抽出で吸収する(両バックエンド同条件なので反復が出ても比較の公平性は保たれる)。これにより正答率差はバックエンド実装差のみを反映する。

## 運用フロー(ロック専有時間を最小化)

KLD はサーバ不要(バイナリ)、Phase 2/3 はサーバ要(API)。バックエンドごとにまとめてサーバ起動を 1 回ずつに抑える:

1. `lock.sh mi25` でロック取得。
2. 事前準備(ロック中・読み取り/ビルドのみ):
   - **mi25 上の実 GGUF パスを特定**(`unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` は llama-server が DL 済み。HF キャッシュ等のローカルパスを確認し、両バックエンドの `llama-perplexity` に同一ファイルを渡す)。
   - **mi25 上の llama.cpp ツリー(`~/llama.cpp`)の所在確認**と、`build/`・`build-vulkan/` の `llama-perplexity` ターゲットをビルド。perplexity スクリプトは mi25 側ツリーのものを使うか、バイナリを直接叩く(スクリプト依存を避け直接実行が確実)。
   - **KLD logits 互換性の事前チェック**(上記リスク参照。数チャンクで ROCm `.kld` を Vulkan が読めるか確認し、主指標の確定)。
   - 日本語コーパス(日本語 Wikipedia raw 抜粋)・JMMLU/GSM8K データ取得。
3. **ROCm フェーズ**: `llama-up.sh` で ROCm サーバ起動 → Phase 2 greedy 生成 + Phase 3 正答率(API) → サーバ停止 → Phase 1 基準 logits 生成(バイナリ, 英日)。
4. **Vulkan フェーズ**: `MI25_BACKEND=vulkan llama-up.sh` で起動 → Phase 2 + Phase 3(API) → 停止 → Phase 1 Vulkan KLD 計算(バイナリ, 英日)。
5. `unlock.sh mi25` で解放。
6. 集計・可視化・レポート作成。

### 異常時対応(CLAUDE.md 準拠)

本ベンチは f16 KV を避け q8_0 限定とするが、長時間高負荷(PPL 大量チャンク・正答率大量問題・長文生成)で既存レポートと同種のホストダウンが再発する可能性がある。**mi25 が SSH・ping 不通になったら、電源リセットの前に必ず `.claude/skills/gpu-server/scripts/bmc-screenshot.sh` で KVM スクショを取得して証跡(カーネルパニック・FS 破損・OOM 等のコンソール表示)を保全**し、その後 `bmc-power.sh` で復旧する(`gpu-server` スキル、SSH 不通でも操作可)。負荷は段階的に上げ、各 Phase は小さいバッチから開始してダウン兆候を早期に検知する。

## 作成・変更するファイル

- `report/attachment/<timestamp>_backend_quality/jmmlu_eval.py` — JMMLU 採点スクリプト(GPQA 抽出流用)
- `report/attachment/<timestamp>_backend_quality/gen_diff.py` — greedy 生成・破綻検出・差分スクリプト
- `report/attachment/<timestamp>_backend_quality/prompts_{ja,en}.jsonl` — Phase 2 プロンプト
- `report/attachment/<timestamp>_backend_quality/*.png` — KLD 分布・PPL 比較・正答率比較グラフ
- `report/attachment/<timestamp>_backend_quality/results.json` — 全生データ
- `report/<timestamp>_mi25_vulkan_backend_quality.md` — 最終レポート(REPORT.md 準拠)

既存資産の再利用: `perplexity-gen.sh`/`perplexity-run.sh`(KLD)、`llama-eval.py`(GSM8K)、`lock.sh`/`unlock.sh`、`llama-up.sh`/`llama-down.sh`。src/llama.cpp(サブツリー)は改変せず、独自スクリプトは attachment 配下に置く。

## 検証(成功条件)

レポートに以下を表として提示し、各々が閾値内なら「Vulkan 実装に品質劣化・破損なし」と結論:

1. **分布等価性(英・日)**:
   - KLD が使える場合 → Same-top-token > 99%、Mean KLD < 0.01 nats、PPL 比 ±1% 以内。
   - KLD 非互換時(フォールバック)→ PPL 比 ±1% 以内、かつ Phase 2 の greedy トークン列一致率が高水準(片方のみの破綻なし)。
2. **greedy 破綻チェック(英・日)**: 文字化け・反復ループ・途中停止・空応答が Vulkan 側のみで発生していない(両バックエンド同等)。
3. **正答率(GSM8K 英・JMMLU 日)**: 両バックエンドの正答率差が統計誤差(おおむね ±数 %、問題数に応じた信頼区間)内。

万一いずれかで Vulkan 側のみの劣化が出た場合は、言語・経路(prefill/decode、特定 KLD 外れ値トークン)に加え、**実装差(RADV シェーダ)由来かバージョン差(v8533→v9620)由来か**の切り分けを試み(可能なら ROCm と Vulkan の中間バージョンや CPU バックエンドを参照点に)、レポートに記載する。

## レポート方針(REPORT.md / メモリ準拠)

- タイトルは 50 字以内・簡潔に。
- 「核心発見サマリ」冒頭に結果グラフ(KLD/PPL/正答率の ROCm vs Vulkan)を PNG 画像埋め込み。
- plan mode で計画したため、対になるレポートを必ず作成。
