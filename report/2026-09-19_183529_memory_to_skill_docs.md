# メモリの注意点を CLAUDE.md とスキル文書へ移す

- **実施日時**: 2026年9月19日 18:00 〜 18:35 JST (メモリと CLAUDE.md / スキル文書の照合、移設、メモリ整理)
- **報告日時**: 2026年9月19日 18:35 JST
- **作成者**: Claude Opus 5 (1M context)

## 概要

Claude のメモリにしか書かれておらず、CLAUDE.md にもスキル文書にも無い運用上の注意点を洗い出し、置き場所を決めて移した。メモリはセッションをまたいで読まれるものの、リポジトリには残らないので、別のマシンや別の担当者から見えない。スキル文書に書けば、その作業を始めるときに必ず読まれる。

まずメモリ全件と CLAUDE.md・REPORT.md・スキル文書を照合し、どこにも書かれていない注意点を 11 件見つけた。そのうち GPU サーバ固有の 7 件はスキル文書（llama-server・gpu-server・BMC 手順）へ移した。Bash ツールの落とし穴と fine-tune の移管先はスキルに属さないので CLAUDE.md に書いた。OSS への投稿ルールと memtest_vulkan の使い方はメモリに残した。

移す前に出典のレポートと突き合わせたところ、メモリの記述に誤りや古い点が 3 つ見つかった。1 つ目は、aws-gpu01 の tensor 分割のハング回避策として覚えていた設定値が実在しない値だったこと。後のレポートで訂正済みで、正しい値と、その回避策の性能コストを書いた。2 つ目は、同じハングが別サーバ（4 枚構成）では起きないと後から分かっていたこと。3 つ目は、グローバルに配置したプラグイン版の起動スクリプトが 5 月時点の古いコピーのままで、問題は一つの設定だけでなくコピー全体が古いことだった。

あわせて、スキル文書の古い記述を 2 件直した。aws-gpu の起動時のファン騒音はすでにほぼ解消しているのに「消せていない」と書かれていた点と、mi25 の既定バックエンドが ROCm のままになっていた点である。

移した内容と重複するメモリ 3 件（うち 1 件は誤った設定値を含む）は削除した。mi25 の GPU 配置は実機で確かめようとしたが、mi25 に SSH が届かなかったので、2026-07-20 時点のレポートの記録をもとに書き、日付を明記した。

次にやることは、mi25 に届くようになったら GPU 配置と power cap を実機で確かめて mi25 の注意事項を裏付けること、それと今回対象外にした古いメモリ（mi25 の Vulkan 関連など）の整理である。

## 添付ファイル

- [実装プラン](attachment/2026-09-19_183529_memory_to_skill_docs/plan.md)

## 核心発見サマリ

**結論**: 11 件の注意点を CLAUDE.md（2 件）とスキル文書（7 件）へ移し、2 件はメモリに残した。移設の過程で **メモリの誤り 1 件（`GGML_CUDA_ALLREDUCE=butterfly`）と、事実の更新 2 件** を見つけて正しい内容で書いた。

| # | 発見 | 出典 |
|---|---|---|
| 1 | **`GGML_CUDA_ALLREDUCE=butterfly` は存在しない値**。`ggml-cuda.cu` が受け付けるのは `nccl` / `internal` / `none` だけで、未知の値は警告付きで `none` に落ちる。正しい回避策は `none` だが、NCCL 比 **decode -25% / prefill -78〜-80%** | 2026-09-16 3 腕レポート、`src/llama.cpp/ggml/src/ggml-cuda/ggml-cuda.cu` の `getenv("GGML_CUDA_ALLREDUCE")` |
| 2 | NCCL 起動ハングは **aws-gpu01 ×7 固有**。t120h-p100 ×4 では既定の NCCL で起動 3/3・本計測も完走 | 2026-09-18 t120h-p100 MTP レポート |
| 3 | plugin cache `llama-server/1.0.0` は **2026-05-13 のコピー**で、`--presence-penalty 1.0`・RPC スタック・mi25 Vulkan 自動検出・`ttyd-up.sh` を含まない（dry 行が無いのは llama.cpp 既定の 0 と同じで実害は無い） | `~/.claude/plugins/cache/claude-plugins-official/llama-server/1.0.0/skills/llama-server/scripts/` |

## 結果詳細

### 移した先

