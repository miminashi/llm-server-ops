# llama.cpp 最新版 CUDA OOM の根本対策 (t120h-p100 を -ub 4096 へ)

- **実施日時**: 2026年6月3日 06:36 (JST)
- **担当**: llm-server-ops メンテ Claude
- **報告元の障害**: opencode 機能追加ベンチ担当 Claude からの「llama.cpp master HEAD 再ビルドで CUDA OOM」報告

## 添付ファイル

- [実装プラン](attachment/2026-06-03_063647_llama_cpp_oom_regression_fix/plan.md)

## 核心発見サマリ

- **真因**: 2026-06-02 頃の llama.cpp master で **1 ubatch あたりの compute buffer 確保が大きく増加**した
  （同一 `-ub` での VRAM 比較から **推定 ~2倍**。下記「補足」の baseline 計測の留保も参照）。
  t120h-p100 (4×P100 / 各16GB) で Qwen3.6-35B-A3B / ctx=131072 / KV q8_0 を `-ub 8192` で起動すると、
  **ロード時点で VRAM 15.3/16 GiB (空き ~0.6 GiB)** まで埋まり、2回目以降の大リクエスト時に
  VMM プール (`ggml_cuda_pool_vmm::alloc` → `cuMemCreate`) が成長しきれず device 0 で OOM・クラッシュ。
- **context checkpoint は主因ではない**: checkpoint は host RAM 保存で、`--ctx-checkpoints 0` にしても
  大プロンプト(>8192 tok)の OOM は解消しなかった（→ 主因は ub=8192 の VRAM 逼迫）。ただし ub=8192 の
  極小 headroom 下では、checkpoint の作成・無効化→full reprocess に伴う追加確保が <8192 tok の
  プロンプト（報告元の 6834 tok ケース）を OOM に押し込む**寄与はありうる**。ログの
  "forcing full prompt re-processing" / "erased invalidated context checkpoint" 警告はこの経路。
- **対策 (確定)**: **t120h-p100 の default を `-ub 8192` → `-ub 4096`**（`-b 4096`）。
  ロード時 VRAM が **10.6 GiB (空き ~5.4 GiB)** に下がり OOM 解消。**eval ~40 t/s 維持**、context checkpoint も
  有効のまま（同一プレフィクスの再リクエストは ~2〜3倍高速）。ピン留めは不採用（最新 master を維持できた）。

## 前提・目的

- **背景**: 2026-06-02 に `llama-up.sh`(→`start.sh`→`update_and_build-t120h-p100.sh`) が llama.cpp を
  master HEAD へ自動 `git pull`・再ビルドした結果、Qwen3.6-35B-A3B / ctx=131072 の 2回目リクエストで
  CUDA OOM・クラッシュするようになった。報告元は `af6528e6d`(2026-06-01) へロールバックして暫定安定化していた。
- **目的 (ユーザ方針)**: **最新版 llama.cpp を調査し、それに合わせたパラメータ変更で根本対策する**。
  ピン留め (`af6528e6d` 固定) は根本解決ができなかった場合のフォールバックに留める。
- **前提条件**: t120h-p100 が利用可能でロック取得済みであること、ctx=131072 のベンチ環境を変えないこと。

## 環境情報

- **サーバ**: t120h-p100 (10.1.4.14)、NVIDIA Tesla P100 16GB ×4 (合計 64GB)、CUDA 12.9
- **モデル**: unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL (MoE 35B/3B activated)
- **起動構成**: ctx-size 131072、`--cache-type-k/v q8_0`、`--flash-attn 1`、`-ngl 99 --split-mode layer`、`--parallel 1`
- **llama.cpp**: 検証時の master HEAD `63e66fdd2` (セッション中に `4fb16eccc` から自動更新)。
  リグレッションは `af6528e6d`(2026-06-01 06:32) より後・`d5ab0834a`(2026-06-02) 以降の master 全般で発生。

## 調査・検証の経緯

### 1. ベースライン再現 (master HEAD, `-ub 8192`)

