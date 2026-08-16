# 次セッションへの引き継ぎ

**更新**: 2026-07-25 JST (llama-finetune 検証 → PR #25428 動作確認タスクを追加)
**前回更新**: 2026-07-20 JST (prompt eval 退行切り分け完了時点)
**前回作成**: 2026-07-19 (D-2 R1 完了、LFS 導入手順記載)

## 方針変更 (2026-07-20 セッション後)

本日 2026-07-20 のセッションで、ユーザ報告「mi25 Qwen3.6-35B の prompt eval が以前 ~400 t/s → 現在 ~70 t/s」を切り分けた結果、**Vulkan は健全 / ROCm 側だけが long-context 依存で退行** ということが判明した ([2026-07-20 prompt eval 退行レポート](report/2026-07-20_013500_mi25_prompt_eval_regression.md))。

**今後の mi25 運用方針**:
- **今後は Vulkan のパフォーマンス改善に注力**する (bisect による軽微退行 PR 特定、Vulkan 側の tuning など)
- **ROCm 側の long-ctx 退行の原因調査は行わない** (Vulkan が pp / tg とも ROCm を上回るため、ROCm 側の労力対効果が低い)
- ROCm ビルド構成 (v8533 pin) は当面残置 (万一の fallback 用途、能動的な維持は不要)

## 最優先: mi25 デフォルトバックエンドを Vulkan に変更

### 目的

現状、mi25 の default backend は ROCm (hip) で、Vulkan を使うには毎回 `MI25_BACKEND=vulkan ...` を prefix する必要がある。方針変更に伴いこれを反転し、**default = Vulkan** にする (万一 ROCm を使う場合のみ `MI25_BACKEND=hip` を明示)。

### 変更対象ファイル (本日確認済み)

| ファイル | 行 | 変更内容 |
|---|---|---|
| `.claude/skills/llama-server/scripts/start.sh` | L239 | `if [ "${MI25_BACKEND:-hip}" = "vulkan" ]; then` → `if [ "${MI25_BACKEND:-vulkan}" = "vulkan" ]; then` (default 反転) |
| `.claude/skills/llama-server/server-scripts/update_and_build-mi25.sh` | L12, L21 | `MI25_BACKEND="${MI25_BACKEND:-hip}"` → `MI25_BACKEND="${MI25_BACKEND:-vulkan}"`、usage コメント `(hip 既定)` → `(vulkan 既定)` |
| `.claude/skills/llama-server/SKILL.md` | L289 | 表の見出し「mi25 (ROCm/hip, 既定)」→「mi25 (ROCm/hip, `MI25_BACKEND=hip`)」 |
| `.claude/skills/llama-server/SKILL.md` | L290 | 表の見出し「mi25 (Vulkan/RADV, `MI25_BACKEND=vulkan`)」→「mi25 (Vulkan/RADV, 既定)」 |
| `.claude/skills/llama-server/SKILL.md` | L297 | 「**既定は ROCm（hip）**。環境変数 `MI25_BACKEND=vulkan` を付けると Vulkan（RADV）に切り替わる」→「**既定は Vulkan（RADV）**。環境変数 `MI25_BACKEND=hip` を付けると ROCm（hip）に切り替わる」+ 反転理由の 1 段落 (2026-07-20 レポートを引用) |
| `.claude/skills/llama-server/SKILL.md` | L285-311 周辺 | Vulkan の特性・注意点 (KV q8_0 固定 / master 追従 pin 不要 / vulkaninfo 自動検出) を「既定」節に統合。ROCm 側は「fallback」節に整理 |
| `CLAUDE.md` | mi25 節 | mi25 の default backend が Vulkan であることを 1 行明記 (現状は明示なし、SKILL.md の記述が唯一) |

### 実施手順 (見積り 60 分)

1. **git status 確認 + プランファイル作成** (5 分)
2. **start.sh / update_and_build-mi25.sh の default 反転** (10 分)
3. **SKILL.md の記述反転** (20 分、既定/fallback の役割入れ替え + 過去 pp/tg 実測値を「なぜ Vulkan 既定にするか」の根拠として引用)
4. **CLAUDE.md 更新** (5 分、必要なら)
5. **動作確認** (15 分):
   ```bash
   .claude/skills/gpu-server/scripts/lock.sh mi25
   .claude/skills/llama-server/scripts/stop.sh mi25            # 稼働中を停止
   .claude/skills/llama-server/scripts/start.sh mi25 \
     "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072          # MI25_BACKEND なしで Vulkan 起動されるか
   .claude/skills/llama-server/scripts/wait-ready.sh mi25 \
     "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
   # 起動ログで "GGML_VK_VISIBLE_DEVICES=0,1,2,3 (4枚)" が出れば Vulkan 既定に切替できたこと
   # フォールバック確認: MI25_BACKEND=hip .claude/skills/llama-server/scripts/start.sh mi25 ...
   ```
6. **レポート作成** (5 分、変更内容 + 動作確認結果を短くまとめる) → INDEX.md に 1 行追記

### 成果物

`report/<日付>_mi25_default_backend_switch_to_vulkan.md` として、変更差分 + 動作確認結果 + 方針変更の背景を記載。

## 追加タスク (2026-07-25 セッションで発生): llama.cpp PR #25428 の CPU-only 検証と結果投稿

> **移管済み (2026-07-25)**: 本タスクは独立プロジェクト `~/projects/llama.cpp-fine-tuning` へ移管した。以降の作業は同プロジェクトで行い、本セクションは経緯の記録として残す。移管時点の到達点・環境・残課題（次の一手は PR #21924 の独立検証）は同プロジェクトの `report/2026-07-25_223555_project-handover-from-llm-server-ops.md` を参照。なお PR #25428 の CPU-only 検証は 2026-07-25 に完了済み（[レポート](report/2026-07-25_054901_llama-cpp-cpu-finetune-pr25428-verify.md)）。

### 背景

2026-07-25 セッションで mmns-cpu-llm (CPU-only, 94 vCPU / 62 GiB RAM / GPU なし) 上で `llama-finetune` の動作確認を試みたが、現行 master (b7542) は modern LLM (Llama/Qwen 系 dense) 全てで backward の `GGML_ASSERT` で abort。既知回帰 Issue [#18805](https://github.com/ggml-org/llama.cpp/issues/18805) と一致 (KV cache 書込みが `ggml_set_rows` に切替わり backward の許可 op に含まれない)。詳細と再現手順は本セッションのレポート [2026-07-25 llama-cpp-cpu-finetune-broken](report/2026-07-25_045111_llama-cpp-cpu-finetune-broken.md) にまとめ済。

**修正 PR の状況**: upstream で PR [#25428](https://github.com/ggml-org/llama.cpp/pull/25428) が Draft (2026-07-08〜) として存在。`LLM_GRAPH_TYPE_TRAIN` を導入し訓練時は KV cache を経由しない no-cache attention 経路に切り替える本質的な修正。作者は Qwen2.5-14B-Instruct で「複数 epoch 収束」まで確認したと述べているが、**HW 環境は不明・14B のみ・具体的な `llama-finetune` 実行コマンドの記載なし**。レビュー未着手、Draft のまま停滞中。

### 我々が持ち込める差別化ポイント

- **CPU-only + QEMU 94 vCPU 環境**での独立再現 (作者は恐らく GPU)
- **AVX-512 のみ / AMX / AVX-VNNI / BF16 なし / BLAS OFF** という特殊な CPU flag プロファイル
- **Qwen2.5-0.5B** の小型モデルでの再現 (作者の 14B より遥かに軽量、~30 分で 1 epoch 回せる)
- **before/after の wiki.test.raw PPL** — 独立した外部評価尺度で「収束した」の定量証拠
- **loss curve PNG** (前回セッションで plot_loss.py を作成済み、流用可)

### 実施プラン (推定 1.5〜2 時間)

1. **PR ブランチを worktree で fetch + build** (10〜15 分)
   ```bash
   ssh mmns-cpu-llm '
     cd ~/llama.cpp &&
     git fetch origin pull/25428/head:pr-25428 &&
     git worktree add -f ~/llama-worktrees/pr-25428 pr-25428 &&
     cd ~/llama-worktrees/pr-25428 &&
     cmake -B build -DGGML_OPENMP=ON -DGGML_CUDA=OFF -DGGML_VULKAN=OFF -DGGML_BLAS=OFF -DCMAKE_BUILD_TYPE=Release &&
     cmake --build build --target llama-finetune llama-perplexity llama-completion --config Release -j 32'
   ```
2. **Qwen2.5-0.5B baseline PPL 取得** (今回未取得, ~10 分)
   ```bash
   ssh mmns-cpu-llm '
     ~/llama-worktrees/pr-25428/build/bin/llama-perplexity \
         -m ~/finetune-lab/gguf/qwen2.5-0.5b.f32.gguf \
         -f ~/finetune-lab/data/wikitext-2-raw/wiki.test.raw \
         -c 512 -b 512 -t 64 --numa distribute \
         2>&1 | tee ~/finetune-lab/logs/pr25428_ppl_qwen_before.log'
   ```
3. **`llama-finetune` を Qwen2.5-0.5B + wikitext-2 で 1 epoch 実行** (~30〜60 分、`-fa off` 必須)
   ```bash
   ssh mmns-cpu-llm '
     cd ~/finetune-lab &&
     nohup ~/llama-worktrees/pr-25428/build/bin/llama-finetune \
         -m gguf/qwen2.5-0.5b.f32.gguf \
         -f data/wikitext-2-raw/wiki.test.raw \
         -o out/qwen2.5-0.5b-ft-pr25428.f32.gguf \
         -c 512 -b 512 -ub 512 -fa off \
         -t 64 --numa distribute \
         -epochs 1 -lr 1e-5 -opt adamw \
         > logs/pr25428_ft_qwen.log 2>&1 & disown'
   ```
4. **学習後 PPL + 生成の比較評価** (~10 分)
5. **loss curve PNG 生成 + 結果を短いレポートにまとめる** (~15 分、`scratchpad/plot_loss.py` を流用)
6. **PR #25428 に投稿する英語コメント文を用意**、投稿方法についてはユーザ判断 (下記「未解決の投稿方針」参照)

### 前セッションからの残置物 (即使える状態)

**mmns-cpu-llm 上 (SSH ですぐ入れる)**:
- `~/finetune-lab/venv/` — Python 3.12 venv (torch 2.6.0+cpu / transformers / gguf 一式、1.1 GB)
- `~/finetune-lab/gguf/smollm2-135m-instruct.f32.gguf` (538 MB, SmolLM2-135M-Instruct F32)
- `~/finetune-lab/gguf/qwen2.5-0.5b.f32.gguf` (1.98 GB, Qwen2.5-0.5B F32) — **PR 検証の主対象**
- `~/finetune-lab/data/wikitext-2-raw/` (wiki.{train,valid,test}.raw、13 MB)
- `~/finetune-lab/logs/ppl_smollm_before.log` (SmolLM2 baseline PPL = 18.6775 ± 0.14304)
- `~/finetune-lab/logs/gen_smollm_before.log` (baseline 生成 "Barack Obama was born in 1961.")
- `~/llama-worktrees/finetune-b6290/` (patch 済み検証用 build、参考として残置)
- `~/llama-worktrees/finetune-b6305/` (`LLAMA_SET_ROWS=0` 検証用、参考)
- ディスク空き: 開始 23 GB → 16 GB (PR 検証で + ~5 GB 使う想定、余裕あり)

**ローカルリポジトリ**:
- `report/2026-07-25_045111_llama-cpp-cpu-finetune-broken.md` — 前セッションのレポート (背景 / 環境 / 再現手順 / 11 系統の実験表 / loss 発散 PNG)
- `report/attachment/2026-07-25_045111_llama-cpp-cpu-finetune-broken/plot_loss.py` — loss curve プロット用スクリプト (PR 検証結果にも流用可)
- メモリ [`project_llama_cpp_finetune_broken.md`](../.claude/projects/-home-ubuntu-projects-llm-server-ops/memory/project_llama_cpp_finetune_broken.md) — 事象の要約

### 未解決の投稿方針 (次セッション開始時にユーザに確認)

- 投稿先: GitHub PR [#25428](https://github.com/ggml-org/llama.cpp/pull/25428) のコメント
- ローカルの `gh` CLI は未認証 (前セッション実行時 `gh auth login` 要求)。二択:
  - **(a)** `~/.config/gpu-server/.env` に `GH_TOKEN` を追加してユーザに登録してもらう → Claude が `gh pr comment` で自動投稿
  - **(b)** Claude はコメント文 (英語) を用意するのみ、ユーザが GitHub Web / 手元 CLI で投稿
- 匿名性: 投稿は `miminashi` アカウントから (HF token と同一)。「Claude Code で自動検証」を明記するかは要判断

### 想定される結果パターン

- **Qwen2.5-0.5B が収束**: PR #25428 の効果を CPU-only で独立確認、他 arch への展開が望まれる旨をコメント (positive)
- **収束するが速度が遅い**: CPU では実用にならないという別知見 (中立)
- **crash or 発散**: 特定の CPU 環境で追加問題あり、環境詳細を添えて報告 (negative だが有用)

いずれのパターンも PR コメントとして意義があるので、結果によらず投稿する方針とする。

### 参照

- [PR #25428 — qwen2 : use no-cache attention path for training graphs](https://github.com/ggml-org/llama.cpp/pull/25428) (本タスクの検証対象)
- [PR #21924 — fix: llama-finetune backward pass crashes](https://github.com/ggml-org/llama.cpp/pull/21924) (別アプローチ、scheduler crash 修正のみ、参考)
- [Issue #18805 — llama-finetune broken on modern transformers](https://github.com/ggml-org/llama.cpp/issues/18805) (元 issue、closed 表示だが fix は未 merge)
- [2026-07-25 前セッションのレポート](report/2026-07-25_045111_llama-cpp-cpu-finetune-broken.md)

---

## 今回セッションで完了した対応

### 2026-07-25: llama.cpp CPU fine-tune 検証 (mmns-cpu-llm) — 現状 broken を確定

- 詳細: [2026-07-25 llama-cpp-cpu-finetune-broken レポート](report/2026-07-25_045111_llama-cpp-cpu-finetune-broken.md)
- mmns-cpu-llm 上に環境構築 (venv, SmolLM2-135M / Qwen2.5-0.5B の F32 GGUF, wikitext-2-raw)、`llama-perplexity` / `llama-completion` によるベースラインまで確認
- `llama-finetune` は master (b7542) で SET_ROWS backward assert により abort、Qwen でも再現 (model 非依存)
- 古い commit まで戻して `LLAMA_SET_ROWS=0` + `graph_max_nodes` 8x→32x patch を当てるとようやく起動、しかし全 optimizer / 学習率で loss 発散、gradient 計算そのものが broken と判定
- **本セッション終了時点で mmns-cpu-llm 側の実験環境は残置** (次セッションで PR #25428 検証にそのまま流用)
- 上記「追加タスク」節で PR #25428 検証を次セッションに引き継ぎ

### mi25 prompt eval 退行の切り分け + 主対応 (Vulkan 切替)

- 詳細: [2026-07-20 prompt eval 退行レポート](report/2026-07-20_013500_mi25_prompt_eval_regression.md)
- Phase A で PCIe / VBIOS / 温度 / ROCm ドライバ / 物理配置 / ROCm HEAD を全部棄却
- Phase B/C で ROCm と Vulkan の pp/tg を 1k/32k/100k で実測、Vulkan が pp/tg とも ROCm を上回る現状を確認
- **本セッション終了時点で llama-server は Vulkan で稼働中**、ユーザは即座に高い pp/tg を享受できる状態
- 停止したい場合は `.claude/skills/llama-server/scripts/stop.sh mi25`
- 起動し直す場合は `MI25_BACKEND=vulkan .claude/skills/llama-server/scripts/start.sh mi25 "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072`

## 未完タスク (優先度順)

### 中優先

1. **BMC 時刻同期** (BMC Web UI 経由): BMC は 2015-01-02 開始のまま、`ipmitool sel time set` は "Specified time could not be parsed" エラーで失敗中 (2026-07-17 BIOS 復旧レポートの副次発見 2/9 参照)
   - 対処: BMC Web UI (https://10.1.4.7/) → Configuration → Date and Time → Timezone=Asia/Tokyo + NTP Enable (Server=ntp.nict.jp) → Save
   - 効果: BMC SEL のタイムスタンプが JST 正確化 → 今後の fault 相関分析の基盤になる

2. **Vulkan パフォーマンス改善** (方針変更の帰結、優先度は着手時に個別判断):
   - **Vulkan 32k / 100k の -9% / -12% 誤差要因の bisect** — 過去 `f3e182816` (2026-06-17) → 現行 `ded1561b4` (v9812) で軽微退行 PR が挟まった可能性。特定できれば Vulkan build にも pin を導入 (`PINNED_COMMIT_VULKAN`)
   - `git log --oneline f3e182816..ded1561b4 -- 'ggml/src/ggml-vulkan/**' 'ggml-vulkan*'` で候補列挙、代表的な数点を checkout してビルド + 32k pp 実測で bisect 縮小
   - Vulkan 側の tuning (ub / batch / FA workspace など、当時「ub 非依存」と結論した特性が現行 master でも成立するか再確認)

### 低優先

3. **Fable D-2 R2 追試** (追加 N ≥ 100 で累計 N ≥ 200、任意): SA SLOT6 (1.36%) 水準の完全棄却、SA SLOT8 (0/221) との統計比較を確立
   - 現状: N=99 では SA SLOT6 (1.36%) は棄却できず (Fisher p=0.3561)
   - R2 で N=200 到達 → SA SLOT6 水準の Fisher p ≒ 0.06 (10% 有意)、fault=0 なら SLOT8 SA (0/221) との完全対称性を確立
4. **Fable D-3 fault シグネチャ台帳の一次データ再監査** (サーバ時間ゼロ): ディスク上の既存ログのみで完結
   - 対象: stand_alone_24h の 3 件目 (uptime 43173) の由来ラベル vs 算術の緊張関係、fault アドレス (0x33000 vs 0x100000000) の体系的解析
5. **Fable D-4 VBIOS / RAS カウンタ 4 枚比較** (サーバ数分): 4 枚間で hidden 個体差 (VBIOS 版数以外の hw counter) がないかを確認
6. **VBAT 監視の運用整備** (cron 日次記録 + 閾値通知):
   - VBAT = 2.794V が `ok` 域維持だが新品 3.0V より 6.87% 低い、将来の低下を早期検知する仕組みが未実装
   - 対処: `ipmitool sensor | grep VBAT` を cron で日次記録 → 閾値 2.5V 割れで discord-notify 経由通知

### 打ち切り (今後行わない)

- **ROCm long-ctx 退行の原因調査**: 2026-07-20 セッションで PCIe / VBIOS / 温度 / ROCm ドライバ / 物理配置 / ROCm HEAD を棄却、残変数は kernel/DKMS / 負荷時 DPM / GPU 個体組合せ差の 3 つに絞られていたが、方針変更 (Vulkan 既定化) に伴い着手しない。ROCm 実行が必要になった場合は `MI25_BACKEND=hip` で fallback するのみ

## 初動手順 (次セッション開始時)

1. **git 状態確認** — 直近 commit を確認、以下の M は前セッション残および LFS 遡及の産物なので**触らない**:
   ```bash
   git status
   git log --oneline -3
   # 期待する直近 commit:
   #   91040468 report: mi25 Qwen3.6-35B pp 退行の切り分け (ROCm 長 ctx で発現・Vulkan 健全)
   #   2bd5a9f3 report: mi25 ttyd 経由 llama-server ログ閲覧を開通 (前セッション積み残し)
   #   9abcd551 chore: LFS で attachment 配下の .log/.png/.jsonl を管理 (将来分のみ)
   ```
   **触らない対象** (2026-07-20 時点で意図的に放置した M / ??):
   - `.gitignore` の M (1 ファイル) — 前セッションが `NEXT_SESSION.md` を再び追跡対象に戻す変更 (`# NEXT_SESSION.md` にコメントアウト)。追跡再開の是非はユーザ判断待ち
   - `report/attachment/2026-0[4-6]*/` 配下の M (5090 ファイル) — `.gitattributes` の LFS pattern に既存ファイルが遡及マッチしただけの検出、コミットすると LFS pointer に置き換わって履歴が混在するため放置。前セッション方針「将来分のみ LFS」と整合
   - `NEXT_SESSION.md` の ?? — 現在 `.gitignore` で除外中

2. **ロック取得** (作業実施のため必須):
   ```bash
   .claude/skills/gpu-server/scripts/lock-status.sh
   .claude/skills/gpu-server/scripts/lock.sh mi25
   # 前回終了時に Vulkan で稼働状態を維持したままロック解放したが、時間経過で停止している可能性あり
   ssh mi25 "ps aux | grep llama-server | grep -v grep"
   curl -sf http://10.1.4.13:8000/health && echo   # {"status":"ok"} なら稼働中
   # 動作確認 (実施手順 5) は稼働状態に関わらず stop.sh で明示停止 → 反転後の start.sh で確認する
   ```

3. **mi25 デフォルトバックエンドを Vulkan に変更** (上記「最優先」節に従って実施)、または ユーザ判断で次のタスク (BMC 時刻同期 / Vulkan bisect / D-2 R2 / D-3 / D-4 / VBAT 監視) を選択

### mi25 の現状 (2026-07-20 03:30 時点)

- **稼働中**: llama-server **Vulkan** で稼働 (Qwen3.6-35B-A3B UD-Q4_K_XL, ctx 131072, 4 枚 = `GGML_VK_VISIBLE_DEVICES=0,1,2,3` 自動検出)
- **エンドポイント**: `http://10.1.4.13:8000/v1` (実測 pp 1k 541 t/s / 32k 372 t/s / 100k 191 t/s / tg 39.5 t/s)
- **GPU 物理配置**: SLOT2=c3164 / SLOT4=448c4 / **SLOT8=c48c4** / SLOT6=a48e4 (変更なし)
- **BIOS 設定**: 2026-07-17 復旧設定 (MMIOHBase=3TB / MMIO High=512GB / Boot Order UEFI) を維持
- **VBAT**: 2.794V (`ok` 域維持、監視継続要)
- **BMC 時刻**: 2015-01-02 開始のまま (未対処、次セッションで恒久設定推奨)
- **運用方針**: `MI25_BACKEND=vulkan` で起動 (`GGML_VK_VISIBLE_DEVICES=0,1,2,3` 4 枚 64GB) が pp/tg とも ROCm を上回る最適解。**次セッションで default backend を反転する**ため、それ以降は `MI25_BACKEND` prefix なしで Vulkan 起動される予定
- **ロック**: 本セッション終了時に解放済 (次セッションで再取得必要)