| 注意点 | 移した先 |
|---|---|
| `pkill -f` / `pgrep -f` で自分自身を kill する（exit 144） | `CLAUDE.md` の「重要な制約」表 |
| `llama-finetune` は壊れていて、fine-tune は別プロジェクトへ移管済み | `CLAUDE.md` の「ソースコード」節 |
| aws-gpu01 の `--split-mode tensor` が NCCL で起動ハング | `llama-server/SKILL.md` に「既知の問題」節を新設 |
| plugin 版の `start.sh` が古い | `llama-server/SKILL.md` のサンプリングパラメータ節の直後 |
| mi25 の GPU 配置と常用／fallback のマスク、MMIO 依存、BACO 後の power cap、重い I/O での ext4 破損 | `gpu-server/SKILL.md` に「mi25 の注意事項」を新設 |
| ハング判定では経路障害と区別する（BMC と対象拠点の参照先で判定）、負荷で再現させない | `gpu-server/bmc.md` に「ハング判定: 経路障害と区別する」を新設 |
| `Connection reset by peer` は fail2ban ではなく FS 障害のことがある | `gpu-server/bmc.md` の「いつ使うか」 |
| VBAT（CMOS 電池）の確認 | `gpu-server/bmc.md` の「トラブルシュート」 |

### 直した古い記述

- `gpu-server/SKILL.md` のサーバ一覧表: mi25 のプラットフォーム `ROCm` → `Vulkan（既定）/ ROCm`
- `gpu-server/SKILL.md` の aws-gpu の注意事項: 「POST 中の爆音は消せていない」→ `boot-quiet.sh` の自動併走で 2,900rpm 台（ガードは維持）

### メモリの整理

| 削除したメモリ | 理由 |
|---|---|
| `feedback_pkill_self_match.md` | CLAUDE.md に移したため |
| `project_gpu01_tensor_split_nccl_hang.md` | SKILL.md に移したうえ、`butterfly` の記述が誤りだったため |
| `project_dry0_unpushed.md` | push 済みで役目を終え、plugin の注意は SKILL.md に移したため |

MEMORY.md の索引からも該当行を削除し、残ったファイルと索引が 1 対 1 で対応することを確認した。

### 検証

- 追記した数値・コマンドは出典のレポート（2026-06-13 / 06-24 / 07-04 / 07-12 / 07-17 / 07-19 / 09-14 / 09-16 / 09-18）と llama.cpp ソースで照合した
- `grep -rn butterfly .claude/skills CLAUDE.md` は「不正値」という文脈の 2 箇所だけ
- 追加した相対リンクの参照先はすべて実在する
- mi25 の GPU 配置は実機（`rocm-smi --showuniqueid`）で確かめようとしたが、`No route to host` で未確認

## 残課題

- mi25 に届くようになったら、GPU 配置（BDF ↔ Unique ID）と power cap（160W）を実機で確かめ、`gpu-server/SKILL.md` の「mi25 の注意事項」を裏付ける
- 今回対象外にした古いメモリの整理: `project_mi25_vulkan` / `project_mi25_vulkan_param_sweep`（`start.sh` のデバイス指定バグは修正済み）、`project_mi25_gpu4_pcie_dropout`（description と「当面の運用」節が矛盾）、`feedback_shell_features`（MEMORY.md の説明と本文が不一致）
- plugin cache を使う予定があるなら `install-global.sh` を再実行して更新する

## 参照レポート

- [aws-gpu01 tensor 分割の NCCL 起動ハング](./2026-09-14_142115_aws_gpu01_tensor_split_nccl_hang.md)
- [aws-gpu01 split-mode × MTP 3 腕再測定（butterfly の訂正）](./2026-09-16_103619_aws_gpu01_split_mode_mtp_3arm.md)
- [t120h-p100 ×4 で tensor 分割 + MTP を NCCL 経路で測る](./2026-09-18_155438_t120h_p100_split_mode_qwen38_27b_mtp.md)
- [mi25 c48c4×SLOT8 4 枚 24h R1](./2026-07-19_053651_mi25_c48c4_slot8_4card_24h_r1.md)
- [mi25 CMOS 電池切れ](./2026-07-12_045926_mi25_cmos_battery_reboot_loop.md)
- [mi25 ハング負荷再現キャンペーン](./2026-06-24_161909_mi25_hang_repro_load_campaign.md)