- ロード直後 VRAM: GPU0 15.76 / GPU1 15.28 / GPU2 15.16 / GPU3 15.39 GiB (各16GB、空き ~0.6 GiB)。
- 小リクエスト(17 tok)成功 → 大リクエストで **2.9秒でクラッシュ**。ログ署名は報告と完全一致:
  ```
  context checkpoints enabled, max = 32, min spacing = 256
  created context checkpoint 1 of 32 (... size = 62.813 MiB)
  W forcing full prompt re-processing due to lack of cache data (... PR#13194)
  W erased invalidated context checkpoint
  CUDA error: out of memory / current device: 0 / cuMemCreate(&handle, reserve_size, &prop, 0)
  → ggml_cuda_pool_vmm::alloc (ggml-cuda.cu:528)
  ```
- 比較: 作業開始時に稼働していた `af6528e6d` のサーバは GPU0 10.0 / GPU1 9.6 / GPU2 9.4 / GPU3 14.5 GiB だった。
  ただしこれは**ベンチ稼働後（KV 一部充填済み）のスナップショット**で、クリーンなアイドル時の値ではない
  （`af6528e6d` を最新へ checkout し直したため、同条件のアイドル実測は未取得）。アイドルなら ≤ この値のはずで、
  最新版のクリーンロード 15.3 GiB との差 **+5 GiB/GPU 以上**は保守的に見て確実だが、厳密な同条件比較ではない点に注意。

### 2. パラメータ・スイープ (EXTRA_LLAMA_OPTS で注入、ctx=131072 維持)

| 構成 | ロード時 VRAM | <8192 tok | >8192 tok (満杯 ubatch) | 判定 |
|------|--------------|-----------|------------------------|------|
| baseline `-ub 8192` | ~15.3 GiB (空き 0.6) | — | **OOM クラッシュ** | × |
| `--ctx-checkpoints 0 -ub 8192` | ~15.3 GiB (空き 0.6) | OK (4943 tok×3) | **OOM クラッシュ** | × |
| `--ctx-checkpoints 0 -b 4096 -ub 4096` | ~10.6 GiB (空き 5.4) | OK | OK (15515 tok×3) | ○ |
| **`-b 4096 -ub 4096` (checkpoint 有効)** | **~10.6 GiB (空き 5.4)** | **OK** | **OK (15515 tok×3)** | **◎ 採用** |

- 表の「—」は当方未実施セル。baseline(checkpoint 有効, ub=8192) は報告元が 6834 tok(<8192) でクラッシュを観測しており、
  当方も大プロンプトで再現済み。
