# プラン: 過去3ヶ月のllama.cpp主要変更レポート(P100 / MI25+Vulkan関連)

## Context

ユーザ要望: 過去3ヶ月でおこなわれた llama.cpp の主要な変更のうち、**P100(t120h-p100, CUDA/Pascal)** と **MI25+Vulkan(RADV/gfx900)** に関係するものだけをレポートにまとめる。

当プロジェクトは両サーバ上で llama-server を運用しており、upstream の変更が運用構成(ビルド・性能・安定性)にどう影響するかを把握する必要がある。本レポートは upstream の git 履歴(`src/llama.cpp/`, 完全履歴あり, HEAD=2026-06-17)を一次情報源に、3ヶ月窓(2026-03-18 以降, 約1292コミット)を両ハードウェアの観点で絞り込んだ調査レポートである。コード変更は行わない(ドキュメント=レポート1本の新規作成のみ)。

## 一次情報源と再現方法

`cd src/llama.cpp` 後:
- `git log --since='2026-03-18' --oneline -- ggml/src/ggml-vulkan` (65件)
- `git log --since='2026-03-18' --oneline -- ggml/src/ggml-cuda` (84件)
- 各コミットは `git show --stat <hash>` / `git show <hash>` で内容を実確認済み

## 成果物

`report/<TZ=Asia/Tokyo date>_llamacpp_3mo_changes_p100_mi25vulkan.md` を新規作成。
タイムスタンプは作成時に `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得(推測しない)。

## レポート構成

### 1. 前提・目的
- 背景: upstream 追従/pin 判断・性能チューニングの材料として 3ヶ月分の関連変更を棚卸し
- 対象: P100(CUDA/Pascal/cc6.0) と MI25(Vulkan/RADV/gfx900) のみ。MI25 ROCm 側は対比に必要な範囲だけ言及
- 一次情報源と窓(上記)

### 2. 環境情報
- P100: t120h-p100 (10.1.4.14), Tesla P100 16GB, CUDA, **master 追従**, `-DCMAKE_CUDA_ARCHITECTURES="60"` 明示
- MI25 Vulkan: mi25 (10.1.4.13), Vega10/gfx900, RADV(Mesa), **master 追従(pin 不要)**, build-vulkan/

### 3. 核心発見サマリ
- **P100**: 最重要は `e82aaf258` (tile FA on Pascal 修正)。P100 は Tensor Core 非搭載で mma FA を使えず **tile FA 経路**に依存するため、この修正と一連の tile/mma FA 拡張が FA 利用に直結。新型量子化 NVFP4(`112c78159`)は DP4A(cc6.1+)前提で **P100 非対応**。CMake デフォルト arch に cc60 ネイティブは無いが当環境は明示指定でカバー済み(=サポート対象外ではない)。
- **MI25+Vulkan**: UMA 最適化(`32120c10e`/`4d8cc0c56`)、メモリ同期・安定性(`3e7bd4f39`/`91eb8f4fa`)、並行性(`55ac0909e`/`bef69f130`)、生成系演算最適化(`c6e408837`/`19620004f`)が gfx900 に効きうる。coopmat2/PDL/BF16 系は gfx900 非関連。Vulkan は HIP device compile を経ないため `112c78159` 由来の fp8 リグレッションと無縁=pin 不要が継続的に妥当。

### 4. P100(CUDA/Pascal)関連の変更
表形式(ハッシュ7桁 / 日付 / 件名(PR) / P100への影響 / 重要度)。主な採録:
- `e82aaf258` (04-30) CUDA: fix tile FA kernel on Pascal (#22541) — 高(P100明示, FA直結)
- `046e28443`/`ff5ef8278`/`7b8443ac7`/`88458164c` — tile/mma FA の head-dim 拡張・最適化(P100 は tile 経路)— 中
- `86221cf6d` — FA kernel selection bugfix — 中
- `112c78159` (03-26) NVFP4 dp4a kernel (#20644) — P100は DP4A 非対応で非利用 / MI25 ROCm pin の原因 — 中
- CMake デフォルト arch(`50/61/70-virtual`)に cc60 ネイティブ無し → 当環境は `-DCMAKE_CUDA_ARCHITECTURES=60` 明示でカバー(注記)
- 参考: 2026-06-02 頃の compute buffer 倍増による CUDA OOM リグレッション(既存レポートで `-ub 4096` 対策済み)を「upstream 変更が P100 運用に波及した実例」として言及

### 5. MI25+Vulkan(RADV/gfx900)関連の変更
表形式。主な採録:
- `32120c10e` (06-16) UMA device で host-visible memory 優先 (#22930) — 高
- `4d8cc0c56` (05-27) AMD UMA で transfer queue を避ける (#22455) — 高
- `558e221b7` (06-17) buffer 作成時に実メモリプロパティ記録 (#24326) — 中
- `3e7bd4f39` (06-12) memcpy read に pipeline barrier 追加 (#23770) — 中(同期/安定性)
- `55ac0909e` (06-01) pipeline コンパイル中に device mutex を保持しない (#23641) — 中
- `bef69f130` (06-01) host memory lock contention 削減 (#23376) — 中
- `fdc3db9b6` (06-11) 連続バッファ転送の fast path (#23973) — 中
- `c6e408837` (05-27) MUL_MAT_VEC を F16/32 で 4K/iter 化 (#22887) — 中(生成系演算, eval 改善の可能性)
- `19620004f` (06-01) Q3_K/Q6_K block-load 最適化 (#23056) — 中(Mesa)
- `d6d0ce821` (06-09) iq1 mul_mm 共有メモリ削減 (#24287) — 低-中
- `b4e3dc613` (06-09) v_dot2_f32_f16 サポート(条件付き, gfx900 での有効性は実機確認要)— 低-中
- `a6d6183db` (05-17) ggml-vulkan/CMakeLists に SPIRV-Headers チェック追加 (#22009) — 中(当環境で spirv-headers 必須なので汎用的に有益)
- `95405ac65` (05-23) SPIRV-Headers の find_package 修正 (#23215) — **Windows 限定**で Linux 運用の MI25 には直接無関係(注記のみ)
- `91eb8f4fa` (05-28) memory logger iterator 安全性 (#23667) — 低

※ サブエージェントの因果推測(例「f16 KV 破損防止に寄与」)は断定せず「同期強化/安定性向上」等に留める。eval/prompt への効果は実機ベンチ未取得のため「可能性」と明記。

### 6. 無関係と判定したカテゴリ(明示)
coopmat2(NVIDIA/RDNA3+), Hopper PDL, BF16 専用, Apple/Asahi ARM GPU — gfx900/P100 いずれにも非関連。

### 7. 運用への示唆
- P100: master 追従継続で問題なし。FA 経路の改善が継続中。OOM リグレッションのような波及に注意し ub は要監視。
- MI25 Vulkan: pin 不要の前提(HIP 非経由)は今期も維持。UMA/同期/並行性改善で安定性・性能が漸進。eval 遅さ(0.6倍)に効きうる `c6e408837` 等は次回ベンチで実測価値あり。

### 8. 参照レポート(リンク)
- `report/2026-06-03_063647_llama_cpp_oom_regression_fix.md`(P100 OOM)
- `report/2026-06-13_112006_mi25_qwen36_128k.md`(MI25 ROCm 基準)
- `report/2026-06-14_001107_mi25_vulkan_qwen36_128k.md`(Vulkan 性能/pin不要)
- `report/2026-06-14_041305_mi25_vulkan_backend_quality.md`(Vulkan 品質等価)

### 9. 添付ファイル
- REPORT.md ルールに従い、本プランファイルを `report/attachment/<レポート名>/plan.md` にコピーしてリンク。

## 検証状況(プラン段階で実施済み)
- 採録した全ハッシュ(P100 7件 + Vulkan 14件 + pin commit)が窓内(2026-03-18以降)に実在し件名一致を `git show -s` で確認済み
- pin `0fac87b15`(03-26 08:14)は NVFP4 `112c78159`(03-26 09:54)の直前であることを確認(pin 妥当性の裏付け)
- `95405ac65` は Windows 限定と判明 → 重要度を下方修正済み

## 検証(レポート作成後)
- 参照レポート4本のパス実在を確認
- タイムスタンプが `TZ=Asia/Tokyo date` 由来であること
- 画像(PNG)は本調査では無いため埋め込み不要(該当時のみのルール)
