# GLM-5.3-Flash 最新コミットの実機確認（2026-09-10）

## Context

前回レポート `report/2026-09-06_234319_glm53flash_pr27773_vs_27754_depth.md` で、GLM-5.3-Flash 対応の
競合 2 実装（#27773 / #27754）を aws-gpu01+02 の 13x Tesla P100 RPC 分散で深さ 5 段階まで直接比較し、
**「どちらが速いかは深さで反転する」**（浅いと #27754 が pp +28%、109,917 tok では #27773 が tg +30%）
ことを実測した。残課題として「#27754 が深さで落ちる理由の切り分け」「#27754 の MTP を深文脈で測る」を残した。

今回の依頼は「その続きで、最新版のコミットを実機確認。既にマージされている PR もあるかもしれない」。
**上流調査の結果、マージは 1 件もなく、代わりに前回の残課題に正面から答える新実装が出現していた**ので、
それを実機で確かめるのが本セッションの目的になる。

ユーザ確認済み: 範囲は「**#27754 最新 + smalinin フォーク**」、**電源投入は許可**（作業後は前回同様シャットダウン）。

---

## 上流調査の結果（2026-09-10 実施・確定済み）

### マージ状況 — **GLM-5.3-Flash はまだ 1 つもマージされていない**

- 本家 master HEAD = `434ddbbc0e`（2026-09-09）。`src/models/` に **`glm5next.cpp` は存在しない**
- master の `src/llama-memory-hybrid-idx.{cpp,h}` は **qwen4exp (#27742) 由来**で GLM とは無関係（紛らわしいので注意）
- 関連 PR は 4 本すべて OPEN: #27752（eauchs、`dirty`、09-03 停止）/ #27754 / #27773 / #27917（draft・`dirty`、09-02 停止）

### 各 PR の HEAD

| PR | 前回検証時 | 現在 | 差分 |
|---|---|---|---|
| **#27773** | `8134115f88` | **`8134115f88`（不変）** | **1 コミットも進んでいない**。master から 70 コミット遅れ。09-09 に fairydreaming / CISC のレビューコメントのみ |
| **#27754** | `629b505528` | **`d94f44e79a`** | `b9b8207fcf`(09-07) / `2af9da2d5e`(09-10 Merge upstream master) / `d94f44e79a`(09-10)。**master と完全同期（behind 0）** |
| **#27917** | dirty | `5b8593b545`（09-02） | 実質変化なし |

**#27754 の実質的変更は 2 つだけ**:
1. **上流 master 約 90 コミットの取り込み**（09-04 → 09-10）。CUDA の `fattn-mma-f16.cuh`(48/48)・
   `fattn.cu`(102/98)・`mmq`/`mmvq`/`vecdotq` が動いている。とくに `b74f590eaf`「fix divergent barrier
   in f16 flash attention (#27870)」は `-fa on` の本環境に直撃しうる
2. `src/models/glm5next.cpp` の **1 行**: `ggml_mul_mat_set_prec` → `ggml_prec_set_acc`
   （上流 `5a6caa05fc` の API 改称追従。**glm5next のロジックは無変更**）

→ **#27754 最新の測定 ＝「上流 master 90 コミットが sm_60 / IQ4_XS / 深文脈でどう効くか」の測定**になる。
前回 F1/F2 がバイト再現可能なベースラインとして残っているのできれいな A/B になる。

### ★ 第 3 の実装系統 smalinin フォーク（今回の主目的）

09-09 に #27754 スレッドで smalinin が [`smalinin/llama.cpp` の `my_glm53_flash`](https://github.com/smalinin/llama.cpp/tree/my_glm53_flash) を告知。
**#27754 (`glm5next/upstream`) を土台に本家 master `465e49b9ce`（前回セッション終了時に両機を置いた master と同一コミット）へポート**したもの。
HEAD `271235bb63`（2026-09-10 01:16 UTC）。`GLM5NEXT_LOCAL_CHANGES_EN.md` に全 40 コミットの説明あり。

**前回の実測に正面から刺さる内容**:
1. **長文脈での sparse attention コスト削減**（decode を選択プール＋不完全テールの compact 集合に限定）← 「#27754 は 108k で tg 維持率 70.6%」の直接の対策
2. **完了プールの indexer key の永続キャッシュ** ← 前回「#27773 の pooled cache が深さに強い」と見た機構と同種
3. **完全な MTP 対応**（prompt reuse / multimodal / multi-slot）
4. **indexed attention の自動切替閾値変更**: prefill batch ≥4096 tok という条件をやめ、**KV が 32768 tok に達するまで dense FA を保つ** ← 前回測った反転点をちょうど跨ぐ変更
5. CUDA fused MoE down reduction（IQ4_XS で 4090 27-39% / 3090 14-18% と主張。**sm_60 で効くかは未知**。前回の Sparse FA が sm_60 で効かなかった前例あり）

**最大の利点: 環境変数で A/B できる（再ビルド不要）**。ソース上の実在も確認済み:

| 環境変数 | 効果 | 実装箇所（確認済み） |
|---|---|---|
| `LLAMA_GLM5_INDEXED_ATTN` | `0`=dense 固定 / `2`=indexed 強制 | `src/llama-kv-cache-kpool.cpp:40` |
| `LLAMA_GLM5_POOL_CACHE=0` | 完了プール key の永続キャッシュ無効化 | 同 `:1081`, `src/llama-graph.cpp:3705` |
| `GGML_CUDA_MOE_DOWN_REDUCE=0` | fused expert-down reduction 無効化 | CUDA 側 |
| `LLAMA_GLM5_KPOOL_EXPAND=0` | fused pool-index expansion 無効化 | `src/models/glm5next.cpp:38` |
| `LLAMA_MTP_DEVICE_DRAFT=0` / `LLAMA_MTP_ADAPTIVE=0` / `LLAMA_GLM5_MTP_TOPK_SHARE=0` | MTP 各機構 | `src/llama-context.cpp:1355` ほか |

### ビルドフラグの注意

上流 `5a4d0fecae`（09-09）で `GGML_CUDA_FA_ALL_QUANTS` は `GGML_CUDA_FA_QUANTS` に改称され、旧フラグは
**deprecated alias（警告付きで `=all` 相当）**になった。#27754 最新はこれを含み、smalinin ブランチ
（master `465e49b9ce` ベース）は旧フラグのまま。
→ **既存 `update_and_build-aws-gpu0N.sh` はそのまま使う**（警告が出るだけ）。前回との比較可能性を
優先し、`GGML_CUDA_FA_QUANTS` への絞り込み（ビルド短縮）は**やらない**。

### サーバ現況（2026-09-10 確認）

- aws-gpu01 / aws-gpu02 とも **電源 OFF**（`bmc-power.sh status` = `System Power: off`）。ロックは SSH 不通で未確認
- 前回作業後: 両機の llama.cpp は master `465e49b9c`、aws-gpu01 は `--ui-mcp-proxy` 404 修正パッチ込み、
  `~/patches/2026-09-06-local.patch` 残置。モデルは `UD-IQ4_XS/`（146 GiB）ほか残置
- **電源 OFF なので page cache は消えている → 初回ロードは必ず cold（約 11 分）**

---

## 測定計画

### 対象と GGUF

| 構成 | ブランチ / コミット | GGUF（shard 1） | 前回の比較相手 |
|---|---|---|---|
| **G** | #27754 `d94f44e79a` | `~/models/GLM-5.3-Flash-GGUF/UD-IQ4_XS/`（配布元メイン） | **F1 / F2**（`629b50552`） |
| **H** | smalinin `my_glm53_flash` `271235bb63` | 同上（#27754 派生のため） | G および F1/F2 |

**#27773 は再ビルドしない**。HEAD が 1 コミットも動いておらず、前回 E1/E2 が
「前日の応答とバイト単位で一致・109,917 tok の pp/tg が小数点まで同値」と実証済みなので、
そのまま参照値として使う。

### 起動構成と試行（プロンプトは 09-05 セッションの添付をバイト同一で流用）

| # | 構成 | ctx | プロンプト | 合言葉 |
|---|---|---|---|---|
| G1-1〜4 | #27754 最新 | 32768 | short(16) / needle_7k(7,349) / needle_11k(11,338) / needle_29k(28,390) | 撫子2841 竜胆6795 / 山茶花6104 木蓮3357 / 桔梗5063 椿9174 |
| G2-1 | #27754 最新 | 131072 | needle_108k(109,917) | 蒲公英3612 山吹7429 |
| H1-1〜4 | smalinin 既定 | 32768 | 同 G1 | 同上 |
| H1-A | smalinin `LLAMA_GLM5_POOL_CACHE=0` | 32768 | needle_29k | 桔梗5063 椿9174 |
| H1-B | smalinin `LLAMA_GLM5_INDEXED_ATTN=2` | 32768 | needle_29k | 同上 |
| H1-C | smalinin `GGML_CUDA_MOE_DOWN_REDUCE=0` | 32768 | needle_29k | 同上 |
| H2-1 | smalinin 既定 | 131072 | needle_108k | 蒲公英3612 山吹7429 |

各試行で記録するもの（前回と同一）: pp / tg (t/s)、`n_prompt` / `n_pred`、content と reasoning_content の
文字数と全文、合言葉 2 か所の正誤、崩壊検出（同一文字 5 連・4-gram）、VRAM 使用量と最小空き（両機）、
モデルロード所要、`unused tensor ... -- ignoring` の件数、`graph_reserve` 警告の有無。

**時間が押した場合の削り順**: H1-C → H1-B → H1-A（H2-1 と G2-1 の 108k は残す。深文脈が本題のため）。

---

## 実施手順

### 1. 電源投入と準備（ユーザ許可済み）

```bash
cd /home/ubuntu/projects/llm-server-ops
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 on
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu02 on
# boot-quiet.sh が自動併走する（2,900rpm 台に収まる実績）
# SSH 到達を待つ（POST 約 146 秒 + OS 起動）
```
- SSH 到達後、**ロックは電源投入の後に取る**（再起動で `/tmp` が飛ぶため）:
  `lock.sh aws-gpu01` / `lock.sh aws-gpu02`
- 100GbE の確認: `ip -br addr show`（`192.168.100.1/2`。netplan で永続化済み）
- **aws-gpu02 の SEL 基準値を記録**: `ipmitool sel elist` の `Uncorrectable ECC` 件数（前回終了時 **11 件**）

### 2. ビルド準備

```bash
# aws-gpu01 のローカル修正（--ui-mcp-proxy 404 修正）を退避
ssh -n aws-gpu01 "cd ~/llama.cpp && mkdir -p ~/patches && git diff > ~/patches/\$(date +%F)-local.patch \
  && git stash push -m pre-glm5next-5 -- tools/server/server-http.cpp"

scp .claude/skills/llama-server/server-scripts/update_and_build-aws-gpu01.sh aws-gpu01:~/llama.cpp/update_and_build.sh
scp .claude/skills/llama-server/server-scripts/update_and_build-aws-gpu02.sh aws-gpu02:~/llama.cpp/update_and_build.sh
ssh -n aws-gpu02 "cd ~/llama.cpp && sed -i 's/-- -j \$(nproc)/-- -j 20/' update_and_build.sh"
```

### 3. 測定資材の配置

前回と同じ `run_cfg.sh` / `ask.sh` / `measure.sh` / `check.py` と 5 本のプロンプト JSON を
`report/attachment/2026-09-05_204557_glm53flash_pr27773_sparse_fa_multistream/` から scp する。

**追加で 1 本だけ新規作成が必要**: `run_cfg.sh` は起動コマンドに `env NVIDIA_TF32_OVERRIDE=0` を
ハードコードしており環境変数を足せないため、**`EXTRA_ENV` を受け取る `run_cfg2.sh`** を派生させる
（`env NVIDIA_TF32_OVERRIDE=0 $EXTRA_ENV ./build/bin/llama-server ...` の 1 行差）。
G / H の既定測定も `run_cfg2.sh`（`EXTRA_ENV` 空）で行い、A/B と同一経路にそろえる。
新規スクリプトはレポート添付に含める。

### 4. 構成 G — #27754 最新 `d94f44e79a`

```bash
for S in aws-gpu01 aws-gpu02; do
  ssh -n $S "cd ~/llama.cpp && git fetch origin pull/27754/head:pr27754-new -f && git checkout pr27754-new && git rev-parse HEAD"
done   # 両機で d94f44e79a... が一致することを必ず確認
# 各機で ./update_and_build.sh --no-pull --force をバックグラウンド実行し、pgrep で完了待ち
# → build 番号と commit を llama-server ログで確認（両機一致が必須）
```
- G1: `run_cfg2.sh G1 <UD-IQ4_XS/shard1> 32768 4096` → `measure.sh` 4 本
- G2: `run_cfg2.sh G2 <同> 131072 4096` → 108k は `ask.sh` で投げて `.done` を待つ（65〜70 分）

### 5. 構成 H — smalinin `my_glm53_flash` `271235bb63`

**PR ではないので remote 追加が要る**:
```bash
for S in aws-gpu01 aws-gpu02; do
  ssh -n $S "cd ~/llama.cpp && git remote add smalinin https://github.com/smalinin/llama.cpp.git 2>/dev/null; \
             git fetch smalinin my_glm53_flash && git checkout -B smalinin-glm53 smalinin/my_glm53_flash && git rev-parse HEAD"
done   # 両機で 271235bb63... 一致を確認 → 両機ビルド
```
- H1: `run_cfg2.sh H1 <UD-IQ4_XS/shard1> 32768 4096` → `measure.sh` 4 本
- H1-A/B/C: `EXTRA_ENV="LLAMA_GLM5_POOL_CACHE=0"` 等で起動し直し、**needle_29k のみ**を流す
- H2: ctx 131072 で 108k 1 本

**リスクと対処**:
- **GGUF が合わない可能性**: smalinin は #27754 派生なので `UD-IQ4_XS/`（メイン shard）を使う。
  `head_count_kv` で弾かれたら `UD-IQ4_XS-nopatch/` に切り替えて再試行する
- **ビルドが通らない可能性**: 個人フォークなので sm_60 / CUDA 12.0 でのビルド実績が無い。
  失敗したらログを保全し、H を諦めて G の結果と上流調査でレポートをまとめる（G だけでも依頼は満たす）
- **VRAM 不足**: 前回 #27754 / ctx 131072 は aws-gpu02 の最小空きが **162 MiB** しかなかった。
  smalinin は MTP 用の追加確保があるため OOM しうる。その場合は `-ub 512` に落として再試行し、
  条件差をレポートに明記する

### 6. 後片付け（前回と同一）

```bash
.claude/skills/llama-server/scripts/stop.sh aws-gpu01      # llama-server → RPC の順。逆は不可
.claude/skills/llama-server/scripts/rpc-down.sh aws-gpu02
for S in aws-gpu01 aws-gpu02; do ssh -n $S "cd ~/llama.cpp && git checkout master && git pull --ff-only"; done
ssh -n aws-gpu01 "cd ~/llama.cpp && git stash pop"         # --ui-mcp-proxy 404 修正を復元
# 両機で update_and_build.sh --no-pull --force を流し直す
# SEL の ECC 件数を再確認（11 件から増えていないこと）
.claude/skills/gpu-server/scripts/unlock.sh aws-gpu01
.claude/skills/gpu-server/scripts/unlock.sh aws-gpu02
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu01 soft   # ACPI グレースフル
ALLOW_FAN_NOISE=1 .claude/skills/gpu-server/scripts/bmc-power.sh aws-gpu02 soft
```

### 7. レポート作成（REPORT.md 準拠・必須）

- ファイル: `report/<TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S>_glm53flash_latest_commits_smalinin.md`
- タイトルは平易な日本語 50 字以内。数値はタイトルに入れず「核心発見サマリ」へ
- **`## 概要`** を H1 直下に置き、5〜8 段落の通読できる平易な日本語で書く
- **`## 核心発見サマリ` の冒頭に PNG を画像埋め込み**。前回の `mkfig.py` は数値ハードコードなので、
  今回の G / H を加えた 4 系列（#27773 参照値 / #27754 旧 / #27754 新 / smalinin）で書き換えて流用する
- `## 添付ファイル` に `plan.md`（本ファイルをコピー）、`run_cfg2.sh` ほかスクリプト、`log_*.log`、`r_*.json` をリンク
- `report/INDEX.md` に 1 行追加

---

## 異常時の対応

- **SSH / ping 不通（ハング）を検知したら、電源リセットの前に必ず**
  `bmc-screenshot.sh <server> <out.png>` で KVM 画面を保全し、**あわせて `ipmitool sel elist` で SEL を読む**。
  `journalctl` が空でも SEL には残る（2026-09-05 の aws-gpu02 の実例）。保全後に `bmc-power.sh` で復旧
- aws-gpu02 の `P2_DIMME1` は故障中。BIOS `Patrol Scrub` を Disable にして回避済みなので、
  **`Restore Optimized Defaults` は絶対に実行しない**
- ビルドは 1 台につき 1 本だけ（同じ `build/` に 2 本走らせると `nvcc fatal: Could not open options file` で壊れる）
- `pgrep -f 'bin/llama-server'` は ssh 越しだと必ず真になる → `[b]in/llama-server` と書く

---

## 検証（この作業が成功したと言える条件）

1. **両機のコミットが一致している**こと（`git rev-parse HEAD` と llama-server ログの `build NNNN, commit XXXX` の両方で確認）
2. **G が F1/F2 と比較可能**であること — 同じプロンプト・同じ起動オプション・同じ GGUF で、
   pp / tg が数値として並べられ、content の一致／不一致が判定できている
3. **全試行で合言葉 2 か所が正答**し、崩壊検出が 0 であること（品質退行がないことの確認）。
   退行した場合はそれ自体が発見なので、応答全文を添付して報告する
4. **H の A/B で、無効化した機構が実際に効いていることが数値で見える**こと
   （少なくとも `LLAMA_GLM5_POOL_CACHE=0` で 28,390 tok の pp か tg が動く／動かないが確定する）
5. **aws-gpu02 の SEL `Uncorrectable ECC` が 11 件から増えていない**こと
6. 後片付け後、両機が master で再ビルド済み・ロック解放済み・電源 OFF になっていること