- `--ctx-checkpoints 0` 単独は <8192 tok のプロンプトしか救えず（checkpoint は VRAM 主因ではない）。
- `-ub 4096` でロード時 VRAM が ~5 GiB 減り、満杯 ubatch でも headroom 内に収まって OOM 解消。
- checkpoint を **有効のまま**にすると、同一プレフィクスの再リクエスト(large#2/#3)が **~2〜3倍高速**
  (例: large#1 48s → large#2/#3 16〜17s)。よって `--ctx-checkpoints 0` は付けず `-ub 4096` のみを採用。

### 3. E2E 検証 (コミット済み start.sh 経由、EXTRA_LLAMA_OPTS なし)

`start.sh t120h-p100 unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL 131072` で起動 (`-ub 4096` 反映を確認):

| フェーズ | プロンプト | 連続3回の結果 | 再リクエスト eval | OOM |
|----------|-----------|--------------|------------------|-----|
| bench-like | 6945 tok + 600 completion | ALL_OK | large#2/#3 ~38〜40 t/s | 0件 |
| stress | 15515 tok + 600 completion | ALL_OK | large#2/#3 ~34〜35 t/s | 0件 |

- ロード時 VRAM: ~10.6 GiB/16 GiB (空き ~5.4 GiB)。`/health` 200 維持。サーバ実測 tg **~37〜43 t/s**。
- 報告元のベンチ条件 (6834 prompt + 600 completion ×3) を満たし、目標 ~40 t/s を達成。

## 実施した変更

- `.claude/skills/llama-server/scripts/start.sh`: t120h-p100 の `SERVER_OPTS` を
  `--flash-attn 1 --poll 0 -b 8192 -ub 8192` → **`-b 4096 -ub 4096`** に変更し、経緯コメントを追記。
- `.claude/skills/llama-server/SKILL.md`: サーバ別最適化パラメータ表を更新し、
  「既知の問題: `-ub 8192` の CUDA OOM (2026-06-02 master リグレッション)」セクションを追加。
- **ピン留め (PIN_REF) は導入せず**: パラメータ修正で最新 master が安定動作したため、`update_and_build-*.sh` の
  `git pull` (最新追従) は据え置き。報告元の detached `af6528e6d` ピンは master 追従へ戻した。

## トレードオフ・注意

- `-ub 4096` で prompt processing が低下する見込み（概算で ~30% 程度。pp の 693/489 t/s は出典が異なる
  概算のため目安、下記「補足」参照）。eval(tg) と ctx=131072 は不変。
- 上流が compute buffer 確保を元に戻せば `-ub 8192` へ戻して pp 速度を回復できる（SKILL.md に明記）。
- 変更は t120h-p100 の全モデル default に効く。MTP / Qwen3.5-122B の専用プロファイル上書きには影響しない。

## 再現方法

```bash
# ロック取得
.claude/skills/gpu-server/scripts/lock.sh t120h-p100

# 修正版で起動 (ctx=131072 を明示。llama-up.sh 経由なら default 131072)
.claude/skills/llama-server/scripts/start.sh t120h-p100 unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL 131072

# 6834 相当 + 600 completion を連続投入し OOM 非再発を確認
python3 /tmp/oom_repro.py 90    # bench-like (~6945 tok)
python3 /tmp/oom_repro.py 200   # stress   (~15515 tok)

# ロード時 VRAM / OOM 確認
ssh t120h-p100 "nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader"
ssh t120h-p100 "grep -c 'out of memory' /tmp/llama-server.log"
```

## 補足・調査で判明したその他の事実

- **`start.sh` 単体の ctx 既定は 65536、`llama-up.sh` 経由は 131072**（`start.sh:74` / `llama-up.sh:33`）。
  ベンチ環境(131072)で起動するには `start.sh ... 131072` の **明示指定**か `llama-up.sh` 使用が必須。
  ctx を省くと 65536 で起動してしまい、本件の OOM は ub=8192 でも再現しにくくなる（headroom が増えるため）。
  本検証はすべて 131072 明示で実施した。
- **`start.sh` は毎回 `update_and_build`(=`git pull`) を実行**するため、起動のたびに master 最新へ追従し、
  新規コミットがあれば再ビルドする。本セッション中も HEAD が `4fb16eccc` → `63e66fdd2` に自動更新された。
  `-ub 4096` の修正はこの HEAD 移動をまたいで有効であることを確認済み（最新追従＋パラメータ修正という方針通り）。
- **OOM を導入した正確なコミットは bisect 未実施**（ユーザ方針によりパラメータ対策を優先）。
  範囲 `af6528e6d`(06-01) 〜 現行 master で再現することと、`-ub 4096` で解消することを実機で確認したに留まる。
  恒久的には上流が compute buffer 確保を是正すれば `-ub 8192` 復帰で pp 速度を回復できる。
- **pp 速度の数値**（ub=8192:693 / ub=4096:489 t/s）は、693 が過去の pp512 ベンチ値、489 が本検証の
  ub=4096 サーバログ実測値で、出典が異なる概算。厳密な同一条件の ub 別 pp 比較は別途要計測。

## 関連

- 上流 issue #23371「Qwen3.6 long-context checkpoint retention raises VRAM」(checkpoint 周りの VRAM 漸増)
- llama.cpp PR#13194 (context checkpoint / SWA の full re-processing 警告)
